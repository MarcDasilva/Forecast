"""add dataset artifact storage

Revision ID: 0005_dataset_artifacts
Revises: 0004_forecast_storage
Create Date: 2026-03-22 15:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_dataset_artifacts"
down_revision: str | None = "0004_forecast_storage"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "dataset_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_type", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("artifact_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_dataset_artifacts_dataset_created_at",
        "dataset_artifacts",
        ["dataset_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_dataset_artifacts_type_created_at",
        "dataset_artifacts",
        ["artifact_type", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_dataset_artifacts_type_created_at", table_name="dataset_artifacts")
    op.drop_index("ix_dataset_artifacts_dataset_created_at", table_name="dataset_artifacts")
    op.drop_table("dataset_artifacts")
