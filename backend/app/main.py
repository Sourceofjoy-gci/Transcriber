import hmac
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import bind_log_context, clear_log_context, configure_logging
from app.core.metrics import monotonic_time, runtime_metrics
from app.db.session import SessionLocal
from app.services.bootstrap import bootstrap_initial_admin
from app.services.model_catalog import seed_model_catalog
from app.services.report_templates import seed_report_templates

settings = get_settings()
configure_logging(settings.log_format)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        request.state.request_id = request_id
        bind_log_context(request_id=request_id)
        started = monotonic_time()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            runtime_metrics.record_http_request(response.status_code, monotonic_time() - started)
            return response
        finally:
            clear_log_context()


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        requires_check = request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith(
            "/api/v1/"
        )
        # CSRF only applies to cookie-authenticated sessions and never to the
        # login endpoint (which is how the cookies are issued in the first place).
        is_login = request.url.path == "/api/v1/auth/login"
        has_session_cookie = bool(request.cookies.get("access_token") or request.cookies.get("refresh_token"))
        if requires_check and not is_login and has_session_cookie:
            cookie_token = request.cookies.get("csrf_token")
            header_token = request.headers.get("X-CSRF-Token")
            if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
                return JSONResponse(status_code=403, content={"detail": "CSRF validation failed"})
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    with SessionLocal() as session:
        bootstrap_initial_admin(session, settings)
        seed_model_catalog(session)
        seed_report_templates(session)
    yield


app = FastAPI(title="Transcriber Platform API", version="0.1.0", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", "X-Organisation-ID", "X-Request-ID"],
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def ready() -> dict[str, str]:
    with SessionLocal() as session:
        session.execute(text("SELECT 1"))
    return {"status": "ready"}
