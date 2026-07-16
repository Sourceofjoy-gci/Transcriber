"""Create Phase 1 foundation schema.

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-06-24
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0001_initial_foundation"
down_revision = None
branch_labels = None
depends_on = None


def _uuid(name: str = "id", *, nullable: bool = False) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "organisations",
        _uuid(),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(120), nullable=False),
        sa.Column("external_apis_allowed", sa.Boolean(), nullable=False),
        sa.Column("local_only_enforced", sa.Boolean(), nullable=False),
        sa.Column("retention_days", sa.Integer()),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_organisations_slug", "organisations", ["slug"], unique=True)
    op.create_table(
        "users",
        _uuid(),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(500), nullable=False),
        sa.Column("display_name", sa.String(200)),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "roles",
        _uuid(),
        _uuid("organisation_id", nullable=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "code", name="uq_roles_org_code"),
    )
    op.create_table(
        "permissions",
        _uuid(),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("description", sa.String(500)),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_table(
        "role_permissions",
        _uuid("role_id"),
        _uuid("permission_id"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )
    op.create_table(
        "organisation_memberships",
        _uuid(),
        _uuid("organisation_id"),
        _uuid("user_id"),
        _uuid("role_id"),
        sa.Column("status", sa.String(9), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "user_id", name="uq_membership_org_user"),
    )
    op.create_table(
        "projects",
        _uuid(),
        _uuid("organisation_id"),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("sensitivity", sa.String(50), nullable=False),
        sa.Column("retention_days", sa.Integer()),
        sa.Column("external_apis_allowed", sa.Boolean()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "media_assets",
        _uuid(),
        _uuid("organisation_id"),
        _uuid("project_id", nullable=True),
        _uuid("uploaded_by_id", nullable=True),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("content_type", sa.String(200), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(19), nullable=False),
        sa.Column("failure_code", sa.String(100)),
        sa.Column("failure_message", sa.Text()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "media_metadata",
        _uuid("asset_id"),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("container", sa.String(100)),
        sa.Column("audio_codec", sa.String(100)),
        sa.Column("video_codec", sa.String(100)),
        sa.Column("sample_rate_hz", sa.Integer()),
        sa.Column("channels", sa.Integer()),
        sa.Column("bit_rate", sa.Integer()),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"]),
        sa.PrimaryKeyConstraint("asset_id"),
    )
    op.create_table(
        "transcription_jobs",
        _uuid(),
        _uuid("organisation_id"),
        _uuid("asset_id"),
        _uuid("requested_by_id", nullable=True),
        sa.Column("execution_target_kind", sa.String(50), nullable=False),
        _uuid("execution_target_id", nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(20)),
        sa.Column("options_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("processing_ms", sa.Integer()),
        sa.Column("cost_estimate", sa.Numeric(12, 6)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        *_timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["media_assets.id"]),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_attempts",
        _uuid(),
        _uuid("job_id"),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(200)),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("error_detail", sa.Text()),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_events",
        _uuid(),
        _uuid("job_id"),
        _uuid("attempt_id", nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["job_attempts.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "refresh_tokens",
        _uuid(),
        _uuid("user_id"),
        sa.Column("token_hash", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        _uuid("replaced_by_id", nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["refresh_tokens.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_refresh_tokens_token_hash", "refresh_tokens", ["token_hash"])
    op.create_table(
        "system_settings",
        _uuid(),
        _uuid("organisation_id", nullable=True),
        sa.Column("key", sa.String(200), nullable=False),
        sa.Column("value_json", sa.JSON(), nullable=False),
        sa.Column("is_secret", sa.Boolean(), nullable=False),
        _uuid("updated_by_id", nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organisation_id", "key", name="uq_system_settings_org_key"),
    )
    op.create_table(
        "audit_logs",
        _uuid(),
        _uuid("organisation_id", nullable=True),
        _uuid("actor_id", nullable=True),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(100)),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("ip_hash", sa.String(128)),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("system_settings")
    op.drop_index("ix_refresh_tokens_token_hash", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("job_events")
    op.drop_table("job_attempts")
    op.drop_table("transcription_jobs")
    op.drop_table("media_metadata")
    op.drop_table("media_assets")
    op.drop_table("projects")
    op.drop_table("organisation_memberships")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
    op.drop_index("ix_organisations_slug", table_name="organisations")
    op.drop_table("organisations")
