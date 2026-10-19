"""Behavioral collector regressions against deterministic Gnocchi REST replies.

No real cloud, credentials, elapsed sleeps, source-text or wiring assertions.
Transport fixtures model documented resources, named metrics, archive policies,
ISO/granularity/value measures and marker pagination, including hostile replies.
"""

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit

import pytest

from app.services import native_telemetry as native

BASE = 1_791_936_000
PROJECT = "45ff6933aabc422cbbeb52a548093d90"
INSTANCE = "b28659f3-b102-46de-a805-cf535430e5e8"
OTHER = "bc83ef8b-8a2e-4a55-bc8b-927f1ca96ad5"
RANGE = {"start_ts": BASE, "end_ts": BASE + 1800, "step_s": 300}
SECRET = "https://private.example/token=never-expose"


def iso(offset):
    return datetime.fromtimestamp(BASE + offset, UTC).isoformat()


class Response:
    def __init__(self, value=None, status=200, raw=None):
        self.status_code = status
        self.raw = raw if raw is not None else json.dumps(value).encode()
        self.closed = False

    def iter_content(self, chunk_size):
        for index in range(0, len(self.raw), chunk_size):
            yield self.raw[index : index + chunk_size]

    def close(self):
        self.closed = True


class Cloud:
    def __init__(self):
        self.endpoint = "https://gnocchi.example/v1/"
        self.rows, self.metadata, self.measures, self.overrides = {}, {}, {}, {}
        self.calls, self.responses, self.discovery = [], [], []
        self.page_size = 32
        self.conn = SimpleNamespace(
            config=SimpleNamespace(get_interface=lambda _: "internal", get_region_name=lambda _: "region-a"),
            session=self,
            _afterglow_authenticated_project_id=PROJECT,
        )
        self.server = SimpleNamespace(id=INSTANCE, project_id=PROJECT)

    def get_endpoint(self, **kwargs):
        self.discovery.append(kwargs)
        return self.endpoint

    def resource(self, kind="instance", resource_id=INSTANCE, project=PROJECT, **attributes):
        row = {"id": resource_id, "project_id": project, "type": kind, "metrics": {}, **attributes}
        self.rows.setdefault(kind, []).append(row)
        return row

    def meter(self, row, name, unit, values, granularity=300, policy=None):
        row["metrics"][name] = f"metric-{row['id']}-{name}"
        path = f"/resource/{row['type']}/{row['id']}/metric/{name}"
        self.metadata[path] = {
            "id": row["metrics"][name],
            "unit": unit,
            "archive_policy": policy
            or {
                "aggregation_methods": ["mean", "rate:mean"],
                "definition": [{"granularity": granularity, "timespan": "30 days, 0:00:00"}],
            },
        }
        self.measures[path + "/measures"] = [[iso(ts), granularity, value] for ts, value in values]
        return path

    def request(self, url, method, **kwargs):
        path = unquote(urlsplit(url).path.removeprefix("/v1"))
        self.calls.append((method, path, kwargs))
        override = self.overrides.get((method, path))
        if override is not None:
            result = override(kwargs) if callable(override) else override
            if isinstance(result, Exception):
                raise result
            response = result if isinstance(result, Response) else Response(result)
        elif path.endswith("/measures"):
            # Leave response validation/range filtering to the collector, also
            # allowing malformed timestamps to reach the intended boundary.
            response = Response(self.measures.get(path, []))
        elif path in self.metadata:
            response = Response(self.metadata[path])
        elif path.startswith("/search/resource/") or (path.startswith("/resource/") and path.count("/") == 2):
            kind = path.rsplit("/", 1)[-1]
            rows = sorted(self.rows.get(kind, []), key=lambda row: row["id"])
            params = kwargs["params"]
            marker = params.get("marker")
            # Intentionally do not enforce search filters in the fixture: the
            # collector must recheck ownership on every received object.
            index = next((i + 1 for i, row in enumerate(rows) if row["id"] == marker), 0) if marker else 0
            response = Response(rows[index : index + min(params["limit"], self.page_size)])
        else:
            parts = path.split("/")
            row = next((row for row in self.rows.get(parts[2], []) if row["id"] == parts[3]), None)
            response = Response(row, 200 if row else 404)
        self.responses.append(response)
        return response


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setattr(native.time, "time", lambda: BASE + 3600)
    return Cloud()


async def instance(cloud, keys, **kwargs):
    return await native.instance_series(cloud.conn, cloud.server, keys, **(RANGE | kwargs))


@pytest.mark.asyncio
async def test_cpu_ns_per_elapsed_and_historical_vcpus_reset_gap_and_order(cloud):
    row = cloud.resource()
    values = [(0, 0), (300, 300e9), (600, 100e9), (900, 400e9), (1500, 700e9), (1800, 1000e9)]
    cloud.meter(row, "cpu", "ns", list(reversed(values)))
    cloud.meter(row, "vcpus", "vcpu", [(ts, 2) for ts, _ in values])
    result = (await instance(cloud, ["cpu"]))["cpu"]
    assert result["series"] == [{"ts": BASE + ts, "value": 50.0} for ts in (300, 900, 1800)]
    assert result["status"] == "partial"
    assert result["unit"] == "%"
    assert result["source"] == "gnocchi"


