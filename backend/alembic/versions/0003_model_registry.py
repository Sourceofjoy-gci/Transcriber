"""Create model catalog and installation records.

Revision ID: 0003_model_registry
Revises: 0002_transcripts_and_exports
Create Date: 2026-06-24
"""

from alembic import op
from app.db.base import Base

revision = "0003_model_registry"
down_revision = "0002_transcripts_and_exports"
branch_labels = None
depends_on = None

TABLES = ["model_catalog", "installed_models", "model_task_defaults"]


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in TABLES])


def downgrade() -> None:
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in reversed(TABLES)]
    )
