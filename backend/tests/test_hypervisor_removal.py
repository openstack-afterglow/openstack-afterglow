"""Semantic Nova/Placement removal evidence; no network or destructive calls."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException

from app.services import hypervisor_removal as removal
from app.services import nova_hosts

HYP = "11111111-1111-1111-1111-111111111111"
SERVICE = "22222222-2222-2222-2222-222222222222"
CHILD = "33333333-3333-3333-3333-333333333333"
HOST = "compute-host"
STAMP = "2020-01-01T00:00:00Z"


class UpstreamError(Exception):
    def __init__(self, status=503):
        super().__init__("upstream password=secret token=private https://internal.example")
        self.status_code = status


class Reply:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def raise_for_status(self):
        if self.status >= 400:
            raise UpstreamError(self.status)

    def json(self):
        return deepcopy(self.body)


def server(server_id="instance-a", *, status="SHUTOFF", host=HOST):
    return {
        "id": server_id,
        "name": "workload",
        "status": status,
        "tenant_id": "project-a",
        "created": STAMP,
        "OS-EXT-SRV-ATTR:host": host,
    }


def migration(migration_id="migration-a", *, status="confirmed", kind="migration", incoming=False):
    return {
        "id": migration_id,
        "uuid": migration_id,
        "instance_uuid": "historical-instance",
        "source_compute": "other-host" if incoming else HOST,
        "dest_compute": HOST if incoming else "other-host",
        "status": status,
        "migration_type": kind,
        "created_at": STAMP,
        "updated_at": STAMP,
    }


def provider(uuid=HYP, *, parent=None):
    return {
        "uuid": uuid,
        "name": "driver-name" if parent is None else "gpu-child",
        "parent_provider_uuid": parent,
        "root_provider_uuid": HYP,
        "generation": 7,
    }


class Cloud:
    """Small raw-HTTP fixture that enforces version and UUID-marker contracts."""

    def __init__(self):
        self.hypervisor = {
            "id": HYP,
            "hypervisor_hostname": "driver-name",
            "state": "down",
            "status": "disabled",
            "service": {"id": SERVICE, "host": HOST, "disabled_reason": "maintenance"},
            "running_vms": 0,
            "vcpus_used": 1,
            "memory_mb_used": 512,
        }
        self.service = {
            "id": SERVICE,
            "host": HOST,
            "binary": "nova-compute",
            "state": "down",
            "status": "disabled",
            "updated_at": STAMP,
            "forced_down": False,
            "disabled_reason": "maintenance",
            "zone": "nova",
        }
        self.nodes = [self.hypervisor]
        self.services = [self.service]
        self.current = []
        self.deleted = []
        self.migrations = []  # Visible 2.59 pages after Nova's post-pagination hidden filter.
        self.unpaged_migrations = None  # Defaults to every record in self.migrations.
        self.unexpected = []
        self.residual_providers = set()
        self.tree = [provider()]
        self.allocations = {HYP: {"allocations": {}, "resource_provider_generation": 7}}
        self.aggregates = []
        self.removed = False
        self.uptime = Reply({}, 503)
        self.root_reply = None
        self.failures = {}
        self.calls = []
        self.conn = SimpleNamespace(
            compute=SimpleNamespace(get_endpoint=lambda: "https://nova.example"),
            placement=SimpleNamespace(get_endpoint=lambda: "https://placement.example"),
            session=MagicMock(),
        )
        self.conn.session.get.side_effect = self.get

    @staticmethod
    def page(pages, marker, key="id"):
        if marker is None:
            return pages[0] if pages else []
        for index, page in enumerate(pages):
            if page and page[-1][key] == marker:
                return pages[index + 1] if index + 1 < len(pages) else []
        raise AssertionError(f"Unexpected marker {marker}")

    def get(self, url, *, params=None, headers=None):
        try:
            return self.route(url, params=params, headers=headers)
        except AssertionError as exc:
            # Production code converts errors into `unknown`; never let a fixture gap pass as such.
            self.unexpected.append(str(exc))
            raise

    def route(self, url, *, params=None, headers=None):
        path = urlsplit(url).path
        self.calls.append((url, deepcopy(params), deepcopy(headers)))
        params = params or {}
        if url.startswith("https://placement.example"):
            assert headers == removal.PLACEMENT_HEADERS
        elif path == "/os-migrations":
            assert headers in (removal.MIGRATION_HEADERS, removal.UNPAGED_MIGRATION_HEADERS)
        else:
            assert headers == nova_hosts.NOVA_HOST_HEADERS
        failure = self.failures.get((path, params.get("marker")), self.failures.get(path))
        if failure is not None:
            if isinstance(failure, Exception):
                raise failure
            return failure
        if path == f"/os-hypervisors/{HYP}":
            return Reply({}, 404) if self.removed else Reply({"hypervisor": self.hypervisor})
        if path == f"/os-hypervisors/{HYP}/uptime":
            return self.uptime
        if path == "/os-services":
            assert params == {"host": HOST, "binary": "nova-compute"}
            return Reply({"services": [] if self.removed else self.services})
        if path == "/os-hypervisors/detail":
            return Reply({"hypervisors": self.page([] if self.removed else [self.nodes], params.get("marker"))})
        if path == "/servers/detail":
            assert params["all_tenants"] == "1" and params["host"] == HOST
            pages = self.deleted if params.get("deleted") == "true" else self.current
            return Reply({"servers": self.page(pages, params.get("marker"))})
        if path == "/os-migrations" and headers == removal.UNPAGED_MIGRATION_HEADERS:
            assert params == {"host": HOST}
            records = self.unpaged_migrations
            if records is None:
                records = [item for page in self.migrations for item in page]
            return Reply({"migrations": [{k: v for k, v in item.items() if k != "uuid"} for item in records]})
        if path == "/os-migrations":
            assert params["host"] == HOST and "hidden" not in params
            return Reply({"migrations": self.page(self.migrations, params.get("marker"), "uuid")})
        if path == f"/resource_providers/{HYP}" and self.root_reply is not None:
            return self.root_reply
        if path.startswith("/resource_providers/") and path.count("/") == 2:
            uuid = path.split("/")[2]
            if self.removed:
                return (
                    Reply(provider(uuid, parent=None if uuid == HYP else HYP))
                    if uuid in self.residual_providers
                    else Reply({}, 404)
                )
            known = next((item for item in self.tree if item["uuid"] == uuid), None)
            return Reply(known) if known else Reply({}, 404)
        if path == "/resource_providers":
            assert not self.removed, "verification must not rely on in_tree/full listing"
            return Reply({"resource_providers": self.tree})
        if path.endswith("/allocations"):
            return Reply(self.allocations[path.split("/")[2]])
        if path == "/os-aggregates":
            return Reply({"aggregates": self.aggregates})
        raise AssertionError((url, params, headers))

    def inspect(self):
        return removal.inspect_host(self.conn, HYP)

    def assert_read_only(self):
        for method in ("delete", "post", "put", "patch"):
            getattr(self.conn.session, method).assert_not_called()


@pytest.fixture
def cloud():
    fixture = Cloud()
    yield fixture
    assert fixture.unexpected == []


def state(report, code):
    return next(check["state"] for check in report["checks"] if check["code"] == code)


def test_empty_disabled_down_host_is_eligible_without_uptime_or_zero_overhead(cloud):
    report = cloud.inspect()
    assert report["eligible"] is True
    assert set(report) == {
        "hypervisor_id",
        "hostname",
        "checked_at",
        "service",
        "uptime",
        "servers",
        "history",
        "placement",
        "checks",
        "eligible",
    }
    assert report["service"] == cloud.service
    assert report["hostname"] == "driver-name"  # Not necessarily the compute service host.
    assert report["uptime"] == {"status": "unavailable", "value": None, "host_time": None}
    assert report["placement"]["providers"][0]["allocations"] == {}
    assert all(check["state"] == "pass" for check in report["checks"])
    cloud.assert_read_only()


@pytest.mark.parametrize(
    "field,value,code,expected",
    [
        ("status", "enabled", "service_status", "blocked"),
        ("status", "new-status", "service_status", "unknown"),
        ("state", "up", "service_state", "blocked"),
        ("state", None, "service_state", "unknown"),
        ("forced_down", True, "forced_down", "blocked"),
        ("forced_down", None, "forced_down", "unknown"),
        ("forced_down", "false", "forced_down", "unknown"),
        ("updated_at", None, "service_updated_at", "unknown"),
        ("updated_at", "invalid-date", "service_updated_at", "unknown"),
        ("updated_at", "2999-01-01T00:00:00Z", "service_updated_at", "unknown"),
    ],
)
def test_service_critical_evidence_is_fail_closed(cloud, field, value, code, expected):
    cloud.service[field] = value
    report = cloud.inspect()
    assert not report["eligible"]
    assert state(report, code) == expected


@pytest.mark.parametrize(
    "value,expected", [(1, "blocked"), (None, "unknown"), ("0", "unknown"), (-1, "unknown"), (False, "unknown")]
)
def test_reported_running_vms_never_becomes_safe_zero(cloud, value, expected):
    cloud.hypervisor["running_vms"] = value
    report = cloud.inspect()
    assert report["servers"] == [] and not report["eligible"]
    assert state(report, "running_vms") == expected


@pytest.mark.parametrize("field,value", [("id", "wrong-service"), ("host", "wrong-host"), ("binary", "nova-scheduler")])
def test_exact_service_identity_required(cloud, field, value):
    cloud.service[field] = value
    report = cloud.inspect()
    assert not report["eligible"]
    assert state(report, "identity") == "unknown"


def test_shared_helpers_preserve_identity_conflicts_and_legacy_hostless_pages(cloud):
    cloud.current = [[{"id": "one"}], [{"id": "two"}]]
    assert list(nova_hosts.host_servers(cloud.conn, HOST)) == [{"id": "one"}, {"id": "two"}]
    params = [params for url, params, _ in cloud.calls if url.endswith("/servers/detail")]
    assert [item.get("marker") for item in params] == [None, "one", "two"]
    assert all("deleted" not in item for item in params)
    with pytest.raises(HTTPException) as missing:
        nova_hosts.get_compute_service(cloud.conn, {"service": {}})
    assert missing.value.status_code == 409
    cloud.hypervisor["id"] = "wrong-hypervisor"
    with pytest.raises(HTTPException) as mismatch:
        nova_hosts.get_hypervisor(cloud.conn, HYP)
    assert mismatch.value.status_code == 409


@pytest.mark.parametrize("malformed", [{}, {"servers": None}, {"servers": [None]}, {"servers": [{"id": ""}]}])
def test_shared_host_scan_rejects_malformed_pages(cloud, malformed):
    cloud.failures["/servers/detail"] = Reply(malformed)
    with pytest.raises(ValueError):
        list(nova_hosts.host_servers(cloud.conn, HOST))


def test_shared_host_scan_rejects_repeated_marker(cloud):
    cloud.current = [[{"id": "one"}], [{"id": "one"}]]
    with pytest.raises(ValueError):
        list(nova_hosts.host_servers(cloud.conn, HOST))


@pytest.mark.parametrize("field", ["OS-EXT-SRV-ATTR:host", "id", "status", "tenant_id"])
def test_removal_scan_requires_critical_server_fields(cloud, field):
    record = server()
    del record[field]
    cloud.current = [[record]]
    report = cloud.inspect()
    assert not report["eligible"]
    assert state(report, "present_servers") == "unknown"


def test_server_scan_exhausts_short_pages_and_later_record_blocks(cloud, monkeypatch):
    monkeypatch.setattr(nova_hosts, "HOST_SERVER_PAGE_SIZE", 200)
    cloud.current = [[server("first", status="SHUTOFF")], [server("later", status="VERIFY_RESIZE")]]
    report = cloud.inspect()
    assert [item["id"] for item in report["servers"]] == ["first", "later"]
    assert not report["eligible"] and state(report, "present_servers") == "blocked"
    calls = [params for url, params, _ in cloud.calls if url.endswith("/servers/detail") and "deleted" not in params]
    assert [params.get("marker") for params in calls] == [None, "first", "later"]


def test_soft_deleted_is_present_but_retained_deleted_is_history(cloud):
    cloud.deleted = [[server("old", status="DELETED")], [server("recoverable", status="SOFT_DELETED")]]
    report = cloud.inspect()
    assert [item["id"] for item in report["servers"]] == ["recoverable"]
    assert [item["id"] for item in report["history"]["deleted_servers"]] == ["old"]
    assert not report["eligible"] and state(report, "retained_servers") == "blocked"
    cloud.deleted = [[server("old", status="DELETED")]]
    report = cloud.inspect()
    assert report["eligible"] and report["history"]["deleted_servers"]
    assert "does not prove" in report["history"]["note"]


@pytest.mark.parametrize(
    "kind,status,expected",
    [
        ("migration", "confirmed", "pass"),
        ("migration", "reverted", "pass"),
        ("migration", "finished", "blocked"),
        ("migration", "done", "pass"),
        ("resize", "finished", "blocked"),
        ("resize", "VERIFY_RESIZE", "blocked"),
        ("resize", "confirming", "blocked"),
        ("resize", "confirmed", "pass"),
        ("live-migration", "completed", "pass"),
        ("live-migration", "failed", "pass"),
        ("live-migration", "cancelled", "pass"),
        ("live-migration", "running", "blocked"),
        ("evacuation", "done", "pass"),
        ("evacuation", "accepted", "blocked"),
        ("migration", "future-state", "blocked"),
        ("future-type", "completed", "unknown"),
    ],
)
def test_migration_terminal_boundaries_and_unknown_states(cloud, kind, status, expected):
    cloud.migrations = [[migration(kind=kind, status=status)]]
    report = cloud.inspect()
    assert state(report, "migrations") == expected
    assert report["eligible"] == (expected == "pass")
    assert report["history"]["migrations"][0]["status"] == status


def test_incoming_later_migration_blocks_after_single_uuid_scan(cloud):
    cloud.migrations = [
        [migration("completed-outgoing")],
        [migration("completed-incoming", incoming=True)],
        [migration("pending-incoming", status="finished", incoming=True)],
    ]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "blocked"
    assert len(report["history"]["migrations"]) == 3
    assert "hidden" in report["history"]["note"]
    calls = [(headers, params) for url, params, headers in cloud.calls if url.endswith("/os-migrations")]
    assert calls[0] == (removal.UNPAGED_MIGRATION_HEADERS, {"host": HOST})
    assert [p.get("marker") for _, p in calls[1:]] == [
        None,
        "completed-outgoing",
        "completed-incoming",
        "pending-incoming",
    ]
    assert all("hidden" not in p for _, p in calls)


def test_all_hidden_intermediate_page_cannot_hide_later_unfinished_migration(cloud):
    # Nova filters hidden rows after paginating: page two is empty with no links,
    # although a visible unfinished migration exists after it.
    completed = migration("completed")
    pending = migration("pending", status="pre-migrating", incoming=True)
    cloud.migrations = [[completed]]
    cloud.unpaged_migrations = [completed, pending]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "blocked"
    records = {item["id"]: item for item in report["history"]["migrations"]}
    assert records["completed"]["uuid"] == "completed"
    assert records["pending"]["uuid"] == ""  # Visible only through the authoritative unpaged read.


@pytest.mark.parametrize("change", ["missing_from_unpaged", "status_changed"])
def test_paged_and_unpaged_disagreement_is_unknown(cloud, change):
    record = migration("record")
    cloud.migrations = [[record]]
    cloud.unpaged_migrations = [] if change == "missing_from_unpaged" else [record | {"status": "running"}]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


def test_repeated_migration_marker_is_unknown(cloud):
    cloud.migrations = [[migration("same")], [migration("same", incoming=True)]]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


@pytest.mark.parametrize("field", ["uuid", "id", "status", "migration_type", "instance_uuid"])
def test_missing_migration_fields_are_unknown(cloud, field):
    record = migration()
    del record[field]
    cloud.migrations = [[record]]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


@pytest.mark.parametrize("status", ["failed", "error"])
def test_failed_migration_with_explicit_null_destination_is_valid_history(cloud, status):
    cloud.migrations = [[migration(status=status) | {"dest_compute": None}]]
    report = cloud.inspect()
    assert report["eligible"] and state(report, "migrations") == "pass"
    assert report["history"]["migrations"][0]["dest_compute"] is None


@pytest.mark.parametrize("field", ["source_compute", "dest_compute"])
def test_missing_migration_side_key_is_unknown_not_null(cloud, field):
    record = migration(status="error")
    del record[field]
    cloud.migrations = [[record]]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


# (None, None) is also what Nova returns without the os-migrations:index:host policy.
@pytest.mark.parametrize("sides", [(None, None), ("other-host", None), ("", HOST), (HOST, 7)])
def test_migration_must_reference_host_with_valid_sides(cloud, sides):
    cloud.migrations = [[migration(status="failed") | {"source_compute": sides[0], "dest_compute": sides[1]}]]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


def test_cross_cell_shared_id_is_matched_by_full_identity(cloud):
    local = migration("local-uuid") | {"id": 5}
    remote = migration("remote-uuid", incoming=True) | {"id": 5, "instance_uuid": "other-instance"}
    cloud.migrations = [[local], [remote]]
    report = cloud.inspect()
    assert report["eligible"] and state(report, "migrations") == "pass"
    assert sorted(item["uuid"] for item in report["history"]["migrations"]) == ["local-uuid", "remote-uuid"]


def test_indistinguishable_unpaged_records_are_unknown(cloud):
    record = migration("one") | {"id": 5}
    cloud.migrations = [[record]]
    cloud.unpaged_migrations = [record, record]
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "migrations") == "unknown"


def test_multi_node_service_is_blocked_even_without_workloads(cloud):
    cloud.nodes.append(cloud.hypervisor | {"id": "ironic-second-node"})
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "single_compute_node") == "blocked"


def test_child_gpu_allocations_block_empty_root(cloud):
    cloud.tree.append(provider(CHILD, parent=HYP))
    cloud.allocations[CHILD] = {
        "resource_provider_generation": 7,
        "allocations": {"consumer": {"resources": {"CUSTOM_GPU": 1}}},
    }
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "placement_allocations") == "blocked"
    providers = {item["uuid"]: item for item in report["placement"]["providers"]}
    assert providers[HYP]["allocations"] == {}
    assert providers[CHILD]["allocations"]["consumer"]["resources"] == {"CUSTOM_GPU": 1}
    cloud.assert_read_only()


@pytest.mark.parametrize(
    "damage",
    [
        "root_missing",
        "tree_missing_root",
        "parent_missing",
        "bad_generation",
        "missing_allocations",
        "missing_allocation_generation",
        "changed_generation",
        "continuation",
        "bad_resources",
    ],
)
def test_placement_uncertainty_is_never_empty_safe_evidence(cloud, damage):
    if damage == "root_missing":
        cloud.root_reply = Reply({}, 404)
    elif damage == "tree_missing_root":
        cloud.root_reply = Reply(provider())  # Root read succeeds; only in_tree omits it.
        cloud.tree = []
    elif damage == "parent_missing":
        del cloud.tree[0]["parent_provider_uuid"]
    elif damage == "bad_generation":
        cloud.tree[0]["generation"] = None
    elif damage == "missing_allocations":
        del cloud.allocations[HYP]["allocations"]
    elif damage == "missing_allocation_generation":
        del cloud.allocations[HYP]["resource_provider_generation"]
    elif damage == "changed_generation":
        cloud.allocations[HYP]["resource_provider_generation"] = 8
    elif damage == "continuation":
        cloud.failures["/resource_providers"] = Reply(
            {"resource_providers": cloud.tree, "resource_providers_links": [{"rel": "next", "href": "private"}]}
        )
    else:
        cloud.allocations[HYP]["allocations"] = {"consumer": {"resources": None}}
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "placement_allocations") == "unknown"


@pytest.mark.parametrize(
    "path,code",
    [
        ("/servers/detail", "present_servers"),
        ("/os-migrations", "migrations"),
        ("/os-hypervisors/detail", "single_compute_node"),
        (f"/resource_providers/{HYP}/allocations", "placement_allocations"),
    ],
)
def test_upstream_failures_are_explicit_unknown_without_secrets(cloud, path, code):
    cloud.failures[path] = UpstreamError(403)
    report = cloud.inspect()
    assert not report["eligible"] and state(report, code) == "unknown"
    serialized = str(report["checks"])
    assert "secret" not in serialized and "private" not in serialized and "internal.example" not in serialized


def test_later_page_failure_prevents_safe_result(cloud):
    cloud.current = [[server("first")]]
    cloud.failures[("/servers/detail", "first")] = UpstreamError()
    report = cloud.inspect()
    assert not report["eligible"] and state(report, "present_servers") == "unknown"
    cloud.assert_read_only()


def test_fingerprint_is_semantic_and_excludes_sampling(cloud):
    cloud.deleted = [[server("old-b", status="DELETED"), server("old-a", status="DELETED")]]
    cloud.migrations = [[migration("b"), migration("a")]]
    cloud.tree.append(provider(CHILD, parent=HYP))
    cloud.allocations[CHILD] = {"allocations": {}, "resource_provider_generation": 7}
    report = cloud.inspect()
    before = removal.review_fingerprint(report)
    changed = deepcopy(report)
    changed["checked_at"] = "different-time"
    changed["uptime"] = {"status": "available", "value": "new sample", "host_time": "new clock"}
    changed["history"]["deleted_servers"].reverse()
    changed["history"]["migrations"].reverse()
    changed["placement"]["providers"].reverse()
    changed["checks"].reverse()
    assert removal.review_fingerprint(changed) == before
    for section, field, value in [
        ("service", "updated_at", "2020-01-02T00:00:00Z"),
        ("service", "forced_down", True),
        ("service", "status", "enabled"),
    ]:
        changed = deepcopy(report)
        changed[section][field] = value
        assert removal.review_fingerprint(changed) != before
    changed = deepcopy(report)
    changed["history"]["deleted_servers"][0]["name"] = "renamed"
    assert removal.review_fingerprint(changed) != before
    changed = deepcopy(report)
    changed["history"]["migrations"][0]["status"] = "finished"
    assert removal.review_fingerprint(changed) != before
    changed = deepcopy(report)
    changed["placement"]["providers"][0]["generation"] += 1
    assert removal.review_fingerprint(changed) != before
    changed = deepcopy(report)
    changed["placement"]["providers"][0]["allocations"] = {"consumer": {"resources": {"VCPU": 1}}}
    assert removal.review_fingerprint(changed) != before


def test_post_delete_verifies_each_absence_without_mutation(cloud):
    report = cloud.inspect()
    cloud.removed = True
    outcome = removal.verify_removal(cloud.conn, report)
    assert outcome["status"] == "removed" and outcome["verified"] is True
    assert outcome["service_id"] == SERVICE and outcome["hostname"] == "driver-name"
    assert {check["code"] for check in outcome["checks"]} == {
        "service_absent",
        "hypervisor_absent",
        "placement_absent",
        "aggregates_removed",
    }
    assert all(check["state"] == "pass" for check in outcome["checks"])
    cloud.assert_read_only()


@pytest.mark.parametrize(
    "residue,code",
    [
        ("service", "service_absent"),
        ("hypervisor", "hypervisor_absent"),
        ("root", "placement_absent"),
        ("child", "placement_absent"),
        ("aggregate", "aggregates_removed"),
    ],
)
def test_post_delete_residue_is_unverified(cloud, residue, code):
    cloud.tree.append(provider(CHILD, parent=HYP))
    cloud.allocations[CHILD] = {"allocations": {}, "resource_provider_generation": 7}
    report = cloud.inspect()
    cloud.removed = True
    if residue == "service":
        cloud.failures["/os-services"] = Reply({"services": [cloud.service]})
    elif residue == "hypervisor":
        cloud.failures[f"/os-hypervisors/{HYP}"] = Reply({"hypervisor": cloud.hypervisor})
    elif residue == "root":
        cloud.residual_providers = {HYP}
    elif residue == "child":
        cloud.residual_providers = {CHILD}
    else:
        cloud.aggregates = [{"hosts": [HOST]}]
    outcome = removal.verify_removal(cloud.conn, report)
    assert outcome["status"] == "removal_unverified" and not outcome["verified"]
    assert state(outcome, code) == "blocked"
    cloud.assert_read_only()


@pytest.mark.parametrize(
    "path,code",
    [
        ("/os-services", "service_absent"),
        (f"/os-hypervisors/{HYP}", "hypervisor_absent"),
        (f"/resource_providers/{CHILD}", "placement_absent"),
        ("/os-aggregates", "aggregates_removed"),
    ],
)
def test_post_delete_unavailable_evidence_is_unverified_not_absent(cloud, path, code):
    cloud.tree.append(provider(CHILD, parent=HYP))
    cloud.allocations[CHILD] = {"allocations": {}, "resource_provider_generation": 7}
    report = cloud.inspect()
    cloud.removed = True
    cloud.failures[path] = UpstreamError(503)
    outcome = removal.verify_removal(cloud.conn, report)
    assert not outcome["verified"] and outcome["status"] == "removal_unverified"
    assert state(outcome, code) == "unknown"
    assert "secret" not in str(outcome)
    cloud.assert_read_only()


def test_post_delete_missing_aggregate_membership_is_unknown(cloud):
    report = cloud.inspect()
    cloud.removed = True
    cloud.aggregates = [{"id": 1, "name": "aggregate-without-hosts"}]
    outcome = removal.verify_removal(cloud.conn, report)
    assert not outcome["verified"] and state(outcome, "aggregates_removed") == "unknown"


def test_post_delete_requires_reviewed_tree_and_explicit_404(cloud):
    report = cloud.inspect()
    cloud.removed = True
    cloud.root_reply = Reply({}, 403)
    outcome = removal.verify_removal(cloud.conn, report)
    assert state(outcome, "placement_absent") == "unknown"
    cloud.root_reply = None
    report["placement"]["providers"] = []
    outcome = removal.verify_removal(cloud.conn, report)
    assert state(outcome, "placement_absent") == "unknown"
    cloud.assert_read_only()
