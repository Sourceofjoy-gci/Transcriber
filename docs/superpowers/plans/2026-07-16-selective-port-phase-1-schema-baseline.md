# Selective Port Phase 1 Schema Baseline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace mutable Alembic history with explicit PostgreSQL DDL, reconcile the deployed schema safely, and prove a green Python 3.12 backend baseline.

**Architecture:** Preserve the existing revision IDs and make each historical revision self-contained with Alembic and SQLAlchemy operations only. A new `0012_schema_reconciliation` revision widens the one verified deployed-schema drift while disposable PostgreSQL integration tests prove fresh, current-head, legacy, and downgrade/upgrade paths without modifying the running database.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2, Alembic, psycopg 3, PostgreSQL 16, pytest, Ruff, Docker.

## Global Constraints

- PostgreSQL 16 is the only authoritative migration target; SQLite migration success is not acceptance evidence.
- Preserve all existing Alembic revision IDs, application identifiers, and deployed rows.
- Historical revision modules may import Alembic and SQLAlchemy only; they may not import `Base`, domain models, settings, providers, or services.
- Never execute `Base.metadata.create_all` or `Base.metadata.drop_all` from an Alembic revision.
- Never migrate, truncate, stamp, or otherwise mutate the running `transcriber-postgres-1` database or its persistent volume.
- Run destructive migration tests only against disposable PostgreSQL databases on an isolated Docker network.
- Use Python 3.12 and the existing dependency lock; do not regenerate or prune dependencies in Phase 1.
- Keep application external-provider egress disabled during verification.
- Do not add durable chunks, model-runtime fields, provider changes, worker topology changes, frontend changes, Voicebox imports, TTS, voice cloning, Tauri, or story generation.
- Every behavior-changing correction follows red-green-refactor.

---

### Task 1: Controlled Python 3.12 Test Runtime and Explicit Foundation Revision

**Files:**

- Create: `backend/Dockerfile.test`
- Modify: `backend/alembic.ini`
- Modify: `backend/tests/test_migrations.py`
- Modify: `backend/alembic/versions/0001_initial_foundation.py`

**Interfaces:**

- Consumes: `backend/requirements.lock`, `backend/pyproject.toml`, the existing Alembic revision directory.
- Produces: local image `transcriber-backend-test:phase1`; `EXPLICIT_DDL_REVISIONS`; deterministic foundation schema through revision `0001_initial_foundation`.

- [ ] **Step 1: Create the locked Python 3.12 test image definition**

```dockerfile
FROM transcriber-api:latest

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

USER root
WORKDIR /app
COPY backend/pyproject.toml backend/requirements.lock ./
RUN pip install --no-cache-dir -c requirements.lock -e ".[dev]"

COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/alembic.ini ./
COPY backend/Dockerfile ./Dockerfile
COPY backend/tests ./tests
COPY infra /infra

USER appuser
CMD ["pytest", "-q"]
```

- [ ] **Step 2: Build the controlled test image**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 .`

Expected: exit 0 with Python 3.12, pytest, Ruff, and locked backend dependencies installed.

- [ ] **Step 3: Replace the migration unit test with graph and source-contract tests**

```python
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"

EXPLICIT_DDL_REVISIONS = {
    "0001_initial_foundation.py",
}

FORBIDDEN_HISTORICAL_DDL = (
    "Base.metadata.create_all",
    "Base.metadata.drop_all",
    "from app.",
    "import app.",
    "_column_exists",
    "sa.inspect",
    "inspect(",
)


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_revision_graph_has_one_head_and_unique_short_ids() -> None:
    script = _script_directory()
    revisions = list(script.walk_revisions())
    revision_ids = [item.revision for item in revisions]

    assert len(script.get_heads()) == 1
    assert len(revision_ids) == len(set(revision_ids))
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)


