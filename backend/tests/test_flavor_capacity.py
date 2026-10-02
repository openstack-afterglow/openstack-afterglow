"""Same-host flavor capacity through a real openstacksdk connection over an in-process transport."""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import urllib.parse
from copy import deepcopy

import pytest
import requests
from keystoneauth1 import noauth
from keystoneauth1 import session as ks_session
from openstack import connection

from app.models.compute import FlavorInfo
from app.services import flavor_capacity, gpu_inventory

BASE = "http://capacity.test"
GPU_RC = "CUSTOM_PCI_10DE_2203"
AUDIO_RC = "CUSTOM_PCI_10DE_1AEF"
PROJECT = "project-capacity-a"
ZONE = "gpu-zone"
ROOT_A = "6f1d3a62-6c1b-4d5e-9a10-00000000000a"
GPU_A1 = "6f1d3a62-6c1b-4d5e-9a10-0000000000a1"
GPU_A2 = "6f1d3a62-6c1b-4d5e-9a10-0000000000a2"
AUDIO_A1 = "6f1d3a62-6c1b-4d5e-9a10-0000000000a3"
ROOT_B = "6f1d3a62-6c1b-4d5e-9a10-00000000000b"
ROOT_C = "6f1d3a62-6c1b-4d5e-9a10-00000000000c"
GPU_C1 = "6f1d3a62-6c1b-4d5e-9a10-0000000000c1"
GPU_C2 = "6f1d3a62-6c1b-4d5e-9a10-0000000000c2"
HOST_NAMES = {ROOT_A: "gpu-node-a", ROOT_B: "cpu-node-b", ROOT_C: "gpu-node-c"}
GPU_SPECS = {"pci_passthrough:alias": "rtx3090ti:1"}
# Shape of the deployed RTX 3090 Ti flavors: one NUMA cell, any page size, GPU plus its HDMI audio function.
LIVE_GPU_SPECS = {
    "hw:mem_page_size": "any",
    "hw:numa_nodes": "1",
    "pci_passthrough:alias": "RTX-3090ti:1,GA102-audio:1",
}
ONE = {"VCPU": 1, "MEMORY_MB": 1}


def shape(resources="VCPU:1,MEMORY_MB:1", *pci):
    """Key of one allocation-candidates query: unsuffixed resources plus one group per PCI device."""
    return "|".join([resources, *(f"resources_PCI{i}={rc}:1" for i, rc in enumerate(sorted(pci)))])


CPU_SHAPE = shape()
GPU_SHAPE = shape("VCPU:1,MEMORY_MB:1", GPU_RC)


def inventory(total, *, reserved=0, ratio=1.0, min_unit=1, max_unit=None, step_size=1):
    return {
        "total": total,
        "reserved": reserved,
        "allocation_ratio": ratio,
        "min_unit": min_unit,
        "max_unit": total if max_unit is None else max_unit,
        "step_size": step_size,
    }


def allocation(by_provider):
    return {"allocations": {uuid: {"resources": resources} for uuid, resources in by_provider.items()}, "mappings": {}}


def flavor(flavor_id, *, vcpus=4, ram=8192, specs=None, name=None):
    return FlavorInfo(
        id=flavor_id, name=name or f"m1.{flavor_id}", vcpus=vcpus, ram=ram, disk=100, extra_specs=specs or {}
    )


def observed(capacity):
    return (
        capacity.status,
        capacity.candidate_hosts,
        capacity.cpu_resource_class,
        capacity.remaining_vcpus,
        capacity.remaining_ram_mb,
    )


