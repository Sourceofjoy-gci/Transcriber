# Production Readiness Completion Design

> **Historical plan:** Superseded by the approved selective-port program and its Phase 1 schema-baseline design dated 2026-07-16. Retained for audit history; do not execute as the governing implementation plan.

**Date:** 2026-07-10
**Status:** Approved; implementation plan complete
**Repository baseline:** `6f281a33e444778a68d71700d00431bce56a4030`

## Goal

Turn the current Transcriber repository into a fully verified, reproducible production candidate. Completion requires one PowerShell entry point to prove every documented application feature, every catalog-model download, dependency health, clean PostgreSQL migration, Docker health, backup/restore, recovery behavior, and production configuration. A deterministic AI stub is not acceptable in production; local AI and translation must use a real open-source model.

Production readiness is a claim about fresh evidence, not source-code presence. A feature is complete only when the acceptance manifest names it, an automated or explicitly hardware-limited check exercises it, and the final evidence bundle records the result.

## Governing constraints

- Readiness covers the complete documented backend, frontend, worker, administration, transcription, model-management, storage, export, reporting, security, backup, and restore surface.
- Existing dated status reports are historical evidence, not waivers. Features described as deferred or incomplete are included when the governing goal or architecture documents require them.
- Make the smallest complete fixes and avoid unrelated refactors.
- Write a failing regression or acceptance test before every behavior-changing fix.
- Use locked backend and frontend installs.
- Every required command must exit zero; high- or critical-severity dependency vulnerabilities fail the gate.
- Run the stack with clean PostgreSQL, Redis, storage, and model volumes under an isolated Docker Compose project name.
- Download every entry enumerated dynamically from `CATALOG_ENTRIES`. Never maintain a second hard-coded catalog list in the gate.
- A hardware-only inference limitation is allowed only after download and artifact verification succeed and the hardware probe proves the missing capability. It is reported separately from passed inference.
- Stop after three complete test-and-fix iterations, or immediately on the user-defined secret, permission, network, storage, hardware, licensing, destructive-change, duplicate-PR, or scope blockers.
- Do not open a pull request without a separate user instruction. Obtain independent read-only review before any later PR action.

## Current-state findings that shape the design

- The source already includes broad API/UI coverage, local and S3 storage, backup/restore scripts, retention tasks, Whisper.cpp and diarisation provider modules, external transcription, multiple Hugging Face speech adapters, and an expanded test suite.
- Historical readiness documents understate the current source and contain claims that must be re-proved.
- `scripts/production-readiness.ps1` is absent.
- Local AI uses `StubPostProcessingProvider` by default even though an OpenAI-compatible external adapter exists.
- The host is CPU-only with approximately 30 GiB RAM. GPU-required model inference must therefore be classified from the application hardware probe, while downloads remain mandatory.
- The root filesystem has been expanded to approximately 148 GiB, leaving approximately 119 GiB available for the clean model cache, images, dependencies, and evidence.

## Chosen architecture

### Local AI runtime

Use a dedicated single-concurrency Celery worker running `llama-cpp-python` and the official Apache-2.0 Qwen3 4B GGUF model, `Qwen3-4B-Q4_K_M.gguf`.

This option was selected over an Ollama/llama.cpp HTTP sidecar and an embedded Transformers runtime because it:

- keeps model download, verification, enablement, deletion, and defaults inside the existing application Model Manager;
- avoids a second model registry or duplicate cache;
- isolates LLM memory and failures from transcription workers through a separate `postprocess` queue;
- uses a quantized CPU-capable model rather than the heavier PyTorch/Transformers runtime; and
- supports JSON-schema-constrained chat completion through `llama-cpp-python`.

The catalog entry contains a pinned upstream revision, exact artifact size, direct source metadata, Apache-2.0 license metadata, CPU/RAM requirements, post-processing capabilities, and a SHA-256 checksum obtained from the downloaded artifact. It is downloaded through the same authenticated Model Manager workflow as all other catalog entries.

Production configuration sets `POST_PROCESSING_PROVIDER=llama_cpp_local`. Startup validation rejects `stub` in production. The deterministic fake remains available only through test fixtures; it is not registered as a production provider.

### AI provider behavior

`LlamaCppPostProcessingProvider` has one responsibility: load the verified enabled Qwen model, format a task-specific prompt, request schema-constrained JSON, validate the response, and return normalized `PostProcessResult` data.

