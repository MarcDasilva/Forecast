"""add specialist agent scores table

Revision ID: 0003_specialist_agent_scores
Revises: 0002_category_scores
Create Date: 2026-03-22 09:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_specialist_agent_scores"
down_revision: str | None = "0002_category_scores"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "specialist_agent_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("status_label", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("benchmark_highlights", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("supporting_evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_dataset_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_specialist_agent_scores_category_created_at",
        "specialist_agent_scores",
        ["category", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_specialist_agent_scores_agent_name_created_at",
        "specialist_agent_scores",
        ["agent_name", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_specialist_agent_scores_agent_name_created_at",
        table_name="specialist_agent_scores",
    )
    op.drop_index(
        "ix_specialist_agent_scores_category_created_at",
        table_name="specialist_agent_scores",
    )
    op.drop_table("specialist_agent_scores")
