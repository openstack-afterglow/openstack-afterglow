"""Actual summary HTTP with deterministic identity/cloud/native read boundaries."""

from collections import Counter
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.main import app
from app.services import user_inventory as inventory

CATEGORIES = {
    "instances",
    "volumes",
    "floating_ips",
    "networks",
    "subnets",
    "routers",
    "security_groups",
    "load_balancers",
    "images",
    "keypairs",
    "database_instances",
    "database_backups",
    "k3s_clusters",
    "waygate_gateways",
    "containers",
    "magnum_clusters",
    "shares",
    "share_snapshots",
    "share_networks",
    "security_services",
    "buckets",
    "volume_snapshots",
    "volume_backups",
    "packages",
    "secrets",
}
URL = "/api/v1/user-dashboard/summary"


class ReadProxy:
    """Only native GET/list methods exist; unexpected mutation attempts are recorded."""

    def __init__(self, state, project, methods):
        self.state, self.project, self.methods = state, project, methods

    def __getattr__(self, method):
        if method not in self.methods:
            self.state.mutations.append(method)
            raise AssertionError("Inventory invoked a non-list primitive")
        category = self.methods[method]

        def listing(**query):
            assert not {"all_tenants", "all_projects", "all"}.intersection(query)
            if "project_id" in query:
                assert query["project_id"] == self.project
            if "owner" in query:
                assert query["owner"] == self.project
            if "user_id" in query:
                assert query["user_id"] == self.state.subject["user_id"]
            return self.state.rows(self.project, category)

        return listing


class InventoryState:
    def __init__(self, directory):
        self.directory = directory
        self.subject = {
            "user_id": "user-a",
            "project_id": "p-a",
            "token": "source-a",
            "domain_id": "tenant-a",
            "domain_name": "Tenant A",
            "identity_domain_id": "tenant-a",
            "identity_domain_name": "Tenant A",
            "is_domain_manager": False,
        }
        self.memberships = [
            {"id": "p-a", "name": "Alpha", "domain_id": "tenant-a"},
            {"id": "p-b", "name": "Beta", "domain_id": "tenant-a"},
        ]
        self.roles = {
            p: ["member", "drover-inventory_reader", "waygate-inventory_reader", "palimpsest-inventory_reader"]
            for p in ("p-a", "p-b")
        }
        directory.roles.extend(
            {"id": name + "-role", "name": name, "domain_id": None}
            for name in sorted({role for roles in self.roles.values() for role in roles} - {"member"})
        )
        self.system_grants = []
        self.assignment_errors = {}
        self.settings = SimpleNamespace(
            **{f"service_{gate}_enabled": True for _, gate in inventory.CATALOG.values() if gate}
        )
        self.data, self.errors, self.pages, self.package_pages = {}, {}, {}, {}
        self.calls, self.events, self.mutations, self.connections = Counter(), [], [], []
        self.identity_override = {}
        self.contexts = {}
        self.membership_error = None

    def sync_directory(self):
        """Publish current native resources/assignments before any request guard runs."""
        uid = self.subject["user_id"]
        self.directory.users[uid] = {
            "id": uid,
            "name": uid,
            "domain_id": self.subject["identity_domain_id"],
            "enabled": True,
        }
        self.directory.projects = {p["id"]: {**p, "enabled": True} for p in self.memberships}
        # Do not add conftest's implicit member grants on top of the explicit graph.
        self.directory.grants = {}
        self.directory.assignments = [
            *self.system_grants,
            *(
                {"user": {"id": uid}, "role": {"id": role + "-role"}, "scope": {"project": {"id": p["id"]}}}
                for p in self.memberships
                for role in self.roles.get(p["id"], [])
            ),
        ]

    def native_access(self, token, project):
        user, scope = self.identity_override.get(project, (self.subject["user_id"], project))
        identity = self.directory.users[self.subject["user_id"]]
        native_project = self.directory.projects[project]
        role_ids = {
            row["role"]["id"]
            for row in self.directory.assignments
            if row.get("user", {}).get("id") == user and row["scope"] == {"project": {"id": project}}
        }
        return SimpleNamespace(
            user_id=user,
            username=identity["name"],
            user_domain_id=identity["domain_id"],
            project_id=scope,
            project_name=native_project["name"],
            project_domain_id=native_project["domain_id"],
            auth_token=token,
            role_names=[role["name"] for role in self.directory.roles if role["id"] in role_ids],
            expires=None,
        )

    def rows(self, project, category):
        self.calls[project, category] += 1
        self.events.append(("list", project, category))
        if (project, category) in self.errors:
            raise self.errors[project, category]
        return self.data.get((project, category), [])

    def rest(self, project, path, key, endpoint):
        self.events.append(("rest", project, path))
        if (project, path) in self.pages:
            page = self.pages[project, path]
            if isinstance(page, Exception):
                raise page
            return page
        category = {
            "instances": "database_instances",
            "backups": "database_backups",
            "shares": "shares",
            "snapshots": "share_snapshots",
            "share_networks": "share_networks",
            "security_services": "security_services",
            "containers": "containers",
        }[key]
        return {key: self.rows(project, category)}

    def connection(self, token, project):
        self.events.append(("connection", token, project))
        issued = f"issued:{token}:{project}"

        def access(session):
            self.events.append(("identity", project))
            return self.native_access(issued, project)

        conn = SimpleNamespace(
            close=lambda: self.events.append(("close", project)),
            session=SimpleNamespace(auth=SimpleNamespace(get_access=access), get_token=lambda: issued),
            compute=ReadProxy(self, project, {"servers": "instances", "keypairs": "keypairs"}),
            block_storage=ReadProxy(
                self, project, {"volumes": "volumes", "snapshots": "volume_snapshots", "backups": "volume_backups"}
            ),
            network=ReadProxy(
                self,
                project,
                {
                    "ips": "floating_ips",
                    "networks": "networks",
                    "subnets": "subnets",
                    "routers": "routers",
                    "security_groups": "security_groups",
                },
            ),
            load_balancer=ReadProxy(self, project, {"load_balancers": "load_balancers"}),
            image=ReadProxy(self, project, {"images": "images"}),
            container_infrastructure_management=ReadProxy(self, project, {"clusters": "magnum_clusters"}),
            key_manager=ReadProxy(self, project, {"secrets": "secrets"}),
            object_store=ReadProxy(self, project, {"containers": "buckets"}),
        )
        endpoint = f"https://trove.test/v1.0/{project}"
        conn.database = SimpleNamespace(
            get_endpoint=lambda: endpoint,
            get=lambda path: self.rest(
                project, path, "instances" if path.startswith("/instances") else "backups", endpoint
            ),
        )
        conn.object_store.get_endpoint = lambda: f"https://swift.test/v1/AUTH_{project}"
        conn.session.get = lambda url: self.rest(
            project,
            urlsplit(url).path + ("?" + urlsplit(url).query if urlsplit(url).query else ""),
            "containers",
            "https://zun.test/v1",
        )
        self.connections.append(conn)
        return conn

    def manila(self, conn):
        project = conn._afterglow_project_id
        assert conn._afterglow_token == f"issued:{self.subject['token']}:{project}"
        assert conn._afterglow_user_id == self.subject["user_id"]
        endpoint = f"https://manila.test/v2/{project}"

        def get(path):
            key = {
                "shares": "shares",
                "snapshots": "snapshots",
                "share-networks": "share_networks",
                "security-services": "security_services",
            }[path.lstrip("/").split("/")[0].split("?")[0]]
            return self.rest(project, path, key, endpoint)

        return SimpleNamespace(base=endpoint, _url=lambda path: endpoint + path, get=get)

    def assert_scoped(self, request):
        info = request.state.token_info
        assert info["token"] == f"issued:{self.subject['token']}:{info['project_id']}"
        assert info["connection_project_id"] == info["project_id"]
        assert info["user_id"] == self.subject["user_id"]
        assert info["is_system_admin"] is False
        assert request.headers["x-auth-token"] == info["token"]
        assert request.headers["x-project-id"] == info["project_id"]
        assert "authorization" not in request.headers
        assert request.method == "GET" and not request.url.query
        return info

    async def remote(self, service, request, path):
        info = self.assert_scoped(request)
        assert path == {"drover": "/v1/clusters", "waygate": "/v1/servers"}[service]
        return self.rows(info["project_id"], {"drover": "k3s_clusters", "waygate": "waygate_gateways"}[service])

    async def package(self, request, path, *, query=None):
        info = self.assert_scoped(request)
        project = info["project_id"]
        self.events.append(("package", project, path, query))
        if path == "/v1/projects/current":
            return JSONResponse(
                self.contexts.get(
                    project,
                    {
                        "project_id": project,
                        "project_name": project,
                        "namespace": None,
                        "package_authority": None,
                        "capabilities": {
                            key: True
                            for key in (
                                "packages_read",
                                "packages_download",
                                "packages_write",
                                "keys_issue",
                                "keys_revoke",
                            )
                        },
                    },
                )
            )
        namespace = self.contexts.get(project, {}).get("namespace", f"ns-{project}")
        assert path == f"/v1/projects/{namespace}/packages"
        value = self.package_pages[project, query.get("cursor")]
        return JSONResponse(value)


