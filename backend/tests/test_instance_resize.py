"""Owned-instance resize discovery and mutation contracts."""

from unittest.mock import AsyncMock, patch

import pytest

from app.models.compute import FlavorInfo, InstanceInfo

pytest_plugins = ("tests.test_rbac_project_roles",)

BASE = "/api/v1/instances/inst-1"
PROJECT = "test-project-123"


def _server(*, status="ACTIVE", project_id=PROJECT, flavor_id="small", image_id="image-1"):
    return InstanceInfo(
        id="inst-1", name="vm", status=status, project_id=project_id, flavor_id=flavor_id, image_id=image_id
    )


def _flavors():
    return [
        FlavorInfo(id="small", name="small", vcpus=2, ram=2048, disk=20),
        FlavorInfo(id="large", name="large", vcpus=4, ram=4096, disk=20),
        FlavorInfo(id="shrinking", name="shrinking", vcpus=4, ram=4096, disk=10),
        FlavorInfo(
            id="hidden",
            name="hidden",
            vcpus=4,
            ram=4096,
            disk=20,
            extra_specs={"afterglow:frontend_visible": "false"},
        ),
    ]


def _quota(*, used_cores=8, limit_cores=10):
    return {
        "instances": {"limit": 1, "in_use": 1},
        "cores": {"limit": limit_cores, "in_use": used_cores},
        "ram": {"limit": 4096, "in_use": 2048},
    }


@pytest.mark.asyncio
async def test_resize_flavors_reports_delta_and_excludes_hidden_for_member(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server()),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
    ):
        resp = await client.get(f"{BASE}/resize-flavors")

    assert resp.status_code == 200
    flavors = {item["id"]: item for item in resp.json()}
    assert set(flavors) == {"small", "large", "shrinking"}
    assert flavors["large"]["eligibility"]["selectable"] is True
    assert flavors["large"]["eligibility"]["requirements"] == {
        "instances": 0,
        "cores": 2,
        "ram_mb": 2048,
        "gpus": {},
    }
    assert [b["code"] for b in flavors["small"]["eligibility"]["blockers"]] == ["same_flavor"]
    assert [b["code"] for b in flavors["shrinking"]["eligibility"]["blockers"]] == ["disk_shrink"]


@pytest.mark.asyncio
async def test_volume_backed_resize_allows_smaller_flavor_disk(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(image_id=None)),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        discovery = await client.get(f"{BASE}/resize-flavors")
        candidate = next(flavor for flavor in discovery.json() if flavor["id"] == "shrinking")
        accepted = await client.post(f"{BASE}/resize", json={"flavor_id": "shrinking"})
    assert candidate["eligibility"]["selectable"] is True
    assert accepted.status_code == 200
    resize.assert_called_once()


@pytest.mark.asyncio
async def test_name_only_current_flavor_is_resolved_for_incremental_demand(client):
    server = _server(flavor_id=None).model_copy(update={"flavor_name": "small"})
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=server),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
    ):
        resp = await client.get(f"{BASE}/resize-flavors")
    assert resp.status_code == 200
    large = next(item for item in resp.json() if item["id"] == "large")
    assert large["eligibility"]["requirements"]["cores"] == 2


@pytest.mark.asyncio
async def test_gpu_resize_uses_additional_gpu_demand_for_discovery_and_submission(client):
    current = FlavorInfo(
        id="gpu-small",
        name="gpu.small",
        vcpus=2,
        ram=2048,
        disk=40,
        extra_specs={"pci_passthrough:alias": "RTX-3090:1"},
    )
    target = current.model_copy(
        update={
            "id": "gpu-large",
            "name": "gpu.large",
            "extra_specs": {"pci_passthrough:alias": "RTX-3090:2"},
        }
    )
    status = [{"gpu_type": "RTX3090", "limit": 2, "in_use": 1, "available": 1}]
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(flavor_id="gpu-small")),
        patch("app.api.compute.instances.nova.list_flavors", return_value=[current, target]),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
        patch(
            "app.services.flavor_eligibility.gpu_quota.get_effective_gpu_quota_status",
            new_callable=AsyncMock,
        ) as gpu_quota,
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        gpu_quota.return_value = status
        discovery = await client.get(f"{BASE}/resize-flavors")
        result = next(item for item in discovery.json() if item["id"] == "gpu-large")
        assert result["eligibility"]["selectable"] is True
        assert result["eligibility"]["requirements"]["gpus"] == {"RTX3090": 1}
        status[0]["available"] = 0
        denied = await client.post(f"{BASE}/resize", json={"flavor_id": "gpu-large"})
    assert denied.status_code == 409
    assert "gpu_insufficient" in denied.json()["detail"]
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_resize_rechecks_quota_at_submission_and_invalidates_on_success(client):
    quota = _quota()
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server()),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", side_effect=lambda *_: quota),
        patch("app.api.compute.instances.nova.resize_server") as resize,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
        patch("app.api.compute.instances.cache_invalidation.invalidate_mutation_count", new_callable=AsyncMock),
    ):
        discovery = await client.get(f"{BASE}/resize-flavors")
        assert {f["id"]: f for f in discovery.json()}["large"]["eligibility"]["selectable"] is True
        quota = _quota(used_cores=9)
        denied = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
        assert denied.status_code == 409
        assert "cores_insufficient" in denied.json()["detail"]
        resize.assert_not_called()
        quota = _quota()
        accepted = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
        assert accepted.status_code == 200
        assert accepted.json() == {"status": "resizing"}
        assert resize.call_args.args[1:] == ("inst-1", "large")
        assert resize.call_args.args[0]._afterglow_project_id == PROJECT
        assert {call.args[0] for call in invalidate.await_args_list} == {
            f"afterglow:nova:{PROJECT}:instance:inst-1",
            f"afterglow:nova:{PROJECT}:instances",
        }


