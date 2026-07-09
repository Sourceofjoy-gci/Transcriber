"""AI run API and worker integration tests."""

import base64
import importlib
import os
import secrets
import uuid

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
import app.api.routes.auth  # noqa: E402
import app.api.routes.providers  # noqa: E402
import app.api.routes.transcripts  # noqa: E402
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.worker.post_processing_tasks  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.ai,
    app.api.routes.auth,
    app.api.routes.providers,
    app.api.routes.transcripts,
    app.api.router,
    app.main,
    app.worker.post_processing_tasks,
):
    importlib.reload(mod)

from app.api.routes import ai as ai_routes  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AIProcessingRun,
    AssetStatus,
    JobStatus,
    MediaAsset,
    Organisation,
    ProviderDefinition,
    ProviderSecret,
    Transcript,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptVersion,
    User,
)
from app.providers.contracts import PostProcessRequest, PostProcessResult  # noqa: E402
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.services.provider_secrets import encrypt_secret  # noqa: E402
from app.worker import post_processing_tasks as ai_tasks_module  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    ai_tasks_module.SessionLocal = session_module.SessionLocal

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit

    rate_limit.limiter.reset()
    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())
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


def _seed_transcript(text: str = "Um hello team. Need to ship the report.") -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="ai.wav",
            content_type="audio/wav",
            byte_size=1024,
            sha256="d" * 64,
            storage_key=f"organisations/{org.id}/assets/ai.wav",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.flush()
        job = TranscriptionJob(
            organisation_id=org.id,
            asset_id=asset.id,
            requested_by_id=user.id,
            status=JobStatus.completed,
        )
        db.add(job)
        db.flush()
        transcript = Transcript(
            job_id=job.id,
            organisation_id=org.id,
            language="en",
            detected_language="en",
            source_provider="faster_whisper",
            status=TranscriptStatus.completed,
        )
        db.add(transcript)
        db.flush()
        version = TranscriptVersion(
            transcript_id=transcript.id,
            version_number=1,
            source="transcription_provider",
            change_summary="Initial transcription",
        )
        db.add(version)
        db.flush()
        db.add(
            TranscriptSegment(
                version_id=version.id,
                sequence=1,
                start_ms=0,
                end_ms=1500,
                text=text,
            )
        )
        transcript.active_version_id = version.id
        db.commit()
        return transcript.id


