import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.models.domain import ExportRecord, ExportStatus, Report, Transcript, TranscriptSegment
from app.schemas.transcripts import ExportCreateRequest, ExportResponse
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.storage_factory import build_storage_provider

router = APIRouter(prefix="/exports", tags=["exports"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]
ExportCreator = Annotated[Principal, Depends(require_permission("exports.create"))]


@router.post("", response_model=ExportResponse, status_code=status.HTTP_202_ACCEPTED)
def create_export(
    payload: ExportCreateRequest, request: Request, principal: ExportCreator, db: DbSession
) -> ExportResponse:
    transcript_version_id, options = _resolve_export_source(db, principal, payload)
    export = ExportRecord(
        organisation_id=principal.organisation.id,
        requested_by_id=principal.user.id,
        transcript_version_id=transcript_version_id,
        format=payload.format,
        options=options,
        status=ExportStatus.queued,
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )
    db.add(export)
    db.flush()
    write_audit(
        db,
        principal,
        "export.created",
        "export",
        export.id,
        "success",
        request,
        {"format": export.format, "source_type": options["source_type"]},
    )
    db.commit()
    db.refresh(export)
    _enqueue_export(export.id)
    return ExportResponse.model_validate(export)


@router.get("", response_model=list[ExportResponse])
def list_exports(principal: ExportCreator, db: DbSession, limit: int = 50) -> list[ExportResponse]:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid limit")
    rows = list(
        db.scalars(
            select(ExportRecord)
            .where(ExportRecord.organisation_id == principal.organisation.id)
            .order_by(ExportRecord.created_at.desc())
            .limit(limit)
        )
    )
    return [ExportResponse.model_validate(item) for item in rows]


@router.get("/{export_id}", response_model=ExportResponse)
def get_export(export_id: uuid.UUID, principal: ExportCreator, db: DbSession) -> ExportResponse:
    return ExportResponse.model_validate(_get_export(db, principal, export_id))


@router.get("/{export_id}/download")
def download_export(
    export_id: uuid.UUID,
    request: Request,
    principal: ExportCreator,
    db: DbSession,
    settings: SettingsDependency,
) -> Response:
    export = _get_export(db, principal, export_id)
    if export.status != ExportStatus.completed or not export.storage_key:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Export is not ready")
    if _is_expired(export.expires_at):
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Export has expired")
    source_type = (export.options or {}).get("source_type", "transcript")
    write_audit(
        db,
        principal,
        "export.downloaded",
        "export",
        export.id,
        "success",
        request,
        {"format": export.format, "source_type": source_type},
    )
    db.commit()
    filename = f"{source_type}.{export.format}"
    storage = build_storage_provider(settings)
    try:
        return FileResponse(
            storage.path_for(export.storage_key),
            media_type=_media_type_for_export(export.format),
            filename=filename,
        )
    except RuntimeError:
        return StreamingResponse(
            storage.open(export.storage_key),
            media_type=_media_type_for_export(export.format),
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
        )


def _get_export(db: Session, principal: Principal, export_id: uuid.UUID) -> ExportRecord:
    export = db.scalar(
        select(ExportRecord).where(
            ExportRecord.id == export_id, ExportRecord.organisation_id == principal.organisation.id
        )
    )
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export


def _resolve_export_source(
    db: Session, principal: Principal, payload: ExportCreateRequest
) -> tuple[uuid.UUID, dict]:
    options = dict(payload.options or {})
    options["source_type"] = payload.source_type
    if payload.source_type == "report":
        if payload.report_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Report is required")
        report = db.scalar(
            select(Report).where(
                Report.id == payload.report_id,
                Report.organisation_id == principal.organisation.id,
            )
        )
        if report is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")
        if report.status != "completed":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Report is not ready for export")
        options["report_id"] = str(report.id)
        return report.transcript_version_id, options

    if payload.transcript_id is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Transcript is required")
    transcript = db.scalar(
        select(Transcript).where(
            Transcript.id == payload.transcript_id,
            Transcript.organisation_id == principal.organisation.id,
        )
    )
    if transcript is None or transcript.active_version_id is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Transcript is not available for export"
        )
    if payload.segment_ids:
        segment_count = db.scalar(
            select(func.count(TranscriptSegment.id)).where(
                TranscriptSegment.version_id == transcript.active_version_id,
                TranscriptSegment.id.in_(payload.segment_ids),
            )
        )
        if segment_count != len(set(payload.segment_ids)):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Selected segments must belong to the active transcript version",
            )
        options["segment_ids"] = [str(segment_id) for segment_id in payload.segment_ids]
    return transcript.active_version_id, options


def _is_expired(expires_at: datetime | None) -> bool:
    if expires_at is None:
        return False
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return expires_at < datetime.now(UTC)


def _enqueue_export(export_id: uuid.UUID) -> None:
    try:
        from app.worker.tasks import generate_export

        generate_export.delay(str(export_id))
    except Exception:
        return


def _media_type_for_export(export_format: str) -> str:
    return {
        "txt": "text/plain",
        "json": "application/json",
        "srt": "application/x-subrip",
        "vtt": "text/vtt",
        "csv": "text/csv",
        "md": "text/markdown",
        "html": "text/html",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }[export_format]
