"""Complete monitor GET and single normal DELETE through the installed native SDK."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qsl, urlsplit

import pytest
from keystoneclient.v3.client import Client as KeystoneClient

from app.api.deps import get_admin_os_conn
from app.api.identity import admin_identity
from app.main import app
from app.services import keystone, project_cleanup
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_project_deletion import (
    FOREIGN,
    KINDS,
    LEAK,
    TARGET,
    URL,
    FakeCloud,
    _response,
    item,
    later_page,
    seed_target,
)

SINGULAR = {
    "instances": "server",
    "server_groups": "server_group",
    "volumes": "volume",
    "volume_snapshots": "snapshot",
    "volume_backups": "backup",
    "networks": "network",
    "subnets": "subnet",
    "routers": "router",
    "ports": "port",
    "floating_ips": "floatingip",
    "security_groups": "security_group",
    "images": "image",
}


class CleanupCloud(FakeCloud):
    """Provider simulator extends existing pagination fixture with exact native details/deletes."""

    def __init__(self):
        super().__init__()
        self.resource_deletes = []
        self.detail_failures = {}
        self.delete_failures = {}
        self.projects = {}
        self.backup_versions = []

    def _backup_row(self, request, row):
        header = request.headers.get(
            "OpenStack-API-Version", request.headers.get("X-OpenStack-Volume-API-Version", "3.0")
        )
        version = tuple(int(part) for part in header.split()[-1].split("."))
        self.backup_versions.append(version)
        if version < (3, 18):
            return {key: value for key, value in row.items() if key not in KINDS["volume_backups"].owners}
        return row

    def _page(self, request, url, name, query):
        body = super()._page(request, url, name, query)
        if name == "volume_backups":
            body["backups"] = [self._backup_row(request, row) for row in body["backups"]]
        return body

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        path = url.path.rstrip("/")
        query = dict(parse_qsl(url.query))
        if url.netloc == "keystone.test" and path.startswith("/v3/projects/") and request.method == "GET":
            resource_id = path.rsplit("/", 1)[-1]
            if resource_id in self.projects:
                self.requests.append((request.method, url.netloc, path, query))
                return _response(request, 200, {"project": self.projects[resource_id]})
        if url.netloc == "keystone.test" and path == "/v3/projects" and query.get("marker"):
            self.requests.append((request.method, url.netloc, path, query))
            return _response(request, 200, {"projects": []})
        for kind, spec in KINDS.items():
            if path in spec.paths:
                # Collection /detail is not an individual object named detail.
                continue
            bases = [base for base in spec.paths if not base.endswith("/detail")]
            base = next((base for base in bases if path.startswith(base + "/")), None)
            if url.netloc != spec.host or base is None:
                continue
            resource_id = path[len(base) + 1 :]
            self.requests.append((request.method, url.netloc, path, query))
            if request.method == "GET" and kind in self.detail_failures:
                return _response(request, self.detail_failures[kind], {"error": {"message": LEAK}})
            row = next((row for row in self.rows[kind] if row["id"] == resource_id), None)
            if row is None:
                return _response(request, 404, {"error": {"message": LEAK}})
            if request.method == "GET":
                if kind == "volume_backups":
                    row = self._backup_row(request, row)
                return _response(request, 200, row if kind == "images" else {SINGULAR[kind]: row})
            if request.method == "DELETE":
                failure = self.delete_failures.get(kind)
                if failure:
                    response = _response(request, failure, {"error": {"message": LEAK}})
                    if failure in (307, 308):
                        response.headers["Location"] = "http://sink.test/secret-target"
                    return response
                self.resource_deletes.append((kind, resource_id))
                self.rows[kind].remove(row)
                return _response(request, 204, None)
        return super().send(request, **kwargs)


@pytest.fixture
async def cleanup_native(admin_client, monkeypatch, ownership_journal):
    cloud = CleanupCloud()

    async def connection():
        conn = cloud.connect()
        try:
            yield conn
        finally:
            conn.close()

    native = cloud.connect()
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: KeystoneClient(session=native.session))
    app.dependency_overrides[get_admin_os_conn] = connection
    try:
        yield admin_client, cloud
    finally:
        native.close()
    assert not cloud.unexpected


async def monitor(client, kind, project=TARGET, domain="default"):
    return await client.get(f"/api/v1/admin/projects/{project}/resources", params={"domain_id": domain, "kind": kind})


async def remove(client, kind, resource_id, project=TARGET, domain="default"):
    return await client.delete(
        f"/api/v1/admin/projects/{project}/resources/{kind}/{resource_id}", params={"domain_id": domain}
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", tuple(KINDS))
async def test_complete_scoped_monitor_exhausts_pages_without_writes(cleanup_native, kind):
    client, cloud = cleanup_native
    wanted = seed_target(cloud, kind, 7)
    cloud.rows[kind].append(item(kind, "foreign", FOREIGN))
    response = await monitor(client, kind)
    assert response.status_code == 200, response.text
    assert response.headers["Cache-Control"] == "no-store, private"
    result = response.json()
    assert (result["project_id"], result["kind"], result["status"], result["count"]) == (TARGET, kind, "ok", 7)
    assert result["reason"] is None
    assert {row["id"] for row in result["resources"]} == set(wanted)
    assert all(set(row) <= {"id", "name", "status"} for row in result["resources"])
    assert not cloud.resource_deletes and not cloud.deleted
    assert all(method == "GET" for method, *_ in cloud.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", tuple(KINDS))
async def test_later_page_failure_never_returns_partial_success(cleanup_native, kind):
    client, cloud = cleanup_native
    seed_target(cloud, kind, 7)
    cloud.failures[kind] = (later_page, 503)
    response = await monitor(client, kind)
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["resources"] == [] and response.json()["count"] is None
    assert LEAK not in response.text and not cloud.resource_deletes


@pytest.mark.asyncio
async def test_native_denial_and_missing_ownership_are_not_empty(cleanup_native):
    client, cloud = cleanup_native
    cloud.denied.add("neutron.test")
    response = await monitor(client, "networks")
    assert response.json()["status"] == "unavailable"
    cloud.denied.clear()
    cloud.rows["networks"] = [{"id": "network", "name": "name"}]
    response = await monitor(client, "networks")
    assert response.json()["status"] == "unavailable" and response.json()["count"] is None
    assert not cloud.resource_deletes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["networks", "subnets", "routers", "server_groups", "floating_ips", "security_groups", "images"]
)
async def test_exact_single_normal_deletion_and_fresh_readback(cleanup_native, kind):
    client, cloud = cleanup_native
    cloud.rows[kind] = [item(kind, "owned", TARGET, protected=False), item(kind, "foreign", FOREIGN)]
    response = await remove(client, kind, "owned")
    assert response.status_code == 204, response.text
    assert cloud.resource_deletes == [(kind, "owned")]
    report = await monitor(client, kind)
    assert report.json()["status"] == "ok" and report.json()["count"] == 0
    assert cloud.rows[kind][0]["id"] == "foreign"


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["foreign", "missing", "moved", "ownerless", "denied"])
async def test_fresh_detail_ownership_or_denial_never_dispatches_delete(cleanup_native, state):
    client, cloud = cleanup_native
    cloud.rows["networks"] = [item("networks", "network", TARGET)]
    assert (await monitor(client, "networks")).json()["count"] == 1
    expected = 403
    if state in {"foreign", "moved"}:
        cloud.rows["networks"][0].update(project_id=FOREIGN, tenant_id=FOREIGN)
    elif state == "missing":
        cloud.rows["networks"] = []
        expected = 404
    elif state == "ownerless":
        cloud.rows["networks"] = [{"id": "network"}]
        expected = 503
    else:
        cloud.detail_failures["networks"] = 403
    response = await remove(client, "networks", "network")
    assert response.status_code == expected, response.text
    assert LEAK not in response.text and not cloud.resource_deletes


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [401, 403, 409, 307, 308, 503])
async def test_native_delete_is_single_attempt_no_redirect_no_reauth(cleanup_native, failure):
    client, cloud = cleanup_native
    cloud.rows["networks"] = [item("networks", "network", TARGET)]
    cloud.delete_failures["networks"] = failure
    response = await remove(client, "networks", "network")
    assert response.status_code >= 400, response.text
    assert LEAK not in response.text
    writes = [(method, host, path) for method, host, path, _ in cloud.requests if method != "GET"]
    assert writes == [("DELETE", "neutron.test", "/v2.0/networks/network")]
    assert not cloud.resource_deletes


@pytest.mark.asyncio
async def test_default_security_group_and_attached_ip_are_protected(cleanup_native):
    client, cloud = cleanup_native
    cloud.rows["security_groups"] = [item("security_groups", "default-sg", TARGET, name="default")]
    assert (await monitor(client, "security_groups")).json()["count"] == 1
    assert (await remove(client, "security_groups", "default-sg")).status_code == 409
    cloud.rows["floating_ips"] = [item("floating_ips", "ip", TARGET, port_id="attached-port")]
    assert (await remove(client, "floating_ips", "ip")).status_code == 409
    assert not cloud.resource_deletes


@pytest.mark.asyncio
async def test_unknown_kind_required_domain_and_domain_mismatch(cleanup_native):
    client, cloud = cleanup_native
    assert (await monitor(client, "not-a-kind")).status_code == 422
    assert (await remove(client, "not-a-kind", "resource")).status_code == 422
    assert (await client.get(URL + "/resources", params={"kind": "networks"})).status_code == 422
    cloud.projects[TARGET] = {"id": TARGET, "domain_id": "other", "name": "moved"}
    assert (await monitor(client, "networks")).status_code == 403
    assert (await remove(client, "networks", "network")).status_code == 403
    assert not cloud.resource_deletes


@pytest.mark.asyncio
async def test_non_admin_cannot_list_or_delete(client):
    assert (await monitor(client, "networks")).status_code == 403
    assert (await remove(client, "networks", "network")).status_code == 403


@pytest.mark.asyncio
async def test_child_list_and_delete_use_full_project_guard(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    child = {"id": "child", "name": "Child", "domain_id": "default", "parent_id": TARGET}
    cloud.children = [child]
    cloud.projects["child"] = child
    response = await monitor(client, "child_projects")
    assert response.json()["status"] == "ok" and response.json()["resources"] == [{"id": "child", "name": "Child"}]
    # Child native resources prevent deletion through the unchanged complete guard.
    cloud.rows["networks"] = [item("networks", "child-network", "child")]
    response = await remove(client, "child_projects", "child")
    assert response.status_code == 409 and response.json()["detail"]["code"] == "project_has_resources"
    assert not cloud.deleted
    cloud.rows["networks"] = []
    response = await remove(client, "child_projects", "child")
    assert response.status_code == 204, response.text
    assert cloud.deleted == ["child"] and TARGET not in cloud.deleted


@pytest.mark.asyncio
async def test_child_moved_parent_default_and_unresolved_journal_never_delete(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    cloud.projects["child"] = {"id": "child", "name": "Child", "domain_id": "default", "parent_id": FOREIGN}
    assert (await remove(client, "child_projects", "child")).status_code == 403
    cloud.projects["child"]["parent_id"] = TARGET
    monkeypatch.setattr(
        admin_identity.domain_projects,
        "assert_default_immutable",
        lambda *a, **kw: (_ for _ in ()).throw(__import__("fastapi").HTTPException(409, "default")),
    )
    assert (await remove(client, "child_projects", "child")).status_code == 409
    assert not cloud.deleted


@pytest.mark.asyncio
async def test_volume_uses_durable_unmanaged_guard_before_mutation(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    from app.services import volume_transfers

    cloud.rows["volumes"] = [item("volumes", "volume", TARGET, status="available", attachments=[])]
    guard = AsyncMock(side_effect=volume_transfers.TransferError(409, "private provider detail"))
    monkeypatch.setattr(volume_transfers, "assert_unmanaged", guard)
    response = await remove(client, "volumes", "volume")
    assert response.status_code == 409 and "private provider" not in response.text
    guard.assert_awaited_once()
    assert not cloud.resource_deletes


@pytest.mark.asyncio
async def test_managed_instance_marker_and_durable_binding_block_normal_deletion(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    from app.services import layer_consume_resources

    cloud.rows["instances"] = [item("instances", "managed", TARGET, metadata={"layer_transport": "block"})]
    assert (await remove(client, "instances", "managed")).status_code == 409
    cloud.rows["instances"][0]["metadata"] = {}
    monkeypatch.setattr(layer_consume_resources, "lookup_for_server", AsyncMock(return_value=[42]))
    assert (await remove(client, "instances", "managed")).status_code == 409
    assert not cloud.resource_deletes


def test_sdk_descriptor_ownership_wins_over_stale_dict_snapshot():
    from openstack.network.v2.network import Network

    row = Network(id="network", project_id=TARGET)
    row.project_id = FOREIGN
    assert project_cleanup._owner(row, "networks") == FOREIGN


def test_transport_copy_disables_mutation_replay_without_changing_shared_proxy():
    cloud = CleanupCloud()
    conn = cloud.connect()
    try:
        proxy = conn.network
        before = proxy.request
        safe = project_cleanup.safe_proxy(proxy)
        assert proxy.request == before
        assert safe.request.keywords == {
            "allow_reauth": False,
            "connect_retries": 0,
            "status_code_retries": 0,
            "redirect": False,
            "skip_cache": True,
        }
    finally:
        conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "metadata",
    [
        {"afterglow_share_grant_share": "private-grant"},
        {"afterglow_managed_by": "afterglow", "afterglow_purpose": "cloud-shell-home"},
        {"afterglow_workspace": "workspace", "afterglow_signature": "signature"},
    ],
)
async def test_managed_grant_or_home_marker_never_dispatches_native_delete(cleanup_native, metadata):
    client, cloud = cleanup_native
    cloud.rows["instances"] = [item("instances", "managed", TARGET, metadata=metadata)]
    assert (await remove(client, "instances", "managed")).status_code == 409
    cloud.rows["volumes"] = [
        item("volumes", "managed-volume", TARGET, metadata=metadata, status="available", attachments=[])
    ]
    assert (await remove(client, "volumes", "managed-volume")).status_code == 409
    assert not cloud.resource_deletes


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["instances", "volumes", "volume_snapshots", "volume_backups", "ports"])
async def test_unmanaged_core_kind_single_delete(cleanup_native, monkeypatch, kind):
    client, cloud = cleanup_native
    from app.services import layer_consume_resources, palimpsest_catalog_cleanup, volume_transfers

    monkeypatch.setattr(volume_transfers, "assert_unmanaged", AsyncMock())
    monkeypatch.setattr(layer_consume_resources, "lookup_for_server", AsyncMock(return_value=[]))
    monkeypatch.setattr(palimpsest_catalog_cleanup, "lookup_catalog_consume", AsyncMock(return_value=None))
    if kind == "ports":
        # This case tests the normal native transport; the dedicated managed
        # marker/ledger tests exercise refusal before dispatch independently.
        monkeypatch.setattr(project_cleanup, "assert_deletion_safe", AsyncMock())
    cloud.rows[kind] = [
        item(kind, "owned", TARGET, status="available", attachments=[], metadata={}, volume_id="parent")
    ]
    if kind in {"volume_snapshots", "volume_backups"}:
        cloud.rows["volumes"] = [item("volumes", "parent", TARGET, status="available", attachments=[])]
    response = await remove(client, kind, "owned")
    assert response.status_code == 204, response.text
    assert cloud.resource_deletes == [(kind, "owned")]


@pytest.mark.asyncio
async def test_redirect_with_valid_empty_body_cannot_prove_empty(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    original = cloud.send

    def redirected(request, **kwargs):
        if urlsplit(request.url).path == "/v2.0/networks":
            return _response(request, 307, {"networks": []})
        return original(request, **kwargs)

    monkeypatch.setattr(cloud, "send", redirected)
    response = await monitor(client, "networks")
    assert response.json()["status"] == "unavailable" and response.json()["count"] is None
    assert not cloud.resource_deletes


@pytest.mark.asyncio
async def test_child_unresolved_ownership_journal_blocks_deletion(cleanup_native, ownership_journal):
    from app.models.project_ownership import ProjectOwnershipTransfer

    client, cloud = cleanup_native
    cloud.projects["child"] = {"id": "child", "name": "Child", "domain_id": "default", "parent_id": TARGET}
    async with ownership_journal() as session:
        session.add(
            ProjectOwnershipTransfer(
                id="unknown-transfer",
                project_id="child",
                domain_id="default",
                from_user_id="old",
                to_user_id="new",
                status="unknown",
                stage="grant",
            )
        )
        await session.commit()
    response = await remove(client, "child_projects", "child")
    assert response.status_code == 409, response.text
    assert not cloud.deleted and not cloud.resource_deletes


@pytest.mark.asyncio
async def test_backup_list_and_detail_request_native_ownership_microversion(cleanup_native, monkeypatch):
    client, cloud = cleanup_native
    from app.services import volume_transfers

    monkeypatch.setattr(volume_transfers, "assert_unmanaged", AsyncMock())
    cloud.rows["volume_backups"] = [item("volume_backups", "backup", TARGET, status="available", volume_id="parent")]
    cloud.rows["volumes"] = [item("volumes", "parent", TARGET)]
    result = await monitor(client, "volume_backups")
    assert result.json()["status"] == "ok" and result.json()["count"] == 1
    assert (await remove(client, "volume_backups", "backup")).status_code == 204
    assert len(cloud.backup_versions) >= 3 and all(version >= (3, 18) for version in cloud.backup_versions)


@pytest.mark.asyncio
@pytest.mark.parametrize("managed", [False, True])
async def test_orphan_backup_deletion_keeps_source_id_ledger_guard(cleanup_native, monkeypatch, managed):
    client, cloud = cleanup_native
    cloud.rows["volume_backups"] = [
        item("volume_backups", "backup", TARGET, status="available", volume_id="deleted-source")
    ]
    rows = [(42, TARGET, [{"kind": "volume", "id": "deleted-source", "state": "created"}], {}, None)] if managed else []
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: rows)))

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    response = await remove(client, "volume_backups", "backup")
    assert response.status_code == (409 if managed else 204), response.text
    assert cloud.resource_deletes == ([] if managed else [("volume_backups", "backup")])
    session.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_backup_source_denial_is_not_orphan_permission(cleanup_native):
    client, cloud = cleanup_native
    cloud.rows["volume_backups"] = [item("volume_backups", "backup", TARGET, status="available", volume_id="source")]
    cloud.detail_failures["volumes"] = 403
    assert (await remove(client, "volume_backups", "backup")).status_code == 403
    assert not cloud.resource_deletes
