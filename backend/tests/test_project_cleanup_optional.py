"""Optional cleanup behavior through native Keystoneauth transport and API boundaries.

No provider helper is mocked into returning a successful cleanup inventory.
"""

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests
from fastapi import HTTPException
from keystoneauth1 import access
from keystoneauth1 import session as ks_session
from keystoneauth1.adapter import Adapter
from keystoneauth1.identity.access import AccessInfoPlugin
from requests.adapters import BaseAdapter

from app.services import project_cleanup_optional as cleanup

TARGET = "target-project"
FOREIGN = "foreign-project"
SECRET = "provider-password-and-secret-name"


def response(request, code, body=None, headers=None):
    result = requests.Response()
    result.request = request
    result.url = request.url
    result.status_code = code
    result._content = b"" if body is None else json.dumps(body).encode()
    result.headers.update(headers or {})
    result.headers.setdefault("Content-Type", "application/json")
    return result


def token(catalog, roles=("admin",), project=TARGET):
    return access.create(
        auth_token="native-token",
        body={
            "token": {
                "methods": ["token"],
                "expires_at": "2036-10-26T00:00:00Z",
                "issued_at": "2026-10-26T00:00:00Z",
                "user": {"id": "actor", "domain": {"id": "default"}},
                "project": {"id": project, "domain": {"id": "default"}},
                "roles": [{"id": role, "name": role} for role in roles],
                "is_admin_project": True,
                "catalog": [
                    {
                        "id": service,
                        "type": service,
                        "name": service,
                        "endpoints": [{"id": service, "interface": "public", "url": endpoint}],
                    }
                    for service, endpoint in catalog.items()
                ],
            }
        },
    )


class NativeProvider(BaseAdapter):
    """Tiny native provider, preserving HTTP paths, headers, paging and errors."""

    def __init__(self, kind):
        super().__init__()
        self.kind = kind
        self.spec = cleanup._SPECS[kind]
        self.calls = []
        self.rows = [self.row(f"resource-{index}") for index in range(3)]
        self.detail_changes = {}
        self.parent_changes = {}
        self.fail_page = False
        self.denied = False
        self.delete_status = 204
        self.next_url = None
        self.base = "/v1"
        if kind == "object_containers":
            self.base += f"/AUTH_{TARGET}"
        elif kind in ("stacks", "database_instances", "database_backups", "database_configurations"):
            self.base += f"/{TARGET}"
        self.endpoint = f"http://native.test{self.base}"
        service = self.spec[4][0]
        http = requests.Session()
        http.trust_env = False
        http.mount("http://", self)
        auth = AccessInfoPlugin(token({service: self.endpoint}))
        native_session = ks_session.Session(auth=auth, session=http)
        self.proxy = Adapter(session=native_session, service_type=service, endpoint_override=self.endpoint)
        self.conn = SimpleNamespace(session=native_session, current_project_id=TARGET)
        setattr(self.conn, self.spec[0], self.proxy)
        if kind == "containers":
            # Zun intentionally has no openstacksdk proxy: use the real session.
            self.conn.session = native_session

    def row(self, identifier, owner=TARGET):
        result = {"id": identifier, "project_id": owner, "name": SECRET, "status": "STOPPED"}
        if self.kind == "share_snapshots":
            result["share_id"] = "parent-share"
        if self.kind == "stacks":
            result["stack_name"] = "stack name"
        if self.kind in cleanup._PRIVATE:
            del result["project_id"]
        return result

    def send(self, request, **kwargs):
        parsed = urlsplit(request.url)
        path = unquote(parsed.path).removeprefix(self.base).rstrip("/") or "/"
        self.calls.append((request.method, request.url, dict(request.headers)))
        if parsed.hostname != "native.test":
            raise AssertionError("Authentication forwarded to provider next URL")
        if self.kind == "containers":
            path = unquote(parsed.path)
        collection = self.spec[1]
        if self.kind == "containers":
            collection = "/v1/containers"
        if self.kind == "containers" and path != collection and parse_qs(parsed.query).get("all_projects") != ["True"]:
            return response(request, 404, {"error": SECRET})
        if request.method == "DELETE":
            return response(request, self.delete_status, {"error": SECRET} if self.delete_status != 204 else None)
        if self.denied:
            return response(request, 403, {"error": SECRET})
        if request.method == "HEAD":
            return response(request, 204)
        if path == collection or (self.kind == "object_containers" and path == "/"):
            query = parse_qs(parsed.query)
            start = int(query.get("offset", [0])[0])
            marker = query.get("marker", [None])[0]
            if marker:
                start = next(index + 1 for index, row in enumerate(self.rows) if row["id"] == marker)
            if self.fail_page and start >= 2:
                return response(request, 503, {"error": SECRET})
            rows = [dict(row) for row in self.rows[start : start + 2]]
            if self.kind == "object_containers":
                return response(request, 200, [{"name": row["id"], "count": 0} for row in rows])
            body = {self.spec[2]: rows}
            if rows and self.next_url:
                body["next"] = (
                    f"{self.next_url}?{'offset' if self.spec[5] else 'marker'}={start + len(rows) if self.spec[5] else rows[-1]['id']}"
                )
            return response(request, 200, body)
        if self.kind == "share_snapshots" and path == "/shares/parent-share":
            return response(
                request, 200, {"share": {"id": "parent-share", "project_id": TARGET, **self.parent_changes}}
            )
        identifier = path.rsplit("/", 1)[-1]
        row = next((dict(row) for row in self.rows if row["id"] == identifier), None)
        if row is None:
            return response(request, 404, {"error": SECRET})
        row.update(self.detail_changes)
        envelope = self.spec[3]
        return response(request, 200, {envelope: row} if envelope else row)

    def close(self):
        pass


