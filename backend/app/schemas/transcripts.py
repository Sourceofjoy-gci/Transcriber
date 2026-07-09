from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import ExportStatus, TranscriptStatus


class TranscriptVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version_number: int
    source: str
    change_summary: str | None
    created_at: datetime


class VersionRestoreRequest(BaseModel):
    version_id: UUID
    base_version_id: UUID | None = None


class SpeakerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    label: str
    display_name: str | None
    role: str | None
    color: str | None


class TranscriptSegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    start_ms: int
    end_ms: int
    text: str
    confidence: str | None
    is_unclear: bool
    notes: str | None
    speaker_id: UUID | None
    speaker_label: str | None = None
    word_count: int = 0


class SegmentEditRequest(BaseModel):
    base_version_id: UUID | None = None
    text: str = Field(min_length=1, max_length=50000)
    notes: str | None = Field(default=None, max_length=5000)
    is_unclear: bool | None = None
    change_summary: str | None = Field(default=None, max_length=500)


class SegmentBatchEditItem(BaseModel):
    segment_id: UUID
    text: str | None = Field(default=None, min_length=1, max_length=50000)
    notes: str | None = Field(default=None, max_length=5000)
    is_unclear: bool | None = None
    speaker_id: UUID | None = None


class SegmentBatchEditRequest(BaseModel):
    base_version_id: UUID | None = None
    edits: list[SegmentBatchEditItem] = Field(min_length=1, max_length=200)
    change_summary: str | None = Field(default=None, max_length=500)


class SegmentSpeakerRequest(BaseModel):
    base_version_id: UUID | None = None
    speaker_id: UUID | None = None


class SpeakerRequest(BaseModel):
    label: str = Field(min_length=1, max_length=100)
    display_name: str | None = Field(default=None, max_length=150)
    role: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=20)


class SpeakerUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=150)
    role: str | None = Field(default=None, max_length=100)
    color: str | None = Field(default=None, max_length=20)


class SplitSegmentRequest(BaseModel):
    base_version_id: UUID | None = None
    segment_id: UUID | None = None
    split_at_ms: int = Field(ge=0)


class MergeSegmentsRequest(BaseModel):
    base_version_id: UUID | None = None
    first_segment_id: UUID
    second_segment_id: UUID


class AnnotationRequest(BaseModel):
    base_version_id: UUID | None = None
    segment_id: UUID
    note: str | None = Field(default=None, max_length=5000)
    is_unclear: bool | None = None


class SearchReplaceRequest(BaseModel):
    base_version_id: UUID | None = None
    query: str = Field(min_length=1, max_length=500)
    replacement: str = Field(default="", max_length=5000)
    replace_all: bool = True
    case_sensitive: bool = False


class OperationCheckpointRequest(BaseModel):
    base_version_id: UUID | None = None


class SearchHit(BaseModel):
    segment_id: UUID
    sequence: int
    start_ms: int
    end_ms: int
    snippet: str


class SearchResponse(BaseModel):
    query: str
    hits: list[SearchHit]


class TranscriptResponse(BaseModel):
    id: UUID
    job_id: UUID
    asset_id: UUID | None
    language: str | None
    detected_language: str | None
    source_provider: str
    status: TranscriptStatus
    active_version: TranscriptVersionResponse | None
    created_at: datetime


class TranscriptDetailResponse(TranscriptResponse):
    segments: list[TranscriptSegmentResponse]


class SearchReplaceResponse(BaseModel):
    transcript: TranscriptDetailResponse
    replacement_count: int


class ExportCreateRequest(BaseModel):
    source_type: str = Field(default="transcript", pattern="^(transcript|report)$")
    transcript_id: UUID | None = None
    report_id: UUID | None = None
    segment_ids: list[UUID] = Field(default_factory=list)
    format: str = Field(pattern="^(txt|json|srt|vtt|csv|md|html|docx|pdf)$")
    options: dict = Field(default_factory=dict)


class ExportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transcript_version_id: UUID
    format: str
    status: ExportStatus
    error_message: str | None
    created_at: datetime
    expires_at: datetime | None
