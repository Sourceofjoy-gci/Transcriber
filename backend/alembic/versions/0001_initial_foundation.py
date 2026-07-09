"""Create Phase 1 foundation schema.

Revision ID: 0001_initial_foundation
Revises:
Create Date: 2026-06-24
"""

from alembic import op
from app.db.base import Base

revision = "0001_initial_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    foundation_tables = [
        "organisations",
        "users",
        "roles",
        "permissions",
        "role_permissions",
        "organisation_memberships",
        "projects",
        "media_assets",
        "media_metadata",
        "transcription_jobs",
        "job_attempts",
        "job_events",
        "refresh_tokens",
        "system_settings",
        "audit_logs",
    ]
    Base.metadata.create_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in foundation_tables]
    )


def downgrade() -> None:
    foundation_tables = [
        "audit_logs",
        "system_settings",
        "refresh_tokens",
        "job_events",
        "job_attempts",
        "transcription_jobs",
        "media_metadata",
        "media_assets",
        "projects",
        "organisation_memberships",
        "role_permissions",
        "permissions",
        "roles",
        "users",
        "organisations",
    ]
    Base.metadata.drop_all(
        bind=op.get_bind(), tables=[Base.metadata.tables[name] for name in foundation_tables]
    )
