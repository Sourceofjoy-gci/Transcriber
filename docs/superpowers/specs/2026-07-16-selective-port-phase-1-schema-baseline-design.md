# Selective Port Phase 1: Canonical Schema and Backend Baseline Design

**Date:** 2026-07-16

**Status:** Approved

**Repository baseline:** `b30bb49` (`main`, five commits ahead of `origin/main`)

## Goal

Establish a trustworthy PostgreSQL and backend foundation for the selective-port program before changing transcription behavior, model lifecycle, deployment topology, or frontend workflows.

Phase 1 makes every Alembic revision deterministic, repairs known schema drift through a forward reconciliation revision, proves supported database upgrade paths against PostgreSQL, and restores a green backend quality baseline. It does not port Voicebox code or add later-phase product features.

## Governing Product Decision

Transcriber remains the source of truth for the product model, identifiers, API, schema lineage, authentication, organisation scoping, RBAC, storage abstraction, durable jobs, transcripts, versions, exports, reports, audit, and retention.

Voicebox is a design and implementation reference only. Later phases may selectively reimplement or port its model-readiness, download-progress, lazy model lifecycle, waveform interaction, and capture-state ideas behind Transcriber's existing boundaries.

The unified transcription release explicitly excludes Voicebox's:

- text-to-speech workflows;
- voice cloning and voice profiles;
- Tauri desktop shell;
- story generation; and
- local-path, SQLite, in-memory queue, and synchronous request-bound transcription architecture.

Any later source-level port from Voicebox must preserve the applicable MIT notice. Transcriber still has no repository license; choosing one remains an owner decision and is not part of Phase 1.

## Precedence and Superseded Plans

This design supersedes the implementation direction in:

- `docs/superpowers/specs/2026-07-10-production-readiness-design.md`;
- `docs/superpowers/plans/2026-07-10-production-readiness.md`;
- `docs/superpowers/specs/2026-07-13-universal-model-downloads-design.md`; and
- `docs/superpowers/plans/2026-07-13-universal-model-downloads.md`.

Those documents remain in Git as historical records. Their requirements to install Qwen/NeMo/Torch-heavy runtimes, download every GPU-oriented catalog entry on the CPU worker, and prove the entire application in one gate are not governing requirements for the selective-port release.

The selective-port program is intentionally decomposed into independent phases:

1. canonical schema, migration repair, and green backend baseline;
2. strict CPU dependency lock, Compose startup, S3 dependency repair, health checks, and resource limits;
3. durable chunks, resumability, admission control, model caching, cancellation, and timeouts;
4. provider conformance, Whisper.cpp timestamps, and optional real diarization;
5. task-oriented navigation, upload preflight, job monitoring, waveform editing, model-resource UX, and accessibility;
6. security hardening, operations, backup/restore, compatibility, and dry-run Voicebox capture import; and
7. CPU smoke tests and short, medium, long, and concurrent benchmarks followed by tuned defaults.

Each phase receives its own reviewed specification and implementation plan. This document governs Phase 1 only.

## Repository Evidence

The design is based on the following verified state at `b30bb49`:

- The worktree is clean and `main` is five local commits ahead of `origin/main`.
- PostgreSQL, Redis, the API, the CPU worker, and Caddy are running, but Phase 1 diagnostics did not modify their data or volumes.
- The live database reports Alembic revision `0011_media_derivatives_retention` and 33 application tables.
- `alembic check` against the live database detects schema drift: `media_assets.status` is `VARCHAR(10)`, while current metadata requires values up to `processing_metadata` and therefore a wider type.
- The only migration-specific automated test checks that revision IDs fit Alembic's default version column.
- Revisions `0001`, `0002`, `0003`, `0004`, `0005`, `0006`, `0007`, `0010`, and `0011` call `Base.metadata.create_all` or `Base.metadata.drop_all`.
- An isolated, temporary PostgreSQL 16 upgrade from an empty database fails in `0002_transcripts_and_exports`. Current metadata makes `export_records.report_id` reference `reports`, but `reports` is not created until revision `0007`.
- Host Python is 3.14 without project test dependencies; the application requires Python 3.12. Phase 1 verification must therefore run in a controlled Python 3.12 environment rather than installing into the host interpreter.
- `docker compose config --quiet` succeeds at the baseline. Full CPU image and service validation belongs to Phase 2.

These findings invalidate prior claims that an empty PostgreSQL migration is proven. SQLite success is not an acceptable substitute because the production database is PostgreSQL and the current failure is a foreign-key dependency-order problem.

## Considered Phase 1 Approaches

### 1. Freeze historical DDL and add a reconciliation fence — selected

