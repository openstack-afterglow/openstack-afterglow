from __future__ import annotations

import re
import struct
import time
from datetime import UTC, datetime
from typing import Any

from openstack.exceptions import ResourceNotFound

from app.config import get_settings
from app.models.storage import (
    VolumeDeleteBackendInspection,
    VolumeDeleteCheck,
    VolumeDeleteDependency,
    VolumeDeleteDiagnostic,
    VolumeDeleteMessage,
    VolumeDeleteRecoveryResult,
    VolumeDeleteRecoveryStep,
)
from app.services import ceph_rbd, cinder

_RECOVERABLE_DELETE_STATUSES = {
    "error",
    "deleting",
    "error_deleting",
    "error_extending",
    "error_restoring",
    "error_managing",
}
_DEPENDENCY_TERMINAL_STATUSES = {"deleted"}
_DEPENDENCY_CHECK_NAMES = {
    "volume_attachments",
    "cinder_attachments",
    "nova_attachments",
    "snapshots",
    "backups",
    "clone_volumes",
    "group_or_migration",
}
_IMAGE_ID_RE = re.compile(r"^[0-9a-f]{6,32}$")


def _as_str(value: Any, limit: int = 200) -> str | None:
    if value is None:
        return None
    return str(value)[:limit]


def _safe_detail(exc: Exception) -> str:
    message = str(exc)
    if message:
        return f"{type(exc).__name__}: {message[:200]}"
    return type(exc).__name__


def _volume_project_id(volume: Any) -> str | None:
    return getattr(volume, "project_id", None) or getattr(volume, "os-vol-tenant-attr:tenant_id", None)


def _volume_status(volume: Any) -> str | None:
    status = (getattr(volume, "status", None) or "").lower()
    return status or None


def _volume_attachments(volume: Any) -> list[dict]:
    attachments: list[dict] = []
    for attachment in list(getattr(volume, "attachments", []) or []):
        if isinstance(attachment, dict):
            attachments.append(dict(attachment))
        else:
            attachments.append({"raw": str(attachment)[:200]})
    return attachments


def _extract_dependency(kind: str, raw: dict) -> VolumeDeleteDependency | None:
    dep_id = _as_str(raw.get("id"))
    if not dep_id:
        return None
    return VolumeDeleteDependency(
        id=dep_id,
        status=_as_str(raw.get("status")),
        name=_as_str(raw.get("name")),
        kind=kind,  # type: ignore[arg-type]
    )


def _http_status(exc: Exception) -> int | None:
    pending: list[BaseException] = [exc]
    seen: set[int] = set()
    depth = 0
    while pending and depth < 3:
        current = pending.pop(0)
        if id(current) in seen:
            continue
        seen.add(id(current))
        for candidate in (
            getattr(current, "status_code", None),
            getattr(current, "http_status", None),
            getattr(getattr(current, "response", None), "status_code", None),
        ):
            if isinstance(candidate, int):
                return candidate
            try:
                if candidate is not None:
                    return int(candidate)
            except (TypeError, ValueError):
                pass
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)
        if isinstance(context, BaseException):
            pending.append(context)
        depth += 1
    return None


def _check_from_exception(exc: Exception) -> tuple[str, str]:
    status = _http_status(exc)
    if status == 401:
        return "unknown", "http_401"
    if status == 403:
        return "unknown", "http_403"
    return "unknown", _safe_detail(exc)


def _add_check(
    checks: list[VolumeDeleteCheck],
    name: str,
    state: str,
    detail: str | None = None,
) -> VolumeDeleteCheck:
    check = VolumeDeleteCheck(name=name, state=state, detail=_as_str(detail))  # type: ignore[arg-type]
    checks.append(check)
    return check


def _message_models(raw_messages: list[dict], volume_id: str) -> list[VolumeDeleteMessage]:
    messages: list[VolumeDeleteMessage] = []
    for message in raw_messages:
        if not isinstance(message, dict):
            continue
        resource_uuid = str(message.get("resource_uuid") or "")
        resource_type = str(message.get("resource_type") or "").upper()
        if resource_uuid and resource_uuid != volume_id:
            continue
        if resource_type and resource_type != "VOLUME":
            continue
        messages.append(
            VolumeDeleteMessage(
                id=_as_str(message.get("id")),
                event_id=_as_str(message.get("event_id")),
                request_id=_as_str(message.get("request_id")),
                message_level=_as_str(message.get("message_level")),
                resource_uuid=_as_str(message.get("resource_uuid")),
                resource_type=_as_str(message.get("resource_type")),
                user_message=_as_str(message.get("user_message"), 500),
                created_at=_as_str(message.get("created_at")),
            )
        )
        if len(messages) >= 10:
            break
    return messages


def _message_evidence(messages: list[VolumeDeleteMessage]) -> list[str]:
    evidence: list[str] = []
    for message in messages[:3]:
        text = message.user_message or message.event_id or message.request_id
        if text:
            evidence.append(f"cinder_message={text[:200]}")
    return evidence


def _parse_name_mapping_payload(payload: bytes | None) -> str | None:
    if payload is None or len(payload) < 4:
        return None
    size = struct.unpack("<I", payload[:4])[0]
    raw_id = payload[4:]
    if size != len(raw_id):
        return None
    try:
        image_id = raw_id.decode("ascii")
    except UnicodeDecodeError:
        return None
    return image_id if _IMAGE_ID_RE.fullmatch(image_id) else None


def _check_evidence(status: str | None, checks: list[VolumeDeleteCheck]) -> list[str]:
    evidence = [f"status={status}"] if status else []
    evidence.extend(f"{check.name}={check.state}" for check in checks if check.state in {"present", "unknown"})
    return evidence


def _diagnostic(
    *,
    volume_id: str,
    root_cause_code: str,
    confidence: str,
    summary: str,
    recommended_action: str,
    recovery_available: bool,
    status: str | None = None,
    project_id: str | None = None,
    name: str | None = None,
    size_gb: int | None = None,
    backend_host: str | None = None,
    updated_at: str | None = None,
    attachments: list[dict] | None = None,
    dependencies: list[VolumeDeleteDependency] | None = None,
    messages: list[VolumeDeleteMessage] | None = None,
    checks: list[VolumeDeleteCheck] | None = None,
    backend: VolumeDeleteBackendInspection | None = None,
    evidence: list[str] | None = None,
) -> VolumeDeleteDiagnostic:
    return VolumeDeleteDiagnostic(
        volume_id=volume_id,
        status=status,
        project_id=project_id,
        name=name,
        size_gb=size_gb,
        backend_host=backend_host,
        updated_at=updated_at,
        attachments=attachments or [],
        dependencies=dependencies or [],
        messages=messages or [],
        checks=checks or [],
        backend=backend or VolumeDeleteBackendInspection(),
        root_cause_code=root_cause_code,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        summary=summary,
        evidence=evidence or [],
        recommended_action=recommended_action,
        recovery_available=recovery_available,
    )