@pytest.mark.asyncio
async def test_true_zero_is_available_not_empty(cloud):
    row = cloud.resource()
    cloud.meter(row, "cpu", "ns", [(0, 10e9), (300, 10e9)])
    cloud.meter(row, "vcpus", "vcpu", [(0, 2), (300, 2)])
    cloud.meter(row, "memory.usage", "MiB", [])
    result = await instance(cloud, ["cpu", "memory", "gpu_util"])
    assert result["cpu"]["series"] == [{"ts": BASE + 300, "value": 0.0}]
    assert result["cpu"]["status"] == "available"
    for key in ("memory", "gpu_util"):
        assert result[key]["series"] == []
        assert result[key]["status"] == "not_collected"
        assert result[key]["source"] == "gnocchi"


@pytest.mark.asyncio
async def test_memory_guest_usage_uses_historical_allocated_not_host_resident(cloud):
    row = cloud.resource()
    cloud.meter(row, "memory.usage", "MiB", [(0, 128), (300, 128)])
    cloud.meter(row, "memory", "MiB", [(0, 256), (300, 512)])
    cloud.meter(row, "memory.resident", "MiB", [(0, 9000), (300, 8000)])
    result = await instance(cloud, ["memory", "memory_allocated", "memory_resident"])
    assert [p["value"] for p in result["memory"]["series"]] == [50, 25]
    assert [p["value"] for p in result["memory_resident"]["series"]] == [9000, 8000]
    assert result["memory_allocated"]["unit"] == "MiB"
    assert result["memory"]["status"] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("capacity", [None, 0])
async def test_missing_or_zero_denominator_never_uses_current_flavor(cloud, capacity):
    row = cloud.resource()
    cloud.server.flavor = {"vcpus": 100, "ram": 100000}
    cloud.meter(row, "memory.usage", "MiB", [(0, 128)])
    cloud.meter(row, "cpu", "ns", [(0, 0), (300, 300e9)])
    if capacity is not None:
        cloud.meter(row, "memory", "MiB", [(0, capacity)])
        cloud.meter(row, "vcpus", "vcpu", [(0, capacity), (300, capacity)])
    result = await instance(cloud, ["cpu", "memory"])
    for metric in result.values():
        assert metric["series"] == []
        assert metric["error"] == "denominator_missing"
        assert metric["status"] == "partial"


@pytest.mark.asyncio
async def test_resize_interval_is_omitted_and_prior_denominator_baseline_is_read(cloud):
    row = cloud.resource()
    cloud.meter(row, "cpu", "ns", [(-300, 0), (0, 300e9), (300, 600e9), (600, 1200e9)])
    cloud.meter(row, "vcpus", "vcpu", [(-300, 2), (0, 2), (300, 4), (600, 4)])
    result = (await instance(cloud, ["cpu"]))["cpu"]
    assert result["series"] == [{"ts": BASE, "value": 50.0}, {"ts": BASE + 600, "value": 50.0}]
    assert result["status"] == "partial"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key,meter,kind,unit,output",
    [
        ("network_rx", "network.incoming.bytes", "instance_network_interface", "B", "B/s"),
        ("network_tx", "network.outgoing.bytes", "instance_network_interface", "B", "B/s"),
        ("network_rx_packets", "network.incoming.packets", "instance_network_interface", "packet", "packet/s"),
        ("network_tx_packets", "network.outgoing.packets", "instance_network_interface", "packet", "packet/s"),
        ("disk_read", "disk.device.read.bytes", "instance_disk", "B", "B/s"),
        ("disk_write", "disk.device.write.bytes", "instance_disk", "B", "B/s"),
        ("disk_read_iops", "disk.device.read.requests", "instance_disk", "request", "request/s"),
        ("disk_write_iops", "disk.device.write.requests", "instance_disk", "request", "request/s"),
        ("memory_swap_in", "memory.swap.in", "instance", "MiB", "MiB/s"),
        ("memory_swap_out", "memory.swap.out", "instance", "MiB", "MiB/s"),
    ],
)
async def test_real_native_counter_names_and_units(cloud, key, meter, kind, unit, output):
    parent = cloud.resource()
    row = parent if kind == "instance" else cloud.resource(kind, "child-a", instance_id=INSTANCE)
    cloud.meter(row, meter, unit, [(0, 10), (300, 610)])
    metric = (await instance(cloud, [key]))[key]
    assert metric["series"] == [{"ts": BASE + 300, "value": 2.0}]
    assert metric["unit"] == output
    assert metric["status"] == "available"


