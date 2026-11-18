"""ERROR 인스턴스 자동 진단 및 복구 서비스.

1. analyze_error_instance() — 안전 증거 수집 및 복구 계획 판정
2. execute_recovery() — fail-closed 재검증 후 화이트리스트 액션 순차 실행

보안:
- execute_recovery는 클라이언트 전달 step을 신뢰하지 않고 서버측 재분석(fail-closed).
- 액션은 reset_volume_state / reset_server_state / hard_reboot 3종 화이트리스트만.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from time import monotonic, sleep
from typing import TYPE_CHECKING
from urllib.parse import quote

from openstack.compute.v2.server import Server

if TYPE_CHECKING:
    from collections.abc import Callable

    import openstack

from app.services import cinder, nova

logger = logging.getLogger(__name__)

# 볼륨 고착 상태 목록
_STUCK_VOLUME_STATUSES = {"attaching", "detaching", "reserved", "error"}

_LIVE_MIGRATION = "live-migration"
_ROLLBACK_EVENT = "compute_rollback_live_migration_at_destination"
_ACTION_MATCH_SECONDS = 60
_RUNNING = 1
# Nova explicitly reports a stopped/crashed guest; NOSTATE does not establish that it is stopped.
_STOPPED_POWER_STATES = {4, 6}  # SHUTDOWN, CRASHED
_OBSERVATION_SECONDS = 55
_POLL_INTERVAL_SECONDS = 2


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _timestamp(value: str | None) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("Missing or invalid Nova timestamp")
    parsed = datetime.fromisoformat(value)
    return parsed.astimezone(UTC) if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _collect_server(conn: openstack.connection.Connection, server_id: str) -> dict | None:
    """서버 정보를 수집한다. 실패 시 None."""
    try:
        srv = conn.compute.get_server(server_id)
        if srv.id != server_id:
            raise ValueError("Server identity mismatch")
        flavor = getattr(srv, "flavor", {}) or {}
        disk = flavor.get("disk") if isinstance(flavor, dict) else getattr(flavor, "disk", None)
        image = getattr(srv, "image", {}) or {}
        fault_raw = getattr(srv, "fault", None)
        fault: dict | None = None
        if isinstance(fault_raw, dict):
            fault = {
                "message": fault_raw.get("message"),
                "code": fault_raw.get("code"),
                "created": fault_raw.get("created"),
            }
        elif fault_raw is not None:
            fault = {"message": str(fault_raw), "code": None, "created": None}
        power_state = getattr(srv, "power_state", None)

        return {
            "id": srv.id,
            "name": getattr(srv, "name", ""),
            "status": (getattr(srv, "status", "") or "").upper(),
            "power_state": power_state if type(power_state) is int else None,
            "task_state": getattr(srv, "task_state", None),
            # SDK descriptors default missing fields to None, but only an
            # explicitly null Nova task_state establishes that the server is idle.
            "task_state_known": "OS-EXT-STS:task_state" in srv._body
            if isinstance(srv, Server)
            else hasattr(srv, "task_state"),
            "compute_host": getattr(srv, "compute_host", None),
            "flavor_disk": int(disk) if disk is not None else -1,
            "image_id": image.get("id") if isinstance(image, dict) else getattr(image, "id", None),
            "fault": fault,
        }
    except Exception as exc:
        logger.warning("서버 정보 수집 실패: %s", exc)
        return None


def _collect_migrations(conn: openstack.connection.Connection, server_id: str) -> list[dict] | None:
    """Return newest-first migration history, distinguishing absence from failure."""
    try:
        result = []
        for migration in conn.compute.migrations(server_id=server_id):
            if getattr(migration, "server_id", server_id) != server_id:
                raise ValueError("Migration belongs to a different server")
            status = migration.status.lower()
            migration_type = migration.migration_type.lower()
            if not status or not migration_type:
                raise ValueError("Migration status or type unavailable")
            created = _timestamp(migration.created_at)
            updated = _timestamp(migration.updated_at) if migration.updated_at is not None else None
            if updated is not None and updated < created:
                raise ValueError("Migration timestamps are inverted")
            result.append(
                {
                    "id": migration.id,
                    "status": status,
                    "migration_type": migration_type,
                    "source_compute": migration.source_compute,
                    "dest_compute": migration.dest_compute,
                    "created_at": created.isoformat(),
                    "updated_at": updated.isoformat() if updated is not None else None,
                }
            )
        result.sort(key=lambda migration: _timestamp(migration["created_at"]), reverse=True)
        return result
    except Exception:
        logger.warning("마이그레이션 이력 수집 실패")
        return None


def _collect_active_migrations(conn: openstack.connection.Connection, server_id: str) -> list | None:
    """Return active live migrations (Nova 2.23+), or unknown on read failure."""
    try:
        return list(conn.compute.server_migrations(server_id))
    except Exception:
        logger.warning("진행 중 마이그레이션 수집 실패")
        return None


def _collect_volumes(conn: openstack.connection.Connection, server_id: str) -> list[dict] | None:
    """Return Nova's attached volumes with Cinder attachment metadata."""
    try:
        attachments = nova.list_volume_attachments(conn, server_id)
        result = []
        seen: set[str] = set()
        for att in attachments:
            vol_id = att["volume_id"]
            if not isinstance(vol_id, str) or not vol_id or vol_id in seen:
                raise ValueError("Missing or duplicate Nova volume ID")
            seen.add(vol_id)
            vol = conn.block_storage.get_volume(vol_id)
            if vol.id != vol_id or not isinstance(vol.status, str) or not vol.status:
                raise ValueError("Cinder volume identity or status unknown")
            if not isinstance(vol.attachments, list) or not all(isinstance(item, dict) for item in vol.attachments):
                raise ValueError("Cinder attachment list unavailable")
            result.append(
                {
                    "volume_id": vol_id,
                    "device": att.get("device"),
                    "status": vol.status.lower(),
                    "bootable": bool(vol.is_bootable),
                    "attachments": vol.attachments,
                    "delete_on_termination": att.get("delete_on_termination", False),
                }
            )
        return result
    except Exception:
        logger.warning("볼륨 및 연결 정보 수집 실패")
        return None