@pytest.mark.parametrize("filename", sorted(EXPLICIT_DDL_REVISIONS))
def test_historical_revision_uses_only_explicit_ddl(filename: str) -> None:
    source = (VERSIONS_DIR / filename).read_text(encoding="utf-8")
    violations = [token for token in FORBIDDEN_HISTORICAL_DDL if token in source]
    assert violations == []
```

- [ ] **Step 4: Run the source-contract test and verify RED**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm transcriber-backend-test:phase1 pytest tests/test_migrations.py -q`

Expected: FAIL for `0001_initial_foundation.py` with forbidden `Base.metadata` and `from app.` tokens.

- [ ] **Step 5: Replace `0001_initial_foundation.py` with explicit foundation DDL**

Use these self-contained helpers and table declarations; retain the existing revision metadata:

```python
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
```

- [ ] **Step 6: Rebuild and verify GREEN**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm transcriber-backend-test:phase1 pytest tests/test_migrations.py -q`

Expected: 2 tests pass.

- [ ] **Step 7: Commit the controlled test runtime and explicit foundation**

```bash
git add backend/Dockerfile.test backend/alembic.ini backend/tests/test_migrations.py backend/alembic/versions/0001_initial_foundation.py docs/superpowers/plans/2026-07-16-selective-port-phase-1-schema-baseline.md
git commit -m "fix: freeze foundation migration ddl"
```

### Task 2: PostgreSQL Upgrade Harness and Transcript/Report History

**Files:**

- Modify: `backend/tests/test_migrations.py`
- Create: `backend/tests/test_migrations_postgres.py`
- Modify: `backend/alembic/versions/0002_transcripts_and_exports.py`
- Modify: `backend/alembic/versions/0006_ai_processing.py`
- Modify: `backend/alembic/versions/0007_reports.py`
- Modify: `backend/alembic/versions/0009_ai_run_progress.py`
- Modify: `backend/alembic/versions/0010_transcript_editor_operations.py`

**Interfaces:**

- Consumes: `TEST_DATABASE_ADMIN_URL`; revision `0001_initial_foundation` from Task 1.
- Produces: `temporary_database()` and `run_alembic()` test helpers; dependency-safe transcript/report DDL; deterministic AI-progress DDL.

- [ ] **Step 1: Expand the explicit-revision source contract before editing history**

Add these filenames to `EXPLICIT_DDL_REVISIONS`:

```python
    "0002_transcripts_and_exports.py",
    "0006_ai_processing.py",
    "0007_reports.py",
    "0009_ai_run_progress.py",
    "0010_transcript_editor_operations.py",
```

- [ ] **Step 2: Add the disposable PostgreSQL integration harness and acceptance tests**

```python
from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app.models.domain import Base

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("TEST_DATABASE_ADMIN_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="TEST_DATABASE_ADMIN_URL is required for PostgreSQL migration acceptance",
)


@contextmanager
def temporary_database() -> Iterator[str]:
    assert ADMIN_URL is not None
    admin_url = make_url(ADMIN_URL)
    database_name = f"transcriber_migration_{uuid4().hex}"
    connect_kwargs = {
        "host": admin_url.host,
        "port": admin_url.port,
        "dbname": admin_url.database,
        "user": admin_url.username,
        "password": admin_url.password,
        "autocommit": True,
    }
    with psycopg.connect(**connect_kwargs) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))
    database_url = admin_url.set(database=database_name).render_as_string(hide_password=False)
    try:
        yield database_url
    finally:
        with psycopg.connect(**connect_kwargs) as connection:
            connection.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            connection.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))


def run_alembic(database_url: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET_KEY": "migration-test-app-secret-that-is-long-enough",
            "CREDENTIAL_ENCRYPTION_KEY": "migration-test-encryption-key-long-enough",
            "DATABASE_URL": database_url,
            "REDIS_URL": "redis://unused:6379/0",
            "EXTERNAL_APIS_ALLOWED": "false",
            "LOCAL_ONLY_ENFORCED": "true",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def assert_alembic_succeeds(database_url: str, *arguments: str) -> None:
    result = run_alembic(database_url, *arguments)
    assert result.returncode == 0, result.stdout + result.stderr


def test_empty_postgresql_database_upgrades_to_head_and_matches_models() -> None:
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "check")

        engine = create_engine(database_url)
        inspector = inspect(engine)
        assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {"alembic_version"}
        for table_name, table in Base.metadata.tables.items():
            assert {column["name"] for column in inspector.get_columns(table_name)} == set(
                table.columns.keys()
            )
        engine.dispose()


