# Universal Model Downloads Design

> **Historical plan:** Superseded by the approved selective-port program and its Phase 1 schema-baseline design dated 2026-07-16. Retained for audit history; do not execute as the governing implementation plan.

## Goal

Allow the CPU worker to download every model in the catalog while clearly preventing models with unavailable runtime requirements from being enabled, tested, or selected as defaults.

## Current Problems

- The backend creates installed-model records with status `queued`, while Model Manager only renders its Download action for the nonexistent `available` status.
- Failed downloads display their last error but provide no Retry action.
- Hugging Face failures can leave useful partial downloads, but the application does not explain whether a retry will resume them.
- Whisper Local downloads call `whisper.load_model`, coupling weight acquisition to model loading and unnecessary CPU/RAM use.
- The CPU worker lacks the OpenAI Whisper package needed to resolve and download Whisper Local weights.
- GPU-only catalog entries are downloadable with `huggingface_hub`, but Model Manager does not clearly separate download support from runtime compatibility.
- Downloads begin without an application-level capacity check, so low-space failures surface late as opaque I/O errors.

## Architecture

Keep the existing API, Celery maintenance queue, CPU worker, and protected model volume. The CPU worker becomes a universal downloader without becoming a universal inference worker.

Model acquisition remains adapter-specific:

- Faster-Whisper and advanced Hugging Face entries use `huggingface_hub.snapshot_download` with the installed model directory as `local_dir`. Existing `.incomplete` files remain in place so retries can resume.
- Whisper.cpp continues streaming its configured source URL into the installed model directory.
- Whisper Local uses the OpenAI Whisper package only to resolve the official weight URL and download the checkpoint. It must not instantiate or load the model during acquisition.

Runtime compatibility remains driven by catalog `requirements`, hardware detection, and provider probes. Download success does not imply that a model can run on the active CPU worker.

## Backend Behavior

Before starting network I/O, the worker calculates:

- free bytes on the filesystem containing `MODEL_ROOT`;
- estimated catalog bytes;
- bytes already present in the target directory;
- remaining estimated bytes plus a fixed 512 MiB safety margin.

If free capacity is below the required estimate, the task fails before network access with an actionable error containing required and available byte counts. Entries without `size_bytes` skip the estimate rather than being rejected.

Retrying a `failed` model resets its error and progress through the existing API endpoint. The worker preserves the target directory so supported downloaders can resume partial content. Successful completion clears `last_error`, records `storage_key`, sets progress to 100, and marks the model installed.

Whisper Local acquisition returns the downloaded checkpoint path for checksum and storage-key handling. Missing model identifiers produce a clear unsupported-model error.

## Frontend Behavior

Model Manager aligns with backend statuses:

- `queued`: show **Download**.
- `failed`: show **Retry download** and retain the previous error until retry begins.
- `downloading`: show progress and Cancel.
- `installed`: retain enable, disable, test, and default actions.

Catalog requirements render a visible compatibility message. Entries with `requires_cuda: true` show **GPU required to run; download is available** when CUDA is unavailable. Enable, Test, and Set default remain unavailable unless the model is installed and its compatibility assessment permits execution.

The shared TypeScript `ModelInstallStatus` union uses the same values as the backend enum and removes `available`.

## Worker Packaging

The CPU worker installs the existing `ai` extra plus the `whisper-local` extra. Advanced speech inference dependencies remain exclusive to the GPU worker. This lets CPU download official Whisper checkpoints without installing NeMo, Transformers, Qwen-ASR, or CUDA-oriented inference stacks.

## Error Handling

- Capacity errors are detected before download and stored in `last_error`.
- Interrupted Hugging Face and Whisper downloads preserve partial files for retry.
- Cancellation keeps its current explicit failed/cancelled state and can subsequently be retried.
- Checksum verification remains mandatory where a checksum is configured.
- A downloaded but runtime-incompatible model is not reported as a failed download; compatibility is a separate state shown to the user.

## Testing

Backend tests will verify:

- capacity calculation with and without partial bytes;
- early failure when capacity is insufficient;
- Whisper Local downloads weights without calling `load_model`;
- failed downloads can be retried and successful retries clear errors;
- existing Hugging Face adapter routing remains intact.

Frontend tests will verify:

- queued models render Download;
- failed models render Retry download and their error;
- the obsolete `available` state is absent;
- GPU-required entries show the download-versus-runtime compatibility message;
- incompatible installed models cannot be selected as defaults or tested.

Deployment verification will include backend and frontend test suites, frontend build, CPU image rebuild, health checks, worker ping, and real downloads representative of direct URL, Faster-Whisper, Whisper Local, and advanced Hugging Face paths. Full catalog acquisition may consume approximately 40–50 GB and is treated as an explicit long-running verification step.

## Non-Goals

- Running NeMo, Qwen-ASR, Granite/Transformers, or other GPU-oriented inference on the CPU worker.
- Automatically deleting existing installed models or partial downloads.
- Adding a separate downloader service or queue.
- Changing catalog model sizes or hardware requirements beyond correcting demonstrably inaccurate metadata.
