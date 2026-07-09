from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import Report, ReportTemplate, Transcript, TranscriptSegment, TranscriptVersion
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission
from app.services.reports import build_report_content

router = APIRouter(prefix="/reports", tags=["reports"])
DbSession = Annotated[Session, Depends(get_db)]
Reader = Annotated[Principal, Depends(require_permission("reports.read"))]
Manager = Annotated[Principal, Depends(require_permission("reports.manage"))]


class TemplateInput(BaseModel):
    model_config = {"populate_by_name": True}

    name: str = Field(min_length=1, max_length=200)
    kind: str = Field(min_length=1, max_length=100)
    schema_: dict = Field(default_factory=dict, alias="schema")
    prompt_template: str | None = Field(default=None, max_length=5000)


class TemplateUpdateInput(BaseModel):
    model_config = {"populate_by_name": True}

    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, min_length=1, max_length=100)
    schema_: dict | None = Field(default=None, alias="schema")
    prompt_template: str | None = Field(default=None, max_length=5000)
    enabled: bool | None = None


class TemplateResponse(BaseModel):
    model_config = {"populate_by_name": True}

    id: UUID
    name: str
    kind: str
    schema_: dict = Field(alias="schema")
    prompt_template: str | None
    enabled: bool
    is_builtin: bool


class ReportInput(BaseModel):
    transcript_id: UUID
    template_id: UUID | None = None
    title: str = Field(min_length=1, max_length=300)


class TemplatePreviewInput(BaseModel):
    transcript_id: UUID
    title: str = Field(default="Report preview", min_length=1, max_length=300)


class TemplatePreviewResponse(BaseModel):
    content: dict