def _already_deleted_diagnostic(
    volume_id: str,
    *,
    checks: list[VolumeDeleteCheck] | None = None,
    backend: VolumeDeleteBackendInspection | None = None,
    evidence: list[str] | None = None,
) -> VolumeDeleteDiagnostic:
    return _diagnostic(
        volume_id=volume_id,
        root_cause_code="already_deleted",
        confidence="high",
        summary="Cinder에서 볼륨을 찾을 수 없어 이미 삭제된 것으로 판단됩니다.",
        recommended_action="목록을 새로고침하세요.",
        recovery_available=False,
        checks=checks,
        backend=backend,
        evidence=evidence or ["volume_not_found"],
    )


def _fresh_deleting(updated_at: str | None) -> bool:
    if not updated_at:
        return False
    try:
        parsed = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return (datetime.now(UTC) - parsed.astimezone(UTC)).total_seconds() <= 900
    except (TypeError, ValueError, OverflowError):
        return False


def _backend_from_info(
    *,
    pool: str,
    image_name: str,
    classification: str,
    image_id: str | None = None,
    info: ceph_rbd.RbdImageInfo | None = None,
) -> VolumeDeleteBackendInspection:
    return VolumeDeleteBackendInspection(
        mode="inspected",
        classification=classification,  # type: ignore[arg-type]
        pool=pool,
        image_name=image_name,
        image_id=image_id or (info.id if info else None),
        size_bytes=info.size if info else None,
        order=info.order if info else None,
        parent_spec=info.parent_spec if info else None,
    )


def _inspect_backend(
    client: ceph_rbd.RbdClient,
    settings: Any,
    volume_id: str,
    host: str | None,
    checks: list[VolumeDeleteCheck],
) -> VolumeDeleteBackendInspection:
    try:
        image_name = ceph_rbd.volume_image_name(volume_id)
    except ValueError:
        return VolumeDeleteBackendInspection(mode="unknown", classification="unknown", image_name=None)

    fsid_state, seen_fsid = client.cluster_fsid()
    if fsid_state == "present" and seen_fsid == settings.ceph_rbd_cluster_fsid:
        _add_check(checks, "backend_fsid", "present", seen_fsid)
    else:
        detail = "fsid_mismatch" if fsid_state == "present" else seen_fsid
        _add_check(checks, "backend_fsid", "unknown", detail)
        return VolumeDeleteBackendInspection(mode="unknown", classification="unknown", image_name=image_name)

    pool = ceph_rbd.pool_for_volume(settings, host)
    if host and pool is None:
        backend_name = host.split("@", 1)[1].split("#", 1)[0] if "@" in host else host
        _add_check(checks, "rbd_directory_entry", "unknown", f"backend_unmapped:{backend_name}")
        return VolumeDeleteBackendInspection(mode="unknown", classification="unknown", image_name=image_name)

    if pool is None:
        unknown_seen = False
        for candidate_pool in dict.fromkeys(settings.ceph_rbd_volume_pools.values()):
            state, detail = client.directory_lookup(candidate_pool, image_name)
            _add_check(checks, "rbd_directory_entry", state, f"pool={candidate_pool}:{detail or ''}")
            if state == "present":
                pool = candidate_pool
                break
            unknown_seen = unknown_seen or state == "unknown"
        if pool is None:
            mode = "unknown" if unknown_seen else "inspected"
            classification = "unknown" if unknown_seen else "absent"
            return VolumeDeleteBackendInspection(
                mode=mode,
                classification=classification,
                image_name=image_name,
            )

    by_name_state, by_name_info = client.image_info_by_name(pool, image_name)
    _add_check(checks, "rbd_image_by_name", by_name_state, by_name_info.id if by_name_info else None)
    directory_state, directory_detail = client.directory_lookup(pool, image_name)
    directory_id = directory_detail if directory_state == "present" else None
    _add_check(checks, "rbd_directory_entry", directory_state, directory_detail)
    mapping_state, mapping_detail = client.stat_object(pool, f"rbd_id.{image_name}")
    _add_check(checks, "rbd_name_mapping", mapping_state, mapping_detail)

    mapping_id: str | None = None
    if mapping_state == "present":
        read_state, payload = client.read_name_mapping(pool, image_name)
        if read_state == "present":
            mapping_id = _parse_name_mapping_payload(payload)
            if mapping_id is None:
                _add_check(checks, "rbd_name_mapping", "unknown", "mapping_payload_invalid")
        elif read_state == "unknown":
            _add_check(checks, "rbd_name_mapping", "unknown", "mapping_read_unknown")

    image_id = directory_id or (by_name_info.id if by_name_info else None) or mapping_id
    by_id_state = "absent"
    by_id_info: ceph_rbd.RbdImageInfo | None = None
    header_state = "absent"
    watcher_state = "absent"
    snapshot_state = "absent"
    object_map_state = "absent"
    parent_state = "absent"
    if image_id:
        by_id_state, by_id_info = client.image_info_by_id(pool, image_id)
        _add_check(checks, "rbd_image_by_id", by_id_state, by_id_info.id if by_id_info else None)
        header_state, header_detail = client.stat_object(pool, f"rbd_header.{image_id}")
        _add_check(checks, "rbd_header", header_state, header_detail)
        object_map_state, object_map_detail = client.object_map_present(pool, image_id)
        _add_check(checks, "rbd_object_map", object_map_state, object_map_detail)
        watcher_state, watcher_detail = client.watchers(pool, image_id)
        _add_check(checks, "rbd_watchers", watcher_state, watcher_detail)
        snapshot_state, snapshot_detail = client.snapshots_by_id(pool, image_id)
        _add_check(checks, "rbd_snapshots", snapshot_state, snapshot_detail)
        info = by_id_info or by_name_info
        if info and info.parent_pool and info.parent_image and info.parent_snapshot:
            parent_state, parent_detail = client.children_of(
                info.parent_pool,
                info.parent_image,
                info.parent_snapshot,
                image_name=image_name,
                image_id=image_id,
            )
            _add_check(checks, "rbd_parent_child_link", parent_state, parent_detail)
    trash_state, trash_detail = client.trash_contains(pool, image_name, image_id)
    _add_check(checks, "rbd_trash", trash_state, trash_detail)

    info = by_id_info or by_name_info
    inspection = _backend_from_info(
        pool=pool,
        image_name=image_name,
        classification="inconsistent",
        image_id=image_id,
        info=info,
    )
    backend_checks = [
        check
        for check in checks
        if check.name
        in {
            "rbd_image_by_name",
            "rbd_directory_entry",
            "rbd_name_mapping",
            "rbd_image_by_id",
            "rbd_header",
            "rbd_object_map",
            "rbd_watchers",
            "rbd_snapshots",
            "rbd_parent_child_link",
            "rbd_trash",
        }
    ]
    if any(check.state == "unknown" for check in backend_checks):
        inspection.classification = "unknown"
        inspection.mode = "unknown"
        return inspection
    if (
        by_name_state == "present"
        and by_name_info is not None
        and directory_state == "present"
        and directory_id == by_name_info.id
        and mapping_state == "present"
        and mapping_id == by_name_info.id
        and by_id_state == "present"
        and by_id_info is not None
        and by_id_info.id == by_name_info.id
        and header_state == "present"
    ):
        inspection.classification = "consistent"
        return inspection
    if (
        by_name_state == "absent"
        and directory_state == "present"
        and image_id is not None
        and by_id_state == "present"
        and by_id_info is not None
        and by_id_info.id == image_id
        and header_state == "present"
        and mapping_state == "absent"
    ):
        inspection.classification = "name_mapping_missing"
        return inspection
    if (
        by_name_state == "absent"
        and directory_state == "absent"
        and mapping_state == "absent"
        and trash_state == "absent"
    ):
        inspection.classification = "absent"
        inspection.image_id = None
        inspection.size_bytes = None
        inspection.order = None
        inspection.parent_spec = None
        return inspection
    if (
        by_name_state == "absent"
        and directory_state == "absent"
        and mapping_state == "present"
        and mapping_id is not None
        and header_state == "absent"
    ):
        inspection.classification = "stale_name_mapping_only"
        return inspection
    return inspection


