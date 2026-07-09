"""End-to-end tests for the model manager (download + delete flows).

These mirror the bootstrap pattern in test_routes_smoke.py: build the
in-memory engine at module import time, reload every module that captured
SessionLocal / get_db at import time, then exercise the routes with a
TestClient and run the Celery task bodies inline (no Redis broker).
"""

import base64
import builtins
import hashlib
import importlib
import os
import secrets
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy import event as _sa_event
from sqlalchemy.pool import StaticPool

# ── Module-level environment setup (mirrors test_routes_smoke.py) ─────────
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


@_sa_event.listens_for(engine, "connect")
def _enable_sqlite_fk(dbapi_connection, _):
    """SQLite ships with foreign keys disabled; Postgres enforces them, so we
    enable the pragma here to match production semantics for these tests."""
    dbapi_connection.execute("PRAGMA foreign_keys = ON")


Base.metadata.create_all(engine)

importlib.reload(session_module)
session_module.engine = engine
session_module.SessionLocal = session_module.sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)

import app.api.router  # noqa: E402
import app.api.routes.models  # noqa: E402
import app.main  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.worker.model_tasks  # noqa: E402

for mod in (
    app.services.authorization,
    app.services.bootstrap,
    app.api.routes.models,
    app.worker.model_tasks,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.api.routes import models as models_route_module  # noqa: E402
from app.main import app  # noqa: E402
from app.models.domain import (  # noqa: E402
    InstalledModel,
    ModelCatalog,
    ModelInstallStatus,
    ModelTaskDefault,
    Organisation,
)
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402
from app.worker import model_tasks as model_tasks_module  # noqa: E402


# ── Fakes for the third-party downloaders (no network in tests) ──────────
def _fake_snapshot_download(repo_id: str, local_dir: str, **_: object) -> str:
    target = Path(local_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / "model.bin").write_bytes(b"fake-weights")
    return str(target)


def _fake_whisper_load_model(name: str, download_root: str | None = None):
    target = Path(download_root or "")
    target.mkdir(parents=True, exist_ok=True)
    (target / f"{name}.pt").write_bytes(b"fake-weights")

    class _Model:
        pass

    return _Model()


def _install_fake_downloaders(monkeypatch: pytest.MonkeyPatch) -> None:
    hf_hub = types.ModuleType("huggingface_hub")
    hf_hub.snapshot_download = _fake_snapshot_download
    monkeypatch.setitem(sys.modules, "huggingface_hub", hf_hub)
    whisper_mod = types.ModuleType("whisper")
    whisper_mod.load_model = _fake_whisper_load_model
    monkeypatch.setitem(sys.modules, "whisper", whisper_mod)


@pytest.fixture()
def client() -> TestClient:
    session_module.engine = engine
    session_module.SessionLocal = session_module.sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    model_tasks_module.SessionLocal = session_module.SessionLocal

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit
    from app.services.model_catalog import seed_model_catalog

    rate_limit.limiter.reset()

    # Confirm PRAGMA survived table drops on the static-pool connection.
    with engine.connect() as _c:
        from sqlalchemy import text as _text

        assert _c.execute(_text("PRAGMA foreign_keys")).scalar() == 1, "PRAGMA foreign_keys not enabled"

    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())
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


