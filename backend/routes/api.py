import io
import os
import uuid
import mimetypes
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import current_user, login_required
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError
from sqlalchemy.orm import defer, selectinload
from werkzeug.utils import secure_filename

from backend.extensions import db
from backend.models import (
    ContactMessage,
    Conversation,
    Document,
    EvidenceChunk,
    LegalSourceDocument,
    Message,
    User,
    utcnow,
)
from backend.services.ai_service import answer_question
from backend.services.audit_service import record_audit_event
from backend.services.citation_service import build_citations
from backend.services.document_extraction_service import (
    DocumentExtractionError,
    extract_uploaded_document,
)
from backend.services.ingestion_service import append_unverified_chunk, create_unverified_records
from backend.services.knowledge_service import get_knowledge_status
from backend.services.language_service import (
    get_language_messages,
    normalize_language,
    resolve_answer_language,
    resolve_request_language,
)
from backend.services.retrieval_service import retrieve_evidence
from backend.utils.validation import clean_text, json_object, valid_email

api_bp = Blueprint("api", __name__)


def admin_required():
    if current_user.role != "admin":
        record_audit_event(
            "admin.access_denied",
            user_id=current_user.id,
            resource_type="admin_api",
            status="denied",
            commit=True,
        )
        return jsonify(error="Administrator access required."), 403
    return None


def conversation_for_user(conversation_id):
    return Conversation.query.filter_by(id=conversation_id, user_id=current_user.id).first()


@api_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except OperationalError:
        db.session.rollback()
        return jsonify(status="error", database="unavailable"), 503
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(status="error", database="error"), 500
    return jsonify(status="ok", database="connected")


@api_bp.get("/knowledge/status")
def knowledge_status():
    return jsonify(get_knowledge_status())


@api_bp.get("/profile")
@login_required
def profile():
    return jsonify(user=current_user.to_dict())


@api_bp.patch("/profile")
@login_required
def update_profile():
    data = json_object()
    if data is None:
        return jsonify(error="A JSON object is required."), 400
    username = clean_text(data.get("username"), 80)
    if len(username) < 2:
        return jsonify(error="Username must contain at least 2 characters."), 400
    new_email = current_user.email
    if "email" in data:
        candidate = clean_text(data.get("email"), 254).lower()
        if not valid_email(candidate):
            return jsonify(error="Enter a valid email address."), 400
        existing = User.query.filter(User.email == candidate, User.id != current_user.id).first()
        if existing:
            return jsonify(error="That email address is already in use."), 409
        new_email = candidate

    try:
        current_user.username = username
        current_user.email = new_email
        record_audit_event(
            "profile.update",
            user_id=current_user.id,
            resource_type="user",
            resource_id=current_user.id,
            status="success",
        )
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify(error="That email address is already in use."), 409
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Unable to update profile due to a database error."), 500

    return jsonify(user=current_user.to_dict())


@api_bp.get("/conversations")
@login_required
def list_conversations():
    conversations = (
        Conversation.query.filter_by(user_id=current_user.id)
        .order_by(Conversation.created_at.desc())
        .all()
    )
    return jsonify(
        conversations=[
            {
                "id": item.id,
                "title": item.title,
                "created_at": item.created_at.isoformat(),
                "message_count": len(item.messages),
            }
            for item in conversations
        ]
    )


@api_bp.post("/conversations")
@login_required
def create_conversation():
    msgs = get_language_messages(resolve_request_language(request))
    conversation = Conversation(user_id=current_user.id)
    try:
        db.session.add(conversation)
        db.session.flush()
        record_audit_event(
            "conversation.create",
            user_id=current_user.id,
            resource_type="conversation",
            resource_id=conversation.id,
            status="success",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error=msgs["error_create_conversation_db"]), 500
    return jsonify(conversation={"id": conversation.id, "title": conversation.title}), 201


@api_bp.get("/conversations/<int:conversation_id>")
@login_required
def get_conversation(conversation_id):
    msgs = get_language_messages(resolve_request_language(request))
    conversation = conversation_for_user(conversation_id)
    if not conversation:
        return jsonify(error=msgs["error_conversation_not_found"]), 404
    return jsonify(
        conversation={
            "id": conversation.id,
            "title": conversation.title,
            "messages": [
                {
                    "id": message.id,
                    "sender": message.sender,
                    "message": message.message,
                    "created_at": message.created_at.isoformat(),
                }
                for message in conversation.messages
            ],
        }
    )


