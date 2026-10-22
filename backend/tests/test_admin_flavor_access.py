"""Native flavor visibility and quota updates are independent authorities."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_quota_access_mode_and_reconcile_routes_are_removed(admin_client, mock_conn):
    mode = await admin_client.put("/api/v1/admin/flavors/fl-gpu/access-mode", json={"mode": "gpu_quota"})
    reconcile = await admin_client.post(
        "/api/v1/admin/flavors/access-reconcile", json={"project_id": "proj-1", "apply": True}
    )
    assert mode.status_code == 404
    assert reconcile.status_code in (404, 405)
    mock_conn.session.post.assert_not_called()
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()


@pytest.mark.asyncio
async def test_set_flavor_frontend_visibility_and_admin_listing(admin_client, mock_conn):
    flavor = SimpleNamespace(
        id="fl-service",
        name="amphora",
        vcpus=1,
        ram=1024,
        disk=5,
        is_public=True,
        description=None,
        extra_specs={},
    )
    hidden = SimpleNamespace(
        id="fl-hidden",
        name="manila-service-flavor",
        vcpus=1,
        ram=128,
        disk=0,
        is_public=True,
        description=None,
        extra_specs={"afterglow:frontend_visible": "false"},
    )
    mock_conn.compute.get_flavor.return_value = flavor
    with patch("app.api.identity.admin_flavors.invalidate", AsyncMock()) as mock_invalidate:
        resp = await admin_client.put(
            "/api/v1/admin/flavors/fl-service/frontend-visibility",
            json={"visible": False},
        )

    assert resp.status_code == 200
    assert resp.json() == {"flavor_id": "fl-service", "frontend_visible": False}
    mock_conn.compute.create_flavor_extra_specs.assert_called_once_with(
        "fl-service",
        {"afterglow:frontend_visible": "false"},
    )
    mock_invalidate.assert_awaited_once_with("afterglow:nova:*:flavors")

    mock_conn.compute.flavors.return_value = [flavor, hidden]
    listed = await admin_client.get("/api/v1/admin/flavors?limit=999")
    assert listed.status_code == 200
    assert [item["frontend_visible"] for item in listed.json()["items"]] == [True, False]


@pytest.mark.asyncio
async def test_update_compute_and_gpu_quotas_never_mutates_native_flavor_grants(admin_client, mock_conn):

    mock_conn.compute.update_quota_set = MagicMock()
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-1", domain_id="default")
    with (
        patch("app.services.gpu_quota.set_project_gpu_quota", AsyncMock()) as mock_set_gpu,
        patch("app.api.identity.admin_identity.invalidate", AsyncMock()),
        patch(
            "app.services.domain_quotas.update_project",
            AsyncMock(return_value={"status": "updated", "operation_id": "native-journal"}),
        ) as native_quota,
    ):
        resp = await admin_client.put(
            "/api/v1/admin/compute-policy/proj-1?domain_id=default",
            json={
                "instances": 10,
                "cores": 20,
                "ram": 40960,
                "gpu_quotas": {"RTX3090": 2},
            },
        )

    assert resp.status_code == 200
    native_quota.assert_awaited_once_with(mock_conn, "proj-1", {"instances": 10, "cores": 20, "ram": 40960})
    mock_conn.compute.update_quota_set.assert_not_called()
    mock_set_gpu.assert_awaited_once_with(mock_conn, "proj-1", "RTX3090", 2)
    mock_conn.session.post.assert_not_called()
    mock_conn.compute.add_flavor_access.assert_not_called()
    mock_conn.compute.remove_flavor_access.assert_not_called()
    assert "access_reconcile" not in resp.json()


@pytest.mark.asyncio
async def test_compute_policy_stops_before_gpu_after_uncertain_native_quota(admin_client, mock_conn):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-1", domain_id="default")
    operation = {
        "status": "unknown",
        "operation_id": "pending-native",
        "errors": {"compute": "native_readback_unavailable"},
    }
    with (
        patch("app.services.domain_quotas.update_project", AsyncMock(return_value=operation)),
        patch("app.services.gpu_quota.set_project_gpu_quota", AsyncMock()) as gpu,
    ):
        response = await admin_client.put(
            "/api/v1/admin/compute-policy/proj-1?domain_id=default",
            json={"instances": 10, "gpu_quotas": {"RTX3090": 2}},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["native_quotas"] == operation
    gpu.assert_not_awaited()
    mock_conn.session.post.assert_not_called()


@pytest.mark.asyncio
async def test_compute_policy_cannot_bypass_domain_budget(admin_client, mock_conn):
    from fastapi import HTTPException

    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-1", domain_id="default")
    with (
        patch(
            "app.services.domain_quotas.update_project",
            AsyncMock(side_effect=HTTPException(409, "quota_budget_exceeded:instances")),
        ),
        patch("app.services.gpu_quota.set_project_gpu_quota", AsyncMock()) as gpu,
    ):
        response = await admin_client.put(
            "/api/v1/admin/compute-policy/proj-1?domain_id=default",
            json={"instances": 10, "gpu_quotas": {"RTX3090": 2}},
        )
    assert response.status_code == 409
    gpu.assert_not_awaited()
    mock_conn.compute.update_quota_set.assert_not_called()


@pytest.mark.asyncio
async def test_native_access_list_disambiguates_domain_and_project_uuid(admin_client, mock_conn):
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "flavor_access": [{"flavor_id": "fl", "tenant_id": "project-a"}, {"flavor_id": "fl", "tenant_id": "project-b"}]
    }
    mock_conn.session.get.return_value = response
    mock_conn.identity.get_project.side_effect = lambda pid: SimpleNamespace(
        id=pid, name="Same project", domain_id="domain-a" if pid == "project-a" else "domain-b"
    )
    mock_conn.identity.get_domain.side_effect = lambda did: SimpleNamespace(id=did, name="Same domain")
    result = await admin_client.get("/api/v1/admin/flavors/fl/access")
    assert result.status_code == 200
    assert [(row["domain_id"], row["project_id"]) for row in result.json()] == [
        ("domain-a", "project-a"),
        ("domain-b", "project-b"),
    ]


@pytest.mark.asyncio
async def test_native_access_lookup_failure_is_not_empty_success(admin_client, mock_conn):
    mock_conn.session.get.side_effect = RuntimeError("native unavailable")
    response = await admin_client.get("/api/v1/admin/flavors/fl/access")
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 2])
async def test_gpu_quota_only_update_preserves_native_access_in_both_directions(admin_client, mock_conn, limit):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-1", domain_id="default")
    with patch("app.services.gpu_quota.set_project_gpu_quota", AsyncMock()) as setter:
        response = await admin_client.put(
            "/api/v1/admin/compute-policy/proj-1?domain_id=default", json={"gpu_quotas": {"RTX3090": limit}}
        )
    assert response.status_code == 200
    setter.assert_awaited_once_with(mock_conn, "proj-1", "RTX3090", limit)
    mock_conn.session.post.assert_not_called()
    mock_conn.compute.get_flavor_access.assert_not_called()
    mock_conn.compute.flavors.assert_not_called()
    mock_conn.compute.add_flavor_access.assert_not_called()
    mock_conn.compute.remove_flavor_access.assert_not_called()