@pytest.fixture
async def inventory_http(monkeypatch, auth_directory):
    """Keep native authority guards live; synthesize directory, token and resource I/O."""
    state = InventoryState(auth_directory)
    assignments = inventory.keystone._get_admin_ks_client().role_assignments.list

    def observed_assignments(**query):
        project = query.get("project")
        if project is not None:
            state.events.append(("membership", project, state.subject["user_id"]))
            if project in state.assignment_errors:
                raise state.assignment_errors[project]
        rows = assignments(**query)
        # Native effective assignment lists omit system grants. System authority
        # must still be established from the complete raw user/group source.
        if query.get("effective"):
            rows = [row for row in rows if "system" not in row["scope"]]
        return rows

    class Token:
        """Only the native token exchange is synthetic; validation guards still run."""

        def __init__(self, **kwargs):
            self.token, self.project = kwargs["token"], kwargs.get("project_id", "")

        def get_access(self, session):
            assert self.token == f"issued:{state.subject['token']}:{self.project}"
            state.events.append(("token", self.token, self.project))
            return state.native_access(self.token, self.project)

    async def subject(request: Request):
        state.sync_directory()
        request.state.token_info = {
            **state.subject,
            "roles": list(state.roles.get(state.subject["project_id"], [])),
            "is_system_admin": inventory.keystone._is_system_admin(state.subject["user_id"]),
        }
        return request.state.token_info

    def memberships(token, domain_id):
        assert token == state.subject["token"]
        state.events.append(("memberships", token))
        if state.membership_error:
            raise state.membership_error
        return state.memberships

    old_overrides = dict(app.dependency_overrides)
    app.dependency_overrides[get_token_info] = subject
    monkeypatch.setattr(inventory, "get_settings", lambda: state.settings)
    monkeypatch.setattr(inventory.keystone, "list_projects", memberships)
    monkeypatch.setattr(inventory.keystone, "get_openstack_connection", state.connection)
    monkeypatch.setattr(inventory.keystone.v3, "Token", Token)
    monkeypatch.setattr(inventory.keystone._get_admin_ks_client().role_assignments, "list", observed_assignments)
    monkeypatch.setattr(inventory.manila, "get_client", state.manila)
    monkeypatch.setattr(inventory.zun, "_get_zun_endpoint", lambda conn: "https://zun.test/v1")
    monkeypatch.setattr(inventory.swift, "_apply_endpoint_override", lambda conn: None)
    monkeypatch.setattr(inventory.service_proxy, "get_json", state.remote)
    monkeypatch.setattr(inventory.service_proxy, "package_member_request", state.package)
    cached_call = inventory.cached_call

    async def observed_cache(key, ttl, fn, **mode):
        state.events.append(("cache", key))
        return await cached_call(key, ttl, fn, **mode)

    monkeypatch.setattr(inventory, "cached_call", observed_cache)

    # Native authority reads remain active; cloud inventory must never use admin credentials.
    def forbidden(*args, **kwargs):
        state.mutations.append("administrative connection")
        raise AssertionError("Inventory used administrative cloud connection")

    monkeypatch.setattr(inventory.keystone, "get_admin_connection_for_project", forbidden)
    monkeypatch.setattr(inventory.keystone, "get_admin_project_connection", forbidden)
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer browser-jwt", "X-Project-Id": "p-a"},
        ) as client:
            yield state, client
        assert not state.mutations
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(old_overrides)