@api_bp.delete("/conversations/<int:conversation_id>")
@login_required
def delete_conversation(conversation_id):
    msgs = get_language_messages(resolve_request_language(request))
    conversation = conversation_for_user(conversation_id)
    if not conversation:
        return jsonify(error=msgs["error_conversation_not_found"]), 404
    try:
        record_audit_event(
            "conversation.delete",
            user_id=current_user.id,
            resource_type="conversation",
            resource_id=conversation.id,
            status="success",
        )
        db.session.delete(conversation)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error=msgs["error_delete_conversation_db"]), 500
    return jsonify(message=msgs["message_conversation_cleared"])


@api_bp.post("/chat")
@login_required
def chat():
    fallback_lang = resolve_request_language(request)
    fallback_msgs = get_language_messages(fallback_lang)
    data = json_object()
    if data is None:
        return jsonify(error=fallback_msgs["error_json_required"]), 400
    raw_language = data.get("language")
    if raw_language is None or (isinstance(raw_language, str) and not raw_language.strip()):
        language = fallback_lang
    else:
        try:
            language = normalize_language(raw_language)
        except ValueError:
            return jsonify(error=fallback_msgs["error_unsupported_language"]), 400
    msgs = get_language_messages(language)

    question = clean_text(data.get("message"), 4000)
    if not question:
        return jsonify(error=msgs["error_empty_message"]), 400
    effective_language = resolve_answer_language(question, language)
    msgs = get_language_messages(effective_language)

    conversation_id = data.get("conversation_id")
    if conversation_id is not None:
        if isinstance(conversation_id, bool) or not isinstance(conversation_id, int) or conversation_id < 1:
            return jsonify(error=msgs["error_invalid_conversation_id"]), 400
        conversation = conversation_for_user(conversation_id)
        if not conversation:
            return jsonify(error=msgs["error_conversation_not_found"]), 404
    else:
        conversation = None

    try:
        if not conversation:
            conversation = Conversation(user_id=current_user.id)
            db.session.add(conversation)
            db.session.flush()

        if conversation.title == "New conversation":
            conversation.title = question[:80]
        conversation.updated_at = utcnow()
        history = [
            {"sender": message.sender, "message": message.message}
            for message in (conversation.messages[-8:] if conversation.messages else [])
        ]
        answer = answer_question(question, history=history, language=language)
        db.session.add_all(
            [
                Message(conversation_id=conversation.id, sender="user", message=question),
                Message(conversation_id=conversation.id, sender="assistant", message=answer["answer"]),
            ]
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error=msgs["error_save_messages_db"]), 500

    return jsonify(
        conversation_id=conversation.id,
        answer=answer["answer"],
        citations=answer["citations"],
        sources=answer["sources"],
        matches=[
            {
                "chunk_id": item["id"],
                "document_id": item["document_id"],
                "document_name": item.get("document_name") or item.get("filename") or item["document_title"],
                "page_number": item.get("page_number", item.get("page")),
                "section": item.get("section"),
                "passage": item.get("passage", item["excerpt"]),
                "matched_keywords": item.get("matched_keywords", []),
            }
            for item in answer["sources"]
        ],
        verified=answer["verified"],
        evidence_status=answer["evidence_status"],
        limitations=answer["limitations"],
        language=answer["language"],
    )


@api_bp.route("/retrieval", methods=["GET", "POST"])
@login_required
def retrieval():
    if request.method == "GET":
        query = clean_text(request.args.get("q", ""), 4000)
        raw_limit = request.args.get("limit", "5")
    else:
        data = json_object()
        if data is None:
            return jsonify(error="A JSON object is required."), 400
        raw_query = data.get("query") if data.get("query") is not None else data.get("message")
        query = clean_text(raw_query, 4000)
        raw_limit = data.get("limit", 5)

    if not query:
        return jsonify(error="Enter a legal question or search query."), 400
    try:
        limit = int(raw_limit)
    except (TypeError, ValueError):
        return jsonify(error="Limit must be an integer between 1 and 10."), 400
    if isinstance(raw_limit, bool) or limit < 1 or limit > 10:
        return jsonify(error="Limit must be an integer between 1 and 10."), 400

    evidence = retrieve_evidence(query, limit=limit)
    citations = build_citations(evidence)
    results = [
        {
            "chunk_id": item["id"],
            "document_id": item["document_id"],
            "document_name": item["document_name"],
            "document_title": item["document_title"],
            "page_number": item["page_number"],
            "section": item["section"],
            "subsection": item["subsection"],
            "paragraph": item["paragraph"],
            "passage": item["passage"],
            "matched_keywords": item["matched_keywords"],
            "relevance_score": item["relevance_score"],
        }
        for item in citations
    ]
    return jsonify(
        query=query,
        count=len(results),
        verified_only=True,
        results=results,
        message=(
            None
            if results
            else "No matching passages were found in verified legal documents."
        ),
    )


