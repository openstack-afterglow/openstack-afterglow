"""squashfs NFS 레이어 빌드 + 소비 인스턴스 오케스트레이터.

빌드 흐름:
  NFS RW share → Neutron port(IP 예약) → NFS access rule(RW) →
  cloud-init user_data(squashfs 빌드) → Nova server →
  SHUTOFF 폴링 → sentinel grep → 성공/실패 처리

소비 흐름:
  NFS RO share export 조회 → cloud-init(layer-activate.sh 주입) →
  Neutron port → NFS access rule(RO) → Nova server 생성 → DB 기록
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import textwrap
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.config import get_settings
from app.services import cinder, cloudinit, layer_consume_ssh, manila, neutron, nova
from app.services.cloud_init_builder import render_user_data
from app.services.layer_base_images import legacy_snapshot_for_ubuntu_base
from app.services.layer_ubuntu import normalize_ubuntu_base
from app.services.palimpsest_digest import parse_digest_sentinel
from app.services.palimpsest_layers import resolve_digest_fields
from app.services.recipe_blocks import (
    squashfs_nvidia_driver_layer,
    squashfs_stacked_layer,
    squashfs_system_apt_layer,
    squashfs_uv_layer,
)
from app.services.ssh_access import normalize_github_username
from app.utils.ssh_keys import validate_ssh_public_key

_logger = logging.getLogger(__name__)


def _base_image_fields(snapshot: dict | None) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    return {
        name: snapshot.get(name)
        for name in (
            "base_image_id",
            "base_image_name",
            "base_image_checksum",
            "base_image_os_hash_algo",
            "base_image_os_hash_value",
            "base_image_min_disk",
            "base_image_visibility",
            "base_image_owner",
            "source_metadata",
        )
        if snapshot.get(name) is not None
    }


def _artifact_base_image_snapshot(artifact, settings) -> dict:
    base_image_id = getattr(artifact, "base_image_id", None)
    if base_image_id:
        return {
            "base_image_id": base_image_id,
            "base_image_name": getattr(artifact, "base_image_name", None),
            "base_image_checksum": getattr(artifact, "base_image_checksum", None),
            "base_image_os_hash_algo": getattr(artifact, "base_image_os_hash_algo", None),
            "base_image_os_hash_value": getattr(artifact, "base_image_os_hash_value", None),
            "base_image_min_disk": getattr(artifact, "base_image_min_disk", None),
            "base_image_visibility": getattr(artifact, "base_image_visibility", None),
            "base_image_owner": getattr(artifact, "base_image_owner", None),
            "ubuntu_base": normalize_ubuntu_base(getattr(artifact, "ubuntu_base", None)),
            "source_metadata": getattr(artifact, "source_metadata", None),
        }
    return legacy_snapshot_for_ubuntu_base(settings, getattr(artifact, "ubuntu_base", None))


_SHUTOFF_POLL_INTERVAL = 15
_SHUTOFF_MAX_WAIT = 3600
_SUCCESS_SENTINEL = "::AFTERGLOW::SUCCESS::"
_FAILURE_SENTINEL = "::AFTERGLOW::FAILURE::"
_CONSOLE_EXCERPT_CHARS = 12000
_DEFAULT_NVIDIA_DRIVER_BRANCH = "580"
_NVIDIA_DRIVER_BRANCH_VALUES = {"550", "570", "575", "580"}


_CONSUME_POLL_INTERVAL = 5
_CONSUME_MAX_WAIT = 900


async def _wait_for_consume_health(
    conn,
    server_id: str,
    token: str,
    *,
    ssh_host: str | None = None,
    ssh_key_path: str | None = None,
    ssh_username: str = "ubuntu",
) -> bool:
    """Prove the mounted root through Nova console or the guest's one-use SSH key."""
    success = f"{_SUCCESS_SENTINEL}{token}"
    failure = f"{_FAILURE_SENTINEL}{token}"
    console_unavailable = False
    for _ in range(_CONSUME_MAX_WAIT // _CONSUME_POLL_INTERVAL):
        server = await asyncio.to_thread(conn.compute.get_server, server_id)
        state = str(getattr(server, "status", "") or "").upper()
        if state in {"ERROR", "DELETED", "SOFT_DELETED"}:
            raise RuntimeError(f"consumer VM entered {state} before guest health")
        try:
            console = await asyncio.to_thread(nova.get_console_output, conn, server_id, _CONSOLE_EXCERPT_CHARS)
        except Exception:
            if not console_unavailable:
                _logger.warning("[layer_consume] guest console unavailable: %s", server_id, exc_info=True)
                console_unavailable = True
        else:
            if failure in console:
                raise RuntimeError("consumer guest layer activation failed")
            if success in console:
                return False
        if (
            ssh_host
            and ssh_key_path
            and await layer_consume_ssh.guest_root_is_ready(ssh_host, ssh_username, ssh_key_path, token)
        ):
            return True
        await asyncio.sleep(_CONSUME_POLL_INTERVAL)
    raise TimeoutError("consumer guest did not report layer mount health")


def nvidia_driver_apt_packages(driver_branch: str | None = None) -> list[str]:
    """Packages installed on the consumer VM by the NVIDIA driver hook."""
    branch = driver_branch or _DEFAULT_NVIDIA_DRIVER_BRANCH
    if branch not in _NVIDIA_DRIVER_BRANCH_VALUES:
        allowed = ", ".join(sorted(_NVIDIA_DRIVER_BRANCH_VALUES))
        raise RuntimeError(f"지원하지 않는 NVIDIA 드라이버 브랜치: {branch!r} (allowed: {allowed})")
    return [
        "ca-certificates",
        "curl",
        "gnupg",
        "linux-headers-$(uname -r)",
        "dkms",
        "kmod",
        f"nvidia-dkms-{branch}-open",
        f"libnvidia-compute-{branch}",
        f"nvidia-utils-{branch}",
    ]


# 화이트리스트 정규식
_LAYER_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]*$")
_NFS_EXPORT_RE = re.compile(r"^[0-9a-zA-Z.\[\]:/_\-]+$")
_SSH_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")


def _resolve_flavor_id(conn, flavor_ref: str) -> str:
    """플레이버 이름/ID를 Nova flavor ID로 해석한다."""
    if not flavor_ref:
        raise RuntimeError("플레이버 ID가 비어 있습니다")

    flavor = conn.compute.find_flavor(flavor_ref)
    if flavor is None:
        raise RuntimeError(f"플레이버를 찾을 수 없습니다: {flavor_ref!r}")
    return flavor.id


# ---------------------------------------------------------------------------
# render_user_data 프로토콜을 충족하는 가상 레시피 (ORM 불필요)
# ---------------------------------------------------------------------------


@dataclass
class _LayerRecipe:
    """squashfs 빌드용 가상 레시피 — render_user_data 인터페이스 충족."""

    share_proto: str = "NFS"
    commands: list[dict] = field(default_factory=list)
    apt_packages: list[str] = field(default_factory=list)
    cephx_id: str | None = None
    cephx_key: str | None = None
    base_image_id: str | None = None


# Builder/consumer 이미지에 미리 bake 해둘 layer 워크플로우 OS 패키지.
# cloud-init packages: 블록은 오래된 이미지 호환용 idempotent fallback 으로 유지한다.
LAYER_BUILD_IMAGE_PACKAGES = ("curl", "nfs-common", "squashfs-tools")
LAYER_CONSUME_IMAGE_PACKAGES = ("nfs-common", "squashfs-tools")


# ---------------------------------------------------------------------------
# layer-activate.sh 원본 (layers/vm/layer-activate.sh 와 동기화 유지)
# base64 인코딩 후 cloud-init write_files에 주입
# ---------------------------------------------------------------------------

_ROOT_INITRAMFS_DEPS = """\
#!/bin/sh
set -e
. /usr/share/initramfs-tools/hook-functions
copy_exec /usr/bin/sha256sum /usr/bin
copy_exec "$(command -v blkid)" /sbin
"""


_ROOT_IDENTITY_MERGE_PY = """\
import os
import shutil
import sys
from pathlib import Path

layer, upper, username, consumer = map(Path, sys.argv[1:])
name = str(username)
upper_etc = upper / "etc"

def row(path, account):
    return next((line for line in path.read_text().splitlines() if line.split(":", 1)[0] == account), None)

source_passwd = layer / "etc/passwd"
consumer_passwd = consumer / "etc/passwd"
account = row(source_passwd, name)
if account is None:
    account = row(consumer_passwd, name)
    if account is None:
        raise RuntimeError("consumer SSH account was not provisioned")
    uid = account.split(":")[2]
    if any(line.split(":")[2] == uid for line in source_passwd.read_text().splitlines()):
        raise RuntimeError("consumer SSH UID conflicts with Dockerfile user")
    upper_etc.mkdir(parents=True, exist_ok=True)
    for filename in ("passwd", "shadow", "group", "gshadow"):
        source = layer / "etc" / filename
        destination = upper_etc / filename
        shutil.copy2(source, destination)
        extra = row(consumer / "etc" / filename, name)
        if extra is None:
            raise RuntimeError("consumer SSH identity is incomplete")
        if row(destination, name) is None:
            with destination.open("a") as handle:
                handle.write(extra + "\\n")
    for filename in ("group", "gshadow"):
        destination = upper_etc / filename
        original = destination.read_text().splitlines()
        consumer_rows = (consumer / "etc" / filename).read_text().splitlines()
        for index, line in enumerate(original):
            fields = line.split(":")
            if fields[0] not in {"sudo", "adm"}:
                continue
            baseline = next((value for value in consumer_rows if value.startswith(fields[0] + ":")), "")
            if name in baseline.split(":")[-1].split(",") and name not in fields[-1].split(","):
                fields[-1] = ",".join(filter(None, (fields[-1], name)))
                original[index] = ":".join(fields)
        destination.write_text("\\n".join(original) + "\\n")

uid, gid = (int(value) for value in account.split(":")[2:4])
home_dir = upper / "home" / name
if home_dir.is_dir():
    os.chown(home_dir, uid, gid)
ssh_dir = home_dir / ".ssh"
if ssh_dir.is_dir():
    for directory, dirs, files in os.walk(ssh_dir):
        os.chown(directory, uid, gid)
        for filename in files:
            os.chown(os.path.join(directory, filename), uid, gid)
"""

_ROOT_UPPER_DEVICE_PY = """\
import json
import subprocess
import sys
import time
import uuid

volume_id = str(uuid.UUID(sys.argv[1])).replace('-', '').lower()
boot_source = subprocess.check_output(['findmnt', '-n', '-o', 'SOURCE', '/'], text=True).strip()
boot_disk = subprocess.check_output(['lsblk', '-n', '-o', 'PKNAME', boot_source], text=True).strip()
deadline = time.monotonic() + 180
while time.monotonic() < deadline:
    disks = json.loads(subprocess.check_output(
        ['lsblk', '-J', '-o', 'NAME,TYPE,PATH,SERIAL,FSTYPE'], text=True
    ))['blockdevices']
    matches = [disk for disk in disks if disk['type'] == 'disk' and disk['name'] != boot_disk
               and len((disk.get('serial') or '').replace('-', '')) >= 17
               and volume_id.startswith((disk.get('serial') or '').replace('-', '').lower())]
    if len(matches) > 1:
        raise RuntimeError('ambiguous Cinder upper volume serial')
    if matches:
        disk = matches[0]
        if disk.get('children') or disk.get('fstype'):
            raise RuntimeError('Cinder upper volume is not an empty dedicated disk')
        print(disk['path'])
        break
    time.sleep(2)
else:
    raise TimeoutError('Cinder upper volume did not attach by serial')
"""


