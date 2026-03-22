"""add forecast storage tables

Revision ID: 0004_forecast_storage
Revises: 0003_specialist_agent_scores
Create Date: 2026-03-22 12:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_forecast_storage"
down_revision: str | None = "0003_specialist_agent_scores"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("target_y", sa.Float(), nullable=False),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("target_days", sa.Integer(), nullable=True),
        sa.Column("forecast_periods", sa.Integer(), nullable=False),
        sa.Column("history_window_days", sa.Integer(), nullable=False),
        sa.Column("history_date_basis", sa.String(length=32), nullable=False),
        sa.Column("history_source", sa.Text(), nullable=False),
        sa.Column("observed_point_count", sa.Integer(), nullable=False),
        sa.Column("projection_point_count", sa.Integer(), nullable=False),
        sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_runs_category_created_at",
        "forecast_runs",
        ["category", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_runs_mode_created_at",
        "forecast_runs",
        ["mode", "created_at"],
        unique=False,
    )

    op.create_table(
        "forecast_points",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("forecast_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("point_kind", sa.String(length=24), nullable=False),
        sa.Column("point_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("predicted", sa.Float(), nullable=True),
        sa.Column("lower_ci", sa.Float(), nullable=True),
        sa.Column("upper_ci", sa.Float(), nullable=True),
        sa.Column("trend", sa.Float(), nullable=True),
        sa.Column("is_historical", sa.Boolean(), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("point_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["forecast_run_id"], ["forecast_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_forecast_points_run_kind_date",
        "forecast_points",
        ["forecast_run_id", "point_kind", "point_date"],
        unique=False,
    )
    op.create_index(
        "ix_forecast_points_point_date",
        "forecast_points",
        ["point_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_points_point_date", table_name="forecast_points")
    op.drop_index("ix_forecast_points_run_kind_date", table_name="forecast_points")
    op.drop_table("forecast_points")
    op.drop_index("ix_forecast_runs_mode_created_at", table_name="forecast_runs")
    op.drop_index("ix_forecast_runs_category_created_at", table_name="forecast_runs")
    op.drop_table("forecast_runs")
