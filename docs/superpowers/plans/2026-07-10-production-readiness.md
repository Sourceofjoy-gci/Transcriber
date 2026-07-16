# Production Readiness Completion Implementation Plan

> **Historical plan:** Superseded by the approved selective-port program and its Phase 1 schema-baseline design dated 2026-07-16. Retained for audit history; do not execute as the governing implementation plan.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a production-ready Transcriber release whose complete documented feature set, real local AI/translation, real acoustic diarisation, catalog-model lifecycle, recovery behavior, and production configuration are proven by one zero-exit PowerShell gate.

**Architecture:** Keep the existing FastAPI/PostgreSQL/Redis/Celery/React boundaries, add Qwen3 4B GGUF through a dedicated single-concurrency `postprocess` worker, and replace synthetic diarisation with the public CC-BY-4.0 NeMo streaming Sortformer model. Drive all proof from one machine-readable acceptance manifest and isolated Docker resources; the PowerShell entry point records evidence from locked installs, integration/browser flows, model downloads, backup/restore, security scans, and health checks.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, Celery/Redis, PostgreSQL 16, `llama-cpp-python` 0.3.33, NeMo 2.x, whisper.cpp v1.9.1, React 18, TypeScript, Vite/Vitest, Playwright 1.61.1, Docker Compose, PowerShell 7.

## Global Constraints

- Governing design: `docs/superpowers/specs/2026-07-10-production-readiness-design.md`.
- Readiness covers the complete documented backend, frontend, worker, administration, transcription, model-management, storage, export, reporting, security, backup, and restore surface.
- End-to-end scope explicitly includes authentication/RBAC, uploads, media processing, transcription, transcript editing, diarisation, AI processing/translation, reports, exports/downloads, projects, organisations, users, roles, providers, settings, storage, retention, audit logs, model management, failure recovery, backup/restore, and readiness endpoints.
- Existing dated status reports are historical evidence, not waivers.
- Make the smallest complete fixes and avoid unrelated refactors.
- Write a failing regression or acceptance test before every behavior-changing fix.
- Use Python 3.12 and Node.js 22 for reproducible checks.
- Use locked backend and frontend installs; regenerate locks only through documented lock commands.
- Every required command must exit zero; high- or critical-severity dependency/image vulnerabilities fail the gate.
- Run the stack with clean PostgreSQL, Redis, storage, and model volumes under an isolated Docker Compose project name.
- Dynamically enumerate `CATALOG_ENTRIES`; never hard-code a second model list in the gate.
- Download every catalog entry before classifying inference; hardware-only inference limitations require hardware-probe evidence.
- Default production AI provider is `llama_cpp_local`; `stub` is test-only.
- Stop after three complete test-and-fix iterations or immediately on the user-defined blockers.
- Do not open a pull request without separate user authorization and independent reviewer sign-off.

## File and responsibility map

- `scripts/production-readiness.matrix.json`: authoritative acceptance criteria and evidence contracts.
- `scripts/production_readiness/manifest.py`: validate the manifest and generate Markdown coverage.
- `scripts/production_readiness/evidence.py`: append sanitized command/criterion/model evidence.
- `scripts/production_readiness/api_flow.py`: real API acceptance flows and recovery operations.
- `scripts/production_readiness/model_flow.py`: dynamic catalog installation, verification, and inference.
- `scripts/production-readiness.ps1`: sole orchestration entry point.
- `docs/16-production-readiness-acceptance-matrix.md`: generated human-readable acceptance view.
- `backend/app/providers/local_llm.py`: Qwen GGUF inference and JSON-schema normalization.
- `backend/app/providers/post_processing_schemas.py`: task prompts and exact output schemas.
- `backend/app/providers/diarization.py`: real NeMo Sortformer adapter and result normalization.
- `backend/app/services/installed_models.py`: safe installed-model resolution shared by transcription, AI, and diarisation.
- `backend/app/worker/model_tasks.py`: atomic, checksummed, progress-reporting model downloads.
- `backend/app/worker/post_processing_tasks.py`: real local AI/report execution.
- `backend/app/worker/tasks.py`: real diarisation and model-path routing.
- `backend/app/core/config.py`: production safety validation.
- `docker-compose.yml` and `backend/Dockerfile`: worker separation, runtimes, health checks, and profiles.
- `frontend/src/components/PermissionRoute.tsx`: route-level permission guard.
- `frontend/e2e/*.spec.ts`: browser acceptance flows against the composed application.
- `scripts/backup*.{ps1,sh}` and `scripts/restore*.{ps1,sh}`: database plus storage-manifest recovery.

---

### Task 1: Acceptance manifest, coverage validator, and evidence primitives

**Files:**
- Create: `scripts/production-readiness.matrix.json`
- Create: `scripts/__init__.py`
- Create: `scripts/production_readiness/__init__.py`
- Create: `scripts/production_readiness/manifest.py`
- Create: `scripts/production_readiness/evidence.py`
- Create: `scripts/production_readiness/environment.py`
- Create: `backend/tests/test_production_readiness_manifest.py`
- Create: `docs/16-production-readiness-acceptance-matrix.md`
- Modify: `.gitignore`

**Interfaces:**
- Produces: `load_manifest(path: Path) -> list[dict]`, `validate_manifest(rows: list[dict], repo: Path) -> list[str]`, `render_markdown(rows: list[dict]) -> str`.
- Produces: `EvidenceWriter(root: Path).record(kind: str, identifier: str, status: str, payload: dict) -> None` with recursive secret redaction.
- Produces: `write_readiness_environment(path: Path, project_name: str) -> None`; writes mode `0600` without returning or logging generated secrets.
- Consumed by: Tasks 9–14 and `scripts/production-readiness.ps1`.

- [ ] **Step 1: Write failing manifest schema and coverage tests**

```python
from pathlib import Path

from scripts.production_readiness.manifest import load_manifest, validate_manifest


REQUIRED_AREAS = {
    "baseline", "identity", "administration", "media", "transcription",
    "diarisation", "editor", "ai", "reports", "exports", "models",
    "providers", "security", "backup_restore", "recovery", "documentation",
}


def test_acceptance_manifest_is_complete_and_source_backed() -> None:
    repo = Path(__file__).resolve().parents[2]
    rows = load_manifest(repo / "scripts/production-readiness.matrix.json")
    assert len(rows) >= 80
    assert {row["area"] for row in rows} == REQUIRED_AREAS
    assert not validate_manifest(rows, repo)
    assert len({row["id"] for row in rows}) == len(rows)
    assert all(row["blocking"] is True for row in rows if row["hardware_policy"] == "required")
```

- [ ] **Step 2: Run the focused test and confirm the missing-module failure**

Run: `cd backend && python -m pytest tests/test_production_readiness_manifest.py -q`

Expected: FAIL because `scripts.production_readiness.manifest` does not exist.

- [ ] **Step 3: Implement manifest validation and safe evidence writing**

```python
# scripts/production_readiness/manifest.py
import json
from pathlib import Path

REQUIRED_KEYS = {
    "id", "area", "feature", "source", "scenario", "expected",
    "evidence", "hardware_policy", "blocking",
}


def load_manifest(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Acceptance manifest must be a JSON array")
    return payload


def validate_manifest(rows: list[dict], repo: Path) -> list[str]:
    errors: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        missing = REQUIRED_KEYS - row.keys()
        if missing:
            errors.append(f"row {index} missing {sorted(missing)}")
            continue
        if row["id"] in seen:
            errors.append(f"duplicate id {row['id']}")
        seen.add(row["id"])
        source_path = str(row["source"]).split("#", 1)[0]
        if source_path and not (repo / source_path).exists():
            errors.append(f"{row['id']} source not found: {source_path}")
        if row["hardware_policy"] not in {"required", "hardware_limited"}:
            errors.append(f"{row['id']} invalid hardware policy")
    return errors


def render_markdown(rows: list[dict]) -> str:
    header = "| ID | Area | Feature | Source | Scenario | Expected | Evidence |\n|---|---|---|---|---|---|---|"
    lines = [header]
    for row in rows:
        values = [str(row[key]).replace("|", "\\|") for key in (
            "id", "area", "feature", "source", "scenario", "expected", "evidence"
        )]
        lines.append("| " + " | ".join(values) + " |")
    return "# Production Readiness Acceptance Matrix\n\n" + "\n".join(lines) + "\n"
```

