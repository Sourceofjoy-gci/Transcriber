from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import (
    AssetStatus,
    AuditLog,
    JobStatus,
    MediaAsset,
    MediaMetadata,
    ProviderUsageLog,
    TranscriptionJob,
)
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DbSession = Annotated[Session, Depends(get_db)]
DashboardReader = Annotated[Principal, Depends(require_permission("dashboard.read"))]


class DashboardMetrics(BaseModel):
    total_files: int
    completed_transcriptions: int
    failed_transcriptions: int
    jobs_in_progress: int
    storage_bytes: int
    total_transcription_seconds: float
    average_processing_ms: float | None
    most_used_models: list[dict]
    most_used_providers: list[dict]
    recent_jobs: list[dict]
    api_cost_estimate: float
    recent_errors: list[dict]


@router.get("/metrics", response_model=DashboardMetrics)
def get_metrics(principal: DashboardReader, db: DbSession) -> DashboardMetrics:
    org_id = principal.organisation.id
    total_files = (
        db.scalar(
            select(func.count())
            .select_from(MediaAsset)
            .where(MediaAsset.organisation_id == org_id, MediaAsset.status != AssetStatus.deleted)
        )
        or 0
    )
    storage_bytes = (
        db.scalar(
            select(func.coalesce(func.sum(MediaAsset.byte_size), 0)).where(
                MediaAsset.organisation_id == org_id, MediaAsset.status != AssetStatus.deleted
            )
        )
        or 0
    )
    completed = (
        db.scalar(
            select(func.count())
            .select_from(TranscriptionJob)
            .where(TranscriptionJob.organisation_id == org_id, TranscriptionJob.status == JobStatus.completed)
        )
        or 0
    )
    failed = (
        db.scalar(
            select(func.count())
            .select_from(TranscriptionJob)
            .where(TranscriptionJob.organisation_id == org_id, TranscriptionJob.status == JobStatus.failed)
        )
        or 0
    )
    in_progress = (
        db.scalar(
            select(func.count())
            .select_from(TranscriptionJob)
            .where(
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.status.in_(
                    [
                        JobStatus.queued,
                        JobStatus.uploading,
                        JobStatus.extracting_audio,
                        JobStatus.preprocessing,
                        JobStatus.transcribing,
                        JobStatus.post_processing,
                    ]
                ),
            )
        )
        or 0
    )
    total_duration_ms = (
        db.scalar(
            select(func.coalesce(func.sum(MediaMetadata.duration_ms), 0))
            .join(MediaAsset, MediaAsset.id == MediaMetadata.asset_id)
            .where(MediaAsset.organisation_id == org_id)
        )
        or 0
    )
    avg_processing_ms = db.scalar(
        select(func.avg(TranscriptionJob.processing_ms)).where(
            TranscriptionJob.organisation_id == org_id,
            TranscriptionJob.processing_ms.is_not(None),
        )
    )

    # Most-used providers (rough proxy: count of job targets in this org)
    provider_rows = list(
        db.execute(
            select(
                TranscriptionJob.execution_target_kind,
                func.count(TranscriptionJob.id).label("count"),
            )
            .where(TranscriptionJob.organisation_id == org_id)
            .group_by(TranscriptionJob.execution_target_kind)
            .order_by(func.count(TranscriptionJob.id).desc())
            .limit(5)
        )
    )
    most_used_providers = [{"provider": row[0], "count": int(row[1])} for row in provider_rows]

    # Most-used models (count of jobs grouped by execution_target_id; nulls are omitted)
    model_rows = list(
        db.execute(
            select(
                TranscriptionJob.execution_target_id,
                func.count(TranscriptionJob.id).label("count"),
            )
            .where(
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.execution_target_id.is_not(None),
            )
            .group_by(TranscriptionJob.execution_target_id)
            .order_by(func.count(TranscriptionJob.id).desc())
            .limit(5)
        )
    )
    most_used_models = [{"installed_model_id": str(row[0]), "count": int(row[1])} for row in model_rows]

    # Recent jobs
    recent = list(
        db.scalars(
            select(TranscriptionJob)
            .where(TranscriptionJob.organisation_id == org_id)
            .order_by(TranscriptionJob.created_at.desc())
            .limit(5)
        )
    )
    recent_jobs = [
        {
            "id": str(job.id),
            "status": job.status.value,
            "progress_percent": job.progress_percent,
            "created_at": job.created_at.isoformat(),
            "error_code": job.error_code,
        }
        for job in recent
    ]

    # API cost estimate: sum of provider usage estimated costs (parsed as float)
    cost_total = 0.0
    cost_rows = db.execute(
        select(ProviderUsageLog.estimated_cost)
        .join(TranscriptionJob, TranscriptionJob.id == ProviderUsageLog.job_id, isouter=True)
        .where(TranscriptionJob.organisation_id == org_id)
    ).all()
    for (raw,) in cost_rows:
        if not raw:
            continue
        try:
            cost_total += float(raw)
        except (TypeError, ValueError):
            continue

    # Recent errors: failed jobs from last 24h, plus failed audit rows
    recent_cutoff = datetime.now(UTC) - timedelta(hours=24)
    recent_errors_rows = list(
        db.scalars(
            select(TranscriptionJob)
            .where(
                TranscriptionJob.organisation_id == org_id,
                TranscriptionJob.status == JobStatus.failed,
                TranscriptionJob.created_at >= recent_cutoff,
            )
            .order_by(TranscriptionJob.created_at.desc())
            .limit(5)
        )
    )
    recent_errors = [
        {
            "job_id": str(job.id),
            "error_code": job.error_code,
            "error_message": job.error_message,
            "created_at": job.created_at.isoformat(),
        }
        for job in recent_errors_rows
    ]

    return DashboardMetrics(
        total_files=int(total_files),
        completed_transcriptions=int(completed),
        failed_transcriptions=int(failed),
        jobs_in_progress=int(in_progress),
        storage_bytes=int(storage_bytes),
        total_transcription_seconds=round(int(total_duration_ms) / 1000.0, 2),
        average_processing_ms=float(avg_processing_ms) if avg_processing_ms is not None else None,
        most_used_models=most_used_models,
        most_used_providers=most_used_providers,
        recent_jobs=recent_jobs,
        api_cost_estimate=round(cost_total, 4),
        recent_errors=recent_errors,
    )


class AuditEvent(BaseModel):
    id: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    outcome: str
    data: dict
    created_at: datetime


@router.get("/audit-logs", response_model=list[AuditEvent])
def list_audit_logs(
    principal: Annotated[Principal, Depends(require_permission("audit.read"))],
    db: DbSession,
    limit: int = 100,
):
    if limit < 1 or limit > 500:
        limit = 100
    rows = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.organisation_id == principal.organisation.id)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
    )
    return [
        AuditEvent(
            id=str(row.id),
            actor_id=str(row.actor_id) if row.actor_id else None,
            action=row.action,
            resource_type=row.resource_type,
            resource_id=str(row.resource_id) if row.resource_id else None,
            outcome=row.outcome,
            data=row.data or {},
            created_at=row.created_at,
        )
        for row in rows
    ]
