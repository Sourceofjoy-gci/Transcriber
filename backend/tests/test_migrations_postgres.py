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


def test_current_head_status_drift_is_reconciled_without_changing_rows() -> None:
    sentinel_id = uuid4()
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", "0011_media_derivatives_retention")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE media_assets ALTER COLUMN status TYPE VARCHAR(10)"))
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


def test_current_head_application_contract_is_backfilled_without_changing_rows() -> None:
    ids = {name: uuid4() for name in (
        "organisation",
        "asset",
        "job",
        "transcript",
        "version_one",
        "version_two",
        "segment",
        "derivative",
        "ai_run",
        "template",
        "report",
        "export",
        "operation",
        "annotation",
        "audit",
    )}
    with temporary_database() as database_url:
        assert_alembic_succeeds(database_url, "upgrade", "0011_media_derivatives_retention")
        engine = create_engine(database_url)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO organisations "
                    "(id, name, slug, external_apis_allowed, local_only_enforced, created_at, updated_at) "
                    "VALUES (:id, 'Contract sentinel', :slug, false, true, now(), now())"
                ),
                {"id": ids["organisation"], "slug": f"contract-{ids['organisation'].hex}"},
            )
            connection.execute(
                text(
                    "INSERT INTO media_assets "
                    "(id, organisation_id, original_filename, content_type, byte_size, sha256, "
                    "storage_key, status, created_at, updated_at) VALUES "
                    "(:id, :organisation_id, 'sentinel.wav', 'audio/wav', 1, :sha256, "
                    ":storage_key, 'ready', now(), now())"
                ),
                {
                    "id": ids["asset"],
                    "organisation_id": ids["organisation"],
                    "sha256": "a" * 64,
                    "storage_key": f"sentinel/{ids['asset']}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO transcription_jobs "
                    "(id, organisation_id, asset_id, execution_target_kind, status, "
                    "progress_percent, options_json, created_at, updated_at) VALUES "
                    "(:id, :organisation_id, :asset_id, 'automatic', 'completed', 100, "
                    "CAST('{}' AS json), now(), now())"
                ),
                {
                    "id": ids["job"],
                    "organisation_id": ids["organisation"],
                    "asset_id": ids["asset"],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO transcripts "
                    "(id, job_id, source_provider, status, created_at, updated_at) VALUES "
                    "(:id, :job_id, 'test', 'completed', now(), now())"
                ),
                {"id": ids["transcript"], "job_id": ids["job"]},
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_versions "
                    "(id, transcript_id, version_number, source, snapshot_json, created_at) VALUES "
                    "(:id, :transcript_id, 1, 'test', CAST('{}' AS json), now())"
                ),
                {"id": ids["version_one"], "transcript_id": ids["transcript"]},
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_versions "
                    "(id, transcript_id, version_number, parent_version_id, source, snapshot_json, "
                    "created_at) VALUES "
                    "(:id, :transcript_id, 2, :parent_id, 'human_edit', CAST('{}' AS json), now())"
                ),
                {
                    "id": ids["version_two"],
                    "transcript_id": ids["transcript"],
                    "parent_id": ids["version_one"],
                },
            )
            connection.execute(
                text("UPDATE transcripts SET active_version_id = :version_id WHERE id = :id"),
                {"version_id": ids["version_two"], "id": ids["transcript"]},
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_segments "
                    "(id, version_id, sequence, start_ms, end_ms, text, is_unclear) VALUES "
                    "(:id, :version_id, 1, 0, 1000, 'Sentinel', false)"
                ),
                {"id": ids["segment"], "version_id": ids["version_two"]},
            )
            connection.execute(
                text(
                    "INSERT INTO media_derivatives "
                    "(id, asset_id, kind, status, byte_size, metadata_json, created_at, updated_at) "
                    "VALUES (:id, :asset_id, 'waveform', 'ready', 1, CAST('{}' AS json), now(), now())"
                ),
                {"id": ids["derivative"], "asset_id": ids["asset"]},
            )
            connection.execute(
                text(
                    "INSERT INTO ai_processing_runs "
                    "(id, transcript_version_id, task, execution_target_kind, options_json, status, "
                    "result_json, progress_percent, created_at, updated_at) VALUES "
                    "(:id, :version_id, 'summary', 'automatic', CAST('{}' AS json), 'completed', "
                    "CAST('{}' AS json), 100, now(), now())"
                ),
                {"id": ids["ai_run"], "version_id": ids["version_two"]},
            )
            connection.execute(
                text(
                    "INSERT INTO report_templates "
                    "(id, organisation_id, name, kind, schema_json, enabled, created_at, updated_at) "
                    "VALUES (:id, :organisation_id, 'Sentinel', 'summary', CAST('{}' AS json), "
                    "true, now(), now())"
                ),
                {"id": ids["template"], "organisation_id": ids["organisation"]},
            )
            connection.execute(
                text(
                    "INSERT INTO reports "
                    "(id, transcript_version_id, template_id, title, content_json, status, "
                    "created_at, updated_at) VALUES "
                    "(:id, :version_id, :template_id, 'Sentinel', CAST('{}' AS json), "
                    "'completed', now(), now())"
                ),
                {
                    "id": ids["report"],
                    "version_id": ids["version_two"],
                    "template_id": ids["template"],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO export_records "
                    "(id, transcript_version_id, report_id, source_type, format, options_json, "
                    "status, created_at, updated_at) VALUES "
                    "(:id, :version_id, :report_id, 'report', 'json', CAST('{}' AS json), "
                    "'completed', now(), now())"
                ),
                {
                    "id": ids["export"],
                    "version_id": ids["version_two"],
                    "report_id": ids["report"],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_edit_operations "
                    "(id, version_id, operation_type, payload_json, created_at) VALUES "
                    "(:id, :version_id, 'segment_edit', CAST('{}' AS json), now())"
                ),
                {"id": ids["operation"], "version_id": ids["version_two"]},
            )
            connection.execute(
                text(
                    "INSERT INTO transcript_annotations "
                    "(id, version_id, segment_id, kind, body, created_at, updated_at) VALUES "
                    "(:id, :version_id, :segment_id, 'note', 'Preserve me', now(), now())"
                ),
                {
                    "id": ids["annotation"],
                    "version_id": ids["version_two"],
                    "segment_id": ids["segment"],
                },
            )
            connection.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, organisation_id, action, resource_type, resource_id, outcome, "
                    "metadata_json, created_at) VALUES "
                    "(:id, :organisation_id, 'sentinel', 'media_asset', :resource_id, "
                    "'success', CAST('{}' AS json), now())"
                ),
                {
                    "id": ids["audit"],
                    "organisation_id": ids["organisation"],
                    "resource_id": str(ids["asset"]),
                },
            )
        engine.dispose()

        assert_alembic_succeeds(database_url, "upgrade", "head")
        assert_alembic_succeeds(database_url, "check")

        engine = create_engine(database_url)
        with engine.connect() as connection:
            for table_name, row_id in (
                ("transcripts", ids["transcript"]),
                ("media_derivatives", ids["derivative"]),
                ("ai_processing_runs", ids["ai_run"]),
                ("reports", ids["report"]),
                ("export_records", ids["export"]),
            ):
                assert connection.scalar(
                    text(f"SELECT organisation_id FROM {table_name} WHERE id = :id"),
                    {"id": row_id},
                ) == ids["organisation"]
            operation = connection.execute(
                text(
                    "SELECT transcript_id, from_version_id, to_version_id "
                    "FROM transcript_edit_operations WHERE id = :id"
                ),
                {"id": ids["operation"]},
            ).one()
            annotation = connection.execute(
                text(
                    "SELECT transcript_id, note, is_unclear "
                    "FROM transcript_annotations WHERE id = :id"
                ),
                {"id": ids["annotation"]},
            ).one()
            audit_resource_id = connection.scalar(
                text("SELECT resource_id FROM audit_logs WHERE id = :id"),
                {"id": ids["audit"]},
            )
        engine.dispose()

        assert tuple(operation) == (
            ids["transcript"],
            ids["version_one"],
            ids["version_two"],
        )
        assert tuple(annotation) == (ids["transcript"], "Preserve me", False)
        assert audit_resource_id == ids["asset"]
