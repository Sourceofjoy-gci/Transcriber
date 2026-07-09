from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import AssetStatus, MediaDerivativeKind, MediaDerivativeStatus


class AssetMetadataResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    duration_ms: int | None
    container: str | None
    audio_codec: str | None
    video_codec: str | None
    sample_rate_hz: int | None
    channels: int | None
    bit_rate: int | None


class AssetResponse(BaseModel):
    id: UUID
    project_id: UUID | None
    original_filename: str
    content_type: str
    byte_size: int
    sha256: str
    status: AssetStatus
    failure_code: str | None
    failure_message: str | None
    created_at: datetime
    metadata: AssetMetadataResponse | None = None


class AssetListResponse(BaseModel):
    items: list[AssetResponse]
    next_offset: int | None


class MediaDerivativeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: UUID
    asset_id: UUID
    kind: MediaDerivativeKind
    status: MediaDerivativeStatus
    content_type: str | None
    byte_size: int
    metadata: dict = Field(validation_alias="derivative_metadata")
    failure_message: str | None
    created_at: datetime
    updated_at: datetime


class MediaDerivativeListResponse(BaseModel):
    items: list[MediaDerivativeResponse]


class AssetDownloadUrlResponse(BaseModel):
    url: str
    method: str = "GET"
    expires_at: datetime
    headers: dict[str, str] = Field(default_factory=dict)


class StorageOverviewResponse(BaseModel):
    provider: str
    healthy: bool
    storage_bytes: int
    original_bytes: int
    derivative_bytes: int
    active_assets: int
    deleted_assets: int
    legal_hold_assets: int
    retention_days: int | None


class StoragePurgeResponse(BaseModel):
    status: str
    purged_assets: int
    deleted_objects: int


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    sensitivity: str = Field(default="standard", pattern="^(standard|sensitive|restricted)$")
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    external_apis_allowed: bool | None = None


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    sensitivity: str | None = Field(default=None, pattern="^(standard|sensitive|restricted)$")
    retention_days: int | None = Field(default=None, ge=1, le=36500)
    external_apis_allowed: bool | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    sensitivity: str
    retention_days: int | None
    external_apis_allowed: bool | None
    created_at: datetime
