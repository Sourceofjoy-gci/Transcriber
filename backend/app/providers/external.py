import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx

from app.providers.contracts import TranscriptionRequest, TranscriptionResult, TranscriptSegmentResult


class ExternalProviderError(RuntimeError):
    pass


def transcribe(provider, api_key: str | None, request: TranscriptionRequest) -> TranscriptionResult:
    url = _endpoint_url(provider.base_url, provider.endpoint_path)
    headers = {str(key): str(value) for key, value in provider.headers.items()}
    if provider.auth_type == "bearer" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    elif provider.auth_type == "api_key" and api_key:
        headers["X-API-Key"] = api_key
    try:
        with (
            request.media_path.open("rb") as media,
            httpx.Client(timeout=provider.timeout_seconds, follow_redirects=False) as client,
        ):
            response = client.post(
                url,
                headers=headers,
                data={"model": provider.model_name or "", "language": request.language or ""},
                files={"file": (request.media_path.name, media, "audio/wav")},
            )
        response.raise_for_status()
    except httpx.HTTPError as error:
        raise ExternalProviderError("External transcription request failed") from error
    payload = response.json()
    segments = [
        TranscriptSegmentResult(
            start_ms=round(float(item.get("start", 0)) * 1000),
            end_ms=round(float(item.get("end", 0)) * 1000),
            text=str(item.get("text", "")).strip(),
        )
        for item in payload.get("segments", [])
    ]
    return TranscriptionResult(
        detected_language=payload.get("language"),
        duration_ms=None,
        text=str(payload.get("text", "")).strip(),
        segments=segments,
    )


def test_connection(provider, api_key: str | None) -> None:
    _endpoint_url(provider.base_url, provider.endpoint_path)
    if provider.auth_type != "none" and not api_key:
        raise ExternalProviderError("Provider has no configured credential")


def _endpoint_url(base_url: str | None, endpoint_path: str) -> str:
    if not base_url or not endpoint_path.startswith("/"):
        raise ExternalProviderError("Provider URL configuration is invalid")
    parsed = urlparse(base_url)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname:
        raise ExternalProviderError("Provider base URL is invalid")
    if parsed.scheme != "https" and parsed.hostname not in {"localhost", "127.0.0.1"}:
        raise ExternalProviderError("External providers must use HTTPS")
    for address in socket.getaddrinfo(parsed.hostname, None):
        if ipaddress.ip_address(address[4][0]).is_private and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
        }:
            raise ExternalProviderError("Provider host resolves to a private address")
    return urljoin(base_url.rstrip("/") + "/", endpoint_path.lstrip("/"))