def _diagnose_missing_volume(conn: Any, volume_id: str) -> VolumeDeleteDiagnostic:
    settings = get_settings()
    try:
        client = ceph_rbd.from_settings(settings)
    except Exception as exc:
        backend = VolumeDeleteBackendInspection(mode="unknown", classification="unknown")
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="backend_lookup_unknown",
            confidence="low",
            summary="Cinder에는 볼륨이 없지만 Ceph 설정을 불러오지 못해 backend 부재 여부를 확인할 수 없습니다.",
            recommended_action="Ceph 설정과 keyring 경로를 확인한 뒤 재진단하세요.",
            recovery_available=False,
            backend=backend,
            evidence=["volume_not_found", f"backend_lookup_unknown:{_safe_detail(exc)}"],
        )
    if client is None:
        return _already_deleted_diagnostic(
            volume_id,
            backend=VolumeDeleteBackendInspection(mode="unavailable", classification="not_inspected"),
            evidence=["volume_not_found", "ceph_rbd=disabled"],
        )
    fsid_state, seen_fsid = client.cluster_fsid()
    if fsid_state != "present" or seen_fsid != settings.ceph_rbd_cluster_fsid:
        detail = "fsid_mismatch" if fsid_state == "present" else seen_fsid
        checks = [
            VolumeDeleteCheck(
                name="backend_fsid",
                state="unknown",
                detail=_as_str(detail),
            )
        ]
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="backend_lookup_unknown",
            confidence="low",
            summary="Cinder에는 볼륨이 없지만 Ceph cluster FSID를 확인하지 못해 backend 부재 여부를 알 수 없습니다.",
            recommended_action="Ceph 설정과 클러스터 FSID를 확인한 뒤 재진단하세요.",
            recovery_available=False,
            checks=checks,
            backend=VolumeDeleteBackendInspection(mode="unknown", classification="unknown"),
            evidence=["volume_not_found", f"backend_lookup_unknown:fsid:{detail}"],
        )
    try:
        image_name = ceph_rbd.volume_image_name(volume_id)
    except ValueError:
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="backend_lookup_unknown",
            confidence="low",
            summary="볼륨 ID가 RBD 이미지 이름 규칙에 맞지 않아 backend 부재 여부를 알 수 없습니다.",
            recommended_action="볼륨 ID 형식(UUID)을 확인하세요.",
            recovery_available=False,
            backend=VolumeDeleteBackendInspection(mode="unknown", classification="unknown"),
            evidence=["volume_not_found", "backend_lookup_unknown:invalid_volume_id"],
        )

    checks: list[VolumeDeleteCheck] = [VolumeDeleteCheck(name="backend_fsid", state="present", detail=seen_fsid)]
    present_seen = False
    unknown_seen = False
    seen_pool: str | None = None
    seen_id: str | None = None
    for pool in dict.fromkeys(settings.ceph_rbd_volume_pools.values()):
        directory_state, directory_detail = client.directory_lookup(pool, image_name)
        _add_check(checks, "rbd_directory_entry", directory_state, f"pool={pool}:{directory_detail or ''}")
        mapping_state, _ = client.stat_object(pool, f"rbd_id.{image_name}")
        _add_check(checks, "rbd_name_mapping", mapping_state, f"pool={pool}")
        image_id = directory_detail if directory_state == "present" else None
        header_state = "absent"
        if image_id:
            header_state, header_detail = client.stat_object(pool, f"rbd_header.{image_id}")
            _add_check(checks, "rbd_header", header_state, header_detail)
        trash_state, trash_detail = client.trash_contains(pool, image_name, image_id)
        _add_check(checks, "rbd_trash", trash_state, f"pool={pool}:{trash_detail or ''}")

        if "present" in {directory_state, mapping_state, header_state, trash_state}:
            present_seen = True
            seen_pool = seen_pool or pool
            seen_id = seen_id or image_id
        if "unknown" in {directory_state, mapping_state, header_state, trash_state}:
            unknown_seen = True

    if present_seen:
        backend = VolumeDeleteBackendInspection(
            mode="inspected",
            classification="inconsistent",
            pool=seen_pool,
            image_name=image_name,
            image_id=seen_id,
        )
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="api_absent_backend_present",
            confidence="high",
            summary="Cinder에는 없지만 Ceph에 이미지·휴지통 또는 매핑이 남아 있음",
            recommended_action="운영자 rados/rbd 점검으로 Ceph 잔여 객체 및 휴지통을 확인하세요. 웹 복구 대상이 아닙니다.",
            recovery_available=False,
            checks=checks,
            backend=backend,
            evidence=["volume_not_found", *_check_evidence(None, checks), "backend=inconsistent"],
        )
    if unknown_seen:
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="backend_lookup_unknown",
            confidence="low",
            summary="Cinder에는 볼륨이 없지만 Ceph pool 또는 휴지통 조회가 완료되지 않아 완전한 부재 여부를 알 수 없습니다.",
            recommended_action="Ceph 설정, pool 권한과 연결을 확인한 뒤 재진단하세요.",
            recovery_available=False,
            checks=checks,
            backend=VolumeDeleteBackendInspection(
                mode="unknown",
                classification="unknown",
                image_name=image_name,
            ),
            evidence=["volume_not_found", *_check_evidence(None, checks), "backend_lookup_unknown"],
        )
    return _already_deleted_diagnostic(
        volume_id,
        checks=checks,
        backend=VolumeDeleteBackendInspection(
            mode="inspected",
            classification="absent",
            image_name=image_name,
        ),
        evidence=["volume_not_found", "ceph_rbd=absent"],
    )