```python
# scripts/production_readiness/evidence.py
import json
from pathlib import Path

SENSITIVE_KEYS = {"authorization", "api_key", "password", "secret", "token", "transcript", "filename"}


def _redact(value):
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]"
            if any(marker in str(key).lower() for marker in SENSITIVE_KEYS)
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class EvidenceWriter:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, identifier: str, status: str, payload: dict) -> None:
        target = self.root / f"{kind}.jsonl"
        record = {"id": identifier, "status": status, "payload": _redact(payload)}
        with target.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
```

```python
# scripts/production_readiness/environment.py
import base64
import os
import secrets
import sys
from pathlib import Path


def write_readiness_environment(path: Path, project_name: str) -> None:
    postgres_password = secrets.token_urlsafe(32)
    minio_user = f"readiness-{secrets.token_hex(8)}"
    minio_password = secrets.token_urlsafe(32)
    values = {
        "APP_ENV": "production",
        "APP_SECRET_KEY": secrets.token_urlsafe(48),
        "CREDENTIAL_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii"),
        "CREDENTIAL_KEY_VERSION": "1",
        "BOOTSTRAP_ADMIN_EMAIL": "readiness-admin@example.test",
        "BOOTSTRAP_ADMIN_PASSWORD": secrets.token_urlsafe(32),
        "BOOTSTRAP_ORGANISATION_NAME": "Readiness Organisation",
        "BOOTSTRAP_ENABLED": "true",
        "POSTGRES_DB": "transcriber",
        "POSTGRES_USER": "transcriber",
        "POSTGRES_PASSWORD": postgres_password,
        "DATABASE_URL": f"postgresql+psycopg://transcriber:{postgres_password}@postgres:5432/transcriber",
        "REDIS_URL": "redis://redis:6379/0",
        "ALLOWED_ORIGINS": "https://localhost:8088",
        "MALWARE_SCANNER_MODE": "clamav",
        "POST_PROCESSING_PROVIDER": "llama_cpp_local",
        "EXTERNAL_APIS_ALLOWED": "false",
        "LOCAL_ONLY_ENFORCED": "true",
        "MINIO_ROOT_USER": minio_user,
        "MINIO_ROOT_PASSWORD": minio_password,
        "S3_ACCESS_KEY_ID": minio_user,
        "S3_SECRET_ACCESS_KEY": minio_password,
        "S3_BUCKET": "transcriber-readiness",
        "S3_ENDPOINT_URL": "http://minio:9000",
        "S3_PUBLIC_ENDPOINT_URL": "https://objects.localhost:8088",
        "COMPOSE_PROJECT_NAME": project_name,
    }
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()), encoding="utf-8")
    os.chmod(path, 0o600)


if __name__ == "__main__":
    write_readiness_environment(Path(sys.argv[1]), sys.argv[2])
```

Populate the JSON with at least one source-backed row for every endpoint/page/capability in `docs/03-api-contract.md`, `docs/04-frontend-page-map.md`, every phase exit gate in `docs/06-implementation-plan.md`, every security/operations requirement in `docs/07-security-and-privacy.md` and `docs/08-deployment.md`, every delivered/deferred/known-limitation item in `docs/14-implementation-status.md` and `docs/15-production-readiness-report.md`, plus each explicit user-required command and model/backup/reviewer criterion. IDs use the prefixes `BASE`, `AUTH`, `ADMIN`, `MEDIA`, `TRANS`, `DIAR`, `EDITOR`, `AI`, `REPORT`, `EXPORT`, `MODEL`, `PROVIDER`, `SEC`, `BACKUP`, `RECOVERY`, and `DOC` with zero-padded counters.

- [ ] **Step 4: Generate the Markdown matrix and verify deterministic output**

Run:

```bash
python -c "from pathlib import Path; from scripts.production_readiness.manifest import load_manifest,render_markdown; p=Path('scripts/production-readiness.matrix.json'); Path('docs/16-production-readiness-acceptance-matrix.md').write_text(render_markdown(load_manifest(p)), encoding='utf-8')"
cd backend && python -m pytest tests/test_production_readiness_manifest.py -q
```

Expected: PASS; rerunning generation leaves `git diff` unchanged.

- [ ] **Step 5: Ignore generated runtime evidence and commit**

Add `artifacts/production-readiness/` to `.gitignore`.

```bash
git add .gitignore scripts/__init__.py scripts/production-readiness.matrix.json scripts/production_readiness backend/tests/test_production_readiness_manifest.py docs/16-production-readiness-acceptance-matrix.md
git commit -m "test: define production readiness acceptance manifest"
```

### Task 2: Locked dependencies, test images, and pinned native runtimes

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/requirements.lock`
- Modify: `backend/Dockerfile`
- Modify: `frontend/package.json`
- Modify: `frontend/package-lock.json`
- Create: `frontend/Dockerfile`
- Create: `backend/tests/test_dependency_contract.py`

**Interfaces:**
- Produces optional extra `local-llm` containing `llama-cpp-python>=0.3.33,<0.4`.
- Produces Docker targets `api`, `worker`, and `test`; worker image contains `whisper-cli` from whisper.cpp commit `f049fff95a089aa9969deb009cdd4892b3e74916`.
- Produces frontend scripts `test:e2e` and `test:e2e:install`.
- Pins Python and frontend build bases to `python:3.12-slim@sha256:423ed6ab25b1921a477529254bfeeabf5855151dc2c3141699a1bfc852199fbf` and `node:22.23.1-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2`.

- [ ] **Step 1: Write failing dependency/worker-runtime contract tests**

```python
from pathlib import Path


def test_locked_runtime_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    project = (root / "backend/pyproject.toml").read_text()
    lock = (root / "backend/requirements.lock").read_text()
    dockerfile = (root / "backend/Dockerfile").read_text()
    assert 'local-llm = [' in project
    assert "llama-cpp-python==0.3.33" in lock
    assert "pip-audit==2.10.1" in lock
    assert "f049fff95a089aa9969deb009cdd4892b3e74916" in dockerfile
    assert "COPY --from=whispercpp /src/build/bin/whisper-cli /usr/local/bin/whisper-cli" in dockerfile
    assert "FROM worker AS test" in dockerfile
```

- [ ] **Step 2: Run the contract test and confirm missing dependency/runtime assertions**

Run: `cd backend && python -m pytest tests/test_dependency_contract.py -q`

Expected: FAIL on the first missing `local-llm` assertion.

- [ ] **Step 3: Add exact dependency ranges and frontend browser tooling**

Add to `backend/pyproject.toml`:

```toml
local-llm = [
  "llama-cpp-python>=0.3.33,<0.4",
]
```

Add `pip-audit>=2.10.1,<3.0` to `dev`. Add these frontend dev dependencies and scripts:

```json
{
  "scripts": {
    "test:e2e": "playwright test",
    "test:e2e:install": "playwright install --with-deps chromium"
  },
  "devDependencies": {
    "@axe-core/playwright": "^4.12.1",
    "@playwright/test": "^1.61.1"
  },
  "engines": { "node": ">=22.12.0" }
}
```

- [ ] **Step 4: Add pinned whisper.cpp and test Docker stages**

Use this stage before `base`:

```dockerfile
FROM debian:bookworm-slim AS whispercpp
RUN apt-get update && apt-get install -y --no-install-recommends build-essential cmake git ca-certificates
WORKDIR /src
RUN git clone https://github.com/ggml-org/whisper.cpp.git . \
    && git checkout f049fff95a089aa9969deb009cdd4892b3e74916 \
    && cmake -B build -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_EXAMPLES=ON \
    && cmake --build build --config Release -j2 --target whisper-cli
