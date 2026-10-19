"""Tests for quota-managed flavor access reconciliation and unified compute policy."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_set_flavor_access_mode_validations(admin_client, mock_conn):
    public_flavor = MagicMock(id="fl-pub", is_public=True, extra_specs={})
    non_gpu_flavor = MagicMock(id="fl-cpu", is_public=False, extra_specs={})
    gpu_flavor = MagicMock(
        id="fl-gpu",
        is_public=False,
        extra_specs={"pci_passthrough:alias": "RTX3090:1"},
    )

    # Public flavor rejects gpu_quota mode
    mock_conn.compute.get_flavor.return_value = public_flavor
    resp = await admin_client.put(
        "/api/v1/admin/flavors/fl-pub/access-mode",
        json={"mode": "gpu_quota"},
    )
    assert resp.status_code == 409
    assert "Public" in resp.json()["detail"]

    # Flavor without GPU specs rejects gpu_quota mode
    mock_conn.compute.get_flavor.return_value = non_gpu_flavor
    resp = await admin_client.put(
        "/api/v1/admin/flavors/fl-cpu/access-mode",
        json={"mode": "gpu_quota"},
    )
    assert resp.status_code == 409
    assert "GPU" in resp.json()["detail"]

    # Private GPU flavor succeeds
    mock_conn.compute.get_flavor.return_value = gpu_flavor
    resp = await admin_client.put(
        "/api/v1/admin/flavors/fl-gpu/access-mode",
        json={"mode": "gpu_quota"},
    )
    assert resp.status_code == 200
    assert resp.json()["mode"] == "gpu_quota"


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
async def test_flavor_access_reconcile_preview_and_apply(admin_client, mock_conn):
    managed_flavor = MagicMock(
        id="fl-gpu-1",
        name="gpu.3090",
        vcpus=8,
        ram=16384,
        disk=40,
        is_public=False,
        description=None,
        extra_specs={"afterglow:access_mode": "gpu_quota", "pci_passthrough:alias": "RTX3090:1"},
    )

    mock_conn.compute.flavors.return_value = [managed_flavor]
    mock_conn.compute.get_endpoint.return_value = "http://nova"
    access_resp = MagicMock()
    access_resp.json.return_value = {"flavor_access": []}
    access_resp.raise_for_status = MagicMock()
    mock_conn.session.get.return_value = access_resp

    # Dry-run preview: project has RTX3090 limit=2, currently has no access -> action is 'add'
    with patch("app.services.gpu_quota.get_effective_gpu_quotas", return_value={"RTX3090": 2}):
        resp = await admin_client.post(
            "/api/v1/admin/flavors/access-reconcile",
            json={"project_id": "proj-1", "apply": False},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["applied"] is False
    assert len(data["operations"]) == 1
    op = data["operations"][0]
    assert op["flavor_id"] == "fl-gpu-1"
    assert op["desired_access"] is True
    assert op["current_access"] is False
    assert op["action"] == "add"
    assert data["enforcement_scope"] == "afterglow_admissions_only"

    # Apply: calls Nova addTenantAccess
    post_resp = MagicMock()
    post_resp.raise_for_status = MagicMock()
    mock_conn.session.post.return_value = post_resp

    with (
        patch("app.services.gpu_quota.get_effective_gpu_quotas", return_value={"RTX3090": 2}),
        patch("app.api.identity.admin_flavors.invalidate", AsyncMock()) as mock_inv,
    ):
        resp = await admin_client.post(
            "/api/v1/admin/flavors/access-reconcile",
            json={"project_id": "proj-1", "apply": True},
        )
    assert resp.status_code == 200
    assert resp.json()["applied"] is True
    mock_conn.session.post.assert_called_once_with(
        "http://nova/flavors/fl-gpu-1/action",
        json={"addTenantAccess": {"tenant": "proj-1"}},
    )
    mock_inv.assert_awaited()


@pytest.mark.asyncio
async def test_update_project_compute_policy_coordinates_all_authorities(admin_client, mock_conn):
    reconcile_result = {
        "project_id": "proj-1",
        "applied": True,
        "status": "ok",
        "operations": [],
        "errors": [],
        "enforcement_scope": "afterglow_admissions_only",
    }

    mock_conn.compute.update_quota_set = MagicMock()
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.get_project.return_value = SimpleNamespace(id="proj-1", domain_id="default")
    with (
        patch("app.services.gpu_quota.set_project_gpu_quota", AsyncMock()) as mock_set_gpu,
        patch(
            "app.api.identity.admin_flavors.reconcile_quota_managed_flavor_access",
            AsyncMock(return_value=reconcile_result),
        ) as mock_reconcile,
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
                "reconcile_flavor_access": True,
            },
        )

    assert resp.status_code == 200
    native_quota.assert_awaited_once_with(mock_conn, "proj-1", {"instances": 10, "cores": 20, "ram": 40960})
    mock_conn.compute.update_quota_set.assert_not_called()
    mock_set_gpu.assert_awaited_once_with(mock_conn, "proj-1", "RTX3090", 2)
    mock_reconcile.assert_awaited_once()


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
        patch("app.api.identity.admin_flavors.reconcile_quota_managed_flavor_access", AsyncMock()) as reconcile,
    ):
        response = await admin_client.put(
            "/api/v1/admin/compute-policy/proj-1?domain_id=default",
            json={"instances": 10, "gpu_quotas": {"RTX3090": 2}},
        )
    assert response.status_code == 200
    assert response.json()["status"] == "partial"
    assert response.json()["native_quotas"] == operation
    gpu.assert_not_awaited()
    reconcile.assert_not_awaited()


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
