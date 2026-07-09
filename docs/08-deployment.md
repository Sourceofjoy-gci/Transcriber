# Deployment Plan

## Runtime topology

Docker Compose supplies the initial deployment topology:

| Service      | Responsibilities                                                              | Persistent data                          |
| ------------ | ----------------------------------------------------------------------------- | ---------------------------------------- |
| `proxy`      | Caddy TLS, request-size limits, security headers, static frontend/API routing | Certificates/configuration               |
| `frontend`   | Built React static assets                                                     | None                                     |
| `api`        | FastAPI HTTP/SSE, authorization, database coordination                        | None                                     |
| `worker-cpu` | Metadata, exports, CPU transcription, post-processing                         | Optional cache only                      |
| `worker-gpu` | CUDA model execution, assigned GPU queue                                      | Optional model cache                     |
| `postgres`   | Primary relational record store                                               | Database volume/backups                  |
| `redis`      | Celery broker/results and ephemeral rate-limit cache                          | Optional append-only volume              |
| `storage`    | Local volume initially; MinIO optional profile                                | Original/derivative/export/model volumes |

Model files, uploads, derivatives, and exports live on separate mounted paths/buckets. The API has write access only to upload/export staging through the storage adapter; GPU worker access is restricted to model and processing paths. Database and Redis are private network services, never exposed publicly.

## Compose profiles

- **`cpu`:** API, CPU workers, PostgreSQL, Redis, local storage, and proxy. No CUDA libraries required.
- **`gpu`:** Adds NVIDIA Container Toolkit configuration and GPU worker with `CUDA_VISIBLE_DEVICES`/resource reservations. The worker performs a startup capability check and stays unready if CUDA/model runtime is unavailable.
- **`object-storage`:** Replaces local-storage configuration with MinIO/S3-compatible adapter credentials and bucket lifecycle policies.
- **`development`:** Enables hot reload and local test mail/log services only; it is never a production configuration.

## Configuration

Provide `.env.example` with non-secret defaults and require secrets through environment injection, Docker secrets, Kubernetes secrets, or an external secret manager. Configuration is validated on startup and fails fast for unsafe production defaults such as `DEBUG=true`, placeholder encryption key, public storage, wildcard CORS, or missing allowed origins.

Key variables include:

```text
APP_ENV, APP_SECRET_KEY, DATABASE_URL, REDIS_URL,
STORAGE_PROVIDER, STORAGE_ROOT or S3_ENDPOINT/S3_BUCKET,
MODEL_ROOT, FFMPEG_PATH, MAX_UPLOAD_BYTES,
ALLOWED_ORIGINS, EXTERNAL_APIS_ALLOWED,
CREDENTIAL_ENCRYPTION_KEY, CREDENTIAL_KEY_VERSION,
CELERY_CPU_CONCURRENCY, CELERY_GPU_CONCURRENCY
```

Provider API credentials are created in the admin UI and persisted encrypted; they should not normally live in shared `.env` files. Bootstrap secrets and key-encryption material are the exception and belong in the deployment secret manager.

## Operational flow

1. Provision host storage, TLS DNS, PostgreSQL backups, and secrets.
2. Start PostgreSQL/Redis, run Alembic migrations as a one-shot controlled deployment step, then start API/workers/proxy.
3. Verify `/health/live` and `/health/ready`, worker registrations, storage write/read, FFmpeg availability, and GPU probe where applicable.
4. Create the first system administrator through a controlled bootstrap command/one-time environment variable, then remove bootstrap access.
5. Configure organisation policy, storage retention, local models, then optional external providers.

## Scaling and resilience

- Scale API replicas statelessly; SSE can use a shared event source/polling fallback as scale grows.
- Separate Celery queues: `media`, `transcription.cpu`, `transcription.gpu`, `postprocess`, `exports`, and `model_downloads`. Concurrency is resource-specific rather than global.
- Use `acks_late`, idempotency keys, retries with backoff, and DB-backed job attempts to survive worker restarts.
- For multi-node GPU deployments, mount models from a shared read-only cache/object store or install independently with checksums; route by worker capability labels.
- Back up PostgreSQL daily plus point-in-time recovery where supported; back up storage manifests and test restore into an isolated environment on a schedule.

## Production reverse proxy and observability

Caddy terminates TLS, limits upload body size, enforces security headers, and routes `/api/*` to FastAPI while serving frontend assets. Nginx is a supported alternative when enterprise policy requires it. Emit JSON logs with request/job IDs, Prometheus-compatible metrics hooks, and OpenTelemetry tracing hooks; do not export transcripts, source text, filenames, or credentials as metric labels.

## Documentation deliverables during implementation

- Local quick start and prerequisites (Docker, FFmpeg, CPU path).
- CUDA/NVIDIA Container Toolkit setup and GPU troubleshooting.
- Production deployment, configuration, backup/restore, and upgrade/migration guides.
- Model installation and Qwen/local-service configuration guides.
- Provider configuration, security/privacy, data retention, user management, editor, export, and incident troubleshooting guides.
