# Database Schema

PostgreSQL is the system of record. Every tenant-owned table includes `organisation_id`, `created_at`, and `updated_at` unless noted. UUID primary keys are recommended; timestamps are stored as `timestamptz`; durations are stored in integer milliseconds; monetary estimates use `numeric(12,6)` plus ISO currency code.

## Identity and authorization

| Table                      | Key columns                                                                            | Notes                                                        |
| -------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `organisations`            | `id`, `name`, `slug`, `external_apis_allowed`, `local_only_enforced`, `retention_days` | Tenant policy boundary.                                      |
| `users`                    | `id`, `email`, `password_hash`, `display_name`, `is_active`, `last_login_at`           | Password hashes use Argon2id.                                |
| `roles`                    | `id`, `organisation_id nullable`, `code`, `name`, `is_system`                          | System roles seed the requested six role levels.             |
| `permissions`              | `id`, `code`, `description`                                                            | Examples: `models.manage`, `transcripts.edit`, `audit.read`. |
| `role_permissions`         | `role_id`, `permission_id`                                                             | Unique composite key.                                        |
| `organisation_memberships` | `organisation_id`, `user_id`, `role_id`, `status`                                      | Enforces organisation access.                                |
| `refresh_tokens`           | `id`, `user_id`, `token_hash`, `expires_at`, `revoked_at`, `replaced_by_id`            | Refresh rotation and revocation.                             |

## Media and work

| Table                | Key columns                                                                                                                                                                                                        | Notes                                                  |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| `projects`           | `id`, `organisation_id`, `name`, `sensitivity`, `retention_days`, `external_apis_allowed`                                                                                                                          | Optional folder/policy boundary for recordings.        |
| `media_assets`       | `id`, `organisation_id`, `project_id`, `uploaded_by_id`, `original_filename`, `content_type`, `byte_size`, `sha256`, `storage_key`, `status`, `deleted_at`                                                         | Original file metadata; no local path exposed.         |
| `media_metadata`     | `asset_id`, `duration_ms`, `container`, `audio_codec`, `video_codec`, `sample_rate_hz`, `channels`, `bit_rate`                                                                                                     | Output from ffprobe.                                   |
| `media_derivatives`  | `id`, `asset_id`, `kind`, `storage_key`, `sha256`, `byte_size`, `metadata_json`, `expires_at`                                                                                                                      | Extracted audio, waveform, thumbnail, chunk artifacts. |
| `transcription_jobs` | `id`, `asset_id`, `requested_by_id`, `execution_target_id`, `status`, `progress_percent`, `language`, `options_json`, `started_at`, `finished_at`, `processing_ms`, `cost_estimate`, `error_code`, `error_message` | Central lifecycle record.                              |
| `job_attempts`       | `id`, `job_id`, `attempt_number`, `worker_id`, `status`, `started_at`, `finished_at`, `error_detail`, `metrics_json`                                                                                               | Retry and diagnostic history.                          |
| `job_events`         | `id`, `job_id`, `attempt_id`, `sequence`, `state`, `progress_percent`, `message`, `metadata_json`, `created_at`                                                                                                    | Persisted source for SSE/status history.               |

`transcription_jobs.status` is constrained to `queued`, `uploading`, `extracting_audio`, `preprocessing`, `transcribing`, `post_processing`, `completed`, `failed`, and `cancelled`. A partial unique index prevents more than one active transcription job per asset/execution profile where desired.

## Transcript data

| Table                        | Key columns                                                                                                                | Notes                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| `transcripts`                | `id`, `job_id`, `language`, `detected_language`, `source_provider`, `active_version_id`, `status`                          | One transcription output per job.          |
| `transcript_versions`        | `id`, `transcript_id`, `version_number`, `parent_version_id`, `created_by_id`, `source`, `snapshot_json`, `change_summary` | Immutable snapshots for edits and AI runs. |
| `transcript_segments`        | `id`, `version_id`, `sequence`, `start_ms`, `end_ms`, `speaker_id`, `text`, `confidence`, `is_unclear`, `notes`            | Ordered and range-validated.               |
| `transcript_words`           | `id`, `segment_id`, `sequence`, `start_ms`, `end_ms`, `word`, `confidence`                                                 | Optional, only when supplied.              |
| `speakers`                   | `id`, `transcript_id`, `label`, `display_name`, `role`, `color`                                                            | Labels can outlive segment edits.          |
| `transcript_edit_operations` | `id`, `version_id`, `actor_id`, `operation_type`, `payload_json`, `created_at`                                             | Enables audit/replay and UI undo history.  |
| `transcript_annotations`     | `id`, `version_id`, `segment_id nullable`, `author_id`, `kind`, `body`, `start_offset`, `end_offset`                       | Notes, highlights, unclear-audio markers.  |

