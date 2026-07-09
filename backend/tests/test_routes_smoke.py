"""Smoke tests that exercise the FastAPI app end-to-end.

These tests bind a single in-memory engine for the whole module so we don't
have to reload every dependent module per test.
"""

import base64
import importlib
import os
import secrets
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

# Module-level: configure env vars and build the engine BEFORE importing app
# modules so they bind to it at import time.
_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

os.environ.setdefault("APP_SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "a-very-safe-bootstrap-password-1")
os.environ.setdefault("EXTERNAL_APIS_ALLOWED", "true")
os.environ.setdefault("LOCAL_ONLY_ENFORCED", "false")

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import session as session_module  # noqa: E402
from app.db.base import Base  # noqa: E402

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)

# Force a fresh SessionLocal bound to our test engine, then reload all
# modules that captured the original SessionLocal at import time.
importlib.reload(session_module)
session_module.engine = engine
session_module.SessionLocal = session_module.sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)

# Reload every module that captures SessionLocal / get_db at import time.
import app.api.router  # noqa: E402
import app.api.routes.ai  # noqa: E402
import app.api.routes.assets  # noqa: E402
import app.api.routes.auth  # noqa: E402
import app.api.routes.dashboard  # noqa: E402
import app.api.routes.exports  # noqa: E402
import app.api.routes.jobs  # noqa: E402
import app.api.routes.models  # noqa: E402
import app.api.routes.operations  # noqa: E402
import app.api.routes.projects  # noqa: E402
import app.api.routes.providers  # noqa: E402
import app.api.routes.reports  # noqa: E402
import app.api.routes.settings  # noqa: E402
import app.api.routes.transcripts  # noqa: E402
import app.api.routes.users  # noqa: E402
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.services.exports  # noqa: E402
import app.services.jobs  # noqa: E402
import app.services.media  # noqa: E402
import app.worker.model_tasks  # noqa: E402
import app.worker.post_processing_tasks  # noqa: E402
import app.worker.tasks  # noqa: E402

for mod in (
    app.services.jobs,
    app.services.media,
    app.services.exports,
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.jobs,
    app.api.routes.assets,
    app.api.routes.exports,
    app.api.routes.auth,
    app.api.routes.dashboard,
    app.api.routes.providers,
    app.api.routes.reports,
    app.api.routes.ai,
    app.api.routes.transcripts,
    app.api.routes.models,
    app.api.routes.operations,
    app.api.routes.users,
    app.api.routes.settings,
    app.api.routes.projects,
    app.worker.tasks,
    app.worker.model_tasks,
    app.worker.post_processing_tasks,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.main import app  # noqa: E402
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    # Re-create tables for a clean test
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit
    from app.services.model_catalog import seed_model_catalog
    from app.services.report_templates import seed_report_templates

    rate_limit.limiter.reset()

    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())
        seed_report_templates(session)
        seed_model_catalog(session)
    return TestClient(app)


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "a-very-safe-bootstrap-password-1"},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.cookies.set("csrf_token", csrf)
    return csrf


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json()["status"] == "ready"


def test_login_returns_csrf_token(client: TestClient) -> None:
    _login(client)
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "admin@example.com"


def test_metrics_endpoint_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/metrics")
    assert response.status_code == 401


def test_metrics_endpoint_returns_expected_fields(client: TestClient) -> None:
    _login(client)
    metrics = client.get("/api/v1/dashboard/metrics").json()
    assert metrics["total_files"] == 0
    assert metrics["completed_transcriptions"] == 0
    assert metrics["jobs_in_progress"] == 0
    assert "most_used_models" in metrics
    assert "most_used_providers" in metrics
    assert "recent_errors" in metrics
    assert "api_cost_estimate" in metrics


def test_operations_queue_depth_counts_transcription_work(client: TestClient) -> None:
    from sqlalchemy import select

    from app.db import session as session_module
    from app.models.domain import AssetStatus, JobStatus, MediaAsset, Organisation, TranscriptionJob, User

    _login(client)
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="operations-depth.wav",
            content_type="audio/wav",
            byte_size=1024,
            sha256="c" * 64,
            storage_key=f"organisations/{org.id}/assets/operations-depth.wav",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.flush()
        db.add_all(
            [
                TranscriptionJob(
                    organisation_id=org.id,
                    asset_id=asset.id,
                    requested_by_id=user.id,
                    status=JobStatus.queued,
                ),
                TranscriptionJob(
                    organisation_id=org.id,
                    asset_id=asset.id,
                    requested_by_id=user.id,
                    status=JobStatus.transcribing,
                ),
                TranscriptionJob(
                    organisation_id=org.id,
                    asset_id=asset.id,
                    requested_by_id=user.id,
                    status=JobStatus.failed,
                ),
            ]
        )
        db.commit()

    response = client.get("/api/v1/operations/queue-depth")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["transcription"]["queued"] == 1
    assert payload["transcription"]["active"] == 1
    assert payload["transcription"]["failed"] == 1


