
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym

from app.db.base import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class MembershipStatus(StrEnum):
    active = "active"
    invited = "invited"
    suspended = "suspended"


class AssetStatus(StrEnum):
    uploaded = "uploaded"
    processing_metadata = "processing_metadata"
    ready = "ready"
    processing = "processing"
    failed = "failed"
    deleted = "deleted"


class JobStatus(StrEnum):
    queued = "queued"
    uploading = "uploading"
    extracting_audio = "extracting_audio"
    preprocessing = "preprocessing"
    transcribing = "transcribing"
    post_processing = "post_processing"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class TranscriptStatus(StrEnum):
    draft = "draft"
    ready = "ready"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ExportStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    expired = "expired"


class ModelInstallStatus(StrEnum):
    queued = "queued"
    downloading = "downloading"
    installed = "installed"
    failed = "failed"
    deleting = "deleting"


class MediaDerivativeKind(StrEnum):
    normalized_audio = "normalized_audio"
    waveform = "waveform"
    thumbnail = "thumbnail"
    chunk = "chunk"


class MediaDerivativeStatus(StrEnum):
    queued = "queued"
    processing = "processing"
    ready = "ready"
    failed = "failed"
    deleted = "deleted"


def enum_column(enum_cls, default=None, nullable=False):
    return mapped_column(
        SAEnum(enum_cls, values_callable=lambda cls: [item.value for item in cls], native_enum=False),
        default=default,
        nullable=nullable,
    )


role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=False
    )


class Organisation(TimestampMixin, Base):
    __tablename__ = "organisations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    external_apis_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_only_enforced: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Role(TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organisation_id", "code", name="uq_roles_org_code"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, back_populates="roles")


class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    roles: Mapped[list[Role]] = relationship(secondary=role_permissions, back_populates="permissions")


class OrganisationMembership(TimestampMixin, Base):
    __tablename__ = "organisation_memberships"
    __table_args__ = (UniqueConstraint("organisation_id", "user_id", name="uq_membership_org_user"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False)
    status: Mapped[MembershipStatus] = enum_column(MembershipStatus, MembershipStatus.active)
    organisation: Mapped[Organisation] = relationship()
    user: Mapped[User] = relationship()
    role: Mapped[Role] = relationship()


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    sensitivity: Mapped[str] = mapped_column(String(50), default="standard", nullable=False)
    retention_days: Mapped[int | None] = mapped_column(Integer)
    external_apis_allowed: Mapped[bool | None] = mapped_column(Boolean)
    organisation: Mapped[Organisation] = relationship()


class MediaAsset(TimestampMixin, Base):
    __tablename__ = "media_assets"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"))
    uploaded_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[AssetStatus] = enum_column(AssetStatus, AssetStatus.uploaded)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    legal_hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organisation: Mapped[Organisation] = relationship()
    project: Mapped[Project | None] = relationship()
    uploaded_by: Mapped[User | None] = relationship()
    media_metadata: Mapped[MediaMetadata | None] = relationship(back_populates="asset", uselist=False)
    derivatives: Mapped[list[MediaDerivative]] = relationship(back_populates="asset")


class MediaMetadata(Base):
    __tablename__ = "media_metadata"

    asset_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("media_assets.id"), primary_key=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    container: Mapped[str | None] = mapped_column(String(100))
    audio_codec: Mapped[str | None] = mapped_column(String(100))
    video_codec: Mapped[str | None] = mapped_column(String(100))
    sample_rate_hz: Mapped[int | None] = mapped_column(Integer)
    channels: Mapped[int | None] = mapped_column(Integer)
    bit_rate: Mapped[int | None] = mapped_column(Integer)
    asset: Mapped[MediaAsset] = relationship(back_populates="media_metadata")


class MediaDerivative(TimestampMixin, Base):
    __tablename__ = "media_derivatives"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("media_assets.id"), nullable=False)
    kind: Mapped[MediaDerivativeKind] = enum_column(MediaDerivativeKind, MediaDerivativeKind.normalized_audio)
    status: Mapped[MediaDerivativeStatus] = enum_column(MediaDerivativeStatus, MediaDerivativeStatus.queued)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    sha256: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(200))
    byte_size: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    failure_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    asset: Mapped[MediaAsset] = relationship(back_populates="derivatives")

    @property
    def derivative_metadata(self) -> dict:
        return self.metadata_json or {}

    @derivative_metadata.setter
    def derivative_metadata(self, value: dict) -> None:
        self.metadata_json = value or {}