@pytest.mark.asyncio
async def test_stopped_instance_can_resize(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(status="SHUTOFF")),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        resp = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
    assert resp.status_code == 200
    resize.assert_called_once()


@pytest.mark.asyncio
async def test_resize_flavors_rejects_nonresizable_instance(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(status="ERROR")),
        patch("app.api.compute.instances.nova.list_flavors") as flavors,
    ):
        resp = await client.get(f"{BASE}/resize-flavors")
    assert resp.status_code == 409
    flavors.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["foreign", None])
@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("get", "resize-flavors", None),
        ("post", "resize", {"flavor_id": "large"}),
        ("post", "confirm-resize", None),
        ("post", "revert-resize", None),
    ],
)
async def test_resize_routes_reject_foreign_or_missing_owner(client, method, suffix, body, project_id):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(project_id=project_id)),
        patch("app.api.compute.instances.nova.list_flavors") as flavors,
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        resp = await getattr(client, method)(f"{BASE}/{suffix}", **({"json": body} if body else {}))
    assert resp.status_code == 404
    flavors.assert_not_called()
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_reader_can_discover_owned_resize_targets(reader_client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server()),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()),
    ):
        resp = await reader_client.get(f"{BASE}/resize-flavors")
    assert resp.status_code == 200
    assert next(item for item in resp.json() if item["id"] == "large")["eligibility"]["selectable"]


@pytest.mark.asyncio
async def test_admin_owner_bypass_uses_instance_project_quota(admin_client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(project_id="foreign")),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", return_value=_quota()) as quota,
        patch("app.api.compute.instances.nova.resize_server") as resize,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        resp = await admin_client.post(f"{BASE}/resize", json={"flavor_id": "large"})
    assert resp.status_code == 200
    assert quota.call_args.args[1] == "foreign"
    resize.assert_called_once()
    assert all(":foreign:" in call.args[0] for call in invalidate.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix,body",
    [
        ("resize", {"flavor_id": "large"}),
        ("confirm-resize", None),
        ("revert-resize", None),
    ],
)
async def test_reader_cannot_mutate_resize(reader_client, suffix, body):
    with patch("app.api.compute.instances.nova.get_server") as get_server:
        resp = await reader_client.post(f"{BASE}/{suffix}", **({"json": body} if body else {}))
    assert resp.status_code == 403
    get_server.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "flavor_id,status,expected",
    [
        ("small", "ACTIVE", 409),
        ("shrinking", "ACTIVE", 409),
        ("hidden", "ACTIVE", 400),
        ("missing", "ACTIVE", 400),
        ("large", "ERROR", 409),
        ("large", "VERIFY_RESIZE", 409),
    ],
)
async def test_resize_rejects_invalid_target_or_status(client, flavor_id, status, expected):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(status=status)),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        resp = await client.post(f"{BASE}/resize", json={"flavor_id": flavor_id})
    assert resp.status_code == expected
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_resize_fails_closed_when_current_flavor_cannot_be_resolved(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(flavor_id="deleted")),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.api.compute.instances.nova.resize_server") as resize,
    ):
        discovery = await client.get(f"{BASE}/resize-flavors")
        submission = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
    assert discovery.status_code == submission.status_code == 409
    resize.assert_not_called()


@pytest.mark.asyncio
async def test_resize_quota_unavailable_and_nova_failure_do_not_invalidate(client):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server()),
        patch("app.api.compute.instances.nova.list_flavors", return_value=_flavors()),
        patch("app.services.flavor_eligibility.nova.get_project_quota", side_effect=RuntimeError("offline")) as quota,
        patch("app.api.compute.instances.nova.resize_server", side_effect=RuntimeError("nova failed")) as resize,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        unavailable = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
        assert unavailable.status_code == 503
        resize.assert_not_called()
        quota.side_effect = None
        quota.return_value = _quota()
        failure = await client.post(f"{BASE}/resize", json={"flavor_id": "large"})
    assert failure.status_code == 400
    invalidate.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix,operation,expected",
    [
        ("confirm-resize", "confirm_resize_server", "confirmed"),
        ("revert-resize", "revert_resize_server", "reverting"),
    ],
)
async def test_finish_resize_requires_verify_and_invalidates(client, suffix, operation, expected):
    with (
        patch("app.api.compute.instances.nova.get_server", side_effect=[_server(), _server(status="VERIFY_RESIZE")]),
        patch(f"app.api.compute.instances.nova.{operation}") as nova_action,
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        denied = await client.post(f"{BASE}/{suffix}")
        assert denied.status_code == 409
        nova_action.assert_not_called()
        accepted = await client.post(f"{BASE}/{suffix}")
    assert accepted.status_code == 200
    assert accepted.json() == {"status": expected}
    nova_action.assert_called_once()
    assert {call.args[0] for call in invalidate.await_args_list} == {
        f"afterglow:nova:{PROJECT}:instance:inst-1",
        f"afterglow:nova:{PROJECT}:instances",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "suffix,operation",
    [
        ("confirm-resize", "confirm_resize_server"),
        ("revert-resize", "revert_resize_server"),
    ],
)
async def test_finish_resize_nova_failure_does_not_invalidate(client, suffix, operation):
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=_server(status="VERIFY_RESIZE")),
        patch(f"app.api.compute.instances.nova.{operation}", side_effect=RuntimeError("nova failed")),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock) as invalidate,
    ):
        resp = await client.post(f"{BASE}/{suffix}")
    assert resp.status_code == 400
    invalidate.assert_not_awaited()
