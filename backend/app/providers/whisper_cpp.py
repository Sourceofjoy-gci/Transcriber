import shutil
import subprocess
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.providers.contracts import (
    ProviderCapabilities,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegmentResult,
)
from app.providers.local_whisper import ProviderUnavailableError


class WhisperCppProvider:
    key = "whisper_cpp"
    capabilities = ProviderCapabilities(
        tasks=frozenset({"transcription", "translation"}),
        supported_media_types=frozenset({"audio/*", "video/*"}),
        supports_translation=True,
        settings_schema={
            "model_path": {"type": "string"},
            "binary_path": {"type": "string"},
            "language": {"type": "string"},
            "translation_mode": {"type": "boolean"},
        },
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_options(self, options: dict) -> None:
        if not options.get("model_path"):
            raise ValueError("Whisper.cpp requires an installed model path")

    def probe(self) -> dict:
        binary = self._binary_path({})
        if shutil.which(binary) is None and not Path(binary).exists():
            return {"status": "unavailable", "reason": "whisper.cpp binary was not found"}
        try:
            completed = subprocess.run(
                [binary, "--help"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except OSError as error:
            return {"status": "unavailable", "reason": str(error)}
        return {"status": "ready" if completed.returncode in {0, 1} else "unavailable"}

    def probe_model(self, model_path: Path, catalog) -> dict:
        probe = self.probe()
        result = {
            **probe,
            "model_path": str(model_path),
            "model_identifier": catalog.model_identifier,
            "compatible": model_path.exists() and probe.get("status") == "ready",
        }
        if not model_path.exists():
            result["reason"] = "Installed model file was not found"
        return result

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        binary = self._binary_path(request.options)
        model_path = Path(request.options["model_path"])
        if not model_path.exists():
            raise ProviderUnavailableError("Installed Whisper.cpp model file was not found")
        if shutil.which(binary) is None and not Path(binary).exists():
            raise ProviderUnavailableError("Install whisper.cpp and expose whisper-cli in the worker image")

        report_progress(10, "Starting Whisper.cpp", {})
        with tempfile.TemporaryDirectory() as tmpdir:
            output_prefix = Path(tmpdir) / "transcript"
            command = [
                binary,
                "-m",
                str(model_path),
                "-f",
                str(request.media_path),
                "-otxt",
                "-of",
                str(output_prefix),
            ]
            if request.language:
                command.extend(["-l", request.language])
            if request.options.get("translation_mode"):
                command.append("-tr")
            completed = subprocess.run(command, capture_output=True, text=True, timeout=None, check=False)
            if completed.returncode != 0:
                raise ProviderUnavailableError(completed.stderr.strip() or "Whisper.cpp transcription failed")
            output_file = output_prefix.with_suffix(".txt")
            text = (
                output_file.read_text(encoding="utf-8").strip()
                if output_file.exists()
                else completed.stdout.strip()
            )
        report_progress(95, "Finalising transcript", {})
        return TranscriptionResult(
            detected_language=request.language,
            duration_ms=None,
            text=text,
            segments=[TranscriptSegmentResult(start_ms=0, end_ms=0, text=text)] if text else [],
        )

    def _binary_path(self, options: dict) -> str:
        return str(options.get("binary_path") or "whisper-cli")
