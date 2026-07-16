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
