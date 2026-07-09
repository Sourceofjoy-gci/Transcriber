"""Report template lifecycle and schema-driven report tests."""

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
import app.api.routes.auth  # noqa: E402
import app.api.routes.reports  # noqa: E402
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.worker.post_processing_tasks  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.auth,
    app.api.routes.reports,
    app.worker.post_processing_tasks,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.api.routes import reports as reports_routes  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    JobStatus,
    MediaAsset,
    Organisation,
    Report,
    Transcript,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptVersion,
    User,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.services.report_templates import seed_report_templates  # noqa: E402
from app.worker import post_processing_tasks as post_tasks  # noqa: E402


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    post_tasks.SessionLocal = session_module.SessionLocal
    monkeypatch.setattr(reports_routes, "_enqueue_report", lambda report_id: None)

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit

    rate_limit.limiter.reset()
    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())
        seed_report_templates(session)
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


def _seed_transcript(segment_texts: list[str]) -> tuple[uuid.UUID, uuid.UUID]:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="report-source.wav",
            content_type="audio/wav",
            byte_size=2048,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            storage_key=f"organisations/{org.id}/assets/report-source.wav",
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
            source_provider="test",
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
        for index, text in enumerate(segment_texts, start=1):
            db.add(
                TranscriptSegment(
                    version_id=version.id,
                    sequence=index,
                    start_ms=(index - 1) * 1000,
                    end_ms=index * 1000,
                    text=text,
                )
            )
        transcript.active_version_id = version.id
        db.commit()
        return transcript.id, version.id


def test_report_template_lifecycle_and_preview(client: TestClient) -> None:
    csrf = _login(client)
    transcript_id, _ = _seed_transcript(["Opening overview.", "Risk register and next steps."])

    created = client.post(
        "/api/v1/reports/templates",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Client brief",
            "kind": "client_brief",
            "schema": {"sections": ["Overview", "Risks"]},
            "prompt_template": "Create a client brief.",
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    assert created.json()["enabled"] is True
    assert created.json()["is_builtin"] is False

    patched = client.patch(
        f"/api/v1/reports/templates/{template_id}",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Client brief v2",
            "schema": {"sections": ["Overview", "Risks", "Next steps"]},
            "enabled": False,
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Client brief v2"
    assert patched.json()["enabled"] is False
    assert patched.json()["schema"]["sections"] == ["Overview", "Risks", "Next steps"]

    enabled = client.post(
        f"/api/v1/reports/templates/{template_id}/enable",
        headers={"X-CSRF-Token": csrf},
    )
    assert enabled.status_code == 200, enabled.text
    assert enabled.json()["enabled"] is True

    preview = client.post(
        f"/api/v1/reports/templates/{template_id}/preview",
        headers={"X-CSRF-Token": csrf},
        json={"transcript_id": str(transcript_id), "title": "Preview brief"},
    )
    assert preview.status_code == 200, preview.text
    assert [section["heading"] for section in preview.json()["content"]["sections"]] == [
        "Overview",
        "Risks",
        "Next steps",
    ]

    disabled = client.post(
        f"/api/v1/reports/templates/{template_id}/disable",
        headers={"X-CSRF-Token": csrf},
    )
    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["enabled"] is False

    deleted = client.delete(
        f"/api/v1/reports/templates/{template_id}",
        headers={"X-CSRF-Token": csrf},
    )
    assert deleted.status_code == 204, deleted.text

    listed = client.get("/api/v1/reports/templates")
    assert template_id not in {row["id"] for row in listed.json()}


def test_report_worker_uses_template_schema_and_report_patch(client: TestClient) -> None:
    csrf = _login(client)
    transcript_id, _ = _seed_transcript(["Product summary.", "Implementation risks."])

    template = client.post(
        "/api/v1/reports/templates",
        headers={"X-CSRF-Token": csrf},
        json={
            "name": "Risk brief",
            "kind": "risk_brief",
            "schema": {"sections": ["Executive summary", "Risks"]},
        },
    )
    assert template.status_code == 201, template.text

    queued = client.post(
        "/api/v1/reports",
        headers={"X-CSRF-Token": csrf},
        json={
            "transcript_id": str(transcript_id),
            "template_id": template.json()["id"],
            "title": "Risk review",
        },
    )
    assert queued.status_code == 202, queued.text
    report_id = queued.json()["id"]

    result = post_tasks.generate_report.run(report_id)
    assert result["status"] == "completed"

    generated = client.get(f"/api/v1/reports/{report_id}")
    assert generated.status_code == 200, generated.text
    assert generated.json()["status"] == "completed"
    assert [section["heading"] for section in generated.json()["content"]["sections"]] == [
        "Executive summary",
        "Risks",
    ]

    patched = client.patch(
        f"/api/v1/reports/{report_id}",
        headers={"X-CSRF-Token": csrf},
        json={
            "title": "Edited risk review",
            "content": {
                "summary": "Manual summary",
                "sections": [{"heading": "Executive summary", "body": "Manual summary"}],
            },
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "Edited risk review"
    assert patched.json()["content"]["summary"] == "Manual summary"

    with session_module.SessionLocal() as db:
        report = db.get(Report, uuid.UUID(report_id))
        assert report is not None
        assert report.content["summary"] == "Manual summary"