class FakeCloud(requests.adapters.BaseAdapter):
    """Nova 2.53 and Placement 1.36 read endpoints backed by mutable fixture state."""

    def __init__(self):
        super().__init__()
        self.services: list[dict] = []
        self.hypervisors: list[dict] = []
        self.aggregates: list[dict] = []
        self.providers: list[dict] = []
        self.inventories: dict[str, dict] = {}
        self.usages: dict[str, dict] = {}
        self.answers: dict[str, list] = {}
        self.failures: dict[str, tuple[int, bytes]] = {}
        self.stalls: dict[str, float] = {}
        self.calls: list[tuple[str, dict, str | None]] = []
        self.opened = 0
        self.closed = 0

    def add_host(self, root, *, vcpu=(32, 0), pcpu=None, ram=(65536, 0), gpus=(), zone=ZONE):
        host = HOST_NAMES[root]
        service_id = f"svc-{host}"
        self.services.append(
            {
                "id": service_id,
                "binary": "nova-compute",
                "host": host,
                "zone": zone,
                "status": "enabled",
                "state": "up",
                "forced_down": False,
            }
        )
        self.hypervisors.append(
            {
                "id": root,
                "hypervisor_hostname": host,
                "status": "enabled",
                "state": "up",
                "service": {"id": service_id, "host": host, "disabled_reason": None},
            }
        )
        self.aggregates.append(
            {
                "id": len(self.aggregates) + 1,
                "name": f"agg-{host}",
                "availability_zone": zone,
                "hosts": [host],
                "metadata": {"availability_zone": zone},
            }
        )
        self.providers.append({"uuid": root, "parent_provider_uuid": None, "root_provider_uuid": root})
        self.inventories[root] = {"MEMORY_MB": inventory(ram[0])}
        self.usages[root] = {"MEMORY_MB": ram[1]}
        for resource_class, pair in (("VCPU", vcpu), ("PCPU", pcpu)):
            if pair is not None:
                self.inventories[root][resource_class] = inventory(pair[0])
                self.usages[root][resource_class] = pair[1]
        for child, used in gpus:
            self.add_device(root, child, GPU_RC, used)

    def add_device(self, root, child, resource_class, used=0):
        self.providers.append({"uuid": child, "parent_provider_uuid": root, "root_provider_uuid": root})
        self.inventories[child] = {resource_class: inventory(1)}
        self.usages[child] = {resource_class: used}

    def service(self, root):
        return next(item for item in self.services if item["host"] == HOST_NAMES[root])

    def hypervisor(self, root):
        return next(item for item in self.hypervisors if item["id"] == root)

    def aggregate(self, root):
        return next(item for item in self.aggregates if HOST_NAMES[root] in item["hosts"])

    def candidate_queries(self):
        return [params for path, params, _ in self.calls if path == "/placement/allocation_candidates"]

    def summaries(self, requests_):
        """Placement 1.29+ provider summaries: every provider in each candidate tree, from current usage."""
        roots = {
            next(p["root_provider_uuid"] for p in self.providers if p["uuid"] == provider)
            for request in requests_
            for provider in request["allocations"]
        }
        summaries = {}
        for provider in self.providers:
            if provider["root_provider_uuid"] not in roots:
                continue
            uuid = provider["uuid"]
            summaries[uuid] = {
                "resources": {
                    rc: {
                        "capacity": int((inv["total"] - inv["reserved"]) * inv["allocation_ratio"]),
                        "used": self.usages.get(uuid, {}).get(rc, 0),
                    }
                    for rc, inv in self.inventories.get(uuid, {}).items()
                },
                "traits": [],
                "parent_provider_uuid": provider["parent_provider_uuid"],
                "root_provider_uuid": provider["root_provider_uuid"],
            }
        return summaries

    def send(self, request, **kwargs):
        url = urllib.parse.urlsplit(request.url)
        path = re.sub("/+", "/", url.path).rstrip("/")
        params = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
        self.calls.append((path, params, request.headers.get("OpenStack-API-Version")))
        if path in self.stalls:
            timeout = kwargs.get("timeout")
            if timeout is not None and self.stalls[path] > timeout:
                time.sleep(timeout)
                raise requests.exceptions.ReadTimeout(f"stalled {path}")
            time.sleep(self.stalls[path])
        if path in self.failures:
            status, content = self.failures[path]
        else:
            status, body = self._route(path, params)
            content = json.dumps(body).encode()
        response = requests.Response()
        response.status_code = status
        response._content = content
        response.headers["Content-Type"] = "application/json"
        response.encoding = "utf-8"
        response.url = request.url
        response.request = request
        return response

    def close(self):
        pass

    def _route(self, path, params):
        if path == "/compute/v2.1":
            links = [{"rel": "self", "href": f"{BASE}/compute/v2.1/"}]
            return 200, {
                "version": {"id": "v2.1", "status": "CURRENT", "version": "2.95", "min_version": "2.1", "links": links}
            }
        if path == "/placement":
            version = {
                "id": "v1.0",
                "status": "CURRENT",
                "max_version": "1.39",
                "min_version": "1.0",
                "links": [{"rel": "self", "href": f"{BASE}/placement/"}],
            }
            return 200, {"versions": [version]}
        if path == "/compute/v2.1/os-services":
            return 200, {"services": [item for item in self.services if item["binary"] == params.get("binary")]}
        if path == "/compute/v2.1/os-aggregates":
            return 200, {"aggregates": self.aggregates}
        if path == "/compute/v2.1/os-hypervisors/detail":
            # One hypervisor per page so every scenario crosses Nova pagination.
            ids = [item["id"] for item in self.hypervisors]
            start = ids.index(params["marker"]) + 1 if "marker" in params else 0
            page = self.hypervisors[start : start + 1]
            body = {"hypervisors": page}
            if start + 1 < len(self.hypervisors):
                href = f"{BASE}/compute/v2.1/os-hypervisors/detail?limit=1&marker={page[-1]['id']}"
                body["hypervisors_links"] = [{"rel": "next", "href": href}]
            return 200, body
        if path == "/placement/resource_providers":
            return 200, {"resource_providers": self.providers}
        match = re.fullmatch(r"/placement/resource_providers/([^/]+)/(inventories|usages)", path)
        if match:
            uuid, leaf = match.groups()
            store = self.inventories if leaf == "inventories" else self.usages
            if uuid not in store:
                return 404, {"errors": [{"status": 404, "title": "Not Found"}]}
            return 200, {leaf: store[uuid], "resource_provider_generation": 1}
        match = re.fullmatch(r"/placement/resource_classes/([^/]+)", path)
        if match:
            name = match.group(1)
            known = {"VCPU", "PCPU", "MEMORY_MB", "DISK_GB", "VGPU"} | {
                rc for inventories in self.inventories.values() for rc in inventories
            }
            return (200, {"name": name}) if name in known else (404, {"errors": [{"status": 404}]})
        if path == "/placement/allocation_candidates":
            key = "|".join(
                [
                    params.get("resources", ""),
                    *(f"{k}={v}" for k, v in sorted(params.items()) if k.startswith("resources_")),
                ]
            )
            answer = self.answers.get(key, [])
            return 200, {"allocation_requests": answer, "provider_summaries": self.summaries(answer)}
        return 404, {"error": path}


