from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_collect_instance_data_clears_gpu_map_for_shelved_offloaded():
    from app.services.openstack_inventory import collect_instance_data

    flavor = SimpleNamespace(
        id="flavor-gpu",
        name="gpu.3090_8c_16g",
        vcpus=8,
        ram=16384,
        extra_specs={"pci_passthrough:alias": "nvidia-rtx3090:1"},
        disk=100,
        is_public=True,
    )
    active_server = SimpleNamespace(
        id="inst-active",
        name="active-gpu",
        status="ACTIVE",
        flavor={"id": "flavor-gpu", "original_name": "gpu.3090_8c_16g"},
        addresses={},
        created_at="2026-07-01 00:00:00",
        compute_host="compute-1",
        user_id="user-1",
        project_id="project-1",
    )
    shelved_server = SimpleNamespace(
        id="inst-shelved",
        name="shelved-gpu",
        status="SHELVED_OFFLOADED",
        flavor={"id": "flavor-gpu", "original_name": "gpu.3090_8c_16g"},
        addresses={},
        created_at="2026-07-01 00:00:00",
        compute_host="compute-1",
        user_id="user-1",
        project_id="project-1",
    )

    conn = SimpleNamespace(
        compute=SimpleNamespace(
            flavors=MagicMock(return_value=[flavor]),
            servers=MagicMock(return_value=[active_server, shelved_server]),
        ),
        identity=SimpleNamespace(
            projects=MagicMock(return_value=[SimpleNamespace(id="project-1", name="project")]),
            users=MagicMock(return_value=[SimpleNamespace(id="user-1", name="user", email="user@example.com")]),
        ),
        close=MagicMock(),
    )
    settings = SimpleNamespace(
        os_auth_url="https://openstack.example/v3",
        os_username="user",
        os_password="password",
        os_project_name="service",
        os_user_domain_name="Default",
        os_project_domain_name="Default",
        ssl_verify=True,
    )

    with (
        patch("app.services.native_transport.connect", return_value=conn),
        patch("app.config.get_settings", return_value=settings),
        patch(
            "app.services.gpu_inventory.build_alias_to_device_name_map",
            return_value={"nvidia-rtx3090": "RTX 3090"},
        ),
    ):
        rows = await collect_instance_data(
            email_to_page_id={"user@example.com": "user-page"},
            host_to_page_id={"compute-1": "host-page"},
            gpu_name_to_page_id={"RTX 3090": "gpu-page"},
        )

    active = next(row for row in rows if row["instance_id"] == "inst-active")
    shelved = next(row for row in rows if row["instance_id"] == "inst-shelved")

    assert active["gpu_count"] == 1
    assert active["gpu_spec_page_id"] == "gpu-page"
    assert active["hypervisor_page_id"] == "host-page"

    assert shelved["gpu_count"] == 0
    assert shelved["gpu_spec_page_id"] == ""
    assert shelved["hypervisor_page_id"] == ""
    assert shelved["status"] == "SHELVED_OFFLOADED"
    assert shelved["gpu_name"] == "RTX 3090"


@pytest.mark.asyncio
async def test_collect_instance_data_resolves_named_server_flavor_with_detailed_extra_specs():
    from app.services.openstack_inventory import collect_instance_data

    listed_flavor = SimpleNamespace(
        id="flavor-uuid",
        name="accelerator.large",
        vcpus=8,
        ram=32768,
        disk=100,
        is_public=True,
        extra_specs={},
    )
    detailed_flavor = SimpleNamespace(
        extra_specs={"pci_passthrough:alias": "RTX-3060:2,GA104-audio:2"},
    )
    server = SimpleNamespace(
        id="inst-3060",
        name="alias-vm",
        status="ACTIVE",
        flavor={"original_name": "accelerator.large"},
        addresses={},
        created_at="2026-07-01 00:00:00",
        compute_host="compute-1",
        user_id="user-1",
        project_id="project-1",
    )
    conn = SimpleNamespace(
        compute=SimpleNamespace(
            flavors=MagicMock(return_value=[listed_flavor]),
            fetch_flavor_extra_specs=MagicMock(return_value=detailed_flavor),
            servers=MagicMock(return_value=[server]),
        ),
        identity=SimpleNamespace(
            projects=MagicMock(return_value=[SimpleNamespace(id="project-1", name="project")]),
            users=MagicMock(return_value=[SimpleNamespace(id="user-1", name="user", email="user@example.com")]),
        ),
        close=MagicMock(),
    )
    settings = SimpleNamespace(
        os_auth_url="https://openstack.example/v3",
        os_username="user",
        os_password="password",
        os_project_name="service",
        os_user_domain_name="Default",
        os_project_domain_name="Default",
        ssl_verify=True,
    )

    with (
        patch("app.services.native_transport.connect", return_value=conn),
        patch("app.config.get_settings", return_value=settings),
        patch(
            "app.services.gpu_inventory.build_alias_to_device_name_map",
            return_value={"RTX-3060": "RTX 3060"},
        ),
    ):
        rows = await collect_instance_data(gpu_name_to_page_id={"RTX 3060": "gpu-page"})

    assert rows[0]["gpu_name"] == "RTX 3060"
    assert rows[0]["gpu_count"] == 2
    assert rows[0]["gpu_spec_page_id"] == "gpu-page"
