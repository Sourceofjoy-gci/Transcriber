# Universal Model Downloads Implementation Plan

> **Historical plan:** Superseded by the approved selective-port program and its Phase 1 schema-baseline design dated 2026-07-16. Retained for audit history; do not execute as the governing implementation plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every catalog model downloadable by the CPU worker while keeping GPU-only models visibly unavailable for execution on CPU-only hardware.

**Architecture:** Preserve the current API, Celery maintenance queue, and model volume. Add downloader-only behavior and capacity preflight in `model_tasks.py`, align frontend states with the backend enum, and install only the OpenAI Whisper download dependency in the CPU worker; advanced inference dependencies remain GPU-only.

**Tech Stack:** Python 3.12, FastAPI, Celery, SQLAlchemy, Hugging Face Hub, OpenAI Whisper, React, TypeScript, TanStack Query, Vitest, Docker Compose.

## Global Constraints

- The CPU worker downloads every catalog entry but does not run NeMo, Qwen-ASR, Granite/Transformers, or other GPU-oriented inference stacks.
- Existing partial downloads are preserved so supported downloaders can resume.
- Capacity preflight uses remaining catalog bytes plus a fixed 512 MiB safety margin.
- Entries without `size_bytes` are allowed to download without an estimate.
- GPU incompatibility is distinct from download failure and must remain visible after download.
- No installed model or partial download is automatically deleted.

---

### Task 0: Establish the tracked and testable baseline

**Files:**
- Modify: `.gitignore`
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/domain.py`
- Create: `backend/tests/test_models_package.py`
- Create locally, ignored: `backend/.venv/`
- Create locally, ignored: `frontend/node_modules/`

**Interfaces:**
- Produces: the restored `app.models.domain` package required by the API, migrations, worker, and tests.
- Produces: local backend and frontend dependency environments used by every later verification step.

- [ ] **Step 1: Verify the recovered model-package regression test**

Run:

```bash
docker run --rm -v /root/Transcriber/backend:/workspace -w /workspace transcriber-api \
  python -m unittest tests/test_models_package.py
```

Expected: one passing test proving `app.models.domain` imports and exposes `Organisation` and `TranscriptionJob`.

- [ ] **Step 2: Commit the recovered model package and corrected ignore rule**

```bash
git add .gitignore backend/app/models backend/tests/test_models_package.py
git commit -m "fix: restore tracked domain models"
```

- [ ] **Step 3: Install backend development dependencies**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -c requirements.lock -e '.[dev]'
```

Expected: editable backend and pytest/ruff install successfully inside the ignored virtual environment.

- [ ] **Step 4: Install frontend dependencies**

```bash
cd frontend
npm ci
```

Expected: npm installs the lockfile dependency graph with no high-severity install failure.

---

### Task 1: Backend downloader preflight and download-only Whisper handling

**Files:**
- Modify: `backend/tests/test_model_manager.py`
- Modify: `backend/app/worker/model_tasks.py`

**Interfaces:**
- Produces: `_ensure_download_capacity(target: Path, estimated_size: int | None) -> None`
- Produces: `_download_whisper_local(catalog: ModelCatalog, target: Path) -> Path`
- Consumes: `ModelCatalog.size_bytes`, existing target bytes, `shutil.disk_usage`, and OpenAI Whisper `_MODELS`/`_download` download primitives.

- [ ] **Step 1: Replace the Whisper fake with a download-only fake and add failing downloader tests**

Add a fake module with `_MODELS = {"base": "https://models.example/base.pt"}`, an `_download(url, root, in_memory)` function that writes `base.pt`, and a `load_model` function that raises if called. Add tests asserting `_download_whisper_local` returns the checkpoint without calling `load_model`, `_ensure_download_capacity` accounts for partial bytes, and insufficient free space raises `OSError` containing required and available byte counts.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_model_manager.py -k 'whisper_local or download_capacity' -q
```

Expected: failures because `_download_whisper_local` and `_ensure_download_capacity` do not exist and the current code calls `load_model`.

- [ ] **Step 3: Implement the minimal backend behavior**

In `model_tasks.py`, add:

```python
DOWNLOAD_SAFETY_MARGIN_BYTES = 512 * 1024 * 1024


