#!/bin/sh
# Install ONLY the passive collector. No package/network/service changes here.
# Usage: sudo sh install.sh /absolute/path/to/reviewed-root-owned-0600.json
# Prerequisites (Ubuntu/Debian, operator-managed): python3-bpfcc libbpfcc
# clang LLVM and matching running-kernel headers; modern Linux >=5.8 BPF support.
# Verify distro /usr/bin/python3 imports the native BCC package, not PyPI bcc.
# The example contains documentation addresses, NOT production scope.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
[ "$(id -u)" = 0 ] || { echo 'root_required' >&2; exit 1; }
[ "$#" = 1 ] || { echo 'one_reviewed_config_required' >&2; exit 1; }
case "$1" in /*) ;; *) echo 'absolute_config_required' >&2; exit 1 ;; esac
SOURCE=$(dirname -- "$0")
case "$SOURCE" in /*) ;; *) SOURCE="$(pwd -P)/$SOURCE" ;; esac
# Bootstrap only from stdlib: no root-executed project import before source
# ancestry and every consumed inode are protected. Retain directory FDs.
/usr/bin/python3 -I - "$SOURCE" "$1" <<'PY'
import os
import stat
import sys
from pathlib import Path
from importlib.machinery import SourceFileLoader
from types import ModuleType

def directory(path, create=False, mode=0o755):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for position, component in enumerate(path.parts[1:], 1):
            try:
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except FileNotFoundError:
                if not create or position != len(path.parts) - 1:
                    raise
                os.mkdir(component, mode=mode, dir_fd=fd)
                child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = child
            info = os.fstat(fd)
            if info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022:
                raise ValueError
        return fd
    except BaseException:
        os.close(fd)
        raise

def checked_file(parent, name, optional=False):
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=parent)
    except FileNotFoundError:
        if optional:
            return
        raise
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o022:
            raise ValueError
    finally:
        os.close(fd)

try:
    source = directory(sys.argv[1])
    try:
        for name in ('install.sh', 'collector.py', 'security.py', 'flow_filter.c', 'afterglow-flow-collector.service'):
            checked_file(source, name)
    finally:
        os.close(source)
    # Read checked source explicitly: neither cwd shadow modules nor a retained
    # __pycache__ may execute while installing with root authority.
    for name in ('security', 'collector'):
        module = ModuleType(name)
        module.__file__ = str(Path(sys.argv[1]) / (name + '.py'))
        sys.modules[name] = module
        code = SourceFileLoader(name, module.__file__).get_source(name)
        exec(compile(code, module.__file__, 'exec'), module.__dict__)
    from collector import validate_config
    from security import decode_json, protected_read
    payload = protected_read(sys.argv[2], mode=0o600)
    validate_config(decode_json(payload))
    for path, mode, names in (
        ('/opt/afterglow-flow', 0o755, ('collector.py', 'security.py', 'flow_filter.c')),
        ('/etc/afterglow-flow', 0o700, ('collector.json',)),
        ('/etc/systemd/system', 0o755, ('afterglow-flow-collector.service',)),
    ):
        parent = directory(path, create=True, mode=mode)
        try:
            for name in names:
                checked_file(parent, name, optional=True)
        finally:
            os.close(parent)
    parent = directory('/etc/afterglow-flow')
    try:
        fd = os.open('collector.json', os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
                     0o600, dir_fd=parent)
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), 0o600)
            output.write(payload)
    finally:
        os.close(parent)
except Exception:
    raise SystemExit('unsafe_install_inputs') from None
PY
getent group afterglow-flow-read >/dev/null || groupadd --system afterglow-flow-read
install -d -o root -g root -m 0755 /opt/afterglow-flow
install -d -o root -g root -m 0700 /etc/afterglow-flow
install -o root -g root -m 0644 "$SOURCE/security.py" "$SOURCE/flow_filter.c" /opt/afterglow-flow/
install -o root -g root -m 0755 "$SOURCE/collector.py" /opt/afterglow-flow/collector.py
install -o root -g root -m 0644 "$SOURCE/afterglow-flow-collector.service" /etc/systemd/system/afterglow-flow-collector.service
printf '%s\n' 'Installed only; service NOT started or enabled.' 'Review config and unit, then: systemctl daemon-reload; systemctl enable --now afterglow-flow-collector' 'Add observer-flow-read.conf to the existing observer unit and append --flow-snapshot-file /run/afterglow-flow/snapshot.json to its ExecStart; preserve all other options.' 'Restart that observer only after a fresh root:afterglow-flow-read 0640 snapshot exists. No observer capabilities are required.'
