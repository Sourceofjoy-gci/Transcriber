from app.core.config import Settings
from app.providers.contracts import PostProcessingProvider, TranscriptionProvider
from app.providers.hf_speech import (
    NemoASRProvider,
    NemoSALMProvider,
    QwenASRProvider,
    TransformersASRProvider,
)
from app.providers.local_whisper import FasterWhisperProvider, WhisperLocalProvider
from app.providers.post_processing import StubPostProcessingProvider
from app.providers.whisper_cpp import WhisperCppProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._transcription_providers: dict[str, TranscriptionProvider] = {}
        self._post_processing_providers: dict[str, PostProcessingProvider] = {}

    def register_transcription(self, provider: TranscriptionProvider) -> None:
        if provider.key in self._transcription_providers:
            raise ValueError(f"Transcription provider already registered: {provider.key}")
        self._transcription_providers[provider.key] = provider

    def register_post_processing(self, provider: PostProcessingProvider) -> None:
        if provider.key in self._post_processing_providers:
            raise ValueError(f"Post-processing provider already registered: {provider.key}")
        self._post_processing_providers[provider.key] = provider

    def transcription(self, key: str) -> TranscriptionProvider:
        try:
            return self._transcription_providers[key]
        except KeyError as error:
            raise LookupError(f"Unknown transcription provider: {key}") from error

    def post_processing(self, key: str) -> PostProcessingProvider:
        try:
            return self._post_processing_providers[key]
        except KeyError as error:
            raise LookupError(f"Unknown post-processing provider: {key}") from error

    def list_transcription(self) -> list[TranscriptionProvider]:
        return list(self._transcription_providers.values())

    def list_post_processing(self) -> list[PostProcessingProvider]:
        return list(self._post_processing_providers.values())


def build_local_registry(settings: Settings) -> ProviderRegistry:
    registry = ProviderRegistry()
    registry.register_transcription(FasterWhisperProvider(settings))
    registry.register_transcription(WhisperLocalProvider(settings))
    registry.register_transcription(WhisperCppProvider(settings))
    registry.register_transcription(NemoASRProvider(settings))
    registry.register_transcription(NemoSALMProvider(settings))
    registry.register_transcription(TransformersASRProvider(settings))
    registry.register_transcription(QwenASRProvider(settings))
    registry.register_post_processing(StubPostProcessingProvider())
    return registry
