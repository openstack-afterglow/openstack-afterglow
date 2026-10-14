from __future__ import annotations

import logging
from collections.abc import Mapping
from copy import copy
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import openstack

from openstack.compute.v2.server import Server
from openstack.exceptions import ResourceNotFound
from openstack.proxy import Proxy
from openstack.resource import Resource

from app.models.storage import VolumeInfo

_logger = logging.getLogger(__name__)


def create_volume_from_image(
    conn: openstack.connection.Connection,
    name: str,
    image_id: str,
    size_gb: int,
    availability_zone: str | None = None,
) -> VolumeInfo:
    """OS 이미지를 소스로 부트 볼륨 생성."""
    kwargs = {
        "name": name,
        "size": size_gb,
        "imageRef": image_id,
    }
    if availability_zone:
        kwargs["availability_zone"] = availability_zone

    vol = conn.block_storage.create_volume(**kwargs)
    vol = conn.block_storage.wait_for_status(vol, status="available", wait=300)
    return _vol_to_info(vol)


def create_empty_volume(
    conn: openstack.connection.Connection,
    name: str,
    size_gb: int,
    availability_zone: str | None = None,
) -> VolumeInfo:
    """upperdir 용 빈 볼륨 생성."""
    kwargs = {"name": name, "size": size_gb}
    if availability_zone:
        kwargs["availability_zone"] = availability_zone

    vol = conn.block_storage.create_volume(**kwargs)
    try:
        vol = conn.block_storage.wait_for_status(vol, status="available", wait=120)
    except Exception:
        try:
            conn.block_storage.delete_volume(vol.id, ignore_missing=True)
        except Exception:
            _logger.warning("Failed to delete unavailable empty volume %s", vol.id, exc_info=True)
        raise
    return _vol_to_info(vol)


def rename_volume(conn: openstack.connection.Connection, volume_id: str, new_name: str) -> None:
    conn.block_storage.update_volume(volume_id, name=new_name)


def delete_volume(conn: openstack.connection.Connection, volume_id: str) -> None:
    conn.block_storage.delete_volume(volume_id, ignore_missing=True)


def set_volume_readonly(conn, volume_id: str) -> dict:
    """Use Cinder's action, never ordinary user-writable metadata as proof."""
    response = conn.block_storage.post(
        f"/volumes/{volume_id}/action", json={"os-update_readonly_flag": {"readonly": True}}
    )
    response.raise_for_status()
    return get_volume_details(conn, volume_id)


def get_volume_details(conn, volume_id: str) -> dict:
    response = conn.block_storage.get(f"/volumes/{volume_id}")
    response.raise_for_status()
    return response.json()["volume"]


def reset_volume_status(
    conn: openstack.connection.Connection,
    volume_id: str,
    status: str = "error",
    attach_status: str | None = None,
) -> None:
    """볼륨 상태를 강제로 변경한다 (Cinder os-reset_status action).

    attach_status 지정 시 함께 변경한다 (예: 'attached'). 기존 호출부 호환 유지.
    """
    conn.block_storage.reset_volume_status(volume_id, status, attach_status)


def force_delete_volume(conn: openstack.connection.Connection, volume_id: str) -> None:
    """볼륨을 강제 삭제한다 (Cinder os-force_delete action). 관리자 전용."""
    endpoint = conn.block_storage.get_endpoint()
    resp = conn.session.post(
        f"{endpoint}/volumes/{volume_id}/action",
        json={"os-force_delete": {}},
    )
    if hasattr(resp, "raise_for_status"):
        resp.raise_for_status()


MAX_VOLUME_SIZE = 2**31 - 1