_ROOT_INITRAMFS_HOOK = """\
#!/bin/sh
# initramfs-tools local-bottom: the original boot disk is mounted at rootmnt.
case "${1:-}" in
    prereqs) exit 0 ;;
esac
set -eu
base=/run/afterglow/base-root
layers=/run/afterglow/sqsh
state=/run/afterglow/state
mkdir -p "$base" "$layers" "$state"
conf="${rootmnt}/etc/afterglow/layers/root.conf"
[ -s "$conf" ] || { echo 'afterglow: root layer manifest missing' >&2; exit 1; }
uuid_file="${rootmnt}/etc/afterglow/layers/root-upper-uuid"
[ -s "$uuid_file" ] || { echo 'afterglow: dedicated upper UUID missing' >&2; exit 1; }
uuid="$(cat "$uuid_file")"
case "$uuid" in
    ????????-????-????-????-????????????) ;;
    *) echo 'afterglow: invalid upper filesystem UUID' >&2; exit 1 ;;
esac
case "$uuid" in
    *[!0-9a-fA-F-]*) echo 'afterglow: invalid upper filesystem UUID' >&2; exit 1 ;;
esac
device="$(/sbin/blkid -U "$uuid")"
[ -b "$device" ] || { echo 'afterglow: dedicated upper device unavailable' >&2; exit 1; }
mount -t ext4 -o rw "$device" "$state" || exit 1
[ -d "$state/upper" ] && [ -d "$state/work" ] || { echo 'afterglow: root upper missing' >&2; exit 1; }
lower=
index=0
while IFS='|' read -r unused file digest; do
    [ -n "$file" ] || continue
    case "$file" in
        *[!a-zA-Z0-9.+_-]*|'') echo 'afterglow: invalid layer filename' >&2; exit 1 ;;
    esac
    src="$state/blobs/${index}.sqsh"
    [ -s "$src" ] || { echo "afterglow: missing cached layer $index" >&2; exit 1; }
    if [ -n "$digest" ]; then
        case "$digest" in
            sha256:????????????????????????????????????????????????????????????????) ;;
            *) echo 'afterglow: invalid layer digest' >&2; exit 1 ;;
        esac
        printf '%s  %s\\n' "${digest#sha256:}" "$src" | sha256sum -c - || exit 1
    fi
    dir="$layers/$index"
    mkdir -p "$dir"
    mount -t squashfs -o ro,loop "$src" "$dir" || exit 1
    lower="${lower:+${lower}:}${dir}"
    index=$((index + 1))
done < "$conf"
[ "$index" -gt 0 ] || { echo 'afterglow: empty root lineage' >&2; exit 1; }
# The immutable filesystem is a child-first lower stack. Keep the bootstrap
# filesystem writable for its private cloud-init state, never as a lowerdir.
mount -o remount,rw "$rootmnt" || exit 1
mount --move "$rootmnt" "$base" || exit 1
# Child-first deltas (including OverlayFS whiteouts) override the oldest full
# root image. The boot disk only supplies private writable consumer state.
mount -t overlay overlay -o "lowerdir=${lower},upperdir=${state}/upper,workdir=${state}/work" "$rootmnt" || exit 1
# Preserve the consumer's completed first-boot cloud-init state, not builder data.
mkdir -p "$rootmnt/var/lib/cloud"
mount --bind "$base/var/lib/cloud" "$rootmnt/var/lib/cloud" || exit 1
"""


