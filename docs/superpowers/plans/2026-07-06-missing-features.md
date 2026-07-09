# Missing Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gap between the documented Transcriber Platform scope and the behavior currently implemented in the FastAPI, Celery, and React application.

**Architecture:** Repair broken frontend/backend contracts first, then implement one end-to-end vertical slice at a time: API schema, persistence, worker behavior, React UI, and tests. Preserve the existing FastAPI route modules, SQLAlchemy models, Celery task structure, React pages, and TanStack Query API layer.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, Celery, Redis, React 18, Vite, TypeScript, Tailwind, Vitest, pytest.

---

## Review Summary

Review date: 2026-07-06

Verification run:

- `cd backend && python -m pytest -q`: PASS, 49 tests.
- `cd frontend && npm.cmd run build`: PASS.
- `cd frontend && npm.cmd test -- --run`: PASS, 6 tests.
- `git status --short`: not available because the workspace is not recognized as a valid Git repository despite containing a `.git` directory.

The current test suite passes, but it does not exercise multiple runtime contract mismatches and planned product flows. The highest-risk gaps are external provider transcription, API-provider UI shape drift, AI post-processing target routing, transcript editor completeness, storage/retention lifecycle, and production operations.

## Missing Or Incomplete Features

### 1. External API Transcription Is Not End-To-End

Evidence:

- `backend/app/worker/tasks.py:102` rejects every `api_provider` transcription job with `provider_not_configured`.
- `backend/app/providers/external.py:14` contains an external transcription helper, but it is not called by the transcription worker.
- `frontend/src/App.tsx:524` hard-codes `External API` as "Not used for this workflow".
- `frontend/src/lib/api.ts:139` allows `execution_target_kind: "api_provider"`, but the upload UI cannot select one.

Missing behavior:

- Provider target validation for enabled provider, category, capabilities, and secret presence.
- Per-job egress acknowledgement and project-level external API policy enforcement.
- Worker execution through `app.providers.external.transcribe`.
- Provider usage logging for success/failure/cost/duration.
- Upload UI provider selection, consent warning, and policy-block messaging.
- Generic REST declarative response mapping.

### 2. API Provider Frontend Does Not Match Backend

Evidence:

- Backend expects `adapter_key`, `name`, `base_url`, `endpoint_path`, `model_name`, and `api_key` in `backend/app/api/routes/providers.py:24`.
- Frontend sends `label`, `provider_kind`, `endpoint_url`, `default_model`, and `secret` in `frontend/src/lib/api.ts:315`.
- Secret rotation sends `{ secret }` in `frontend/src/lib/api.ts:338`, while backend expects `{ api_key }`.
- UI reads `provider.label`, `provider.is_enabled`, `provider.provider_kind`, and `provider.endpoint_url` in `frontend/src/pages/ProvidersPage.tsx:276`, while backend returns `name`, `enabled`, `adapter_key`, and `base_url`.
- Provider usage UI expects aggregate totals in `frontend/src/pages/ProvidersPage.tsx:432`; backend returns a list of raw usage rows in `backend/app/api/routes/providers.py:251`.

Missing behavior:

- A shared frontend type that matches `ProviderResponse`.
- Working create/update/rotate/test/default/delete flows from the Providers page.
- Aggregate provider usage API or matching UI for raw usage rows.
- UI removal or backend support for unsupported `anthropic_compatible` provider kind.

### 3. AI Post-Processing Is Stub-Only And Target Selection Is Ignored

Evidence:

- `backend/app/worker/post_processing_tasks.py:52` always uses `settings.post_processing_provider`.
- `backend/app/providers/registry.py:43` registers only `StubPostProcessingProvider`.
- `backend/app/providers/post_processing.py:32` implements deterministic stub tasks only.
- `backend/app/api/routes/ai.py:31` only supports create; `backend/app/api/routes/ai.py:75` only supports get by ID.
- `frontend/src/pages/AIRunsPage.tsx:115` lists providers using stale provider fields.

Missing behavior:

