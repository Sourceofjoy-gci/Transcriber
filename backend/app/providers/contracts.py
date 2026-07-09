from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ProviderCapabilities:
    tasks: frozenset[str]
    supported_media_types: frozenset[str] = frozenset()
    supported_languages: frozenset[str] = frozenset()
    supports_word_timestamps: bool = False
    supports_diarization: bool = False
    supports_translation: bool = False
    is_external: bool = False
    settings_schema: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TranscriptionRequest:
    media_path: Path
    language: str | None
    options: dict


@dataclass(frozen=True)
class TranscriptSegmentResult:
    start_ms: int
    end_ms: int
    text: str
    confidence: float | None = None
    speaker_label: str | None = None
    words: list["TranscriptWordResult"] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptWordResult:
    start_ms: int
    end_ms: int
    word: str
    confidence: float | None = None


@dataclass(frozen=True)
class TranscriptionResult:
    detected_language: str | None
    duration_ms: int | None
    text: str
    segments: list[TranscriptSegmentResult]
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DiarizationRequest:
    media_path: Path
    duration_ms: int | None
    options: dict


@dataclass(frozen=True)
class DiarizationSegmentResult:
    start_ms: int
    end_ms: int
    speaker_label: str
    confidence: float | None = None


@dataclass(frozen=True)
class DiarizationResult:
    segments: list[DiarizationSegmentResult]
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PostProcessRequest:
    text: str
    task: str
    options: dict


@dataclass(frozen=True)
class PostProcessResult:
    result: dict
    warnings: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


ProgressReporter = Callable[[int, str, dict], None]


class TranscriptionProvider(Protocol):
    key: str
    capabilities: ProviderCapabilities

    def validate_options(self, options: dict) -> None: ...

    def probe(self) -> dict: ...

    def transcribe(
        self, request: TranscriptionRequest, report_progress: ProgressReporter
    ) -> TranscriptionResult: ...


class PostProcessingProvider(Protocol):
    key: str
    capabilities: ProviderCapabilities

    def validate_options(self, task: str, options: dict) -> None: ...

    def process(
        self, request: PostProcessRequest, report_progress: ProgressReporter
    ) -> PostProcessResult: ...


class DiarizationProvider(Protocol):
    key: str
    capabilities: ProviderCapabilities

    def validate_options(self, options: dict) -> None: ...

    def diarize(
        self, request: DiarizationRequest, report_progress: ProgressReporter
    ) -> DiarizationResult: ...


class ModelProvider(Protocol):
    key: str

    def download_model(self, model_id: str, report_progress: ProgressReporter) -> dict: ...
