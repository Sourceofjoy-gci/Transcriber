"""Create report templates and reports.

Revision ID: 0007_reports
Revises: 0006_ai_processing
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_reports"
down_revision = "0006_ai_processing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("prompt_template", sa.Text()),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("processing_run_id", postgresql.UUID(as_uuid=True)),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("content_markdown", sa.Text()),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["processing_run_id"], ["ai_processing_runs.id"]),
        sa.ForeignKeyConstraint(["template_id"], ["report_templates.id"]),
        sa.ForeignKeyConstraint(["transcript_version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "export_records",
        sa.Column("source_type", sa.String(50), nullable=False, server_default="transcript"),
    )
    op.alter_column("export_records", "source_type", server_default=None)
    op.add_column("export_records", sa.Column("source_id", postgresql.UUID(as_uuid=True)))
    op.add_column("export_records", sa.Column("report_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key(
        "fk_export_records_report_id", "export_records", "reports", ["report_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint("fk_export_records_report_id", "export_records", type_="foreignkey")
    op.drop_column("export_records", "report_id")
    op.drop_column("export_records", "source_id")
    op.drop_column("export_records", "source_type")
    op.drop_table("reports")
    op.drop_table("report_templates")
