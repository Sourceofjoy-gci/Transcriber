"""Add transcript editor operation and annotation tables.

Revision ID: 0010_transcript_editor_ops
Revises: 0009_ai_run_progress
"""

from alembic import op
from app.db.base import Base

revision = "0010_transcript_editor_ops"
down_revision = "0009_ai_run_progress"
branch_labels = None
depends_on = None

TABLES = ["transcript_edit_operations", "transcript_annotations"]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in reversed(TABLES)]
    )
