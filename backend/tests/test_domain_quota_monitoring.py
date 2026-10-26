"""Manager monitoring uses exact projects and explicit native user attribution.

Synthetic native boundaries only; no tests executed by the implementation agent.
"""

import json
import threading
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.api.deps import require_domain_manager
from app.api.identity import domain_quotas as api
from app.services import domain_monitoring as monitoring
from app.services import domain_quotas
from app.services.quota_native import read_project as native_read_project

DOMAIN = "domain-a"


def row(ident, domain_id, enabled=True, **attrs):
    return SimpleNamespace(id=ident, name=ident, domain_id=domain_id, is_enabled=enabled, **attrs)


@pytest.fixture
def native(monkeypatch):
    conn = MagicMock()
    domain = row(DOMAIN, DOMAIN, afterglow_display_name="Shared display")
    conn.identity.get_domain.return_value = domain
    users = [row("home", DOMAIN), row("disabled-home", DOMAIN, enabled=False), row("foreign-home", "foreign")]
    conn.identity.users.return_value = users
    projects = [row("default", DOMAIN), row("disabled", DOMAIN, enabled=False), row("foreign", "foreign")]
    conn.identity.projects.return_value = projects
    joined = SimpleNamespace(
        id="joined",
        name="Joined",
        domain_id="personal-domain",
        enabled=True,
        password="credential-secret",
        email="not-returned@example.invalid",
    )
    monkeypatch.setattr(monitoring.domain_iam, "directory_users", AsyncMock(return_value=[joined]))
    settings = SimpleNamespace(
        **{f"service_{gate}_enabled": False for _, gate in monitoring.user_inventory.CATALOG.values() if gate}
    )
    monkeypatch.setattr(monitoring, "get_settings", lambda: settings)
    categories = {
        "instances": [
            {
                "id": "s1",
                "name": "Joined VM",
                "project_id": "default",
                "user_id": "joined",
                "status": "ACTIVE",
                "flavor": {"vcpus": 2, "ram": 1024},
                "adminPass": "credential-secret",
                "metadata": {"secret": "not-public"},
            },
            {
                "id": "s2",
                "name": "Disabled project VM",
                "project_id": "disabled",
                "user_id": "home",
                "flavor": {"vcpus": 1, "ram": 512},
            },
            {"id": "s3", "project_id": "default", "flavor": {"vcpus": 1, "ram": 512}},
            {
                "id": "foreign-server",
                "project_id": "foreign",
                "user_id": "foreign-home",
                "flavor": {"vcpus": 99, "ram": 999999},
            },
            {"id": "ownerless", "flavor": {"vcpus": 88, "ram": 999999}},
        ],
        "volumes": [{"id": "v1", "project_id": "default", "size": 10, "user_id": "former-member"}],
    }
    reads = []

    def resources(_, category):
        reads.append(category)
        return categories.get(category, [])

    monkeypatch.setattr(monitoring, "_admin_rows", resources)

    def assignments(**filters):
        pid = filters["scope_project_id"]
        return [
            SimpleNamespace(scope={"project": {"id": pid}}, user={"id": uid})
            for uid in (("home", "joined") if pid == "default" else ("joined",))
        ]

    conn.identity.role_assignments.side_effect = assignments

    async def quota(_, pid):
        assert pid in {"default", "disabled"}
        return {
            "project_id": pid,
            "compute": {"instances": {"limit": 5 if pid == "default" else 3, "in_use": 1, "reserved": 2}},
            "volume": {"gigabytes": {"limit": 100, "in_use": 10}},
            "network": None,
            "file_storage": None,
            "availability": {"compute": True, "volume": True, "network": False, "file_storage": False},
            "errors": {"network": "quota_unavailable", "file_storage": "service_disabled"},
        }

    monkeypatch.setattr(monitoring.quota_native, "read_project", quota)
    return SimpleNamespace(conn=conn, users=users, projects=projects, categories=categories, joined=joined, reads=reads)


def metric(rows, name):
    return next(value for value in rows if value["metric"] == name)


