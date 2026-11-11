"""Merge one Afterglow cloud entry into the Kolla toolbox clouds.yaml.

The file is shared with Kolla's own clouds (for example ``kolla-admin-internal``).
Only the named cloud entry is replaced; sibling clouds are preserved. An
unreadable or malformed existing file fails closed instead of being replaced.

Input (stdin, JSON): {"name": "...", "source_cloud": "...", "auth_overrides": {...}, "region_name": "...", "interface": "..."}
Run inside the kolla-toolbox container as root; prints "changed" or "unchanged".
"""

import copy
import json
import os
import pwd
import stat
import sys
import tempfile

import yaml

CLOUDS_PATH = "/var/lib/ansible/.config/openstack/clouds.yaml"
OWNER = "ansible"


def merge_clouds(existing_text, cloud_name, source_cloud_name, auth_overrides, region_name, interface):
    """Build the Afterglow CLI cloud from Kolla's configured admin cloud."""
    if not isinstance(cloud_name, str) or not cloud_name:
        raise ValueError("cloud name must be a non-empty string")
    if not isinstance(source_cloud_name, str) or not source_cloud_name:
        raise ValueError("source cloud name must be a non-empty string")
    if not isinstance(auth_overrides, dict) or not auth_overrides:
        raise ValueError("authentication overrides must be a non-empty mapping")
    document = yaml.safe_load(existing_text) if existing_text and existing_text.strip() else {}
    if document is None:
        document = {}
    if not isinstance(document, dict):
        raise ValueError("clouds.yaml root must be a mapping")
    clouds = document.get("clouds") or {}
    if not isinstance(clouds, dict):
        raise ValueError("clouds.yaml 'clouds' must be a mapping")
    source = clouds.get(source_cloud_name)
    if not isinstance(source, dict):
        raise ValueError("source cloud entry is missing or invalid")
    source_auth = source.get("auth")
    if not isinstance(source_auth, dict):
        raise ValueError("source cloud auth must be a mapping")
    auth = dict(source_auth)
    auth.update(auth_overrides)
    if not isinstance(auth.get("auth_url"), str) or not auth["auth_url"]:
        raise ValueError("source cloud auth requires auth_url")
    if not isinstance(auth.get("password"), str) or not auth["password"]:
        raise ValueError("authentication overrides require password")
    entry = copy.deepcopy(source)
    entry["auth"] = auth
    entry["auth_type"] = "password"
    entry["region_name"] = region_name
    entry["interface"] = interface
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
    document, changed = merge_clouds(
        existing,
        request["name"],
        request["source_cloud"],
        request["auth_overrides"],
        request["region_name"],
        request["interface"],
    )
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
