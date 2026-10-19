"""Policy endpoints against the stateful native Default/projection directory."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select

from app.api.identity import admin_identity, domains
from app.models.domain_quotas import DomainQuotaOperation, DomainQuotaPolicy
from app.models.project_ownership import ProjectOwnershipTransfer
from app.services import (
    domain_iam,
    domain_projects,
    domain_quotas,
    domain_scope,
    identity_roles,
    keystone,
    project_service,
)
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_domain_projects import grant
from tests.test_project_deletion import FakeCloud


@pytest_asyncio.fixture
async def policy_native(domain_native, ownership_journal, monkeypatch):
    native = domain_native
    async with ownership_journal() as session:
        connection = await session.connection()
        await connection.run_sync(DomainQuotaPolicy.__table__.create)
        await connection.run_sync(DomainQuotaOperation.__table__.create)
        await session.commit()
    native.journal = ownership_journal
    monkeypatch.setattr(domain_quotas, "get_session_factory", lambda: ownership_journal)
    # Keep a real administrator outside the home domain being disabled below.
    native.user_rows["operator"].domain_id = "tenant-b"
    native.raw.append(SimpleNamespace(role={"id": "admin"}, user={"id": "operator"}, scope={"system": {"all": True}}))
    native.resource_cloud = FakeCloud()
    native.resource_cloud.is_admin_project = True
    monkeypatch.setattr(keystone, "get_admin_project_connection", native.resource_cloud.connect)

    def projects_list(domain=None, parent=None):
        return [project for project in native.projects_list(domain) if parent is None or project.parent_id == parent]

    native.projects.list = projects_list
    monkeypatch.setattr(
        identity_roles, "_trusted_catalog", lambda: identity_roles._catalog(native.role_rows, native.edges)
    )
    monkeypatch.setattr(identity_roles, "invalidate", AsyncMock())
    monkeypatch.setattr(domain_scope, "invalidate_authority", AsyncMock())
    monkeypatch.setattr(identity_roles.activity, "record", AsyncMock())
    monkeypatch.setattr(domain_iam, "get_settings", lambda: SimpleNamespace(os_username="operator"))
    monkeypatch.setattr("app.config.get_settings", lambda: SimpleNamespace(monitoring_auto_sg_enabled=False))
    monkeypatch.setattr(keystone, "_resolve_admin_role_id", lambda: "admin")

    def create_project(**attrs):
        assert native.lock_depth == 1
        project = native.create_project(
            name=attrs["name"],
            domain=attrs["domain_id"],
            enabled=attrs["enabled"],
            description=attrs.get("description", ""),
        )
        project.is_enabled = project.enabled
        return project

    def delete_project(project_id, **kwargs):
        assert native.lock_depth == 1
        native.delete_project(project_id)

    def assignments(role_id=None, effective=False):
        return [row for row in native.assignments(effective=effective) if role_id is None or row.role["id"] == role_id]

    def request(*args, **kwargs):
        raise AssertionError("Unexpected SDK transport request")

    identity = SimpleNamespace(
        get_domain=native.domains.get,
        projects=lambda domain_id: native.projects.list(domain=domain_id),
        get_user=native.users.get,
        request=request,
        get_project=native.projects.get,
        create_project=create_project,
        delete_project=delete_project,
        role_assignments=assignments,
    )
    native.sdk = SimpleNamespace(identity=identity)
    return native


def actor(user_id="creator"):
    return {"user_id": user_id, "username": user_id, "domain_id": "tenant-a", "project_id": "work-a"}


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["default", "active-manager"])
async def test_admin_project_creation_requires_explicit_bootstrap_and_enabled_default_manager(policy_native, missing):
    native = policy_native
    if missing == "default":
        del native.project_rows["default-a"]
    else:
        native.user_rows["creator"].enabled = False
    before = set(native.project_rows)
    with pytest.raises(HTTPException) as denied:
        await admin_identity.create_project(
            admin_identity.CreateProjectRequest(name="New", domain_id="tenant-a"),
            conn=native.sdk,
            token_info={**actor("operator"), "is_system_admin": True},
        )
    assert denied.value.status_code == 409
    assert set(native.project_rows) == before
    assert not native.calls


@pytest.mark.asyncio
async def test_admin_created_project_has_common_native_readers_and_explicit_sole_operator_owner(policy_native):
    native = policy_native
    created = await admin_identity.create_project(
        admin_identity.CreateProjectRequest(name="New", domain_id="tenant-a"),
        conn=native.sdk,
        token_info={**actor("operator"), "is_system_admin": True},
    )
    assert native.members["projection-tenant-a"] == {"creator"}
    manager_access = await project_service.get_project_access(created["id"], "creator")
    assert manager_access == {"is_owner": False, "is_manager": False, "roles": ["project_reader", "reader"]}
    assert await project_service.get_project_access(created["id"], "operator") == {
        "is_owner": True,
        "is_manager": True,
        "roles": ["member", "project_admin", "project_member", "project_owner", "project_reader", "reader"],
    }
    assert domain_projects.has_manager("creator", "tenant-a")
    assert [call for call in native.calls if call[0] == "grant" and call[2] == "operator"] == [
        ("grant", "project_owner", "operator", None, created["id"], None, False)
    ]
    owners = [row for row in native.assignments(project=created["id"]) if row.role["id"] == "project_owner"]
    assert len(owners) == 1 and owners[0].user == {"id": "operator"}
    assert native.project_rows[created["id"]].enabled is True
    assert native.activation_snapshot["direct_roles"] == {"project_owner"}
    async with native.journal() as session:
        operation = (await session.execute(select(ProjectOwnershipTransfer))).scalar_one()
        assert (operation.project_id, operation.from_user_id, operation.to_user_id, operation.status) == (
            created["id"],
            "operator",
            "operator",
            "completed",
        )
        assert list((await session.execute(select(DomainQuotaOperation))).scalars()) == []
    assert native.lock_depth == 0


@pytest.mark.asyncio
async def test_admin_project_setup_compensates_only_exact_new_project_on_postcreate_failure(policy_native):
    native = policy_native
    before = set(native.project_rows)
    read_project = native.sdk.identity.get_project

    def unavailable(project_id):
        if project_id == "created-default":
            raise ConnectionError("created resource readback reply lost")
        return read_project(project_id)

    native.sdk.identity.get_project = unavailable
    with pytest.raises(HTTPException) as failed:
        await admin_identity.create_project(
            admin_identity.CreateProjectRequest(name="New", domain_id="tenant-a"),
            conn=native.sdk,
            token_info={**actor("operator"), "is_system_admin": True},
        )
    assert failed.value.status_code == 503
    assert set(native.project_rows) == before
    assert [call for call in native.calls if call[0] == "project.delete"] == [("project.delete", "created-default")]
    assert native.members["projection-tenant-a"] == {"creator"}
    assert native.resource_cloud.calls and native.resource_cloud.unexpected == []
    assert ("project.enable", "created-default", False) in native.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["iam", "admin"])
async def test_committed_disable_timeout_reconciles_native_projection(policy_native, surface):
    native = policy_native
    if surface == "iam":
        native.user_rows["creator"].domain_id = "tenant-a"
    native.raw.append(grant("manager", user="second", project="default-a"))
    await domain_projects.sync_manager_access("tenant-a")
    assert native.members["projection-tenant-a"] == {"creator", "second"}

    def disable_then_timeout(user_id, **attrs):
        assert native.lock_depth == 1
        native.user_rows[user_id].enabled = attrs["enabled"]
        raise ConnectionError("native write committed but reply lost")

    native.users.update = disable_then_timeout
    native.sdk.identity.update_user = disable_then_timeout
    with pytest.raises(HTTPException) as failed:
        if surface == "iam":
            await domain_iam.update_user("creator", {"enabled": False}, actor("second"))
        else:
            await admin_identity.update_user(
                "creator",
                admin_identity.UpdateUserRequest(enabled=False),
                conn=native.sdk,
                token_info={**actor("operator"), "is_system_admin": True},
            )
    assert failed.value.status_code == 503
    assert not native.user_rows["creator"].enabled
    assert native.members["projection-tenant-a"] == {"second"}
    assert not domain_projects.has_manager("creator", "tenant-a")
    assert domain_projects.has_manager("second", "tenant-a")
    assert identity_roles.activity.record.await_args.kwargs["status"] == "failed"
    assert native.lock_depth == 0


@pytest.mark.asyncio
async def test_committed_manager_edge_timeout_reconciles_projection_and_failure_audit(policy_native):
    native = policy_native
    native.raw = [
        grant("alias", user="creator", project="default-a"),
        grant("manager", user="second", project="default-a"),
    ]
    await domain_projects.sync_manager_access("tenant-a")
    assert native.members["projection-tenant-a"] == {"creator", "second"}

    def remove_then_timeout(path):
        assert native.lock_depth == 1 and path == "/roles/alias/implies/manager"
        native.edges[:] = [edge for edge in native.edges if edge["prior_role"]["id"] != "alias"]
        raise ConnectionError("native edge removal committed but reply lost")

    native.sdk.identity.delete = remove_then_timeout
    with pytest.raises(HTTPException) as failed:
        await identity_roles.change_edge(native.sdk, actor("operator"), "alias", "manager", remove=True)
    assert failed.value.status_code == 503
    assert native.members["projection-tenant-a"] == {"second"}
    assert not domain_projects.has_manager("creator", "tenant-a")
    assert domain_projects.has_manager("second", "tenant-a")
    assert native.assignments(project="work-a", user="creator", effective=True) == []
    assert identity_roles.activity.record.await_args.kwargs["status"] == "failed"
    assert native.lock_depth == 0


@pytest.mark.asyncio
async def test_admin_create_provider_returning_foreign_existing_project_never_compensates_it(policy_native):
    native = policy_native
    existing = native.project_rows["work-b"]
    existing.is_enabled = existing.enabled
    native.sdk.identity.create_project = lambda **attrs: existing
    before = set(native.project_rows)
    with pytest.raises(HTTPException) as failed:
        await admin_identity.create_project(
            admin_identity.CreateProjectRequest(name="New", domain_id="tenant-a"),
            conn=native.sdk,
            token_info={**actor("operator"), "is_system_admin": True},
        )
    assert failed.value.status_code == 503
    assert set(native.project_rows) == before
    assert not any(call[0] == "project.delete" for call in native.calls)


@pytest.mark.asyncio
async def test_admin_create_lost_native_reply_never_retries_or_guesses_compensation(policy_native):
    native = policy_native
    create = native.sdk.identity.create_project
    before = set(native.project_rows)

    def create_then_timeout(**attrs):
        create(**attrs)
        raise ConnectionError("native project created but response lost")

    native.sdk.identity.create_project = create_then_timeout
    with pytest.raises(HTTPException) as failed:
        await admin_identity.create_project(
            admin_identity.CreateProjectRequest(name="New", domain_id="tenant-a"),
            conn=native.sdk,
            token_info={**actor("operator"), "is_system_admin": True},
        )
    assert failed.value.status_code == 503
    assert set(native.project_rows) == before | {"created-default"}
    assert [call for call in native.calls if call[0] == "project.create"] == [("project.create", "tenant-a")]
    assert not any(call[0] == "project.delete" for call in native.calls)
    assert native.project_rows["created-default"].enabled is False
    assert not any(call[0] == "grant" and call[2] == "operator" for call in native.calls)
    async with native.journal() as session:
        assert list((await session.execute(select(ProjectOwnershipTransfer))).scalars()) == []
        assert list((await session.execute(select(DomainQuotaOperation))).scalars()) == []
    assert (await project_service.get_project_access("created-default", "creator"))["roles"] == [
        "project_reader",
        "reader",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("genuine_projection", [False, True])
@pytest.mark.parametrize("surface", ["create", "update"])
@pytest.mark.parametrize(
    "attrs",
    [
        {"name": "afterglow-default-managers-tenant-a"},
        {"description": "afterglow:default-manager-reader:v1:tenant-a"},
        {"name": "afterglow-default-managers-tenant-a", "description": "afterglow:default-manager-reader:v1:tenant-a"},
    ],
)
async def test_generic_group_inputs_cannot_spoof_or_poison_manager_projection(
    policy_native, genuine_projection, surface, attrs
):
    native = policy_native
    if genuine_projection:
        await domain_projects.sync_manager_access("tenant-a")
    native.group_rows["ordinary-group"] = SimpleNamespace(
        id="ordinary-group", name="Ordinary", description="Plain", domain_id="tenant-a"
    )
    native.members["ordinary-group"] = set()
    before_groups = {gid: vars(group).copy() for gid, group in native.group_rows.items()}
    before_calls = list(native.calls)

    def create_group(**values):
        return native.create_group(
            name=values["name"], domain=values["domain_id"], description=values.get("description", "")
        )

    def update_group(group_id, **values):
        native.calls.append(("group.update", group_id))
        for key, value in values.items():
            setattr(native.group_rows[group_id], key, value)
        return native.group_rows[group_id]

    native.sdk.identity.create_group = create_group
    native.sdk.identity.update_group = update_group
    with pytest.raises(HTTPException) as denied:
        if surface == "create":
            await admin_identity.create_group(
                admin_identity.CreateGroupRequest(**{"name": "Ordinary", "domain_id": "tenant-a", **attrs}),
                conn=native.sdk,
                token_info=actor("operator"),
            )
        else:
            await admin_identity.update_group(
                "ordinary-group", admin_identity.UpdateGroupRequest(**attrs), conn=native.sdk
            )
    assert denied.value.status_code == 403
    assert native.calls == before_calls
    assert {gid: vars(group).copy() for gid, group in native.group_rows.items()} == before_groups
    assert native.lock_depth == 0
    await domain_projects.sync_manager_access("tenant-a")
    assert native.members["projection-tenant-a"] == {"creator"}
    assert domain_projects.has_manager("creator", "tenant-a")
    assert (await project_service.get_project_access("work-a", "creator"))["roles"] == ["project_reader", "reader"]


@pytest.mark.asyncio
async def test_direct_manager_revoke_lost_reply_removes_native_read_projection(policy_native):
    native = policy_native
    native.raw.append(grant("manager", user="second", project="default-a"))
    await domain_projects.sync_manager_access("tenant-a")
    revoke = native.roles.revoke

    def revoke_then_timeout(*args, **kwargs):
        revoke(*args, **kwargs)
        raise ConnectionError("native manager revoke committed but reply lost")

    native.roles.revoke = revoke_then_timeout
    with pytest.raises(HTTPException) as failed:
        await domain_projects.change_manager("tenant-a", "creator", "manager", remove=True, actor=actor("second"))
    assert failed.value.status_code == 503
    assert native.members["projection-tenant-a"] == {"second"}
    assert native.assignments(project="work-a", user="creator", effective=True) == []
    assert domain_projects.has_manager("second", "tenant-a")


@pytest.mark.asyncio
async def test_home_domain_disable_lost_reply_removes_external_manager_projection(policy_native):
    native = policy_native
    native.user_rows["second"].domain_id = "tenant-b"
    native.raw.append(grant("manager", user="second", project="default-a"))
    await domain_projects.sync_manager_access("tenant-a")

    def disable_then_timeout(domain_id, **attrs):
        assert native.lock_depth == 1
        native.domain_rows[domain_id].enabled = attrs["enabled"]
        raise ConnectionError("native domain disable committed but reply lost")

    native.domains.update = disable_then_timeout
    with pytest.raises(HTTPException) as failed:
        await domains.update_domain(
            "home", domains.UpdateDomainRequest(enabled=False), conn=native.sdk, token_info=actor("operator")
        )
    assert failed.value.status_code == 503
    assert native.domain_rows["home"].enabled is False
    assert native.members["projection-tenant-a"] == {"second"}
    assert native.assignments(project="work-a", user="creator", effective=True) == []
    assert domain_projects.has_manager("second", "tenant-a")
