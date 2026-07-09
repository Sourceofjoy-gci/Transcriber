"""Create report templates and reports.

Revision ID: 0007_reports
Revises: 0006_ai_processing
"""

from alembic import op
from app.db.base import Base

revision = "0007_reports"
down_revision = "0006_ai_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in ["report_templates", "reports"]]
    )


def downgrade() -> None:
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in ["reports", "report_templates"]]
    )