class TranscriptionJob(TimestampMixin, Base):
    __tablename__ = "transcription_jobs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False)
    asset_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("media_assets.id"), nullable=False)
    requested_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    execution_target_kind: Mapped[str] = mapped_column(String(50), default="automatic", nullable=False)
    execution_target_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[JobStatus] = enum_column(JobStatus, JobStatus.queued)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    options_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    processing_ms: Mapped[int | None] = mapped_column(Integer)
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(12, 6))
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    asset: Mapped[MediaAsset] = relationship()
    requested_by: Mapped[User | None] = relationship()


class JobAttempt(Base):
    __tablename__ = "job_attempts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcription_jobs.id"), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[JobStatus] = enum_column(JobStatus, JobStatus.queued)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_detail: Mapped[str | None] = mapped_column(Text)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    job: Mapped[TranscriptionJob] = relationship()


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcription_jobs.id"), nullable=False)
    attempt_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("job_attempts.id"))
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[JobStatus] = enum_column(JobStatus, JobStatus.queued)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message: Mapped[str] = mapped_column(Text, default="", nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    job: Mapped[TranscriptionJob] = relationship()
    attempt: Mapped[JobAttempt | None] = relationship()

    @property
    def data(self) -> dict:
        return self.metadata_json or {}

    @data.setter
    def data(self, value: dict) -> None:
        self.metadata_json = value or {}


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("refresh_tokens.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    user: Mapped[User] = relationship(foreign_keys=[user_id])


class SystemSetting(TimestampMixin, Base):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("organisation_id", "key", name="uq_system_settings_org_key"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    key: Mapped[str] = mapped_column(String(200), nullable=False)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    actor_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(100))
    outcome: Mapped[str] = mapped_column(String(50), default="success", nullable=False)
    ip_hash: Mapped[str | None] = mapped_column(String(128))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)

    @property
    def data(self) -> dict:
        return self.metadata_json or {}

    @data.setter
    def data(self, value: dict) -> None:
        self.metadata_json = value or {}


class Transcript(TimestampMixin, Base):
    __tablename__ = "transcripts"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcription_jobs.id"), nullable=False)
    language: Mapped[str | None] = mapped_column(String(20))
    detected_language: Mapped[str | None] = mapped_column(String(20))
    source_provider: Mapped[str] = mapped_column(String(100), default="unknown", nullable=False)
    active_version_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"))
    status: Mapped[TranscriptStatus] = enum_column(TranscriptStatus, TranscriptStatus.draft)
    job: Mapped[TranscriptionJob] = relationship()
    active_version: Mapped[TranscriptVersion | None] = relationship(foreign_keys=[active_version_id])


class TranscriptVersion(Base):
    __tablename__ = "transcript_versions"
    __table_args__ = (UniqueConstraint("transcript_id", "version_number", name="uq_transcript_version_number"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    transcript_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcripts.id"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"))
    created_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    source: Mapped[str] = mapped_column(String(100), default="system", nullable=False)
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    change_summary: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    transcript: Mapped[Transcript] = relationship(foreign_keys=[transcript_id])
    parent_version: Mapped[TranscriptVersion | None] = relationship(remote_side=[id])


class Speaker(TimestampMixin, Base):
    __tablename__ = "speakers"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    transcript_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcripts.id"), nullable=False)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(150))
    role: Mapped[str | None] = mapped_column(String(100))
    color: Mapped[str | None] = mapped_column(String(20))


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (UniqueConstraint("version_id", "sequence", name="uq_segment_version_sequence"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("speakers.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(50))
    is_unclear: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    version: Mapped[TranscriptVersion] = relationship()
    speaker: Mapped[Speaker | None] = relationship()


class TranscriptWord(Base):
    __tablename__ = "transcript_words"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    segment_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_segments.id"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    word: Mapped[str] = mapped_column(String(500), nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(50))
    segment: Mapped[TranscriptSegment] = relationship()


class ExportRecord(TimestampMixin, Base):
    __tablename__ = "export_records"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    requested_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    transcript_version_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"))
    report_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("reports.id"))
    source_type: Mapped[str] = mapped_column(String(50), default="transcript", nullable=False)
    source_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    format: Mapped[str] = mapped_column(String(20), nullable=False)
    options_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ExportStatus] = enum_column(ExportStatus, ExportStatus.queued)
    error_message: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelCatalog(TimestampMixin, Base):
    __tablename__ = "model_catalog"
    __table_args__ = (UniqueConstraint("adapter_key", "model_identifier", name="uq_model_catalog_adapter_identifier"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    model_identifier: Mapped[str] = mapped_column(String(300), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    model_type: Mapped[str] = mapped_column(String(100), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(1000))
    revision: Mapped[str | None] = mapped_column(String(200))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    requirements_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(200))

    @property
    def requirements(self) -> dict:
        return self.requirements_json or {}

    @requirements.setter
    def requirements(self, value: dict) -> None:
        self.requirements_json = value or {}

    @property
    def capabilities(self) -> dict:
        return self.capabilities_json or {}

    @capabilities.setter
    def capabilities(self, value: dict) -> None:
        self.capabilities_json = value or {}


class InstalledModel(TimestampMixin, Base):
    __tablename__ = "installed_models"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    catalog_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("model_catalog.id"), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[ModelInstallStatus] = enum_column(ModelInstallStatus, ModelInstallStatus.queued)
    download_progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    hardware_compatibility_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text)
    catalog: Mapped[ModelCatalog] = relationship()

    @property
    def hardware_compatibility(self) -> dict:
        return self.hardware_compatibility_json or {}

    @hardware_compatibility.setter
    def hardware_compatibility(self, value: dict) -> None:
        self.hardware_compatibility_json = value or {}


class ModelTaskDefault(TimestampMixin, Base):
    __tablename__ = "model_task_defaults"
    __table_args__ = (UniqueConstraint("organisation_id", "task", name="uq_model_task_default_org_task"),)

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"), nullable=False)
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    installed_model_id: Mapped[UUID] = mapped_column("execution_target_id", UUID(as_uuid=True), nullable=False)
    execution_target_id = synonym("installed_model_id")
    updated_by_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))


class ProviderDefinition(TimestampMixin, Base):
    __tablename__ = "provider_definitions"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    adapter_key: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(1000))
    endpoint_path: Mapped[str] = mapped_column(String(500), default="/audio/transcriptions", nullable=False)
    model_name: Mapped[str | None] = mapped_column(String(300))
    auth_type: Mapped[str] = mapped_column(String(100), default="none", nullable=False)
    headers_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    retry_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
    secrets: Mapped[list[ProviderSecret]] = relationship(back_populates="provider")

    @property
    def headers(self) -> dict:
        return self.headers_json or {}

    @headers.setter
    def headers(self, value: dict) -> None:
        self.headers_json = value or {}

    @property
    def capabilities(self) -> dict:
        return self.capabilities_json or {}

    @capabilities.setter
    def capabilities(self, value: dict) -> None:
        self.capabilities_json = value or {}


