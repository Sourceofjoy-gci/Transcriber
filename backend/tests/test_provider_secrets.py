"""Tests for provider secret encryption helpers."""

import base64
import secrets

from app.core.config import Settings
from app.services.provider_secrets import decrypt_secret, encrypt_secret


def _settings() -> Settings:
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    return Settings(
        app_secret_key="a" * 64,
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
        credential_encryption_key=key,
    )


def test_encryption_roundtrip() -> None:
    settings = _settings()
    ciphertext, nonce = encrypt_secret(settings, "super-secret-key")
    assert ciphertext and nonce
    assert decrypt_secret(settings, ciphertext, nonce) == "super-secret-key"


def test_encryption_produces_unique_nonces() -> None:
    settings = _settings()
    ciphertext_one, nonce_one = encrypt_secret(settings, "value")
    ciphertext_two, nonce_two = encrypt_secret(settings, "value")
    assert ciphertext_one != ciphertext_two
    assert nonce_one != nonce_two


def test_short_key_is_rejected() -> None:
    settings = _settings()
    settings.credential_encryption_key = "too-short"
    try:
        encrypt_secret(settings, "value")
    except RuntimeError:
        return
    raise AssertionError("RuntimeError expected for short encryption key")
