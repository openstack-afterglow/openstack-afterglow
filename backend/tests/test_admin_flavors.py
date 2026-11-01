"""Administrator flavor routes and additive native usage annotations."""

import copy
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
import requests
from keystoneauth1 import noauth
from keystoneauth1 import session as ks_session
from openstack import connection

from app.api.identity import admin_flavors
from app.services.instance_usage import requires_schedule


@pytest.mark.asyncio
async def test_list_admin_flavors_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/flavors")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_admin_flavors_allowed(admin_client, mock_conn):
    mock_conn.compute.flavors.return_value = iter([])
    resp = await admin_client.get("/api/v1/admin/flavors")
    assert resp.status_code != 403


@pytest.mark.asyncio
async def test_create_flavor_requires_admin(non_admin_client):
    resp = await non_admin_client.post(
        "/api/v1/admin/flavors", json={"name": "m1.test", "vcpus": 1, "ram": 512, "disk": 10}
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_flavor_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/flavors/flavor-1")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_flavor_access_requires_admin(non_admin_client):
    resp = await non_admin_client.get("/api/v1/admin/flavors/flavor-1/access")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_set_extra_specs_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/flavors/flavor-1/extra-specs", json={"key": "val"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_extra_spec_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/flavors/flavor-1/extra-specs/mykey")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_add_flavor_access_requires_admin(non_admin_client):
    resp = await non_admin_client.post("/api/v1/admin/flavors/flavor-1/access", json={"project_id": "p"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_remove_flavor_access_requires_admin(non_admin_client):
    resp = await non_admin_client.delete("/api/v1/admin/flavors/flavor-1/access/proj-1")
    assert resp.status_code == 403


@pytest.fixture
def usage_native(mock_conn, monkeypatch):
    """Installed SDK transport, mutable Nova fixture; no external cloud traffic."""

    class Nova(requests.adapters.BaseAdapter):
        def __init__(self):
            self.flavor = {
                "id": "small",
                "name": "small",
                "vcpus": 2,
                "ram": 2048,
                "disk": 0,
                "os-flavor-access:is_public": False,
                "description": "afterglow:domain-compute-v1:claim",
            }
            self.specs = {"afterglow:managed_by": "domain-compute-v1", "hw:cpu_policy": "shared"}
            self.calls = []
            self.foreign_id = False
            self.drop_write = False
            self.fail_after_write = False
            self.write_status = None

        def send(self, request, **kwargs):
            path = urlsplit(request.url).path.rstrip("/")
            self.calls.append((request.method, path, request.body))
            status, body = 200, {}
            headers = {}
            if path == "/compute/v2.1":
                body = {
                    "version": {
                        "id": "v2.1",
                        "status": "CURRENT",
                        "version": "2.95",
                        "min_version": "2.1",
                        "links": [{"rel": "self", "href": "http://flavor-usage.test/compute/v2.1/"}],
                    }
                }
            elif path.endswith("/os-extra_specs") and request.method == "POST":
                if self.write_status:
                    status = self.write_status
                    headers["Location"] = "http://flavor-usage.test/sink"
                elif not self.drop_write:
                    self.specs.update(json.loads(request.body)["extra_specs"])
                body = {"extra_specs": self.specs}
            elif request.method == "DELETE":
                self.specs.pop("afterglow:usage_schedule_required", None)
                status = 204
            elif path.endswith("/os-extra_specs"):
                body = {"extra_specs": copy.deepcopy(self.specs)}
            elif path.endswith("/flavors/small"):
                body = {"flavor": {**self.flavor, "id": "foreign" if self.foreign_id else "small"}}
                if self.fail_after_write and any(call[0] == "POST" for call in self.calls):
                    status = 503
            else:
                status = 404
            response = requests.Response()
            response.status_code = status
            response._content = json.dumps(body).encode()
            response.headers.update({"Content-Type": "application/json", **headers})
            response.request = request
            response.url = request.url
            return response

        def close(self):
            pass

    cloud = Nova()
    transport = requests.Session()
    transport.mount("http://flavor-usage.test/", cloud)
    native = connection.Connection(
        session=ks_session.Session(auth=noauth.NoAuth(), session=transport),
        compute_endpoint_override="http://flavor-usage.test/compute/v2.1",
        compute_default_microversion="2.61",
    )
    mock_conn.compute = native.compute
    cloud.calls.clear()  # Exclude setup discovery, never endpoint operations.
    lease = SimpleNamespace(assert_owned=AsyncMock())

    @asynccontextmanager
    async def lock(conn):
        yield lease

    monkeypatch.setattr(admin_flavors.identity_roles, "_graph_lock", lock)
    monkeypatch.setattr(admin_flavors, "invalidate", AsyncMock())
    yield cloud
    native.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_usage_requirement_adds_manual_and_managed_native_flavors(admin_client, usage_native, managed):
    cloud = usage_native
    if not managed:
        cloud.flavor["description"] = "manual"
        del cloud.specs["afterglow:managed_by"]
    before = dict(cloud.specs)
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True})
    assert response.status_code == 200, response.text
    assert response.json() == {"flavor_id": "small", "usage_schedule_required": True, "additional_requirement": True}
    assert cloud.specs == {**before, "afterglow:usage_schedule_required": "true"}
    assert requires_schedule({**cloud.flavor, "extra_specs": cloud.specs})
    assert [call[0] for call in cloud.calls].count("POST") == 1
    admin_flavors.invalidate.assert_awaited_once_with("afterglow:nova:*:flavors")


