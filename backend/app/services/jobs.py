import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.domain import (
    AssetStatus,
    InstalledModel,
    JobEvent,
    JobStatus,
    MediaAsset,
    ModelInstallStatus,
    Project,
    ProviderDefinition,
    ProviderSecret,
    TranscriptionJob,
)
from app.schemas.jobs import TranscriptionJobCreateRequest, normalize_job_options
from app.services.authorization import Principal


class JobService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, principal: Principal, payload: TranscriptionJobCreateRequest) -> TranscriptionJob:
        try:
            options = normalize_job_options(payload.options)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
            ) from error
        asset = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.id == payload.asset_id,
                MediaAsset.organisation_id == principal.organisation.id,
                MediaAsset.deleted_at.is_(None),
            )
        )
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media asset not found")
        if asset.status != AssetStatus.ready:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Media metadata must be ready before transcription",
            )
        if payload.execution_target_kind == "api_provider":
            self._validate_api_provider_target(principal, asset, payload)
        elif payload.execution_target_kind == "local_model":
            self._validate_local_model_target(principal, payload.execution_target_id)

        job = TranscriptionJob(
            organisation_id=principal.organisation.id,
            asset_id=asset.id,
            requested_by_id=principal.user.id,
            execution_target_kind=payload.execution_target_kind,
            execution_target_id=payload.execution_target_id,
            status=JobStatus.queued,
            language=payload.language,
            options=options,
        )
        self.db.add(job)
        self.db.flush()
        self.add_event(job, JobStatus.queued, 0, "Job queued for provider resolution")
        return job

    def _validate_local_model_target(self, principal: Principal, model_id: uuid.UUID | None) -> None:
        if model_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A selected local model is required",
            )
        model = self.db.scalar(
            select(InstalledModel).where(
                InstalledModel.id == model_id,
                InstalledModel.organisation_id == principal.organisation.id,
            )
        )
        if model is None or model.status != ModelInstallStatus.installed or not model.enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected local model must be installed and enabled",
            )

    def _validate_api_provider_target(
        self,
        principal: Principal,
        asset: MediaAsset,
        payload: TranscriptionJobCreateRequest,
    ) -> None:
        if not payload.egress_acknowledged:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="External API jobs require explicit egress acknowledgement",
            )
        self._validate_external_api_policy(principal, asset)
        if payload.execution_target_id is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="A selected API provider is required",
            )
        provider = self.db.scalar(
            select(ProviderDefinition).where(
                ProviderDefinition.id == payload.execution_target_id,
                ProviderDefinition.organisation_id == principal.organisation.id,
            )
        )
        if provider is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API provider not found")
        if not provider.enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected API provider must be enabled",
            )
        if provider.category != "transcription":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected API provider does not support transcription",
            )
        if not (provider.model_name or "").strip():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected API provider must define a model name",
            )
        if not _capabilities_support_transcription(provider.capabilities):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected API provider does not support transcription",
            )
        if provider.auth_type != "none":
            secret_id = self.db.scalar(
                select(ProviderSecret.id).where(ProviderSecret.provider_id == provider.id)
            )
            if secret_id is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Selected API provider must have a configured credential",
                )

    def _validate_external_api_policy(self, principal: Principal, asset: MediaAsset) -> None:
        if principal.organisation.local_only_enforced or not principal.organisation.external_apis_allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="External API processing is disabled by policy",
            )
        if asset.project_id is None:
            return
        project = self.db.scalar(
            select(Project).where(
                Project.id == asset.project_id,
                Project.organisation_id == principal.organisation.id,
            )
        )
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
        if project.external_apis_allowed is False:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="External API processing is disabled by policy",
            )

    def get(self, principal: Principal, job_id: uuid.UUID) -> TranscriptionJob:
        job = self.db.scalar(
            select(TranscriptionJob).where(
                TranscriptionJob.id == job_id,
                TranscriptionJob.organisation_id == principal.organisation.id,
            )
        )
        if job is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcription job not found")
        return job

    def list_events(self, job_id: uuid.UUID) -> list[JobEvent]:
        return list(
            db_event
            for db_event in self.db.scalars(
                select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.sequence)
            )
        )

    def request_cancellation(self, job: TranscriptionJob) -> None:
        if job.status in {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Job is already in a terminal state"
            )
        job.cancel_requested_at = datetime.now(UTC)
        self.add_event(job, job.status, job.progress_percent, "Cancellation requested")

    def reset_for_retry(self, job: TranscriptionJob) -> None:
        """Reset a failed/cancelled job so it can be re-queued.

        Existing attempt history is preserved so administrators can see what
        went wrong on each prior run.
        """
        if job.status not in {JobStatus.failed, JobStatus.cancelled}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Only failed or cancelled jobs can be retried"
            )
        job.status = JobStatus.queued
        job.progress_percent = 0
        job.error_code = None
        job.error_message = None
        job.cancel_requested_at = None
        job.started_at = None
        job.finished_at = None
        job.processing_ms = None
        self.add_event(job, JobStatus.queued, 0, "Job queued for retry")

    def add_event(
        self,
        job: TranscriptionJob,
        state: JobStatus,
        progress_percent: int,
        message: str,
        data: dict | None = None,
    ) -> JobEvent:
        sequence = (
            self.db.scalar(select(func.max(JobEvent.sequence)).where(JobEvent.job_id == job.id)) or 0
        ) + 1
        event = JobEvent(
            job_id=job.id,
            sequence=sequence,
            state=state,
            progress_percent=progress_percent,
            message=message,
            data=data or {},
        )
        self.db.add(event)
        return event


def _capabilities_support_transcription(capabilities: dict | None) -> bool:
    capabilities = capabilities or {}
    if capabilities.get("transcription") is False:
        return False
    tasks = capabilities.get("tasks") or capabilities.get("supported_tasks")
    if tasks is None:
        return True
    if isinstance(tasks, str):
        return tasks == "transcription"
    try:
        return "transcription" in tasks
    except TypeError:
        return False