def diagnose_volume_delete_issue(conn: Any, volume_id: str) -> VolumeDeleteDiagnostic:
    checks: list[VolumeDeleteCheck] = []
    try:
        volume = conn.block_storage.get_volume(volume_id)
    except ResourceNotFound:
        return _diagnose_missing_volume(conn, volume_id)
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "auth_preflight", state, detail)
        status = _http_status(exc)
        if status == 401:
            return _diagnostic(
                volume_id=volume_id,
                root_cause_code="authentication_scope_failed",
                confidence="high",
                summary="관리자 Cinder 토큰의 인증 또는 scope 확인에 실패했습니다.",
                recommended_action="관리자 토큰 scope/세션을 확인하고 재로그인 후 재시도하세요.",
                recovery_available=False,
                checks=checks,
                evidence=["volume_lookup_failed:http_401", "auth_preflight=unknown"],
            )
        if status == 403:
            return _diagnostic(
                volume_id=volume_id,
                root_cause_code="authorization_denied",
                confidence="high",
                summary="관리자 토큰이 볼륨을 조회할 권한이 없습니다.",
                recommended_action="system administrator 역할과 Cinder 정책을 확인하세요.",
                recovery_available=False,
                checks=checks,
                evidence=["volume_lookup_failed:http_403", "auth_preflight=unknown"],
            )
        return _diagnostic(
            volume_id=volume_id,
            root_cause_code="dependency_unknown",
            confidence="low",
            summary="볼륨 조회 실패로 삭제 안전성을 판정할 수 없습니다.",
            recommended_action="인증/네트워크를 복구한 뒤 재진단하세요.",
            recovery_available=False,
            checks=checks,
            evidence=[f"volume_lookup_failed:{detail}", "auth_preflight=unknown"],
        )

    _add_check(checks, "auth_preflight", "present")
    status = _volume_status(volume)
    project_id = _volume_project_id(volume)
    display_name = _as_str(getattr(volume, "name", None))
    size_value = getattr(volume, "size", None)
    try:
        size_gb = int(size_value) if size_value is not None else None
    except (TypeError, ValueError):
        size_gb = None
    backend_host = _as_str(getattr(volume, "host", None) or getattr(volume, "os-vol-host-attr:host", None))
    updated_at = _as_str(getattr(volume, "updated_at", None))
    migration_status = _as_str(getattr(volume, "migration_status", None))
    group_id = _as_str(getattr(volume, "group_id", None))
    attachments = _volume_attachments(volume)
    dependencies: list[VolumeDeleteDependency] = []

    if attachments:
        first = attachments[0]
        server_id = first.get("server_id") or first.get("serverId") or first.get("instance") or "unknown"
        device = first.get("device") or "unknown"
        _add_check(checks, "volume_attachments", "present", f"attachment:{server_id}:{device}")
    else:
        _add_check(checks, "volume_attachments", "absent")

    try:
        cinder_attachments = [
            item
            for item in cinder.list_volume_attachments(conn, volume_id)
            if isinstance(item, dict) and str(item.get("status") or "").lower() != "deleted"
        ]
        detail = f"attachment:{cinder_attachments[0].get('id', 'unknown')}" if cinder_attachments else None
        _add_check(checks, "cinder_attachments", "present" if cinder_attachments else "absent", detail)
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "cinder_attachments", state, detail)

    try:
        nova_attachment: tuple[str, str] | None = None
        for server in conn.compute.servers(details=True, all_projects=True):
            server_id = str(getattr(server, "id", None) or "unknown")
            attached = getattr(server, "attached_volumes", None)
            if attached is None and hasattr(server, "to_dict"):
                raw_server = server.to_dict()
                attached = raw_server.get("os-extended-volumes:volumes_attached", [])
            for attachment in list(attached or []):
                attachment_id = (
                    attachment.get("id") if isinstance(attachment, dict) else getattr(attachment, "id", None)
                )
                if attachment_id == volume_id:
                    nova_attachment = server_id, str(attachment_id)
                    break
            if nova_attachment:
                break
        _add_check(
            checks,
            "nova_attachments",
            "present" if nova_attachment else "absent",
            f"server:{nova_attachment[0]}" if nova_attachment else None,
        )
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "nova_attachments", state, detail)

    try:
        snapshots = cinder.list_snapshots(conn, volume_id=volume_id, all_projects=True)
        active_snapshots = [
            item for item in snapshots if str(item.get("status") or "").lower() not in _DEPENDENCY_TERMINAL_STATUSES
        ]
        for snapshot in active_snapshots:
            dep = _extract_dependency("snapshot", snapshot)
            if dep:
                dependencies.append(dep)
        _add_check(
            checks,
            "snapshots",
            "present" if active_snapshots else "absent",
            f"snapshot:{active_snapshots[0].get('id', 'unknown')}" if active_snapshots else None,
        )
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "snapshots", state, detail)

    try:
        backups = cinder.list_backups(conn, volume_id=volume_id, all_projects=True)
        active_backups = [
            item for item in backups if str(item.get("status") or "").lower() not in _DEPENDENCY_TERMINAL_STATUSES
        ]
        for backup in active_backups:
            dep = _extract_dependency("backup", backup)
            if dep:
                dependencies.append(dep)
        _add_check(
            checks,
            "backups",
            "present" if active_backups else "absent",
            f"backup:{active_backups[0].get('id', 'unknown')}" if active_backups else None,
        )
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "backups", state, detail)

    try:
        clone_id: str | None = None
        for candidate in conn.block_storage.volumes(details=True, all_projects=True):
            source_volume_id = getattr(candidate, "source_volume_id", None)
            if source_volume_id is None and hasattr(candidate, "to_dict"):
                source_volume_id = candidate.to_dict().get("source_volume_id")
            if source_volume_id == volume_id:
                clone_id = str(getattr(candidate, "id", None) or "unknown")
                break
        _add_check(
            checks,
            "clone_volumes",
            "present" if clone_id else "absent",
            f"clone:{clone_id}" if clone_id else None,
        )
    except Exception as exc:
        state, detail = _check_from_exception(exc)
        _add_check(checks, "clone_volumes", state, detail)

    migration_active = bool(migration_status and migration_status.lower() not in {"success", "error"})
    if group_id or migration_active:
        detail = f"group:{group_id}" if group_id else f"migration:{migration_status}"
        _add_check(checks, "group_or_migration", "present", detail)
    else:
        _add_check(checks, "group_or_migration", "absent")

    message_evidence: list[str] = []
    try:
        messages = _message_models(cinder.list_volume_messages(conn, volume_id), volume_id)
        message_evidence.extend(_message_evidence(messages))
    except Exception as exc:
        detail = f"http_{_http_status(exc)}" if _http_status(exc) is not None else _safe_detail(exc)
        message_evidence.append(f"cinder_messages_unavailable:{detail}")
        messages = []

    common = {
        "volume_id": volume_id,
        "status": status,
        "project_id": project_id,
        "name": display_name,
        "size_gb": size_gb,
        "backend_host": backend_host,
        "updated_at": updated_at,
        "attachments": attachments,
        "dependencies": dependencies,
        "messages": messages,
        "checks": checks,
    }

    attachment_present = any(
        check.name in {"volume_attachments", "cinder_attachments", "nova_attachments"} and check.state == "present"
        for check in checks
    )
    if attachment_present:
        return _diagnostic(
            **common,
            root_cause_code="attached_volume_delete_blocked",
            confidence="high",
            summary="볼륨 연결 정보가 남아 있어 자동 삭제 복구를 중단했습니다.",
            recommended_action="인스턴스 연결을 해제하고 Cinder/Nova 양쪽에서 detach 완료를 확인한 뒤 재진단하세요.",
            recovery_available=False,
            evidence=[*_check_evidence(status, checks), *message_evidence],
        )

    dependency_present = any(
        check.name in {"snapshots", "backups", "clone_volumes", "group_or_migration"} and check.state == "present"
        for check in checks
    )
    if dependency_present:
        return _diagnostic(
            **common,
            root_cause_code="dependent_resource_present",
            confidence="high",
            summary="볼륨에 종속 리소스 또는 진행 중 작업이 남아 있어 자동 삭제 복구를 중단했습니다.",
            recommended_action="종속 리소스를 보존할지 삭제할지 명시적으로 결정한 뒤 별도 작업으로 정리하고 재진단하세요.",
            recovery_available=False,
            evidence=[*_check_evidence(status, checks), *message_evidence],
        )

    dependency_unknown = any(check.name in _DEPENDENCY_CHECK_NAMES and check.state == "unknown" for check in checks)
    if dependency_unknown:
        return _diagnostic(
            **common,
            root_cause_code="dependency_unknown",
            confidence="low",
            summary="하나 이상의 종속성 조회가 실패해 안전한 삭제를 확인할 수 없습니다.",
            recommended_action="조회 실패는 종속성 없음이 아닙니다. 인증/네트워크 복구 후 재진단하세요.",
            recovery_available=False,
            evidence=[*_check_evidence(status, checks), *message_evidence],
        )

    if status == "deleting" and _fresh_deleting(updated_at):
        return _diagnostic(
            **common,
            root_cause_code="deleting_in_progress",
            confidence="high",
            summary="최근 시작된 비동기 Cinder 삭제가 아직 진행 중일 수 있습니다.",
            recommended_action="비동기 삭제 진행 중일 수 있음. 15분 후 재진단하세요.",
            recovery_available=False,
            evidence=[*_check_evidence(status, checks), *message_evidence],
        )

    settings = get_settings()
    try:
        client = ceph_rbd.from_settings(settings)
        backend = (
            _inspect_backend(client, settings, volume_id, backend_host, checks)
            if client is not None
            else VolumeDeleteBackendInspection(mode="unavailable", classification="not_inspected")
        )
    except Exception as exc:
        _add_check(checks, "backend_fsid", "unknown", _safe_detail(exc))
        backend = VolumeDeleteBackendInspection(mode="unknown", classification="unknown")

    evidence = [*_check_evidence(status, checks), f"backend={backend.classification}", *message_evidence]
    common["backend"] = backend

    if status not in _RECOVERABLE_DELETE_STATUSES:
        if status == "available":
            return _diagnostic(
                **common,
                root_cause_code="normal_delete_possible",
                confidence="medium",
                summary="볼륨이 available 상태라 일반 관리자 삭제 경로를 먼저 사용해야 합니다.",
                recommended_action="기존 관리자 볼륨 삭제 버튼으로 일반 삭제를 실행하세요.",
                recovery_available=False,
                evidence=evidence,
            )
        return _diagnostic(
            **common,
            root_cause_code="not_recoverable_status",
            confidence="low",
            summary="현재 볼륨 상태는 자동 삭제 복구 대상이 아닙니다.",
            recommended_action="Cinder 상태와 작업 로그를 수동으로 확인한 뒤 적절한 복구 절차를 선택하세요.",
            recovery_available=False,
            evidence=evidence,
        )

    if backend.mode == "unavailable":
        return _diagnostic(
            **common,
            root_cause_code="recoverable_backend_unverified",
            confidence="medium",
            summary="Cinder 종속성 없음. Ceph backend 검증은 미설정으로 생략 — force-delete 후 backend 잔여 이미지 여부는 확인되지 않음",
            recommended_action="Ceph backend 미검증 조건을 확인한 뒤 Cinder force-delete를 실행하세요.",
            recovery_available=True,
            evidence=evidence,
        )
    if backend.mode == "unknown" or backend.classification == "unknown":
        return _diagnostic(
            **common,
            root_cause_code="backend_lookup_unknown",
            confidence="low",
            summary="Ceph backend 조회가 완료되지 않아 삭제 안전성을 판정할 수 없습니다.",
            recommended_action="Ceph 설정, FSID, pool 매핑, 권한과 연결을 복구한 뒤 재진단하세요.",
            recovery_available=False,
            evidence=evidence,
        )
    if backend.classification == "consistent":
        return _diagnostic(
            **common,
            root_cause_code="backend_present_consistent",
            confidence="high",
            summary="Cinder 레코드와 Ceph RBD 이미지가 일관되며 force-delete 후 backend 검증이 가능합니다.",
            recommended_action="자동 복구로 Cinder force-delete 후 Ceph backend 부재를 검증하세요.",
            recovery_available=True,
            evidence=evidence,
        )
    if backend.classification == "absent":
        return _diagnostic(
            **common,
            root_cause_code="backend_absent_record_only",
            confidence="high",
            summary="Ceph backend 이미지는 없고 Cinder 레코드만 남아 있습니다.",
            recommended_action="자동 복구로 Cinder 레코드를 정리하고 이름 기반 backend 부재를 재확인하세요.",
            recovery_available=True,
            evidence=evidence,
        )
    if backend.classification == "name_mapping_missing":
        watcher = next((check for check in checks if check.name == "rbd_watchers"), None)
        snapshots = next((check for check in checks if check.name == "rbd_snapshots"), None)
        if watcher and snapshots and watcher.state == "absent" and snapshots.state == "absent":
            return _diagnostic(
                **common,
                root_cause_code="rbd_name_mapping_missing",
                confidence="high",
                summary="Ceph RBD 이름→ID 매핑만 없고 directory/header/parent 관계는 남아 있습니다.",
                recommended_action="이름→ID 매핑 1개를 복원한 뒤 Cinder force-delete를 실행하세요.",
                recovery_available=True,
                evidence=evidence,
            )
    return _diagnostic(
        **common,
        root_cause_code="backend_inconsistent",
        confidence="high",
        summary="Ceph RBD metadata 조합이 웹 자동 복구의 안전 전제와 일치하지 않습니다.",
        recommended_action="운영자 rados 점검이 필요합니다. 웹 복구 대상이 아닙니다.",
        recovery_available=False,
        evidence=evidence,
    )


