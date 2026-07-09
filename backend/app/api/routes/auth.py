from datetime import UTC, datetime
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.rate_limit import rate_limit
from app.core.security import (
    create_access_token,
    create_csrf_token,
    create_refresh_token,
    decode_token,
    hash_token,
    verify_password,
)
from app.db.session import get_db
from app.models.domain import MembershipStatus, OrganisationMembership, RefreshToken, Role, User
from app.schemas.auth import LoginRequest, LogoutResponse, MembershipSummary, SessionResponse, UserSummary
from app.services.audit import write_audit
from app.services.authorization import Principal, get_principal, require_csrf

router = APIRouter(prefix="/auth", tags=["authentication"])
DbSession = Annotated[Session, Depends(get_db)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


class ProfileUpdateRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)


@router.post(
    "/login",
    response_model=SessionResponse,
    dependencies=[Depends(rate_limit("login", get_settings().rate_limit_login))],
)
def login(
    payload: LoginRequest, response: Response, db: DbSession, settings: SettingsDependency
) -> SessionResponse:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    memberships = _get_memberships(db, user.id)
    if not memberships:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No active organisation membership")

    refresh_token, expires_at = create_refresh_token(settings, user.id)
    db.add(RefreshToken(user_id=user.id, token_hash=hash_token(refresh_token), expires_at=expires_at))
    user.last_login_at = datetime.now(UTC)
    db.commit()

    csrf_token = create_csrf_token()
    _set_session_cookies(
        response, settings, create_access_token(settings, user.id), refresh_token, csrf_token
    )
    return _session_response(user, memberships, csrf_token)


@router.post("/refresh", response_model=SessionResponse, dependencies=[Depends(require_csrf)])
def refresh(
    request: Request, response: Response, db: DbSession, settings: SettingsDependency
) -> SessionResponse:
    token = request.cookies.get("refresh_token")
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session is required")
    try:
        user_id = decode_token(settings, token, "refresh")
    except (jwt.InvalidTokenError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh session"
        ) from error

    stored_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))
    if (
        stored_token is None
        or stored_token.revoked_at is not None
        or stored_token.expires_at <= datetime.now(UTC)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh session has expired")
    user = db.get(User, user_id)
    if user is None or not user.is_active or stored_token.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is unavailable")

    memberships = _get_memberships(db, user.id)
    refresh_token, expires_at = create_refresh_token(settings, user.id)
    replacement = RefreshToken(user_id=user.id, token_hash=hash_token(refresh_token), expires_at=expires_at)
    db.add(replacement)
    db.flush()
    stored_token.revoked_at = datetime.now(UTC)
    stored_token.replaced_by_id = replacement.id
    db.commit()

    csrf_token = create_csrf_token()
    _set_session_cookies(
        response, settings, create_access_token(settings, user.id), refresh_token, csrf_token
    )
    return _session_response(user, memberships, csrf_token)


@router.post("/logout", response_model=LogoutResponse, dependencies=[Depends(require_csrf)])
def logout(request: Request, response: Response, db: DbSession) -> LogoutResponse:
    token = request.cookies.get("refresh_token")
    revoked_at = datetime.now(UTC)
    if token:
        stored_token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(token)))
        if stored_token and stored_token.revoked_at is None:
            stored_token.revoked_at = revoked_at
            db.commit()
    for cookie_name in ("access_token", "refresh_token", "csrf_token"):
        response.delete_cookie(cookie_name, path="/")
    return LogoutResponse(revoked_at=revoked_at)


@router.get("/me", response_model=SessionResponse)
def get_me(
    principal: Annotated[Principal, Depends(get_principal)], db: DbSession, request: Request
) -> SessionResponse:
    return _session_response(
        principal.user, _get_memberships(db, principal.user.id), request.cookies.get("csrf_token", "")
    )


@router.patch("/me/profile", response_model=UserSummary, dependencies=[Depends(require_csrf)])
def update_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
    db: DbSession,
) -> UserSummary:
    principal.user.display_name = payload.display_name
    write_audit(db, principal, "profile.updated", "user", principal.user.id, "success", request)
    db.commit()
    db.refresh(principal.user)
    return UserSummary.model_validate(principal.user)


def _get_memberships(db: Session, user_id) -> list[tuple[OrganisationMembership, Role]]:
    return list(
        db.execute(
            select(OrganisationMembership, Role)
            .join(Role, Role.id == OrganisationMembership.role_id)
            .where(
                OrganisationMembership.user_id == user_id,
                OrganisationMembership.status == MembershipStatus.active,
            )
            .order_by(OrganisationMembership.created_at)
        )
    )


def _session_response(
    user: User, memberships: list[tuple[OrganisationMembership, Role]], csrf_token: str
) -> SessionResponse:
    return SessionResponse(
        user=UserSummary.model_validate(user),
        memberships=[
            MembershipSummary(
                organisation_id=membership.organisation_id,
                role_code=role.code,
                status=membership.status.value,
            )
            for membership, role in memberships
        ],
        csrf_token=csrf_token,
    )


def _set_session_cookies(
    response: Response, settings: Settings, access_token: str, refresh_token: str, csrf_token: str
) -> None:
    secure = settings.is_production
    response.set_cookie(
        "access_token",
        access_token,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "refresh_token",
        refresh_token,
        max_age=settings.refresh_token_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie("csrf_token", csrf_token, httponly=False, secure=secure, samesite="lax", path="/")