class VolumeExtensionError(ValueError):
    """A project extension whose target or safe provider state cannot be proven."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code


def _extension_field(resource, name: str, api_name: str | None = None, default=None):
    if isinstance(resource, Resource):
        # Resource subclasses dict, but its dict snapshot can predate fetch().
        # Preserve authoritative Nova power/task values before SDK descriptors
        # coerce them (e.g. a malformed fractional power value must not become 4).
        # Only an explicit provider null proves that task_state is idle.
        if isinstance(resource, Server) and api_name:
            return _extension_field(resource._body.attributes, name, api_name, default)
        if name == "size":
            # Cinder's int descriptor would coerce bool/fraction/string data.
            return resource._body.attributes.get("size", default)
        return getattr(resource, name, default)
    if isinstance(resource, Mapping):
        if api_name and name in resource and api_name in resource and resource[name] != resource[api_name]:
            raise VolumeExtensionError(409, "공급자 상태 정보가 일치하지 않습니다")
        return resource.get(name, resource.get(api_name, default) if api_name else default)
    return getattr(resource, name, default)


def _extension_owned(resource, project_id: str) -> bool:
    owner = _extension_field(resource, "project_id")
    tenant = _extension_field(resource, "tenant_id")
    return bool(owner or tenant) and all(value == project_id for value in (owner, tenant) if value)


def _extension_volume(conn, volume_id: str, project_id: str, new_size: int):
    try:
        volume = conn.block_storage.get_volume(volume_id)
    except ResourceNotFound as exc:
        raise VolumeExtensionError(404, "볼륨을 찾을 수 없습니다") from exc
    if volume is None or _extension_field(volume, "id") != volume_id or not _extension_owned(volume, project_id):
        raise VolumeExtensionError(404, "볼륨을 찾을 수 없습니다")
    size = _extension_field(volume, "size")
    if type(size) is not int or not 0 < size <= MAX_VOLUME_SIZE:
        raise VolumeExtensionError(409, "현재 볼륨 크기를 확인할 수 없습니다")
    if new_size <= size:
        raise VolumeExtensionError(400, f"새 크기({new_size}GB)는 현재 크기({size}GB)보다 커야 합니다")
    status = _extension_field(volume, "status")
    attachments = _extension_field(volume, "attachments")
    if not isinstance(attachments, list) or not all(isinstance(a, Mapping) for a in attachments):
        raise VolumeExtensionError(409, "볼륨 연결 상태를 확인할 수 없습니다")
    if not ((status == "available" and not attachments) or (status == "in-use" and attachments)):
        raise VolumeExtensionError(409, "현재 볼륨 상태에서는 확장할 수 없습니다")
    return volume, (status, size, [dict(a) for a in attachments])


def extend_volume(conn: openstack.connection.Connection, volume_id: str, new_size: int) -> VolumeInfo:
    """Extend an owned, detached or positively powered-off volume, without guest I/O.

    This project helper deliberately has no system-admin ownership bypass. The
    separate global admin API retains its direct SDK action and response contract.
    Provider acceptance is asynchronous: return the reread, never the desired size.
    """
    if type(new_size) is not int or not 0 < new_size <= MAX_VOLUME_SIZE:
        raise VolumeExtensionError(400, "새 크기는 1~2147483647 사이의 정수여야 합니다")
    project_id = getattr(conn, "_afterglow_project_id", None)
    if not isinstance(project_id, str) or not project_id:
        raise VolumeExtensionError(404, "볼륨을 찾을 수 없습니다")
    _, before = _extension_volume(conn, volume_id, project_id, new_size)
    for attachment in before[2]:
        server_id = attachment.get("server_id")
        if (
            not isinstance(server_id, str)
            or not server_id.strip()
            or attachment.get("volume_id", volume_id) != volume_id
            or attachment.get("status", "attached") != "attached"
        ):
            raise VolumeExtensionError(409, "볼륨 연결 대상을 확인할 수 없습니다")
        try:
            server = conn.compute.get_server(server_id)
        except ResourceNotFound as exc:
            raise VolumeExtensionError(409, "볼륨 연결 대상을 확인할 수 없습니다") from exc
        missing = object()
        power = _extension_field(server, "power_state", "OS-EXT-STS:power_state")
        task = _extension_field(server, "task_state", "OS-EXT-STS:task_state", missing)
        volumes = _extension_field(server, "attached_volumes", "os-extended-volumes:volumes_attached")
        if (
            server is None
            or _extension_field(server, "id") != server_id
            or not _extension_owned(server, project_id)
            or _extension_field(server, "status") != "SHUTOFF"
            # Nova's authoritative SHUTDOWN power state is 4, not NOSTATE (0).
            or not ((type(power) is int and power == 4) or (type(power) is str and power == "4"))
            or task is not None
            or not isinstance(volumes, list)
            or not all(isinstance(v, Mapping) and isinstance(v.get("id"), str) for v in volumes)
            or not any(v["id"] == volume_id for v in volumes)
        ):
            raise VolumeExtensionError(409, "연결된 모든 인스턴스의 소유권과 전원 종료 상태를 확인해야 합니다")
    # Fence Cinder changes during Nova reads. No cache, audit, or other work is
    # interposed between this final authoritative snapshot and the provider action.
    _, latest = _extension_volume(conn, volume_id, project_id, new_size)
    if latest != before:
        raise VolumeExtensionError(409, "볼륨 상태가 변경되었습니다. 다시 시도해 주세요")
    conn.block_storage.extend_volume(volume_id, new_size)
    try:
        volume = conn.block_storage.get_volume(volume_id)
    except Exception as exc:
        raise VolumeExtensionError(502, "확장 요청 후 볼륨을 확인할 수 없습니다") from exc
    if volume is None or _extension_field(volume, "id") != volume_id or not _extension_owned(volume, project_id):
        raise VolumeExtensionError(502, "확장 요청 후 볼륨을 확인할 수 없습니다")
    size = _extension_field(volume, "size")
    status = _extension_field(volume, "status")
    attachments = _extension_field(volume, "attachments")
    if (
        type(size) is not int
        or not 0 < size <= MAX_VOLUME_SIZE
        or not isinstance(status, str)
        or not status
        or not isinstance(attachments, list)
        or not all(isinstance(a, Mapping) for a in attachments)
    ):
        raise VolumeExtensionError(502, "확장 요청 후 볼륨 상태를 확인할 수 없습니다")
    return _vol_to_info(volume)


def get_volume(conn: openstack.connection.Connection, volume_id: str) -> VolumeInfo:
    vol = conn.block_storage.get_volume(volume_id)
    return _vol_to_info(vol)


def list_volumes(conn: openstack.connection.Connection) -> list[VolumeInfo]:
    return [_vol_to_info(v) for v in conn.block_storage.volumes(details=True)]


def get_volume_limits(conn: openstack.connection.Connection) -> dict:
    """프로젝트의 Cinder 리소스 사용량/한도 조회."""
    limits = conn.block_storage.get_limits()
    a = limits.absolute
    return {
        "volumes_used": getattr(a, "total_volumes_used", 0),
        "volumes_limit": getattr(a, "max_total_volumes", -1),
        "gigabytes_used": getattr(a, "total_gigabytes_used", 0),
        "gigabytes_limit": getattr(a, "max_total_volume_gigabytes", -1),
    }


_QUOTA_KEYS = ("volumes", "snapshots", "gigabytes", "backups", "backup_gigabytes")


def get_volume_quota(conn: openstack.connection.Connection, project_id: str, *, strict: bool = False) -> dict:
    """프로젝트의 상세 Cinder 할당량 (usage 포함).

    Overview callers use ``strict`` to require explicit usage fields for the
    rendered resources.  Default callers keep legacy sentinel fallback
    semantics intact.
    """

    def _normalize(q) -> dict:
        if isinstance(q, dict):
            return {"limit": int(q.get("limit", -1)), "in_use": int(q.get("in_use", 0))}
        if isinstance(q, int):
            return {"limit": q, "in_use": 0}
        return {"limit": -1, "in_use": 0}

    def _strict_entry(q, key: str) -> dict:
        if not isinstance(q, dict) or "limit" not in q or "in_use" not in q:
            raise ValueError(f"Cinder quota usage is missing for {key}")
        limit, in_use = q["limit"], q["in_use"]
        if (
            not isinstance(limit, (int, float))
            or isinstance(limit, bool)
            or not isinstance(in_use, (int, float))
            or isinstance(in_use, bool)
        ):
            raise ValueError(f"Cinder quota data is malformed for {key}")
        return {"limit": limit, "in_use": in_use}

    def _strict_limits_entry(limits, limit_attr: str, used_attr: str, key: str) -> dict:
        limit = getattr(limits, limit_attr, None)
        in_use = getattr(limits, used_attr, None)
        if limit is None or in_use is None:
            raise ValueError(f"Cinder limits usage is missing for {key}")
        return _strict_entry({"limit": limit, "in_use": in_use}, key)

    try:
        bs_endpoint = conn.block_storage.get_endpoint()
        resp = conn.session.get(f"{bs_endpoint}/os-quota-sets/{project_id}", params={"usage": "true"})
        if strict:
            resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError("Cinder quota payload is malformed")
        qs = payload.get("quota_set", {})
        if not isinstance(qs, dict):
            raise ValueError("Cinder quota_set is malformed")
        if strict:
            return {key: _strict_entry(qs.get(key), key) for key in ("volumes", "gigabytes")}
        return {k: _normalize(qs.get(k)) for k in _QUOTA_KEYS}
    except Exception as exc:
        if strict and isinstance(exc, ValueError):
            raise
        import logging as _logging

        _logging.getLogger(__name__).warning("Cinder quota_set 조회 실패 — limits API로 fallback", exc_info=True)
        limits = conn.block_storage.get_limits()
        absolute = limits.absolute
        if strict:
            return {
                "volumes": _strict_limits_entry(absolute, "max_total_volumes", "total_volumes_used", "volumes"),
                "gigabytes": _strict_limits_entry(
                    absolute, "max_total_volume_gigabytes", "total_gigabytes_used", "gigabytes"
                ),
            }
        return {
            "volumes": {
                "limit": getattr(absolute, "max_total_volumes", -1),
                "in_use": getattr(absolute, "total_volumes_used", 0),
            },
            "snapshots": {
                "limit": getattr(absolute, "max_total_snapshots", -1),
                "in_use": getattr(absolute, "total_snapshots_used", 0),
            },
            "gigabytes": {
                "limit": getattr(absolute, "max_total_volume_gigabytes", -1),
                "in_use": getattr(absolute, "total_gigabytes_used", 0),
            },
            "backups": {
                "limit": getattr(absolute, "max_total_backups", -1),
                "in_use": getattr(absolute, "total_backups_used", 0),
            },
            "backup_gigabytes": {
                "limit": getattr(absolute, "max_total_backup_gigabytes", -1),
                "in_use": getattr(absolute, "total_backup_gigabytes_used", 0),
            },
        }


def get_volume_image_metadata(conn: openstack.connection.Connection, volume_id: str) -> dict | None:
    """부트 볼륨의 원본 이미지 메타데이터 반환 (volume_image_metadata 필드)."""
    try:
        vol = conn.block_storage.get_volume(volume_id)
        raw = vol.to_dict() if hasattr(vol, "to_dict") else {}
        return raw.get("volume_image_metadata") or getattr(vol, "volume_image_metadata", None)
    except Exception:
        return None


def list_backups(
    conn: openstack.connection.Connection,
    *,
    volume_id: str | None = None,
    all_projects: bool = False,
) -> list[dict]:
    kwargs: dict = {}
    if volume_id:
        kwargs["volume_id"] = volume_id
    if all_projects:
        kwargs["all_projects"] = True
    return [_backup_to_dict(b) for b in conn.block_storage.backups(details=True, **kwargs)]


def list_volume_attachments(conn: openstack.connection.Connection, volume_id: str) -> list[dict]:
    endpoint = conn.block_storage.get_endpoint().rstrip("/")
    response = conn.session.get(
        f"{endpoint}/attachments",
        params={"all_tenants": "1", "volume_id": volume_id},
        headers={"OpenStack-API-Version": "volume 3.70"},
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("attachments", [])) if isinstance(payload, dict) else []


def list_volume_messages(conn: openstack.connection.Connection, volume_id: str) -> list[dict]:
    endpoint = conn.block_storage.get_endpoint().rstrip("/")
    response = conn.session.get(
        f"{endpoint}/messages",
        params={
            "all_tenants": "1",
            "resource_uuid": volume_id,
            "limit": "50",
            "sort": "created_at:desc",
        },
        headers={"OpenStack-API-Version": "volume 3.70"},
    )
    response.raise_for_status()
    payload = response.json()
    return list(payload.get("messages", [])) if isinstance(payload, dict) else []


def get_backup(conn: openstack.connection.Connection, backup_id: str) -> dict:
    b = conn.block_storage.get_backup(backup_id)
    return _backup_to_dict(b)


def create_backup(
    conn: openstack.connection.Connection,
    volume_id: str,
    name: str,
    description: str | None = None,
    incremental: bool = False,
    *,
    force: bool = False,
) -> dict:
    kwargs: dict = {"volume_id": volume_id, "name": name, "is_incremental": incremental, "force": force}
    if description:
        kwargs["description"] = description
    adapter = conn.block_storage
    if isinstance(adapter, Proxy):
        # A lost reply may already have created a backup. Scope the SDK's
        # transport/status retry override to this POST, not the caller session.
        adapter = copy(adapter)
        adapter.request = partial(adapter.request, connect_retries=0, status_code_retries=0)
    b = adapter.create_backup(**kwargs)
    return _backup_to_dict(b)


def delete_backup(conn: openstack.connection.Connection, backup_id: str) -> None:
    conn.block_storage.delete_backup(backup_id, ignore_missing=True)


def restore_backup(conn: openstack.connection.Connection, backup_id: str, volume_id: str | None = None) -> dict:
    kwargs: dict = {}
    if volume_id:
        kwargs["volume_id"] = volume_id
    result = conn.block_storage.restore_backup(backup_id, **kwargs)
    return {"volume_id": getattr(result, "volume_id", None), "volume_name": getattr(result, "volume_name", None)}


def list_snapshots(
    conn: openstack.connection.Connection,
    volume_id: str | None = None,
    caller_project_id: str | None = None,
    all_projects: bool = False,
) -> list[dict]:
    kwargs: dict = {}
    if volume_id:
        kwargs["volume_id"] = volume_id
    if all_projects:
        kwargs["all_projects"] = True
    snapshots = [_snapshot_to_dict(s) for s in conn.block_storage.snapshots(details=True, **kwargs)]
    if caller_project_id is not None:
        snapshots = [s for s in snapshots if s.get("project_id") == caller_project_id]
    return snapshots


def get_snapshot(conn: openstack.connection.Connection, snapshot_id: str) -> dict:
    s = conn.block_storage.get_snapshot(snapshot_id)
    return _snapshot_to_dict(s)


def create_snapshot(
    conn: openstack.connection.Connection,
    volume_id: str,
    name: str,
    description: str | None = None,
    force: bool = False,
) -> dict:
    kwargs: dict = {"volume_id": volume_id, "name": name, "is_forced": force}
    if description:
        kwargs["description"] = description
    s = conn.block_storage.create_snapshot(**kwargs)
    return _snapshot_to_dict(s)


def delete_snapshot(conn: openstack.connection.Connection, snapshot_id: str) -> None:
    conn.block_storage.delete_snapshot(snapshot_id, ignore_missing=True)


def _snapshot_to_dict(s) -> dict:
    return {
        "id": s.id,
        "name": s.name or "",
        "status": s.status,
        "volume_id": s.volume_id,
        "size": s.size,
        "description": getattr(s, "description", "") or "",
        "created_at": str(s.created_at) if getattr(s, "created_at", None) else None,
        "project_id": getattr(s, "project_id", None),
    }


def _backup_to_dict(b) -> dict:
    return {
        "id": b.id,
        "name": b.name or "",
        "status": b.status,
        "volume_id": b.volume_id,
        "size": b.size,
        "project_id": getattr(b, "project_id", None),
        "has_dependent_backups": getattr(b, "has_dependent_backups", None),
        "is_incremental": getattr(b, "is_incremental", None),
        "description": b.description or "",
        "created_at": str(b.created_at) if getattr(b, "created_at", None) else None,
    }


def wait_volume_available(
    conn: openstack.connection.Connection,
    volume_id: str,
    timeout: int = 120,
) -> VolumeInfo:
    """볼륨이 'available' 상태가 될 때까지 폴링."""
    vol = conn.block_storage.get_volume(volume_id)
    vol = conn.block_storage.wait_for_status(vol, status="available", wait=timeout)
    return _vol_to_info(vol)


def _transfer_result(transfer, *, created: bool = False, detail: bool = False) -> dict:
    result = {
        "id": transfer.id,
        "name": transfer.name or "",
        "volume_id": transfer.volume_id,
    }
    if detail or created:
        result["created_at"] = transfer.created_at
    if created:
        result["auth_key"] = transfer.auth_key
    return result


def create_volume_transfer(
    conn: openstack.connection.Connection,
    volume_id: str,
    name: str | None = None,
) -> dict:
    """Issue the native key once; never retry an ambiguous POST."""
    proxy = copy(conn.block_storage)
    proxy.request = partial(proxy.request, connect_retries=0, status_code_retries=0)
    attrs = {"volume_id": volume_id}
    if name:
        attrs["name"] = name
    return _transfer_result(proxy.create_transfer(**attrs), created=True)


def accept_volume_transfer(
    conn: openstack.connection.Connection,
    transfer_id: str,
    auth_key: str,
) -> dict:
    """Let native Cinder authenticate the key, without POST retries."""
    proxy = copy(conn.block_storage)
    proxy.request = partial(proxy.request, connect_retries=0, status_code_retries=0)
    return _transfer_result(proxy.accept_transfer(transfer_id, auth_key))


def list_volume_transfers(conn: openstack.connection.Connection) -> list[dict]:
    """Only the caller token's project, including for administrator tokens."""
    return [
        _transfer_result(transfer, detail=True)
        for transfer in conn.block_storage.transfers(details=True, all_projects=False)
    ]


