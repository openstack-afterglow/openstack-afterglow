#!/usr/bin/env python3
"""Promote package-owned Kolla roles from immutable sibling release tags.

The operator is intentionally not a live "latest" consumer.  A release tag can
advance the committed operator manifest only through this tool, which resolves
the tag into ``uv.lock`` and leaves a reviewable change for a maintainer.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse


@dataclass(frozen=True)
class Service:
    distribution: str
    repository: str


SERVICES: dict[str, Service] = {
    "drover": Service("drover", "https://github.com/openstack-afterglow/drover.git"),
    "lumen": Service("lumen", "https://github.com/openstack-afterglow/lumen.git"),
    "waygate": Service("waygate", "https://github.com/openstack-afterglow/waygate.git"),
    "palimpsest": Service("palimpsest-client", "https://github.com/openstack-afterglow/palimpsest.git"),
}
TAG_RE = re.compile(r"^v(?P<major>0|[1-9][0-9]*)\.(?P<minor>0|[1-9][0-9]*)\.(?P<patch>0|[1-9][0-9]*)$")


class PromotionError(RuntimeError):
    """A release tag cannot safely become an operator source."""


def tag_version(tag: str) -> tuple[int, int, int]:
    match = TAG_RE.fullmatch(tag)
    if not match:
        raise PromotionError(f"release tag must be stable vX.Y.Z, got {tag!r}")
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def select_tag(current_version: str, configured_tag: str | None, available_tags: list[str]) -> str | None:
    """Choose the newest non-downgrade stable release tag.

    Equality is intentional: it replaces an existing commit pin with the
    release tag of the same package version.  Tags older than the resolved
    package never downgrade an operator environment.
    """

    current = tag_version(f"v{current_version}")
    candidates = [tag for tag in available_tags if tag_version(tag) >= current]
    if not candidates:
        return None
    selected = max(candidates, key=tag_version)
    return None if selected == configured_tag else selected


def run(*args: str, cwd: Path) -> str:
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        message = result.stderr.strip() or result.stdout.strip() or "command failed"
        raise PromotionError(f"{' '.join(args)}: {message}")
    return result.stdout


def read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as source:
            return tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PromotionError(f"cannot read {path}: {exc}") from exc


def package_lock_entry(lock: dict[str, object], distribution: str) -> dict[str, object]:
    entries = [entry for entry in lock.get("package", []) if entry.get("name") == distribution]
    if len(entries) != 1:
        raise PromotionError(f"lock must contain exactly one {distribution!r} package entry")
    return entries[0]


def lock_version(operator_dir: Path, distribution: str) -> str:
    entry = package_lock_entry(read_toml(operator_dir / "uv.lock"), distribution)
    version = entry.get("version")
    if not isinstance(version, str):
        raise PromotionError(f"lock entry for {distribution!r} has no version")
    tag_version(f"v{version}")
    return version


def configured_tag(operator_dir: Path, distribution: str) -> str | None:
    data = read_toml(operator_dir / "pyproject.toml")
    try:
        source = data["tool"]["uv"]["sources"][distribution]
    except KeyError as exc:
        raise PromotionError(f"operator source for {distribution!r} is missing") from exc
    if not isinstance(source, dict):
        raise PromotionError(f"operator source for {distribution!r} is invalid")
    tag = source.get("tag")
    if tag is None:
        return None
    if not isinstance(tag, str):
        raise PromotionError(f"operator source tag for {distribution!r} is invalid")
    tag_version(tag)
    return tag


def remote_tags(service: Service, root: Path) -> list[str]:
    output = run("git", "ls-remote", "--tags", "--refs", service.repository, "refs/tags/v*", cwd=root)
    tags: list[str] = []
    for line in output.splitlines():
        try:
            _, ref = line.split("\t", 1)
        except ValueError as exc:
            raise PromotionError(f"malformed tag reference from {service.repository}") from exc
        tag = ref.removeprefix("refs/tags/")
        try:
            tag_version(tag)
        except PromotionError:
            continue
        tags.append(tag)
    return tags


def verify_tag_source(operator_dir: Path, service_name: str, service: Service) -> None:
    tag = configured_tag(operator_dir, service.distribution)
    if tag is None:
        raise PromotionError(f"{service_name} must use an explicit immutable Git tag, not a branch or commit")
    entry = package_lock_entry(read_toml(operator_dir / "uv.lock"), service.distribution)
    version = entry.get("version")
    source = entry.get("source")
    if version != tag.removeprefix("v"):
        raise PromotionError(f"{service_name} tag {tag} resolves to package version {version!r}")
    if not isinstance(source, dict) or not isinstance(source.get("git"), str):
        raise PromotionError(f"{service_name} lock entry must be a Git source")
    query = parse_qs(urlparse(source["git"]).query)
    if query.get("tag") != [tag]:
        raise PromotionError(f"{service_name} lock entry is not resolved from tag {tag}")


def promote(operator_dir: Path, names: list[str]) -> bool:
    changed = False
    root = operator_dir.parent.parent.parent
    promoted: list[str] = []
    for name in names:
        service = SERVICES[name]
        current = lock_version(operator_dir, service.distribution)
        selected = select_tag(current, configured_tag(operator_dir, service.distribution), remote_tags(service, root))
        if selected is None:
            print(f"{name}: no released tag at or above installed {current}; keeping current source")
            continue
        print(f"{name}: promoting {current} to {selected}")
        run(
            "uv",
            "add",
            "--no-sync",
            "--tag",
            selected,
            f"{service.distribution} @ git+{service.repository}",
            cwd=operator_dir,
        )
        promoted.append(name)
        changed = True
    if changed:
        run("uv", "lock", "--refresh", cwd=operator_dir)
        for name in promoted:
            verify_tag_source(operator_dir, name, SERVICES[name])
    return changed

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operator-dir", type=Path, default=Path("deploy/kolla/operator"))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="promote every service with an eligible newest release tag")
    group.add_argument("--check", action="store_true", help="require every service source and lock entry to use its release tag")
    args = parser.parse_args()
    operator_dir = args.operator_dir.resolve()
    if not (operator_dir / "pyproject.toml").is_file() or not (operator_dir / "uv.lock").is_file():
        raise PromotionError(f"{operator_dir} is not an operator project with pyproject.toml and uv.lock")
    if args.check:
        for name, service in SERVICES.items():
            verify_tag_source(operator_dir, name, service)
        print("all package-owned Kolla roles resolve from immutable release tags")
        return 0
    promote(operator_dir, list(SERVICES))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PromotionError as exc:
        print(f"promote_kolla_role_tags: {exc}", file=sys.stderr)
        raise SystemExit(2)