@pytest.fixture
def cloud(monkeypatch):
    fake = FakeCloud()
    monkeypatch.setattr(gpu_inventory, "PCI_DEVICE_MAP", deepcopy(gpu_inventory._DEFAULT_PCI_DEVICE_MAP))
    monkeypatch.setattr(flavor_capacity, "_operator", None)
    monkeypatch.setattr(flavor_capacity, "_shared_snapshot", None)

    def connect():
        transport = requests.Session()
        transport.mount(f"{BASE}/", fake)
        conn = connection.Connection(
            session=ks_session.Session(auth=noauth.NoAuth(), session=transport),
            compute_endpoint_override=f"{BASE}/compute/v2.1",
            placement_endpoint_override=f"{BASE}/placement",
        )
        original_close = conn.close

        def close():
            fake.closed += 1
            original_close()

        conn.close = close
        fake.opened += 1
        return conn

    monkeypatch.setattr("app.services.keystone.get_admin_project_connection", connect)
    monkeypatch.setattr("app.database.is_db_available", lambda: False)
    yield fake
    flavor_capacity._operator = None
    flavor_capacity._shared_snapshot = None


async def evaluate(*flavors, zone=ZONE, fresh=True):
    return await flavor_capacity.evaluate_flavor_capacities(
        flavors, project_id=PROJECT, availability_zone=zone, fresh=fresh
    )


async def test_gpu_capacity_pairs_cpu_and_ram_from_the_gpu_root_only(cloud):
    cloud.add_host(ROOT_A, vcpu=(16, 10), ram=(65536, 49152), gpus=[(GPU_A1, 1), (GPU_A2, 0)])
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[GPU_SHAPE] = [
        # A GPU on one host paired with CPU/RAM on another must never count as capacity.
        allocation({ROOT_B: ONE, GPU_A2: {GPU_RC: 1}}),
        allocation({ROOT_A: ONE, GPU_A2: {GPU_RC: 1}}),
    ]

    result = await evaluate(flavor("gpu", specs=GPU_SPECS, name="gpu.3090ti_4c"))

    assert observed(result["gpu"]) == ("available", 1, "VCPU", 6, 16384)
    assert cloud.candidate_queries() == [
        {
            "resources": "VCPU:1,MEMORY_MB:1",
            "resources_PCI0": f"{GPU_RC}:1",
            "group_policy": "none",
            "root_required": "!COMPUTE_STATUS_DISABLED",
        }
    ]
    versions = {path: version for path, _, version in cloud.calls if version}
    assert versions["/placement/allocation_candidates"] == "placement 1.36"
    assert versions["/compute/v2.1/os-hypervisors/detail"] == "compute 2.53"
    # Usage comes from the candidates' provider summaries, never from per-provider usage reads.
    assert not [path for path, _, _ in cloud.calls if path.endswith("/usages")]


async def test_gpu_root_cpu_shortage_is_insufficient_despite_spare_cpu_elsewhere(cloud):
    cloud.add_host(ROOT_A, vcpu=(16, 10), ram=(65536, 49152), gpus=[(GPU_A1, 1), (GPU_A2, 0)])
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[GPU_SHAPE] = [allocation({ROOT_A: ONE, GPU_A2: {GPU_RC: 1}})]
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_A: ONE}), allocation({ROOT_B: ONE})]

    result = await evaluate(
        flavor("gpu", vcpus=8, ram=8192, specs=GPU_SPECS, name="gpu.3090ti_8c"),
        flavor("cpu", vcpus=8, ram=4096),
    )

    # Shortage telemetry describes the GPU host, not the CPU-rich host without a GPU.
    assert observed(result["gpu"]) == ("insufficient", 0, "VCPU", 6, 16384)
    assert observed(result["cpu"]) == ("available", 1, "VCPU", 64, 262144)