It supports the existing tasks:

- `clean`
- `translate`
- `summary`
- `minutes`
- `action_items`
- `topics`
- `entities`
- `qa`

Each task owns a concrete JSON schema and normalization function. `clean` and `translate` may create reviewable transcript versions. Analytical tasks store structured results without overwriting human transcript text. Report generation uses the same real provider rather than calling heuristic handlers.

The worker lazily loads one model instance per process. Queue concurrency is one, requests have bounded context/output sizes, and transcript input is chunked or rejected with a safe capacity error rather than silently truncated. Metrics include model identifier, prompt/output token counts, wall time, and inference timing without transcript content.

### Runtime topology

Docker Compose adds a CPU-profile `worker-ai` service that consumes the `postprocess` queue with concurrency one and mounts the model cache read-only. Existing CPU workers continue media, transcription, maintenance, and export work. GPU workers remain responsible only for GPU speech queues.

Celery routes AI runs and AI-backed report generation to `postprocess`. Non-AI rendering stays on `exports`. API and worker readiness expose sanitized checks for queue registration, model installation/verification, runtime import, storage, PostgreSQL, Redis, FFmpeg, and worker heartbeat.

## Acceptance manifest and evidence model

### Authoritative manifest

Create `scripts/production-readiness.matrix.json` as the authoritative, machine-readable acceptance manifest. Create `docs/16-production-readiness-acceptance-matrix.md` as its human-readable generated view.

Every row contains:

- stable acceptance ID;
- subsystem and feature name;
- source document/section or governing user requirement;
- preconditions and fixture data;
- automated test or end-to-end scenario;
- expected result;
- evidence artifact path;
- hardware policy, if applicable; and
- blocking/non-blocking classification.

The manifest covers, at minimum:

1. installation, configuration validation, dependency locks, migrations, liveness, readiness, structured logging, metrics/tracing hooks, queue/worker diagnostics, and observability;
2. login, refresh rotation, logout, current-user/profile updates, CSRF, rate limits, MFA/SSO extension points, six seeded roles, custom roles, granular permissions, tenant/project isolation, and RBAC denials;
3. organisations, users, memberships, projects, settings, providers, storage, retention, audit logs, model defaults, and administration UI;
4. upload validation, quarantine/malware decisions, local/S3 storage, object-storage lifecycle/signed URLs, metadata, derivatives, downloads, deletion, retention, and legal-hold extension behavior;
5. media processing, audio/video transcription, chunking, timestamps, words, cancellation, retry, attempts, persisted events/SSE progress, recovery, and failure classification;
6. diarisation, persisted speakers, speaker edits, and speaker-aware transcript/export output;
7. transcript search, playback sync, edit/split/merge, annotations, undo/redo behavior, version conflict/restore, and immutable lineage;
8. local Qwen cleanup, translation, summary, minutes, action items, topics, entities, Q&A, multimodal slide/image/document validation and source attribution, cancellation, retry, and lineage;
9. all report templates, custom templates, report generation/edit/delete/export, and source-version traceability;
10. TXT, JSON, SRT, VTT, CSV, Markdown, HTML, DOCX, and PDF generation, selected-section export, expiry, authorization, and downloads;
11. catalog seeding, install/download progress, checksums, artifact inspection, enable/disable, test, defaults, compatibility routing, deletion, and clean-cache behavior;
12. encrypted provider secrets, rotation, redaction, SSRF controls, generic REST mappings, OpenAI-compatible execution, explicit external egress consent, local-only blocks, provider usage/cost/error logs, and fake external endpoint execution;
13. every documented frontend route including help/operator guidance, browser accessibility, keyboard paths, responsive critical flows, security headers, TLS/Caddy behavior, CSP/CORS, safe errors, path confinement, secret scanning, SBOM, and vulnerability scans;
14. PostgreSQL backup, storage manifest backup, isolated restore, row/artifact reconciliation, encryption-key continuity, and restored application health;
15. CPU, GPU, object-storage, and development profile rules; worker loss; Redis/PostgreSQL/storage/provider/model failures; restart recovery; idempotency; and terminal state correctness; and
16. upgrade, rollback, credential rotation, incident response, privacy assessment, backup restoration, GPU troubleshooting, model installation, provider administration, retention, editor/export, and user/operator runbooks.

