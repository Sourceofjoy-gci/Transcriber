import uuid
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.domain import AssetStatus, MediaAsset
from app.schemas.media import (
    AssetDownloadUrlResponse,
    AssetListResponse,
    AssetMetadataResponse,
    AssetResponse,
    MediaDerivativeListResponse,
    MediaDerivativeResponse,
)
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.malware import build_malware_scanner
from app.services.media import MediaService
from app.services.storage_factory import build_storage_provider

router = APIRouter(prefix="/assets", tags=["assets"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
AssetReader = Annotated[Principal, Depends(require_permission("assets.read"))]
AssetCreator = Annotated[Principal, Depends(require_permission("assets.create"))]
AssetDeleter = Annotated[Principal, Depends(require_permission("assets.delete"))]


@router.post(
    "/upload",
    response_model=AssetResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", get_settings().rate_limit_upload))],
)
def upload_asset(
    request: Request,
    file: Annotated[UploadFile, File(...)],
    principal: AssetCreator,
    db: DbSession,
    settings: SettingsDependency,
    project_id: uuid.UUID | None = None,
) -> AssetResponse:
    service = _media_service(db, settings)
    asset = service.upload(principal, file, project_id)
    write_audit(
        db,
        principal,
        "asset.uploaded",
        "media_asset",
        asset.id,
        "success",
        request,
        {"size": asset.byte_size},
    )
    db.commit()
    db.refresh(asset)
    _enqueue_metadata_extraction(asset.id)
    return _asset_response(service, asset)


@router.get("", response_model=AssetListResponse)
def list_assets(
    principal: AssetReader,
    db: DbSession,
    settings: SettingsDependency,
    offset: int = 0,
    limit: int = 25,
    project_id: uuid.UUID | None = None,
    status_filter: Annotated[AssetStatus | None, Query(alias="status")] = None,
    q: str | None = None,
) -> AssetListResponse:
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid pagination values"
        )
    service = _media_service(db, settings)
    query = select(MediaAsset).where(
        MediaAsset.organisation_id == principal.organisation.id, MediaAsset.deleted_at.is_(None)
    )
    if project_id is not None:
        query = query.where(MediaAsset.project_id == project_id)
    if status_filter is not None:
        query = query.where(MediaAsset.status == status_filter)
    if q and q.strip():
        query = query.where(MediaAsset.original_filename.ilike(f"%{q.strip()}%"))
    assets = list(db.scalars(query.order_by(MediaAsset.created_at.desc()).offset(offset).limit(limit + 1)))
    has_more = len(assets) > limit
    return AssetListResponse(
        items=[_asset_response(service, asset) for asset in assets[:limit]],
        next_offset=offset + limit if has_more else None,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: uuid.UUID, principal: AssetReader, db: DbSession, settings: SettingsDependency
) -> AssetResponse:
    service = _media_service(db, settings)
    return _asset_response(service, service.get_asset(principal, asset_id))


@router.get("/{asset_id}/download")
def download_asset(
    asset_id: uuid.UUID, request: Request, principal: AssetReader, db: DbSession, settings: SettingsDependency
) -> Response:
    service = _media_service(db, settings)
    asset = service.get_asset(principal, asset_id)
    if asset.status == AssetStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    write_audit(db, principal, "asset.downloaded", "media_asset", asset.id, "success", request)
    db.commit()
    storage = build_storage_provider(settings)
    try:
        return FileResponse(
            path=storage.path_for(asset.storage_key),
            media_type=asset.content_type,
            filename=asset.original_filename,
        )
    except RuntimeError:
        headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(asset.original_filename)}"}
        return StreamingResponse(
            storage.open(asset.storage_key),
            media_type=asset.content_type,
            headers=headers,
        )


@router.post("/{asset_id}/download-url", response_model=AssetDownloadUrlResponse)
def create_asset_download_url(
    asset_id: uuid.UUID,
    request: Request,
    principal: AssetReader,
    db: DbSession,
    settings: SettingsDependency,
) -> AssetDownloadUrlResponse:
    service = _media_service(db, settings)
    asset = service.get_asset(principal, asset_id)
    if asset.status == AssetStatus.deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
    signed_url = service.signed_download_url(
        asset,
        api_download_url=str(request.url_for("download_asset", asset_id=asset.id)),
    )
    write_audit(
        db,
        principal,
        "asset.download_url.created",
        "media_asset",
        asset.id,
        "success",
        request,
        {"storage_provider": build_storage_provider(settings).key},
    )
    db.commit()
    return AssetDownloadUrlResponse(
        url=signed_url.url,
        method=signed_url.method,
        expires_at=signed_url.expires_at,
        headers=signed_url.headers or {},
    )


@router.get("/{asset_id}/derivatives", response_model=MediaDerivativeListResponse)
def list_asset_derivatives(
    asset_id: uuid.UUID, principal: AssetReader, db: DbSession, settings: SettingsDependency
) -> MediaDerivativeListResponse:
    service = _media_service(db, settings)
    derivatives = service.list_derivatives(principal, asset_id)
    return MediaDerivativeListResponse(
        items=[MediaDerivativeResponse.model_validate(item) for item in derivatives]
    )


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: uuid.UUID,
    request: Request,
    principal: AssetDeleter,
    db: DbSession,
    settings: SettingsDependency,
) -> None:
    service = _media_service(db, settings)
    asset = service.get_asset(principal, asset_id)
    asset.status = AssetStatus.deleted
    asset.deleted_at = datetime.now(UTC)
    write_audit(db, principal, "asset.delete_requested", "media_asset", asset.id, "success", request)
    db.commit()


def _asset_response(service: MediaService, asset: MediaAsset) -> AssetResponse:
    metadata = service.get_metadata(asset.id)
    return AssetResponse(
        id=asset.id,
        project_id=asset.project_id,
        original_filename=asset.original_filename,
        content_type=asset.content_type,
        byte_size=asset.byte_size,
        sha256=asset.sha256,
        status=asset.status,
        failure_code=asset.failure_code,
        failure_message=asset.failure_message,
        created_at=asset.created_at,
        metadata=AssetMetadataResponse.model_validate(metadata) if metadata else None,
    )


def _enqueue_metadata_extraction(asset_id: uuid.UUID) -> None:
    try:
        from app.worker.tasks import extract_media_metadata

        extract_media_metadata.delay(str(asset_id))
    except Exception:
        return


def _media_service(db: Session, settings: Settings) -> MediaService:
    return MediaService(db, build_storage_provider(settings), settings, build_malware_scanner(settings))