class ProviderSecret(Base):
    __tablename__ = "provider_secrets"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("provider_definitions.id"), nullable=False)
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    nonce: Mapped[str] = mapped_column(String(200), nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    rotated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)
    provider: Mapped[ProviderDefinition] = relationship(back_populates="secrets")


class ProviderUsageLog(Base):
    __tablename__ = "provider_usage_logs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    provider_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("provider_definitions.id"), nullable=False)
    job_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcription_jobs.id"))
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(200))
    input_units: Mapped[int | None] = mapped_column(Integer)
    output_units: Mapped[int | None] = mapped_column(Integer)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(12, 6))
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class AIProcessingRun(TimestampMixin, Base):
    __tablename__ = "ai_processing_runs"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    transcript_version_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"), nullable=False)
    task: Mapped[str] = mapped_column(String(100), nullable=False)
    execution_target_kind: Mapped[str] = mapped_column(String(50), default="automatic", nullable=False)
    execution_target_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True))
    options_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="queued", nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    output_version_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"))
    cost_estimate: Mapped[float | None] = mapped_column(Numeric(12, 6))
    error_message: Mapped[str | None] = mapped_column(Text)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    progress_message: Mapped[str | None] = mapped_column(String(500))
    cancel_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportTemplate(TimestampMixin, Base):
    __tablename__ = "report_templates"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    organisation_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("organisations.id"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    prompt_template: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    @property
    def schema(self) -> dict:
        return self.schema_json or {}

    @schema.setter
    def schema(self, value: dict) -> None:
        self.schema_json = value or {}


class Report(TimestampMixin, Base):
    __tablename__ = "reports"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    transcript_version_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"), nullable=False)
    template_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("report_templates.id"), nullable=False)
    processing_run_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("ai_processing_runs.id"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_markdown: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(50), default="ready", nullable=False)
    template: Mapped[ReportTemplate] = relationship()


class TranscriptEditOperation(Base):
    __tablename__ = "transcript_edit_operations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    operation_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, nullable=False)


class TranscriptAnnotation(TimestampMixin, Base):
    __tablename__ = "transcript_annotations"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_versions.id"), nullable=False)
    segment_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("transcript_segments.id"))
    author_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)