def assert_contract(data):
    assert set(data) == {"user_id", "domain_id", "current_project_id", "projects", "totals"}
    assert set(data["totals"]) == {"resources", "usage"}
    assert set(data["totals"]["resources"]) == CATEGORIES
    for project in data["projects"]:
        assert set(project) == {"project_id", "project_name", "resources", "usage"}
        assert set(project["resources"]) == CATEGORIES
        assert set(project["usage"]) == {"vcpus", "ram_mb", "storage_gb"}
        for value in project["resources"].values():
            assert value["state"] in {"ready", "disabled", "denied", "failed"}
            if value["state"] == "ready":
                assert value["count"] == len(value["items"])
            else:
                assert value["count"] is None and value["items"] == []
            for item in value["items"]:
                assert {
                    "id",
                    "name",
                    "status",
                    "project_id",
                    "project_name",
                    "owner_scope",
                    "owner_id",
                    "href",
                } <= item.keys()
                assert item["project_id"] == project["project_id"]
                assert item["owner_id"] == (data["user_id"] if item["owner_scope"] == "user" else project["project_id"])
    for value in data["totals"]["resources"].values():
        assert set(value) == {"count", "known_count", "state"}
        assert value["state"] in {"ready", "disabled", "denied", "failed", "partial"}
        assert (value["count"] is not None) == (value["state"] == "ready")


@pytest.mark.asyncio
async def test_get_user_dashboard_summary_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(URL)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_summary_excludes_foreign_domain_membership_before_resource_reads(inventory_http):
    state, client = inventory_http
    state.memberships.append({"id": "foreign-project", "name": "Foreign", "domain_id": "tenant-b"})
    state.roles["foreign-project"] = ["member"]
    response = await client.get(URL)
    assert response.status_code == 200
    assert {project["project_id"] for project in response.json()["projects"]} == {"p-a", "p-b"}
    assert response.json()["domain_id"] == "tenant-a"
    assert not any(event[0] == "connection" and event[2] == "foreign-project" for event in state.events)


@pytest.mark.asyncio
async def test_summary_uses_foreign_working_domain_without_changing_account_identity(inventory_http):
    state, client = inventory_http
    state.subject["identity_domain_id"] = "tenant-b"
    state.subject["identity_domain_name"] = "Tenant B"
    state.data["p-a", "instances"] = [{"id": "vm", "name": "VM", "project_id": "p-a", "status": "ACTIVE"}]
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json()["domain_id"] == "tenant-a"
    project = next(row for row in response.json()["projects"] if row["project_id"] == "p-a")
    assert project["resources"]["instances"]["items"][0]["id"] == "vm"
    assert all(conn._afterglow_identity_domain_id == "tenant-b" for conn in state.connections)
    assert all(conn._afterglow_domain_id == "tenant-a" for conn in state.connections)


@pytest.mark.asyncio
async def test_summary_requires_authenticated_domain(inventory_http):
    state, client = inventory_http
    state.subject["domain_id"] = ""
    response = await client.get(URL)
    assert response.status_code == 403
    assert not state.calls


