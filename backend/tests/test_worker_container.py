import tomllib
from pathlib import Path


def test_worker_ai_extra_excludes_openai_whisper() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))

    extras = pyproject["project"]["optional-dependencies"]
    ai_dependencies = extras["ai"]
    advanced_speech_dependencies = extras["advanced-speech"]
    whisper_local_dependencies = extras["whisper-local"]

    assert any(dependency.startswith("faster-whisper") for dependency in ai_dependencies)
    assert any(dependency.startswith("huggingface-hub") for dependency in ai_dependencies)
    assert not any(dependency.startswith("openai-whisper") for dependency in ai_dependencies)
    assert any("nemo_toolkit" in dependency for dependency in advanced_speech_dependencies)
    assert any(dependency.startswith("qwen-asr") for dependency in advanced_speech_dependencies)
    assert any(dependency.startswith("transformers") for dependency in advanced_speech_dependencies)
    assert any(dependency.startswith("openai-whisper") for dependency in whisper_local_dependencies)


def test_worker_image_installs_native_build_tools_for_advanced_speech() -> None:
    dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert "build-essential" in dockerfile
    assert "cmake" in dockerfile


def test_cpu_worker_uses_cpu_lock_and_gpu_worker_can_use_full_lock() -> None:
    dockerfile_path = Path(__file__).resolve().parents[1] / "Dockerfile"
    dockerfile = dockerfile_path.read_text(encoding="utf-8")

    assert "requirements.cpu.lock" in dockerfile
    assert "ARG WORKER_LOCK=requirements.cpu.lock" in dockerfile
