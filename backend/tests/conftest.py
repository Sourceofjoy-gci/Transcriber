import base64
import os
import secrets

os.environ.setdefault("APP_SECRET_KEY", "test-secret-key-that-is-long-enough-for-jwt")
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite://")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("RATE_LIMIT_STORAGE", "memory")
# 32-byte URL-safe base64 secret for tests
_test_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
os.environ.setdefault("CREDENTIAL_ENCRYPTION_KEY", _test_key)