@pytest.mark.asyncio
@pytest.mark.parametrize("baseline", [{"vcpus": 12}, {"ram": 65536}, {"name": "gpu.example"}, {}])
async def test_usage_requirement_false_removes_only_addition_not_baseline(admin_client, usage_native, baseline):
    cloud = usage_native
    cloud.flavor.update(baseline)
    cloud.specs["afterglow:usage_schedule_required"] = "true"
    before = dict(cloud.specs)
    response = await admin_client.put(
        "/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": False}
    )
    assert response.status_code == 200, response.text
    assert response.json()["usage_schedule_required"] is bool(baseline)
    assert response.json()["additional_requirement"] is False
    del before["afterglow:usage_schedule_required"]
    assert cloud.specs == before
    assert [call[0] for call in cloud.calls].count("DELETE") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["foreign_id", "drop_write", "fail_after_write"])
async def test_usage_requirement_rejects_foreign_identity_and_uncertain_readback(admin_client, usage_native, failure):
    setattr(usage_native, failure, True)
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True})
    assert response.status_code == 502
    assert [call[0] for call in usage_native.calls].count("POST") == (0 if failure == "foreign_id" else 1)
    assert not any(call[0] == "DELETE" for call in usage_native.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 307, 308, 503])
async def test_usage_requirement_never_replays_native_annotation_write(admin_client, usage_native, status):
    usage_native.write_status = status
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True})
    assert response.status_code == 502
    assert [call[0] for call in usage_native.calls].count("POST") == 1
    assert not any(call[1] == "/sink" for call in usage_native.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{"required": "true"}, {"required": 1}, {"required": True, "vcpus": 99}, {}])
async def test_usage_requirement_accepts_only_strict_annotation_body(admin_client, usage_native, body):
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json=body)
    assert response.status_code == 422
    assert not usage_native.calls


@pytest.mark.asyncio
async def test_usage_requirement_requires_admin(non_admin_client, mock_conn):
    response = await non_admin_client.put(
        "/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True}
    )
    assert response.status_code == 403
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()


@pytest.mark.asyncio
async def test_usage_annotation_requires_dedicated_route_for_manual_flavors(admin_client, mock_conn):
    mock_conn.compute.get_flavor.return_value = SimpleNamespace(
        id="small", description="", extra_specs={"hw:cpu_policy": "shared"}
    )
    for method, suffix, body in [
        ("POST", "/extra-specs", {"key": "afterglow:usage_schedule_required", "value": "true"}),
        ("DELETE", "/extra-specs/afterglow:usage_schedule_required", None),
    ]:
        response = await admin_client.request(method, "/api/v1/admin/flavors/small" + suffix, json=body)
        assert response.status_code == 409
        assert response.json()["detail"] == "use_flavor_usage_schedule_requirement"
    mock_conn.compute.create_flavor_extra_specs.assert_not_called()
    mock_conn.compute.delete_flavor_extra_specs_property.assert_not_called()


