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


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    columns = [
        (
            "progress_percent",
            sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
        ),
        ("progress_message", sa.Column("progress_message", sa.String(length=500))),
        ("cancel_requested_at", sa.Column("cancel_requested_at", sa.DateTime(timezone=True))),
        ("completed_at", sa.Column("completed_at", sa.DateTime(timezone=True))),
    ]
    for name, column in columns:
        if not _column_exists("ai_processing_runs", name):
            op.add_column("ai_processing_runs", column)


def downgrade() -> None:
    for column in ["completed_at", "cancel_requested_at", "progress_message", "progress_percent"]:
        if _column_exists("ai_processing_runs", column):
            op.drop_column("ai_processing_runs", column)
