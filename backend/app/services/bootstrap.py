import re
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models.domain import (
    MembershipStatus,
    Organisation,
    OrganisationMembership,
    Permission,
    Role,
    User,
    role_permissions,
)

PERMISSIONS = {
    "dashboard.read": "View organisation dashboard",
    "assets.create": "Upload media files",
    "assets.read": "View media files",
    "assets.delete": "Delete media files",
    "jobs.create": "Create transcription jobs",
    "jobs.read": "View transcription jobs",
    "jobs.cancel": "Cancel transcription jobs",
    "transcripts.read": "View transcripts",
    "transcripts.edit": "Edit transcripts",
    "exports.create": "Create transcript and report exports",
    "reports.read": "View reports",
    "reports.manage": "Manage reports and templates",
    "models.manage": "Manage local models",
    "providers.manage": "Manage API providers",
    "users.manage": "Manage users and memberships",
    "settings.manage": "Manage organisation settings",
    "storage.manage": "Manage storage and retention",
    "audit.read": "View audit events",
}

ROLE_CODES = {
    "system_administrator": tuple(PERMISSIONS),
    "organisation_administrator": tuple(code for code in PERMISSIONS if code != "models.manage"),
    "transcription_manager": (
        "dashboard.read",
        "assets.create",
        "assets.read",
        "assets.delete",
        "jobs.create",
        "jobs.read",
        "jobs.cancel",
        "transcripts.read",
        "transcripts.edit",
        "exports.create",
        "reports.read",
    ),
    "reviewer": (
        "dashboard.read",
        "assets.read",
        "jobs.read",
        "transcripts.read",
        "transcripts.edit",
        "exports.create",
        "reports.read",
    ),
    "standard_user": (
        "assets.create",
        "assets.read",
        "jobs.create",
        "jobs.read",
        "transcripts.read",
        "exports.create",
        "reports.read",
    ),
    "read_only_user": ("dashboard.read", "assets.read", "jobs.read", "transcripts.read", "reports.read"),
}


def bootstrap_initial_admin(db: Session, settings: Settings) -> None:
    _ensure_permissions(db)
    if not settings.bootstrap_admin_email or not settings.bootstrap_admin_password:
        db.commit()
        return

    email = settings.bootstrap_admin_email.lower()
    organisation = _get_or_create_bootstrap_organisation(db, settings)
    roles = _ensure_organisation_roles(db, organisation)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(settings.bootstrap_admin_password),
            display_name="System Administrator",
        )
        db.add(user)
        db.flush()
    _ensure_admin_membership(db, organisation, user, roles["system_administrator"])
    db.commit()


def _get_or_create_bootstrap_organisation(db: Session, settings: Settings) -> Organisation:
    slug = _slugify(settings.bootstrap_organisation_name)
    organisation = db.scalar(select(Organisation).where(Organisation.slug == slug))
    if organisation is not None:
        return organisation

    organisation = Organisation(
        name=settings.bootstrap_organisation_name,
        slug=slug,
        external_apis_allowed=settings.external_apis_allowed,
        local_only_enforced=settings.local_only_enforced,
    )
    db.add(organisation)
    db.flush()
    return organisation


def _ensure_admin_membership(db: Session, organisation: Organisation, user: User, role: Role) -> None:
    membership = db.scalar(
        select(OrganisationMembership).where(
            OrganisationMembership.organisation_id == organisation.id,
            OrganisationMembership.user_id == user.id,
        )
    )
    if membership is None:
        db.add(OrganisationMembership(organisation_id=organisation.id, user_id=user.id, role_id=role.id))
        return

    membership.role_id = role.id
    membership.status = MembershipStatus.active


def create_organisation_roles(db: Session, organisation: Organisation) -> dict[str, Role]:
    _ensure_permissions(db)
    roles = _ensure_organisation_roles(db, organisation)
    db.commit()
    return roles


def _ensure_permissions(db: Session) -> None:
    existing = {permission.code: permission for permission in db.scalars(select(Permission))}
    for code, description in PERMISSIONS.items():
        if code not in existing:
            db.add(Permission(code=code, description=description))
    db.flush()


def _ensure_organisation_roles(db: Session, organisation: Organisation) -> dict[str, Role]:
    permissions_by_code = {permission.code: permission for permission in db.scalars(select(Permission))}
    roles = {
        role.code: role for role in db.scalars(select(Role).where(Role.organisation_id == organisation.id))
    }
    for code, granted_permissions in ROLE_CODES.items():
        role = roles.get(code)
        role_name = code.replace("_", " ").title()
        if role is None:
            role = Role(
                organisation_id=organisation.id,
                code=code,
                name=role_name,
                is_system=True,
            )
            db.add(role)
            db.flush()
            roles[code] = role
        else:
            role.name = role_name
            role.is_system = True
        _assign_permissions(
            db,
            role,
            (permissions_by_code[permission_code] for permission_code in granted_permissions),
        )
    return roles


def _assign_permissions(db: Session, role: Role, permissions: Iterable[Permission]) -> None:
    existing_permission_ids = set(
        db.scalars(select(role_permissions.c.permission_id).where(role_permissions.c.role_id == role.id))
    )
    for permission in permissions:
        if permission.id in existing_permission_ids:
            continue
        db.execute(role_permissions.insert().values(role_id=role.id, permission_id=permission.id))


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:110] or "organisation"
