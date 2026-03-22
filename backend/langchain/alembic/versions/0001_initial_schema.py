"""create initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-03-22 02:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("input_type", sa.String(length=16), nullable=False),
        sa.Column("source_ref", sa.Text(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_msg", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "anchor_embeddings",
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("anchor_text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=384), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("category"),
    )

    op.create_table(
        "dataset_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embed_input", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(dim=384), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id"),
    )

    op.create_index(
        "ix_dataset_embeddings_dataset_id",
        "dataset_embeddings",
        ["dataset_id"],
        unique=False,
    )
    op.execute(
        "CREATE INDEX ix_dataset_embeddings_embedding_ivfflat "
        "ON dataset_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_dataset_embeddings_embedding_ivfflat")
    op.drop_index("ix_dataset_embeddings_dataset_id", table_name="dataset_embeddings")
    op.drop_table("dataset_embeddings")
    op.drop_table("anchor_embeddings")
    op.drop_table("datasets")
