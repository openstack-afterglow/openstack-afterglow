#!/usr/bin/env python3
"""Extract the expected package version from an operator uv.lock file."""

from __future__ import annotations

import re
import sys
from pathlib import Path


def get_version(lock_path: Path, distribution: str) -> str:
    try:
        import tomllib

        with lock_path.open("rb") as f:
            data = tomllib.load(f)
        for pkg in data.get("package", []):
            if pkg.get("name") == distribution:
                version = pkg.get("version")
                if isinstance(version, str):
                    return version
        raise ValueError(f"Package {distribution!r} not found in {lock_path}")
    except (ImportError, ModuleNotFoundError):
        text = lock_path.read_text(encoding="utf-8")
        # Match [[package]] blocks with name and version
        pattern = re.compile(
            r'\[\[package\]\]\s*\n(?:[^\n]*\n)*?name\s*=\s*"'
            + re.escape(distribution)
            + r'"\s*\nversion\s*=\s*"([^"]+)"'
        )
        match = pattern.search(text)
        if match:
            return match.group(1)
        raise ValueError(f"Package {distribution!r} not found in {lock_path}")


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: read_locked_version.py LOCK_PATH DISTRIBUTION", file=sys.stderr)
        return 2
    lock_path = Path(sys.argv[1])
    distribution = sys.argv[2]
    if not lock_path.is_file():
        print(f"error: lockfile {lock_path} does not exist", file=sys.stderr)
        return 1
    try:
        print(get_version(lock_path, distribution))
        return 0
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
