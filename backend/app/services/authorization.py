import hmac
import uuid
from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import decode_token
from app.db.session import get_db
from app.models.domain import (
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    Permission,
    Role,
    User,
    role_permissions,
)


@dataclass(frozen=True)
class Principal:
    user: User
    organisation: Organisation
    membership: OrganisationMembership
    role: Role


DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def get_principal(
    request: Request,
    db: DbSession,
    settings: SettingsDependency,
    x_organisation_id: Annotated[str | None, Header()] = None,
) -> Principal:
    token = _read_access_token(request)
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication is required")
    try:
        user_id = decode_token(settings, token, "access")
    except (jwt.InvalidTokenError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session"
        ) from error

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")

    memberships = list(
        db.scalars(
            select(OrganisationMembership)
            .where(
                OrganisationMembership.user_id == user.id,
                OrganisationMembership.status == MembershipStatus.active,
            )
            .order_by(OrganisationMembership.created_at)
        )
    )
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active organisation membership")

    if x_organisation_id:
        try:
            requested_organisation_id = uuid.UUID(x_organisation_id)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid organisation header"
            ) from error
        membership = next(
            (item for item in memberships if item.organisation_id == requested_organisation_id), None
        )
        if membership is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organisation access denied")
    else:
        membership = memberships[0]

    organisation = db.get(Organisation, membership.organisation_id)
    role = db.get(Role, membership.role_id)
    if organisation is None or role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Membership configuration is unavailable"
        )
    return Principal(user=user, organisation=organisation, membership=membership, role=role)


def require_permission(permission_code: str):
    def dependency(principal: Annotated[Principal, Depends(get_principal)], db: DbSession) -> Principal:
        allowed = db.scalar(
            select(role_permissions.c.role_id)
            .join(Permission, Permission.id == role_permissions.c.permission_id)
            .where(role_permissions.c.role_id == principal.role.id, Permission.code == permission_code)
        )
        if allowed is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
        return principal

    return dependency


def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or not _safe_equals(cookie_token, header_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def _read_access_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token
    return request.cookies.get("access_token")


def _safe_equals(first: str, second: str) -> bool:
    return hmac.compare_digest(first, second)
