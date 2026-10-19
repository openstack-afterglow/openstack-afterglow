"""Admin project quotas: target scope, measured usage, and independent writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services import quota_native

TARGET = "target-project"
PATH = f"/api/v1/admin/quotas/{TARGET}?domain_id=default"


@pytest.fixture(autouse=True)
def selected_domain_directory(mock_conn):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id=TARGET, domain_id="default")


def _entries(*keys, usage_key="in_use"):
    return {key: {"limit": index + 10, usage_key: index + 2} for index, key in enumerate(keys)}


def _read_sources(conn):
    nova = _entries(
        "instances",
        "cores",
        "ram",
        "key_pairs",
        "server_groups",
        "server_group_members",
        "injected_files",
        "injected_file_content_bytes",
        "injected_file_path_bytes",
        "metadata_items",
    )
    cinder = _entries("volumes", "snapshots", "gigabytes")
    neutron = _entries(
        "network",
        "subnet",
        "port",
        "router",
        "floatingip",
        "security_group",
        "security_group_rule",
        usage_key="used",
    )
    manila = _entries(
        "shares",
        "gigabytes",
        "snapshots",
        "snapshot_gigabytes",
        "share_networks",
        "share_groups",
        "share_group_snapshots",
    )
    conn.compute.get_endpoint.return_value = "https://nova/v2"
    conn.block_storage.get_endpoint.return_value = "https://cinder/v3"
    conn.network.get_endpoint.return_value = "https://neutron/v2.0"

    def fetch(url, **kwargs):
        response = MagicMock()
        if url == f"https://nova/v2/os-quota-sets/{TARGET}/detail":
            assert kwargs == {}
            response.json.return_value = {"quota_set": nova}
        elif url == f"https://cinder/v3/os-quota-sets/{TARGET}":
            assert kwargs == {"params": {"usage": "true"}}
            response.json.return_value = {"quota_set": cinder}
        else:
            raise AssertionError(f"unexpected quota request: {url}")
        return response

    conn.session.get.side_effect = fetch
    network_quota = MagicMock()
    network_quota.to_dict.return_value = neutron
    conn.network.get_quota.return_value = network_quota
    client = MagicMock()
    client.get.return_value = {"quota_set": manila}
    return nova, cinder, neutron, manila, client


@pytest.mark.asyncio
async def test_read_all_target_quota_sections(admin_client, mock_conn):
    nova, cinder, neutron, manila, client = _read_sources(mock_conn)
    with (
        patch.object(quota_native, "get_settings", return_value=SimpleNamespace(service_manila_enabled=True)),
        patch.object(quota_native.manila, "get_client", return_value=client) as get_client,
    ):
        response = await admin_client.get(PATH)
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == TARGET
    assert body["errors"] == {}
    assert body["availability"] == dict.fromkeys(("compute", "volume", "network", "file_storage"), True)
    assert body["compute"] == nova
    assert body["volume"] == cinder
    assert body["network"] == {
        key: {"limit": entry["limit"], "in_use": entry["used"]} for key, entry in neutron.items()
    }
    assert body["file_storage"] == manila
    mock_conn.network.get_quota.assert_called_once_with(TARGET, details=True)
    get_client.assert_called_once_with(mock_conn)
    client.get.assert_called_once_with(f"quota-sets/{TARGET}/detail")


@pytest.mark.asyncio
async def test_read_partial_failure_does_not_report_fabricated_usage(admin_client, mock_conn):
    nova, _, _, _, client = _read_sources(mock_conn)
    nova.pop("cores")
    # A successful payload can omit an optional resource; a failed section is unavailable.
    mock_conn.network.get_quota.side_effect = RuntimeError("upstream unavailable")
    client.get.return_value = {"quota_set": {"shares": {"limit": 4}}}
    with (
        patch.object(quota_native, "get_settings", return_value=SimpleNamespace(service_manila_enabled=True)),
        patch.object(quota_native.manila, "get_client", return_value=client),
    ):
        response = await admin_client.get(PATH)
    assert response.status_code == 200
    body = response.json()
    assert "cores" not in body["compute"]
    assert body["volume"]["volumes"]["in_use"] == 2
    assert body["network"] is body["file_storage"] is None
    assert body["availability"] == {"compute": True, "volume": True, "network": False, "file_storage": False}
    assert body["errors"] == {"network": "quota_unavailable", "file_storage": "quota_unavailable"}


@pytest.mark.asyncio
async def test_read_rejects_unsuccessful_cinder_response(admin_client, mock_conn):
    _read_sources(mock_conn)
    original = mock_conn.session.get.side_effect

    def fetch(url, **kwargs):
        response = original(url, **kwargs)
        if "cinder" in url:
            response.raise_for_status.side_effect = RuntimeError("503")
        return response

    mock_conn.session.get.side_effect = fetch
    with patch.object(quota_native, "get_settings", return_value=SimpleNamespace(service_manila_enabled=False)):
        response = await admin_client.get(PATH)
    body = response.json()
    assert body["volume"] is None
    assert body["availability"]["volume"] is False
    assert body["errors"]["volume"] == "quota_unavailable"
    assert body["compute"]["instances"] == {"limit": 10, "in_use": 2}


@pytest.mark.asyncio
async def test_manila_disabled_does_not_contact_service(admin_client, mock_conn):
    _read_sources(mock_conn)
    with (
        patch.object(quota_native, "get_settings", return_value=SimpleNamespace(service_manila_enabled=False)),
        patch.object(quota_native.manila, "get_client") as get_client,
    ):
        response = await admin_client.get(PATH)
    assert response.status_code == 200
    assert response.json()["file_storage"] is None
    assert response.json()["availability"]["file_storage"] is False
    assert response.json()["errors"]["file_storage"] == "service_disabled"
    get_client.assert_not_called()


@pytest.mark.asyncio
async def test_admin_guard_prevents_cross_project_reads_and_writes(non_admin_client, mock_conn):
    assert (await non_admin_client.get(PATH)).status_code == 403
    assert (await non_admin_client.put(PATH, json={"instances": 3})).status_code == 403
    mock_conn.session.get.assert_not_called()
    mock_conn.compute.update_quota_set.assert_not_called()


@pytest.mark.asyncio
async def test_every_admin_quota_section_uses_shared_budget_writer(admin_client, mock_conn):
    from app.services import domain_quotas

    payload = {
        key: index for index, key in enumerate(key for fields in quota_native.QUOTA_FIELDS.values() for key in fields)
    }
    result = {
        "project_id": TARGET,
        "domain_id": "default",
        "operation_id": "journal",
        "status": "updated",
        "updated": list(quota_native.QUOTA_FIELDS),
        "errors": {},
    }
    with patch.object(domain_quotas, "update_project", new_callable=AsyncMock, return_value=result) as update:
        response = await admin_client.put(PATH, json=payload)
    assert response.status_code == 200
    assert response.json() == result
    update.assert_awaited_once_with(mock_conn, TARGET, payload)
    mock_conn.compute.update_quota_set.assert_not_called()
    mock_conn.block_storage.update_quota_set.assert_not_called()
    mock_conn.network.update_quota.assert_not_called()


@pytest.mark.asyncio
async def test_budget_conflict_is_not_suppressed_by_old_admin_writer(admin_client, mock_conn):
    from fastapi import HTTPException

    from app.services import domain_quotas

    with patch.object(
        domain_quotas,
        "update_project",
        new_callable=AsyncMock,
        side_effect=HTTPException(409, "quota_budget_exceeded:instances"),
    ):
        response = await admin_client.put(PATH, json={"instances": 100})
    assert response.status_code == 409
    mock_conn.compute.update_quota_set.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [{}, {"instances": -2}, {"instances": 1.5}, {"instances": True}, {"instances": None}, {"unknown": 4}]
)
async def test_invalid_write_never_mutates(admin_client, mock_conn, payload):
    response = await admin_client.put(PATH, json=payload)
    assert response.status_code == 422
    mock_conn.compute.update_quota_set.assert_not_called()
    mock_conn.block_storage.update_quota_set.assert_not_called()
    mock_conn.network.update_quota.assert_not_called()


@pytest.mark.asyncio
async def test_admin_writer_preserves_partial_native_operation_state(admin_client, mock_conn):
    from app.services import domain_quotas

    result = {
        "project_id": TARGET,
        "domain_id": "default",
        "operation_id": "durable-operation",
        "status": "unknown",
        "updated": ["compute"],
        "errors": {"volume": "native_readback_unavailable"},
    }
    with patch.object(domain_quotas, "update_project", new_callable=AsyncMock, return_value=result):
        response = await admin_client.put(PATH, json={"instances": 1, "volumes": 2})
    assert response.status_code == 200
    assert response.json() == result
    mock_conn.compute.update_quota_set.assert_not_called()
