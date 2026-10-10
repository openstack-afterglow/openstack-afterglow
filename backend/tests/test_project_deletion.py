"""Administrator project deletion safety through real FastAPI and native OpenStack SDK HTTP boundaries.

Every test drives the public deletion-check / delete endpoints with a genuine ``openstack.connection.Connection``
whose transport is an in-process provider simulation. The simulation behaves like the providers rather than like
the implementation: Nova and Cinder only return other projects with ``all_tenants``, Neutron and Glance honour
project/owner filters, Glance hides ``os_hidden`` images unless asked and excludes community/pending-shared images
without ``visibility=all``/``member_status=all``, Nova server groups paginate only by ``offset`` and omit ownership
before microversion 2.13, and every provider enforces a page size smaller than any requested limit so incomplete
pagination stays visible.
"""

import asyncio
import json
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlsplit

import openstack.connection
import pytest
import requests
from keystoneauth1 import access
from keystoneauth1 import session as ks_session
from keystoneauth1.identity.access import AccessInfoPlugin
from requests import Response
from requests.adapters import BaseAdapter

from app.api.deps import get_os_conn
from app.main import app

TARGET = "target-project"
FOREIGN = "foreign-project"
CALLER = "admin-project"
PAGE = 2
LEAK = "upstream-secret-detail"
URL = f"/api/v1/admin/projects/{TARGET}"


@dataclass(frozen=True)
class Kind:
    host: str
    paths: tuple[str, ...]
    key: str
    owners: tuple[str, ...]
    admin_wide: bool


KINDS = {
    "instances": Kind("nova.test", ("/v2.1/servers/detail", "/v2.1/servers"), "servers", ("tenant_id",), True),
    "server_groups": Kind("nova.test", ("/v2.1/os-server-groups",), "server_groups", ("project_id",), True),
    "volumes": Kind(
        "cinder.test", ("/v3/volumes/detail", "/v3/volumes"), "volumes", ("os-vol-tenant-attr:tenant_id",), True
    ),
    "volume_snapshots": Kind(
        "cinder.test",
        ("/v3/snapshots/detail", "/v3/snapshots"),
        "snapshots",
        ("os-extended-snapshot-attributes:project_id",),
        True,
    ),
    "volume_backups": Kind(
        "cinder.test", ("/v3/backups/detail", "/v3/backups"), "backups", ("os-backup-project-attr:project_id",), True
    ),
    "networks": Kind("neutron.test", ("/v2.0/networks",), "networks", ("project_id", "tenant_id"), False),
    "subnets": Kind("neutron.test", ("/v2.0/subnets",), "subnets", ("project_id", "tenant_id"), False),
    "routers": Kind("neutron.test", ("/v2.0/routers",), "routers", ("project_id", "tenant_id"), False),
    "ports": Kind("neutron.test", ("/v2.0/ports",), "ports", ("project_id", "tenant_id"), False),
    "floating_ips": Kind("neutron.test", ("/v2.0/floatingips",), "floatingips", ("project_id", "tenant_id"), False),
    "security_groups": Kind(
        "neutron.test", ("/v2.0/security-groups",), "security_groups", ("project_id", "tenant_id"), False
    ),
    "images": Kind("glance.test", ("/v2/images",), "images", ("owner",), False),
}
CORE_KINDS = tuple(KINDS)
HOST_KINDS = {
    host: tuple(name for name, kind in KINDS.items() if kind.host == host) for host in {k.host for k in KINDS.values()}
}
CATALOG = {
    "identity": "http://keystone.test/v3",
    "compute": "http://nova.test/v2.1",
    "volumev3": "http://cinder.test/v3",
    "network": "http://neutron.test",
    "image": "http://glance.test",
}
SERVICE_HOSTS = {"compute": "nova.test", "volumev3": "cinder.test", "network": "neutron.test", "image": "glance.test"}
VERSIONS = {
    "keystone.test": ("/v3", {"id": "v3.14", "status": "stable"}),
    "nova.test": ("/v2.1", {"id": "v2.1", "status": "CURRENT", "version": "2.96", "min_version": "2.1"}),
    "cinder.test": ("/v3", {"id": "v3.0", "status": "CURRENT", "version": "3.71", "min_version": "3.0"}),
    "neutron.test": ("/v2.0", {"id": "v2.0", "status": "CURRENT"}),
    "glance.test": ("/v2", {"id": "v2.17", "status": "CURRENT"}),
}
STATES = ("SHUTOFF", "ERROR", "available", "SHELVED_OFFLOADED")