def _path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _ensure_download_capacity(target: Path, estimated_size: int | None) -> None:
    if estimated_size is None:
        return
    existing_bytes = _path_size(target)
    remaining_bytes = max(estimated_size - existing_bytes, 0)
    required_bytes = remaining_bytes + DOWNLOAD_SAFETY_MARGIN_BYTES
    available_bytes = shutil.disk_usage(target).free
    if available_bytes < required_bytes:
        raise OSError(
            28,
            f"Insufficient model storage: requires {required_bytes} bytes "
            f"including safety margin; {available_bytes} bytes available",
        )


def _download_whisper_local(catalog: ModelCatalog, target: Path) -> Path:
    try:
        import whisper
    except ImportError as error:
        raise RuntimeError("openai-whisper package is not installed in this worker image") from error
    url = getattr(whisper, "_MODELS", {}).get(catalog.model_identifier)
    if not url:
        raise ValueError(f"Unsupported Whisper Local model: {catalog.model_identifier}")
    downloaded = whisper._download(url, str(target), False)
    return Path(downloaded)
```

Call `_ensure_download_capacity(target, catalog.size_bytes)` after `target.mkdir(...)` and before network I/O. Replace `whisper.load_model(...)` with `downloaded_path = _download_whisper_local(catalog, target)`.

- [ ] **Step 4: Run the focused and full model-manager tests**

Run:

```bash
cd backend
.venv/bin/python -m pytest tests/test_model_manager.py -q
```

Expected: all tests pass, including retry behavior already exercised through the existing download endpoint.

- [ ] **Step 5: Commit the backend downloader change**

```bash
git add backend/app/worker/model_tasks.py backend/tests/test_model_manager.py
git commit -m "fix: make model downloads resumable and capacity aware"
```

---

### Task 2: Align Model Manager states and GPU-only messaging

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/ModelsPage.tsx`
- Modify: `frontend/src/pages/ModelsPage.test.tsx`
- Modify: `backend/tests/test_model_routing.py`

**Interfaces:**
- Produces: `InstalledModel.status` union `"queued" | "downloading" | "installed" | "failed" | "deleting"`.
- Produces: Download action for `queued`, Retry download action for `failed`, and the message `GPU required to run; download is available` for CUDA-required catalog entries that are incompatible.

- [ ] **Step 1: Add failing frontend tests for queued, failed, and GPU-required models**

Extend the Models page fixture with one queued entry and one failed entry. Assert that `Download` invokes `downloadInstalledModel` for the queued ID, `Retry download` invokes it for the failed ID, the prior error remains visible, and a catalog entry with `requirements.requires_cuda === true` plus `hardware_compatibility.compatible === false` renders `GPU required to run; download is available`.

- [ ] **Step 2: Run the Models page test and verify RED**

Run:

```bash
cd frontend
npm test -- --run src/pages/ModelsPage.test.tsx
```

Expected: queued/retry buttons and GPU-specific message are missing.

- [ ] **Step 3: Implement aligned frontend states**

Change the TypeScript union from `available` to `queued`. Render a primary action when status is `queued` or `failed`, use label `Download` for queued and `Retry download` for failed, and invoke the existing `downloadMutation` with the installed model ID. Render the GPU-only message when `catalog.requirements.requires_cuda === true` and the installed model is incompatible. Keep Test and Set default disabled for incompatible models.

- [ ] **Step 4: Correct the stale backend test enum**

In `backend/tests/test_model_routing.py`, replace `ModelInstallStatus.available` with `ModelInstallStatus.queued` so the unusable-state test matches the restored production enum.

- [ ] **Step 5: Run focused frontend and backend tests**

Run:

