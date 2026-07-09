# Phase 0–2 Implementation Status

## Delivered

- FastAPI, PostgreSQL/Alembic, Redis/Celery, React/Vite/Tailwind, Caddy, CPU worker, and GPU worker Compose profile.
- Tenant-scoped users, memberships, roles, granular permissions, refresh-token rotation, CSRF protection for cookie sessions, CORS allowlisting, and audit records.
- Local private storage adapter with root confinement, filename sanitisation, byte signature validation, checksumming, upload-size enforcement, controlled download endpoint, and a malware-scanner hook. The development placeholder is rejected in production until a real scanner adapter is configured.
- Media asset, metadata, transcription-job, attempt/event, settings, and audit schema; initial Alembic migration.
- FFprobe metadata worker that records duration/stream details and safely marks corrupt or unreadable media as failed.
- Dashboard, login, upload-progress, and jobs user interfaces.
- Provider interfaces and registry so Phase 2 model adapters do not alter the web workflow.
- Faster-Whisper and official Whisper adapters with device, compute, beam, VAD, translation, and optional word-timestamp settings.
- Queue-driven FFmpeg audio normalization, optional fixed-duration chunking, transcription progress/events, cancellation checks, versioned transcript persistence, and TXT/JSON/SRT/VTT export workers.
- Read-only transcript archive/viewer and core export controls.

## Deliberately deferred to the approved next phase

- Whisper.cpp, administrator-managed model downloads, hardware recommendations, and model lifecycle controls.
- API provider configuration, encrypted credential persistence, external egress confirmations, transcript editing, reports, and multimodal/Qwen adapters.

## Local verification

```text
cd backend
pip install -e ".[dev,ai]"
pytest
ruff check app tests

cd ../frontend
npm install
npm run build
```

Run `docker compose --profile cpu up --build` after copying `.env.example` to `.env` and replacing the placeholder values.