- OpenAI-compatible/local-service post-processing adapter for real summary, cleanup, translation, extraction, and minutes tasks.
- Use of `execution_target_kind` and `execution_target_id` in worker routing.
- AI-run list endpoint, cancel/retry endpoint, and progress/event surface.
- Reviewable output versions for cleanup/translation tasks instead of result JSON only.
- Local-only and external-egress confirmation enforcement for AI tasks.
- Optional slide/image/document ingestion with validation and source attribution.

### 4. Transcript Editor Is Partial

Evidence:

- Documented editor requirements are in `docs/04-frontend-page-map.md:34`.
- `backend/app/schemas/transcripts.py:25` omits `speaker_id` from segment responses, while frontend expects it in `frontend/src/types.ts:142`.
- `backend/app/schemas/transcripts.py:43` segment edits can update text, notes, and unclear state only.
- `backend/app/api/routes/transcripts.py:71` creates a full new version per segment edit with no version precondition.
- `backend/app/api/routes/transcripts.py:263` supports split and `backend/app/api/routes/transcripts.py:315` supports merge, but these actions do not expose keyboard shortcuts, undo/redo, operation history, or conflict handling.
- `frontend/src/pages/TranscriptViewerPage.tsx:193` provides search, but no search/replace.

Missing behavior:

- `speaker_id` in segment API responses and speaker assignment from the editor.
- Speaker creation UI and segment speaker assignment UI.
- Autosave batching with optimistic concurrency using version preconditions.
- Undo/redo backed by durable edit operations.
- Search/replace.
- Keyboard shortcuts for playback, navigation, split, merge, speaker assignment, annotation, undo, and redo.
- Separate annotation persistence for notes/highlights/unclear markers.
- Accessible player controls, waveform, timestamp ruler, and active segment scroll/highlight beyond the current basic audio element.
- Word-level display when word timestamps exist.

### 5. Diarisation Is Not Implemented

Evidence:

- Backlog lists diarisation as pending in `docs/12-implementation-backlog.md:46`.
- `backend/app/providers/contracts.py` has no diarisation provider contract.
- `backend/app/worker/tasks.py:444` persists transcript segments but does not create speakers from provider speaker labels.

Missing behavior:

- Diarisation adapter contract.
- Initial diarisation provider, such as pyannote.audio or another configured local service.
- Speaker creation and assignment during transcript persistence.
- Diarisation options in job request validation and upload UI.
- Tests proving speaker labels survive chunking, editing, and exports.

### 6. Media Derivatives, Signed URLs, Storage Adapters, And Retention Are Missing

Evidence:

- API contract lists `/assets/{id}/derivatives` in `docs/03-api-contract.md:28`, but `backend/app/api/routes/assets.py` has no derivatives route.
- `backend/app/api/routes/assets.py:98` returns a direct `FileResponse` for original media downloads.
- SQLAlchemy models do not include a `MediaDerivative` table, despite the schema document listing it.
- `backend/app/api/routes/assets.py:115` soft-deletes assets only.
- Backlog lists retention/hard delete/legal hold cleanup workers as pending in `docs/12-implementation-backlog.md:38`.

Missing behavior:

- Media derivative model and Alembic migration.
- Waveform, normalized audio, thumbnail, and chunk derivative workers.
- Signed private URLs or equivalent short-lived download authorization for object storage.
- S3/MinIO-compatible storage adapter.
- Hard-delete, retention, legal-hold, and derivative cleanup workers.
- Storage management UI with usage, retention state, purge requests, and provider health.
- Audit records for all media/report view and download actions.

### 7. Project, Asset Library, Settings, Organisation, And Role Administration Are Incomplete

Evidence:

- API contract lists project detail/update/delete in `docs/03-api-contract.md:23`; backend only has list/create in `backend/app/api/routes/projects.py:19`.
- API contract lists `/users/me`, `/organisations`, and `/roles` in `docs/03-api-contract.md:13`; backend only exposes auth session and user management.
- `frontend/src/App.tsx:156` has no route for `/storage`, `/help`, `/report-templates`, or project/asset management.
- Settings page writes arbitrary key/value records in `frontend/src/pages/SettingsPage.tsx:81`.
- `backend/app/models/domain.py` stores `SystemSetting.value` as JSON even when `is_secret=True`.