@pytest.mark.asyncio
async def test_summary_all_categories_owning_metadata_and_no_secrets(inventory_http):
    state, client = inventory_http
    for category in CATEGORIES - {"packages"}:
        row = {
            "id": category + "-1",
            "name": category,
            "project_id": "p-a",
            "status": "ACTIVE",
            "user_id": "user-a",
            "password": "DO-NOT-EXPOSE",
            "payload": "DO-NOT-EXPOSE",
        }
        if category == "instances":
            row["flavor"] = {"vcpus": 2, "ram": 2048}
        if category == "volumes":
            row["size"] = 10
        if category == "subnets":
            row["network_id"] = "network-1"
        if category == "secrets":
            row["secret_ref"] = "https://barbican.test/v1/secrets/secret-1"
        state.data["p-a", category] = [row]
    state.contexts["p-a"] = {
        "project_id": "p-a",
        "project_name": "Alpha",
        "namespace": "ns-p-a",
        "package_authority": None,
        "capabilities": {
            key: True for key in ("packages_read", "packages_download", "packages_write", "keys_issue", "keys_revoke")
        },
    }
    state.package_pages["p-a", None] = {
        "project_id": "p-a",
        "namespace": "ns-p-a",
        "items": [
            {
                "package_id": "package-1",
                "project_id": "p-a",
                "namespace": "ns-p-a",
                "name": "team/package",
                "latest_pushed_by": "another-user",
            }
        ],
        "next_cursor": None,
    }
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    assert data["user_id"] == "user-a" and data["current_project_id"] == "p-a"
    alpha, beta = data["projects"]
    assert all(value["count"] == 1 for value in alpha["resources"].values())
    assert all(value["count"] == 0 for value in beta["resources"].values())
    assert alpha["usage"] == data["totals"]["usage"] == {"vcpus": 2, "ram_mb": 2048, "storage_gb": 10}
    assert alpha["resources"]["packages"]["items"][0]["id"] == "package-1"
    assert alpha["resources"]["subnets"]["items"][0]["href"] == "/dashboard/network/networks/network-1"
    assert alpha["resources"]["secrets"]["items"][0]["id"] == "secret-1"
    assert alpha["resources"]["networks"]["items"][0]["owner_scope"] == "project"
    assert "DO-NOT-EXPOSE" not in response.text
    assert {event[2] for event in state.events if event[0] == "connection"} == {"p-a", "p-b"}
    assert all(conn._afterglow_token.startswith("issued:") for conn in state.connections[1:])


@pytest.mark.asyncio
async def test_summary_rejects_foreign_owners_and_labels_unknown_creator_project_shared(inventory_http):
    state, client = inventory_http
    for category in ("instances", "volumes", "networks", "images", "containers", "k3s_clusters", "waygate_gateways"):
        owner_field = "owner" if category == "images" else "project_id"
        state.data["p-a", category] = [{"id": "foreign", owner_field: "foreign", "user_id": "user-a"}]
    for category in ("instances", "volumes", "keypairs"):
        state.data.setdefault(("p-a", category), []).extend(
            [
                {"id": "other-user", "project_id": "p-a", "user_id": "other"},
                {"id": "own", "name": "own", "project_id": "p-a", "user_id": "user-a"},
            ]
        )
    state.data["p-a", "volumes"].append({"id": "project-volume", "project_id": "p-a", "size": 5})
    state.data["p-a", "instances"].append({"id": "project-vm", "project_id": "p-a"})
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    resources = data["projects"][0]["resources"]
    assert "foreign" not in response.text and "other-user" not in response.text
    assert resources["volumes"]["items"][-1]["owner_scope"] == "project"
    assert resources["instances"]["items"][-1]["owner_scope"] == "project"
    assert data["projects"][0]["usage"] == {"vcpus": None, "ram_mb": None, "storage_gb": None}


@pytest.mark.asyncio
async def test_summary_distinguishes_disabled_denied_failed_empty_and_partial(inventory_http):
    state, client = inventory_http
    state.settings.service_magnum_enabled = False
    state.roles["p-a"] = ["member", "palimpsest-inventory_reader"]
    state.errors["p-a", "volumes"] = RuntimeError("SECRET-DATABASE-URL")
    state.errors["p-b", "volumes"] = HTTPException(403, "private policy detail")
    state.errors["p-a", "instances"] = RuntimeError("Nova outage")
    state.errors["p-a", "containers"] = HTTPException(401, "expired native credential")
    state.errors["p-b", "shares"] = HTTPException(503, "Manila outage")
    state.data["p-b", "instances"] = [
        {"id": "vm", "project_id": "p-b", "user_id": "user-a", "flavor": {"vcpus": 4, "ram": 4096}}
    ]
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    alpha, beta = data["projects"]
    assert alpha["resources"]["k3s_clusters"]["state"] == "denied"
    assert alpha["resources"]["waygate_gateways"]["state"] == "denied"
    assert alpha["resources"]["containers"]["state"] == "denied"
    assert alpha["resources"]["networks"] == {"state": "ready", "count": 0, "items": []}
    assert alpha["resources"]["volumes"]["state"] == "failed"
    assert beta["resources"]["volumes"]["state"] == "denied"
    assert data["totals"]["resources"]["instances"] == {"state": "partial", "known_count": 1, "count": None}
    assert data["totals"]["resources"]["magnum_clusters"] == {"state": "disabled", "known_count": 0, "count": None}
    assert data["totals"]["usage"] == {"vcpus": None, "ram_mb": None, "storage_gb": None}
    assert not state.calls["p-a", "magnum_clusters"] and not state.calls["p-a", "k3s_clusters"]
    assert "SECRET" not in response.text and "private policy" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", [("foreign-user", "p-b"), ("user-a", "foreign-project")])
async def test_summary_refuses_rescoped_identity_mismatch(inventory_http, mismatch):
    state, client = inventory_http
    state.identity_override["p-b"] = mismatch
    response = await client.get(URL + "?cache=true")
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    assert all(value["state"] == "denied" for value in data["projects"][1]["resources"].values())
    assert not any(project == "p-b" for project, _ in state.calls)
    assert ("close", "p-b") in state.events