def item(kind, id, owner, **fields):
    row = {"id": id, "name": fields.pop("name", id), "status": fields.pop("status", "ACTIVE")}
    row.update(dict.fromkeys(KINDS[kind].owners, owner))
    row.update(fields)
    if kind == "images":
        row.setdefault("visibility", "private")
        row.setdefault("os_hidden", False)
    return row


def _response(request, status, body):
    result = Response()
    result.status_code = status
    result._content = b"" if body is None else json.dumps(body).encode()
    if body is not None:
        result.headers["Content-Type"] = "application/json"
    result.url = request.url
    result.request = request
    return result


def _truthy(value):
    return str(value).lower() in {"true", "1", "yes"}


def later_page(query):
    return bool(query.get("marker")) or int(query.get("offset") or 0) > 0


def first_page(query):
    return not later_page(query)


def _compute_microversion(request):
    for header in ("OpenStack-API-Version", "X-OpenStack-Nova-API-Version"):
        value = request.headers.get(header)
        if value:
            major, minor = value.split()[-1].split(".")
            return int(major), int(minor)
    return 2, 1


class FakeCloud(BaseAdapter):
    """Provider-side behaviour for Keystone, Nova, Cinder, Neutron and Glance over a requests transport."""

    def __init__(self):
        super().__init__()
        self.rows = {kind: [] for kind in KINDS}
        self.catalog = dict(CATALOG)
        self.extra_catalog = []
        self.failures = {}  # kind -> (predicate over the request query, HTTP status)
        self.denied = set()  # provider hosts whose policy rejects resource listing
        self.block = {}  # kind -> (started, release) threading events held inside the provider read
        self.glance_ignores_hidden_filter = False  # legacy/broken Glance returning every image for both partitions
        self.calls = Counter()
        self.requests = []
        self.unexpected = []
        self.failed_requests = []
        self.deleted = []
        self.roles = ["admin"]
        self.is_admin_project = None  # Keystone omits the flag when no admin project is configured.

    def native_admin(self):
        return "admin" in self.roles and self.is_admin_project is not False

    def connect(self):
        token = {
            "token": {
                "methods": ["token"],
                "expires_at": "2036-10-08T00:00:00Z",
                "issued_at": "2026-10-08T00:00:00Z",
                "user": {"id": "admin-user", "name": "admin-user", "domain": {"id": "default"}},
                "project": {"id": CALLER, "name": "admin", "domain": {"id": "default"}},
                "roles": [{"id": f"role-{role}", "name": role} for role in self.roles],
                "catalog": [
                    {
                        "id": service_type,
                        "name": service_type,
                        "type": service_type,
                        "endpoints": [
                            {"id": service_type + interface, "interface": interface, "region": "RegionOne", "url": url}
                            for interface in ("public", "internal", "admin")
                        ],
                    }
                    for service_type, url in self.catalog.items()
                ]
                + self.extra_catalog,
            }
        }
        if self.is_admin_project is not None:
            token["token"]["is_admin_project"] = self.is_admin_project
        http = requests.Session()
        http.mount("http://", self)
        auth = AccessInfoPlugin(access.create(body=token, auth_token="admin-token"))
        conn = openstack.connection.Connection(
            session=ks_session.Session(auth=auth, session=http),
            identity_api_version="3",
            compute_api_version="2",
            block_storage_api_version="3",
            network_api_version="2",
            image_api_version="2",
        )
        conn._afterglow_token = "admin-token"
        conn._afterglow_project_id = CALLER
        conn._afterglow_user_id = "admin-user"
        return conn

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        query = dict(parse_qsl(url.query))
        path = url.path.rstrip("/") or "/"
        self.requests.append((request.method, url.netloc, path, query))
        if request.method == "GET" and url.netloc in VERSIONS:
            prefix, doc = VERSIONS[url.netloc]
            doc = {**doc, "links": [{"rel": "self", "href": f"http://{url.netloc}{prefix}/"}]}
            if path == "/":
                return _response(request, 200, {"versions": [doc]})
            if path == prefix:
                return _response(request, 200, {"version": doc})
        if url.netloc == "keystone.test" and path.startswith("/v3/projects/"):
            project_id = path.rsplit("/", 1)[1]
            if request.method == "DELETE":
                self.deleted.append(project_id)
                return _response(request, 204, None)
            project = {"id": project_id, "name": project_id, "domain_id": "default", "enabled": True}
            return _response(request, 200, {"project": {**project, "description": "", "is_domain": False}})
        name = next((n for n, k in KINDS.items() if k.host == url.netloc and path in k.paths), None)
        if name is None or request.method != "GET":
            self.unexpected.append((request.method, request.url))
            return _response(request, 404, {"error": {"message": "not found"}})
        self.calls[name] += 1
        if url.netloc in self.denied:
            return _response(request, 403, {"forbidden": {"code": 403, "message": LEAK}})
        failure = self.failures.get(name)
        if failure and failure[0](query):
            self.failed_requests.append((name, query.copy()))
            return _response(request, failure[1], {"error": {"message": LEAK}})
        if name == "instances" and _truthy(query.get("all_tenants")) and not self.native_admin():
            return _response(request, 403, {"forbidden": {"code": 403, "message": LEAK}})
        if name in self.block:
            started, release = self.block[name]
            started.set()
            if not release.wait(5):
                raise TimeoutError("blocked provider read was not released")
        return _response(request, 200, self._page(request, url, name, query))

    def _page(self, request, url, name, query):
        kind = KINDS[name]

        def owner(row):
            return next((row[field] for field in kind.owners if field in row), None)

        rows = self.rows[name]
        if kind.admin_wide:
            # Cinder and Nova server groups ignore all-project requests from non-admin tokens.
            if not self.native_admin() or not (_truthy(query.get("all_tenants")) or _truthy(query.get("all_projects"))):
                rows = [row for row in rows if owner(row) == CALLER]
            # Nova os-server-groups does not support project_id filtering, only all_projects/limit/offset.
            wanted = query.get("project_id") if name != "server_groups" else None
        else:
            wanted = query.get("owner") if name == "images" else query.get("project_id", query.get("tenant_id"))
            if not self.native_admin():
                # Neutron/Glance filters apply only within the caller-visible set.
                rows = [row for row in rows if owner(row) == CALLER]
        if wanted:
            # Malformed provider rows without ownership survive server-side filters on purpose.
            rows = [row for row in rows if owner(row) in (wanted, None)]
        if name == "server_groups" and _compute_microversion(request) < (2, 13):
            rows = [{k: v for k, v in row.items() if k not in ("project_id", "user_id")} for row in rows]
        if name == "images":
            # Glance list defaults: visible partition only, no community images, accepted shares only.
            if not self.glance_ignores_hidden_filter:
                rows = [row for row in rows if bool(row["os_hidden"]) == _truthy(query.get("os_hidden"))]
            if query.get("visibility") != "all":
                rows = [row for row in rows if row["visibility"] != "community"]
            if query.get("member_status") != "all":
                rows = [row for row in rows if row.get("member_status", "accepted") == "accepted"]
        limit = min(int(query.get("limit") or PAGE), PAGE)
        if name == "server_groups":
            start = int(query.get("offset") or 0)
        else:
            marker = query.get("marker")
            start = [row["id"] for row in rows].index(marker) + 1 if marker else 0
        page = rows[start : start + limit]
        body = {kind.key: page}
        if start + limit < len(rows) and name != "server_groups":
            following = urlencode({**query, "marker": page[-1]["id"], "limit": limit})
            if name == "images":
                body["next"] = f"/v2/images?{following}"
            else:
                body[f"{kind.key}_links"] = [{"rel": "next", "href": f"http://{url.netloc}{url.path}?{following}"}]
        return body


