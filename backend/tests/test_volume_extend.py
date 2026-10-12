"""Project extension policy exercised through the real endpoint and helper.

Only provider I/O, cache invalidation and activity persistence are mocked. SDK
resources retain real Nova/Cinder field aliases and VolumeInfo conversion.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

import pytest
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.server import Server
from openstack.exceptions import HttpException, ResourceNotFound

from app.services import cinder

PROJECT = "test-project-123"
VOLUME = "vol-extend-1"
URL = f"/api/v1/volumes/{VOLUME}/extend"


def _volume(**changes):
    fields = dict(
        id=VOLUME,
        project_id=PROJECT,
        name="test-vol",
        size=50,
        status="available",
        attachments=[],
        volume_type="ceph",
    )
    fields.update(changes)
    return Volume(**fields)


def _server(server_id="vm-1", **changes):
    fields = {
        "id": server_id,
        "tenant_id": PROJECT,
        "status": "SHUTOFF",
        "OS-EXT-STS:power_state": 4,
        "OS-EXT-STS:task_state": None,
        "os-extended-volumes:volumes_attached": [{"id": VOLUME}],
    }
    fields.update(changes)
    return Server(**fields)


def _attached(*server_ids):
    return _volume(status="in-use", attachments=[{"server_id": sid, "volume_id": VOLUME} for sid in server_ids])


@pytest.fixture(autouse=True)
def isolate_extension_side_effects():
    with (
        patch("app.api.storage.volumes.rec", new_callable=AsyncMock) as record,
        patch("app.api.storage.volumes.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        yield record, invalidate


@pytest.mark.asyncio
@pytest.mark.parametrize("observed_size", [50, 60])
async def test_available_unattached_returns_actual_provider_reread(client, mock_conn, observed_size):
    current = _volume()
    observed = _volume(size=observed_size, status="extending", name="provider-name")
    mock_conn.block_storage.get_volume.side_effect = [current, _volume(), observed]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 200
    assert response.json()["size"] == observed_size
    assert response.json()["status"] == "extending"
    assert response.json()["name"] == "provider-name"
    assert response.json()["volume_type"] == "ceph"
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)
    mock_conn.compute.get_server.assert_not_called()
    assert mock_conn.block_storage.method_calls == [
        call.get_volume(VOLUME),
        call.get_volume(VOLUME),
        call.extend_volume(VOLUME, 60),
        call.get_volume(VOLUME),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("server_ids", [("vm-1",), ("vm-1", "vm-2")])
async def test_stopped_attached_and_multiattach_checks_every_owner(client, mock_conn, server_ids):
    current = _attached(*server_ids)
    mock_conn.block_storage.get_volume.side_effect = [current, _attached(*server_ids), _volume(status="extending")]
    mock_conn.compute.get_server.side_effect = [_server(sid) for sid in server_ids]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 200
    assert response.json()["size"] == 50
    mock_conn.compute.get_server.assert_has_calls([call(sid) for sid in server_ids])
    assert mock_conn.compute.get_server.call_count == len(server_ids)
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)
    assert mock_conn.mock_calls == [
        call.block_storage.get_volume(VOLUME),
        *[call.compute.get_server(sid) for sid in server_ids],
        call.block_storage.get_volume(VOLUME),
        call.block_storage.extend_volume(VOLUME, 60),
        call.block_storage.get_volume(VOLUME),
    ]


_UNSAFE_SERVERS = [
    pytest.param(
        Server(id="vm-1", project_id=PROJECT, status="SHUTOFF", power_state=4, attached_volumes=[{"id": VOLUME}]),
        id="sdk-omitted-task-is-not-idle",
    ),
    pytest.param(
        {
            "id": "vm-1",
            "tenant_id": PROJECT,
            "status": "SHUTOFF",
            "power_state": 4,
            "OS-EXT-STS:power_state": 1,
            "task_state": None,
            "attached_volumes": [{"id": VOLUME}],
        },
        id="contradictory-power-aliases",
    ),
    pytest.param(None, id="missing-server"),
    pytest.param(_server(status="ACTIVE"), id="active"),
    pytest.param(_server(status="UNKNOWN"), id="unknown-status"),
    pytest.param(_server(status=None), id="missing-status"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": 1}), id="running-power"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": 0}), id="nostate-is-not-off"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": None}), id="unknown-power"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": False}), id="boolean-power"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": 4.0}), id="fractional-power"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": 4.9}), id="sdk-must-not-truncate-fractional-power"),
    pytest.param(_server(**{"OS-EXT-STS:power_state": "4.9"}), id="sdk-must-not-coerce-malformed-power-string"),
    pytest.param(_server(**{"OS-EXT-STS:task_state": "powering-on"}), id="transitional-task"),
    pytest.param(_server(**{"OS-EXT-STS:task_state": ""}), id="unproven-idle-task"),
    pytest.param(_server(tenant_id="foreign"), id="foreign-project"),
    pytest.param(_server(tenant_id=None), id="missing-project"),
    pytest.param(_server(server_id="wrong-vm"), id="wrong-server-identity"),
    pytest.param(_server(**{"os-extended-volumes:volumes_attached": []}), id="stale-cinder-attachment"),
    pytest.param(_server(**{"os-extended-volumes:volumes_attached": None}), id="unknown-nova-attachments"),
    pytest.param(_server(**{"os-extended-volumes:volumes_attached": [{"id": "different-volume"}]}), id="wrong-volume"),
    pytest.param(_server(**{"os-extended-volumes:volumes_attached": [None]}), id="malformed-nova-attachments"),
    pytest.param(SimpleNamespace(id="vm-1", project_id=PROJECT, status="SHUTOFF"), id="missing-state-fields"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("server", _UNSAFE_SERVERS)
async def test_unproven_attachment_state_never_extends(client, mock_conn, server):
    mock_conn.block_storage.get_volume.return_value = _attached("vm-1")
    mock_conn.compute.get_server.return_value = server

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("server", [_server("vm-2", status="ACTIVE"), _server("vm-2", tenant_id="foreign")])
async def test_multiattach_rejects_later_unsafe_owner(client, mock_conn, server):
    mock_conn.block_storage.get_volume.return_value = _attached("vm-1", "vm-2")
    mock_conn.compute.get_server.side_effect = [_server(), server]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 409
    assert mock_conn.compute.get_server.call_args_list == [call("vm-1"), call("vm-2")]
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "volume,expected",
    [
        pytest.param(None, 404, id="missing-target"),
        pytest.param(_volume(id="wrong-volume"), 404, id="wrong-identity"),
        pytest.param(_volume(project_id="foreign"), 404, id="foreign-volume"),
        pytest.param(_volume(project_id=None), 404, id="unknown-owner"),
        pytest.param(_volume(status=None), 409, id="missing-status"),
        pytest.param(_volume(status="error"), 409, id="error-status"),
        pytest.param(_volume(status="extending"), 409, id="already-extending"),
        pytest.param(_volume(status="in-use"), 409, id="in-use-without-attachments"),
        pytest.param(_volume(attachments=[{"server_id": "vm-1"}]), 409, id="available-with-attachments"),
        pytest.param(_volume(attachments=None), 409, id="unknown-attachments"),
        pytest.param(_volume(status="in-use", attachments=[{}]), 409, id="unknown-server"),
        pytest.param(_volume(status="in-use", attachments=[None]), 409, id="malformed-attachment"),
        pytest.param(_volume(status="in-use", attachments=[{"server_id": ""}]), 409, id="empty-server"),
        pytest.param(
            _volume(status="in-use", attachments=[{"server_id": "vm-1", "volume_id": "foreign"}]),
            409,
            id="inconsistent-attachment-volume",
        ),
        pytest.param(
            _volume(status="in-use", attachments=[{"server_id": "vm-1", "status": "detaching"}]),
            409,
            id="detaching-attachment",
        ),
    ],
)
async def test_uncertain_volume_never_extends(client, mock_conn, volume, expected):
    mock_conn.block_storage.get_volume.return_value = volume

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == expected
    mock_conn.block_storage.extend_volume.assert_not_called()
    mock_conn.compute.get_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("new_size", [30, 50])
async def test_shrink_and_equal_sizes_never_extend(client, mock_conn, new_size):
    mock_conn.block_storage.get_volume.return_value = _volume()

    response = await client.post(URL, json={"new_size": new_size})

    assert response.status_code == 400
    assert f"{new_size}GB" in response.json()["detail"]
    assert "50GB" in response.json()["detail"]
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("new_size", [0, -10, 60.5, 60.0, True, False, "60", 2**31, None])
async def test_request_requires_strict_positive_int32(client, mock_conn, new_size):
    response = await client.post(URL, json={"new_size": new_size})

    assert response.status_code == 422
    mock_conn.block_storage.get_volume.assert_not_called()
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.parametrize("new_size", [0, -1, 60.5, 60.0, True, False, "60", 2**31, None])
def test_helper_also_rejects_invalid_sizes(mock_conn, new_size):
    with pytest.raises(cinder.VolumeExtensionError) as exc:
        cinder.extend_volume(mock_conn, VOLUME, new_size)

    assert exc.value.status_code == 400
    mock_conn.block_storage.get_volume.assert_not_called()
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.parametrize("size", [None, 0, -1, True, 50.5, "50", 2**31])
@pytest.mark.parametrize("sdk", [False, True])
def test_helper_rejects_unknown_or_invalid_current_capacity(mock_conn, size, sdk):
    mock_conn.block_storage.get_volume.return_value = (
        _volume(size=size)
        if sdk
        else SimpleNamespace(id=VOLUME, project_id=PROJECT, size=size, status="available", attachments=[])
    )

    with pytest.raises(cinder.VolumeExtensionError) as exc:
        cinder.extend_volume(mock_conn, VOLUME, 60)

    assert exc.value.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


def test_helper_allows_int32_maximum_and_returns_actual_info(mock_conn):
    current = _volume(size=cinder.MAX_VOLUME_SIZE - 1)
    mock_conn.block_storage.get_volume.side_effect = [current, current, _volume(size=cinder.MAX_VOLUME_SIZE)]

    result = cinder.extend_volume(mock_conn, VOLUME, cinder.MAX_VOLUME_SIZE)

    assert result.size == cinder.MAX_VOLUME_SIZE
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, cinder.MAX_VOLUME_SIZE)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "latest,expected",
    [
        pytest.param(None, 404, id="disappeared"),
        pytest.param(_volume(project_id="foreign"), 404, id="ownership-changed"),
        pytest.param(_volume(size=60), 400, id="already-grown"),
        pytest.param(_volume(size=55), 409, id="size-changed"),
        pytest.param(_volume(status="extending"), 409, id="status-changed"),
        pytest.param(_attached("vm-2"), 409, id="attachments-changed"),
    ],
)
async def test_final_cinder_reread_fences_stale_snapshot(client, mock_conn, latest, expected):
    mock_conn.block_storage.get_volume.side_effect = [_volume(), latest]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == expected
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
async def test_attachment_change_during_nova_lookup_is_rejected(client, mock_conn):
    mock_conn.block_storage.get_volume.side_effect = [_attached("vm-1"), _attached("vm-1", "vm-2")]
    mock_conn.compute.get_server.return_value = _server()

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner", ["foreign", None])
async def test_system_admin_project_route_has_no_ownership_bypass(admin_client, mock_conn, owner):
    mock_conn.block_storage.get_volume.return_value = _volume(project_id=owner)

    response = await admin_client.post(URL, json={"new_size": 60})

    assert response.status_code == 404
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
async def test_system_admin_project_route_uses_effective_target_not_home_project(admin_client, mock_conn):
    mock_conn._afterglow_project_id = "target-project"
    mock_conn._afterglow_authenticated_project_id = PROJECT
    current = _volume(project_id="target-project")
    mock_conn.block_storage.get_volume.side_effect = [current, current, _volume(project_id="target-project", size=60)]

    response = await admin_client.post(URL, json={"new_size": 60})

    assert response.status_code == 200
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)


@pytest.mark.parametrize("project_id", [None, ""])
def test_helper_rejects_unknown_effective_scope(mock_conn, project_id):
    mock_conn._afterglow_project_id = project_id

    with pytest.raises(cinder.VolumeExtensionError) as exc:
        cinder.extend_volume(mock_conn, VOLUME, 60)

    assert exc.value.status_code == 404
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "final-lookup", "extend"])
@pytest.mark.parametrize("status", [400, 403, 404, 409, 413, 500, 503])
async def test_cinder_http_errors_are_not_misreported(client, mock_conn, stage, status):
    error = HttpException("private provider error", http_status=status)
    mock_conn.block_storage.get_volume.return_value = _volume()
    if stage == "lookup":
        mock_conn.block_storage.get_volume.side_effect = error
    elif stage == "final-lookup":
        mock_conn.block_storage.get_volume.side_effect = [_volume(), error]
    else:
        mock_conn.block_storage.extend_volume.side_effect = error

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == (status if status in (400, 403, 404, 409, 413) else 502)
    assert "private provider error" not in response.text
    if stage != "extend":
        mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("error,expected", [(ResourceNotFound(), 409), (RuntimeError("private failure"), 502)])
async def test_nova_lookup_errors_fail_closed(client, mock_conn, error, expected):
    mock_conn.block_storage.get_volume.return_value = _attached("vm-1")
    mock_conn.compute.get_server.side_effect = error

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == expected
    assert "private failure" not in response.text
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "observed",
    [
        None,
        _volume(status=None),
        _volume(size=None),
        _volume(size=True),
        _volume(attachments=None),
        _volume(project_id="foreign"),
        ResourceNotFound(),
    ],
)
async def test_accepted_extension_with_unreadable_result_is_uncertain(client, mock_conn, observed):
    mock_conn.block_storage.get_volume.side_effect = [_volume(), _volume(), observed]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 502
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)


@pytest.mark.parametrize("power", [4, "4"])
def test_helper_accepts_authoritative_nova_power_representations(mock_conn, power):
    mock_conn.block_storage.get_volume.side_effect = [_attached("vm-1"), _attached("vm-1"), _volume(status="extending")]
    mock_conn.compute.get_server.return_value = _server(**{"OS-EXT-STS:power_state": power})

    result = cinder.extend_volume(mock_conn, VOLUME, 60)

    assert result.size == 50
    assert result.status == "extending"
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)


@pytest.mark.asyncio
async def test_global_admin_extension_preserves_separate_sdk_response_contract(admin_client, mock_conn):
    # This privileged global action intentionally does not use the project helper.
    response = await admin_client.post(f"/api/v1/admin/volumes/{VOLUME}/extend", json={"new_size": 60})

    assert response.status_code == 200
    assert response.json() == {"status": "extending"}
    mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)
    mock_conn.block_storage.get_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "final-lookup"])
async def test_missing_target_provider_exception_never_extends(client, mock_conn, stage):
    error = ResourceNotFound()
    mock_conn.block_storage.get_volume.side_effect = error if stage == "lookup" else [_volume(), error]

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 404
    mock_conn.block_storage.extend_volume.assert_not_called()


def test_helper_uses_live_sdk_fields_not_resource_dict_snapshot(mock_conn):
    mock_conn.block_storage.get_volume.return_value = _attached("vm-1")
    server = _server()
    # SDK resources also subclass dict; that dict retains the initial value.
    server.power_state = 1
    mock_conn.compute.get_server.return_value = server

    with pytest.raises(cinder.VolumeExtensionError) as exc:
        cinder.extend_volume(mock_conn, VOLUME, 60)

    assert exc.value.status_code == 409
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
async def test_system_admin_effective_target_rejects_home_project_volume(admin_client, mock_conn):
    mock_conn._afterglow_project_id = "target-project"
    mock_conn._afterglow_authenticated_project_id = PROJECT
    mock_conn.block_storage.get_volume.return_value = _volume(project_id=PROJECT)

    response = await admin_client.post(URL, json={"new_size": 60})

    assert response.status_code == 404
    mock_conn.block_storage.extend_volume.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["lookup", "final-lookup", "extend", "reread"])
async def test_generic_cinder_failures_are_service_errors(client, mock_conn, stage):
    error = RuntimeError("private provider failure")
    current = _volume()
    if stage == "lookup":
        mock_conn.block_storage.get_volume.side_effect = error
    elif stage == "final-lookup":
        mock_conn.block_storage.get_volume.side_effect = [current, error]
    elif stage == "reread":
        mock_conn.block_storage.get_volume.side_effect = [current, current, error]
    else:
        mock_conn.block_storage.get_volume.return_value = current
        mock_conn.block_storage.extend_volume.side_effect = error

    response = await client.post(URL, json={"new_size": 60})

    assert response.status_code == 502
    assert "private provider failure" not in response.text
    if stage in ("lookup", "final-lookup"):
        mock_conn.block_storage.extend_volume.assert_not_called()
    else:
        mock_conn.block_storage.extend_volume.assert_called_once_with(VOLUME, 60)
