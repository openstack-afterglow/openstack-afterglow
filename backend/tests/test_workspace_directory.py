"""Directory read phases preserve live authority; synthetic native I/O, real routes."""

import asyncio
import json
import socket
import threading
from collections import Counter
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
import uvicorn
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import noauth
from keystoneauth1 import session as native_session
from keystoneclient.v3.client import Client as NativeClient

from app.api.identity import auth
from app.services import cache, domain_scope, project_service
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant, row


@pytest.fixture
async def directory_client(domain_native):
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.dependency_overrides[auth.get_token_info] = lambda: {
        "user_id": "creator",
        "identity_domain_id": "home",
        "domain_id": "tenant-a",
        "token": "synthetic-native-subject",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_manager_directory_is_read_only_and_rechecks_next_request(directory_client, domain_native):
    n = domain_native
    original = deepcopy(n.raw)
    response = await directory_client.get("/api/v1/auth/workspaces?domain_id=tenant-a")
    assert response.status_code == 200, response.text
    body = response.json()
    assert {p["id"] for p in body["projects"]} == {"default-a", "work-a"}
    assert body["default_project_id"] == "default-a"
    assert body["is_domain_manager"] is True
    assert body["can_create_project"] is True
    assert "no-store" in response.headers["cache-control"]
    assert n.raw == original
    assert n.calls == []
    n.domain_rows["tenant-a"] = row(id="tenant-a", name="tenant-a", enabled=False)
    denied = await directory_client.get("/api/v1/auth/workspaces?domain_id=tenant-a")
    assert denied.status_code == 403
    assert n.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["inventory", "capability"])
@pytest.mark.parametrize(
    "change,status",
    [("manager", 403), ("membership", 403), ("identity", 401), ("home", 403), ("domain", 403), ("graph", 503)],
)
async def test_workspace_publication_rechecks_after_directory_read(
    directory_client, domain_native, monkeypatch, change, status, stage
):
    n = domain_native
    enumerate_projects = auth._workspace_projects

    def apply_change(result):
        if change == "manager":
            # Membership remains, but the wider manager-only project directory must not escape.
            n.raw = [grant("reader", user="creator", project="default-a")]
        elif change == "membership":
            n.raw = []
        elif change == "identity":
            n.user_rows["creator"] = row(id="creator", domain_id="home", enabled=False)
        elif change in {"home", "domain"}:
            domain = "home" if change == "home" else "tenant-a"
            n.domain_rows[domain] = row(id=domain, name=domain, enabled=False)
        else:
            n.raw = [grant("unknown-role", user="creator", project="default-a")]
        return result

    def changed_during_read(*args, **kwargs):
        return apply_change(enumerate_projects(*args, **kwargs))

    capability = auth.project_service.can_create_project

    async def changed_during_capability(*args, **kwargs):
        return apply_change(await capability(*args, **kwargs))

    if stage == "inventory":
        monkeypatch.setattr(auth, "_workspace_projects", changed_during_read)
    else:
        monkeypatch.setattr(auth.project_service, "can_create_project", changed_during_capability)
    response = await directory_client.get("/api/v1/auth/workspaces?domain_id=tenant-a")
    assert response.status_code == status, response.text
    assert "projects" not in response.json()
    assert "no-store" in response.headers["cache-control"]
    assert n.calls == []


@pytest.mark.asyncio
async def test_domain_directory_does_not_keep_revoked_membership(directory_client, domain_native):
    response = await directory_client.get("/api/v1/auth/domains")
    assert response.status_code == 200
    assert {d["id"] for d in response.json()} == {"home", "tenant-a"}
    domain_native.raw = []
    fresh = await directory_client.get("/api/v1/auth/domains")
    assert fresh.status_code == 200
    assert {domain["id"] for domain in fresh.json()} == {"home"}
    assert domain_native.calls == []