@pytest.mark.asyncio
async def test_gauge_allocation_is_not_guest_filesystem_and_gpu_must_be_instance_attributed(cloud):
    row = cloud.resource()
    disk = cloud.resource("instance_disk", "disk-a", instance_id=INSTANCE)
    cloud.meter(disk, "disk.device.allocation", "B", [(0, 8192)])
    cloud.meter(row, "gpu.utilization", "%", [(0, 99)])
    result = await instance(cloud, ["disk_allocation", "storage", "gpu_util", "gpu_mem"])
    assert result["disk_allocation"]["series"] == [{"ts": BASE, "value": 8192.0}]
    assert result["storage"]["series"] == []
    assert result["gpu_util"]["series"] == []
    cloud.meter(row, "vgpu.utilization", "%", [(0, 0)])
    cloud.meter(row, "vgpu.memory.used", "MiB", [(0, 256)])
    cloud.meter(row, "vgpu.memory.total", "MiB", [(0, 1024)])
    result = await instance(cloud, ["gpu_util", "gpu_mem"])
    assert result["gpu_util"]["series"] == [{"ts": BASE, "value": 0.0}]
    assert result["gpu_mem"]["series"] == [{"ts": BASE, "value": 25.0}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        {"project_id": "other-project"},
        {"project_id": None},
        {"id": OTHER},
        {"type": "volume"},
    ],
)
async def test_parent_resource_ownership_fails_closed_before_measures(cloud, change):
    cloud.resource()
    cloud.overrides[("GET", f"/resource/instance/{INSTANCE}")] = {
        "id": INSTANCE,
        "project_id": PROJECT,
        "type": "instance",
        "metrics": {},
        **change,
    }
    metric = (await instance(cloud, ["memory"]))["memory"]
    assert metric["status"] == "forbidden"
    assert metric["series"] == []
    assert len(cloud.calls) == 1


@pytest.mark.asyncio
async def test_arbitrary_project_ids_do_not_compare_like_uuid_spellings(cloud):
    cloud.server.project_id = "project-one"
    cloud.resource(project="projectone")
    assert (await instance(cloud, ["cpu"]))["cpu"]["status"] == "forbidden"


@pytest.mark.asyncio
async def test_uuid_project_spelling_is_canonicalized(cloud):
    cloud.resource(project="45ff6933-aabc-422c-bbeb-52a548093d90")
    assert (await instance(cloud, ["cpu"]))["cpu"]["status"] == "not_collected"


@pytest.mark.asyncio
async def test_child_project_and_instance_ownership_checked_and_totals_partial(cloud):
    cloud.resource()
    good = cloud.resource("instance_network_interface", "good", instance_id=INSTANCE)
    foreign = cloud.resource("instance_network_interface", "foreign", project="other", instance_id=INSTANCE)
    wrong_parent = cloud.resource("instance_network_interface", "wrong-parent", instance_id=OTHER)
    missing_parent = cloud.resource("instance_network_interface", "missing-parent")
    for row in (good, foreign, wrong_parent, missing_parent):
        cloud.meter(row, "network.incoming.bytes", "B", [(0, 0), (300, 3000)])
    result = (await instance(cloud, ["network_rx"]))["network_rx"]
    assert result["series"] == [{"ts": BASE + 300, "value": 10.0}]
    assert result["status"] == "partial"
    assert result["error"] == "ownership_mismatch"
    measure_calls = [path for _, path, _ in cloud.calls if "/metric/" in path]
    assert all("/good/" in path for path in measure_calls)
    search = next(options for method, path, options in cloud.calls if path.startswith("/search/"))
    assert search["json"] == {"and": [{"=": {"project_id": PROJECT}}, {"=": {"instance_id": INSTANCE}}]}


@pytest.mark.asyncio
async def test_missing_child_and_misaligned_child_times_never_become_exact_total(cloud):
    cloud.resource()
    first = cloud.resource("instance_disk", "a", instance_id=INSTANCE)
    second = cloud.resource("instance_disk", "b", instance_id=INSTANCE)
    cloud.meter(first, "disk.device.read.requests", "request", [(0, 0), (300, 300), (600, 600)])
    cloud.meter(second, "disk.device.read.requests", "request", [(300, 0), (600, 600)])
    result = (await instance(cloud, ["disk_read_iops"]))["disk_read_iops"]
    assert result["series"] == [{"ts": BASE + 300, "value": 1.0}, {"ts": BASE + 600, "value": 3.0}]
    assert result["status"] == "partial"
    second["metrics"].clear()
    result = (await instance(cloud, ["disk_read_iops"]))["disk_read_iops"]
    assert result["status"] == "partial"
    assert [p["value"] for p in result["series"]] == [1, 1]


@pytest.mark.asyncio
async def test_project_pagination_follows_markers_even_when_server_clamps_limit(cloud):
    cloud.page_size = 1
    first = cloud.resource()
    second = cloud.resource(resource_id=OTHER)
    for row, vcpus in ((first, 2), (second, 8)):
        cloud.meter(row, "vcpus", "vcpu", [(0, vcpus)])
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert set(result["instances"]) == {INSTANCE, OTHER}
    assert result["status"] == "available"
    assert result["truncated"] is False
    assert result["instances"][OTHER]["vcpus"]["series"][0]["value"] == 8
    searches = [options for _, path, options in cloud.calls if path == "/search/resource/instance"]
    assert len(searches) == 3  # Includes an empty terminal page, not len<limit guessing.
    assert all(options["json"] == {"=": {"project_id": PROJECT}} for options in searches)
    assert searches[1]["params"]["marker"] == sorted([INSTANCE, OTHER])[0]


