import re
from collections import defaultdict
from typing import Any

from sqlalchemy import or_

from backend.models import EvidenceChunk, LegalSourceDocument
from backend.services.legal_reference_service import (
    enrich_chunk_references,
    extract_last_heading,
    extract_legal_references,
    is_polluted_reference,
    strip_gazette_headers,
)


MIN_RELEVANCE_SCORE = 0.18
MAX_SQL_KEYWORDS = 12
_TOKEN_PATTERN = re.compile(r"[^\s\.,;:!?()\[\]{}\"'/\\|<>@#$%^&*+=~`–—-]+")
_STOP_WORDS = {
    "about", "after", "also", "an", "and", "are", "as", "at", "be", "by",
    "can", "did", "do", "does", "explain", "for", "from", "have", "how",
    "in", "into", "is", "it", "its", "law", "legal", "me", "my", "of",
    "on", "or", "please", "say", "tell", "that", "the", "this", "to",
    "under", "was", "what", "when", "where", "which", "who", "will",
    "with", "would",
}
_GENERIC_LEGAL_TERMS = {
    "act", "acts", "article", "articles", "clause", "clauses",
    "notification", "notifications", "order", "orders", "policy",
    "provision", "provisions", "regulation", "regulations", "rule",
    "rules", "section", "sections", "subsection",
}


def _stem_token(token: str) -> str:
    if len(token) >= 5 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) >= 5 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> set[str]:
    result = set()
    for token in _TOKEN_PATTERN.findall(text or ""):
        low = token.casefold()
        if (len(token) >= 2 or token.isdigit()) and low not in _STOP_WORDS:
            result.add(low)
            stemmed = _stem_token(low)
            if stemmed != low and stemmed not in _STOP_WORDS:
                result.add(stemmed)
    return result


def _token_list(text: str) -> list[str]:
    items = []
    for token in _TOKEN_PATTERN.findall(text or ""):
        low = token.casefold()
        if (len(token) >= 2 or token.isdigit()) and low not in _STOP_WORDS:
            items.append(low)
    return items


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _as_evidence(
    chunk: EvidenceChunk,
    document: LegalSourceDocument,
    score: float,
    matched_keywords: list[str],
    passage_override: str | None = None,
    page_range: str | None = None,
) -> dict[str, Any]:
    document_name = document.original_filename or document.title
    file_url = (
        f"/api/documents/{document.uploaded_document_id}/file"
        if document.uploaded_document_id
        else None
    )
    passage = passage_override if passage_override is not None else chunk.extracted_text
    return enrich_chunk_references(
        {
            "id": chunk.id,
            "document_id": document.id,
            "uploaded_document_id": document.uploaded_document_id,
            "document_name": document_name,
            "document_title": document.title,
            "filename": document.original_filename,
            "file_url": file_url,
            "document_type": document.document_type,
            "issuing_authority": document.issuing_authority,
            "act_name": document.act_or_rule_name,
            "section": chunk.section_number,
            "section_title": chunk.section_title,
            "subsection": chunk.subsection,
            "paragraph": chunk.paragraph_number,
            "page": chunk.page_number,
            "page_number": chunk.page_number,
            "page_range": page_range,
            "passage": passage,
            "excerpt": passage,
            "source_url": document.source_url,
            "publication_date": document.publication_date.isoformat() if document.publication_date else None,
            "commencement_date": document.commencement_date.isoformat() if document.commencement_date else None,
            "amendment_status": document.amendment_status,
            "verification_status": document.verification_status,
            "matched_keywords": matched_keywords,
            "relevance_score": round(score, 4),
        }
    )


def _effective_chunk_heading(chunk: EvidenceChunk) -> tuple[str | None, str | None]:
    sec = chunk.section_number
    title = chunk.section_title
    if not sec or is_polluted_reference(sec, title):
        refs = extract_legal_references(chunk.extracted_text)
        return refs["section_number"], refs["section_title"]
    return sec, title