```

Copy `whisper-cli` into the worker, and add:

```dockerfile
FROM worker AS test
USER root
RUN pip install --no-cache-dir -c requirements.lock ".[dev,ai,storage,whisper-local]"
COPY backend/tests ./tests
COPY scripts ./scripts
USER appuser
CMD ["python", "-m", "pytest", "-q"]
```

Change the backend build context to the repository root. In `backend/Dockerfile`, copy `backend/pyproject.toml`, `backend/requirements.lock`, `backend/app`, `backend/alembic`, and `backend/alembic.ini` into `/app`; in Compose use `context: .` and `dockerfile: backend/Dockerfile` for API/worker builds.

Pin the runtime `FROM` line to the Python digest named above. Build the frontend test image from the pinned Node digest, use `npm ci`, and copy only lockfile-declared dependencies before source files so dependency layers are reproducible.

- [ ] **Step 5: Regenerate locks from declared dependencies**

Run:

```bash
docker run --rm -v "$PWD/backend:/work" -w /work python:3.12-slim sh -c "python -m pip install uv==0.11.28 && uv pip compile pyproject.toml --all-extras --system-certs --output-file requirements.lock"
docker run --rm -v "$PWD/frontend:/work" -w /work node:22-bookworm npm install --package-lock-only
```

Expected: both commands exit 0; `requirements.lock` contains exact `llama-cpp-python==0.3.33` and `pip-audit==2.10.1`; `package-lock.json` contains exact Playwright/Axe packages.

- [ ] **Step 6: Build runtime/test targets and commit**

Run:

```bash
docker build -f backend/Dockerfile --target worker -t transcriber-worker-plan-check .
docker build -f backend/Dockerfile --target test -t transcriber-test-plan-check .
docker run --rm transcriber-worker-plan-check whisper-cli --help
cd backend && python -m pytest tests/test_dependency_contract.py -q
```

Expected: all commands exit 0.

```bash
git add backend/pyproject.toml backend/requirements.lock backend/Dockerfile backend/tests/test_dependency_contract.py frontend/package.json frontend/package-lock.json frontend/Dockerfile
git commit -m "build: pin production AI and test runtimes"
```

### Task 3: Atomic managed downloads and immutable catalog metadata

**Files:**
- Modify: `backend/app/services/model_catalog.py`
- Modify: `backend/app/worker/model_tasks.py`
- Modify: `backend/app/api/routes/models.py`
- Modify: `backend/tests/test_model_manager.py`
- Create: `backend/tests/test_model_catalog_integrity.py`

**Interfaces:**
- Produces `DIRECT_FILE_ADAPTERS = {"whisper_cpp", "llama_cpp_local", "nemo_diarization"}`.
- Produces `_download_direct_file(catalog: ModelCatalog, target: Path, progress: Callable[[int], None]) -> Path`.
- Produces `_atomic_download_target(root: Path, item: InstalledModel) -> tuple[Path, Path]` returning staging/final directories.
- Catalog Qwen artifact: revision `bc640142c66e1fdd12af0bd68f40445458f3869b`, size `2497280256`, SHA-256 `7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5`.
- Catalog Sortformer artifact: revision `6dbf0d69730bfee097056692b86525a0a23b32f9`, size `471367680`, SHA-256 `b371afce2c4958186469df33d939936b9746c89f38b10a69cfd2c61254e83329`.

- [ ] **Step 1: Add failing catalog and atomic-download tests**

```python
def test_real_ai_and_diarisation_entries_are_immutable() -> None:
    by_key = {(e.adapter_key, e.model_identifier): e for e in CATALOG_ENTRIES}
    qwen = by_key[("llama_cpp_local", "Qwen/Qwen3-4B-GGUF")]
    assert qwen.revision == "bc640142c66e1fdd12af0bd68f40445458f3869b"
    assert qwen.size_bytes == 2497280256
    assert qwen.checksum == "sha256:7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5"
    diar = by_key[("nemo_diarization", "nvidia/diar_streaming_sortformer_4spk-v2")]
    assert diar.requirements["license"] == "cc-by-4.0"
    assert diar.checksum == "sha256:b371afce2c4958186469df33d939936b9746c89f38b10a69cfd2c61254e83329"
```

Add a download test that raises after writing half the bytes and asserts the final target does not exist, the staging directory is removed, and the row is failed/disabled.

- [ ] **Step 2: Run the tests and confirm missing catalog entries/atomic behavior**

Run: `cd backend && python -m pytest tests/test_model_catalog_integrity.py tests/test_model_manager.py -q`

Expected: FAIL because both catalog entries and atomic staging are absent.

- [ ] **Step 3: Add exact Qwen and Sortformer entries**

```python
CatalogEntry(
    adapter_key="llama_cpp_local",
    model_identifier="Qwen/Qwen3-4B-GGUF",
    name="Qwen3 4B Q4_K_M",
    model_type="post_processing",
    size_bytes=2_497_280_256,
    source_url="https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/bc640142c66e1fdd12af0bd68f40445458f3869b/Qwen3-4B-Q4_K_M.gguf",
    revision="bc640142c66e1fdd12af0bd68f40445458f3869b",
    requirements={"recommended_device": "cpu_or_cuda", "min_ram_bytes": 8_000_000_000, "download_backend": "direct_file", "python_dependencies": ["llama-cpp-python>=0.3.33"], "license": "apache-2.0"},
    capabilities={"tasks": ["clean", "translate", "summary", "minutes", "action_items", "topics", "entities", "qa"], "structured_output": True},
    checksum="sha256:7485fe6f11af29433bc51cab58009521f205840f5b4ae3a32fa7f92e8534fdf5",
),
CatalogEntry(
    adapter_key="nemo_diarization",
    model_identifier="nvidia/diar_streaming_sortformer_4spk-v2",
    name="NeMo Streaming Sortformer 4-Speaker v2",
    model_type="diarization",
    size_bytes=471_367_680,
    source_url="https://huggingface.co/nvidia/diar_streaming_sortformer_4spk-v2/resolve/6dbf0d69730bfee097056692b86525a0a23b32f9/diar_streaming_sortformer_4spk-v2.nemo",
    revision="6dbf0d69730bfee097056692b86525a0a23b32f9",
    requirements={"recommended_device": "cpu_or_cuda", "min_ram_bytes": 8_000_000_000, "download_backend": "direct_file", "python_dependencies": ["nemo_toolkit[asr]>=2.5.0", "torch>=2.6"], "license": "cc-by-4.0", "attribution": "NVIDIA Streaming Sortformer"},
    capabilities={"tasks": ["diarization"], "max_speakers": 4, "streaming": True},
    checksum="sha256:b371afce2c4958186469df33d939936b9746c89f38b10a69cfd2c61254e83329",
),
```

- [ ] **Step 4: Implement streamed progress and atomic promotion**

Download into `<final>.partial`, update persisted progress from bytes read/expected size, verify checksum in staging, then call `staging.replace(final)`. On cancellation/failure, remove staging and keep final untouched. Reject source URLs outside HTTPS except loopback test servers; use a 60-second connect/read timeout and `Content-Length` reconciliation.

```python
def _download_direct_file(catalog, target: Path, progress) -> Path:
    destination = target / (Path(urlparse(catalog.source_url).path).name or catalog.model_identifier)
    request = Request(catalog.source_url, headers={"User-Agent": "Transcriber/0.1"})
    with urlopen(request, timeout=60) as response, destination.open("wb") as handle:
        downloaded = 0
        while chunk := response.read(1024 * 1024):
            handle.write(chunk)
            downloaded += len(chunk)
            progress(downloaded)
    if catalog.size_bytes is not None and downloaded != catalog.size_bytes:
        raise ValueError("Downloaded model size does not match catalog metadata")
    return destination
```

- [ ] **Step 5: Make model tests task-aware**

Update `/installed-models/{id}/test` to dispatch transcription, `llama_cpp_local`, or `nemo_diarization` probes, and generalize `/task-defaults/{task}` for `transcription`, `post_processing`, and `diarization` while preserving the old transcription URL behavior.

- [ ] **Step 6: Run model tests and commit**

Run: `cd backend && python -m pytest tests/test_model_catalog_integrity.py tests/test_model_manager.py tests/test_model_routing.py -q`

Expected: all selected tests pass.

```bash
git add backend/app/services/model_catalog.py backend/app/worker/model_tasks.py backend/app/api/routes/models.py backend/tests/test_model_manager.py backend/tests/test_model_catalog_integrity.py
git commit -m "feat: make catalog model downloads atomic and verifiable"
```

### Task 4: Real local Qwen post-processing and translation

**Files:**
- Create: `backend/app/providers/post_processing_schemas.py`
- Create: `backend/app/providers/local_llm.py`
- Create: `backend/app/services/installed_models.py`
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/worker/post_processing_tasks.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/tests/test_post_processing.py`
- Modify: `backend/tests/test_ai_runs.py`
- Create: `backend/tests/test_local_llm.py`

