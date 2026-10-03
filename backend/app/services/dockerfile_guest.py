"""Run a pinned Dockerfile plan inside a disposable Ubuntu builder VM.

This file is copied verbatim into cloud-init by dockerfile_import. It has no app imports so
it can run in the guest; parent artifacts are immutable NFS/squashfs mounts. The root
artifact is a full filesystem snapshot, not the builder's /usr-only view.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import time
from pathlib import Path

STATE = Path("/var/lib/afterglow-dockerfile")
OUTPUTS = Path("/mnt/afterglow-import/out")
INPUTS = Path("/mnt/afterglow-import/in")

REPORTS: list[dict] = []

# Never package per-VM credentials, cloud-init input, runtime mounts or builder control.
# mksquashfs -one-file-system additionally excludes any distinct mounted filesystem.
ROOT_EXCLUDES = (
    "dev",
    "proc",
    "sys",
    "run",
    "tmp",
    "mnt",
    "media",
    "lost+found",
    "var/lib/cloud",
    "var/log",
    "var/cache",
    "var/tmp",
    "etc/fstab",
    "etc/hostname",
    "etc/hosts",
    "etc/machine-id",
    "etc/ssh/ssh_host_*",
    "root/.ssh",
    "home/*/.ssh",
    "etc/afterglow",
    "usr/local/bin/afterglow-dockerfile-*",
)


def call(*args: str) -> None:
    subprocess.run(args, check=True)


def detach_image_loops(image: Path) -> None:
    """Release loop devices bound to this blob, even when NFS breaks inode-based -j lookup."""
    attached = subprocess.check_output(["losetup", "-a"], text=True)
    for line in attached.splitlines():
        if not line.endswith(f" ({image})"):
            continue
        device = line.partition(":")[0]
        if not device.startswith("/dev/loop") or not device.removeprefix("/dev/loop").isdigit():
            raise RuntimeError("unexpected loop device for Dockerfile artifact")
        call("losetup", "-d", device)


def report_digest(name: str, blob: Path) -> None:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    with blob.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            sha256.update(part)
            md5.update(part)
    line = f"::AFTERGLOW::DIGEST::layer={name} sha256={sha256.hexdigest()} md5={md5.hexdigest()} size={blob.stat().st_size}"
    REPORTS.append({"name": name, "sha256": sha256.hexdigest(), "md5": md5.hexdigest(), "size": blob.stat().st_size})

    try:
        with open("/dev/console", "w") as console:
            print(line, file=console, flush=True)
    except OSError:
        pass  # Some Nova deployments do not expose a guest serial device.


def mount_ancestors(ancestors: list[dict]) -> list[str]:
    """The caller supplies child-first sealed ancestors; overlay leftmost is newest."""
    lowers = []
    for index, ancestor in enumerate(ancestors):
        share = INPUTS / str(index)
        lower = STATE / f"cached-{index}"
        share.mkdir(parents=True, exist_ok=True)
        lower.mkdir(parents=True, exist_ok=True)
        # Try all Manila export locations per round, but never let a hung mount
        # or the number of locations extend the total wait without bound.
        deadline = time.monotonic() + 180
        mounted = False
        for attempt in range(12):
            for export in ancestor["exports"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    result = subprocess.run(
                        ["mount", "-t", "nfs4", "-o", "ro,hard", export, str(share)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=min(15, remaining),
                    )
                except (OSError, subprocess.TimeoutExpired):
                    continue
                if result.returncode == 0:
                    mounted = True
                    break
            if mounted or time.monotonic() >= deadline:
                break
            if attempt < 11 and ancestor["exports"]:
                time.sleep(max(0, min(5, deadline - time.monotonic())))
        if not mounted:
            raise RuntimeError("cached ancestor NFS mount failed")
        image = share / "images" / ancestor["filename"]
        staged = STATE / f"ancestor-{index}.sqsh"
        checksum = hashlib.sha256()
        try:
            with image.open("rb") as source, staged.open("xb") as destination:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    checksum.update(chunk)
                    destination.write(chunk)
        finally:
            call("umount", str(share))
        if "sha256:" + checksum.hexdigest() != ancestor["blob_digest"]:
            staged.unlink()
            raise RuntimeError(f"cached ancestor digest mismatch: {ancestor['filename']}")
        call("mount", "-t", "squashfs", "-o", "ro", str(staged), str(lower))
        lowers.append(str(lower))
    return lowers


def image_root(volume_id: str) -> Path:
    """Identify the attached Glance-cloned disk by Cinder serial, never by /dev/vdX."""
    canonical = volume_id.replace("-", "").lower()
    if len(canonical) != 32 or any(char not in "0123456789abcdef" for char in canonical):
        raise ValueError("invalid base image volume ID")
    # A Glance clone has the same filesystem UUID as the builder's boot image.
    # findmnt SOURCE may resolve that UUID to the newly attached clone instead.
    root_device = subprocess.check_output(["findmnt", "-n", "-o", "MAJ:MIN", "/"], text=True).strip()
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        disks = json.loads(
            subprocess.check_output(["lsblk", "-J", "-o", "NAME,TYPE,PATH,SERIAL,FSTYPE,PKNAME,MAJ:MIN"], text=True)
        )["blockdevices"]
        boot_disks = [
            disk
            for disk in disks
            if disk["type"] == "disk"
            and any(part.get("maj:min") == root_device for part in (disk.get("children") or [disk]))
        ]
        if len(boot_disks) != 1:
            raise RuntimeError("cannot identify builder root disk by device number")
        boot_disk = boot_disks[0]["name"]
        matching = [
            disk
            for disk in disks
            if disk["type"] == "disk"
            and disk["name"] != boot_disk
            and len((disk.get("serial") or "").replace("-", "")) >= 17
            and canonical.startswith((disk.get("serial") or "").replace("-", "").lower())
        ]
        if len(matching) > 1:
            raise RuntimeError("ambiguous image volume identity")
        if matching:
            disk = matching[0]
            candidates = disk.get("children") or [disk]
            mounted = []
            for part in candidates:
                filesystem = part.get("fstype")
                if filesystem not in ("ext4", "xfs"):
                    continue
                target = STATE / f"image-root-{len(mounted)}"
                target.mkdir(parents=True, exist_ok=True)
                options = "ro,noload" if filesystem == "ext4" else "ro,norecovery"
                call("mount", "-t", filesystem, "-o", options, part["path"], str(target))
                if (target / "etc/os-release").is_file() and (target / "usr").is_dir():
                    return target
                call("umount", str(target))
                mounted.append(target)
            raise RuntimeError("attached Glance volume has no mountable Ubuntu root")
        time.sleep(2)
    raise TimeoutError("Glance base volume did not attach by serial")


def snapshot_root(name: str, out_index: int, volume_id: str) -> str:
    """Snapshot the never-booted Glance clone, not the mutated builder VM."""
    source = image_root(volume_id)
    staged = STATE / "root.sqsh"
    target = OUTPUTS / str(out_index) / "images" / f"{name}-latest.sqsh"
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        call(
            "mksquashfs",
            str(source),
            str(staged),
            "-noappend",
            "-one-file-system",
            "-comp",
            "zstd",
            "-wildcards",
            "-e",
            *ROOT_EXCLUDES,
        )
    finally:
        call("umount", str(source))
    shutil.copyfile(staged, target)
    report_digest(name, target)
    lower = STATE / "new-root"
    lower.mkdir(parents=True, exist_ok=True)
    call("mount", "-t", "squashfs", "-o", "ro", str(staged), str(lower))
    return str(lower)


def context_source(root: Path, name: str) -> Path:
    source = (root / name).resolve()
    if not source.is_relative_to(root) or not source.exists():
        raise ValueError(f"COPY/ADD source outside pinned context or missing: {name}")
    return source


def copy_source(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)
    elif source.is_symlink():
        if target.exists() or target.is_symlink():
            target.unlink()
        target.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, target)


def load_inherited_state(lowers: list[str]) -> tuple[dict[str, str], str]:
    """Recover cumulative ENV and WORKDIR from child-first lower layer mounts."""
    env: dict[str, str] = {}
    workdir = "/"
    for lower_str in reversed(lowers):
        lower = Path(lower_str)
        env_json = lower / "etc/afterglow/dockerfile-env.json"
        env_sh = lower / "etc/profile.d/afterglow-docker-env.sh"
        if env_json.is_file():
            data = json.loads(env_json.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                env.update({str(k): str(v) for k, v in data.items()})
        elif env_sh.is_file():
            for raw_line in env_sh.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if not stripped.startswith("export "):
                    continue
                for token in shlex.split(stripped[len("export ") :]):
                    if "=" in token:
                        key, value = token.split("=", 1)
                        env[key] = value
        wd_file = lower / "etc/afterglow/dockerfile-workdir"
        wd_sh = lower / "etc/profile.d/afterglow-docker-workdir.sh"
        if wd_file.is_file():
            candidate = wd_file.read_text(encoding="utf-8").strip()
            if candidate.startswith("/"):
                workdir = os.path.normpath(candidate)
        elif wd_sh.is_file():
            for raw_line in wd_sh.read_text(encoding="utf-8").splitlines():
                stripped = raw_line.strip()
                if stripped.startswith("cd "):
                    parts = shlex.split(stripped)
                    if len(parts) >= 2 and parts[1].startswith("/"):
                        workdir = os.path.normpath(parts[1])
    return env, workdir


def _escape_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def write_env_files(upper: Path, full_env: dict[str, str]) -> None:
    ordered = dict(sorted((str(k), str(v)) for k, v in full_env.items()))
    meta_dir = upper / "etc/afterglow"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "dockerfile-env.json").write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    profile_dir = upper / "etc/profile.d"
    profile_dir.mkdir(parents=True, exist_ok=True)
    with (profile_dir / "afterglow-docker-env.sh").open("w", encoding="utf-8") as handle:
        for key, value in ordered.items():
            handle.write(f"export {key}={shlex.quote(value)}\n")
    if ordered:
        sshd_dir = upper / "etc/ssh/sshd_config.d"
        sshd_dir.mkdir(parents=True, exist_ok=True)
        sshd_pairs = " ".join(f'{key}="{_escape_quoted(value)}"' for key, value in ordered.items())
        (sshd_dir / "90-afterglow-docker-env.conf").write_text(f"SetEnv {sshd_pairs}\n", encoding="utf-8")
        systemd_dir = upper / "etc/systemd/system.conf.d"
        systemd_dir.mkdir(parents=True, exist_ok=True)
        pairs = " ".join(f'"{key}={_escape_quoted(value)}"' for key, value in ordered.items())
        (systemd_dir / "90-afterglow-docker-env.conf").write_text(
            f"[Manager]\nDefaultEnvironment={pairs}\n", encoding="utf-8"
        )
        envd_dir = upper / "etc/environment.d"
        envd_dir.mkdir(parents=True, exist_ok=True)
        with (envd_dir / "90-afterglow-docker.conf").open("w", encoding="utf-8") as handle:
            for key, value in ordered.items():
                handle.write(f'{key}="{_escape_quoted(value)}"\n')


def write_workdir_files(upper: Path, workdir: str) -> None:
    normalized = os.path.normpath(workdir) if workdir and workdir.startswith("/") else "/"
    (upper / normalized.lstrip("/")).mkdir(parents=True, exist_ok=True)
    meta_dir = upper / "etc/afterglow"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / "dockerfile-workdir").write_text(f"{normalized}\n", encoding="utf-8")
    profile_dir = upper / "etc/profile.d"
    profile_dir.mkdir(parents=True, exist_ok=True)
    quoted = shlex.quote(normalized)
    (profile_dir / "afterglow-docker-workdir.sh").write_text(
        f"if [ -d {quoted} ]; then\n    cd {quoted} || true\nfi\n",
        encoding="utf-8",
    )


def run_step(step: dict, index: int, out_index: int, lowers: list[str], context: Path | None) -> str:
    """Execute one instruction; seal only its writable delta after successful unmount."""
    name = step["name"]
    payload = step["payload"]
    instr = step["instruction"]
    upper = STATE / f"upper-{index}"
    work = STATE / f"work-{index}"
    merged = STATE / f"merged-{index}"
    for directory in (upper, work, merged):
        directory.mkdir(parents=True, exist_ok=True)

    inherited_env, inherited_workdir = load_inherited_state(lowers)

    if instr in ("RUN", "COPY", "ADD"):
        if not lowers:
            raise RuntimeError("a Dockerfile delta cannot run without a full root")
        payload_wd = payload.get("workdir") or "/"
        workdir = payload_wd if payload_wd != "/" else inherited_workdir
        merged_env = {**inherited_env, **(payload.get("full_env") or {}), **(payload.get("env") or {})}
        call(
            "mount",
            "-t",
            "overlay",
            "overlay",
            "-o",
            f"lowerdir={':'.join(lowers)},upperdir={upper},workdir={work},metacopy=off,index=off,redirect_dir=off",
            str(merged),
        )
        try:
            if instr == "RUN":
                environment = {
                    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                    "HOME": "/root",
                    **merged_env,
                }
                mounted: list[tuple[Path, bool]] = []
                try:
                    for system_dir in ("dev", "proc", "sys"):
                        target_dir = merged / system_dir
                        target_dir.mkdir(parents=True, exist_ok=True)
                        call("mount", "--rbind", f"/{system_dir}", str(target_dir))
                        mounted.append((target_dir, True))
                        call("mount", "--make-rprivate", str(target_dir))
                    runtime_dir = merged / "run"
                    runtime_dir.mkdir(parents=True, exist_ok=True)
                    call("mount", "-t", "tmpfs", "-o", "mode=0755", "tmpfs", str(runtime_dir))
                    mounted.append((runtime_dir, False))
                    resolver = merged / "etc/resolv.conf"
                    if resolver.is_symlink():
                        target = os.path.normpath(os.path.join("/etc", os.readlink(resolver)))
                        if target.startswith("/run/"):
                            runtime_resolver = merged / target.lstrip("/")
                            runtime_resolver.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2("/etc/resolv.conf", runtime_resolver)
                    (merged / workdir.lstrip("/")).mkdir(parents=True, exist_ok=True)
                    command = f"cd {shlex.quote(workdir)} && {payload['command']}"
                    subprocess.run(["chroot", str(merged), "/bin/bash", "-lc", command], env=environment, check=True)
                finally:
                    for mountpoint, recursive in reversed(mounted):
                        if recursive:
                            call("umount", "-R", str(mountpoint))
                        else:
                            call("umount", str(mountpoint))
            else:
                if context is None:
                    raise RuntimeError("COPY/ADD requires a pinned GitHub build context")
                sources = payload["sources"]
                raw_dest = payload.get("raw_dest")
                destination = payload["dest"]
                if raw_dest and not raw_dest.startswith("/") and workdir != "/":
                    default_dest = os.path.normpath(os.path.join("/", raw_dest))
                    if raw_dest.endswith("/") or raw_dest in {".", "./"}:
                        default_dest += "/"
                    if destination == default_dest:
                        destination = os.path.normpath(os.path.join(workdir, raw_dest))
                        if raw_dest.endswith("/") or raw_dest in {".", "./"}:
                            destination += "/"
                base = merged / destination.lstrip("/")
                if not base.resolve().is_relative_to(merged.resolve()):
                    raise ValueError(f"COPY/ADD destination escapes the image root: {destination}")
                multiple = len(sources) > 1 or destination.endswith("/") or base.is_dir()
                for name in sources:
                    source = context_source(context, name)
                    copy_source(source, base / source.name if multiple else base)
        finally:
            call("umount", str(merged))
    elif instr == "ENV":
        full_env = {**inherited_env, **(payload.get("full_env") or {}), **(payload.get("env") or {})}
        write_env_files(upper, full_env)
    elif instr == "WORKDIR":
        raw_wd = payload.get("raw_workdir") or payload.get("workdir") or step.get("args", "/")
        if not str(raw_wd).startswith("/"):
            workdir = os.path.normpath(os.path.join(inherited_workdir, str(raw_wd)))
        else:
            workdir = os.path.normpath(payload.get("workdir") or str(raw_wd))
        write_workdir_files(upper, workdir)
    else:
        raise ValueError(f"unsupported instruction: {instr}")

    staged = STATE / f"step-{index}.sqsh"
    target = OUTPUTS / str(out_index) / "images" / f"{step['name']}-latest.sqsh"
    target.parent.mkdir(parents=True, exist_ok=True)
    call("mksquashfs", str(upper), str(staged), "-noappend", "-comp", "zstd")
    shutil.copyfile(staged, target)
    report_digest(step["name"], target)
    lower = STATE / f"new-{index}"
    lower.mkdir(parents=True, exist_ok=True)
    call("mount", "-t", "squashfs", "-o", "ro", str(staged), str(lower))
    return str(lower)


def run() -> None:
    plan = json.loads(Path("/etc/afterglow/dockerfile-plan.json").read_text())
    config = json.loads(Path("/etc/afterglow/dockerfile-config.json").read_text())
    STATE.mkdir(parents=True, exist_ok=True)
    lowers = mount_ancestors(config["ancestors"])
    out_index = 0
    if config["root_name"]:
        if lowers:
            raise RuntimeError("new full root cannot be stacked on a cached ancestor")
        lowers = [snapshot_root(config["root_name"], out_index, config["base_volume_id"])]
        out_index += 1
    if not lowers:
        raise RuntimeError("Dockerfile needs an existing or newly materialized full root")
    context = Path(config["context"]).resolve() if config["context"] else None
    for index, step in enumerate(plan):
        lower = run_step(step, index, out_index + index, lowers, context)
        lowers.insert(0, lower)
    token = os.environ["AFTERGLOW_BUILD_TOKEN"]
    payload = json.dumps({"token": token, "reports": REPORTS}, separators=(",", ":")).encode("utf-8")
    manifest_path = OUTPUTS / "0" / ".afterglow-manifest.json"
    pending_path = manifest_path.with_suffix(".pending")
    with pending_path.open("xb") as pending:
        pending.write(payload)
        pending.flush()
        os.fsync(pending.fileno())
    os.replace(pending_path, manifest_path)
    manifest = base64.b64encode(json.dumps(REPORTS, separators=(",", ":")).encode("utf-8")).decode("ascii")
    try:
        with open("/dev/console", "w") as console:
            print(f"::AFTERGLOW::MANIFEST::{token}::{manifest}", file=console, flush=True)
    except OSError:
        pass  # The persisted manifest is verified via a one-use read-only VM.

    # Cached images are local copies; unmount their input NFS shares before loop mounting.
    # Detach only the verified image loops before releasing the output shares.
    images = [STATE / f"step-{index}.sqsh" for index in reversed(range(len(plan)))]
    if config["root_name"]:
        images.append(STATE / "root.sqsh")
    images.extend(STATE / f"ancestor-{index}.sqsh" for index, _ancestor in enumerate(config["ancestors"]))
    for lower, image in zip(lowers, images, strict=True):
        call("umount", lower)
        detach_image_loops(image)
    for index in range(out_index + len(plan)):
        call("umount", str(OUTPUTS / str(index)))


if __name__ == "__main__":
    run()