@pytest.fixture
async def personal_directory_client(domain_native, monkeypatch):
    native = domain_native
    native.domain_rows["account"] = row(id="account", name="account", enabled=True, afterglow_domain_kind="account")
    native.domain_rows["personal"] = row(id="personal", name="Personal", enabled=True)
    for uid, pid in (("creator", "alice-personal"), ("second", "bob-personal")):
        native.user_rows[uid].domain_id = "account"
        native.project_rows[pid] = row(
            id=pid,
            name=f"{uid}-6ee92398",
            domain_id="personal",
            enabled=True,
            parent_id="personal",
            afterglow_personal_user_id=uid,
            afterglow_personal_primary=True,
        )
        native.raw.extend(
            [
                grant("project_owner", user=uid, project=pid),
                grant("project_reader", user=uid, project=pid),
            ]
        )
    # Model a native inherited grant that over-exposes the shared domain. The
    # application must still prove each personal project's owner, not trust it.
    native.raw.append(grant("project_reader", user="creator", domain="personal", inherited=True))
    monkeypatch.setattr(
        auth.keystone,
        "list_projects",
        lambda token, did, **kwargs: [
            vars(project).copy() for project in native.project_rows.values() if project.domain_id == did
        ],
    )
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.dependency_overrides[auth.get_token_info] = lambda: {
        "user_id": "creator",
        "identity_domain_id": "account",
        "domain_id": "personal",
        "project_id": "alice-personal",
        "token": "synthetic-native-subject",
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_account_home_never_becomes_a_workspace(personal_directory_client, domain_native):
    response = await personal_directory_client.get("/api/v1/auth/domains")
    assert response.status_code == 200, response.text
    assert {domain["id"] for domain in response.json()} == {"personal", "tenant-a"}
    personal = next(domain for domain in response.json() if domain["id"] == "personal")
    assert personal["kind"] == "personal"
    rejected = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=account")
    assert rejected.status_code == 403
    assert rejected.json()["detail"] == "account_domain_is_identity_only"
    assert domain_native.calls == []


@pytest.mark.asyncio
async def test_personal_workspace_filters_foreign_inherited_access(personal_directory_client, domain_native):
    response = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=personal")
    assert response.status_code == 200, response.text
    body = response.json()
    assert [project["id"] for project in body["projects"]] == ["alice-personal"]
    assert body["default_project_id"] == "alice-personal"
    assert body["domain"]["kind"] == "personal"
    assert body["is_domain_manager"] is False
    assert body["can_create_project"] is True
    domain_native.raw = [
        assignment
        for assignment in domain_native.raw
        if assignment.scope.get("project", {}).get("id") != "alice-personal"
    ]
    # Domain inheritance alone cannot revive the revoked user's personal space.
    denied = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=personal")
    assert denied.status_code == 403, denied.text
    assert domain_native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["account", "personal"])
async def test_reserved_domains_cannot_bootstrap_shared_default(personal_directory_client, domain_native, kind):
    from fastapi import HTTPException

    from app.services import domain_projects

    with pytest.raises(HTTPException) as rejected:
        await domain_projects.bootstrap_default(kind, creator_id="creator")
    assert rejected.value.status_code == 403
    assert domain_native.calls == []


@pytest.mark.asyncio
async def test_personal_primary_cannot_be_deleted_or_renamed(personal_directory_client, domain_native):
    from fastapi import HTTPException

    from app.services import domain_projects

    for attrs, delete in (({"name": "shared"}, False), ({"enabled": False}, False), ({}, True)):
        with pytest.raises(HTTPException) as rejected:
            domain_projects.assert_default_immutable("alice-personal", attrs=attrs, delete=delete, ks=domain_native)
        assert rejected.value.status_code == 422
    assert domain_native.calls == []


@pytest.mark.asyncio
async def test_system_admin_user_directory_keeps_actual_memberships_only(
    personal_directory_client, domain_native, monkeypatch
):
    monkeypatch.setattr(auth.keystone, "_is_system_admin", lambda *args, **kwargs: True)
    domains = await personal_directory_client.get("/api/v1/auth/domains")
    assert domains.status_code == 200, domains.text
    assert {domain["id"] for domain in domains.json()} == {"personal", "tenant-a"}
    personal = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=personal")
    assert personal.status_code == 200, personal.text
    assert [project["id"] for project in personal.json()["projects"]] == ["alice-personal"]
    foreign = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=tenant-b")
    assert foreign.status_code == 403, foreign.text
    assert domain_native.calls == []