def test_model_catalog_listed_and_protected(client: TestClient) -> None:
    response = client.get("/api/v1/model-catalog")
    assert response.status_code == 401, "Catalog must require auth"

    _login(client)
    response = client.get("/api/v1/model-catalog")
    assert response.status_code == 200
    body = response.json()
    assert len(body) >= 1
    names = {entry["name"] for entry in body}
    assert "Faster-Whisper Base" in names
    assert "Faster-Whisper Tiny" in names
    whisper_cpp = next(entry for entry in body if entry["name"] == "Whisper.cpp Tiny")
    assert whisper_cpp["adapter_key"] == "whisper_cpp"
    assert whisper_cpp["source_url"]
    assert whisper_cpp["checksum"] is not None
    assert whisper_cpp["requirements"]["recommended_device"] == "cpu"

    expected_hf_models = {
        "Canary Qwen 2.5B": ("nemo_salm", "nvidia/canary-qwen-2.5b", "nemo_toolkit"),
        "Granite Speech 3.3 8B": (
            "transformers_asr",
            "ibm-granite/granite-speech-3.3-8b",
            "transformers",
        ),
        "Parakeet TDT 1.1B": ("nemo_asr", "nvidia/parakeet-tdt-1.1b", "nemo_toolkit"),
        "Qwen3-ASR 1.7B": ("qwen_asr", "Qwen/Qwen3-ASR-1.7B", "qwen-asr"),
    }
    by_name = {entry["name"]: entry for entry in body}
    for name, (adapter_key, model_identifier, dependency_marker) in expected_hf_models.items():
        entry = by_name[name]
        assert entry["adapter_key"] == adapter_key
        assert entry["model_identifier"] == model_identifier
        assert entry["source_url"] == f"https://huggingface.co/{model_identifier}"
        assert entry["requirements"]["recommended_device"] == "cuda"
        assert entry["requirements"]["download_backend"] == "huggingface_hub"
        assert any(
            dependency_marker in dependency for dependency in entry["requirements"]["python_dependencies"]
        )
        assert "transcription" in entry["capabilities"]["tasks"]


