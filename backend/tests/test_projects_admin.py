import base64
import importlib
import os
import secrets
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool

_TEST_KEY = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")

os.environ.setdefault("APP_SECRET_KEY", "a" * 64)
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
os.environ.setdefault("BOOTSTRAP_ADMIN_PASSWORD", "a-very-safe-bootstrap-password-1")
os.environ.setdefault("EXTERNAL_APIS_ALLOWED", "true")
os.environ.setdefault("LOCAL_ONLY_ENFORCED", "false")

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
import app.api.routes.assets  # noqa: E402
import app.api.routes.auth  # noqa: E402
import app.api.routes.projects  # noqa: E402
import app.api.routes.settings  # noqa: E402
import app.main  # noqa: E402
import app.services.authorization  # noqa: E402
import app.services.bootstrap  # noqa: E402
import app.services.media  # noqa: E402

for mod in (
    app.services.media,
    app.services.bootstrap,
    app.services.authorization,
    app.api.routes.assets,
    app.api.routes.auth,
    app.api.routes.projects,
    app.api.routes.settings,
    app.api.router,
    app.main,
):
    importlib.reload(mod)

from app.main import app  # noqa: E402
from app.models.domain import AssetStatus, MediaAsset, Organisation, User  # noqa: E402
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


def test_project_detail_update_delete_and_asset_filters(client: TestClient) -> None:
    csrf = _login(client)

    created = client.post(
        "/api/v1/projects",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Legal Discovery", "description": "Case audio", "sensitivity": "restricted"},
    )
    assert created.status_code == 201, created.text
    project_id = created.json()["id"]
    project_uuid = UUID(project_id)

    fetched = client.get(f"/api/v1/projects/{project_id}")
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Legal Discovery"

    patched = client.patch(
        f"/api/v1/projects/{project_id}",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Legal Discovery 2026", "retention_days": 365, "external_apis_allowed": False},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "Legal Discovery 2026"
    assert patched.json()["retention_days"] == 365

    with session_module.SessionLocal() as db:
        org = db.scalar(select(Organisation))
        user = db.scalar(select(User).where(User.email == "admin@example.com"))
        assert org is not None and user is not None
        first = MediaAsset(
            organisation_id=org.id,
            project_id=project_uuid,
            uploaded_by_id=user.id,
            original_filename="meeting-alpha.wav",
            content_type="audio/wav",
            byte_size=100,
            sha256="a" * 64,
            storage_key="organisations/org/assets/meeting-alpha.wav",
            status=AssetStatus.ready,
        )
        second = MediaAsset(
            organisation_id=org.id,
            uploaded_by_id=user.id,
            original_filename="meeting-loose.wav",
            content_type="audio/wav",
            byte_size=100,
            sha256="b" * 64,
            storage_key="organisations/org/assets/meeting-loose.wav",
            status=AssetStatus.ready,
        )
        db.add_all([first, second])
        db.commit()
        first_id = str(first.id)
        first_uuid = first.id

    filtered = client.get(
        "/api/v1/assets",
        params={"project_id": project_id, "status": "ready", "q": "meeting"},
    )
    assert filtered.status_code == 200, filtered.text
    assert [item["id"] for item in filtered.json()["items"]] == [first_id]

    deleted = client.delete(f"/api/v1/projects/{project_id}", headers={"X-CSRF-Token": csrf})
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404

    with session_module.SessionLocal() as db:
        leftover = db.get(MediaAsset, first_uuid)
        assert leftover is not None
        assert leftover.project_id is None


def test_profile_organisation_and_structured_settings(client: TestClient) -> None:
    csrf = _login(client)

    profile = client.patch(
        "/api/v1/auth/me/profile",
        headers={"X-CSRF-Token": csrf},
        json={"display_name": "Ops Lead"},
    )
    assert profile.status_code == 200, profile.text
    assert profile.json()["display_name"] == "Ops Lead"
    assert client.get("/api/v1/auth/me").json()["user"]["display_name"] == "Ops Lead"

    orgs = client.get("/api/v1/organisations")
    assert orgs.status_code == 200, orgs.text
    assert orgs.json()[0]["name"] == "Local Organisation"

    created_org = client.post(
        "/api/v1/organisations",
        headers={"X-CSRF-Token": csrf},
        json={"name": "Research Division", "retention_days": 90, "external_apis_allowed": True},
    )
    assert created_org.status_code == 201, created_org.text
    organisation_id = created_org.json()["id"]

    patched_org = client.patch(
        f"/api/v1/organisations/{organisation_id}",
        headers={"X-CSRF-Token": csrf, "X-Organisation-ID": organisation_id},
        json={"name": "Research Division Archive", "local_only_enforced": True},
    )
    assert patched_org.status_code == 200, patched_org.text
    assert patched_org.json()["name"] == "Research Division Archive"
    assert patched_org.json()["local_only_enforced"] is True

    structured = client.put(
        "/api/v1/settings/structured",
        headers={"X-CSRF-Token": csrf, "X-Organisation-ID": organisation_id},
        json={
            "organisation": {
                "retention_days": 120,
                "external_apis_allowed": False,
                "local_only_enforced": True,
            },
            "upload": {"max_upload_bytes": 104857600},
            "queue": {"max_concurrent_jobs": 2},
            "ai": {"default_report_template_kind": "executive_summary"},
        },
    )
    assert structured.status_code == 200, structured.text
    body = structured.json()
    assert body["organisation"]["retention_days"] == 120
    assert body["upload"]["max_upload_bytes"] == 104857600
    assert body["queue"]["max_concurrent_jobs"] == 2
    assert body["ai"]["default_report_template_kind"] == "executive_summary"

    secret = client.put(
        "/api/v1/settings",
        headers={"X-CSRF-Token": csrf},
        json={"key": "raw_secret", "value": {"value": "secret"}, "is_secret": True},
    )
    assert secret.status_code == 400
    assert "secret" in secret.json()["detail"].lower()
