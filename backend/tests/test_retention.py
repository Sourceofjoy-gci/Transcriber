"""Retention and hard-delete lifecycle tests."""

import base64
import importlib
import os
import secrets
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
_STORAGE_ROOT = Path(tempfile.mkdtemp(prefix="transcriber-retention-"))

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
from app.storage.contracts import StoredObject  # noqa: E402

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

import app.services.bootstrap  # noqa: E402
import app.worker.retention_tasks  # noqa: E402

for mod in (app.services.bootstrap, app.worker.retention_tasks):
    importlib.reload(mod)

from app.models.domain import (  # noqa: E402
    AssetStatus,
    MediaAsset,
    MediaDerivative,
    MediaDerivativeKind,
    MediaDerivativeStatus,
    Organisation,
    User,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.worker import retention_tasks  # noqa: E402


class FakeObjectStorage:
    key = "fake_object_storage"

    def __init__(self) -> None:
        self.deleted: list[str] = []

    def save(self, source: BinaryIO, object_key: str, max_bytes: int) -> StoredObject:
        content = source.read(max_bytes + 1)
        return StoredObject(storage_key=object_key, byte_size=len(content), sha256="d" * 64)

    def open(self, object_key: str) -> BinaryIO:
        return BytesIO(b"")

    def path_for(self, object_key: str) -> str:
        raise RuntimeError("Object storage does not expose local file paths")

    def delete(self, object_key: str) -> None:
        self.deleted.append(object_key)

    def signed_url(self, object_key: str, expires_in_seconds: int, filename: str | None = None):
        raise NotImplementedError


def _reset_db() -> None:
    os.environ["STORAGE_ROOT"] = str(_STORAGE_ROOT)
    get_settings.cache_clear()
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    retention_tasks.SessionLocal = session_module.SessionLocal
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())


def _seed_deleted_asset(*, legal_hold: bool = False) -> tuple[uuid.UUID, str, str]:
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None
        assert user is not None
        org.retention_days = 7
        asset = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="old.wav",
            content_type="audio/wav",
            byte_size=4096,
            sha256="e" * 64,
            storage_key=f"organisations/{org.id}/assets/old.wav",
            status=AssetStatus.deleted,
            deleted_at=datetime.now(UTC) - timedelta(days=30),
            legal_hold_until=datetime.now(UTC) + timedelta(days=30) if legal_hold else None,
        )
        db.add(asset)
        db.flush()
        derivative_key = f"{asset.storage_key}.waveform.json"
        db.add(
            MediaDerivative(
                organisation_id=org.id,
                asset_id=asset.id,
                kind=MediaDerivativeKind.waveform,
                status=MediaDerivativeStatus.ready,
                storage_key=derivative_key,
                content_type="application/json",
                byte_size=256,
                derivative_metadata={},
            )
        )
        db.commit()
        return asset.id, asset.storage_key, derivative_key


def test_retention_purges_expired_local_asset_files_and_derivatives() -> None:
    _reset_db()
    asset_id, asset_key, derivative_key = _seed_deleted_asset()
    for key in (asset_key, derivative_key):
        path = _STORAGE_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")

    result = retention_tasks.purge_expired_assets.run()

    assert result["purged_assets"] == 1
    assert not (_STORAGE_ROOT / asset_key).exists()
    assert not (_STORAGE_ROOT / derivative_key).exists()
    with session_module.SessionLocal() as db:
        assert db.get(MediaAsset, asset_id) is None
        assert not list(db.scalars(select(MediaDerivative).where(MediaDerivative.asset_id == asset_id)))


def test_retention_skips_assets_with_active_legal_hold() -> None:
    _reset_db()
    asset_id, asset_key, derivative_key = _seed_deleted_asset(legal_hold=True)
    for key in (asset_key, derivative_key):
        path = _STORAGE_ROOT / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"media")

    result = retention_tasks.purge_expired_assets.run()

    assert result["purged_assets"] == 0
    assert (_STORAGE_ROOT / asset_key).exists()
    assert (_STORAGE_ROOT / derivative_key).exists()
    with session_module.SessionLocal() as db:
        assert db.get(MediaAsset, asset_id) is not None


def test_retention_uses_storage_contract_for_object_storage(monkeypatch) -> None:
    _reset_db()
    asset_id, asset_key, derivative_key = _seed_deleted_asset()
    fake_storage = FakeObjectStorage()
    monkeypatch.setattr(retention_tasks, "build_storage_provider", lambda _settings: fake_storage)

    result = retention_tasks.purge_expired_assets.run()

    assert result["purged_assets"] == 1
    assert fake_storage.deleted == [derivative_key, asset_key]
    with session_module.SessionLocal() as db:
        assert db.get(MediaAsset, asset_id) is None