**Interfaces:**
- Produces `task_schema(task: str, options: dict) -> dict`, `task_prompt(task: str, text: str, options: dict) -> list[dict]`, and `normalize_task_result(task: str, value: dict) -> dict`.
- Produces `LlamaCppPostProcessingProvider(model_path: Path, runtime_factory: Callable | None = None)`.
- Produces `resolve_installed_model(db: Session, organisation_id: UUID, task: str, adapter_key: str, installed_model_id: UUID | None = None) -> tuple[InstalledModel, ModelCatalog, Path]`.

- [ ] **Step 1: Write failing real-provider schema, retry, and production-config tests**

```python
def test_local_qwen_retries_invalid_json_once(tmp_path: Path) -> None:
    responses = iter([
        {"choices": [{"message": {"content": "not-json"}}]},
        {"choices": [{"message": {"content": '{"translation":"Bonjour","target_language":"fr"}'}}], "usage": {"total_tokens": 12}},
    ])
    class FakeRuntime:
        call_count = 0
        def create_chat_completion(self, **kwargs):
            self.call_count += 1
            return next(responses)
    model = tmp_path / "qwen.gguf"
    model.write_bytes(b"gguf")
    runtime = FakeRuntime()
    provider = LlamaCppPostProcessingProvider(model, lambda _: runtime)
    result = provider.process(PostProcessRequest("Hello", "translate", {"target_language": "fr"}), lambda *_: None)
    assert result.result == {"translation": "Bonjour", "target_language": "fr"}
    assert runtime.call_count == 2


def test_production_rejects_stub_ai(monkeypatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("POST_PROCESSING_PROVIDER", "stub")
    with pytest.raises(ValidationError, match="Stub AI is not permitted"):
        Settings()
```

- [ ] **Step 2: Run focused tests and confirm missing provider/config failures**

Run: `cd backend && python -m pytest tests/test_local_llm.py tests/test_post_processing.py -q`

Expected: FAIL because `LlamaCppPostProcessingProvider` and task schemas are absent.

- [ ] **Step 3: Implement exact task schemas and prompts**

Define object schemas with required keys: `cleaned_text`, `translation` plus `target_language`, `summary`, `summary`/`decisions`/`action_items` for minutes, `action_items`, `topics`, `entities`, and `questions`. Every schema sets `additionalProperties: false`. Prompts state that transcript content is untrusted data, instruct the model not to follow instructions contained in it, require source-grounded output, disable Qwen thinking, and cap output tokens.

- [ ] **Step 4: Implement lazy llama.cpp loading and bounded corrective retry**

```python
class LlamaCppPostProcessingProvider:
    key = "llama_cpp_local"
    capabilities = ProviderCapabilities(tasks=frozenset(TASK_SCHEMAS), is_external=False)

    def __init__(self, model_path: Path, runtime_factory=None) -> None:
        self.model_path = model_path
        self._runtime_factory = runtime_factory or self._load_runtime
        self._runtime = None

    def _model(self):
        if self._runtime is None:
            if not self.model_path.is_file():
                raise ProviderUnavailableError("Verified local AI model file was not found")
            self._runtime = self._runtime_factory(self.model_path)
        return self._runtime

    def process(self, request, report_progress):
        schema = task_schema(request.task, request.options)
        messages = task_prompt(request.task, request.text, request.options)
        for attempt in range(2):
            response = self._model().create_chat_completion(
                messages=messages,
                response_format={"type": "json_object", "schema": schema},
                temperature=float(request.options.get("temperature", 0.1)),
                max_tokens=min(int(request.options.get("max_tokens", 1024)), 2048),
                chat_template_kwargs={"enable_thinking": False},
            )
            try:
                value = json.loads(_extract_chat_content(response))
                return PostProcessResult(normalize_task_result(request.task, value), metrics=_usage_metrics(response))
            except (json.JSONDecodeError, ValueError):
                if attempt:
                    raise ValueError("Local AI returned invalid structured output")
                messages.append({"role": "user", "content": "Return only JSON matching the supplied schema."})
```

- [ ] **Step 5: Resolve only verified enabled task-default models in worker tasks**

`resolve_installed_model` must scope by organisation, require status `installed`, `enabled=True`, non-null `storage_key`/`verified_at`, compatible hardware, root confinement, and an existing file. For a supplied `installed_model_id`, require that exact model; otherwise resolve the organisation's `ModelTaskDefault` for the task. `_resolve_post_processing_provider` passes `run.execution_target_id` for `local_model` runs and resolves the post-processing default for `automatic` runs. `generate_report` resolves the report organisation's post-processing default through the same function. Remove production registry registration of `StubPostProcessingProvider`; tests inject their fake explicitly.

- [ ] **Step 6: Run AI suites and commit**

Run: `cd backend && python -m pytest tests/test_local_llm.py tests/test_post_processing.py tests/test_ai_runs.py tests/test_reports_api.py -q`

Expected: all selected tests pass and no local production path returns `[stub:`.

```bash
git add backend/app/providers/post_processing_schemas.py backend/app/providers/local_llm.py backend/app/services/installed_models.py backend/app/providers/registry.py backend/app/worker/post_processing_tasks.py backend/app/core/config.py backend/tests/test_local_llm.py backend/tests/test_post_processing.py backend/tests/test_ai_runs.py
git commit -m "feat: run AI and translation through local Qwen"
```

### Task 5: Real NeMo acoustic diarisation

**Files:**
- Modify: `backend/app/providers/diarization.py`
- Modify: `backend/app/worker/tasks.py`
- Modify: `backend/app/schemas/jobs.py`
- Modify: `backend/tests/test_diarization.py`
- Create: `backend/tests/test_nemo_diarization.py`

**Interfaces:**
- Produces `NemoSortformerDiarizationProvider(settings: Settings, model_path: Path, loader: Callable | None = None)`.
- Produces `normalize_sortformer_segments(value: object) -> list[DiarizationSegmentResult]`.
- `build_diarization_provider("nemo_sortformer", settings, model_path)` returns only the real provider; synthetic turn assignment remains a test fake outside production code.

- [ ] **Step 1: Add failing acoustic-result and no-synthetic-default tests**

```python
def test_sortformer_normalizes_real_segments(tmp_path: Path) -> None:
    class FakeModules:
        chunk_len = chunk_right_context = fifo_len = spkcache_update_period = 0
    class FakeSortformer:
        sortformer_modules = FakeModules()
        def eval(self):
            return self
        def diarize(self, **kwargs):
            return [["0.08 1.20 speaker_0", "1.28 2.40 speaker_1"]]
    model = tmp_path / "model.nemo"
    model.write_bytes(b"nemo")
    provider = NemoSortformerDiarizationProvider(Settings(), model, lambda *_: FakeSortformer())
    result = provider.diarize(DiarizationRequest(tmp_path / "two-speaker.wav", 2400, {}), lambda *_: None)
    assert [(s.start_ms, s.end_ms, s.speaker_label) for s in result.segments] == [
        (80, 1200, "S1"), (1280, 2400, "S2")
    ]


def test_default_diarization_provider_is_not_fixed_turns() -> None:
    assert normalize_job_options({"diarization": {"enabled": True}})["diarization"]["provider"] == "nemo_sortformer"
```

- [ ] **Step 2: Run tests and confirm current fixed-turn failure**

Run: `cd backend && python -m pytest tests/test_nemo_diarization.py tests/test_diarization.py -q`

Expected: FAIL because the real provider is absent and the default is `local_turns`.

- [ ] **Step 3: Implement local checkpoint loading and segment normalization**

Load `SortformerEncLabelModel.restore_from(restore_path=str(model_path), map_location=device, strict=False)`, call `eval()`, configure documented streaming parameters (`chunk_len=340`, `chunk_right_context=40`, `fifo_len=40`, `spkcache_update_period=300`), and invoke `diarize(audio=[str(media_path)], batch_size=1)`. Normalize string/tuple outputs, reject negative/reversed intervals, merge adjacent same-speaker segments, and assign stable `S1`–`S4` labels in arrival order.

- [ ] **Step 4: Resolve the verified diarisation model before transcription execution**

Use `resolve_installed_model(db, job.organisation_id, task="diarization", adapter_key="nemo_diarization", installed_model_id=None)` whenever diarisation is enabled. A missing/incompatible model produces stable `diarization_model_unavailable`; there is no synthetic fallback. Preserve overlap-based label assignment and speaker persistence already covered by `test_diarization.py`.

- [ ] **Step 5: Run diarisation/transcription suites and commit**

Run: `cd backend && python -m pytest tests/test_nemo_diarization.py tests/test_diarization.py tests/test_media_derivatives.py tests/test_model_routing.py -q`