@pytest.mark.parametrize("kind", sorted(cleanup.OPTIONAL_KINDS))
def test_all_optional_kinds_return_complete_metadata_and_one_normal_delete(kind):
    native = NativeProvider(kind)
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert result["status"] == "ok"
    assert result["count"] == 3
    assert [row["id"] for row in result["resources"]] == [f"resource-{i}" for i in range(3)]
    if kind in cleanup._PRIVATE:
        assert SECRET not in json.dumps(result)
        native.detail_changes["name"] = "user-owned"
    cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    if kind in cleanup._PRIVATE:
        assert all(headers.get("Accept") == "application/json" for _, _, headers in native.calls)
    mutations = [call for call in native.calls if call[0] != "GET" and call[0] != "HEAD"]
    assert len(mutations) == 1
    method, url, _ = mutations[0]
    assert method == "DELETE"
    assert parse_qs(urlsplit(url).query) == ({"all_projects": ["True"]} if kind == "containers" else {})
    assert "force" not in url and "cascade" not in url and "stop=" not in url
    if kind == "stacks":
        assert "/stacks/stack%20name/resource-0" in url
    if kind == "database_instances":
        assert urlsplit(url).path == f"/v1/{TARGET}/instances/resource-0"
    if kind in ("shares", "share_snapshots", "share_networks", "security_services"):
        assert all(call[2].get("OpenStack-API-Version") == "shared-file-system 2.73" for call in native.calls)


@pytest.mark.parametrize("kind", sorted(cleanup.OPTIONAL_KINDS))
def test_later_page_failure_is_unavailable_not_a_partial_list(kind):
    native = NativeProvider(kind)
    native.fail_page = True
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert result == {"status": "unavailable", "reason": "resource_check_failed", "resources": [], "count": None}
    assert SECRET not in json.dumps(result)
    assert all(method == "GET" for method, _, _ in native.calls)