def _collect_ports(conn: openstack.connection.Connection, server_id: str) -> list[dict] | None:
    """Return attached Neutron ports, including their admin-only binding fields."""
    try:
        result = []
        seen: set[str] = set()
        for port in conn.network.ports(device_id=server_id):
            if not isinstance(port.id, str) or not port.id or port.id in seen:
                raise ValueError("Missing or duplicate Neutron port ID")
            seen.add(port.id)
            result.append(
                {
                    "id": port.id,
                    "status": (port.status or "").upper(),
                    "binding_vif_type": port.binding_vif_type,
                    "binding_host_id": port.binding_host_id,
                    "binding_profile": port.binding_profile,
                }
            )
        return result
    except Exception:
        logger.warning("포트 수집 실패")
        return None


# ---------------------------------------------------------------------------
# 안전 검사
# ---------------------------------------------------------------------------


def _check(key: str, label: str, passed: bool, detail: str) -> dict:
    return {"key": key, "label": label, "passed": passed, "detail": detail}


def _check_is_error_state(srv: dict | None) -> dict:
    if srv is None:
        return {
            "key": "is_error_state",
            "label": "인스턴스 ERROR 상태",
            "passed": False,
            "detail": "서버 정보를 가져올 수 없습니다",
        }
    passed = srv["status"] == "ERROR"
    return {
        "key": "is_error_state",
        "label": "인스턴스 ERROR 상태",
        "passed": passed,
        "detail": f"현재 상태: {srv['status']}" if not passed else "ERROR 상태 확인됨",
    }


def _check_volume_backed(srv: dict | None, volumes: list[dict] | None) -> dict:
    """볼륨 부팅 여부 확인 — flavor disk=0이면 데이터가 Ceph RBD에 보존됨."""
    if srv is None:
        return {
            "key": "volume_backed",
            "label": "볼륨 부팅 (데이터 보존)",
            "passed": False,
            "detail": "서버 정보를 가져올 수 없습니다",
        }

    flavor_disk = srv.get("flavor_disk", -1)
    has_boot_volume = any(v.get("bootable") for v in volumes or ())
    # flavor disk=0이거나, image 없고 부팅 볼륨이 있으면 볼륨 부팅
    is_volume_backed = (flavor_disk == 0) or (not srv.get("image_id") and has_boot_volume)

    return {
        "key": "volume_backed",
        "label": "볼륨 부팅 (데이터 보존)",
        "passed": is_volume_backed,
        "detail": "볼륨 부팅 확인 — 데이터는 Ceph RBD에 보존됨"
        if is_volume_backed
        else f"로컬 디스크 사용 가능성 있음 (flavor disk={flavor_disk}GB). 수동 확인 권장",
    }