The gate fails if a documented requirement has no manifest row, a required row lacks evidence, or a row remains failed/unverified.

### Evidence bundle

Each run writes an ignored directory under `artifacts/production-readiness/<UTC-run-id>/` containing:

- `summary.json` and `summary.md`;
- acceptance results keyed by stable ID;
- command, start/end time, exit code, and captured log for every gate step;
- sanitized Compose configuration and container/image identifiers;
- migration history and clean-database results;
- liveness/readiness response bodies and container health states;
- browser test traces/screenshots for failures and concise successful-flow logs;
- backup/restore reconciliation data;
- dependency, vulnerability, SBOM, and secret-scan reports; and
- model-by-model download, source, revision, size, checksum, artifact, load, inference, duration, and hardware-limitation results.

Secrets, tokens, provider credentials, transcript text, filenames, and raw sensitive media never enter evidence logs.

## Single reproducible gate

`scripts/production-readiness.ps1` is cross-platform PowerShell and the sole supported entry point. It uses strict error handling, verifies prerequisite versions, and records every subprocess exit code. On this Linux host, a `powershell` launcher aliases the installed PowerShell 7 executable so the exact required command is exercised:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\production-readiness.ps1
```

The gate performs these phases in order:

1. preflight capacity, CPU/GPU/RAM, network, licensing metadata, Docker, Compose, PowerShell, Git state, and secret generation;
2. manifest schema/coverage validation and large-file/secret checks;
3. locked backend install followed by `python -m pip check`, `python -m ruff check .`, vulnerability audit, and `python -m pytest -q`;
4. `npm ci`, `npm test`, `npm run lint`, `npm run build`, and `npm audit --audit-level=high`;
5. Compose config validation, pinned-image build, SBOM/image scan, and non-root/configuration checks;
6. clean PostgreSQL startup and Alembic upgrade to head, followed by schema/history verification;
7. complete stack startup, worker registration, container health, `/health/live`, and `/health/ready` checks;
8. API integration and Playwright browser acceptance flows;
9. backup/restore and failure-recovery drills in isolated resources;
10. clean model-cache catalog download, verification, loading, and hardware-supported minimal inference;
11. final acceptance coverage audit and evidence summary generation.

The script uses a unique Compose project name and fresh named volumes. It never reuses the developer cache to claim a clean download. It preserves failed-run evidence while safely removing ephemeral credentials and test containers. Successful cleanup is itself recorded.

## Model-catalog verification

The model phase imports `CATALOG_ENTRIES` inside the application image at runtime and compares the API catalog to that exact set. For every entry it:

1. creates or selects an installed-model record through the authenticated API;
2. queues the application's real download task;
3. polls persisted progress and job state;
4. verifies the expected application-managed artifact path exists;
5. reconciles actual size with catalog/source metadata;
6. computes and compares SHA-256 when a checksum is supplied;
7. exercises enable, test, default-routing, disable, and delete safeguards without discarding the verified artifact before inference; and
8. attempts model load and minimal fixture inference whenever the application hardware probe says the runtime is supported.

Downloads are never treated as passed based on pre-existing files or metadata rows. GPU-required models are still downloaded and verified on the CPU-only host. Their inference result is `hardware_limited` only when the entry declares the requirement, the hardware probe confirms the capability is absent, and no supported CPU path exists. Other load failures fail the gate.

The new Qwen post-processing entry follows the same workflow and must complete real summary and translation inference.

## End-to-end application flow

The primary browser/API scenario creates two organisations and representative users for all seeded roles. It proves successful and forbidden actions across tenant/project boundaries, then performs:

1. production-safe bootstrap and credential rotation;
2. project creation and policy configuration;
3. fixture audio and video uploads with validation and progress;
4. FFprobe/FFmpeg processing and derivative inspection;
5. local model selection and background transcription;
6. cancellation, worker restart, retry, and completed transcript persistence;
7. diarisation and speaker persistence;
8. transcript playback, search, edit, split, merge, annotation, conflict, restore, and speaker assignment;
9. real local Qwen cleanup, translation, analysis tasks, and traceable derived versions;
10. report generation from all built-in template kinds plus one custom template;
11. every export format, selected segments, expiry enforcement, and authorized download;
12. organisation/user/role/provider/setting/storage/retention/audit/model administration;
13. external provider execution against a local fake endpoint with consent, usage logging, secret redaction, and local-only denial; and
14. backup, destructive mutation only inside the isolated readiness database, restore, reconciliation, and health checks.

Fixture media is small, redistributable, generated or repository-owned, and contains deterministic speech suitable for transcription/diarisation assertions.

## Error handling and data safety

- Production startup rejects placeholder secrets, wildcard/missing origins, development malware mode, and stub AI configuration.
- AI model absence, disabled state, checksum mismatch, runtime import failure, incompatible hardware, context overflow, invalid JSON, and timeout have stable redacted error codes.
- Invalid model JSON receives one bounded corrective retry. A second invalid response fails the run without creating or activating a transcript version.
- AI cancellation is cooperative between prompt preparation and inference boundaries; cancelled/failed outputs are not published.
- Download tasks use attempt-specific temporary paths and atomic promotion after verification. Partial files cannot be enabled or routed.
- Worker retries remain idempotent through database state and artifact checks.
- Backup/restore operates only on isolated readiness resources and never targets an existing user database.
- Any unclear destructive operation, missing permission, licensing restriction, unavailable required secret, insufficient capacity, or persistent network failure stops the run with a precise blocker.

## Testing strategy

### Test-driven changes

Every behavior fix follows red-green-refactor:

1. add the smallest regression/acceptance test;
2. run it and confirm the expected failure;
3. implement the minimal complete change;
4. run the focused test and affected suite;
5. refactor only while green.

Configuration-only changes receive static validation or integration tests where executable behavior exists.

### Automated layers

- Unit: task schemas, prompt construction, response normalization, checksum/path rules, hardware classification, RBAC decisions, rendering, and redaction.
- Integration: PostgreSQL migrations, Redis rate limits, Celery tasks, storage providers, fake external service, model downloads, backup/restore, and worker recovery.
- Browser: complete user and administrator flows through the built frontend and Caddy endpoint using Playwright.
- Real-model smoke: Qwen and every speech model supported by detected hardware, using minimal deterministic fixtures.
- Non-functional: dependency/image/secret scans, accessibility, security headers, large/invalid upload handling, retention, and recovery.

Mocked unit tests do not substitute for the required real integration, browser, model-download, or inference acceptance evidence.

## Iteration and review policy

One complete iteration means running the full PowerShell gate from clean resources, recording every failure, applying TDD fixes, and rerunning the gate. Work stops after the third complete gate run even if failures remain; the report then identifies each blocker without claiming readiness. Focused red-green runs inside an iteration do not increment this counter.

After a zero-exit gate, an independent reviewer receives the governing goal, acceptance manifest, production configuration, Git diff, and evidence bundle. The review is read-only and must check every acceptance ID, secrets/configuration, container hardening, migrations, backup/restore, model results, and unresolved risks. Critical and important findings are fixed and the affected/full gate rerun before sign-off.

No pull request is created by this work unless the user separately authorizes publication after reviewer sign-off.

## Completion criteria

The work is complete only when all of the following are simultaneously true:

- the exact required PowerShell command exits zero;
- its summary reports every blocking acceptance row passed;
- all required commands exit zero with recorded logs and totals;
- no high/critical dependency or image vulnerability remains;
- clean PostgreSQL migrations and all container/readiness checks pass;
- every application feature flow passes end to end;
- backup/restore and recovery drills pass;
- every dynamic catalog entry downloads and verifies from a clean cache;
- all hardware-supported models complete load and minimal inference;
- hardware-only limitations are explicit, evidence-backed, and not mislabeled as inference success;
- real local Qwen AI/translation/report processing passes;
- no unresolved critical/important reviewer finding remains; and
- the independent reviewer signs off on acceptance coverage and production configuration.

If any item lacks authoritative evidence, production readiness remains unproven.

## Primary upstream references

- Qwen3 4B GGUF model and Apache-2.0 license: <https://huggingface.co/Qwen/Qwen3-4B-GGUF>
- Qwen3 model family: <https://huggingface.co/Qwen/Qwen3-4B>
- llama-cpp-python JSON/JSON-schema completion: <https://github.com/abetlen/llama-cpp-python/blob/main/README.md>
- llama.cpp CPU/GPU and OpenAI-compatible runtime: <https://github.com/ggml-org/llama.cpp>