class ReportUpdateInput(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    content: dict | None = None
    status: str | None = Field(default=None, pattern="^(queued|generating|completed|failed)$")


class ReportResponse(BaseModel):
    id: UUID
    transcript_version_id: UUID
    template_id: UUID | None
    title: str
    status: str
    content: dict
    created_at: datetime


@router.get("/templates", response_model=list[TemplateResponse])
def list_templates(principal: Reader, db: DbSession):
    rows = list(
        db.scalars(
            select(ReportTemplate)
            .where(
                (ReportTemplate.organisation_id == principal.organisation.id)
                | (ReportTemplate.organisation_id.is_(None))
            )
            .order_by(ReportTemplate.kind)
        )
    )
    return [_template_response(item) for item in rows]


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
def create_template(payload: TemplateInput, principal: Manager, db: DbSession):
    template = ReportTemplate(
        organisation_id=principal.organisation.id,
        name=payload.name,
        kind=payload.kind,
        schema=payload.schema_,
        prompt_template=payload.prompt_template,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: UUID, payload: TemplateUpdateInput, request: Request, principal: Manager, db: DbSession
):
    template = _get_manageable_template(db, principal, template_id)
    if payload.name is not None:
        template.name = payload.name
    if payload.kind is not None:
        template.kind = payload.kind
    if payload.schema_ is not None:
        template.schema = payload.schema_
    if "prompt_template" in payload.model_fields_set:
        template.prompt_template = payload.prompt_template
    if payload.enabled is not None:
        template.enabled = payload.enabled
    write_audit(
        db,
        principal,
        "report_template.updated",
        "report_template",
        template.id,
        "success",
        request,
    )
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.post("/templates/{template_id}/enable", response_model=TemplateResponse)
def enable_template(template_id: UUID, request: Request, principal: Manager, db: DbSession):
    template = _get_manageable_template(db, principal, template_id)
    template.enabled = True
    write_audit(
        db,
        principal,
        "report_template.enabled",
        "report_template",
        template.id,
        "success",
        request,
    )
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.post("/templates/{template_id}/disable", response_model=TemplateResponse)
def disable_template(template_id: UUID, request: Request, principal: Manager, db: DbSession):
    template = _get_manageable_template(db, principal, template_id)
    template.enabled = False
    write_audit(
        db,
        principal,
        "report_template.disabled",
        "report_template",
        template.id,
        "success",
        request,
    )
    db.commit()
    db.refresh(template)
    return _template_response(template)


@router.post("/templates/{template_id}/preview", response_model=TemplatePreviewResponse)
def preview_template(
    template_id: UUID,
    payload: TemplatePreviewInput,
    request: Request,
    principal: Reader,
    db: DbSession,
):
    template = _get_readable_template(db, principal, template_id)
    transcript = _get_transcript_for_report(db, principal, payload.transcript_id)
    version = db.get(TranscriptVersion, transcript.active_version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Transcript version not found")
    segments = _segments_for_version(db, version.id)
    content = build_report_content(
        title=payload.title,
        transcript=transcript,
        version=version,
        template=template,
        segments=segments,
    )
    write_audit(
        db,
        principal,
        "report_template.previewed",
        "report_template",
        template.id,
        "success",
        request,
        {"transcript_id": str(transcript.id)},
    )
    db.commit()
    return TemplatePreviewResponse(content=content)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: UUID, request: Request, principal: Manager, db: DbSession):
    template = _get_manageable_template(db, principal, template_id)
    write_audit(
        db,
        principal,
        "report_template.deleted",
        "report_template",
        template.id,
        "success",
        request,
    )
    db.delete(template)
    db.commit()


@router.get("", response_model=list[ReportResponse])
def list_reports(principal: Reader, db: DbSession, limit: int = 50):
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Invalid limit")
    rows = list(
        db.scalars(
            select(Report)
            .where(Report.organisation_id == principal.organisation.id)
            .order_by(Report.created_at.desc())
            .limit(limit)
        )
    )
    return [
        ReportResponse(
            id=item.id,
            transcript_version_id=item.transcript_version_id,
            template_id=item.template_id,
            title=item.title,
            status=item.status,
            content=item.content,
            created_at=item.created_at,
        )
        for item in rows
    ]


@router.post("", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
def create_report(payload: ReportInput, request: Request, principal: Manager, db: DbSession):
    transcript = _get_transcript_for_report(db, principal, payload.transcript_id)
    template = _get_readable_template(db, principal, payload.template_id) if payload.template_id else None
    if template is not None and not template.enabled:
        raise HTTPException(status_code=409, detail="Report template is disabled")
    report = Report(
        organisation_id=principal.organisation.id,
        transcript_version_id=transcript.active_version_id,
        template_id=template.id if template else None,
        title=payload.title,
        status="queued",
    )
    db.add(report)
    db.flush()
    write_audit(
        db,
        principal,
        "report.created",
        "report",
        report.id,
        "success",
        request,
        {"transcript_id": str(transcript.id)},
    )
    db.commit()
    db.refresh(report)
    _enqueue_report(report.id)
    return ReportResponse(
        id=report.id,
        transcript_version_id=report.transcript_version_id,
        template_id=report.template_id,
        title=report.title,
        status=report.status,
        content=report.content,
        created_at=report.created_at,
    )


@router.patch("/{report_id}", response_model=ReportResponse)
def update_report(
    report_id: UUID, payload: ReportUpdateInput, request: Request, principal: Manager, db: DbSession
):
    report = _get_report(db, principal, report_id)
    if payload.title is not None:
        report.title = payload.title
    if payload.content is not None:
        report.content = payload.content
    if payload.status is not None:
        report.status = payload.status
    elif payload.content is not None and report.status != "failed":
        report.status = "completed"
    write_audit(db, principal, "report.updated", "report", report.id, "success", request)
    db.commit()
    db.refresh(report)
    return _report_response(report)


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(report_id: UUID, request: Request, principal: Reader, db: DbSession):
    report = _get_report(db, principal, report_id)
    write_audit(db, principal, "report.viewed", "report", report.id, "success", request)
    db.commit()
    return _report_response(report)


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: UUID, request: Request, principal: Manager, db: DbSession):
    report = _get_report(db, principal, report_id)
    write_audit(db, principal, "report.deleted", "report", report.id, "success", request)
    db.delete(report)
    db.commit()


def _get_report(db: Session, principal: Principal, report_id: UUID) -> Report:
    report = db.scalar(
        select(Report).where(Report.id == report_id, Report.organisation_id == principal.organisation.id)
    )
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _get_readable_template(db: Session, principal: Principal, template_id: UUID) -> ReportTemplate:
    template = db.scalar(
        select(ReportTemplate).where(
            ReportTemplate.id == template_id,
            (ReportTemplate.organisation_id == principal.organisation.id)
            | (ReportTemplate.organisation_id.is_(None)),
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Report template not found")
    return template


def _get_manageable_template(db: Session, principal: Principal, template_id: UUID) -> ReportTemplate:
    template = db.scalar(
        select(ReportTemplate).where(
            ReportTemplate.id == template_id,
            ReportTemplate.organisation_id == principal.organisation.id,
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Editable report template not found")
    return template


def _get_transcript_for_report(db: Session, principal: Principal, transcript_id: UUID) -> Transcript:
    transcript = db.get(Transcript, transcript_id)
    if (
        transcript is None
        or transcript.organisation_id != principal.organisation.id
        or transcript.active_version_id is None
    ):
        raise HTTPException(status_code=404, detail="Transcript not found")
    return transcript


def _segments_for_version(db: Session, version_id: UUID) -> list[TranscriptSegment]:
    return list(
        db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.version_id == version_id)
            .order_by(TranscriptSegment.sequence)
        )
    )


def _template_response(template: ReportTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "kind": template.kind,
        "schema": template.schema,
        "prompt_template": template.prompt_template,
        "enabled": template.enabled,
        "is_builtin": template.organisation_id is None,
    }


def _report_response(report: Report) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        transcript_version_id=report.transcript_version_id,
        template_id=report.template_id,
        title=report.title,
        status=report.status,
        content=report.content,
        created_at=report.created_at,
    )


def _enqueue_report(report_id: UUID) -> None:
    try:
        from app.worker.post_processing_tasks import generate_report

        generate_report.delay(str(report_id))
    except Exception:
        return
