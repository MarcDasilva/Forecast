"""add category scores table

Revision ID: 0002_category_scores
Revises: 0001_initial_schema
Create Date: 2026-03-22 04:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_category_scores"
down_revision: str | None = "0001_initial_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "category_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("cosine_similarity", sa.Float(), nullable=False),
        sa.Column("benchmark_eval", sa.Float(), nullable=False),
        sa.Column("importance_weight", sa.Float(), nullable=False),
        sa.Column("final_score", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_category_scores_dataset_id_category",
        "category_scores",
        ["dataset_id", "category"],
        unique=False,
    )
    op.create_index(
        "ix_category_scores_category_created_at",
        "category_scores",
        ["category", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_category_scores_category_created_at", table_name="category_scores")
    op.drop_index("ix_category_scores_dataset_id_category", table_name="category_scores")
    op.drop_table("category_scores")
