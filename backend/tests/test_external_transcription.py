"""External API transcription route and worker integration tests."""

import base64
import importlib
import os
import secrets
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

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

importlib.reload(session_module)
session_module.engine = engine
session_module.SessionLocal = session_module.sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)

import app.api.router  # noqa: E402
import app.api.routes.ai  # noqa: E402
import app.api.routes.assets  # noqa: E402
import app.api.routes.auth  # noqa: E402
import app.api.routes.dashboard  # noqa: E402
import app.api.routes.exports  # noqa: E402
import app.api.routes.jobs  # noqa: E402
import app.api.routes.models  # noqa: E402
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
import app.services.jobs  # noqa: E402
import app.worker.tasks  # noqa: E402

for mod in (
    app.services.jobs,
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.jobs,
    app.api.routes.providers,
    app.api.router,
    app.main,
    app.worker.tasks,
):
    importlib.reload(mod)

from app.api.routes import jobs as jobs_routes  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    JobStatus,
    MediaAsset,
    Organisation,
    Project,
    ProviderDefinition,
    ProviderSecret,
    ProviderUsageLog,
    Transcript,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptVersion,
    User,
)
from app.providers.contracts import TranscriptionResult, TranscriptSegmentResult  # noqa: E402
from app.providers.external import ExternalProviderError  # noqa: E402
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.services.provider_secrets import encrypt_secret  # noqa: E402
from app.worker import tasks as tasks_module  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    tasks_module.SessionLocal = session_module.SessionLocal

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


def _seed_ready_asset(filename: str = "external.wav", project_id: uuid.UUID | None = None) -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            project_id=project_id,
            uploaded_by_id=user.id,
            original_filename=filename,
            content_type="audio/wav",
            byte_size=1024,
            sha256="c" * 64,
            storage_key=f"organisations/{org.id}/assets/{filename}",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.commit()
        return asset.id


def _seed_project(external_apis_allowed: bool | None) -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        assert org is not None
        project = Project(
            organisation_id=org.id,
            name=f"Project {uuid.uuid4()}",
            external_apis_allowed=external_apis_allowed,
        )
        db.add(project)
        db.commit()
        return project.id


def _seed_provider(
    *,
    enabled: bool = True,
    category: str = "transcription",
    model_name: str | None = "whisper-1",
    capabilities: dict | None = None,
    secret: str | None = "sk-test-external",
    auth_type: str = "bearer",
) -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        assert org is not None
        provider = ProviderDefinition(
            organisation_id=org.id,
            adapter_key="openai_compatible",
            name="External Whisper",
            category=category,
            base_url="https://api.example.test",
            endpoint_path="/audio/transcriptions",
            model_name=model_name,
            auth_type=auth_type,
            capabilities=capabilities if capabilities is not None else {"tasks": ["transcription"]},
            enabled=enabled,
        )
        db.add(provider)
        db.flush()
        if secret is not None:
            ciphertext, nonce = encrypt_secret(get_settings(), secret)
            db.add(
                ProviderSecret(
                    provider_id=provider.id,
                    ciphertext=ciphertext,
                    nonce=nonce,
                    key_version=get_settings().credential_key_version,
                )
            )
        db.commit()
        return provider.id


def _post_api_provider_job(
    client: TestClient,
    csrf: str,
    asset_id: uuid.UUID,
    provider_id: uuid.UUID | None,
    *,
    egress_acknowledged: bool | None = True,
):
    payload: dict[str, object] = {
        "asset_id": str(asset_id),
        "execution_target_kind": "api_provider",
        "execution_target_id": str(provider_id) if provider_id else None,
    }
    if egress_acknowledged is not None:
        payload["egress_acknowledged"] = egress_acknowledged
    return client.post(
        "/api/v1/transcription-jobs",
        headers={"X-CSRF-Token": csrf},
        json=payload,
    )