@pytest.mark.asyncio
async def test_summary_fresh_membership_before_cache_and_system_admin_not_global(inventory_http):
    state, client = inventory_http
    state.system_grants.append(
        {"user": {"id": "user-a"}, "role": {"id": "admin-role"}, "scope": {"system": {"all": True}}}
    )
    state.memberships.append({"id": "not-member", "name": "Hidden", "domain_id": "tenant-a"})
    state.data["p-a", "networks"] = [{"id": "network", "project_id": "p-a"}]
    first = await client.get(URL + "?cache=true")
    assert first.status_code == 200
    assert state.connections[0]._afterglow_is_system_admin is True
    assert first.json()["projects"][0]["resources"]["networks"]["count"] == 1
    # A member with native packages_read and no namespace has an empty inventory,
    # not a denial or a failed administrator-context validation.
    assert first.json()["projects"][0]["resources"]["packages"] == {"state": "ready", "count": 0, "items": []}
    assert first.json()["projects"][-1]["resources"]["networks"]["state"] == "denied"
    # Missing membership denies packages; the source administrator flag alone does not.
    assert first.json()["projects"][-1]["resources"]["packages"]["state"] == "denied"
    state.roles["p-a"] = []
    second = await client.get(URL + "?cache=true")
    assert second.status_code == 200
    assert second.json()["projects"][0]["resources"]["networks"]["state"] == "denied"
    assert second.json()["projects"][0]["resources"]["packages"]["state"] == "denied"
    assert state.calls["p-a", "networks"] == 1
    assert not any(project == "not-member" for project, _ in state.calls)
    assert not any(event[:2] == ("package", "not-member") for event in state.events)
    state.memberships = [{"id": "p-b", "name": "Beta", "domain_id": "tenant-a"}]
    third = await client.get(URL + "?cache=true")
    assert third.status_code == 200
    assert [p["project_id"] for p in third.json()["projects"]] == ["p-b"]
    assert third.json()["current_project_id"] == "p-a"


@pytest.mark.asyncio
async def test_summary_cache_hits_still_authorize_service_permission_revocation(inventory_http):
    state, client = inventory_http
    state.data["p-a", "k3s_clusters"] = [{"id": "cluster", "project_id": "p-a"}]
    first = await client.get(URL + "?cache=true")
    second = await client.get(URL + "?cache=true")
    assert first.status_code == second.status_code == 200
    assert state.calls["p-a", "k3s_clusters"] == 1
    assert sum(event[:2] == ("membership", "p-a") for event in state.events) >= 2
    state.roles["p-a"].remove("drover-inventory_reader")
    third = await client.get(URL + "?cache=true")
    assert third.json()["projects"][0]["resources"]["k3s_clusters"]["state"] == "denied"
    assert state.calls["p-a", "k3s_clusters"] == 1
    assert len([event for event in state.events if event[0] == "cache" and event[1].endswith(":k3s_clusters")]) == 5
    # The role fingerprint changes, so the still-authorized service is re-read.
    assert state.calls["p-a", "waygate_gateways"] == 2
    reads_before_disable = state.calls["p-a", "waygate_gateways"]
    state.settings.service_waygate_enabled = False
    fourth = await client.get(URL + "?cache=true")
    assert fourth.json()["projects"][0]["resources"]["waygate_gateways"]["state"] == "disabled"
    assert state.calls["p-a", "waygate_gateways"] == reads_before_disable


@pytest.mark.asyncio
async def test_summary_cache_token_user_project_partition_refresh_and_bypass(inventory_http):
    state, client = inventory_http
    state.data["p-a", "networks"] = [{"id": "first", "project_id": "p-a"}]
    first = await client.get(URL + "?cache=true")
    state.data["p-a", "networks"] = [{"id": "changed", "project_id": "p-a"}]
    hit = await client.get(URL + "?cache=true")
    assert first.json() == hit.json()
    refresh = await client.get(URL + "?refresh=true")
    assert refresh.json()["projects"][0]["resources"]["networks"]["items"][0]["id"] == "changed"
    state.data["p-a", "networks"] = []
    bypass = await client.get(URL)
    assert bypass.json()["projects"][0]["resources"]["networks"]["count"] == 0
    after = await client.get(URL + "?cache=true")
    assert after.json() == refresh.json()
    state.subject["token"] = "source-b"
    changed_token = await client.get(URL + "?cache=true")
    assert changed_token.json()["projects"][0]["resources"]["networks"]["count"] == 0
    state.data["p-a", "networks"] = [{"id": "other-context", "project_id": "p-a"}]
    state.subject["user_id"] = "user-b"
    changed_user = await client.get(URL + "?cache=true")
    assert changed_user.json()["user_id"] == "user-b"
    assert changed_user.json()["projects"][0]["resources"]["networks"]["count"] == 1
    assert changed_user.json()["projects"][1]["resources"]["networks"]["count"] == 0
    state.subject["project_id"] = "p-b"
    switched = await client.get(URL + "?cache=true")
    assert switched.json()["current_project_id"] == "p-b"
    assert_contract(switched.json())


