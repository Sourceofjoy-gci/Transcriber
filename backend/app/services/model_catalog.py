from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.domain import ModelCatalog


@dataclass(frozen=True)
class CatalogEntry:
    adapter_key: str
    model_identifier: str
    name: str
    model_type: str
    size_bytes: int | None
    source_url: str | None = None
    revision: str | None = None
    requirements: dict = field(default_factory=dict)
    capabilities: dict = field(default_factory=dict)
    checksum: str | None = None


def _requirements(
    size_bytes: int | None,
    *,
    min_ram_bytes: int | None = None,
    recommended_device: str | None = None,
    requires_cuda: bool = False,
    download_backend: str | None = None,
    python_dependencies: list[str] | None = None,
) -> dict:
    requirements = {
        "recommended_device": recommended_device
        or ("cuda" if size_bytes and size_bytes > 1_000_000_000 else "cpu_or_cuda"),
    }
    if min_ram_bytes is not None:
        requirements["min_ram_bytes"] = min_ram_bytes
    if requires_cuda:
        requirements["requires_cuda"] = True
    if download_backend is not None:
        requirements["download_backend"] = download_backend
    if python_dependencies:
        requirements["python_dependencies"] = python_dependencies
    return requirements


DEFAULT_CAPABILITIES = {"tasks": ["transcription", "translation"], "word_timestamps": True}
WHISPER_CPP_CAPABILITIES = {"tasks": ["transcription", "translation"], "word_timestamps": False}
HF_TRANSCRIPTION_CAPABILITIES = {"tasks": ["transcription"], "word_timestamps": False}
CANARY_QWEN_CAPABILITIES = {
    **HF_TRANSCRIPTION_CAPABILITIES,
    "languages": ["en"],
    "punctuation": True,
    "capitalization": True,
}
GRANITE_SPEECH_CAPABILITIES = {
    **HF_TRANSCRIPTION_CAPABILITIES,
    "languages": ["en", "fr", "de", "es", "pt"],
    "translation": True,
}
QWEN_ASR_CAPABILITIES = {
    **HF_TRANSCRIPTION_CAPABILITIES,
    "language_identification": True,
    "streaming": True,
}
NEMO_ASR_DEPENDENCIES = ["nemo_toolkit[asr]>=2.5.0", "torch>=2.6"]
NEMO_SALM_DEPENDENCIES = [
    "nemo_toolkit[asr,tts]>=2.5.0",
    "torch>=2.6",
]
TRANSFORMERS_ASR_DEPENDENCIES = [
    "transformers>=4.52.4",
    "torch",
    "torchaudio",
    "peft",
    "soundfile",
    "accelerate",
]
QWEN_ASR_DEPENDENCIES = ["qwen-asr", "flash-attn (optional, recommended for CUDA)"]