@pytest.mark.parametrize("kind", sorted(cleanup.OPTIONAL_KINDS))
def test_denied_and_missing_service_are_distinct(kind):
    native = NativeProvider(kind)
    native.denied = True
    assert cleanup.list_resources(native.conn, TARGET, kind)["status"] == "unavailable"
    native.conn.session.auth = AccessInfoPlugin(token({}))
    assert cleanup.list_resources(native.conn, TARGET, kind) == {
        "status": "skipped",
        "reason": "service_not_present",
        "resources": [],
        "count": None,
    }
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.status_code == 503
    assert not any(method == "DELETE" for method, _, _ in native.calls)


@pytest.mark.parametrize("kind", sorted(cleanup.OPTIONAL_KINDS - cleanup.REQUIRED_PROJECT_SCOPE_KINDS))
@pytest.mark.parametrize("change,status", [({"project_id": FOREIGN}, 403), ({"id": "different"}, 503)])
def test_fresh_native_detail_moved_missing_owner_or_wrong_identity_never_deletes(kind, change, status):
    native = NativeProvider(kind)
    native.detail_changes = change
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.status_code == status
    assert not any(method == "DELETE" for method, _, _ in native.calls)


@pytest.mark.parametrize("kind", sorted(cleanup.OPTIONAL_KINDS - cleanup.REQUIRED_PROJECT_SCOPE_KINDS - {"stacks"}))
def test_native_detail_without_owner_is_not_inferred_from_an_admin_token(kind):
    native = NativeProvider(kind)
    native.detail_changes = {"project_id": None}
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.status_code == 503
    assert not any(method == "DELETE" for method, _, _ in native.calls)


def test_heat_fresh_owned_index_and_exact_name_id_detail_support_native_ownerless_detail():
    native = NativeProvider("stacks")
    native.detail_changes = {"project_id": None}
    cleanup.delete_resource(native.conn, TARGET, "stacks", "resource-0")
    assert sum(method == "DELETE" for method, _, _ in native.calls) == 1


@pytest.mark.parametrize("kind", sorted(cleanup.REQUIRED_PROJECT_SCOPE_KINDS))
def test_scoped_services_reject_actual_token_project_mismatch(kind):
    native = NativeProvider(kind)
    catalog = {native.spec[4][0]: native.endpoint}
    native.conn.session.auth = AccessInfoPlugin(token(catalog, project=FOREIGN))
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert result["reason"] == "project_scope_unverified"
    with pytest.raises(HTTPException):
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert not native.calls


def test_swift_account_scope_must_match_and_full_long_name_is_preserved():
    native = NativeProvider("object_containers")
    identifier = "container-" + "a" * 240
    native.rows = [native.row(identifier)]
    assert cleanup.list_resources(native.conn, TARGET, native.kind)["resources"][0]["id"] == identifier
    cleanup.delete_resource(native.conn, TARGET, native.kind, identifier)
    assert urlsplit(native.calls[-1][1]).path.endswith(identifier)
    native.proxy.endpoint_override = f"http://native.test/v1/AUTH_{FOREIGN}"
    result = cleanup.list_resources(native.conn, TARGET, native.kind)
    assert result["reason"] == "project_scope_unverified"


@pytest.mark.parametrize("kind", sorted(cleanup._PRIVATE))
def test_barbican_acl_detail_not_in_owned_project_index_cannot_delete(kind):
    native = NativeProvider(kind)
    native.rows = []
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "shared-secret")
    assert error.value.status_code == 404
    assert not any(method == "DELETE" for method, _, _ in native.calls)


def test_trove_configuration_exact_detail_can_supply_owner_not_admin_index():
    native = NativeProvider("database_configurations")
    for row in native.rows:
        row.pop("project_id")
    native.detail_changes = {"tenant_id": TARGET}
    assert cleanup.list_resources(native.conn, TARGET, native.kind)["count"] == 3
    cleanup.delete_resource(native.conn, TARGET, native.kind, "resource-0")
    assert any(method == "DELETE" for method, _, _ in native.calls)


