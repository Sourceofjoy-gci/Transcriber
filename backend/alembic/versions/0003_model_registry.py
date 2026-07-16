"""Create model catalog and installation records.

Revision ID: 0003_model_registry
Revises: 0002_transcripts_and_exports
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0003_model_registry"
down_revision = "0002_transcripts_and_exports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("adapter_key", sa.String(100), nullable=False),
        sa.Column("model_identifier", sa.String(300), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("model_type", sa.String(100), nullable=False),
        sa.Column("source_url", sa.String(1000)),
        sa.Column("revision", sa.String(200)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("requirements_json", sa.JSON(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("checksum", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "adapter_key", "model_identifier", name="uq_model_catalog_adapter_identifier"
        ),
    )
    op.create_table(
        "installed_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("catalog_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column("status", sa.String(11), nullable=False),
        sa.Column("download_progress", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("hardware_compatibility_json", sa.JSON(), nullable=False),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["catalog_id"], ["model_catalog.id"]),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_task_defaults",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("execution_target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "task", name="uq_model_task_default_org_task"),
    )


def downgrade() -> None:
    op.drop_table("model_task_defaults")
    op.drop_table("installed_models")
    op.drop_table("model_catalog")
