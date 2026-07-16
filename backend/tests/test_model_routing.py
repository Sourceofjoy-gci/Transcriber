import base64
import os
import secrets
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("APP_SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault(
    "CREDENTIAL_ENCRYPTION_KEY",
    base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "a-very-safe-bootstrap-password-1")

from app.api.routes.jobs import _enqueue_transcription, _transcription_queue_for_job  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.models.domain import (  # noqa: E402
    AssetStatus,
    InstalledModel,
    JobStatus,
    MediaAsset,
    ModelCatalog,
    ModelInstallStatus,
    Organisation,
    TranscriptionJob,
    User,
)
from app.providers.local_whisper import ProviderUnavailableError  # noqa: E402
from app.worker.tasks import _resolve_model_options  # noqa: E402


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    with SessionLocal() as db:
        yield db


def test_resolve_model_options_adds_installed_path_for_whisper_cpp(db_session, tmp_path) -> None:
    org = Organisation(name="Acme", slug="acme")
    catalog = ModelCatalog(
        adapter_key="whisper_cpp",
        model_identifier="ggml-tiny.bin",
        name="Whisper.cpp Tiny",
        model_type="transcription",
        requirements={"recommended_device": "cpu"},
        capabilities={"tasks": ["transcription"]},
    )
    db_session.add_all([org, catalog])
    db_session.flush()
    item = InstalledModel(
        organisation_id=org.id,
        catalog_id=catalog.id,
        status=ModelInstallStatus.installed,
        enabled=True,
        storage_key="organisations/acme/models/ggml-tiny.bin",
        hardware_compatibility={"compatible": True},
    )
    db_session.add(item)
    db_session.commit()

    provider_key, options = _resolve_model_options(
        db_session,
        SimpleNamespace(
            execution_target_id=item.id,
            execution_target_kind="local_model",
            organisation_id=org.id,
            options={},
        ),
        SimpleNamespace(
            model_root=tmp_path,
            default_transcription_provider="faster_whisper",
            default_transcription_model="base",
        ),
    )

    assert provider_key == "whisper_cpp"
    assert options["model_path"] == str(tmp_path / "organisations/acme/models/ggml-tiny.bin")
    assert options["model_size"] == "ggml-tiny.bin"


@pytest.mark.parametrize("adapter_key", ["nemo_asr", "nemo_salm", "transformers_asr", "qwen_asr"])
def test_resolve_model_options_adds_installed_path_for_huggingface_snapshot_adapters(
    db_session, tmp_path, adapter_key
) -> None:
    org = Organisation(name="Acme", slug="acme")
    catalog = ModelCatalog(
        adapter_key=adapter_key,
        model_identifier="vendor/speech-model",
        name="Managed Speech Model",
        model_type="transcription",
        requirements={"recommended_device": "cuda", "download_backend": "huggingface_hub"},
        capabilities={"tasks": ["transcription"]},
    )
    db_session.add_all([org, catalog])
    db_session.flush()
    item = InstalledModel(
        organisation_id=org.id,
        catalog_id=catalog.id,
        status=ModelInstallStatus.installed,
        enabled=True,
        storage_key="organisations/acme/models/vendor-speech-model",
        hardware_compatibility={"compatible": True},
    )
    db_session.add(item)
    db_session.commit()

    provider_key, options = _resolve_model_options(
        db_session,
        SimpleNamespace(
            execution_target_id=item.id,
            execution_target_kind="local_model",
            organisation_id=org.id,
            options={},
        ),
        SimpleNamespace(
            model_root=tmp_path,
            default_transcription_provider="faster_whisper",
            default_transcription_model="base",
        ),
    )

    assert provider_key == adapter_key
    assert options["model_path"] == str(tmp_path / "organisations/acme/models/vendor-speech-model")
    assert options["model_size"] == "vendor/speech-model"


def test_cuda_required_model_jobs_route_to_gpu_queue(db_session) -> None:
    job = _seed_cuda_model_job(db_session)

    assert _transcription_queue_for_job(db_session, job.id) == "transcription.gpu"


