"""Bash guest helpers shared by activation and full-root initramfs.

Inventory records are device|type|driver|serial|kernel_ro|capacity_bytes.
Layers require kernel RO; the dedicated root upper requires kernel RW, no boot
or layer alias, and an empty disk before formatting. Reboots bind both the
persisted Cinder identity and the unique ext4 UUID before any writable mount.
No payload cache, loop device or Python guest runtime for block layers.
"""

LAYER_BLOCK_DEVICE_SH = r"""#!/bin/bash
set -euo pipefail
# Prefer the real copied utilities over initramfs BusyBox applets.
PATH=/usr/bin:/sbin:/bin:/usr/sbin
export PATH

layer_block_error() {
    echo "afterglow: $*" >&2
    return 1
}

layer_block_uuid() {
    local value="${1,,}" compact
    if [[ "$value" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
        printf '%s\n' "$value"
    elif [[ "$value" =~ ^[0-9a-f]{32}$ ]]; then
        compact="$value"
        printf '%s-%s-%s-%s-%s\n' "${compact:0:8}" "${compact:8:4}" "${compact:12:4}" "${compact:16:4}" "${compact:20:12}"
    else
        layer_block_error 'invalid Cinder volume UUID'
    fi
}

layer_block_inventory() {
    local sys name serial driver kind ro sectors
    for sys in /sys/class/block/*; do
        [ -e "$sys" ] || continue
        name="${sys##*/}"
        serial=
        if [ -r "$sys/serial" ]; then
            serial="$(< "$sys/serial")"
        elif [ -r "$sys/device/serial" ]; then
            serial="$(< "$sys/device/serial")"
        fi
        [ -n "$serial" ] || continue
        driver="$(/usr/bin/readlink -f "$sys/device/driver")" || return 1
        driver="${driver##*/}"
        kind=disk
        [ ! -e "$sys/partition" ] || kind=part
        ro="$(< "$sys/ro")"
        sectors="$(< "$sys/size")"
        [[ "$sectors" =~ ^[0-9]{1,16}$ ]] || { layer_block_error 'invalid kernel disk size'; return 1; }
        printf '/dev/%s|%s|%s|%s|%s|%s\n' "$name" "$kind" "$driver" "$serial" "$ro" "$((10#$sectors * 512))"
    done
}

layer_block_resolve() {
    local target volumes inventory device kind driver serial ro capacity extra policy="${3:-ro}"
    local supplied canonical compact serial_uuid matches matched count=0 found=
    target="$(layer_block_uuid "$1")" || return 1
    [ "$policy" = ro ] || [ "$policy" = rw ] || { layer_block_error 'invalid disk policy'; return 1; }
    volumes="$2"
    [ -s "$volumes" ] || { layer_block_error 'supplied volume inventory missing'; return 1; }
    inventory="$(layer_block_inventory)" || return 1
    while IFS='|' read -r device kind driver serial ro capacity extra; do
        [ -n "$device" ] || continue
        serial="${serial,,}"
        matches=0
        matched=
        serial_uuid=
        if [[ "$serial" =~ ^[0-9a-f]{32}$ || "$serial" =~ ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$ ]]; then
            serial_uuid="$(layer_block_uuid "$serial")" || return 1
        elif [ "${#serial}" -ne 20 ]; then
            continue
        fi
        while IFS= read -r supplied; do
            canonical="$(layer_block_uuid "$supplied")" || return 1
            compact="${canonical//-/}"
            if { [ -n "$serial_uuid" ] && [ "$serial_uuid" = "$canonical" ]; } ||
               { [ "${#serial}" -eq 20 ] && { [ "$serial" = "${canonical:0:20}" ] || [ "$serial" = "${compact:0:20}" ]; }; }; then
                matches=$((matches + 1))
                matched="$canonical"
            fi
        done < "$volumes"
        [ "$matches" -le 1 ] || { layer_block_error 'ambiguous Cinder serial among supplied volumes'; return 1; }
        [ "$matched" = "$target" ] || continue
        [ -z "$extra" ] && [ "$kind" = disk ] && [ "$driver" = virtio_blk ] || {
            layer_block_error 'unexpected layer disk type (requires whole virtio-blk disk)'; return 1;
        }
        if [ "$policy" = ro ]; then
            [ "$ro" = 1 ] || { layer_block_error 'layer device is not kernel readonly'; return 1; }
        else
            [ "$ro" = 0 ] || { layer_block_error 'upper device is not kernel writable'; return 1; }
        fi
        [[ "$capacity" =~ ^[0-9]{1,19}$ ]] || { layer_block_error 'invalid kernel disk capacity'; return 1; }
        count=$((count + 1))
        found="$device"
    done <<< "$inventory"
    if [ "$count" -eq 0 ]; then
        layer_block_error 'missing or ambiguous Cinder layer device'
        return 2
    fi
    [ "$count" -eq 1 ] || { layer_block_error 'missing or ambiguous Cinder layer device'; return 1; }
    printf '%s\n' "$found"
}

layer_block_verify() {
    local device="$1" digest="$2" size="$3" capacity actual
    [[ "$digest" =~ ^sha256:[0-9a-f]{64}$ ]] || { layer_block_error 'invalid layer digest'; return 1; }
    [[ "$size" =~ ^[1-9][0-9]{0,18}$ ]] && [ "$size" -le 9223372036854775807 ] || {
        layer_block_error 'invalid payload size'; return 1;
    }
    [ "$(blockdev --getro "$device")" = 1 ] || { layer_block_error 'layer device is not kernel readonly'; return 1; }
    capacity="$(blockdev --getsize64 "$device")" || return 1
    [[ "$capacity" =~ ^[0-9]{1,19}$ ]] && [ "$capacity" -ge "$size" ] || {
        layer_block_error 'insufficient layer device size'; return 1;
    }
    # GNU head stops at the sealed payload length, ignoring Cinder GiB padding.
    # bash pipefail propagates read errors rather than trusting a partial hash.
    actual="$(/usr/bin/head -c "$size" -- "$device" | /usr/bin/sha256sum)" || return 1
    [ "${actual%% *}" = "${digest#sha256:}" ] || { layer_block_error 'layer payload digest mismatch'; return 1; }
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    [ "$#" -eq 4 ] || { layer_block_error 'usage: layer-block-device.sh volume-id digest size-bytes supplied-volumes'; exit 1; }
    device="$(layer_block_resolve "$1" "$4")" || exit 1
    [ -b "$device" ] || { layer_block_error 'resolved layer is not a block device'; exit 1; }
    layer_block_verify "$device" "$2" "$3" || exit 1
    printf '%s\n' "$device"
fi
"""


