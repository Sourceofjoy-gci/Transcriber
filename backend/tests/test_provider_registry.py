import pytest

from app.providers.contracts import ProviderCapabilities, TranscriptionRequest, TranscriptionResult
from app.providers.registry import ProviderRegistry


class FakeTranscriptionProvider:
    key = "fake"
    capabilities = ProviderCapabilities(tasks=frozenset({"transcription"}))

    def validate_options(self, options: dict) -> None:
        return None

    def probe(self) -> dict:
        return {"status": "ready"}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        return TranscriptionResult(detected_language="en", duration_ms=0, text="", segments=[])


def test_registry_resolves_registered_provider() -> None:
    registry = ProviderRegistry()
    provider = FakeTranscriptionProvider()
    registry.register_transcription(provider)

    assert registry.transcription("fake") is provider

    with pytest.raises(LookupError):
        registry.transcription("missing")
