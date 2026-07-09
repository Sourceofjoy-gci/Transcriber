"""Create transcript and export records.

Revision ID: 0002_transcripts_and_exports
Revises: 0001_initial_foundation
Create Date: 2026-06-24
"""

from alembic import op
from app.db.base import Base

revision = "0002_transcripts_and_exports"
down_revision = "0001_initial_foundation"
branch_labels = None
depends_on = None

TABLES = [
    "transcripts",
    "transcript_versions",
    "speakers",
    "transcript_segments",
    "transcript_words",
    "export_records",
]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in reversed(TABLES)]
    )