_LAYER_ACTIVATE_SH = """\
#!/usr/bin/env bash
# layer-activate.sh — squashfs 레이어 마운트 + OverlayFS 합성 (VM 측)
# conf 파일 형식 (per-layer-share 방식):
#   줄당 "<nfs_mountpoint>|<sqsh_filename>"  (child-first = 최상위)
#   예:
#     /mnt/nfs-layers/0|torch-latest.sqsh
#     /mnt/nfs-layers/1|python-latest.sqsh
#     /mnt/nfs-layers/2|uv-latest.sqsh
set -euo pipefail

if [ $# -ne 1 ]; then
    echo "사용법: $0 <profile-name>" >&2
    exit 1
fi

_validate_name() {
    local val="$1" kind="$2"
    if ! [[ "$val" =~ ^[a-z0-9][a-z0-9.+\\-]*$ ]]; then
        echo "오류: 유효하지 않은 ${kind}: '${val}'" >&2
        exit 1
    fi
}

_validate_mountpoint() {
    local val="$1"
    if ! [[ "$val" =~ ^/mnt/nfs-layers/[0-9]+$ ]]; then
        echo "오류: 유효하지 않은 마운트 포인트: '${val}'" >&2
        exit 1
    fi
}

_validate_sqsh() {
    local val="$1"
    if ! [[ "$val" =~ ^[a-z0-9][a-z0-9.+\\-]*\\.sqsh$ ]]; then
        echo "오류: 유효하지 않은 sqsh 파일명: '${val}'" >&2
        exit 1
    fi
}

PROFILE="$1"
_validate_name "$PROFILE" "profile-name"

SQSH_BASE="${SQSH_BASE:-/mnt/sqsh}"
CACHE_DIR="${CACHE_DIR:-/var/cache/layers}"
LOCAL_UPPER="${LOCAL_UPPER:-/var/lib/overlay/upper}"
LOCAL_WORK="${LOCAL_WORK:-/var/lib/overlay/work}"
OVERLAY_TARGET="${OVERLAY_TARGET:-/usr}"
LOCAL_PROFILE_DIR="${LOCAL_PROFILE_DIR:-/etc/afterglow/layers}"

LOG="/var/log/layer-activate.log"
exec >> "$LOG" 2>&1
echo "[$(date)] layer-activate 시작: profile=${PROFILE} target=${OVERLAY_TARGET}"
if [ "$OVERLAY_TARGET" = "/" ] && [ -f /etc/afterglow/root-staged ]; then
    if [ "$(findmnt -n -o FSTYPE /)" != overlay ] || ! mountpoint -q /var/lib/cloud; then
        echo '[ERROR] staged root did not boot through overlay' >&2
        exit 1
    fi
    echo "[$(date)] Root OverlayFS health verified"
    exit 0
fi

if [ "$OVERLAY_TARGET" = "/" ]; then
    [[ "${ROOT_UPPER_VOLUME_ID:-}" =~ ^[0-9a-fA-F-]{36}$ ]] || { echo '[ERROR] Cinder upper volume ID missing' >&2; exit 1; }
    [ ! -e /etc/afterglow/layers/root-upper-uuid ] || { echo '[ERROR] root upper already prepared' >&2; exit 1; }
    upper_device="$(python3 /usr/local/bin/layer-upper-device.py "$ROOT_UPPER_VOLUME_ID")"
    [ -b "$upper_device" ] || { echo '[ERROR] Cinder upper device unavailable' >&2; exit 1; }
    if blkid -p "$upper_device" >/dev/null 2>&1; then
        echo '[ERROR] Cinder upper is not empty; refusing to format' >&2
        exit 1
    fi
    mkfs.ext4 -q -F "$upper_device"
    mkdir -p /run/afterglow/state
    mount -t ext4 -o rw "$upper_device" /run/afterglow/state
    upper_uuid="$(blkid -s UUID -o value "$upper_device")"
    [[ "$upper_uuid" =~ ^[0-9a-fA-F-]{8}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{4}-[0-9a-fA-F-]{12}$ ]] || exit 1
    echo "$upper_uuid" > /etc/afterglow/layers/root-upper-uuid
    mkdir -p /run/afterglow/state/upper /run/afterglow/state/work /run/afterglow/state/blobs
    CACHE_DIR=/run/afterglow/state/blobs
    ROOT_LAYER_INDEX=0
fi


mkdir -p "$SQSH_BASE" "$CACHE_DIR"
if [ "$OVERLAY_TARGET" != "/" ]; then
    mkdir -p "$LOCAL_UPPER" "$LOCAL_WORK"
fi
_ensure_nfs_mount() {
    local mntpt="$1"
    if mountpoint -q "$mntpt" 2>/dev/null; then
        return 0
    fi
    for attempt in $(seq 1 12); do
        if mount "$mntpt" 2>/dev/null || mountpoint -q "$mntpt" 2>/dev/null; then
            echo "[$(date)] NFS 마운트 완료: ${mntpt}"
            return 0
        fi
        echo "[$(date)] NFS 마운트 대기: ${mntpt} (${attempt}/12)"
        sleep 5
    done
    mount "$mntpt"
}

_stage_root_layer() {
    local index="$1" mntpt="$2" file="$3" digest="$4" cache="$5"
    local candidate export round remaining mount_timeout
    local deadline=$(( $(date +%s) + 180 ))
    [ -n "$digest" ] || { echo '[ERROR] sealed root digest missing' >&2; exit 1; }
    # NFS is only needed during staging; initramfs reads verified Cinder blobs.
    for ((round=1; round<=12; round++)); do
        while IFS='|' read -r candidate export; do
            [ "$candidate" = "$index" ] || continue
            [ -n "$export" ] || { echo '[ERROR] empty root export' >&2; exit 1; }
            remaining=$((deadline - $(date +%s)))
            [ "$remaining" -gt 0 ] || break
            mount_timeout=$((remaining < 15 ? remaining : 15))
            if mountpoint -q "$mntpt" 2>/dev/null; then
                echo '[ERROR] root staging mountpoint already in use' >&2
                exit 1
            fi
            if ! timeout "${mount_timeout}s" mount -t nfs4 -o ro,soft,timeo=50,retrans=3,retry=0 "$export" "$mntpt"; then
                echo "[WARN] root export mount failed: ${export}" >&2
                continue
            fi
            if [ -f "$mntpt/images/$file" ] && cp -- "$mntpt/images/$file" "${cache}.tmp"; then
                # A readable blob with the wrong digest is corrupt, not a reason
                # to trust a different endpoint. Never publish unverified bytes.
                if ! printf '%s  %s\\n' "${digest#sha256:}" "${cache}.tmp" | sha256sum -c -; then
                    rm -f -- "${cache}.tmp"
                    umount "$mntpt" || exit 1
                    exit 1
                fi
                umount "$mntpt" || exit 1
                mv -- "${cache}.tmp" "$cache"
                return 0
            fi
            rm -f -- "${cache}.tmp"
            umount "$mntpt" || exit 1
            echo "[WARN] root blob unavailable on ${export}: ${file}" >&2
        done < "${LOCAL_PROFILE_DIR}/root-exports.conf"
        remaining=$((deadline - $(date +%s)))
        [ "$round" -lt 12 ] && [ "$remaining" -gt 0 ] || break
        sleep "$((remaining < 5 ? remaining : 5))"
    done
    echo "[ERROR] no usable root export for layer ${index}" >&2
    exit 1
}

_layer_lowerdir() {
    local mount_point="$1"
    if [ "$OVERLAY_TARGET" = "/usr" ]; then
        local lower="${mount_point}/usr"
        if [ ! -d "$lower" ]; then
            echo "[ERROR] /usr lowerdir 없음: ${lower}" >&2
            exit 1
        fi
        printf '%s\n' "$lower"
    else
        printf '%s\n' "$mount_point"
    fi
}


LOCAL_CONF="${LOCAL_PROFILE_DIR}/${PROFILE}.conf"
if [ ! -f "$LOCAL_CONF" ]; then
    echo "[ERROR] 프로필 파일 없음: ${LOCAL_CONF}" >&2
    exit 1
fi

LOWER_DIRS=""
while IFS='|' read -r MNTPT SQSH_FILE DIGEST; do
    MNTPT="${MNTPT//[[:space:]]/}"
    SQSH_FILE="${SQSH_FILE//[[:space:]]/}"
    [ -z "$MNTPT" ] && continue
    _validate_mountpoint "$MNTPT"
    _validate_sqsh "$SQSH_FILE"
    if [ -n "$DIGEST" ] && ! [[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]]; then
        echo '[ERROR] invalid layer digest' >&2
        exit 1
    fi
    if [ "$OVERLAY_TARGET" != "/" ]; then
        _ensure_nfs_mount "$MNTPT"
    fi


    LAYER_KEY="${SQSH_FILE%.sqsh}"
    SQSH_NFS="${MNTPT}/images/${SQSH_FILE}"
    SQSH_CACHE="${CACHE_DIR}/${LAYER_KEY}.sqsh"
    MOUNT_POINT="${SQSH_BASE}/${LAYER_KEY}"

    if [ "$OVERLAY_TARGET" = "/" ] && mountpoint -q "$MOUNT_POINT"; then
        echo '[ERROR] duplicate Dockerfile layer mount' >&2
        exit 1
    fi

    if mountpoint -q "$MOUNT_POINT" 2>/dev/null; then
        LAYER_LOWER="$(_layer_lowerdir "$MOUNT_POINT")"
        LOWER_DIRS="${LOWER_DIRS:+${LOWER_DIRS}:}${LAYER_LOWER}"
        continue
    fi
    mkdir -p "$MOUNT_POINT"

    if [ "$OVERLAY_TARGET" = "/" ]; then
        SQSH_CACHE="${CACHE_DIR}/${ROOT_LAYER_INDEX}.sqsh"
        _stage_root_layer "$ROOT_LAYER_INDEX" "$MNTPT" "$SQSH_FILE" "$DIGEST" "$SQSH_CACHE"
        ROOT_LAYER_INDEX=$((ROOT_LAYER_INDEX + 1))
        SQSH_SRC="$SQSH_CACHE"
    else
        if [ -f "$SQSH_NFS" ]; then
            _nfs_size="$(stat -c%s "$SQSH_NFS" 2>/dev/null || echo 0)"
            _cache_size="$(stat -c%s "$SQSH_CACHE" 2>/dev/null || echo -1)"
            if [ ! -f "$SQSH_CACHE" ] || \
               [ "$SQSH_NFS" -nt "$SQSH_CACHE" ] || \
               [ "$_nfs_size" != "$_cache_size" ]; then
                cp "$SQSH_NFS" "${SQSH_CACHE}.tmp" 2>/dev/null \
                    && mv "${SQSH_CACHE}.tmp" "$SQSH_CACHE" || true
            fi
        fi
        if [ -f "$SQSH_CACHE" ]; then
            SQSH_SRC="$SQSH_CACHE"
        elif [ -f "$SQSH_NFS" ]; then
            SQSH_SRC="$SQSH_NFS"
        else
            echo "[ERROR] 이미지 없음: ${SQSH_NFS}" >&2
            exit 1
        fi
    fi

    mount -t squashfs "$SQSH_SRC" "$MOUNT_POINT" -o ro
    echo "[$(date)] 마운트 완료: ${LAYER_KEY} → ${MOUNT_POINT}"
    LAYER_LOWER="$(_layer_lowerdir "$MOUNT_POINT")"
    LOWER_DIRS="${LOWER_DIRS:+${LOWER_DIRS}:}${LAYER_LOWER}"
done < "$LOCAL_CONF"

[ -z "$LOWER_DIRS" ] && echo "[ERROR] 레이어 없음" >&2 && exit 1

_run_layer_hooks() {
    local hook_dir
    if [ "$OVERLAY_TARGET" = "/usr" ]; then
        hook_dir="/usr/lib/afterglow/layer-hooks.d"
    else
        hook_dir="${OVERLAY_TARGET}/usr/lib/afterglow/layer-hooks.d"
    fi
    if [ ! -d "$hook_dir" ]; then
        return 0
    fi
    echo "[$(date)] 레이어 hook 실행: ${hook_dir}"
    while IFS= read -r -d '' hook; do
        echo "[$(date)] hook 시작: ${hook}"
        "$hook"
        echo "[$(date)] hook 완료: ${hook}"
    done < <(find "$hook_dir" -maxdepth 1 -type f -name '*.sh' -perm -0100 -print0 | sort -z)
}

if [ "$OVERLAY_TARGET" = "/" ]; then
    command -v update-initramfs >/dev/null || { echo '[ERROR] initramfs-tools required' >&2; exit 1; }
    modprobe overlay
    modprobe squashfs
    modprobe loop
    [ -d /etc/initramfs-tools/scripts/local-bottom ] || { echo '[ERROR] initramfs-tools missing' >&2; exit 1; }
    [ "$(findmnt -n -o FSTYPE /run/afterglow/state)" = ext4 ] || { echo '[ERROR] Cinder upper not mounted' >&2; exit 1; }
    ROOT_UPPER=/run/afterglow/state/upper
    [ "$ROOT_LAYER_INDEX" -gt 0 ] || { echo '[ERROR] root layers missing' >&2; exit 1; }
    for ((index=0; index<ROOT_LAYER_INDEX; index++)); do
        [ -s "/run/afterglow/state/blobs/${index}.sqsh" ] || { echo '[ERROR] missing staged root layer' >&2; exit 1; }
    done
    cp -- "$LOCAL_CONF" /etc/afterglow/layers/root.conf
    # Keep Dockerfile-created users, SSH configuration and application files.
    # Only transient directories are opaque; private host keys are replaced.
    for path in var/log tmp var/tmp; do
        mkdir -p "$ROOT_UPPER/$path"
        if [ -d "/$path" ]; then
            cp -a "/$path/." "$ROOT_UPPER/$path/"
        fi
        python3 -c 'import os,sys; os.setxattr(sys.argv[1], "trusted.overlay.opaque", b"y")' \
            "$ROOT_UPPER/$path"
    done
    for path in etc/machine-id etc/hostname etc/layer-profile; do
        [ -f "/$path" ] || continue
        mkdir -p "$ROOT_UPPER/$(dirname "$path")"
        cp -a -- "/$path" "$ROOT_UPPER/$path"
    done
    if [ -f /etc/fstab ]; then
        mkdir -p "$ROOT_UPPER/etc"
        awk '$1 !~ /^#/ && ($2 == "/boot" || $2 == "/boot/efi")' /etc/fstab > "$ROOT_UPPER/etc/fstab"
    fi
    for path in etc/afterglow/layers/root.conf etc/afterglow/layers/root-upper-uuid \
                etc/afterglow/layer-health.sh etc/systemd/system/layer-activate.service \
                etc/systemd/system/layer-health.service \
                etc/systemd/system/multi-user.target.wants/layer-activate.service \
                etc/systemd/system/multi-user.target.wants/layer-health.service \
                etc/initramfs-tools/scripts/local-bottom/afterglow-root \
                etc/initramfs-tools/hooks/afterglow-root \
                etc/netplan/50-cloud-init.yaml etc/sudoers.d/90-cloud-init-users \
                root/.ssh "home/${CONSUMER_SSH_USER:-ubuntu}/.ssh"; do
        [ -e "/$path" ] || continue
        mkdir -p "$ROOT_UPPER/$(dirname "$path")"
        cp -a -- "/$path" "$ROOT_UPPER/$path"
    done
    mkdir -p "$ROOT_UPPER/etc/ssh"
    for key in /etc/ssh/ssh_host_*; do
        [ -f "$key" ] || continue
        cp -a -- "$key" "$ROOT_UPPER/etc/ssh/"
    done
    COMPOSED_ROOT=/mnt/afterglow-composed-root
    mkdir -p "$COMPOSED_ROOT"
    mount -t overlay overlay -o "lowerdir=${LOWER_DIRS}" "$COMPOSED_ROOT"
    python3 /usr/local/bin/layer-identity-merge.py "$COMPOSED_ROOT" "$ROOT_UPPER" \
        "${CONSUMER_SSH_USER:-ubuntu}" /
    umount "$COMPOSED_ROOT"
    mkdir -p "$ROOT_UPPER/usr/local/bin"
    cp -a /usr/local/bin/layer-*.sh /usr/local/bin/layer-*.py "$ROOT_UPPER/usr/local/bin/"
    touch /etc/afterglow/root-staged
    cp -a /etc/afterglow/root-staged "$ROOT_UPPER/etc/afterglow/"
    printf 'overlay\nsquashfs\nloop\next4\n' >> /etc/initramfs-tools/modules
    update-initramfs -u -k "$(uname -r)"
    # cloud-init power_state reboots only after all user-data scripts finish.
    exit 42
fi

if mountpoint -q "$OVERLAY_TARGET" 2>/dev/null; then
    _ft="$(findmnt -n -o FSTYPE "$OVERLAY_TARGET" 2>/dev/null || true)"
    if [ "$_ft" = "overlay" ]; then
        echo "[$(date)] 이미 overlay 활성 — hook 재실행 후 스킵"
        _run_layer_hooks
        exit 0
    fi
fi

[ -d "$LOCAL_WORK" ] && rm -rf "${LOCAL_WORK:?}/"* "${LOCAL_WORK:?}/".* 2>/dev/null || true

BASE_LOWER="/"
if [ "$OVERLAY_TARGET" = "/usr" ]; then
    BASE_LOWER="${BASE_USR_LOWER:-/run/afterglow/base-usr}"
    mkdir -p "$BASE_LOWER"
    if ! mountpoint -q "$BASE_LOWER" 2>/dev/null; then
        mount --bind /usr "$BASE_LOWER"
    fi
fi

mount -t overlay overlay \\
    -o "lowerdir=${LOWER_DIRS}:${BASE_LOWER},upperdir=${LOCAL_UPPER},workdir=${LOCAL_WORK},metacopy=on" \\
    "$OVERLAY_TARGET"

_run_layer_hooks

echo "[$(date)] OverlayFS 활성화 완료: ${OVERLAY_TARGET}"
"""


# ---------------------------------------------------------------------------
# DB 업데이트 헬퍼
# ---------------------------------------------------------------------------


async def _update_build_db(
    build_id: int | None,
    *,
    status: str | None = None,
    cloud_init_status: str | None = None,
    progress_step: str | None = None,
    progress_pct: int | None = None,
    server_id: str | None = None,
    port_id: str | None = None,
    build_token: str | None = None,
    error_message: str | None = None,
    console_log_excerpt: str | None = None,
    completed: bool = False,
) -> None:
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LayerBuild

    if build_id is None:
        return
    factory = get_session_factory()
    if factory is None:
        return

    async with factory() as session:
        row = (await session.execute(select(LayerBuild).where(LayerBuild.id == build_id))).scalar_one_or_none()
        if row is None:
            return
        terminal = {"complete", "error", "timeout", "cancelled"}
        if row.status in terminal and not completed:
            return
        if status is not None:
            row.status = status
        if cloud_init_status is not None:
            row.cloud_init_status = cloud_init_status
        if progress_step is not None:
            row.progress_step = progress_step
        if progress_pct is not None:
            row.progress_pct = progress_pct
        if server_id is not None:
            row.server_id = server_id
        if port_id is not None:
            row.port_id = port_id
        if build_token is not None:
            row.build_token = build_token
        if error_message is not None:
            row.error_message = error_message
        if console_log_excerpt is not None:
            row.console_log_excerpt = console_log_excerpt
        if completed:
            row.completed_at = datetime.now(UTC)
        await session.commit()


