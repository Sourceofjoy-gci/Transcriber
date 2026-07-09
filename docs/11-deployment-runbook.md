# Deployment Runbook

## Preflight

1. Install Docker Engine/Compose, FFmpeg is included in the backend image, and optionally install NVIDIA Container Toolkit.
2. Generate `CREDENTIAL_ENCRYPTION_KEY` with `python scripts/generate-encryption-key.py`.
3. Copy `.env.example` to `.env`; replace every placeholder and set production origins, database credentials, bootstrap administrator credentials, and a generated encryption key.
4. Configure a persistent PostgreSQL backup location and a private storage/model volume before first startup.

## Start and validate

```text
docker compose --profile cpu up --build -d
docker compose exec api alembic upgrade head
curl http://localhost:8080/health/live
curl http://localhost:8080/health/ready
```

Use `--profile gpu` only after validating CUDA compatibility with the chosen model runtime. Do not expose PostgreSQL or Redis ports publicly.

## Backup and restore

- Back up PostgreSQL with `pg_dump` and test restore into an isolated environment.
- Back up original media, exports, and model manifests; storage alone is not a complete recovery without PostgreSQL.
- Retain encryption key versions securely. Losing a key version makes provider credentials encrypted under it unrecoverable.

## Security operations

- Rotate bootstrap credentials after first login and remove bootstrap variables from deployment configuration.
- Rotate provider secrets through the admin workflow once completed; avoid editing encrypted database rows manually.
- Monitor failed logins, external provider failures, worker OOMs, export activity, and storage growth.
- Keep external APIs disabled unless the organisation approves data egress.

## Release gate

Do not classify the current repository as production-ready until all incomplete Phase 4–7 items in `docs/10-implementation-audit.md` are implemented and CI has passed its backend, frontend, integration, and deployment smoke suites.
