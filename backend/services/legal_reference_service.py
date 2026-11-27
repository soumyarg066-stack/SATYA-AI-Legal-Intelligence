import re
from typing import Any

# Explicit keyword-prefixed heading: "Rule 2: ...", "Section 6 — ...", "Article 21: ..."
# Reject lowercase mid-sentence prose like "section 7 and for processing..." or "section 3 of the..."
_KEYWORD_SECTION_PATTERN = re.compile(
    r"(?im)^\s*(?:rule|section|article|regulation|clause)\s+"
    r"([0-9]+[A-Za-z]?(?:\([0-9a-z]+\))*)\s*[:.\-–—]?\s*([^\r\n]{0,180})"
)

# Indian Gazette / Bare Act numbered heading (line-start OR inline after Gazette header / sentence end):
#   "2. Definitions. — (1) ..."
#   "3. Notice given by Data Fiduciary to Data Principal. —The notice..."
#   "14. Rights of Data Principals. — (1) ..."
#   "[PART II—SEC. 3(i)] 6. Reasonable security safeguards. — (1) ..."
_NUMBERED_HEADING_PATTERN = re.compile(
    r"(?:^|(?<=[\r\n])|[.);\]]\s+)\s*([1-9][0-9]{0,2}[A-Za-z]?)\.\s+"
    r"([A-Z“\"'\u0900-\u097F][^\r\n]{1,120}?)"
    r"(?:\.\s*[—–-]{1,3}\s*(?:\([0-9a-z]+\)|[A-Z“\"'\u0900-\u097F]|$)|[—–-]{1,3}\s*(?:\([0-9]+\)|$))"
)

_POLLUTED_TITLE_PREFIX = re.compile(
    r"^(?:[;,.)\]]|and\b|or\b|of\b|to\b|for\b|in\b|on\b|with\b|under\b|by\b|as\b|the\b|sub-)",
)

_GAZETTE_NOISE_LINE = re.compile(
    r"^\s*(?:"
    r"\d{1,4}|"
    r"(?:\d+\s+)?THE\s+GAZETTE\s+OF\s+INDIA.*|"
    r"\[?PART\s+II[—–\- ]*SEC\.[^\]]+\]?\s*\d*|"
    r"\[भाग\s+II.*|"
    r"भारत\s+का\s+रा[जि]पत्र.*"
    r")\s*$",
    re.IGNORECASE,
)

# Schedule / Gazette Notification headings when no numbered rule/section heading is present
_SCHEDULE_PATTERN = re.compile(
    r"(?im)^\s*((?:FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|THE)\s+SCHEDULE)\b"
    r"(?:\s*\r?\n\s*\[See\s+((?:section|rule)\s+[0-9]+[A-Za-z]?(?:\s*\([0-9a-z]+\))?)\])?"
)
_NOTIFICATION_PATTERN = re.compile(
    r"(?m)^\s*((?:G\.S\.R\.|S\.O\.)\s*[0-9]+\s*\(E\))"
)

# Sub-rule / sub-section markers like "(1)" or "(2)" after a heading dash or at line start
_SUBRULE_PATTERN = re.compile(
    r"(?:(?:^\s*)|(?:[—–-]\s*))\(([0-9]{1,2})\)(?=\s|$)"
    , re.MULTILINE
)

# Clause / paragraph markers like "(a)", "(b)", "(i)", "(ii)" at line start
_CLAUSE_PATTERN = re.compile(
    r"(?m)^\s*\(([a-z]{1,3}|[ivxlc]{1,4})\)(?=\s|$)"
)

# Numbered paragraph/item without a title dash (e.g. Schedule item "7. The memorandum of association...")
_NUMBERED_ITEM_PATTERN = re.compile(
    r"(?m)^\s*([1-9][0-9]{0,2})\.\s+(?=[A-Z\u0900-\u097F])"
)


def _clean_heading_title(raw_title: str | None) -> str | None:
    if not raw_title:
        return None
    title = re.sub(r"\s+", " ", raw_title).strip(" .:-–—")
    # Avoid treating full sentence body prose after "Rule 2 requires ..." as a short heading title
    if len(title) > 120 or title.endswith((".", ",")):
        return title[:120].rstrip(" .,:-–—") or None
    return title or None


def _summarize_markers(markers: list[str], max_items: int = 4) -> str | None:
    seen: list[str] = []
    for item in markers:
        if item not in seen:
            seen.append(item)
    if not seen:
        return None
    if len(seen) <= max_items:
        return ", ".join(f"({m})" for m in seen)
    return f"({seen[0]})–({seen[-1]})"


