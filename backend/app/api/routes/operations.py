from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from redis import Redis, RedisError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.metrics import runtime_metrics
from app.db.session import get_db
from app.models.domain import AIProcessingRun, ExportRecord, ExportStatus, JobStatus, Report, TranscriptionJob
from app.services.authorization import Principal, require_permission
from app.worker.celery_app import celery_app

router = APIRouter(prefix="/operations", tags=["operations"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
OperationsReader = Annotated[Principal, Depends(require_permission("dashboard.read"))]


class WorkDepth(BaseModel):
    queued: int
    active: int
    failed: int


class QueueDepthResponse(BaseModel):
    transcription: WorkDepth
    ai: WorkDepth
    exports: WorkDepth
    reports: WorkDepth


@router.get("/queue-depth", response_model=QueueDepthResponse)
def queue_depth(principal: OperationsReader, db: DbSession) -> QueueDepthResponse:
    return _queue_depth(db, principal)


@router.get("/worker-health")
def worker_health(
    principal: OperationsReader,
    db: DbSession,
    settings: SettingsDependency,
) -> dict:
    db.execute(text("SELECT 1"))
    return {
        "database": {"status": "ok"},
        "queue_backend": _redis_health(settings),
        "workers": _worker_inspection(settings),
        "queue_depth": _queue_depth(db, principal).model_dump(),
    }


@router.get("/metrics")
def metrics(principal: OperationsReader, db: DbSession) -> dict:
    depth = _queue_depth(db, principal)
    counters = {
        **runtime_metrics.snapshot(),
        "transcription_jobs_queued": depth.transcription.queued,
        "transcription_jobs_active": depth.transcription.active,
        "transcription_jobs_failed": depth.transcription.failed,
        "ai_runs_queued": depth.ai.queued,
        "ai_runs_active": depth.ai.active,
        "ai_runs_failed": depth.ai.failed,
        "exports_queued": depth.exports.queued,
        "exports_active": depth.exports.active,
        "exports_failed": depth.exports.failed,
        "reports_queued": depth.reports.queued,
        "reports_active": depth.reports.active,
        "reports_failed": depth.reports.failed,
    }
    return {"counters": counters}


def _queue_depth(db: Session, principal: Principal) -> QueueDepthResponse:
    org_id = principal.organisation.id
    return QueueDepthResponse(
        transcription=WorkDepth(
            queued=_count(
                db,
                TranscriptionJob,
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.status == JobStatus.queued,
            ),
            active=_count(
                db,
                TranscriptionJob,
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.status.in_(
                    [
                        JobStatus.uploading,
                        JobStatus.extracting_audio,
                        JobStatus.preprocessing,
                        JobStatus.transcribing,
                        JobStatus.post_processing,
                    ]
                ),
            ),
            failed=_count(
                db,
                TranscriptionJob,
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.status == JobStatus.failed,
            ),
        ),
        ai=WorkDepth(
            queued=_count(
                db,
                AIProcessingRun,
                AIProcessingRun.organisation_id == org_id,
                AIProcessingRun.status == "queued",
            ),
            active=_count(
                db,
                AIProcessingRun,
                AIProcessingRun.organisation_id == org_id,
                AIProcessingRun.status == "running",
            ),
            failed=_count(
                db,
                AIProcessingRun,
                AIProcessingRun.organisation_id == org_id,
                AIProcessingRun.status == "failed",
            ),
        ),
        exports=WorkDepth(
            queued=_count(
                db,
                ExportRecord,
                ExportRecord.organisation_id == org_id,
                ExportRecord.status == ExportStatus.queued,
            ),
            active=_count(
                db,
                ExportRecord,
                ExportRecord.organisation_id == org_id,
                ExportRecord.status == ExportStatus.generating,
            ),
            failed=_count(
                db,
                ExportRecord,
                ExportRecord.organisation_id == org_id,
                ExportRecord.status == ExportStatus.failed,
            ),
        ),
        reports=WorkDepth(
            queued=_count(db, Report, Report.organisation_id == org_id, Report.status == "queued"),
            active=_count(db, Report, Report.organisation_id == org_id, Report.status == "generating"),
            failed=_count(db, Report, Report.organisation_id == org_id, Report.status == "failed"),
        ),
    )


def _count(db: Session, model, *clauses) -> int:
    return int(db.scalar(select(func.count()).select_from(model).where(*clauses)) or 0)


def _redis_health(settings: Settings) -> dict[str, str]:
    try:
        Redis.from_url(
            settings.redis_url,
            socket_connect_timeout=settings.worker_health_timeout_seconds,
            socket_timeout=settings.worker_health_timeout_seconds,
        ).ping()
    except RedisError as error:
        return {"status": "unavailable", "error": type(error).__name__}
    return {"status": "ok"}


def _worker_inspection(settings: Settings) -> dict:
    try:
        stats = celery_app.control.inspect(timeout=settings.worker_health_timeout_seconds).stats() or {}
    except Exception as error:  # noqa: BLE001 - health endpoint reports degraded dependencies
        return {"status": "unavailable", "count": 0, "error": type(error).__name__}
    return {
        "status": "ok" if stats else "unavailable",
        "count": len(stats),
        "worker_names": sorted(stats),
    }
