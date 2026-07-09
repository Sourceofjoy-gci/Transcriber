import base64
import importlib
import os
import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

os.environ.setdefault("APP_SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "a-very-safe-bootstrap-password-1")

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app.db import session as session_module  # noqa: E402
from app.db.base import Base  # noqa: E402

engine = create_engine(
    "sqlite+pysqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Base.metadata.create_all(engine)

importlib.reload(session_module)
session_module.engine = engine
session_module.SessionLocal = session_module.sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
)

import app.api.router  # noqa: E402
import app.api.routes.auth  # noqa: E402
import app.api.routes.users  # noqa: E402
import app.main  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402

for mod in (
    app.services.bootstrap,
    app.services.authorization,
    app.api.routes.auth,
    app.api.routes.users,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.main import app  # noqa: E402
from app.services.bootstrap import bootstrap_initial_admin  # noqa: E402


@pytest.fixture()
def client() -> TestClient:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    from app.core import rate_limit

    rate_limit.limiter.reset()
    with session_module.SessionLocal() as session:
        bootstrap_initial_admin(session, get_settings())
    return TestClient(app)


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@example.com", "password": "a-very-safe-bootstrap-password-1"},
    )
    assert response.status_code == 200, response.text
    csrf = response.json()["csrf_token"]
    client.cookies.set("csrf_token", csrf)
    return csrf


def test_role_crud_and_permission_assignment(client: TestClient) -> None:
    csrf = _login(client)

    permissions = client.get("/api/v1/roles/permissions")
    assert permissions.status_code == 200, permissions.text
    permission_codes = {item["code"] for item in permissions.json()}
    assert {"assets.read", "transcripts.read"}.issubset(permission_codes)

    created = client.post(
        "/api/v1/roles",
        headers={"X-CSRF-Token": csrf},
        json={
            "code": "legal_reviewer",
            "name": "Legal Reviewer",
            "permission_codes": ["assets.read", "transcripts.read"],
        },
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["code"] == "legal_reviewer"
    assert role["is_system"] is False
    assert set(role["permissions"]) == {"assets.read", "transcripts.read"}

    listed = client.get("/api/v1/roles")
    assert listed.status_code == 200
    assert any(item["code"] == "legal_reviewer" for item in listed.json())

    patched = client.patch(
        f"/api/v1/roles/{role['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Legal Read Only", "permission_codes": ["assets.read"]},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Legal Read Only"
    assert patched.json()["permissions"] == ["assets.read"]

    deleted = client.delete(f"/api/v1/roles/{role['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 204, deleted.text
    assert not any(item["code"] == "legal_reviewer" for item in client.get("/api/v1/roles").json())


def test_system_roles_are_protected_from_mutation(client: TestClient) -> None:
    csrf = _login(client)
    roles_response = client.get("/api/v1/roles")
    assert roles_response.status_code == 200, roles_response.text
    roles = roles_response.json()
    system_role = next(item for item in roles if item["code"] == "standard_user")

    patched = client.patch(
        f"/api/v1/roles/{system_role['id']}",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Changed"},
    )
    assert patched.status_code == 409

    deleted = client.delete(f"/api/v1/roles/{system_role['id']}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 409