def test_operations_worker_health_reports_database_and_workers(client: TestClient) -> None:
    _login(client)

    response = client.get("/api/v1/operations/worker-health")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["database"]["status"] == "ok"
    assert "queue_backend" in payload
    assert "workers" in payload


def test_operations_metrics_returns_alert_counters(client: TestClient) -> None:
    _login(client)

    response = client.get("/api/v1/operations/metrics")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert "transcription_jobs_queued" in payload["counters"]
    assert "transcription_jobs_failed" in payload["counters"]
    assert "http_requests_total" in payload["counters"]


def test_settings_endpoint_is_accessible(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/v1/settings")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_users_lists_admin(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/v1/users")
    assert response.status_code == 200
    emails = {user["email"] for user in response.json()}
    assert "admin@example.com" in emails


def test_audit_log_endpoint(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/v1/dashboard/audit-logs")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_provider_creation_and_test_redacts_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    response = client.post(
        "/api/v1/api-providers",
        headers={"X-CSRF-Token": csrf},
        json={
            "adapter_key": "openai_compatible",
            "name": "Test provider",
            "base_url": "https://localhost.test",
            "endpoint_path": "/audio/transcriptions",
            "model_name": "whisper-1",
            "auth_type": "bearer",
            "api_key": "sk-test-key-1234567890",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["secret_configured"] is True
    assert "sk-test" not in str(body)

    # Stub getaddrinfo so the SSRF check passes without DNS resolution.
    import socket

    def _fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    test_response = client.post(
        f"/api/v1/api-providers/{body['id']}/test",
        headers={"X-CSRF-Token": csrf},
    )
    assert test_response.status_code == 200
    payload = test_response.json()
    assert payload["last_error"] is None or "sk-test" not in payload["last_error"]


def test_get_provider_returns_redacted_contract(client: TestClient) -> None:
    csrf = _login(client)
    create_response = client.post(
        "/api/v1/api-providers",
        headers={"X-CSRF-Token": csrf},
        json={
            "adapter_key": "openai_compatible",
            "name": "Readable provider",
            "base_url": "https://localhost.test",
            "endpoint_path": "/audio/transcriptions",
            "model_name": "whisper-1",
            "auth_type": "bearer",
            "api_key": "sk-test-key-1234567890",
        },
    )
    assert create_response.status_code == 201, create_response.text
    provider_id = create_response.json()["id"]

    response = client.get(f"/api/v1/api-providers/{provider_id}")

    assert response.status_code == 200, response.text
    provider = response.json()
    assert provider["name"] == "Readable provider"
    assert provider["adapter_key"] == "openai_compatible"
    assert provider["endpoint_path"] == "/audio/transcriptions"
    assert provider["secret_configured"] is True
    assert "sk-test" not in str(provider)


def test_provider_usage_returns_aggregates(client: TestClient) -> None:
    from app.db import session as session_module
    from app.models.domain import ProviderUsageLog

    csrf = _login(client)
    create_response = client.post(
        "/api/v1/api-providers",
        headers={"X-CSRF-Token": csrf},
        json={
            "adapter_key": "openai_compatible",
            "name": "Usage provider",
            "base_url": "https://localhost.test",
            "endpoint_path": "/audio/transcriptions",
            "model_name": "whisper-1",
            "auth_type": "bearer",
            "api_key": "sk-test-key-1234567890",
        },
    )
    assert create_response.status_code == 201, create_response.text
    provider_id = create_response.json()["id"]
    provider_uuid = UUID(provider_id)

    with session_module.SessionLocal() as db:
        db.add_all(
            [
                ProviderUsageLog(
                    provider_id=provider_uuid,
                    task="transcription",
                    duration_ms=250,
                    estimated_cost="0.125",
                    status="success",
                ),
                ProviderUsageLog(
                    provider_id=provider_uuid,
                    task="transcription",
                    duration_ms=100,
                    estimated_cost="not-a-number",
                    status="failure",
                    error_code="timeout",
                ),
            ]
        )
        db.commit()

    usage_response = client.get(f"/api/v1/api-providers/{provider_id}/usage")

    assert usage_response.status_code == 200, usage_response.text
    usage = usage_response.json()
    assert usage["provider_id"] == provider_id
    assert usage["total_calls"] == 2
    assert usage["successful_calls"] == 1
    assert usage["failed_calls"] == 1
    assert usage["total_duration_ms"] == 350
    assert usage["estimated_cost_usd"] == 0.125
    assert len(usage["recent_calls"]) == 2


def test_job_event_history_endpoint_returns_json(client: TestClient) -> None:
    from sqlalchemy import select

    from app.db import session as session_module
    from app.models.domain import (
        AssetStatus,
        JobEvent,
        JobStatus,
        MediaAsset,
        Organisation,
        TranscriptionJob,
        User,
    )

    _login(client)
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="meeting-history.wav",
            content_type="audio/wav",
            byte_size=1024,
            sha256="b" * 64,
            storage_key=f"organisations/{org.id}/assets/meeting-history.wav",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.flush()
        job = TranscriptionJob(
            organisation_id=org.id,
            asset_id=asset.id,
            requested_by_id=user.id,
            status=JobStatus.queued,
        )
        db.add(job)
        db.flush()
        db.add(
            JobEvent(
                job_id=job.id,
                sequence=1,
                state=JobStatus.queued,
                progress_percent=0,
                message="Job queued for provider resolution",
                data={"source": "test"},
            )
        )
        db.commit()
        job_id = str(job.id)

    response = client.get(f"/api/v1/transcription-jobs/{job_id}/events/history")

    assert response.status_code == 200, response.text
    events = response.json()
    assert len(events) == 1
    assert events[0]["sequence"] == 1
    assert events[0]["state"] == "queued"
    assert events[0]["data"] == {"source": "test"}


def test_report_templates_listed(client: TestClient) -> None:
    _login(client)
    response = client.get("/api/v1/reports/templates")
    assert response.status_code == 200
    kinds = {template["kind"] for template in response.json()}
    expected = {
        "presentation",
        "meeting",
        "workshop",
        "benchmarking",
        "training",
        "legal_policy",
        "technical_demo",
        "project_implementation",
    }
    assert expected.issubset(kinds)


def test_login_rate_limit(client: TestClient) -> None:
    # 10 per minute is the default; send 12 to exceed it
    for _ in range(12):
        client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@example.com", "password": "wrong-wrong-wrong"},
        )
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@example.com", "password": "wrong-wrong-wrong"},
    )
    assert response.status_code == 429