@pytest.mark.asyncio
async def test_system_admin_cannot_keep_revoked_user_workspace_membership(
    personal_directory_client, domain_native, monkeypatch
):
    monkeypatch.setattr(auth.keystone, "_is_system_admin", lambda *args, **kwargs: True)
    before = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=personal")
    assert before.status_code == 200, before.text
    domain_native.raw = [
        assignment
        for assignment in domain_native.raw
        if assignment.scope.get("project", {}).get("id") != "alice-personal"
    ]
    after = await personal_directory_client.get("/api/v1/auth/workspaces?domain_id=personal")
    assert after.status_code == 403, after.text
    assert domain_native.calls == []


@pytest.fixture
async def cached_directory(domain_native, monkeypatch):
    """Real routes/cache layer with isolated native state and fake Redis."""
    native = domain_native
    native.raw = [grant("project_reader", user="creator", project=pid) for pid in ("default-a", "work-a")]
    actor = {
        "user_id": "creator",
        "identity_domain_id": "home",
        "domain_id": "tenant-a",
        "project_id": "default-a",
        "refresh_jti": "isolated-login-jti",
        "roles": ["project_reader"],
        "token": "never-store-this-native-secret",
    }
    real_projects = auth.keystone.list_projects
    enumerations = []

    def projects(token, domain_id, **kwargs):
        enumerations.append((token, domain_id))
        return [vars(project).copy() for project in native.project_rows.values() if project.domain_id == domain_id]

    monkeypatch.setattr(auth.keystone, "list_projects", projects)
    app = FastAPI()
    app.include_router(auth.router, prefix="/api/v1/auth")
    app.dependency_overrides[auth.get_token_info] = lambda: actor.copy()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(
            app=app,
            client=client,
            native=native,
            actor=actor,
            enumerations=enumerations,
            real_projects=real_projects,
        )


@pytest.mark.asyncio
async def test_warm_workspace_keeps_live_checks_and_refresh_separate(cached_directory):
    env = cached_directory
    path = "/api/v1/auth/workspaces?domain_id=tenant-a"
    first = await env.client.get(path + "&cache=true")
    assert first.status_code == 200, first.text
    env.native.project_rows["work-a"].name = "Renamed"
    before = Counter(env.native.read_calls)
    warm = await env.client.get(path + "&cache=true")
    assert warm.status_code == 200, warm.text
    assert warm.json() == first.json()
    assert len(env.enumerations) == 1
    after = Counter(env.native.read_calls)
    assert after[("user", "creator")] > before[("user", "creator")]
    assert after[("project", "work-a")] > before[("project", "work-a")]
    bypass = await env.client.get(path + "&cache=false")
    assert bypass.status_code == 200
    assert next(p["name"] for p in bypass.json()["projects"] if p["id"] == "work-a") == "Renamed"
    assert (await env.client.get(path + "&cache=true")).json() == first.json()
    refreshed = await env.client.get(path + "&refresh=true")
    assert refreshed.json() == bypass.json()
    assert (await env.client.get(path + "&cache=true")).json() == refreshed.json()
    assert len(env.enumerations) == 3
    redis = await cache._get_redis()
    keys = await redis.keys("afterglow:identity:workspace-directory:*")
    assert len(keys) == 1
    assert 0 < await redis.ttl(keys[0]) <= 30
    serialized = str(keys) + str(await redis.get(keys[0]))
    assert env.actor["token"] not in serialized
    assert env.actor["refresh_jti"] not in serialized
    assert env.native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["membership", "disabled", "moved"])