def test_api_provider_job_requires_explicit_egress_acknowledgement(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    monkeypatch.setattr(jobs_routes, "_enqueue_transcription", lambda job_id: None)
    asset_id = _seed_ready_asset("acknowledgement.wav")
    provider_id = _seed_provider()

    response = _post_api_provider_job(client, csrf, asset_id, provider_id, egress_acknowledged=None)

    assert response.status_code == 422, response.text
    assert "egress acknowledgement" in response.json()["detail"].lower()


def test_api_provider_job_validates_provider_readiness(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    monkeypatch.setattr(jobs_routes, "_enqueue_transcription", lambda job_id: None)
    asset_id = _seed_ready_asset("provider-validation.wav")

    disabled_provider = _seed_provider(enabled=False)
    disabled_response = _post_api_provider_job(client, csrf, asset_id, disabled_provider)
    assert disabled_response.status_code == 409
    assert "enabled" in disabled_response.json()["detail"].lower()

    wrong_category_provider = _seed_provider(category="post_processing")
    wrong_category_response = _post_api_provider_job(client, csrf, asset_id, wrong_category_provider)
    assert wrong_category_response.status_code == 409
    assert "transcription" in wrong_category_response.json()["detail"].lower()

    missing_model_provider = _seed_provider(model_name=None)
    missing_model_response = _post_api_provider_job(client, csrf, asset_id, missing_model_provider)
    assert missing_model_response.status_code == 409
    assert "model" in missing_model_response.json()["detail"].lower()

    unsupported_provider = _seed_provider(capabilities={"tasks": ["summary"]})
    unsupported_response = _post_api_provider_job(client, csrf, asset_id, unsupported_provider)
    assert unsupported_response.status_code == 409
    assert "transcription" in unsupported_response.json()["detail"].lower()

    missing_secret_provider = _seed_provider(secret=None)
    missing_secret_response = _post_api_provider_job(client, csrf, asset_id, missing_secret_provider)
    assert missing_secret_response.status_code == 409
    assert "credential" in missing_secret_response.json()["detail"].lower()


def test_api_provider_job_enforces_project_external_policy(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    monkeypatch.setattr(jobs_routes, "_enqueue_transcription", lambda job_id: None)
    project_id = _seed_project(external_apis_allowed=False)
    asset_id = _seed_ready_asset("project-policy.wav", project_id)
    provider_id = _seed_provider()

    response = _post_api_provider_job(client, csrf, asset_id, provider_id)

    assert response.status_code == 409, response.text
    assert "external api processing is disabled" in response.json()["detail"].lower()


def test_external_provider_worker_completes_transcript_and_usage_log(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csrf = _login(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(tasks_module, "_prepare_audio", lambda _ffmpeg, source, _tmp: source)
    asset_id = _seed_ready_asset("worker-success.wav")
    provider_id = _seed_provider(secret="sk-worker-success")
    storage_path = tmp_path / f"organisations/{_organisation_id()}/assets/worker-success.wav"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(b"RIFF0000WAVE")

    captured: dict[str, object] = {}

    def fake_transcribe(provider, api_key, request):
        captured["provider_id"] = provider.id
        captured["api_key"] = api_key
        captured["media_exists"] = request.media_path.exists()
        return TranscriptionResult(
            detected_language="en",
            duration_ms=1200,
            text="hello world",
            segments=[TranscriptSegmentResult(start_ms=0, end_ms=1200, text="hello world", confidence=0.92)],
            metrics={"estimated_cost": "0.015"},
        )

    with patch.object(jobs_routes, "_enqueue_transcription", lambda job_id: None):
        create_response = _post_api_provider_job(client, csrf, asset_id, provider_id)
    assert create_response.status_code == 202, create_response.text
    job_id = create_response.json()["id"]

    monkeypatch.setattr(tasks_module, "external_transcribe", fake_transcribe)
    result = tasks_module.run_transcription_job.run(job_id)

    assert result["status"] == "completed"
    assert captured == {
        "provider_id": provider_id,
        "api_key": "sk-worker-success",
        "media_exists": True,
    }
    with session_module.SessionLocal() as db:
        job = db.get(TranscriptionJob, uuid.UUID(job_id))
        assert job is not None
        assert job.status == JobStatus.completed
        transcript = db.scalar(select(Transcript).where(Transcript.job_id == job.id))
        assert transcript is not None
        assert transcript.source_provider == "openai_compatible"
        version = db.get(TranscriptVersion, transcript.active_version_id)
        assert version is not None
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.version_id == version.id)
                .order_by(TranscriptSegment.sequence)
            )
        )
        assert [segment.text for segment in segments] == ["hello world"]
        usage = db.scalar(select(ProviderUsageLog).where(ProviderUsageLog.job_id == job.id))
        assert usage is not None
        assert usage.provider_id == provider_id
        assert usage.task == "transcription"
        assert usage.status == "success"
        assert usage.duration_ms is not None
        assert usage.estimated_cost == "0.015"


def test_external_provider_worker_logs_redacted_failure(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csrf = _login(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(tasks_module, "_prepare_audio", lambda _ffmpeg, source, _tmp: source)
    asset_id = _seed_ready_asset("worker-failure.wav")
    provider_id = _seed_provider(secret="sk-worker-failure")
    storage_path = tmp_path / f"organisations/{_organisation_id()}/assets/worker-failure.wav"
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(b"RIFF0000WAVE")

    def failing_transcribe(_provider, _api_key, _request):
        raise ExternalProviderError("upstream rejected sk-worker-failure")

    with patch.object(jobs_routes, "_enqueue_transcription", lambda job_id: None):
        create_response = _post_api_provider_job(client, csrf, asset_id, provider_id)
    assert create_response.status_code == 202, create_response.text
    job_id = create_response.json()["id"]

    monkeypatch.setattr(tasks_module, "external_transcribe", failing_transcribe)
    result = tasks_module.run_transcription_job.run(job_id)

    assert result == {
        "status": "failed",
        "job_id": job_id,
        "code": "external_provider_failed",
    }
    with session_module.SessionLocal() as db:
        job = db.get(TranscriptionJob, uuid.UUID(job_id))
        provider = db.get(ProviderDefinition, provider_id)
        assert job is not None
        assert provider is not None
        assert job.status == JobStatus.failed
        assert job.error_code == "external_provider_failed"
        assert "sk-worker-failure" not in (job.error_message or "")
        assert "sk-worker-failure" not in (provider.last_error or "")
        usage = db.scalar(select(ProviderUsageLog).where(ProviderUsageLog.job_id == job.id))
        assert usage is not None
        assert usage.status == "failure"
        assert usage.error_code == "external_provider_failed"


def _organisation_id() -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        assert org is not None
        return org.id