Expected: all selected tests pass.

```bash
git add backend/app/providers/diarization.py backend/app/worker/tasks.py backend/app/schemas/jobs.py backend/tests/test_diarization.py backend/tests/test_nemo_diarization.py
git commit -m "feat: replace synthetic turns with NeMo diarisation"
```

### Task 6: Production configuration, queue topology, object storage profile, and health

**Files:**
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/worker/celery_app.py`
- Modify: `backend/app/api/routes/operations.py`
- Modify: `backend/app/storage/s3.py`
- Modify: `backend/app/services/storage_factory.py`
- Modify: `docker-compose.yml`
- Modify: `.env.example`
- Modify: `infra/caddy/Caddyfile`
- Modify: `infra/caddy/Dockerfile`
- Modify: `backend/tests/test_celery_config.py`
- Modify: `backend/tests/test_worker_container.py`
- Modify: `backend/tests/test_operational_hardening.py`
- Create: `backend/tests/test_production_config.py`

**Interfaces:**
- Produces health response `{"status":"ready","checks":{"database":"ok","redis":"ok","storage":"ok","ffmpeg":"ok","workers":"ok","local_ai_model":"ok"}}`.
- Produces queues `media`, `maintenance`, `transcription.cpu`, `transcription.gpu`, `exports`, `postprocess`, and `model_downloads`.
- Produces CPU-profile services `worker-cpu` and `worker-ai`, GPU-profile `worker-gpu`, object-storage profile `minio`/`minio-init`, and clamav profile.
- Produces `BOOTSTRAP_ENABLED`; readiness is degraded until the one-time bootstrap is disabled and credentials are removed.
- Produces separate internal `S3_ENDPOINT_URL` and browser-visible `S3_PUBLIC_ENDPOINT_URL`; presigned URLs use the dedicated Caddy `objects.localhost` host while service operations use the internal MinIO endpoint.
- Pins Compose/Caddy images to immutable digests: PostgreSQL `57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`, Redis `6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99`, ClamAV `6f4a9e7d616ffc8d1070200fe35ac860735fdd522161a1043f94856e6ee13c28`, Caddy `5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648`, MinIO `14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`, and MinIO Client `a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727`.

- [ ] **Step 1: Add failing production-safety and topology tests**

```python
@pytest.mark.parametrize("name,value,message", [
    ("ALLOWED_ORIGINS", "*", "Wildcard origins"),
    ("MALWARE_SCANNER_MODE", "placeholder", "real malware scanner"),
    ("POST_PROCESSING_PROVIDER", "stub", "Stub AI"),
])
def test_production_rejects_unsafe_configuration(monkeypatch, name, value, message):
    for key, safe in {
        "APP_ENV": "production",
        "APP_SECRET_KEY": "a" * 64,
        "CREDENTIAL_ENCRYPTION_KEY": "b" * 64,
        "DATABASE_URL": "postgresql+psycopg://user:pass@postgres/db",
        "REDIS_URL": "redis://redis:6379/0",
        "ALLOWED_ORIGINS": "https://transcriber.example.test",
        "MALWARE_SCANNER_MODE": "clamav",
        "POST_PROCESSING_PROVIDER": "llama_cpp_local",
    }.items():
        monkeypatch.setenv(key, safe)
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match=message):
        Settings()
```

Compose tests assert worker-ai concurrency one/read-only model mount, CPU worker advanced-speech dependencies, model-download queue routing, healthchecks for all long-running services, no public PostgreSQL/Redis/MinIO ports, and non-root API/worker containers.

- [ ] **Step 2: Run focused tests and confirm unsafe defaults/topology failures**

Run: `cd backend && python -m pytest tests/test_production_config.py tests/test_celery_config.py tests/test_worker_container.py tests/test_operational_hardening.py -q`

Expected: FAIL on missing production validators and worker-ai/profile assertions.

- [ ] **Step 3: Implement production validators and sanitized readiness checks**

In `Settings.reject_placeholder_secrets_in_production`, also reject empty/wildcard origins, `malware_scanner_mode=placeholder`, `post_processing_provider=stub`, `BOOTSTRAP_ENABLED=true` without both bootstrap credentials, credentials present when bootstrap is disabled, and incomplete S3 configuration. Initial startup may run with bootstrap enabled; after first login the gate restarts API/workers with `BOOTSTRAP_ENABLED=false` and both bootstrap credential variables removed. Only then may readiness return `ready`. Readiness catches dependency exceptions and returns HTTP 503 with check names/error types only; liveness remains dependency-free.

- [ ] **Step 4: Separate queues and add worker/profile services**

Route `run_ai_processing` and `generate_report` to `postprocess`, model downloads/deletes to `model_downloads`, and keep export rendering on `exports`. Configure worker-cpu with `WORKER_EXTRAS=ai,advanced-speech,whisper-local,storage` and queues `media,maintenance,transcription.cpu,exports,model_downloads`; configure worker-ai with `WORKER_EXTRAS=ai,local-llm` and `postprocess --concurrency=1` plus read-only model storage.

Replace hard-coded PostgreSQL credentials with required `${POSTGRES_DB}`, `${POSTGRES_USER}`, and `${POSTGRES_PASSWORD}` substitutions supplied by the generated readiness environment.

Use these exact image references in Compose: `postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`, `redis:7-alpine@sha256:6ab0b6e7381779332f97b8ca76193e45b0756f38d4c0dcda72dbb3c32061ab99`, `clamav/clamav:stable@sha256:6f4a9e7d616ffc8d1070200fe35ac860735fdd522161a1043f94856e6ee13c28`, `minio/minio:RELEASE.2025-09-07T16-13-09Z@sha256:14cea493d9a34af32f524e538b8346cf79f3321eff8e708c1e2960462bd8936e`, and `minio/mc:RELEASE.2025-08-13T08-35-41Z@sha256:a7fe349ef4bd8521fb8497f55c6042871b2ae640607cf99d9bede5e9bdf11727`. Add MinIO only under `object-storage`; `minio-init` creates the private bucket and lifecycle configuration. The gate sets `STORAGE_PROVIDER=s3_compatible` and the internal/public endpoints when exercising this profile.

In `infra/caddy/Dockerfile`, pin `node:22.23.1-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2` and `caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648`, copy `package-lock.json`, and replace `npm install` with `npm ci`.

Configure Caddy for internal TLS on port 8080, route the dedicated `objects.localhost` host to MinIO without rewriting its signed bucket/key path, and publish only `8088:8080`. `S3CompatibleStorage` uses its internal client for reads/writes and a public-endpoint client for signature generation so browser downloads retain a valid host/path signature. The readiness gate proves `objects.localhost` resolution before running signed-download tests.

- [ ] **Step 5: Validate Compose/build/health contracts and commit**

Run:

```bash
docker compose config --quiet
docker compose --profile cpu --profile clamav config --quiet
docker compose --profile object-storage config --quiet
cd backend && python -m pytest tests/test_production_config.py tests/test_celery_config.py tests/test_worker_container.py tests/test_operational_hardening.py -q
```

Expected: all commands exit 0.

```bash
git add backend/app/core/config.py backend/app/main.py backend/app/worker/celery_app.py backend/app/api/routes/operations.py backend/app/storage/s3.py backend/app/services/storage_factory.py docker-compose.yml .env.example infra/caddy/Caddyfile infra/caddy/Dockerfile backend/tests/test_production_config.py backend/tests/test_celery_config.py backend/tests/test_worker_container.py backend/tests/test_operational_hardening.py
git commit -m "feat: harden production topology and readiness"
```

### Task 7: Effective-permission sessions and frontend route guards

**Files:**
- Modify: `backend/app/schemas/auth.py`
- Modify: `backend/app/api/routes/auth.py`
- Modify: `frontend/src/types.ts`
- Create: `frontend/src/components/PermissionRoute.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/PermissionRoute.test.tsx`
- Modify: `backend/tests/test_routes_smoke.py`

**Interfaces:**
- `MembershipSummary.permission_codes: list[str]` is sorted and organisation-specific.
- `<PermissionRoute session permission>{children}</PermissionRoute>` renders children only for an active membership containing the permission; otherwise renders an accessible denial and link home.

- [ ] **Step 1: Add failing session-permission and route-guard tests**

```tsx
it("blocks a direct navigation without the required permission", () => {
  const session: Session = {
    user: { id: "user-1", email: "reader@example.test", display_name: "Reader", is_active: true, last_login_at: null },
    memberships: [{ organisation_id: "org-1", role_code: "read_only_user", status: "active", permission_codes: ["transcripts.read"] }],
    csrf_token: "csrf",
  };
  render(<MemoryRouter><PermissionRoute session={session} permission="models.manage"><p>Models</p></PermissionRoute></MemoryRouter>);
  expect(screen.queryByText("Models")).toBeNull();
  expect(screen.getByRole("alert").textContent).toContain("permission");
});
```

Backend smoke assertion: every membership in `/auth/me` includes its exact sorted permission codes, and switching `X-Organisation-ID` changes effective codes.

- [ ] **Step 2: Run focused backend/frontend tests and confirm missing fields/guard**

Run:

```bash
cd backend && python -m pytest tests/test_routes_smoke.py -q
cd ../frontend && npm test -- PermissionRoute.test.tsx
```

Expected: both focused suites fail for the new behavior.

- [ ] **Step 3: Add permission codes to session responses and guard every route**

Query `Permission.code` through `role_permissions` for each membership. Replace role-code navigation checks with permission checks. Wrap every documented route in its matching permission from `docs/04-frontend-page-map.md`; `/help` remains authenticated. API authorization remains authoritative.

- [ ] **Step 4: Run frontend/backend suites and commit**

Run:

```bash
cd backend && python -m pytest tests/test_routes_smoke.py tests/test_roles_admin.py -q
cd ../frontend && npm test
npm run lint
```

Expected: all commands exit 0.

```bash
git add backend/app/schemas/auth.py backend/app/api/routes/auth.py backend/tests/test_routes_smoke.py frontend/src/types.ts frontend/src/components/PermissionRoute.tsx frontend/src/PermissionRoute.test.tsx frontend/src/App.tsx
git commit -m "feat: enforce permission-aware frontend routes"
```

### Task 8: Complete backup/restore with storage manifests and reconciliation

**Files:**
- Modify: `scripts/backup.ps1`
- Modify: `scripts/restore.ps1`
- Modify: `scripts/backup-postgres.sh`
- Modify: `scripts/restore-postgres.sh`
- Modify: `scripts/restore-smoke.sh`
- Create: `scripts/storage-manifest.py`
- Create: `backend/tests/test_backup_restore_scripts.py`
- Modify: `docs/11-deployment-runbook.md`

**Interfaces:**
- `storage-manifest.py create ROOT OUTPUT` writes sorted `{path,size,sha256}` entries with root confinement.
- `storage-manifest.py verify ROOT MANIFEST` exits 0 only when every expected object matches and no unexpected object exists.
- Backup scripts accept `STORAGE_ROOT`/`BACKUP_STORAGE_ARCHIVE`; restore scripts accept `RESTORE_STORAGE_ROOT` and verify before returning.

- [ ] **Step 1: Add failing script-contract and traversal tests**

```python
def test_storage_manifest_round_trip_and_rejects_symlinks(tmp_path: Path) -> None:
    storage = tmp_path / "storage"
    storage.mkdir()
    (storage / "asset.bin").write_bytes(b"asset")
    manifest = tmp_path / "manifest.json"
    run_script("create", storage, manifest)
    run_script("verify", storage, manifest)
    (storage / "asset.bin").write_bytes(b"tampered")
    assert run_script("verify", storage, manifest, check=False).returncode == 1
