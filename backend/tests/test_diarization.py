"""Diarisation option, persistence, and export tests."""

import base64
import importlib
import os
import secrets
import uuid
from types import SimpleNamespace

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
import app.api.routes.assets  # noqa: E402
import app.api.routes.auth  # noqa: E402
import app.api.routes.jobs  # noqa: E402
import app.api.routes.transcripts  # noqa: E402
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
    app.api.routes.transcripts,
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
    Speaker,
    TranscriptionJob,
    TranscriptSegment,
    User,
)
from app.providers.contracts import (  # noqa: E402
    DiarizationResult,
    DiarizationSegmentResult,
    TranscriptionResult,
    TranscriptSegmentResult,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.services.exports import render_export  # noqa: E402
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


def _seed_ready_asset(filename: str = "diarization.wav") -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename=filename,
            content_type="audio/wav",
            byte_size=1024,
            sha256="d" * 64,
            storage_key=f"organisations/{org.id}/assets/{filename}",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.commit()
        return asset.id


def _seed_job() -> TranscriptionJob:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="speaker-result.wav",
            content_type="audio/wav",
            byte_size=2048,
            sha256="f" * 64,
            storage_key=f"organisations/{org.id}/assets/speaker-result.wav",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.flush()
        job = TranscriptionJob(
            organisation_id=org.id,
            asset_id=asset.id,
            requested_by_id=user.id,
            status=JobStatus.transcribing,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job


def test_job_options_validate_diarization_payload(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    csrf = _login(client)
    monkeypatch.setattr(jobs_routes, "_enqueue_transcription", lambda job_id: None)
    asset_id = _seed_ready_asset("options.wav")

    bad_response = client.post(
        "/api/v1/transcription-jobs",
        headers={"X-CSRF-Token": csrf},
        json={
            "asset_id": str(asset_id),
            "options": {"diarization": {"enabled": True, "speaker_count": 0}},
        },
    )
    assert bad_response.status_code == 422, bad_response.text
    assert "speaker count" in bad_response.json()["detail"].lower()

    good_response = client.post(
        "/api/v1/transcription-jobs",
        headers={"X-CSRF-Token": csrf},
        json={
            "asset_id": str(asset_id),
            "options": {
                "diarization": {
                    "enabled": True,
                    "provider": "local_turns",
                    "speaker_count": 2,
                }
            },
        },
    )
    assert good_response.status_code == 202, good_response.text


def test_persist_transcript_creates_speakers_from_segment_labels(client: TestClient) -> None:
    csrf = _login(client)
    job = _seed_job()
    result = TranscriptionResult(
        detected_language="en",
        duration_ms=2500,
        text="Hello there. General Kenobi.",
        segments=[
            TranscriptSegmentResult(
                start_ms=0,
                end_ms=1200,
                text="Hello there.",
                confidence=0.94,
                speaker_label="S1",
            ),
            TranscriptSegmentResult(
                start_ms=1200,
                end_ms=2500,
                text="General Kenobi.",
                confidence=0.91,
                speaker_label="S2",
            ),
        ],
    )

    with session_module.SessionLocal() as db:
        transcript = tasks_module._persist_transcript(db, db.merge(job), "fake_provider", result)
        db.commit()
        transcript_id = transcript.id
        version_id = transcript.active_version_id

    with session_module.SessionLocal() as db:
        speakers = list(
            db.scalars(select(Speaker).where(Speaker.transcript_id == transcript_id).order_by(Speaker.label))
        )
        segments = list(
            db.scalars(
                select(TranscriptSegment)
                .where(TranscriptSegment.version_id == version_id)
                .order_by(TranscriptSegment.sequence)
            )
        )
    assert [speaker.label for speaker in speakers] == ["S1", "S2"]
    assert [segment.speaker_id for segment in segments] == [speakers[0].id, speakers[1].id]

    detail = client.get(f"/api/v1/transcripts/{transcript_id}", headers={"X-CSRF-Token": csrf})
    assert detail.status_code == 200, detail.text
    assert [segment["speaker_label"] for segment in detail.json()["segments"]] == ["S1", "S2"]


def test_diarization_result_assigns_labels_by_largest_time_overlap() -> None:
    result = TranscriptionResult(
        detected_language="en",
        duration_ms=62_000,
        text="first second",
        segments=[
            TranscriptSegmentResult(start_ms=60_000, end_ms=61_000, text="first"),
            TranscriptSegmentResult(start_ms=61_000, end_ms=62_000, text="second"),
        ],
    )
    diarization = DiarizationResult(
        segments=[
            DiarizationSegmentResult(start_ms=0, end_ms=60_200, speaker_label="S1"),
            DiarizationSegmentResult(start_ms=60_200, end_ms=61_400, speaker_label="S2"),
            DiarizationSegmentResult(start_ms=61_400, end_ms=62_000, speaker_label="S1"),
        ]
    )

    updated = tasks_module._apply_diarization_to_result(result, diarization)

    assert [segment.speaker_label for segment in updated.segments] == ["S2", "S1"]


def test_exports_can_include_speaker_labels() -> None:
    speaker_id = uuid.uuid4()
    segment = SimpleNamespace(
        sequence=1,
        start_ms=0,
        end_ms=1500,
        speaker_id=speaker_id,
        text="Speaker-aware export.",
        confidence=None,
        is_unclear=False,
    )

    txt, _, _ = render_export(
        "txt",
        [segment],
        {"include_timestamps": False, "include_speakers": True},
        {speaker_id: "Presenter"},
    )
    json_export, _, _ = render_export(
        "json",
        [segment],
        {"include_speakers": True},
        {speaker_id: "Presenter"},
    )

    assert txt.decode("utf-8") == "Presenter: Speaker-aware export.\n"
    assert '"speaker_label": "Presenter"' in json_export.decode("utf-8")
