from backend.extensions import db
from backend.models import EvidenceChunk, LegalSourceDocument


def get_knowledge_status() -> dict[str, int | bool]:
    verified_sources = (
        LegalSourceDocument.query.filter(
            LegalSourceDocument.verification_status == "verified",
            LegalSourceDocument.chunks.any(EvidenceChunk.verification_status == "verified"),
        ).count()
    )
    verified_chunks = (
        db.session.query(EvidenceChunk.id)
        .join(LegalSourceDocument)
        .filter(
            EvidenceChunk.verification_status == "verified",
            LegalSourceDocument.verification_status == "verified",
        )
        .count()
    )
    pending_sources = LegalSourceDocument.query.filter(
        LegalSourceDocument.verification_status.notin_(("verified", "rejected"))
    ).count()
    return {
        "available": verified_sources > 0 and verified_chunks > 0,
        "verified_sources": verified_sources,
        "verified_chunks": verified_chunks,
        "pending_sources": pending_sources,
    }
