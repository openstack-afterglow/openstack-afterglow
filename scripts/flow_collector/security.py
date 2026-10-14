"""Root-owned collector input and atomic-handoff filesystem boundaries."""
from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path

MAX_ROWS = 1024
MAX_BYTES = 256 * 1024
MAX_COUNTER = (1 << 64) - 1
HOST_ID = re.compile(r"(?:compute|controller|storage):[a-z0-9][a-z0-9_.-]{0,252}")
INTERFACE = re.compile(r"[A-Za-z0-9_.-]{1,15}")


class FlowSnapshotError(Exception):
    """A fixed diagnostic code, never input data or packet information."""


def secure_directory(path):
    """Walk absolute directories without following links or writable ancestors.

    Returning an open directory FD also makes subsequent open/replace relative to
    the checked inode, rather than a second traversal of an attacker-changed path.
    """
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise FlowSnapshotError("unsafe_path")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise FlowSnapshotError("unsafe_directory")
        return fd
    except BaseException:
        os.close(fd)
        raise


def protected_read(path, *, mode=0o640):
    parent = None
    fd = None
    try:
        path = Path(path)
        parent = secure_directory(path.parent)
        fd = os.open(path.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) != mode:
            raise FlowSnapshotError("unsafe_file")
        if info.st_size > MAX_BYTES:
            raise FlowSnapshotError("snapshot_limit")
        with os.fdopen(fd, "rb") as handle:
            fd = None
            data = handle.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise FlowSnapshotError("snapshot_limit")
        return data
    except OSError:
        raise FlowSnapshotError("snapshot_unavailable") from None
    finally:
        if fd is not None:
            os.close(fd)
        if parent is not None:
            os.close(parent)


def decode_json(data):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError

    try:
        if len(data) > MAX_BYTES:
            raise ValueError
        return json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise FlowSnapshotError("invalid_json") from None