async def _update_consume_db(
    consume_id: int | None,
    *,
    status: str | None = None,
    server_id: str | None = None,
    port_id: str | None = None,
    error_message: str | None = None,
    server_name: str | None = None,
    completed: bool = False,
) -> None:
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LayerConsume

    if consume_id is None:
        return
    factory = get_session_factory()
    if factory is None:
        return

    async with factory() as session:
        row = (await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id))).scalar_one_or_none()
        if row is None:
            return
        if status is not None:
            row.status = status
        if server_id is not None:
            row.server_id = server_id
        if port_id is not None:
            row.port_id = port_id
        if server_name is not None:
            row.server_name = server_name
        if error_message is not None:
            row.error_message = error_message
        if completed:
            row.completed_at = datetime.now(UTC)
        await session.commit()


# ---------------------------------------------------------------------------
# SHUTOFF 폴링 (ephemeral_build._wait_for_shutoff와 동일 패턴)
# ---------------------------------------------------------------------------


async def _wait_for_shutoff(conn, server_id: str, build_db_id: int | None, build_token: str) -> tuple[bool, bool]:
    """VM이 SHUTOFF 될 때까지 폴링. (early_success, early_failure) 반환."""
    waited = 0
    early_success = False
    early_failure = False
    success_tok = f"{_SUCCESS_SENTINEL}{build_token}"
    failure_tok = f"{_FAILURE_SENTINEL}{build_token}"

    while waited < _SHUTOFF_MAX_WAIT:
        await asyncio.sleep(_SHUTOFF_POLL_INTERVAL)
        waited += _SHUTOFF_POLL_INTERVAL

        server = await asyncio.to_thread(conn.compute.get_server, server_id)
        status = (server.status or "").upper()

        if status in ("SHUTOFF", "ERROR"):
            _logger.info("[layer_build] VM %s 상태: %s (elapsed=%ds)", server_id, status, waited)
            return (early_success, early_failure)

        if status == "ACTIVE" and waited > 60:
            try:
                partial = await asyncio.to_thread(nova.get_console_output, conn, server_id, _CONSOLE_EXCERPT_CHARS)
                if success_tok in partial and not early_success:
                    early_success = True
                    await _update_build_db(build_db_id, console_log_excerpt=partial[-_CONSOLE_EXCERPT_CHARS:])
                elif failure_tok in partial and not early_failure:
                    early_failure = True
                    await _update_build_db(build_db_id, console_log_excerpt=partial[-_CONSOLE_EXCERPT_CHARS:])
            except Exception:
                pass

        cloud_status = "booting" if waited < 120 else "installing"
        await _update_build_db(build_db_id, cloud_init_status=cloud_status)

    raise TimeoutError(f"VM {server_id}이 {_SHUTOFF_MAX_WAIT}s 내에 SHUTOFF 되지 않았습니다")


# ---------------------------------------------------------------------------
# 소비 VM cloud-init 렌더러
# ---------------------------------------------------------------------------