@pytest.mark.asyncio
async def test_project_excludes_foreign_instances_and_children_without_data_leak(cloud):
    own = cloud.resource()
    foreign = cloud.resource(resource_id=OTHER, project="foreign-project", secret=SECRET)
    for row in (own, foreign):
        cloud.meter(row, "vcpus", "vcpu", [(0, 2)])
    child = cloud.resource(
        "instance_network_interface", "foreign-child", project="foreign-project", instance_id=INSTANCE
    )
    cloud.meter(child, "network.incoming.bytes", "B", [(0, 0), (300, 300)])
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus", "network_rx"], **RANGE)
    assert set(result["instances"]) == {INSTANCE}
    assert result["status"] == "partial"
    assert "foreign-project" not in json.dumps(result)
    assert SECRET not in json.dumps(result)
    assert all(OTHER not in path and "foreign-child" not in path for _, path, _ in cloud.calls if "/metric/" in path)


@pytest.mark.asyncio
async def test_page_budget_and_stalled_pagination_are_finite_and_partial(cloud, monkeypatch):
    monkeypatch.setattr(native, "_MAX_PAGES", 2)
    cloud.page_size = 1
    for name in ("a", "b", "c"):
        row = cloud.resource(resource_id=name)
        cloud.meter(row, "vcpus", "vcpu", [(0, 1)])
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert set(result["instances"]) == {"a", "b"}
    assert result["truncated"] and result["status"] == "partial"
    assert result["error"] == "page_budget"
    cloud.overrides[("POST", "/search/resource/instance")] = [cloud.rows["instance"][0]]
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert result["truncated"] and result["error"] == "pagination_stalled"


@pytest.mark.asyncio
async def test_second_page_forbidden_preserves_authorized_first_page_with_partial_status(cloud):
    row = cloud.resource()
    cloud.meter(row, "vcpus", "vcpu", [(0, 2)])
    cloud.overrides[("POST", "/search/resource/instance")] = lambda options: (
        Response({"error": SECRET}, 403) if options["params"].get("marker") else [row]
    )
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert result["status"] == "partial"
    assert result["error"] == "access_denied"
    assert result["instances"][INSTANCE]["vcpus"]["series"][0]["value"] == 2
    assert SECRET not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,expected",
    [
        (401, "forbidden"),
        (403, "forbidden"),
        (404, "not_collected"),
        (429, "unavailable"),
        (503, "unavailable"),
        (302, "unavailable"),
    ],
)
async def test_native_http_failure_codes_are_safe_and_not_zero(cloud, status, expected):
    cloud.overrides[("GET", f"/resource/instance/{INSTANCE}")] = Response({"error": SECRET}, status)
    result = await instance(cloud, ["cpu"])
    assert result["cpu"]["status"] == expected
    assert result["cpu"]["series"] == []
    assert SECRET not in json.dumps(result)
    assert len(cloud.calls) == 1
    assert all(response.closed for response in cloud.responses)


@pytest.mark.asyncio
async def test_catalog_absent_vs_transport_failed_are_distinct_and_uncached(cloud):
    cloud.endpoint = None
    missing = (await instance(cloud, ["cpu"]))["cpu"]
    assert missing["status"] == "not_configured" and missing["source"] is None
    cloud.endpoint = "https://gnocchi.example/v1"
    cloud.resource()
    cloud.overrides[("GET", f"/resource/instance/{INSTANCE}")] = RuntimeError(SECRET)
    failed = (await instance(cloud, ["cpu"]))["cpu"]
    assert failed["status"] == "unavailable" and failed["source"] == "gnocchi"
    assert failed["error"] == "request_failed"
    assert SECRET not in json.dumps(failed)
    assert cloud.discovery[-1] == {
        "service_type": "metric",
        "interface": "internal",
        "region_name": "region-a",
        "skip_discovery": True,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": "object"},
        [["bad-date", 300, 1]],
        [[iso(0), 300, None]],
        [[iso(0), 300, True]],
        [[iso(0), 300, float("nan")]],
        [[iso(0), 300, -1]],
    ],
)
async def test_malformed_measure_replies_are_empty_not_zero_and_do_not_raise(cloud, payload):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "MiB", [])
    cloud.overrides[("GET", path + "/measures")] = payload
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["series"] == []
    assert result["status"] in ("unavailable", "partial")


@pytest.mark.asyncio
async def test_duplicate_and_bad_points_do_not_corrupt_remaining_real_measurements(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "MiB", [(0, 1), (300, 0), (600, 3)])
    cloud.measures[path + "/measures"].extend([[iso(0), 300, 5], ["nonsense", 300, 8]])
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["series"] == [{"ts": BASE + 300, "value": 0.0}, {"ts": BASE + 600, "value": 3.0}]
    assert result["status"] == "partial"


@pytest.mark.asyncio
async def test_wrong_units_and_unsupported_aggregation_never_silently_convert(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "B", [(0, 1024)])
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "unit_mismatch" and result["series"] == []
    cloud.metadata[path]["unit"] = "MiB"
    cloud.metadata[path]["archive_policy"]["aggregation_methods"] = ["max"]
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "aggregation_missing" and result["series"] == []


