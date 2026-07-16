"""Add transcript editor operation and annotation tables.

Revision ID: 0010_transcript_editor_ops
Revises: 0009_ai_run_progress
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0010_transcript_editor_ops"
down_revision = "0009_ai_run_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcript_edit_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("operation_type", sa.String(100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True)),
        sa.Column("author_id", postgresql.UUID(as_uuid=True)),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("start_offset", sa.Integer()),
        sa.Column("end_offset", sa.Integer()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("transcript_annotations")
    op.drop_table("transcript_edit_operations")
