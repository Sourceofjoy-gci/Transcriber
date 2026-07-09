# Transcriber Platform Planning Package

## Scope and approval boundary

This package is the pre-implementation design for a modular, local-first AI transcription platform. It deliberately does **not** create application code, Docker files, dependencies, migrations, or model downloads. Implementation begins only after approval of this design.

## Recommended baseline

| Area                   | Choice                                                                    | Reason                                                                           |
| ---------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Frontend               | React, Vite, TypeScript, Tailwind CSS, shadcn/ui                          | Fast local development and a maintainable application UI.                        |
| Backend                | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2                           | Typed API contracts and excellent ML ecosystem compatibility.                    |
| Data                   | PostgreSQL, Alembic, Redis                                                | Durable relational data plus queue/state support.                                |
| Jobs                   | Celery workers with Redis broker/result backend                           | Separates long model execution from HTTP request handling.                       |
| Local AI               | Faster-Whisper first; Whisper and Whisper.cpp adapters                    | Strong GPU/CPU coverage behind a provider contract.                              |
| Multimodal and text AI | OpenAI-compatible and local-service adapters; Hugging Face model metadata | Supports Qwen, Ollama, vLLM, LM Studio, and future models without core rewrites. |
| Media                  | FFmpeg/ffprobe in workers                                                 | Reliable metadata extraction and video-to-audio conversion.                      |
| Storage                | Local filesystem adapter first, S3-compatible adapter next                | Local-first deployment while preserving production portability.                  |
| Deployment             | Docker Compose profiles for CPU/GPU behind Caddy                          | Simple local/server deployment with automatic TLS in production.                 |

## Design principles

1. **Local-first and explicit egress:** external APIs are opt-in per organisation, project, and job.
2. **Provider neutrality:** workflow code depends on task-specific interfaces, not on Whisper or any vendor SDK.
3. **Async by default:** model downloads, media processing, transcription, exports, and reports run as observable background jobs.
4. **Tenant isolation:** every user-owned record is scoped to an organisation; access checks happen in services, not only the UI.
5. **Immutable originals, versioned derivatives:** original media is preserved until deletion; transcript edits and AI outputs are versioned.
6. **Operational honesty:** model capability and hardware constraints are exposed before a job starts, not hidden behind vague failures.

## Documents

- [Architecture](01-architecture.md)
- [Database schema](02-database-schema.md)
- [API contract](03-api-contract.md)
- [Frontend page map](04-frontend-page-map.md)
- [Provider adapter design](05-provider-adapters.md)
- [Implementation plan](06-implementation-plan.md)
- [Security and privacy plan](07-security-and-privacy.md)
- [Deployment plan](08-deployment.md)

## Decisions to confirm before implementation

1. Use the recommended React/Vite + FastAPI/Celery/PostgreSQL stack.
2. Start with organisation-scoped accounts and local-email/password authentication; add SSO in a later phase.
3. Make Faster-Whisper the default local transcription backend, with Whisper and Whisper.cpp available as adapters.
4. Treat Qwen as a pluggable multimodal/post-processing capability, initially through a configured local/OpenAI-compatible inference endpoint rather than bundling a particular Qwen runtime.
5. Ship local filesystem storage first and make S3/MinIO the first additional storage adapter.
6. Begin implementation with Phase 1 and deliver working vertical slices at each phase gate.
