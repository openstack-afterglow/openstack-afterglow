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