@pytest.mark.asyncio
async def test_usage_annotation_uses_invocation_local_transport(admin_client, usage_native, mock_conn):
    original_request = mock_conn.compute.request
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True})
    assert response.status_code == 200
    assert mock_conn.compute.request == original_request


@pytest.fixture
def approved_admin_gpu_policy(monkeypatch):
    from app.models.flavor_automation import validate_profiles
    from app.services import flavor_automation_policy

    profile = {
        "name": "render-group",
        "display_name": "Render group",
        "enabled": True,
        "resource_class": "CUSTOM_PCI_10DE_2208",
        "resource_requirements": {"CUSTOM_PCI_10DE_2208": 1, "CUSTOM_PCI_10DE_1AEB": 1},
        "extra_specs": {"pci_passthrough:alias": "graphics:1,sound:1"},
        "alias_resource_classes": {"graphics": "CUSTOM_PCI_10DE_2208", "sound": "CUSTOM_PCI_10DE_1AEB"},
    }
    policy = {"revision": 1, "gpu_profiles": validate_profiles([profile])}
    load = AsyncMock(return_value=policy)
    monkeypatch.setattr(flavor_automation_policy, "load_policy", load)
    return policy, load


def admin_catalog_flavor(identifier, *, managed=True, specs=None):
    return SimpleNamespace(
        id=identifier,
        name=identifier,
        vcpus=2,
        ram=2048,
        disk=0,
        is_public=False,
        description="afterglow:domain-compute-v1:claim" if managed else "manual",
        extra_specs={
            **({"afterglow:managed_by": "domain-compute-v1"} if managed else {}),
            **({"pci_passthrough:alias": "graphics:1,sound:1"} if specs is None else specs),
        },
    )


@pytest.mark.asyncio
async def test_admin_list_projects_only_approved_primary_aliases(admin_client, mock_conn, approved_admin_gpu_policy):
    _, load = approved_admin_gpu_policy
    mock_conn.compute.flavors.return_value = [
        admin_catalog_flavor(
            "managed",
            specs={"pci_passthrough:alias": "graphics:1,sound:1", "afterglow:usage_schedule_required": "true"},
        ),
        admin_catalog_flavor("managed-two", specs={"pci_passthrough:alias": "graphics:2,sound:2"}),
        admin_catalog_flavor("manual", managed=False),
        admin_catalog_flavor("cpu", specs={"hw:cpu_policy": "shared"}),
    ]
    response = await admin_client.get("/api/v1/admin/flavors")
    assert response.status_code == 200, response.text
    managed, doubled, manual, cpu = response.json()["items"]
    assert managed["gpu_count"] == 1
    assert managed["is_gpu"] is True
    assert managed["gpu_primary_aliases"] == [
        {"name": "graphics", "count": 1, "resource_class": "CUSTOM_PCI_10DE_2208", "profile_name": "render-group"}
    ]
    assert doubled["gpu_count"] == 2
    assert doubled["gpu_primary_aliases"][0]["count"] == 2
    assert manual["gpu_count"] == 2
    assert manual["is_gpu"] is True
    assert "gpu_primary_aliases" not in manual
    assert cpu["gpu_count"] == 0
    assert cpu["is_gpu"] is False
    assert cpu["gpu_primary_aliases"] == []
    load.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "disabled",
        "retired",
        "unavailable",
        "unknown-alias",
        "unknown-resource",
        "missing-specs",
        "missing-companion",
        "changed-companion-count",
        "changed-scheduling",
        "gpu-request-missing",
        "retired-visible",
        "oversized-alias",
    ],
)
async def test_admin_list_preserves_manageable_unknown_gpu_mapping(
    admin_client, mock_conn, approved_admin_gpu_policy, state
):
    policy, load = approved_admin_gpu_policy
    managed = admin_catalog_flavor("managed")
    if state == "disabled":
        policy["gpu_profiles"][0]["enabled"] = False
    elif state == "retired":
        policy["gpu_profiles"] = []
    elif state == "unavailable":
        load.side_effect = RuntimeError("policy unavailable")
    elif state == "unknown-alias":
        managed.extra_specs["pci_passthrough:alias"] = "unknown:1,sound:1"
    elif state == "unknown-resource":
        managed.extra_specs = {"afterglow:managed_by": "domain-compute-v1", "resources:CUSTOM_RETIRED": "1"}
    elif state == "missing-specs":
        managed.extra_specs = {}
    elif state == "missing-companion":
        managed.extra_specs["pci_passthrough:alias"] = "graphics:1"
    elif state == "changed-companion-count":
        managed.extra_specs["pci_passthrough:alias"] = "graphics:1,sound:2"
    elif state == "changed-scheduling":
        policy["gpu_profiles"][0]["extra_specs"]["hw:cpu_policy"] = "dedicated"
        managed.extra_specs["hw:cpu_policy"] = "shared"
    elif state == "gpu-request-missing":
        managed.extra_specs = {"afterglow:managed_by": "domain-compute-v1", "afterglow:access_mode": "gpu_quota"}
    elif state == "retired-visible":
        managed.extra_specs["afterglow:frontend_visible"] = "false"
    elif state == "oversized-alias":
        managed.extra_specs["pci_passthrough:alias"] = "graphics:17,sound:17"
    mock_conn.compute.flavors.return_value = [managed, admin_catalog_flavor("manual", managed=False)]
    response = await admin_client.get("/api/v1/admin/flavors")
    assert response.status_code == 200, response.text
    unknown, manual = response.json()["items"]
    assert unknown["id"] == "managed"
    assert unknown["gpu_count"] is None
    assert unknown["is_gpu"] is None
    assert unknown["gpu_primary_aliases"] is None
    assert manual["gpu_count"] == 2
    assert response.json()["count"] == 2


