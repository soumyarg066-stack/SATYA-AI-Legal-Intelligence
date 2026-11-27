import csv
import io
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from backend.services.legal_reference_service import extract_legal_references


MAX_CHUNK_CHARACTERS = 1800
_SECTION_PATTERN = re.compile(
    r"(?im)^\s*(?:rule|section|article|regulation|clause)\s+"
    r"([0-9]+[a-z]?(?:\([0-9a-z]+\))*)\s*[:.\-–—]?\s*([^\r\n]{0,180})"
)
_STRUCTURED_FIELDS = {"document_id", "document_name", "page_number", "content"}


class DocumentExtractionError(ValueError):
    """Raised when an uploaded file cannot be safely converted to source text."""


def extract_uploaded_document(filename: str, file_bytes: bytes) -> list[dict[str, Any]]:
    """Extract page-provenanced PDF text or content from supported text files."""
    extension = Path(filename).suffix.lower()
    if not file_bytes:
        raise DocumentExtractionError("The uploaded file is empty.")

    if extension == ".pdf":
        pages = _extract_pdf(file_bytes)
        return _single_source(filename, "PDF", pages)
    if extension not in {".txt", ".csv", ".tsv", ".xls"}:
        raise DocumentExtractionError(
            "Supported formats are PDF, TXT, CSV, and TSV."
        )
    if extension == ".txt":
        text = _decode_text(file_bytes)
        return _single_source(filename, "TXT", [(None, text)])
    if extension == ".xls" and not _looks_like_delimited_text(file_bytes):
        raise DocumentExtractionError(
            "Binary XLS workbooks are not supported. Export the sheet as CSV or TSV and upload it again."
        )

    rows = _extract_delimited(file_bytes)
    return _sources_from_rows(filename, rows)


def _single_source(
    filename: str,
    document_type: str,
    pages: list[tuple[int | None, str]],
) -> list[dict[str, Any]]:
    title = Path(filename).stem
    chunks = []
    for page_number, text in pages:
        for excerpt in _split_text(text):
            refs = extract_legal_references(excerpt)
            chunks.append(
                {
                    "page_number": page_number,
                    "section_number": refs["section_number"],
                    "section_title": refs["section_title"],
                    "subsection": refs["subsection"],
                    "paragraph_number": refs["paragraph_number"],
                    "extracted_text": excerpt,
                }
            )
    if not chunks:
        raise DocumentExtractionError(
            "No extractable text was found. Scanned PDFs require OCR before upload."
        )
    return [
        {
            "metadata": {
                "title": title,
                "document_type": document_type,
                "act_or_rule_name": title,
                "original_filename": filename,
            },
            "chunks": chunks,
        }
    ]


def _extract_pdf(file_bytes: bytes) -> list[tuple[int | None, str]]:
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        if reader.is_encrypted:
            raise DocumentExtractionError("Password-protected PDFs cannot be processed.")
        pages = [(index, page.extract_text() or "") for index, page in enumerate(reader.pages, 1)]
    except DocumentExtractionError:
        raise
    except Exception as error:
        raise DocumentExtractionError("The PDF could not be read.") from error
    return [(number, text) for number, text in pages if text.strip()]


def _extract_delimited(file_bytes: bytes) -> list[list[list[str]]]:
    text = _decode_text(file_bytes)
    sample = text[:8192]
    header = text.partition("\n")[0]
    delimiter = max((",", "\t", ";", "|"), key=header.count)
    if header.count(delimiter) == 0:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
        except csv.Error:
            delimiter = ","
    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
        rows = [[cell for cell in row] for row in reader]
    except csv.Error as error:
        raise DocumentExtractionError("The delimited text file could not be read.") from error
    if not rows or len(rows[0]) < 2:
        raise DocumentExtractionError("The CSV/TSV file must contain a header and data columns.")
    return [rows]


