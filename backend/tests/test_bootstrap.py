from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import Base
from app.models.domain import (
    Organisation,
    OrganisationMembership,
    Permission,
    Role,
    User,
    role_permissions,
)
from app.services.bootstrap import PERMISSIONS, bootstrap_initial_admin


def test_bootstrap_creates_administrator_with_system_role() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    settings = Settings(
        app_secret_key="test-secret-key-that-is-long-enough-for-jwt",
        database_url="sqlite+pysqlite://",
        redis_url="redis://localhost:6379/15",
        credential_encryption_key="test-credential-encryption-key-12345",
        bootstrap_admin_email="admin@example.test",
        bootstrap_admin_password="a-safe-bootstrap-password",
    )

    with Session(engine) as session:
        bootstrap_initial_admin(session, settings)

        user = session.scalar(select(User).where(User.email == "admin@example.test"))
        assert user is not None
        membership = session.scalar(
            select(OrganisationMembership).where(OrganisationMembership.user_id == user.id)
        )
        assert membership is not None
        role = session.get(Role, membership.role_id)
        granted = set(
            session.scalars(
                select(Permission.code)
                .join(role_permissions, Permission.id == role_permissions.c.permission_id)
                .where(role_permissions.c.role_id == role.id)
            )
        )

    assert role.code == "system_administrator"
    assert granted == set(PERMISSIONS)


def test_bootstrap_reuses_existing_organisation_when_admin_email_changes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    first_settings = Settings(
        app_secret_key="test-secret-key-that-is-long-enough-for-jwt",
        database_url="sqlite+pysqlite://",
        redis_url="redis://localhost:6379/15",
        credential_encryption_key="test-credential-encryption-key-12345",
        bootstrap_admin_email="first-admin@example.test",
        bootstrap_admin_password="a-safe-bootstrap-password",
    )
    second_settings = Settings(
        app_secret_key="test-secret-key-that-is-long-enough-for-jwt",
        database_url="sqlite+pysqlite://",
        redis_url="redis://localhost:6379/15",
        credential_encryption_key="test-credential-encryption-key-12345",
        bootstrap_admin_email="second-admin@example.test",
        bootstrap_admin_password="another-safe-bootstrap-password",
    )

    with Session(engine) as session:
        bootstrap_initial_admin(session, first_settings)
        bootstrap_initial_admin(session, second_settings)

        organisation_count = session.scalar(select(func.count()).select_from(Organisation))
        second_user = session.scalar(select(User).where(User.email == "second-admin@example.test"))
        assert second_user is not None
        membership = session.scalar(
            select(OrganisationMembership).where(OrganisationMembership.user_id == second_user.id)
        )
        assert membership is not None
        role = session.get(Role, membership.role_id)

    assert organisation_count == 1
    assert role is not None
    assert role.code == "system_administrator"