def _score_candidate(
    query_tokens: set[str],
    query_text: str,
    chunk: EvidenceChunk,
    document: LegalSourceDocument,
) -> tuple[float, list[str]]:
    eff_section, eff_title = _effective_chunk_heading(chunk)
    doc_title_text = " ".join(
        filter(None, [document.title, document.act_or_rule_name, document.original_filename])
    )
    heading_text = " ".join(filter(None, [eff_section, eff_title, chunk.subsection]))
    doc_title_tokens = _tokens(doc_title_text)
    heading_tokens = _tokens(heading_text)
    passage_tokens_list = _token_list(chunk.extracted_text)
    content_tokens = set(passage_tokens_list) | heading_tokens
    evidence_tokens = content_tokens | doc_title_tokens
    matched = sorted(query_tokens & evidence_tokens)
    if not matched:
        return 0.0, []

    specific_tokens = query_tokens - _GENERIC_LEGAL_TERMS
    if specific_tokens and not (set(matched) & specific_tokens):
        return 0.0, []

    # When the query asks about specific substantive topics beyond the document title,
    # require at least one topic term to match inside the chunk text/heading itself.
    topic_query_tokens = query_tokens - _GENERIC_LEGAL_TERMS - doc_title_tokens
    topic_hits = topic_query_tokens & content_tokens
    if topic_query_tokens and not topic_hits:
        return 0.0, []

    coverage = len(matched) / len(query_tokens)
    if coverage < MIN_RELEVANCE_SCORE:
        return 0.0, []

    topic_coverage = (len(topic_hits) / len(topic_query_tokens)) if topic_query_tokens else coverage
    heading_topic_hits = len((topic_hits or set(matched)) & heading_tokens)
    heading_topic_ratio = heading_topic_hits / max(1, len(topic_query_tokens) if topic_query_tokens else len(query_tokens))
    tf_hits = sum(min(passage_tokens_list.count(term), 4) for term in (topic_hits or matched))
    title_match_ratio = len(query_tokens & doc_title_tokens) / len(query_tokens)
    section_bonus = (
        0.35
        if eff_section and eff_section.strip().casefold() in query_tokens
        else (0.12 if eff_section else 0.0)
    )
    normalized_query = " ".join(_token_list(query_text))
    normalized_passage = " ".join(passage_tokens_list)
    phrase_bonus = 0.25 if len(normalized_query) >= 6 and normalized_query in normalized_passage else 0.0
    rank_score = (
        (0.35 * coverage)
        + (0.95 * topic_coverage)
        + (0.55 * heading_topic_ratio)
        + (0.04 * tf_hits)
        + (0.85 * title_match_ratio)
        + section_bonus
        + phrase_bonus
    )
    return rank_score, matched


_NEXT_RULE_START = re.compile(
    r"(?:^|\n)\s*([1-9][0-9]{0,2}[A-Za-z]?)\.\s+[A-Z“\"'\u0900-\u097F][^\r\n]{1,120}?(?:\.\s*[—–-]{1,3}|[—–-]{1,3}\s*(?:\([0-9]+\)|[A-Z]))"
)
_CONTINUATION_START = re.compile(r"^\s*(?:\([a-z0-9ivx]+\)|[a-z])", re.IGNORECASE)


