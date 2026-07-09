# Contributing

## Setup

Copy `.env.example` to `.env`, then replace every `replace-with-*` value. Generate application and credential keys with:

```text
python scripts/generate-encryption-key.py
```

Install backend dependencies with the lock constraints:

```text
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -c requirements.lock -e ".[dev]"
```

Install frontend dependencies with the lockfile:

```text
cd frontend
npm ci
```

## Checks

Run these before opening a pull request:

```text
cd backend
python -m ruff check .
python -m pytest

cd ../frontend
npm test
npm run lint
npm run build
npm audit --audit-level=high
```

Pre-commit hooks are configured in `.pre-commit-config.yaml`. They run backend Ruff checks, staged-file Ruff format checks, frontend typecheck, and staged-file Prettier checks.

## Operational Smoke Checks

Use the large-file repository check before committing binary artifacts:

```text
python scripts/check-large-files.py --max-mb 25
```

PostgreSQL backup and restore helpers are available as shell and PowerShell scripts:

```text
DATABASE_URL=postgresql://... sh scripts/backup-postgres.sh
RESTORE_DATABASE_URL=postgresql://... sh scripts/restore-postgres.sh backups/example.dump
```

```text
$env:DATABASE_URL = "postgresql://..."
.\scripts\backup.ps1
$env:RESTORE_DATABASE_URL = "postgresql://..."
.\scripts\restore.ps1 .\backups\example.dump
```