```

- [ ] **Step 2: Run tests and confirm missing storage-manifest failure**

Run: `cd backend && python -m pytest tests/test_backup_restore_scripts.py -q`

Expected: FAIL because `scripts/storage-manifest.py` is absent.

- [ ] **Step 3: Implement deterministic manifest creation/verification**

Use SHA-256 streaming in 1 MiB chunks, reject symlinks/non-regular files, normalize paths to POSIX relative keys, and write canonical JSON with sorted keys. Never store absolute paths.

- [ ] **Step 4: Extend PowerShell/shell backup and restore symmetrically**

Create a tar archive of storage plus the manifest next to the PostgreSQL custom dump. Restore into an explicitly supplied empty directory, verify the manifest, then run `pg_restore`. Refuse `/`, an existing non-empty directory, or source/target database URL equality.

- [ ] **Step 5: Run an isolated PostgreSQL/storage restore drill and commit**

Run:

```bash
docker compose -p transcriber-restore-plan up -d postgres
docker run --rm --network transcriber-restore-plan_internal -v "$PWD:/repo" -w /repo -e DATABASE_URL=postgresql://transcriber:transcriber@postgres:5432/transcriber_restore_source -e RESTORE_DATABASE_URL=postgresql://transcriber:transcriber@postgres:5432/transcriber_restore_target postgres:16-alpine sh scripts/restore-smoke.sh
docker compose -p transcriber-restore-plan down -v
```

Expected: exit 0 and output `Restore smoke test passed`; the script verifies database row value and storage SHA-256.

```bash
git add scripts/backup.ps1 scripts/restore.ps1 scripts/backup-postgres.sh scripts/restore-postgres.sh scripts/restore-smoke.sh scripts/storage-manifest.py backend/tests/test_backup_restore_scripts.py docs/11-deployment-runbook.md
git commit -m "feat: verify database and storage backup restoration"
```

### Task 9: PostgreSQL/Redis/Celery integration acceptance tests

**Files:**
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_identity_admin_flow.py`
- Create: `backend/tests/integration/test_media_transcription_flow.py`
- Create: `backend/tests/integration/test_ai_reports_exports_flow.py`
- Create: `backend/tests/integration/test_storage_retention_recovery.py`
- Modify: `backend/pyproject.toml`

**Interfaces:**
- Pytest marker `integration` requires `READINESS_DATABASE_URL`, `REDIS_URL`, and `READINESS_BASE_URL`.
- Fixtures create two organisations and all six seeded roles, use unique resource names, and remove only their own records/artifacts.

- [ ] **Step 1: Add failing real-dependency health and isolation tests**

```python
@pytest.mark.integration
def test_real_postgres_redis_and_worker_are_available(readiness_client, redis_client):
    assert readiness_client.get("/health/ready").json()["status"] == "ready"
    assert redis_client.ping() is True
    health = readiness_client.get("/api/v1/operations/worker-health").json()
    assert health["database"]["status"] == "ok"
    assert health["queue_backend"]["status"] == "ok"
    assert health["workers"]["count"] >= 2
```

- [ ] **Step 2: Run against clean Compose resources and confirm missing test harness**

Run:

```bash
python3 -m scripts.production_readiness.environment .env.readiness transcriber-plan-it
docker compose -p transcriber-plan-it --env-file .env.readiness --profile cpu up -d postgres redis api worker-cpu worker-ai caddy
docker build -f backend/Dockerfile --target test -t transcriber-test-plan-check .
docker run --rm --network transcriber-plan-it_internal --env-file .env.readiness transcriber-test-plan-check python -m pytest tests/integration -m integration -q
```

Expected: FAIL because the integration files/fixtures do not exist in the test image.

- [ ] **Step 3: Implement real flows without task mocks**

Cover authentication/refresh/logout/CSRF/rate limits, all six roles and tenant denials, projects/users/roles/providers/settings/storage/audit, upload/quarantine/metadata/derivatives, cancellation/retry/worker restart, transcript edits/version conflicts/search/speakers, Qwen AI tasks, reports/templates, all export formats/download authorization, MinIO signed URLs, retention/legal hold, external fake provider consent/local-only block/usage/redaction, and stable failure codes. Poll background resources with bounded deadlines; never call Celery task `.run()` in this suite.

- [ ] **Step 4: Run integration suite and commit**

Run: `docker build -f backend/Dockerfile --target test -t transcriber-test-plan-check . && docker run --rm --network transcriber-plan-it_internal --env-file .env.readiness transcriber-test-plan-check python -m pytest tests/integration -m integration -q`

Expected: all integration tests pass against PostgreSQL/Redis/real workers.

```bash
git add backend/tests/integration backend/pyproject.toml
git commit -m "test: cover real service integration flows"
```

