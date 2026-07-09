"""Extend provider lifecycle and usage tracking.

Revision ID: 0005_provider_operations
Revises: 0004_provider_definitions
"""

import sqlalchemy as sa

from alembic import op
from app.db.base import Base

revision = "0005_provider_operations"
down_revision = "0004_provider_definitions"
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    """Inspect the live database to see if a column already exists."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column in {c["name"] for c in inspector.get_columns(table)}


def upgrade() -> None:
    # 0004 created provider_definitions via Base.metadata.create_all, which
    # already included the full model. Add only the columns that are missing
    # so this migration stays idempotent on the current schema definition.
    add_columns = [
        ("is_default", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false())),
        ("timeout_seconds", sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120")),
        ("retry_limit", sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="2")),
        ("last_tested_at", sa.Column("last_tested_at", sa.DateTime(timezone=True))),
        ("last_error", sa.Column("last_error", sa.String(length=500))),
    ]
    for name, column in add_columns:
        if not _column_exists("provider_definitions", name):
            op.add_column("provider_definitions", column)

    # endpoint_path was already created in 0004, but the model has a default
    # value of "/audio/transcriptions"; back-fill any rows where it is null
    # (defensive only).
    op.execute(
        "UPDATE provider_definitions SET endpoint_path = '/audio/transcriptions' WHERE endpoint_path IS NULL"
    )

    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["provider_usage_logs"]])


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables["provider_usage_logs"]])
    for column in ["last_error", "last_tested_at", "retry_limit", "timeout_seconds", "is_default"]:
        if _column_exists("provider_definitions", column):
            op.drop_column("provider_definitions", column)