@pytest.mark.asyncio
async def test_admin_manual_list_and_create_keep_legacy_projection_without_policy(
    admin_client, mock_conn, approved_admin_gpu_policy
):
    _, load = approved_admin_gpu_policy
    manual = admin_catalog_flavor("manual", managed=False)
    mock_conn.compute.flavors.return_value = [manual]
    mock_conn.compute.create_flavor.return_value = manual
    listed = await admin_client.get("/api/v1/admin/flavors")
    created = await admin_client.post(
        "/api/v1/admin/flavors", json={"name": "manual", "vcpus": 2, "ram": 2048, "disk": 0}
    )
    assert listed.status_code == 200, listed.text
    assert created.status_code == 201, created.text
    assert listed.json()["items"][0]["gpu_count"] == created.json()["gpu_count"] == 2
    load.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_create_managed_marker_is_unknown_without_approval(admin_client, mock_conn):
    mock_conn.compute.create_flavor.return_value = admin_catalog_flavor("managed")
    response = await admin_client.post(
        "/api/v1/admin/flavors", json={"name": "managed", "vcpus": 2, "ram": 2048, "disk": 0}
    )
    assert response.status_code == 201, response.text
    assert response.json()["gpu_count"] is None
    assert response.json()["gpu_primary_aliases"] is None


@pytest.mark.asyncio
async def test_admin_gpu_mapping_checks_each_exact_companion_quantity(
    admin_client, mock_conn, approved_admin_gpu_policy
):
    policy, _ = approved_admin_gpu_policy
    profile = policy["gpu_profiles"][0]
    profile["resource_requirements"]["CUSTOM_PCI_10DE_1AEB"] = 3
    profile["extra_specs"]["pci_passthrough:alias"] = "graphics:1,sound:2,aux:1"
    profile["alias_resource_classes"]["aux"] = "CUSTOM_PCI_10DE_1AEB"
    mock_conn.compute.flavors.return_value = [
        admin_catalog_flavor("reordered", specs={"pci_passthrough:alias": "aux:1,graphics:1,sound:2"}),
        admin_catalog_flavor("swapped", specs={"pci_passthrough:alias": "aux:2,graphics:1,sound:1"}),
    ]
    response = await admin_client.get("/api/v1/admin/flavors")
    assert response.status_code == 200, response.text
    reordered, swapped = response.json()["items"]
    assert reordered["gpu_count"] == 1
    assert [row["name"] for row in reordered["gpu_primary_aliases"]] == ["graphics"]
    assert swapped["gpu_count"] is None
    assert swapped["gpu_primary_aliases"] is None