def _check_ports_healthy(ports: list[dict] | None) -> dict:
    """모든 포트 ACTIVE이고 binding_failed/unbound 없어야 함."""
    if ports is None:
        return _check("ports_healthy", "포트 바인딩 정상", False, "Neutron 포트 목록을 확인할 수 없습니다")
    if not ports:
        return _check("ports_healthy", "포트 바인딩 정상", True, "Neutron에 연결된 포트 없음")
    bad_vif = {"binding_failed", "unbound"}
    failed_ports = [
        p
        for p in ports
        if p.get("status") != "ACTIVE"
        or not isinstance(p.get("binding_vif_type"), str)
        or not p["binding_vif_type"]
        or p["binding_vif_type"].lower() in bad_vif
    ]
    passed = len(failed_ports) == 0
    return {
        "key": "ports_healthy",
        "label": "포트 바인딩 정상",
        "passed": passed,
        "detail": "모든 포트 ACTIVE + 바인딩 정상"
        if passed
        else f"비정상 포트 {len(failed_ports)}개: "
        + ", ".join(
            f"{p['id'][:8]} (vif={p.get('binding_vif_type')}, status={p.get('status')})" for p in failed_ports[:3]
        ),
    }


def _check_migration_history(migrations: list[dict] | None) -> dict:
    label = "마이그레이션 이력 확인"
    if migrations is None:
        return _check("migrations_known", label, False, "Nova 마이그레이션 이력을 확인할 수 없습니다")
    if (
        len(migrations) > 1
        and migrations[0]["created_at"] == migrations[1]["created_at"]
        and any(m["migration_type"] == _LIVE_MIGRATION for m in migrations[:2])
    ):
        return _check("migrations_known", label, False, "최신 라이브 마이그레이션을 하나로 특정할 수 없습니다")
    failures = (m["created_at"] for m in migrations if m["status"] == "error")
    latest_failure = next(failures, None)
    if latest_failure is not None and latest_failure == next(failures, None):
        return _check("migrations_known", label, False, "최신 실패 마이그레이션을 하나로 특정할 수 없습니다")
    return _check("migrations_known", label, True, f"Nova 마이그레이션 이력 {len(migrations)}건 확인")


def _check_rollback_event(conn: openstack.connection.Connection, server_id: str, migration: dict) -> dict:
    key, label = "live_migration_rollback", "대상 호스트 롤백 완료"
    try:
        migration_started = _timestamp(migration["created_at"])
        live_actions = [
            (_timestamp(action.start_time), action.request_id)
            for action in conn.compute.server_actions(server_id)
            if action.action == _LIVE_MIGRATION
        ]
        # Nova records the action and the migration separately. Require one
        # nearby request and reject older rollback proof if a new action exists.
        matches = [
            item for item in live_actions if abs((item[0] - migration_started).total_seconds()) <= _ACTION_MATCH_SECONDS
        ]
        if len(matches) != 1 or matches[0][0] != max(start for start, _ in live_actions):
            return _check(
                key, label, False, "실패 시각과 일치하는 최신 Nova 라이브 마이그레이션 요청을 특정할 수 없습니다"
            )
        _, request_id = matches[0]
        if not isinstance(request_id, str) or not request_id.startswith("req-"):
            raise ValueError("Nova request ID unavailable")
        action = conn.compute.get_server_action(request_id, server_id)
        if action.request_id != request_id or action.action != _LIVE_MIGRATION or not isinstance(action.events, list):
            raise ValueError("Nova action identity or events unavailable")
        rollback = [event for event in action.events if event.event == _ROLLBACK_EVENT]
        if (
            len(rollback) != 1
            or rollback[0].result != "Success"
            or getattr(rollback[0], "host", None) not in (None, "", migration["dest_compute"])
        ):
            return _check(key, label, False, "대상 호스트를 정리한 롤백 성공 이벤트가 확인되지 않습니다")
        return _check(key, label, True, f"{_ROLLBACK_EVENT}: Success ({request_id})")
    except Exception:
        logger.warning("Nova 라이브 마이그레이션 요청의 롤백 이벤트 수집 실패")
        return _check(key, label, False, "Nova 작업 또는 이벤트를 읽을 수 없습니다")


