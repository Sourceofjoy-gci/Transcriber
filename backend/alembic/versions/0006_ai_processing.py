"""Create AI post-processing runs.

Revision ID: 0006_ai_processing
Revises: 0005_provider_operations
"""

from alembic import op
from app.db.base import Base

revision = "0006_ai_processing"
down_revision = "0005_provider_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind(), tables=[Base.metadata.tables["ai_processing_runs"]])


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind(), tables=[Base.metadata.tables["ai_processing_runs"]])
