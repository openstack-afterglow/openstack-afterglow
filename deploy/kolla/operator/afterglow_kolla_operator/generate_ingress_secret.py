#!/usr/bin/env python3
"""Initialize the shared Lumen ingress key in the private Kolla secrets file."""

from __future__ import annotations

import argparse
import fcntl
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

import yaml


_KEY = "lumen_afterglow_ingress_secret"
_NULL_LINE = re.compile(
    rf"^{_KEY}:([ \t]*)(~|null|Null|NULL)?([ \t]*(?:#[^\r\n]*)?)(?=\r?$)",
    re.MULTILINE,
)


class _SecretsLoader(yaml.SafeLoader):
    """Read an inline Ansible Vault blob as an opaque scalar; never decrypt it."""


_SecretsLoader.add_constructor("!vault", _SecretsLoader.construct_scalar)


def _load_mapping(text: str) -> dict:
    loader = _SecretsLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            return {}
        if not isinstance(node, yaml.MappingNode) or node.tag != "tag:yaml.org,2002:map":
            raise SystemExit("The private secrets.yml must contain a YAML mapping")
        if sum(isinstance(key, yaml.ScalarNode) and key.value == _KEY for key, _ in node.value) > 1:
            raise SystemExit(f"The private secrets.yml contains duplicate {_KEY} keys")
        return loader.construct_document(node)
    finally:
        loader.dispose()


def _initialize(text: str) -> str:
    values = _load_mapping(text)
    if values.get(_KEY) is not None:
        raise SystemExit(f"{_KEY} is already set; no changes were made")

    secret = secrets.token_hex(32)
    if _KEY in values:
        def replace_null(match: re.Match[str]) -> str:
            whitespace, explicit_null, tail = match.groups()
            if explicit_null is not None:
                return f'{_KEY}:{whitespace}"{secret}"{tail}'
            return f'{_KEY}: "{secret}"{whitespace}{tail}'

        updated, matches = _NULL_LINE.subn(replace_null, text)
        if matches != 1:
            raise SystemExit(f"Edit {_KEY} manually; its null entry is not a simple top-level key")
    else:
        newline = "\r\n" if "\r\n" in text else "\n"
        separator = newline if text and not text.endswith(("\n", "\r")) else ""
        updated = f'{text}{separator}{_KEY}: "{secret}"{newline}'

    # A document terminator, flow mapping or clipped block scalar can make
    # the one-line edit unsafe. Never change other values to force a rewrite.
    if _load_mapping(updated) != (values | {_KEY: secret}):
        raise SystemExit(f"Edit {_KEY} manually; the automatic edit would alter other values")
    return updated


def generate(path: Path) -> None:
    # Do not follow the globals.d link or open a non-regular input.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8", newline="") as source:
        # A second initializer that opened this inode must wait through publication.
        fcntl.flock(source.fileno(), fcntl.LOCK_EX)
        original = os.fstat(source.fileno())
        if (
            not stat.S_ISREG(original.st_mode)
            or stat.S_IMODE(original.st_mode) & 0o7077
            or original.st_uid != os.geteuid()
        ):
            raise SystemExit("Use the regular private secrets.yml owned by the invoking deployment user")
        updated = _initialize(source.read())

        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as target:
                temporary = Path(target.name)
                target.write(updated)
                if os.fstat(target.fileno()).st_gid != original.st_gid:
                    os.fchown(target.fileno(), -1, original.st_gid)
                os.fchmod(target.fileno(), stat.S_IMODE(original.st_mode))
                target.flush()
                os.fsync(target.fileno())
            current = path.lstat()
            if not os.path.samestat(original, current) or original.st_ctime_ns != current.st_ctime_ns:
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
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError):
        # YAML diagnostics can contain unrelated plaintext credentials.
        raise SystemExit("Cannot initialize ingress signing; check the protected secrets.yml input") from None


if __name__ == "__main__":
    main()