@pytest.mark.asyncio
async def test_archive_granularity_uses_actual_default_and_retention_not_requested_step(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "MiB", [(0, 1)])
    cloud.metadata[path]["archive_policy"]["definition"] = [
        {"granularity": "0:01:00", "timespan": "0:15:00"},
        {"granularity": "0:05:00", "timespan": "30 days, 0:00:00"},
    ]
    result = (await instance(cloud, ["memory_resident"], step_s=60))["memory_resident"]
    assert result["series"] == [{"ts": BASE, "value": 1.0}]
    measure_request = next(options for _, path, options in cloud.calls if path.endswith("/measures"))
    assert measure_request["params"]["granularity"] == 300
    assert measure_request["params"]["aggregation"] == "mean"


@pytest.mark.asyncio
async def test_response_request_and_sample_budgets_are_enforced(cloud, monkeypatch):
    row = cloud.resource()
    cloud.meter(row, "memory.resident", "MiB", [(0, 0), (300, 1), (600, 2)])
    monkeypatch.setattr(native, "_MAX_BYTES", 10)
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "response_budget" and result["series"] == []
    monkeypatch.setattr(native, "_MAX_BYTES", 512 * 1024)
    monkeypatch.setattr(native, "_MAX_REQUESTS", 1)
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "request_budget" and result["series"] == []
    monkeypatch.setattr(native, "_MAX_REQUESTS", 96)
    monkeypatch.setattr(native, "_MAX_SAMPLES", 2)
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "sample_budget" and result["series"] == []
    assert all(response.closed for response in cloud.responses)
    assert all(
        options["timeout"] <= 1.5
        and options["stream"]
        and not options["redirect"]
        and not options["allow_reauth"]
        and options["connect_retries"] == options["status_code_retries"] == 0
        for _, _, options in cloud.calls
    )


@pytest.mark.asyncio
async def test_deadline_and_invalid_range_return_finite_safe_failures(cloud, monkeypatch):
    monkeypatch.setattr(native, "_DEADLINE_S", 0)
    result = (await instance(cloud, ["cpu"]))["cpu"]
    assert result["status"] == "unavailable" and result["error"] == "time_budget"
    monkeypatch.setattr(native, "_DEADLINE_S", 6)
    for invalid in ({"step_s": 0}, {"end_ts": BASE}, {"start_ts": -1}, {"step_s": True}, {"end_ts": BASE + 32 * 86400}):
        result = (await instance(cloud, ["cpu"], **invalid))["cpu"]
        assert result["error"] == "invalid_range"


@pytest.mark.asyncio
async def test_system_only_reads_whitelisted_host_storage_gauges_and_no_private_metadata(cloud):
    host = cloud.resource("nova_compute", "host-a", host_name="compute-a", secret=SECRET)
    storage = cloud.resource("volume_provider_pool", "pool-a", provider=SECRET)
    tenant_volume = cloud.resource("volume", "tenant-volume", display_name=SECRET)
    cloud.meter(host, "compute.node.cpu.percent", "%", [(0, 0), (300, 12)])
    cloud.meter(host, "private.internal.meter", "secret", [(0, 99)])
    cloud.meter(storage, "volume.provider.pool.capacity.free", "GiB", [(0, 120)])
    cloud.meter(tenant_volume, "volume.size", "GiB", [(0, 10000)])
    result = await native.system_series(cloud.conn, **RANGE)
    assert result["status"] == "available"
    assert [row["type"] for row in result["resources"]] == ["nova_compute", "volume_provider_pool"]
    assert result["resources"][0]["name"] == "compute-a"
    assert result["resources"][0]["metrics"]["compute.node.cpu.percent"]["series"][0]["value"] == 0
    assert result["resources"][1]["metrics"]["volume.provider.pool.capacity.free"]["unit"] == "GiB"
    assert SECRET not in json.dumps(result)
    assert all("private.internal.meter" not in path and "tenant-volume" not in path for _, path, _ in cloud.calls)


@pytest.mark.asyncio
async def test_system_partial_policy_and_absent_resource_types_do_not_hide_existing_data(cloud):
    host = cloud.resource("nova_compute", "host-a")
    cloud.meter(host, "compute.node.cpu.percent", "%", [(0, 20)])
    cloud.overrides[("GET", "/resource/ipmi")] = Response({"detail": SECRET}, 403)
    cloud.overrides[("GET", "/resource/volume_provider")] = Response({}, 404)
    result = await native.system_series(cloud.conn, **RANGE)
    assert result["status"] == "partial" and result["error"] == "access_denied"
    assert len(result["resources"]) == 1
    assert SECRET not in json.dumps(result)


@pytest.mark.asyncio
async def test_measure_access_denied_for_one_child_preserves_other_child_as_partial(cloud):
    cloud.resource()
    for name in ("a", "b"):
        child = cloud.resource("instance_disk", name, instance_id=INSTANCE)
        path = cloud.meter(child, "disk.device.read.bytes", "B", [(0, 0), (300, 3000)])
    cloud.overrides[("GET", path + "/measures")] = Response({"detail": SECRET}, 403)
    result = (await instance(cloud, ["disk_read"]))["disk_read"]
    assert result["series"] == [{"ts": BASE + 300, "value": 10.0}]
    assert result["status"] == "partial"
    assert SECRET not in json.dumps(result)