def _seed_provider(
    *,
    enabled: bool = True,
    capabilities: dict | None = None,
    secret: str | None = "sk-ai",
) -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        assert org is not None
        provider = ProviderDefinition(
            organisation_id=org.id,
            adapter_key="openai_compatible",
            name="AI Provider",
            category="post_processing",
            base_url="https://api.example.test",
            endpoint_path="/v1/chat/completions",
            model_name="gpt-test",
            auth_type="bearer",
            capabilities=capabilities if capabilities is not None else {"tasks": ["summary", "clean"]},
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


def test_ai_runs_can_be_listed_cancelled_and_retried(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    transcript_id = _seed_transcript()
    enqueued: list[uuid.UUID] = []
    monkeypatch.setattr(ai_routes, "_enqueue", lambda run_id: enqueued.append(run_id))

    create_response = client.post(
        "/api/v1/ai-runs",
        headers={"X-CSRF-Token": csrf},
        json={"transcript_id": str(transcript_id), "task": "summary"},
    )

    assert create_response.status_code == 202, create_response.text
    run_id = create_response.json()["id"]
    assert create_response.json()["progress_percent"] == 0
    assert enqueued == [uuid.UUID(run_id)]

    list_response = client.get("/api/v1/ai-runs")
    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()] == [run_id]

    cancel_response = client.post(f"/api/v1/ai-runs/{run_id}/cancel", headers={"X-CSRF-Token": csrf})
    assert cancel_response.status_code == 200, cancel_response.text
    assert cancel_response.json()["status"] == "cancelled"

    with session_module.SessionLocal() as db:
        run = db.get(AIProcessingRun, uuid.UUID(run_id))
        assert run is not None
        run.status = "failed"
        run.error_message = "temporary"
        db.commit()

    retry_response = client.post(f"/api/v1/ai-runs/{run_id}/retry", headers={"X-CSRF-Token": csrf})
    assert retry_response.status_code == 202, retry_response.text
    assert retry_response.json()["status"] == "queued"
    assert retry_response.json()["error_message"] is None


def test_api_provider_ai_run_requires_policy_and_egress_acknowledgement(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    transcript_id = _seed_transcript()
    provider_id = _seed_provider()
    monkeypatch.setattr(ai_routes, "_enqueue", lambda run_id: None)

    missing_ack = client.post(
        "/api/v1/ai-runs",
        headers={"X-CSRF-Token": csrf},
        json={
            "transcript_id": str(transcript_id),
            "task": "summary",
            "execution_target_kind": "api_provider",
            "execution_target_id": str(provider_id),
        },
    )
    assert missing_ack.status_code == 422, missing_ack.text
    assert "egress acknowledgement" in missing_ack.json()["detail"].lower()

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        assert org is not None
        org.local_only_enforced = True
        db.commit()

    blocked = client.post(
        "/api/v1/ai-runs",
        headers={"X-CSRF-Token": csrf},
        json={
            "transcript_id": str(transcript_id),
            "task": "summary",
            "execution_target_kind": "api_provider",
            "execution_target_id": str(provider_id),
            "egress_acknowledged": True,
        },
    )
    assert blocked.status_code == 409, blocked.text
    assert "external ai processing is disabled" in blocked.json()["detail"].lower()


def test_ai_worker_routes_selected_api_provider_and_creates_clean_version(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    transcript_id = _seed_transcript()
    provider_id = _seed_provider(secret="sk-ai-worker")
    monkeypatch.setattr(ai_routes, "_enqueue", lambda run_id: None)

    create_response = client.post(
        "/api/v1/ai-runs",
        headers={"X-CSRF-Token": csrf},
        json={
            "transcript_id": str(transcript_id),
            "task": "clean",
            "execution_target_kind": "api_provider",
            "execution_target_id": str(provider_id),
            "egress_acknowledged": True,
        },
    )
    assert create_response.status_code == 202, create_response.text
    run_id = create_response.json()["id"]
    captured: dict[str, object] = {}

    def fake_process(self, request: PostProcessRequest, report_progress):
        captured["provider_id"] = self.provider.id
        captured["api_key"] = self.api_key
        captured["task"] = request.task
        report_progress(40, "Calling provider", {"provider_id": str(self.provider.id)})
        return PostProcessResult(result={"cleaned_text": "Hello team. Need to ship the report."})

    monkeypatch.setattr(ai_tasks_module.OpenAICompatiblePostProcessingProvider, "process", fake_process)

    result = ai_tasks_module.run_ai_processing.run(run_id)

    assert result["status"] == "completed"
    assert captured == {
        "provider_id": provider_id,
        "api_key": "sk-ai-worker",
        "task": "clean",
    }
    with session_module.SessionLocal() as db:
        run = db.get(AIProcessingRun, uuid.UUID(run_id))
        transcript = db.get(Transcript, transcript_id)
        assert run is not None
        assert transcript is not None
        assert run.status == "completed"
        assert run.progress_percent == 100
        assert run.progress_message == "Completed"
        assert run.result is not None
        assert run.result["transcript_version_id"] == str(transcript.active_version_id)
        version = db.get(TranscriptVersion, transcript.active_version_id)
        assert version is not None
        assert version.source == "ai_processing"
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.version_id == version.id)
                .order_by(TranscriptSegment.sequence)
            )
        )
        assert [segment.text for segment in segments] == ["Hello team. Need to ship the report."]