@pytest.mark.asyncio
async def test_exact_projects_joined_users_actual_use_and_safe_inventory(native):
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert data["domain"]["name"] == "Shared display"
    assert {project["id"] for project in data["projects"]} == {"default", "disabled"}
    assert {user["id"] for user in data["users"]} == {"home", "disabled-home", "joined"}
    joined = next(user for user in data["users"] if user["id"] == "joined")
    assert joined["domain_id"] == "personal-domain"
    assert joined["project_ids"] == ["default", "disabled"]
    assert joined["membership_state"] == "ready"
    assert metric(joined["resources"], "instances")["value"] == 1
    assert not any(value["kind"] == "allocation" for value in joined["resources"])
    assert metric(data["resources"], "instances")["value"] == 3
    assert metric(data["resources"], "vcpus")["value"] == 4
    assert metric(data["resources"], "quota_instances")["value"] == 8
    assert metric(data["resources"], "quota_instances")["kind"] == "allocation"
    project = next(project for project in data["projects"] if project["id"] == "default")
    assert project["quotas"]["compute"]["instances"] == {"limit": 5, "in_use": 1, "reserved": 2}
    assert {item["id"] for item in data["inventory"]} == {"s1", "s2", "s3", "v1"}
    assert next(item for item in data["inventory"] if item["id"] == "v1")["user_id"] is None
    assert all(set(item) == {"category", "id", "name", "project_id", "user_id", "status"} for item in data["inventory"])
    rendered = str(data)
    assert all(
        value not in rendered
        for value in (
            "credential-secret",
            "not-public",
            "not-returned@example.invalid",
            "foreign-server",
            "foreign-home",
            "former-member",
        )
    )
    # One service listing is shared across domain/project/user views.
    assert native.reads.count("instances") == 1


@pytest.mark.asyncio
async def test_missing_user_attribution_is_partial_not_per_user_quota(native):
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    for user in data["users"]:
        assert metric(user["resources"], "instances")["status"] == "partial"
        assert metric(user["resources"], "instances")["error"] == "user_attribution_unavailable"
        assert metric(user["resources"], "volumes")["status"] == "partial"
    assert "instances:user_attribution_unavailable" in data["coverage"]["notes"]
    assert data["coverage"]["partial"] is True


@pytest.mark.asyncio
async def test_missing_native_owners_do_not_become_empty_inventory_success(native):
    native.categories["instances"] = [{"id": "orphan", "name": "not-attributable"}]
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert metric(data["resources"], "instances")["value"] is None
    assert metric(data["resources"], "instances")["status"] == "unavailable"
    assert not any(item["category"] == "instances" for item in data["inventory"])


@pytest.mark.asyncio
async def test_unsupported_disabled_and_failed_services_are_explicit(native, monkeypatch):
    original = monitoring._admin_rows

    def denied(conn, category):
        if category == "networks":
            error = RuntimeError("native-password")
            error.status_code = 403
            raise error
        return original(conn, category)

    monkeypatch.setattr(monitoring, "_admin_rows", denied)
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert metric(data["resources"], "keypairs")["error"] == "domain_aggregate_unsupported"
    assert metric(data["resources"], "containers")["status"] == "disabled"
    assert metric(data["resources"], "networks")["status"] == "denied"
    assert metric(data["resources"], "quota_network")["value"] is None
    assert metric(data["resources"], "quota_shares")["status"] == "disabled"
    assert "native-password" not in str(data)


@pytest.mark.asyncio
async def test_unlimited_quota_is_not_actual_use_or_finite_sum(native, monkeypatch):
    original = monitoring.quota_native.read_project

    async def unlimited(conn, pid):
        quota = await original(conn, pid)
        quota["compute"]["instances"]["limit"] = -1
        return quota

    monkeypatch.setattr(monitoring.quota_native, "read_project", unlimited)
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert metric(data["resources"], "quota_instances")["status"] == "unlimited"
    assert metric(data["resources"], "quota_instances")["value"] is None
    assert metric(data["resources"], "instances")["value"] == 3