@pytest.mark.asyncio
async def test_summary_keypairs_user_global_totals_not_multiplied(inventory_http):
    state, client = inventory_http
    for project in ("p-a", "p-b"):
        state.data[project, "keypairs"] = [{"name": "my-key", "user_id": "user-a", "public_key": "DO-NOT-EXPOSE"}]
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    assert all(project["resources"]["keypairs"]["count"] == 1 for project in data["projects"])
    assert data["totals"]["resources"]["keypairs"] == {"state": "ready", "count": 1, "known_count": 1}
    assert "DO-NOT-EXPOSE" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [(HTTPException(403, "private"), 403), (RuntimeError("private"), 503)])
async def test_summary_membership_failure_not_empty(inventory_http, error, status):
    state, client = inventory_http
    state.membership_error = error
    response = await client.get(URL)
    assert response.status_code == status
    # The global HTTP handler intentionally redacts unmarked 5xx details.
    assert response.json() == {"detail": "Project memberships unavailable" if status == 403 else "내부 서버 오류"}
    assert "private" not in response.text
    assert not state.calls


@pytest.mark.asyncio
async def test_summary_empty_membership_is_known_empty_not_injected_current_project(inventory_http):
    state, client = inventory_http
    state.memberships = []
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    assert data["projects"] == []
    assert all(
        value == {"state": "ready", "count": 0, "known_count": 0} for value in data["totals"]["resources"].values()
    )
    assert data["totals"]["usage"] == {"vcpus": 0, "ram_mb": 0, "storage_gb": 0}
    assert not state.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category,key,path,endpoint",
    [
        ("database_instances", "instances", "/instances", "https://trove.test/v1.0/p-a"),
        ("database_backups", "backups", "/backups", "https://trove.test/v1.0/p-a"),
        ("shares", "shares", "/shares/detail", "https://manila.test/v2/p-a"),
        ("share_snapshots", "snapshots", "/snapshots/detail", "https://manila.test/v2/p-a"),
        ("share_networks", "share_networks", "/share-networks/detail", "https://manila.test/v2/p-a"),
        ("security_services", "security_services", "/security-services/detail", "https://manila.test/v2/p-a"),
        ("containers", "containers", "/v1/containers", "https://zun.test"),
    ],
)
async def test_summary_native_pagination_complete(category, key, path, endpoint, inventory_http):
    state, client = inventory_http
    state.pages["p-a", path] = {
        key: [{"id": "first", "project_id": "p-a"}],
        key + "_links": [{"rel": "next", "href": endpoint + path + "?marker=first"}],
    }
    state.pages["p-a", path + "?marker=first"] = {key: [{"id": "second", "project_id": "p-a"}]}
    response = await client.get(URL)
    assert response.status_code == 200
    value = response.json()["projects"][0]["resources"][category]
    assert value["state"] == "ready" and value["count"] == 2
    assert [item["id"] for item in value["items"]] == ["first", "second"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "next_href",
    [
        "https://evil.test/instances?marker=x",
        "https://trove.test/v1.0/foreign/instances?marker=x",
        "/instances?all_tenants=1",
        "/instances?project_id=foreign",
        "/instances?marker=x&marker=y",
        "/instances#fragment",
        "/other?marker=x",
    ],
)
async def test_summary_rejects_unsafe_native_continuation(inventory_http, next_href):
    state, client = inventory_http
    state.pages["p-a", "/instances"] = {
        "instances": [{"id": "partial"}],
        "instances_links": [{"rel": "next", "href": next_href}],
    }
    response = await client.get(URL)
    value = response.json()["projects"][0]["resources"]["database_instances"]
    assert response.status_code == 200
    assert value == {"state": "failed", "count": None, "items": [], "error": "inventory_unavailable"}
    assert not any(event[0] == "rest" and event[2] == next_href for event in state.events)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "second",
    [
        HTTPException(503, "outage"),
        {"instances": [], "instances_links": [{"rel": "next", "href": "/instances?marker=x"}]},
    ],
)
async def test_summary_paginated_failure_or_cycle_never_partial_zero(inventory_http, second):
    state, client = inventory_http
    state.pages["p-a", "/instances"] = {
        "instances": [{"id": "partial"}],
        "instances_links": [{"rel": "next", "href": "/instances?marker=x"}],
    }
    state.pages["p-a", "/instances?marker=x"] = second
    response = await client.get(URL)
    assert response.status_code == 200
    assert response.json()["projects"][0]["resources"]["database_instances"]["state"] == "failed"
    assert response.json()["projects"][0]["resources"]["database_instances"]["count"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_page", [None, "foreign-project", "foreign-namespace", "cycle"])
async def test_summary_package_cursor_and_namespace_fences(inventory_http, bad_page):
    state, client = inventory_http
    state.contexts["p-a"] = {
        "project_id": "p-a",
        "project_name": "Alpha",
        "namespace": "ns-p-a",
        "package_authority": None,
        "capabilities": {
            key: True for key in ("packages_read", "packages_download", "packages_write", "keys_issue", "keys_revoke")
        },
    }

    def page(name, cursor):
        return {
            "project_id": "p-a",
            "namespace": "ns-p-a",
            "items": [{"package_id": name, "name": name, "project_id": "p-a", "namespace": "ns-p-a"}],
            "next_cursor": cursor,
        }

    state.package_pages["p-a", None] = page("first", "cursor-1")
    second = page("second", None)
    if bad_page == "foreign-project":
        second["items"][0]["project_id"] = "foreign"
    elif bad_page == "foreign-namespace":
        second["namespace"] = "other"
    elif bad_page == "cycle":
        second["next_cursor"] = "cursor-1"
    state.package_pages["p-a", "cursor-1"] = second
    response = await client.get(URL)
    assert response.status_code == 200
    value = response.json()["projects"][0]["resources"]["packages"]
    if bad_page is None:
        assert value["count"] == 2 and value["state"] == "ready"
    else:
        assert value["count"] is None and value["state"] == "failed" and value["items"] == []


@pytest.mark.asyncio
async def test_summary_package_permission_revocation_before_cache(inventory_http):
    state, client = inventory_http
    first = await client.get(URL + "?cache=true")
    assert first.json()["projects"][0]["resources"]["packages"]["state"] == "ready"
    native_before = len([event for event in state.events if event[:2] == ("package", "p-a")])
    state.roles["p-a"].remove("palimpsest-inventory_reader")
    second = await client.get(URL + "?cache=true")
    assert second.json()["projects"][0]["resources"]["packages"]["state"] == "denied"
    assert len([event for event in state.events if event[:2] == ("package", "p-a")]) == native_before
    assert len([event for event in state.events if event[0] == "cache" and event[1].endswith(":packages")]) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["capability_revoked", "context_unavailable", "namespace_changed"])
