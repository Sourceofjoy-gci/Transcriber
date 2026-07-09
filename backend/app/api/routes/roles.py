import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import OrganisationMembership, Permission, Role, role_permissions
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/roles", tags=["roles"])
DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[Principal, Depends(require_permission("users.manage"))]


class PermissionResponse(BaseModel):
    id: uuid.UUID
    code: str
    description: str


class RoleResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_system: bool
    permissions: list[str]


class RoleCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100, pattern="^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1, max_length=150)
    permission_codes: list[str] = Field(default_factory=list)


class RoleUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    permission_codes: list[str] | None = None


@router.get("/permissions", response_model=list[PermissionResponse])
def list_permissions(principal: Manager, db: DbSession) -> list[Permission]:
    return list(db.scalars(select(Permission).order_by(Permission.code)))


@router.get("", response_model=list[RoleResponse])
def list_roles(principal: Manager, db: DbSession) -> list[RoleResponse]:
    roles = list(
        db.scalars(
            select(Role)
            .where((Role.organisation_id == principal.organisation.id) | Role.organisation_id.is_(None))
            .order_by(Role.code)
        )
    )
    return [_role_response(db, role) for role in roles]


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreateRequest, request: Request, principal: Manager, db: DbSession
) -> RoleResponse:
    existing = db.scalar(
        select(Role).where(
            Role.organisation_id == principal.organisation.id,
            Role.code == payload.code,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role code already exists")
    permissions = _permissions_by_code(db, payload.permission_codes)
    role = Role(
        organisation_id=principal.organisation.id,
        code=payload.code,
        name=payload.name,
        is_system=False,
    )
    db.add(role)
    db.flush()
    _replace_permissions(db, role, permissions)
    write_audit(db, principal, "role.created", "role", role.id, "success", request)
    db.commit()
    db.refresh(role)
    return _role_response(db, role)


@router.patch("/{role_id}", response_model=RoleResponse)
def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdateRequest,
    request: Request,
    principal: Manager,
    db: DbSession,
) -> RoleResponse:
    role = _role_or_404(db, principal, role_id)
    _ensure_mutable(role)
    if payload.name is not None:
        role.name = payload.name
    if payload.permission_codes is not None:
        _replace_permissions(db, role, _permissions_by_code(db, payload.permission_codes))
    write_audit(db, principal, "role.updated", "role", role.id, "success", request)
    db.commit()
    db.refresh(role)
    return _role_response(db, role)


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(role_id: uuid.UUID, request: Request, principal: Manager, db: DbSession) -> None:
    role = _role_or_404(db, principal, role_id)
    _ensure_mutable(role)
    membership = db.scalar(select(OrganisationMembership).where(OrganisationMembership.role_id == role.id))
    if membership is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role is assigned to users")
    db.execute(delete(role_permissions).where(role_permissions.c.role_id == role.id))
    write_audit(db, principal, "role.deleted", "role", role.id, "success", request)
    db.delete(role)
    db.commit()


def _role_or_404(db: Session, principal: Principal, role_id: uuid.UUID) -> Role:
    role = db.scalar(
        select(Role).where(
            Role.id == role_id,
            Role.organisation_id == principal.organisation.id,
        )
    )
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return role


def _ensure_mutable(role: Role) -> None:
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System roles cannot be modified")


def _permissions_by_code(db: Session, codes: list[str]) -> list[Permission]:
    if not codes:
        return []
    permissions = list(db.scalars(select(Permission).where(Permission.code.in_(codes))))
    found = {permission.code for permission in permissions}
    missing = sorted(set(codes) - found)
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown permissions: {missing}",
        )
    return sorted(permissions, key=lambda permission: permission.code)


def _replace_permissions(db: Session, role: Role, permissions: list[Permission]) -> None:
    db.execute(delete(role_permissions).where(role_permissions.c.role_id == role.id))
    for permission in permissions:
        db.execute(role_permissions.insert().values(role_id=role.id, permission_id=permission.id))


def _role_response(db: Session, role: Role) -> RoleResponse:
    permissions = list(
        db.scalars(
            select(Permission.code)
            .join(role_permissions, role_permissions.c.permission_id == Permission.id)
            .where(role_permissions.c.role_id == role.id)
            .order_by(Permission.code)
        )
    )
    return RoleResponse(
        id=role.id,
        code=role.code,
        name=role.name,
        is_system=role.is_system,
        permissions=permissions,
    )