async def test_each_admission_reads_fresh_contention_on_one_operator_session(cloud):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 1), (GPU_A2, 0)])
    cloud.answers[GPU_SHAPE] = [allocation({ROOT_A: ONE, GPU_A2: {GPU_RC: 1}})]
    gpu = flavor("gpu", specs=GPU_SPECS, name="gpu.3090ti_4c")

    assert (await evaluate(gpu))["gpu"].status == "available"

    cloud.usages[GPU_A2][GPU_RC] = 1  # another tenant took the last GPU; the static candidate is now stale
    assert observed((await evaluate(gpu))["gpu"])[:2] == ("insufficient", 0)

    cloud.usages[GPU_A2][GPU_RC] = 0
    cloud.usages[ROOT_A]["MEMORY_MB"] = 65536 - 4096
    assert observed((await evaluate(gpu))["gpu"])[:2] == ("insufficient", 0)

    cloud.usages[ROOT_A]["MEMORY_MB"] = 0
    assert (await evaluate(gpu))["gpu"].status == "available"
    # Four fresh evaluations, one authenticated operator session.
    assert (cloud.opened, cloud.closed) == (1, 0)


@pytest.mark.parametrize(
    ("vcpu_inventory", "vcpus", "expected"),
    [
        (inventory(16, reserved=4, ratio=2.0), 4, ("available", 1, "VCPU", 4, 32768)),
        (inventory(16, reserved=4, ratio=2.0), 5, ("insufficient", 0, "VCPU", 4, 32768)),
        # 44 vCPUs remain on the host, but one VM can never exceed max_unit (the physical CPU count).
        (inventory(64, max_unit=8), 8, ("available", 1, "VCPU", 8, 32768)),
        (inventory(64, max_unit=4), 8, ("insufficient", 0, "VCPU", 4, 32768)),
    ],
    ids=["reserved-ratio-fit", "reserved-ratio-short", "max-unit-caps-per-vm", "max-unit-short"],
)
async def test_reserved_ratio_and_max_unit_bound_one_vm(cloud, vcpu_inventory, vcpus, expected):
    cloud.add_host(ROOT_B, vcpu=(64, 20), ram=(32768, 0))
    cloud.inventories[ROOT_B]["VCPU"] = vcpu_inventory
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]

    result = await evaluate(flavor("cpu", vcpus=vcpus, ram=2048))

    assert observed(result["cpu"]) == expected


async def test_dedicated_cpu_policy_uses_pcpu_and_ignores_hosts_without_it(cloud):
    cloud.add_host(ROOT_A, vcpu=None, pcpu=(16, 4), ram=(65536, 0), gpus=[(GPU_A1, 0)])
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    pinned = flavor(
        "pinned",
        specs={
            **GPU_SPECS,
            "hw:cpu_policy": "dedicated",
            "hw:emulator_threads_policy": "isolate",
            "hw:cpu_thread_policy": "isolate",
        },
        name="gpu.3090ti_pinned",
    )
    cloud.answers[shape("PCPU:1,MEMORY_MB:1", GPU_RC)] = [
        allocation({ROOT_A: {"PCPU": 1, "MEMORY_MB": 1}, GPU_A1: {GPU_RC: 1}})
    ]
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]

    result = await evaluate(pinned, flavor("shared", vcpus=4, ram=4096))

    assert observed(result["pinned"]) == ("available", 1, "PCPU", 12, 65536)
    assert observed(result["shared"]) == ("available", 1, "VCPU", 64, 262144)
    # Pinned CPUs imply one guest NUMA cell whose headroom Placement does not expose.
    assert (result["pinned"].numa_unverified, result["shared"].numa_unverified) == (True, False)
    pinned_query = next(q for q in cloud.candidate_queries() if q["resources"].startswith("PCPU"))
    assert pinned_query["required"] == "!HW_CPU_HYPERTHREADING"


async def test_single_cell_numa_gpu_flavor_uses_host_totals_and_is_flagged(cloud):
    # The live RTX 3090 Ti host: 24 threads at cpu ratio 2.0, 128 GB, a free GPU and its audio function.
    cloud.add_host(ROOT_A, vcpu=(24, 12), ram=(128597, 40960), gpus=[(GPU_A1, 0)])
    cloud.add_device(ROOT_A, AUDIO_A1, AUDIO_RC)
    cloud.inventories[ROOT_A]["VCPU"] = inventory(24, ratio=2.0)
    cloud.inventories[ROOT_A]["MEMORY_MB"] = inventory(128597, reserved=512)
    cloud.answers[shape("VCPU:1,MEMORY_MB:1", GPU_RC, AUDIO_RC)] = [
        allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}, AUDIO_A1: {AUDIO_RC: 1}})
    ]
    numa = flavor("numa", vcpus=8, ram=65536, specs=LIVE_GPU_SPECS, name="gpu.3090ti_8c_64g")
    plain = flavor("plain", vcpus=8, ram=65536, specs={"pci_passthrough:alias": "RTX-3090ti:1,GA102-audio:1"})

    result = await evaluate(numa, plain)

    # 36 of 48 schedulable vCPUs remain, but one VM is capped at the 24 physical threads (max_unit).
    assert observed(result["numa"]) == ("available", 1, "VCPU", 24, 87125)
    assert (result["numa"].numa_unverified, result["plain"].numa_unverified) == (True, False)
    # NUMA keys add nothing to Placement; the audio function is its own same-tree request group.
    assert cloud.candidate_queries() == [
        {
            "resources": "VCPU:1,MEMORY_MB:1",
            "resources_PCI0": f"{AUDIO_RC}:1",
            "resources_PCI1": f"{GPU_RC}:1",
            "group_policy": "none",
            "root_required": "!COMPUTE_STATUS_DISABLED",
        }
    ]

    cloud.usages[ROOT_A]["VCPU"] = 44  # 4 of 48 schedulable vCPUs left: no NUMA cell can fit 8 either
    short = (await evaluate(numa))["numa"]
    assert observed(short) == ("insufficient", 0, "VCPU", 4, 87125)