### Task 10: Playwright browser acceptance and accessibility

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/fixtures.ts`
- Create: `frontend/e2e/auth-rbac.spec.ts`
- Create: `frontend/e2e/transcription-editor.spec.ts`
- Create: `frontend/e2e/ai-reports-exports.spec.ts`
- Create: `frontend/e2e/administration.spec.ts`
- Create: `frontend/e2e/accessibility.spec.ts`
- Create: `scripts/generate-fixture-media.sh`
- Modify: `backend/Dockerfile`

**Interfaces:**
- `readinessTest` Playwright fixture authenticates through the UI and returns CSRF/session context only through browser state.
- Media generator creates `artifacts/production-readiness/fixtures/single-speaker.wav`, `two-speaker.wav`, and `two-speaker.mp4` using `espeak-ng` plus FFmpeg; no binary fixture is committed.

- [ ] **Step 1: Add failing browser login and direct-route RBAC specs**

```typescript
test("read-only user cannot open model administration", async ({ page }) => {
  await loginAs(page, users.readOnly);
  await page.goto("/models");
  await expect(page.getByRole("alert")).toContainText("permission");
  await expect(page.getByRole("navigation").getByText("Models")).toHaveCount(0);
});
```

- [ ] **Step 2: Install Chromium and confirm the new spec initially fails**

Run:

```bash
docker run --rm -v "$PWD/frontend:/work" -w /work mcr.microsoft.com/playwright:v1.61.1-noble bash -lc "npm ci && npm run test:e2e -- --project=chromium e2e/auth-rbac.spec.ts"
```

Expected: FAIL until Playwright configuration/seed users are wired to the live stack.

- [ ] **Step 3: Generate deterministic speech/video fixtures**

Install `espeak-ng` in the test image. Generate two mono 16 kHz voices, concatenate alternating turns for the diarisation fixture, and mux the audio with a generated color video. Record fixture SHA-256 values in the evidence bundle at runtime.

- [ ] **Step 4: Implement browser flows for every documented page**

Exercise login feedback, upload/advanced selection/progress, assets/projects/jobs/events/cancel/retry, transcript playback/search/edit/split/merge/annotation/version restore/speakers, Qwen summary/translation and invalid-state UI, reports/templates, nine exports/downloads, organisations/users/roles/models/providers/audit/storage/settings/help, responsive navigation, confirmations, secret-field behavior, and safe error request IDs.

- [ ] **Step 5: Add Axe checks and keyboard paths**

Run Axe on every top-level route with zero serious/critical violations. Verify keyboard login, navigation, player play/pause, segment next/previous, split/merge, speaker assignment, annotation, and dialog focus restoration.

- [ ] **Step 6: Run browser suite and commit**

Run: `docker run --rm --network host -v "$PWD/frontend:/work" -w /work mcr.microsoft.com/playwright:v1.61.1-noble bash -lc "npm ci && npm run test:e2e"`

Expected: all Chromium projects pass against `https://localhost:8088` with Playwright `ignoreHTTPSErrors: true`; traces/screenshots are retained on failure only.

```bash
git add frontend/playwright.config.ts frontend/e2e scripts/generate-fixture-media.sh backend/Dockerfile frontend/package.json frontend/package-lock.json
git commit -m "test: exercise complete browser acceptance flows"
```

### Task 11: Dynamic catalog download and inference runner

**Files:**
- Create: `scripts/production_readiness/http_client.py`
- Create: `scripts/production_readiness/model_flow.py`
- Create: `backend/tests/test_model_readiness_runner.py`
- Modify: `backend/app/api/routes/models.py`
- Modify: `backend/app/providers/whisper_cpp.py`
- Modify: `backend/app/providers/hf_speech.py`
- Modify: `backend/app/providers/local_whisper.py`

**Interfaces:**
- Produces `run_catalog_flow(base_url: str, evidence: EvidenceWriter, fixture: Path, timeout_seconds: int) -> list[dict]`.
- Model API exposes a sanitized artifact manifest with relative paths, sizes, and computed checksums; inference is exercised through normal transcription/AI/diarisation job workflows rather than a privileged filesystem-path test hook.
- Each result has `adapter_key`, `model_identifier`, `download_status`, `artifact_paths`, `actual_bytes`, `checksum_status`, `load_status`, `inference_status`, `hardware_reason`, and `duration_ms`.

- [ ] **Step 1: Add failing dynamic-enumeration and hardware-policy tests**

```python
def test_runner_uses_api_catalog_without_static_model_names(fake_api, tmp_path):
    fake_api.catalog = [{"id": "catalog-1", "adapter_key": "new_adapter", "model_identifier": "new/model", "requirements": {}, "checksum": None}]
    results = run_catalog_flow(fake_api.base_url, EvidenceWriter(tmp_path), tmp_path / "fixture.wav", 60)
    assert [(r["adapter_key"], r["model_identifier"]) for r in results] == [("new_adapter", "new/model")]


def test_hardware_limited_requires_successful_download_and_declared_requirement():
    assert classify_inference({"download_status": "passed", "requirements": {"requires_cuda": True}}, {"has_cuda": False}) == "hardware_limited"
    with pytest.raises(ValueError):
        classify_inference({"download_status": "failed", "requirements": {"requires_cuda": True}}, {"has_cuda": False})
```

- [ ] **Step 2: Run tests and confirm missing runner**

Run: `cd backend && python -m pytest tests/test_model_readiness_runner.py -q`

Expected: FAIL because the runner does not exist.

- [ ] **Step 3: Implement authenticated catalog lifecycle polling**

Log in, fetch `/model-catalog`, assert exact equality with an application-side `CATALOG_ENTRIES` export endpoint available only to `models.manage`, create/install each model, queue download, poll until terminal, inspect server-reported relative artifacts/checksum/bytes, enable, call the model-test probe, set task default where applicable, prove disabled/deleted models cannot route, then restore installed/enabled state needed by later acceptance flows.

- [ ] **Step 4: Make probes perform real minimal inference**

Use the generated short speech fixture. Faster-Whisper, Whisper, whisper.cpp, Granite, and any other non-CUDA-required runtime must attempt actual load/inference by creating a normal local-model transcription job and polling it to completion. CUDA-required Canary, Parakeet, and Qwen3-ASR still download/checksum; only the hardware probe may classify their inference `hardware_limited`. Qwen GGUF must produce a real summary and translation through `/ai-runs`. Sortformer must return at least two acoustic speakers through a diarisation-enabled transcription job using the generated two-voice fixture.

- [ ] **Step 5: Run runner unit tests and commit**

Run: `cd backend && python -m pytest tests/test_model_readiness_runner.py tests/test_model_manager.py tests/test_hf_speech_providers.py -q`

Expected: all selected tests pass.

```bash
git add scripts/production_readiness/http_client.py scripts/production_readiness/model_flow.py backend/tests/test_model_readiness_runner.py backend/app/api/routes/models.py backend/app/providers/whisper_cpp.py backend/app/providers/hf_speech.py backend/app/providers/local_whisper.py
git commit -m "test: verify every catalog model through the application"
```

### Task 12: API flow runner, backup/recovery drill, and acceptance result mapping

**Files:**
- Create: `scripts/production_readiness/api_flow.py`
- Create: `scripts/production_readiness/recovery_flow.py`
- Create: `backend/tests/test_readiness_api_flow.py`

**Interfaces:**
- Produces `run_api_flow(base_url: str, evidence: EvidenceWriter, fixtures: Path) -> dict[str, str]` keyed by acceptance ID.
- Produces `run_recovery_flow(compose_project: str, evidence: EvidenceWriter) -> dict[str, str]`.

- [ ] **Step 1: Add failing completeness/result tests**

```python
def test_api_flow_returns_only_manifest_ids(manifest_rows, fake_flow_dependencies):
    results = run_api_flow(fake_flow_dependencies.base_url, fake_flow_dependencies.evidence, fake_flow_dependencies.fixtures)
    allowed = {row["id"] for row in manifest_rows}
    assert set(results) <= allowed
    assert all(value in {"passed", "failed", "hardware_limited"} for value in results.values())
```

- [ ] **Step 2: Run and confirm missing flow modules**

Run: `cd backend && python -m pytest tests/test_readiness_api_flow.py -q`

Expected: FAIL because API/recovery runners are absent.

- [ ] **Step 3: Implement API scenario mapping**

Implement every non-browser-only manifest scenario with typed helper methods, bounded polling, resource IDs, exact assertions, and an evidence record per acceptance ID. Never mark a criterion from route existence alone.

- [ ] **Step 4: Implement destructive recovery only in isolated Compose resources**

