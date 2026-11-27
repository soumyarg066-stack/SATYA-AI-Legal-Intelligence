import logging

from flask import has_request_context, request
from sqlalchemy.exc import SQLAlchemyError

from backend.extensions import db
from backend.models import AuditLog

logger = logging.getLogger(__name__)


def record_audit_event(
    action: str,
    *,
    user_id: int | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    status: str = "success",
    details: str | None = None,
    commit: bool = False,
) -> None:
    """Append an audit log entry without exposing sensitive secrets or breaking requests."""
    ip_address = None
    if has_request_context():
        ip_address = (request.remote_addr or "")[:45] or None

    entry = AuditLog(
        user_id=user_id,
        action=action[:80],
        resource_type=resource_type[:50] if resource_type else None,
        resource_id=str(resource_id)[:64] if resource_id is not None else None,
        status=status[:20],
        ip_address=ip_address,
        details=details[:500] if details else None,
    )
    db.session.add(entry)
    if commit:
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            logger.warning("Failed to persist audit log event '%s'.", action)