async def test_cpu_info_capability_matches_the_hypervisor_like_nova(cloud):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0))
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.hypervisor(ROOT_A)["cpu_info"] = {"arch": "x86_64", "vendor": "AMD"}
    cloud.hypervisor(ROOT_B)["cpu_info"] = {"arch": "aarch64", "vendor": "ARM"}
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE}), allocation({ROOT_A: ONE})]
    arch = flavor("arch", vcpus=2, ram=16384, specs={"capabilities:cpu_info:arch": "x86_64"}, name="cpu.2c_16g")

    # The roomier aarch64 host fails ComputeCapabilitiesFilter and never supplies the pair.
    assert observed((await evaluate(arch))["arch"]) == ("available", 1, "VCPU", 32, 65536)

    del cloud.hypervisor(ROOT_A)["cpu_info"]
    assert (await evaluate(arch))["arch"].status == "unavailable"


async def test_multi_gpu_demand_counts_roots_and_requires_one_tree(cloud):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(131072, 0), gpus=[(GPU_A1, 0), (GPU_A2, 0)])
    cloud.add_host(ROOT_C, vcpu=(32, 8), ram=(131072, 0), gpus=[(GPU_C1, 0), (GPU_C2, 0)])
    cloud.answers[shape("VCPU:1,MEMORY_MB:1", GPU_RC, GPU_RC)] = [
        allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}, GPU_A2: {GPU_RC: 1}}),
        allocation({ROOT_A: ONE, GPU_A2: {GPU_RC: 1}, GPU_A1: {GPU_RC: 1}}),
        allocation({ROOT_C: ONE, GPU_C1: {GPU_RC: 1}, GPU_C2: {GPU_RC: 1}}),
        allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}, GPU_C1: {GPU_RC: 1}}),
    ]
    two = flavor("gpu2", vcpus=16, ram=32768, specs={"pci_passthrough:alias": "RTX_3090_Ti:2"}, name="gpu.3090tix2")

    first = (await evaluate(two))["gpu2"]

    assert observed(first) == ("available", 2, "VCPU", 32, 131072)
    query = cloud.candidate_queries()[0]
    assert (query["resources_PCI0"], query["resources_PCI1"], query["group_policy"]) == (
        f"{GPU_RC}:1",
        f"{GPU_RC}:1",
        "none",
    )

    cloud.usages[GPU_C2][GPU_RC] = 1
    assert (await evaluate(two))["gpu2"].candidate_hosts == 1


def _disable_service(cloud):
    cloud.service(ROOT_A)["status"] = "disabled"


def _down_service(cloud):
    cloud.service(ROOT_A)["state"] = "down"


def _force_down(cloud):
    cloud.service(ROOT_A)["forced_down"] = True


def _disable_hypervisor(cloud):
    cloud.hypervisor(ROOT_A)["status"] = "disabled"


def _move_zone(cloud):
    cloud.service(ROOT_A)["zone"] = "other-zone"
    cloud.aggregate(ROOT_A)["availability_zone"] = "other-zone"


def _mismatch_aggregate(cloud):
    cloud.aggregate(ROOT_A)["metadata"]["gpu"] = "a100"


def _multi_value_aggregate(cloud):
    cloud.aggregate(ROOT_A)["metadata"]["gpu"] = " a100 , rtx3090ti "


def _isolate_other_tenant(cloud):
    cloud.aggregate(ROOT_A)["metadata"]["filter_tenant_id"] = "other-project,third-project"


def _isolate_this_tenant(cloud):
    cloud.aggregate(ROOT_A)["metadata"]["filter_tenant_id"] = f"other-project,{PROJECT}"


