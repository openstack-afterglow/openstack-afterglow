#!/usr/bin/env python3
"""Merge native Kolla defaults with explicit operator TOML without truthy fallbacks."""

from __future__ import annotations

import hashlib
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


NATIVE_MAPPING_SCHEMA = "2.0"


def native_mapping_digest(schema_version: Any, rules: Any) -> str:
    """Canonical digest used by backend native_oidc.mapping_matches; any other document is rejected."""
    if schema_version != NATIVE_MAPPING_SCHEMA or not isinstance(rules, list) or not rules:
        raise ValueError("native mapping document is invalid")
    document = {"schema_version": schema_version, "rules": rules}
    return hashlib.sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def pin_native_mappings(config: dict[str, Any], mappings: Any) -> dict[str, Any]:
    """Derive each native provider's pin from the Kolla mapping source it must match.

    An operator-declared sha256 is accepted only when it equals the derived value; any other value fails closed.
    """
    if not isinstance(mappings, list):
        raise ValueError("native mapping sources must be a list")
    auth = config.get("auth")
    providers = auth.get("providers", {}) if isinstance(auth, dict) else {}
    if not isinstance(providers, dict):
        raise ValueError("auth providers must be a table")
    for provider in providers.values():
        pin = provider.get("native_mapping") if isinstance(provider, dict) else None
        if pin is None:
            continue
        if not isinstance(pin, dict):
            raise ValueError("native_mapping must be a table")
        found = [m for m in mappings if isinstance(m, dict) and m.get("name") == pin.get("mapping_id")]
        if len(found) != 1:
            raise ValueError("native mapping source is missing or ambiguous")
        with Path(str(found[0].get("file", ""))).open(encoding="utf-8") as source:
            digest = native_mapping_digest(NATIVE_MAPPING_SCHEMA, json.load(source))
        declared = pin.get("sha256")
        if declared not in (None, "", digest):
            raise ValueError("native mapping pin differs from the Kolla mapping source")
        pin["sha256"] = digest
    return config


def native_mapping_pins(config: dict[str, Any]) -> list[dict[str, str]]:
    """Pinned native providers as (mapping_id, sha256) pairs for the live Keystone precheck."""
    auth = config.get("auth")
    providers = auth.get("providers", {}) if isinstance(auth, dict) else {}
    pins = []
    for provider in providers.values() if isinstance(providers, dict) else []:
        pin = provider.get("native_mapping") if isinstance(provider, dict) else None
        if isinstance(pin, dict):
            pins.append({"mapping_id": str(pin.get("mapping_id", "")), "sha256": str(pin.get("sha256", ""))})
    return pins



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
            config = pin_native_mappings(
                merge_config(request["base"], request.get("operator", "")),
                request.get("keystone_identity_mappings", []),
            )
            print(json.dumps(config))
        elif sys.argv[1:] == ["--mapping-digest"]:
            print(native_mapping_digest(request.get("schema_version"), request.get("rules")))
        elif sys.argv[1:] == ["--native-pins"]:
            print(json.dumps(native_mapping_pins(request)))
        else:
            raise ValueError("invalid arguments")
    except (KeyError, TypeError, ValueError, OSError):
        # Never echo TOML lines, credentials or secret-bearing parser diagnostics.
        raise SystemExit("Cannot render effective Afterglow configuration; check protected inputs") from None


if __name__ == "__main__":
    main()
