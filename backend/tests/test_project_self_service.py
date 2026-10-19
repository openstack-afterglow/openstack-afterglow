"""Legacy project routes share the domain IAM boundary, never Default fallback."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.identity.iam import router as iam_router
from app.api.identity.projects import router
from app.database import get_session
from app.services import project_service
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import PROJECT, rid

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
                {"email": "new@test.invalid", "project_id": PROJECT, "role_ids": [rid("project_member")]},
            ),
        ]:
            response = await client.post(path, json=body)
            assert response.status_code == 403
    assert not directory.sent and not directory.creates


@pytest.mark.asyncio
async def test_project_create_explicit_domain_and_real_creator_owner(directory, monkeypatch):
    created_attrs = []
    from app.services import domain_quotas

    directory.direct = []
    directory.project = None

    async def quota_defaults(conn, domain_id, project_id, *, lease):
        assert directory.project.enabled is False
        assert domain_id == "domain" and project_id == PROJECT

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
    result = await project_service.create_project_for_user(
        "new-project", "description", "domain-manager", "manager", "domain"
    )
    assert created_attrs == [
        {"name": "new-project", "domain": "domain", "enabled": False, "description": "description"}
    ]
    quota.assert_awaited_once()
    assert directory.project.enabled is True
    assert result["id"] == PROJECT
    assert (await project_service.get_project_access(PROJECT, "domain-manager"))["is_owner"]


@pytest.mark.asyncio
async def test_manager_cannot_create_project_in_other_domain(directory):
    with pytest.raises(HTTPException) as denied:
        await project_service.create_project_for_user("project", "", "domain-manager", "manager", "other")
    assert denied.value.status_code == 403
    assert not directory.calls


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
            json={"email": "new@test.invalid", "project_id": "foreign-project", "role_ids": [rid("project_member")]},
        )
        assert response.status_code == 403
    assert not directory.sent