@pytest.mark.parametrize(
    ("mutate", "zone", "expected"),
    [
        (None, ZONE, "available"),
        (_disable_service, ZONE, "insufficient"),
        (_down_service, ZONE, "insufficient"),
        (_force_down, ZONE, "insufficient"),
        (_disable_hypervisor, ZONE, "insufficient"),
        (_move_zone, ZONE, "insufficient"),
        (_move_zone, None, "available"),
        (_mismatch_aggregate, ZONE, "insufficient"),
        (_multi_value_aggregate, ZONE, "available"),
        (_isolate_other_tenant, ZONE, "insufficient"),
        (_isolate_this_tenant, ZONE, "available"),
    ],
    ids=[
        "eligible",
        "disabled",
        "down",
        "forced-down",
        "hypervisor-disabled",
        "other-az",
        "no-requested-az",
        "aggregate-spec",
        "aggregate-multiple-values",
        "tenant-isolated",
        "tenant-member",
    ],
)
async def test_compute_service_zone_and_aggregate_filters(cloud, mutate, zone, expected):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 0)])
    cloud.aggregate(ROOT_A)["metadata"]["gpu"] = "rtx3090ti"
    cloud.answers[GPU_SHAPE] = [allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}})]
    if mutate is not None:
        mutate(cloud)
    gpu = flavor("gpu", specs={**GPU_SPECS, "aggregate_instance_extra_specs:gpu": "rtx3090ti"}, name="gpu.3090ti_4c")

    capacity = (await evaluate(gpu, zone=zone))["gpu"]

    assert capacity.status == expected
    assert capacity.candidate_hosts == (1 if expected == "available" else 0)


def _drop_hypervisors(cloud):
    cloud.hypervisors.clear()


def _drop_services(cloud):
    cloud.services.clear()


def _rename_service_host(cloud):
    cloud.hypervisor(ROOT_A)["service"]["host"] = "renamed-node"


def _conflicting_zones(cloud):
    cloud.aggregates.append(
        {
            "id": 99,
            "name": "second-az",
            "availability_zone": "other-zone",
            "hosts": [HOST_NAMES[ROOT_A]],
            "metadata": {},
        }
    )


@pytest.mark.parametrize("mutate", [_drop_hypervisors, _drop_services, _rename_service_host, _conflicting_zones])
async def test_unmappable_candidate_root_is_unavailable_not_insufficient(cloud, mutate):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 0)])
    cloud.answers[GPU_SHAPE] = [allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}})]
    mutate(cloud)

    capacity = (await evaluate(flavor("gpu", specs=GPU_SPECS, name="gpu.3090ti_4c")))["gpu"]

    assert observed(capacity) == ("unavailable", 0, "VCPU", None, None)


@pytest.mark.parametrize(
    ("name", "specs"),
    [
        ("gpu.mystery", {"pci_passthrough:alias": "mystery_gpu:1"}),
        ("gpu.3090ti_bad", {"pci_passthrough:alias": "rtx3090ti:two"}),
        ("gpu.3090ti_nocount", {"pci_passthrough:alias": "rtx3090ti"}),
        ("gpu.3090ti_noalias", {}),
        ("m1.mixed", {"hw:cpu_policy": "mixed", "hw:cpu_dedicated_mask": "0-1"}),
        ("m1.numa", {"hw:numa_nodes": "2"}),
        ("m1.numa-zero", {"hw:numa_nodes": "0"}),
        ("m1.hugepages", {"hw:mem_page_size": "large"}),
        ("m1.page-1g", {"hw:mem_page_size": "1GB"}),
        ("m1.granular", {"resources1:VGPU": "1"}),
        ("m1.operator", {"aggregate_instance_extra_specs:gpu": "<in> 3090"}),
        ("m1.conflict", {"hw:cpu_policy": "dedicated", "resources:PCPU": "4"}),
        ("m1.capabilities", {"capabilities:hypervisor_type": "QEMU"}),
        ("m1.capability-op", {"capabilities:cpu_info:arch": "s== x86_64"}),
        ("m1.pci-class", {"resources:CUSTOM_PCI_10DE_2203": "1"}),
        ("m1.trait", {"trait:custom_lowercase": "required"}),
    ],
)
async def test_unrepresentable_flavor_demand_fails_closed_per_flavor(cloud, name, specs):
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]

    result = await evaluate(
        flavor("odd", vcpus=2, ram=2048, specs=specs, name=name), flavor("plain", vcpus=2, ram=2048)
    )

    assert observed(result["odd"]) == ("unavailable", 0, None, None, None)
    assert result["plain"].status == "available"
    assert [q["resources"] for q in cloud.candidate_queries()] == ["VCPU:1,MEMORY_MB:1"]


@pytest.mark.parametrize(
    "aliases,valid_alias",
    [
        ("rtx3090ti:999999999", None),
        ("rtx3090ti:9,GA102-audio:8", "rtx3090ti"),
    ],
)
def test_pci_count_rejected_before_over_budget_catalog_work(aliases, valid_alias):
    class BoundedCatalog:
        def resource_class(self, alias):
            if alias == valid_alias:
                return GPU_RC
            raise MemoryError("over-budget expansion must never start")

    with pytest.raises(flavor_capacity._Unsupported):
        flavor_capacity._parse_pci_aliases(aliases, BoundedCatalog())


