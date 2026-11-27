"""Store uploaded source file bytes in the document record.

Revision ID: ea42f83d7c10
Revises: c83b2d1f6a90
Create Date: 2026-11-25 16:25:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


revision = "ea42f83d7c10"
down_revision = "c83b2d1f6a90"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "documents",
        sa.Column(
            "file_data",
            sa.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_column("documents", "file_data")
