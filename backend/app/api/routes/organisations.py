import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import MembershipStatus, Organisation, OrganisationMembership, Role
from app.services.audit import write_audit
from app.services.authorization import Principal, get_principal, require_permission
from app.services.bootstrap import create_organisation_roles

router = APIRouter(prefix="/organisations", tags=["organisations"])
DbSession = Annotated[Session, Depends(get_db)]
Reader = Annotated[Principal, Depends(get_principal)]
Manager = Annotated[Principal, Depends(require_permission("settings.manage"))]


class OrganisationResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    external_apis_allowed: bool
    local_only_enforced: bool
    retention_days: int | None
    role_code: str | None = None
    is_current: bool = False


class OrganisationCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    external_apis_allowed: bool | None = None
    local_only_enforced: bool | None = None
    retention_days: int | None = Field(default=None, ge=1, le=36500)


class OrganisationUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    external_apis_allowed: bool | None = None
    local_only_enforced: bool | None = None
    retention_days: int | None = Field(default=None, ge=1, le=36500)


@router.get("", response_model=list[OrganisationResponse])
def list_organisations(principal: Reader, db: DbSession) -> list[OrganisationResponse]:
    rows = list(
        db.execute(
            select(Organisation, OrganisationMembership, Role)
            .join(OrganisationMembership, OrganisationMembership.organisation_id == Organisation.id)
            .join(Role, Role.id == OrganisationMembership.role_id)
            .where(
                OrganisationMembership.user_id == principal.user.id,
                OrganisationMembership.status == MembershipStatus.active,
            )
            .order_by(Organisation.name)
        )
    )
    return [_response(org, role.code, org.id == principal.organisation.id) for org, _membership, role in rows]


@router.post("", response_model=OrganisationResponse, status_code=status.HTTP_201_CREATED)
def create_organisation(
    payload: OrganisationCreateRequest, request: Request, principal: Manager, db: DbSession
) -> OrganisationResponse:
    organisation = Organisation(
        name=payload.name,
        slug=_unique_slug(db, payload.name),
        external_apis_allowed=(
            principal.organisation.external_apis_allowed
            if payload.external_apis_allowed is None
            else payload.external_apis_allowed
        ),
        local_only_enforced=(
            principal.organisation.local_only_enforced
            if payload.local_only_enforced is None
            else payload.local_only_enforced
        ),
        retention_days=payload.retention_days,
    )
    db.add(organisation)
    db.flush()
    roles = create_organisation_roles(db, organisation)
    role_code = (
        "system_administrator"
        if principal.role.code == "system_administrator"
        else "organisation_administrator"
    )
    role = roles[role_code]
    db.add(
        OrganisationMembership(
            organisation_id=organisation.id,
            user_id=principal.user.id,
            role_id=role.id,
            status=MembershipStatus.active,
        )
    )
    write_audit(db, principal, "organisation.created", "organisation", organisation.id, "success", request)
    db.commit()
    db.refresh(organisation)
    return _response(organisation, role.code, False)


@router.get("/{organisation_id}", response_model=OrganisationResponse)
def get_organisation(organisation_id: uuid.UUID, principal: Reader, db: DbSession) -> OrganisationResponse:
    organisation, role = _accessible_organisation(db, principal, organisation_id)
    return _response(organisation, role.code, organisation.id == principal.organisation.id)


@router.patch("/{organisation_id}", response_model=OrganisationResponse)
def update_organisation(
    organisation_id: uuid.UUID,
    payload: OrganisationUpdateRequest,
    request: Request,
    principal: Manager,
    db: DbSession,
) -> OrganisationResponse:
    organisation, role = _accessible_organisation(db, principal, organisation_id)
    if payload.name is not None and payload.name != organisation.name:
        organisation.name = payload.name
        organisation.slug = _unique_slug(db, payload.name, exclude_id=organisation.id)
    for field in ("external_apis_allowed", "local_only_enforced", "retention_days"):
        value = getattr(payload, field)
        if value is not None:
            setattr(organisation, field, value)
    write_audit(db, principal, "organisation.updated", "organisation", organisation.id, "success", request)
    db.commit()
    db.refresh(organisation)
    return _response(organisation, role.code, organisation.id == principal.organisation.id)


def _accessible_organisation(
    db: Session, principal: Principal, organisation_id: uuid.UUID
) -> tuple[Organisation, Role]:
    row = db.execute(
        select(Organisation, Role)
        .join(OrganisationMembership, OrganisationMembership.organisation_id == Organisation.id)
        .join(Role, Role.id == OrganisationMembership.role_id)
        .where(
            Organisation.id == organisation_id,
            OrganisationMembership.user_id == principal.user.id,
            OrganisationMembership.status == MembershipStatus.active,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organisation not found")
    return row[0], row[1]


def _response(organisation: Organisation, role_code: str | None, is_current: bool) -> OrganisationResponse:
    return OrganisationResponse(
        id=organisation.id,
        name=organisation.name,
        slug=organisation.slug,
        external_apis_allowed=organisation.external_apis_allowed,
        local_only_enforced=organisation.local_only_enforced,
        retention_days=organisation.retention_days,
        role_code=role_code,
        is_current=is_current,
    )


def _unique_slug(db: Session, name: str, exclude_id: uuid.UUID | None = None) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:100] or "organisation"
    slug = base
    suffix = 2
    while True:
        query = select(Organisation).where(Organisation.slug == slug)
        if exclude_id is not None:
            query = query.where(Organisation.id != exclude_id)
        if db.scalar(query) is None:
            return slug
        slug = f"{base}-{suffix}"
        suffix += 1