def _wait_volume_absent(
    conn: Any,
    volume_id: str,
    timeout_seconds: int,
    poll_interval_seconds: float,
) -> tuple[bool, str | None]:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    last_status: str | None = None
    while True:
        try:
            volume = conn.block_storage.get_volume(volume_id)
            last_status = _volume_status(volume)
        except ResourceNotFound:
            return True, None
        except Exception as exc:
            return False, f"lookup_unknown:{_safe_detail(exc)}"
        if time.monotonic() >= deadline:
            return False, last_status
        time.sleep(max(min(poll_interval_seconds, deadline - time.monotonic()), 0))


def _result(
    *,
    volume_id: str,
    status: str,
    verified_deleted: bool,
    diagnostic: VolumeDeleteDiagnostic,
    steps: list[VolumeDeleteRecoveryStep],
    final_status: str | None = None,
    backend_verification: str = "unavailable",
    quota_verification: str = "unavailable",
) -> VolumeDeleteRecoveryResult:
    return VolumeDeleteRecoveryResult(
        volume_id=volume_id,
        status=status,  # type: ignore[arg-type]
        verified_deleted=verified_deleted,
        final_status=final_status,
        backend_verification=backend_verification,  # type: ignore[arg-type]
        quota_verification=quota_verification,  # type: ignore[arg-type]
        diagnostic=diagnostic,
        steps=steps,
    )