def test_trove_ownerless_admin_configuration_is_explicitly_unverified_even_at_target_path():
    native = NativeProvider("database_configurations")
    for row in native.rows:
        row.pop("project_id")
    result = cleanup.list_resources(native.conn, TARGET, native.kind)
    assert result["reason"] == "resource_ownership_unverified"
    assert result["count"] is None and result["resources"] == []
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, native.kind, "resource-0")
    assert error.value.status_code == 503
    assert not any(method == "DELETE" for method, _, _ in native.calls)
    assert any("/configurations/resource-0" in url for _, url, _ in native.calls)


def test_trove_non_admin_exact_tenant_native_path_is_authoritative_for_ownerless_configuration():
    native = NativeProvider("database_configurations")
    for row in native.rows:
        row.pop("project_id")
    native.conn.session.auth = AccessInfoPlugin(token({"database": native.endpoint}, roles=("member",)))
    assert cleanup.list_resources(native.conn, TARGET, native.kind)["count"] == 3
    cleanup.delete_resource(native.conn, TARGET, native.kind, "resource-0")
    assert sum(method == "DELETE" for method, _, _ in native.calls) == 1


@pytest.mark.parametrize("kind", ["shares", "share_snapshots", "load_balancers", "clusters", "stacks", "containers"])
def test_managed_native_metadata_cannot_be_deleted(kind):
    native = NativeProvider(kind)
    native.detail_changes["metadata"] = {"drover_cluster_id": "cluster"}
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.status_code == 409
    assert not any(method == "DELETE" for method, _, _ in native.calls)


@pytest.mark.parametrize("kind", sorted(cleanup._PRIVATE))
def test_managed_barbican_names_are_never_exposed_or_deleted(kind):
    native = NativeProvider(kind)
    native.detail_changes["name"] = "afterglow-managed-secret"
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert "afterglow-managed-secret" not in json.dumps(result)
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.detail == "resource_is_system_managed"
    assert not any(method == "DELETE" for method, _, _ in native.calls)


def test_running_zun_requires_explicit_stop_elsewhere_and_never_forces_or_stops():
    native = NativeProvider("containers")
    native.detail_changes["status"] = "Running"
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, native.kind, "resource-0")
    assert error.value.detail == "container_must_be_stopped"
    assert not any(method != "GET" for method, _, _ in native.calls)


@pytest.mark.parametrize("kind", ["shares", "secrets", "clusters", "stacks", "containers"])
def test_provider_next_url_is_never_a_credential_destination(kind):
    native = NativeProvider(kind)
    native.next_url = "http://credential-sink.test/steal"
    assert cleanup.list_resources(native.conn, TARGET, kind)["count"] == 3
    assert all(urlsplit(url).hostname == "native.test" for _, url, _ in native.calls)


@pytest.mark.parametrize("identifier", ["..", ".", "a/b", "https://sink.invalid/a", "\x00"])
def test_unsafe_identifier_never_reaches_native_provider(identifier):
    native = NativeProvider("shares")
    with pytest.raises(HTTPException):
        cleanup.delete_resource(native.conn, TARGET, "shares", identifier)
    assert not native.calls