@pytest.mark.asyncio
async def test_admin_cpu_display_uses_native_specs_and_preserves_manual_identity(admin_client, mock_conn):
    from openstack.compute.v2.flavor import Flavor

    flavor = Flavor(
        id="native-manual",
        name="m1.old",
        vcpus=2,
        ram=1536,
        disk=17,
        is_public=True,
        description="user description",
    )
    mock_conn.compute.flavors.return_value = [flavor]
    mock_conn.compute.get.return_value = SimpleNamespace(
        status_code=200, json=lambda: {"extra_specs": {"afterglow:cpu_control_token": "claim"}}
    )
    response = await admin_client.get("/api/v1/admin/flavors")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert (item["id"], item["name"], item["display_name"]) == ("native-manual", "m1.old", "cpu.2c_1.5g")
    assert item["description"] == "user description"
    assert item["extra_specs"] == {}
    assert item["cpu_automation_managed"] is True
    assert "gpu_primary_aliases" not in item
    assert item["is_public"] is True
    mock_conn.compute.get.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"extra_specs": None}, {"extra_specs": []}, {"extra_specs": {"bad": 1}}])
async def test_admin_cpu_display_is_unknown_without_native_spec_envelope(admin_client, mock_conn, payload):
    from openstack.compute.v2.flavor import Flavor

    mock_conn.compute.flavors.return_value = [Flavor(id="manual", name="cpu.manual", vcpus=2, ram=2048, disk=0)]
    mock_conn.compute.get.return_value = SimpleNamespace(status_code=200, json=lambda: payload)
    response = await admin_client.get("/api/v1/admin/flavors")
    assert response.status_code == 200
    assert response.json()["items"][0]["display_name"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "suffix", "body"),
    [
        ("delete", "", None),
        ("post", "/extra-specs", {"key": "hw:cpu_policy", "value": "dedicated"}),
        ("delete", "/extra-specs/hw:cpu_policy", None),
        ("post", "/access", {"project_id": "target"}),
        ("delete", "/access/target", None),
        ("put", "/frontend-visibility", {"visible": False}),
    ],
)
async def test_controlled_manual_cpu_mutations_are_owned_by_automation(
    admin_client, usage_native, method, suffix, body
):
    usage_native.flavor["description"] = "untouched manual description"
    usage_native.specs = {"afterglow:cpu_control_token": "claim", "hw:cpu_policy": "shared"}
    kwargs = {"json": body} if body is not None else {}
    response = await admin_client.request(method, f"/api/v1/admin/flavors/small{suffix}", **kwargs)
    assert response.status_code == 409
    assert all(call[0] == "GET" for call in usage_native.calls)
    assert usage_native.flavor["description"] == "untouched manual description"
    assert usage_native.specs == {"afterglow:cpu_control_token": "claim", "hw:cpu_policy": "shared"}


@pytest.mark.asyncio
async def test_controlled_manual_cpu_keeps_additive_usage_schedule_exception(admin_client, usage_native):
    usage_native.flavor["description"] = "manual"
    usage_native.specs = {"afterglow:cpu_control_token": "claim", "hw:cpu_policy": "shared"}
    response = await admin_client.put("/api/v1/admin/flavors/small/usage-schedule-requirement", json={"required": True})
    assert response.status_code == 200
    assert usage_native.specs == {
        "afterglow:cpu_control_token": "claim",
        "hw:cpu_policy": "shared",
        "afterglow:usage_schedule_required": "true",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "delete"])
async def test_cpu_control_marker_cannot_be_created_or_removed_by_manual_spec_route(admin_client, usage_native, method):
    usage_native.flavor["description"] = "manual"
    usage_native.specs = {"hw:cpu_policy": "shared"}
    path = "/api/v1/admin/flavors/small/extra-specs"
    kwargs = {}
    if method == "post":
        kwargs["json"] = {"key": "afterglow:cpu_control_token", "value": "forged"}
    else:
        path += "/afterglow:cpu_control_token"
    response = await admin_client.request(method, path, **kwargs)
    assert response.status_code == 409
    assert all(call[0] == "GET" for call in usage_native.calls)
    assert usage_native.specs == {"hw:cpu_policy": "shared"}