async def test_ambiguous_catalog_alias_fails_closed(cloud, monkeypatch):
    nvidia = dict(gpu_inventory.PCI_DEVICE_MAP["10DE"])
    nvidia["2299"] = {"name": "RTX 3090 Ti Clone", "is_audio": False, "aliases": ["RTX3090Ti"]}
    monkeypatch.setitem(gpu_inventory.PCI_DEVICE_MAP, "10DE", nvidia)
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 0)])

    result = await evaluate(flavor("gpu", specs={"pci_passthrough:alias": "RTX3090Ti:1"}, name="gpu.3090ti_4c"))

    assert result["gpu"].status == "unavailable"
    assert cloud.candidate_queries() == []


async def test_unknown_resource_class_is_unavailable_but_exhausted_class_is_insufficient(cloud, monkeypatch):
    nvidia = dict(gpu_inventory.PCI_DEVICE_MAP["10DE"])
    nvidia["FFFF"] = {"name": "Mystery GPU", "is_audio": False, "aliases": ["MYSTERY"]}
    monkeypatch.setitem(gpu_inventory.PCI_DEVICE_MAP, "10DE", nvidia)
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 1)])

    result = await evaluate(
        flavor("mystery", specs={"pci_passthrough:alias": "MYSTERY:1"}, name="gpu.mystery_4c"),
        flavor("busy", specs=GPU_SPECS, name="gpu.3090ti_4c"),
    )

    # A class Placement has never heard of is a mapping problem (확인 불가), not "no free host".
    assert result["mystery"].status == "unavailable"
    assert observed(result["busy"]) == ("insufficient", 0, "VCPU", None, None)


EXPLAINED = allocation({ROOT_A: ONE, GPU_A1: {GPU_RC: 1}})
NEGATIVE_SUMMARY = json.dumps(
    {
        "allocation_requests": [EXPLAINED],
        "provider_summaries": {
            ROOT_A: {"resources": {"VCPU": {"capacity": 32, "used": -1}, "MEMORY_MB": {"capacity": 65536, "used": 0}}},
            GPU_A1: {"resources": {GPU_RC: {"capacity": 1, "used": 0}}},
        },
    }
).encode()


@pytest.mark.parametrize(
    ("path", "status", "content", "discards_session"),
    [
        ("/compute/v2.1/os-services", 403, b'{"forbidden": {"code": 403}}', True),
        ("/compute/v2.1/os-hypervisors/detail", 500, b'{"computeFault": {"code": 500}}', True),
        ("/compute/v2.1/os-aggregates", 200, b'{"aggregates": {}}', True),
        ("/placement/resource_providers", 503, b'{"errors": [{"status": 503}]}', True),
        ("/placement/allocation_candidates", 200, b"not json", False),
        ("/placement/allocation_candidates", 204, b"", False),
        ("/placement/allocation_candidates", 200, NEGATIVE_SUMMARY, False),
        (f"/placement/resource_providers/{ROOT_A}/inventories", 404, b'{"errors": [{"status": 404}]}', False),
    ],
)
async def test_authority_failures_are_unavailable(cloud, path, status, content, discards_session):
    cloud.add_host(ROOT_A, vcpu=(32, 0), ram=(65536, 0), gpus=[(GPU_A1, 0)])
    cloud.answers[GPU_SHAPE] = [EXPLAINED]
    cloud.failures[path] = (status, content)

    capacity = (await evaluate(flavor("gpu", specs=GPU_SPECS, name="gpu.3090ti_4c")))["gpu"]

    assert (capacity.status, capacity.candidate_hosts, capacity.remaining_vcpus, capacity.remaining_ram_mb) == (
        "unavailable",
        0,
        None,
        None,
    )
    # A snapshot-level failure drops the shared operator session so the next call re-authenticates.
    assert (cloud.opened, cloud.closed) == (1, 1 if discards_session else 0)


async def test_operator_session_is_replaced_after_a_snapshot_failure(cloud):
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cloud.failures["/compute/v2.1/os-services"] = (401, b'{"error": {"code": 401}}')
    cpu = flavor("cpu", vcpus=2, ram=2048)

    assert (await evaluate(cpu))["cpu"].status == "unavailable"

    del cloud.failures["/compute/v2.1/os-services"]
    assert (await evaluate(cpu))["cpu"].status == "available"
    assert (cloud.opened, cloud.closed) == (2, 1)


