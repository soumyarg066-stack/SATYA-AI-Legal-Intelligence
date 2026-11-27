"""Link extracted legal sources to uploaded files.

Revision ID: c83b2d1f6a90
Revises: fa9b99b478e6
Create Date: 2026-11-25 15:10:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = "c83b2d1f6a90"
down_revision = "fa9b99b478e6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "legal_source_document",
        sa.Column("domain", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "legal_source_document",
        sa.Column("uploaded_document_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_legal_source_document_uploaded_document_id",
        "legal_source_document",
        ["uploaded_document_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_legal_source_document_uploaded_document_id_documents",
        "legal_source_document",
        "documents",
        ["uploaded_document_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint(
        "fk_legal_source_document_uploaded_document_id_documents",
        "legal_source_document",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_legal_source_document_uploaded_document_id",
        table_name="legal_source_document",
    )
    op.drop_column("legal_source_document", "uploaded_document_id")
    op.drop_column("legal_source_document", "domain")
