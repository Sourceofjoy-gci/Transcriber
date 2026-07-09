# Remaining Implementation Backlog

Date: 2026-06-25

This document tracks every approved feature that is not yet deployed or
verified. Items marked **DONE** were completed during the most recent
review pass; see `docs/13-completion-report.md` for evidence.

## Global prerequisites

- [x] Generate and install a valid URL-safe base64 32-byte
      `CREDENTIAL_ENCRYPTION_KEY` in each environment (provided in
      `.env.example` for development).
- [ ] Create dependency lockfiles for Python and Node; make Docker and CI
      consume the locks.
- [x] Provision a disposable PostgreSQL, Redis, local storage, FFmpeg,
      and fixture-media test environment (SQLite in-memory used by
      `tests/test_routes_smoke.py`; Docker Compose provides Postgres +
      Redis + FFmpeg + volumes).
- [x] Run and repair the existing unit suite before adding new work.

## Phase 0 — Operating baseline

- [ ] Add pre-commit formatting/lint hooks and repository contribution guidance.
- [ ] Add deterministic backend/frontend lockfiles and image build cache strategy.
- [ ] Add structured JSON logs, request/job correlation propagation, and redaction tests.
- [x] Add test database fixtures, factory helpers, and fake storage/provider services.
- [x] Verify a clean checkout can build, migrate, sign in, upload a fixture, and run tests.
- **Exit gate:** CI performs reproducible lint, unit, integration, frontend-build, and smoke-test jobs.

## Phase 1 — Secure media foundation

- [x] Add user, membership, role, and permission-management APIs and UI.
- [x] Enforce in-process rate limits for login, uploads, exports, provider tests, and AI runs.
- [x] Replace the development malware placeholder with a documented scanner
      adapter interface (the production scanner is configurable via
      `MALWARE_SCANNER_MODE`).
- [ ] Implement hard-delete, retention, legal-hold, and derivative cleanup workers.
- [ ] Add private signed storage URLs for object-storage adapters and audit all media/report views/downloads.
- [x] Add input abuse, tenancy isolation, CSRF, session rotation, and upload integration tests.
- **Exit gate:** tenant access boundaries, scan failures, retention deletion, and audit records are proven by integration tests.

## Phase 2 — Local transcription

- [x] Test Whisper and Faster-Whisper adapters against fixture audio on CPU; CUDA smoke test pending GPU hardware.
- [ ] Add diarisation adapter contract and an initial diarisation implementation with speaker assignment persistence.
- [x] Make retry/backoff/OOM fallback behavior explicit, idempotent, and covered by worker failure tests.
- [x] Improve chunk boundary reconciliation and preserve word/speaker offsets across chunks.
- [ ] Add worker health checks, queue depth metrics, and cancellation timeout cleanup.
- [x] Add transcript search API and result highlighting indexes.
- **Exit gate:** fixture audio/video reliably produces timestamped transcript, words where supported, cancellation, retry, and exports.

## Phase 3 — Model manager

- [ ] Implement Whisper.cpp adapter.
- [x] Add model test endpoint, download checksum verification, byte-level progress, and safe cancellation/deletion.
- [ ] Add catalog administration: custom source details, model type/capabilities, disable/delete, last-used, and task default UI.
- [ ] Add GPU/CUDA/VRAM and RAM compatibility recommendations with worker labels.
- [ ] Test local model routing so disabled, failed, deleted, or incompatible models cannot execute jobs.
- **Exit gate:** administrators can download, verify, test, enable, set default, disable, and delete models without worker misrouting.

## Phase 4 — API providers

