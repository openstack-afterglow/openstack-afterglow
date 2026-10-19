"""Manager monitoring uses exact projects and explicit native user attribution.

Synthetic native boundaries only; no tests executed by the implementation agent.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from app.api.deps import require_domain_manager
from app.api.identity import domain_quotas as api
from app.services import domain_monitoring as monitoring
from app.services import domain_quotas

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
async def test_non_manager_monitoring_denied_before_operator_connection(native, monkeypatch):
    app = FastAPI()
    app.include_router(api.router, prefix="/api/v1")

    async def forbidden():
        raise HTTPException(403, "domain_manager_required")

    app.dependency_overrides[require_domain_manager] = forbidden
    operator = MagicMock()
    monkeypatch.setattr(domain_quotas.keystone, "get_admin_project_connection", operator)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/iam/monitoring")
    assert response.status_code == 403
    operator.assert_not_called()
    assert not native.reads
