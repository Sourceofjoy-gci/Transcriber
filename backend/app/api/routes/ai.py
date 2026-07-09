from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import (
    AIProcessingRun,
    MediaAsset,
    Project,
    ProviderDefinition,
    ProviderSecret,
    Transcript,
    TranscriptionJob,
    TranscriptVersion,
)
from app.schemas.ai import AIProcessingRequest
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/ai-runs", tags=["AI post-processing"])
DbSession = Annotated[Session, Depends(get_db)]
Runner = Annotated[Principal, Depends(require_permission("transcripts.edit"))]


class AIProcessingResponse(BaseModel):
    id: UUID
    status: str
    task: str
    transcript_id: UUID
    transcript_version_id: UUID
    execution_target_kind: str
    execution_target_id: UUID | None
    progress_percent: int
    progress_message: str | None
    result: dict | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AIProcessingResponse)
def create_run(payload: AIProcessingRequest, request: Request, principal: Runner, db: DbSession):
    transcript = _get_transcript(db, principal, payload.transcript_id)
    _validate_target(db, principal, transcript, payload)
    run = AIProcessingRun(
        organisation_id=principal.organisation.id,
        transcript_version_id=transcript.active_version_id,
        task=payload.task,
        execution_target_kind=payload.execution_target_kind,
        execution_target_id=payload.execution_target_id,
        options=payload.options,
        status="queued",
        progress_percent=0,
        progress_message="Queued",
    )
    db.add(run)
    db.flush()
    write_audit(
        db,
        principal,
        "ai_run.created",
        "ai_run",
        run.id,
        "success",
        request,
        {"task": payload.task, "transcript_id": str(transcript.id)},
    )
    db.commit()
    db.refresh(run)
    _enqueue(run.id)
    return _response(db, run)


@router.get("", response_model=list[AIProcessingResponse])
def list_runs(principal: Runner, db: DbSession, limit: int = 50) -> list[AIProcessingResponse]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid limit")
    runs = list(
        db.scalars(
            select(AIProcessingRun)
            .where(AIProcessingRun.organisation_id == principal.organisation.id)
            .order_by(AIProcessingRun.created_at.desc())
            .limit(limit)
        )
    )
    return [_response(db, run) for run in runs]


@router.get("/{run_id}", response_model=AIProcessingResponse)
def get_run(run_id: UUID, principal: Runner, db: DbSession):
    return _response(db, _get_run(db, principal, run_id))


@router.post("/{run_id}/cancel", response_model=AIProcessingResponse)
def cancel_run(run_id: UUID, request: Request, principal: Runner, db: DbSession) -> AIProcessingResponse:
    run = _get_run(db, principal, run_id)
    if run.status in {"completed", "failed", "cancelled"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="AI run is already terminal")
    run.status = "cancelled"
    run.progress_message = "Cancellation requested"
    run.cancel_requested_at = datetime.now(UTC)
    write_audit(db, principal, "ai_run.cancelled", "ai_run", run.id, "success", request)
    db.commit()
    db.refresh(run)
    return _response(db, run)


@router.post("/{run_id}/retry", status_code=status.HTTP_202_ACCEPTED, response_model=AIProcessingResponse)
def retry_run(run_id: UUID, request: Request, principal: Runner, db: DbSession) -> AIProcessingResponse:
    run = _get_run(db, principal, run_id)
    if run.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only failed or cancelled AI runs can be retried",
        )
    run.status = "queued"
    run.progress_percent = 0
    run.progress_message = "Queued for retry"
    run.error_message = None
    run.result = None
    run.cancel_requested_at = None
    run.completed_at = None
    write_audit(db, principal, "ai_run.retry_requested", "ai_run", run.id, "success", request)
    db.commit()
    db.refresh(run)
    _enqueue(run.id)
    return _response(db, run)


def _get_transcript(db: Session, principal: Principal, transcript_id: UUID) -> Transcript:
    transcript = db.scalar(
        select(Transcript).where(
            Transcript.id == transcript_id, Transcript.organisation_id == principal.organisation.id
        )
    )
    if transcript is None or transcript.active_version_id is None:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript


def _get_run(db: Session, principal: Principal, run_id: UUID) -> AIProcessingRun:
    run = db.scalar(
        select(AIProcessingRun).where(
            AIProcessingRun.id == run_id, AIProcessingRun.organisation_id == principal.organisation.id
        )
    )
    if run is None:
        raise HTTPException(status_code=404, detail="AI run not found")
    return run


def _validate_target(
    db: Session, principal: Principal, transcript: Transcript, payload: AIProcessingRequest
) -> None:
    if payload.execution_target_kind != "api_provider":
        return
    if not payload.egress_acknowledged:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="External AI jobs require explicit egress acknowledgement",
        )
    _validate_external_policy(db, principal, transcript)
    if payload.execution_target_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A selected API provider is required",
        )
    provider = db.scalar(
        select(ProviderDefinition).where(
            ProviderDefinition.id == payload.execution_target_id,
            ProviderDefinition.organisation_id == principal.organisation.id,
        )
    )
    if provider is None:
        raise HTTPException(status_code=404, detail="API provider not found")
    if not provider.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected API provider must be enabled",
        )
    if provider.category != "post_processing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected API provider does not support AI post-processing",
        )
    if not (provider.model_name or "").strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Selected API provider must define a model name",
        )
    if not _capabilities_support_task(provider.capabilities, payload.task):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Selected API provider does not support {payload.task}",
        )
    if provider.auth_type != "none":
        secret_id = db.scalar(select(ProviderSecret.id).where(ProviderSecret.provider_id == provider.id))
        if secret_id is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Selected API provider must have a configured credential",
            )


def _validate_external_policy(db: Session, principal: Principal, transcript: Transcript) -> None:
    if principal.organisation.local_only_enforced or not principal.organisation.external_apis_allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="External AI processing is disabled by policy",
        )
    job = db.scalar(select(TranscriptionJob).where(TranscriptionJob.id == transcript.job_id))
    asset = db.get(MediaAsset, job.asset_id) if job else None
    if asset is None or asset.project_id is None:
        return
    project = db.scalar(
        select(Project).where(
            Project.id == asset.project_id,
            Project.organisation_id == principal.organisation.id,
        )
    )
    if project is not None and project.external_apis_allowed is False:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="External AI processing is disabled by policy",
        )


def _capabilities_support_task(capabilities: dict | None, task: str) -> bool:
    capabilities = capabilities or {}
    tasks = capabilities.get("tasks") or capabilities.get("supported_tasks")
    if tasks is None:
        return True
    if isinstance(tasks, str):
        return tasks == task
    try:
        return task in tasks
    except TypeError:
        return False


def _response(db: Session, run: AIProcessingRun) -> AIProcessingResponse:
    version = db.get(TranscriptVersion, run.transcript_version_id)
    transcript_id = version.transcript_id if version else UUID(int=0)
    return AIProcessingResponse(
        id=run.id,
        status=run.status,
        task=run.task,
        transcript_id=transcript_id,
        transcript_version_id=run.transcript_version_id,
        execution_target_kind=run.execution_target_kind,
        execution_target_id=run.execution_target_id,
        progress_percent=run.progress_percent,
        progress_message=run.progress_message,
        result=run.result,
        error_message=run.error_message,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


def _enqueue(run_id: UUID) -> None:
    try:
        from app.worker.post_processing_tasks import run_ai_processing

        run_ai_processing.delay(str(run_id))
    except Exception:
        return
