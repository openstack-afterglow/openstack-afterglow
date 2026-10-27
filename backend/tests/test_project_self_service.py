"""Legacy project routes share the domain IAM boundary, never Default fallback."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1.exceptions.http import Forbidden, ServiceUnavailable

from app.api.deps import get_token_info
from app.api.identity.iam import router as iam_router
from app.api.identity.projects import router
from app.database import get_session
from app.services import project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import PROJECT, assignment, rid

pytestmark = pytest.mark.usefixtures("ownership_journal")


@pytest.mark.asyncio
@pytest.mark.parametrize("uid", ["member", "admin", "owner"])
async def test_project_create_and_invite_deny_ordinary_project_roles(directory, enrollments, uid):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/projects")
    app.include_router(iam_router, prefix="/api/v1/iam")
    app.dependency_overrides[get_token_info] = lambda: manager(uid)

    async def db():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path, body in [
            ("/api/v1/projects", {"name": "project"}),
            (
                "/api/v1/iam/invitations",
                {
                    "email": "new@test.invalid",
                    "projects": [{"project_id": PROJECT, "role_ids": [rid("project_member")]}],
                },
            ),
        ]:
            response = await client.post(path, json=body)
            assert response.status_code == 403
    assert not directory.sent and not directory.creates


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor,creator_preset,revoke_before_activation",
    [
        ("domain-manager", True, False),
        ("domain-manager", False, False),
        ("member", True, False),
        ("member", True, True),
    ],
)
async def test_project_create_explicit_domain_and_real_creator_owner(
    directory, monkeypatch, actor, creator_preset, revoke_before_activation
):
    created_attrs = []
    from app.services import domain_quotas

    directory.direct = []
    directory.project = None
    if not creator_preset:
        directory.catalog = [role for role in directory.catalog if role["name"] != "project_creator"]
    if actor == "member":
        directory.default_direct.append(assignment(actor, "project_creator", project_id="default-project"))
    assert directory.domain_direct == []  # The manager has no creator grant.

    async def quota_defaults(conn, domain_id, project_id, *, lease):
        assert directory.project.enabled is False
        assert domain_id == "domain" and project_id == PROJECT
        if revoke_before_activation:
            directory.default_direct.clear()

    quota = AsyncMock(side_effect=quota_defaults)
    monkeypatch.setattr(domain_quotas, "apply_project_defaults", quota)

    def update_project(pid, **attrs):
        assert pid == PROJECT
        for key, value in attrs.items():
            setattr(directory.project, key, value)
        return directory.project

    directory.ks.projects.update = update_project

    def create_project(**attrs):
        created_attrs.append(attrs)
        project = SimpleNamespace(
            id=PROJECT,
            name=attrs["name"],
            description=attrs.get("description", ""),
            domain_id=attrs["domain"],
            enabled=attrs["enabled"],
        )
        directory.project = project
        return project

    directory.ks.projects.create = create_project
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/projects")
    app.dependency_overrides[get_token_info] = lambda: manager(actor)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        capability = await client.get("/api/v1/projects/capabilities?domain_id=domain")
        assert capability.status_code == 200
        assert capability.json()["can_create_project"] is True
        response = await client.post(
            "/api/v1/projects", json={"name": "new-project", "description": "description", "domain_id": "domain"}
        )
    if revoke_before_activation:
        assert response.status_code == 403
        assert directory.project.enabled is False
        assert (await project_service.get_project_access(PROJECT, actor))["is_owner"]
        quota.assert_awaited_once()
        return
    assert response.status_code == 201
    result = response.json()
    assert created_attrs == [
        {"name": "new-project", "domain": "domain", "enabled": False, "description": "description"}
    ]
    quota.assert_awaited_once()
    assert directory.project.enabled is True
    assert result["id"] == PROJECT
    assert (await project_service.get_project_access(PROJECT, actor))["is_owner"]


@pytest.mark.asyncio
async def test_manager_cannot_create_project_in_other_domain(directory):
    with pytest.raises(HTTPException) as denied:
        await project_service.create_project_for_user("project", "", "domain-manager", "manager", "other")
    assert denied.value.status_code == 403
    assert not directory.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("actor", ["domain-manager", "member"])
async def test_project_creation_rechecks_authority_inside_graph_lock(directory, monkeypatch, actor):
    from app.services import identity_roles

    if actor == "member":
        directory.default_direct.append(assignment(actor, "project_creator", project_id="default-project"))
    graph_lock = identity_roles._graph_lock

    @asynccontextmanager
    async def revoked_lock(conn):
        async with graph_lock(conn) as lease:
            directory.managers.clear()
            directory.default_direct.clear()
            yield lease

    monkeypatch.setattr(identity_roles, "_graph_lock", revoked_lock)
    with pytest.raises(HTTPException) as denied:
        await project_service.create_project_for_user("project", "", actor, actor, "domain")
    assert denied.value.status_code == 403
    assert not directory.calls and not directory.personal_projects


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("native_error", "native_status", "detail"),
    [
        (Forbidden, 403, "Keystone role operation rejected"),
        (ServiceUnavailable, 503, "Keystone role operation is unavailable"),
    ],
)
async def test_manager_project_creation_propagates_native_rejection_without_success(
    directory, native_error, native_status, detail
):
    native_calls = []

    def reject_create(**attrs):
        native_calls.append(attrs)
        raise native_error()

    directory.ks.projects.create = reject_create
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/projects")
    app.dependency_overrides[get_token_info] = lambda: manager()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/v1/projects", json={"name": "project", "domain_id": "domain"})
    assert response.status_code == native_status
    assert response.json()["detail"] == detail
    assert len(native_calls) == 1
    assert not directory.calls and not directory.personal_projects
    assert not directory.quota_writes


@pytest.mark.asyncio
async def test_manager_project_creation_keeps_default_name_reserved(directory):
    with pytest.raises(HTTPException) as denied:
        await project_service.create_project_for_user("Default", "", "domain-manager", "manager", "domain")
    assert denied.value.status_code == 409
    assert not directory.calls and not directory.personal_projects


@pytest.mark.asyncio
async def test_iam_invitation_rejects_foreign_domain(directory, enrollments):
    app = FastAPI()
    app.include_router(iam_router, prefix="/api/v1/iam")
    app.dependency_overrides[get_token_info] = lambda: manager()

    async def db():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/iam/invitations",
            json={
                "email": "new@test.invalid",
                "projects": [{"project_id": "foreign-project", "role_ids": [rid("project_member")]}],
            },
        )
        assert response.status_code == 403
    assert not directory.sent
