# API Endpoint List

All endpoints use `/api/v1`, JSON responses, RFC 7807-style problem responses, server-side authorization, and an opaque request correlation ID. Mutations are audited. File uploads use multipart bodies; large direct-to-object-storage upload flows can be added behind the same asset contract later.

## Authentication and account

| Method           | Path                                    | Purpose                                                          |
| ---------------- | --------------------------------------- | ---------------------------------------------------------------- |
| `POST`           | `/auth/login`                           | Establish short-lived access session and rotated refresh cookie. |
| `POST`           | `/auth/refresh`                         | Rotate refresh session.                                          |
| `POST`           | `/auth/logout`                          | Revoke current refresh session.                                  |
| `GET`            | `/auth/me`                              | Current user, membership, and effective permissions.             |
| `PATCH`          | `/users/me`                             | Update display settings.                                         |
| `GET/POST/PATCH` | `/organisations`, `/organisations/{id}` | Administrator tenant management.                                 |
| `GET/POST/PATCH` | `/users`, `/users/{id}`                 | User management.                                                 |
| `GET/POST/PATCH` | `/roles`, `/roles/{id}`                 | Role assignment and custom organisation roles.                   |

## Assets and projects

| Method             | Path                       | Purpose                                              |
| ------------------ | -------------------------- | ---------------------------------------------------- |
| `GET/POST`         | `/projects`                | List/create projects.                                |
| `GET/PATCH/DELETE` | `/projects/{id}`           | Project details and policy.                          |
| `POST`             | `/assets/upload`           | Validate and receive supported audio/video media.    |
| `GET`              | `/assets`                  | Filterable media library.                            |
| `GET/PATCH/DELETE` | `/assets/{id}`             | Asset detail, metadata, soft/hard deletion request.  |
| `GET`              | `/assets/{id}/download`    | Authorized, time-limited original download redirect. |
| `GET`              | `/assets/{id}/derivatives` | Available waveform/audio/video derivatives.          |

`POST /assets/upload` reports bytes accepted and creates an asset in `uploading`; the client derives browser-side upload progress. The server rejects unsupported magic bytes, size limits, failed malware-hook decisions, and unauthorised projects before job creation.

## Jobs and transcription

| Method | Path                                | Purpose                                                           |
| ------ | ----------------------------------- | ----------------------------------------------------------------- |
| `POST` | `/transcription-jobs`               | Create a queued job from an asset, target selection, and options. |
| `GET`  | `/transcription-jobs`               | Filter by status, project, target, dates, and requester.          |
| `GET`  | `/transcription-jobs/{id}`          | Job status, stage, result links, timings, and redacted errors.    |
| `GET`  | `/transcription-jobs/{id}/events`   | Server-sent event stream with persisted progress.                 |
| `POST` | `/transcription-jobs/{id}/cancel`   | Request cooperative cancellation.                                 |
| `POST` | `/transcription-jobs/{id}/retry`    | Create a new attempt after a failed/cancelled job.                |
| `GET`  | `/transcription-jobs/{id}/attempts` | Administrator diagnostic history.                                 |
| `GET`  | `/hardware/capabilities`            | Available worker capabilities and recommendation data.            |

Job creation accepts `execution_target`, `language`, `translation_mode`, `diarization`, `timestamp_granularity`, and a provider-specific options object validated by that target's capability schema. It returns a 409 problem when policy disallows external egress or model/hardware is unavailable.

## Transcripts and speakers

