# Phase 0–6 Implementation Status

Date: 2026-06-25

## Governing update — 2026-07-16

This dated inventory is retained as historical implementation evidence. The [approved selective-port Phase 1 design](superpowers/specs/2026-07-16-selective-port-phase-1-schema-baseline-design.md) now governs repository scope and precedence.

- PostgreSQL 16 is the only authoritative migration target; the canonical head is `0012_schema_reconciliation`.
- Production migration is a backed-up, controlled one-shot Alembic step completed before API rollout, not an API-startup side effect.
- Transcriber remains the authoritative product database. Voicebox databases are not merged into its schema.
- Voicebox text-to-speech, voice cloning and voice profiles, Tauri, and story generation are excluded from the unified transcription release.
- The July 10 production-readiness and July 13 universal-download documents are superseded historical plans.

This document replaces the earlier `09-foundation-status.md` and
`10-implementation-audit.md` after the most recent gap-analysis pass.

## Delivered

- FastAPI, PostgreSQL/Alembic, Redis/Celery, React/Vite/Tailwind, Caddy,
  CPU worker, and GPU worker Compose profile.
- Tenant-scoped users, memberships, roles, granular permissions,
  refresh-token rotation, CSRF protection for cookie sessions, CORS
  allowlisting, audit records, and per-endpoint rate limiting.
- Local private storage adapter with root confinement, filename
  sanitisation, byte signature validation, checksumming, upload-size
  enforcement, controlled download endpoint, and a malware-scanner hook.
- Media asset, metadata, transcription-job, attempt/event, settings, and
  audit schema; seven incremental Alembic migrations.
- FFprobe metadata worker that records duration/stream details and safely
  marks corrupt or unreadable media as failed.
- Dashboard, login, upload-progress, jobs, transcripts, models, providers,
  reports, audit, settings, and users UI shells.
- Provider interfaces and registry so the worker can route to local or
  external adapters.
- Faster-Whisper and official Whisper adapters with device, compute,
  beam, VAD, translation, and optional word-timestamp settings.
- Queue-driven FFmpeg audio normalization, optional fixed-duration
  chunking, transcription progress/events, cancellation checks,
  retry/resume, versioned transcript persistence, and TXT/JSON/SRT/VTT/
  CSV/Markdown/HTML/DOCX/PDF export workers.
- Read-only transcript archive/viewer with edit/split/merge/annotate/
  search/version-restore controls.
- Encrypted API-provider configuration with rotate-secret, test, enable/
  disable, default selection, and usage tracking.
- Stub post-processing provider covering clean, summary, minutes,
  action items, topics, entities, Q&A, and translation tasks.
- Eight seeded report templates (presentation, meeting, workshop,
  benchmarking, training, legal/policy, technical demo, project
  implementation) with a worker-driven report generator.

## Deferred (not in current scope)

- Whisper.cpp adapter.
- Real (non-stub) speaker diarisation.
- Production translation model integration.
- Frontend pages for AI runs, settings, audit, and user management.

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

Run `docker compose --profile cpu up --build` after copying
`.env.example` to `.env`, generating `CREDENTIAL_ENCRYPTION_KEY`, and
replacing the remaining placeholder values.
