import hashlib
from datetime import date
from typing import Any

from backend.extensions import db
from backend.models import EvidenceChunk, LegalSourceDocument


def create_unverified_records(
    metadata: dict[str, Any],
    chunks: list[dict[str, Any]],
    uploaded_document_id: int | None = None,
) -> LegalSourceDocument:
    """Persist already-extracted structured records without reading any files.

    Newly created records are always unverified and therefore cannot be retrieved.
    """
    title = str(metadata.get("title", "")).strip()
    document_type = str(metadata.get("document_type", "")).strip()
    if not title or not document_type:
        raise ValueError("Document title and document type are required.")
    if not chunks:
        raise ValueError("At least one extracted text chunk is required.")

    publication_date = _parse_date(metadata.get("publication_date"))
    commencement_date = _parse_date(metadata.get("commencement_date"))
    document_text = "\n".join(str(chunk.get("extracted_text", "")) for chunk in chunks)
    document = LegalSourceDocument(
        title=title[:500],
        document_type=document_type[:80],
        issuing_authority=_optional_text(metadata.get("issuing_authority"), 255),
        act_or_rule_name=_optional_text(metadata.get("act_or_rule_name"), 500),
        chapter=_optional_text(metadata.get("chapter"), 255),
        publication_date=publication_date,
        commencement_date=commencement_date,
        amendment_status=_optional_text(metadata.get("amendment_status"), 100),
        source_url=_optional_text(metadata.get("source_url"), 2000),
        original_filename=_optional_text(metadata.get("original_filename"), 255),
        domain=_optional_text(metadata.get("domain"), 100),
        uploaded_document_id=uploaded_document_id,
        content_hash=hashlib.sha256(document_text.encode("utf-8")).hexdigest(),
        verification_status="unverified",
    )
    for chunk_data in chunks:
        append_unverified_chunk(document, chunk_data)
    db.session.add(document)
    return document


def append_unverified_chunk(document: LegalSourceDocument, chunk_data: dict[str, Any]) -> EvidenceChunk:
    """Validate and attach one unverified evidence chunk to a source document."""
    extracted_text = str(chunk_data.get("extracted_text", "")).strip()
    if not extracted_text:
        raise ValueError("Each evidence chunk must contain extracted text.")
    page_number = chunk_data.get("page_number")
    if page_number is not None and (
        not isinstance(page_number, int) or isinstance(page_number, bool) or page_number < 1
    ):
        raise ValueError("Page numbers must be positive integers.")
    chunk_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
    chunk = EvidenceChunk(
        section_number=_optional_text(chunk_data.get("section_number"), 100),
        section_title=_optional_text(chunk_data.get("section_title"), 500),
        subsection=_optional_text(chunk_data.get("subsection"), 100),
        paragraph_number=_optional_text(chunk_data.get("paragraph_number"), 100),
        page_number=page_number,
        extracted_text=extracted_text,
        content_hash=chunk_hash,
        verification_status="unverified",
    )
    document.chunks.append(chunk)
    return chunk


def _optional_text(value: Any, maximum: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text[:maximum] or None


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("Dates must use ISO format YYYY-MM-DD.") from error
    raise ValueError("Dates must use ISO format YYYY-MM-DD.")
