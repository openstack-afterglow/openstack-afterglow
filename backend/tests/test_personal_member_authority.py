"""Personal member preservation and additive native account namespace cutover."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity import admin_identity
from app.models.account_spaces import SharedDomainIntent
from app.services import account_spaces, domain_projects, identity_roles, keystone, project_service
from tests.admin_gate import synthetic_verified_admin
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_domain_iam import manager
from tests.test_project_membership_roles import rid


@pytest.mark.asyncio
async def test_personal_member_can_enter_only_own_workspace_and_cannot_lose_primary_grant(directory, enrollments):
    project = await account_spaces.ensure_personal_project("foreign")
    domain_projects.assert_project_membership("foreign", project["id"])
    assert project["domain_id"] in {d["id"] for d in domain_projects.accessible_domains("foreign")}
    assert project["domain_id"] not in {d["id"] for d in domain_projects.accessible_domains("member")}
    access = await project_service.get_project_access(project["id"], "foreign")
    assert access == {"is_owner": False, "is_manager": False, "roles": ["member"]}
    assert await project_service.can_create_project("foreign", project["domain_id"])
    connection = keystone.get_admin_project_connection()
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: connection
    app.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "is_system_admin": True}
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        rejected = await client.delete(
            "/api/v1/admin/roles/assign",
            params={"user_id": "foreign", "project_id": project["id"], "role_id": rid("member")},
        )
    assert rejected.status_code == 409
    assert project_service._direct_ids(directory.ks.role_assignments.list(project=project["id"]), "foreign") == {
        rid("member")
    }
    assert account_spaces.personal_project("foreign") == project


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["project_admin", "project_member", "reader", "lumen_admin"])
async def test_system_assignment_cannot_add_other_roles_to_personal_member(directory, enrollments, role, monkeypatch):
    project = await account_spaces.ensure_personal_project("foreign")
    connection = keystone.get_admin_project_connection()
    connection.identity = SimpleNamespace(
        get_project=directory.ks.projects.get,
        get_user=directory.ks.users.get,
        get_role=lambda role_id: SimpleNamespace(**next(row for row in directory.catalog if row["id"] == role_id)),
        assign_project_role_to_user=lambda pid, uid, role_id: directory.ks.roles.grant(role_id, user=uid, project=pid),
    )
    monkeypatch.setattr(identity_roles, "_assignment_invalidation", AsyncMock())
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: connection
    app.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "is_system_admin": True}
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post(
            "/api/v1/admin/roles/assign",
            json={"user_id": "foreign", "project_id": project["id"], "role_id": rid(role)},
        )
    assert denied.status_code == 403, denied.text
    assert denied.json()["detail"] == "personal_project_roles_are_fixed"
    assert project_service._direct_ids(directory.ks.role_assignments.list(project=project["id"]), "foreign") == {
        rid("member")
    }
    assert account_spaces.personal_project("foreign") == project


@pytest.mark.asyncio
async def test_extra_personal_project_keeps_required_member_grant(directory, enrollments, monkeypatch):
    await account_spaces.ensure_personal_project("foreign")
    project = await account_spaces.create_personal_project("foreign")
    connection = keystone.get_admin_project_connection()
    connection.identity = SimpleNamespace(
        unassign_project_role_from_user=lambda pid, uid, role_id: directory.ks.roles.revoke(
            role_id, user=uid, project=pid
        ),
    )
    monkeypatch.setattr(identity_roles, "_assignment_invalidation", AsyncMock())
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    app.dependency_overrides[get_os_conn] = lambda: connection
    app.dependency_overrides[get_token_info] = lambda: {**manager("system-admin"), "is_system_admin": True}
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.delete(
            "/api/v1/admin/roles/assign",
            params={"user_id": "foreign", "project_id": project["id"], "role_id": rid("member")},
        )
    assert denied.status_code == 409
    assert project_service._direct_ids(directory.ks.role_assignments.list(project=project["id"]), "foreign") == {
        rid("member")
    }


@pytest.mark.asyncio
async def test_legacy_personal_owner_cannot_add_service_role_through_managed_editor(directory, enrollments):
    project = await account_spaces.ensure_personal_project("foreign")
    # Preserve a historical owner project; the generic editor must not use its
    # established ownership to add new service/project roles to Personal.
    directory.ks.roles.revoke(rid("member"), user="foreign", project=project["id"])
    directory.ks.roles.grant(rid("project_owner"), user="foreign", project=project["id"])
    actor = {**manager("foreign"), "domain_id": project["domain_id"], "project_id": project["id"]}
    async with identity_roles._graph_lock(keystone.get_admin_project_connection()) as lease:
        snapshot = (
            lease,
            directory.ks,
            directory.catalog,
            project_service._assignment_rows(directory.ks, project["id"], effective=True),
            project_service._assignment_rows(directory.ks, project["id"]),
        )
        with pytest.raises(HTTPException) as denied:
            await project_service.replace_member_roles(
                project["id"], "foreign", [rid("project_owner"), rid("lumen_admin")], actor, _mutation=snapshot
            )
    assert denied.value.status_code == 403
    assert denied.value.detail == "personal_project_roles_are_fixed"
    assert project_service._direct_ids(directory.ks.role_assignments.list(project=project["id"]), "foreign") == {
        rid("project_owner")
    }


@pytest.mark.asyncio
async def test_new_accounts_namespace_does_not_reuse_or_migrate_singular_account_receipt(directory, enrollments):
    marker = "historical-account-domain"
    old = directory.ks.domains.create(
        name="account", enabled=True, afterglow_domain_kind="account", afterglow_topology_id=marker
    )
    original_domain_writes = list(directory.domain_writes)
    async with enrollments() as session:
        session.add(SharedDomainIntent(kind="account", domain_id=old.id, marker=marker, status="accepted", history=[]))
        await session.commit()
    project = await account_spaces.ensure_personal_project("foreign")
    current = account_spaces.shared_domain("account")
    assert current.name == "Accounts" and current.id == "operator-accounts" and current.id != old.id
    assert directory.ks.domains.get(old.id) is old and old.name == "account"
    assert directory.users["foreign"].domain_id == "other"
    assert project["domain_id"] == account_spaces.shared_domain("personal").id
    async with enrollments() as session:
        intents = {row.kind: row for row in (await session.execute(select(SharedDomainIntent))).scalars()}
        assert intents["account"].domain_id == old.id and intents["account"].marker == marker
        assert set(intents) == {"account"}
    await account_spaces.settle_shared_domain("account", manager("system-admin"), native_calls_settled=True)
    assert directory.ks.domains.get(old.id) is old
    assert directory.domain_writes == original_domain_writes
    assert not directory.creates