CATALOG_ENTRIES = (
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-tiny",
        "Faster-Whisper Tiny",
        "transcription",
        75_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-tiny",
        requirements=_requirements(75_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-base",
        "Faster-Whisper Base",
        "transcription",
        145_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-base",
        requirements=_requirements(145_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-small",
        "Faster-Whisper Small",
        "transcription",
        490_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-small",
        requirements=_requirements(490_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-medium",
        "Faster-Whisper Medium",
        "transcription",
        1_500_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-medium",
        requirements=_requirements(1_500_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-large-v3",
        "Faster-Whisper Large v3",
        "transcription",
        3_100_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-large-v3",
        requirements=_requirements(3_100_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "faster_whisper",
        "Systran/faster-whisper-turbo",
        "Faster-Whisper Turbo",
        "transcription",
        1_600_000_000,
        source_url="https://huggingface.co/Systran/faster-whisper-turbo",
        requirements=_requirements(1_600_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_local",
        "tiny",
        "Whisper Tiny",
        "transcription",
        75_000_000,
        requirements=_requirements(75_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_local",
        "base",
        "Whisper Base",
        "transcription",
        145_000_000,
        requirements=_requirements(145_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_local",
        "small",
        "Whisper Small",
        "transcription",
        490_000_000,
        requirements=_requirements(490_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_local",
        "medium",
        "Whisper Medium",
        "transcription",
        1_500_000_000,
        requirements=_requirements(1_500_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_local",
        "large-v3",
        "Whisper Large v3",
        "transcription",
        3_100_000_000,
        requirements=_requirements(3_100_000_000),
        capabilities=DEFAULT_CAPABILITIES,
    ),
    CatalogEntry(
        "whisper_cpp",
        "ggml-tiny.bin",
        "Whisper.cpp Tiny",
        "transcription",
        77_691_713,
        source_url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-tiny.bin",
        requirements={"recommended_device": "cpu", "min_ram_bytes": 512_000_000},
        capabilities=WHISPER_CPP_CAPABILITIES,
        checksum="sha256:be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21",
    ),
    CatalogEntry(
        "whisper_cpp",
        "ggml-base.bin",
        "Whisper.cpp Base",
        "transcription",
        147_951_465,
        source_url="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.bin",
        requirements={"recommended_device": "cpu", "min_ram_bytes": 1_000_000_000},
        capabilities=WHISPER_CPP_CAPABILITIES,
        checksum="sha256:60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe",
    ),
    CatalogEntry(
        adapter_key="nemo_salm",
        model_identifier="nvidia/canary-qwen-2.5b",
        name="Canary Qwen 2.5B",
        model_type="transcription",
        size_bytes=5_120_000_000,
        source_url="https://huggingface.co/nvidia/canary-qwen-2.5b",
        requirements=_requirements(
            5_120_000_000,
            min_ram_bytes=16_000_000_000,
            recommended_device="cuda",
            requires_cuda=True,
            download_backend="huggingface_hub",
            python_dependencies=NEMO_SALM_DEPENDENCIES,
        ),
        capabilities=CANARY_QWEN_CAPABILITIES,
    ),
    CatalogEntry(
        adapter_key="transformers_asr",
        model_identifier="ibm-granite/granite-speech-3.3-8b",
        name="Granite Speech 3.3 8B",
        model_type="transcription",
        size_bytes=17_400_000_000,
        source_url="https://huggingface.co/ibm-granite/granite-speech-3.3-8b",
        requirements=_requirements(
            17_400_000_000,
            min_ram_bytes=32_000_000_000,
            recommended_device="cuda",
            download_backend="huggingface_hub",
            python_dependencies=TRANSFORMERS_ASR_DEPENDENCIES,
        ),
        capabilities=GRANITE_SPEECH_CAPABILITIES,
    ),
    CatalogEntry(
        adapter_key="nemo_asr",
        model_identifier="nvidia/parakeet-tdt-1.1b",
        name="Parakeet TDT 1.1B",
        model_type="transcription",
        size_bytes=4_280_000_000,
        source_url="https://huggingface.co/nvidia/parakeet-tdt-1.1b",
        requirements=_requirements(
            4_280_000_000,
            min_ram_bytes=12_000_000_000,
            recommended_device="cuda",
            requires_cuda=True,
            download_backend="huggingface_hub",
            python_dependencies=NEMO_ASR_DEPENDENCIES,
        ),
        capabilities={**HF_TRANSCRIPTION_CAPABILITIES, "languages": ["en"]},
    ),
    CatalogEntry(
        adapter_key="qwen_asr",
        model_identifier="Qwen/Qwen3-ASR-1.7B",
        name="Qwen3-ASR 1.7B",
        model_type="transcription",
        size_bytes=4_700_000_000,
        source_url="https://huggingface.co/Qwen/Qwen3-ASR-1.7B",
        requirements=_requirements(
            4_700_000_000,
            min_ram_bytes=16_000_000_000,
            recommended_device="cuda",
            requires_cuda=True,
            download_backend="huggingface_hub",
            python_dependencies=QWEN_ASR_DEPENDENCIES,
        ),
        capabilities=QWEN_ASR_CAPABILITIES,
    ),
)


def seed_model_catalog(db: Session) -> None:
    existing = {(item.adapter_key, item.model_identifier): item for item in db.scalars(select(ModelCatalog))}
    for entry in CATALOG_ENTRIES:
        item = existing.get((entry.adapter_key, entry.model_identifier))
        if item is None:
            db.add(
                ModelCatalog(
                    adapter_key=entry.adapter_key,
                    model_identifier=entry.model_identifier,
                    name=entry.name,
                    model_type=entry.model_type,
                    source_url=entry.source_url,
                    revision=entry.revision,
                    size_bytes=entry.size_bytes,
                    requirements=entry.requirements,
                    capabilities=entry.capabilities,
                    checksum=entry.checksum,
                )
            )
            continue
        item.name = entry.name
        item.model_type = entry.model_type
        item.source_url = entry.source_url
        item.revision = entry.revision
        item.size_bytes = entry.size_bytes
        item.requirements = entry.requirements
        item.capabilities = entry.capabilities
        item.checksum = entry.checksum
    db.commit()
