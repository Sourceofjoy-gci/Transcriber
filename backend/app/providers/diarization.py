from app.providers.contracts import (
    DiarizationRequest,
    DiarizationResult,
    DiarizationSegmentResult,
    ProviderCapabilities,
)


class LocalTurnDiarizationProvider:
    key = "local_turns"
    capabilities = ProviderCapabilities(
        tasks=frozenset({"diarization"}),
        supported_media_types=frozenset({"audio/*", "video/*"}),
        supports_diarization=True,
        settings_schema={
            "speaker_count": {"type": "integer", "minimum": 1, "maximum": 20},
            "turn_length_ms": {"type": "integer", "minimum": 1000, "maximum": 600000},
        },
    )

    def validate_options(self, options: dict) -> None:
        speaker_count = options.get("speaker_count", 2)
        turn_length_ms = options.get("turn_length_ms", 30_000)
        if not isinstance(speaker_count, int) or not 1 <= speaker_count <= 20:
            raise ValueError("Speaker count must be between 1 and 20")
        if not isinstance(turn_length_ms, int) or not 1_000 <= turn_length_ms <= 600_000:
            raise ValueError("Turn length must be between 1000 and 600000 milliseconds")

    def diarize(self, request: DiarizationRequest, report_progress) -> DiarizationResult:
        options = request.options
        self.validate_options(options)
        duration_ms = request.duration_ms or options.get("duration_ms") or 0
        speaker_count = options.get("speaker_count", 2)
        turn_length_ms = options.get("turn_length_ms", 30_000)
        if duration_ms <= 0:
            report_progress(95, "Assigning speaker labels", {"provider": self.key})
            return DiarizationResult(
                segments=[
                    DiarizationSegmentResult(
                        start_ms=0,
                        end_ms=max(1, turn_length_ms),
                        speaker_label="S1",
                        confidence=None,
                    )
                ],
                warnings=["Diarisation used a single fallback turn because media duration was unknown"],
                metrics={"provider": self.key},
            )

        turns: list[DiarizationSegmentResult] = []
        start_ms = 0
        turn_index = 0
        while start_ms < duration_ms:
            end_ms = min(duration_ms, start_ms + turn_length_ms)
            turns.append(
                DiarizationSegmentResult(
                    start_ms=start_ms,
                    end_ms=end_ms,
                    speaker_label=f"S{turn_index % speaker_count + 1}",
                    confidence=None,
                )
            )
            start_ms = end_ms
            turn_index += 1
        report_progress(95, "Assigning speaker labels", {"provider": self.key, "turns": len(turns)})
        return DiarizationResult(segments=turns, metrics={"provider": self.key, "turns": len(turns)})


def build_diarization_provider(provider_key: str | None) -> LocalTurnDiarizationProvider:
    key = provider_key or LocalTurnDiarizationProvider.key
    if key != LocalTurnDiarizationProvider.key:
        raise LookupError(f"Unknown diarisation provider: {key}")
    return LocalTurnDiarizationProvider()
