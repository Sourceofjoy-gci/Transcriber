from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.schemas.media import StorageOverviewResponse, StoragePurgeResponse
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.malware import build_malware_scanner
from app.services.media import MediaService
from app.services.storage_factory import build_storage_provider

router = APIRouter(prefix="/storage", tags=["storage"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
StorageManager = Annotated[Principal, Depends(require_permission("storage.manage"))]


@router.get("/overview", response_model=StorageOverviewResponse)
def get_storage_overview(
    principal: StorageManager,
    db: DbSession,
    settings: SettingsDependency,
) -> StorageOverviewResponse:
    service = _media_service(db, settings)
    return StorageOverviewResponse(**service.storage_overview(principal))


@router.post("/purge", response_model=StoragePurgeResponse)
def purge_expired_storage(
    request: Request,
    principal: StorageManager,
    db: DbSession,
) -> StoragePurgeResponse:
    from app.worker.retention_tasks import purge_expired_assets

    result = purge_expired_assets.run()
    write_audit(
        db,
        principal,
        "storage.purge_requested",
        "storage",
        None,
        "success",
        request,
        result,
    )
    db.commit()
    return StoragePurgeResponse(
        status=result.get("status", "completed"),
        purged_assets=int(result.get("purged_assets", 0)),
        deleted_objects=int(result.get("deleted_objects", 0)),
    )


def _media_service(db: Session, settings: Settings) -> MediaService:
    return MediaService(db, build_storage_provider(settings), settings, build_malware_scanner(settings))
