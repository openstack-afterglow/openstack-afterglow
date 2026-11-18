#!/usr/bin/env python3
"""Initialize the shared Lumen ingress key in the private Kolla secrets file."""

from __future__ import annotations

import argparse
import os
import secrets
import stat
import tempfile
from pathlib import Path

import yaml


_KEY = "lumen_afterglow_ingress_secret"


def generate(path: Path) -> None:
    # Do not follow the globals.d link or open a non-regular input.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8") as source:
        original = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(original.st_mode)
            or stat.S_IMODE(original.st_mode) & 0o077
            or original.st_uid != os.geteuid()
        ):
            raise SystemExit("Use the regular private secrets.yml owned by the invoking deployment user")
        values = yaml.safe_load(source)
    if not isinstance(values, dict):
        raise SystemExit("The private secrets.yml must contain a YAML mapping")
    value = values.get(_KEY)
    if value is not None:
        if not isinstance(value, str) or (value and len(value.encode("utf-8")) < 32):
            raise SystemExit(f"{_KEY} must be empty or at least 32 UTF-8 bytes")
        return

    values[_KEY] = secrets.token_hex(32)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as target:
            temporary = Path(target.name)
            yaml.safe_dump(values, target, sort_keys=False, allow_unicode=True)
        current = path.lstat()
        if not os.path.samestat(original, current) or original.st_mtime_ns != current.st_mtime_ns:
            raise SystemExit("The private secrets.yml changed during generation; rerun after reviewing it")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("secrets_file", type=Path)
    args = parser.parse_args()
    try:
        generate(args.secrets_file)
    except (OSError, UnicodeError, yaml.YAMLError):
        # YAML diagnostics can contain unrelated plaintext credentials.
        raise SystemExit("Cannot initialize ingress signing; check the protected secrets.yml input") from None


if __name__ == "__main__":
    main()
