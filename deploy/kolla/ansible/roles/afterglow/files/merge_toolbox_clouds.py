"""Merge one Afterglow cloud entry into the Kolla toolbox clouds.yaml.

The file is shared with Kolla's own clouds (for example ``kolla-admin-internal``).
Only the named cloud entry is replaced; sibling clouds are preserved. An
unreadable or malformed existing file fails closed instead of being replaced.

Input (stdin, JSON): {"name": "<cloud>", "entry": {...}}
Run inside the kolla-toolbox container as root; prints "changed" or "unchanged".
"""

import json
import os
import pwd
import stat
import sys
import tempfile

import yaml

CLOUDS_PATH = "/var/lib/ansible/.config/openstack/clouds.yaml"
OWNER = "ansible"


def merge_clouds(existing_text, cloud_name, entry):
    """Return (document, changed) with ``clouds[cloud_name]`` set and siblings kept."""
    if not isinstance(cloud_name, str) or not cloud_name:
        raise ValueError("cloud name must be a non-empty string")
    if not isinstance(entry, dict):
        raise ValueError("cloud entry must be a mapping")
    document = yaml.safe_load(existing_text) if existing_text and existing_text.strip() else {}
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ValueError("clouds.yaml root must be a mapping")
    clouds = document.get("clouds") or {}
    if not isinstance(clouds, dict):
        raise ValueError("clouds.yaml 'clouds' must be a mapping")
    updated = dict(document)
    updated["clouds"] = {**clouds, cloud_name: entry}
    return updated, updated != document


def _read_existing(path):
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None, None
    if not stat.S_ISREG(st.st_mode):
        raise RuntimeError("cloud configuration must be a regular file")
    with open(path, encoding="utf-8") as handle:
        return handle.read(), st


def main():
    request = json.loads(sys.stdin.read())
    owner = pwd.getpwnam(OWNER)
    existing, st = _read_existing(CLOUDS_PATH)
    document, changed = merge_clouds(existing, request["name"], request["entry"])
    up_to_date = (
        st is not None
        and not changed
        and st.st_uid == owner.pw_uid
        and st.st_gid == owner.pw_gid
        and stat.S_IMODE(st.st_mode) == 0o600
    )
    if up_to_date:
        print("unchanged")
        return
    directory = os.path.dirname(CLOUDS_PATH)
    fd, temporary = tempfile.mkstemp(prefix=".clouds.", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            os.fchmod(out.fileno(), 0o600)
            os.fchown(out.fileno(), owner.pw_uid, owner.pw_gid)
            out.write(yaml.safe_dump(document, default_flow_style=False, sort_keys=True))
        os.replace(temporary, CLOUDS_PATH)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("changed" if changed else "unchanged")


if __name__ == "__main__":
    main()