async def test_summary_warm_package_cache_obeys_current_native_context(inventory_http, monkeypatch, change):
    state, client = inventory_http
    context = {
        "project_id": "p-a",
        "project_name": "Alpha",
        "namespace": "ns-p-a",
        "package_authority": None,
        "capabilities": {
            key: True for key in ("packages_read", "packages_download", "packages_write", "keys_issue", "keys_revoke")
        },
    }
    state.contexts["p-a"] = context
    state.package_pages["p-a", None] = {
        "project_id": "p-a",
        "namespace": "ns-p-a",
        "items": [{"package_id": "old-package", "name": "Old package", "project_id": "p-a", "namespace": "ns-p-a"}],
        "next_cursor": None,
    }
    first = await client.get(URL + "?cache=true")
    assert [item["id"] for item in first.json()["projects"][0]["resources"]["packages"]["items"]] == ["old-package"]
    if change == "capability_revoked":
        context["capabilities"]["packages_read"] = False
    elif change == "context_unavailable":
        original = state.package

        async def unavailable_context(request, path, *, query=None):
            if path == "/v1/projects/current" and state.assert_scoped(request)["project_id"] == "p-a":
                return JSONResponse({"detail": "private native context failure"}, status_code=503)
            return await original(request, path, query=query)

        monkeypatch.setattr(inventory.service_proxy, "package_member_request", unavailable_context)
    else:
        context["namespace"] = "ns-replacement"
        state.package_pages["p-a", None] = {
            "project_id": "p-a",
            "namespace": "ns-replacement",
            "items": [
                {"package_id": "new-package", "name": "New package", "project_id": "p-a", "namespace": "ns-replacement"}
            ],
            "next_cursor": None,
        }
    second = await client.get(URL + "?cache=true")
    assert second.status_code == 200
    value = second.json()["projects"][0]["resources"]["packages"]
    if change == "namespace_changed":
        assert value["state"] == "ready" and value["count"] == 1
        assert [item["id"] for item in value["items"]] == ["new-package"]
    else:
        assert value == {
            "state": "denied" if change == "capability_revoked" else "failed",
            "count": None,
            "items": [],
            "error": "inventory_denied" if change == "capability_revoked" else "inventory_unavailable",
        }
    assert "private native context failure" not in second.text


@pytest.mark.asyncio
async def test_summary_rechecks_rescoped_identity_even_with_warm_cache(inventory_http):
    state, client = inventory_http
    first = await client.get(URL + "?cache=true")
    assert first.status_code == 200
    reads = sum(state.calls.values())
    state.identity_override["p-a"] = ("user-a", "foreign")
    second = await client.get(URL + "?cache=true")
    assert second.status_code == 200
    assert all(value["state"] == "denied" for value in second.json()["projects"][0]["resources"].values())
    assert sum(state.calls.values()) == reads


@pytest.mark.asyncio
async def test_summary_category_failure_is_not_cached_as_empty(inventory_http):
    state, client = inventory_http
    state.errors["p-a", "volumes"] = RuntimeError("outage")
    first = await client.get(URL + "?cache=true")
    assert first.json()["projects"][0]["resources"]["volumes"]["state"] == "failed"
    del state.errors["p-a", "volumes"]
    second = await client.get(URL + "?cache=true")
    third = await client.get(URL + "?cache=true")
    assert (
        second.json()["projects"][0]["resources"]["volumes"]
        == third.json()["projects"][0]["resources"]["volumes"]
        == {"state": "ready", "count": 0, "items": []}
    )
    assert state.calls["p-a", "volumes"] == 2


@pytest.mark.asyncio
async def test_summary_native_scope_without_creator_is_project_owned(inventory_http):
    state, client = inventory_http
    for category in ("volumes", "volume_snapshots", "volume_backups", "magnum_clusters", "security_services"):
        state.data["p-a", category] = [{"id": "shared-" + category, "name": category}]
    state.data["p-a", "database_instances"] = [{"id": "deleted", "deleted": 1}, {"id": "db"}]
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    for category in (
        "volumes",
        "volume_snapshots",
        "volume_backups",
        "magnum_clusters",
        "security_services",
        "database_instances",
    ):
        value = data["projects"][0]["resources"][category]
        assert value["count"] == 1
        assert value["items"][0]["owner_scope"] == "project"
    assert data["projects"][0]["usage"]["storage_gb"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category", ["networks", "instances", "images", "containers", "k3s_clusters", "waygate_gateways"]
)
async def test_summary_missing_required_provider_owner_is_unavailable(inventory_http, category):
    state, client = inventory_http
    state.data["p-a", category] = [{"id": "not-proven", "user_id": "user-a"}]
    response = await client.get(URL)
    assert response.status_code == 200
    value = response.json()["projects"][0]["resources"][category]
    assert value["state"] == "failed" and value["count"] is None and value["items"] == []