async def test_discovery_shares_a_single_flight_snapshot_but_admission_reads_fresh(cloud, monkeypatch):
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cpu = flavor("cpu", vcpus=8, ram=8192)

    first, second = await asyncio.gather(evaluate(cpu, fresh=False), evaluate(cpu, fresh=False))
    assert first["cpu"].status == second["cpu"].status == "available"
    assert len(cloud.candidate_queries()) == 1  # concurrent wizard polls share one Placement snapshot

    cloud.usages[ROOT_B]["VCPU"] = 60  # 4 vCPUs left
    assert (await evaluate(cpu, fresh=False))["cpu"].status == "available"  # still within the snapshot TTL
    assert (await evaluate(cpu))["cpu"].status == "insufficient"  # create admission never uses that snapshot

    monkeypatch.setattr(flavor_capacity, "_SNAPSHOT_TTL_SECONDS", 0.0)
    assert (await evaluate(cpu, fresh=False))["cpu"].status == "insufficient"  # an expired snapshot is replaced


async def test_discovery_reuses_a_failed_shape_until_the_snapshot_expires(cloud, monkeypatch, caplog):
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.failures["/placement/allocation_candidates"] = (503, b'{"errors": [{"status": 503}]}')
    small, large = flavor("small", vcpus=2, ram=2048), flavor("large", vcpus=8, ram=8192)
    caplog.set_level(logging.WARNING, logger=flavor_capacity.__name__)

    for _ in range(3):  # wizard polls during a Placement outage
        result = await evaluate(small, large, fresh=False)
        assert {capacity.status for capacity in result.values()} == {"unavailable"}
    assert len(cloud.candidate_queries()) == 1  # one failed shape query, not one per flavor per poll
    # Polls must not flood the log either: one line for the failed shape, without a traceback.
    logged = [record for record in caplog.records if record.name == flavor_capacity.__name__]
    assert [(record.levelno, record.exc_info) for record in logged] == [(logging.WARNING, None)]
    assert "HTTP 503" in logged[0].getMessage()

    del cloud.failures["/placement/allocation_candidates"]
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    monkeypatch.setattr(flavor_capacity, "_SNAPSHOT_TTL_SECONDS", 0.0)
    assert (await evaluate(small, fresh=False))["small"].status == "available"


async def test_stalled_placement_returns_unavailable_within_the_deadline(cloud, monkeypatch):
    monkeypatch.setattr(flavor_capacity, "_REQUEST_TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(flavor_capacity, "_DEADLINE_SECONDS", 0.5)
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cloud.stalls["/placement/allocation_candidates"] = 30.0
    started = time.monotonic()

    result = await evaluate(flavor("cpu", vcpus=2, ram=2048))

    assert result["cpu"].status == "unavailable"
    assert time.monotonic() - started < 2.0


async def test_equal_demands_share_one_query_and_response_hides_identifiers(cloud):
    cloud.add_host(ROOT_A, vcpu=(32, 4), ram=(65536, 0), gpus=[(GPU_A1, 0), (GPU_A2, 1)])
    cloud.answers[GPU_SHAPE] = [EXPLAINED]
    first = flavor(
        "gpu-a",
        specs={"pci_passthrough:alias": "rtx3090ti:1", "afterglow:frontend_visible": "true"},
        name="gpu.3090ti_a",
    )
    second = flavor("gpu-b", specs={"pci_passthrough:alias": "RTX_3090_Ti:1"}, name="gpu.3090ti_b")

    result = await evaluate(first, second)

    assert result["gpu-a"] == result["gpu-b"]
    assert observed(result["gpu-a"]) == ("available", 1, "VCPU", 28, 65536)
    assert len(cloud.candidate_queries()) == 1
    payload = json.dumps({key: value.model_dump() for key, value in result.items()})
    for identifier in (ROOT_A, GPU_A1, GPU_A2, *HOST_NAMES.values(), PROJECT, "svc-"):
        assert identifier not in payload
    assert set(result["gpu-a"].model_dump()) == {
        "status",
        "checked_at",
        "candidate_hosts",
        "cpu_resource_class",
        "remaining_vcpus",
        "remaining_ram_mb",
        "numa_unverified",
    }


async def test_boot_from_volume_ignores_flavor_disk_but_honors_explicit_disk(cloud):
    cloud.add_host(ROOT_B, vcpu=(64, 0), ram=(262144, 0))
    cloud.inventories[ROOT_B]["DISK_GB"] = inventory(50)
    cloud.usages[ROOT_B]["DISK_GB"] = 40
    cloud.answers[CPU_SHAPE] = [allocation({ROOT_B: ONE})]
    cloud.answers[shape("VCPU:1,MEMORY_MB:1,DISK_GB:20")] = [allocation({ROOT_B: {**ONE, "DISK_GB": 20}})]

    result = await evaluate(
        flavor("bfv", vcpus=2, ram=2048),
        flavor("scratch", vcpus=2, ram=4096, specs={"resources:DISK_GB": "20"}),
    )

    assert result["bfv"].status == "available"
    assert result["scratch"].status == "insufficient"
    assert sorted(q["resources"] for q in cloud.candidate_queries()) == [
        "VCPU:1,MEMORY_MB:1",
        "VCPU:1,MEMORY_MB:1,DISK_GB:20",
    ]