## Providers, models, and AI work

| Table                  | Key columns                                                                                                                                                              | Notes                                                           |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------- |
| `provider_definitions` | `id`, `organisation_id nullable`, `adapter_key`, `name`, `category`, `base_url`, `model_name`, `auth_type`, `headers_json`, `capabilities_json`, `enabled`, `is_default` | Non-secret provider configuration.                              |
| `provider_secrets`     | `id`, `provider_id`, `ciphertext`, `nonce`, `key_version`, `rotated_at`                                                                                                  | Encrypted credentials only; never serialized to client schemas. |
| `provider_usage_logs`  | `id`, `provider_id`, `job_id nullable`, `task`, `request_id`, `input_units`, `output_units`, `duration_ms`, `estimated_cost`, `status`, `error_code`                     | Redacted cost/health telemetry.                                 |
| `model_catalog`        | `id`, `adapter_key`, `model_identifier`, `name`, `model_type`, `source_url`, `revision`, `size_bytes`, `requirements_json`, `capabilities_json`, `checksum`              | Curated/downloadable model metadata.                            |
| `installed_models`     | `id`, `organisation_id nullable`, `catalog_id`, `storage_key`, `status`, `download_progress`, `enabled`, `last_used_at`, `verified_at`, `hardware_compatibility_json`    | Download result and local state.                                |
| `model_task_defaults`  | `id`, `organisation_id`, `task`, `execution_target_id`, `updated_by_id`                                                                                                  | Default target per task: transcription, translation, etc.       |
| `ai_processing_runs`   | `id`, `transcript_version_id`, `task`, `execution_target_id`, `options_json`, `status`, `result_json`, `output_version_id`, `cost_estimate`                              | Clean-up, translation, extraction, and summary lineage.         |

An `execution_target` in API contracts resolves to either an enabled `installed_models` record or an enabled `provider_definitions` record; a database check/typed reference layer prevents a target from being both.

## Reports, exports, settings, and audit

| Table              | Key columns                                                                                                                                 | Notes                                                                 |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `report_templates` | `id`, `organisation_id`, `name`, `kind`, `schema_json`, `prompt_template`, `enabled`                                                        | Built-in kinds plus custom templates.                                 |
| `reports`          | `id`, `transcript_version_id`, `template_id`, `processing_run_id`, `title`, `content_json`, `content_markdown`, `status`                    | Structured content plus rendered source.                              |
| `export_records`   | `id`, `requested_by_id`, `source_type`, `source_id`, `format`, `options_json`, `storage_key`, `status`, `expires_at`                        | Generated artifacts are short-lived by default.                       |
| `system_settings`  | `id`, `organisation_id nullable`, `key`, `value_json`, `is_secret`, `updated_by_id`                                                         | Scope-specific configuration; secrets use a separate encryption path. |
| `audit_logs`       | `id`, `organisation_id`, `actor_id nullable`, `action`, `resource_type`, `resource_id`, `outcome`, `ip_hash`, `metadata_json`, `created_at` | Redacted, append-only operational trail.                              |

## Integrity, indexes, and retention

- Add foreign keys with `RESTRICT` for active business records and `SET NULL` for audit actor references.
- Index organisation plus common filters: `media_assets(organisation_id, created_at DESC)`, `transcription_jobs(organisation_id, status, created_at DESC)`, `transcript_segments(version_id, sequence)`, and `audit_logs(organisation_id, created_at DESC)`.
- Store `options_json`, capabilities, and reports as `jsonb`, validate their shape in application schemas, and index only stable query fields.
- Use soft deletion for user-visible assets; a retention task performs hard deletion of storage objects, derivatives, transcript/report data, and keys under documented policy.
