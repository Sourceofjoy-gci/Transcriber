from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import JobStatus


class TranscriptionJobCreateRequest(BaseModel):
    asset_id: UUID
    execution_target_kind: str = Field(default="automatic", pattern="^(automatic|local_model|api_provider)$")
    execution_target_id: UUID | None = None
    egress_acknowledged: bool = False
    language: str | None = Field(default=None, min_length=2, max_length=20)
    options: dict = Field(default_factory=dict)


def normalize_job_options(options: dict | None) -> dict:
    normalized = dict(options or {})
    diarization = normalized.get("diarization")
    if diarization in (None, False):
        normalized.pop("diarization", None)
        return normalized
    if diarization is True:
        diarization = {"enabled": True}
    if not isinstance(diarization, dict):
        raise ValueError("Diarization options must be an object")

    enabled = bool(diarization.get("enabled", True))
    if not enabled:
        normalized["diarization"] = {"enabled": False}
        return normalized

    provider = str(diarization.get("provider") or "local_turns").strip()
    if provider != "local_turns":
        raise ValueError("Unsupported diarization provider")

    speaker_count = diarization.get("speaker_count", 2)
    if not isinstance(speaker_count, int) or not 1 <= speaker_count <= 20:
        raise ValueError("Speaker count must be between 1 and 20")

    turn_length_ms = diarization.get("turn_length_ms", 30_000)
    if not isinstance(turn_length_ms, int) or not 1_000 <= turn_length_ms <= 600_000:
        raise ValueError("Turn length must be between 1000 and 600000 milliseconds")

    normalized["diarization"] = {
        "enabled": True,
        "provider": provider,
        "speaker_count": speaker_count,
        "turn_length_ms": turn_length_ms,
    }
    return normalized


class JobEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    state: JobStatus
    progress_percent: int
    message: str
    data: dict
    created_at: datetime


class JobAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    attempt_number: int
    status: JobStatus
    started_at: datetime | None
    finished_at: datetime | None
    error_detail: str | None


class TranscriptionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    asset_id: UUID
    status: JobStatus
    progress_percent: int
    execution_target_kind: str
    execution_target_id: UUID | None
    language: str | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobDetailResponse(TranscriptionJobResponse):
    events: list[JobEventResponse]
