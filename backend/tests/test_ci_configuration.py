from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_gitleaks_pull_request_scan_receives_github_token() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    secret_scan = workflow.split("  secret-scan:\n", maxsplit=1)[1]

    assert "- uses: gitleaks/gitleaks-action@v2" in secret_scan
    assert "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}" in secret_scan


def test_windows_only_locked_dependency_has_platform_marker() -> None:
    requirements = (REPOSITORY_ROOT / "backend" / "requirements.lock").read_text(
        encoding="utf-8"
    )
    pywin32_lines = [
        line for line in requirements.splitlines() if line.startswith("pywin32==")
    ]

    assert all('sys_platform == "win32"' in line for line in pywin32_lines)


def test_dependency_scan_uses_cpu_lock_without_building_packages() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    dependency_scan = workflow.split("  dependency-scan:\n", maxsplit=1)[1].split(
        "  sbom:\n", maxsplit=1
    )[0]

    assert "pip-audit --no-deps --disable-pip" in dependency_scan
    assert "backend/requirements.cpu.lock" in dependency_scan


def test_operational_smoke_uses_postgres_service_hostname() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    operational_smoke = workflow.split("  operational-smoke:\n", maxsplit=1)[1].split(
        "  dependency-scan:\n", maxsplit=1
    )[0]

    assert "DATABASE_URL: postgresql://postgres:postgres@postgres:5432/" in operational_smoke
    assert "RESTORE_DATABASE_URL: postgresql://postgres:postgres@postgres:5432/" in operational_smoke


def test_cpu_lock_excludes_optional_advanced_speech_packages() -> None:
    requirements_path = REPOSITORY_ROOT / "backend" / "requirements.cpu.lock"
    requirements = requirements_path.read_text(encoding="utf-8")

    assert "transformers==" not in requirements
    assert "nltk==" not in requirements
