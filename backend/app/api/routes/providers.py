import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.domain import ProviderDefinition, ProviderSecret, ProviderUsageLog
from app.providers.external import ExternalProviderError, test_connection
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.provider_secrets import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/api-providers", tags=["API providers"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ProviderManager = Annotated[Principal, Depends(require_permission("providers.manage"))]


class ProviderInput(BaseModel):
    adapter_key: str = Field(pattern="^(openai_compatible|generic_rest_transcription)$")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(default="transcription", max_length=100)
    base_url: str | None = Field(default=None, max_length=1000)
    endpoint_path: str = Field(default="/audio/transcriptions", pattern="^/")
    model_name: str | None = Field(default=None, max_length=300)
    auth_type: str = Field(default="bearer", pattern="^(bearer|api_key|none)$")
    headers: dict = Field(default_factory=dict)
    capabilities: dict = Field(default_factory=dict)
    timeout_seconds: int = Field(default=120, ge=5, le=600)
    retry_limit: int = Field(default=2, ge=0, le=5)
    api_key: str | None = Field(default=None, min_length=1, max_length=10000)


class ProviderResponse(BaseModel):
    id: uuid.UUID
    adapter_key: str
    name: str
    category: str
    base_url: str | None
    endpoint_path: str
    model_name: str | None
    auth_type: str
    headers: dict
    capabilities: dict
    enabled: bool
    is_default: bool
    secret_configured: bool
    timeout_seconds: int
    retry_limit: int
    last_tested_at: datetime | None
    last_error: str | None


class ProviderUsageCallResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID | None
    task: str
    status: str
    duration_ms: int | None
    estimated_cost: str | None
    error_code: str | None
    created_at: datetime


class ProviderUsageResponse(BaseModel):
    provider_id: uuid.UUID
    total_calls: int
    successful_calls: int
    failed_calls: int
    total_duration_ms: int
    estimated_cost_usd: float
    recent_calls: list[ProviderUsageCallResponse]


class RotateSecretRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=10000)


@router.get("", response_model=list[ProviderResponse])
def list_providers(principal: ProviderManager, db: DbSession):
    return [
        _response(db, provider)
        for provider in db.scalars(
            select(ProviderDefinition).where(ProviderDefinition.organisation_id == principal.organisation.id)
        )
    ]


@router.post("", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderInput,
    request: Request,
    principal: ProviderManager,
    db: DbSession,
    settings: SettingsDependency,
):
    provider = ProviderDefinition(
        organisation_id=principal.organisation.id, **payload.model_dump(exclude={"api_key"})
    )
    db.add(provider)
    db.flush()
    if payload.api_key:
        ciphertext, nonce = encrypt_secret(settings, payload.api_key)
        db.add(
            ProviderSecret(
                provider_id=provider.id,
                ciphertext=ciphertext,
                nonce=nonce,
                key_version=settings.credential_key_version,
            )
        )
    write_audit(
        db,
        principal,
        "provider.created",
        "provider",
        provider.id,
        "success",
        request,
        {"adapter_key": provider.adapter_key},
    )
    db.commit()
    return _response(db, provider)


@router.get("/{provider_id}", response_model=ProviderResponse)
def get_provider(provider_id: uuid.UUID, principal: ProviderManager, db: DbSession):
    return _response(db, _provider(db, principal, provider_id))


@router.post("/{provider_id}/enable", response_model=ProviderResponse)
def enable_provider(provider_id: uuid.UUID, request: Request, principal: ProviderManager, db: DbSession):
    provider = _provider(db, principal, provider_id)
    provider.enabled = True
    write_audit(db, principal, "provider.enabled", "provider", provider.id, "success", request)
    db.commit()
    return _response(db, provider)


@router.post("/{provider_id}/disable", response_model=ProviderResponse)
def disable_provider(provider_id: uuid.UUID, request: Request, principal: ProviderManager, db: DbSession):
    provider = _provider(db, principal, provider_id)
    provider.enabled = False
    write_audit(db, principal, "provider.disabled", "provider", provider.id, "success", request)
    db.commit()
    return _response(db, provider)


@router.patch("/{provider_id}", response_model=ProviderResponse)
def update_provider(
    provider_id: uuid.UUID,
    payload: ProviderInput,
    request: Request,
    principal: ProviderManager,
    db: DbSession,
    settings: SettingsDependency,
):
    provider = _provider(db, principal, provider_id)
    for key, value in payload.model_dump(exclude={"api_key"}).items():
        setattr(provider, key, value)
    if payload.api_key:
        secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
        ciphertext, nonce = encrypt_secret(settings, payload.api_key)
        if secret is None:
            db.add(
                ProviderSecret(
                    provider_id=provider.id,
                    ciphertext=ciphertext,
                    nonce=nonce,
                    key_version=settings.credential_key_version,
                )
            )
        else:
            secret.ciphertext, secret.nonce, secret.key_version = (
                ciphertext,
                nonce,
                settings.credential_key_version,
            )
    write_audit(db, principal, "provider.updated", "provider", provider.id, "success", request)
    db.commit()
    return _response(db, provider)