def seed_background(cloud):
    """Paginated foreign and caller-owned resources plus the target's automatic default security group."""
    for name in KINDS:
        cloud.rows[name].extend(item(name, f"{name}-foreign-{i}", FOREIGN) for i in range(PAGE + 1))
        cloud.rows[name].append(item(name, f"{name}-caller", CALLER))
    cloud.rows["security_groups"].append(item("security_groups", "sg-target-default", TARGET, name="default"))


def seed_target(cloud, name, count):
    ids = [f"{name}-target-{i}" for i in range(count)]
    cloud.rows[name].extend(
        item(name, id, TARGET, name=f"custom-{id}", status=STATES[i % len(STATES)]) for i, id in enumerate(ids)
    )
    return ids


def by_kind(report):
    return {row["kind"]: row for row in report["resources"]}


def assert_report(report):
    assert report["project_id"] == TARGET
    assert datetime.fromisoformat(report["checked_at"].replace("Z", "+00:00")).utcoffset() is not None
    assert LEAK not in json.dumps(report)
    kinds = [row["kind"] for row in report["resources"]]
    assert len(kinds) == len(set(kinds))
    assert set(CORE_KINDS) <= set(kinds)
    for row in report["resources"]:
        assert row["status"] in {"ok", "unavailable", "skipped"}
        assert len(row["samples"]) <= 5
        assert all(set(sample) <= {"id", "name", "status"} and sample["id"] for sample in row["samples"])
        if row["status"] == "ok":
            assert isinstance(row["count"], int) and row["reason"] is None
        else:
            assert row["count"] is None and row["samples"] == [] and row["reason"]
    assert report["can_delete"] is all(
        row["status"] != "unavailable" and not row["count"] for row in report["resources"]
    )


