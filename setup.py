#!/usr/bin/env python3
"""Edit local Afterglow settings and generate Kubernetes, Helm, or both.

Python 3.11+; standard library only. Nothing is installed or deployed.

    python3 /path/to/setup.py
    python3 /path/to/setup.py --non-interactive --target both \
        --config ./afterglow.conf --output-dir ./generated \
        --set 'app.site_name="My cloud"' --set-file openstack.password=./password.txt

Missing bases use afterglow.conf.example, creating app.secret_key once. Existing
text, unknown settings, comments, and unselected placeholders are retained.
Only selected edits are written. --set accepts public TOML literals; private
strings must come from hidden terminal input or --set-file (exact UTF-8 bytes,
including trailing newline). Never pass a secret literal on a command line.

Menu: 1 edit a dotted setting, 2 Kubernetes, 3 Helm, 4 both, q cancel. Blank edit
input keeps the value; enter the TOML literal "" to explicitly clear a public
string. Secret input is hidden; blank keeps it. No values appear in previews.
The final y confirmation saves and generates; q, EOF, Ctrl-C, or n saves nothing.

Precedence: base < sorted sibling overrides (not afterglow.frontend.conf) and
config.gpu.toml < repeated --override files in order. Namespace selection never
selects a public domain; deploy/afterglow-prod.conf and dev profiles are opt-in.
Overrides are read, never rewritten. Output paths are relative to the caller,
not the downloaded source. Existing base backups are private afterglow.conf.bak.
All generated files are private (0600). Keep them and backups out of version
control. K8s output contains a local application Kustomize tree; its ingress
controller/cert-manager prerequisites remain operator-owned. Helm output is a
complete chart plus values-local.yaml; no helm/kubectl command is executed.
"""

import argparse
import getpass
import json
import os
import re
import sys
import tomllib
import warnings
from pathlib import Path

import config2helm
import generate_k8s
from generation_config import (
    CONFIG_EXAMPLE,
    config_override_paths,
    merge_config,
    prepare_config,
    private_setting,
    write_files,
)