Missing behavior:

- Project detail, update, delete, policy UI, and project selector in upload/transcript/archive views.
- Asset library page with filters, project awareness, delete/download, and metadata.
- Structured settings controls for upload limits, retention, local-only policy, external API policy, queue policy, and post-processing provider defaults.
- Secret-safe settings storage or removal of `is_secret` from this generic settings API.
- User profile update endpoint for display settings.
- Organisation management API/UI.
- Custom role CRUD and permission assignment UI.
- Multi-organisation switcher instead of always selecting the first membership.
- Help/operator documentation page.

### 8. Reports And Report Templates Are Partial

Evidence:

- Frontend page map lists `/report-templates` in `docs/04-frontend-page-map.md:15`; frontend has no route.
- Backend nests template routes under `/reports/templates` in `backend/app/api/routes/reports.py:55`.
- Backend has list/create template routes only; no patch/delete/enable/preview.
- Report worker always generates minutes-derived sections in `backend/app/worker/post_processing_tasks.py:94`.
- API contract lists report `PATCH` and export hooks in `docs/03-api-contract.md:88`; backend has get/delete only.

Missing behavior:

- Report template manager page.
- Template patch/delete/enable/disable/preview endpoints.
- Template schema-driven report generation.
- Report status progression to `generating`.
- Report edit endpoint.
- Report export endpoint or integration with the export queue.
- Report error fields and completed timestamps in API responses if the UI keeps those fields.

### 9. Export Workflows Are Incomplete

Evidence:

- `backend/app/schemas/transcripts.py:97` export creation accepts only `transcript_id`, `format`, and `options`.
- `backend/app/api/routes/exports.py:24` exports only active transcript versions.
- API contract says exports can be for transcript, report, or selected segments in `docs/03-api-contract.md:91`.

Missing behavior:

- Selected-segment export request contract.
- Report export support.
- Export source type/source ID contract.
- Export download audit logging.
- UI for selecting transcript sections before export.

### 10. Model Manager And Hardware Routing Are Partial

Evidence:

- Planning docs require Whisper.cpp in `docs/06-implementation-plan.md:28`.
- `backend/app/providers/registry.py:40` registers only Faster-Whisper and official Whisper.
- `backend/app/worker/model_tasks.py:30` downloads models but does not verify catalog checksums.
- `backend/app/api/routes/models.py:116` test endpoint probes the adapter, not a specific downloaded model.
- `frontend/src/lib/api.ts:429` has a `putTaskDefault` helper with the wrong payload shape for `backend/app/api/routes/models.py:157`.

Missing behavior:

- Whisper.cpp adapter and catalog entries.
- Managed download checksum verification.
- Download cancellation.
- Custom catalog administration UI.
- Task default UI.
- Hardware compatibility recommendations using GPU/CUDA/VRAM/RAM.
- Worker labels and queue routing based on compatibility.
- Tests proving disabled, failed, deleted, or incompatible models cannot execute jobs.

### 11. Jobs, Events, Worker Health, And Queue Observability Are Incomplete

Evidence:

- `backend/app/api/routes/jobs.py:69` returns an SSE stream.
- `frontend/src/lib/api.ts:168` treats `/transcription-jobs/{id}/events` as a JSON request.
- Frontend has no `/jobs/:jobId` route despite `docs/04-frontend-page-map.md:10`.
- Backlog lists worker health checks, queue depth metrics, and cancellation timeout cleanup as pending in `docs/12-implementation-backlog.md:49`.

Missing behavior:

- Either a JSON event-history endpoint plus separate SSE endpoint, or a frontend EventSource client for the current SSE endpoint.
- Job detail route/page with timeline, output links, errors, and attempts.
- Worker health endpoint.
- Queue depth metrics.
- Cancellation timeout cleanup.
- Redis-backed progress channel for multi-process updates.

### 12. Baseline, CI, Security, And Production Operations Are Incomplete

Evidence:

- `README.md:14` and deployment docs refer to `.env.example`, but the workspace only contains `.env` and `.env.local_backup`.
- `backend/pyproject.toml` has no lockfile; CI installs unpinned backend dependency ranges.
- `.github/workflows/ci.yml` uses `npm install` instead of `npm ci`.
- `backend/app/core/rate_limit.py:6` documents the rate limiter as replaceable by Redis later.
- `backend/app/core/config.py:25` defaults `malware_scanner_mode` to `placeholder`.
- `backend/app/main.py:15` uses basic text logging, not structured JSON logs.
- Backlog lists production observability, backup/restore, scans, load tests, privacy review, and accessibility review as pending in `docs/12-implementation-backlog.md:102`.

Missing behavior:

- `.env.example` with safe non-secret defaults and generated-key instructions.
- Backend deterministic lockfile and CI consumption.
- `npm ci` in CI.
- Pre-commit hooks and contribution guidance.
- Structured JSON logs with request/job correlation propagation and redaction tests.
- Redis-backed rate limiter.
- Production malware scanner adapter integration.
- Metrics, tracing, alert hooks, queue/worker dashboards, and log retention.
- Backup/restore script and tested restore drill.
- Dependency/SBOM/secret scans.
- Load/large-file tests.
- Accessibility review and E2E coverage for keyboard paths.
- Production-like smoke deployment evidence.

## Implementation Task List

### Task 1: Repair Frontend/Backend Contract Drift

**Files:**

- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/pages/ProvidersPage.tsx`
- Modify: `frontend/src/pages/AIRunsPage.tsx`
- Modify: `frontend/src/pages/UsersPage.tsx`
- Modify: `frontend/src/pages/ReportsPage.tsx`
- Modify: `frontend/src/pages/JobsPage.tsx`
- Modify: `backend/app/api/routes/providers.py`
- Modify: `backend/app/api/routes/users.py`
- Test: `frontend/src/lib/api.test.ts`
- Test: create `frontend/src/pages/ProvidersPage.test.tsx`
- Test: create `frontend/src/pages/UsersPage.test.tsx`

- [x] Align `ApiProvider`, `ApiProviderInput`, and provider usage frontend types with backend response fields.
- [x] Change provider create/update payloads to send `adapter_key`, `name`, `base_url`, `endpoint_path`, `model_name`, `auth_type`, `capabilities`, `timeout_seconds`, `retry_limit`, and `api_key`.
- [x] Change secret rotation to send `{ "api_key": value }`.
- [x] Either return aggregate usage from `GET /api-providers/{id}/usage` or render the raw usage rows the backend currently returns.
- [x] Remove unsupported provider kinds from the UI until backend adapters exist.
- [x] Fix `MemberDetail` to match `MembershipSummary`, or enrich backend membership responses with nested `user` data and `created_at`.
- [x] Replace `listJobEvents()` JSON fetch with a JSON history endpoint or EventSource handling.
- [x] Add contract tests for provider creation, rotation, usage, membership rendering, and job events.
- [x] Run `npm.cmd test -- --run` and `npm.cmd run build`.

### Task 2: Implement External API Transcription

**Files:**

- Modify: `backend/app/services/jobs.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/providers/external.py`
- Modify: `backend/app/api/routes/providers.py`
- Modify: `backend/app/schemas/jobs.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/api.ts`
- Test: `backend/tests/test_routes_smoke.py`
- Test: create `backend/tests/test_external_transcription.py`
- Test: create `frontend/src/pages/UploadPage.test.tsx`

- [x] Validate selected API provider existence, enabled state, category, model name, capabilities, and secret configuration in `JobService.create`.
- [x] Enforce organisation and project external API policy in one backend service path.
- [x] Add explicit egress acknowledgement to `TranscriptionJobCreateRequest` for API-provider jobs.
- [x] Route API-provider jobs through `app.providers.external.transcribe`.
- [x] Persist provider usage logs for success and failure.
- [x] Preserve redacted provider error messages on failed jobs.
- [x] Add Upload page provider selector with local/API modes, consent warning, and policy-block states.
- [x] Add fake-provider integration tests that complete a transcript through the external adapter.
- [x] Run `python -m pytest -q` and `npm.cmd test -- --run`.

### Task 3: Replace Stub-Only AI Routing With Targeted Post-Processing

**Files:**

- Modify: `backend/app/providers/contracts.py`
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/worker/post_processing_tasks.py`
- Modify: `backend/app/api/routes/ai.py`
- Modify: `backend/app/schemas/ai.py`
- Modify: `frontend/src/pages/AIRunsPage.tsx`
- Modify: `frontend/src/pages/TranscriptViewerPage.tsx`
- Test: `backend/tests/test_post_processing.py`
- Test: create `backend/tests/test_ai_runs.py`
- Test: create `frontend/src/pages/AIRunsPage.test.tsx`