@router.post("/{provider_id}/test", response_model=ProviderResponse)
def test_provider(
    provider_id: uuid.UUID,
    request: Request,
    principal: ProviderManager,
    db: DbSession,
    settings: SettingsDependency,
):
    provider = _provider(db, principal, provider_id)
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    api_key = decrypt_secret(settings, secret.ciphertext, secret.nonce) if secret else None
    redacted_error: str | None = None
    try:
        test_connection(provider, api_key)
    except ExternalProviderError as error:
        redacted_error = _redact_provider_error(str(error))
    except RuntimeError as error:
        redacted_error = _redact_provider_error(str(error))
    provider.last_error = redacted_error
    provider.last_tested_at = datetime.now(UTC)
    write_audit(
        db,
        principal,
        "provider.tested",
        "provider",
        provider.id,
        "success" if redacted_error is None else "failure",
        request,
        {"redacted_error": redacted_error},
    )
    db.commit()
    return _response(db, provider)


@router.post("/{provider_id}/rotate-secret", response_model=ProviderResponse)
def rotate_provider_secret(
    provider_id: uuid.UUID,
    payload: RotateSecretRequest,
    request: Request,
    principal: ProviderManager,
    db: DbSession,
    settings: SettingsDependency,
):
    provider = _provider(db, principal, provider_id)
    ciphertext, nonce = encrypt_secret(settings, payload.api_key)
    secret = db.scalar(select(ProviderSecret).where(ProviderSecret.provider_id == provider.id))
    if secret is None:
        db.add(
            ProviderSecret(
                provider_id=provider.id,
                ciphertext=ciphertext,
                nonce=nonce,
                key_version=settings.credential_key_version,
            )
        )
    else:
        secret.ciphertext, secret.nonce, secret.key_version = (
            ciphertext,
            nonce,
            settings.credential_key_version,
        )
    provider.last_error = None
    write_audit(db, principal, "provider.secret_rotated", "provider", provider.id, "success", request)
    db.commit()
    return _response(db, provider)


@router.post("/{provider_id}/default", response_model=ProviderResponse)
def default_provider(provider_id: uuid.UUID, request: Request, principal: ProviderManager, db: DbSession):
    provider = _provider(db, principal, provider_id)
    if not provider.enabled:
        raise HTTPException(status_code=409, detail="Provider must be enabled before it can be the default")
    for item in db.scalars(
        select(ProviderDefinition).where(ProviderDefinition.organisation_id == principal.organisation.id)
    ):
        item.is_default = item.id == provider.id
    write_audit(db, principal, "provider.default_set", "provider", provider.id, "success", request)
    db.commit()
    return _response(db, provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: uuid.UUID, request: Request, principal: ProviderManager, db: DbSession):
    provider = _provider(db, principal, provider_id)
    write_audit(db, principal, "provider.deleted", "provider", provider.id, "success", request)
    db.delete(provider)
    db.commit()


@router.get("/{provider_id}/usage", response_model=ProviderUsageResponse)
def provider_usage(
    provider_id: uuid.UUID, principal: ProviderManager, db: DbSession
) -> ProviderUsageResponse:
    _provider(db, principal, provider_id)
    rows = list(
        db.scalars(
            select(ProviderUsageLog)
            .where(ProviderUsageLog.provider_id == provider_id)
            .order_by(ProviderUsageLog.created_at.desc())
            .limit(100)
        )
    )
    successful_statuses = {"success", "completed"}
    successful_calls = sum(1 for item in rows if item.status in successful_statuses)
    failed_calls = len(rows) - successful_calls
    total_duration_ms = sum(item.duration_ms or 0 for item in rows)
    estimated_cost_usd = 0.0
    for item in rows:
        if item.estimated_cost is None:
            continue
        try:
            estimated_cost_usd += float(item.estimated_cost)
        except (TypeError, ValueError):
            continue
    return ProviderUsageResponse(
        provider_id=provider_id,
        total_calls=len(rows),
        successful_calls=successful_calls,
        failed_calls=failed_calls,
        total_duration_ms=total_duration_ms,
        estimated_cost_usd=round(estimated_cost_usd, 6),
        recent_calls=[
            ProviderUsageCallResponse(
                id=item.id,
                job_id=item.job_id,
                task=item.task,
                status=item.status,
                duration_ms=item.duration_ms,
                estimated_cost=item.estimated_cost,
                error_code=item.error_code,
                created_at=item.created_at,
            )
            for item in rows
        ],
    )


def _provider(db, principal, provider_id):
    provider = db.scalar(
        select(ProviderDefinition).where(
            ProviderDefinition.id == provider_id,
            ProviderDefinition.organisation_id == principal.organisation.id,
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _response(db, provider):
    return ProviderResponse(
        id=provider.id,
        adapter_key=provider.adapter_key,
        name=provider.name,
        category=provider.category,
        base_url=provider.base_url,
        endpoint_path=provider.endpoint_path,
        model_name=provider.model_name,
        auth_type=provider.auth_type,
        headers=provider.headers,
        capabilities=provider.capabilities,
        enabled=provider.enabled,
        is_default=provider.is_default,
        secret_configured=db.scalar(
            select(ProviderSecret.id).where(ProviderSecret.provider_id == provider.id)
        )
        is not None,
        timeout_seconds=provider.timeout_seconds,
        retry_limit=provider.retry_limit,
        last_tested_at=provider.last_tested_at,
        last_error=provider.last_error,
    )


def _redact_provider_error(message: str) -> str:
    """Return a short, redacted error label that does not leak credentials."""
    lowered = message.lower()
    if "credential" in lowered:
        return "Provider is missing or has an invalid credential"
    if "private" in lowered or "https" in lowered:
        return "Provider URL is not reachable or is not allowed"
    if "invalid" in lowered:
        return "Provider configuration is invalid"
    return "Provider connection test failed"
