from types import SimpleNamespace

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