- [x] Add a real OpenAI-compatible/local-service post-processing provider behind the existing contract.
- [x] Resolve `execution_target_kind` and `execution_target_id` in the AI worker instead of always using `settings.post_processing_provider`.
- [x] Enforce local-only and external-egress policy for AI tasks.
- [x] Add `GET /ai-runs` for list/history.
- [x] Add cancel/retry support for queued or failed runs.
- [x] Persist cleanup/translation outputs as reviewable transcript versions when the task changes transcript text.
- [x] Add progress records or events for AI runs.
- [x] Update AI Runs page to list historical runs from the backend and show target/provider state.
- [x] Run `python -m pytest -q`.
- [x] Run `npm.cmd test -- --run`.

### Task 4: Complete Transcript Editor Data Model And API

**Files:**

- Modify: `backend/app/models/domain.py`
- Add: `backend/alembic/versions/0009_transcript_editor_operations.py`
- Modify: `backend/app/schemas/transcripts.py`
- Modify: `backend/app/api/routes/transcripts.py`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/TranscriptViewerPage.tsx`
- Test: create `backend/tests/test_transcript_editor.py`
- Test: extend `frontend/src/pages/TranscriptViewerPage.test.tsx`

- [x] Add durable transcript edit operation and annotation models.
- [x] Return `speaker_id` and word counts or word rows where needed.
- [x] Add segment speaker assignment endpoint.
- [x] Add speaker creation UI and segment speaker selector.
- [x] Add version precondition to edit, split, merge, annotate, and restore requests.
- [x] Implement autosave batching with conflict responses.
- [x] Implement search/replace.
- [x] Implement undo/redo using operation history.
- [x] Add keyboard shortcuts for play/pause, next/previous segment, split, merge, speaker assignment, annotation, undo, and redo.
- [x] Add editor tests for conflict, undo/redo, speaker assignment, search/replace, and keyboard paths.
- [x] Run Alembic upgrade from a clean database and run backend/frontend tests.

### Task 5: Add Waveform, Derivatives, Signed Downloads, And Retention

**Files:**

- Modify: `backend/app/models/domain.py`
- Add: `backend/alembic/versions/0010_media_derivatives_retention.py`
- Modify: `backend/app/api/routes/assets.py`
- Modify: `backend/app/services/media.py`
- Modify: `backend/app/storage/contracts.py`
- Add: `backend/app/storage/s3.py`
- Add: `backend/app/worker/media_derivative_tasks.py`
- Add: `backend/app/worker/retention_tasks.py`
- Modify: `frontend/src/App.tsx`
- Add: `frontend/src/pages/StoragePage.tsx`
- Modify: `frontend/src/pages/TranscriptViewerPage.tsx`
- Test: create `backend/tests/test_media_derivatives.py`
- Test: create `backend/tests/test_retention.py`

- [x] Add media derivative persistence and endpoint for waveform/audio/thumbnail records.
- [x] Generate waveform and normalized audio derivatives after metadata extraction.
- [x] Replace direct local-file download assumptions with a storage download contract.
- [x] Add short-lived signed URL support for object storage.
- [x] Add S3/MinIO-compatible storage adapter.
- [x] Add hard-delete, retention, legal-hold, and derivative cleanup workers.
- [x] Add Storage page with usage, retention state, purge requests, and provider health.
- [x] Audit media/report view and download actions.
- [x] Run retention tests against local storage and fake object storage.

### Task 6: Implement Diarisation

**Files:**

- Modify: `backend/app/providers/contracts.py`
- Add: `backend/app/providers/diarization.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/schemas/jobs.py`
- Modify: `backend/app/schemas/transcripts.py`
- Modify: `backend/app/api/routes/transcripts.py`
- Modify: `backend/app/services/exports.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/TranscriptViewerPage.tsx`
- Test: create `backend/tests/test_diarization.py`

- [x] Add diarisation provider contract.
- [x] Implement one configured local diarisation provider.
- [x] Add job options for diarisation enablement and provider selection.
- [x] Persist speakers and segment assignments during transcription.
- [x] Preserve speaker assignments across chunking and editing.
- [x] Add diarisation controls to Upload and display labels in the transcript editor.
- [x] Add fixture tests for speaker assignment persistence.
- [x] Run `python -m ruff check .`, `python -m pytest`, `npm.cmd test`, and `npm.cmd run build`.

### Task 7: Complete Reports, Templates, And Export Scope

**Files:**

- Modify: `backend/app/api/routes/reports.py`
- Modify: `backend/app/api/routes/exports.py`
- Modify: `backend/app/schemas/transcripts.py`
- Modify: `backend/app/worker/post_processing_tasks.py`
- Modify: `backend/app/services/exports.py`
- Add: `backend/app/services/reports.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/types.ts`
- Add: `frontend/src/pages/ReportTemplatesPage.tsx`
- Modify: `frontend/src/pages/ReportsPage.tsx`
- Modify: `frontend/src/pages/TranscriptViewerPage.tsx`
- Test: create `backend/tests/test_reports_api.py`
- Test: create `backend/tests/test_report_exports.py`
- Test: create `frontend/src/pages/ReportTemplatesPage.test.tsx`
- Test: modify `frontend/src/lib/api.test.ts`
- Test: modify `frontend/src/pages/TranscriptViewerPage.test.tsx`

- [x] Add report template patch/delete/enable/disable/preview endpoints.
- [x] Add `/report-templates` frontend route.
- [x] Generate reports from template schema instead of fixed minutes sections.
- [x] Add report edit endpoint.
- [x] Add report export support.
- [x] Extend export request contract to support source type and selected segment IDs.
- [x] Add transcript UI for selecting sections before export.
- [x] Audit export downloads.
- [x] Add tests for selected-segment exports and report exports.
- [x] Run `python -m ruff check .`, `python -m pytest`, `npm.cmd test`, and `npm.cmd run build`.

### Task 8: Complete Model Manager And Hardware Routing

**Files:**

- Add: `backend/app/providers/whisper_cpp.py`
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/services/model_catalog.py`
- Modify: `backend/app/worker/model_tasks.py`
- Modify: `backend/app/api/routes/models.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `frontend/src/pages/ModelsPage.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Test: `backend/tests/test_model_manager.py`
- Test: create `backend/tests/test_model_routing.py`

