#!/usr/bin/env python3
"""Merge Afterglow configuration layers and emit a closed public frontend projection."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_PUBLIC_SCHEMA: dict[str, dict[str, type]] = {
    "app": {
        "backend_port": int,
        "site_name": str,
        "site_description": str,
        "logo_path": str,
        "logo_dark_path": str,
        "logo_light_path": str,
        "favicon_path": str,
        "refresh_interval_ms": int,
        "frontend_base_url": str,
        "public_api_base": str,
    },
    "services": {
        "magnum": bool,
        "manila": bool,
        "zun": bool,
        "k3s": bool,
        "trove": bool,
        "swift": bool,
        "barbican": bool,
        "waygate": bool,
        "chat": bool,
        "mcp": bool,
    },
    "openstack": {"s3_endpoint": str},
    "monitoring": {"grafana_base_url": str},
    "chat": {"base_url": str},
    "mcp": {"public_url": str},
}


def _deep_merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def load_merged(paths: list[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        with path.open("rb") as config_file:
            layer = tomllib.load(config_file)
        merged = _deep_merge(merged, layer)
    return merged


def project_public_config(config: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    projected: dict[str, dict[str, Any]] = {}
    for section, fields in _PUBLIC_SCHEMA.items():
        source = config.get(section)
        if source is None:
            continue
        if not isinstance(source, Mapping):
            raise TypeError(f"[{section}] must be a TOML table")

        values: dict[str, Any] = {}
        for field, expected_type in fields.items():
            if field not in source:
                continue
            value = source[field]
            if type(value) is not expected_type:
                raise TypeError(f"[{section}].{field} must be {expected_type.__name__}")
            values[field] = value
        if values:
            projected[section] = values
    return projected


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported public TOML value type: {type(value).__name__}")


def render_toml(config: Mapping[str, Mapping[str, Any]]) -> str:
    lines = [
        "# Generated public runtime configuration for the Afterglow frontend.",
        "# Contains only allowlisted browser-safe values; do not edit.",
        "",
    ]
    for section, values in config.items():
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_scalar(value)}")
        lines.append("")
    return "\n".join(lines)


def write_if_changed(destination: Path, content: str) -> bool:
    existing = destination.read_text(encoding="utf-8") if destination.exists() else None
    mode_changed = destination.exists() and destination.stat().st_mode & 0o777 != 0o644
    if existing == content and not mode_changed:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=destination.parent, delete=False
    ) as staging_file:
        staging_file.write(content)
        staging_path = Path(staging_file.name)
    replaced = False
    try:
        os.chmod(staging_path, 0o644)
        os.replace(staging_path, destination)
        replaced = True
    finally:
        if not replaced:
            staging_path.unlink(missing_ok=True)
    return True


def main(*path_args: str) -> bool:
    if len(path_args) < 2:
        raise ValueError("at least one input and one destination are required")
    *input_args, destination_arg = path_args
    merged = load_merged([Path(input_arg) for input_arg in input_args])
    projected = project_public_config(merged)
    return write_if_changed(Path(destination_arg), render_toml(projected))


if __name__ == "__main__":
    if sys.argv[1:] == ["--project-json"]:
        try:
            request = json.load(sys.stdin)
            merged = _deep_merge(request["config"], tomllib.loads(request.get("operator", "")))
            projected = project_public_config(merged)
            print(json.dumps({"config": projected, "toml": render_toml(projected)}))
        except (KeyError, TypeError, ValueError, OSError):
            raise SystemExit("Cannot project frontend configuration; check protected inputs") from None
    else:
        if len(sys.argv) < 3:
            raise SystemExit(
                "usage: render_frontend_config.py INPUT [INPUT ...] DESTINATION"
            )
        changed = main(*sys.argv[1:])
        print(json.dumps({"changed": changed}))
