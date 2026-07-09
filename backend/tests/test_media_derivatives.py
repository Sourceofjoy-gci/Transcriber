"""Media derivative and signed download lifecycle tests."""

import base64
import importlib
import os
import secrets
import tempfile
import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="transcriber-media-derivatives-"))

os.environ.setdefault("APP_SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "a-very-safe-bootstrap-password-1")
os.environ.setdefault("STORAGE_ROOT", str(_STORAGE_ROOT))

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
import app.main  # noqa: E402
import app.services.audit  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.worker.media_derivative_tasks as media_derivative_tasks_module  # noqa: E402
import app.worker.tasks as worker_tasks_module  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.audit,
    app.services.authorization,
    app.api.routes.auth,
    app.api.routes.assets,
    media_derivative_tasks_module,
    worker_tasks_module,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    AuditLog,
    MediaAsset,
    MediaDerivative,
    MediaDerivativeKind,
    MediaDerivativeStatus,
    Organisation,
    User,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.worker import media_derivative_tasks  # noqa: E402
from app.worker.tasks import extract_media_metadata  # noqa: E402


def _client() -> TestClient:
    os.environ["STORAGE_ROOT"] = str(_STORAGE_ROOT)
    get_settings.cache_clear()
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    worker_tasks_module.SessionLocal = session_module.SessionLocal
    media_derivative_tasks_module.SessionLocal = session_module.SessionLocal
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


def _seed_ready_asset() -> uuid.UUID:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="meeting.wav",
            content_type="audio/wav",
            byte_size=4096,
            sha256="c" * 64,
            storage_key=f"organisations/{org.id}/assets/meeting.wav",
            status=AssetStatus.ready,
        )
        db.add(asset)
        db.flush()
        original_path = _STORAGE_ROOT / asset.storage_key
        original_path.parent.mkdir(parents=True, exist_ok=True)
        original_path.write_bytes(b"RIFF....WAVE")
        db.commit()
        return asset.id


def test_derivative_endpoint_and_signed_download_contract_are_audited() -> None:
    client = _client()
    csrf = _login(client)
    asset_id = _seed_ready_asset()

    with session_module.SessionLocal() as db:
        asset = db.get(MediaAsset, asset_id)
        assert asset is not None
        db.add(
            MediaDerivative(
                organisation_id=asset.organisation_id,
                asset_id=asset.id,
                kind=MediaDerivativeKind.waveform,
                status=MediaDerivativeStatus.ready,
                storage_key=f"{asset.storage_key}.waveform.json",
                content_type="application/json",
                byte_size=128,
                derivative_metadata={"points": 64, "sample_rate_hz": 50},
            )
        )
        db.commit()

    derivatives = client.get(f"/api/v1/assets/{asset_id}/derivatives")
    assert derivatives.status_code == 200, derivatives.text
    body = derivatives.json()
    assert body["items"][0]["kind"] == "waveform"
    assert body["items"][0]["status"] == "ready"
    assert body["items"][0]["metadata"]["points"] == 64

    signed = client.post(
        f"/api/v1/assets/{asset_id}/download-url",
        headers={"X-CSRF-Token": csrf},
    )
    assert signed.status_code == 200, signed.text
    signed_body = signed.json()
    assert signed_body["method"] == "GET"
    assert f"/api/v1/assets/{asset_id}/download" in signed_body["url"]
    assert signed_body["expires_at"]

    with session_module.SessionLocal() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "asset.download_url.created"))
        assert audit is not None
        assert audit.resource_id == asset_id
        assert audit.data["storage_provider"] == "local_filesystem"


def test_generate_media_derivatives_persists_waveform_audio_and_thumbnail_records() -> None:
    client = _client()
    _login(client)
    asset_id = _seed_ready_asset()

    result = media_derivative_tasks.generate_media_derivatives.run(str(asset_id))

    assert result == {"status": "completed", "asset_id": str(asset_id), "created": 3}
    with session_module.SessionLocal() as db:
        derivatives = list(db.scalars(select(MediaDerivative).where(MediaDerivative.asset_id == asset_id)))
        assert {item.kind for item in derivatives} == {
            MediaDerivativeKind.waveform,
            MediaDerivativeKind.normalized_audio,
            MediaDerivativeKind.thumbnail,
        }
        assert all(item.status == MediaDerivativeStatus.ready for item in derivatives)
        assert all(item.storage_key for item in derivatives)
        assert sum(item.byte_size for item in derivatives) > 0


def test_metadata_extraction_queues_derivative_generation(monkeypatch) -> None:
    client = _client()
    _login(client)
    asset_id = _seed_ready_asset()

    queued: list[str] = []

    monkeypatch.setattr(
        worker_tasks_module,
        "_run_ffprobe",
        lambda *_args, **_kwargs: {
            "format": {"duration": "1.5", "format_name": "wav", "bit_rate": "128000"},
            "streams": [
                {
                    "codec_type": "audio",
                    "codec_name": "pcm_s16le",
                    "sample_rate": "16000",
                    "channels": 1,
                }
            ],
        },
    )
    monkeypatch.setattr(
        media_derivative_tasks_module.generate_media_derivatives,
        "delay",
        lambda queued_asset_id: queued.append(queued_asset_id),
    )

    result = extract_media_metadata.run(str(asset_id))

    assert result["status"] == "ready"
    assert queued == [str(asset_id)]
