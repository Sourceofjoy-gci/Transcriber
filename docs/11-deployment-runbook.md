# Deployment Runbook

## Migration authority

PostgreSQL 16 is the only authoritative migration target. Before every schema upgrade, take and verify a PostgreSQL backup. Run Alembic as a controlled one-shot deployment step before rolling out the API and workers; API startup is not the preferred production migration runner.

The current canonical head is `0012_schema_reconciliation`. It retains Transcriber identifiers and rows while reconciling supported deployed variants. Never merge a Voicebox SQLite database into the Transcriber schema. Voicebox capture import is a later, dry-run-first compatibility workflow; text-to-speech, voice cloning and voice profiles, Tauri, and story generation are excluded from the unified transcription release.

## Preflight

1. Install Docker Engine/Compose, FFmpeg is included in the backend image, and optionally install NVIDIA Container Toolkit.
2. Generate `CREDENTIAL_ENCRYPTION_KEY` with `python scripts/generate-encryption-key.py`.
3. Copy `.env.example` to `.env`; replace every placeholder and set production origins, database credentials, bootstrap administrator credentials, and a generated encryption key.
4. Configure a persistent PostgreSQL backup location and a private storage/model volume before first startup.

## Build, migrate, start, and validate

```text
docker compose --profile cpu build
docker compose up -d postgres redis
docker compose run --rm --no-deps api alembic upgrade 0012_schema_reconciliation
docker compose --profile cpu up -d
curl http://localhost:8088/health/live
curl http://localhost:8088/health/ready
```

Do not start a new API revision until the one-shot migration exits successfully. Use `--profile gpu` only after validating CUDA compatibility with the chosen model runtime. Do not expose PostgreSQL or Redis ports publicly.

## Backup and restore

- Back up PostgreSQL with `pg_dump` before every Alembic upgrade and test restore into an isolated environment.
- Back up original media, exports, and model manifests; storage alone is not a complete recovery without PostgreSQL.
- Retain encryption key versions securely. Losing a key version makes provider credentials encrypted under it unrecoverable.

## Security operations

- Rotate bootstrap credentials after first login and remove bootstrap variables from deployment configuration.
- Rotate provider secrets through the admin workflow once completed; avoid editing encrypted database rows manually.
- Monitor failed logins, external provider failures, worker OOMs, export activity, and storage growth.
- Keep external APIs disabled unless the organisation approves data egress.

## Release gate

Do not classify the current repository as production-ready until all incomplete Phase 4–7 items in `docs/10-implementation-audit.md` are implemented and CI has passed its backend, frontend, integration, and deployment smoke suites.