@api_bp.get("/documents")
@login_required
def list_documents():
    documents = (
        Document.query.options(
            defer(Document.file_data),
            selectinload(Document.legal_sources).selectinload(LegalSourceDocument.chunks)
        )
        .order_by(Document.upload_date.desc())
        .all()
    )
    return jsonify(
        documents=[
            {
                "id": doc.id,
                "filename": doc.filename,
                "document_type": doc.document_type,
                "upload_date": doc.upload_date.isoformat(),
                "processing_status": doc.processing_status,
                "sources": [
                    {
                        "id": source.id,
                        "title": source.title,
                        "domain": source.domain,
                        "verification_status": source.verification_status,
                        "chunk_count": len(source.chunks),
                        "preview": (
                            sorted(
                                source.chunks,
                                key=lambda chunk: (
                                    chunk.page_number is None,
                                    chunk.page_number or 0,
                                ),
                            )[0].extracted_text[:1200]
                            if source.chunks
                            else ""
                        ),
                        "file_url": f"/api/documents/{doc.id}/file",
                    }
                    for source in doc.legal_sources
                ],
            }
            for doc in documents
        ]
    )


def _safe_db_file_data(file_bytes: bytes) -> bytes | None:
    """Keep file_data in DB only when within the active database packet limit."""
    if db.engine.dialect.name != "mysql":
        return file_bytes
    max_packet = 1048576
    try:
        row = db.session.execute(text("SHOW VARIABLES LIKE 'max_allowed_packet'")).first()
        if row and row[1]:
            max_packet = int(row[1])
    except (SQLAlchemyError, TypeError, ValueError):
        pass
    safe_limit = max(0, max_packet - 256 * 1024)
    return file_bytes if len(file_bytes) <= safe_limit else None


@api_bp.post("/documents")
@login_required
def upload_document():
    denied = admin_required()
    if denied:
        return denied
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify(error="Choose a supported source document to upload."), 400
    safe_name = secure_filename(uploaded.filename)
    extension = Path(safe_name).suffix.lower()
    if not safe_name or extension not in {
        ".pdf", ".txt", ".csv", ".tsv", ".xls"
    }:
        return jsonify(
            error="Supported formats are PDF, TXT, CSV, and TSV."
        ), 400
    file_bytes = uploaded.stream.read(current_app.config["MAX_UPLOAD_BYTES"] + 1)
    if len(file_bytes) > current_app.config["MAX_UPLOAD_BYTES"]:
        return jsonify(error="The uploaded file exceeds the maximum allowed size."), 413

    try:
        source_records = extract_uploaded_document(safe_name, file_bytes)
    except DocumentExtractionError as error:
        return jsonify(error=str(error)), 400

    safe_name = safe_name[:255]
    storage_name = uuid.uuid4().hex + extension
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = str(upload_dir / storage_name)
    Path(target).write_bytes(file_bytes)
    document = Document(
        filename=safe_name,
        file_path=target,
        document_type=extension.lstrip(".").upper(),
        processing_status="processed",
        file_data=_safe_db_file_data(file_bytes),
        uploaded_by=current_user.id,
    )
    try:
        db.session.add(document)
        db.session.flush()
        chunk_count = 0
        for source_record in source_records:
            all_chunks = source_record["chunks"]
            source = create_unverified_records(
                source_record["metadata"],
                all_chunks[:100],
                uploaded_document_id=document.id,
            )
            db.session.flush()
            for offset in range(100, len(all_chunks), 100):
                for chunk_data in all_chunks[offset : offset + 100]:
                    append_unverified_chunk(source, chunk_data)
                db.session.flush()
            chunk_count += len(all_chunks)
        record_audit_event(
            "document.upload",
            user_id=current_user.id,
            resource_type="document",
            resource_id=document.id,
            status="success",
            details=(
                f"Extracted {len(source_records)} source record(s) and "
                f"{chunk_count} evidence chunk(s) from '{safe_name}'."
            ),
        )
        db.session.commit()
    except (SQLAlchemyError, ValueError):
        db.session.rollback()
        if os.path.isfile(target):
            os.remove(target)
        current_app.logger.exception("Unable to persist extracted legal source content.")
        return jsonify(error="Unable to save extracted source content to the database."), 500

    return jsonify(
        document={
            "id": document.id,
            "filename": document.filename,
            "document_type": document.document_type,
            "upload_date": document.upload_date.isoformat(),
            "processing_status": document.processing_status,
            "source_count": len(source_records),
            "chunk_count": chunk_count,
        },
        message=(
            f"Uploaded and extracted {len(source_records)} source document(s) into "
            f"{chunk_count} evidence passage(s). Sources remain unverified until an "
            "administrator reviews and verifies each source."
        ),
    ), 201


