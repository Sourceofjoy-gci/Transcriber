import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen
from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.domain import InstalledModel, ModelCatalog, ModelInstallStatus, ModelTaskDefault
from app.worker.celery_app import celery_app

HUGGINGFACE_SNAPSHOT_ADAPTERS = {"nemo_asr", "nemo_salm", "transformers_asr", "qwen_asr"}


class DownloadCancelled(RuntimeError):
    pass


@celery_app.task(name="app.worker.model_tasks.download_model")
def download_model(model_id: str) -> dict:
    settings = get_settings()
    model_uuid = UUID(model_id)
    with SessionLocal() as db:
        item = db.get(InstalledModel, model_uuid)
        if item is None:
            return {"status": "missing"}
        catalog = db.get(ModelCatalog, item.catalog_id)
        if catalog is None:
            item.status = ModelInstallStatus.failed
            item.last_error = "Model catalog entry is missing"
            db.commit()
            return {"status": "failed", "reason": "catalog_missing"}
        if _download_cancel_requested(item):
            return _mark_download_cancelled(db, item)
        target = _target_path(settings.model_root, item)
        try:
            target.mkdir(parents=True, exist_ok=True)
            item.download_progress = 10
            db.commit()
            downloaded_path: Path = target
            if catalog.adapter_key == "faster_whisper":
                from huggingface_hub import snapshot_download

                snapshot_download(catalog.model_identifier, local_dir=str(target))
            elif catalog.adapter_key in HUGGINGFACE_SNAPSHOT_ADAPTERS:
                downloaded_path = _download_huggingface_snapshot(catalog, target)
            elif catalog.adapter_key == "whisper_local":
                try:
                    import whisper
                except ImportError as error:
                    raise RuntimeError(
                        "openai-whisper package is not installed in this worker image"
                    ) from error

                whisper.load_model(catalog.model_identifier, download_root=str(target))
            elif catalog.adapter_key == "whisper_cpp":
                downloaded_path = _download_whisper_cpp(catalog, target)
            else:
                raise ValueError("This adapter does not support managed downloads")
            db.refresh(item)
            if _download_cancel_requested(item):
                raise DownloadCancelled("Model download cancelled")
            _verify_model_checksum(downloaded_path, catalog.checksum)
            item.storage_key = str(downloaded_path.relative_to(settings.model_root))
            item.status = ModelInstallStatus.installed
            item.download_progress = 100
            item.last_error = None
            item.hardware_compatibility = {
                key: value
                for key, value in (item.hardware_compatibility or {}).items()
                if key != "download_cancel_requested"
            }
            item.verified_at = datetime.now(UTC)
            db.commit()
            return {"status": "installed"}
        except DownloadCancelled:
            return _mark_download_cancelled(db, item)
        except Exception as error:
            return _mark_download_failed(db, model_uuid, error)


@celery_app.task(name="app.worker.model_tasks.delete_model")
def delete_model(model_id: str) -> dict:
    settings = get_settings()
    with SessionLocal() as db:
        item = db.get(InstalledModel, UUID(model_id))
        if item is None:
            return {"status": "missing"}
        default = db.scalar(select(ModelTaskDefault).where(ModelTaskDefault.installed_model_id == item.id))
        if default is not None:
            item.status = ModelInstallStatus.installed
            item.enabled = True
            db.commit()
            return {"status": "blocked", "reason": "default_model"}
        if item and item.storage_key:
            target = (settings.model_root / item.storage_key).resolve()
            if settings.model_root.resolve() in target.parents:
                if target.is_dir():
                    shutil.rmtree(target, ignore_errors=True)
                elif target.exists():
                    target.unlink(missing_ok=True)
        db.delete(item)
        db.commit()
    return {"status": "deleted"}


def _target_path(root: Path, item: InstalledModel) -> Path:
    return (root / "organisations" / str(item.organisation_id) / "models" / str(item.id)).resolve()


def _download_whisper_cpp(catalog: ModelCatalog, target: Path) -> Path:
    if not catalog.source_url:
        raise ValueError("Whisper.cpp catalog entry is missing a source URL")
    filename = Path(urlparse(catalog.source_url).path).name or Path(catalog.model_identifier).name
    destination = target / filename
    with urlopen(catalog.source_url, timeout=60) as response:
        with destination.open("wb") as handle:
            shutil.copyfileobj(response, handle)
    return destination


def _download_huggingface_snapshot(catalog: ModelCatalog, target: Path) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise RuntimeError("huggingface-hub package is not installed in this worker image") from error

    snapshot_download(
        repo_id=catalog.model_identifier,
        revision=catalog.revision,
        local_dir=str(target),
    )
    return target


def _verify_model_checksum(target: Path, checksum: str | None) -> None:
    if not checksum:
        return
    algorithm, expected = _parse_checksum(checksum)
    if algorithm != "sha256":
        raise ValueError(f"Unsupported model checksum algorithm: {algorithm}")
    actual = _sha256_for_path(target)
    if actual.lower() != expected.lower():
        raise ValueError("Model checksum verification failed")


def _parse_checksum(checksum: str) -> tuple[str, str]:
    if ":" in checksum:
        algorithm, expected = checksum.split(":", 1)
        return algorithm.lower(), expected
    return "sha256", checksum


def _sha256_for_path(target: Path) -> str:
    if target.is_file():
        return _sha256_file(target)
    files = sorted(path for path in target.rglob("*") if path.is_file())
    if len(files) == 1:
        return _sha256_file(files[0])
    digest = hashlib.sha256()
    for path in files:
        relative = path.relative_to(target).as_posix().encode("utf-8")
        digest.update(relative)
        digest.update(b"\0")
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_cancel_requested(item: InstalledModel) -> bool:
    return bool((item.hardware_compatibility or {}).get("download_cancel_requested"))


def _mark_download_cancelled(db, item: InstalledModel) -> dict:
    item.status = ModelInstallStatus.failed
    item.enabled = False
    item.last_error = "Model download cancelled"
    item.download_progress = 0
    item.hardware_compatibility = {
        **(item.hardware_compatibility or {}),
        "download_cancel_requested": True,
    }
    db.commit()
    return {"status": "cancelled"}


def _mark_download_failed(db, model_id: UUID, error: Exception) -> dict:
    db.rollback()
    item = db.get(InstalledModel, model_id)
    if item is None:
        return {"status": "missing"}
    item.status = ModelInstallStatus.failed
    item.last_error = f"Model download failed: {error}"[:500]
    try:
        db.commit()
    except Exception:
        db.rollback()
        if db.get(InstalledModel, model_id) is None:
            return {"status": "missing"}
        raise
    return {"status": "failed", "reason": "download_failed"}