def render_layer_consume_user_data(
    profile_name: str,
    mounts: list[tuple[str, str]],
    ssh_public_key: str | None = None,
    ssh_username: str | None = None,
    github_username: str | None = None,
    *,
    root_mode: bool = False,
    health_token: str | None = None,
    digests: list[str | None] | None = None,
    root_upper_volume_id: str | None = None,
    health_ssh_public_key: str | None = None,
    root_export_candidates: list[list[str]] | None = None,
) -> str:
    """소비 VM cloud-init YAML 문자열을 반환한다 (per-layer-share 방식).

    Legacy /usr mounts use one fstab automount per layer; full-root staging
    tries each validated Manila export in order and unmounts it after copying.
    root.conf remains the child-first cached-blob manifest for initramfs.

    Args:
        profile_name: 레이어 프로필 이름 (^[a-z0-9][a-z0-9.+-]*$). 개행 불허.
        mounts:       [(export_path, sqsh_filename), ...] child-first 순서.
                      export_path: Manila NFS export 경로. 개행·셸 메타문자 불허.
                      sqsh_filename: share /images/ 아래 .sqsh 파일명.
        root_export_candidates: root-only candidate paths per layer, in mounts order.
    """
    if not _LAYER_NAME_RE.match(profile_name):
        raise ValueError(f"유효하지 않은 프로필 이름: {profile_name!r}")
    if "\n" in profile_name or "\r" in profile_name:
        raise ValueError("프로필 이름에 개행 문자 불허")
    if not mounts:
        raise ValueError("mounts 목록이 비어 있습니다")
    if digests is not None:
        if len(digests) != len(mounts):
            raise ValueError("layer digest count does not match mounts")
        if any(value and not re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in digests):
            raise ValueError("invalid layer digest")
    if root_mode and (not digests or any(not digest for digest in digests)):
        raise ValueError("dockerfile lineage requires sealed blob digests")

    if root_mode:
        if not isinstance(root_upper_volume_id, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            root_upper_volume_id,
        ):
            raise ValueError("root mode requires a dedicated Cinder upper volume ID")
    elif root_upper_volume_id is not None:
        raise ValueError("Cinder upper volume only applies to root mode")
    if health_ssh_public_key:
        if not root_mode:
            raise ValueError("temporary health SSH key applies only to root mode")
        validate_ssh_public_key(health_ssh_public_key)
    if root_export_candidates is not None and (
        not root_mode
        or len(root_export_candidates) != len(mounts)
        or any(not group for group in root_export_candidates)
    ):
        raise ValueError("root export candidates must match mounts")

    # Manila 반환 동적값 검증 (신뢰하지 않음)
    _SQSH_RE = re.compile(r"^[a-z0-9][a-z0-9.+\-]*\.sqsh$")
    for export_path, sqsh_filename in mounts:
        if not _NFS_EXPORT_RE.match(export_path):
            raise ValueError(f"유효하지 않은 NFS export 경로: {export_path!r}")
        if "\n" in export_path or "\r" in export_path:
            raise ValueError("NFS export 경로에 개행 문자 불허")
        if not _SQSH_RE.match(sqsh_filename):
            raise ValueError(f"유효하지 않은 sqsh 파일명: {sqsh_filename!r}")
    if root_export_candidates is not None:
        for group, (primary, _) in zip(root_export_candidates, mounts, strict=True):
            if group[0] != primary or any(
                not isinstance(export, str) or not _NFS_EXPORT_RE.fullmatch(export) for export in group
            ):
                raise ValueError("invalid root export candidates")

    if ssh_public_key:
        validate_ssh_public_key(ssh_public_key)
    if ssh_username:
        if not _SSH_USERNAME_RE.match(ssh_username):
            raise ValueError(f"유효하지 않은 SSH 사용자명: {ssh_username!r}")
        if ssh_username == "root":
            raise ValueError("root SSH 사용자는 허용되지 않습니다")
    github_username = normalize_github_username(github_username)
    if github_username and (ssh_public_key or ssh_username):
        raise ValueError("github_username은 ssh_public_key 또는 ssh_username과 함께 사용할 수 없습니다")
    if health_token is None:
        health_token = uuid.uuid4().hex
    if not re.fullmatch(r"[0-9a-f]{32}", health_token):
        raise ValueError("invalid layer health token")

    activate_b64 = base64.b64encode(_LAYER_ACTIVATE_SH.encode()).decode()

    # layer-activate-auto.sh — /etc/layer-profile 에서 프로필 읽어 activate 실행
    auto_sh = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        PROFILE="$(cat /etc/layer-profile | tr -d '[:space:]')"
        if OVERLAY_TARGET={"/" if root_mode else "/usr"} ROOT_UPPER_VOLUME_ID={root_upper_volume_id or ""} CONSUMER_SSH_USER={ssh_username or "ubuntu"} /usr/local/bin/layer-activate.sh "$PROFILE"; then
            if [ "$(findmnt -n -o FSTYPE {"/" if root_mode else "/usr"})" != overlay ]; then
                {{ echo '{_FAILURE_SENTINEL}{health_token}' > /dev/console; }} 2>/dev/null || :
                exit 1
            fi
        else
            status=$?
            if [ "$status" -eq 42 ] && [ {"1" if root_mode else "0"} -eq 1 ]; then
                exit 0
            fi
            {{ echo '{_FAILURE_SENTINEL}{health_token}' > /dev/console; }} 2>/dev/null || :
            exit "$status"
        fi
    """)
    auto_b64 = base64.b64encode(auto_sh.encode()).decode()
    health_sh = textwrap.dedent(f"""\
        #!/usr/bin/env bash
        set -euo pipefail
        if [ {"1" if root_mode else "0"} -eq 1 ] && [ -f /etc/afterglow/root-staged ] \\
            && [ "$(findmnt -n -o FSTYPE /)" != overlay ]; then
            exit 0
        fi
        if [ "$(findmnt -n -o FSTYPE {"/" if root_mode else "/usr"})" != overlay ] \\
            || ! systemctl is-active --quiet ssh.service \\
            || ! ss -ltn '( sport = :22 )' | grep -q LISTEN; then
            {{ echo '{_FAILURE_SENTINEL}{health_token}' > /dev/console; }} 2>/dev/null || :
            exit 1
        fi
        echo '{health_token}' > {layer_consume_ssh.READY_FILE}
        chmod 600 {layer_consume_ssh.READY_FILE}
        {{ echo '{_SUCCESS_SENTINEL}{health_token}' > /dev/console; }} 2>/dev/null || :
    """)
    health_b64 = base64.b64encode(health_sh.encode()).decode()

    health_unit = textwrap.dedent("""\
        [Unit]
        Description=Verify layer overlay and SSH readiness
        After=layer-activate.service ssh.service network-online.target
        Requires=layer-activate.service ssh.service

        [Service]
        Type=oneshot
        RemainAfterExit=yes
        ExecStart=/etc/afterglow/layer-health.sh

        [Install]
        WantedBy=multi-user.target
    """)
    health_unit_b64 = base64.b64encode(health_unit.encode()).decode()

    # systemd unit — network-online 후 실행 (automount가 NFS 마운트 처리)
    unit = textwrap.dedent("""\
        [Unit]
        Description=Activate squashfs overlay layers
        After=network-online.target
        Requires=network-online.target
        Before=multi-user.target

        [Service]
        Type=oneshot
        RemainAfterExit=yes
        ExecStart=/usr/local/bin/layer-activate-auto.sh
        StandardOutput=journal
        StandardError=journal

        [Install]
        WantedBy=multi-user.target
    """)
    unit_b64 = base64.b64encode(unit.encode()).decode()

    # /etc/layer-profile 내용
    profile_b64 = base64.b64encode((profile_name + "\n").encode()).decode()

    # conf 파일: 줄당 "<nfs_mountpoint>|<sqsh_filename>" (child-first)
    conf_lines = [
        f"/mnt/nfs-layers/{i}|{sqsh}" + (f"|{digests[i]}" if digests and digests[i] else "")
        for i, (_, sqsh) in enumerate(mounts)
    ]
    local_conf_b64 = base64.b64encode(("\n".join(conf_lines) + "\n").encode()).decode()

    # Only legacy /usr uses fstab automount. Root staging unmounts NFS before
    # reboot and initramfs then reads verified blobs from the Cinder volume.
    fstab_lines = (
        ""
        if root_mode
        else "".join(
            f"{export}  /mnt/nfs-layers/{i}  nfs4  ro,hard,timeo=50,retrans=3,_netdev,x-systemd.automount  0  0\n"
            for i, (export, _) in enumerate(mounts)
        )
    )
    fstab_b64 = base64.b64encode(fstab_lines.encode()).decode()
    if root_mode:
        root_exports = root_export_candidates or [[export] for export, _ in mounts]
        root_exports_b64 = base64.b64encode(
            "".join(f"{i}|{export}\n" for i, group in enumerate(root_exports) for export in group).encode()
        ).decode()

    # /mnt/nfs-layers/<i> 디렉터리 생성 runcmd
    nfs_dirs = " ".join(f"/mnt/nfs-layers/{i}" for i in range(len(mounts)))

    ssh_lines: list[str] = []
    if ssh_public_key:
        quoted_ssh_key = json.dumps(ssh_public_key)
        if ssh_username:
            ssh_lines = [
                "users:",
                "  - default",
                f"  - name: {ssh_username}",
                "    shell: /bin/bash",
                "    lock_passwd: true",
                "    sudo: ALL=(ALL) NOPASSWD:ALL",
                "    groups: [adm, sudo]",
                "    ssh_authorized_keys:",
                f"      - {quoted_ssh_key}",
            ]
        else:
            ssh_lines = [
                "ssh_authorized_keys:",
                f"  - {quoted_ssh_key}",
            ]
    if health_ssh_public_key:
        if not ssh_lines:
            ssh_lines = ["ssh_authorized_keys:"]
        ssh_lines.append(
            f"{'      ' if ssh_public_key and ssh_username else '  '}- {json.dumps(health_ssh_public_key)}"
        )

    parts = [
        "#cloud-config",
        "package_update: true",
        "package_upgrade: false",
        "packages:",
        *(f"  - {pkg}" for pkg in LAYER_CONSUME_IMAGE_PACKAGES),
        *ssh_lines,
        *(
            [
                "ssh_import_id:",
                f"  - {json.dumps(f'gh:{github_username}')}",
            ]
            if github_username
            else []
        ),
        "write_files:",
        "  - path: /usr/local/bin/layer-activate.sh",
        "    encoding: b64",
        f"    content: {activate_b64}",
        '    permissions: "0755"',
        "  - path: /usr/local/bin/layer-activate-auto.sh",
        "    encoding: b64",
        f"    content: {auto_b64}",
        '    permissions: "0755"',
        "  - path: /etc/afterglow/layer-health.sh",
        "    encoding: b64",
        f"    content: {health_b64}",
        '    permissions: "0755"',
        "  - path: /etc/layer-profile",
        "    encoding: b64",
        f"    content: {profile_b64}",
        f"  - path: /etc/afterglow/layers/{profile_name}.conf",
        "    encoding: b64",
        f"    content: {local_conf_b64}",
        "  - path: /etc/systemd/system/layer-activate.service",
        "    encoding: b64",
        f"    content: {unit_b64}",
        "  - path: /etc/systemd/system/layer-health.service",
        "    encoding: b64",
        f"    content: {health_unit_b64}",
        *(
            [
                "  - path: /etc/initramfs-tools/scripts/local-bottom/afterglow-root",
                "    encoding: b64",
                f"    content: {base64.b64encode(_ROOT_INITRAMFS_HOOK.encode()).decode()}",
                '    permissions: "0755"',
                "  - path: /etc/initramfs-tools/hooks/afterglow-root",
                "    encoding: b64",
                f"    content: {base64.b64encode(_ROOT_INITRAMFS_DEPS.encode()).decode()}",
                '    permissions: "0755"',
                "  - path: /usr/local/bin/layer-identity-merge.py",
                "    encoding: b64",
                f"    content: {base64.b64encode(_ROOT_IDENTITY_MERGE_PY.encode()).decode()}",
                '    permissions: "0755"',
                "  - path: /usr/local/bin/layer-upper-device.py",
                "    encoding: b64",
                f"    content: {base64.b64encode(_ROOT_UPPER_DEVICE_PY.encode()).decode()}",
                '    permissions: "0755"',
                "  - path: /etc/afterglow/layers/root-exports.conf",
                "    encoding: b64",
                f"    content: {root_exports_b64}",
            ]
            if root_mode
            else []
        ),
        *(
            ["  - path: /etc/fstab", "    encoding: b64", "    append: true", f"    content: {fstab_b64}"]
            if not root_mode
            else []
        ),
        *(
            [
                "power_state:",
                "  mode: reboot",
                "  delay: now",
                "  condition: test -f /etc/afterglow/root-staged",
            ]
            if root_mode
            else []
        ),
        "runcmd:",
        "  - mkdir -p /etc/afterglow/layers",
        f"  - mkdir -p {nfs_dirs} /mnt/sqsh /var/cache/layers /var/lib/overlay/upper /var/lib/overlay/work",
        "  - systemctl daemon-reload",
        "  - systemctl enable layer-activate.service",
        "  - systemctl enable layer-health.service",
        "  - systemctl start layer-activate.service",
        "  - systemctl start layer-health.service",
    ]

    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# 메인 빌드 오케스트레이터
# ---------------------------------------------------------------------------


def _validate_build_recipe_contract(
    kind: str,
    python_version: str | None,
    pip_packages: list[str],
    apt_packages: list[str] | None = None,
    parent_artifact_id: int | None = None,
    pip_index_url: str | None = None,
    pip_extra_index_urls: list[str] | None = None,
    pip_find_links: list[str] | None = None,
    nvidia_driver_branch: str | None = None,
) -> None:
    """OpenStack 리소스 할당 전 빌드 recipe 조합 계약을 검증한다."""
    has_parent = parent_artifact_id is not None
    has_packages = bool(pip_packages)
    has_apt_packages = bool(apt_packages)
    has_pip_sources = pip_index_url is not None or bool(pip_extra_index_urls) or bool(pip_find_links)
    if kind == "uv":
        if has_parent:
            raise RuntimeError("kind='uv'일 때 parent_artifact_id는 사용할 수 없습니다")
        if python_version is not None:
            raise RuntimeError("kind='uv'일 때 python_version은 사용할 수 없습니다")
        if has_packages:
            raise RuntimeError("kind='uv'일 때 pip_packages는 사용할 수 없습니다")
        if has_apt_packages:
            raise RuntimeError("kind='uv'일 때 apt_packages는 사용할 수 없습니다")
        if has_pip_sources:
            raise RuntimeError("kind='uv'일 때 pip source 옵션은 사용할 수 없습니다")
        return
    if kind == "system":
        if has_parent:
            raise RuntimeError("kind='system'일 때 parent_artifact_id는 사용할 수 없습니다")
        if python_version is not None:
            raise RuntimeError("kind='system'일 때 python_version은 사용할 수 없습니다")
        if has_packages:
            raise RuntimeError("kind='system'일 때 pip_packages는 사용할 수 없습니다")
        if has_pip_sources:
            raise RuntimeError("kind='system'일 때 pip source 옵션은 사용할 수 없습니다")
        if not has_apt_packages:
            raise RuntimeError("kind='system'일 때 apt_packages는 최소 1개 이상 필요합니다")
        return
    if kind == "nvidia":
        branch = nvidia_driver_branch or _DEFAULT_NVIDIA_DRIVER_BRANCH
        if branch not in _NVIDIA_DRIVER_BRANCH_VALUES:
            allowed = ", ".join(sorted(_NVIDIA_DRIVER_BRANCH_VALUES))
            raise RuntimeError(f"지원하지 않는 NVIDIA 드라이버 브랜치: {branch!r} (allowed: {allowed})")
        if has_parent:
            raise RuntimeError("kind='nvidia'일 때 parent_artifact_id는 사용할 수 없습니다")
        if python_version is not None:
            raise RuntimeError("kind='nvidia'일 때 python_version은 사용할 수 없습니다")
        if has_packages:
            raise RuntimeError("kind='nvidia'일 때 pip_packages는 사용할 수 없습니다")
        if has_apt_packages:
            raise RuntimeError("kind='nvidia'일 때 apt_packages는 서버 템플릿이 생성하므로 입력할 수 없습니다")
        if has_pip_sources:
            raise RuntimeError("kind='nvidia'일 때 pip source 옵션은 사용할 수 없습니다")
        return
    if kind == "python":
        if not has_parent:
            raise RuntimeError("kind='python'일 때 parent_artifact_id가 필요합니다")
        if not python_version:
            raise RuntimeError("kind='python'일 때 python_version은 필수입니다")
        if has_packages:
            raise RuntimeError("kind='python'일 때 pip_packages는 사용할 수 없습니다")
        if has_apt_packages:
            raise RuntimeError("kind='python'일 때 apt_packages는 사용할 수 없습니다")
        if has_pip_sources:
            raise RuntimeError("kind='python'일 때 pip source 옵션은 사용할 수 없습니다")
        if nvidia_driver_branch is not None:
            raise RuntimeError("kind='python'일 때 nvidia_driver_branch는 사용할 수 없습니다")
        return
    if kind == "pip":
        if not has_parent:
            raise RuntimeError("kind='pip'일 때 parent_artifact_id가 필요합니다")
        if python_version is not None:
            raise RuntimeError("kind='pip'일 때 python_version은 사용할 수 없습니다")
        if not has_packages:
            raise RuntimeError("kind='pip'일 때 pip_packages는 최소 1개 이상 필요합니다")
        if has_apt_packages:
            raise RuntimeError("kind='pip'일 때 apt_packages는 사용할 수 없습니다")
        if nvidia_driver_branch is not None:
            raise RuntimeError("kind='pip'일 때 nvidia_driver_branch는 사용할 수 없습니다")
        return
    raise RuntimeError(f"지원하지 않는 layer kind: {kind}")


async def run_layer_build(
    build_db_id: int | None,
    layer_name: str,
    kind: str,
    python_version: str | None,
    pip_packages: list[str],
    apt_packages: list[str] | None = None,
    pip_index_url: str | None = None,
    pip_extra_index_urls: list[str] | None = None,
    pip_find_links: list[str] | None = None,
    parent_artifact_id: int | None = None,
    nvidia_driver_branch: str | None = None,
    ubuntu_base: str | None = None,
    base_image_snapshot: dict | None = None,
    source_metadata: dict | None = None,
    resource_snapshot: dict | None = None,
) -> None:
    """squashfs layer build background task.

    빌드마다 Manila NFS share를 새로 생성하고, 성공 시 RW rule 회수(봉인)한다.
    부모가 있으면(parent_artifact_id ≠ None) 조상 체인을 RO 마운트해 delta만 squash하는
    stacked 빌드를 수행한다.

    kind="uv"     : uv 바이너리 전용 base 레이어 (부모 없음).
    kind="system" : apt 패키지 전용 root 레이어 (부모 없음).
    kind="python" : uv 부모 위에 CPython만 추가하는 stacked delta 레이어.
    kind="pip"    : Python lineage 부모 위에 pip 패키지만 추가하는 stacked delta 레이어.
    """
    from app.database import get_session_factory
    from app.models.db import LayerArtifact

    conn = None

    port_id: str | None = None
    server_id: str | None = None
    new_share_id: str | None = None  # 이번 빌드가 생성한 share (실패 시 삭제)
    rw_access_id: str | None = None  # 빌드 VM RW rule (성공 시 회수 = 봉인)
    ancestor_ro_access_ids: list[tuple[str, str]] = []  # [(share_id, access_id)] 조상 RO
    build_succeeded = False

    pip_packages = list(pip_packages or [])
    apt_packages = list(apt_packages or [])
    if base_image_snapshot and base_image_snapshot.get("ubuntu_base"):
        effective_ubuntu_base = normalize_ubuntu_base(base_image_snapshot.get("ubuntu_base"))
    else:
        effective_ubuntu_base = normalize_ubuntu_base(ubuntu_base)
    if source_metadata is not None:
        base_image_snapshot = {**(base_image_snapshot or {}), "source_metadata": source_metadata}
    try:
        _validate_build_recipe_contract(
            kind,
            python_version,
            pip_packages,
            apt_packages,
            parent_artifact_id,
            pip_index_url,
            pip_extra_index_urls,
            pip_find_links,
            nvidia_driver_branch,
        )
        if kind == "nvidia":
            nvidia_driver_branch = nvidia_driver_branch or _DEFAULT_NVIDIA_DRIVER_BRANCH
            apt_packages = nvidia_driver_apt_packages(nvidia_driver_branch)
        resource_snapshot = resource_snapshot or {}
        base_image = resource_snapshot.get("base_image") or {}
        builder_flavor = resource_snapshot.get("builder.flavor") or {}
        builder_network = resource_snapshot.get("builder.network") or {}
        manila_snapshot = resource_snapshot.get("manila") or {}
        service_project = resource_snapshot.get("openstack.service_project") or {}
        image_id = base_image.get("id")
        flavor_id = builder_flavor.get("id")
        network_id = builder_network.get("id")
        share_network_id = manila_snapshot.get("share_network_id")
        share_type = manila_snapshot.get("share_type")
        share_size_gb = manila_snapshot.get("share_size_gb")
        if not all(
            (image_id, flavor_id, network_id, share_network_id, share_type, share_size_gb, service_project.get("id"))
        ):
            raise RuntimeError("build resource snapshot is incomplete")
        from app.services.keystone import get_admin_connection_for_project

        conn = await asyncio.to_thread(get_admin_connection_for_project, service_project["id"])
        build_token = uuid.uuid4().hex
        await _update_build_db(build_db_id, build_token=build_token)

        # ── 2. 조상 체인 조회 (parent_artifact_id → [share_id, sqsh_filename, ...]) ──
        ancestor_info: list[tuple[str, str, int]] = []  # [(share_id, sqsh_filename, art_id)]
        async with get_session_factory()() as _sess:
            cur_id: int | None = parent_artifact_id
            while cur_id is not None:
                art = await _sess.get(LayerArtifact, cur_id)
                if art is None:
                    break
                ancestor_info.append((art.share_id, art.sqsh_filename, art.id))
                cur_id = art.parent_id  # type: ignore[assignment]

        # ── 3. Neutron port 생성 (IP 예약) ────────────────────────────
        await _update_build_db(build_db_id, status="creating_access", progress_step="Neutron port 생성", progress_pct=5)
        port_info = await asyncio.to_thread(
            neutron.create_port, conn, network_id, f"afterglow-layer-build-{build_token[:8]}"
        )
        port_id = port_info["id"]
        fixed_ip = port_info["fixed_ip"]
        await _update_build_db(build_db_id, port_id=port_id)
        _logger.info("[layer_build] port 생성: %s (%s)", port_id, fixed_ip)

        # ── 4. 신규 레이어 share 동적 생성 ──────────────────────────────
        await _update_build_db(build_db_id, progress_step="레이어 share 생성", progress_pct=8)
        share_name = f"afterglow-layer-{layer_name}-{build_token[:8]}"
        share_info = await asyncio.to_thread(
            manila.create_file_storage,
            conn,
            share_name,
            share_size_gb,
            share_network_id,
            share_type,
            {
                "afterglow_role": "union-layer",
                "afterglow_layer_name": layer_name,
                "afterglow_layer_kind": kind,
                "afterglow_build_token": build_token[:16],
            },
        )
        new_share_id = share_info.id
        _logger.info("[layer_build] 레이어 share 생성: %s (%s)", share_name, new_share_id)

        # ── 5. 신규 share에 RW access rule 부여 → export ────────────────
        rule = await asyncio.to_thread(
            manila.ensure_nfs_access_rule,
            conn,
            new_share_id,
            fixed_ip,
            "rw",
            root_squash=False,
            sec_flavor="sys",
        )
        rw_access_id = rule["access_id"]
        _logger.info("[layer_build] NFS RW rule 생성: %s", rw_access_id)

        export_locations = await asyncio.to_thread(manila.get_export_locations, conn, new_share_id)
        if not export_locations:
            raise RuntimeError(f"신규 share {new_share_id}의 export location이 없습니다")
        mount_spec = {"share_proto": "NFS", "export_path": export_locations[0]}

        # ── 6. 조상 share에 RO rule + export 수집 ────────────────────
        parent_exports: list[tuple[str, str]] = []  # [(export_path, sqsh_filename)]
        for anc_share_id, anc_sqsh, _ in ancestor_info:
            ro_rule = await asyncio.to_thread(
                manila.ensure_nfs_access_rule,
                conn,
                anc_share_id,
                fixed_ip,
                "ro",
                root_squash=False,
                sec_flavor="sys",
            )
            ancestor_ro_access_ids.append((anc_share_id, ro_rule["access_id"]))
            anc_exports = await asyncio.to_thread(manila.get_export_locations, conn, anc_share_id)
            if not anc_exports:
                raise RuntimeError(f"조상 share {anc_share_id}의 export location이 없습니다")
            parent_exports.append((anc_exports[0], anc_sqsh))
            _logger.info("[layer_build] 조상 share RO rule: share=%s", anc_share_id)

        # ── 7. cloud-init 렌더 ────────────────────────────────────────
        await _update_build_db(build_db_id, status="creating_vm", progress_step="VM 생성", progress_pct=15)

        if kind == "uv":
            build_script = squashfs_uv_layer(layer_name)
        elif kind == "system":
            build_script = squashfs_system_apt_layer(layer_name, apt_packages)
        elif kind == "nvidia":
            build_script = squashfs_nvidia_driver_layer(
                layer_name, nvidia_driver_branch or _DEFAULT_NVIDIA_DRIVER_BRANCH
            )
        elif kind == "python":
            build_script = squashfs_stacked_layer(layer_name, python_version, None, parent_exports)
        elif kind == "pip":
            build_script = squashfs_stacked_layer(
                layer_name,
                None,
                pip_packages,
                parent_exports,
                pip_index_url=pip_index_url,
                pip_extra_index_urls=pip_extra_index_urls,
                pip_find_links=pip_find_links,
            )
        else:
            raise RuntimeError(f"지원하지 않는 layer kind: {kind}")

        recipe = _LayerRecipe(
            share_proto="NFS",
            apt_packages=list(LAYER_BUILD_IMAGE_PACKAGES),
            commands=[{"step": "squashfs_build", "progress_pct": 80, "script": build_script}],
        )
        user_data_str = render_user_data(recipe, mount_spec, build_token)
        user_data_b64 = base64.b64encode(user_data_str.encode()).decode()
        # ── 8. Builder VM 생성 ────────────────────────────────────────
        vm_name = f"afterglow-layer-build-{layer_name}-{build_token[:8]}"
        server = await asyncio.to_thread(
            conn.compute.create_server,
            name=vm_name,
            image_id=image_id,
            flavor_id=flavor_id,
            networks=[{"port": port_id}],
            user_data=user_data_b64,
            metadata={"union_type": "layer-build", "layer_name": layer_name, "afterglow_managed": "true"},
        )
        server_id = server.id
        await _update_build_db(
            build_db_id, server_id=server_id, cloud_init_status="booting", progress_step="VM 부팅 중", progress_pct=20
        )
        _logger.info("[layer_build] VM 생성: %s (%s)", vm_name, server_id)

        # ── 9. SHUTOFF 폴링 ───────────────────────────────────────────
        await _update_build_db(build_db_id, status="building", progress_step="cloud-init 실행 중", progress_pct=25)
        early_success, early_failure = await _wait_for_shutoff(conn, server_id, build_db_id, build_token)

        # ── 10. sentinel 검증 ─────────────────────────────────────────
        await _update_build_db(build_db_id, cloud_init_status="finalizing", progress_step="결과 검증", progress_pct=90)
        console = ""
        for _len in (None, 500, 200):
            try:
                console = await asyncio.to_thread(nova.get_console_output, conn, server_id, _len)
                if console:
                    break
            except Exception:
                pass
        if not console:
            _logger.warning("[layer_build] console_output 조회 실패 (early sentinel fallback: %s)", early_success)

        excerpt = console[-_CONSOLE_EXCERPT_CHARS:] if len(console) > _CONSOLE_EXCERPT_CHARS else console
        if excerpt:
            await _update_build_db(build_db_id, console_log_excerpt=excerpt)

        success_tok = f"{_SUCCESS_SENTINEL}{build_token}"
        failure_tok = f"{_FAILURE_SENTINEL}{build_token}"

        if success_tok in console or early_success:
            # ── 봉인: RW rule 회수 (share는 이제 사실상 RO) ──────────────
            if rw_access_id:
                try:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, new_share_id, rw_access_id)
                    rw_access_id = None
                    _logger.info("[layer_build] RW rule 회수 완료(봉인): share=%s", new_share_id)
                except Exception:
                    _logger.warning("[layer_build] RW rule 회수 실패", exc_info=True)

            await _update_build_db(
                build_db_id,
                status="complete",
                cloud_init_status="success",
                progress_step="빌드 완료",
                progress_pct=100,
                completed=True,
            )
            build_succeeded = True
            _logger.info("[layer_build] 빌드 성공: layer=%s share=%s", layer_name, new_share_id)

            # LayerArtifact DB 기록
            try:
                sqsh_filename = f"{layer_name}-latest.sqsh"
                # Palimpsest 콘텐츠 주소화: 빌드 VM 이 mksquashfs 직후 방출한 digest sentinel 을
                # 회수한다. 없으면 digest_state='pending' 으로 기록되고 백필이 채운다 —
                # 빌드 성공 자체를 되돌리지 않는다.
                digest_report = parse_digest_sentinel(console, layer_name)
                if digest_report is None:
                    _logger.warning("[layer_build] digest sentinel 부재 — pending 으로 기록: layer=%s", layer_name)
                async with get_session_factory()() as _art_session:
                    digest_fields = await resolve_digest_fields(
                        _art_session,
                        report=digest_report,
                        parent_artifact_id=parent_artifact_id,
                        name=layer_name,
                        kind=kind,
                        ubuntu_base=effective_ubuntu_base,
                        python_version=python_version if kind == "python" else None,
                        pip_packages=list(pip_packages or []),
                        apt_packages=list(apt_packages or []),
                    )
                    artifact = LayerArtifact(
                        name=layer_name,
                        kind=kind,
                        python_version=python_version if kind == "python" else None,
                        pip_packages=list(pip_packages or []),
                        apt_packages=list(apt_packages or []),
                        ubuntu_base=effective_ubuntu_base,
                        sqsh_filename=sqsh_filename,
                        share_id=new_share_id,
                        build_id=build_db_id,
                        parent_id=parent_artifact_id,
                        is_sealed=True,
                        size_bytes=digest_report.size_bytes if digest_report else None,
                        **digest_fields,
                        **_base_image_fields(base_image_snapshot),
                    )
                    _art_session.add(artifact)
                    await _art_session.commit()
                _logger.info(
                    "[layer_build] LayerArtifact 기록: layer=%s kind=%s digest=%s",
                    layer_name,
                    kind,
                    digest_fields.get("blob_digest") or "pending",
                )
            except Exception:
                _logger.warning("[layer_build] LayerArtifact 기록 실패 (빌드는 성공)", exc_info=True)

        elif failure_tok in console or early_failure:
            raise RuntimeError("cloud-init FAILURE sentinel 감지 — console_log_excerpt 참조")
        else:
            _logger.error("[layer_build] sentinel 부재 (indeterminate): layer=%s", layer_name)
            await _update_build_db(
                build_db_id,
                status="error",
                cloud_init_status="indeterminate",
                progress_step="sentinel 부재",
                error_message="console_output에서 sentinel을 찾을 수 없습니다",
                completed=True,
            )

    except Exception as exc:
        _logger.error("[layer_build] 빌드 실패: layer=%s", layer_name, exc_info=True)
        await _update_build_db(
            build_db_id,
            status="error",
            cloud_init_status="failure",
            progress_step="빌드 실패",
            error_message=str(exc)[:1000],
            completed=True,
        )

    finally:
        if conn is not None:
            # RW rule 잔여분 회수 (예외 경로 — 성공 시에는 이미 봉인됨)
            if rw_access_id and new_share_id:
                try:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, new_share_id, rw_access_id)
                except Exception:
                    _logger.warning("[layer_build] finally: RW rule 회수 실패", exc_info=True)
            # 조상 RO rule 회수 (항상 — 빌드 VM이 종료됐으므로 불필요)
            for _sid, _aid in ancestor_ro_access_ids:
                try:
                    await asyncio.to_thread(manila.revoke_access_rule, conn, _sid, _aid)
                except Exception:
                    _logger.warning("[layer_build] finally: 조상 RO rule 회수 실패 share=%s", _sid, exc_info=True)
            # 빌드 실패 시 신규 share 삭제 (고아 방지)
            if not build_succeeded and new_share_id:
                try:
                    await asyncio.to_thread(manila.delete_file_storage, conn, new_share_id)
                    _logger.info("[layer_build] 실패한 share 삭제: %s", new_share_id)
                except Exception:
                    _logger.warning("[layer_build] 실패한 share 삭제 실패: %s", new_share_id, exc_info=True)
            # server + port 정리
            if server_id:
                try:
                    await asyncio.to_thread(conn.compute.delete_server, server_id)
                    _logger.info("[layer_build] server 삭제: %s", server_id)
                except Exception:
                    _logger.warning("[layer_build] server 삭제 실패: %s", server_id, exc_info=True)
            if port_id:
                try:
                    await asyncio.to_thread(neutron.delete_port, conn, port_id)
                    _logger.info("[layer_build] port 삭제: %s", port_id)
                except Exception:
                    _logger.warning("[layer_build] port 삭제 실패: %s", port_id, exc_info=True)
            try:
                await asyncio.to_thread(conn.close)
            except Exception:
                _logger.warning("[layer_build] service connection close failed", exc_info=True)


# ---------------------------------------------------------------------------
# 소비 인스턴스 생성
# ---------------------------------------------------------------------------


async def resolve_layer_consume_resource_snapshot(
    conn,
    *,
    flavor_ref: str,
    network_id: str | None,
) -> dict[str, dict[str, str]]:
    """Validate and freeze consumer placement before creating its DB row."""
    from app.services.resource_policies import ResourcePolicyValidationError, validate_existing_selection
    from app.services.resource_policy_store import get_policy_snapshot, resolve_policy_snapshot

    try:
        if network_id:
            network = await validate_existing_selection(conn, "nova.default_network", network_id)
        else:
            network = (await resolve_policy_snapshot(conn=conn, keys=("nova.default_network",)))["nova.default_network"]
        flavor = await asyncio.to_thread(conn.compute.find_flavor, flavor_ref)
        if flavor is None:
            raise ResourcePolicyValidationError(f"플레이버를 찾을 수 없습니다: {flavor_ref!r}")
        service_project = (await get_policy_snapshot(("openstack.service_project",)))["openstack.service_project"]
        if service_project is None:
            raise ResourcePolicyValidationError("required resource policy is not configured: openstack.service_project")
    except ResourcePolicyValidationError as exc:
        raise RuntimeError(str(exc)) from exc
    return {
        "network": {"id": network["id"], "name": network["name"]},
        "flavor": {"id": str(flavor.id), "name": str(getattr(flavor, "name", flavor.id))},
        "openstack.service_project": service_project,
    }


def _consumer_artifact_entry(art, settings) -> dict:
    snapshot = _artifact_base_image_snapshot(art, settings)
    return {
        "id": art.id,
        "name": art.name,
        "kind": getattr(art, "kind", None),
        "parent_id": getattr(art, "parent_id", None),
        "blob_digest": getattr(art, "blob_digest", None),
        "share_id": art.share_id,
        "sqsh_filename": art.sqsh_filename,
        "ubuntu_base": normalize_ubuntu_base(snapshot.get("ubuntu_base")),
        "base_image_id": snapshot.get("base_image_id"),
        "base_image_checksum": snapshot.get("base_image_checksum"),
        "base_image_os_hash_algo": snapshot.get("base_image_os_hash_algo"),
        "base_image_os_hash_value": snapshot.get("base_image_os_hash_value"),
    }


async def resolve_import_consume_artifacts(import_id: int) -> tuple[str, list[dict]]:
    """Resolve one completed import's exact sealed root-first chain, not its mutable profile."""
    from app.database import get_session_factory
    from app.models.db import LayerArtifact, LayerImportJob

    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DB 연결이 초기화되지 않았습니다")
    async with factory() as session:
        job = await session.get(LayerImportJob, import_id)
        if job is None or job.status != "complete":
            raise RuntimeError(f"완료된 Dockerfile 작업을 찾을 수 없습니다: {import_id}")
        ids = job.artifact_ids
        if (
            not isinstance(ids, list)
            or not ids
            or any(type(item) is not int or item <= 0 for item in ids)
            or len(ids) != len(set(ids))
        ):
            raise RuntimeError("Dockerfile 작업의 artifact IDs가 유효하지 않습니다")
        artifacts = []
        settings = get_settings()
        for index, artifact_id in enumerate(ids):
            art = await session.get(LayerArtifact, artifact_id)
            if art is None or not art.is_sealed or not art.share_id or not art.blob_digest:
                raise RuntimeError(f"봉인된 작업 artifact를 찾을 수 없습니다: {artifact_id}")
            expected_parent = None if index == 0 else ids[index - 1]
            expected_kind = "dockerfile-root" if index == 0 else "dockerfile"
            if art.parent_id != expected_parent or art.kind != expected_kind:
                raise RuntimeError("Dockerfile 작업의 artifact lineage가 일치하지 않습니다")
            artifacts.append(_consumer_artifact_entry(art, settings))
        return job.profile_name, artifacts