def _check_live_port_bindings(
    conn: openstack.connection.Connection, ports: list[dict] | None, host: str | None
) -> dict:
    key, label = "live_migration_ports", "포트가 소스 호스트에만 연결"
    if ports is None or not host:
        return _check(key, label, False, "Neutron 포트 또는 소스 호스트를 확인할 수 없습니다")
    for port in ports:
        port_id = port["id"]
        profile = port.get("binding_profile")
        if port.get("binding_host_id") != host or not isinstance(profile, dict) or "migrating_to" in profile:
            return _check(key, label, False, f"포트 {port_id}: 소스 호스트 바인딩 또는 마이그레이션 프로필 불일치")
        try:
            # The SDK does not expose Neutron's extended port bindings resource.
            bindings = conn.network.get(f"/ports/{quote(port_id, safe='')}/bindings", raise_exc=True).json()["bindings"]
            if not isinstance(bindings, list) or any(not isinstance(binding, dict) for binding in bindings):
                raise ValueError("Invalid Neutron binding list")
        except Exception:
            logger.warning("Neutron 다중 포트 바인딩 수집 실패")
            return _check(key, label, False, f"포트 {port_id}: 다중 바인딩 목록을 읽을 수 없습니다")
        if (
            len(bindings) != 1
            or bindings[0].get("host") != host
            or bindings[0].get("status") != "ACTIVE"
            or not isinstance(bindings[0].get("profile"), dict)
            or "migrating_to" in bindings[0]["profile"]
        ):
            return _check(
                key, label, False, f"포트 {port_id}: 소스 외 바인딩이 있거나 활성 소스 바인딩을 확인할 수 없습니다"
            )
    return _check(key, label, True, f"포트 {len(ports)}개 확인 — 대상 호스트 바인딩 또는 이동 프로필 없음")


def _check_live_volume_attachments(volumes: list[dict] | None, server_id: str, host: str | None) -> dict:
    key, label = "live_migration_volumes", "볼륨이 소스 호스트에만 연결"
    if not volumes or not host:
        return _check(key, label, False, "연결된 볼륨 또는 소스 호스트를 확인할 수 없습니다")
    for volume in volumes:
        attachments = volume["attachments"]
        if (
            volume["status"] != "in-use"
            or not any(attachment.get("server_id") == server_id for attachment in attachments)
            or any(attachment.get("host_name") != host for attachment in attachments)
        ):
            return _check(
                key, label, False, f"볼륨 {volume['volume_id']}: 소스 호스트의 볼륨 연결을 확인할 수 없습니다"
            )
    return _check(key, label, True, f"볼륨 {len(volumes)}개 확인 — 모든 연결 호스트가 {host}")