@pytest.mark.asyncio
async def test_bad_effective_membership_does_not_claim_no_projects(native):
    native.conn.identity.role_assignments.side_effect = lambda **_: [
        SimpleNamespace(scope={"project": {"id": "foreign"}}, user={"id": "joined"})
    ]
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert all(user["membership_state"] == "unavailable" for user in data["users"])
    assert "project_memberships_unavailable" in data["coverage"]["notes"]


@pytest.mark.asyncio
async def test_joined_directory_failure_is_not_silently_home_only(native, monkeypatch):
    monkeypatch.setattr(
        monitoring.domain_iam, "directory_users", AsyncMock(side_effect=HTTPException(503, "directory_unavailable"))
    )
    with pytest.raises(HTTPException) as failure:
        await monitoring.manager_workspace(native.conn, DOMAIN)
    assert failure.value.status_code == 503
    assert not native.reads


@pytest.mark.asyncio
async def test_manager_monitoring_route_requires_manager_and_never_returns_admin_observation(native, monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    token = {"user_id": "joined", "domain_id": DOMAIN}
    app.dependency_overrides[require_domain_manager] = lambda: token
    monkeypatch.setattr(
        domain_quotas.domain_iam, "context", AsyncMock(return_value={"domain_id": DOMAIN, "is_domain_manager": True})
    )
    monkeypatch.setattr(domain_quotas.keystone, "get_admin_project_connection", lambda: native.conn)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/monitoring")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert not ({"sessions", "logins", "activity", "requests"} & set(response.json()))
    native.conn.close.assert_called_once()


@pytest.mark.asyncio
async def test_admin_snapshot_includes_joined_identity_observation(native, monkeypatch):
    observed = {}

    async def activity(domain_id, user_ids, project_ids, window):
        observed["users"] = user_ids
        return {
            "notes": [],
            "logins": {"state": "ready"},
            "activity": {"state": "ready"},
            "sessions": {"state": "ready"},
        }

    monkeypatch.setattr(monitoring.login_monitoring, "domain_observation", activity)
    monkeypatch.setattr(monitoring.traffic_analytics, "domain_snapshot", AsyncMock(return_value={"state": "ready"}))
    monkeypatch.setattr(monitoring, "allocation", AsyncMock(return_value=[]))
    data = await monitoring.snapshot(native.conn, DOMAIN, "24h")
    assert observed["users"] == {"home", "disabled-home", "joined"}
    assert data["directory"] == {"users": 3, "projects": 2}


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/api/v1/iam/monitoring", "/api/v1/iam/monitoring/forecast"])
async def test_non_manager_monitoring_denied_before_operator_connection(native, monkeypatch, path):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")

    async def forbidden():
        raise HTTPException(403, "domain_manager_required")

    app.dependency_overrides[require_domain_manager] = forbidden
    operator = MagicMock()
    monkeypatch.setattr(domain_quotas.keystone, "get_admin_project_connection", operator)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 403
    operator.assert_not_called()
    assert not native.reads


@pytest.mark.asyncio
async def test_native_quota_section_denial_preserves_other_sections_and_inventory(native, monkeypatch):
    def section(conn, pid, name):
        if name == "network":
            error = RuntimeError("private-provider-detail")
            error.status_code = 403
            raise error
        return {key: {"limit": 5, "in_use": 1} for key in monitoring.quota_native.QUOTA_FIELDS[name].values()}

    monkeypatch.setattr(monitoring.quota_native, "read_project", native_read_project)
    monkeypatch.setattr(monitoring.quota_native, "get_section", section)
    data = await monitoring.manager_workspace(native.conn, DOMAIN)
    assert metric(data["resources"], "instances")["value"] == 3
    assert metric(data["resources"], "quota_instances")["value"] == 10
    assert metric(data["resources"], "quota_network")["status"] == "unavailable"
    assert "private-provider-detail" not in str(data)


@pytest.fixture
def forecast_native(native, monkeypatch):
    calls = []

    def projects(path, *, params):
        assert path == "/projects"
        assert params == {"domain_id": DOMAIN}
        return httpx.Response(
            200,
            json={
                "projects": [
                    {"id": project.id, "domain_id": project.domain_id, "enabled": project.is_enabled}
                    for project in native.projects
                    if project.domain_id == DOMAIN
                ],
                "links": {"next": None},
            },
            request=httpx.Request("GET", "http://native.test/projects"),
        )

    native.conn.identity.get.side_effect = projects

    def usage(path, *, params, microversion):
        assert microversion == "2.39"
        pid = path.rsplit("/", 1)[1]
        calls.append(pid)
        end = datetime.fromisoformat(params["end"])
        return httpx.Response(
            200,
            json={
                "tenant_usage": {
                    "tenant_id": pid,
                    "start": params["start"],
                    "stop": params["end"],
                    "server_usages": [
                        {
                            "tenant_id": pid,
                            "started_at": (end - timedelta(days=5)).isoformat(),
                            "ended_at": None,
                            "vcpus": 2,
                            "memory_mb": 1024,
                        }
                    ],
                }
            },
            request=httpx.Request("GET", "http://native.test" + path),
        )

    native.conn.compute.get.side_effect = usage
    monkeypatch.setattr(
        monitoring.quota_native,
        "get_section",
        lambda conn, pid, section: {
            "instances": {"limit": 10, "in_use": 1},
            "cores": {"limit": 20, "in_use": 2},
            "ram": {"limit": 8192, "in_use": 1024},
        },
    )
    return native, calls


@pytest.mark.asyncio
async def test_forecast_aggregates_every_exact_project_and_reuses_daily_trend(forecast_native):
    native, calls = forecast_native
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert set(calls) == {"default", "disabled"}
    assert data["domain_id"] == DOMAIN
    assert not ({"requests", "sessions", "logins", "activity"} & set(data))
    cores = metric(data["entries"], "vcpus")
    assert cores["current"] == 4
    assert cores["limit"] == 40
    assert cores["status"] == "ready"
    assert cores["trend"]["series"] == [0, 4, 4, 4, 4, 4, 4]
    assert cores["trend"]["slope_per_day"] == 0.43
    assert metric(data["entries"], "volume_gb")["error"] == "history_unsupported"


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["denied", "wrong_project", "missing_start", "wrong_window", "foreign_row"])
async def test_incomplete_domain_history_never_becomes_partial_or_zero_forecast(forecast_native, mode):
    native, _ = forecast_native
    original = native.conn.compute.get.side_effect

    def usage(path, **kwargs):
        response = original(path, **kwargs)
        payload = response.json()
        result = payload["tenant_usage"]
        if path.endswith("/disabled"):
            if mode == "denied":
                return httpx.Response(403, request=response.request)
            if mode == "wrong_project":
                result["tenant_id"] = "foreign"
            elif mode == "missing_start":
                result["server_usages"][0]["started_at"] = None
            elif mode == "wrong_window":
                result["start"] = "2020-01-01T00:00:00"
            else:
                result["server_usages"][0]["tenant_id"] = "foreign"
        return httpx.Response(200, json=payload, request=response.request)

    native.conn.compute.get.side_effect = usage
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    for entry in data["entries"][:3]:
        assert entry["current"] is None
        assert entry["trend"] is None
        assert entry["status"] == ("denied" if mode == "denied" else "unavailable")
    assert "private-provider-detail" not in str(data)