Replace ORM-metadata calls in every affected historical revision with explicit Alembic operations. Preserve revision IDs and ordering. Add one forward reconciliation revision after `0011` that repairs known deployed-schema drift and is a no-op on a canonical fresh installation.

This fixes empty installations, preserves the upgrade lineage for deployed databases, prevents future ORM edits from mutating history, and keeps a single schema chain.

### 2. Add a new squashed baseline for fresh installations

Keep the existing chain for deployments and route fresh installations through a new baseline or stamp procedure. This leaves two installation paths, complicates automation and operator guidance, and makes future upgrades prove two histories. It is not justified before a stable release boundary exists.

### 3. Add only a forward repair revision

Leave historical revisions mutable and attempt to reconcile at the new head. An empty PostgreSQL database cannot reach the repair revision because it fails at `0002`, so this does not solve the primary defect. Rejected.

## Architecture

### Canonical schema contract

The canonical schema is the explicit Alembic schema at the new head. SQLAlchemy models must agree with that schema, but ORM metadata must never be used to execute historical DDL.

The fixed chain preserves all existing revision identifiers so deployed databases are not restamped and applied migrations are not rerun. Historical revisions define the schema that existed at that point in the chain; later revisions perform later additions and type changes in dependency-safe order.

The expected revision responsibilities are:

- `0001`: organisation, identity, RBAC, project, media, job, refresh-token, settings, and audit foundation;
- `0002`: transcript, version, speaker, segment, word, and initial export records without a premature dependency on reports;
- `0003`: model catalog, installed model, and task-default records;
- `0004`: initial provider definitions and secrets;
- `0005`: provider lifecycle additions and usage logs;
- `0006`: initial AI-processing run records;
- `0007`: report templates and reports, followed by report-aware export linkage;
- `0008`: deterministic integer-to-bigint changes for media and model artifact sizes;
- `0009`: AI run progress and cancellation fields;
- `0010`: transcript edit-operation and annotation records; and
- `0011`: media legal-hold and derivative records.

Every upgrade and downgrade uses explicit `op.create_table`, `op.drop_table`, `op.add_column`, `op.drop_column`, `op.create_index`, `op.drop_index`, `op.create_foreign_key`, `op.drop_constraint`, or batch operations. Migration modules may import SQLAlchemy and Alembic only; they may not import `Base`, current domain models, application services, settings, or provider code.

### Forward reconciliation revision

Add revision `0012_schema_reconciliation` after `0011`. It inspects only schema metadata, never application rows or secrets, and applies explicit, bounded repairs for known deployed variants. Its responsibilities are:

- widen undersized string columns required by the current enumerated values, including `media_assets.status`;
- add any columns, indexes, unique constraints, or foreign keys missing from an already-stamped head database;
- retain every existing identifier and application row;
- backfill only deterministic values where a new non-null constraint requires them;
- refuse an unsafe narrowing, destructive cast, ambiguous duplicate cleanup, or non-deterministic backfill with an actionable migration error; and
- perform no DDL when the database is already canonical.

The reconciliation revision's downgrade is intentionally a schema no-op. The revision repairs a database to the canonical schema expected at its `0011` down-revision; reverting those repairs would recreate invalid drift rather than restore a supported historical state. Downgrades through earlier revisions remain explicit and testable.

### Schema fixture boundary

Upgrade tests use schema-only fixtures and disposable PostgreSQL databases. Fixtures contain no application rows, media paths, credentials, hashes, tokens, or secrets.

The supported fixtures are:

1. an empty PostgreSQL 16 database;
2. a canonical database produced by the repaired chain;
3. a schema-only representation of the current `0011` deployment, including the observed narrow status column; and
4. representative legacy schemas at earlier revision boundaries where metadata-driven creation caused known shape differences.

Tests stamp only disposable fixture databases. The running development database is read-only evidence and is never used as a migration target.

### Backend baseline boundary

Phase 1 uses Python 3.12 with the backend's development dependencies. The green baseline consists of:

- migration static checks;
- PostgreSQL migration integration tests;
- the complete backend pytest suite;
- Ruff linting; and
- an API import/startup smoke test with external egress disabled.

Phase 1 may make the smallest backend corrections required for those checks when they expose a foundation defect. Every behavior-changing correction requires a failing regression test first. Dependency pruning, lock regeneration, worker image rebuilding, service health checks, S3 packaging, and container resource controls remain Phase 2.

## Migration Data Flow

### Empty installation

1. Create an empty disposable PostgreSQL database.
2. Run Alembic from base through the explicit historical revisions.
3. Run `0012_schema_reconciliation`; it should make no corrective changes.
4. Verify the head revision and compare the database schema with the canonical contract.
5. Run `alembic check` and require no generated upgrade operations.

