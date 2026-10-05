#!/usr/bin/env python3
"""Resolve selected moving image refs through Docker's distribution descriptor API.

Stdin: {"refs": {"variable_name": "image_ref"}, "auth_config": optional_object}.
Stdout: the complete variable-name/ref JSON object, only after every lookup succeeds.
Omit auth_config to use the Docker SDK's existing registry credential configuration.
Supplied auth_config requires username/password/serveraddress strings and is used
only for that registry (Docker Hub aliases are equivalent); other registries use
the SDK's configured credentials.
Version tags, digest pins and afterglow-local source refs are returned unchanged.
The returned digest identifies the registry manifest/index, not a platform image ID.
"""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlsplit


_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class ResolutionError(Exception):
    """An operator-safe diagnostic that contains no registry response or credentials."""


def moving_repository(ref: str) -> str | None:
    if "@" in ref or ref.startswith("afterglow-local/"):
        return None
    for suffix in (":latest", ":stable"):
        if ref.endswith(suffix):
            return ref[:-len(suffix)]
    # A colon in the registry authority is a port, not an image tag.
    if ":" not in ref.rsplit("/", 1)[-1]:
        return ref
    return None


def registry_authority(address: str) -> str:
    try:
        parsed = urlsplit(address if "://" in address else "//" + address)
        authority = parsed.netloc.lower()
        if not authority or parsed.username is not None or parsed.password is not None:
            raise ValueError
    except ValueError:
        raise ResolutionError("auth_config serveraddress must identify a registry without embedded credentials.") from None
    if authority in {"docker.io", "index.docker.io", "registry-1.docker.io"}:
        return "docker.io"
    return authority


def image_registry(ref: str) -> str:
    first, separator, _ = ref.partition("/")
    if separator and ("." in first or ":" in first or first == "localhost"):
        return registry_authority(first)
    return "docker.io"


def resolve_refs(refs: dict[str, str], auth_config: dict | None = None) -> dict[str, str]:
    selected = dict(refs)
    moving = [(name, ref, moving_repository(ref)) for name, ref in refs.items()]
    moving = [(name, ref, repo) for name, ref, repo in moving if repo is not None]
    if not moving:
        return selected

    auth_registry = None
    if auth_config is not None:
        if not isinstance(auth_config, dict) or set(auth_config) != {"username", "password", "serveraddress"} or any(
            not isinstance(value, str) or not value for value in auth_config.values()
        ):
            raise ResolutionError("auth_config requires nonempty username, password and serveraddress strings.")
        auth_registry = registry_authority(auth_config["serveraddress"])

    try:
        import docker

        client = docker.from_env()
    except Exception:
        raise ResolutionError("Cannot initialize Docker; check the SDK and Docker Engine connection.") from None

    try:
        for position, (name, ref, repo) in enumerate(moving, 1):
            try:
                auth = auth_config if auth_registry == image_registry(ref) else None
                digest = client.images.get_registry_data(ref, auth_config=auth).id
            except Exception:
                raise ResolutionError(
                    f"Registry lookup failed for moving image {position}; check access, credentials and tag availability."
                ) from None
            if not isinstance(digest, str) or _DIGEST.fullmatch(digest) is None:
                raise ResolutionError(
                    f"Registry returned an invalid manifest/index digest for moving image {position}; expected sha256 and 64 lowercase hex characters."
                )
            selected[name] = f"{repo}@{digest}"
    finally:
        try:
            client.close()
        except Exception:
            raise ResolutionError("Cannot close the Docker connection after image resolution.") from None
    return selected


def main() -> int:
    try:
        if len(sys.argv) != 1:
            raise ResolutionError("Usage: resolve_image_refs.py < selected-images.json")
        try:
            request = json.load(sys.stdin)
        except (ValueError, OSError):
            raise ResolutionError("Input must be a JSON object containing refs and optional auth_config.") from None
        if not isinstance(request, dict) or set(request) - {"refs", "auth_config"}:
            raise ResolutionError("Input must contain only refs and optional auth_config.")
        refs = request.get("refs")
        if not isinstance(refs, dict) or any(
            not isinstance(name, str) or not name or not isinstance(ref, str)
            or not ref or ref != ref.strip() or any(character.isspace() for character in ref)
            for name, ref in refs.items()
        ):
            raise ResolutionError("refs must map nonempty variable names to nonempty image references without whitespace.")
        auth_config = request.get("auth_config")
        if auth_config is not None and not isinstance(auth_config, dict):
            raise ResolutionError("auth_config must be an object when supplied.")
        selected = resolve_refs(refs, auth_config)
        result = json.dumps(selected)
    except ResolutionError as error:
        print(f"Image resolution failed: {error}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
