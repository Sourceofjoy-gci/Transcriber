import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.domain import InstalledModel, ModelCatalog, ModelInstallStatus, ModelTaskDefault
from app.providers.registry import build_local_registry
from app.services.authorization import Principal, require_permission
from app.services.hardware import assess_model_compatibility, detect_hardware

router = APIRouter(tags=["models"])
DbSession = Annotated[Session, Depends(get_db)]
ModelManager = Annotated[Principal, Depends(require_permission("models.manage"))]


class CatalogResponse(BaseModel):
    id: uuid.UUID
    adapter_key: str
    model_identifier: str
    name: str
    model_type: str
    source_url: str | None
    revision: str | None
    size_bytes: int | None
    requirements: dict
    capabilities: dict
    checksum: str | None


class CatalogInput(BaseModel):
    adapter_key: str = Field(min_length=1, max_length=100)
    model_identifier: str = Field(min_length=1, max_length=300)
    name: str = Field(min_length=1, max_length=200)
    model_type: str = Field(default="transcription", min_length=1, max_length=100)
    source_url: str | None = Field(default=None, max_length=1000)
    revision: str | None = Field(default=None, max_length=150)
    size_bytes: int | None = Field(default=None, ge=0)
    requirements: dict = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)
    checksum: str | None = Field(default=None, max_length=128)


class InstalledResponse(BaseModel):
    id: uuid.UUID
    catalog_id: uuid.UUID
    status: ModelInstallStatus
    enabled: bool
    download_progress: int
    storage_key: str | None
    verified_at: datetime | None
    last_error: str | None
    hardware_compatibility: dict
    is_default: bool
    catalog: CatalogResponse


class DefaultRequest(BaseModel):
    installed_model_id: uuid.UUID


@router.get("/model-catalog", response_model=list[CatalogResponse])
def list_catalog(principal: ModelManager, db: DbSession):
    return [
        CatalogResponse.model_validate(model, from_attributes=True)
        for model in db.scalars(select(ModelCatalog).order_by(ModelCatalog.name))
    ]