def delete_volume_transfer(conn: openstack.connection.Connection, transfer_id: str) -> None:
    conn.block_storage.delete_transfer(transfer_id, ignore_missing=False)


def _vol_to_info(vol) -> VolumeInfo:
    # Use original API field names (bootable, volume_image_metadata) since the SDK
    # Python alias for bootable is `is_bootable`, not `bootable`.
    raw = vol.to_dict(original_names=True, computed=False) if hasattr(vol, "to_dict") else {}
    raw_bootable = raw.get("bootable", getattr(vol, "is_bootable", getattr(vol, "bootable", False)))
    bootable = raw_bootable if isinstance(raw_bootable, bool) else str(raw_bootable).lower() == "true"
    raw_vim = raw.get("volume_image_metadata", getattr(vol, "volume_image_metadata", None))
    volume_image_metadata = raw_vim if isinstance(raw_vim, dict) else None
    return VolumeInfo(
        id=vol.id,
        name=vol.name or "",
        status=vol.status,
        size=vol.size,
        volume_type=vol.volume_type,
        attachments=list(vol.attachments or []),
        bootable=bootable,
        volume_image_metadata=volume_image_metadata,
    )


def _safe_float(v) -> float:
    try:
        return round(float(v), 2)
    except Exception:
        return 0.0


