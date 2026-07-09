from __future__ import annotations

import threading
import time
from collections import defaultdict


class RuntimeMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests_total = 0
        self._http_errors_total = 0
        self._http_duration_seconds_total = 0.0
        self._http_requests_by_status: dict[str, int] = defaultdict(int)

    def record_http_request(self, status_code: int, duration_seconds: float) -> None:
        with self._lock:
            self._http_requests_total += 1
            if status_code >= 500:
                self._http_errors_total += 1
            self._http_duration_seconds_total += max(0.0, duration_seconds)
            self._http_requests_by_status[str(status_code)] += 1

    def snapshot(self) -> dict[str, int | float | dict[str, int]]:
        with self._lock:
            return {
                "http_requests_total": self._http_requests_total,
                "http_errors_total": self._http_errors_total,
                "http_duration_seconds_total": round(self._http_duration_seconds_total, 6),
                "http_requests_by_status": dict(self._http_requests_by_status),
            }

    def reset(self) -> None:
        with self._lock:
            self._http_requests_total = 0
            self._http_errors_total = 0
            self._http_duration_seconds_total = 0.0
            self._http_requests_by_status.clear()


runtime_metrics = RuntimeMetrics()


def monotonic_time() -> float:
    return time.monotonic()