@pytest.mark.asyncio
async def test_forecast_empty_native_history_has_no_fabricated_trend(forecast_native):
    native, _ = forecast_native
    original = native.conn.compute.get.side_effect

    def empty(path, **kwargs):
        response = original(path, **kwargs)
        return httpx.Response(200, json={"tenant_usage": {}}, request=response.request)

    native.conn.compute.get.side_effect = empty
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert all(entry["status"] == "unavailable" for entry in data["entries"])
    assert metric(data["entries"], "vcpus")["trend"]["trend_available"] is False


@pytest.mark.asyncio
async def test_idle_project_native_empty_body_does_not_hide_other_project_trend(forecast_native):
    native, _ = forecast_native
    original = native.conn.compute.get.side_effect

    def usage(path, **kwargs):
        response = original(path, **kwargs)
        if path.endswith("/disabled"):
            return httpx.Response(200, json={"tenant_usage": {}}, request=response.request)
        return response

    native.conn.compute.get.side_effect = usage
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    cores = metric(data["entries"], "vcpus")
    assert cores["status"] == "ready"
    assert cores["trend"]["series"] == [0, 2, 2, 2, 2, 2, 2]
    assert cores["limit"] == 40


@pytest.mark.asyncio
async def test_forecast_project_limit_never_reads_or_estimates_a_project_subset(forecast_native, monkeypatch):
    native, calls = forecast_native
    monkeypatch.setattr(monitoring, "QUOTA_PROJECT_LIMIT", 1)
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert not calls
    assert all(entry["trend"] is None for entry in data["entries"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload", [{}, {"tenant_usage": None}, {"tenant_usage": {}, "tenant_usage_links": [{"href": "next"}]}]
)
async def test_missing_or_paged_history_is_not_native_empty_success(forecast_native, payload):
    native, _ = forecast_native
    native.conn.compute.get.side_effect = lambda path, **_: httpx.Response(
        200, json=payload, request=httpx.Request("GET", "http://native.test" + path)
    )
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert all(entry["trend"] is None for entry in data["entries"])


@pytest.mark.asyncio
async def test_forecast_route_verifies_current_manager_and_owns_connection(forecast_native, monkeypatch):
    native, _ = forecast_native
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    app.dependency_overrides[require_domain_manager] = lambda: {"user_id": "joined", "domain_id": DOMAIN}
    monkeypatch.setattr(
        domain_quotas.domain_iam, "context", AsyncMock(return_value={"domain_id": DOMAIN, "is_domain_manager": True})
    )
    monkeypatch.setattr(domain_quotas.keystone, "get_admin_project_connection", lambda: native.conn)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/monitoring/forecast")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    assert response.json()["domain_id"] == DOMAIN
    native.conn.close.assert_called_once()


@pytest.fixture
def forecast_identity_http(forecast_native):
    """Installed SDK over TCP; Nova history/quota remain the focused fixtures."""
    native, usage_calls = forecast_native
    state = {
        "truncated": False,
        "projects": [
            {"id": "default", "name": "Default", "domain_id": DOMAIN, "enabled": True},
            {"id": "disabled", "name": "Disabled", "domain_id": DOMAIN, "enabled": False},
        ],
        "requests": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            state["requests"].append((url.path, parse_qs(url.query)))
            status = 200
            if url.path.rstrip("/") in {"", "/v3"}:
                payload = {
                    "version": {
                        "id": "v3.14",
                        "status": "stable",
                        "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                    }
                }
            elif url.path == f"/v3/domains/{DOMAIN}":
                payload = {"domain": {"id": DOMAIN, "name": "Domain", "enabled": True}}
            elif url.path == "/v3/projects":
                payload = {
                    "projects": state["projects"],
                    "links": {"next": None, "previous": None, "self": endpoint + self.path},
                    "truncated": state["truncated"],
                }
            elif url.path == "/v3/users":
                payload = {"users": [], "links": {"next": None}}
            else:
                status, payload = 404, {"error": "unexpected endpoint"}
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sdk = Connection(
        session=Session(auth=Token(endpoint=endpoint, token="synthetic-forecast-token")),
        identity_endpoint_override=endpoint + "/v3",
        identity_api_version="3",
        connect_retries=0,
    )
    native.conn.identity = sdk.identity
    try:
        yield native, usage_calls, state
    finally:
        sdk.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
@pytest.mark.parametrize("truncated", [False, True])
async def test_forecast_route_checks_native_collection_before_domain_totals(
    forecast_identity_http, monkeypatch, truncated
):
    native, usage_calls, state = forecast_identity_http
    state["truncated"] = truncated
    if truncated:
        state["projects"] = state["projects"][:1]
        # This real SDK iterator silently loses HTTP-200 truncation metadata.
        assert [project.id for project in native.conn.identity.projects(domain_id=DOMAIN)] == ["default"]
        state["requests"].clear()
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")
    app.dependency_overrides[require_domain_manager] = lambda: {"user_id": "joined", "domain_id": DOMAIN}
    monkeypatch.setattr(
        domain_quotas.domain_iam, "context", AsyncMock(return_value={"domain_id": DOMAIN, "is_domain_manager": True})
    )
    monkeypatch.setattr(domain_quotas.keystone, "get_admin_project_connection", lambda: native.conn)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/monitoring/forecast")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"
    entries = response.json()["entries"][:3]
    if truncated:
        assert not usage_calls
        assert all(entry["status"] == "unavailable" for entry in entries)
        assert all(entry["error"] == "project_inventory_unavailable" for entry in entries)
        assert all(entry[key] is None for entry in entries for key in ("current", "limit", "trend"))
    else:
        assert set(usage_calls) == {"default", "disabled"}
        assert all(entry["status"] == "ready" for entry in entries)
        assert metric(entries, "vcpus")["current"] == 4
        assert metric(entries, "vcpus")["limit"] == 40
    assert [(path, query) for path, query in state["requests"] if path == "/v3/projects"] == [
        ("/v3/projects", {"domain_id": [DOMAIN]})
    ]
    native.conn.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changes",
    [
        {"truncated": True},
        {"limited": True},
        {"truncated": "false"},
        {"limited": 0},
        {"truncated": None},
        {"links": None},
        {"links": []},
        {"links": {}},
        {"links": {"next": "/projects?marker=default"}},
        {"links": {"next": None, "previous": "/projects?marker=earlier"}},
        {"next": "/projects?marker=default"},
        {"projects": None},
        {"projects": [None]},
        {"projects": [{"id": "default", "domain_id": DOMAIN}] * 2},
        {"projects": [{"id": " ", "domain_id": DOMAIN}]},
        {"projects": [{"domain_id": DOMAIN}]},
        {"projects": [{"id": "foreign", "domain_id": "other-domain"}]},
    ],
)
async def test_forecast_rejects_incomplete_or_malformed_project_metadata(forecast_native, changes):
    native, calls = forecast_native
    response = native.conn.identity.get.side_effect("/projects", params={"domain_id": DOMAIN})
    payload = response.json()
    payload.update(changes)
    native.conn.identity.get.side_effect = lambda *args, **kwargs: httpx.Response(
        200, json=payload, request=response.request
    )
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert not calls
    for entry in data["entries"][:3]:
        assert entry["status"] == "unavailable"
        assert entry["error"] == "project_inventory_unavailable"
        assert entry["current"] is None
        assert entry["limit"] is None
        assert entry["trend"] is None


@pytest.mark.asyncio
async def test_forecast_rejects_http_link_continuation(forecast_native):
    native, calls = forecast_native
    response = native.conn.identity.get.side_effect("/projects", params={"domain_id": DOMAIN})
    native.conn.identity.get.side_effect = lambda *args, **kwargs: httpx.Response(
        200,
        json=response.json(),
        headers={"Link": '</projects?marker=default>; rel="next"'},
        request=response.request,
    )
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert not calls
    assert all(entry["error"] == "project_inventory_unavailable" for entry in data["entries"][:3])


@pytest.mark.asyncio
async def test_forecast_project_inventory_denial_is_not_an_empty_domain(forecast_native):
    native, calls = forecast_native
    native.conn.identity.get.side_effect = lambda *args, **kwargs: httpx.Response(
        403, request=httpx.Request("GET", "http://native.test/projects")
    )
    data = await monitoring.manager_forecast(native.conn, DOMAIN)
    assert not calls
    assert all(entry["status"] == "denied" for entry in data["entries"][:3])
    assert all(entry["current"] is None for entry in data["entries"])
