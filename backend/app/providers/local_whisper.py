from typing import Any

from app.core.config import Settings
from app.providers.contracts import (
    ProviderCapabilities,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegmentResult,
    TranscriptWordResult,
)


class ProviderUnavailableError(RuntimeError):
    pass


class FasterWhisperProvider:
    key = "faster_whisper"
    capabilities = ProviderCapabilities(
        tasks=frozenset({"transcription", "translation"}),
        supported_media_types=frozenset({"audio/*", "video/*"}),
        supports_word_timestamps=True,
        supports_translation=True,
        settings_schema={
            "model_size": {"type": "string"},
            "device": {"enum": ["auto", "cpu", "cuda"]},
            "compute_type": {"enum": ["int8", "float16", "int8_float16", "float32"]},
            "beam_size": {"type": "integer", "minimum": 1, "maximum": 10},
            "temperature": {"type": "number", "minimum": 0, "maximum": 1},
            "vad_filter": {"type": "boolean"},
            "word_timestamps": {"type": "boolean"},
        },
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_options(self, options: dict) -> None:
        device = options.get("device", self.settings.transcription_device)
        compute_type = options.get("compute_type", self.settings.transcription_compute_type)
        beam_size = options.get("beam_size", 5)
        if device not in {"auto", "cpu", "cuda"}:
            raise ValueError("Unsupported Faster-Whisper device")
        if compute_type not in {"int8", "float16", "int8_float16", "float32"}:
            raise ValueError("Unsupported Faster-Whisper compute type")
        if not isinstance(beam_size, int) or not 1 <= beam_size <= 10:
            raise ValueError("Beam size must be between 1 and 10")

    def probe(self) -> dict:
        try:
            import faster_whisper
        except ImportError:
            return {"status": "unavailable", "reason": "faster-whisper package is not installed"}
        return {"status": "ready", "version": getattr(faster_whisper, "__version__", "unknown")}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            from faster_whisper import WhisperModel
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the faster-whisper optional dependency in the worker image"
            ) from error

        options = request.options
        model = WhisperModel(
            options.get("model_path", options.get("model_size", self.settings.default_transcription_model)),
            device=options.get("device", self.settings.transcription_device),
            compute_type=options.get("compute_type", self.settings.transcription_compute_type),
            download_root=str(self.settings.model_root),
        )
        segments, info = model.transcribe(
            str(request.media_path),
            language=request.language,
            task="translate" if options.get("translation_mode") else "transcribe",
            beam_size=options.get("beam_size", 5),
            temperature=options.get("temperature", 0),
            vad_filter=options.get("vad_filter", False),
            word_timestamps=options.get("word_timestamps", False),
        )
        normalized_segments: list[TranscriptSegmentResult] = []
        for index, segment in enumerate(segments, start=1):
            words = [
                TranscriptWordResult(
                    start_ms=_seconds_to_ms(word.start),
                    end_ms=_seconds_to_ms(word.end),
                    word=word.word,
                    confidence=_probability_to_confidence(getattr(word, "probability", None)),
                )
                for word in (getattr(segment, "words", None) or [])
                if word.start is not None and word.end is not None
            ]
            normalized_segments.append(
                TranscriptSegmentResult(
                    start_ms=_seconds_to_ms(segment.start),
                    end_ms=_seconds_to_ms(segment.end),
                    text=segment.text.strip(),
                    confidence=_probability_to_confidence(getattr(segment, "avg_logprob", None)),
                    words=words,
                )
            )
            report_progress(min(95, 10 + index), "Transcribing media", {"segment": index})
        language = getattr(info, "language", request.language)
        duration = getattr(info, "duration", None)
        return TranscriptionResult(
            detected_language=language,
            duration_ms=_seconds_to_ms(duration) if duration is not None else None,
            text=" ".join(segment.text for segment in normalized_segments).strip(),
            segments=normalized_segments,
        )


class WhisperLocalProvider:
    key = "whisper_local"
    capabilities = ProviderCapabilities(
        tasks=frozenset({"transcription", "translation"}),
        supported_media_types=frozenset({"audio/*", "video/*"}),
        supports_word_timestamps=True,
        supports_translation=True,
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_options(self, options: dict) -> None:
        beam_size = options.get("beam_size", 5)
        if not isinstance(beam_size, int) or not 1 <= beam_size <= 10:
            raise ValueError("Beam size must be between 1 and 10")

    def probe(self) -> dict:
        try:
            import whisper
        except ImportError:
            return {"status": "unavailable", "reason": "openai-whisper package is not installed"}
        return {"status": "ready", "version": getattr(whisper, "__version__", "unknown")}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            import whisper
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the openai-whisper optional dependency in the worker image"
            ) from error

        options = request.options
        device = options.get("device", self.settings.transcription_device)
        model = whisper.load_model(
            options.get("model_size", self.settings.default_transcription_model),
            device=None if device == "auto" else device,
            download_root=options.get("model_download_root", str(self.settings.model_root)),
        )
        report_progress(15, "Loading Whisper model", {})
        result: dict[str, Any] = model.transcribe(
            str(request.media_path),
            language=request.language,
            task="translate" if options.get("translation_mode") else "transcribe",
            temperature=options.get("temperature", 0),
            beam_size=options.get("beam_size", 5),
            word_timestamps=options.get("word_timestamps", False),
            fp16=options.get("compute_type", self.settings.transcription_compute_type) == "float16",
        )
        normalized_segments = [
            TranscriptSegmentResult(
                start_ms=_seconds_to_ms(segment["start"]),
                end_ms=_seconds_to_ms(segment["end"]),
                text=segment["text"].strip(),
                confidence=_probability_to_confidence(segment.get("avg_logprob")),
                words=[
                    TranscriptWordResult(
                        start_ms=_seconds_to_ms(word["start"]),
                        end_ms=_seconds_to_ms(word["end"]),
                        word=word["word"],
                        confidence=_probability_to_confidence(word.get("probability")),
                    )
                    for word in segment.get("words", [])
                ],
            )
            for segment in result.get("segments", [])
        ]
        report_progress(95, "Finalising transcript", {})
        return TranscriptionResult(
            detected_language=result.get("language", request.language),
            duration_ms=None,
            text=result.get("text", "").strip(),
            segments=normalized_segments,
        )


def _seconds_to_ms(value: float | int) -> int:
    return max(0, round(float(value) * 1000))


def _probability_to_confidence(value: float | None) -> float | None:
    if value is None:
        return None
    if value < 0:
        return round(max(0.0, min(1.0, 1.0 + value)), 4)
    return round(max(0.0, min(1.0, value)), 4)
