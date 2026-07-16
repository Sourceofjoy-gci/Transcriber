"""Extend provider lifecycle and usage tracking.

Revision ID: 0005_provider_operations
Revises: 0004_provider_definitions
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_provider_operations"
down_revision = "0004_provider_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_definitions",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("provider_definitions", "is_default", server_default=None)
    op.add_column(
        "provider_definitions",
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
    )
    op.alter_column("provider_definitions", "timeout_seconds", server_default=None)
    op.add_column(
        "provider_definitions",
        sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="2"),
    )
    op.alter_column("provider_definitions", "retry_limit", server_default=None)
    op.add_column(
        "provider_definitions", sa.Column("last_tested_at", sa.DateTime(timezone=True))
    )
    op.add_column("provider_definitions", sa.Column("last_error", sa.String(500)))
    op.create_table(
        "provider_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(200)),
        sa.Column("input_units", sa.Integer()),
        sa.Column("output_units", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(12, 6)),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provider_usage_logs")
    op.drop_column("provider_definitions", "last_error")
    op.drop_column("provider_definitions", "last_tested_at")
    op.drop_column("provider_definitions", "retry_limit")
    op.drop_column("provider_definitions", "timeout_seconds")
    op.drop_column("provider_definitions", "is_default")
