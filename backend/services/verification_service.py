import re
from typing import Any


_TOKEN_PATTERN = re.compile(r"[a-z0-9]{2,}", re.IGNORECASE)
_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "in", "is", "it", "of", "on", "or", "that", "the", "this", "to",
    "was", "were", "with",
}
_NUMBER_VALUES = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000",
}
_ASSERTION_TERMS = {
    "must", "shall", "may", "can", "cannot", "required", "prohibited",
    "permitted", "entitled", "eligible", "not", "no", "only", "unless",
    "except", "without", "never",
}
_NEGATION_TERMS = {"not", "no", "cannot", "prohibited", "unless", "except", "without", "never"}
MIN_CLAIM_OVERLAP = 0.2


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in _TOKEN_PATTERN.findall(text)
        if token.lower() not in _STOP_WORDS
    }


def _number_tokens(text: str) -> set[str]:
    words = _tokens(text)
    return {
        _NUMBER_VALUES.get(word, word)
        for word in words
        if word.isdigit() or word in _NUMBER_VALUES
    }


_SCRIPT_PATTERNS = {
    "kn": re.compile(r"[\u0C80-\u0CFF]"),
    "hi": re.compile(r"[\u0900-\u097F]"),
}


def _has_target_script(text: str, language: str) -> bool:
    pattern = _SCRIPT_PATTERNS.get(language)
    return bool(pattern and pattern.search(text))


def _record_numbers(record: dict[str, Any]) -> set[str]:
    fields = [
        record.get("excerpt") or "",
        record.get("document_title") or "",
        record.get("act_name") or "",
        record.get("document_name") or "",
        record.get("filename") or "",
        str(record.get("section") or ""),
        str(record.get("subsection") or ""),
        str(record.get("paragraph") or ""),
        str(record.get("page") or ""),
    ]
    return _number_tokens(" ".join(fields))


def verify_claims(
    claims: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    asks_current_legal_status: bool = False,
    language: str = "en",
) -> dict[str, Any]:
    """Require real evidence IDs and lexical support; not an entailment guarantee."""
    by_id = {record["id"]: record for record in evidence}
    supported = []
    unsupported = []
    currentness_unverified = False

    for claim in claims:
        text = claim["text"].strip()
        source_claim = (claim.get("source_claim") or "").strip()
        check_text = source_claim or text
        evidence_ids = claim["evidence_ids"]
        linked_records = [by_id[item] for item in evidence_ids if item in by_id]
        claim_tokens = _tokens(check_text)
        has_textual_support = any(
            claim_tokens
            and len(claim_tokens & _tokens(record["excerpt"])) / len(claim_tokens)
            >= MIN_CLAIM_OVERLAP
            and _number_tokens(check_text).issubset(_record_numbers(record))
            and _number_tokens(text).issubset(_record_numbers(record))
            and (claim_tokens & _ASSERTION_TERMS).issubset(
                _tokens(record["excerpt"]) & _ASSERTION_TERMS
            )
            and bool(claim_tokens & _NEGATION_TERMS)
            == bool(_tokens(record["excerpt"]) & _NEGATION_TERMS)
            for record in linked_records
        )
        if (
            not has_textual_support
            and language != "en"
            and not source_claim
            and linked_records
            and _has_target_script(text, language)
        ):
            has_textual_support = any(
                _number_tokens(text).issubset(_record_numbers(record))
                for record in linked_records
            )
        has_currentness_metadata = bool(linked_records) and all(
            record["commencement_date"]
            and record["amendment_status"]
            and record["amendment_status"].strip().casefold()
            not in {"unknown", "unverified", "not verified", "not assessed"}
            for record in linked_records
        )
        if not text or not evidence_ids or len(linked_records) != len(evidence_ids) or not has_textual_support:
            unsupported.append(text)
        elif asks_current_legal_status and not has_currentness_metadata:
            currentness_unverified = True
            unsupported.append(text)
        else:
            supported.append({"text": text, "evidence_ids": [r["id"] for r in linked_records]})

    return {
        "supported_claims": supported,
        "unsupported_claims": unsupported,
        "currentness_unverified": currentness_unverified,
        "all_supported": bool(claims) and not unsupported,
    }
