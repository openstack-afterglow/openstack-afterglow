"""Standard Nova/Placement stable inventory and complete domain directory."""

from types import SimpleNamespace

import pytest

from app.services import managed_flavors as svc


def inventory(total, maximum=None):
    return {
        "total": total,
        "reserved": 0,
        "allocation_ratio": 1,
        "min_unit": 1,
        "max_unit": maximum or total,
        "step_size": 1,
    }


@pytest.fixture
def native(monkeypatch):
    services = {"service": {"host": "host", "status": "enabled", "state": "up", "forced_down": False}}
    hypervisors = ({"id": "root", "service": {"id": "service", "host": "host"}, "state": "up", "status": "enabled"},)
    facts = SimpleNamespace(services=services, hypervisors=hypervisors)
    calls = []
    values = {
        "/resource_providers": {
            "resource_providers": [
                {"uuid": "root", "root_provider_uuid": "root", "parent_provider_uuid": None},
                {"uuid": "child", "root_provider_uuid": "root", "parent_provider_uuid": "root"},
            ]
        },
        "/resource_providers/root/inventories": {"inventories": {"VCPU": inventory(16), "MEMORY_MB": inventory(65536)}},
        "/resource_providers/child/inventories": {"inventories": {"CUSTOM_PCI_10DE_2208": inventory(8, 1)}},
    }

    class Client:
        def placement(self, path, params, deadline):
            calls.append(path)
            assert "allocation_candidates" not in path and "usages" not in path
            return values[path]

    monkeypatch.setattr(svc.flavor_capacity, "_Client", lambda conn: Client())
    monkeypatch.setattr(svc.flavor_capacity._HostFacts, "fetch", lambda client, deadline: facts)
    return SimpleNamespace(facts=facts, values=values, calls=calls)


def test_inventory_uses_stable_total_not_current_free_candidates(native):
    hosts, complete = svc.supported_hosts(object())
    assert complete is True
    assert hosts[0]["id"] == "root" and hosts[0]["name"] == "host"
    assert hosts[0]["cpu"]["capacity"] == 16
    assert hosts[0]["gpu"]["CUSTOM_PCI_10DE_2208"] == 8
    assert native.calls == [
        "/resource_providers",
        "/resource_providers/root/inventories",
        "/resource_providers/child/inventories",
    ]


@pytest.mark.parametrize("field,value", [("state", "down"), ("status", "disabled"), ("forced_down", True)])
def test_host_maintenance_still_observes_supported_hardware(native, field, value):
    native.facts.services["service"][field] = value
    hosts, complete = svc.supported_hosts(object())
    assert complete is True and hosts[0]["cpu"]["capacity"] == 16
    assert hosts[0]["status"] == native.facts.services["service"]["status"]
    assert hosts[0]["state"] == ("down" if field in {"state", "forced_down"} else "up")


def test_unmapped_or_duplicate_native_node_fails_closed(native):
    native.facts.hypervisors = native.facts.hypervisors * 2
    with pytest.raises(ValueError, match="duplicate"):
        svc.supported_hosts(object())


def test_unjoined_compute_service_is_not_complete(native):
    native.facts.services["missing-node"] = {"host": "other"}
    _, complete = svc.supported_hosts(object())
    assert complete is False


def test_provider_pagination_does_not_pretend_complete(native):
    native.values["/resource_providers"]["resource_providers_links"] = [{"rel": "next", "href": "next"}]
    with pytest.raises(ValueError, match="incomplete"):
        svc.supported_hosts(object())


def test_missing_child_inventory_never_implies_zero_gpus(native):
    native.values["/resource_providers/child/inventories"] = {}
    with pytest.raises(ValueError, match="child"):
        svc.supported_hosts(object())


@pytest.mark.asyncio
async def test_stale_reconciler_cannot_overwrite_completed_disable(monkeypatch):
    from fastapi import HTTPException

    disabled = {**svc._default(), "revision": 2}
    row = SimpleNamespace(value_json=disabled)

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, *args, **kwargs):
            assert kwargs["with_for_update"] is True
            return row

    monkeypatch.setattr(svc, "_factory", lambda: Session)
    with pytest.raises(HTTPException) as error:
        await svc._save({**svc._default(), "enabled": True, "revision": 1})
    assert error.value.status_code == 409 and row.value_json is disabled