@pytest.mark.parametrize("status", [401, 403, 404, 409, 500])
def test_delete_native_error_is_sanitized_and_never_replayed(status):
    native = NativeProvider("shares")
    native.delete_status = status
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, "shares", "resource-0")
    assert SECRET not in str(error.value.detail)
    assert sum(method == "DELETE" for method, _, _ in native.calls) == 1


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401])
def test_actual_tcp_mutation_does_not_redirect_or_reauthenticate(status):
    calls = Counter()

    class RefreshableToken(AccessInfoPlugin):
        def invalidate(self):
            calls[("AUTH", "invalidate")] += 1
            return True

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            calls[("GET", self.path)] += 1
            body = json.dumps({"share": {"id": "resource", "project_id": TARGET, "status": "available"}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_DELETE(self):
            calls[("DELETE", self.path)] += 1
            self.send_response(status)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/sink")
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}/v2/{TARGET}"
    http = requests.Session()
    http.trust_env = False
    auth = RefreshableToken(token({"sharev2": endpoint}))
    session = ks_session.Session(auth=auth, session=http)
    conn = SimpleNamespace(
        session=session,
        current_project_id=TARGET,
        shared_file_system=Adapter(session=session, endpoint_override=endpoint, service_type="sharev2"),
    )
    try:
        with pytest.raises(HTTPException):
            cleanup.delete_resource(conn, TARGET, "shares", "resource")
        assert calls[("DELETE", f"/v2/{TARGET}/shares/resource")] == 1
        assert not any("sink" in path for _, path in calls)
        assert sum(count for (method, _), count in calls.items() if method == "DELETE") == 1
        assert calls[("AUTH", "invalidate")] == 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        session.session.close()


@pytest.mark.asyncio
async def test_optional_monitor_endpoint_preserves_complete_metadata_and_exact_domain(
    admin_client, mock_conn, monkeypatch
):
    from app.services import keystone

    native = NativeProvider("shares")
    mock_conn.shared_file_system = native.proxy
    mock_conn.session.auth.get_access.return_value = native.conn.session.auth.get_access(native.conn.session)
    mock_conn.identity.get_project.return_value = SimpleNamespace(id=TARGET, domain_id="default")
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    native_identity = SimpleNamespace(projects=SimpleNamespace(list=lambda **kwargs: []))
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native_identity)
    url = f"/api/v1/admin/projects/{TARGET}/resources?domain_id=default&kind=shares"
    result = await admin_client.get(url)
    assert result.status_code == 200
    body = result.json()
    assert body["project_id"] == TARGET and body["kind"] == "shares"
    assert body["status"] == "ok" and body["count"] == 3
    deleted = await admin_client.delete(
        f"/api/v1/admin/projects/{TARGET}/resources/shares/resource-0?domain_id=default"
    )
    assert deleted.status_code == 204
    assert sum(method == "DELETE" for method, _, _ in native.calls) == 1
    mock_conn.identity.delete_project.assert_not_called()


@pytest.mark.parametrize("kind", sorted(cleanup._PRIVATE))
def test_missing_private_identity_never_projects_the_secret_name_as_identifier(kind):
    native = NativeProvider(kind)
    native.rows = [{"name": SECRET, "status": "ACTIVE"}]
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert result["status"] == "unavailable"
    assert result["count"] is None and result["resources"] == []
    assert SECRET not in json.dumps(result)


@pytest.mark.parametrize("kind", ["shares", "load_balancers", "clusters", "containers", "stacks"])
def test_member_scoped_admin_ui_authority_cannot_prove_global_optional_inventory(kind):
    native = NativeProvider(kind)
    native.conn.session.auth = AccessInfoPlugin(token({native.spec[4][0]: native.endpoint}, roles=("member",)))
    result = cleanup.list_resources(native.conn, TARGET, kind)
    assert result["reason"] == "admin_authority_unverified"
    assert not native.calls


@pytest.mark.parametrize("identifier", ["50%-logs", "query?#fragment", "back\\slash"])
def test_swift_native_name_special_characters_are_encoded_not_truncated_or_reinterpreted(identifier):
    native = NativeProvider("object_containers")
    native.rows = [native.row(identifier)]
    result = cleanup.list_resources(native.conn, TARGET, native.kind)
    assert result["resources"] == [{"id": identifier, "name": identifier}]
    cleanup.delete_resource(native.conn, TARGET, native.kind, identifier)
    parsed = urlsplit(native.calls[-1][1])
    assert not parsed.query and not parsed.fragment
    assert unquote(parsed.path).rsplit("/", 1)[-1] == identifier


