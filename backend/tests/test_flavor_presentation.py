"""Native flavor identities and conservative CPU-only presentation labels."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openstack.compute.v2.flavor import Flavor
from openstack.compute.v2.server import Server

from app.services import nova
from app.services.flavor_presentation import canonical_cpu_display_name


@pytest.mark.parametrize(
    ("name", "vcpus", "ram", "specs", "expected"),
    [
        ("cpu.ag.2c.4g.legacy", 2, 4096, {}, "cpu.2c_4g"),
        ("m1.manual", 4, 10240, {}, "cpu.4c_10g"),
        ("m1.manual", 1, 1536, {}, "cpu.1c_1.5g"),
        ("m1.manual", 1, 1, {}, "cpu.1c_0.0009765625g"),
        ("cpu.2c_8g", 2, 8192, {}, "mem.2c_8g"),
        ("cpu.ag.2c.16g.legacy", 2, 16384, {}, "mem.2c_16g"),
        ("manual", 1, 16384, {}, "mem.1c_16g"),
        ("manual", 2, 8191, {}, "cpu.2c_7.9990234375g"),
        ("mem.2c_8g", 2, 4096, {}, "cpu.2c_4g"),
        ("manual", 2, 8193, {"hw:cpu_policy": "dedicated"}, "mem.2c_8.0009765625g"),
        (
            "cpu.1c_4g",
            1,
            4096,
            {"afterglow:managed_by": "domain-compute-v1", "afterglow:access_mode": "domain_quota"},
            "mem.1c_4g",
        ),
        ("mem.2c_8g", 2, 8192, {"pci_passthrough:alias": "graphics:1"}, None),
        ("mem.2c_8g", 2, 8192, {"trait:CUSTOM_SPECIAL": "required"}, None),
        ("mem.2c_8g", 2, 8192, None, None),
        ("mem.2c_8g", 0, 8192, {}, None),
        ("mem.2c_8g", 2, True, {}, None),
        ("mem.2c_8g", 2, float("nan"), {}, None),
        ("m1.manual", 2, 1024, {"hw:cpu_policy": "dedicated", "hw:mem_page_size": "large"}, "cpu.2c_1g"),
        ("m1.manual", 2, 1024, {"resources:PCPU": "2", "resources:MEMORY_MB": "1024"}, "cpu.2c_1g"),
        ("m1.manual", 2, 1024, {"trait:HW_CPU_X86_AVX2": "required"}, "cpu.2c_1g"),
        ("gpu.renderx1_2c_4g", 2, 4096, {}, None),
        ("cpu.innocent", 2, 4096, {"pci_passthrough:alias": "graphics:1,sound:1"}, None),
        ("cpu.innocent", 2, 4096, {"resources:VGPU": "1"}, None),
        ("cpu.innocent", 2, 4096, {"resources:CUSTOM_DEVICE": "1"}, None),
        ("cpu.innocent", 2, 4096, {"resources1:CUSTOM_DEVICE": "1"}, None),
        ("cpu.innocent", 2, 4096, {"capabilities:accelerator": "true"}, None),
        ("cpu.innocent", 2, 4096, {"trait:CUSTOM_SPECIAL": "required"}, None),
        ("cpu.innocent", 2, 4096, {"hw:accelerator_device": "opaque"}, None),
        ("cpu.innocent", 2, 4096, {"afterglow:access_mode": "gpu_quota"}, None),
        ("cpu.innocent", 2, 4096, {"hw:cpu_policy": "unknown"}, None),
        ("cpu.innocent", 2, 4096, {"resources:VCPU": "not-a-count"}, None),
        ("cpu.innocent", 2, 4096, None, None),
        ("cpu.innocent", 2, 4096, [], None),
        ("cpu.innocent", 2, 4096, {"hw:cpu_policy": None}, None),
        ("cpu.innocent", 2, 4096, {1: "value"}, None),
        ("", 2, 4096, {}, None),
        ("manual", True, 4096, {}, None),
        ("manual", 2, 0, {}, None),
        ("manual", 2, 1536.5, {}, None),
    ],
)
def test_canonical_cpu_label_requires_exact_cpu_evidence(name, vcpus, ram, specs, expected):
    assert canonical_cpu_display_name(name, vcpus, ram, specs) == expected


def test_cpu_control_annotation_preserves_label_and_specs():
    baseline = {"hw:cpu_policy": "dedicated", "hw:numa_nodes": "1", "hw:numa_cpus.0": "0,1"}
    controlled = {**baseline, "afterglow:cpu_control_token": "exact-token"}
    assert canonical_cpu_display_name("manual", 2, 2048, baseline) == "cpu.2c_2g"
    assert canonical_cpu_display_name("manual", 2, 2048, controlled) == "cpu.2c_2g"
    assert controlled == {**baseline, "afterglow:cpu_control_token": "exact-token"}


@pytest.mark.parametrize("catalog", [False, True])
@pytest.mark.parametrize(
    "native_name,ram,label",
    [
        ("m1.manual", 1536, "cpu.2c_1.5g"),
        ("cpu.2c_8g", 8192, "mem.2c_8g"),
        ("cpu.ag.2c.16g.legacy", 16384, "mem.2c_16g"),
    ],
)
def test_native_catalog_reads_explicit_specs_without_changing_identity(catalog, native_name, ram, label):
    flavor = Flavor(id="native-id", name=native_name, vcpus=2, ram=ram, disk=17, is_public=True)
    compute = MagicMock()
    compute.flavors.return_value = [flavor]
    compute.get.return_value = SimpleNamespace(status_code=200, json=lambda: {"extra_specs": {}})
    conn = SimpleNamespace(compute=compute, _afterglow_project_id="project", _afterglow_compute_admin=False)
    items = nova.list_catalog_flavors(conn) if catalog else nova.list_flavors(conn)
    assert items[0].model_dump()["display_name"] == label
    assert (items[0].id, items[0].name, items[0].disk) == ("native-id", native_name, 17)
    compute.get.assert_called_once_with(
        "/flavors/native-id/os-extra_specs",
        redirect=False,
        allow_reauth=False,
        connect_retries=0,
        status_code_retries=0,
    )


@pytest.mark.parametrize("specs", [None, [], {"hw:cpu_policy": False}])
def test_catalog_never_uses_sdk_empty_default_as_native_proof(specs):
    flavor = Flavor(id="native-id", name="manual", vcpus=2, ram=2048, disk=0)
    compute = MagicMock()
    compute.flavors.return_value = [flavor]
    compute.get.return_value = SimpleNamespace(status_code=200, json=lambda: {"extra_specs": specs})
    conn = SimpleNamespace(compute=compute, _afterglow_project_id="project", _afterglow_compute_admin=False)
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as error:
        nova.list_flavors(conn)
    assert error.value.status_code == 503


@pytest.mark.parametrize(
    ("extra", "expected"),
    [({}, "cpu.2c_1.5g"), (None, None), ([], None), ({"pci_passthrough:alias": "graphics:1"}, None)],
)
def test_server_snapshot_label_keeps_native_identity_and_private_hardware(extra, expected):
    server = Server(
        id="server",
        name="vm",
        status="ACTIVE",
        addresses={},
        metadata={},
        flavor={
            "id": "native-id",
            "original_name": "m1.manual",
            "vcpus": 2,
            "ram": 1536,
            "disk": 17,
            "extra_specs": extra,
        },
    )
    info = nova._server_to_info(server)
    data = info.model_dump()
    assert data["flavor_display_name"] == expected
    assert data["flavor_name"] == "m1.manual"
    assert data["flavor_id"] == "native-id"
    assert "_flavor_snapshot" not in data
    assert info._flavor_snapshot["extra_specs"] == extra


@pytest.mark.parametrize("native_name", ["cpu.2c_8g", "cpu.ag.2c.8g.legacy", "mem.2c_8g"])
def test_memory_server_snapshot_label_preserves_native_reference_and_hardware(native_name):
    snapshot = {
        "id": "native-id",
        "original_name": native_name,
        "vcpus": 2,
        "ram": 8192,
        "disk": 17,
        "extra_specs": {"hw:cpu_policy": "shared"},
    }
    server = Server(id="server", name="vm", status="ACTIVE", addresses={}, metadata={}, flavor=snapshot)
    info = nova._server_to_info(server)
    assert (info.flavor_id, info.flavor_name, info.flavor_display_name) == ("native-id", native_name, "mem.2c_8g")
    assert info._flavor_snapshot == {key: snapshot[key] for key in ("vcpus", "ram", "disk", "extra_specs")}


def test_server_snapshot_missing_extra_specs_never_infers_cpu_from_name():
    server = Server(
        id="server",
        name="vm",
        status="ACTIVE",
        addresses={},
        metadata={},
        flavor={"original_name": "cpu.2c_4g", "vcpus": 2, "ram": 4096, "disk": 0},
    )
    data = nova._server_to_info(server).model_dump()
    assert data["flavor_display_name"] is None
    assert data["flavor_name"] == "cpu.2c_4g"
    assert data["flavor_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native_name,ram,label",
    [("m1.manual", 1536, "cpu.2c_1.5g"), ("cpu.2c_8g", 8192, "mem.2c_8g")],
)
async def test_project_flavor_api_and_cache_keep_distinct_display_name(
    client, mock_conn, monkeypatch, native_name, ram, label
):
    from app.services import flavor_eligibility
    from app.services.cache import _make_serializable

    native = Flavor(
        id="native-id",
        name=native_name,
        vcpus=2,
        ram=ram,
        disk=17,
        is_public=True,
        extra_specs={"afterglow:cpu_control_token": "private-marker", "hw:cpu_policy": "shared"},
    )
    mock_conn.compute.flavors.return_value = [native]
    projected = nova.list_flavors(mock_conn)
    cached = _make_serializable(projected)
    assert projected[0].extra_specs["afterglow:cpu_control_token"] == "private-marker"
    assert cached[0]["cpu_automation_managed"] is True
    assert "afterglow:cpu_control_token" not in cached[0]["extra_specs"]
    monkeypatch.setattr("app.services.cache.cached_call", AsyncMock(return_value=cached))
    monkeypatch.setattr(
        flavor_eligibility,
        "evaluate_project_flavors",
        AsyncMock(side_effect=lambda _conn, _pid, flavors, **kwargs: list(flavors)),
    )
    response = await client.get("/api/v1/flavors")
    assert response.status_code == 200
    item = response.json()[0]
    assert (item["id"], item["name"], item["display_name"]) == ("native-id", native_name, label)
    assert item["cpu_automation_managed"] is True
    assert item["extra_specs"] == {"hw:cpu_policy": "shared"}


@pytest.mark.parametrize("key", ["afterglow:frontend_visible", "afterglow:usage_schedule_required"])
@pytest.mark.parametrize("value", ["true", "false", "1", "0", "YES", "no", "on", "OFF", "legacy", "", " "])
def test_benign_application_annotations_do_not_change_cpu_hardware_classification(key, value):
    specs = {key: value, "hw:cpu_policy": "shared"}
    assert canonical_cpu_display_name("m1.manual", 2, 2048, specs) == "cpu.2c_2g"
    assert specs == {key: value, "hw:cpu_policy": "shared"}


@pytest.mark.parametrize("nested_resource", [False, True])
@pytest.mark.parametrize("extras", [None, [], "malformed", {"hw:cpu_policy": False}])
def test_server_raw_body_never_trusts_normalized_extra_specs(nested_resource, extras):
    raw = {"original_name": "m1.manual", "vcpus": 2, "ram": 2048, "disk": 0, "extra_specs": extras}
    server = Server(id="vm", name="vm", status="ACTIVE", addresses={}, metadata={})
    server._body.attributes["flavor"] = Flavor(**raw) if nested_resource else raw
    info = nova._server_to_info(server)
    assert info.flavor_display_name is None
    assert info._flavor_snapshot["extra_specs"] == extras


@pytest.mark.parametrize("nested_resource", [False, True])
def test_missing_raw_embedded_specs_stays_unknown_even_with_sdk_default(nested_resource):
    raw = {"original_name": "m1.manual", "vcpus": 2, "ram": 2048, "disk": 0}
    server = Server(id="vm", name="vm", status="ACTIVE", addresses={}, metadata={})
    server._body.attributes["flavor"] = Flavor(**raw) if nested_resource else raw
    info = nova._server_to_info(server)
    assert info.flavor_display_name is None
    assert info._flavor_snapshot["extra_specs"] is None