async def inspect(client):
    response = await client.get(f"{URL}/deletion-check")
    assert response.status_code == 200, response.text
    assert_report(response.json())
    return response.json()


async def refused(client, status, code):
    response = await client.delete(URL)
    assert response.status_code == status, response.text
    assert LEAK not in response.text
    detail = response.json()["detail"]
    assert detail["code"] == code
    assert isinstance(detail["message"], str) and detail["message"]
    assert_report(detail["check"])
    assert detail["check"]["can_delete"] is False
    return detail["check"]


def assert_only(report, kinds, status):
    for name, row in by_kind(report).items():
        if name in kinds:
            assert row["status"] == status, row
        elif name in KINDS:
            assert row["status"] == "ok", row


@pytest.fixture
def cloud():
    cloud = FakeCloud()
    yield cloud
    assert cloud.unexpected == [], cloud.unexpected
    # Inspection never mutates cloud resources; the only permitted write is the verified Keystone delete.
    writes = [(method, host, path) for method, host, path, _ in cloud.requests if method != "GET"]
    assert all(method == "DELETE" and host == "keystone.test" for method, host, _ in writes), writes


@pytest.fixture
async def native_admin(admin_client, cloud):
    async def connection():
        conn = cloud.connect()
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_os_conn] = connection
    return admin_client