- [x] Add Whisper.cpp adapter and catalog entries.
- [x] Verify model checksums after managed downloads.
- [x] Add model download cancellation.
- [x] Add custom catalog source administration.
- [x] Add task default UI using the backend `installed_model_id` contract.
- [x] Add model test that runs against the selected installed model path.
- [x] Add hardware compatibility recommendations and worker labels.
- [x] Block incompatible model routing in the worker.
- [x] Add routing tests for disabled, failed, deleted, and incompatible models.
- [x] Run `python -m ruff check .`, `python -m pytest`, `npm.cmd test`, and `npm.cmd run build`.

### Task 9: Add Project, Asset, Settings, Organisation, Role, And Help Surfaces

**Files:**

- Modify: `backend/app/api/routes/projects.py`
- Add: `backend/app/api/routes/organisations.py`
- Add: `backend/app/api/routes/roles.py`
- Modify: `backend/app/api/routes/auth.py`
- Modify: `backend/app/api/routes/settings.py`
- Modify: `backend/app/api/router.py`
- Add: `frontend/src/pages/AssetsPage.tsx`
- Add: `frontend/src/pages/ProjectsPage.tsx`
- Add: `frontend/src/pages/OrganisationsPage.tsx`
- Add: `frontend/src/pages/RolesPage.tsx`
- Add: `frontend/src/pages/HelpPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/SettingsPage.tsx`
- Test: create `backend/tests/test_projects_admin.py`
- Test: create `backend/tests/test_roles_admin.py`
- Test: create `frontend/src/pages/SettingsPage.test.tsx`

