from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.db.session import get_db
from app.models.domain import (
    MembershipStatus,
    OrganisationMembership,
    Permission,
    Role,
    User,
    role_permissions,
)
from app.services.audit import write_audit
from app.services.authorization import Principal, require_permission

router = APIRouter(prefix="/users", tags=["users"])
DbSession = Annotated[Session, Depends(get_db)]
Manager = Annotated[Principal, Depends(require_permission("users.manage"))]


class UserSummary(BaseModel):
    id: str
    email: EmailStr
    display_name: str
    is_active: bool
    last_login_at: datetime | None


class MembershipSummary(BaseModel):
    id: str
    user_id: str
    organisation_id: str
    role_id: str
    role_code: str
    status: str
    created_at: datetime


class UserCreateRequest(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=256)
    role_code: str = Field(default="standard_user")


class UserUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=200)
    is_active: bool | None = None
    role_code: str | None = None


def _user_to_summary(user: User) -> UserSummary:
    return UserSummary(
        id=str(user.id),
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        last_login_at=user.last_login_at,
    )


@router.get("", response_model=list[UserSummary])
def list_users(principal: Manager, db: DbSession, limit: int = 100):
    if limit < 1 or limit > 500:
        limit = 100
    # Show users who share any organisation with the caller
    memberships = list(
        db.scalars(
            select(OrganisationMembership).where(
                OrganisationMembership.organisation_id == principal.organisation.id
            )
        )
    )
    user_ids = {membership.user_id for membership in memberships}
    users = (
        list(db.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.email).limit(limit)))
        if user_ids
        else []
    )
    return [_user_to_summary(user) for user in users]


@router.get("/roles", response_model=list[dict])
def list_roles(principal: Manager, db: DbSession):
    rows = list(
        db.execute(
            select(Role, Permission)
            .join(role_permissions, role_permissions.c.role_id == Role.id, isouter=True)
            .join(Permission, Permission.id == role_permissions.c.permission_id, isouter=True)
            .where((Role.organisation_id == principal.organisation.id) | Role.organisation_id.is_(None))
            .order_by(Role.code)
        )
    )
    roles: dict[str, dict] = {}
    for role, permission in rows:
        entry = roles.setdefault(
            str(role.id), {"id": str(role.id), "code": role.code, "name": role.name, "permissions": []}
        )
        if permission is not None:
            entry["permissions"].append(permission.code)
    return list(roles.values())


@router.get("/memberships", response_model=list[MembershipSummary])
def list_memberships(principal: Manager, db: DbSession):
    rows = list(
        db.execute(
            select(OrganisationMembership, Role)
            .join(Role, Role.id == OrganisationMembership.role_id)
            .where(OrganisationMembership.organisation_id == principal.organisation.id)
            .order_by(OrganisationMembership.created_at)
        )
    )
    return [
        MembershipSummary(
            id=str(membership.id),
            user_id=str(membership.user_id),
            organisation_id=str(membership.organisation_id),
            role_id=str(membership.role_id),
            role_code=role.code,
            status=membership.status.value,
            created_at=membership.created_at,
        )
        for membership, role in rows
    ]


@router.post("", response_model=UserSummary, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreateRequest, request: Request, principal: Manager, db: DbSession):
    existing = db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    role = db.scalar(
        select(Role).where(Role.code == payload.role_code, Role.organisation_id == principal.organisation.id)
    )
    if role is None:
        raise HTTPException(status_code=422, detail="Unknown role")
    user = User(
        email=payload.email.lower(),
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    db.flush()
    db.add(
        OrganisationMembership(
            organisation_id=principal.organisation.id,
            user_id=user.id,
            role_id=role.id,
            status=MembershipStatus.active,
        )
    )
    write_audit(
        db,
        principal,
        "user.created",
        "user",
        user.id,
        "success",
        request,
        {"email": user.email, "role": role.code},
    )
    db.commit()
    db.refresh(user)
    return _user_to_summary(user)


@router.patch("/{user_id}", response_model=UserSummary)
def update_user(
    user_id: str, payload: UserUpdateRequest, request: Request, principal: Manager, db: DbSession
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    membership = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.organisation_id == principal.organisation.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="User is not a member of this organisation")
    if payload.display_name is not None:
        user.display_name = payload.display_name
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.role_code is not None:
        role = db.scalar(
            select(Role).where(
                Role.code == payload.role_code, Role.organisation_id == principal.organisation.id
            )
        )
        if role is None:
            raise HTTPException(status_code=422, detail="Unknown role")
        membership.role_id = role.id
    write_audit(db, principal, "user.updated", "user", user.id, "success", request)
    db.commit()
    db.refresh(user)
    return _user_to_summary(user)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_user(user_id: str, request: Request, principal: Manager, db: DbSession):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    membership = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.user_id == user.id,
            OrganisationMembership.organisation_id == principal.organisation.id,
        )
    )
    if membership is None:
        raise HTTPException(status_code=403, detail="User is not a member of this organisation")
    user.is_active = False
    membership.status = MembershipStatus.suspended
    write_audit(db, principal, "user.deactivated", "user", user.id, "success", request)
    db.commit()