@pytest.mark.asyncio
async def test_verified_empty_project_ignores_foreign_resources_and_default_group_then_deletes(native_admin, cloud):
    seed_background(cloud)

    report = await inspect(native_admin)

    assert report["can_delete"] is True
    resources = by_kind(report)
    for name in CORE_KINDS:
        assert (resources[name]["status"], resources[name]["count"], resources[name]["samples"]) == ("ok", 0, [])
    optional = [row for row in report["resources"] if row["kind"] not in KINDS]
    assert all((row["status"], row["reason"]) == ("skipped", "service_not_present") for row in optional)
    before = cloud.calls.copy()
    response = await native_admin.delete(URL)
    assert response.status_code == 204, response.text
    assert cloud.deleted == [TARGET]
    # The delete reran every provider read server-side instead of trusting the earlier report.
    assert all(cloud.calls[name] > before[name] for name in KINDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("name", CORE_KINDS)
async def test_each_core_kind_counts_every_owned_resource_across_pages(native_admin, cloud, name):
    seed_background(cloud)
    ids = seed_target(cloud, name, PAGE + 1)

    report = await inspect(native_admin)

    row = by_kind(report)[name]
    assert (row["status"], row["count"]) == ("ok", PAGE + 1)
    assert {sample["id"] for sample in row["samples"]} == set(ids)
    assert all(by_kind(report)[other]["count"] == 0 for other in CORE_KINDS if other != name)
    assert report["can_delete"] is False
    check = await refused(native_admin, 409, "project_has_resources")
    assert by_kind(check)[name]["count"] == PAGE + 1
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_custom_security_group_blocks_while_automatic_default_does_not(native_admin, cloud):
    seed_background(cloud)
    cloud.rows["security_groups"].append(item("security_groups", "foreign-default", FOREIGN, name="default"))
    assert (await inspect(native_admin))["can_delete"] is True

    cloud.rows["security_groups"].append(item("security_groups", "sg-target-web", TARGET, name="web"))
    row = by_kind(await inspect(native_admin))["security_groups"]

    assert (row["count"], [sample["id"] for sample in row["samples"]]) == (1, ["sg-target-web"])
    await refused(native_admin, 409, "project_has_resources")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_two_owned_default_named_groups_cannot_both_be_automatic(native_admin, cloud):
    seed_background(cloud)
    cloud.rows["security_groups"].append(item("security_groups", "sg-second-default", TARGET, name="default"))

    report = await inspect(native_admin)

    assert_only(report, {"security_groups"}, "unavailable")
    assert by_kind(report)["security_groups"]["reason"] == "resource_ownership_unverified"
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_samples_are_capped_while_count_stays_complete(native_admin, cloud):
    seed_background(cloud)
    ids = seed_target(cloud, "instances", 7)

    row = by_kind(await inspect(native_admin))["instances"]

    assert row["count"] == 7
    assert len(row["samples"]) == 5
    assert {sample["id"] for sample in row["samples"]} <= set(ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("page", [first_page, later_page], ids=["first", "later"])
@pytest.mark.parametrize("name", CORE_KINDS)
async def test_failed_page_is_unknown_not_a_partial_count(native_admin, cloud, name, page):
    seed_background(cloud)
    seed_target(cloud, name, PAGE + 1)
    cloud.failures[name] = (page, 500)

    report = await inspect(native_admin)

    assert_only(report, {name}, "unavailable")
    assert report["can_delete"] is False
    assert len(cloud.failed_requests) == 1
    failed_kind, failed_query = cloud.failed_requests[0]
    assert failed_kind == name and page(failed_query)
    if page is later_page:
        assert cloud.calls[name] >= 2
        if name == "server_groups":
            assert int(failed_query["offset"]) == PAGE
        else:
            # The marker is exactly the previous page's final resource; failure cannot come from fake setup.
            if KINDS[name].admin_wide:
                expected_marker = f"{name}-foreign-1"
            else:
                expected_marker = f"{name}-target-{0 if name == 'security_groups' else 1}"
            assert failed_query["marker"] == expected_marker
    check = await refused(native_admin, 503, "project_resource_check_failed")
    assert by_kind(check)[name]["status"] == "unavailable"
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "anomaly"),
    [
        ("instances", "missing"),
        ("server_groups", "missing"),
        ("volumes", "missing"),
        ("volume_snapshots", "missing"),
        ("volume_backups", "missing"),
        ("networks", "missing"),
        ("ports", "conflict"),
        ("floating_ips", "conflict"),
        ("images", "missing"),
    ],
)
async def test_missing_or_conflicting_ownership_is_unknown(native_admin, cloud, name, anomaly):
    seed_background(cloud)
    row = item(name, f"{name}-anomaly", TARGET)
    if anomaly == "missing":
        for field in KINDS[name].owners:
            row.pop(field)
    else:
        row["tenant_id"] = FOREIGN
    cloud.rows[name].append(row)

    report = await inspect(native_admin)

    assert_only(report, {name}, "unavailable")
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("host", sorted(HOST_KINDS))
async def test_provider_permission_failure_is_isolated_and_outranks_positive_counts(native_admin, cloud, host):
    seed_background(cloud)
    positive = "images" if host == "nova.test" else "instances"
    seed_target(cloud, positive, 1)
    cloud.denied.add(host)

    report = await inspect(native_admin)

    assert_only(report, set(HOST_KINDS[host]), "unavailable")
    assert by_kind(report)[positive]["count"] == 1
    check = await refused(native_admin, 503, "project_resource_check_failed")
    assert by_kind(check)[positive]["count"] == 1
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("service_type", sorted(SERVICE_HOSTS))
async def test_required_service_missing_from_catalog_blocks(native_admin, cloud, service_type):
    seed_background(cloud)
    del cloud.catalog[service_type]

    report = await inspect(native_admin)

    assert_only(report, set(HOST_KINDS[SERVICE_HOSTS[service_type]]), "unavailable")
    assert report["can_delete"] is False
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_unverifiable_catalog_marks_optional_inventory_unknown(native_admin, cloud):
    seed_background(cloud)
    # keystoneauth silently skips an entry without a type; the deletion check must not.
    cloud.extra_catalog.append({"id": "broken", "name": "unknown", "endpoints": []})

    report = await inspect(native_admin)

    assert all(by_kind(report)[name]["count"] == 0 for name in CORE_KINDS)
    optional = [row for row in report["resources"] if row["kind"] not in KINDS]
    assert optional and all(row["status"] == "unavailable" for row in optional)
    assert report["can_delete"] is False
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_every_check_and_delete_reads_current_cloud_state(native_admin, cloud):
    seed_background(cloud)
    assert (await inspect(native_admin))["can_delete"] is True

    seed_target(cloud, "volumes", 1)
    check = await refused(native_admin, 409, "project_has_resources")
    assert by_kind(check)["volumes"]["count"] == 1
    assert by_kind(await inspect(native_admin))["volumes"]["count"] == 1

    cloud.rows["volumes"] = [row for row in cloud.rows["volumes"] if row["id"] != "volumes-target-0"]
    cloud.denied.add("neutron.test")
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []

    cloud.denied.clear()
    response = await native_admin.delete(URL)
    assert response.status_code == 204, response.text
    assert cloud.deleted == [TARGET]


