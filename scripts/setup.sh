#!/usr/bin/env bash
# Afterglow configuration generation only; never installs or deploys anything.
# Requires Bash, curl, and an available Python >=3.11 with stdlib tomllib.
# Run from the directory where setup.py should generate its output:
#   curl --fail --location --show-error --silent \
#     https://raw.githubusercontent.com/openstack-afterglow/openstack-afterglow/dev/scripts/setup.sh | bash
#   curl --fail --location --show-error --silent \
#     https://raw.githubusercontent.com/openstack-afterglow/openstack-afterglow/dev/scripts/setup.sh | bash -s -- --non-interactive --config ./input.toml
# All arguments are forwarded unchanged to the bundled setup.py; supply secrets
# through its private input file or hidden terminal prompts, never CLI arguments.
# AFTERGLOW_SETUP_REF selects a branch/tag/ref (default: dev) or a full 40-hex SHA.
# Set it on the Bash side of the pipeline, e.g. ... | AFTERGLOW_SETUP_REF=<sha> bash.
# A ref is resolved once through the public GitHub commits API, then the entire
# source bundle is downloaded by that immutable SHA from GitHub codeload.
# Bundled setup.py receives AFTERGLOW_SETUP_SOURCE_REVISION set to that resolved
# SHA, replacing any caller-supplied value; this metadata never changes its args.
# These three GitHub hosts/repository paths are fixed, not URL overrides. No API
# token is required or accepted. Pin the raw script URL to a reviewed SHA too
# when the entrypoint itself must be immutable; curl-pipe-Bash trusts that script.
# Use set -o pipefail in the calling Bash so raw-script curl failures propagate.
# Interactive piped execution opens /dev/tty; without a controlling terminal,
# pass --non-interactive. The shell does not read, preview, or log input values.
# Temporary source is removed on exit/signals; caller cwd is never changed.
# Exit status: setup.py's status, or nonzero for prerequisites/download/extraction.

# Disable inherited tracing/verbose mode before handling arguments or input.
set +xv
set -euo pipefail

setup_error() {
    printf '%s\n' "afterglow setup: $1" >&2
    exit 1
}

setup_main() {
    local python='' candidate non_interactive=false arg revision api_url
    for candidate in python3 python3.14 python3.13 python3.12 python3.11 python; do
        if command -v "$candidate" >/dev/null 2>&1 &&
            "$candidate" -I -c 'import sys; assert sys.version_info >= (3, 11); import tomllib' >/dev/null 2>&1; then
            python="$candidate"
            break
        fi
    done
    if [[ -z "$python" ]]; then
        setup_error 'Python >=3.11 with stdlib tomllib is required; nothing was installed.'
    fi
    command -v curl >/dev/null 2>&1 || setup_error 'curl is required; nothing was installed.'

    for arg in "$@"; do
        [[ "$arg" != -- ]] || break
        if [[ "$arg" == --non-interactive ]]; then
            non_interactive=true
        fi
    done
    if [[ "$non_interactive" == false && ! -t 0 ]]; then
        if ! ( : </dev/tty ) 2>/dev/null; then
            setup_error 'Interactive setup requires /dev/tty; use --non-interactive without a terminal.'
        fi
    fi

    umask 077
    work=$("$python" -I -c 'import tempfile; print(tempfile.mkdtemp(prefix="afterglow-setup-"))') ||
        setup_error 'Could not create temporary source directory.'
    # work is shell-global so the EXIT trap retains it after setup_main returns.
    trap 'rm -rf -- "$work"' EXIT
    trap 'exit 129' HUP
    trap 'exit 130' INT
    trap 'exit 143' TERM

    revision=$("$python" -I - <<'PY'
import os
import re
import sys
from urllib.parse import quote

ref = os.environ.get("AFTERGLOW_SETUP_REF", "dev")
if not ref or any(ord(char) < 32 or ord(char) == 127 for char in ref):
    sys.exit("afterglow setup: Invalid source ref.")
if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
    print(ref.lower())
else:
    print("https://api.github.com/repos/openstack-afterglow/openstack-afterglow/commits/" + quote(ref, safe=""))
PY
    ) || setup_error 'Could not select source revision.'

    if [[ "$revision" == https://api.github.com/repos/openstack-afterglow/openstack-afterglow/commits/* ]]; then
        api_url="$revision"
        curl --disable --fail --location --show-error --silent --proto '=https' --proto-redir '=https' \
            --output "$work/commit.json" "$api_url" || setup_error 'GitHub revision download failed.'
        revision=$("$python" -I - "$work/commit.json" <<'PY'
import json
import re
import sys

try:
    with open(sys.argv[1], encoding="utf-8") as source:
        revision = json.load(source)["sha"]
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError
except (OSError, ValueError, KeyError, TypeError):
    sys.exit("afterglow setup: Invalid GitHub revision response.")
print(revision.lower())
PY
        ) || setup_error 'Could not resolve immutable source revision.'
    fi

    curl --disable --fail --location --show-error --silent --proto '=https' --proto-redir '=https' \
        --output "$work/source.tar.gz" \
        "https://codeload.github.com/openstack-afterglow/openstack-afterglow/tar.gz/$revision" ||
        setup_error 'GitHub source archive download failed.'

    "$python" -I - "$work/source.tar.gz" "$work/source" "$revision" <<'PY'
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive, destination, revision = sys.argv[1:]
destination = Path(destination)
root = "openstack-afterglow-" + revision
try:
    with tarfile.open(archive, "r:gz") as source:
        members = source.getmembers()
        # Validate the entire archive before writing. Never use extractall or
        # trust archive modes/owners/links, including on Python 3.11.
        for member in members:
            path = PurePosixPath(member.name)
            if (path.is_absolute() or ".." in path.parts or "\\" in member.name
                    or not path.parts or path.parts[0] != root
                    or member.type not in (tarfile.DIRTYPE, tarfile.REGTYPE, tarfile.AREGTYPE)):
                raise ValueError
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open("xb") as outgoing:
                    shutil.copyfileobj(incoming, outgoing)
    if not (destination / root / "setup.py").is_file():
        raise ValueError
except (OSError, ValueError, tarfile.TarError):
    sys.exit("afterglow setup: Unsafe or invalid GitHub source archive.")
PY

    # Redirect only the child. Redirecting Bash's parser stdin would make
    # curl | bash read further terminal commands instead of reaching pipe EOF.
    if [[ "$non_interactive" == false && ! -t 0 ]]; then
        AFTERGLOW_SETUP_SOURCE_REVISION="$revision" \
            "$python" "$work/source/openstack-afterglow-$revision/setup.py" "$@" </dev/tty
    else
        AFTERGLOW_SETUP_SOURCE_REVISION="$revision" \
            "$python" "$work/source/openstack-afterglow-$revision/setup.py" "$@"
    fi
}

setup_main "$@"
