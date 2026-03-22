"""add standalone source recordings

Revision ID: 0006_source_recordings
Revises: 0005_dataset_artifacts
Create Date: 2026-03-22 19:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_source_recordings"
down_revision: str | None = "0005_dataset_artifacts"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_recordings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("recording_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_recordings_source_ref_created_at",
        "source_recordings",
        ["source_ref", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_source_recordings_artifact_type_created_at",
        "source_recordings",
        ["artifact_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_source_recordings_artifact_type_created_at", table_name="source_recordings")
    op.drop_index("ix_source_recordings_source_ref_created_at", table_name="source_recordings")
    op.drop_table("source_recordings")
