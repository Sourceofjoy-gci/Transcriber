import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.providers.contracts import (
    ProviderCapabilities,
    TranscriptionRequest,
    TranscriptionResult,
    TranscriptSegmentResult,
)
from app.providers.local_whisper import ProviderUnavailableError


class HuggingFaceSpeechProviderBase:
    key: str
    dependency_imports: dict[str, str] = {}
    capabilities = ProviderCapabilities(
        tasks=frozenset({"transcription"}),
        supported_media_types=frozenset({"audio/*", "video/*"}),
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def validate_options(self, options: dict) -> None:
        if options.get("model_path") and not Path(str(options["model_path"])).exists():
            raise ValueError("Installed model path was not found")

    def probe(self) -> dict:
        missing = self._missing_dependencies()
        if missing:
            return {
                "status": "unavailable",
                "reason": "Missing Python runtime dependencies: " + ", ".join(missing),
            }
        return {"status": "ready"}

    def probe_model(self, model_path: Path, catalog) -> dict:
        probe = self.probe()
        result = {
            **probe,
            "model_path": str(model_path),
            "model_identifier": catalog.model_identifier,
            "compatible": model_path.exists() and probe.get("status") == "ready",
        }
        if not model_path.exists():
            result["reason"] = "Installed model snapshot was not found"
        return result

    def _missing_dependencies(self) -> list[str]:
        missing: list[str] = []
        for module_name, dependency_name in self.dependency_imports.items():
            if module_name in sys.modules:
                continue
            try:
                spec = importlib.util.find_spec(module_name)
            except (ImportError, ModuleNotFoundError, ValueError):
                spec = None
            if spec is None:
                missing.append(dependency_name)
        return missing

    def _model_reference(self, options: dict) -> str:
        model_path = options.get("model_path")
        if model_path:
            path = Path(str(model_path))
            if path.exists():
                return str(path)
        return str(options.get("model_size") or "")


class NemoASRProvider(HuggingFaceSpeechProviderBase):
    key = "nemo_asr"
    dependency_imports = {"nemo.collections.asr": "nemo_toolkit[asr]"}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            import nemo.collections.asr as nemo_asr
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the nemo-asr optional dependency in the worker image"
            ) from error

        model_reference = self._model_reference(request.options)
        report_progress(10, "Loading NeMo ASR model", {"model": model_reference})
        checkpoint = _nemo_checkpoint(model_reference)
        if checkpoint is not None:
            model = nemo_asr.models.ASRModel.restore_from(str(checkpoint))
        else:
            model = nemo_asr.models.ASRModel.from_pretrained(model_name=model_reference)
        _prepare_model_device(model, request.options)
        output = model.transcribe([str(request.media_path)])
        text = _extract_text(_first(output))
        report_progress(95, "Finalising transcript", {})
        return _single_segment_result(text, request.language)


class NemoSALMProvider(HuggingFaceSpeechProviderBase):
    key = "nemo_salm"
    dependency_imports = {"nemo.collections.speechlm2.models": "nemo_toolkit[asr,tts]"}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            from nemo.collections.speechlm2.models import SALM
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the nemo-salm optional dependency in the worker image"
            ) from error

        model_reference = self._model_reference(request.options)
        report_progress(10, "Loading NeMo SALM model", {"model": model_reference})
        model = SALM.from_pretrained(model_reference)
        _prepare_model_device(model, request.options)
        locator = getattr(model, "audio_locator_tag", "<|audioplaceholder|>")
        answer_ids = model.generate(
            prompts=[
                [
                    {
                        "role": "user",
                        "content": f"Transcribe the following: {locator}",
                        "audio": [str(request.media_path)],
                    }
                ]
            ],
            max_new_tokens=request.options.get("max_new_tokens", 1024),
        )
        text = _extract_salm_text(model, answer_ids)
        report_progress(95, "Finalising transcript", {})
        return _single_segment_result(text, request.language)


