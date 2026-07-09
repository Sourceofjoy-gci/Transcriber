"""Create external provider configuration tables.

Revision ID: 0004_provider_definitions
Revises: 0003_model_registry
"""

from alembic import op
from app.db.base import Base

revision = "0004_provider_definitions"
down_revision = "0003_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in ["provider_definitions", "provider_secrets"]],
    )


def downgrade() -> None:
    Base.metadata.drop_all(
        bind=op.get_bind(),
        tables=[Base.metadata.tables[name] for name in ["provider_secrets", "provider_definitions"]],
    )
