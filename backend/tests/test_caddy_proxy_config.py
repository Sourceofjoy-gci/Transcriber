from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = REPO_ROOT / "infra" / "caddy" / "Caddyfile"


def _directive_depths(directive: str) -> list[int]:
    depths: list[int] = []
    depth = 0
    for raw_line in CADDYFILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        leading_closes = len(line) - len(line.lstrip("}"))
        effective_depth = depth - leading_closes
        if line == directive or line.startswith(f"{directive} "):
            depths.append(effective_depth)
        depth += line.count("{") - line.count("}")
    return depths


def test_spa_rewrite_is_scoped_to_fallback_handle() -> None:
    assert _directive_depths("try_files") == [2]


def test_api_and_health_paths_are_proxied() -> None:
    caddyfile = CADDYFILE.read_text(encoding="utf-8")
    assert "@api path /api /api/* /health /health/*" in caddyfile
    assert caddyfile.index("handle @api") < caddyfile.index("try_files")