def _quota_snapshot(conn: Any, project_id: str | None) -> tuple[int, int] | None:
    if not project_id:
        return None
    quota = cinder.get_volume_quota(conn, project_id)
    return int(quota["volumes"]["in_use"]), int(quota["gigabytes"]["in_use"])


def _backend_absence_without_id(
    client: ceph_rbd.RbdClient,
    settings: Any,
    diagnostic: VolumeDeleteDiagnostic,
) -> tuple[str, str]:
    image_name = diagnostic.backend.image_name
    if not image_name:
        return "unknown", "missing_image_name"
    pools = (
        [diagnostic.backend.pool]
        if diagnostic.backend.pool
        else list(dict.fromkeys(settings.ceph_rbd_volume_pools.values()))
    )
    states: list[str] = []
    for pool in pools:
        if not pool:
            continue
        mapping_state, _ = client.stat_object(pool, f"rbd_id.{image_name}")
        directory_state, _ = client.directory_lookup(pool, image_name)
        trash_state, _ = client.trash_contains(pool, image_name)
        states.extend([mapping_state, directory_state, trash_state])
    if "present" in states:
        return "residue", "name_based_residue"
    if not states or "unknown" in states:
        return "unknown", "name_based_unknown"
    return "verified", "name_based_absent"


def _verify_backend_after_delete(
    client: ceph_rbd.RbdClient,
    settings: Any,
    diagnostic: VolumeDeleteDiagnostic,
    steps: list[VolumeDeleteRecoveryStep],
) -> str:
    backend = diagnostic.backend
    if backend.image_id is None:
        verification, detail = _backend_absence_without_id(client, settings, diagnostic)
        steps.append(
            VolumeDeleteRecoveryStep(
                action="backend_verify",
                status="success" if verification == "verified" else "failed",
                detail=detail,
            )
        )
        return verification
    if not backend.pool or not backend.image_name:
        steps.append(
            VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail="missing_backend_identity")
        )
        return "unknown"

    pool = backend.pool
    image_name = backend.image_name
    image_id = backend.image_id
    checks: list[tuple[str, str, str | None]] = []
    header = client.stat_object(pool, f"rbd_header.{image_id}")
    checks.append(("rbd_header", *header))
    object_map = client.object_map_present(pool, image_id)
    checks.append(("rbd_object_map", *object_map))
    directory_name = client.directory_lookup(pool, image_name)
    checks.append(("rbd_directory_entry", *directory_name))
    directory_id = client.directory_lookup_by_id(pool, image_id)
    checks.append(("rbd_directory_entry", *directory_id))
    trash = client.trash_contains(pool, image_name, image_id)
    checks.append(("rbd_trash", *trash))
    if backend.parent_spec and "/" in backend.parent_spec and "@" in backend.parent_spec:
        parent_pool, parent_rest = backend.parent_spec.split("/", 1)
        parent_image, parent_snapshot = parent_rest.rsplit("@", 1)
        parent = client.children_of(
            parent_pool,
            parent_image,
            parent_snapshot,
            image_name=image_name,
            image_id=image_id,
        )
        checks.append(("rbd_parent_child_link", *parent))
    if backend.size_bytes is None or backend.order is None:
        data = ("unknown", "missing_image_geometry")
    else:
        data = client.sampled_data_objects(pool, image_id, backend.size_bytes, backend.order)
    checks.append(("rbd_data_objects", *data))
    for name, state, detail in checks:
        _add_check(diagnostic.checks, name, state, detail)

    states = [state for _, state, _ in checks]
    if "present" in states:
        detail = next(name for name, state, _ in checks if state == "present")
        steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail=f"residue:{detail}"))
        return "residue"
    if "unknown" in states:
        detail = next(name for name, state, _ in checks if state == "unknown")
        steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail=f"unknown:{detail}"))
        return "unknown"

    mapping_state, mapping_payload = client.read_name_mapping(pool, image_name)
    _add_check(diagnostic.checks, "rbd_name_mapping", mapping_state, "post_delete")
    if mapping_state == "absent":
        steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="success", detail="backend_absent"))
        return "verified"
    if mapping_state == "unknown":
        steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail="mapping_unknown"))
        return "unknown"
    if mapping_payload != client.name_mapping_payload(image_id):
        steps.append(
            VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail="mapping_payload_mismatch")
        )
        return "residue"
    steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="success", detail="stale_mapping_only"))
    try:
        client.cleanup_stale_name_mapping(pool, image_name, image_id)
        steps.append(
            VolumeDeleteRecoveryStep(
                action="cleanup_stale_name_mapping",
                status="success",
                detail="mapping_removed",
            )
        )
        return "verified"
    except ceph_rbd.RbdCommandError as exc:
        steps.append(
            VolumeDeleteRecoveryStep(
                action="cleanup_stale_name_mapping",
                status="failed",
                detail=_safe_detail(exc),
            )
        )
        return "residue"