@pytest.mark.parametrize("kind", ["shares", "share_snapshots"])
@pytest.mark.parametrize(
    "marker", ["afterglow_build_id", "afterglow_build_token", "afterglow_role", "afterglow_layer_id"]
)
def test_palimpsest_native_share_markers_require_managed_cleanup(kind, marker):
    native = NativeProvider(kind)
    native.detail_changes["metadata"] = {marker: "build"}
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, kind, "resource-0")
    assert error.value.status_code == 409
    assert not any(method == "DELETE" for method, _, _ in native.calls)


def test_snapshot_of_active_palimpsest_share_cannot_bypass_parent_metadata_guard():
    native = NativeProvider("share_snapshots")
    native.parent_changes["metadata"] = {"afterglow_build_token": "opaque-build"}
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, native.kind, "resource-0")
    assert error.value.status_code == 409
    assert not any(method == "DELETE" for method, _, _ in native.calls)


@pytest.mark.parametrize("failed,matched", [(False, True), (True, False), (False, False)])
def test_magnum_owned_heat_stack_requires_magnum_teardown_and_failed_inventory_is_closed(failed, matched):
    heat = NativeProvider("stacks")
    magnum = NativeProvider("clusters")
    for row in magnum.rows:
        row["stack_id"] = "resource-0" if matched else "other-stack"
    magnum.fail_page = failed
    heat.conn.container_infrastructure_management = magnum.proxy
    heat.conn.session.auth = AccessInfoPlugin(
        token({"orchestration": heat.endpoint, "container-infra": magnum.endpoint})
    )
    if failed or matched:
        with pytest.raises(HTTPException) as error:
            cleanup.delete_resource(heat.conn, TARGET, "stacks", "resource-0")
        assert error.value.status_code == (409 if matched else 502)
        assert not any(method == "DELETE" for method, _, _ in heat.calls)
    else:
        cleanup.delete_resource(heat.conn, TARGET, "stacks", "resource-0")
        assert sum(method == "DELETE" for method, _, _ in heat.calls) == 1
    assert magnum.calls


@pytest.mark.parametrize("output_ref", ["secret_ref", "container_ref"])
def test_completed_barbican_order_identity_is_not_its_generated_resource(output_ref):
    class CompletedOrderProvider(NativeProvider):
        def send(self, request, **kwargs):
            result = super().send(request, **kwargs)
            if request.method == "GET" and result.status_code == 200:
                body = result.json()
                rows = body.get("orders", [body])
                for row in rows:
                    identifier = row.pop("id")
                    row.update(
                        order_ref=f"http://native.test/v1/orders/{identifier}",
                        status="ACTIVE",
                        name=SECRET,
                    )
                    row[output_ref] = "https://credential-sink.test/v1/generated/different-output-id"
                result._content = json.dumps(body).encode()
            return result

    native = CompletedOrderProvider("secret_orders")
    result = cleanup.list_resources(native.conn, TARGET, "secret_orders")
    assert result["status"] == "ok" and result["count"] == 3
    assert [row["id"] for row in result["resources"]] == [f"resource-{index}" for index in range(3)]
    assert SECRET not in json.dumps(result)
    cleanup.delete_resource(native.conn, TARGET, "secret_orders", "resource-0")
    deletes = [url for method, url, _ in native.calls if method == "DELETE"]
    assert len(deletes) == 1
    assert urlsplit(deletes[0]).path == "/v1/orders/resource-0"
    assert all(urlsplit(url).hostname == "native.test" for _, url, _ in native.calls)


def test_barbican_order_genuine_id_and_order_reference_mismatch_still_refuses_delete():
    native = NativeProvider("secret_orders")
    native.detail_changes["order_ref"] = "http://native.test/v1/orders/other-order"
    native.detail_changes["secret_ref"] = "http://native.test/v1/secrets/output-secret"
    with pytest.raises(HTTPException) as error:
        cleanup.delete_resource(native.conn, TARGET, "secret_orders", "resource-0")
    assert error.value.status_code == 503
    assert not any(method == "DELETE" for method, _, _ in native.calls)
