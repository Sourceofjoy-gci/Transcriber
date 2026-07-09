from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import Organisation, SystemSetting
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/settings", tags=["settings"])
DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[Principal, Depends(require_permission("settings.manage"))]
Reader = Annotated[Principal, Depends(require_permission("settings.manage"))]


class SettingResponse(BaseModel):
    key: str
    value: dict
    is_secret: bool
    updated_at: datetime | None


class SettingUpsertRequest(BaseModel):
    key: str = Field(min_length=1, max_length=150)
    value: dict = Field(default_factory=dict)
    is_secret: bool = False


class OrganisationSettingsPayload(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    external_apis_allowed: bool | None = None
    local_only_enforced: bool | None = None


class StructuredSettingsRequest(BaseModel):
    organisation: OrganisationSettingsPayload | None = None
    upload: dict | None = None
    queue: dict | None = None
    ai: dict | None = None


class StructuredSettingsResponse(BaseModel):
    organisation: dict
    upload: dict
    queue: dict
    ai: dict


def _setting_to_response(item: SystemSetting) -> SettingResponse:
    return SettingResponse(
        key=item.key, value=item.value, is_secret=item.is_secret, updated_at=item.updated_at
    )


@router.get("", response_model=list[SettingResponse])
def list_settings(principal: Reader, db: DbSession):
    rows = list(
        db.scalars(
            select(SystemSetting)
            .where(
                (SystemSetting.organisation_id == principal.organisation.id)
                | SystemSetting.organisation_id.is_(None)
            )
            .order_by(SystemSetting.key)
        )
    )
    return [_setting_to_response(row) for row in rows]


@router.get("/structured", response_model=StructuredSettingsResponse)
def get_structured_settings(principal: Reader, db: DbSession) -> StructuredSettingsResponse:
    return _structured_response(db, principal.organisation)


@router.put("/structured", response_model=StructuredSettingsResponse)
def update_structured_settings(
    payload: StructuredSettingsRequest, request: Request, principal: Manager, db: DbSession
) -> StructuredSettingsResponse:
    if payload.organisation is not None:
        organisation_patch = payload.organisation.model_dump(exclude_unset=True)
        for field, value in organisation_patch.items():
            setattr(principal.organisation, field, value)
    for key in ("upload", "queue", "ai"):
        value = getattr(payload, key)
        if value is not None:
            _upsert_setting(db, principal, key, value, is_secret=False)
    write_audit(
        db,
        principal,
        "settings.structured.updated",
        "setting",
        None,
        "success",
        request,
        {"keys": [key for key in ("upload", "queue", "ai") if getattr(payload, key) is not None]},
    )
    db.commit()
    db.refresh(principal.organisation)
    return _structured_response(db, principal.organisation)


@router.put("", response_model=SettingResponse)
def upsert_setting(payload: SettingUpsertRequest, request: Request, principal: Manager, db: DbSession):
    if payload.is_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Secret settings must use dedicated encrypted provider secret endpoints",
        )
    item = _upsert_setting(db, principal, payload.key, payload.value, payload.is_secret)
    write_audit(db, principal, "setting.upserted", "setting", None, "success", request, {"key": payload.key})
    db.commit()
    db.refresh(item)
    return _setting_to_response(item)


def _upsert_setting(
    db: Session, principal: Principal, key: str, value: dict, is_secret: bool
) -> SystemSetting:
    item = db.scalar(
        select(SystemSetting).where(
            SystemSetting.organisation_id == principal.organisation.id, SystemSetting.key == key
        )
    )
    if item is None:
        item = SystemSetting(
            organisation_id=principal.organisation.id,
            key=key,
            value=value,
            is_secret=is_secret,
            updated_by_id=principal.user.id,
        )
        db.add(item)
    else:
        item.value = value
        item.is_secret = is_secret
        item.updated_by_id = principal.user.id
    return item


@router.delete("/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting(key: str, request: Request, principal: Manager, db: DbSession):
    item = db.scalar(
        select(SystemSetting).where(
            SystemSetting.organisation_id == principal.organisation.id, SystemSetting.key == key
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    write_audit(db, principal, "setting.deleted", "setting", None, "success", request, {"key": key})
    db.delete(item)
    db.commit()


def _structured_response(db: Session, organisation: Organisation) -> StructuredSettingsResponse:
    return StructuredSettingsResponse(
        organisation={
            "id": str(organisation.id),
            "name": organisation.name,
            "retention_days": organisation.retention_days,
            "external_apis_allowed": organisation.external_apis_allowed,
            "local_only_enforced": organisation.local_only_enforced,
        },
        upload=_setting_value(db, organisation, "upload", {"max_upload_bytes": None}),
        queue=_setting_value(db, organisation, "queue", {"max_concurrent_jobs": None}),
        ai=_setting_value(db, organisation, "ai", {"default_report_template_kind": None}),
    )


def _setting_value(db: Session, organisation: Organisation, key: str, default: dict) -> dict:
    item = db.scalar(
        select(SystemSetting).where(
            SystemSetting.organisation_id == organisation.id,
            SystemSetting.key == key,
        )
    )
    return item.value if item is not None else default
