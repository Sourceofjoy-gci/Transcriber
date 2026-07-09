import json
import time
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal, get_db
from app.models.domain import (
    InstalledModel,
    JobEvent,
    JobStatus,
    ModelCatalog,
    ModelTaskDefault,
    TranscriptionJob,
)
from app.schemas.jobs import (
    JobAttemptResponse,
    JobDetailResponse,
    JobEventResponse,
    TranscriptionJobCreateRequest,
    TranscriptionJobResponse,
)
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.jobs import JobService

router = APIRouter(prefix="/transcription-jobs", tags=["transcription jobs"])
DbSession = Annotated[Session, Depends(get_db)]
JobCreator = Annotated[Principal, Depends(require_permission("jobs.create"))]
JobReader = Annotated[Principal, Depends(require_permission("jobs.read"))]
JobCanceller = Annotated[Principal, Depends(require_permission("jobs.cancel"))]
TRANSCRIPTION_CPU_QUEUE = "transcription.cpu"
TRANSCRIPTION_GPU_QUEUE = "transcription.gpu"


@router.post("", response_model=TranscriptionJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_job(
    payload: TranscriptionJobCreateRequest, request: Request, principal: JobCreator, db: DbSession
) -> TranscriptionJobResponse:
    service = JobService(db)
    job = service.create(principal, payload)
    write_audit(db, principal, "transcription_job.created", "transcription_job", job.id, "success", request)
    db.commit()
    db.refresh(job)
    _enqueue_transcription(job.id)
    return TranscriptionJobResponse.model_validate(job)


@router.get("", response_model=list[TranscriptionJobResponse])
def list_jobs(
    principal: JobReader,
    db: DbSession,
    limit: int = 50,
    status_filter: JobStatus | None = None,
) -> list[TranscriptionJob]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid limit")
    statement = select(TranscriptionJob).where(TranscriptionJob.organisation_id == principal.organisation.id)
    if status_filter is not None:
        statement = statement.where(TranscriptionJob.status == status_filter)
    return list(db.scalars(statement.order_by(TranscriptionJob.created_at.desc()).limit(limit)))


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: uuid.UUID, principal: JobReader, db: DbSession) -> JobDetailResponse:
    service = JobService(db)
    job = service.get(principal, job_id)
    return JobDetailResponse(
        **TranscriptionJobResponse.model_validate(job).model_dump(),
        events=[JobEventResponse.model_validate(event) for event in service.list_events(job.id)],
    )


@router.get("/{job_id}/events/history", response_model=list[JobEventResponse])
def list_job_event_history(job_id: uuid.UUID, principal: JobReader, db: DbSession) -> list[JobEventResponse]:
    service = JobService(db)
    job = service.get(principal, job_id)
    return [JobEventResponse.model_validate(event) for event in service.list_events(job.id)]


@router.get("/{job_id}/events")
def stream_job_events(job_id: uuid.UUID, principal: JobReader, db: DbSession) -> StreamingResponse:
    JobService(db).get(principal, job_id)

    def event_stream():
        last_sequence = 0
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            with SessionLocal() as event_db:
                events = list(
                    event_db.scalars(
                        select(JobEvent)
                        .where(JobEvent.job_id == job_id, JobEvent.sequence > last_sequence)
                        .order_by(JobEvent.sequence)
                    )
                )
                for event in events:
                    last_sequence = event.sequence
                    payload = {
                        "sequence": event.sequence,
                        "state": event.state.value,
                        "progress_percent": event.progress_percent,
                        "message": event.message,
                        "data": event.data,
                        "created_at": event.created_at.isoformat(),
                    }
                    yield f"event: job\ndata: {json.dumps(payload)}\n\n"
                current_job = event_db.get(TranscriptionJob, job_id)
                if current_job and current_job.status in {
                    JobStatus.completed,
                    JobStatus.failed,
                    JobStatus.cancelled,
                }:
                    return
            yield ": keepalive\n\n"
            time.sleep(1)

    return StreamingResponse(
        event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
    )


@router.post("/{job_id}/cancel", response_model=TranscriptionJobResponse)
def cancel_job(
    job_id: uuid.UUID, request: Request, principal: JobCanceller, db: DbSession
) -> TranscriptionJobResponse:
    service = JobService(db)
    job = service.get(principal, job_id)
    service.request_cancellation(job)
    write_audit(
        db, principal, "transcription_job.cancel_requested", "transcription_job", job.id, "success", request
    )
    db.commit()
    db.refresh(job)
    return TranscriptionJobResponse.model_validate(job)


@router.post("/{job_id}/retry", response_model=TranscriptionJobResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_job(
    job_id: uuid.UUID, request: Request, principal: JobCreator, db: DbSession
) -> TranscriptionJobResponse:
    service = JobService(db)
    job = service.get(principal, job_id)
    if job.status not in {JobStatus.failed, JobStatus.cancelled}:
        raise HTTPException(status_code=409, detail="Only failed or cancelled jobs can be retried")
    service.reset_for_retry(job)
    write_audit(
        db, principal, "transcription_job.retry_requested", "transcription_job", job.id, "success", request
    )
    db.commit()
    db.refresh(job)
    _enqueue_transcription(job.id)
    return TranscriptionJobResponse.model_validate(job)


@router.get("/{job_id}/attempts", response_model=list[JobAttemptResponse])
def list_attempts(job_id: uuid.UUID, principal: JobReader, db: DbSession) -> list[JobAttemptResponse]:
    JobService(db).get(principal, job_id)
    from app.models.domain import JobAttempt

    attempts = list(
        db.scalars(select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.attempt_number))
    )
    return [JobAttemptResponse.model_validate(attempt) for attempt in attempts]


def _enqueue_transcription(job_id: uuid.UUID, db: Session | None = None) -> None:
    try:
        from app.worker.tasks import run_transcription_job

        if db is None:
            with SessionLocal() as queue_db:
                queue = _transcription_queue_for_job(queue_db, job_id)
        else:
            queue = _transcription_queue_for_job(db, job_id)
        run_transcription_job.apply_async(
            args=(str(job_id),),
            queue=queue,
        )
    except Exception:
        return


def _transcription_queue_for_job(db: Session, job_id: uuid.UUID) -> str:
    job = db.get(TranscriptionJob, job_id)
    if job is None or job.execution_target_kind == "api_provider":
        return TRANSCRIPTION_CPU_QUEUE

    model_id = job.execution_target_id
    if model_id is None and job.execution_target_kind == "automatic":
        default = db.scalar(
            select(ModelTaskDefault).where(
                ModelTaskDefault.organisation_id == job.organisation_id,
                ModelTaskDefault.task == "transcription",
            )
        )
        model_id = default.installed_model_id if default else None
    if model_id is None:
        return TRANSCRIPTION_CPU_QUEUE

    installed = db.scalar(
        select(InstalledModel).where(
            InstalledModel.id == model_id,
            InstalledModel.organisation_id == job.organisation_id,
        )
    )
    if installed is None:
        return TRANSCRIPTION_CPU_QUEUE
    catalog = db.get(ModelCatalog, installed.catalog_id)
    if catalog is not None and _catalog_requires_gpu_queue(catalog):
        return TRANSCRIPTION_GPU_QUEUE
    return TRANSCRIPTION_CPU_QUEUE


def _catalog_requires_gpu_queue(catalog: ModelCatalog) -> bool:
    requirements = catalog.requirements or {}
    if requirements.get("requires_cuda") is True:
        return True
    return str(requirements.get("recommended_device") or "").lower() == "cuda"
