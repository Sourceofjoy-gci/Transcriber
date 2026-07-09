from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

import jwt
from pwdlib import PasswordHash

from app.core.config import Settings

_password_hash = PasswordHash.recommended()
_JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def create_access_token(settings: Settings, user_id: UUID) -> str:
    return _create_token(settings, user_id, "access", timedelta(minutes=settings.access_token_ttl_minutes))


def create_refresh_token(settings: Settings, user_id: UUID) -> tuple[str, datetime]:
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days)
    token = _create_token(settings, user_id, "refresh", expires_at - datetime.now(UTC))
    return token, expires_at


def decode_token(settings: Settings, token: str, token_type: str) -> UUID:
    payload = jwt.decode(token, settings.app_secret_key, algorithms=[_JWT_ALGORITHM])
    if payload.get("type") != token_type:
        raise jwt.InvalidTokenError("Unexpected token type")
    return UUID(payload["sub"])


def hash_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_csrf_token() -> str:
    return token_urlsafe(32)


def _create_token(settings: Settings, user_id: UUID, token_type: str, lifetime: timedelta) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "type": token_type,
            "iat": now,
            "exp": now + lifetime,
            "jti": token_urlsafe(16),
        },
        settings.app_secret_key,
        algorithm=_JWT_ALGORITHM,
    )