async def resolve_admin_consume_artifacts(profile_name: str) -> list[dict]:
    """Freeze a sealed profile and its complete root ancestry by artifact ID."""
    from sqlalchemy import select

    from app.database import get_session_factory
    from app.models.db import LayerArtifact, LayerProfile

    async with get_session_factory()() as session:
        profile = (
            await session.execute(select(LayerProfile).where(LayerProfile.name == profile_name))
        ).scalar_one_or_none()
        if profile is None or not profile.layers:
            raise RuntimeError(f"프로필을 찾을 수 없거나 레이어가 비어 있습니다: {profile_name!r}")
        selected = []
        for name in profile.layers:
            art = (
                await session.execute(
                    select(LayerArtifact)
                    .where(LayerArtifact.name == name)
                    .where(LayerArtifact.is_sealed.is_(True))
                    .order_by(LayerArtifact.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            if art is None:
                raise RuntimeError(f"봉인된 레이어 아티팩트를 찾을 수 없습니다: {name!r}")
            selected.append(art)
        if any(art.kind in {"dockerfile-root", "dockerfile"} for art in selected):
            child = selected[0]
            lineage = []
            seen = set()
            while child is not None:
                if child.id in seen or not child.is_sealed:
                    raise RuntimeError("dockerfile-root lineage is cyclic or unsealed")
                seen.add(child.id)
                lineage.append(child)
                if child.parent_id is None:
                    break
                child = await session.get(LayerArtifact, child.parent_id)
                if child is None:
                    raise RuntimeError("dockerfile-root lineage is incomplete")
            if lineage[-1].kind != "dockerfile-root":
                raise RuntimeError("dockerfile lineage has no sealed full root")
            lineage.reverse()
            selected_ids = [art.id for art in selected]
            if selected_ids != [art.id for art in reversed(lineage)] and selected_ids != [lineage[-1].id]:
                raise RuntimeError("프로필의 dockerfile-root lineage가 일치하지 않습니다")
            selected = lineage
        settings = get_settings()
        return [_consumer_artifact_entry(art, settings) for art in selected]


async def validate_consume_image_identity(conn, artifacts: list[dict], image_id: str | None = None) -> None:
    """Reject drifted/inaccessible Glance images before allocating a consumer."""
    from app.services.layer_base_images import resolve_base_image_snapshot

    if not artifacts:
        raise RuntimeError("소비할 레이어 목록이 비어 있습니다")
    base_ids = {str(entry.get("base_image_id") or "") for entry in artifacts}
    bases = {normalize_ubuntu_base(entry.get("ubuntu_base")) for entry in artifacts}
    if "" in base_ids or len(base_ids) != 1 or len(bases) != 1:
        raise RuntimeError("프로필 레이어의 base image가 일치하지 않습니다")
    base_id = next(iter(base_ids))
    if image_id and image_id != base_id:
        raise RuntimeError("요청 image_id가 프로필 base image와 일치하지 않습니다")
    try:
        live_image = await asyncio.to_thread(resolve_base_image_snapshot, conn, base_id, next(iter(bases)))
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    for fingerprint_field in ("base_image_checksum", "base_image_os_hash_algo", "base_image_os_hash_value"):
        for entry in artifacts:
            if entry.get(fingerprint_field) and str(entry[fingerprint_field]) != str(live_image.get(fingerprint_field)):
                raise RuntimeError(f"base image identity mismatch: {fingerprint_field}")


async def run_layer_consume(
    consume_db_id: int | None,
    profile_name: str,
    server_name: str | None,
    flavor_id: str,
    image_id: str | None = None,
    network_id: str | None = None,
    ssh_public_key: str | None = None,
    ssh_username: str | None = None,
    github_username: str | None = None,
    custom_userdata: str | None = None,
    resource_snapshot: dict | None = None,
    *,
    compute_conn=None,
    share_conn=None,
    artifact_ids: list[int] | None = None,
    resolved_artifacts: list[dict] | None = None,
) -> str:
    """Create a layer consumer VM.

    Admin callers keep the historical default: service-project compute and Manila.
    Public callers pass a caller-scoped compute connection plus the service-project
    Manila connection and concrete artifact ids so authorization cannot drift to a
    newer unpublished artifact with the same name.
    """
    from sqlalchemy import select as _select

    from app.database import get_session_factory
    from app.models.db import LayerArtifact

    settings = get_settings()
    resource_snapshot = resource_snapshot or {}
    network_snapshot = resource_snapshot.get("network") or {}
    flavor_snapshot = resource_snapshot.get("flavor") or {}
    service_project_snapshot = resource_snapshot.get("openstack.service_project") or {}
    effective_network_id = network_snapshot.get("id")
    resolved_flavor_id = flavor_snapshot.get("id")
    if not all((effective_network_id, resolved_flavor_id, service_project_snapshot.get("id"))):
        raise RuntimeError("consume resource snapshot is incomplete")

    owned_compute_conn = compute_conn
    owned_share_conn = share_conn
    owns_compute_connection = compute_conn is None
    owns_share_connection = share_conn is None
    port_id: str | None = None
    server_id: str | None = None
    upper_volume_id: str | None = None
    consume_ro_access_ids: list[tuple[str, str]] = []
    health_key_path: str | None = None
    health_public_key: str | None = None

    try:
        if resolved_artifacts is not None:
            artifact_entries = list(resolved_artifacts)
        elif artifact_ids is not None:
            if not artifact_ids:
                raise RuntimeError("소비할 레이어 artifact 목록이 비어 있습니다")
            ordered_ids = list(dict.fromkeys(artifact_ids))
            async with get_session_factory()() as _art_session:
                rows = (
                    (await _art_session.execute(_select(LayerArtifact).where(LayerArtifact.id.in_(ordered_ids))))
                    .scalars()
                    .all()
                )
                by_id = {row.id: row for row in rows}
                missing = [artifact_id for artifact_id in ordered_ids if artifact_id not in by_id]
                if missing:
                    raise RuntimeError(f"레이어 artifact를 찾을 수 없습니다: {missing}")
                artifact_entries = [
                    _consumer_artifact_entry(by_id[artifact_id], settings) for artifact_id in ordered_ids
                ]
        else:
            artifact_entries = await resolve_admin_consume_artifacts(profile_name)

        if not artifact_entries:
            raise RuntimeError("소비할 레이어 목록이 비어 있습니다")

        layer_share_info: list[tuple[str, str]] = []
        profile_ubuntu_bases: set[str] = set()
        profile_base_image_ids: set[str] = set()
        for entry in artifact_entries:
            share_id = str(entry.get("share_id") or "")
            sqsh_filename = str(entry.get("sqsh_filename") or "")
            if not share_id:
                raise RuntimeError(f"레이어 {entry.get('name')!r}에 share_id가 없습니다")
            if not sqsh_filename:
                raise RuntimeError(f"레이어 {entry.get('name')!r}에 sqsh_filename이 없습니다")
            resolved_image_id = entry.get("base_image_id")
            if not resolved_image_id:
                raise RuntimeError(f"레이어 {entry.get('name')!r}의 base_image_id를 확인할 수 없습니다")
            profile_ubuntu_bases.add(normalize_ubuntu_base(entry.get("ubuntu_base")))
            profile_base_image_ids.add(str(resolved_image_id))
            layer_share_info.append((share_id, sqsh_filename))

        if len(profile_ubuntu_bases) != 1:
            raise RuntimeError(
                f"프로필 레이어의 Ubuntu base가 일치하지 않습니다: {', '.join(sorted(profile_ubuntu_bases))}"
            )
        if len(profile_base_image_ids) != 1:
            raise RuntimeError(
                f"프로필 레이어의 base image가 일치하지 않습니다: {', '.join(sorted(profile_base_image_ids))}"
            )
        profile_ubuntu_base = next(iter(profile_ubuntu_bases))
        profile_base_image_id = next(iter(profile_base_image_ids))
        if image_id and image_id != profile_base_image_id:
            raise RuntimeError("요청 image_id가 프로필 base image와 일치하지 않습니다")
        effective_image_id = profile_base_image_id
        root_mode = any(entry.get("kind") in {"dockerfile-root", "dockerfile"} for entry in artifact_entries)
        if root_mode:
            if artifact_entries[0].get("kind") != "dockerfile-root":
                raise RuntimeError("dockerfile lineage must begin with dockerfile-root")
            if any(entry.get("kind") != "dockerfile" for entry in artifact_entries[1:]):
                raise RuntimeError("dockerfile-root must be followed only by dockerfile deltas")
            for index, entry in enumerate(artifact_entries):
                expected_parent = None if index == 0 else artifact_entries[index - 1].get("id")
                if entry.get("parent_id") != expected_parent:
                    raise RuntimeError("dockerfile-root lineage is incomplete or out of order")
            if any(not entry.get("blob_digest") for entry in artifact_entries):
                raise RuntimeError("dockerfile lineage requires sealed blob digests")
        for field in ("base_image_checksum", "base_image_os_hash_algo", "base_image_os_hash_value"):
            recorded = {str(entry[field]) for entry in artifact_entries if entry.get(field)}
            if len(recorded) > 1:
                raise RuntimeError(f"프로필 레이어의 {field}가 일치하지 않습니다")

        for entry in artifact_entries:
            digest = entry.get("blob_digest")
            if digest and not re.fullmatch(r"sha256:[0-9a-f]{64}", str(digest)):
                raise RuntimeError(f"invalid sealed blob digest: {entry.get('id')}")
        if owned_compute_conn is None:
            from app.services.keystone import get_admin_connection_for_project

            owned_compute_conn = await asyncio.to_thread(
                get_admin_connection_for_project, service_project_snapshot["id"]
            )
        await validate_consume_image_identity(owned_compute_conn, artifact_entries, image_id)
        await _update_consume_db(consume_db_id, status="creating")

        if owned_share_conn is None:
            owned_share_conn = owned_compute_conn
        from app.services.instance_names import ensure_unique_instance_name

        try:
            server_name = await asyncio.to_thread(ensure_unique_instance_name, owned_compute_conn, server_name)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        await _update_consume_db(consume_db_id, server_name=server_name)

        token = uuid.uuid4().hex[:8]
        port_info = await asyncio.to_thread(
            neutron.create_port, owned_compute_conn, effective_network_id, f"afterglow-layer-consume-{token}"
        )
        port_id = port_info["id"]
        fixed_ip = port_info["fixed_ip"]
        await _update_consume_db(consume_db_id, port_id=port_id)

        mounts: list[tuple[str, str]] = []
        root_exports: list[list[str]] = []
        for share_id, sqsh_filename in layer_share_info:
            existing_rules = await asyncio.to_thread(manila.list_access_rules, owned_share_conn, share_id)
            existing_ids = {item.get("id") for item in existing_rules}
            rule = await asyncio.to_thread(
                manila.ensure_nfs_access_rule,
                owned_share_conn,
                share_id,
                fixed_ip,
                "ro",
                root_squash=False,
                sec_flavor="sys",
            )
            if rule["access_id"] not in existing_ids:
                consume_ro_access_ids.append((share_id, rule["access_id"]))

            export_locations = await asyncio.to_thread(manila.get_export_locations, owned_share_conn, share_id)
            if not export_locations:
                raise RuntimeError(f"share {share_id}의 export location이 없습니다")
            mounts.append((export_locations[0], sqsh_filename))
            if root_mode:
                root_exports.append(export_locations)
            _logger.info("[layer_consume] share RO rule: share=%s access=%s", share_id, rule["access_id"])

        health_token = uuid.uuid4().hex
        mounts_child_first = list(reversed(mounts))
        root_exports_child_first = list(reversed(root_exports)) if root_mode else None
        if root_mode:
            upper_volume = await asyncio.to_thread(
                cinder.create_empty_volume,
                owned_compute_conn,
                f"afterglow-root-upper-{token}",
                settings.upper_volume_size_gb,
            )
            upper_volume_id = upper_volume.id
            health_key_path, health_public_key = layer_consume_ssh.create_health_key()
        user_data_str = render_layer_consume_user_data(
            profile_name,
            mounts_child_first,
            ssh_public_key=ssh_public_key,
            ssh_username=ssh_username,
            github_username=github_username,
            root_mode=root_mode,
            health_token=health_token,
            digests=[entry.get("blob_digest") for entry in reversed(artifact_entries)] if root_mode else None,
            root_upper_volume_id=upper_volume_id,
            health_ssh_public_key=health_public_key,
            root_export_candidates=root_exports_child_first,
        )
        user_data_b64 = cloudinit.compose_userdata(
            base64.b64encode(user_data_str.encode()).decode(),
            custom_userdata,
        )

        server = await asyncio.to_thread(
            owned_compute_conn.compute.create_server,
            name=server_name,
            image_id=effective_image_id,
            flavor_id=resolved_flavor_id,
            networks=[{"port": port_id}],
            user_data=user_data_b64,
            **(
                {
                    "block_device_mapping_v2": [
                        {
                            "boot_index": 0,
                            "uuid": effective_image_id,
                            "source_type": "image",
                            "destination_type": "local",
                        },
                        {
                            "boot_index": -1,
                            "uuid": upper_volume_id,
                            "source_type": "volume",
                            "destination_type": "volume",
                            "delete_on_termination": True,
                        },
                    ]
                }
                if root_mode
                else {}
            ),
            metadata={
                "union_type": "layer-consumer",
                "layer_profile": profile_name,
                "ubuntu_base": profile_ubuntu_base,
                "base_image_id": profile_base_image_id,
                "afterglow_managed": "true",
                **({"union_upper_volume_id": upper_volume_id} if root_mode else {}),
            },
        )
        server_id = server.id
        await _update_consume_db(consume_db_id, server_id=server_id)
        proven_by_ssh = await _wait_for_consume_health(
            owned_compute_conn,
            server_id,
            health_token,
            ssh_host=fixed_ip if root_mode else None,
            ssh_key_path=health_key_path,
            ssh_username=ssh_username or "ubuntu",
        )
        if health_key_path and health_public_key:
            try:
                await layer_consume_ssh.remove_health_key(
                    fixed_ip, ssh_username or "ubuntu", health_key_path, health_public_key
                )
            except Exception:
                if proven_by_ssh:
                    raise
                _logger.warning("[layer_consume] temporary guest SSH key removal failed", exc_info=True)
        await _update_consume_db(consume_db_id, status="active", completed=True)
        _logger.info("[layer_consume] 소비 VM 생성: %s (%s), profile=%s", server_name, server_id, profile_name)
        return server_id

    except Exception as exc:
        _logger.error("[layer_consume] 소비 VM 생성 실패: %s", profile_name, exc_info=True)
        await _update_consume_db(
            consume_db_id,
            status="error",
            error_message=str(exc)[:1000],
            completed=True,
        )
        if not server_id:
            if upper_volume_id and owned_compute_conn is not None:
                try:
                    await asyncio.to_thread(cinder.delete_volume, owned_compute_conn, upper_volume_id)
                except Exception:
                    _logger.warning(
                        "[layer_consume] unclaimed Cinder upper cleanup failed: %s", upper_volume_id, exc_info=True
                    )
            if owned_share_conn is not None:
                for _sid, _aid in consume_ro_access_ids:
                    try:
                        await asyncio.to_thread(manila.revoke_access_rule, owned_share_conn, _sid, _aid)
                    except Exception:
                        _logger.warning(
                            "[layer_consume] RO rule 회수 실패: share=%s access=%s",
                            _sid,
                            _aid,
                            exc_info=True,
                        )
            if port_id and owned_compute_conn is not None:
                try:
                    await asyncio.to_thread(neutron.delete_port, owned_compute_conn, port_id)
                except Exception:
                    _logger.warning("[layer_consume] 실패 후 port 정리 실패", exc_info=True)
        raise

    finally:
        if health_key_path:
            try:
                os.unlink(health_key_path)
            except FileNotFoundError:
                pass
        connections_to_close: list[object] = []
        if owns_compute_connection and owned_compute_conn is not None:
            connections_to_close.append(owned_compute_conn)
        if owns_share_connection and owned_share_conn is not None and owned_share_conn is not owned_compute_conn:
            connections_to_close.append(owned_share_conn)
        for connection in connections_to_close:
            try:
                await asyncio.to_thread(connection.close)
            except Exception:
                _logger.warning("[layer_consume] connection close failed", exc_info=True)