@pytest.fixture
def directory():
    policy = {
        "schema": 1,
        "revision": 1,
        "enabled": True,
        "limits": {"CPU": 64, "MEMORY_MB": 131072},
        "project_limits": {},
    }
    bodies = {
        "/domains": {
            "domains": [{"id": "d", "enabled": True, "afterglow_compute_pool": policy}],
            "links": {"next": None},
        },
        "/projects?domain_id=d": {
            "projects": [{"id": f"p{index}", "domain_id": "d", "enabled": True} for index in range(501)],
            "links": {"next": None},
        },
    }
    calls = []

    class Transport:
        def get(self, path):
            calls.append(path)
            return None, bodies[path]

    manager = SimpleNamespace(client=Transport())
    return SimpleNamespace(ks=SimpleNamespace(domains=manager, projects=manager), bodies=bodies, calls=calls)


def test_pool_project_directory_501_rows_has_no_per_project_get(directory):
    projects = svc._directory_projects(directory.ks)
    assert len(projects) == 501 and projects["p0"]["domain_id"] == "d"
    assert projects["p0"]["limits"] == {"CPU": 64, "MEMORY_MB": 131072}
    assert directory.calls == ["/domains", "/projects?domain_id=d"]


@pytest.mark.parametrize("key,value", [("limited", True), ("truncated", True), ("links", {"next": "next-page"})])
def test_partial_project_directory_cannot_authorize_acl_removal(directory, key, value):
    directory.bodies["/projects?domain_id=d"][key] = value
    with pytest.raises(ValueError, match="incomplete"):
        svc._directory_projects(directory.ks)


def test_mismatched_project_domain_blocks_publication(directory):
    directory.bodies["/projects?domain_id=d"]["projects"][0]["domain_id"] = "foreign"
    with pytest.raises(ValueError, match="directory"):
        svc._directory_projects(directory.ks)


@pytest.mark.parametrize("disabled", ["domain", "project", "pool"])
def test_disabled_directory_objects_lose_acl_eligibility(directory, disabled):
    if disabled == "domain":
        directory.bodies["/domains"]["domains"][0]["enabled"] = False
    elif disabled == "pool":
        directory.bodies["/domains"]["domains"][0]["afterglow_compute_pool"]["enabled"] = False
    else:
        for project in directory.bodies["/projects?domain_id=d"]["projects"]:
            project["enabled"] = False
    projects = svc._directory_projects(directory.ks)
    shape = {"vcpus": 2, "ram": 4096, "gpu_resource_class": None}
    # Directory evidence remains available for safe withdrawal, but disabled
    # scopes must never gain access to a newly published CPU flavor.
    assert svc._shape_projects(projects, shape) == set()


def test_pcpu_only_host_keeps_separate_physical_inventory_without_virtual_cpu_inference(native):
    root = native.values["/resource_providers/root/inventories"]["inventories"]
    root["PCPU"] = inventory(12)
    root.pop("VCPU")
    hosts, complete = svc.supported_hosts(object())
    assert complete is True
    assert hosts[0]["cpu"] == {"capacity": 0, "min": 1, "step": 1}
    assert hosts[0]["pcpu"] == {"capacity": 12, "min": 1, "step": 1}
    assert hosts[0]["gpu"]["CUSTOM_PCI_10DE_2208"] == 8


def test_vcpu_only_host_does_not_infer_physical_cpu_inventory(native):
    hosts, complete = svc.supported_hosts(object())
    assert complete is True and "pcpu" not in hosts[0]


def test_physical_cpu_inventory_cannot_overcommit(native):
    root = native.values["/resource_providers/root/inventories"]["inventories"]
    root["PCPU"] = {**inventory(12), "allocation_ratio": 2}
    with pytest.raises(ValueError, match="PCPU overcommit"):
        svc.supported_hosts(object())