def recover_delete_volume(
    conn: Any,
    volume_id: str,
    verify_timeout_seconds: int = 30,
    poll_interval_seconds: float = 2.0,
) -> VolumeDeleteRecoveryResult:
    diagnostic = diagnose_volume_delete_issue(conn, volume_id)
    steps: list[VolumeDeleteRecoveryStep] = [
        VolumeDeleteRecoveryStep(action="diagnose", status="success", detail=diagnostic.root_cause_code)
    ]

    if diagnostic.root_cause_code == "already_deleted":
        backend_verification = {
            "inspected": "verified",
            "unavailable": "unavailable",
            "unknown": "unknown",
        }[diagnostic.backend.mode]
        if diagnostic.backend.mode == "inspected":
            return _result(
                volume_id=volume_id,
                status="already_deleted",
                verified_deleted=True,
                diagnostic=diagnostic,
                steps=steps,
                backend_verification=backend_verification,
            )
        return _result(
            volume_id=volume_id,
            status="backend_unverified",
            verified_deleted=False,
            diagnostic=diagnostic,
            steps=steps,
            backend_verification=backend_verification,
        )
    if diagnostic.root_cause_code == "api_absent_backend_present":
        return _result(
            volume_id=volume_id,
            status="backend_residue",
            verified_deleted=False,
            diagnostic=diagnostic,
            steps=steps,
            backend_verification="residue",
        )
    if not diagnostic.recovery_available:
        steps.append(
            VolumeDeleteRecoveryStep(
                action="force_delete",
                status="skipped",
                detail=diagnostic.recommended_action,
            )
        )
        return _result(
            volume_id=volume_id,
            status=("backend_unverified" if diagnostic.root_cause_code == "backend_lookup_unknown" else "blocked"),
            verified_deleted=False,
            final_status=diagnostic.status,
            diagnostic=diagnostic,
            steps=steps,
            backend_verification="unknown" if diagnostic.backend.mode == "unknown" else "unavailable",
        )

    quota_before: tuple[int, int] | None = None
    try:
        quota_before = _quota_snapshot(conn, diagnostic.project_id)
    except Exception:
        quota_before = None

    settings = get_settings()
    client = ceph_rbd.from_settings(settings)
    if diagnostic.root_cause_code == "rbd_name_mapping_missing":
        if (
            client is None
            or not diagnostic.backend.pool
            or not diagnostic.backend.image_name
            or not diagnostic.backend.image_id
        ):
            steps.append(
                VolumeDeleteRecoveryStep(
                    action="restore_name_mapping", status="failed", detail="backend_identity_missing"
                )
            )
            return _result(
                volume_id=volume_id,
                status="failed",
                verified_deleted=False,
                diagnostic=diagnostic,
                steps=steps,
                final_status=diagnostic.status,
                backend_verification="unknown",
            )
        try:
            client.restore_name_mapping(
                diagnostic.backend.pool,
                diagnostic.backend.image_name,
                diagnostic.backend.image_id,
            )
            steps.append(
                VolumeDeleteRecoveryStep(action="restore_name_mapping", status="success", detail="mapping_restored")
            )
        except ceph_rbd.RbdCommandError as exc:
            steps.append(
                VolumeDeleteRecoveryStep(action="restore_name_mapping", status="failed", detail=_safe_detail(exc))
            )
            return _result(
                volume_id=volume_id,
                status="failed",
                verified_deleted=False,
                diagnostic=diagnostic,
                steps=steps,
                final_status=diagnostic.status,
                backend_verification="unknown",
            )
        verify_state, verify_info = client.image_info_by_name(diagnostic.backend.pool, diagnostic.backend.image_name)
        if verify_state != "present" or verify_info is None or verify_info.id != diagnostic.backend.image_id:
            seen = verify_info.id if verify_info else verify_state
            steps.append(
                VolumeDeleteRecoveryStep(
                    action="verify_name_mapping",
                    status="failed",
                    detail=f"mapping_verify_failed:{seen}",
                )
            )
            return _result(
                volume_id=volume_id,
                status="failed",
                verified_deleted=False,
                diagnostic=diagnostic,
                steps=steps,
                final_status=diagnostic.status,
                backend_verification="unknown",
            )
        steps.append(VolumeDeleteRecoveryStep(action="verify_name_mapping", status="success", detail=verify_info.id))

    try:
        rechecked = conn.block_storage.get_volume(volume_id)
        current_status = _volume_status(rechecked)
        current_attachments = _volume_attachments(rechecked)
        if current_status not in _RECOVERABLE_DELETE_STATUSES or current_attachments:
            steps.append(
                VolumeDeleteRecoveryStep(
                    action="recheck_state",
                    status="failed",
                    detail=f"state_changed:{current_status or 'unknown'}",
                )
            )
            return _result(
                volume_id=volume_id,
                status="failed",
                verified_deleted=False,
                diagnostic=diagnostic,
                steps=steps,
                final_status=current_status,
                backend_verification="unknown" if diagnostic.backend.mode == "inspected" else "unavailable",
            )
        recheck_attachments = [
            item
            for item in cinder.list_volume_attachments(conn, volume_id)
            if isinstance(item, dict) and str(item.get("status") or "").lower() != "deleted"
        ]
        if recheck_attachments:
            raise RuntimeError("recheck_attachment_present")
        steps.append(VolumeDeleteRecoveryStep(action="recheck_state", status="success", detail=current_status))
    except Exception as exc:
        steps.append(
            VolumeDeleteRecoveryStep(
                action="recheck_state", status="failed", detail=f"recheck_unknown:{_safe_detail(exc)}"
            )
        )
        return _result(
            volume_id=volume_id,
            status="failed",
            verified_deleted=False,
            diagnostic=diagnostic,
            steps=steps,
            final_status=diagnostic.status,
            backend_verification="unknown" if diagnostic.backend.mode == "inspected" else "unavailable",
        )

    try:
        cinder.force_delete_volume(conn, volume_id)
        steps.append(VolumeDeleteRecoveryStep(action="force_delete", status="success", detail="force_delete_submitted"))
    except Exception as exc:
        status_code = _http_status(exc)
        error_text = str(exc)
        if status_code == 400 and "attached" in error_text.lower():
            try:
                cinder.reset_volume_status(conn, volume_id, "error", "detached")
                steps.append(
                    VolumeDeleteRecoveryStep(action="reset_attach_status", status="success", detail="error/detached")
                )
                cinder.force_delete_volume(conn, volume_id)
                steps.append(
                    VolumeDeleteRecoveryStep(
                        action="force_delete",
                        status="success",
                        detail="force_delete_resubmitted",
                    )
                )
            except Exception as retry_exc:
                retry_status = _http_status(retry_exc)
                detail = f"http_{retry_status}" if retry_status in {401, 403} else _safe_detail(retry_exc)
                steps.append(VolumeDeleteRecoveryStep(action="force_delete", status="failed", detail=detail))
                return _result(
                    volume_id=volume_id,
                    status="failed",
                    verified_deleted=False,
                    diagnostic=diagnostic,
                    steps=steps,
                    final_status=diagnostic.status,
                    backend_verification="unknown" if diagnostic.backend.mode == "inspected" else "unavailable",
                )
        else:
            detail = f"http_{status_code}" if status_code in {401, 403} else _safe_detail(exc)
            steps.append(VolumeDeleteRecoveryStep(action="force_delete", status="failed", detail=detail))
            return _result(
                volume_id=volume_id,
                status="failed",
                verified_deleted=False,
                diagnostic=diagnostic,
                steps=steps,
                final_status=diagnostic.status,
                backend_verification="unknown" if diagnostic.backend.mode == "inspected" else "unavailable",
            )

    verified, last_status = _wait_volume_absent(
        conn,
        volume_id,
        verify_timeout_seconds,
        poll_interval_seconds,
    )
    if verified:
        try:
            if any(
                getattr(volume, "id", None) == volume_id
                for volume in conn.block_storage.volumes(details=False, all_projects=True)
            ):
                verified = False
                last_status = "listed_all_projects"
        except Exception as exc:
            verified = False
            last_status = f"list_all_projects_unknown:{_safe_detail(exc)}"
    steps.append(
        VolumeDeleteRecoveryStep(
            action="verify_after_force_delete",
            status="success" if verified else "failed",
            detail="deleted" if verified else f"still_present:{last_status or 'unknown'}",
        )
    )
    if not verified:
        return _result(
            volume_id=volume_id,
            status="delete_submitted",
            verified_deleted=False,
            diagnostic=diagnostic,
            steps=steps,
            final_status=last_status,
            backend_verification="unknown" if diagnostic.backend.mode == "inspected" else "unavailable",
        )

    if diagnostic.backend.mode == "inspected":
        if client is None:
            steps.append(
                VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail="client_unavailable")
            )
            backend_verification = "unknown"
        else:
            try:
                backend_verification = _verify_backend_after_delete(client, settings, diagnostic, steps)
            except Exception as exc:
                steps.append(
                    VolumeDeleteRecoveryStep(action="backend_verify", status="failed", detail=_safe_detail(exc))
                )
                backend_verification = "unknown"
    elif diagnostic.backend.mode == "unknown":
        backend_verification = "unknown"
    else:
        backend_verification = "unavailable"
        steps.append(VolumeDeleteRecoveryStep(action="backend_verify", status="skipped", detail="backend_unavailable"))

    quota_verification = "unavailable"
    if quota_before is None or diagnostic.size_gb is None:
        steps.append(
            VolumeDeleteRecoveryStep(action="quota_verify", status="skipped", detail="quota_snapshot_unavailable")
        )
    else:
        try:
            quota_after = _quota_snapshot(conn, diagnostic.project_id)
            if quota_after is None:
                raise RuntimeError("quota_after_unavailable")
            expected = (quota_before[0] - 1, quota_before[1] - diagnostic.size_gb)
            if quota_after == expected:
                quota_verification = "verified"
                steps.append(
                    VolumeDeleteRecoveryStep(
                        action="quota_verify",
                        status="success",
                        detail=(
                            f"volumes:{quota_before[0]}→{quota_after[0]},gigabytes:{quota_before[1]}→{quota_after[1]}"
                        ),
                    )
                )
            else:
                quota_verification = "mismatch"
                steps.append(
                    VolumeDeleteRecoveryStep(
                        action="quota_verify",
                        status="failed",
                        detail=(
                            f"volumes:{quota_before[0]}→{quota_after[0]},gigabytes:{quota_before[1]}→{quota_after[1]}"
                        ),
                    )
                )
        except Exception as exc:
            steps.append(VolumeDeleteRecoveryStep(action="quota_verify", status="skipped", detail=_safe_detail(exc)))

    if backend_verification == "verified":
        return _result(
            volume_id=volume_id,
            status="deleted",
            verified_deleted=True,
            diagnostic=diagnostic,
            steps=steps,
            backend_verification=backend_verification,
            quota_verification=quota_verification,
        )
    if backend_verification == "residue":
        return _result(
            volume_id=volume_id,
            status="backend_residue",
            verified_deleted=False,
            diagnostic=diagnostic,
            steps=steps,
            backend_verification=backend_verification,
            quota_verification=quota_verification,
        )
    return _result(
        volume_id=volume_id,
        status="backend_unverified",
        verified_deleted=False,
        diagnostic=diagnostic,
        steps=steps,
        backend_verification=backend_verification,
        quota_verification=quota_verification,
    )
