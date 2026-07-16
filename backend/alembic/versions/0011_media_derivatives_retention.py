"""Add media derivatives and retention legal holds.

Revision ID: 0011_media_derivatives_retention
Revises: 0010_transcript_editor_ops
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0011_media_derivatives_retention"
down_revision = "0010_transcript_editor_ops"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "media_assets", sa.Column("legal_hold_until", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_table(
        "media_derivatives",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column("sha256", sa.String(64)),
        sa.Column("content_type", sa.String(200)),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("failure_message", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("media_derivatives")
    op.drop_column("media_assets", "legal_hold_until")
