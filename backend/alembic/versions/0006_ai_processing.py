"""Create AI post-processing runs.

Revision ID: 0006_ai_processing
Revises: 0005_provider_operations
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0006_ai_processing"
down_revision = "0005_provider_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_processing_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("execution_target_kind", sa.String(50), nullable=False),
        sa.Column("execution_target_id", postgresql.UUID(as_uuid=True)),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("output_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("cost_estimate", sa.Numeric(12, 6)),
        sa.Column("error_message", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["output_version_id"], ["transcript_versions.id"]),
        sa.ForeignKeyConstraint(["transcript_version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("ai_processing_runs")
