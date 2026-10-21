"""Display-name writes keep caller authority, ownership and provider confirmation."""

from unittest.mock import AsyncMock, patch

import pytest
from openstack.compute.v2.server import Server

from app.models.compute import InstanceInfo
from app.services import nova

pytest_plugins = ("tests.test_rbac_project_roles",)

PROJECT = "test-project-123"
USER_PATH = "/api/v1/instances/inst-1/name"
ADMIN_PATH = "/api/v1/admin/instances/inst-1/name"


def server(*, name="old-name", project_id=PROJECT, status="ACTIVE", id="inst-1"):
    return InstanceInfo(id=id, name=name, project_id=project_id, status=status)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ACTIVE", "SHUTOFF", "ERROR", "SHELVED_OFFLOADED"])
async def test_user_rename_confirms_metadata_without_power_requirement(client, mock_conn, status):
    with (
        patch.object(nova, "get_server", return_value=server(status=status)),
        patch.object(nova, "rename_server", return_value=server(name="new-name", status=status)) as rename,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await client.put(USER_PATH, json={"name": "  new name  "})
    assert response.status_code == 200
    assert response.json() == {"id": "inst-1", "name": "new-name", "project_id": PROJECT}
    rename.assert_called_once_with(mock_conn, "inst-1", "new-name")
    assert {call.args[0] for call in invalidate.await_args_list} == {
        "afterglow:nova:*:instance:inst-1",
        f"afterglow:nova:{PROJECT}:instances*",
        "afterglow:admin:instances*",
        "afterglow:admin:topology",
    }
    mock_conn.compute.stop_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", [None, "", "foreign-project"])
async def test_user_rename_requires_actual_project_ownership(client, project_id):
    with (
        patch.object(nova, "get_server", return_value=server(project_id=project_id)),
        patch.object(nova, "rename_server") as rename,
    ):
        response = await client.put(USER_PATH, json={"name": "new-name"})
    assert response.status_code == 404
    rename.assert_not_called()


@pytest.mark.asyncio
async def test_system_admin_user_route_does_not_bypass_project_ownership(admin_client):
    with (
        patch.object(nova, "get_server", return_value=server(project_id="foreign-project")),
        patch.object(nova, "rename_server") as rename,
    ):
        response = await admin_client.put(USER_PATH, json={"name": "new-name"})
    assert response.status_code == 404
    rename.assert_not_called()


@pytest.mark.asyncio
async def test_reader_rename_is_denied_before_resource_read(reader_client):
    with patch.object(nova, "get_server") as read, patch.object(nova, "rename_server") as rename:
        response = await reader_client.put(USER_PATH, json={"name": "new-name"})
    assert response.status_code == 403
    read.assert_not_called()
    rename.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [USER_PATH, ADMIN_PATH])
@pytest.mark.parametrize("current_name", ["old-name", "web server"])
async def test_rename_unchanged_name_is_authorized_noop(admin_client, path, current_name):
    with (
        patch.object(nova, "get_server", return_value=server(name=current_name)),
        patch.object(nova, "rename_server") as rename,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await admin_client.put(path, json={"name": f"  {current_name}  "})
    assert response.status_code == 200
    assert response.json()["name"] == current_name
    rename.assert_not_called()
    invalidate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["", "  ", "-invalid", "a" * 64, "bad\nname", "bad/name"])
async def test_rename_rejects_invalid_names_before_provider_write(client, name):
    with (
        patch.object(nova, "get_server", return_value=server()),
        patch.object(nova, "rename_server") as rename,
    ):
        response = await client.put(USER_PATH, json={"name": name})
    assert response.status_code == 422
    rename.assert_not_called()


@pytest.mark.asyncio
async def test_admin_rename_uses_caller_connection_and_actual_foreign_project(admin_client, mock_conn):
    with (
        patch.object(nova, "get_server", return_value=server(project_id="target-project")),
        patch.object(
            nova, "rename_server", return_value=server(name="new-name", project_id="target-project")
        ) as rename,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        response = await admin_client.put(ADMIN_PATH, json={"name": "new-name"})
    assert response.status_code == 200
    assert response.json()["project_id"] == "target-project"
    rename.assert_called_once_with(mock_conn, "inst-1", "new-name")
    assert "afterglow:nova:target-project:instances*" in {call.args[0] for call in invalidate.await_args_list}


@pytest.mark.asyncio
async def test_admin_rename_requires_fresh_admin_authority(non_admin_client):
    with patch.object(nova, "get_server") as read, patch.object(nova, "rename_server") as rename:
        response = await non_admin_client.put(ADMIN_PATH, json={"name": "new-name"})
    assert response.status_code == 403
    read.assert_not_called()
    rename.assert_not_called()


@pytest.mark.asyncio
async def test_admin_rename_denies_missing_target_project(admin_client):
    with (
        patch.object(nova, "get_server", return_value=server(project_id=None)),
        patch.object(nova, "rename_server") as rename,
    ):
        response = await admin_client.put(ADMIN_PATH, json={"name": "new-name"})
    assert response.status_code == 409
    rename.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("path", [USER_PATH, ADMIN_PATH])
async def test_rename_failure_never_reports_changed_name(admin_client, path):
    with (
        patch.object(nova, "get_server", return_value=server()),
        patch.object(nova, "rename_server", side_effect=RuntimeError("provider failure")) as rename,
    ):
        response = await admin_client.put(path, json={"name": "new-name"})
    assert response.status_code == 400
    assert "name" not in response.json()
    assert rename.call_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [{"name": "old-name"}, {"id": "other"}, {"project_id": "other"}])
async def test_rename_mismatched_provider_metadata_is_not_accepted(client, changed):
    with (
        patch.object(nova, "get_server", return_value=server()),
        patch.object(nova, "rename_server", return_value=server(name="new-name").model_copy(update=changed)),
    ):
        response = await client.put(USER_PATH, json={"name": "new-name"})
    assert response.status_code == 400


def test_sdk_rename_rejects_unconfirmed_metadata(mock_conn):
    mock_conn.compute.get_server.return_value = Server.new(
        id="inst-1", name="old-name", status="ACTIVE", project_id=PROJECT
    )
    with pytest.raises(RuntimeError, match="did not confirm"):
        nova.rename_server(mock_conn, "inst-1", "new-name")
    mock_conn.compute.update_server.assert_called_once_with("inst-1", name="new-name")
