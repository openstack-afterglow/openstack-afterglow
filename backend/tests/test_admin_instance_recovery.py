"""ERROR 인스턴스 복구 — 진단·안전 게이트·실행 순서·권한 테스트."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from itertools import count
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.compute.v2._proxy import Proxy as ComputeProxy
from openstack.compute.v2.server import Server
from requests import Response
from requests.exceptions import ReadTimeout

from app.api.identity import admin
from app.services import instance_recovery

_SERVER_ID = "00000000-0000-4000-8000-000000000001"
_VOLUME_ID = "00000000-0000-4000-8000-000000000002"
_PORT_ID = "00000000-0000-4000-8000-000000000003"
_SOURCE_PROVIDER = "00000000-0000-4000-8000-000000000004"
_DEST_PROVIDER = "00000000-0000-4000-8000-000000000005"
_REQUEST_ID = "req-00000000-0000-4000-8000-000000000006"
_SOURCE = "compute1"
_SOURCE_NODE = "compute1.example.test"
_DEST = "compute2"
_MIGRATION_CREATED = "2026-01-01T09:19:25Z"
_MIGRATION_UPDATED = "2026-01-01T09:20:05Z"
_ACTION_STARTED = "2026-01-01T09:19:24.000000"
_FAULT_CREATED = "2026-01-07T13:29:41Z"
_INSTANCE_URL = f"/api/v1/admin/instances/{_SERVER_ID}"
_UNMATCHED_FINGERPRINT = "0" * 64
_RECOVERY_STEPS = ["reset_server_state", "hard_reboot"]
_VOLUME_RECOVERY_STEPS = ["reset_volume_state", *_RECOVERY_STEPS]
_LIVE_CHECKS = {
    "live_migration_source",
    "live_migration_rollback",
    "live_migration_ports",
    "live_migration_volumes",
    "live_migration_placement",
    "live_migration_power_state",
}
_BASE_CHECKS = {
    "is_error_state",
    "volume_backed",
    "ports_healthy",
    "migrations_known",
    "volumes_known",
    "no_task_in_progress",
}


def _migration(**overrides):
    return SimpleNamespace(
        **(
            {
                "id": "953",
                "server_id": _SERVER_ID,
                "status": "error",
                "migration_type": "live-migration",
                "source_compute": _SOURCE,
                "source_node": _SOURCE_NODE,
                "dest_compute": _DEST,
                "created_at": _MIGRATION_CREATED,
                "updated_at": _MIGRATION_UPDATED,
            }
            | overrides
        )
    )


def _observed_server(status="ACTIVE", *, power_state=1, task_state=None):
    return {
        "server": {
            "id": _SERVER_ID,
            "status": status,
            "OS-EXT-STS:power_state": power_state,
            "OS-EXT-STS:task_state": task_state,
        }
    }


def _configure_recovery(conn, scenario):
    conn.compute.get_server.return_value = SimpleNamespace(
        id=_SERVER_ID,
        name="test-vm",
        status="ERROR",
        vm_state="error",
        task_state=None,
        power_state=4,
        compute_host=_SOURCE,
        hypervisor_hostname=_SOURCE_NODE,
        flavor={"id": "flavor-1", "disk": 0},
        image={},
        attached_volumes=[{"id": _VOLUME_ID}],
        fault={
            "code": 404,
            "message": "Guest does not have a console available.",
            "created": _FAULT_CREATED,
        },
    )
    conn.compute.migrations.return_value = []
    conn.compute.server_migrations.return_value = []
    attachment_id = "00000000-0000-4000-8000-000000000007"
    conn.compute.volume_attachments.return_value = [
        SimpleNamespace(
            id=None,
            attachment_id=attachment_id,
            volume_id=_VOLUME_ID,
            server_id=_SERVER_ID,
            device="/dev/vda",
            delete_on_termination=True,
        )
    ]
    conn.block_storage.get_volume.return_value = SimpleNamespace(
        id=_VOLUME_ID,
        status="in-use",
        is_bootable=True,
        bootable=True,
        attachments=[
            {
                "attachment_id": attachment_id,
                "volume_id": _VOLUME_ID,
                "host_name": _SOURCE,
                "server_id": _SERVER_ID,
            }
        ],
    )
    conn.network.ports.return_value = [
        SimpleNamespace(
            id=_PORT_ID,
            device_id=_SERVER_ID,
            status="ACTIVE",
            binding_vif_type="ovs",
            binding_host_id=_SOURCE,
            binding_profile={},
        )
    ]
    conn.compute.get.return_value.json.return_value = _observed_server()

    def reset_server_state(_server_id, state):
        conn.compute.get_server.return_value.status = state.upper()

    conn.compute.reset_server_state.side_effect = reset_server_state

    if scenario in ("volume_stuck", "migration_failed_volume_stuck"):
        volume = conn.block_storage.get_volume.return_value
        volume.status = "attaching"
        volume.attachments = []
        if scenario == "migration_failed_volume_stuck":
            conn.compute.migrations.return_value = [_migration(migration_type="migration")]

    if scenario == "live_migration_rolled_back":
        conn.block_storage.get.return_value.json.return_value = {
            "attachments": [
                {
                    "id": attachment_id,
                    "status": "attached",
                    "volume_id": _VOLUME_ID,
                    "instance": _SERVER_ID,
                    "connection_info": {},
                }
            ]
        }
        conn.compute.migrations.return_value = [_migration()]
        conn.compute.server_actions.return_value = [
            SimpleNamespace(action="live-migration", request_id=_REQUEST_ID, start_time=_ACTION_STARTED)
        ]
        conn.compute.get_server_action.return_value = SimpleNamespace(
            action="live-migration",
            request_id=_REQUEST_ID,
            start_time=_ACTION_STARTED,
            events=[
                SimpleNamespace(
                    event="compute_rollback_live_migration_at_destination",
                    result="Success",
                    host=_DEST,
                    start_time="2026-01-01T09:20:02.000000",
                    finish_time="2026-01-01T09:20:07.000000",
                )
            ],
        )
        conn.network.get.return_value.json.return_value = {
            "bindings": [{"host": _SOURCE, "status": "ACTIVE", "profile": {}, "vif_type": "ovs"}]
        }
        conn.placement.get.return_value.json.return_value = {
            "allocations": {_SOURCE_PROVIDER: {"resources": {"VCPU": 4, "MEMORY_MB": 8192}}},
            "consumer_generation": 7,
        }
        providers = MagicMock()
        providers.json.return_value = {
            "resource_providers": [
                {
                    "uuid": _SOURCE_PROVIDER,
                    "name": _SOURCE_NODE,
                    "root_provider_uuid": _SOURCE_PROVIDER,
                    "parent_provider_uuid": None,
                }
            ]
        }
        conn.placement.get.side_effect = lambda path, **kwargs: (
            providers if path == "/resource_providers" else conn.placement.get.return_value
        )
    return conn


@pytest.fixture(autouse=True)
def _recovery_redis(monkeypatch, _fake_redis_global):
    monkeypatch.setattr("app.api.identity.admin._get_redis", AsyncMock(return_value=_fake_redis_global))
    return _fake_redis_global


@pytest.fixture(autouse=True)
def _no_poll_wait(monkeypatch):
    # Observe once by default; tests for multiple observations drive a fake clock.
    monkeypatch.setattr(instance_recovery, "_OBSERVATION_SECONDS", 0)


@pytest.fixture
def live_conn(mock_conn):
    return _configure_recovery(mock_conn, "live_migration_rolled_back")


def _actions(result):
    return [step["action"] for step in result["steps"]]


def _checks(analysis):
    return {check["key"]: check["passed"] for check in analysis["checks"]}


def _preview_fingerprint(conn):
    analysis = instance_recovery.analyze_error_instance(conn, _SERVER_ID)
    assert analysis["auto_executable"] is True
    fingerprint = analysis["plan_fingerprint"]
    assert isinstance(fingerprint, str) and len(fingerprint) == 64
    return fingerprint


def _assert_no_mutations(conn):
    conn.block_storage.reset_volume_status.assert_not_called()
    conn.compute.reset_server_state.assert_not_called()
    conn.compute.reboot_server.assert_not_called()


def _assert_recovery_blocked(conn, check, *, live=True):
    analysis = instance_recovery.analyze_error_instance(conn, _SERVER_ID)
    assert analysis["auto_executable"] is False
    if live:
        assert analysis["scenario"] == "manual_review"
    assert _checks(analysis)[check] is False
    with pytest.raises(ValueError, match="자동 복구 조건 미충족"):
        instance_recovery.execute_recovery(conn, _SERVER_ID, plan_fingerprint=_UNMATCHED_FINGERPRINT)
    _assert_no_mutations(conn)


@pytest.mark.parametrize(
    ("power_state", "actions"),
    [(1, ["reset_server_state"]), (4, ["hard_reboot"]), (6, ["hard_reboot"])],
    ids=["running", "shutdown", "crashed"],
)
def test_verified_live_migration_recovery_plan_and_execution(live_conn, power_state, actions):
    live_conn.compute.get_server.return_value.power_state = power_state

    analysis = instance_recovery.analyze_error_instance(live_conn, _SERVER_ID)

    assert analysis["auto_executable"] is True
    assert analysis["scenario"] == "live_migration_rolled_back"
    assert analysis["server"]["power_state"] == power_state
    assert _actions(analysis) == actions
    checks = _checks(analysis)
    assert (_BASE_CHECKS | _LIVE_CHECKS) <= checks.keys()
    assert all(checks.values())
    live_conn.compute.server_actions.assert_called_once_with(_SERVER_ID)
    live_conn.compute.get_server_action.assert_called_once_with(_REQUEST_ID, _SERVER_ID)
    live_conn.network.get.assert_called_once_with(f"/ports/{_PORT_ID}/bindings", raise_exc=True)
    assert live_conn.placement.get.call_args_list == [
        call(f"/allocations/{_SERVER_ID}", raise_exc=True),
        call("/resource_providers", params={"name": _SOURCE_NODE}, microversion="1.14", raise_exc=True),
    ]

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=analysis["plan_fingerprint"])

    assert result["executed"] is True
    assert result["recovered"] is True
    assert result["observed_status"] == "ACTIVE"
    assert result["scenario"] == "live_migration_rolled_back"
    assert _actions(result) == actions
    live_conn.block_storage.reset_volume_status.assert_not_called()
    if power_state == 1:
        live_conn.compute.reset_server_state.assert_called_once_with(_SERVER_ID, "active")
        live_conn.compute.reboot_server.assert_not_called()
    else:
        live_conn.compute.reset_server_state.assert_not_called()
        live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")


def test_rejected_live_rollback_hard_reboot_does_not_reset_server_state(live_conn):
    live_conn.compute.reboot_server.side_effect = RuntimeError("Nova rejected HARD reboot")
    live_conn.compute.get.return_value.json.return_value = _observed_server("ERROR", power_state=4)

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["executed"] is False
    assert result["recovered"] is False
    assert result["observed_status"] == "ERROR"
    assert _actions(result) == ["hard_reboot"]
    assert result["steps"][0]["status"] == "failed"
    live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")
    live_conn.compute.reset_server_state.assert_not_called()
    live_conn.block_storage.reset_volume_status.assert_not_called()


@pytest.mark.parametrize("power", [1, 4], ids=["running", "stopped"])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", "ACTIVE"),
        ("task_state", "migrating"),
        ("task_state", Ellipsis),
        ("compute_host", _DEST),
        ("hypervisor_hostname", "different-node"),
        ("power_state", 6),
    ],
    ids=["status", "busy", "missing-task", "different-host", "different-node", "different-power"],
)
def test_live_recovery_stops_if_server_changes_after_reanalysis(live_conn, power, field, value):
    server = live_conn.compute.get_server.return_value
    server.power_state = power
    fingerprint = _preview_fingerprint(live_conn)
    refreshed = SimpleNamespace(**vars(server))
    if value is Ellipsis:
        delattr(refreshed, field)
    else:
        setattr(refreshed, field, value)
    live_conn.compute.get_server.side_effect = [server, refreshed]

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=fingerprint)

    assert result["executed"] is False
    assert result["steps"][0]["status"] == "failed"
    _assert_no_mutations(live_conn)


def test_legacy_recovery_rechecks_state_before_hard_reboot(mock_conn):
    conn = _configure_recovery(mock_conn, "volume_stuck")
    server = conn.compute.get_server.return_value
    fingerprint = _preview_fingerprint(conn)

    def reset(_server_id, state):
        server.status = state.upper()
        server.compute_host = _DEST

    conn.compute.reset_server_state.side_effect = reset
    result = instance_recovery.execute_recovery(conn, _SERVER_ID, plan_fingerprint=fingerprint)

    assert [step["status"] for step in result["steps"]] == ["success", "success", "failed"]
    conn.compute.reboot_server.assert_not_called()


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_failed_or_cancelled_live_migration_never_uses_generic_recovery(live_conn, status):
    live_conn.compute.migrations.return_value[0].status = status
    live_conn.compute.get_server_action.return_value.events = []

    _assert_recovery_blocked(live_conn, "live_migration_rollback")


def test_live_volume_list_rejects_missing_modern_bdm(live_conn):
    live_conn.compute.get_server.return_value.attached_volumes.append({"id": "legacy-volume"})
    _assert_recovery_blocked(live_conn, "live_migration_volumes")


@pytest.mark.anyio
async def test_analysis_separates_current_fault_from_migration(admin_client, live_conn):
    resp = await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")

    assert resp.status_code == 200
    body = resp.json()
    assert body["auto_executable"] is True
    assert body["scenario"] == "live_migration_rolled_back"
    assert body["server"]["power_state"] == 4
    assert body["server"]["fault"] == {
        "code": 404,
        "message": "Guest does not have a console available.",
        "created": _FAULT_CREATED,
    }
    migration = body["last_error_migration"]
    assert datetime.fromisoformat(migration["created_at"]) == datetime.fromisoformat(_MIGRATION_CREATED)
    assert datetime.fromisoformat(migration["updated_at"]) == datetime.fromisoformat(_MIGRATION_UPDATED)
    assert migration["migration_type"] == "live-migration"
    assert migration["source_compute"] == _SOURCE
    assert migration["dest_compute"] == _DEST
    _assert_no_mutations(live_conn)


@pytest.mark.parametrize("power_state", [None, 0, 3, 7], ids=["unreadable", "no-state", "paused", "suspended"])
def test_live_migration_blocks_unsafe_power_state(live_conn, power_state):
    live_conn.compute.get_server.return_value.power_state = power_state

    _assert_recovery_blocked(live_conn, "live_migration_power_state")


def test_live_migration_blocks_when_server_is_not_on_source(live_conn):
    live_conn.compute.get_server.return_value.compute_host = _DEST

    _assert_recovery_blocked(live_conn, "live_migration_source")


@pytest.mark.parametrize(
    "failure",
    [
        "missing-rollback",
        "failed-rollback",
        "wrong-event-host",
        "unreadable-actions",
        "unreadable-detail",
        "unreadable-events",
        "unrelated-action",
        "ambiguous-actions",
    ],
)
def test_live_migration_requires_correlated_successful_rollback(live_conn, failure):
    compute = live_conn.compute
    detail = compute.get_server_action.return_value
    if failure == "missing-rollback":
        detail.events = []
    elif failure == "failed-rollback":
        detail.events[0].result = "Error"
    elif failure == "wrong-event-host":
        detail.events[0].host = _SOURCE
    elif failure == "unreadable-actions":
        compute.server_actions.side_effect = RuntimeError("Nova actions unavailable")
    elif failure == "unreadable-detail":
        compute.get_server_action.side_effect = RuntimeError("Nova events unavailable")
    elif failure == "unreadable-events":
        detail.events = None
    elif failure == "unrelated-action":
        compute.server_actions.return_value[0].start_time = "2025-12-31T09:19:24.000000"
        detail.start_time = compute.server_actions.return_value[0].start_time
    else:
        compute.server_actions.return_value.append(
            SimpleNamespace(action="live-migration", request_id="req-ambiguous", start_time=_ACTION_STARTED)
        )

    _assert_recovery_blocked(live_conn, "live_migration_rollback")


@pytest.mark.parametrize("failure", ["dest-host", "migrating-to", "inactive-dest-binding", "unreadable-bindings"])
def test_live_migration_requires_clean_source_port_bindings(live_conn, failure):
    port = live_conn.network.ports.return_value[0]
    bindings = live_conn.network.get.return_value.json.return_value["bindings"]
    if failure == "dest-host":
        port.binding_host_id = _DEST
    elif failure == "migrating-to":
        port.binding_profile = {"migrating_to": _DEST}
    elif failure == "inactive-dest-binding":
        bindings.append({"host": _DEST, "status": "INACTIVE", "profile": {}, "vif_type": "ovs"})
    else:
        live_conn.network.get.side_effect = RuntimeError("Neutron port bindings unavailable")

    _assert_recovery_blocked(live_conn, "live_migration_ports")


@pytest.mark.parametrize("failure", ["dest-host", "dest-attachment-remains", "no-attachment"])
def test_live_migration_requires_clean_source_volume_attachments(live_conn, failure):
    attachments = live_conn.block_storage.get_volume.return_value.attachments
    if failure == "dest-host":
        attachments[0]["host_name"] = _DEST
    elif failure == "dest-attachment-remains":
        attachments.append({"host_name": _DEST, "server_id": _SERVER_ID})
    else:
        attachments.clear()

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


def test_live_migration_reads_each_attachment_view_once(live_conn):
    analysis = instance_recovery.analyze_error_instance(live_conn, _SERVER_ID)

    assert _checks(analysis)["live_migration_volumes"] is True
    live_conn.compute.volume_attachments.assert_called_once_with(_SERVER_ID)
    live_conn.block_storage.get_volume.assert_called_once_with(_VOLUME_ID)
    live_conn.block_storage.get.assert_called_once_with(
        "/attachments/detail",
        params={"volume_id": _VOLUME_ID, "all_tenants": "1"},
        microversion="3.27",
        log=False,
        raise_exc=True,
    )


@pytest.mark.parametrize("status", ["reserved", "attaching"])
def test_live_migration_blocks_leftover_nonattached_cinder_records(live_conn, status):
    records = live_conn.block_storage.get.return_value.json.return_value["attachments"]
    records.append({**records[0], "id": _DEST_PROVIDER, "status": status})

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("id", _DEST_PROVIDER, id="attachment-id"),
        pytest.param("volume_id", _DEST_PROVIDER, id="volume-id"),
        pytest.param("instance", _DEST_PROVIDER, id="instance-id"),
        pytest.param("status", "ATTACHED", id="inexact-status"),
    ],
)
def test_live_migration_requires_exact_cinder_attachment(live_conn, field, value):
    live_conn.block_storage.get.return_value.json.return_value["attachments"][0][field] = value

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


def test_live_migration_requires_nova_bdm_attachment_id(live_conn):
    del live_conn.compute.volume_attachments.return_value[0].attachment_id

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


def test_live_migration_requires_legacy_host_evidence_for_same_attachment(live_conn):
    live_conn.block_storage.get_volume.return_value.attachments[0]["attachment_id"] = _DEST_PROVIDER

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


def test_live_migration_blocks_unreadable_cinder_attachment_detail(live_conn):
    live_conn.block_storage.get.side_effect = RuntimeError("Cinder attachments unavailable")

    _assert_recovery_blocked(live_conn, "live_migration_volumes")


@pytest.mark.parametrize("scenario", ["generic_error", "volume_stuck", "migration_failed_volume_stuck"])
def test_legacy_recovery_does_not_require_modern_volume_attachment_proof(mock_conn, scenario):
    conn = _configure_recovery(mock_conn, scenario)
    del conn.compute.volume_attachments.return_value[0].attachment_id

    analysis = instance_recovery.analyze_error_instance(conn, _SERVER_ID)

    assert analysis["auto_executable"] is True
    assert analysis["scenario"] == scenario
    conn.block_storage.get.assert_not_called()


def test_live_migration_blocks_unreadable_cinder_volume(live_conn):
    live_conn.block_storage.get_volume.side_effect = RuntimeError("Cinder volume unavailable")

    _assert_recovery_blocked(live_conn, "volumes_known")


@pytest.mark.parametrize("failure", ["multiple", "empty", "unreadable", "malformed"])
def test_live_migration_requires_single_readable_allocation(live_conn, failure):
    response = live_conn.placement.get.return_value
    allocations = response.json.return_value["allocations"]
    if failure == "multiple":
        allocations[_DEST_PROVIDER] = {"resources": {"VCPU": 4, "MEMORY_MB": 8192}}
    elif failure == "empty":
        allocations.clear()
    elif failure == "unreadable":
        live_conn.placement.get.side_effect = RuntimeError("Placement unavailable")
    else:
        response.json.return_value = {"allocations": []}

    _assert_recovery_blocked(live_conn, "live_migration_placement")


@pytest.mark.parametrize("failure", ["wrong-host", "lookup-unreadable", "missing-source", "ambiguous-source", "nested"])
def test_live_migration_requires_exact_source_provider(live_conn, failure):
    placement = live_conn.placement
    get = placement.get.side_effect
    providers = get("/resource_providers").json.return_value["resource_providers"]
    if failure == "wrong-host":
        allocations = placement.get.return_value.json.return_value["allocations"]
        allocations[_DEST_PROVIDER] = allocations.pop(_SOURCE_PROVIDER)
    elif failure == "lookup-unreadable":

        def unavailable(path, **kwargs):
            if path == "/resource_providers":
                raise ConnectionError("Placement provider lookup unavailable")
            return get(path, **kwargs)

        placement.get.side_effect = unavailable
    elif failure == "missing-source":
        providers.clear()
    elif failure == "ambiguous-source":
        providers.append({**providers[0], "uuid": _DEST_PROVIDER})
    else:
        providers[0]["parent_provider_uuid"] = _DEST_PROVIDER
        providers[0]["root_provider_uuid"] = _DEST_PROVIDER

    _assert_recovery_blocked(live_conn, "live_migration_placement")


@pytest.mark.parametrize("node", [None, "different.example.test"], ids=["missing", "mismatch"])
def test_live_migration_requires_matching_nova_source_node(live_conn, node):
    live_conn.compute.migrations.return_value[0].source_node = node

    _assert_recovery_blocked(live_conn, "live_migration_placement")
    live_conn.placement.get.assert_not_called()


@pytest.mark.parametrize("failure", ["nova-task", "ongoing-migration"])
def test_live_migration_blocks_when_work_is_in_progress(live_conn, failure):
    if failure == "nova-task":
        live_conn.compute.get_server.return_value.task_state = "migrating"
    else:
        live_conn.compute.server_migrations.return_value = [_migration(id="954", status="running")]

    _assert_recovery_blocked(live_conn, "no_task_in_progress")


def test_live_migration_blocks_missing_nova_task_state(live_conn):
    sdk_server = Server.existing(
        id=_SERVER_ID,
        name="test-vm",
        status="ERROR",
        flavor={"disk": 0},
        power_state=4,
        compute_host=_SOURCE,
    )
    assert sdk_server.task_state is None  # SDK default; Nova omitted the field.
    live_conn.compute.get_server.return_value = sdk_server
    _assert_recovery_blocked(live_conn, "no_task_in_progress")


@pytest.mark.parametrize(
    "failure", ["tied-migrations", "missing-created", "malformed-updated", "inverted-timestamps", "newer-migration"]
)
def test_live_migration_blocks_ambiguous_migration_history(live_conn, failure):
    migrations = live_conn.compute.migrations.return_value
    if failure == "tied-migrations":
        migrations.append(_migration(id="954", source_compute="compute3"))
    elif failure == "missing-created":
        migrations[0].created_at = None
    elif failure == "malformed-updated":
        migrations[0].updated_at = "not-a-timestamp"
    elif failure == "inverted-timestamps":
        migrations[0].updated_at = "2026-01-01T09:00:00Z"
    else:
        migrations.append(
            _migration(
                id="954",
                status="completed",
                created_at="2026-01-02T09:19:25Z",
                updated_at="2026-01-02T09:20:05Z",
            )
        )

    analysis = instance_recovery.analyze_error_instance(live_conn, _SERVER_ID)
    assert analysis["auto_executable"] is False
    if failure in ("tied-migrations", "newer-migration"):
        assert analysis["scenario"] == "manual_review"
    with pytest.raises(ValueError, match="자동 복구 조건 미충족"):
        instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_UNMATCHED_FINGERPRINT)
    _assert_no_mutations(live_conn)


@pytest.mark.parametrize(
    "scenario",
    ["live_migration_rolled_back", "generic_error", "volume_stuck", "migration_failed_volume_stuck"],
)
@pytest.mark.parametrize(
    ("proxy", "method", "check"),
    [
        ("compute", "migrations", "migrations_known"),
        ("compute", "server_migrations", "no_task_in_progress"),
        ("compute", "volume_attachments", "volumes_known"),
        ("network", "ports", "ports_healthy"),
    ],
)
def test_unreadable_common_evidence_blocks_all_recovery(mock_conn, scenario, proxy, method, check):
    conn = _configure_recovery(mock_conn, scenario)
    getattr(getattr(conn, proxy), method).side_effect = RuntimeError(f"{method} unavailable")

    _assert_recovery_blocked(
        conn,
        check,
        live=scenario == "live_migration_rolled_back" and method != "migrations",
    )


@pytest.mark.parametrize(
    ("scenario", "actions", "completed_live"),
    [
        pytest.param("generic_error", _RECOVERY_STEPS, False, id="generic"),
        pytest.param("generic_error", _RECOVERY_STEPS, True, id="completed-live-migration"),
        pytest.param("volume_stuck", _VOLUME_RECOVERY_STEPS, False, id="volume-stuck"),
        pytest.param("migration_failed_volume_stuck", _VOLUME_RECOVERY_STEPS, False, id="failed-cold-migration"),
    ],
)
def test_legacy_recovery_keeps_plan_without_live_evidence(mock_conn, scenario, actions, completed_live):
    conn = _configure_recovery(mock_conn, scenario)
    if completed_live:
        conn.compute.migrations.return_value = [_migration(status="completed")]
    conn.compute.server_actions.side_effect = RuntimeError("Nova actions unavailable")
    conn.network.get.side_effect = RuntimeError("Neutron bindings unavailable")
    conn.placement.get.side_effect = RuntimeError("Placement unavailable")
    mutations = MagicMock()
    mutations.attach_mock(conn.block_storage.reset_volume_status, "volume_reset")
    mutations.attach_mock(conn.compute.reset_server_state, "server_reset")
    mutations.attach_mock(conn.compute.reboot_server, "reboot")

    analysis = instance_recovery.analyze_error_instance(conn, _SERVER_ID)
    result = instance_recovery.execute_recovery(conn, _SERVER_ID, plan_fingerprint=analysis["plan_fingerprint"])

    assert analysis["scenario"] == result["scenario"] == scenario
    assert analysis["auto_executable"] is True
    assert _actions(analysis) == _actions(result) == actions
    assert result["executed"] is True
    assert result["recovered"] is True
    assert result["observed_status"] == "ACTIVE"
    assert all(step["status"] == "success" for step in result["steps"])
    assert not (_LIVE_CHECKS & _checks(analysis).keys())
    if scenario == "migration_failed_volume_stuck":
        assert _SOURCE in analysis["placement_note"]
    conn.compute.server_actions.assert_not_called()
    conn.compute.get_server_action.assert_not_called()
    conn.network.get.assert_not_called()
    conn.placement.get.assert_not_called()
    expected = [call.server_reset(_SERVER_ID, "active"), call.reboot(_SERVER_ID, "HARD")]
    if "reset_volume_state" in actions:
        expected.insert(0, call.volume_reset(_VOLUME_ID, "in-use", "attached"))
    assert mutations.mock_calls == expected


@pytest.mark.parametrize(
    ("reason", "check"),
    [
        ("image-backed", "volume_backed"),
        ("binding-failed", "ports_healthy"),
        ("not-error", "is_error_state"),
    ],
)
def test_legacy_recovery_still_checks_common_safety_rules(mock_conn, reason, check):
    conn = _configure_recovery(mock_conn, "generic_error")
    server = conn.compute.get_server.return_value
    if reason == "image-backed":
        server.flavor["disk"] = 20
        server.image = {"id": "image-1"}
        conn.compute.volume_attachments.return_value = []
    elif reason == "binding-failed":
        port = conn.network.ports.return_value[0]
        port.status = "DOWN"
        port.binding_vif_type = "binding_failed"
    else:
        server.status = "ACTIVE"
        server.vm_state = "active"

    _assert_recovery_blocked(conn, check, live=False)


def test_execute_recovery_stops_on_step_failure(mock_conn):
    conn = _configure_recovery(mock_conn, "generic_error")
    conn.compute.reset_server_state.side_effect = RuntimeError("nova error")

    result = instance_recovery.execute_recovery(conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(conn))

    assert result["executed"] is False
    assert result["recovered"] is False
    assert result["observed_status"] == "ACTIVE"
    assert {step["action"]: step["status"] for step in result["steps"]} == {
        "reset_server_state": "failed",
        "hard_reboot": "skipped",
    }
    conn.compute.reboot_server.assert_not_called()


# ---------------------------------------------------------------------------
# HTTP 엔드포인트 — 권한
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_recovery_analysis_requires_admin(client):
    """일반 사용자 → 403."""
    resp = await client.get(f"{_INSTANCE_URL}/recovery-analysis")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_recover_requires_admin(client):
    """일반 사용자 recover → 403."""
    resp = await client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": _UNMATCHED_FINGERPRINT})
    assert resp.status_code == 403


@pytest.mark.anyio
@pytest.mark.parametrize("replace_owner", [False, True], ids=["same-server", "expired-owner"])
async def test_recover_serializes_concurrent_posts(admin_client, live_conn, _recovery_redis, replace_owner):
    started = Event()
    finish_analysis = Event()
    server = live_conn.compute.get_server.return_value
    lock_key = f"afterglow:instance-recovery:lock:{_SERVER_ID}"
    payload = {"plan_fingerprint": _preview_fingerprint(live_conn)}
    live_conn.compute.get_server.reset_mock()

    def get_server(_server_id):
        started.set()
        assert finish_analysis.wait(timeout=5)
        return server

    live_conn.compute.get_server.side_effect = get_server
    first = asyncio.create_task(admin_client.post(f"{_INSTANCE_URL}/recover", json=payload))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        second = await admin_client.post(f"{_INSTANCE_URL}/recover", json=payload)
        assert second.status_code == 409
        assert second.json()["detail"]["code"] == "RECOVERY_IN_PROGRESS"
        live_conn.compute.get_server.assert_called_once()
        _assert_no_mutations(live_conn)
        if replace_owner:
            await _recovery_redis.set(lock_key, "new-owner", ex=600)
    finally:
        finish_analysis.set()
        result = await first

    if replace_owner:
        assert result.status_code == 409
        assert await _recovery_redis.get(lock_key) == "new-owner"
        _assert_no_mutations(live_conn)
    else:
        assert result.status_code == 200
        assert result.json()["observed_status"] == "ACTIVE"
        live_conn.compute.reset_server_state.assert_not_called()
        live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")
        live_conn.block_storage.reset_volume_status.assert_not_called()
        assert await _recovery_redis.get(lock_key) is None


@pytest.mark.anyio
async def test_recover_requires_shared_redis_before_reanalysis(admin_client, live_conn, monkeypatch):
    monkeypatch.setattr(
        "app.api.identity.admin._get_redis", AsyncMock(side_effect=ConnectionError("Redis unavailable"))
    )
    response = await admin_client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": _UNMATCHED_FINGERPRINT})

    assert response.status_code == 503
    live_conn.compute.get_server.assert_not_called()
    _assert_no_mutations(live_conn)


@pytest.mark.anyio
async def test_recover_returns_409_with_failed_evidence(admin_client, live_conn):
    # A previously safe plan is not enough when evidence changes before POST.
    analysis_resp = await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")
    assert analysis_resp.status_code == 200
    assert analysis_resp.json()["auto_executable"] is True

    live_conn.compute.get_server_action.return_value.events = []
    resp = await admin_client.post(
        f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": analysis_resp.json()["plan_fingerprint"]}
    )

    assert resp.status_code == 409
    failed_analysis_resp = await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")
    assert failed_analysis_resp.status_code == 200
    analysis = failed_analysis_resp.json()
    assert analysis["scenario"] == "manual_review"
    assert analysis["auto_executable"] is False
    failed_check = next(check for check in analysis["checks"] if check["key"] == "live_migration_rollback")
    assert failed_check["passed"] is False
    assert resp.json()["detail"]["code"] == "RECOVERY_BLOCKED"
    assert failed_check["label"] in resp.json()["detail"]["message"]
    _assert_no_mutations(live_conn)


@pytest.mark.anyio
@pytest.mark.parametrize(("old_power", "new_power"), [(1, 4), (4, 1)])
async def test_recover_rejects_stale_power_state_confirmation(admin_client, live_conn, old_power, new_power):
    server = live_conn.compute.get_server.return_value
    server.power_state = old_power
    analysis_resp = await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")
    assert analysis_resp.status_code == 200
    analysis = analysis_resp.json()
    assert analysis["auto_executable"] is True
    expected_restart = "hard_reboot" in _actions(analysis)
    assert expected_restart is (old_power != 1)

    server.power_state = new_power
    resp = await admin_client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": analysis["plan_fingerprint"]})

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RECOVERY_PLAN_CHANGED"
    _assert_no_mutations(live_conn)


@pytest.mark.anyio
async def test_recover_rejects_same_reboot_plan_drift(admin_client, mock_conn):
    conn = _configure_recovery(mock_conn, "generic_error")
    preview = (await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")).json()
    assert preview["scenario"] == "generic_error"
    assert _actions(preview) == _RECOVERY_STEPS
    conn.block_storage.get_volume.return_value.status = "attaching"
    current = (await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")).json()
    assert current["scenario"] == "volume_stuck"
    assert _actions(current) == _VOLUME_RECOVERY_STEPS
    assert current["plan_fingerprint"] != preview["plan_fingerprint"]

    resp = await admin_client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": preview["plan_fingerprint"]})

    assert resp.status_code == 409
    assert resp.json()["detail"]["code"] == "RECOVERY_PLAN_CHANGED"
    _assert_no_mutations(conn)


@pytest.mark.anyio
@pytest.mark.parametrize("payload", [None, {}, {"plan_fingerprint": "bad-digest"}], ids=["no-body", "missing", "bad"])
async def test_recover_requires_valid_plan_fingerprint(admin_client, live_conn, payload):
    resp = await admin_client.post(f"{_INSTANCE_URL}/recover", json=payload)

    assert resp.status_code == 422
    live_conn.compute.get_server.assert_not_called()
    _assert_no_mutations(live_conn)


def test_plan_fingerprint_ignores_unrelated_latest_fault(live_conn):
    fingerprint = _preview_fingerprint(live_conn)
    live_conn.compute.get_server.return_value.fault["message"] = "New console-related fault"
    assert _preview_fingerprint(live_conn) == fingerprint


def test_recovery_polls_until_running_and_idle(live_conn, monkeypatch):
    clock = count()
    monkeypatch.setattr(instance_recovery, "_OBSERVATION_SECONDS", 30)
    monkeypatch.setattr(instance_recovery, "monotonic", lambda: next(clock))
    monkeypatch.setattr(instance_recovery, "sleep", lambda _seconds: None)
    live_conn.compute.get.return_value.json.side_effect = [
        _observed_server("ERROR", power_state=4, task_state="reboot_pending_hard"),
        _observed_server("ERROR", power_state=4, task_state="reboot_started_hard"),
        _observed_server("ERROR", power_state=4, task_state="rebooting_hard"),
        RuntimeError("transient Nova read failure"),
        _observed_server(),
    ]

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["executed"] is True
    assert result["recovered"] is True
    assert result["observed_status"] == "ACTIVE"
    assert [request.args[0] for request in live_conn.compute.get.call_args_list] == [f"/servers/{_SERVER_ID}"] * 5
    live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")


@pytest.mark.parametrize("new_fault", [True, False], ids=["fresh-fault", "old-fault"])
def test_recovery_waits_for_idle_error_and_reports_only_fresh_fault(live_conn, monkeypatch, new_fault):
    monkeypatch.setattr(instance_recovery, "_OBSERVATION_SECONDS", 10)
    monkeypatch.setattr(instance_recovery, "sleep", lambda _seconds: None)
    fault = {
        "message": "Unable to recreate the guest",
        "created": (datetime.now(UTC) + timedelta(seconds=1)).isoformat() if new_fault else _FAULT_CREATED,
        "code": 500,
    }
    terminal = _observed_server("ERROR", power_state=4)
    terminal["server"]["fault"] = fault
    live_conn.compute.get.return_value.json.side_effect = [
        _observed_server("ERROR", power_state=4, task_state="rebooting_hard"),
        terminal,
    ]

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["observed_status"] == "ERROR"
    assert result["observation_terminal"] is True
    assert result["observation_timed_out"] is False
    assert result["observed_fault"] == (fault if new_fault else None)
    assert live_conn.compute.get.call_count == 2


def test_second_precision_nova_record_does_not_prove_it_followed_dispatch(live_conn):
    requested_at = datetime.fromisoformat("2026-01-07T13:29:41.900000+00:00")
    old_or_new = _observed_server("ERROR", power_state=4)["server"]
    old_or_new["fault"] = {"message": "May predate the request", "created": _FAULT_CREATED, "code": 404}
    live_conn.compute.server_actions.return_value.append(SimpleNamespace(action="reboot", start_time=_FAULT_CREATED))

    assert instance_recovery._new_fault(old_or_new, requested_at) is None
    assert not instance_recovery._nova_action_observed(live_conn, _SERVER_ID, "hard_reboot", requested_at, old_or_new)


@pytest.mark.parametrize("outcome", ["commit", "action", "no-commit", "refused"])
def test_ambiguous_reboot_is_never_replayed(live_conn, monkeypatch, outcome):
    if outcome in ("commit", "action"):
        monkeypatch.setattr(instance_recovery, "_OBSERVATION_SECONDS", 10)
        monkeypatch.setattr(instance_recovery, "sleep", lambda _seconds: None)
    # The first observation is only allowed once reboot dispatch returned or raised.
    first = _observed_server("ERROR", power_state=4)
    if outcome == "commit":
        first["server"]["OS-EXT-STS:task_state"] = "rebooting_hard"
    observations = (
        iter([first, _observed_server()])
        if outcome == "commit"
        else iter([_observed_server() if outcome == "action" else first])
    )

    def read_after_dispatch(*_args, **_kwargs):
        live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")
        return next(observations)

    def submit(*_args):
        if outcome == "refused":
            raise ConnectionRefusedError("No TCP connection opened")
        if outcome == "action":
            live_conn.compute.server_actions.return_value.append(
                SimpleNamespace(action="reboot", start_time=(datetime.now(UTC) + timedelta(seconds=1)).isoformat())
            )
        raise ReadTimeout("Response lost")

    live_conn.compute.get.return_value.json.side_effect = read_after_dispatch
    live_conn.compute.reboot_server.side_effect = submit
    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["executed"] is False
    assert result["recovered"] is (outcome in ("commit", "action"))
    assert result["observed_acceptance"] is (outcome in ("commit", "action"))
    assert result["observation_timed_out"] is (outcome == "no-commit")
    assert result["steps"][0]["status"] == ("failed" if outcome == "refused" else "unconfirmed")
    assert result["unconfirmed_action"] == (None if outcome == "refused" else "hard_reboot")
    live_conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")
    live_conn.compute.reset_server_state.assert_not_called()


def test_sdk_executes_exactly_one_hard_reboot_http_request_after_read_timeout(live_conn, monkeypatch):
    """Use the real OpenStack/Keystone adapter over a fake HTTP transport."""
    analysis = instance_recovery.analyze_error_instance(live_conn, _SERVER_ID)
    monkeypatch.setattr(instance_recovery, "analyze_error_instance", lambda *_: analysis)
    native_error = _observed_server("ERROR", power_state=4)["server"]
    native_error.update({"OS-EXT-SRV-ATTR:host": _SOURCE, "OS-EXT-SRV-ATTR:hypervisor_hostname": _SOURCE_NODE})
    wire = MagicMock()
    endpoint = "https://nova.example.test/v2.1"

    def request(method, url, **_kwargs):
        if method == "POST":
            raise ReadTimeout("Nova response lost")
        assert method == "GET"
        response = Response()
        response.status_code = 200
        response.url = url
        response._content = json.dumps({"server": native_error}).encode()
        return response

    wire.request.side_effect = request
    auth_session = Session(auth=Token(endpoint, "synthetic"), session=wire)
    authentic_request = MagicMock(wraps=auth_session.request)
    monkeypatch.setattr(auth_session, "request", authentic_request)
    proxy = ComputeProxy(auth_session, service_type="compute", endpoint_override=endpoint, default_microversion="2.89")
    proxy._connection = SimpleNamespace(
        _global_request_id=None,
        cache_enabled=True,
        _api_cache_keys=set(),
        _cache=MagicMock(),
        current_location=None,
        _get_current_location=lambda **_: None,
    )
    live_conn.compute = proxy

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=analysis["plan_fingerprint"])
    assert result["steps"][0]["status"] == "unconfirmed", result["steps"]
    proxy._connection._cache.get_or_create.assert_not_called()

    [dispatch] = [entry for entry in authentic_request.call_args_list if entry.args[1] == "POST"]
    assert dispatch.kwargs["connect_retries"] == dispatch.kwargs["status_code_retries"] == 0
    assert dispatch.kwargs["timeout"] <= 5
    [sent] = [entry for entry in wire.request.call_args_list if entry.args[0] == "POST"]
    assert sent.args[1] == f"{endpoint}/servers/{_SERVER_ID}/action"
    assert json.loads(sent.kwargs["data"]) == {"reboot": {"type": "HARD"}}


def test_ambiguous_running_reset_is_observed_without_restarting(live_conn):
    live_conn.compute.get_server.return_value.power_state = 1
    observation = _observed_server()
    observation["server"]["updated"] = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    live_conn.compute.get.return_value.json.return_value = observation
    live_conn.compute.reset_server_state.side_effect = ReadTimeout("Response lost after reset")

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["executed"] is False
    assert result["recovered"] is True
    assert result["unconfirmed_action"] == "reset_server_state"
    live_conn.compute.reset_server_state.assert_called_once_with(_SERVER_ID, "active")
    live_conn.compute.reboot_server.assert_not_called()


@pytest.mark.anyio
async def test_cancelled_recovery_request_drains_audit_before_unlock(live_conn, monkeypatch, _recovery_redis):
    audit_started = asyncio.Event()
    finish_audit = asyncio.Event()
    lock_key = f"afterglow:instance-recovery:lock:{_SERVER_ID}"

    async def record(*_args, **_kwargs):
        audit_started.set()
        await finish_audit.wait()

    audit = AsyncMock(side_effect=record)
    monkeypatch.setattr(admin, "rec", audit)
    request = admin.RecoverInstanceRequest(plan_fingerprint=_preview_fingerprint(live_conn))
    recovery = asyncio.create_task(admin.recover_instance(_SERVER_ID, request, live_conn, {"user_id": "admin"}))
    try:
        await asyncio.wait_for(audit_started.wait(), timeout=5)
        recovery.cancel()
        assert await _recovery_redis.get(lock_key)
    finally:
        finish_audit.set()
        with pytest.raises(asyncio.CancelledError):
            await recovery
    audit.assert_awaited_once()
    assert audit.await_args.kwargs["extra"]["observed_status"] == "ACTIVE"
    assert await _recovery_redis.get(lock_key) is None


@pytest.mark.anyio
async def test_recovery_status_is_read_only_and_does_not_guess_acceptance(admin_client, live_conn):
    live_conn.compute.get.return_value.json.return_value = _observed_server("ERROR", power_state=4)
    params = {"requested_at": datetime.now(UTC).isoformat(), "unconfirmed_action": "hard_reboot"}

    result = await admin_client.get(f"{_INSTANCE_URL}/recovery-status", params=params)

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.json()["observed_status"] == "ERROR"
    assert result.json()["observed_acceptance"] is False
    assert result.json()["observation_terminal"] is False
    _assert_no_mutations(live_conn)


@pytest.mark.parametrize(
    ("observation", "status"),
    [
        (_observed_server("REBOOT", task_state="rebooting_hard"), "REBOOT"),
        (_observed_server("ERROR", power_state=4, task_state="rebooting_hard"), "ERROR"),
        (_observed_server(power_state=4), "ACTIVE"),
        (_observed_server(task_state="reboot_pending_hard"), "ACTIVE"),
        ({"server": {"id": _SERVER_ID, "status": "ACTIVE", "OS-EXT-STS:power_state": 1}}, "ACTIVE"),
        (_observed_server("ERROR", power_state=4), "ERROR"),
        (None, "UNKNOWN"),
    ],
    ids=["rebooting", "error-rebooting", "not-running", "task-in-progress", "task-unknown", "error", "unreadable"],
)
def test_recovery_does_not_confuse_accepted_requests_with_completion(live_conn, observation, status):
    if observation is None:
        live_conn.compute.get.side_effect = RuntimeError("Nova status unavailable")
    else:
        live_conn.compute.get.return_value.json.return_value = observation

    result = instance_recovery.execute_recovery(live_conn, _SERVER_ID, plan_fingerprint=_preview_fingerprint(live_conn))

    assert result["executed"] is True
    assert result["recovered"] is False
    assert result["observed_status"] == status
    if observation and observation["server"].get("OS-EXT-STS:task_state") == "rebooting_hard":
        assert result["observation_timed_out"] is True
        assert result["observation_terminal"] is False
        assert result["observed_task_state"] == "rebooting_hard"
    assert all(step["status"] == "success" for step in result["steps"])
    live_conn.compute.get.assert_called_once()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "recovered", "audit_status"),
    [("ACTIVE", True, "success"), ("REBOOT", False, "observed"), ("ERROR", False, "failed")],
)
async def test_recover_reports_and_audits_observed_status(
    admin_client, live_conn, monkeypatch, status, recovered, audit_status
):
    audit = AsyncMock()
    monkeypatch.setattr("app.api.identity.admin.rec", audit)
    live_conn.compute.get.return_value.json.return_value = _observed_server(
        status, task_state="rebooting_hard" if status == "REBOOT" else None
    )

    fingerprint = _preview_fingerprint(live_conn)
    resp = await admin_client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": fingerprint})

    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is True
    assert body["recovered"] is recovered
    assert body["observed_status"] == status
    assert body["scenario"] == "live_migration_rolled_back"
    assert _actions(body) == ["hard_reboot"]
    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["resource_id"] == _SERVER_ID
    assert kwargs["action"] == "recover"
    assert kwargs["resource_type"] == "instance"
    assert kwargs["status"] == audit_status
    assert kwargs["extra"]["scenario"] == body["scenario"]
    assert kwargs["extra"]["plan_fingerprint"] == fingerprint
    assert kwargs["extra"]["observed_status"] == status
    assert kwargs["extra"]["recovered"] is recovered
    assert kwargs["extra"]["steps"] == body["steps"]


@pytest.mark.anyio
async def test_recover_accepts_matching_legacy_plan(admin_client, mock_conn, monkeypatch):
    conn = _configure_recovery(mock_conn, "generic_error")
    monkeypatch.setattr("app.api.identity.admin.rec", AsyncMock())

    preview = (await admin_client.get(f"{_INSTANCE_URL}/recovery-analysis")).json()
    resp = await admin_client.post(f"{_INSTANCE_URL}/recover", json={"plan_fingerprint": preview["plan_fingerprint"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["recovered"] is True
    assert body["scenario"] == "generic_error"
    assert _actions(body) == _RECOVERY_STEPS
    conn.compute.reboot_server.assert_called_once_with(_SERVER_ID, "HARD")