def test_enqueue_transcription_uses_model_queue(db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.worker import tasks as tasks_module

    job = _seed_cuda_model_job(db_session)
    calls: list[dict] = []

    def fake_apply_async(*, args, queue):
        calls.append({"args": args, "queue": queue})

    monkeypatch.setattr(tasks_module.run_transcription_job, "apply_async", fake_apply_async)

    _enqueue_transcription(job.id, db_session)

    assert calls == [{"args": (str(job.id),), "queue": "transcription.gpu"}]


def _seed_cuda_model_job(db_session) -> TranscriptionJob:
    unique_id = uuid4()
    org = Organisation(name=f"Acme {unique_id}", slug=f"acme-{unique_id}")
    user = User(
        email="admin@example.com",
        password_hash="hash",
        display_name="Admin",
    )
    catalog = ModelCatalog(
        adapter_key="nemo_salm",
        model_identifier="nvidia/canary-qwen-2.5b",
        name="Canary Qwen 2.5B",
        model_type="transcription",
        requirements={"recommended_device": "cuda", "requires_cuda": True},
        capabilities={"tasks": ["transcription"]},
    )
    db_session.add_all([org, user, catalog])
    db_session.flush()
    asset = MediaAsset(
        organisation_id=org.id,
        uploaded_by_id=user.id,
        original_filename="meeting.wav",
        content_type="audio/wav",
        byte_size=1024,
        sha256="a" * 64,
        storage_key="organisations/acme/assets/meeting.wav",
        status=AssetStatus.ready,
    )
    model = InstalledModel(
        organisation_id=org.id,
        catalog_id=catalog.id,
        status=ModelInstallStatus.installed,
        enabled=True,
    )
    db_session.add_all([asset, model])
    db_session.flush()
    job = TranscriptionJob(
        organisation_id=org.id,
        asset_id=asset.id,
        requested_by_id=user.id,
        execution_target_kind="local_model",
        execution_target_id=model.id,
        status=JobStatus.queued,
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.mark.parametrize(
    ("status", "enabled"),
    [
        (ModelInstallStatus.queued, True),
        (ModelInstallStatus.downloading, True),
        (ModelInstallStatus.failed, True),
        (ModelInstallStatus.deleting, False),
        (ModelInstallStatus.installed, False),
    ],
)
def test_resolve_model_options_rejects_unusable_model_states(db_session, tmp_path, status, enabled) -> None:
    org, item = _seed_installed_model(db_session, status=status, enabled=enabled)

    with pytest.raises(ProviderUnavailableError, match="installed and enabled"):
        _resolve_model_options(
            db_session,
            SimpleNamespace(
                execution_target_id=item.id,
                execution_target_kind="local_model",
                organisation_id=org.id,
                options={},
            ),
            SimpleNamespace(
                model_root=tmp_path,
                default_transcription_provider="faster_whisper",
                default_transcription_model="base",
            ),
        )


def test_resolve_model_options_rejects_deleted_model_id(db_session, tmp_path) -> None:
    org = Organisation(name="Acme", slug="acme")
    db_session.add(org)
    db_session.commit()

    with pytest.raises(ProviderUnavailableError, match="installed and enabled"):
        _resolve_model_options(
            db_session,
            SimpleNamespace(
                execution_target_id=uuid4(),
                execution_target_kind="local_model",
                organisation_id=org.id,
                options={},
            ),
            SimpleNamespace(
                model_root=tmp_path,
                default_transcription_provider="faster_whisper",
                default_transcription_model="base",
            ),
        )


def test_resolve_model_options_rejects_hardware_incompatible_model(db_session, tmp_path) -> None:
    org, item = _seed_installed_model(
        db_session,
        status=ModelInstallStatus.installed,
        enabled=True,
        hardware_compatibility={"compatible": False, "reasons": ["Requires CUDA GPU"]},
    )

    with pytest.raises(ProviderUnavailableError, match="Requires CUDA GPU"):
        _resolve_model_options(
            db_session,
            SimpleNamespace(
                execution_target_id=item.id,
                execution_target_kind="local_model",
                organisation_id=org.id,
                options={},
            ),
            SimpleNamespace(
                model_root=tmp_path,
                default_transcription_provider="faster_whisper",
                default_transcription_model="base",
            ),
        )


def _seed_installed_model(
    db_session,
    *,
    status: ModelInstallStatus,
    enabled: bool,
    hardware_compatibility: dict | None = None,
) -> tuple[Organisation, InstalledModel]:
    org = Organisation(name="Acme", slug="acme")
    catalog = ModelCatalog(
        adapter_key="faster_whisper",
        model_identifier="Systran/faster-whisper-tiny",
        name="Faster-Whisper Tiny",
        model_type="transcription",
        requirements={"recommended_device": "cpu_or_cuda"},
        capabilities={"tasks": ["transcription"]},
    )
    db_session.add_all([org, catalog])
    db_session.flush()
    item = InstalledModel(
        organisation_id=org.id,
        catalog_id=catalog.id,
        status=status,
        enabled=enabled,
        storage_key="organisations/acme/models/tiny",
        hardware_compatibility=hardware_compatibility or {},
    )
    db_session.add(item)
    db_session.commit()
    return org, item