def test_list_exports_endpoint_exists(client: TestClient) -> None:
    """The GET /exports endpoint should be reachable for any authenticated user."""
    _login(client)
    response = client.get("/api/v1/exports")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_list_exports_rejects_invalid_limit(client: TestClient) -> None:
    csrf = _login(client)
    response = client.get(
        "/api/v1/exports",
        headers={"X-CSRF-Token": csrf},
        params={"limit": 0},
    )
    assert response.status_code == 422


def test_transcription_job_rejects_disabled_selected_local_model(client: TestClient) -> None:
    from sqlalchemy import select

    from app.db import session as session_module
    from app.models.domain import (
        AssetStatus,
        InstalledModel,
        MediaAsset,
        ModelCatalog,
        ModelInstallStatus,
        Organisation,
        User,
    )

    csrf = _login(client)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert org is not None
        assert user is not None
        assert catalog is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="meeting.wav",
            content_type="audio/wav",
            byte_size=1024,
            sha256="a" * 64,
            storage_key=f"organisations/{org.id}/assets/meeting.wav",
            status=AssetStatus.ready,
        )
        model = db.scalar(
            select(InstalledModel).where(
                InstalledModel.organisation_id == org.id,
                InstalledModel.catalog_id == catalog.id,
            )
        )
        if model is None:
            model = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
            db.add(model)
        model.status = ModelInstallStatus.installed
        model.enabled = False
        db.add(asset)
        db.commit()
        asset_id = str(asset.id)
        model_id = str(model.id)

    response = client.post(
        "/api/v1/transcription-jobs",
        headers={"X-CSRF-Token": csrf},
        json={
            "asset_id": asset_id,
            "execution_target_kind": "local_model",
            "execution_target_id": model_id,
        },
    )

    assert response.status_code == 409, response.text
    assert "installed and enabled" in response.json()["detail"]


def test_settings_update_roundtrip(client: TestClient) -> None:
    csrf = _login(client)
    put = client.put(
        "/api/v1/settings",
        headers={"X-CSRF-Token": csrf},
        json={"key": "test_setting", "value": {"enabled": True, "limit": 10}},
    )
    assert put.status_code in (200, 201), put.text
    listed = client.get("/api/v1/settings").json()
    keys = {item["key"] for item in listed}
    assert "test_setting" in keys
    delete = client.delete(
        "/api/v1/settings/test_setting",
        headers={"X-CSRF-Token": csrf},
    )
    assert delete.status_code == 204


def test_unauthenticated_request_rejected(client: TestClient) -> None:
    """Critical endpoints must reject unauthenticated requests."""
    for path in (
        "/api/v1/assets",
        "/api/v1/transcripts",
        "/api/v1/transcription-jobs",
        "/api/v1/api-providers",
        "/api/v1/users",
        "/api/v1/reports",
        "/api/v1/exports",
        "/api/v1/dashboard/metrics",
        "/api/v1/dashboard/audit-logs",
        "/api/v1/settings",
        "/api/v1/model-catalog",
        "/api/v1/installed-models",
        "/api/v1/reports/templates",
        "/api/v1/projects",
        "/api/v1/users/roles",
        "/api/v1/users/memberships",
    ):
        response = client.get(path)
        assert response.status_code == 401, f"{path} should require auth, got {response.status_code}"