def list_storage_pools(conn) -> list[dict]:
    """Cinder backend pool 목록 — total/free/allocated capacity_gb 정규화 반환."""
    bs_ep = conn.block_storage.get_endpoint()
    resp = conn.session.get(f"{bs_ep}/scheduler-stats/get_pools", params={"detail": "True"})
    out = []
    for pool in resp.json().get("pools", []):
        caps = pool.get("capabilities", {})
        total_gb = caps.get("total_capacity_gb", 0)
        free_gb = caps.get("free_capacity_gb", 0)
        allocated_gb = caps.get("allocated_capacity_gb", 0)
        if isinstance(total_gb, str) and total_gb in ("infinite", "unknown"):
            total_gb = 0
        if isinstance(free_gb, str) and free_gb in ("infinite", "unknown"):
            free_gb = 0
        out.append(
            {
                "name": pool.get("name", ""),
                "volume_backend_name": caps.get("volume_backend_name", ""),
                "storage_protocol": caps.get("storage_protocol", ""),
                "total_capacity_gb": _safe_float(total_gb),
                "free_capacity_gb": _safe_float(free_gb),
                "allocated_capacity_gb": _safe_float(allocated_gb),
            }
        )
    return out


def list_volume_types(conn: openstack.connection.Connection) -> list[dict]:
    """볼륨 타입 목록. DB 인스턴스 생성 시 volume.type 선택에 사용."""
    try:
        return [
            {
                "id": vt.id,
                "name": vt.name or "",
                "description": getattr(vt, "description", "") or "",
                "is_public": getattr(vt, "is_public", True),
            }
            for vt in conn.block_storage.types()
            if vt.name
        ]
    except Exception:
        return []