- [x] Add project detail/update/delete endpoints.
- [x] Add project selector to upload and archive views.
- [x] Add asset library with filters, metadata, download, delete, and project grouping.
- [x] Add organisation management endpoints and UI.
- [x] Add role CRUD and permission assignment UI.
- [x] Add user profile update endpoint.
- [x] Add multi-organisation switcher.
- [x] Replace generic settings text inputs with structured controls for upload, retention, local-only, external API, queue, and AI defaults.
- [x] Remove generic secret storage or encrypt secret settings in a dedicated path.
- [x] Add Help route with operator/user troubleshooting content.
- [x] Run `python -m ruff check .`, `python -m pytest`, `npm.cmd test`, and `npm.cmd run build`.

### Task 10: Add Worker Health, Queue Observability, And Production Hardening

**Files:**

- Add: `.env.example`
- Add: `.pre-commit-config.yaml`
- Add: `CONTRIBUTING.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `backend/pyproject.toml`
- Add: backend dependency lockfile using the chosen lock tool
- Modify: `backend/app/core/rate_limit.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/worker/celery_app.py`
- Add: `backend/app/api/routes/operations.py`
- Add: `scripts/backup.ps1`
- Add: `scripts/restore.ps1`
- Test: create `backend/tests/test_operations.py`
- Test: create `backend/tests/test_logging_redaction.py`

- [x] Add `.env.example` with safe defaults and generated-key instructions.
- [x] Add backend lockfile and make Docker/CI consume it.
- [x] Change frontend CI to `npm ci`.
- [x] Add pre-commit hooks for Python and frontend formatting/linting.
- [x] Add structured JSON logging with request ID and job ID propagation.
- [x] Add redaction tests for secrets, provider errors, and audit metadata.
- [x] Replace in-process rate limiting with Redis-backed storage.
- [x] Add production malware scanner adapter configuration and tests.
- [x] Add worker health and queue depth endpoints.
- [x] Add metrics/tracing hooks and alert-ready counters.
- [x] Add backup/restore scripts and CI restore smoke test.
- [x] Add dependency, SBOM, and secret scanning jobs.
- [x] Add load/large-file and accessibility smoke checks.
- [x] Run `python -m ruff check .`, `python -m pytest`, `npm ci`, `npm test`, `npm run lint`, `npm run build`, `npm audit --audit-level=high`, and local smoke-script checks.

## Recommended Delivery Order

1. Task 1: repair broken runtime contracts.
2. Task 2: external transcription end-to-end.
3. Task 3: targeted AI post-processing.
4. Task 4: transcript editor data integrity and workflow completeness.
5. Task 5 and Task 6: media derivatives, retention, and diarisation.
6. Task 7: reports/templates/export scope.
7. Task 8 and Task 9: model/admin surfaces.
8. Task 10: production hardening and operational evidence.

## Exit Criteria

- Backend and frontend contract tests cover provider, users/memberships, reports, jobs/events, AI runs, and exports.
- A user can configure an external transcription provider, acknowledge egress, transcribe media through it, and see redacted usage telemetry.
- A user can edit, search/replace, split/merge, annotate, assign speakers, use keyboard shortcuts, resolve edit conflicts, and export selected transcript sections.
- Retention cleanup removes originals, derivatives, exports, and derived records according to policy while preserving required audit records.
- CI uses deterministic dependency inputs and runs lint, unit, frontend build, integration, migration, smoke, scan, and accessibility checks.