def _check_live_placement(conn: openstack.connection.Connection, server_id: str, source: str | None) -> dict:
    key, label = "live_migration_placement", "Placement 소스 리소스 공급자 단일 할당"
    if not isinstance(source, str) or not source:
        return _check(key, label, False, "소스 호스트를 확인할 수 없습니다")
    try:
        allocations = conn.placement.get(f"/allocations/{quote(server_id, safe='')}", raise_exc=True).json()[
            "allocations"
        ]
        if not isinstance(allocations, dict):
            raise ValueError("Invalid Placement allocations")
    except Exception:
        logger.warning("Placement 할당 수집 실패")
        return _check(key, label, False, "Placement 할당을 읽을 수 없어 중복 할당을 배제할 수 없습니다")
    if len(allocations) != 1:
        return _check(key, label, False, f"인스턴스 할당에 리소스 공급자 {len(allocations)}개 (단일 공급자 필요)")
    provider = next(iter(allocations))
    resources = allocations[provider].get("resources") if isinstance(allocations[provider], dict) else None
    if not provider or not isinstance(resources, dict) or not resources:
        return _check(key, label, False, "Placement 공급자의 리소스 할당을 확인할 수 없습니다")
    try:
        source_providers = conn.placement.get(
            "/resource_providers", params={"name": source}, microversion="1.14", raise_exc=True
        ).json()["resource_providers"]
        if not isinstance(source_providers, list) or len(source_providers) != 1:
            raise ValueError("Placement source provider not unique")
        root = source_providers[0]
        source_uuid = root["uuid"]
        if (
            root["name"] != source
            or not isinstance(source_uuid, str)
            or not source_uuid
            or root["root_provider_uuid"] != source_uuid
            or root["parent_provider_uuid"] is not None
        ):
            raise ValueError("Placement source provider is not the exact named root")
    except Exception:
        logger.warning("Placement 소스 리소스 공급자 확인 실패")
        return _check(key, label, False, f"소스 호스트 {source}의 단일 Placement 공급자를 확인할 수 없습니다")
    if provider != source_uuid:
        return _check(key, label, False, f"Placement 할당 {provider}가 소스 공급자 {source_uuid}와 일치하지 않습니다")
    return _check(key, label, True, f"소스 {source}의 단일 리소스 공급자 확인: {provider}")


def _check_no_task_in_progress(srv: dict | None, active_migs: list | None) -> dict:
    """task_state=None이고 진행 중 마이그레이션 없어야 함."""
    if srv is None:
        return {
            "key": "no_task_in_progress",
            "label": "진행 중 작업 없음",
            "passed": False,
            "detail": "서버 정보를 가져올 수 없습니다",
        }
    if active_migs is None:
        return _check(
            "no_task_in_progress", "진행 중 작업 없음", False, "Nova 진행 중 마이그레이션을 확인할 수 없습니다"
        )
    if not srv.get("task_state_known"):
        return _check("no_task_in_progress", "진행 중 작업 없음", False, "Nova task_state를 확인할 수 없습니다")

    task_state = srv.get("task_state")
    has_active = len(active_migs) > 0
    passed = task_state is None and not has_active
    detail_parts = []
    if task_state:
        detail_parts.append(f"task_state={task_state}")
    if has_active:
        detail_parts.append(f"진행 중 마이그레이션 {len(active_migs)}개")
    return {
        "key": "no_task_in_progress",
        "label": "진행 중 작업 없음",
        "passed": passed,
        "detail": "진행 중 작업 없음" if passed else "진행 중 작업 있음: " + ", ".join(detail_parts),
    }


# ---------------------------------------------------------------------------
# 시나리오 판정
# ---------------------------------------------------------------------------


def _live_recovery_steps(power_state: int) -> tuple[str, str, list[dict]]:
    steps = [
        {
            "action": "reset_server_state",
            "params": {"state": "active"},
            "description": "Nova 인스턴스 상태를 active로 재설정",
        }
    ]
    if power_state == _RUNNING:
        detail = "롤백이 완료됐으며 소스 호스트에서 게스트가 실행 중입니다. 재시작하지 않고 Nova 상태만 재설정합니다."
    else:
        detail = "롤백이 완료됐으며 소스 호스트에서 게스트가 꺼져 있습니다. Nova 상태를 재설정한 뒤 하드 리부트합니다."
        steps.append({"action": "hard_reboot", "params": {}, "description": "소스 호스트에서 게스트 하드 리부트"})
    return "live_migration_rolled_back", detail, steps


