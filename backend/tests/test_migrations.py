from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND_ROOT = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_ROOT / "alembic" / "versions"

EXPLICIT_DDL_REVISIONS = {
    "0001_initial_foundation.py",
}

FORBIDDEN_HISTORICAL_DDL = (
    "Base.metadata.create_all",
    "Base.metadata.drop_all",
    "from app.",
    "import app.",
    "_column_exists",
    "sa.inspect",
    "inspect(",
)


def _script_directory() -> ScriptDirectory:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    return ScriptDirectory.from_config(config)


def test_alembic_revision_graph_has_one_head_and_unique_short_ids() -> None:
    script = _script_directory()
    revisions = list(script.walk_revisions())
    revision_ids = [item.revision for item in revisions]

    assert len(script.get_heads()) == 1
    assert len(revision_ids) == len(set(revision_ids))
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)


@pytest.mark.parametrize("filename", sorted(EXPLICIT_DDL_REVISIONS))
def test_historical_revision_uses_only_explicit_ddl(filename: str) -> None:
    source = (VERSIONS_DIR / filename).read_text(encoding="utf-8")
    violations = [token for token in FORBIDDEN_HISTORICAL_DDL if token in source]
    assert violations == []