@pytest.mark.asyncio
async def test_async_cancellation_is_not_swallowed(cloud, monkeypatch):
    async def cancelled(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr(native.asyncio, "to_thread", cancelled)
    with pytest.raises(asyncio.CancelledError):
        await instance(cloud, ["cpu"])


@pytest.mark.asyncio
async def test_malformed_json_and_metadata_fail_per_metric_not_entire_instance(cloud):
    row = cloud.resource()
    good = cloud.meter(row, "memory.resident", "MiB", [(0, 7)])
    bad = cloud.meter(row, "memory.swap.in", "MiB", [(0, 0), (300, 300)])
    cloud.metadata[bad]["archive_policy"]["aggregation_methods"] = None
    result = await instance(cloud, ["memory_resident", "memory_swap_in"])
    assert result["memory_resident"]["series"] == [{"ts": BASE, "value": 7.0}]
    assert result["memory_swap_in"]["status"] == "unavailable"
    assert result["memory_swap_in"]["error"] == "malformed_response"
    cloud.overrides[("GET", good + "/measures")] = Response(raw=b"{broken-json")
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["error"] == "malformed_response" and result["series"] == []


@pytest.mark.asyncio
async def test_denominator_permission_failure_is_not_reported_as_real_usage(cloud):
    row = cloud.resource()
    cloud.meter(row, "memory.usage", "MiB", [(0, 20)])
    path = cloud.meter(row, "memory", "MiB", [(0, 100)])
    cloud.overrides[("GET", path)] = Response({"detail": SECRET}, 403)
    result = (await instance(cloud, ["memory"]))["memory"]
    assert result["series"] == [] and result["status"] == "forbidden"
    assert result["error"] == "access_denied"


@pytest.mark.asyncio
async def test_child_intervals_with_different_archive_granularities_are_partial(cloud):
    cloud.resource()
    first = cloud.resource("instance_disk", "a", instance_id=INSTANCE)
    second = cloud.resource("instance_disk", "b", instance_id=INSTANCE)
    cloud.meter(first, "disk.device.read.bytes", "B", [(0, 0), (300, 300)])
    cloud.meter(second, "disk.device.read.bytes", "B", [(0, 0), (600, 600)], granularity=600)
    result = (await instance(cloud, ["disk_read"]))["disk_read"]
    assert result["status"] == "partial" and result["error"] == "granularity_mismatch"


@pytest.mark.asyncio
async def test_resource_and_total_byte_budgets_report_truncated_coverage(cloud, monkeypatch):
    for name in ("a", "b"):
        row = cloud.resource(resource_id=name)
        cloud.meter(row, "vcpus", "vcpu", [(0, 1)])
    monkeypatch.setattr(native, "_MAX_RESOURCES", 1)
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert result["truncated"] and result["status"] == "partial"
    assert set(result["instances"]) == {"a"}
    monkeypatch.setattr(native, "_MAX_RESOURCES", 128)
    monkeypatch.setattr(native, "_MAX_TOTAL_BYTES", 1)
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert result["truncated"] and result["error"] == "response_budget"


@pytest.mark.asyncio
async def test_provider_cache_is_not_shared_across_callers_or_successive_calls(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "MiB", [(0, 1)])
    first = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    cloud.overrides[("GET", path)] = Response({"detail": SECRET}, 403)
    second = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert first["series"] == [{"ts": BASE, "value": 1.0}]
    assert second["status"] == "forbidden" and second["series"] == []


@pytest.mark.asyncio
async def test_signed_temperature_and_overcommitted_virtual_free_remain_actual_gauges(cloud):
    sensor = cloud.resource("ipmi", "sensor-a")
    pool = cloud.resource("volume_provider_pool", "pool-a")
    cloud.meter(sensor, "hardware.ipmi.node.temperature", "C", [(0, -5)])
    cloud.meter(pool, "volume.provider.pool.capacity.virtual_free", "GiB", [(0, -20)])
    result = await native.system_series(cloud.conn, **RANGE)
    assert result["status"] == "available"
    metrics = {name: metric for row in result["resources"] for name, metric in row["metrics"].items()}
    assert metrics["hardware.ipmi.node.temperature"]["series"] == [{"ts": BASE, "value": -5.0}]
    assert metrics["volume.provider.pool.capacity.virtual_free"]["series"] == [{"ts": BASE, "value": -20.0}]


@pytest.mark.asyncio
async def test_malformed_project_page_preserves_good_rows_and_reports_partial(cloud):
    row = cloud.resource()
    cloud.meter(row, "vcpus", "vcpu", [(0, 2)])
    cloud.overrides[("POST", "/search/resource/instance")] = lambda options: (
        {"not": "a-list"} if options["params"].get("marker") else [row]
    )
    result = await native.project_series(cloud.conn, PROJECT, ["vcpus"], **RANGE)
    assert result["status"] == "partial" and result["error"] == "malformed_response"
    assert result["instances"][INSTANCE]["vcpus"]["series"] == [{"ts": BASE, "value": 2.0}]


@pytest.mark.asyncio
async def test_current_child_disk_allocation_sums_owned_gauges_without_legacy_double_count(cloud):
    row = cloud.resource()
    cloud.meter(row, "disk.allocation", "B", [(0, 999999)])
    for name, value in (("a", 1024), ("b", 2048)):
        disk = cloud.resource("instance_disk", name, instance_id=INSTANCE)
        cloud.meter(disk, "disk.device.allocation", "B", [(0, value)])
    foreign = cloud.resource("instance_disk", "foreign", instance_id=OTHER)
    cloud.meter(foreign, "disk.device.allocation", "B", [(0, 888888)])
    result = (await instance(cloud, ["disk_allocation"]))["disk_allocation"]
    assert result["unit"] == "B"
    assert result["series"] == [{"ts": BASE, "value": 3072.0}]
    assert result["status"] == "partial" and result["error"] == "ownership_mismatch"
    assert all("/metric/disk.allocation" not in path for _, path, _ in cloud.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize("unit", ["%", "percent", None])
async def test_native_percent_spelling_normalizes_without_rescaling(cloud, unit):
    host = cloud.resource("nova_compute", "host-a")
    cloud.meter(host, "compute.node.cpu.percent", unit, [(0, 0), (300, 37.5)])
    result = await native.system_series(cloud.conn, **RANGE)
    metric = result["resources"][0]["metrics"]["compute.node.cpu.percent"]
    assert metric["unit"] == "%" and metric["status"] == "available"
    assert metric["series"] == [{"ts": BASE, "value": 0.0}, {"ts": BASE + 300, "value": 37.5}]


@pytest.mark.asyncio
async def test_stopped_resource_history_is_not_rejected_by_wall_clock_retention(cloud, monkeypatch):
    row = cloud.resource()
    cloud.meter(row, "memory.resident", "MiB", [(0, 11), (300, 12)])
    monkeypatch.setattr(native.time, "time", lambda: BASE + 365 * 86400)
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["status"] == "available"
    assert result["series"] == [{"ts": BASE, "value": 11.0}, {"ts": BASE + 300, "value": 12.0}]


@pytest.mark.asyncio
async def test_window_wider_than_archive_reads_retained_portion_as_partial(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.resident", "MiB", [])
    cloud.overrides[("GET", path + "/measures")] = lambda options: [
        [iso(30 * 86400), options["params"].get("resample", 300), 8]
    ]
    result = (await instance(cloud, ["memory_resident"], end_ts=BASE + 31 * 86400))["memory_resident"]
    assert result["series"] == [{"ts": BASE + 30 * 86400, "value": 8.0}]
    assert result["status"] == "partial" and result["error"] == "archive_coverage"


@pytest.mark.asyncio
async def test_default_fourteen_days_resamples_full_window_and_preserves_cpu_denominator(cloud):
    row = cloud.resource()
    length = 14 * 86400
    for meter, unit in (("cpu", "ns"), ("vcpus", "vcpu")):
        path = cloud.meter(row, meter, unit, [])

        def reply(options, meter=meter):
            params = options["params"]
            effective = params.get("resample", params["granularity"])
            timestamps = range(int(params["start"]), int(params["stop"]) + 1, int(effective))
            return [
                [
                    datetime.fromtimestamp(ts, UTC).isoformat(),
                    effective,
                    (ts - BASE + 1200) * 1e9 if meter == "cpu" else 2,
                ]
                for ts in timestamps
            ]

        cloud.overrides[("GET", path + "/measures")] = reply
    result = await instance(cloud, ["cpu", "vcpus"], end_ts=BASE + length)
    cpu = result["cpu"]
    assert cpu["status"] == "available"
    assert cpu["series"][0] == {"ts": BASE, "value": 50.0}
    assert cpu["series"][-1] == {"ts": BASE + length, "value": 50.0}
    assert len(cpu["series"]) <= native._MAX_SAMPLES
    assert all(point["value"] == 50.0 for point in cpu["series"])
    reads = [options["params"] for _, path, options in cloud.calls if path.endswith("/measures")]
    coarse = [params for params in reads if "resample" in params]
    fine = [params for params in reads if "resample" not in params]
    assert coarse and all(params["granularity"] == 300 and params["resample"] == 600 for params in coarse)
    assert all(params["stop"] == BASE + length for params in coarse)
    assert fine and all((params["stop"] - params["start"]) / 300 <= native._MAX_SAMPLES - 2 for params in fine)


@pytest.mark.asyncio
@pytest.mark.parametrize("fine", [[], [[iso(1500), 300, 999]]])
async def test_old_interval_uses_better_covered_coarse_archive_without_mixing_tiers(cloud, fine, monkeypatch):
    row = cloud.resource()
    path = cloud.meter(
        row,
        "memory.resident",
        "MiB",
        [],
        policy={
            "aggregation_methods": ["mean"],
            "definition": [{"granularity": 300, "timespan": 86400}, {"granularity": 600, "timespan": 30 * 86400}],
        },
    )
    coarse = [[iso(ts), 600, value] for ts, value in ((0, 7), (600, 8), (1200, 9), (1800, 10))]
    cloud.overrides[("GET", path + "/measures")] = lambda options: (
        fine if options["params"]["granularity"] == 300 else coarse
    )
    monkeypatch.setattr(native.time, "time", lambda: BASE + 90 * 86400)
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["status"] == "available"
    assert result["series"] == [
        {"ts": BASE + ts, "value": float(value)} for ts, value in ((0, 7), (600, 8), (1200, 9), (1800, 10))
    ]
    requests = [options["params"]["granularity"] for _, path, options in cloud.calls if path.endswith("/measures")]
    assert requests == [300, 600]


@pytest.mark.asyncio
async def test_advertised_archive_retry_fanout_is_bounded(cloud):
    row = cloud.resource()
    path = cloud.meter(
        row,
        "memory.resident",
        "MiB",
        [],
        policy={
            "aggregation_methods": ["mean"],
            "definition": [{"granularity": gran, "timespan": 30 * 86400} for gran in (300, 600, 900, 1800, 3600)],
        },
    )
    cloud.overrides[("GET", path + "/measures")] = []
    result = (await instance(cloud, ["memory_resident"]))["memory_resident"]
    assert result["series"] == [] and result["status"] == "not_collected"
    requests = [options for _, path, options in cloud.calls if path.endswith("/measures")]
    assert len(requests) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("authenticated_project", [None, "", OTHER])
async def test_project_native_enumeration_rejects_unbound_or_foreign_connection(cloud, authenticated_project):
    row = cloud.resource()
    cloud.meter(row, "memory.resident", "MiB", [(0, 42)])
    cloud.conn._afterglow_authenticated_project_id = authenticated_project
    result = await native.project_series(cloud.conn, PROJECT, ["memory_resident"], **RANGE)
    assert result["status"] == "forbidden"
    assert result["instances"] == {}
    assert cloud.calls == [] and cloud.discovery == []


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["reset", "gap", "resize"])
async def test_resampled_means_cannot_hide_native_counter_or_denominator_discontinuity(cloud, defect):
    row = cloud.resource()
    for meter, unit in (("cpu", "ns"), ("vcpus", "vcpu")):
        path = cloud.meter(row, meter, unit, [])

        def reply(options, meter=meter):
            params = options["params"]
            effective = params.get("resample", 300)
            points = []
            for ts in range(int(params["start"]), int(params["stop"]) + 1, int(effective)):
                offset = ts - BASE
                if "resample" in params:
                    # Coarse endpoints alone look perfectly continuous/stable.
                    value = (offset + effective) * 1e9 if meter == "cpu" else 2
                else:
                    if meter == "cpu" and defect == "gap" and offset == 900:
                        continue
                    value = (offset + 600) * 1e9 if meter == "cpu" else 2
                    if meter == "cpu" and defect == "reset" and offset == 900:
                        value = 1
                    if meter == "vcpus" and defect == "resize" and offset == 900:
                        value = 4
                points.append([datetime.fromtimestamp(ts, UTC).isoformat(), effective, value])
            return points

        cloud.overrides[("GET", path + "/measures")] = reply
    result = (await instance(cloud, ["cpu"], end_ts=BASE + 3600, step_s=600))["cpu"]
    assert result["status"] == "partial"
    assert result["series"] and all(point["value"] == 50.0 for point in result["series"])
    assert not any(BASE + 600 <= point["ts"] <= BASE + 1200 for point in result["series"])
    assert any(point["ts"] >= BASE + 2400 for point in result["series"])


@pytest.mark.asyncio
async def test_unqualifiable_native_continuity_never_returns_resampled_counter_rate(cloud):
    row = cloud.resource()
    path = cloud.meter(row, "memory.swap.in", "MiB", [])
    cloud.overrides[("GET", path + "/measures")] = lambda options: (
        [[iso(0), 600, 1000], [iso(600), 600, 2000]]
        if "resample" in options["params"]
        else Response({"detail": SECRET}, 403)
    )
    result = (await instance(cloud, ["memory_swap_in"], step_s=600))["memory_swap_in"]
    assert result["status"] == "forbidden" and result["series"] == []
    assert result["error"] == "access_denied"


@pytest.mark.asyncio
@pytest.mark.parametrize("malformed", [False, True])
async def test_coarser_archive_retry_cannot_replace_a_known_native_reset(cloud, malformed):
    row = cloud.resource()
    path = cloud.meter(
        row,
        "memory.swap.in",
        "MiB",
        [],
        policy={
            "aggregation_methods": ["mean"],
            "definition": [{"granularity": 300, "timespan": 86400}, {"granularity": 600, "timespan": 30 * 86400}],
        },
    )
    cloud.overrides[("GET", path + "/measures")] = lambda options: (
        [[iso(ts), 300, value] for ts, value in ((0, 1000), (300, 0), (600, 100), (900, 1000))]
        + ([["bad", 300, 100]] if malformed else [])
        if options["params"]["granularity"] == 300
        else [[iso(ts), 600, value] for ts, value in ((0, 500), (600, 550), (1200, 600), (1800, 650))]
    )
    result = (await instance(cloud, ["memory_swap_in"]))["memory_swap_in"]
    assert result["status"] == "partial"
    assert [point["ts"] for point in result["series"]] == [BASE + 600, BASE + 900]
    reads = [options["params"]["granularity"] for _, path, options in cloud.calls if path.endswith("/measures")]
    assert reads == [300]