def _sources_from_rows(filename: str, sheets: list[list[list[str]]]) -> list[dict[str, Any]]:
    normalized_sheets = []
    for rows in sheets:
        if len(rows) < 2:
            continue
        headers = [_normalize_header(value) for value in rows[0]]
        if not any(headers):
            continue
        normalized_sheets.append(
            (headers, [dict(zip(headers, row)) for row in rows[1:] if any(row)])
        )
    if not normalized_sheets:
        raise DocumentExtractionError("No tabular records were found in the uploaded file.")

    if all(_STRUCTURED_FIELDS.issubset(set(headers)) for headers, _ in normalized_sheets):
        return _structured_sources(filename, normalized_sheets)

    chunks = []
    for headers, rows in normalized_sheets:
        for row in rows:
            content = "\n".join(
                f"{header}: {value.strip()}"
                for header, value in row.items()
                if header and value.strip()
            )
            page_number = _positive_page(row.get("page_number") or row.get("page"))
            for excerpt in _split_text(content):
                refs = extract_legal_references(excerpt)
                chunks.append(
                    {
                        "page_number": page_number,
                        "section_number": refs["section_number"],
                        "section_title": refs["section_title"],
                        "subsection": refs["subsection"],
                        "paragraph_number": refs["paragraph_number"],
                        "extracted_text": excerpt,
                    }
                )
    if not chunks:
        raise DocumentExtractionError("No extractable text was found in the tabular file.")
    title = Path(filename).stem
    return [
        {
            "metadata": {
                "title": title,
                "document_type": Path(filename).suffix.lstrip(".").upper() or "CSV",
                "act_or_rule_name": title,
                "original_filename": filename,
            },
            "chunks": chunks,
        }
    ]


def _structured_sources(
    filename: str,
    sheets: list[tuple[list[str], list[dict[str, str]]]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for _headers, rows in sheets:
        for row in rows:
            content = row.get("content", "").strip()
            name = row.get("document_name", "").strip()
            source_id = row.get("document_id", "").strip()
            if not content or not source_id or not name:
                continue
            group = grouped.setdefault(
                source_id,
                {
                    "metadata": {
                        "title": name,
                        "document_type": "Legal source",
                        "issuing_authority": (row.get("source_authority") or "").strip() or None,
                        "act_or_rule_name": Path(name).stem.replace("_", " "),
                        "original_filename": name,
                        "domain": (row.get("domain") or "").strip() or None,
                    },
                    "chunks": [],
                },
            )
            page_number = _positive_page(row.get("page_number"))
            for excerpt in _split_text(content):
                refs = extract_legal_references(excerpt)
                group["chunks"].append(
                    {
                        "page_number": page_number,
                        "section_number": refs["section_number"],
                        "section_title": refs["section_title"],
                        "subsection": refs["subsection"],
                        "paragraph_number": refs["paragraph_number"],
                        "extracted_text": excerpt,
                    }
                )
    if not grouped:
        raise DocumentExtractionError("No legal source content was found in the dataset.")
    return list(grouped.values())


def _normalize_header(value: str) -> str:
    return re.sub(r"\s+", "_", value.strip().lstrip("\ufeff").lower())


def _positive_page(value: Any) -> int | None:
    try:
        page = int(float(str(value).strip()))
    except (TypeError, ValueError):
        return None
    return page if page > 0 else None


def _decode_text(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentExtractionError(
        "The text file encoding is unsupported. Save it as UTF-8 and try again."
    )


def _looks_like_delimited_text(file_bytes: bytes) -> bool:
    return not file_bytes.startswith((b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", b"PK\x03\x04"))


def _split_text(text: str) -> list[str]:
    remaining = text.strip()
    chunks = []
    min_split = MAX_CHUNK_CHARACTERS // 2
    while remaining:
        if len(remaining) <= MAX_CHUNK_CHARACTERS:
            chunks.append(remaining)
            break
        window = remaining[: MAX_CHUNK_CHARACTERS + 1]
        # Prefer splitting right before a new numbered Rule/Section heading or paragraph break
        heading_breaks = list(re.finditer(r"\n(?=\s*[1-9][0-9]{0,2}[A-Za-z]?\.\s+[A-Z“\"'\u0900-\u097F])", window))
        split_at = -1
        for m in reversed(heading_breaks):
            if m.start() >= min_split:
                split_at = m.start()
                break
        if split_at < min_split:
            para_pos = remaining.rfind("\n\n", min_split, MAX_CHUNK_CHARACTERS + 1)
            if para_pos >= min_split:
                split_at = para_pos
        if split_at < min_split:
            line_pos = remaining.rfind("\n", min_split, MAX_CHUNK_CHARACTERS + 1)
            if line_pos >= min_split:
                split_at = line_pos
        if split_at < min_split:
            split_at = remaining.rfind(" ", 0, MAX_CHUNK_CHARACTERS + 1)
        if split_at < min_split:
            split_at = MAX_CHUNK_CHARACTERS
        excerpt = remaining[:split_at].strip()
        if excerpt:
            chunks.append(excerpt)
        remaining = remaining[split_at:].strip()
    return chunks


def _section_from_text(text: str) -> tuple[str | None, str | None]:
    match = _SECTION_PATTERN.search(text)
    if not match:
        return None, None
    return match.group(1), match.group(2).strip() or None
