from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import nova
from app.services.nova import _server_to_info


def test_server_info_ignores_none_union_resource_placeholders():
    server = SimpleNamespace(
        id="server-1",
        name="example",
        status="ACTIVE",
        addresses={},
        metadata={
            "union_strategy": "prebuilt",
            "union_share_ids": "none",
            "union_upper_volume_id": "none",
        },
        image={"id": "image-1"},
        flavor={"id": "flavor-1"},
        created_at=None,
        compute_host=None,
        key_name=None,
        user_id="user-1",
        project_id="project-1",
        tenant_id=None,
    )

    info = _server_to_info(server)

    assert info.union_share_ids == []
    assert info.union_upper_volume_id is None


def test_server_info_defaults_absent_union_metadata_for_layerless_instance():
    server = SimpleNamespace(
        id="server-2",
        name="layerless",
        status="ACTIVE",
        addresses={},
        metadata={"scheduling": "standard"},
        image={"id": "image-1"},
        flavor={"id": "flavor-1"},
        created_at=None,
        compute_host=None,
        key_name=None,
        user_id="user-1",
        project_id="project-1",
        tenant_id=None,
    )

    info = _server_to_info(server)

    assert info.union_libraries == []
    assert info.union_strategy is None
    assert info.union_share_ids == []
    assert info.union_upper_volume_id is None


def _ssh_server(metadata, key_name=None):
    return SimpleNamespace(
        id="ssh-server",
        name="github-vm",
        status="ACTIVE",
        addresses={},
        metadata=metadata,
        image={"id": "image-1"},
        flavor={"id": "flavor-1"},
        created_at=None,
        compute_host=None,
        key_name=key_name,
        user_id="test-user-123",
        project_id="test-project-123",
        # Deliberately ignored: legacy servers must not infer GitHub access.
        user_data="#cloud-config\nssh_import_id:\n  - gh:LegacyAccount\n",
    )


@pytest.mark.parametrize(
    ("metadata", "key_name", "expected_mode", "expected_login"),
    [
        (
            {"afterglow_ssh_access_mode": "github", "afterglow_github_login": "OctoCat"},
            None,
            "github",
            "OctoCat",
        ),
        ({}, "existing-keypair", None, None),
        ({}, None, None, None),
        ({"afterglow_github_login": "OctoCat"}, "existing-keypair", None, "OctoCat"),
        ({"afterglow_ssh_access_mode": "github"}, "existing-keypair", "github", None),
        (
            {"afterglow_ssh_access_mode": "github", "afterglow_github_login": ""},
            None,
            "github",
            None,
        ),
        ({"afterglow_ssh_access_mode": "unknown"}, "existing-keypair", None, None),
    ],
)
@pytest.mark.asyncio
async def test_instance_list_and_detail_project_declared_github_access(
    client, mock_conn, metadata, key_name, expected_mode, expected_login
):
    server = _ssh_server(metadata, key_name)
    mock_conn.compute.servers.return_value = [server]
    mock_conn.compute.get_server.return_value = server

    # Exercise the real SDK-resource projection through both API consumers.
    with (
        patch("app.api.compute.instances.nova.list_flavors", return_value=[]),
        patch("app.api.compute.instances.glance.list_images", return_value=[]),
    ):
        listed = await client.get("/api/v1/instances")
        detailed = await client.get("/api/v1/instances/ssh-server")

    assert listed.status_code == detailed.status_code == 200
    for info in (listed.json()[0], detailed.json()):
        assert info["ssh_access_mode"] == expected_mode
        assert info["github_login"] == expected_login
        assert info["key_name"] == key_name
        assert info["metadata"] == metadata


def test_github_projection_preserves_owner_health_and_library_metadata():
    metadata = {
        "afterglow_ssh_access_mode": "github",
        "afterglow_github_login": "OctoCat",
        "union_health_id": "health-1",
        "HA_Enabled": "True",
        "union_libraries": "python311,pytorch",
        "union_strategy": "prebuilt",
        "union_share_ids": "share-1,share-2",
        "union_upper_volume_id": "upper-1",
        "scheduling": "ha",
    }
    info = nova._server_to_info(_ssh_server(metadata))

    assert info.ssh_access_mode == "github"
    assert info.github_login == "OctoCat"
    assert info.metadata == metadata
    assert info.user_id == "test-user-123"
    assert info.project_id == "test-project-123"
    assert info.union_libraries == ["python311", "pytorch"]
    assert info.union_strategy == "prebuilt"
    assert info.union_share_ids == ["share-1", "share-2"]
    assert info.union_upper_volume_id == "upper-1"
    assert info.scheduling == "ha"
