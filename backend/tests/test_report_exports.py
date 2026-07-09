"""Report and selected-segment export tests."""

import base64
import importlib
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path

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
import app.api.routes.exports  # noqa: E402
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.worker.tasks  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.auth,
    app.api.routes.exports,
    app.worker.tasks,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.api.routes import exports as exports_routes  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    AuditLog,
    ExportRecord,
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
from app.worker import tasks as tasks_module  # noqa: E402


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    tasks_module.SessionLocal = session_module.SessionLocal

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit

    settings = get_settings()
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    monkeypatch.setattr(exports_routes, "_enqueue_export", lambda export_id: None)
    rate_limit.limiter.reset()
    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, settings)
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


def _seed_transcript(segment_texts: list[str]) -> dict[str, object]:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="export-source.wav",
            content_type="audio/wav",
            byte_size=2048,
            sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            storage_key=f"organisations/{org.id}/assets/export-source.wav",
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
        segments = []
        for index, text in enumerate(segment_texts, start=1):
            segment = TranscriptSegment(
                version_id=version.id,
                sequence=index,
                start_ms=(index - 1) * 1000,
                end_ms=index * 1000,
                text=text,
            )
            db.add(segment)
            db.flush()
            segments.append(segment.id)
        transcript.active_version_id = version.id
        db.commit()
        return {
            "organisation_id": org.id,
            "transcript_id": transcript.id,
            "version_id": version.id,
            "segment_ids": segments,
        }


def _seed_completed_report(version_id: uuid.UUID, organisation_id: uuid.UUID) -> uuid.UUID:
    with session_module.SessionLocal() as db:
        report = Report(
            organisation_id=organisation_id,
            transcript_version_id=version_id,
            title="Board report",
            status="completed",
            content={
                "title": "Board report",
                "summary": "Board summary",
                "sections": [{"heading": "Findings", "body": "Report body"}],
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )
        db.add(report)
        db.commit()
        return report.id


def test_export_can_target_selected_transcript_segments(client: TestClient) -> None:
    csrf = _login(client)
    seeded = _seed_transcript(["Keep out.", "Export me.", "Also keep out."])

    response = client.post(
        "/api/v1/exports",
        headers={"X-CSRF-Token": csrf},
        json={
            "source_type": "transcript",
            "transcript_id": str(seeded["transcript_id"]),
            "format": "txt",
            "segment_ids": [str(seeded["segment_ids"][1])],
            "options": {"include_timestamps": False},
        },
    )
    assert response.status_code == 202, response.text
    export_id = response.json()["id"]

    result = tasks_module.generate_export.run(export_id)
    assert result["status"] == "completed"

    download = client.get(f"/api/v1/exports/{export_id}/download")
    assert download.status_code == 200, download.text
    assert download.text == "Export me.\n"

    with session_module.SessionLocal() as db:
        export = db.get(ExportRecord, uuid.UUID(export_id))
        assert export is not None
        assert export.options["source_type"] == "transcript"
        assert export.options["segment_ids"] == [str(seeded["segment_ids"][1])]


def test_export_can_target_completed_reports_and_downloads_are_audited(client: TestClient) -> None:
    csrf = _login(client)
    seeded = _seed_transcript(["Report source transcript."])
    report_id = _seed_completed_report(seeded["version_id"], seeded["organisation_id"])

    response = client.post(
        "/api/v1/exports",
        headers={"X-CSRF-Token": csrf},
        json={
            "source_type": "report",
            "report_id": str(report_id),
            "format": "md",
            "options": {},
        },
    )
    assert response.status_code == 202, response.text
    export_id = response.json()["id"]

    result = tasks_module.generate_export.run(export_id)
    assert result["status"] == "completed"

    download = client.get(f"/api/v1/exports/{export_id}/download")
    assert download.status_code == 200, download.text
    assert "# Board report" in download.text
    assert "Board summary" in download.text
    assert "Report body" in download.text

    with session_module.SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.action == "export.downloaded",
                AuditLog.resource_id == uuid.UUID(export_id),
            )
        )
        assert audit is not None
        assert audit.data["source_type"] == "report"