@pytest.mark.asyncio
async def test_hidden_community_and_pending_shared_images_count(native_admin, cloud):
    seed_background(cloud)
    cloud.rows["images"].extend(
        [
            item("images", "image-hidden", TARGET, os_hidden=True),
            item("images", "image-community", TARGET, visibility="community"),
            item("images", "image-shared-pending", TARGET, visibility="shared", member_status="pending"),
            item("images", "image-hidden-foreign", FOREIGN, os_hidden=True),
        ]
    )

    row = by_kind(await inspect(native_admin))["images"]

    assert (row["status"], row["count"]) == ("ok", 3)
    assert {sample["id"] for sample in row["samples"]} == {"image-hidden", "image-community", "image-shared-pending"}
    await refused(native_admin, 409, "project_has_resources")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_hidden_image_partition_failure_is_unknown_despite_visible_success(native_admin, cloud):
    seed_background(cloud)
    cloud.failures["images"] = (lambda query: _truthy(query.get("os_hidden")), 500)

    report = await inspect(native_admin)

    assert_only(report, {"images"}, "unavailable")
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_cancelled_delete_settles_blocked_inventory_and_never_deletes(native_admin, cloud):
    seed_background(cloud)
    started, release = threading.Event(), threading.Event()
    cloud.block["instances"] = (started, release)

    request = asyncio.create_task(native_admin.delete(URL))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        request.cancel()
        await asyncio.sleep(0.1)
        # Cancellation waits for the provider read instead of unwinding the request connection under it.
        assert not request.done()
    finally:
        release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(request, 5)

    assert cloud.deleted == []
    assert not any(method == "DELETE" for method, *_ in cloud.requests)


@pytest.mark.asyncio
async def test_image_partitions_returning_the_same_image_are_unknown(native_admin, cloud):
    seed_background(cloud)
    seed_target(cloud, "images", 1)
    cloud.glance_ignores_hidden_filter = True

    report = await inspect(native_admin)

    # Counting the image once per partition would be wrong; silently de-duplicating could hide a broken filter.
    assert_only(report, {"images"}, "unavailable")
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("roles", "admin_project"),
    [(["member", "reader"], None), (["admin"], False)],
    ids=["member-home-token", "outside-admin-project"],
)
async def test_token_without_native_admin_context_never_proves_empty(native_admin, cloud, roles, admin_project):
    seed_background(cloud)
    seed_target(cloud, "volumes", 1)
    seed_target(cloud, "networks", 1)
    seed_target(cloud, "images", 1)
    cloud.roles = roles
    cloud.is_admin_project = admin_project

    report = await inspect(native_admin)

    assert len(report["resources"]) == 28
    assert {(row["status"], row["reason"]) for row in report["resources"]} == {
        ("unavailable", "admin_authority_unverified")
    }
    # A shrunken HTTP 200 list from a caller-only token is never consulted as proof of emptiness.
    assert sum(cloud.calls.values()) == 0
    await refused(native_admin, 503, "project_resource_check_failed")
    assert cloud.deleted == []


@pytest.mark.asyncio
async def test_non_admin_cannot_inspect_or_delete(non_admin_client, mock_conn):
    assert (await non_admin_client.get(f"{URL}/deletion-check")).status_code == 403
    assert (await non_admin_client.delete(URL)).status_code == 403
    assert mock_conn.method_calls == []
