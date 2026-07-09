import uuid

from app.core.config import Settings
from app.core.security import create_refresh_token, decode_token


def test_refresh_tokens_are_unique_for_same_user() -> None:
    settings = Settings(
        app_secret_key="a" * 64,
        credential_encryption_key="b" * 44,
        database_url="sqlite+pysqlite:///:memory:",
        redis_url="redis://localhost:6379/15",
    )
    user_id = uuid.uuid4()

    first_token, _ = create_refresh_token(settings, user_id)
    second_token, _ = create_refresh_token(settings, user_id)

    assert first_token != second_token
    assert decode_token(settings, first_token, "refresh") == user_id
    assert decode_token(settings, second_token, "refresh") == user_id