_KEY = re.compile(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+\Z")
_ASSIGNMENT = re.compile(r"\s*([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)\s*=")
_TABLE = re.compile(r"\s*\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$")


def _get(cfg: dict, dotted: str):
    value = cfg
    for part in dotted.split("."):
        value = value[part]
    return value


def _public_cli_setting(dotted: str, literal: str) -> bool:
    # Only known public settings can be supplied on argv. Unknown operator
    # extensions can still be edited interactively or through protected files.
    if private_setting(dotted):
        return False
    try:
        _get(tomllib.loads(CONFIG_EXAMPLE.read_text(encoding="utf-8")), dotted)
    except (KeyError, TypeError):
        return False
    # A nominally public URL may contain credentials. Reject userinfo on argv.
    return not re.search(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s]*@", literal)


def edit_config(text: str, dotted: str, literal: str) -> str:
    """Patch only a selected TOML assignment, preserving every other byte.

    Bare dotted paths address ordinary tables, not indexed array-table entries.
    Complex/inline table edits that cannot be made losslessly fail closed.
    tomllib validates both the original and candidate before any file is touched.
    """
    if not _KEY.fullmatch(dotted):
        raise ValueError("Use a bare dotted section.key path")
    tomllib.loads(text)
    value = tomllib.loads("value = " + literal)["value"]
    section, key = dotted.rsplit(".", 1)
    lines = text.splitlines(keepends=True)
    table = ""
    insertion = None
    found_section = False
    index = 0
    while index < len(lines):
        line = lines[index]
        header = _TABLE.fullmatch(line.rstrip("\r\n"))
        if header:
            if table == section and insertion is None:
                insertion = index
            table = header.group(1)
            found_section |= table == section
            index += 1
            continue
        if line.lstrip().startswith("["):
            if table == section and insertion is None:
                insertion = index
            table = ""  # array/quoted tables are preserved, not rewritten
        assignment = _ASSIGNMENT.match(line)
        if assignment:
            end = index + 1
            statement = line
            while True:
                try:
                    tomllib.loads(statement)
                    break
                except tomllib.TOMLDecodeError:
                    if end >= len(lines):
                        raise ValueError("Cannot edit this TOML statement losslessly") from None
                    statement += lines[end]
                    end += 1
            path = f"{table}.{assignment.group(1)}" if table else assignment.group(1)
            if path == dotted:
                lines[index:end] = [f"{assignment.group(1)} = {literal}\n"]
                result = "".join(lines)
                parsed = tomllib.loads(result)
                if _get(parsed, dotted) != value:
                    raise ValueError("Ambiguous setting")
                return result
            index = end
        else:
            index += 1
    if found_section:
        insertion = len(lines) if insertion is None else insertion
        if insertion and not lines[insertion - 1].endswith("\n"):
            lines[insertion - 1] += "\n"
        lines.insert(insertion, f"{key} = {literal}\n")
        result = "".join(lines)
    else:
        result = text + ("\n" if text and not text.endswith("\n") else "")
        result += f"\n[{section}]\n{key} = {literal}\n"
    tomllib.loads(result)
    return result


def collect_artifacts(cfg: dict, target: str, output_dir: Path, namespace: str) -> dict[Path, str]:
    """Use the canonical generators; do not maintain a setup-specific renderer."""
    contents = {}
    if target in ("k8s", "both"):
        contents.update({output_dir / "k8s" / name: content
                         for name, content in generate_k8s.render_artifacts(cfg, namespace).items()})
    if target in ("helm", "both"):
        destination = output_dir / "helm" / "afterglow"
        contents.update({destination / name: content
                         for name, content in config2helm.chart_sources().items()})
        contents[destination / "values-local.yaml"] = config2helm.render_values(cfg)
    revision = os.environ.get("AFTERGLOW_SETUP_SOURCE_REVISION", "")
    if revision and not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Invalid source revision")
    contents[output_dir / "generation.json"] = json.dumps({
        "source_revision": revision.lower() or "local-source-unverified",
        "target": target,
        "namespace": namespace,
    }, indent=2) + "\n"
    return contents


def run_workflow(config_path: Path, text: str, target: str, output_dir: Path,
                 namespace: str, overrides: list[Path], private_inputs: list[Path] | None = None) -> None:
    cfg = merge_config(config_path, text, overrides)
    contents = collect_artifacts(cfg, target, output_dir, namespace)
    sources = [config_path, *config_override_paths(config_path), *overrides, *(private_inputs or [])]
    if {path.resolve() for path in sources} & {path.resolve() for path in contents}:
        raise ValueError("Configuration inputs and output paths must be distinct")
    contents[config_path] = text
    write_files(contents, backup_paths={config_path} if config_path.exists() else None)


def _setting_names(cfg: dict, prefix: str = "") -> list[str]:
    result = []
    for key, value in cfg.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.extend(_setting_names(value, path))
        else:
            result.append(path)
    return result


def interactive(text: str, target: str) -> tuple[str, str] | None:
    print("Afterglow local setup — generation only. Values are never previewed.")
    print("Edits affect the base; supported local and explicit overrides still take precedence.")
    while True:
        print("\n1) Edit setting  2) Generate Kubernetes  3) Generate Helm  4) Generate both  q) Cancel")
        choice = input("Choice: ").strip().lower()
        if choice in ("q", "quit", "cancel"):
            return None
        if choice == "1":
            cfg = tomllib.loads(text)
            print("Available base settings (values hidden):")
            for path in _setting_names(cfg):
                print("  " + path + (" [private: ****]" if private_setting(path) else ""))
            dotted = input("Setting (section.key; blank cancels edit): ").strip()
            if not dotted:
                continue
            try:
                if private_setting(dotted):
                    # getpass normally falls back to echoed stdin without a TTY;
                    # forbid that fallback rather than exposing a credential.
                    with warnings.catch_warnings():
                        warnings.simplefilter("error", getpass.GetPassWarning)
                        raw = getpass.getpass("New private value (hidden; blank keeps current): ")
                    literal = json.dumps(raw, ensure_ascii=False)
                else:
                    raw = input('New TOML value (strings in double quotes; blank keeps current): ')
                    literal = raw
                if raw:
                    text = edit_config(text, dotted, literal)
                    print("Selected edit staged; nothing saved yet.")
            except (ValueError, KeyError, TypeError, getpass.GetPassWarning):
                print("Edit rejected. Check the dotted path and TOML value; no input values displayed.")
            continue
        selected = {"2": "k8s", "3": "helm", "4": "both"}.get(choice)
        if selected is None:
            print("Choose 1, 2, 3, 4, or q.")
            continue
        target = selected
        answer = input(f"Save configuration and generate {target} artifacts? [y/N]: ").strip().lower()
        return (text, target) if answer in ("y", "yes") else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", type=Path, default=Path.cwd() / "afterglow.conf")
    parser.add_argument("--output-dir", type=Path, default=Path.cwd() / "generated")
    parser.add_argument("--target", choices=("k8s", "helm", "both"), default="both")
    parser.add_argument("--namespace", choices=("afterglow", "afterglow-dev"), default="afterglow")
    parser.add_argument("--override", type=Path, action="append", default=[])
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--set", dest="edits", action="append", default=[], metavar="SECTION.KEY=TOML")
    parser.add_argument("--set-file", action="append", default=[], metavar="SECTION.KEY=PATH")
    args = parser.parse_args()
    try:
        config_path = args.config.absolute()
        text = prepare_config(config_path)
        tomllib.loads(text)
        for edit in args.edits:
            dotted, separator, literal = edit.partition("=")
            if not separator or not _public_cli_setting(dotted, literal):
                raise ValueError("Only public known settings may use --set; use --set-file for private values")
            text = edit_config(text, dotted, literal)
        private_inputs = []
        for edit in args.set_file:
            dotted, separator, filename = edit.partition("=")
            if not separator:
                raise ValueError("Expected section.key=path")
            literal = json.dumps(Path(filename).read_bytes().decode("utf-8"), ensure_ascii=False)
            text = edit_config(text, dotted, literal)
            private_inputs.append(Path(filename))
        target = args.target
        if not args.non_interactive:
            result = interactive(text, target)
            if result is None:
                print("Cancelled. No files written.")
                return 0
            text, target = result
        run_workflow(config_path, text, target, args.output_dir.absolute(), args.namespace, args.override, private_inputs)
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled. No files written.")
        return 0
    except (OSError, ValueError, KeyError, TypeError):
        print("Setup failed; check TOML, selected edits and file permissions. No input values displayed.", file=sys.stderr)
        return 1
    print(f"Generated {target} artifacts in {args.output_dir.absolute()}. No deployment performed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
