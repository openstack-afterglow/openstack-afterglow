#!/usr/bin/env python3
"""Merge native Kolla defaults with explicit operator TOML without truthy fallbacks."""

from __future__ import annotations

import json
import math
import sys
import tomllib
from collections.abc import Mapping
from datetime import date, datetime, time
from pathlib import Path
from typing import Any


def _merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(merged.get(key), dict) and isinstance(value, Mapping):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _without_legacy_key(config: dict[str, Any]) -> dict[str, Any]:
    builder = config.get("builder")
    if isinstance(builder, dict):
        builder.pop("ssh_private_key", None)
    return config


def merge_config(base_text: str, operator_text: str) -> dict[str, Any]:
    return _merge(
        _without_legacy_key(tomllib.loads(base_text)),
        _without_legacy_key(tomllib.loads(operator_text)),
    )


def load_merged(paths: list[Path]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for path in paths:
        with path.open("rb") as source:
            merged = _merge(merged, _without_legacy_key(tomllib.load(source)))
    return merged


def _key(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        return repr(value)
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if isinstance(value, list):
        return "[" + ", ".join(_value(item) for item in value) + "]"
    if isinstance(value, Mapping):
        return "{ " + ", ".join(
            f"{_key(key)} = {_value(item)}" for key, item in sorted(value.items())
        ) + " }"
    raise TypeError(f"unsupported TOML value type: {type(value).__name__}")


def render_toml(config: Mapping[str, Any]) -> str:
    lines = ["# Generated effective Afterglow runtime configuration; do not edit.", ""]

    def table(values: Mapping[str, Any], path: tuple[str, ...]) -> None:
        if path:
            lines.append("[" + ".".join(_key(part) for part in path) + "]")
        for key, value in sorted(values.items()):
            if not isinstance(value, Mapping):
                lines.append(f"{_key(key)} = {_value(value)}")
        lines.append("")
        for key, value in sorted(values.items()):
            if isinstance(value, Mapping):
                table(value, (*path, key))

    table(config, ())
    rendered = "\n".join(lines)
    tomllib.loads(rendered)
    return rendered


def main() -> None:
    try:
        request = json.load(sys.stdin)
        if sys.argv[1:] == ["--render"]:
            sys.stdout.write(render_toml(request))
        elif not sys.argv[1:]:
            config = merge_config(request["base"], request.get("operator", ""))
            print(json.dumps(config))
        else:
            raise ValueError("invalid arguments")
    except (KeyError, TypeError, ValueError, OSError):
        # Never echo TOML lines, credentials or secret-bearing parser diagnostics.
        raise SystemExit("Cannot render effective Afterglow configuration; check protected inputs") from None


if __name__ == "__main__":
    main()