@pytest.mark.asyncio
async def test_summary_scope_only_account_and_endpoint_must_match(inventory_http, monkeypatch):
    state, client = inventory_http
    connection = state.connection

    def foreign_endpoint(token, project):
        conn = connection(token, project)
        conn.database.get_endpoint = lambda: "https://trove.test/v1.0/foreign"
        conn.object_store.get_endpoint = lambda: "https://swift.test/v1/AUTH_foreign"
        return conn

    monkeypatch.setattr(inventory.keystone, "get_openstack_connection", foreign_endpoint)
    response = await client.get(URL)
    assert response.status_code == 200
    for project in response.json()["projects"]:
        for category in ("database_instances", "database_backups", "buckets"):
            assert project["resources"][category]["state"] == "denied"
            assert state.calls[project["project_id"], category] == 0


@pytest.mark.asyncio
async def test_summary_empty_membership_preserves_disabled_service_totals(inventory_http):
    state, client = inventory_http
    state.memberships = []
    for _, gate in inventory.CATALOG.values():
        if gate:
            setattr(state.settings, f"service_{gate}_enabled", False)
    response = await client.get(URL)
    assert response.status_code == 200
    data = response.json()
    assert_contract(data)
    assert data["projects"] == []
    for category, (_, gate) in inventory.CATALOG.items():
        expected = (
            {"state": "disabled", "count": None, "known_count": 0}
            if gate
            else {"state": "ready", "count": 0, "known_count": 0}
        )
        assert data["totals"]["resources"][category] == expected
    assert not state.calls


@pytest.mark.asyncio
async def test_summary_cached_project_label_tracks_current_membership(inventory_http):
    state, client = inventory_http
    state.data["p-a", "networks"] = [{"id": "network", "project_id": "p-a"}]
    first = await client.get(URL + "?cache=true")
    assert first.json()["projects"][0]["resources"]["networks"]["items"][0]["project_name"] == "Alpha"
    state.memberships[0]["name"] = "Renamed"
    second = await client.get(URL + "?cache=true")
    assert second.status_code == 200
    assert second.json()["projects"][0]["resources"]["networks"]["items"][0]["project_name"] == "Renamed"


@pytest.mark.asyncio
async def test_summary_membership_provider_outage_cannot_serve_warm_inventory(inventory_http):
    state, client = inventory_http
    first = await client.get(URL + "?cache=true")
    assert first.status_code == 200
    reads = sum(state.calls.values())
    state.assignment_errors["p-a"] = HTTPException(503, "private identity outage")
    second = await client.get(URL + "?cache=true")
    assert second.status_code == 200
    assert all(
        value["state"] == "failed" and value["count"] is None
        for value in second.json()["projects"][0]["resources"].values()
    )
    assert sum(state.calls.values()) == reads
    assert second.json()["totals"]["resources"]["instances"]["state"] == "partial"
    assert "private identity" not in second.text


@pytest.mark.asyncio
async def test_summary_project_rescope_outage_is_not_empty(inventory_http, monkeypatch):
    state, client = inventory_http
    connection = state.connection

    def unavailable_scope(token, project):
        if project == "p-b":
            raise RuntimeError("private rescope outage")
        return connection(token, project)

    monkeypatch.setattr(inventory.keystone, "get_openstack_connection", unavailable_scope)
    response = await client.get(URL)
    assert response.status_code == 200
    assert all(
        value["state"] == "failed" and value["count"] is None
        for value in response.json()["projects"][1]["resources"].values()
    )
    assert not any(project == "p-b" for project, _ in state.calls)
    assert "private rescope" not in response.text


@pytest.mark.asyncio
async def test_summary_zun_native_top_level_next_pagination(inventory_http):
    state, client = inventory_http
    state.pages["p-a", "/v1/containers"] = {
        "containers": [{"uuid": "container-1", "project_id": "p-a"}],
        "next": "https://zun.test/v1/containers?marker=container-1",
    }
    state.pages["p-a", "/v1/containers?marker=container-1"] = {
        "containers": [{"uuid": "container-2", "project_id": "p-a"}],
        "next": None,
    }
    response = await client.get(URL)
    assert response.status_code == 200
    value = response.json()["projects"][0]["resources"]["containers"]
    assert value["state"] == "ready" and value["count"] == 2
    assert [item["id"] for item in value["items"]] == ["container-1", "container-2"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "native_next", ["https://foreign.test/v1/containers?marker=x", "/v1/containers?all_projects=True", {}, ""]
)
async def test_summary_zun_native_next_rejects_unsafe_or_malformed_url(inventory_http, native_next):
    state, client = inventory_http
    state.pages["p-a", "/v1/containers"] = {
        "containers": [{"uuid": "partial", "project_id": "p-a"}],
        "next": native_next,
    }
    response = await client.get(URL)
    assert response.status_code == 200
    value = response.json()["projects"][0]["resources"]["containers"]
    assert value == {"state": "failed", "count": None, "items": [], "error": "inventory_unavailable"}
