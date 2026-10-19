"""Shared native adapters: measured reads, real writes, and API isolation.

Transport completion is deliberately not a verified operation result; domain
quota orchestration owns readback after both successful and failed writes.
"""

import asyncio
from threading import Event
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio import CancelScope

from app.api.identity import admin_identity
from app.services import quota_native

TARGET = "target-project"
SECTIONS = ("compute", "volume", "network", "file_storage")
ENDPOINTS = {
    "compute": "https://nova/v2.1",
    "volume": "https://cinder/v3/admin-project",
    "network": "https://neutron/v2.0",
}
PROXIES = {"compute": "compute", "volume": "block_storage", "network": "network"}


@pytest.fixture
def conn():
    connection = MagicMock()
    for section, proxy in PROXIES.items():
        getattr(connection, proxy).get_endpoint.return_value = ENDPOINTS[section] + "/"
    return connection


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(quota_native, "get_settings", lambda: SimpleNamespace(service_manila_enabled=True))


def test_quota_fields_cover_every_existing_request_field():
    fields = quota_native.QUOTA_FIELDS
    assert tuple(fields) == SECTIONS
    request_keys = [key for section in fields.values() for key in section]
    assert len(request_keys) == len(set(request_keys))
    assert set(request_keys) == set(admin_identity.QuotaUpdateRequest.model_fields)
    assert fields["file_storage"] == {
        "shares": "shares",
        "share_gigabytes": "gigabytes",
        "share_snapshots": "snapshots",
        "share_snapshot_gigabytes": "snapshot_gigabytes",
        "share_networks": "share_networks",
        "share_groups": "share_groups",
        "share_group_snapshots": "share_group_snapshots",
    }
    assert fields["volume"]["gigabytes"] == "gigabytes"
    assert fields["volume"]["snapshots"] == "snapshots"


@pytest.mark.parametrize("section", SECTIONS)
def test_get_section_preserves_every_native_field_and_reservations(conn, enabled, section):
    expected = {
        key: {"limit": -1 if index == 0 else index, "in_use": 0, "reserved": index}
        for index, key in enumerate(quota_native.QUOTA_FIELDS[section].values())
    }
    raw = {key: dict(value) for key, value in expected.items()}
    raw["unsupported_resource"] = {"limit": 500, "in_use": 123}
    client = MagicMock()
    if section == "network":
        # Real SDK resources expose original provider names on request.
        for key in expected:
            raw[key]["used"] = raw[key].pop("in_use")
        resource = MagicMock()
        resource.to_dict.return_value = raw
        conn.network.get_quota.return_value = resource
    elif section == "file_storage":
        client.get.return_value = {"quota_set": raw}
    else:
        conn.session.get.return_value.json.return_value = {"quota_set": raw}
    with patch.object(quota_native.manila, "get_client", return_value=client):
        assert quota_native.get_section(conn, TARGET, section) == expected
    if section == "compute":
        conn.session.get.assert_called_once_with(f"{ENDPOINTS[section]}/os-quota-sets/{TARGET}/detail")
        conn.session.get.return_value.raise_for_status.assert_called_once_with()
    elif section == "volume":
        conn.session.get.assert_called_once_with(
            f"{ENDPOINTS[section]}/os-quota-sets/{TARGET}", params={"usage": "true"}
        )
        conn.session.get.return_value.raise_for_status.assert_called_once_with()
    elif section == "network":
        conn.network.get_quota.assert_called_once_with(TARGET, details=True)
        resource.to_dict.assert_called_once_with(original_names=True)
    else:
        client.get.assert_called_once_with(f"quota-sets/{TARGET}/detail")


@pytest.mark.parametrize("reserved", [None, True, False, -1, 1.5, "0", {}])
def test_unknown_or_invalid_reservation_is_omitted(conn, reserved):
    conn.session.get.return_value.json.return_value = {
        "quota_set": {"instances": {"limit": 0, "in_use": 0, "reserved": reserved}}
    }
    assert quota_native.get_section(conn, TARGET, "compute") == {"instances": {"limit": 0, "in_use": 0}}


def test_missing_optional_resources_and_reservations_stay_absent(conn):
    conn.session.get.return_value.json.return_value = {
        "quota_set": {"instances": {"limit": -1, "in_use": 0}, "unknown": {"limit": 1, "in_use": 0}}
    }
    assert quota_native.get_section(conn, TARGET, "compute") == {"instances": {"limit": -1, "in_use": 0}}


@pytest.mark.parametrize(
    "item",
    [
        5,
        {"limit": 1},
        {"in_use": 0},
        {"limit": True, "in_use": 0},
        {"limit": 1.0, "in_use": 0},
        {"limit": "1", "in_use": 0},
        {"limit": -2, "in_use": 0},
        {"limit": 1, "in_use": True},
        {"limit": 1, "in_use": -1},
    ],
)
@pytest.mark.parametrize("section", SECTIONS)
def test_get_section_refuses_missing_or_malformed_measured_usage(conn, enabled, section, item):
    key = next(iter(quota_native.QUOTA_FIELDS[section].values()))
    raw = {key: item}
    conn.session.get.return_value.json.return_value = {"quota_set": raw}
    conn.network.get_quota.return_value = raw
    client = MagicMock()
    client.get.return_value = {"quota_set": raw}
    with patch.object(quota_native.manila, "get_client", return_value=client), pytest.raises(ValueError):
        quota_native.get_section(conn, TARGET, section)