def test_custom_catalog_entry_can_be_created(client: TestClient) -> None:
    csrf = _login(client)

    response = client.post(
        "/api/v1/model-catalog",
        headers={"X-CSRF-Token": csrf},
        json={
            "adapter_key": "whisper_cpp",
            "model_identifier": "custom/ggml-meeting.bin",
            "name": "Custom Meeting Model",
            "model_type": "transcription",
            "source_url": "https://models.example.com/ggml-meeting.bin",
            "revision": "2026-07-07",
            "size_bytes": 123456,
            "requirements": {"recommended_device": "cpu", "min_ram_bytes": 1_000_000_000},
            "capabilities": {"tasks": ["transcription"], "word_timestamps": False},
            "checksum": "sha256:" + "a" * 64,
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Custom Meeting Model"
    assert body["source_url"] == "https://models.example.com/ggml-meeting.bin"
    assert body["checksum"] == "sha256:" + "a" * 64


def test_download_writes_files_and_updates_status(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    csrf = _login(client)

    # Create the InstalledModel directly so we control its starting state.
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Base"))
        assert catalog is not None
        item = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
        db.add(item)
        db.commit()
        installed_id = str(item.id)

    # Patch the Celery ``.delay`` to execute the task body inline.
    with patch.object(
        model_tasks.download_model, "delay", side_effect=lambda mid: model_tasks.download_model.run(mid)
    ):
        response = client.post(
            f"/api/v1/installed-models/{installed_id}/download",
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 202, response.text

    with session_module.SessionLocal() as db:
        refreshed = db.get(InstalledModel, item.id)
        assert refreshed is not None
        assert refreshed.status == ModelInstallStatus.installed
        assert refreshed.download_progress == 100
        assert refreshed.storage_key is not None
        target = (tmp_path / refreshed.storage_key).resolve()
        assert target.exists(), f"expected files at {target}"
        assert (target / "model.bin").exists()


def test_download_does_not_enqueue_duplicate_active_download(client: TestClient) -> None:
    from app.worker import model_tasks

    csrf = _login(client)
    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Parakeet TDT 1.1B"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.downloading,
            download_progress=10,
        )
        db.add(item)
        db.commit()
        installed_id = str(item.id)

    with patch.object(model_tasks.download_model, "delay") as delay:
        response = client.post(
            f"/api/v1/installed-models/{installed_id}/download",
            headers={"X-CSRF-Token": csrf},
        )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Model download already in progress"
    delay.assert_not_called()


def test_download_writes_huggingface_snapshot_models(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Parakeet TDT 1.1B"))
        assert catalog is not None
        item = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
        db.add(item)
        db.commit()
        installed_id = item.id

    result = model_tasks.download_model.run(str(installed_id))

    assert result == {"status": "installed"}
    with session_module.SessionLocal() as db:
        refreshed = db.get(InstalledModel, installed_id)
        assert refreshed is not None
        assert refreshed.status == ModelInstallStatus.installed
        assert refreshed.storage_key is not None
        target = (tmp_path / refreshed.storage_key).resolve()
        assert target.exists()
        assert (target / "model.bin").exists()


def test_download_verifies_catalog_checksum(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        catalog.checksum = "sha256:" + hashlib.sha256(b"different-weights").hexdigest()
        item = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
        db.add(item)
        db.commit()
        installed_id = item.id

    result = model_tasks.download_model.run(str(installed_id))

    assert result == {"status": "failed", "reason": "download_failed"}
    with session_module.SessionLocal() as db:
        refreshed = db.get(InstalledModel, installed_id)
        assert refreshed is not None
        assert refreshed.status == ModelInstallStatus.failed
        assert refreshed.last_error is not None
        assert "checksum" in refreshed.last_error.lower()


def test_download_can_be_cancelled(client: TestClient) -> None:
    csrf = _login(client)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.downloading,
            download_progress=45,
        )
        db.add(item)
        db.commit()
        installed_id = str(item.id)

    response = client.post(
        f"/api/v1/installed-models/{installed_id}/cancel-download",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "downloading"
    assert body["hardware_compatibility"]["download_cancel_requested"] is True
    assert "cancel" in body["last_error"].lower()


def test_download_worker_honours_cancel_request(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.downloading,
            hardware_compatibility={"download_cancel_requested": True},
        )
        db.add(item)
        db.commit()
        installed_id = item.id

    result = model_tasks.download_model.run(str(installed_id))

    assert result == {"status": "cancelled"}
    with session_module.SessionLocal() as db:
        refreshed = db.get(InstalledModel, installed_id)
        assert refreshed is not None
        assert refreshed.status == ModelInstallStatus.failed
        assert refreshed.last_error == "Model download cancelled"


def test_download_missing_model_noops(client: TestClient) -> None:
    from app.worker import model_tasks

    missing_id = uuid.uuid4()

    with session_module.SessionLocal() as db:
        assert db.get(InstalledModel, missing_id) is None

    assert model_tasks.download_model.run(str(missing_id)) == {"status": "missing"}


def test_download_whisper_local_without_optional_dependency_fails_gracefully(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    real_import = builtins.__import__

    def block_whisper_import(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError("No module named 'whisper'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", block_whisper_import)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
        db.add(item)
        db.commit()
        installed_id = item.id

    result = model_tasks.download_model.run(str(installed_id))

    assert result == {"status": "failed", "reason": "download_failed"}
    with session_module.SessionLocal() as db:
        refreshed = db.get(InstalledModel, installed_id)
        assert refreshed is not None
        assert refreshed.status == ModelInstallStatus.failed
        assert refreshed.last_error is not None
        assert "openai-whisper" in refreshed.last_error


def test_delete_removes_row_and_disk_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    csrf = _login(client)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(organisation_id=org.id, catalog_id=catalog.id)
        db.add(item)
        db.commit()
        installed_id = str(item.id)
        # Simulate a previously-completed install by writing a fake blob.
        target_dir = tmp_path / "organisations" / str(org.id) / "models" / str(item.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "model.bin").write_bytes(b"x")
        item.status = ModelInstallStatus.installed
        item.storage_key = str(target_dir.relative_to(tmp_path))
        db.commit()

    with patch.object(
        model_tasks.delete_model, "delay", side_effect=lambda mid: model_tasks.delete_model.run(mid)
    ):
        response = client.delete(
            f"/api/v1/installed-models/{installed_id}",
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 202, response.text

    with session_module.SessionLocal() as db:
        assert db.get(InstalledModel, item.id) is None

    assert not target_dir.exists(), "model directory should be removed from disk"


def test_delete_blocked_when_set_as_task_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default transcription models must be unassigned before deletion."""
    from app.worker import model_tasks

    _install_fake_downloaders(monkeypatch)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    csrf = _login(client)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Small"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.installed,
            enabled=True,
        )
        db.add(item)
        db.flush()
        db.add(
            ModelTaskDefault(
                organisation_id=org.id,
                task="transcription",
                installed_model_id=item.id,
            )
        )
        db.commit()
        installed_id = str(item.id)
        # Pre-create the model directory so we can prove the route leaves it alone.
        target_dir = tmp_path / "organisations" / str(org.id) / "models" / str(item.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "model.bin").write_bytes(b"x")
        item.storage_key = str(target_dir.relative_to(tmp_path))
        db.commit()

    with patch.object(model_tasks.delete_model, "delay") as delay:
        response = client.delete(
            f"/api/v1/installed-models/{installed_id}",
            headers={"X-CSRF-Token": csrf},
        )
    assert response.status_code == 409, response.text
    assert "default" in response.json()["detail"].lower()
    delay.assert_not_called()

    # The route rejects the request before marking the row or queueing work.
    with session_module.SessionLocal() as db:
        leftover = db.get(InstalledModel, item.id)
        assert leftover is not None
        assert leftover.status == ModelInstallStatus.installed
        assert leftover.enabled is True

    assert target_dir.exists(), "model files must be left intact when deletion is rejected"


def test_delete_task_preserves_default_model_files(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.worker import model_tasks

    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.deleting,
            enabled=False,
        )
        db.add(item)
        db.flush()
        db.add(
            ModelTaskDefault(
                organisation_id=org.id,
                task="transcription",
                installed_model_id=item.id,
            )
        )
        target_dir = tmp_path / "organisations" / str(org.id) / "models" / str(item.id)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "model.bin").write_bytes(b"x")
        item.storage_key = str(target_dir.relative_to(tmp_path))
        db.commit()
        installed_id = item.id

    assert model_tasks.delete_model.run(str(installed_id)) == {"status": "blocked", "reason": "default_model"}

    with session_module.SessionLocal() as db:
        leftover = db.get(InstalledModel, installed_id)
        assert leftover is not None
        assert leftover.status == ModelInstallStatus.installed
        assert leftover.enabled is True

    assert target_dir.exists(), "worker must not delete files for a default model"


def test_set_default_is_reflected_in_installed_models(client: TestClient) -> None:
    csrf = _login(client)

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.installed,
            enabled=True,
        )
        db.add(item)
        db.commit()
        installed_id = str(item.id)

    put = client.put(
        "/api/v1/task-defaults/transcription",
        headers={"X-CSRF-Token": csrf},
        json={"installed_model_id": installed_id},
    )
    assert put.status_code == 200, put.text
    assert put.json()["is_default"] is True

    listed = client.get("/api/v1/installed-models")
    assert listed.status_code == 200
    default_items = [item for item in listed.json() if item["id"] == installed_id]
    assert default_items[0]["is_default"] is True


def test_model_test_uses_installed_model_path(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    csrf = _login(client)
    settings = get_settings()
    monkeypatch.setattr(settings, "model_root", tmp_path)
    captured: dict[str, object] = {}

    class _Provider:
        def probe(self):
            return {"status": "generic"}

        def probe_model(self, model_path: Path, catalog: ModelCatalog) -> dict:
            captured["model_path"] = model_path
            captured["catalog"] = catalog.model_identifier
            return {"status": "ready", "compatible": True}

    class _Registry:
        def transcription(self, key: str):
            assert key == "faster_whisper"
            return _Provider()

    monkeypatch.setattr(models_route_module, "build_local_registry", lambda _: _Registry())

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        catalog = db.scalar(select(ModelCatalog).where(ModelCatalog.name == "Faster-Whisper Tiny"))
        assert catalog is not None
        target_dir = tmp_path / "organisations" / str(org.id) / "models" / "path-aware"
        target_dir.mkdir(parents=True)
        item = InstalledModel(
            organisation_id=org.id,
            catalog_id=catalog.id,
            status=ModelInstallStatus.installed,
            enabled=True,
            storage_key=str(target_dir.relative_to(tmp_path)),
        )
        db.add(item)
        db.commit()
        installed_id = str(item.id)

    response = client.post(
        f"/api/v1/installed-models/{installed_id}/test",
        headers={"X-CSRF-Token": csrf},
    )

    assert response.status_code == 200, response.text
    assert response.json()["probe"]["compatible"] is True
    assert captured["model_path"] == target_dir
    assert captured["catalog"] == "Systran/faster-whisper-tiny"