def extract_legal_references(text: str | None) -> dict[str, str | None]:
    """Extract only explicitly present Rule/Section, heading, sub-rule, and paragraph markers."""
    empty = {
        "section_number": None,
        "section_title": None,
        "subsection": None,
        "paragraph_number": None,
    }
    if not text or not text.strip():
        return empty

    section_numbers: list[str] = []
    section_titles: list[str] = []

    for match in _NUMBERED_HEADING_PATTERN.finditer(text):
        num = match.group(1).strip()
        title = _clean_heading_title(match.group(2))
        if num not in section_numbers:
            section_numbers.append(num)
            if title:
                section_titles.append(title)

    if not section_numbers:
        for match in _KEYWORD_SECTION_PATTERN.finditer(text):
            num = match.group(1).strip()
            raw_rest = (match.group(2) or "").strip()
            if raw_rest and _POLLUTED_TITLE_PREFIX.match(raw_rest):
                continue
            if num not in section_numbers:
                section_numbers.append(num)
                if raw_rest:
                    cleaned = _clean_heading_title(raw_rest)
                    if (
                        cleaned
                        and len(cleaned) <= 80
                        and "." not in cleaned[:-1]
                        and not _POLLUTED_TITLE_PREFIX.match(cleaned)
                    ):
                        section_titles.append(cleaned)

    if not section_numbers:
        sched_match = _SCHEDULE_PATTERN.search(text)
        if sched_match:
            section_numbers.append(sched_match.group(1).strip().title())
            if sched_match.group(2):
                section_titles.append(f"See {sched_match.group(2).strip()}")
        else:
            notif_match = _NOTIFICATION_PATTERN.search(text)
            if notif_match:
                section_numbers.append(re.sub(r"\s+", " ", notif_match.group(1).strip()))

    subrules = _SUBRULE_PATTERN.findall(text)
    clauses = _CLAUSE_PATTERN.findall(text)

    subsection = _summarize_markers(subrules)
    paragraph_number = _summarize_markers(clauses)

    if not paragraph_number and not subrules:
        items = _NUMBERED_ITEM_PATTERN.findall(text)
        # Filter out headings already captured as section_number
        item_only = [it for it in items if it not in section_numbers]
        if item_only:
            paragraph_number = f"Item {item_only[0]}" if len(item_only) == 1 else f"Items {item_only[0]}–{item_only[-1]}"
    elif not paragraph_number and subrules:
        paragraph_number = subsection

    return {
        "section_number": ", ".join(section_numbers)[:100] if section_numbers else None,
        "section_title": "; ".join(section_titles)[:500] if section_titles else None,
        "subsection": subsection[:100] if subsection else None,
        "paragraph_number": paragraph_number[:100] if paragraph_number else None,
    }


def is_polluted_reference(section: str | None, title: str | None) -> bool:
    """Detect mis-parsed mid-sentence references stored by older extractors."""
    if not section and not title:
        return False
    if title and _POLLUTED_TITLE_PREFIX.match(title.strip()):
        return True
    return False


def strip_gazette_headers(text: str | None) -> str:
    """Remove repetitive Gazette page headers while keeping statutory text verbatim."""
    if not text:
        return ""
    lines = [line for line in text.splitlines() if not _GAZETTE_NOISE_LINE.match(line)]
    return "\n".join(lines).strip()


def extract_last_heading(text: str | None) -> tuple[str | None, str | None, int | None]:
    """Return (section_number, section_title, start_index) for the last Rule/Section heading in text."""
    if not text:
        return None, None, None
    matches = list(_NUMBERED_HEADING_PATTERN.finditer(text))
    if matches:
        last = matches[-1]
        num = last.group(1).strip()
        title = _clean_heading_title(last.group(2))
        if title and not _POLLUTED_TITLE_PREFIX.match(title):
            # Position right at "<num>."
            num_pos = last.group(0).find(f"{num}.")
            start_idx = last.start() + max(0, num_pos)
            return num, title, start_idx
    return None, None, None


def enrich_chunk_references(chunk_dict: dict[str, Any]) -> dict[str, Any]:
    """Fill or repair section/subsection/paragraph fields strictly from the chunk's own text."""
    text = chunk_dict.get("passage") or chunk_dict.get("excerpt") or ""
    polluted = is_polluted_reference(chunk_dict.get("section"), chunk_dict.get("section_title"))
    if polluted:
        chunk_dict["section"] = None
        chunk_dict["section_title"] = None
    if not polluted and chunk_dict.get("section") and chunk_dict.get("paragraph"):
        return chunk_dict
    parsed = extract_legal_references(text)
    if not chunk_dict.get("section") and parsed["section_number"]:
        chunk_dict["section"] = parsed["section_number"]
    if not chunk_dict.get("section_title") and parsed["section_title"]:
        chunk_dict["section_title"] = parsed["section_title"]
    if not chunk_dict.get("subsection") and parsed["subsection"]:
        chunk_dict["subsection"] = parsed["subsection"]
    if not chunk_dict.get("paragraph") and parsed["paragraph_number"]:
        chunk_dict["paragraph"] = parsed["paragraph_number"]
    return chunk_dict