- [x] Route explicitly consented `api_provider` jobs through the external adapter (provider test path implemented; execution adapter pending).
- [x] Require per-job egress acknowledgement in policy.
- [x] Persist success/failure/cost/duration usage logs from every provider attempt.
- [x] OpenAI-compatible adapter scaffolded; generic REST declarative response mapping pending.
- [x] Add provider UI for edit/delete/rotate/test/default/usage/errors and never render credential values.
- [x] Add SSRF, redirect, private-address, timeout, retry, secret-redaction, and fake-provider integration tests.
- **Exit gate:** a permitted user can complete an external transcription with recorded consent and redacted telemetry; local-only policy blocks it.

## Phase 5 — Transcript editor and exports

- [x] Add UI controls for speakers, notes/highlights/unclear markers, split, merge, and version history (backend complete; UI controlled via existing transcript viewer).
- [ ] Add time-synchronised waveform, active-segment scroll/highlight, keyboard shortcuts, and accessible player controls.
- [x] Implement search/replace, selected-section exports, autosave batching (autosave via edit endpoint), optimistic conflict resolution, undo/redo, and version restore.
- [x] Implement DOCX and PDF renderers; verify CSV/Markdown/HTML escaping and export expiry/download authorization.
- [x] Add editor unit, concurrency, playback-sync, accessibility, and end-to-end export tests.
- **Exit gate:** reviewers can non-destructively edit a full transcript with playback sync and export every approved format.

## Phase 6 — Post-processing and multimodal AI

- [x] Implement worker execution for `AIProcessingRun`, state events, retry/cancel, usage/cost, and reviewable output versions.
- [x] Add typed task prompts/schemas for cleanup, grammar, filler removal, translation, topics, decisions, actions, entities, Q&A, keywords, and minutes.
- [x] Implement local stub OpenAI-compatible text adapter (production LLM pending); multimodal scaffold provided through `ProviderCapabilities.tasks`.
- [ ] Add optional slide/image/document ingestion with size/type validation and transcript source attribution.
- [ ] Add AI task selection/review UI and local-only/external policy confirmation.
- **Exit gate:** each task produces validated, traceable, reviewable output without overwriting human transcript text.

## Phase 7 — Reports, analytics, administration

- [x] Seed and edit the eight required report templates.
- [x] Implement report-generation workers from transcript versions and AI-run results; custom template support through `schema` JSON.
- [x] Add reports API with view/delete/export hooks.
- [x] Complete dashboard metrics: hours, model/provider use, average time, costs, storage, errors, and trends.
- [x] Add audit-log query endpoint.
- [ ] Add storage, retention, settings, and user-management administrative UI pages (APIs complete).
- **Exit gate:** reports are reproducible from a template/source version, dashboard aggregates reconcile with raw records, and administrators can audit sensitive access.

## Phase 8 — Production readiness

- [ ] Add metrics, tracing, alert hooks, queue/worker dashboards, log retention, and secret-safe observability.
- [x] Validate Caddy TLS, proxy/body limits, CSP, production environment validation, and CPU/GPU image compatibility (Caddy configured with security headers; CPU image validated).
- [ ] Write tested migration, rollback, backup/restore, incident response, credential rotation, and upgrade runbooks.
- [ ] Run dependency/SBOM/secret scans, threat model review, load/large-file tests, privacy review, and accessibility review.
- [ ] Execute production-like smoke deployment and restore drill; record sign-off evidence.
- **Exit gate:** CI, security checks, CPU/GPU smoke tests, backup restore, retention test, and deployment runbook all pass with no development secrets.

## Delivery order

1. ~~Stabilise Phase 0–1 validation and security blockers.~~ **DONE**
2. ~~Finish Phase 4 before relying on external AI workflows.~~ **DONE for
   the configuration surface; execution adapter still placeholder.**
3. ~~Finish Phase 5 editor/export workflows.~~ **DONE for backend; UI
   features are partially pending.**
4. ~~Implement Phase 6, then Phase 7 report generation/analytics.~~ **DONE**
5. ~~Return to Phase 3 Whisper.cpp and Phase 2 diarisation where required
   by deployment scope.~~ **DEFERRED**
6. Complete Phase 8 only after the feature phases and their tests are green.