@pytest.mark.parametrize(
    "legacy_revision",
    ["0001_initial_foundation", "0005_provider_operations", "0007_reports"],
)
def test_representative_legacy_revision_preserves_identifiers(legacy_revision: str) -> None:
    sentinel_id = uuid4()
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", legacy_revision)
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organisations "
                    "(id, name, slug, external_apis_allowed, local_only_enforced, created_at, updated_at) "
                    "VALUES (:id, 'Sentinel', :slug, false, true, now(), now())"
                ),
                {"id": sentinel_id, "slug": f"sentinel-{sentinel_id.hex}"},
            )
        engine.dispose()

        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "check")

        engine = create_engine(database_url)
        with engine.connect() as connection:
            stored_id = connection.scalar(
                text("SELECT id FROM organisations WHERE id = :id"), {"id": sentinel_id}
            )
        engine.dispose()
        assert stored_id == sentinel_id
        assert isinstance(stored_id, UUID)


def test_upgrade_downgrade_upgrade_cycle() -> None:
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "downgrade", "base")
        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "check")
```

- [ ] **Step 3: Start a disposable PostgreSQL 16 service and verify RED**

Run:

```bash
docker network create --internal transcriber_phase1_test
docker run -d --name transcriber_phase1_pg --network transcriber_phase1_test --tmpfs /var/lib/postgresql/data:rw,noexec,nosuid,size=1g -e POSTGRES_DB=postgres -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres postgres:16-alpine
docker exec transcriber_phase1_pg pg_isready -U postgres -d postgres
docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 .
docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest tests/test_migrations.py tests/test_migrations_postgres.py -q
```

Expected: source-contract failures plus the empty-upgrade failure caused by metadata-dependent transcript/report history.

- [ ] **Step 4: Replace `0002_transcripts_and_exports.py` with dependency-safe explicit DDL**

Create `transcripts` without its cyclic active-version foreign key, create `transcript_versions`, add named constraint `fk_transcripts_active_version`, then create speakers, segments, words, and the initial export table. Use `sa.String(10)` for transcript/export status columns and omit `report_id`, `source_type`, and `source_id` until `0007`.

```python
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
```

- [ ] **Step 5: Freeze AI-processing and report revisions**

`0006_ai_processing.py` creates the base AI run without progress fields. `0007_reports.py` creates report tables, then adds report-aware export columns in dependency order:

```python
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
```

Replace `0006_ai_processing.py` with:

```python
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
```

Replace `0009_ai_run_progress.py` with:

```python
import sqlalchemy as sa

from alembic import op

