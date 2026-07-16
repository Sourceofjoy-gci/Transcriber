"""Create transcript and export records.

Revision ID: 0002_transcripts_and_exports
Revises: 0001_initial_foundation
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002_transcripts_and_exports"
down_revision = "0001_initial_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transcripts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("language", sa.String(20)),
        sa.Column("detected_language", sa.String(20)),
        sa.Column("source_provider", sa.String(100), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("change_summary", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_version_id"], ["transcript_versions.id"]),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcript_id", "version_number", name="uq_transcript_version_number"),
    )
    op.create_foreign_key(
        "fk_transcripts_active_version",
        "transcripts",
        "transcript_versions",
        ["active_version_id"],
        ["id"],
    )
    op.create_table(
        "speakers",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcript_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(150)),
        sa.Column("role", sa.String(100)),
        sa.Column("color", sa.String(20)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("speaker_id", postgresql.UUID(as_uuid=True)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.String(50)),
        sa.Column("is_unclear", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.ForeignKeyConstraint(["speaker_id"], ["speakers.id"]),
        sa.ForeignKeyConstraint(["version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "sequence", name="uq_segment_version_sequence"),
    )
    op.create_table(
        "transcript_words",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("segment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("word", sa.String(500), nullable=False),
        sa.Column("confidence", sa.String(50)),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "export_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by_id", postgresql.UUID(as_uuid=True)),
        sa.Column("transcript_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("format", sa.String(20), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("storage_key", sa.String(1000)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["transcript_version_id"], ["transcript_versions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("export_records")
    op.drop_table("transcript_words")
    op.drop_table("transcript_segments")
    op.drop_table("speakers")
    op.drop_constraint("fk_transcripts_active_version", "transcripts", type_="foreignkey")
    op.drop_table("transcript_versions")
    op.drop_table("transcripts")