```bash
cd frontend
npm test -- --run src/pages/ModelsPage.test.tsx
cd ../backend
.venv/bin/python -m pytest tests/test_model_routing.py -q
```

Expected: both commands pass.

- [ ] **Step 6: Commit the state-alignment change**

```bash
git add frontend/src/types.ts frontend/src/pages/ModelsPage.tsx frontend/src/pages/ModelsPage.test.tsx backend/tests/test_model_routing.py
git commit -m "fix: expose model download and retry actions"
```

---

### Task 3: Package Whisper download support in the CPU worker

**Files:**
- Modify: `docker-compose.yml`
- Verify: `backend/pyproject.toml`

**Interfaces:**
- Consumes: existing optional extras `ai` and `whisper-local`.
- Produces: CPU worker build argument `WORKER_EXTRAS: ai,whisper-local`; GPU worker remains `ai,advanced-speech`.

- [ ] **Step 1: Add a failing Compose configuration assertion**

Run:

```bash
docker compose --profile cpu config | rg 'WORKER_EXTRAS: ai,whisper-local'
```

Expected: no match because the CPU worker currently installs only `ai`.

- [ ] **Step 2: Update the CPU worker extra**

Change only the CPU build argument:

```yaml
args:
  WORKER_EXTRAS: ai,whisper-local
```

Do not add advanced inference dependencies to the CPU image.

- [ ] **Step 3: Verify resolved Compose configuration**

Run:

```bash
docker compose --profile cpu config | rg 'WORKER_EXTRAS: ai,whisper-local'
```

Expected: one matching CPU worker build argument.

- [ ] **Step 4: Commit worker packaging**

```bash
git add docker-compose.yml
git commit -m "build: add whisper downloads to cpu worker"
```

---

### Task 4: Full verification, rebuild, and representative downloads

**Files:**
- Verify: `backend/`
- Verify: `frontend/`
- Verify: `docker-compose.yml`

**Interfaces:**
- Consumes: all previous tasks.
- Produces: rebuilt running CPU stack with verified direct URL, Faster-Whisper, Whisper Local, and advanced Hugging Face download paths.

- [ ] **Step 1: Run backend quality gates**

```bash
cd backend
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest
```

Expected: zero lint errors and zero test failures.

- [ ] **Step 2: Run frontend quality gates**

```bash
cd frontend
npm test -- --run
npm run lint
npm run build
```

Expected: zero test or lint failures and a successful production build.

- [ ] **Step 3: Rebuild and restart the CPU stack**

```bash
docker compose --profile cpu up --build -d
```

Expected: API, CPU worker, Caddy, PostgreSQL, and Redis start; PostgreSQL and Redis are healthy.

- [ ] **Step 4: Verify health and worker dependencies**

```bash
docker compose --profile cpu ps --all
docker compose exec -T caddy wget -qO- http://localhost:8080/health/ready
docker compose exec -T worker-cpu celery -A app.worker.celery_app inspect ping --timeout 5
docker compose exec -T worker-cpu python -c 'import faster_whisper, huggingface_hub, whisper; print("downloaders ready")'
```

Expected: all services running, readiness status `ready`, one worker pong, and `downloaders ready`.

- [ ] **Step 5: Verify representative download paths without forcing GPU execution**

Use the authenticated Model Manager to download or retry one small model for each available acquisition path: Whisper.cpp Tiny, Faster-Whisper Tiny, Whisper Tiny, and one advanced Hugging Face entry. Poll `/api/v1/installed-models` until each reaches `installed` or produces a new actionable error. Confirm GPU-required entries remain marked incompatible and cannot become defaults on the CPU-only host.

- [ ] **Step 6: Inspect final capacity and logs**

```bash
df -h /
docker compose exec -T worker-cpu df -h /var/lib/transcriber/models
docker compose --profile cpu logs --since=30m api worker-cpu caddy
```

Expected: sufficient remaining capacity and no unhandled startup or task exceptions.