LAYER_UPPER_DEVICE_SH = r"""#!/bin/bash
set -euo pipefail
. /usr/local/bin/layer-block-device.sh

layer_upper_resolve() {
    local target volumes="$2" manifest="$3" boot_mount="$4" device source ancestors path
    local unused file digest layer_id size
    target="$(layer_block_uuid "$1")" || return 1
    [ -s "$manifest" ] || { layer_block_error 'root layer manifest missing'; return 1; }
    while IFS='|' read -r unused file digest layer_id size; do
        [ -n "$layer_id" ] || continue
        layer_id="$(layer_block_uuid "$layer_id")" || return 1
        [ "$target" != "$layer_id" ] || { layer_block_error 'upper conflicts with a layer volume'; return 1; }
    done < "$manifest"
    device="$(layer_block_resolve "$target" "$volumes" rw)" || return $?
    source="$(findmnt -n -o SOURCE --target "$boot_mount")" || return 1
    [ -n "$source" ] || { layer_block_error 'boot device unavailable'; return 1; }
    ancestors="$(lsblk -s -n -r -o PATH -- "$source")" || return 1
    [ -n "$ancestors" ] || { layer_block_error 'boot disk ancestry unavailable'; return 1; }
    while IFS= read -r path; do
        [ "$device" != "$path" ] || { layer_block_error 'upper is the boot disk'; return 1; }
    done <<< "$ancestors"
    [ "$(blockdev --getro "$device")" = 0 ] || { layer_block_error 'upper device is not kernel writable'; return 1; }
    printf '%s\n' "$device"
}

layer_upper_empty() {
    local device="$1" capacity status
    [ "$(lsblk -n -r -o TYPE -- "$device")" = disk ] || {
        layer_block_error 'upper is not an empty dedicated disk'; return 1;
    }
    if blkid -p "$device" >/dev/null 2>&1; then
        layer_block_error 'upper is not empty; refusing to format'; return 1
    else
        status=$?
        [ "$status" -eq 2 ] || { layer_block_error 'upper signature probe failed'; return 1; }
    fi
    capacity="$(blockdev --getsize64 "$device")" || return 1
    [[ "$capacity" =~ ^[1-9][0-9]{0,18}$ ]] && [ "$capacity" -le 9223372036854775807 ] || return 1
    # No recognizable filesystem is not proof of emptiness: reject raw data too.
    cmp -n "$capacity" -- "$device" /dev/zero >/dev/null || {
        layer_block_error 'upper is not empty; refusing to format'; return 1;
    }
}

layer_upper_filesystems() {
    local sys device uuid status
    # Probe every block node, including partitions and disks without serials.
    # Never use blkid's UUID cache/first-match lookup for a writable mount.
    for sys in /sys/class/block/*; do
        [ -e "$sys" ] || continue
        device="/dev/${sys##*/}"
        if uuid="$(blkid -p -s UUID -o value "$device")"; then
            [ -z "$uuid" ] || printf '%s|%s\n' "$device" "$uuid"
        else
            status=$?
            [ "$status" -eq 2 ] || { layer_block_error 'filesystem UUID probe failed'; return 1; }
        fi
    done
}

layer_upper_verify() {
    local device="$1" expected actual filesystems path uuid count=0
    expected="$(layer_block_uuid "$2")" || return 1
    [ "$(blkid -p -s TYPE -o value "$device")" = ext4 ] || {
        layer_block_error 'upper filesystem is not ext4'; return 1;
    }
    actual="$(blkid -p -s UUID -o value "$device")" || return 1
    actual="$(layer_block_uuid "$actual")" || return 1
    [ "$actual" = "$expected" ] || { layer_block_error 'upper filesystem UUID mismatch'; return 1; }
    filesystems="$(layer_upper_filesystems)" || return 1
    while IFS='|' read -r path uuid; do
        [ -n "$uuid" ] || continue
        [ "${uuid,,}" = "$expected" ] || continue
        [ "$path" = "$device" ] || { layer_block_error 'duplicate upper filesystem UUID'; return 1; }
        count=$((count + 1))
    done <<< "$filesystems"
    [ "$count" -eq 1 ] || { layer_block_error 'missing or duplicate upper filesystem UUID'; return 1; }
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
    [ "$#" -ge 5 ] || { layer_block_error 'usage: layer-upper-device.sh prepare|boot volume-id supplied-volumes root-conf boot-mount [filesystem-uuid]'; exit 1; }
    mode="$1"
    case "$mode:$#" in prepare:5|boot:6) ;; *) layer_block_error 'invalid upper device arguments'; exit 1 ;; esac
    # Preserve the first-boot attachment wait; identity/policy failures never retry.
    for ((attempt=0; ; attempt++)); do
        if device="$(layer_upper_resolve "$2" "$3" "$4" "$5")"; then break; else status=$?; fi
        [ "$mode" = prepare ] && [ "$status" -eq 2 ] && [ "$attempt" -lt 90 ] || exit 1
        sleep 2
    done
    [ -b "$device" ] || { layer_block_error 'resolved upper is not a block device'; exit 1; }
    if [ "$mode" = prepare ]; then
        layer_upper_empty "$device" || exit 1
    else
        layer_upper_verify "$device" "$6" || exit 1
    fi
    printf '%s\n' "$device"
fi
"""
