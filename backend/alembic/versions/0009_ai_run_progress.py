"""Add AI run progress and cancellation state.

Revision ID: 0009_ai_run_progress
Revises: 0008_size_columns_bigint
"""

import sqlalchemy as sa

from alembic import op

revision = "0009_ai_run_progress"
down_revision = "0008_size_columns_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_processing_runs",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("ai_processing_runs", "progress_percent", server_default=None)
    op.add_column("ai_processing_runs", sa.Column("progress_message", sa.String(500)))
    op.add_column(
        "ai_processing_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True))
    )
    op.add_column("ai_processing_runs", sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("ai_processing_runs", "completed_at")
    op.drop_column("ai_processing_runs", "cancel_requested_at")
    op.drop_column("ai_processing_runs", "progress_message")
    op.drop_column("ai_processing_runs", "progress_percent")
