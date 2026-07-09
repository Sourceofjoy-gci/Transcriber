import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.providers.contracts import TranscriptionRequest
from app.providers.registry import build_local_registry


def _settings(tmp_path: Path):
    return SimpleNamespace(
        model_root=tmp_path,
        default_transcription_model="base",
        transcription_device="auto",
        transcription_compute_type="float16",
    )


def test_registry_includes_huggingface_speech_runtime_providers(tmp_path: Path) -> None:
    registry = build_local_registry(_settings(tmp_path))

    assert registry.transcription("nemo_asr").key == "nemo_asr"
    assert registry.transcription("nemo_salm").key == "nemo_salm"
    assert registry.transcription("transformers_asr").key == "transformers_asr"
    assert registry.transcription("qwen_asr").key == "qwen_asr"


def test_qwen_asr_provider_transcribes_with_local_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    class _Result:
        language = "English"
        text = "hello from qwen"

    class _Qwen3ASRModel:
        @classmethod
        def from_pretrained(cls, model_name: str, **kwargs):
            captured["model_name"] = model_name
            captured["load_kwargs"] = kwargs
            return cls()

        def transcribe(self, *, audio: str, language: str | None = None, **kwargs):
            captured["audio"] = audio
            captured["language"] = language
            captured["transcribe_kwargs"] = kwargs
            return [_Result()]

    qwen_asr = types.ModuleType("qwen_asr")
    qwen_asr.Qwen3ASRModel = _Qwen3ASRModel
    monkeypatch.setitem(sys.modules, "qwen_asr", qwen_asr)
    torch = types.ModuleType("torch")
    torch.bfloat16 = "bfloat16"
    torch.float16 = "float16"
    torch.float32 = "float32"
    torch.cuda = SimpleNamespace(is_available=lambda: False)
    monkeypatch.setitem(sys.modules, "torch", torch)

    model_path = tmp_path / "qwen"
    model_path.mkdir()
    media_path = tmp_path / "audio.wav"
    media_path.write_bytes(b"wav")
    provider = build_local_registry(_settings(tmp_path)).transcription("qwen_asr")

    result = provider.transcribe(
        TranscriptionRequest(
            media_path=media_path,
            language="English",
            options={"model_path": str(model_path), "model_size": "Qwen/Qwen3-ASR-1.7B"},
        ),
        lambda *_: None,
    )

    assert captured["model_name"] == str(model_path)
    assert captured["audio"] == str(media_path)
    assert captured["language"] == "English"
    assert result.detected_language == "English"
    assert result.text == "hello from qwen"
    assert result.segments[0].text == "hello from qwen"


def test_transformers_asr_provider_transcribes_with_local_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    captured: dict[str, object] = {}

    def fake_pipeline(task: str, model: str, **kwargs):
        captured["task"] = task
        captured["model"] = model
        captured["load_kwargs"] = kwargs

        def run(audio_path: str, **run_kwargs):
            captured["audio_path"] = audio_path
            captured["run_kwargs"] = run_kwargs
            return {"text": "granite transcript"}

        return run

    transformers = types.ModuleType("transformers")
    transformers.pipeline = fake_pipeline
    monkeypatch.setitem(sys.modules, "transformers", transformers)
    torch = types.ModuleType("torch")
    torch.bfloat16 = "bfloat16"
    torch.float16 = "float16"
    torch.float32 = "float32"
    monkeypatch.setitem(sys.modules, "torch", torch)

    model_path = tmp_path / "granite"
    model_path.mkdir()
    media_path = tmp_path / "audio.wav"
    media_path.write_bytes(b"wav")
    provider = build_local_registry(_settings(tmp_path)).transcription("transformers_asr")

    result = provider.transcribe(
        TranscriptionRequest(
            media_path=media_path,
            language="en",
            options={
                "model_path": str(model_path),
                "model_size": "ibm-granite/granite-speech-3.3-8b",
                "device_map": "auto",
            },
        ),
        lambda *_: None,
    )

    assert captured["task"] == "automatic-speech-recognition"
    assert captured["model"] == str(model_path)
    assert captured["audio_path"] == str(media_path)
    assert result.detected_language == "en"
    assert result.text == "granite transcript"
