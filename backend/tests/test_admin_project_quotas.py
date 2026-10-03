"""Admin project quotas: target scope, measured usage, and independent writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from app.api.identity import admin_identity

TARGET = "target-project"
PATH = f"/api/v1/admin/quotas/{TARGET}"


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
        patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=True)),
        patch.object(admin_identity.manila, "get_client", return_value=client) as get_client,
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
        patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=True)),
        patch.object(admin_identity.manila, "get_client", return_value=client),
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
    with patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=False)):
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
        patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=False)),
        patch.object(admin_identity.manila, "get_client") as get_client,
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
async def test_write_maps_all_sections_and_invalidates_target_cache(admin_client, mock_conn):
    client = MagicMock()
    payload = {
        "instances": 4,
        "cores": 12,
        "ram": 2048,
        "key_pairs": 8,
        "server_groups": 2,
        "server_group_members": 6,
        "injected_files": 4,
        "injected_file_content_bytes": 1024,
        "injected_file_path_bytes": 255,
        "metadata_items": 128,
        "volumes": 7,
        "snapshots": 8,
        "gigabytes": 100,
        "network": 1,
        "subnet": 2,
        "port": 3,
        "router": 4,
        "floatingip": 5,
        "security_group": 6,
        "security_group_rule": 7,
        "shares": 8,
        "share_gigabytes": 200,
        "share_snapshots": 9,
        "share_snapshot_gigabytes": 300,
        "share_networks": 10,
        "share_groups": 11,
        "share_group_snapshots": 12,
    }
    with (
        patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=True)),
        patch.object(admin_identity.manila, "get_client", return_value=client),
        patch.object(admin_identity, "invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await admin_client.put(PATH, json=payload)
    assert response.status_code == 200
    assert response.json() == {
        "project_id": TARGET,
        "status": "updated",
        "updated": ["compute", "volume", "network", "file_storage"],
        "errors": {},
    }
    mock_conn.compute.update_quota_set.assert_called_once_with(
        TARGET,
        instances=4,
        cores=12,
        ram=2048,
        key_pairs=8,
        server_groups=2,
        server_group_members=6,
        injected_files=4,
        injected_file_content_bytes=1024,
        injected_file_path_bytes=255,
        metadata_items=128,
    )
    mock_conn.block_storage.update_quota_set.assert_called_once_with(
        TARGET,
        volumes=7,
        snapshots=8,
        gigabytes=100,
    )
    mock_conn.network.update_quota.assert_called_once_with(
        TARGET,
        network=1,
        subnet=2,
        port=3,
        router=4,
        floatingip=5,
        security_group=6,
        security_group_rule=7,
    )
    client.put.assert_called_once_with(
        f"quota-sets/{TARGET}",
        {
            "quota_set": {
                "shares": 8,
                "gigabytes": 200,
                "snapshots": 9,
                "snapshot_gigabytes": 300,
                "share_networks": 10,
                "share_groups": 11,
                "share_group_snapshots": 12,
            }
        },
    )
    assert invalidate.call_args_list.count(call(f"afterglow:dashboard:{TARGET}:quotas")) == 1
    assert invalidate.call_args_list.count(call(f"afterglow:dashboard:{TARGET}:quotas:overview")) == 1
    assert call(f"afterglow:nova:{TARGET}:quota:strict") in invalidate.call_args_list
    assert call(f"afterglow:cinder:{TARGET}:quota:strict") in invalidate.call_args_list


@pytest.mark.asyncio
async def test_write_one_section_leaves_others_untouched(admin_client, mock_conn):
    with patch.object(admin_identity, "invalidate", new_callable=AsyncMock) as invalidate:
        response = await admin_client.put(PATH, json={"security_group_rule": -1})
    assert response.json()["updated"] == ["network"]
    mock_conn.network.update_quota.assert_called_once_with(TARGET, security_group_rule=-1)
    mock_conn.compute.update_quota_set.assert_not_called()
    mock_conn.block_storage.update_quota_set.assert_not_called()
    assert invalidate.call_count == 2


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
async def test_write_partial_failure_and_disabled_manila(admin_client, mock_conn):
    mock_conn.compute.update_quota_set.side_effect = RuntimeError("Nova failure")
    with (
        patch.object(admin_identity, "get_settings", return_value=SimpleNamespace(service_manila_enabled=False)),
        patch.object(admin_identity.manila, "get_client") as get_client,
        patch.object(admin_identity, "invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await admin_client.put(PATH, json={"instances": 1, "volumes": 2, "shares": 3})
    assert response.status_code == 200
    assert response.json() == {
        "project_id": TARGET,
        "status": "partial",
        "updated": ["volume"],
        "errors": {"compute": "update_failed", "file_storage": "service_disabled"},
    }
    mock_conn.block_storage.update_quota_set.assert_called_once_with(TARGET, volumes=2)
    get_client.assert_not_called()
    assert invalidate.call_args_list == [
        call(f"afterglow:dashboard:{TARGET}:quotas"),
        call(f"afterglow:dashboard:{TARGET}:quotas:overview"),
        call(f"afterglow:cinder:{TARGET}:quota:strict"),
    ]