def _determine_scenario(
    srv: dict | None,
    volumes: list[dict],
    migrations: list[dict],
) -> tuple[str, str, list[dict]]:
    """복구 시나리오와 단계 목록을 반환한다.

    Returns:
        (scenario_key, scenario_description, steps)
    """
    if srv is None or srv["status"] != "ERROR":
        return (
            "manual_review",
            "ERROR 상태가 아니거나 서버 정보를 가져올 수 없어 자동 복구를 수행할 수 없습니다.",
            [{"action": "manual", "params": {}, "description": "Nova, Cinder, Neutron 로그를 직접 확인하세요."}],
        )

    error_migs = [m for m in migrations if m["status"] == "error"]
    stuck_vols = [v for v in volumes if v["status"] in _STUCK_VOLUME_STATUSES]
    normal_vols = [v for v in volumes if v["status"] not in _STUCK_VOLUME_STATUSES and v["status"] != "unknown"]

    if error_migs and stuck_vols:
        latest_mig = error_migs[0]
        steps = []
        for v in stuck_vols:
            steps.append(
                {
                    "action": "reset_volume_state",
                    "params": {"volume_id": v["volume_id"], "status": "in-use", "attach_status": "attached"},
                    "description": f"볼륨 {v['volume_id'][:8]} 상태를 in-use/attached로 강제 복구",
                }
            )
        steps.append(
            {
                "action": "reset_server_state",
                "params": {"state": "active"},
                "description": "인스턴스 상태를 active로 강제 복구",
            }
        )
        steps.append(
            {
                "action": "hard_reboot",
                "params": {},
                "description": "하드 리부트 — nova-compute가 RBD connection info로 도메인 재생성",
            }
        )
        return (
            "migration_failed_volume_stuck",
            f"마이그레이션 실패({latest_mig.get('migration_type')}, "
            f"{latest_mig.get('source_compute')} → {latest_mig.get('dest_compute')}) 후 "
            f"볼륨 {len(stuck_vols)}개가 {stuck_vols[0]['status']} 상태로 고착됨. "
            "볼륨 상태 복구 → 서버 상태 복구 → 하드 리부트 순으로 진행합니다.",
            steps,
        )

    if stuck_vols:
        steps = []
        for v in stuck_vols:
            steps.append(
                {
                    "action": "reset_volume_state",
                    "params": {"volume_id": v["volume_id"], "status": "in-use", "attach_status": "attached"},
                    "description": f"볼륨 {v['volume_id'][:8]} 상태를 in-use/attached로 강제 복구",
                }
            )
        steps.append(
            {
                "action": "reset_server_state",
                "params": {"state": "active"},
                "description": "인스턴스 상태를 active로 강제 복구",
            }
        )
        steps.append(
            {
                "action": "hard_reboot",
                "params": {},
                "description": "하드 리부트 — nova-compute가 도메인을 재생성합니다",
            }
        )
        return (
            "volume_stuck",
            f"볼륨 {len(stuck_vols)}개가 {stuck_vols[0]['status']} 상태로 고착된 채 ERROR 상태입니다. "
            "볼륨 상태 복구 → 서버 상태 복구 → 하드 리부트 순으로 진행합니다.",
            steps,
        )

    if not stuck_vols and len(normal_vols) == len(volumes):
        steps = [
            {
                "action": "reset_server_state",
                "params": {"state": "active"},
                "description": "인스턴스 상태를 active로 강제 복구",
            },
            {
                "action": "hard_reboot",
                "params": {},
                "description": "하드 리부트 — nova-compute가 도메인 상태를 동기화합니다",
            },
        ]
        return (
            "generic_error",
            "볼륨과 포트는 정상이나 인스턴스가 ERROR 상태입니다. 서버 상태 복구 → 하드 리부트로 복구를 시도합니다.",
            steps,
        )

    return (
        "manual_review",
        "자동 복구 조건에 해당하지 않습니다. Nova fault 메시지와 Cinder/Neutron 로그를 확인하세요.",
        [{"action": "manual", "params": {}, "description": "수동 점검이 필요합니다."}],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_error_instance(
    conn: openstack.connection.Connection,
    server_id: str,
) -> dict:
    """ERROR 인스턴스를 진단하고 복구 계획을 반환한다.

    조회 실패는 빈 목록과 구분하며 영향을 받는 검사가 자동 복구를 차단한다.
    ERROR가 아닌 인스턴스도 200으로 응답하고 is_error_state fail을 통해 표현한다.
    """
    srv = _collect_server(conn, server_id)
    migrations = _collect_migrations(conn, server_id)
    active_migs = _collect_active_migrations(conn, server_id)
    volumes = _collect_volumes(conn, server_id)
    ports = _collect_ports(conn, server_id)
    last_error_migration = next((m for m in migrations or () if m["status"] == "error"), None)
    live_failure = last_error_migration is not None and last_error_migration["migration_type"] == _LIVE_MIGRATION
    migration_history = _check_migration_history(migrations)

    checks = [
        _check_is_error_state(srv),
        _check_volume_backed(srv, volumes),
        _check_ports_healthy(ports),
        migration_history,
        _check(
            "volumes_known",
            "볼륨 및 연결 정보 확인",
            volumes is not None,
            f"Nova/Cinder 볼륨 {len(volumes)}개 확인"
            if volumes is not None
            else "볼륨 또는 연결 정보를 읽을 수 없습니다",
        ),
        _check_no_task_in_progress(srv, active_migs),
    ]

    if live_failure:
        host = srv.get("compute_host") if srv else None
        source = last_error_migration["source_compute"]
        destination = last_error_migration["dest_compute"]
        source_confirmed = bool(
            migrations[0] is last_error_migration
            and isinstance(host, str)
            and host
            and host == source
            and isinstance(destination, str)
            and destination
            and destination != source
        )
        power_state = srv.get("power_state") if srv else None
        checks.extend(
            [
                _check(
                    "live_migration_source",
                    "인스턴스가 소스 호스트에 있음",
                    source_confirmed,
                    f"인스턴스 호스트: {host or '미확인'} (마이그레이션: {source or '미확인'} → {destination or '미확인'})"
                    if migrations[0] is last_error_migration
                    else "실패 기록 이후 다른 마이그레이션이 확인됩니다",
                ),
                _check_rollback_event(conn, server_id, last_error_migration),
                _check_live_port_bindings(conn, ports, host),
                _check_live_volume_attachments(volumes, server_id, host),
                _check_live_placement(conn, server_id, source),
                _check(
                    "live_migration_power_state",
                    "Nova 게스트 전원 상태 확인",
                    type(power_state) is int and (power_state == _RUNNING or power_state in _STOPPED_POWER_STATES),
                    f"Nova power_state={power_state}"
                    if power_state is not None
                    else "Nova 전원 상태를 확인할 수 없습니다",
                ),
            ]
        )
        if all(check["passed"] for check in checks):
            scenario, scenario_description, steps = _live_recovery_steps(power_state)
        else:
            scenario = "manual_review"
            scenario_description = "소스 호스트와 대상 롤백 증거를 확인하기 전에는 인스턴스를 재시작하지 마세요."
            steps = [
                {
                    "action": "manual",
                    "params": {},
                    "description": "실패한 검사와 Nova, Cinder, Neutron 및 Placement를 확인하세요.",
                }
            ]
    else:
        scenario, scenario_description, steps = _determine_scenario(srv, volumes or [], migrations or [])
    auto_executable = scenario != "manual_review" and all(c["passed"] for c in checks)
    placement_note: str | None = None
    if (
        migration_history["passed"]
        and not live_failure
        and last_error_migration
        and last_error_migration.get("source_compute")
    ):
        src = last_error_migration["source_compute"]
        placement_note = (
            f"소스 호스트 '{src}'에 잔여 placement 할당이 남았을 수 있습니다. "
            f"`openstack resource provider allocation show {server_id}` 로 확인 후 "
            "중복 항목이 있으면 수동 정리를 권장합니다."
        )

    return {
        "server": {
            "id": server_id,
            "name": srv["name"] if srv else "",
            "status": srv["status"] if srv else "UNKNOWN",
            "compute_host": srv["compute_host"] if srv else None,
            "power_state": srv.get("power_state") if srv else None,
            "fault": srv["fault"] if srv else None,
        },
        "last_error_migration": last_error_migration if migration_history["passed"] else None,
        "volumes": volumes,
        "ports": ports,
        "checks": checks,
        "scenario": scenario,
        "scenario_description": scenario_description,
        "steps": steps,
        "auto_executable": auto_executable,
        "placement_note": placement_note,
    }


def _observe_recovery(
    conn: openstack.connection.Connection,
    server_id: str,
    *,
    executed: bool,
) -> tuple[str, bool]:
    """Observe Nova independently of the action requests; never infer guest readiness."""
    deadline = monotonic() + _OBSERVATION_SECONDS
    path = f"/servers/{quote(server_id, safe='')}"
    observed_status = "UNKNOWN"
    while True:
        try:
            server = conn.compute.get(
                path,
                raise_exc=True,
                timeout=max(0.1, min(5, deadline - monotonic())),
                connect_retries=0,
                status_code_retries=0,
                allow_reauth=False,
                redirect=False,
            ).json()["server"]
            if server["id"] != server_id or not isinstance(server["status"], str) or not server["status"]:
                raise ValueError("Invalid server observation")
            observed_status = server["status"].upper()
            if not executed or observed_status == "ERROR":
                break
            if (
                observed_status == "ACTIVE"
                and type(server.get("OS-EXT-STS:power_state")) is int
                and server["OS-EXT-STS:power_state"] == _RUNNING
                and server.get("OS-EXT-STS:task_state", "") is None
            ):
                return observed_status, True
        except Exception:
            # A transient GET cannot promote an accepted request to a recovery.
            if not executed:
                break
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(_POLL_INTERVAL_SECONDS, remaining))
    return observed_status, False


