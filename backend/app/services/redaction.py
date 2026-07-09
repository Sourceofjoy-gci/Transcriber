from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "refresh_token",
    "secret",
    "token",
)

_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_\-]{6,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(api[_-]?key|token|secret|password)=([^&\s]+)", re.IGNORECASE),
)


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if any(part in key_text for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_sensitive_data(item)
        return redacted
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [redact_sensitive_data(item) for item in value]
    return value


def redact_sensitive_text(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_replace_secret_match, redacted)
    return redacted


def _replace_secret_match(match: re.Match[str]) -> str:
    if match.lastindex and match.lastindex >= 2:
        return f"{match.group(1)}={REDACTED}"
    if match.group(0).lower().startswith("bearer "):
        return f"Bearer {REDACTED}"
    return REDACTED