| Method           | Path                                                                   | Purpose                                           |
| ---------------- | ---------------------------------------------------------------------- | ------------------------------------------------- |
| `GET`            | `/transcripts`                                                         | Search/filter accessible transcripts.             |
| `GET`            | `/transcripts/{id}`                                                    | Transcript metadata and active version.           |
| `GET`            | `/transcripts/{id}/versions`                                           | Version timeline.                                 |
| `POST`           | `/transcripts/{id}/versions`                                           | Create an edit version from validated operations. |
| `GET`            | `/transcripts/{id}/versions/{versionId}/segments`                      | Paginated/time-windowed segments.                 |
| `PATCH`          | `/transcripts/{id}/versions/{versionId}/segments/{segmentId}`          | Edit a segment.                                   |
| `POST`           | `/transcripts/{id}/versions/{versionId}/segments:split`                | Split one segment at validated offset/time.       |
| `POST`           | `/transcripts/{id}/versions/{versionId}/segments:merge`                | Merge adjacent segments.                          |
| `POST`           | `/transcripts/{id}/versions/{versionId}/annotations`                   | Add note/highlight/unclear-audio marker.          |
| `GET/POST/PATCH` | `/transcripts/{id}/speakers`, `/transcripts/{id}/speakers/{speakerId}` | Manage speaker labels.                            |
| `GET`            | `/transcripts/{id}/search`                                             | Text/segment search with time anchors.            |

Autosave uses version preconditions (`If-Match` / version number) so concurrent edits produce a conflict response instead of overwriting data. Undo/redo is client-driven from edit operations, with each accepted change persisted as a new version or durable operation batch.

## Models and providers

| Method                  | Path                                          | Purpose                                             |
| ----------------------- | --------------------------------------------- | --------------------------------------------------- |
| `GET`                   | `/model-catalog`                              | Browse supported/downloadable model entries.        |
| `GET/POST/PATCH/DELETE` | `/installed-models`, `/installed-models/{id}` | Manage local model installation state.              |
| `POST`                  | `/installed-models/{id}/download`             | Queue download with progress events.                |
| `POST`                  | `/installed-models/{id}/test`                 | Queue/retrieve a health or sample inference test.   |
| `GET/PUT`               | `/task-defaults`                              | Read/set default execution target per task.         |
| `GET/POST`              | `/api-providers`                              | List/create redacted provider configurations.       |
| `GET/PATCH/DELETE`      | `/api-providers/{id}`                         | Edit/delete provider; secret fields are write-only. |
| `POST`                  | `/api-providers/{id}/test`                    | Test connection without exposing secret data.       |
| `POST`                  | `/api-providers/{id}/rotate-secret`           | Replace encrypted credential.                       |
| `GET`                   | `/api-providers/{id}/usage`                   | Usage, error, and cost aggregates.                  |

## AI processing, reports, and exports

| Method                  | Path                                          | Purpose                                                                            |
| ----------------------- | --------------------------------------------- | ---------------------------------------------------------------------------------- |
| `POST`                  | `/ai-runs`                                    | Queue clean-up, translation, extraction, or analysis against a transcript version. |
| `GET`                   | `/ai-runs/{id}`                               | Status and structured result.                                                      |
| `GET/POST/PATCH/DELETE` | `/report-templates`, `/report-templates/{id}` | Built-in/custom template management.                                               |
| `GET/POST`              | `/reports`                                    | List/create report generation runs.                                                |
| `GET/PATCH/DELETE`      | `/reports/{id}`                               | View/edit/delete a generated report.                                               |
| `POST`                  | `/exports`                                    | Queue an export of a transcript, report, or selected segments.                     |
| `GET`                   | `/exports/{id}`                               | Export status and short-lived download link.                                       |

## Operations

| Method      | Path                 | Purpose                                               |
| ----------- | -------------------- | ----------------------------------------------------- |
| `GET/PATCH` | `/settings`          | Organisation/system settings within permission scope. |
| `GET`       | `/audit-logs`        | Privileged redacted audit queries.                    |
| `GET`       | `/dashboard/metrics` | Aggregated dashboard counters and trend data.         |
| `GET`       | `/health/live`       | Liveness, no dependency checks.                       |
| `GET`       | `/health/ready`      | Readiness checks without secret disclosure.           |

## Status and error contract

- `202 Accepted` for queued work; response contains resource ID and status endpoint.
- `400/422` for invalid payload/media options, `401/403` for authentication/authorization, `404` for inaccessible resources, `409` for lifecycle/policy conflicts, `413` for size limits, `429` for rate limits, and `502/504` for redacted provider failures.
- Problem responses contain `type`, `title`, `status`, `detail`, `code`, and `request_id`; internal stack traces remain in administrator-only logs.
