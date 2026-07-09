from pathlib import Path


def test_alembic_revision_ids_fit_version_table() -> None:
    """Alembic's default version_num column is varchar(32)."""
    versions_dir = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    for migration in versions_dir.glob("*.py"):
        namespace: dict[str, object] = {}
        exec(migration.read_text(encoding="utf-8"), namespace)
        revision = namespace["revision"]
        assert isinstance(revision, str)
        assert len(revision) <= 32, f"{migration.name} revision id is too long"
