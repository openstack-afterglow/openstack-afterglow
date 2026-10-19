"""Directory read phases preserve live authority; synthetic native I/O, real routes."""

from copy import deepcopy

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.identity import auth
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
    assert fresh.json() == [{"id": "home", "name": "home"}]
    assert domain_native.calls == []
