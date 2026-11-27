from typing import Any
from urllib.parse import urlsplit


def _http_source_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


def citation_from_evidence(evidence: dict[str, Any], number: int) -> dict[str, Any]:
    """Format a citation solely from a retrieved database record."""
    document_name = evidence.get("document_name") or evidence.get("filename") or evidence["document_title"]
    page_number = evidence.get("page_number", evidence.get("page"))
    passage = evidence.get("passage", evidence["excerpt"])
    uploaded_document_id = evidence.get("uploaded_document_id")
    file_url = evidence.get("file_url") or (
        f"/api/documents/{uploaded_document_id}/file" if uploaded_document_id else None
    )
    return {
        "id": evidence["id"],
        "number": number,
        "document_id": evidence["document_id"],
        "uploaded_document_id": uploaded_document_id,
        "document_name": document_name,
        "title": evidence["document_title"],
        "document_title": evidence["document_title"],
        "filename": evidence["filename"],
        "file_url": file_url,
        "document_type": evidence["document_type"],
        "issuing_authority": evidence["issuing_authority"],
        "act_name": evidence["act_name"],
        "section": evidence["section"],
        "section_title": evidence["section_title"],
        "subsection": evidence["subsection"],
        "paragraph": evidence["paragraph"],
        "page": page_number,
        "page_number": page_number,
        "page_range": evidence.get("page_range"),
        "passage": passage,
        "excerpt": passage,
        "matched_keywords": evidence.get("matched_keywords", []),
        "relevance_score": evidence.get("relevance_score"),
        "source_url": _http_source_url(evidence["source_url"]),
        "publication_date": evidence["publication_date"],
        "commencement_date": evidence["commencement_date"],
        "amendment_status": evidence["amendment_status"],
    }


def build_citations(evidence_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        citation_from_evidence(record, index)
        for index, record in enumerate(evidence_records, start=1)
    ]