@pytest.mark.parametrize(
    "payload", [None, [], {}, {"quota_set": None}, {"quota_set": {}}, {"quota_set": {"id": TARGET}}]
)
@pytest.mark.parametrize("section", ("compute", "volume", "file_storage"))
def test_get_section_refuses_empty_or_malformed_envelopes(conn, enabled, section, payload):
    conn.session.get.return_value.json.return_value = payload
    client = MagicMock()
    client.get.return_value = payload
    with patch.object(quota_native.manila, "get_client", return_value=client), pytest.raises(ValueError):
        quota_native.get_section(conn, TARGET, section)


def test_neutron_used_is_authoritative_and_reservations_survive(conn):
    conn.network.get_quota.return_value = {"port": {"limit": 20, "used": 4, "in_use": 99, "reserved": 2}}
    assert quota_native.get_section(conn, TARGET, "network") == {"port": {"limit": 20, "in_use": 4, "reserved": 2}}


@pytest.mark.parametrize("section", ("compute", "volume"))
def test_get_section_propagates_unsuccessful_http_status(conn, section):
    conn.session.get.return_value.raise_for_status.side_effect = RuntimeError("native 503")
    with pytest.raises(RuntimeError, match="native 503"):
        quota_native.get_section(conn, TARGET, section)
    conn.session.get.return_value.json.assert_not_called()


@pytest.mark.parametrize("section", tuple(PROXIES))
@pytest.mark.parametrize("endpoint", [None, "", "   "])
def test_missing_service_endpoint_refuses_reads_and_writes(conn, section, endpoint):
    getattr(conn, PROXIES[section]).get_endpoint.return_value = endpoint
    key = next(iter(quota_native.QUOTA_FIELDS[section].values()))
    with pytest.raises(RuntimeError, match="endpoint is unavailable"):
        quota_native.get_section(conn, TARGET, section)
    with pytest.raises(RuntimeError, match="endpoint is unavailable"):
        quota_native.update_section(conn, TARGET, section, {key: 1})
    conn.session.get.assert_not_called()
    conn.session.put.assert_not_called()
    conn.network.get_quota.assert_not_called()


def test_disabled_manila_refuses_direct_reads_and_writes(conn, monkeypatch):
    monkeypatch.setattr(quota_native, "get_settings", lambda: SimpleNamespace(service_manila_enabled=False))
    with patch.object(quota_native.manila, "get_client") as client:
        with pytest.raises(quota_native.QuotaServiceDisabled):
            quota_native.get_section(conn, TARGET, "file_storage")
        with pytest.raises(quota_native.QuotaServiceDisabled):
            quota_native.update_section(conn, TARGET, "file_storage", {"shares": 1})
    client.assert_not_called()


def test_missing_manila_endpoint_propagates_discovery_failure(conn, enabled):
    with patch.object(quota_native.manila, "_get_manila_endpoint", side_effect=RuntimeError("missing endpoint")):
        with pytest.raises(RuntimeError, match="missing endpoint"):
            quota_native.get_section(conn, TARGET, "file_storage")
        with pytest.raises(RuntimeError, match="missing endpoint"):
            quota_native.update_section(conn, TARGET, "file_storage", {"shares": 1})


def test_unknown_section_is_not_treated_as_manila(conn, enabled):
    with patch.object(quota_native.manila, "get_client") as client:
        with pytest.raises(ValueError, match="unknown quota section"):
            quota_native.get_section(conn, TARGET, "unknown")
        with pytest.raises(ValueError, match="unknown quota section"):
            quota_native.update_section(conn, TARGET, "unknown", {"shares": 1})
    client.assert_not_called()
    conn.session.assert_not_called()


@pytest.mark.parametrize("section", SECTIONS)
def test_update_section_writes_every_provider_field_without_readback(conn, enabled, section):
    values = {
        key: -1 if index == 0 else index - 1 for index, key in enumerate(quota_native.QUOTA_FIELDS[section].values())
    }
    client = MagicMock()
    with patch.object(quota_native.manila, "get_client", return_value=client):
        assert quota_native.update_section(conn, TARGET, section, values) is None
    if section == "file_storage":
        client.put.assert_called_once_with(f"quota-sets/{TARGET}", {"quota_set": values})
        conn.session.put.assert_not_called()
    else:
        path = "quotas" if section == "network" else "os-quota-sets"
        envelope = "quota" if section == "network" else "quota_set"
        conn.session.put.assert_called_once_with(
            f"{ENDPOINTS[section]}/{path}/{TARGET}",
            json={envelope: values},
            connect_retries=0,
            status_code_retries=0,
        )
        conn.session.put.return_value.raise_for_status.assert_called_once_with()
        client.put.assert_not_called()
    conn.session.get.assert_not_called()
    conn.network.get_quota.assert_not_called()
    client.get.assert_not_called()


