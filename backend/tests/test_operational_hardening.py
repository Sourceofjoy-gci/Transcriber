from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi import HTTPException


class FakeRedis:
    def __init__(self) -> None:
        self.sorted_sets: dict[str, dict[str, float]] = {}
        self.expirations: dict[str, int] = {}

    def zremrangebyscore(self, key: str, minimum: float, maximum: float) -> None:
        values = self.sorted_sets.setdefault(key, {})
        for member, score in list(values.items()):
            if minimum <= score <= maximum:
                del values[member]

    def zcard(self, key: str) -> int:
        return len(self.sorted_sets.setdefault(key, {}))

    def zadd(self, key: str, mapping: dict[str, float]) -> None:
        self.sorted_sets.setdefault(key, {}).update(mapping)

    def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


class FakeSocket:
    def __init__(self, response: bytes) -> None:
        self.response = response
        self.sent = bytearray()

    def __enter__(self) -> FakeSocket:
        return self

    def __exit__(self, *args) -> None:
        return None

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def connect(self, address: tuple[str, int]) -> None:
        self.address = address

    def sendall(self, payload: bytes) -> None:
        self.sent.extend(payload)

    def recv(self, size: int) -> bytes:
        return self.response


def test_redis_rate_limit_store_enforces_shared_window() -> None:
    from app.core.rate_limit import RateLimitConfig, RedisRateLimitStore

    fake_redis = FakeRedis()
    ticks = iter([100.0, 101.0, 102.0])
    store = RedisRateLimitStore(fake_redis, namespace="test", clock=lambda: next(ticks))
    config = RateLimitConfig(max_requests=2, window_seconds=60)

    store.check("login:127.0.0.1", config)
    store.check("login:127.0.0.1", config)

    with pytest.raises(HTTPException) as error:
        store.check("login:127.0.0.1", config)

    assert error.value.status_code == 429
    assert fake_redis.expirations["test:login:127.0.0.1"] == 60


def test_clamav_scanner_maps_clean_and_infected_results(tmp_path) -> None:
    from app.services.malware import ClamAVScanner

    payload = tmp_path / "sample.wav"
    payload.write_bytes(b"RIFF....WAVE")

    clean_socket = FakeSocket(b"stream: OK\0")
    clean = ClamAVScanner(
        host="clamav",
        port=3310,
        timeout_seconds=2.5,
        socket_factory=lambda *args, **kwargs: clean_socket,
    ).scan(payload)

    assert clean.clean is True
    assert clean.scanner == "clamav"
    assert b"INSTREAM" in clean_socket.sent

    infected = ClamAVScanner(
        host="clamav",
        port=3310,
        timeout_seconds=2.5,
        socket_factory=lambda *args, **kwargs: FakeSocket(b"stream: Eicar-Test-Signature FOUND\0"),
    ).scan(payload)

    assert infected.clean is False
    assert infected.message == "Malware detected: Eicar-Test-Signature"


def test_redaction_scrubs_nested_secret_material() -> None:
    from app.services.redaction import redact_sensitive_data

    redacted = redact_sensitive_data(
        {
            "api_key": "sk-live-secret",
            "headers": {"Authorization": "Bearer token", "X-Request-ID": "safe"},
            "provider_error": "upstream rejected sk-provider-secret",
            "nested": [{"refresh_token": "refresh-secret"}],
        }
    )

    serialized = json.dumps(redacted)
    assert "sk-live-secret" not in serialized
    assert "Bearer token" not in serialized
    assert "sk-provider-secret" not in serialized
    assert "refresh-secret" not in serialized
    assert redacted["headers"]["X-Request-ID"] == "safe"


def test_json_logging_includes_context_and_redacts_message() -> None:
    from app.core.logging import JsonLogFormatter, bind_log_context, clear_log_context

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger("task10-json-logging")
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False

    bind_log_context(request_id="req-123", job_id="job-456")
    try:
        logger.info("provider failed with sk-secret-value", extra={"provider_error": "sk-extra-secret"})
    finally:
        clear_log_context()

    payload = json.loads(stream.getvalue())
    assert payload["request_id"] == "req-123"
    assert payload["job_id"] == "job-456"
    assert "sk-secret-value" not in payload["message"]
    assert "sk-extra-secret" not in json.dumps(payload)