class TransformersASRProvider(HuggingFaceSpeechProviderBase):
    key = "transformers_asr"
    dependency_imports = {
        "transformers": "transformers",
        "torch": "torch",
        "torchaudio": "torchaudio",
        "soundfile": "soundfile",
        "peft": "peft",
    }

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            import torch
            from transformers import pipeline
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the transformers-asr optional dependency in the worker image"
            ) from error

        model_reference = self._model_reference(request.options)
        report_progress(10, "Loading Transformers ASR model", {"model": model_reference})
        pipeline_kwargs: dict[str, Any] = {"model": model_reference}
        if request.options.get("device_map"):
            pipeline_kwargs["device_map"] = request.options["device_map"]
        dtype = _torch_dtype(torch, request.options)
        if dtype is not None:
            pipeline_kwargs["torch_dtype"] = dtype
        asr_pipeline = pipeline("automatic-speech-recognition", **pipeline_kwargs)
        run_kwargs: dict[str, Any] = {}
        if request.options.get("max_new_tokens"):
            run_kwargs["generate_kwargs"] = {"max_new_tokens": request.options["max_new_tokens"]}
        output = asr_pipeline(str(request.media_path), **run_kwargs)
        text = _extract_pipeline_text(output)
        report_progress(95, "Finalising transcript", {})
        return _single_segment_result(text, request.language)


class QwenASRProvider(HuggingFaceSpeechProviderBase):
    key = "qwen_asr"
    dependency_imports = {"qwen_asr": "qwen-asr", "torch": "torch"}

    def transcribe(self, request: TranscriptionRequest, report_progress) -> TranscriptionResult:
        self.validate_options(request.options)
        try:
            import torch
            from qwen_asr import Qwen3ASRModel
        except ImportError as error:
            raise ProviderUnavailableError(
                "Install the qwen-asr optional dependency in the worker image"
            ) from error

        model_reference = self._model_reference(request.options)
        report_progress(10, "Loading Qwen3-ASR model", {"model": model_reference})
        load_kwargs: dict[str, Any] = {
            "device_map": request.options.get("device_map") or _default_qwen_device_map(torch),
            "max_inference_batch_size": request.options.get("max_inference_batch_size", 32),
            "max_new_tokens": request.options.get("max_new_tokens", 256),
        }
        dtype = _torch_dtype(torch, request.options)
        if dtype is not None:
            load_kwargs["dtype"] = dtype
        if request.options.get("attn_implementation"):
            load_kwargs["attn_implementation"] = request.options["attn_implementation"]
        model = Qwen3ASRModel.from_pretrained(model_reference, **load_kwargs)
        results = model.transcribe(
            audio=str(request.media_path),
            language=request.language,
            return_time_stamps=bool(request.options.get("return_time_stamps")),
        )
        result = _first(results)
        text = _extract_text(result)
        report_progress(95, "Finalising transcript", {})
        return _single_segment_result(text, getattr(result, "language", request.language))


def _nemo_checkpoint(model_reference: str) -> Path | None:
    path = Path(model_reference)
    if path.is_file() and path.suffix == ".nemo":
        return path
    if path.is_dir():
        checkpoints = sorted(path.glob("*.nemo"))
        if checkpoints:
            return checkpoints[0]
    return None


def _prepare_model_device(model, options: dict) -> None:
    if hasattr(model, "eval"):
        model.eval()
    device = options.get("device")
    if device and device != "auto" and hasattr(model, "to"):
        model.to(device)
    dtype = options.get("dtype")
    if dtype == "bfloat16" and hasattr(model, "bfloat16"):
        model.bfloat16()
    elif dtype == "float16" and hasattr(model, "half"):
        model.half()


def _torch_dtype(torch_module, options: dict):
    dtype_name = options.get("dtype", "bfloat16")
    if dtype_name in {None, "auto"}:
        return None
    return getattr(torch_module, str(dtype_name), None)


def _default_qwen_device_map(torch_module) -> str:
    cuda = getattr(torch_module, "cuda", None)
    if cuda is not None and callable(getattr(cuda, "is_available", None)) and cuda.is_available():
        return "cuda:0"
    return "cpu"


def _first(value):
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _extract_salm_text(model, answer_ids) -> str:
    answer = _first(answer_ids)
    if isinstance(answer, str):
        return answer.strip()
    if hasattr(answer, "cpu"):
        answer = answer.cpu()
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is not None and hasattr(tokenizer, "ids_to_text"):
        return str(tokenizer.ids_to_text(answer)).strip()
    return _extract_text(answer)


def _extract_pipeline_text(output) -> str:
    if isinstance(output, dict):
        return str(output.get("text") or "").strip()
    return _extract_text(_first(output))


def _extract_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return str(getattr(value, "text", value)).strip()


def _single_segment_result(text: str, language: str | None) -> TranscriptionResult:
    return TranscriptionResult(
        detected_language=language,
        duration_ms=None,
        text=text,
        segments=[TranscriptSegmentResult(start_ms=0, end_ms=0, text=text)] if text else [],
    )