@api_bp.get("/documents/<int:document_id>/file")
@login_required
def open_document(document_id):
    document = db.session.get(Document, document_id)
    if not document:
        return jsonify(error="Document not found."), 404
    mimetype = mimetypes.guess_type(document.filename)[0] or "application/octet-stream"
    if document.file_data is not None:
        return send_file(
            io.BytesIO(document.file_data),
            mimetype=mimetype,
            download_name=document.filename,
        )
    if not os.path.isfile(document.file_path):
        return jsonify(error="The stored document file is unavailable."), 404
    return send_file(document.file_path, mimetype=mimetype, download_name=document.filename)


@api_bp.post("/legal-sources/<string:source_id>/verify")
@login_required
def verify_legal_source(source_id):
    return _review_legal_source(source_id, "verified")


@api_bp.post("/legal-sources/<string:source_id>/reject")
@login_required
def reject_legal_source(source_id):
    return _review_legal_source(source_id, "rejected")


def _review_legal_source(source_id, decision):
    denied = admin_required()
    if denied:
        return denied
    source = LegalSourceDocument.query.filter_by(id=source_id).first()
    if not source:
        return jsonify(error="Legal source document not found."), 404
    if not source.chunks:
        return jsonify(error="A source must contain extracted passages before review."), 400
    try:
        source.verification_status = decision
        for chunk in source.chunks:
            chunk.verification_status = decision
        action = "document.verify" if decision == "verified" else "document.reject"
        outcome = "verified" if decision == "verified" else "rejected"
        record_audit_event(
            action,
            user_id=current_user.id,
            resource_type="legal_source_document",
            resource_id=source.id,
            status="success",
            details=f"Administrator {outcome} extracted source '{source.title}'.",
        )
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Unable to save legal source review.")
        return jsonify(error="Unable to save the source review due to a database error."), 500
    message = (
        "Source verified and made available to evidence retrieval."
        if decision == "verified"
        else "Source rejected and excluded from evidence retrieval."
    )
    return jsonify(
        message=message,
        source_id=source.id,
        verification_status=source.verification_status,
    )


@api_bp.post("/contact")
def contact():
    data = json_object()
    if data is None:
        return jsonify(error="A JSON object is required."), 400
    name = clean_text(data.get("name"), 100)
    email = clean_text(data.get("email"), 254).lower()
    message = clean_text(data.get("message"), 5000)
    if len(name) < 2 or not valid_email(email) or len(message) < 10:
        return jsonify(error="Please provide a name, valid email, and message of at least 10 characters."), 400
    try:
        db.session.add(ContactMessage(name=name, email=email, message=message))
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
        return jsonify(error="Unable to save your message due to a database error."), 500
    return jsonify(message="Thank you. Your message has been received."), 201


@api_bp.get("/admin/stats")
@login_required
def admin_stats():
    denied = admin_required()
    if denied:
        return denied
    db.session.execute(text("SELECT 1"))
    total_users = User.query.count()
    total_documents = Document.query.count()
    statuses = dict(
        db.session.query(Document.processing_status, func.count(Document.id))
        .group_by(Document.processing_status)
        .all()
    )
    recent_users = User.query.order_by(User.created_at.desc()).limit(8).all()
    recent_documents = Document.query.order_by(Document.upload_date.desc()).limit(8).all()
    return jsonify(
        database="connected",
        extraction_enabled=True,
        monitoring_configured=bool(current_app.logger.handlers or True),
        total_users=total_users,
        total_documents=total_documents,
        processing_statuses=statuses,
        recent_users=[user.to_dict() for user in recent_users],
        recent_documents=[
            {
                "id": doc.id,
                "filename": doc.filename,
                "upload_date": doc.upload_date.isoformat(),
                "processing_status": doc.processing_status,
            }
            for doc in recent_documents
        ],
    )


@api_bp.get("/admin/users")
@login_required
def admin_users():
    denied = admin_required()
    if denied:
        return denied
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify(users=[user.to_dict() for user in users])