Kill worker-cpu during a running fixture job, restart it, and prove idempotent retry/attempt history. Restart Redis/PostgreSQL/API and prove readiness recovery. Corrupt a staged model download and prove atomic rejection. Run retention with/without legal hold. Backup database/storage, mutate isolated data, restore, and compare row/object/checksum counts.

- [ ] **Step 5: Run flow tests and commit**

Run: `cd backend && python -m pytest tests/test_readiness_api_flow.py -q`

Expected: all selected tests pass.

```bash
git add scripts/production_readiness/api_flow.py scripts/production_readiness/recovery_flow.py backend/tests/test_readiness_api_flow.py
git commit -m "test: map full API and recovery acceptance evidence"
```

### Task 13: Single PowerShell production-readiness gate

**Files:**
- Create: `scripts/production-readiness.ps1`
- Create: `backend/tests/test_production_readiness_gate.py`

**Interfaces:**
- Default invocation is exactly `powershell -ExecutionPolicy Bypass -File .\scripts\production-readiness.ps1`.
- Exit 0 requires all blocking criteria passed and every required command exit 0.
- Evidence root is `artifacts/production-readiness/$runId/`, where `$runId = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")`.
- Security tools are pinned to Syft `v1.46.0`, Trivy `v0.72.0`, and Gitleaks `v8.30.1`.

- [ ] **Step 1: Add failing static gate-contract tests**

```python
def test_gate_contains_every_required_command() -> None:
    script = Path("../scripts/production-readiness.ps1").read_text()
    for command in (
        "python -m pip check", "python -m ruff check .", "python -m pytest -q",
        "npm ci", "npm test", "npm run lint", "npm run build",
        "npm audit --audit-level=high", "docker compose config",
        "alembic upgrade head", "/health/live", "/health/ready",
    ):
        assert command in script
    assert "$failedCriteria.Count -eq 0" in script
    assert "exit 0" in script
```

- [ ] **Step 2: Run test and confirm missing script failure**

Run: `cd backend && python -m pytest tests/test_production_readiness_gate.py -q`

Expected: FAIL because the gate script is absent.

- [ ] **Step 3: Implement strict command/evidence orchestration**

```powershell
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-GateStep {
    param([string]$Id, [string]$WorkingDirectory, [string]$Executable, [string[]]$Arguments)
    $log = Join-Path $script:EvidenceRoot ("commands/{0}.log" -f $Id)
    New-Item -ItemType Directory -Force -Path (Split-Path $log) | Out-Null
    Push-Location $WorkingDirectory
    try {
        & $Executable @Arguments 2>&1 | Tee-Object -FilePath $log
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    $script:CommandResults += [pscustomobject]@{ id = $Id; command = "$Executable $($Arguments -join ' ')"; exit_code = $code; log = $log }
    if ($code -ne 0) { throw "Gate step $Id failed with exit code $code" }
}
```

Generate strong ephemeral secrets without printing them, write `.env.readiness` with mode 0600, create a unique Compose project/volumes, and record a sanitized config. Use the immutable Python 3.12 and Node 22 images from Task 2 when host runtimes are absent, while logs retain the literal required commands executed inside them. Before builds/downloads, sum `size_bytes` dynamically from `CATALOG_ENTRIES`, add 25 GiB for images/staging/evidence, and fail before mutation if the Docker/model filesystem lacks that free capacity.

- [ ] **Step 4: Orchestrate every required gate phase**

Run manifest/large-file/secret validation; locked backend install, `python -m pip check`, `python -m pip_audit`, `python -m ruff check .`, and `python -m pytest -q`; `npm ci`, `npm test`, `npm run lint`, `npm run build`, and `npm audit --audit-level=high`; `docker compose config --quiet`, profile validation, `docker compose build`, and pinned Trivy/Syft/Gitleaks checks; clean PostgreSQL `alembic upgrade head`; stack/container/worker/HTTPS health checks using certificate-aware probes; integration/API/Playwright flows; backup/recovery; clean model downloads/inference; final manifest coverage. Write `summary.json`/`summary.md` in a `finally` block and clean secrets/containers safely.

- [ ] **Step 5: Run static gate tests and a preflight-only syntax invocation**

Run:

```bash
cd backend && python -m pytest tests/test_production_readiness_gate.py -q
pwsh -NoProfile -Command "[scriptblock]::Create((Get-Content -Raw ../scripts/production-readiness.ps1)) | Out-Null"
```

Expected: both commands exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/production-readiness.ps1 backend/tests/test_production_readiness_gate.py
git commit -m "feat: add single production readiness gate"
```

### Task 14: Documentation, CI alignment, three full iterations, and independent review

**Files:**
- Modify: `README.md`
- Modify: `CONTRIBUTING.md`
- Modify: `docs/08-deployment.md`
- Modify: `docs/11-deployment-runbook.md`
- Modify: `docs/14-implementation-status.md`
- Modify: `docs/15-production-readiness-report.md`
- Create: `docs/model-management.md`
- Create: `docs/incident-response.md`
- Create: `docs/upgrade-rollback.md`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Documentation names the exact full gate, local Qwen/Sortformer licenses/attribution, CPU/GPU limitations, model installation, backup/restore, incident rotation/disablement, upgrade/rollback, and evidence interpretation.
- CI verifies locks, unit/integration-static suites, manifest generation, Compose config/build, browser tests, dependency/secret/SBOM checks; the heavyweight all-model gate remains the release-host gate.

- [ ] **Step 1: Write failing documentation contract tests**

Extend `backend/tests/test_production_readiness_gate.py` to assert each required document exists and contains the exact PowerShell command, `Qwen3-4B-Q4_K_M`, `diar_streaming_sortformer_4spk-v2`, backup/restore verification, and three-iteration policy.

- [ ] **Step 2: Run the documentation test and confirm missing/stale documents**

Run: `cd backend && python -m pytest tests/test_production_readiness_gate.py -q`

Expected: FAIL on missing model/incident/upgrade documents or stale status language.

- [ ] **Step 3: Update documentation and CI without claiming unrun results**

Document implemented behavior and commands. Leave readiness-result fields explicitly `unverified` until the full gate runs; never copy historical test totals. Add CI jobs that use exact lock installs and high-severity scans.

- [ ] **Step 4: Run complete gate iteration 1**

Run: `powershell -ExecutionPolicy Bypass -File .\scripts\production-readiness.ps1`

Expected: either exit 0 with every blocking criterion passed, or a complete evidence-backed failure list. If nonzero, write failing regression tests for each reproducible product defect, apply minimal fixes, and rerun focused suites.

- [ ] **Step 5: Run complete gate iteration 2 if iteration 1 failed**

Run the same exact command from fresh isolated resources. Apply TDD fixes for remaining reproducible failures. Stop immediately on any user-defined blocker.

- [ ] **Step 6: Run complete gate iteration 3 if iteration 2 failed**

Run the same exact command from fresh isolated resources. Do not run a fourth complete iteration. If nonzero, report precise remaining failures and do not claim readiness.

- [ ] **Step 7: Request independent read-only acceptance/configuration review after a zero-exit gate**

Provide the reviewer the governing goal, this plan, acceptance manifest, `git diff` from `6f281a3`, sanitized Compose config, latest `summary.json`, command logs, model results, backup/restore reconciliation, and health responses. Require an ID-by-ID verdict and Critical/Important/Minor findings. Fix Critical/Important findings with TDD and rerun affected checks plus the full gate if product/configuration behavior changed.

- [ ] **Step 8: Commit truthful final documents**

Update `docs/15-production-readiness-report.md` only from the final evidence bundle, including exact exit codes/test totals/model results/health JSON/risks/reviewer sign-off.

```bash
git add README.md CONTRIBUTING.md docs .github/workflows/ci.yml
git commit -m "docs: record verified production readiness evidence"
```

## Plan self-review checklist

- [x] Every section of the governing design maps to at least one numbered task.
- [x] Every explicit user command is present in Task 13 and the acceptance manifest.
- [x] Qwen, Sortformer, whisper.cpp, and every pre-existing catalog entry use real application-managed download/load paths.
- [x] Hardware-limited inference never substitutes for a failed/unattempted download.
- [x] PostgreSQL migrations, container health, browser flows, backup/restore, security scans, and reviewer sign-off have authoritative evidence paths.
- [x] No task uses a mocked result as final acceptance evidence.
- [x] The three-iteration ceiling and immediate-stop blockers are preserved.
- [x] No PR creation is included.