@router.post("/model-catalog", response_model=CatalogResponse, status_code=status.HTTP_201_CREATED)
def create_catalog_entry(payload: CatalogInput, principal: ModelManager, db: DbSession):
    existing = db.scalar(
        select(ModelCatalog).where(
            ModelCatalog.adapter_key == payload.adapter_key,
            ModelCatalog.model_identifier == payload.model_identifier,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Model catalog entry already exists")
    item = ModelCatalog(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return CatalogResponse.model_validate(item, from_attributes=True)


@router.get("/installed-models", response_model=list[InstalledResponse])
def list_installed(principal: ModelManager, db: DbSession):
    installed = list(
        db.scalars(select(InstalledModel).where(InstalledModel.organisation_id == principal.organisation.id))
    )
    return [_installed_response(db, item) for item in installed]


@router.post(
    "/installed-models/{catalog_id}", response_model=InstalledResponse, status_code=status.HTTP_201_CREATED
)
def add_installed(catalog_id: uuid.UUID, principal: ModelManager, db: DbSession):
    catalog = db.get(ModelCatalog, catalog_id)
    if catalog is None:
        raise HTTPException(status_code=404, detail="Model catalog entry not found")
    item = db.scalar(
        select(InstalledModel).where(
            InstalledModel.organisation_id == principal.organisation.id,
            InstalledModel.catalog_id == catalog_id,
        )
    )
    if item is None:
        item = InstalledModel(organisation_id=principal.organisation.id, catalog_id=catalog_id)
        db.add(item)
        db.commit()
        db.refresh(item)
    return _installed_response(db, item)


@router.post(
    "/installed-models/{model_id}/download",
    response_model=InstalledResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def download(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    if item.status == ModelInstallStatus.downloading:
        raise HTTPException(status_code=409, detail="Model download already in progress")
    item.status, item.download_progress, item.last_error = ModelInstallStatus.downloading, 0, None
    item.hardware_compatibility = {
        key: value
        for key, value in (item.hardware_compatibility or {}).items()
        if key != "download_cancel_requested"
    }
    db.commit()
    from app.worker.model_tasks import download_model

    download_model.delay(str(item.id))
    return _installed_response(db, item)


@router.post("/installed-models/{model_id}/cancel-download", response_model=InstalledResponse)
def cancel_download(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    if item.status != ModelInstallStatus.downloading:
        raise HTTPException(status_code=409, detail="Only active downloads can be cancelled")
    item.last_error = "Model download cancellation requested"
    item.hardware_compatibility = {
        **(item.hardware_compatibility or {}),
        "download_cancel_requested": True,
    }
    db.commit()
    return _installed_response(db, item)


@router.post("/installed-models/{model_id}/enable", response_model=InstalledResponse)
def enable(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    if item.status != ModelInstallStatus.installed:
        raise HTTPException(status_code=409, detail="Model must be installed before it can be enabled")
    item.enabled = True
    db.commit()
    return _installed_response(db, item)


@router.post("/installed-models/{model_id}/disable", response_model=InstalledResponse)
def disable(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    item.enabled = False
    db.commit()
    return _installed_response(db, item)


@router.post("/installed-models/{model_id}/test")
def test_model(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    catalog = db.get(ModelCatalog, item.catalog_id)
    if catalog is None:
        raise HTTPException(status_code=409, detail="Model catalog entry is missing")
    settings = get_settings()
    registry = build_local_registry(settings)
    try:
        provider = registry.transcription(catalog.adapter_key)
    except LookupError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    compatibility = assess_model_compatibility(catalog.requirements, detect_hardware())
    model_path = _installed_model_path(settings, item)
    if model_path is not None and hasattr(provider, "probe_model"):
        probe = provider.probe_model(model_path, catalog)  # type: ignore[attr-defined]
    else:
        probe = provider.probe()
    item.hardware_compatibility = {**compatibility, **probe}
    db.commit()
    return {"status": probe.get("status", "unknown"), "probe": probe, "model_id": str(item.id)}


@router.delete("/installed-models/{model_id}", status_code=status.HTTP_202_ACCEPTED)
def delete(model_id: uuid.UUID, principal: ModelManager, db: DbSession):
    item = _item(db, principal, model_id)
    default = db.scalar(
        select(ModelTaskDefault).where(
            ModelTaskDefault.organisation_id == principal.organisation.id,
            ModelTaskDefault.installed_model_id == item.id,
        )
    )
    if default is not None:
        raise HTTPException(
            status_code=409,
            detail="Default model cannot be deleted. Choose another default model first.",
        )
    item.status, item.enabled = ModelInstallStatus.deleting, False
    db.commit()
    from app.worker.model_tasks import delete_model

    delete_model.delay(str(item.id))


@router.get("/hardware/capabilities")
def hardware(principal: ModelManager):
    return detect_hardware()


@router.get("/task-defaults/transcription", response_model=InstalledResponse | None)
def get_default(principal: ModelManager, db: DbSession):
    default = db.scalar(
        select(ModelTaskDefault).where(
            ModelTaskDefault.organisation_id == principal.organisation.id,
            ModelTaskDefault.task == "transcription",
        )
    )
    if default is None:
        return None
    item = _item(db, principal, default.installed_model_id)
    return _installed_response(db, item)


@router.put("/task-defaults/transcription", response_model=InstalledResponse)
def set_default(payload: DefaultRequest, principal: ModelManager, db: DbSession):
    item = _item(db, principal, payload.installed_model_id)
    if item.status != ModelInstallStatus.installed or not item.enabled:
        raise HTTPException(status_code=409, detail="Default model must be installed and enabled")
    if (item.hardware_compatibility or {}).get("compatible") is False:
        raise HTTPException(status_code=409, detail="Default model is incompatible with this worker")
    default = db.scalar(
        select(ModelTaskDefault).where(
            ModelTaskDefault.organisation_id == principal.organisation.id,
            ModelTaskDefault.task == "transcription",
        )
    )
    if default is None:
        default = ModelTaskDefault(
            organisation_id=principal.organisation.id,
            task="transcription",
            installed_model_id=item.id,
            updated_by_id=principal.user.id,
        )
        db.add(default)
    else:
        default.installed_model_id, default.updated_by_id = item.id, principal.user.id
    db.commit()
    return _installed_response(db, item)


def _item(db, principal, model_id):
    item = db.scalar(
        select(InstalledModel).where(
            InstalledModel.id == model_id, InstalledModel.organisation_id == principal.organisation.id
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Installed model not found")
    return item


def _installed_response(db, item):
    default = db.scalar(
        select(ModelTaskDefault).where(
            ModelTaskDefault.organisation_id == item.organisation_id,
            ModelTaskDefault.task == "transcription",
            ModelTaskDefault.installed_model_id == item.id,
        )
    )
    return InstalledResponse(
        id=item.id,
        catalog_id=item.catalog_id,
        status=item.status,
        enabled=item.enabled,
        download_progress=item.download_progress,
        storage_key=item.storage_key,
        verified_at=item.verified_at,
        last_error=item.last_error,
        hardware_compatibility=item.hardware_compatibility or {},
        is_default=default is not None,
        catalog=CatalogResponse.model_validate(db.get(ModelCatalog, item.catalog_id), from_attributes=True),
    )


def _installed_model_path(settings, item: InstalledModel) -> Path | None:
    if not item.storage_key:
        return None
    return settings.model_root / item.storage_key