def _complete_provision(chunk: EvidenceChunk, document: LegalSourceDocument) -> tuple[str, str | None, str | None, str | None]:
    """Assemble contiguous cross-chunk/cross-page text for split Gazette Rules/Sections."""
    raw_text = (chunk.extracted_text or "").strip()
    cleaned_current = strip_gazette_headers(raw_text) or raw_text
    if chunk.page_number is None:
        refs = extract_legal_references(raw_text)
        return raw_text, None, refs["section_number"], refs["section_title"]

    nearby = (
        EvidenceChunk.query.filter(
            EvidenceChunk.source_document_id == document.id,
            EvidenceChunk.verification_status == "verified",
            EvidenceChunk.page_number.in_([chunk.page_number - 1, chunk.page_number, chunk.page_number + 1]),
        )
        .all()
    )
    prev_pages = [c for c in nearby if c.id != chunk.id and (c.page_number or 0) <= chunk.page_number]
    next_pages = [c for c in nearby if c.id != chunk.id and (c.page_number or 0) >= chunk.page_number]

    assembled = cleaned_current
    inherited_sec = None
    inherited_title = None
    start_page = chunk.page_number
    end_page = chunk.page_number

    # Case A: current chunk begins mid-provision (e.g. "(a) the details...") -> prepend open heading from prev page
    starts_at_page_top = bool(
        re.match(r"^\s*(?:\d{1,4}\s+)?(?:THE\s+GAZETTE|\[भाग|\[PART)", raw_text, re.IGNORECASE)
    )
    first_rule = _NEXT_RULE_START.search(cleaned_current)
    starts_mid_rule = _CONTINUATION_START.match(cleaned_current) and (
        first_rule is None or first_rule.start() > 40
    )
    best_prev = None
    if starts_mid_rule:
        first_next_num = int(re.match(r"\d+", first_rule.group(1)).group()) if first_rule and re.match(r"\d+", first_rule.group(1)) else None
        candidate_prevs = (
            [c for c in prev_pages if (c.page_number or 0) < chunk.page_number]
            if starts_at_page_top
            else prev_pages
        )
        for cand in sorted(candidate_prevs, key=lambda c: -(c.page_number or 0)):
            cand_clean = strip_gazette_headers(cand.extracted_text)
            sec, title, start_idx = extract_last_heading(cand_clean)
            if sec and start_idx is not None:
                sec_num = int(re.match(r"\d+", sec).group()) if re.match(r"\d+", sec) else None
                if first_next_num is not None and sec_num is not None and sec_num > first_next_num:
                    continue
                tail = cand_clean[start_idx:].strip()
                if tail and len(tail) <= 1400 and tail.rstrip().endswith(("—", "-", "–", ",", ":", ";")):
                    best_prev = (cand, sec, title, tail)
                    break
        if best_prev:
            cand, sec, title, tail = best_prev
            inherited_sec, inherited_title = sec, title
            body_before_next = cleaned_current[: first_rule.start()].strip() if first_rule else cleaned_current
            assembled = f"{tail}\n{body_before_next}".strip()
            if cand.page_number and cand.page_number < start_page:
                start_page = cand.page_number

    # Case B: current chunk ends with an open Rule/Section -> append continuation from next page up to next Rule
    if not best_prev:
        sec, title, start_idx = extract_last_heading(cleaned_current)
        if sec and start_idx is not None:
            tail = cleaned_current[start_idx:].strip()
            if tail and tail.rstrip().endswith(("—", "-", "–", ",", ":", ";")):
                ordered_next = sorted(
                    next_pages,
                    key=lambda c: (
                        c.page_number or 0,
                        0 if re.match(r"^\s*(?:\d{1,4}\s+)?(?:THE\s+GAZETTE|\[भाग|\[PART)", c.extracted_text or "", re.IGNORECASE) else 1,
                    ),
                )
                for cand in ordered_next:
                    if (cand.page_number or 0) < chunk.page_number:
                        continue
                    cand_clean = strip_gazette_headers(cand.extracted_text)
                    if _CONTINUATION_START.match(cand_clean):
                        next_rule = _NEXT_RULE_START.search(cand_clean)
                        sec_num = int(re.match(r"\d+", sec).group()) if re.match(r"\d+", sec) else None
                        next_num = int(re.match(r"\d+", next_rule.group(1)).group()) if next_rule and re.match(r"\d+", next_rule.group(1)) else None
                        if sec_num is not None and next_num is not None and next_num <= sec_num:
                            continue
                        continuation = cand_clean[: next_rule.start()].strip() if next_rule else cand_clean
                        if continuation and len(tail) + len(continuation) <= 3600:
                            assembled = f"{tail}\n{continuation}".strip()
                            inherited_sec, inherited_title = sec, title
                            if cand.page_number and cand.page_number > end_page:
                                end_page = cand.page_number
                            break
            elif tail and chunk.page_number and (start_idx > 0) and len(tail) >= 80:
                assembled = cleaned_current

    page_range = f"{start_page}–{end_page}" if end_page > start_page else None
    if len(assembled) > 3600:
        assembled = assembled[:3600].rsplit(" ", 1)[0].strip()
    return assembled or raw_text, page_range, inherited_sec, inherited_title