### Existing head installation

1. Take a schema-only fixture from a known `0011` shape.
2. Load it into a disposable PostgreSQL database and verify its revision stamp.
3. Run only the forward upgrade to `0012_schema_reconciliation`.
4. Verify row-preserving DDL behavior with sentinel identifiers in fixture-owned tables where needed.
5. Compare the resulting schema with the same canonical contract used for empty installation.

### Legacy installation

1. Load a representative schema-only legacy fixture and its matching Alembic revision.
2. Upgrade through the remaining explicit history and reconciliation fence.
3. Verify canonical schema equivalence and preserved sentinel identifiers.

No path calls `Base.metadata.create_all` to prepare or validate a migration database.

## Error Handling and Safety

- Run all PostgreSQL DDL transactionally where PostgreSQL permits it.
- Abort on a missing prerequisite table, incompatible existing type, duplicate data that prevents a unique constraint, or unknown schema variant.
- Include the table, column or constraint name and required operator action in migration errors; never include row contents or secrets.
- Do not automatically delete rows, rename identifiers, collapse duplicates, or coerce invalid status values.
- Do not stamp a failed database as current.
- Do not use the running Transcriber database for destructive tests.
- Preserve a pre-migration backup requirement in later operator documentation; backup and restore implementation remains Phase 6.
- Keep external egress disabled throughout Phase 1 verification.

## Testing Strategy

All behavior changes follow red-green-refactor: add the smallest failing test, verify the expected failure, implement the minimal correction, run the focused test, and then run the affected suite.

### Static migration tests

- Every revision ID is unique, ordered, and at most 32 characters.
- The chain has one head and no missing down-revision.
- No migration revision contains `Base.metadata.create_all`, `Base.metadata.drop_all`, imports from `app.models`, or imports from application services.
- Every created named index and constraint has a matching explicit downgrade operation where the revision owns that object.

### PostgreSQL integration tests

- Empty database upgrade reaches `0012_schema_reconciliation`.
- Fresh upgrade schema matches the canonical table, column, type, nullability, primary-key, foreign-key, unique-constraint, and index manifest.
- Current-head fixture upgrade reaches the same schema without changing sentinel identifiers.
- Each representative legacy fixture reaches the same schema.
- Reapplying the reconciliation helper logic to a canonical schema produces no operations.
- Upgrade to head, downgrade to base, and upgrade to head succeeds on a disposable database.
- `alembic check` reports no new upgrade operations at head.

### Backend baseline tests

- Complete backend pytest suite passes under Python 3.12.
- Ruff reports no errors.
- `app.main` imports and the liveness endpoint responds without loading a transcription model or making network requests.
- Existing authentication, RBAC, storage-key, provider-secret, job, transcript, export, and report tests remain green.

SQLite-only migration tests do not satisfy any Phase 1 acceptance criterion.

## Documentation Changes

Phase 1 updates the planning index, implementation status, and migration/deployment guidance to state:

- PostgreSQL is the only authoritative migration target;
- application startup is not the preferred production migration runner;
- the four July 10/13 documents are superseded historical plans;
- no Voicebox product database is merged into Transcriber; and
- no excluded Voicebox feature is part of the unified transcription release.

Documentation must distinguish verified commands from planned commands and remove unsupported claims that empty PostgreSQL migration already passes.

## Completion Criteria

Phase 1 is complete only when all of the following are true:

- every metadata-driven historical DDL operation has been replaced with explicit Alembic operations;
- revision IDs and deployed application identifiers are preserved;
- `0012_schema_reconciliation` safely repairs each supported deployed fixture and is a no-op on a canonical fresh schema;
- an empty PostgreSQL 16 database upgrades to head;
- current and representative legacy schema fixtures upgrade to the identical canonical head schema;
- upgrade/downgrade/upgrade succeeds in a disposable PostgreSQL database;
- `alembic check` detects no pending schema operations at head;
- the complete backend test suite and Ruff pass in Python 3.12;
- the API import/liveness smoke test passes with external egress disabled;
- no running development database or persistent volume was modified by tests;
- status and migration documentation reflects actual evidence; and
- `git diff --check` passes with no unrelated changes.

## Explicit Non-Goals

Phase 1 does not:

- add durable chunk or checkpoint tables;
- add model runtime/cache fields;
- change Celery routing, concurrency, admission, cancellation, or timeout behavior;
- change transcription or diarization providers;
- prune or regenerate dependency locks;
- rebuild the CPU deployment;
- change primary or administration navigation;
- add upload preflight or waveform editing;
- import Voicebox SQLite data;
- rotate live secrets or back up live data; or
- implement TTS, voice cloning, Tauri, or story generation.
