from __future__ import annotations

import argparse
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "node_modules",
    "__pycache__",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail when repository files exceed a size threshold.")
    parser.add_argument("--root", default=".", help="Repository root to scan")
    parser.add_argument("--max-mb", type=float, default=25.0, help="Maximum allowed file size in MiB")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    max_bytes = int(args.max_mb * 1024 * 1024)
    failures: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        if path.stat().st_size > max_bytes:
            failures.append(path)

    if failures:
        for path in failures:
            size_mb = path.stat().st_size / 1024 / 1024
            print(f"{path.relative_to(root)} is {size_mb:.2f} MiB")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
