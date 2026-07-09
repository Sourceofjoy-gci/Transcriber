# Transcriber Platform

Local-first, provider-based transcription infrastructure for sensitive audio and video. The application includes secure identity/RBAC, validated media upload, local and S3-compatible storage, FFmpeg/FFprobe processing, local Whisper/Faster-Whisper/Whisper.cpp adapters, optional external API transcription, diarisation controls, transcript editing, report templates, scoped exports, model management, administration surfaces, and operational health checks.

The architecture and phase plan are in [docs/00-planning-index.md](docs/00-planning-index.md). Contributor setup and operational smoke checks are in [CONTRIBUTING.md](CONTRIBUTING.md).

## Prerequisites

- Docker Desktop with Docker Compose v2
- Optional: NVIDIA Container Toolkit for the GPU worker profile

## Quick Start

1. Copy `.env.example` to `.env` and replace every placeholder secret.
2. Start the CPU profile: `docker compose --profile cpu up --build`.
3. Open `http://localhost:8088` and sign in with the bootstrap administrator values from `.env`.
4. Upload supported media; the worker records duration and stream metadata using `ffprobe`.
5. Queue transcription after the asset becomes ready. The CPU worker uses Faster-Whisper by default and caches downloaded models in the protected model volume.
6. Review transcripts, assign speakers, run AI post-processing, generate reports, and export selected transcript sections from the web UI.

For a CUDA worker, add `--profile gpu`. The GPU worker installs the advanced speech runtime extra used by NeMo, Qwen3-ASR, and Transformers-based Hugging Face models in Model Manager. Add `--profile clamav` when `MALWARE_SCANNER_MODE=clamav` is enabled.

## Development Commands

```text
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -c requirements.lock -e ".[dev]"
python -m alembic upgrade head
python -m pytest

cd ../frontend
npm ci
npm run dev
```

The API is served at `http://localhost:8000/api/v1`; Caddy publishes the composed application at `http://localhost:8088`.

## Verification

```text
cd backend
python -m ruff check .
python -m pytest

cd ../frontend
npm test
npm run lint
npm run build
npm audit --audit-level=high
```

## Security Notes

- Do not use the example values in any shared environment.
- Bootstrap credentials are an initial-access mechanism only; rotate them and remove them from deployment configuration after first use.
- Uploaded files remain private storage objects. API responses expose IDs, never filesystem paths.
- External AI/API use remains disabled by default.
- Provider secrets and structured audit/log metadata are redacted before they leave trusted backend paths.
