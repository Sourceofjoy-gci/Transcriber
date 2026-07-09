import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import MediaAsset, Project
from app.schemas.media import ProjectCreateRequest, ProjectResponse, ProjectUpdateRequest
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/projects", tags=["projects"])
DbSession = Annotated[Session, Depends(get_db)]
AssetReader = Annotated[Principal, Depends(require_permission("assets.read"))]
SettingsManager = Annotated[Principal, Depends(require_permission("settings.manage"))]


@router.get("", response_model=list[ProjectResponse])
def list_projects(principal: AssetReader, db: DbSession) -> list[Project]:
    return list(
        db.scalars(
            select(Project).where(Project.organisation_id == principal.organisation.id).order_by(Project.name)
        )
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(payload: ProjectCreateRequest, principal: SettingsManager, db: DbSession) -> Project:
    existing = db.scalar(
        select(Project).where(
            Project.organisation_id == principal.organisation.id, Project.name == payload.name
        )
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A project with this name already exists"
        )
    project = Project(organisation_id=principal.organisation.id, **payload.model_dump())
    db.add(project)
    db.flush()
    write_audit(db, principal, "project.created", "project", project.id, "success")
    db.commit()
    db.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: uuid.UUID, principal: AssetReader, db: DbSession) -> Project:
    return _project_or_404(db, principal, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdateRequest,
    request: Request,
    principal: SettingsManager,
    db: DbSession,
) -> Project:
    project = _project_or_404(db, principal, project_id)
    if payload.name is not None and payload.name != project.name:
        existing = db.scalar(
            select(Project).where(
                Project.organisation_id == principal.organisation.id,
                Project.name == payload.name,
                Project.id != project.id,
            )
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="A project with this name already exists"
            )
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(project, field, value)
    write_audit(db, principal, "project.updated", "project", project.id, "success", request)
    db.commit()
    db.refresh(project)
    return project


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID, request: Request, principal: SettingsManager, db: DbSession
) -> None:
    project = _project_or_404(db, principal, project_id)
    assets = db.scalars(select(MediaAsset).where(MediaAsset.project_id == project.id))
    for asset in assets:
        asset.project_id = None
    write_audit(db, principal, "project.deleted", "project", project.id, "success", request)
    db.delete(project)
    db.commit()


def _project_or_404(db: Session, principal: Principal, project_id: uuid.UUID) -> Project:
    project = db.scalar(
        select(Project).where(
            Project.id == project_id,
            Project.organisation_id == principal.organisation.id,
        )
    )
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project
