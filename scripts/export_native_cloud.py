#!/usr/bin/env python3
"""Export the native-cloud-vm rootfs tar as a BIOS-bootable raw cloud disk.

Usage (root, Linux x86_64 builder):
  python3 scripts/export_native_cloud.py --rootfs ROOTFS.tar --output DISK.raw \
      --size-gib 8 --source-sha256 HEX

ROOTFS.tar is the trusted BuildKit ``type=tar`` export of the Dockerfile
``native-cloud-vm`` target, optionally compressed. It is fully validated before any
privileged operation: normalized relative names only, no duplicates, every
parent declared earlier as a directory (so nothing is extracted through a
symlink), hard links only to earlier regular files, lexically contained
symlink targets, and no device nodes or overlay whiteouts.

The disk is a sparse raw file with an MBR label and one bootable ext4
partition starting at 1 MiB, attached to a private loop device that is verified
to be backed by this export's own file. Numeric UID/GID, modes and link
identity are verified for every member after extraction. Nothing from the
rootfs is executed. Declared bootability additions are /etc/fstab, the
systemd-resolved /etc/resolv.conf stub link, /boot/grub (GRUB i386-pc boot code
installed from the trusted builder's grub-pc-bin modules, plus grub.cfg) and the
MBR boot code; each is recorded in the metadata. Rootfs shell scripts and GRUB
modinfo.sh are never sourced or executed by builder tools.

Outputs: DISK.raw, DISK.raw.sha256 (sha256sum format) and
DISK.raw.metadata.json. None may exist beforehand. Cleanup is attempted on all
exits; if unmount/detach fails the backing image is retained and reported.
The result is a conventional cloud disk derived
from the OCI root plus the declared additions; it is not an untouched OCI root,
not the protected OCI-root stage-1 path, and makes no security-parity claim.

Requirements: Linux x86_64, root, Python 3 standard library, util-linux
(losetup, sfdisk, mount, umount), e2fsprogs (mkfs.ext4, e2fsck, dumpe2fs) and
GRUB 2 grub-install and its builder-installed grub-pc-bin BIOS modules.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
import platform
import re
import secrets
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SECTOR_BYTES = 512
PARTITION_START_SECTOR = 2048
DEFAULT_SIZE_GIB = 8
MIN_SIZE_GIB = 4
MAX_SIZE_GIB = 64
FS_LABEL = "afterglow-root"
APP_USER = "appuser"
STATE_DIR = "var/lib/afterglow"
CONFIG_LINK = "app/afterglow.conf"
CONFIG_TARGET = "/var/lib/afterglow/afterglow.conf"
SERVICE = "afterglow-native.service"
RESOLV_STUB = "../run/systemd/resolve/stub-resolv.conf"
SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"
BUILDER_GRUB_MODULES = Path("/usr/lib/grub/i386-pc")
REQUIRED_TOOLS = ("losetup", "sfdisk", "mkfs.ext4", "e2fsck", "dumpe2fs", "mount", "umount", "grub-install")
CONTAINER_ENGINES = (
    "/usr/bin/dockerd",
    "/usr/bin/docker",
    "/usr/bin/containerd",
    "/usr/bin/podman",
    "/usr/sbin/runc",
    "/usr/bin/runc",
    "/usr/bin/crun",
)
IDENTITY_PACKAGES = (
    "linux-image-amd64",
    "initramfs-tools",
    "grub-pc-bin",
    "grub2-common",
    "systemd",
    "systemd-sysv",
    "cloud-init",
    "openssh-server",
    "ceph-common",
    "mariadb-server",
    "redis-server",
)
XATTR_PREFIX = "SCHILY.xattr."
KERNEL_RELEASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~-]*")
MAX_MESSAGE = 240
INTERRUPT_SIGNALS = (signal.SIGTERM, signal.SIGHUP, signal.SIGINT)


class ExportError(Exception):
    pass


def _quote(name: str) -> str:
    text = repr(name)
    return text if len(text) <= MAX_MESSAGE else text[:MAX_MESSAGE] + "..."


# ── Arguments and host ───────────────────────────────────────────────────────


def _sha256_argument(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise argparse.ArgumentTypeError("must be 64 hexadecimal characters")
    return normalized


def _size_argument(value: str) -> int:
    try:
        size = int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError("must be an integer number of GiB") from None
    if not MIN_SIZE_GIB <= size <= MAX_SIZE_GIB:
        raise argparse.ArgumentTypeError(f"must be between {MIN_SIZE_GIB} and {MAX_SIZE_GIB}")
    return size


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="export_native_cloud.py",
        description="Export the native-cloud-vm rootfs tar as a BIOS-bootable raw disk.",
    )
    parser.add_argument("--rootfs", type=Path, required=True, help="BuildKit type=tar rootfs (optionally compressed)")
    parser.add_argument("--output", type=Path, required=True, help="raw disk path to create")
    parser.add_argument("--size-gib", type=_size_argument, default=DEFAULT_SIZE_GIB, help="virtual disk size")
    parser.add_argument(
        "--source-sha256", type=_sha256_argument, required=True, help="SHA-256 of the Afterglow source bundle"
    )
    return parser.parse_args(argv)


def require_host(which=shutil.which) -> dict:
    if sys.platform != "linux":
        raise ExportError("requires a Linux builder")
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise ExportError("requires a Linux amd64 (x86_64) builder")
    if os.geteuid() != 0:
        raise ExportError("requires root for the private loop device, mount and GRUB installation")
    tools = {}
    for name in REQUIRED_TOOLS:
        path = which(name, path=SAFE_PATH)
        if not path:
            raise ExportError(f"missing required tool: {name}")
        tools[name] = path
    tools["udevadm"] = which("udevadm", path=SAFE_PATH)
    return tools


@dataclass(frozen=True)
class ExportPaths:
    rootfs: Path
    output: Path
    partial: Path
    checksum: Path
    metadata: Path


def prepare_paths(rootfs: Path, output: Path) -> ExportPaths:
    rootfs = Path(os.path.abspath(rootfs))
    try:
        rootfs_stat = os.stat(rootfs)
    except FileNotFoundError:
        raise ExportError("rootfs tar does not exist") from None
    if not stat.S_ISREG(rootfs_stat.st_mode):
        raise ExportError("rootfs must be a regular file")
    output = Path(os.path.abspath(output))
    parent = Path(os.path.realpath(output.parent))
    if not parent.is_dir():
        raise ExportError("output directory does not exist")
    for forbidden in ("/dev", "/proc", "/sys"):
        if parent == Path(forbidden) or Path(forbidden) in parent.parents:
            raise ExportError("output must be a regular file outside /dev, /proc and /sys")
    output = parent / output.name
    paths = ExportPaths(
        rootfs=rootfs,
        output=output,
        partial=output.with_name(output.name + ".partial"),
        checksum=output.with_name(output.name + ".sha256"),
        metadata=output.with_name(output.name + ".metadata.json"),
    )
    for path in (paths.output, paths.partial, paths.checksum, paths.metadata):
        if os.path.lexists(path):
            raise ExportError(f"refusing to replace existing path: {path.name}")
    if Path(os.path.realpath(rootfs)) == output:
        raise ExportError("output must differ from the rootfs tar")
    return paths


# ── Rootfs tar validation and extraction ─────────────────────────────────────


def normalize_member_name(name: str) -> str:
    """Return the archive-relative path, "" for the archive root; reject unsafe names."""
    if "\x00" in name or name.startswith("/"):
        raise ExportError(f"absolute or NUL member path: {_quote(name)}")
    raw = name[2:] if name.startswith("./") else name
    raw = raw.rstrip("/")
    if raw in ("", "."):
        return ""
    parts = raw.split("/")
    if any(part in ("", ".", "..") for part in parts):
        raise ExportError(f"unsafe member path: {_quote(name)}")
    if parts[-1].startswith(".wh."):
        raise ExportError(f"overlay whiteout in flattened rootfs: {_quote(name)}")
    return raw


def check_symlink_target(name: str, target: str) -> None:
    """Reject empty targets and targets that lexically climb above the rootfs."""
    if not target or "\x00" in target:
        raise ExportError(f"invalid symlink target: {_quote(name)}")
    stack = [] if target.startswith("/") else name.split("/")[:-1]
    for part in target.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not stack:
                raise ExportError(f"symlink target escapes the rootfs: {_quote(name)}")
            stack.pop()
        else:
            stack.append(part)


@dataclass
class RootfsPlan:
    members: list = field(default_factory=list)
    kinds: dict = field(default_factory=dict)
    xattrs: dict = field(default_factory=dict)
    regular_bytes: int = 0


def scan_rootfs(tar: tarfile.TarFile) -> RootfsPlan:
    plan = RootfsPlan()
    root_seen = False
    by_name = {}
    for info in tar:
        name = normalize_member_name(info.name)
        if name == "":
            if not info.isdir() or root_seen:
                raise ExportError("archive root entry must be a single directory")
            root_seen = True
            info.name = "."
            plan.kinds["."] = "dir"
            plan.members.append(info)
            continue
        if name in plan.kinds:
            raise ExportError(f"duplicate member: {_quote(name)}")
        parts = name.split("/")
        for depth in range(1, len(parts)):
            if plan.kinds.get("/".join(parts[:depth])) != "dir":
                raise ExportError(f"member parent is not an earlier directory entry: {_quote(name)}")
        if info.isdir():
            kind = "dir"
        elif info.isreg():
            kind = "file"
            plan.regular_bytes += info.size
        elif info.issym():
            kind = "symlink"
            check_symlink_target(name, info.linkname)
        elif info.islnk():
            kind = "hardlink"
            target = normalize_member_name(info.linkname)
            if plan.kinds.get(target) not in ("file", "hardlink"):
                raise ExportError(f"hard link target is not an earlier regular file: {_quote(name)}")
            info.linkname = target
            original = by_name[target]
            if (info.uid, info.gid, info.mode & 0o7777) != (original.uid, original.gid, original.mode & 0o7777):
                raise ExportError(f"hard link metadata differs from its target: {_quote(name)}")
        elif info.isfifo():
            kind = "fifo"
        else:
            raise ExportError(f"unsupported member type {info.type!r}: {_quote(name)}")
        info.name = name
        by_name[name] = info
        plan.kinds[name] = kind
        plan.members.append(info)
        attributes = {
            key[len(XATTR_PREFIX) :]: value
            for key, value in info.pax_headers.items()
            if key.startswith(XATTR_PREFIX)
        }
        if attributes:
            plan.xattrs[name] = attributes
    if not any(name != "." for name in plan.kinds):
        raise ExportError("rootfs tar is empty")
    return plan


def extract_rootfs(tar: tarfile.TarFile, plan: RootfsPlan, root: Path) -> dict:
    """Extract validated members with numeric ownership; apply capability/user xattrs."""
    tar.errorlevel = 2
    options = {"filter": "fully_trusted"} if hasattr(tarfile, "fully_trusted_filter") else {}
    previous = os.umask(0o022)
    try:
        tar.extractall(path=root, members=plan.members, numeric_owner=True, **options)
    finally:
        os.umask(previous)
    applied = skipped = 0
    for name, attributes in sorted(plan.xattrs.items()):
        path = root / name
        is_link = stat.S_ISLNK(os.lstat(path).st_mode)
        for key, value in sorted(attributes.items()):
            allowed = key == "security.capability" or key.startswith("user.")
            if is_link or not allowed or not hasattr(os, "setxattr"):
                skipped += 1
                continue
            raw = value.encode("utf-8", "surrogateescape") if isinstance(value, str) else value
            os.setxattr(path, key, raw, follow_symlinks=False)
            applied += 1
    return {"xattrs_applied": applied, "xattrs_skipped": skipped}


_KIND_CHECK = {
    "dir": stat.S_ISDIR,
    "file": stat.S_ISREG,
    "hardlink": stat.S_ISREG,
    "symlink": stat.S_ISLNK,
    "fifo": stat.S_ISFIFO,
}


def verify_extraction(plan: RootfsPlan, root: Path, check_owner: bool) -> int:
    """Confirm type, numeric owner, mode, size and link identity for every member."""
    for info in plan.members:
        kind = plan.kinds[info.name]
        path = root / info.name
        status = os.lstat(path)
        if not _KIND_CHECK[kind](status.st_mode):
            raise ExportError(f"extracted type differs from the archive: {_quote(info.name)}")
        if kind == "symlink":
            if os.readlink(path) != info.linkname:
                raise ExportError(f"symlink target not preserved: {_quote(info.name)}")
        elif kind == "hardlink":
            target = os.lstat(root / info.linkname)
            if (target.st_dev, target.st_ino) != (status.st_dev, status.st_ino):
                raise ExportError(f"hard link identity not preserved: {_quote(info.name)}")
            continue
        elif stat.S_IMODE(status.st_mode) != info.mode & 0o7777:
            raise ExportError(f"mode not preserved: {_quote(info.name)}")
        if kind == "file" and status.st_size != info.size:
            raise ExportError(f"file size not preserved: {_quote(info.name)}")
        if check_owner and (status.st_uid, status.st_gid) != (info.uid, info.gid):
            raise ExportError(f"numeric owner not preserved: {_quote(info.name)}")
    return len(plan.members)


# ── Rootfs inspection (read-only; nothing in the rootfs is executed) ─────────


def resolve_in_root(root: Path, guest_path: str, max_links: int = 40):
    """Resolve an absolute guest path with symlinks interpreted inside root.

    Returns the host path of the existing final object, or None if missing.
    """
    pending = [part for part in guest_path.split("/") if part not in ("", ".")]
    resolved: list[str] = []
    links = 0
    while pending:
        part = pending.pop(0)
        if part == "..":
            if resolved:
                resolved.pop()
            continue
        candidate = root.joinpath(*resolved, part)
        try:
            status = os.lstat(candidate)
        except (FileNotFoundError, NotADirectoryError):
            return None
        if stat.S_ISLNK(status.st_mode):
            links += 1
            if links > max_links:
                raise ExportError(f"symlink loop while resolving {guest_path}")
            target = os.readlink(candidate)
            if target.startswith("/"):
                resolved = []
            pending = [p for p in target.split("/") if p not in ("", ".")] + pending
            continue
        if pending and not stat.S_ISDIR(status.st_mode):
            return None
        resolved.append(part)
    return root.joinpath(*resolved)


def _read_key_values(path: Path) -> dict:
    values = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, separator, value = line.partition("=")
        if separator and key.strip() and not key.lstrip().startswith("#"):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key.strip()] = value
    return values


def parse_passwd_entry(path: Path, user: str):
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        fields = line.split(":")
        if len(fields) >= 7 and fields[0] == user:
            return int(fields[2]), int(fields[3])
    return None


def parse_dpkg_versions(path: Path, packages) -> dict:
    wanted = set(packages)
    versions = {}
    for stanza in path.read_text(encoding="utf-8", errors="replace").split("\n\n"):
        fields = {}
        for line in stanza.splitlines():
            if line and not line[0].isspace():
                key, _, value = line.partition(":")
                fields[key] = value.strip()
        name = fields.get("Package")
        if name in wanted and fields.get("Status") == "install ok installed":
            versions[name] = fields.get("Version", "")
    return dict(sorted(versions.items()))


def grub_upstream_version(text: str):
    match = re.search(r"(\d+\.\d+(?:\.\d+)?)", text)
    return match.group(1) if match else None


def sha256_file(path: Path, limit=None) -> str:
    digest = hashlib.sha256()
    remaining = limit
    with open(path, "rb") as handle:
        while remaining is None or remaining > 0:
            size = 1 << 20 if remaining is None else min(1 << 20, remaining)
            block = handle.read(size)
            if not block:
                break
            digest.update(block)
            if remaining is not None:
                remaining -= len(block)
    return digest.hexdigest()


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except FileNotFoundError:
        return False


def _require_regular(root: Path, relative: str, what: str) -> Path:
    path = root / relative
    try:
        status = os.lstat(path)
    except FileNotFoundError:
        raise ExportError(f"rootfs is missing {what}: /{relative}") from None
    if not stat.S_ISREG(status.st_mode):
        raise ExportError(f"rootfs {what} must be a regular file: /{relative}")
    return path


def inspect_rootfs(root: Path, check_owner: bool = True) -> dict:
    """Validate the native-cloud-vm guest contract and return base identity."""
    init = resolve_in_root(root, "/sbin/init")
    if init is None or init.name != "systemd" or not init.is_file():
        raise ExportError("/sbin/init must resolve to systemd")

    boot = root / "boot"
    if not stat.S_ISDIR(os.lstat(boot).st_mode):
        raise ExportError("/boot must be a directory")
    kernels = sorted(
        entry.name[len("vmlinuz-") :]
        for entry in boot.iterdir()
        if entry.name.startswith("vmlinuz-") and stat.S_ISREG(os.lstat(entry).st_mode)
    )
    if len(kernels) != 1:
        raise ExportError(f"expected exactly one /boot/vmlinuz-*, found {len(kernels)}")
    kernel = kernels[0]
    if not KERNEL_RELEASE.fullmatch(kernel):
        raise ExportError("unexpected kernel release name")
    initrd = _require_regular(root, f"boot/initrd.img-{kernel}", "initramfs")
    if os.lstat(initrd).st_size == 0:
        raise ExportError("initramfs is empty")
    modules = resolve_in_root(root, f"/usr/lib/modules/{kernel}")
    if modules is None or not modules.is_dir():
        raise ExportError("kernel modules for the boot kernel are missing")
    grub_boot = root / "boot" / "grub"
    if os.path.lexists(grub_boot):
        if not stat.S_ISDIR(os.lstat(grub_boot).st_mode) or any(grub_boot.iterdir()):
            raise ExportError("/boot/grub must be absent or empty before export")

    grub_modules = resolve_in_root(root, "/usr/lib/grub/i386-pc")
    if grub_modules is None or not grub_modules.is_dir():
        raise ExportError("rootfs GRUB i386-pc modules (grub-pc-bin) are missing")
    for name in ("boot.img", "kernel.img", "modinfo.sh"):
        if not _is_regular(grub_modules / name):
            raise ExportError(f"rootfs GRUB i386-pc directory is missing {name}")
    modinfo = _read_key_values(grub_modules / "modinfo.sh")
    if (modinfo.get("grub_modinfo_target_cpu"), modinfo.get("grub_modinfo_platform")) != ("i386", "pc"):
        raise ExportError("rootfs GRUB modules are not i386-pc")
    grub_version = modinfo.get("grub_package_version") or modinfo.get("grub_version") or ""
    if not grub_upstream_version(grub_version):
        raise ExportError("rootfs GRUB version is unknown")

    machine_id = root / "etc" / "machine-id"
    if os.path.lexists(machine_id):
        status = os.lstat(machine_id)
        if not stat.S_ISREG(status.st_mode) or status.st_size != 0:
            raise ExportError("/etc/machine-id must be empty so every boot gets a fresh identity")
    ssh_dir = resolve_in_root(root, "/etc/ssh")
    if ssh_dir is None or not ssh_dir.is_dir() or not _is_regular(ssh_dir / "sshd_config"):
        raise ExportError("sshd configuration is missing")
    if any(entry.name.startswith("ssh_host_") for entry in ssh_dir.iterdir()):
        raise ExportError("rootfs contains baked SSH host keys")
    for guest_path, what in (("/usr/sbin/sshd", "sshd"), ("/usr/bin/cloud-init", "cloud-init")):
        if resolve_in_root(root, guest_path) is None:
            raise ExportError(f"rootfs is missing {what}")
    cloud_state = root / "var" / "lib" / "cloud"
    if os.path.lexists(cloud_state) and (
        not stat.S_ISDIR(os.lstat(cloud_state).st_mode) or any(cloud_state.iterdir())
    ):
        raise ExportError("rootfs contains cloud-init instance state")
    for guest_path in CONTAINER_ENGINES:
        if resolve_in_root(root, guest_path) is not None:
            raise ExportError(f"rootfs contains a container engine: {guest_path}")

    owner = parse_passwd_entry(_require_regular(root, "etc/passwd", "passwd"), APP_USER)
    if owner is None:
        raise ExportError(f"rootfs has no {APP_USER} account")
    state = root / STATE_DIR
    status = os.lstat(state)
    if not stat.S_ISDIR(status.st_mode):
        raise ExportError(f"/{STATE_DIR} must be a directory")
    if any(state.iterdir()):
        raise ExportError(f"/{STATE_DIR} must be empty: no credentials or state are baked")
    if stat.S_IMODE(status.st_mode) != 0o700 or (check_owner and (status.st_uid, status.st_gid) != owner):
        raise ExportError(f"/{STATE_DIR} must be {APP_USER}-owned with mode 0700")
    link = root / CONFIG_LINK
    if not os.path.islink(link) or os.readlink(link) != CONFIG_TARGET:
        raise ExportError(f"/{CONFIG_LINK} must be a symlink to {CONFIG_TARGET}")
    _require_regular(root, "app/scripts/native_vm.py", "native supervisor")
    if resolve_in_root(root, "/app/.venv/bin/python") is None:
        raise ExportError("rootfs is missing /app/.venv/bin/python")
    _require_regular(root, f"etc/systemd/system/{SERVICE}", "supervisor unit")
    if not os.path.islink(root / "etc/systemd/system/multi-user.target.wants" / SERVICE):
        raise ExportError(f"{SERVICE} is not enabled")

    os_release_path = resolve_in_root(root, "/etc/os-release")
    if os_release_path is None:
        raise ExportError("rootfs has no os-release")
    os_release = _read_key_values(os_release_path)
    if os_release.get("ID") != "debian":
        raise ExportError("native-cloud-vm rootfs must be Debian")
    return {
        "os_release": {
            key: os_release[key]
            for key in ("ID", "VERSION_ID", "VERSION_CODENAME", "PRETTY_NAME")
            if key in os_release
        },
        "kernel_release": kernel,
        "kernel_sha256": sha256_file(boot / f"vmlinuz-{kernel}"),
        "initramfs_sha256": sha256_file(initrd),
        "init": "systemd",
        "grub_modules_version": grub_version,
        "grub_modules_dir": "/usr/lib/grub/i386-pc",
        "app_user": {"name": APP_USER, "uid": owner[0], "gid": owner[1]},
        "dpkg": parse_dpkg_versions(_require_regular(root, "var/lib/dpkg/status", "dpkg status"), IDENTITY_PACKAGES),
    }


# ── Boot additions ───────────────────────────────────────────────────────────


def fstab_text(fs_uuid: str) -> str:
    return (
        "# Root filesystem; written by scripts/export_native_cloud.py\n"
        f"UUID={fs_uuid} / ext4 defaults,errors=remount-ro 0 1\n"
    )


def grub_cfg_text(fs_uuid: str, kernel: str) -> str:
    cmdline = f"root=UUID={fs_uuid} ro console=tty0 console=ttyS0,115200n8"
    return (
        "# Written by scripts/export_native_cloud.py (BIOS, serial console ttyS0)\n"
        "insmod serial\n"
        "serial --unit=0 --speed=115200 --word=8 --parity=no --stop=1\n"
        "terminal_input serial console\n"
        "terminal_output serial console\n"
        "set default=0\n"
        "set timeout=1\n"
        "insmod part_msdos\n"
        "insmod ext2\n"
        f"search --no-floppy --fs-uuid --set=root {fs_uuid}\n"
        f"menuentry 'Afterglow native cloud (Linux {kernel})' {{\n"
        f"\tlinux /boot/vmlinuz-{kernel} {cmdline}\n"
        f"\tinitrd /boot/initrd.img-{kernel}\n"
        "}\n"
    )


def _require_real_parents(root: Path, relative: str) -> Path:
    current = root
    for part in relative.split("/")[:-1]:
        current = current / part
        try:
            status = os.lstat(current)
        except FileNotFoundError:
            raise ExportError(f"boot addition parent is missing: /{relative}") from None
        if not stat.S_ISDIR(status.st_mode):
            raise ExportError(f"boot addition parent is not a directory: /{relative}")
    return root / relative


def write_boot_file(root: Path, relative: str, text: str, mode: int = 0o644) -> dict:
    path = _require_real_parents(root, relative)
    if os.path.lexists(path) and not stat.S_ISREG(os.lstat(path).st_mode):
        raise ExportError(f"refusing to replace non-regular /{relative}")
    data = text.encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".afterglow-boot-", dir=path.parent)
    try:
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(descriptor, view) :]
            if os.geteuid() == 0:
                os.fchown(descriptor, 0, 0)
            os.fchmod(descriptor, mode)
        finally:
            os.close(descriptor)
        # Replace the pathname, never truncate an archive inode that may also
        # be linked at another path in the guest.
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    return {"path": relative, "kind": "file", "sha256": hashlib.sha256(data).hexdigest(), "mode": f"{mode:04o}"}


MOUNTPOINTS = (("dev", 0o755), ("proc", 0o555), ("sys", 0o555), ("run", 0o755), ("tmp", 0o1777))


def ensure_mountpoints(root: Path) -> list:
    """Create missing top-level API filesystem mountpoints systemd needs; record each."""
    records = []
    for name, mode in MOUNTPOINTS:
        path = root / name
        if os.path.lexists(path):
            if not stat.S_ISDIR(os.lstat(path).st_mode):
                raise ExportError(f"/{name} must be a directory")
            continue
        os.mkdir(path)
        os.chmod(path, mode)
        records.append({"path": name, "kind": "directory", "mode": f"{mode:04o}"})
    return records


def link_resolv_conf(root: Path):
    if resolve_in_root(root, "/usr/lib/systemd/systemd-resolved") is None:
        return None
    path = _require_real_parents(root, "etc/resolv.conf")
    record = {"path": "etc/resolv.conf", "kind": "symlink", "target": RESOLV_STUB}
    if os.path.lexists(path):
        status = os.lstat(path)
        if stat.S_ISLNK(status.st_mode) and os.readlink(path) == RESOLV_STUB:
            return {**record, "changed": False}
        if stat.S_ISDIR(status.st_mode):
            raise ExportError("/etc/resolv.conf is a directory")
        os.unlink(path)
    os.symlink(RESOLV_STUB, path)
    if os.geteuid() == 0:
        os.lchown(path, 0, 0)
    return {**record, "changed": True}


def tree_records(root: Path, relative: str) -> list:
    records = []
    for directory, directories, files in os.walk(root / relative):
        directories.sort()
        for name in sorted(files):
            path = Path(directory) / name
            status = os.lstat(path)
            entry = path.relative_to(root).as_posix()
            if stat.S_ISLNK(status.st_mode):
                records.append({"path": entry, "kind": "symlink", "target": os.readlink(path)})
            elif stat.S_ISREG(status.st_mode):
                records.append({"path": entry, "kind": "file", "sha256": sha256_file(path), "size": status.st_size})
    return records


# ── Disk layout and privileged helpers ───────────────────────────────────────


def partition_layout(size_gib: int) -> dict:
    size_bytes = size_gib * 1024**3
    total_sectors = size_bytes // SECTOR_BYTES
    return {
        "size_bytes": size_bytes,
        "total_sectors": total_sectors,
        "start_sector": PARTITION_START_SECTOR,
        "sectors": total_sectors - PARTITION_START_SECTOR,
    }


def sfdisk_script(disk_id: int, layout: dict) -> str:
    return (
        "label: dos\n"
        f"label-id: 0x{disk_id:08x}\n"
        "unit: sectors\n"
        "\n"
        f"start={layout['start_sector']}, size={layout['sectors']}, type=83, bootable\n"
    )


def parse_dumpe2fs(text: str) -> dict:
    fields = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            fields.setdefault(key.strip(), value.strip())
    try:
        block_count = int(fields["Block count"])
        block_size = int(fields["Block size"])
    except (KeyError, ValueError):
        raise ExportError("could not read the root filesystem superblock") from None
    return {
        "uuid": fields.get("Filesystem UUID", ""),
        "label": fields.get("Filesystem volume name", ""),
        "features": fields.get("Filesystem features", "").split(),
        "block_count": block_count,
        "block_size": block_size,
    }


def run(argv, *, input_text=None, timeout=900) -> str:
    try:
        result = subprocess.run(
            [str(arg) for arg in argv],
            input=input_text,
            env={"PATH": SAFE_PATH, "LC_ALL": "C"},
            stdin=None if input_text is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ExportError(f"{Path(str(argv[0])).name} timed out") from None
    if result.returncode != 0:
        detail = " | ".join(result.stderr.strip().splitlines()[-6:])[:600]
        raise ExportError(f"{Path(str(argv[0])).name} exited with status {result.returncode}: {detail}")
    return result.stdout


def attach_loop(tools: dict, image: Path) -> str:
    device = run([tools["losetup"], "--find", "--show", "--partscan", image]).strip()
    if not re.fullmatch(r"/dev/loop[0-9]+", device):
        raise ExportError("losetup returned an unexpected device name")
    return device


def verify_loop(device: str, image: Path) -> None:
    name = os.path.basename(device)
    if not stat.S_ISBLK(os.stat(device).st_mode):
        raise ExportError("loop device is not a block device")
    backing = Path(f"/sys/block/{name}/loop/backing_file").read_text().strip()
    if backing != os.path.realpath(image):
        raise ExportError("loop device is not backed by this export's image")


def wait_partition(tools: dict, device: str) -> str:
    name = os.path.basename(device)
    partition = f"{device}p1"
    marker = Path(f"/sys/block/{name}/{name}p1/partition")
    for _ in range(100):
        if marker.is_file() and os.path.exists(partition) and stat.S_ISBLK(os.stat(partition).st_mode):
            if marker.read_text().strip() != "1":
                break
            return partition
        if tools.get("udevadm"):
            subprocess.run(
                [tools["udevadm"], "settle", "--timeout=2"],
                env={"PATH": SAFE_PATH},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        time.sleep(0.1)
    raise ExportError("loop partition device did not appear")


def builder_grub_identity(tools: dict) -> dict:
    # grub-install sources modinfo.sh. Never point it at a rootfs-supplied
    # directory: noexec does not prevent a shell from sourcing that file.
    for name in ("boot.img", "kernel.img", "modinfo.sh"):
        if not _is_regular(BUILDER_GRUB_MODULES / name):
            raise ExportError(f"missing builder BIOS GRUB asset: {name}")
    version = run([tools["grub-install"], "--version"]).strip()
    upstream = grub_upstream_version(version)
    if not upstream:
        raise ExportError("builder GRUB version is unknown")
    return {
        "path": "boot/grub/i386-pc",
        "kind": "builder-bios-grub",
        "source_directory": str(BUILDER_GRUB_MODULES),
        "version": version,
        "upstream_version": upstream,
        "source_sha256": {
            name: sha256_file(BUILDER_GRUB_MODULES / name)
            for name in ("boot.img", "kernel.img", "modinfo.sh")
        },
    }


def build_metadata(
    *,
    source_sha256: str,
    rootfs: dict,
    identity: dict,
    additions: list,
    disk: dict,
    filesystem: dict,
    ownership: dict,
    exporter: dict,
) -> dict:
    return {
        "schema": 1,
        "kind": "afterglow-native-cloud-disk",
        "source": {
            "bundle_sha256": source_sha256,
            "dockerfile_target": "native-cloud-vm",
            "derived_from_target": "native-vm",
            "rootfs_tar_sha256": rootfs["sha256"],
            "rootfs_tar_bytes": rootfs["bytes"],
            "rootfs_members": rootfs["members"],
            "rootfs_regular_bytes": rootfs["regular_bytes"],
        },
        "base_identity": identity,
        "boot_additions": additions,
        "disk": disk,
        "root_filesystem": filesystem,
        "ownership": ownership,
        "exporter": exporter,
        "guest": {
            "pid1": "systemd",
            "boot": "bios-i386-pc",
            "console": "ttyS0,115200n8",
            "service": SERVICE,
            "service_user": APP_USER,
            "state_dir": "/" + STATE_DIR,
            "config_link": "/" + CONFIG_LINK,
            "cloud_init_user": "debian",
            "ssh_host_keys": "generated on first boot; none baked",
            "machine_id": "empty; generated on first boot",
            "container_engine": None,
        },
        "claims": {
            "conventional_cloud_disk": True,
            "derived_from_oci_root_plus_declared_additions": True,
            "untouched_oci_root": False,
            "protected_oci_root_stage1": False,
            "security_parity": False,
        },
    }


# ── Orchestration ────────────────────────────────────────────────────────────


@dataclass
class Resources:
    tools: dict
    image: Path | None = None
    loop: str | None = None
    mountpoint: Path | None = None
    workspace: Path | None = None
    mounted: bool = False

    def release(self) -> list:
        """Unmount, detach and remove the mountpoint; never detach a still-mounted loop.

        Interrupting signals are ignored meanwhile so cleanup itself completes.
        """
        shielded = {}
        if threading.current_thread() is threading.main_thread():
            for signum in INTERRUPT_SIGNALS:
                shielded[signum] = signal.signal(signum, signal.SIG_IGN)
        errors = []
        try:
            if self.mounted and self.mountpoint is not None:
                try:
                    run([self.tools["umount"], self.mountpoint], timeout=120)
                    self.mounted = False
                except (ExportError, OSError) as exc:
                    errors.append(f"umount: {exc}")
            if self.loop is not None and not self.mounted:
                try:
                    if self.image is None:
                        raise ExportError("missing loop backing-file identity")
                    verify_loop(self.loop, self.image)
                    run([self.tools["losetup"], "--detach", self.loop], timeout=120)
                    self.loop = None
                except (ExportError, OSError) as exc:
                    errors.append(f"losetup --detach: {exc}")
            if self.mountpoint is not None and not self.mounted:
                try:
                    self.mountpoint.rmdir()
                    self.mountpoint = None
                except OSError as exc:
                    errors.append(f"rmdir mountpoint: {exc.strerror}")
            if self.workspace is not None and self.mountpoint is None:
                try:
                    self.workspace.rmdir()
                    self.workspace = None
                except OSError as exc:
                    errors.append(f"rmdir workspace: {exc.strerror}")
        finally:
            for signum, handler in shielded.items():
                signal.signal(signum, handler)
        return errors


@contextmanager
def defer_interrupts():
    # Preserve pending signals until the acquired resource is tracked. Linux
    # builder only: no signal may land between mount/attach and bookkeeping.
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, INTERRUPT_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _interrupt(signum, _frame):
    raise ExportError(f"interrupted by signal {signum}")


def _create_exclusive(path: Path, text: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o644)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except BaseException:
        path.unlink(missing_ok=True)
        raise


def input_identity(status: os.stat_result) -> tuple:
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns, status.st_ctime_ns)


def export(args: argparse.Namespace, tools: dict) -> dict:
    paths = prepare_paths(args.rootfs, args.output)
    builder_grub = builder_grub_identity(tools)
    layout = partition_layout(args.size_gib)
    fs_uuid = str(uuid.uuid4())
    disk_id = secrets.randbits(32) or 1
    resources = Resources(tools)
    created = False
    succeeded = False
    try:
        with open(paths.rootfs, "rb") as rootfs_file:
            rootfs_status = os.fstat(rootfs_file.fileno())
            if not stat.S_ISREG(rootfs_status.st_mode):
                raise ExportError("rootfs must be a regular file")
            digest = hashlib.sha256()
            for block in iter(lambda: rootfs_file.read(1 << 20), b""):
                digest.update(block)
            rootfs_file.seek(0)
            with tarfile.open(fileobj=rootfs_file, mode="r:*") as tar:
                plan = scan_rootfs(tar)
                descriptor = os.open(paths.partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
                created = True
                try:
                    os.ftruncate(descriptor, layout["size_bytes"])
                finally:
                    os.close(descriptor)
                run([tools["sfdisk"], "--quiet", paths.partial], input_text=sfdisk_script(disk_id, layout))
                resources.image = paths.partial
                with defer_interrupts():
                    resources.loop = attach_loop(tools, paths.partial)
                verify_loop(resources.loop, paths.partial)
                partition = wait_partition(tools, resources.loop)
                run(
                    [
                        tools["mkfs.ext4"],
                        "-q",
                        "-F",
                        "-L",
                        FS_LABEL,
                        "-U",
                        fs_uuid,
                        "-O",
                        "^metadata_csum_seed,^orphan_file",
                        "-E",
                        "root_owner=0:0",
                        partition,
                    ]
                )
                resources.workspace = Path(tempfile.mkdtemp(prefix="afterglow-native-cloud-"))
                resources.mountpoint = resources.workspace / "root"
                resources.mountpoint.mkdir(mode=0o700)
                with defer_interrupts():
                    run(
                        [tools["mount"], "-t", "ext4", "-o", "nodev,nosuid,noexec", partition, resources.mountpoint]
                    )
                    resources.mounted = True
                root = resources.mountpoint
                ownership = extract_rootfs(tar, plan, root)
                ownership["verified_members"] = verify_extraction(plan, root, check_owner=True)
                # The input is read three times (hash, scan, extract); any write in between
                # changes ctime, so the recorded digest must still describe the extracted bytes.
                after_status = os.fstat(rootfs_file.fileno())
                rootfs_file.seek(0)
                recheck = hashlib.sha256()
                for block in iter(lambda: rootfs_file.read(1 << 20), b""):
                    recheck.update(block)
                if recheck.hexdigest() != digest.hexdigest() or input_identity(after_status) != input_identity(
                    rootfs_status
                ):
                    raise ExportError("rootfs tar changed while it was being exported")
                ownership["numeric_owner"] = True
                identity = inspect_rootfs(root)
                additions = [builder_grub]
                additions.extend(ensure_mountpoints(root))
                additions.append(write_boot_file(root, "etc/fstab", fstab_text(fs_uuid)))
                resolv = link_resolv_conf(root)
                if resolv is not None:
                    additions.append(resolv)
                run(
                    [
                        tools["grub-install"],
                        "--target=i386-pc",
                        f"--directory={BUILDER_GRUB_MODULES}",
                        f"--boot-directory={root / 'boot'}",
                        "--modules=part_msdos ext2 biosdisk",
                        "--locales=",
                        "--fonts=",
                        "--themes=",
                        "--no-floppy",
                        resources.loop,
                    ]
                )
                write_boot_file(root, "boot/grub/grub.cfg", grub_cfg_text(fs_uuid, identity["kernel_release"]))
                additions.extend(tree_records(root, "boot/grub"))
                os.sync()
                with defer_interrupts():
                    run([tools["umount"], root], timeout=300)
                    resources.mounted = False
                run([tools["e2fsck"], "-f", "-n", partition])
                filesystem = parse_dumpe2fs(run([tools["dumpe2fs"], "-h", partition]))
                if filesystem["uuid"] != fs_uuid or filesystem["label"] != FS_LABEL:
                    raise ExportError("root filesystem identity differs from the requested UUID/label")
        errors = resources.release()
        if errors:
            raise ExportError("cleanup failed: " + "; ".join(errors))

        os.chmod(paths.partial, 0o644)
        disk_status = os.stat(paths.partial)
        if disk_status.st_size != layout["size_bytes"]:
            raise ExportError("disk size changed during export")
        disk_sha256 = sha256_file(paths.partial)
        boot_region = PARTITION_START_SECTOR * SECTOR_BYTES
        additions.append(
            {
                "path": "<disk sectors 0-2047>",
                "kind": "mbr-and-boot-gap",
                "sha256": sha256_file(paths.partial, limit=boot_region),
                "size": boot_region,
                "note": "MBR partition table and GRUB i386-pc boot.img/core.img",
            }
        )
        metadata = build_metadata(
            source_sha256=args.source_sha256,
            rootfs={
                "sha256": digest.hexdigest(),
                "bytes": rootfs_status.st_size,
                "members": len(plan.members),
                "regular_bytes": plan.regular_bytes,
            },
            identity=identity,
            additions=additions,
            disk={
                "file": paths.output.name,
                "format": "raw",
                "sha256": disk_sha256,
                "size_bytes": disk_status.st_size,
                "size_gib": args.size_gib,
                "allocated_bytes": disk_status.st_blocks * 512,
                "partition_table": "dos",
                "disk_identifier": f"0x{disk_id:08x}",
                "partition": {
                    "number": 1,
                    "start_sector": layout["start_sector"],
                    "sectors": layout["sectors"],
                    "type": "83",
                    "bootable": True,
                },
                "firmware": "bios",
            },
            filesystem={"type": "ext4", **filesystem},
            ownership=ownership,
            exporter={
                "path": "scripts/export_native_cloud.py",
                "sha256": sha256_file(Path(__file__).resolve()),
                "python": platform.python_version(),
            },
        )
        published = []
        with defer_interrupts():
            try:
                os.link(paths.partial, paths.output)
                published.append(paths.output)
                os.unlink(paths.partial)
                created = False
                _create_exclusive(paths.checksum, f"{disk_sha256}  {paths.output.name}\n")
                published.append(paths.checksum)
                _create_exclusive(paths.metadata, json.dumps(metadata, indent=2, sort_keys=True) + "\n")
                published.append(paths.metadata)
            except BaseException:
                for path in published:
                    path.unlink(missing_ok=True)
                raise
            succeeded = True
        return metadata
    finally:
        if not succeeded:
            for error in resources.release():
                print(f"export_native_cloud: cleanup: {error}", file=sys.stderr)
            if created and resources.loop is None and not resources.mounted:
                paths.partial.unlink(missing_ok=True)
            elif created:
                print(f"export_native_cloud: retained image for cleanup: {paths.partial}", file=sys.stderr)


def main(argv=None) -> int:
    args = parse_args(argv)
    previous = {}
    try:
        tools = require_host()
        for signum in INTERRUPT_SIGNALS:
            previous[signum] = signal.signal(signum, _interrupt)
        metadata = export(args, tools)
    except ExportError as exc:
        print(f"export_native_cloud: error: {exc}", file=sys.stderr)
        return 1
    except (OSError, tarfile.TarError) as exc:
        print(f"export_native_cloud: error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
    disk = metadata["disk"]
    print(
        json.dumps(
            {
                "output": str(args.output),
                "sha256": disk["sha256"],
                "size_bytes": disk["size_bytes"],
                "root_filesystem_uuid": metadata["root_filesystem"]["uuid"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
