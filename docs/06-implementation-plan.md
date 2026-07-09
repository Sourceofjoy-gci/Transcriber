# Phased Implementation Plan

Each phase ends with working tests, documentation updates, and a demonstrable vertical slice. New dependencies are locked and scanned before use. No phase must hard-code a provider assumption that blocks a later phase.

## Phase 0 — Repository and operating baseline

- Create monorepo structure, formatting/linting, dependency lockfiles, CI workflow, environment examples, Docker development baseline, and contribution docs.
- Establish FastAPI/React health pages, configuration loading, structured logging, correlation IDs, and a test database fixture strategy.
- **Exit gate:** fresh checkout can run tests and a minimal authenticated health flow with documented commands.

## Phase 1 — Secure foundation and media intake

- Build PostgreSQL/Alembic schema for organisations, users, roles/permissions, projects, media, audit, and settings.
- Implement local authentication, token/session rotation, tenant-scoped RBAC middleware/services, rate limits, and audit events.
- Implement local storage adapter, validated multipart upload, media quarantine status, ffprobe metadata extraction task, and job status UI shell.
- **Exit gate:** authorised users upload supported media, see durable metadata/progress, and unauthorised access is rejected and audited.

## Phase 2 — Provider framework and local transcription

- Implement provider registry, normalized models/results, hardware probe, job state machine, Celery orchestration, retry/cancellation rules, and worker health.
- Implement Faster-Whisper adapter first, plus official Whisper adapter behind the same contract; add FFmpeg video audio extraction and long-file chunking.
- Persist transcripts/segments/words and build read-only transcript viewer with TXT, JSON, SRT, and VTT exports.
- **Exit gate:** a local model completes audio and video transcription in the background with status events and timestamped exports.

## Phase 3 — Model manager and lightweight backend

- Add model catalog, installed-model state, background downloads with checksum/size progress, enable/disable/delete/test, task defaults, and hardware recommendations.
- Add Whisper.cpp adapter as an optional separately enabled lightweight runtime, including conformance tests and resource/error handling.
- **Exit gate:** administrators can manage model lifecycle in the UI and workers only route to healthy enabled models.

## Phase 4 — API providers and external-use controls

- Add encrypted provider secrets, provider configuration schemas, usage/error logs, external-egress policy checks, and configuration test actions.
- Implement OpenAI-compatible and generic REST transcription adapters with declarative constrained mappings.
- **Exit gate:** an administrator can configure a provider safely; a permitted user sees an explicit egress warning; credentials never appear in API/UI/log output.

## Phase 5 — Transcript editor and full export set

- Add player/waveform, timestamp synchronisation, editable speaker-labelled segments, split/merge, notes, search/replace, autosave, version history, and conflict handling.
- Implement DOCX, PDF, CSV, Markdown, and HTML exports, selected-section exports, and short-lived result downloads.
- **Exit gate:** reviewers can make non-destructive edits while playback follows the transcript and produce all requested formats.

## Phase 6 — Post-processing and multimodal adapters

- Add task schemas and AI-run lineage for cleanup, grammar, filler removal, translation, topics, decisions, action items, entities, Q&A, and keywords.
- Implement local/OpenAI-compatible text and multimodal service adapters, including Qwen-compatible model catalog/configuration paths based on actual endpoint capabilities.
- **Exit gate:** each task produces reviewable derived versions/results and respects local-only/external policy.

## Phase 7 — Reports, analytics, and operational administration

- Build structured report templates: presentation, meeting, workshop, benchmarking, training, legal/policy, technical demo, and project implementation; support custom templates.
- Deliver dashboards, costs, storage metrics, audit views, retention controls, and administrator diagnostics.
- **Exit gate:** reports trace to transcript version/template, dashboards aggregate correctly, and audit queries explain sensitive access.

## Phase 8 — Production readiness

- Add CPU/GPU Docker Compose profiles, Caddy reverse proxy, production configuration validation, migration/backup/restore runbooks, security headers, observability hooks, and load/retention tests.
- Perform threat-model review, dependency/security scanning, accessibility pass, API compatibility review, and operator documentation completion.
- **Exit gate:** documented production deployment passes smoke tests on CPU and CUDA-capable hosts with no dev secrets/configuration.

## Test strategy by layer

| Layer          | Coverage                                                                                                                      |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Unit           | Provider normalisation, RBAC policy, schema validation, export rendering, retry/error classifiers.                            |
| Integration    | Upload/metadata tasks, Celery state transitions, encryption/decryption boundaries, storage adapters, model/API fake services. |
| End-to-end     | Login, permitted upload-to-transcript, editor save/version, export, admin model/provider flow, local-only policy block.       |
| Non-functional | Large-file handling, cancellation/retry, secrets redaction, accessibility keyboard paths, backup/restore smoke test.          |

## First implementation increment after approval

Start Phase 0 and Phase 1 as a cohesive foundation: initialize the monorepo, compose development services, build the first migration/auth/RBAC model, and deliver secure upload + ffprobe metadata flow before pulling any Whisper or Qwen model dependencies. This avoids heavyweight AI setup before the system can safely store, authorise, and observe media.