def retrieve_evidence(question: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search verified database chunks by keyword and return matching passages with provenance."""
    query_tokens = _tokens(question)
    if not query_tokens:
        return []

    sql_terms = sorted(query_tokens, key=lambda item: (-len(item), item))[:MAX_SQL_KEYWORDS]
    keyword_clauses = []
    for term in sql_terms:
        pattern = f"%{_escape_like(term)}%"
        keyword_clauses.extend(
            [
                EvidenceChunk.extracted_text.ilike(pattern, escape="\\"),
                EvidenceChunk.section_number.ilike(pattern, escape="\\"),
                EvidenceChunk.section_title.ilike(pattern, escape="\\"),
                LegalSourceDocument.title.ilike(pattern, escape="\\"),
                LegalSourceDocument.act_or_rule_name.ilike(pattern, escape="\\"),
                LegalSourceDocument.original_filename.ilike(pattern, escape="\\"),
            ]
        )

    rows = (
        EvidenceChunk.query.join(LegalSourceDocument)
        .filter(
            EvidenceChunk.verification_status == "verified",
            LegalSourceDocument.verification_status == "verified",
            or_(*keyword_clauses),
        )
        .all()
    )

    matches = []
    seen_passages: set[tuple[str, int | None, str]] = set()
    for chunk in rows:
        document = chunk.source_document
        score, matched_keywords = _score_candidate(query_tokens, question, chunk, document)
        if score <= 0:
            continue
        dedupe_key = (
            document.id,
            chunk.page_number,
            " ".join((chunk.extracted_text or "").casefold().split()),
        )
        if dedupe_key in seen_passages:
            continue
        seen_passages.add(dedupe_key)
        matches.append((chunk, document, score, matched_keywords))

    matches.sort(key=lambda item: (-item[2], item[0].id))
    candidates_to_complete = matches[: max(12, limit * 3)]
    completed_ranked = []
    seen_completed: set[tuple[str, str | None, str]] = set()
    target_limit = max(1, min(limit, 10))
    for chunk, document, score, matched_keywords in candidates_to_complete:
        completed_text, page_range, inherited_sec, inherited_title = _complete_provision(chunk, document)
        record = _as_evidence(
            chunk,
            document,
            score,
            matched_keywords,
            passage_override=completed_text,
            page_range=page_range,
        )
        if inherited_sec:
            record["section"] = inherited_sec
            record["section_title"] = inherited_title
            record = enrich_chunk_references(record)
        # Re-boost when the completed/inherited section heading directly matches query topic terms
        doc_title_tokens = _tokens(
            " ".join(filter(None, [document.title, document.act_or_rule_name, document.original_filename]))
        )
        topic_query_tokens = query_tokens - _GENERIC_LEGAL_TERMS - doc_title_tokens
        final_heading_tokens = _tokens(" ".join(filter(None, [record.get("section"), record.get("section_title")])))
        final_heading_hits = len((topic_query_tokens or query_tokens) & final_heading_tokens)
        completeness_bonus = 0.2 if page_range else 0.0
        adjusted_score = score + (0.65 * final_heading_hits / max(1, len(topic_query_tokens or query_tokens))) + completeness_bonus
        record["relevance_score"] = round(adjusted_score, 4)
        sec_key = record.get("section")
        comp_key = (
            (document.id, sec_key, "__rule__")
            if sec_key and re.fullmatch(r"\d+[A-Za-z]?", sec_key.strip())
            else (document.id, sec_key, " ".join(completed_text[:160].casefold().split()))
        )
        if comp_key in seen_completed:
            continue
        seen_completed.add(comp_key)
        completed_ranked.append((adjusted_score, record))

    completed_ranked.sort(key=lambda item: (-item[0], -len(item[1]["excerpt"]), item[1]["id"]))
    results = [record for _, record in completed_ranked[:target_limit]]
    if not results:
        return []

    relevant_sections = {
        (
            (record["act_name"] or record["document_title"]).strip().casefold(),
            record["section"].casefold(),
        )
        for record in results
        if record["section"]
    }
    conflicting_sections: set[tuple[str, str]] = set()
    if relevant_sections:
        section_names = {section for _, section in relevant_sections}
        section_rows = (
            EvidenceChunk.query.join(LegalSourceDocument)
            .filter(
                EvidenceChunk.verification_status == "verified",
                LegalSourceDocument.verification_status == "verified",
                EvidenceChunk.section_number.in_(section_names),
            )
            .all()
        )
        source_versions: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
            lambda: defaultdict(set)
        )
        for chunk in section_rows:
            document = chunk.source_document
            if not chunk.section_number:
                continue
            key = (
                (document.act_or_rule_name or document.title).strip().casefold(),
                chunk.section_number.casefold(),
            )
            if key in relevant_sections:
                source_versions[key][document.id].add(
                    " ".join(chunk.extracted_text.casefold().split())
                )
        conflicting_sections = {
            key
            for key, versions in source_versions.items()
            if len(versions) > 1 and len({frozenset(texts) for texts in versions.values()}) > 1
        }

    for record in results:
        key = (
            (record["act_name"] or record["document_title"]).strip().casefold(),
            record["section"].casefold() if record["section"] else "",
        )
        record["conflict_detected"] = key in conflicting_sections
    return results
