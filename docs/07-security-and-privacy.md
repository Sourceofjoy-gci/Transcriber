# Security and Privacy Plan

## Threat model and boundaries

Primary assets are sensitive media, transcripts, derived reports, provider credentials, account sessions, and audit data. Trust boundaries are browser-to-API, API-to-storage/database/queue, worker-to-model runtimes, and worker-to-external APIs. Workers receive least-privilege credentials and are the only component allowed to decrypt provider API keys.

## Authentication and authorization

- Use Argon2id password hashing, account lockout/rate limiting, short-lived access tokens, rotated/revocable refresh tokens, secure `HttpOnly` `SameSite` cookies, and MFA/SSO extension points.
- Enforce permissions at service/resource layer with organisation and project scope; frontend route guards are convenience only.
- Seed six requested roles: System Administrator, Organisation Administrator, Transcription Manager, Reviewer, Standard User, and Read-only User. Implement permissions as granular codes so roles can be customized safely.
- Require fresh authorization checks for download, export, deletion, API/provider/model management, and audit access.

## Credential and secret protection

- Encrypt API credentials at rest with envelope encryption (AES-256-GCM data encryption key; master key supplied through KMS/secret manager or protected deployment secret). Store nonce and key version beside ciphertext.
- Provider APIs return a redacted `secret_configured` boolean only. They never return ciphertext, keys, authorization headers, or connection test payloads containing secrets.
- Rotate secrets with versioned keys, support re-encryption migrations, and redact known secret values/header names from structured logs, errors, traces, and job events.

## Data protection and privacy controls

- Encrypt transport with TLS; use encrypted disks/buckets and database encryption controls appropriate to the deployment environment.
- Support organisation/project retention policies, permanent deletion workflow, derived-artifact deletion, legal hold extension point, and export expiry.
- Default to local-only mode when configured. External job targets require both tenant/project policy permission and explicit user acknowledgement describing recipient/provider and data category.
- Generate audit events for media/transcript/report view, download, export, edit, deletion, configuration changes, and external provider execution. Audit content is metadata-only and redacted.
- Keep original media and extracted derivatives in private object keys; expose only authorized, short-lived signed download URLs.

## Input and media security

- Validate configured extension allowlist, MIME type, file magic bytes, maximum size, filename normalization, checksum, and FFmpeg/ffprobe output before processing.
- Store uploads in a quarantine state and invoke an antivirus/malware scanning hook before making them processable; document a fail-closed/fail-open administrator policy.
- Never execute uploaded files. Run FFmpeg, whisper.cpp, and other binaries with fixed argument construction, time/resource limits, non-root users, and constrained container mounts.
- Enforce SSRF prevention for custom providers: HTTPS by default, allowlisted base host, blocked private/link-local targets, fixed relative endpoint path, bounded redirects, and outbound proxy option.

## Application and browser safeguards

- Apply Pydantic validation, parameterized ORM queries, output encoding, content-disposition downloads, strict CORS allowlist, CSP, `X-Content-Type-Options`, referrer policy, and clickjacking protection.
- Use CSRF protection for cookie-authenticated state-changing requests. If bearer flows are enabled later, do not mix them casually with cookie assumptions.
- Rate-limit login, uploads, provider tests, exports, and AI run creation by user/organisation/IP. Set request-body and multipart limits at proxy and application layers.
- Return safe, stable error codes to users and preserve full exceptions only in restricted logs with a correlation ID.

## Operations and assurance

- Use non-root containers, pinned base images/dependencies, SBOM/dependency scans, secret scanning, separated database roles, encrypted backups, and regular restore drills.
- Monitor authentication anomalies, upload validation failures, provider error spikes, worker OOMs, unusual downloads/exports, and retention-task failures.
- Provide incident runbooks for credential rotation, provider disablement, compromised account response, media deletion request, and backup restoration.
- Complete a deployment-specific privacy impact assessment before processing institutional recordings or regulated personal data.
