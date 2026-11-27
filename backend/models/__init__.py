from datetime import datetime, timezone
import uuid

from flask_login import UserMixin
from sqlalchemy.dialects import mysql
from werkzeug.security import check_password_hash, generate_password_hash

from backend.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


LONG_TEXT = db.Text().with_variant(mysql.MEDIUMTEXT(), "mysql")
FILE_DATA = db.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql")


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(254), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    conversations = db.relationship(
        "Conversation",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    documents = db.relationship(
        "Document",
        back_populates="uploader",
        cascade="all, delete-orphan",
    )
    audit_logs = db.relationship(
        "AuditLog",
        back_populates="user",
        passive_deletes=True,
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "created_at": self.created_at.isoformat(),
        }


class Conversation(db.Model):
    __tablename__ = "conversations"
    __table_args__ = (
        db.Index("ix_conversations_user_created", "user_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(160), nullable=False, default="New conversation")
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", back_populates="conversations")
    messages = db.relationship(
        "Message",
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(db.Model):
    __tablename__ = "messages"
    __table_args__ = (
        db.Index("ix_messages_conv_created", "conversation_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    conversation_id = db.Column(
        db.Integer,
        db.ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender = db.Column(db.String(20), nullable=False, index=True)
    message = db.Column(LONG_TEXT, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    conversation = db.relationship("Conversation", back_populates="messages")


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    filename = db.Column(db.String(255), nullable=False)
    document_type = db.Column(db.String(40), nullable=False, default="PDF")
    upload_date = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    processing_status = db.Column(db.String(30), nullable=False, default="uploaded", index=True)
    file_path = db.Column(db.String(1024), nullable=False)
    file_data = db.Column(FILE_DATA, nullable=True)
    uploaded_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    uploader = db.relationship("User", back_populates="documents")
    legal_sources = db.relationship(
        "LegalSourceDocument",
        back_populates="uploaded_document",
        cascade="all, delete-orphan",
    )


class AuditLog(db.Model):
    """Security and operational audit trail stored in the application database."""

    __tablename__ = "audit_logs"
    __table_args__ = (
        db.Index("ix_audit_logs_action_created", "action", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action = db.Column(db.String(80), nullable=False, index=True)
    resource_type = db.Column(db.String(50), nullable=True)
    resource_id = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="success", index=True)
    ip_address = db.Column(db.String(45), nullable=True)
    details = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    user = db.relationship("User", back_populates="audit_logs")


class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(254), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class LegalSourceDocument(db.Model):
    """Extracted legal source metadata linked to its uploaded file."""

    __tablename__ = "legal_source_document"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    title = db.Column(db.String(500), nullable=False)
    document_type = db.Column(db.String(80), nullable=False)
    issuing_authority = db.Column(db.String(255))
    act_or_rule_name = db.Column(db.String(500))
    chapter = db.Column(db.String(255))
    publication_date = db.Column(db.Date)
    commencement_date = db.Column(db.Date)
    amendment_status = db.Column(db.String(100))
    source_url = db.Column(db.Text)
    original_filename = db.Column(db.String(255))
    domain = db.Column(db.String(100))
    uploaded_document_id = db.Column(
        db.Integer,
        db.ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    content_hash = db.Column(db.String(64))
    verification_status = db.Column(db.String(30), nullable=False, default="unverified", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    chunks = db.relationship(
        "EvidenceChunk",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )
    uploaded_document = db.relationship("Document", back_populates="legal_sources")


class EvidenceChunk(db.Model):
    """Page-provenanced extracted text, awaiting verified future ingestion."""

    __tablename__ = "evidence_chunk"

    id = db.Column(db.String(32), primary_key=True, default=lambda: uuid.uuid4().hex)
    source_document_id = db.Column(
        db.String(32),
        db.ForeignKey("legal_source_document.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_number = db.Column(db.String(100))
    section_title = db.Column(db.String(500))
    subsection = db.Column(db.String(100))
    paragraph_number = db.Column(db.String(100))
    page_number = db.Column(db.Integer)
    extracted_text = db.Column(LONG_TEXT, nullable=False)
    content_hash = db.Column(db.String(64), nullable=False)
    verification_status = db.Column(db.String(30), nullable=False, default="unverified", index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    source_document = db.relationship("LegalSourceDocument", back_populates="chunks")