def execute_recovery(
    conn: openstack.connection.Connection,
    server_id: str,
    *,
    expected_guest_restart: bool | None = None,
    before_write: Callable[[], None] | None = None,
) -> dict:
    """복구를 실행한다.

    실행 직전 분석을 재수행해 auto_executable을 재검증한다(fail-closed).
    클라이언트가 보낸 step 목록을 신뢰하지 않는다.

    Raises:
        ValueError: auto_executable=False인 경우 — 라우터에서 409로 변환.
    """
    analysis = analyze_error_instance(conn, server_id)
    if not analysis["auto_executable"]:
        failed = [c for c in analysis["checks"] if not c["passed"]]
        reasons = "; ".join(c["label"] for c in failed)
        raise ValueError(f"자동 복구 조건 미충족 — {reasons}")

    steps = analysis["steps"]
    if expected_guest_restart is not None and expected_guest_restart != any(
        s["action"] == "hard_reboot" for s in steps
    ):
        raise ValueError("복구 계획의 게스트 재시작 여부가 바뀌었습니다. 다시 진단하고 확인하세요.")

    executed = True
    executed_steps: list[dict] = []

    for step in steps:
        action = step["action"]
        params = step.get("params", {})
        description = step.get("description", action)

        if before_write is not None and not executed_steps:
            before_write()
        try:
            if before_write is not None and executed_steps:
                before_write()
            if action == "reset_volume_state":
                volume_id = params["volume_id"]
                status = params.get("status", "in-use")
                attach_status = params.get("attach_status")
                cinder.reset_volume_status(conn, volume_id, status, attach_status)
                detail = f"볼륨 {volume_id[:8]} → {status} 재설정 요청 수락"

            elif action == "reset_server_state":
                state = params.get("state", "active")
                nova.reset_server_state(conn, server_id, state)
                detail = f"서버 상태 → {state} 재설정 요청 수락"

            elif action == "hard_reboot":
                nova.reboot_server(conn, server_id, "HARD")
                detail = "하드 리부트 요청 수락"
            else:
                raise ValueError(f"허용되지 않은 복구 단계: {action}")

            executed_steps.append({"action": action, "description": description, "status": "success", "detail": detail})

        except Exception as exc:
            logger.warning("복구 단계 '%s' 실패: %s", action, exc)
            executed_steps.append(
                {"action": action, "description": description, "status": "failed", "detail": str(exc)[:200]}
            )
            # 실패 시 즉시 중단, 나머지는 skipped
            remaining = steps[len(executed_steps) :]
            for rem in remaining:
                executed_steps.append(
                    {
                        "action": rem["action"],
                        "description": rem.get("description", rem["action"]),
                        "status": "skipped",
                        "detail": "이전 단계 실패로 건너뜀",
                    }
                )
            executed = False
            break

    observed_status, recovered = _observe_recovery(conn, server_id, executed=executed)
    return {
        "executed": executed,
        "observed_status": observed_status,
        "recovered": recovered,
        "scenario": analysis["scenario"],
        "steps": executed_steps,
    }