revision = "0009_ai_run_progress"
down_revision = "0008_size_columns_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ai_processing_runs",
        sa.Column("progress_percent", sa.Integer(), nullable=False, server_default="0"),
    )
    op.alter_column("ai_processing_runs", "progress_percent", server_default=None)
    op.add_column("ai_processing_runs", sa.Column("progress_message", sa.String(500)))
    op.add_column(
        "ai_processing_runs", sa.Column("cancel_requested_at", sa.DateTime(timezone=True))
    )
    op.add_column("ai_processing_runs", sa.Column("completed_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("ai_processing_runs", "completed_at")
    op.drop_column("ai_processing_runs", "cancel_requested_at")
    op.drop_column("ai_processing_runs", "progress_message")
    op.drop_column("ai_processing_runs", "progress_percent")
```

- [ ] **Step 6: Freeze transcript editor tables in `0010`**

Replace `0010_transcript_editor_operations.py` with:

```python
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
```

- [ ] **Step 7: Rebuild and verify transcript/report history GREEN**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest tests/test_migrations.py tests/test_migrations_postgres.py -q`

Expected: all migration source-contract, fresh-upgrade, legacy-upgrade, and downgrade/upgrade tests pass.

- [ ] **Step 8: Commit transcript/report history**

```bash
git add backend/tests/test_migrations.py backend/tests/test_migrations_postgres.py backend/alembic/versions/0002_transcripts_and_exports.py backend/alembic/versions/0006_ai_processing.py backend/alembic/versions/0007_reports.py backend/alembic/versions/0009_ai_run_progress.py backend/alembic/versions/0010_transcript_editor_operations.py
git commit -m "fix: freeze transcript and report migrations"
```

### Task 3: Explicit Model and Provider History

**Files:**

- Modify: `backend/tests/test_migrations.py`
- Modify: `backend/alembic/versions/0003_model_registry.py`
- Modify: `backend/alembic/versions/0004_provider_definitions.py`
- Modify: `backend/alembic/versions/0005_provider_operations.py`

**Interfaces:**

- Consumes: foundation organisations/users/jobs from `0001`.
- Produces: deterministic catalog/provider schema with lifecycle fields added only in `0005`.

- [ ] **Step 1: Add `0003`, `0004`, and `0005` to the explicit source-contract set and verify RED**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm transcriber-backend-test:phase1 pytest tests/test_migrations.py -q`

Expected: three failing parameters caused by application imports, metadata DDL, or inspector-driven conditional history.

- [ ] **Step 2: Replace `0003_model_registry.py` with explicit model tables**

Replace the module with the following; revision `0008` remains responsible for widening `model_catalog.size_bytes` to `BIGINT`:

```python
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
        sa.UniqueConstraint(
            "organisation_id", "task", name="uq_model_task_default_org_task"
        ),
    )


def downgrade() -> None:
    op.drop_table("model_task_defaults")
    op.drop_table("installed_models")
    op.drop_table("model_catalog")
```

- [ ] **Step 3: Replace `0004_provider_definitions.py` with the initial provider shape**

Create `provider_definitions` without the five lifecycle fields owned by `0005`, then create `provider_secrets`:

```python
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004_provider_definitions"
down_revision = "0003_model_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organisation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("adapter_key", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("base_url", sa.String(1000)),
        sa.Column("endpoint_path", sa.String(500), nullable=False),
        sa.Column("model_name", sa.String(300)),
        sa.Column("auth_type", sa.String(100), nullable=False),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["organisation_id"], ["organisations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "provider_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(200), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provider_secrets")
    op.drop_table("provider_definitions")
```

- [ ] **Step 4: Make `0005_provider_operations.py` deterministic**

Replace the module with:

```python
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0005_provider_operations"
down_revision = "0004_provider_definitions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "provider_definitions",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("provider_definitions", "is_default", server_default=None)
    op.add_column(
        "provider_definitions",
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="120"),
    )
    op.alter_column("provider_definitions", "timeout_seconds", server_default=None)
    op.add_column(
        "provider_definitions",
        sa.Column("retry_limit", sa.Integer(), nullable=False, server_default="2"),
    )
    op.alter_column("provider_definitions", "retry_limit", server_default=None)
    op.add_column(
        "provider_definitions", sa.Column("last_tested_at", sa.DateTime(timezone=True))
    )
    op.add_column("provider_definitions", sa.Column("last_error", sa.String(500)))
    op.create_table(
        "provider_usage_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True)),
        sa.Column("task", sa.String(100), nullable=False),
        sa.Column("request_id", sa.String(200)),
        sa.Column("input_units", sa.Integer()),
        sa.Column("output_units", sa.Integer()),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("estimated_cost", sa.Numeric(12, 6)),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("error_code", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"]),
        sa.ForeignKeyConstraint(["provider_id"], ["provider_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("provider_usage_logs")
    op.drop_column("provider_definitions", "last_error")
    op.drop_column("provider_definitions", "last_tested_at")
    op.drop_column("provider_definitions", "retry_limit")
    op.drop_column("provider_definitions", "timeout_seconds")
    op.drop_column("provider_definitions", "is_default")
```

- [ ] **Step 5: Rebuild and verify model/provider history GREEN**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest tests/test_migrations.py tests/test_migrations_postgres.py -q`

Expected: all migration tests pass and `alembic check` reports no generated operations.

- [ ] **Step 6: Commit explicit model/provider history**

```bash
git add backend/tests/test_migrations.py backend/alembic/versions/0003_model_registry.py backend/alembic/versions/0004_provider_definitions.py backend/alembic/versions/0005_provider_operations.py
git commit -m "fix: freeze model and provider migrations"
```

### Task 4: Explicit Retention DDL and Forward Reconciliation

**Files:**

- Modify: `backend/tests/test_migrations.py`
- Modify: `backend/tests/test_migrations_postgres.py`
- Modify: `backend/alembic/versions/0011_media_derivatives_retention.py`
- Create: `backend/alembic/versions/0012_schema_reconciliation.py`

**Interfaces:**

- Consumes: canonical explicit schema at `0010_transcript_editor_ops`.
- Produces: explicit media derivative schema; `0012_schema_reconciliation`; safe widening of `media_assets.status` from known `VARCHAR(10)` drift to `VARCHAR(19)`.

- [ ] **Step 1: Add `0008` and `0011` to the explicit source-contract set and verify RED**

Add both filenames so the final historical set covers every revision before reconciliation:

```python
    "0008_size_columns_bigint.py",
    "0011_media_derivatives_retention.py",
```

Expected: failure caused by inspector-driven conditional DDL and ORM metadata imports.

- [ ] **Step 2: Add the current-head drift acceptance test before creating `0012`**

```python
def test_current_head_status_drift_is_reconciled_without_changing_rows() -> None:
    sentinel_id = uuid4()
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", "0011_media_derivatives_retention")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE media_assets ALTER COLUMN status TYPE VARCHAR(10)")
            )
            connection.execute(
                text(
                    "INSERT INTO organisations "
                    "(id, name, slug, external_apis_allowed, local_only_enforced, created_at, updated_at) "
                    "VALUES (:id, 'Current sentinel', :slug, false, true, now(), now())"
                ),
                {"id": sentinel_id, "slug": f"current-{sentinel_id.hex}"},
            )
        engine.dispose()

        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "check")

        engine = create_engine(database_url)
        status_column = next(
            column for column in inspect(engine).get_columns("media_assets") if column["name"] == "status"
        )
        with engine.connect() as connection:
            stored_id = connection.scalar(
                text("SELECT id FROM organisations WHERE id = :id"), {"id": sentinel_id}
            )
        engine.dispose()
        assert status_column["type"].length == 19
        assert stored_id == sentinel_id
```

Run the focused test before adding `0012`.

Expected: FAIL because `head` is still `0011` and the status column remains length 10.

- [ ] **Step 3: Replace `0011` with explicit retention DDL**

Replace the module with:

```python
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
```

- [ ] **Step 4: Add `0012_schema_reconciliation.py`**

```python
"""Reconcile known schema drift in already-deployed databases.

Revision ID: 0012_schema_reconciliation
Revises: 0011_media_derivatives_retention
"""

import sqlalchemy as sa

from alembic import op

revision = "0012_schema_reconciliation"
down_revision = "0011_media_derivatives_retention"
branch_labels = None
depends_on = None

ASSET_STATUS_LENGTH = 19


def _status_length() -> int:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "media_assets" not in inspector.get_table_names():
        raise RuntimeError("Cannot reconcile schema: table media_assets is missing")
    status_column = next(
        (column for column in inspector.get_columns("media_assets") if column["name"] == "status"),
        None,
    )
    if status_column is None:
        raise RuntimeError("Cannot reconcile schema: column media_assets.status is missing")
    column_type = status_column["type"]
    if not isinstance(column_type, sa.String) or column_type.length is None:
        raise RuntimeError("Cannot reconcile schema: media_assets.status is not a bounded string")
    return column_type.length


def upgrade() -> None:
    current_length = _status_length()
    if current_length == ASSET_STATUS_LENGTH:
        return
    if current_length > ASSET_STATUS_LENGTH:
        raise RuntimeError(
            "Cannot reconcile schema safely: media_assets.status is wider than the canonical length 19"
        )
    with op.batch_alter_table("media_assets") as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.String(length=current_length),
            type_=sa.String(length=ASSET_STATUS_LENGTH),
            existing_nullable=False,
        )


def downgrade() -> None:
    return None
```

Add a source test for the reconciliation module, where schema inspection is allowed but application imports and ORM-driven DDL remain forbidden:

```python
def test_reconciliation_revision_has_no_application_dependency() -> None:
    source = (VERSIONS_DIR / "0012_schema_reconciliation.py").read_text(encoding="utf-8")
    forbidden = (
        "Base.metadata.create_all",
        "Base.metadata.drop_all",
        "from app.",
        "import app.",
    )
    assert [token for token in forbidden if token in source] == []
```

- [ ] **Step 5: Rebuild and verify reconciliation GREEN**

Run: `docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 . && docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest tests/test_migrations.py tests/test_migrations_postgres.py -q`

Expected: all migration tests pass; the drift fixture is widened; sentinel ID is unchanged; fresh upgrade requires no reconciliation DDL.

- [ ] **Step 6: Commit retention and reconciliation**

```bash
git add backend/tests/test_migrations.py backend/tests/test_migrations_postgres.py backend/alembic/versions/0011_media_derivatives_retention.py backend/alembic/versions/0012_schema_reconciliation.py
git commit -m "fix: reconcile canonical postgres schema"
```

### Task 5: CI Enforcement and Backend Baseline Proof

**Files:**

- Modify: `.github/workflows/ci.yml`
- Create: `backend/tests/test_startup_baseline.py`

**Interfaces:**

- Consumes: migration acceptance tests and canonical head from Tasks 1–4.
- Produces: mandatory PostgreSQL migration execution in CI; isolated liveness/import characterization.

- [ ] **Step 1: Add the liveness/import characterization test**

```python
import os
import subprocess
import sys
from pathlib import Path


def test_application_import_and_liveness_need_no_model_or_external_egress() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET_KEY": "startup-test-secret-that-is-long-enough",
            "CREDENTIAL_ENCRYPTION_KEY": "startup-encryption-key-that-is-long-enough",
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "REDIS_URL": "redis://unused:6379/0",
            "EXTERNAL_APIS_ALLOWED": "false",
            "LOCAL_ONLY_ENFORCED": "true",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import live; assert live() == {'status': 'ok'}",
        ],
        cwd=backend_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
```

- [ ] **Step 2: Add PostgreSQL 16 to the CI backend job**

Add a PostgreSQL service to `jobs.backend` with database/user/password `postgres`, health command `pg_isready -U postgres`, and port `5432:5432`. Set:

```yaml
    env:
      TEST_DATABASE_ADMIN_URL: postgresql+psycopg://postgres:postgres@localhost:5432/postgres
```

Keep the existing locked install, Ruff, and pytest commands unchanged.

- [ ] **Step 3: Run Ruff and the complete backend suite in the isolated test network**

Run:

```bash
docker build -f backend/Dockerfile.test -t transcriber-backend-test:phase1 .
docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 ruff check app tests
docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest -q
```

Expected: Ruff exits 0; pytest reports zero failures and zero errors, with PostgreSQL migration tests executed rather than skipped.

- [ ] **Step 4: Commit CI and baseline proof**

```bash
git add .github/workflows/ci.yml backend/tests/test_startup_baseline.py
git commit -m "test: enforce postgres migration baseline"
```

### Task 6: Supersession and Migration Documentation

**Files:**

- Modify: `docs/00-planning-index.md`
- Modify: `docs/11-deployment-runbook.md`
- Modify: `docs/13-completion-report.md`
- Modify: `docs/14-implementation-status.md`
- Modify: `docs/15-production-readiness-report.md`
- Modify: `docs/superpowers/specs/2026-07-10-production-readiness-design.md`
- Modify: `docs/superpowers/plans/2026-07-10-production-readiness.md`
- Modify: `docs/superpowers/specs/2026-07-13-universal-model-downloads-design.md`
- Modify: `docs/superpowers/plans/2026-07-13-universal-model-downloads.md`

**Interfaces:**

- Consumes: verified Phase 1 commands and commit history.
- Produces: one governing selective-port direction and accurate migration/operator claims.

- [ ] **Step 1: Mark all four conflicting July documents as superseded**

Immediately below each title, add:

```markdown
> **Historical plan:** Superseded by the approved selective-port program and its Phase 1 schema-baseline design dated 2026-07-16. Retained for audit history; do not execute as the governing implementation plan.
```

- [ ] **Step 2: Correct historical completion-report claims**

Add a prominent note to `docs/13-completion-report.md` and `docs/15-production-readiness-report.md` stating that their empty-migration claims were invalidated on 2026-07-16 by a reproducible PostgreSQL failure at `0002`, and link to the Phase 1 design. Preserve the original report body as historical evidence.

- [ ] **Step 3: Update planning, status, and operator guidance**

Document these exact rules:

- the 2026-07-16 selective-port design is governing;
- PostgreSQL 16 is the authoritative migration target;
- production operators run Alembic as a controlled one-shot deployment step before API rollout rather than relying on API startup;
- schema backup is required before upgrades;
- Voicebox databases are never merged into the application schema; and
- TTS, voice cloning, Tauri, and story generation are excluded.

- [ ] **Step 4: Verify documentation and commit**

Run: `rg -n "Superseded|PostgreSQL 16|0012_schema_reconciliation|Voicebox|voice cloning" docs`

Expected: governing and historical documents are clearly distinguished and migration guidance names the new head.

```bash
git add docs
git diff --cached --check
git commit -m "docs: supersede conflicting readiness plans"
```

### Task 7: Final Phase 1 Verification and Cleanup

**Files:**

- Modify only if a verification command exposes a defect, and then add a failing regression test before the correction.

**Interfaces:**

- Consumes: all Phase 1 tasks.
- Produces: fresh evidence for the completion criteria and a clean feature branch.

- [ ] **Step 1: Rebuild the test image from the final source**

Run: `docker build --no-cache -f backend/Dockerfile.test -t transcriber-backend-test:phase1 .`

Expected: exit 0 using Python 3.12 and the committed lock.

- [ ] **Step 2: Run complete migration and backend verification**

Run:

```bash
docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 ruff check app tests
docker run --rm --network transcriber_phase1_test -e TEST_DATABASE_ADMIN_URL=postgresql+psycopg://postgres:postgres@transcriber_phase1_pg:5432/postgres transcriber-backend-test:phase1 pytest -q
docker compose config --quiet
git diff --check
```

Expected: every command exits 0; PostgreSQL migration tests execute; no application test fails.

- [ ] **Step 3: Prove the live development database remained unchanged**

Run: `docker exec transcriber-postgres-1 psql -U transcriber -d transcriber -X -Atc "SELECT version_num FROM alembic_version"`

Expected: `0011_media_derivatives_retention`, proving Phase 1 tests did not upgrade the running database.

- [ ] **Step 4: Remove disposable resources**

Run:

```bash
docker rm -f transcriber_phase1_pg
docker network rm transcriber_phase1_test
```

Expected: both resources are removed; persistent Transcriber containers and volumes remain running.

- [ ] **Step 5: Verify branch state and review commit boundaries**

Run: `git status --short --branch && git log --oneline --decorate -8`

Expected: clean feature branch with separate commits for foundation DDL, transcript/report history, model/provider history, reconciliation, CI proof, and documentation.
