import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings


def encrypt_secret(settings: Settings, value: str) -> tuple[str, str]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_key(settings)).encrypt(nonce, value.encode("utf-8"), None)
    return _encode(ciphertext), _encode(nonce)


def decrypt_secret(settings: Settings, ciphertext: str, nonce: str) -> str:
    return AESGCM(_key(settings)).decrypt(_decode(nonce), _decode(ciphertext), None).decode("utf-8")


def _key(settings: Settings) -> bytes:
    try:
        key = _decode(settings.credential_encryption_key)
    except ValueError as error:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must be URL-safe base64") from error
    if len(key) != 32:
        raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY must decode to exactly 32 bytes")
    return key


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def _decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