async def test_warm_workspace_filters_revoked_or_disabled_rows(cached_directory, change):
    env = cached_directory
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    assert (await env.client.get(path)).status_code == 200
    if change == "membership":
        env.native.raw = [grant("project_reader", user="creator", project="default-a")]
    elif change == "disabled":
        env.native.project_rows["work-a"].enabled = False
    else:
        env.native.project_rows["work-a"].domain_id = "tenant-b"
        env.native.project_rows["work-a"].parent_id = "tenant-b"
    fresh = await env.client.get(path)
    assert fresh.status_code == 200, fresh.text
    assert [project["id"] for project in fresh.json()["projects"]] == ["default-a"]
    assert len(env.enumerations) == 1
    assert env.native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("change,status", [("user", 401), ("domain", 403), ("membership", 403), ("graph", 503)])
async def test_warm_workspace_never_caches_native_authority(cached_directory, change, status):
    env = cached_directory
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    assert (await env.client.get(path)).status_code == 200
    if change == "user":
        env.native.user_rows["creator"].enabled = False
    elif change == "domain":
        env.native.domain_rows["tenant-a"].enabled = False
    elif change == "membership":
        env.native.raw = []
    else:
        env.native.raw = [grant("unknown-role", user="creator", project="default-a")]
    denied = await env.client.get(path)
    assert denied.status_code == status, denied.text
    assert "projects" not in denied.json()
    assert len(env.enumerations) == 1
    assert env.native.calls == []


