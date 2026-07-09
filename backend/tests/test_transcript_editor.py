"""Transcript editor API integration tests."""

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
import app.api.routes.transcripts  # noqa: E402
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.auth,
    app.api.routes.transcripts,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    JobStatus,
    MediaAsset,
    Organisation,
    Transcript,
    TranscriptAnnotation,
    TranscriptEditOperation,
    TranscriptionJob,
    TranscriptSegment,
    TranscriptStatus,
    TranscriptVersion,
    TranscriptWord,
    User,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

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


def _seed_transcript() -> dict[str, uuid.UUID]:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="editor.wav",
            content_type="audio/wav",
            byte_size=2048,
            sha256="e" * 64,
            storage_key=f"organisations/{org.id}/assets/editor.wav",
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
        first = TranscriptSegment(
            version_id=version.id,
            sequence=1,
            start_ms=0,
            end_ms=1000,
            text="Alpha segment.",
        )
        second = TranscriptSegment(
            version_id=version.id,
            sequence=2,
            start_ms=1000,
            end_ms=2500,
            text="Beta action item.",
        )
        db.add_all([first, second])
        db.flush()
        db.add(
            TranscriptWord(
                segment_id=first.id,
                sequence=1,
                start_ms=0,
                end_ms=400,
                word="Alpha",
            )
        )
        transcript.active_version_id = version.id
        db.commit()
        return {
            "transcript_id": transcript.id,
            "version_id": version.id,
            "first_segment_id": first.id,
            "second_segment_id": second.id,
        }


def test_segment_edit_requires_current_version_and_records_operation(client: TestClient) -> None:
    csrf = _login(client)
    ids = _seed_transcript()

    stale = client.patch(
        f"/api/v1/transcripts/{ids['transcript_id']}/segments/{ids['first_segment_id']}",
        headers={"X-CSRF-Token": csrf},
        json={
            "base_version_id": str(uuid.uuid4()),
            "text": "Should conflict.",
            "change_summary": "stale update",
        },
    )
    assert stale.status_code == 409, stale.text
    assert "version" in stale.json()["detail"].lower()

    updated = client.patch(
        f"/api/v1/transcripts/{ids['transcript_id']}/segments/{ids['first_segment_id']}",
        headers={"X-CSRF-Token": csrf},
        json={
            "base_version_id": str(ids["version_id"]),
            "text": "Alpha corrected.",
            "change_summary": "Correct first segment",
        },
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["active_version"]["version_number"] == 2
    assert body["segments"][0]["text"] == "Alpha corrected."
    assert body["segments"][0]["speaker_id"] is None
    assert body["segments"][0]["word_count"] == 1

    with session_module.SessionLocal() as db:
        operation = db.scalar(select(TranscriptEditOperation))
        assert operation is not None
        assert operation.operation_type == "segment_edit"
        assert operation.from_version_id == ids["version_id"]
        assert operation.to_version_id == uuid.UUID(body["active_version"]["id"])
        assert operation.payload["segment_id"] == str(ids["first_segment_id"])


def test_batch_edit_speaker_annotation_and_search_replace_are_versioned(client: TestClient) -> None:
    csrf = _login(client)
    ids = _seed_transcript()

    batch = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/segments:batch-edit",
        headers={"X-CSRF-Token": csrf},
        json={
            "base_version_id": str(ids["version_id"]),
            "edits": [
                {"segment_id": str(ids["first_segment_id"]), "text": "Alpha batch edit."},
                {"segment_id": str(ids["second_segment_id"]), "is_unclear": True},
            ],
            "change_summary": "Autosave batch",
        },
    )
    assert batch.status_code == 200, batch.text
    version_id = batch.json()["active_version"]["id"]
    assert batch.json()["segments"][0]["text"] == "Alpha batch edit."
    assert batch.json()["segments"][1]["is_unclear"] is True

    speaker_response = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/speakers",
        headers={"X-CSRF-Token": csrf},
        json={"label": "S1", "display_name": "Presenter", "color": "#0f766e"},
    )
    assert speaker_response.status_code == 200, speaker_response.text
    speaker_id = speaker_response.json()["id"]

    assign = client.patch(
        f"/api/v1/transcripts/{ids['transcript_id']}/segments/{batch.json()['segments'][0]['id']}/speaker",
        headers={"X-CSRF-Token": csrf},
        json={"base_version_id": version_id, "speaker_id": speaker_id},
    )
    assert assign.status_code == 200, assign.text
    assert assign.json()["segments"][0]["speaker_id"] == speaker_id
    version_id = assign.json()["active_version"]["id"]

    annotate = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/annotations",
        headers={"X-CSRF-Token": csrf},
        json={
            "base_version_id": version_id,
            "segment_id": assign.json()["segments"][1]["id"],
            "note": "Verify this action item.",
            "is_unclear": True,
        },
    )
    assert annotate.status_code == 200, annotate.text
    assert "Verify this action item." in annotate.json()["segments"][1]["notes"]
    version_id = annotate.json()["active_version"]["id"]

    replace = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/search:replace",
        headers={"X-CSRF-Token": csrf},
        json={
            "base_version_id": version_id,
            "query": "Beta",
            "replacement": "Gamma",
            "replace_all": True,
        },
    )
    assert replace.status_code == 200, replace.text
    assert replace.json()["replacement_count"] == 1
    assert replace.json()["transcript"]["segments"][1]["text"] == "Gamma action item."

    with session_module.SessionLocal() as db:
        annotations = list(db.scalars(select(TranscriptAnnotation)))
        operations = list(
            db.scalars(
                select(TranscriptEditOperation).where(
                    TranscriptEditOperation.transcript_id == ids["transcript_id"]
                )
            )
        )
        assert len(annotations) == 1
        assert annotations[0].note == "Verify this action item."
        assert [operation.operation_type for operation in operations] == [
            "batch_edit",
            "speaker_assign",
            "annotation",
            "search_replace",
        ]


def test_undo_and_redo_restore_operation_versions(client: TestClient) -> None:
    csrf = _login(client)
    ids = _seed_transcript()

    updated = client.patch(
        f"/api/v1/transcripts/{ids['transcript_id']}/segments/{ids['first_segment_id']}",
        headers={"X-CSRF-Token": csrf},
        json={"base_version_id": str(ids["version_id"]), "text": "Undo target."},
    )
    assert updated.status_code == 200, updated.text

    undo = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/operations:undo",
        headers={"X-CSRF-Token": csrf},
        json={"base_version_id": updated.json()["active_version"]["id"]},
    )
    assert undo.status_code == 200, undo.text
    assert undo.json()["segments"][0]["text"] == "Alpha segment."
    assert undo.json()["active_version"]["id"] == str(ids["version_id"])

    redo = client.post(
        f"/api/v1/transcripts/{ids['transcript_id']}/operations:redo",
        headers={"X-CSRF-Token": csrf},
        json={"base_version_id": str(ids["version_id"])},
    )
    assert redo.status_code == 200, redo.text
    assert redo.json()["segments"][0]["text"] == "Undo target."
