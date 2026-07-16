import os
import subprocess
import sys
from pathlib import Path


def test_application_import_and_liveness_need_no_model_or_external_egress() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    environment = os.environ.copy()
    environment.update(
        {
            "APP_SECRET_KEY": "startup-test-secret-that-is-long-enough",
            "CREDENTIAL_ENCRYPTION_KEY": "startup-encryption-key-that-is-long-enough",
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "REDIS_URL": "redis://unused:6379/0",
            "EXTERNAL_APIS_ALLOWED": "false",
            "LOCAL_ONLY_ENFORCED": "true",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.main import live; assert live() == {'status': 'ok'}",
        ],
        cwd=backend_root,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