@pytest.mark.asyncio
async def test_warm_manager_workspace_rechecks_project_enablement(cached_directory):
    env = cached_directory
    env.native.raw = [grant("manager", user="creator", project="default-a")]
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    assert (await env.client.get(path)).status_code == 200
    env.native.project_rows["work-a"].enabled = False
    warm = await env.client.get(path)
    assert warm.status_code == 200, warm.text
    assert [project["id"] for project in warm.json()["projects"]] == ["default-a"]
    env.native.raw = [grant("project_reader", user="creator", project="default-a")]
    downgraded = await env.client.get(path)
    assert downgraded.status_code == 200, downgraded.text
    assert downgraded.json()["is_domain_manager"] is False
    assert [project["id"] for project in downgraded.json()["projects"]] == ["default-a"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidate", ["authority", "projects"])
async def test_iam_invalidations_clear_workspace_display_cache(cached_directory, invalidate):
    env = cached_directory
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    assert (await env.client.get(path)).status_code == 200
    env.native.project_rows["work-a"].name = "New label"
    if invalidate == "authority":
        await domain_scope.invalidate_authority()
    else:
        await project_service.invalidate_project_lists("creator", "tenant-a")
    fresh = await env.client.get(path)
    assert fresh.status_code == 200, fresh.text
    assert next(p["name"] for p in fresh.json()["projects"] if p["id"] == "work-a") == "New label"
    assert len(env.enumerations) == 2


@pytest.mark.asyncio
async def test_workspace_cache_outage_uses_authoritative_path(cached_directory, monkeypatch):
    env = cached_directory

    async def unavailable(*args, **kwargs):
        raise ConnectionError("isolated cache unavailable")

    monkeypatch.setattr(cache.get_backend(), "get", unavailable)
    monkeypatch.setattr(cache.get_backend(), "set", unavailable)
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    for _ in range(2):
        response = await env.client.get(path)
        assert response.status_code == 200, response.text
    assert len(env.enumerations) == 2
    env.native.raw = []
    assert (await env.client.get(path)).status_code == 403


@pytest.mark.asyncio
async def test_workspace_snapshot_isolated_by_login_and_scope(cached_directory):
    env = cached_directory
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&cache=true"
    assert (await env.client.get(path)).status_code == 200
    env.native.project_rows["work-a"].name = "Second login label"
    env.actor["refresh_jti"] = "different-login-jti"
    second = await env.client.get(path)
    assert second.status_code == 200
    assert next(p["name"] for p in second.json()["projects"] if p["id"] == "work-a") == "Second login label"
    env.actor["project_id"] = "work-a"
    assert (await env.client.get(path)).status_code == 200
    assert len(env.enumerations) == 3


@pytest.fixture
def native_http_directory(cached_directory, monkeypatch):
    """Installed Keystone clients talk only to this disposable loopback server."""
    env = cached_directory
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, payload, *, token=None):
            body = json.dumps(payload, default=vars).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            if token:
                self.send_header("X-Subject-Token", token)
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            requests.append((self.command, urlsplit(self.path).path))
            if self.path != "/v3/auth/tokens":
                return self.respond(405, {"error": {"message": "No native writes allowed"}})
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            assert body["auth"]["identity"]["token"]["id"] == env.actor["token"]
            now = datetime.now(UTC)
            self.respond(
                201,
                {
                    "token": {
                        "methods": ["token"],
                        "issued_at": now.isoformat(),
                        "expires_at": (now + timedelta(hours=1)).isoformat(),
                        "user": {"id": "creator", "name": "creator", "domain": {"id": "home", "name": "home"}},
                        "roles": [],
                        "catalog": [
                            {
                                "id": "identity",
                                "name": "keystone",
                                "type": "identity",
                                "endpoints": [
                                    {
                                        "id": "identity-public",
                                        "interface": "public",
                                        "region": "Isolated",
                                        "url": endpoint,
                                    }
                                ],
                            }
                        ],
                    }
                },
                token="isolated-exchanged-token",
            )

        def do_GET(self):
            parsed = urlsplit(self.path)
            path = parsed.path.rstrip("/")
            query = parse_qs(parsed.query, keep_blank_values=True)
            requests.append((self.command, path))

            def param(name):
                return query.get(name, [None])[0]

            native = env.native
            if path == "/v3":
                return self.respond(
                    200, {"version": {"id": "v3.14", "status": "stable", "links": [{"rel": "self", "href": endpoint}]}}
                )
            if path == "/v3/roles":
                return self.respond(200, {"roles": native.role_rows, "links": {"next": None}})
            if path == "/v3/role_inferences":
                return self.respond(200, {"role_inferences": native.edges, "links": {"next": None}})
            if path == "/v3/role_assignments":
                rows = native.assignments(
                    project=param("scope.project.id"),
                    user=param("user.id"),
                    group=param("group.id"),
                    effective="effective" in query,
                    system=param("scope.system"),
                )
                return self.respond(200, {"role_assignments": rows, "links": {"next": None}})
            if path == "/v3/projects" or path == "/v3/users/creator/projects":
                projects = native.projects_list(domain=param("domain_id"))
                return self.respond(200, {"projects": projects, "links": {"next": None}})
            if path == "/v3/groups" or path.endswith("/groups"):
                uid = path.split("/")[3] if path.startswith("/v3/users/") else param("user_id")
                return self.respond(200, {"groups": native.groups_list(user=uid), "links": {"next": None}})
            if path.endswith("/users") and path.startswith("/v3/groups/"):
                gid = path.split("/")[3]
                return self.respond(200, {"users": native.users_list(group=gid), "links": {"next": None}})
            kind, object_id = path.split("/")[-2:]
            rows = {
                "users": native.user_rows,
                "domains": native.domain_rows,
                "projects": native.project_rows,
                "groups": native.group_rows,
            }.get(kind, {})
            if object_id in rows:
                return self.respond(200, {kind[:-1]: rows[object_id]})
            self.respond(404, {"error": {"message": "No such isolated native resource", "path": path}})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}/v3"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = auth.get_settings()
    monkeypatch.setattr(settings, "os_auth_url", endpoint)
    monkeypatch.setattr(settings, "os_region_name", "Isolated")
    monkeypatch.setattr(settings, "os_interface", "public")
    monkeypatch.setattr(auth.keystone, "list_projects", env.real_projects)

    def admin_client():
        transport = native_session.Session(auth=noauth.NoAuth())
        return NativeClient(session=transport, endpoint_override=endpoint)

    monkeypatch.setattr(auth.keystone, "_get_admin_ks_client", admin_client)
    env.native_requests = requests
    try:
        yield env
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@asynccontextmanager
async def _directory_tcp_server(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error"))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        sock.close()


@pytest.mark.asyncio
async def test_workspace_isolated_tcp_http_cache_smoke(native_http_directory, request):
    """Actual API and Keystone TCP HTTP; no mocked native methods or shared services."""
    env = native_http_directory
    report = {}
    path = "/api/v1/auth/workspaces?domain_id=tenant-a&"
    async with _directory_tcp_server(env.app) as base_url, AsyncClient(base_url=base_url) as client:

        async def measure_request(label, mode):
            start = len(env.native_requests)
            response = await client.get(path + mode)
            counts = Counter(f"{method} {url}" for method, url in env.native_requests[start:])
            report[label] = {
                "http": response.status_code,
                "native_http_total": sum(counts.values()),
                "native_http_counts": dict(sorted(counts.items())),
            }
            return response

        for label, mode in (("cold", "cache=true"), ("warm", "cache=true"), ("refresh", "refresh=true")):
            response = await measure_request(label, mode)
            assert response.status_code == 200, response.text
        assert report["warm"]["native_http_total"] < report["cold"]["native_http_total"]
        for key in ("POST /v3/auth/tokens", "GET /v3/users/creator/projects"):
            assert [report[label]["native_http_counts"].get(key, 0) for label in ("cold", "warm", "refresh")] == [
                1,
                0,
                1,
            ]
        assert report["warm"]["native_http_counts"]["GET /v3/users/creator"] > 0
        assert report["warm"]["native_http_counts"]["GET /v3/role_assignments"] > 0
        env.native.raw = [grant("project_reader", user="creator", project="default-a")]
        revoked = await measure_request("revoked-project", "cache=true")
        assert revoked.status_code == 200, revoked.text
        assert [p["id"] for p in revoked.json()["projects"]] == ["default-a"]
        env.native.raw = []
        assert (await measure_request("revoked-domain", "cache=true")).status_code == 403
        env.native.raw = [grant("manager", user="creator", project="default-a")]
        for label in ("manager-cold", "manager-warm"):
            response = await measure_request(label, "cache=true")
            assert response.status_code == 200, response.text
        assert report["manager-cold"] == report["manager-warm"]
        assert report["manager-warm"]["native_http_counts"]["GET /v3/projects"] > 0
    assert env.native.calls == []
    request.node.user_properties.append(("native_http_report", json.dumps(report, sort_keys=True)))
    print("isolated-workspace-http=" + json.dumps(report, sort_keys=True))


@pytest.mark.asyncio
@pytest.mark.parametrize("domain_id,project_id", [("personal", "bob-personal"), ("tenant-b", "work-b")])
async def test_system_admin_user_workspace_selection_rejects_nonmembership_before_exchange(
    personal_directory_client, domain_native, monkeypatch, domain_id, project_id
):
    monkeypatch.setattr(auth.keystone, "_is_system_admin", lambda *args, **kwargs: True)

    async def forbidden_exchange(*args, **kwargs):
        pytest.fail("User workspace without membership must be rejected before native token exchange")

    monkeypatch.setattr(auth, "_exchange_native_scope", forbidden_exchange)
    selected = await personal_directory_client.post(
        "/api/v1/auth/token/workspace", json={"domain_id": domain_id, "project_id": project_id}
    )
    assert selected.status_code == 403, selected.text
    assert domain_native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("endpoint", ["projects?cache=true", "projects/recent"])
async def test_system_admin_user_project_lists_filter_foreign_and_revoked_membership(
    personal_directory_client, domain_native, monkeypatch, endpoint
):
    monkeypatch.setattr(auth.keystone, "_is_system_admin", lambda *args, **kwargs: True)
    first = await personal_directory_client.get("/api/v1/auth/" + endpoint)
    assert first.status_code == 200, first.text
    assert [project["id"] for project in first.json()] == ["alice-personal"]
    domain_native.raw = [
        assignment
        for assignment in domain_native.raw
        if assignment.scope.get("project", {}).get("id") != "alice-personal"
    ]
    revoked = await personal_directory_client.get("/api/v1/auth/" + endpoint)
    assert revoked.status_code == 403, revoked.text
    assert domain_native.calls == []