@pytest.mark.parametrize("section", SECTIONS)
def test_update_section_propagates_provider_failure_without_replay(conn, enabled, section):
    values = {next(iter(quota_native.QUOTA_FIELDS[section].values())): 4}
    client = MagicMock()
    if section == "file_storage":
        client.put.side_effect = RuntimeError("native failure")
    else:
        conn.session.put.return_value.raise_for_status.side_effect = RuntimeError("native failure")
    with (
        patch.object(quota_native.manila, "get_client", return_value=client),
        pytest.raises(RuntimeError, match="native failure"),
    ):
        quota_native.update_section(conn, TARGET, section, values)
    assert (client.put if section == "file_storage" else conn.session.put).call_count == 1
    conn.session.get.assert_not_called()


@pytest.mark.parametrize("values", [{}, {"unknown": 3}, {"share_gigabytes": 1}, {"shares": True}, {"shares": -2}])
def test_update_section_rejects_non_native_keys_or_invalid_limits(conn, enabled, values):
    with patch.object(quota_native.manila, "get_client") as client, pytest.raises(ValueError):
        quota_native.update_section(conn, TARGET, "file_storage", values)
    client.assert_not_called()


@pytest.mark.asyncio
async def test_read_project_keeps_successes_and_sanitizes_independent_failures(conn, monkeypatch):
    def read(connection, project_id, section):
        assert connection is conn
        assert project_id == TARGET
        if section == "volume":
            raise RuntimeError("secret provider endpoint/token")
        if section == "file_storage":
            raise quota_native.QuotaServiceDisabled("disabled")
        return {"instances" if section == "compute" else "port": {"limit": 0, "in_use": 0}}

    monkeypatch.setattr(quota_native, "get_section", read)
    result = await quota_native.read_project(conn, TARGET)
    assert result == {
        "project_id": TARGET,
        "compute": {"instances": {"limit": 0, "in_use": 0}},
        "volume": None,
        "network": {"port": {"limit": 0, "in_use": 0}},
        "file_storage": None,
        "availability": {"compute": True, "volume": False, "network": True, "file_storage": False},
        "errors": {"volume": "quota_unavailable", "file_storage": "service_disabled"},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("cancellation", ("asyncio", "anyio"))
async def test_read_project_settles_all_workers_even_repeated_or_level_cancellation(conn, monkeypatch, cancellation):
    loop = asyncio.get_running_loop()
    started = {section: asyncio.Event() for section in SECTIONS}
    finished = {section: asyncio.Event() for section in SECTIONS}
    release = {section: Event() for section in SECTIONS}
    scopes = []

    def read(connection, project_id, section):
        loop.call_soon_threadsafe(started[section].set)
        try:
            if not release[section].wait(timeout=10):
                raise TimeoutError("test worker was not released")
            if section == "volume":
                raise RuntimeError("independent failure during cancellation")
            return {"resource": {"limit": 1, "in_use": 0}}
        finally:
            loop.call_soon_threadsafe(finished[section].set)

    async def run():
        with CancelScope() as scope:
            scopes.append(scope)
            await quota_native.read_project(conn, TARGET)

    monkeypatch.setattr(quota_native, "get_section", read)
    task = asyncio.create_task(run())
    try:
        await asyncio.wait_for(asyncio.gather(*(event.wait() for event in started.values())), timeout=5)
        if cancellation == "asyncio":
            task.cancel()
        else:
            scopes[0].cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release["compute"].set()
        await asyncio.wait_for(finished["compute"].wait(), timeout=5)
        if cancellation == "asyncio":
            task.cancel()
            await asyncio.sleep(0)
        assert not task.done()  # One completed worker must not release the connection.
    finally:
        for event in release.values():
            event.set()
        if cancellation == "asyncio":
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            await task
    assert all(event.is_set() for event in finished.values())


@pytest.mark.asyncio
async def test_admin_get_delegates_to_shared_read_boundary(admin_client, mock_conn, monkeypatch):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id=TARGET, domain_id="default")
    expected = {
        "project_id": TARGET,
        **dict.fromkeys(SECTIONS),
        "availability": dict.fromkeys(SECTIONS, False),
        "errors": dict.fromkeys(SECTIONS, "quota_unavailable"),
    }
    read = AsyncMock(return_value=expected)
    monkeypatch.setattr(quota_native, "read_project", read)
    response = await admin_client.get(f"/api/v1/admin/quotas/{TARGET}?domain_id=default")
    assert response.status_code == 200
    assert response.json() == expected
    read.assert_awaited_once_with(mock_conn, TARGET)
    mock_conn.session.get.assert_not_called()


@pytest.mark.asyncio
async def test_admin_get_guard_prevents_shared_provider_reads(non_admin_client, monkeypatch):
    read = AsyncMock()
    monkeypatch.setattr(quota_native, "read_project", read)
    response = await non_admin_client.get(f"/api/v1/admin/quotas/{TARGET}?domain_id=default")
    assert response.status_code == 403
    read.assert_not_awaited()
