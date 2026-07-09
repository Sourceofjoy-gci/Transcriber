from __future__ import annotations

import contextlib
import contextvars
import json
import logging
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from app.services.redaction import redact_sensitive_data, redact_sensitive_text

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
job_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("job_id", default=None)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_sensitive_text(record.getMessage()),
        }
        request_id = request_id_var.get()
        job_id = job_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        if job_id:
            payload["job_id"] = job_id

        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key
            not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
                "taskName",
            }
        }
        if extras:
            payload["extra"] = redact_sensitive_data(extras)
        if record.exc_info:
            payload["exception"] = redact_sensitive_text(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


def configure_logging(log_format: str = "text", level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    if log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)


def bind_log_context(*, request_id: str | None = None, job_id: str | None = None) -> None:
    if request_id is not None:
        request_id_var.set(request_id)
    if job_id is not None:
        job_id_var.set(job_id)


def clear_log_context() -> None:
    request_id_var.set(None)
    job_id_var.set(None)


@contextlib.contextmanager
def log_context(*, request_id: str | None = None, job_id: str | None = None) -> Iterator[None]:
    request_token = request_id_var.set(request_id) if request_id is not None else None
    job_token = job_id_var.set(job_id) if job_id is not None else None
    try:
        yield
    finally:
        if request_token is not None:
            request_id_var.reset(request_token)
        if job_token is not None:
            job_id_var.reset(job_token)
