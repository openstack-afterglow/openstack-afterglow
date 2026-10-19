"""Project delegation behavior with caller-token fixtures and durable MariaDB lifecycle."""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.identity import mcp_access
from app.config import get_settings
from app.database import Base
from app.models.activity import ActivityLog
from app.models.mcp_authority import McpDelegatedGrant, McpLumenSelection, McpPersonalToken, McpProjectCredential
from app.services import k3s_crypto, project_service
from app.services.mcp_control_plane import authority, projects
from app.services.mcp_control_plane.crypto import encrypt_application_credential

pytestmark = pytest.mark.asyncio


@pytest.fixture
def project_provider(monkeypatch):
    user_id = str(uuid4())
    project_a, project_b, project_c = str(uuid4()), str(uuid4()), str(uuid4())
    roles = {project_a: ["member"], project_b: ["reader"], project_c: ["member"]}
    memberships = [
        {"id": project_a, "name": "A", "enabled": True, "domain_id": "tenant-a"},
        {"id": project_b, "name": "B", "enabled": True, "domain_id": "tenant-a"},
    ]
    remote = {}
    created, deleted, discoveries, rescopes = [], [], [], []
    failures = {}
    blocked = set()
    current_role_overrides = {}
    delays = {}

    class Identity:
        def __init__(self, access):
            self.access = access

        def create_application_credential(self, **values):
            target = self.access.project_id
            if target in delays:
                delays[target]()
            assert values["user"] == self.access.user_id == user_id
            assert "roles" not in values
            assert values["unrestricted"] is False
            created.append((target, self.access.auth_token, values))
            if target in failures and getattr(failures[target], "status_code", None) == 403:
                raise failures[target]
            credential = SimpleNamespace(
                id=str(uuid4()),
                secret="secret-" + target,
                name=values["name"],
                project_id=target,
                roles=[
                    {"id": role_id, "name": name}
                    for role_id, name in zip(self.access.role_ids, self.access.role_names, strict=True)
                ],
            )
            remote[credential.id] = credential
            if target in failures:
                raise failures[target]
            return credential

        def find_application_credential(self, user, value, **kwargs):
            assert user == user_id
            return next(
                (credential for credential in remote.values() if value in {credential.id, credential.name}), None
            )

        def delete_application_credential(self, user, value, **kwargs):
            assert user == user_id
            credential = remote.get(value)
            if credential is not None and credential.project_id in blocked:
                raise RuntimeError("provider cleanup unavailable")
            deleted.append(value)
            remote.pop(value, None)

    class Connection:
        def __init__(self, target):
            self.closed = False
            self.access = SimpleNamespace(
                user_id=user_id,
                project_id=target,
                user_domain_id="tenant-a",
                project_domain_id="tenant-a",
                project_name=target,
                role_names=roles[target],
                role_ids=["role-" + role for role in roles[target]],
                auth_token="scoped-token-" + target,
            )
            self.session = SimpleNamespace(auth=SimpleNamespace(get_access=lambda session: self.access), get=self.get)
            self.identity = Identity(self.access)
            self._afterglow_user_id = user_id
            self._afterglow_project_id = target
            self._afterglow_token = self.access.auth_token
            self._afterglow_is_system_admin = True
            self._afterglow_domain_id = "tenant-a"
            self._afterglow_identity_domain_id = "tenant-a"

        def get(self, url, **kwargs):
            discoveries.append((url, kwargs))
            assert url == "https://keystone.example.test/v3/auth/projects"
            assert kwargs == {"headers": {"X-Auth-Token": self._afterglow_token}, "authenticated": False}
            return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"projects": memberships})

        def close(self):
            self.closed = True

    def connect(token, project_id):
        assert token.startswith("scoped-token-")
        rescopes.append((token, project_id))
        return Connection(project_id)

    monkeypatch.setattr(projects.keystone, "get_openstack_connection", connect)

    async def current_roles(project_id, owner_user_id):
        assert owner_user_id == user_id
        return current_role_overrides.get(
            project_id,
            [{"id": "role-" + name, "name": name, "inherited_role_ids": []} for name in roles[project_id]],
        )

    monkeypatch.setattr(project_service, "get_project_delegation_roles", current_roles)
    # The helper imports get_settings locally; configure the provider's trusted URL.
    settings = get_settings().model_copy(update={"os_auth_url": "https://keystone.example.test/v3"})
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr(k3s_crypto, "get_settings", lambda: SimpleNamespace(k3s_kubeconfig_encryption_key="a" * 64))
    conn = Connection(project_a)
    return SimpleNamespace(
        user=user_id,
        a=project_a,
        b=project_b,
        c=project_c,
        conn=conn,
        memberships=memberships,
        roles=roles,
        remote=remote,
        created=created,
        deleted=deleted,
        discoveries=discoveries,
        rescopes=rescopes,
        failures=failures,
        blocked=blocked,
        current_role_overrides=current_role_overrides,
        delays=delays,
        Connection=Connection,
    )


async def test_foreign_domain_memberships_never_enter_mcp_grant(project_provider):
    provider = project_provider
    provider.memberships.append({"id": provider.c, "name": "Foreign", "enabled": True, "domain_id": "tenant-b"})
    scopes = await projects.resolve_project_scope(
        provider.conn, provider.user, provider.a, ["admin"], project_scope="all"
    )
    assert {scope["id"] for scope in scopes} == {provider.a, provider.b}
    with pytest.raises(authority.McpAuthorityError):
        await projects.resolve_project_scope(
            provider.conn, provider.user, provider.a, ["admin"], project_scope="selected", project_ids=[provider.c]
        )


@pytest.mark.parametrize("domain", [None, "tenant-b"])
async def test_target_domain_must_match_selected_working_domain(project_provider, monkeypatch, domain):
    provider = project_provider
    target = provider.Connection(provider.b)
    target.access.project_domain_id = domain
    monkeypatch.setattr(projects.keystone, "get_openstack_connection", lambda token, project_id: target)
    with pytest.raises(authority.McpAuthorityError):
        await projects.project_connection(provider.conn, provider.user, provider.b)
    assert target.closed
    assert not provider.created


async def test_external_identity_account_uses_native_memberships_in_working_domain(project_provider):
    provider = project_provider
    provider.conn._afterglow_identity_domain_id = "identity-home"
    provider.conn.access.user_domain_id = "identity-home"
    discovered = await projects.caller_membership_projects(provider.conn, provider.user)
    assert {row["id"] for row in discovered} == {provider.a, provider.b}
    scope = await projects.resolve_project_scope(provider.conn, provider.user, provider.a, ["member"])
    assert scope == [{"id": provider.a, "name": provider.a, "roles": ["member"], "can_write": True}]
    provider.conn._afterglow_identity_domain_id = "forged-home"
    with pytest.raises(authority.McpAuthorityError):
        await projects.caller_membership_projects(provider.conn, provider.user)


async def test_current_authority_preparation_reports_typed_management_refusal(project_provider):
    provider = project_provider
    provider.conn.access.role_names = ["reader"]
    provider.conn.access.role_ids = ["role-reader"]
    provider.roles[provider.a] = ["reader"]
    with pytest.raises(authority.McpGrantPrivilegeError, match="management"):
        await authority._prepare_connection_projects(
            provider.conn, provider.user, provider.a, ["admin", "member"], "current", None, "manage"
        )
    approved = await authority._prepare_connection_projects(
        provider.conn, provider.user, provider.a, ["admin", "member"], "current", None, "read"
    )
    assert len(approved) == 1
    assert approved[0].roles == [{"id": "role-reader", "name": "reader"}]
    assert approved[0].can_write is False
    assert approved[0].owns_connection is False


async def test_actual_memberships_and_target_token_roles_ignore_system_admin(project_provider):
    provider = project_provider
    metadata = await projects.resolve_project_scope(
        provider.conn,
        provider.user,
        provider.a,
        ["member"],
        project_scope="selected",
        project_ids=[provider.a, provider.b],
        access_level="read",
    )
    assert metadata == [
        {"id": provider.a, "name": "A", "roles": ["member"], "can_write": True},
        {"id": provider.b, "name": "B", "roles": ["reader"], "can_write": False},
    ]
    assert provider.rescopes == [("scoped-token-" + provider.a, provider.b)]
    assert not provider.conn.closed
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await projects.resolve_project_scope(
            provider.conn,
            provider.user,
            provider.a,
            ["member"],
            project_scope="selected",
            project_ids=[provider.b],
            access_level="manage",
        )
    with pytest.raises(authority.McpAuthorityError, match="membership"):
        await projects.resolve_project_scope(
            provider.conn, provider.user, provider.a, ["admin"], project_scope="selected", project_ids=[provider.c]
        )


@pytest.mark.parametrize("moved", ["user", "project"])
async def test_actual_scoped_access_rejects_forged_connection_attributes(project_provider, moved, monkeypatch):
    provider = project_provider
    if moved == "user":
        provider.conn.access.user_id = "foreign-user"
    else:
        provider.conn.access.project_id = provider.b
        monkeypatch.setattr(
            projects.keystone, "get_openstack_connection", lambda token, target: provider.Connection(provider.b)
        )
    with pytest.raises(authority.McpAuthorityError, match="authenticated connection"):
        await projects.project_connection(provider.conn, provider.user, provider.a)
    assert not provider.created


@pytest.mark.parametrize("scope", ["current", "selected"])
async def test_logical_current_project_rescopes_authenticated_home_token(project_provider, scope):
    provider = project_provider
    # get_os_conn preserves an administrator's home SDK token while exposing the
    # browser's selected logical project. Membership in B is still authoritative.
    provider.conn._afterglow_project_id = provider.b
    provider.conn._afterglow_authenticated_project_id = provider.a
    prepared = await authority._prepare_connection_projects(
        provider.conn,
        provider.user,
        provider.b,
        ["member"],
        scope,
        [provider.b] if scope == "selected" else None,
        "read",
    )
    try:
        assert [project.metadata() for project in prepared] == [
            {
                "id": provider.b,
                "name": "B" if scope == "selected" else provider.b,
                "roles": ["reader"],
                "can_write": False,
            }
        ]
        assert provider.rescopes == [("scoped-token-" + provider.a, provider.b)]
        assert prepared[0].conn is not provider.conn
        assert prepared[0].conn.session.auth.get_access(prepared[0].conn.session).project_id == provider.b
        assert provider.conn.access.project_id == provider.a
        assert not provider.conn.closed
    finally:
        await authority.close_project_authority(prepared)


async def test_logical_current_project_cannot_reuse_home_write_roles(project_provider):
    provider = project_provider
    provider.conn._afterglow_project_id = provider.b
    provider.conn._afterglow_authenticated_project_id = provider.a
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await projects.resolve_project_scope(
            provider.conn, provider.user, provider.b, ["member"], access_level="manage"
        )
    assert provider.rescopes == [("scoped-token-" + provider.a, provider.b)]
    assert provider.created == []


async def test_all_scope_is_frozen_and_read_subset_never_allows_writes_or_new_projects(project_provider):
    provider = project_provider
    metadata = await projects.resolve_project_scope(
        provider.conn, provider.user, provider.a, ["member"], project_scope="all"
    )
    grant = SimpleNamespace(
        owner_project_id=provider.a, access_level="read", project_scope="all", approved_projects=metadata
    )
    provider.memberships.append({"id": provider.c, "name": "C", "enabled": True})
    assert authority.approved_project_metadata(grant) == [
        {"id": provider.a, "name": "A"},
        {"id": provider.b, "name": "B"},
    ]
    for project_id in (provider.a, provider.b):
        assert authority.validate_grant_project(grant, project_id)["id"] == project_id
        with pytest.raises(authority.McpGrantStateError, match="management"):
            authority.validate_grant_project(grant, project_id, write=True)
    with pytest.raises(authority.McpGrantStateError, match="outside"):
        authority.validate_grant_project(grant, provider.c)
    grant.access_level = "manage"
    authority.validate_grant_project(grant, provider.a, write=True)
    with pytest.raises(authority.McpGrantStateError, match="management"):
        authority.validate_grant_project(grant, provider.b, write=True)


async def test_legacy_null_snapshot_never_expands():
    grant = SimpleNamespace(owner_project_id="A", access_level="manage", approved_projects=None)
    assert authority.approved_project_metadata(grant) == [{"id": "A", "name": "A"}]
    authority.validate_grant_project(grant, "A", write=True)
    with pytest.raises(authority.McpGrantStateError, match="outside"):
        authority.validate_grant_project(grant, "B")


async def test_secondary_ciphertext_is_bound_to_exact_target(project_provider):
    provider = project_provider
    grant = SimpleNamespace(
        id="grant-id",
        owner_user_id=provider.user,
        owner_project_id=provider.a,
        source="personal_token",
        access_level="read",
        status="active",
        expires_at=datetime.now(UTC) + timedelta(days=1),
        approved_projects=[{"id": provider.b, "name": "B", "roles": ["reader"], "can_write": False}],
    )
    credential = SimpleNamespace(
        grant_id=grant.id,
        project_id=provider.b,
        application_credential_id="credential",
        cleanup_pending=False,
        credential_ciphertext=encrypt_application_credential(
            "B-secret", grant_id=grant.id, owner_user_id=provider.user, owner_project_id=provider.b
        ),
    )
    assert authority.decrypt_grant_secret(grant, project_id=provider.b, credential=credential) == "B-secret"
    credential.project_id = provider.a
    with pytest.raises(authority.McpGrantStateError, match="target"):
        authority.decrypt_grant_secret(grant, project_id=provider.b, credential=credential)
    credential.project_id = provider.b
    credential.credential_ciphertext = encrypt_application_credential(
        "A-secret", grant_id=grant.id, owner_user_id=provider.user, owner_project_id=provider.a
    )
    with pytest.raises(ValueError, match="invalid"):
        authority.decrypt_grant_secret(grant, project_id=provider.b, credential=credential)


async def test_project_membership_failure_is_not_an_empty_success(client, monkeypatch):
    monkeypatch.setattr(mcp_access, "get_settings", lambda: SimpleNamespace(service_mcp_enabled=True))

    async def unavailable(conn, user_id):
        raise authority.McpAuthorityError("Project membership is unavailable")

    monkeypatch.setattr(mcp_access, "caller_membership_projects", unavailable)
    response = await client.get("/api/v1/auth/mcp-projects")
    assert response.status_code == 400


@pytest.fixture(scope="module")
def project_db_tables():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name.startswith("mcp_") or table is ActivityLog.__table__
    ]

    async def schema(create):
        engine = create_async_engine(url)
        try:
            async with engine.begin() as connection:
                operation = Base.metadata.create_all if create else Base.metadata.drop_all
                await connection.run_sync(lambda sync: operation(sync, tables=tables))
        finally:
            await engine.dispose()

    asyncio.run(schema(True))
    yield url
    asyncio.run(schema(False))


@pytest.fixture
async def project_owner(project_db_tables, project_provider, monkeypatch):
    engine = create_async_engine(project_db_tables)
    project_provider.factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(
        authority,
        "get_settings",
        lambda: SimpleNamespace(
            mcp_default_grant_ttl_days=30,
            mcp_max_grant_ttl_days=90,
            mcp_max_delegated_grants=20,
            mcp_max_personal_tokens=10,
        ),
    )
    try:
        yield project_provider
    finally:
        await engine.dispose()


async def issue(owner, **kwargs):
    return await authority.issue_personal_token(
        owner.factory,
        conn=owner.conn,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        roles=["member"],
        display_name="Desktop",
        access_level=kwargs.pop("access_level", "read"),
        project_scope=kwargs.pop("project_scope", "selected"),
        project_ids=kwargs.pop("project_ids", [owner.a, owner.b]),
        **kwargs,
    )


async def cleanup(owner, grant):
    return await authority.confirm_keystone_cleanup(
        owner.factory,
        conn=owner.conn,
        grant_id=grant.id,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        application_credential_id=None,
    )


@pytest.mark.db
@pytest.mark.parametrize("project_scope", ["selected", "all"])
async def test_issuance_creates_real_scoped_credentials_and_persists_snapshot(project_owner, project_scope):
    owner = project_owner
    issued = await issue(
        owner, project_scope=project_scope, project_ids=[owner.a, owner.b] if project_scope == "selected" else None
    )
    owner.memberships.append({"id": owner.c, "name": "C", "enabled": True})
    assert [target for target, token, values in owner.created] == [owner.a, owner.b]
    assert [token for target, token, values in owner.created] == ["scoped-token-" + owner.a, "scoped-token-" + owner.b]
    async with owner.factory() as session, session.begin():
        grant = await authority.resolve_personal_token(session, issued.token)
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert grant.project_scope == project_scope
        with pytest.raises(authority.McpGrantStateError, match="outside"):
            authority.validate_grant_project(grant, owner.c)
        assert authority.approved_project_metadata(grant) == [
            {"id": owner.a, "name": "A"},
            {"id": owner.b, "name": "B"},
        ]
        assert authority.decrypt_grant_secret(grant) == "secret-" + owner.a
        assert authority.decrypt_grant_secret(grant, owner.b, secondary) == "secret-" + owner.b
        assert "secret-" not in secondary.credential_ciphertext
        assert secondary.cleanup_pending is False
        assert authority.grant_public_view(grant)["projects"] == authority.approved_project_metadata(grant)
        assert "approved_projects" not in authority.grant_public_view(grant)


@pytest.mark.db
async def test_selected_subset_can_exclude_home_without_issuing_home_credential(project_owner):
    owner = project_owner
    issued = await issue(owner, project_ids=[owner.b])
    async with owner.factory() as session, session.begin():
        grant = await authority.resolve_personal_token(session, issued.token)
        assert grant.application_credential_id is None and grant.credential_ciphertext is None
        assert authority.default_grant_project(grant) == owner.b
        credential_id, secret = await authority.grant_credential_for_project(session, grant, owner.b)
        assert credential_id in owner.remote and secret == "secret-" + owner.b
        with pytest.raises(authority.McpGrantStateError, match="outside"):
            authority.validate_grant_project(grant, owner.a)
    assert [target for target, token, values in owner.created] == [owner.b]


@pytest.mark.db
async def test_manage_reader_rejected_before_any_reservation_or_remote_creation(project_owner):
    owner = project_owner
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await issue(owner, access_level="manage")
    async with owner.factory() as session:
        assert (
            await session.scalars(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
        ).all() == []
    assert owner.created == []


@pytest.mark.db
@pytest.mark.parametrize("ambiguous", [True, False], ids=["timeout-after-create", "definitive-403"])
async def test_partial_ambiguous_creation_retains_durable_name_and_cleanup_capacity(
    project_owner, monkeypatch, ambiguous
):
    owner = project_owner
    error = (
        TimeoutError("unknown provider creation result")
        if ambiguous
        else type("Denied", (RuntimeError,), {"status_code": 403})("denied")
    )
    owner.failures[owner.b] = error
    with pytest.raises(type(error)):
        await issue(owner)
    async with owner.factory() as session:
        grant = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert grant.status == "revoked" and grant.cleanup_pending
        assert secondary.application_credential_id is None and secondary.cleanup_pending
        assert secondary.upstream_credential_name.startswith("afterglow-mcp-" + grant.id)
        if ambiguous:
            assert secondary.upstream_credential_name in {credential.name for credential in owner.remote.values()}
        assert (
            await authority._count_dispatchable_personal_tokens(
                session, owner_user_id=owner.user, owner_project_id=owner.a
            )
            == 1
        )
    assert {credential.project_id for credential in owner.remote.values()} == ({owner.b} if ambiguous else set())
    future = datetime.now(UTC) + timedelta(hours=1)
    monkeypatch.setattr(authority, "_now", lambda: future)
    assert await cleanup(owner, grant)
    async with owner.factory() as session:
        refreshed = await session.get(McpDelegatedGrant, grant.id)
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert not refreshed.cleanup_pending and not secondary.cleanup_pending
    assert owner.remote == {}


@pytest.mark.db
async def test_revoke_partial_cleanup_records_each_project_and_retries_remaining(project_owner):
    owner = project_owner
    issued = await issue(owner)
    owner.blocked.add(owner.b)
    await authority.revoke_grant(
        owner.factory,
        grant_id=issued.grant_id,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
    )
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
    assert not await cleanup(owner, grant)
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert grant.application_credential_id is None and grant.cleanup_pending
        assert secondary.application_credential_id in owner.remote and secondary.cleanup_pending
    owner.blocked.clear()
    assert await cleanup(owner, grant)
    assert owner.remote == {}
    async with owner.factory() as session:
        with pytest.raises(authority.McpGrantNotFoundError):
            await authority.resolve_personal_token(session, issued.token)


@pytest.mark.db
async def test_expiry_marks_additional_credentials_and_clears_lumen_selection(project_owner):
    owner = project_owner
    issued = await issue(owner)
    await authority.set_lumen_selection(
        owner.factory,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        grant_id=issued.grant_id,
    )
    assert (
        await authority.mark_expired_grants_for_cleanup(owner.factory, now=issued.expires_at + timedelta(seconds=1))
        >= 1
    )
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert grant.status == "expired" and grant.cleanup_pending and secondary.cleanup_pending
        assert await session.get(McpLumenSelection, {"owner_user_id": owner.user, "owner_project_id": owner.a}) is None
    assert await cleanup(owner, grant)
    assert not owner.remote


@pytest.mark.db
async def test_non_expiring_personal_key_survives_cleanup_but_not_revocation(project_owner):
    owner = project_owner
    issued = await issue(owner, non_expiring=True)
    assert issued.expires_at is None
    assert all("expires_at" not in values for _, _, values in owner.created)
    await authority.set_lumen_selection(
        owner.factory,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        grant_id=issued.grant_id,
    )
    future = datetime.now(UTC) + timedelta(days=3660)
    await authority.mark_expired_grants_for_cleanup(owner.factory, now=future)
    async with owner.factory() as session, session.begin():
        grant = await authority.resolve_personal_token(session, issued.token, now=future)
        assert grant.status == "active" and grant.expires_at is None
        assert authority.grant_public_view(grant)["expires_at"] is None
        selection = await session.get(McpLumenSelection, {"owner_user_id": owner.user, "owner_project_id": owner.a})
        assert selection.grant_id == grant.id
        assert authority.decrypt_grant_secret(grant) == "secret-" + owner.a
    await authority.revoke_grant(
        owner.factory,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        grant_id=issued.grant_id,
    )
    async with owner.factory() as session, session.begin():
        with pytest.raises(authority.McpGrantNotFoundError):
            await authority.resolve_personal_token(session, issued.token, now=future)
        assert await session.get(McpLumenSelection, {"owner_user_id": owner.user, "owner_project_id": owner.a}) is None
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        assert grant.status == "revoked" and grant.credential_epoch == 2 and grant.cleanup_pending
    assert await cleanup(owner, grant)
    assert not owner.remote


@pytest.mark.db
@pytest.mark.parametrize("lifetime", ["never", "six_months", "year"])
async def test_personal_key_http_persists_requested_lifetime_and_rejects_conflicting_fields(
    project_owner, client, monkeypatch, lifetime
):
    from app.api.deps import get_os_conn, get_token_info
    from app.main import app

    owner = project_owner
    caller = {"user_id": owner.user, "project_id": owner.a, "username": "fixture-owner", "roles": ["member"]}
    monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: caller)
    monkeypatch.setitem(app.dependency_overrides, get_os_conn, lambda: owner.conn)
    monkeypatch.setattr(mcp_access, "_session_factory", lambda: owner.factory)
    monkeypatch.setattr(
        mcp_access,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=True,
            frontend_base_url="https://app.example.test",
            public_api_base="https://api.example.test",
            cors_origin_list=("https://app.example.test",),
        ),
    )
    deadline = datetime.now(UTC) + timedelta(days=183 if lifetime == "six_months" else 366)
    lifetime_fields = {"non_expiring": True} if lifetime == "never" else {"expires_at": deadline.isoformat()}
    payload = {
        "name": "Desktop",
        "access_level": "read",
        "project_scope": "selected",
        "project_ids": [owner.a, owner.b],
        **lifetime_fields,
    }
    headers = {"Origin": "https://app.example.test", "Sec-Fetch-Site": "same-site"}
    response = await client.post("/api/v1/auth/mcp-tokens", json=payload, headers=headers)
    assert response.status_code == 201
    issued = response.json()
    assert (
        issued["expires_at"] is None
        if lifetime == "never"
        else (datetime.fromisoformat(issued["expires_at"]) == deadline)
    )
    async with owner.factory() as session, session.begin():
        grant = await authority.resolve_personal_token(session, issued["token"])
        assert grant.expires_at is None if lifetime == "never" else authority._as_utc(grant.expires_at) == deadline
        assert authority.grant_project_ids(grant) == (owner.a, owner.b)
    listed = await client.get("/api/v1/auth/mcp-tokens")
    assert listed.status_code == 200 and listed.json()[0]["expires_at"] == issued["expires_at"]
    assert "token" not in listed.json()[0]
    written = len(owner.created)
    rejected = await client.post(
        "/api/v1/auth/mcp-tokens",
        json={**payload, "non_expiring": True, "expires_at": deadline.isoformat()},
        headers=headers,
    )
    assert rejected.status_code == 422 and len(owner.created) == written
    invalid_bool = await client.post(
        "/api/v1/auth/mcp-tokens",
        json={**payload, "non_expiring": "false"},
        headers=headers,
    )
    assert invalid_bool.status_code == 422 and len(owner.created) == written
    assert (await client.delete(f"/api/v1/auth/mcp-tokens/{issued['id']}", headers=headers)).status_code == 204
    async with owner.factory() as session, session.begin():
        with pytest.raises(authority.McpGrantNotFoundError):
            await authority.resolve_personal_token(session, issued["token"])
    assert not owner.remote


@pytest.mark.db
@pytest.mark.parametrize("delayed_project", ["a", "b"], ids=["primary", "additional"])
async def test_late_cancellation_drains_creation_and_deletes_returned_credential(project_owner, delayed_project):
    owner = project_owner
    started, finish = threading.Event(), threading.Event()

    def delayed():
        started.set()
        assert finish.wait(10)

    owner.delays[getattr(owner, delayed_project)] = delayed
    pending = asyncio.create_task(issue(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with owner.factory() as session:
            grant = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
            assert await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b}) is not None
            if delayed_project == "b":
                assert grant.application_credential_id is not None
                assert grant.credential_ciphertext is not None
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert owner.remote == {}
    assert not owner.conn.closed
    async with owner.factory() as session:
        grant = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
        assert grant.status == "revoked"
        assert (
            await session.scalars(select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id))
        ).all() == []


@pytest.mark.db
async def test_internal_lumen_selection_needs_no_pat_but_personal_selection_does(project_owner):
    owner = project_owner
    issued = await issue(owner, project_scope="current", project_ids=None)
    async with owner.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued.grant_id, with_for_update=True)
        token = await session.scalar(select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id))
        await session.delete(token)
    with pytest.raises(authority.McpGrantStateError, match="active delegated"):
        await authority.set_lumen_selection(
            owner.factory,
            owner_user_id=owner.user,
            owner_project_id=owner.a,
            username="fixture-owner",
            grant_id=issued.grant_id,
        )
    async with owner.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued.grant_id, with_for_update=True)
        grant.source = "lumen"
    with pytest.raises(authority.McpGrantStateError, match="explicit consent"):
        await authority.set_lumen_selection(
            owner.factory,
            owner_user_id=owner.user,
            owner_project_id=owner.a,
            username="fixture-owner",
            grant_id=issued.grant_id,
        )
    async with owner.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued.grant_id, with_for_update=True)
        grant.consented_at = datetime.now(UTC)
    generation = await authority.set_lumen_selection(
        owner.factory,
        owner_user_id=owner.user,
        owner_project_id=owner.a,
        username="fixture-owner",
        grant_id=issued.grant_id,
    )
    assert generation >= 1


@pytest.mark.db
async def test_secondary_encryption_failure_preserves_id_then_cleans_all_created_credentials(
    project_owner, monkeypatch
):
    owner = project_owner
    original = authority.encrypt_application_credential

    def encrypt(secret, **binding):
        if binding["owner_project_id"] == owner.b:
            raise ValueError("synthetic encryption failure")
        return original(secret, **binding)

    monkeypatch.setattr(authority, "encrypt_application_credential", encrypt)
    with pytest.raises(ValueError, match="encryption failure"):
        await issue(owner)
    assert [target for target, token, values in owner.created] == [owner.a, owner.b]
    assert owner.remote == {}
    async with owner.factory() as session:
        grant = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
        secondary = await session.get(McpProjectCredential, {"grant_id": grant.id, "project_id": owner.b})
        assert grant.status == "revoked" and not grant.cleanup_pending
        assert secondary.application_credential_id is None and secondary.credential_ciphertext is None


@pytest.mark.db
async def test_revocation_during_secondary_creation_prevents_late_activation(project_owner):
    owner = project_owner
    started, finish = threading.Event(), threading.Event()

    def delayed():
        started.set()
        assert finish.wait(10)

    owner.delays[owner.b] = delayed
    pending = asyncio.create_task(issue(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        async with owner.factory() as session:
            grant = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
            assert grant.application_credential_id is not None
        await authority.revoke_grant(
            owner.factory,
            grant_id=grant.id,
            owner_user_id=owner.user,
            owner_project_id=owner.a,
            username="fixture-owner",
        )
    finally:
        finish.set()
    with pytest.raises(authority.McpGrantStateError, match="changed"):
        await pending
    assert owner.remote == {}
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant.id)
        assert grant.status == "revoked" and not grant.cleanup_pending
        assert (
            await session.scalars(select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id))
        ).all() == []


async def test_manage_uses_target_roles_not_current_roles_or_admin_flag(project_provider):
    provider = project_provider
    provider.conn._afterglow_is_system_admin = True
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await projects.resolve_project_scope(
            provider.conn,
            provider.user,
            provider.a,
            ["admin", "member"],
            project_scope="selected",
            project_ids=[provider.b],
            access_level="manage",
        )
    provider.roles[provider.b] = ["member"]
    metadata = await projects.resolve_project_scope(
        provider.conn,
        provider.user,
        provider.a,
        ["reader"],
        project_scope="selected",
        project_ids=[provider.b],
        access_level="manage",
    )
    assert metadata == [{"id": provider.b, "name": "B", "roles": ["member"], "can_write": True}]


async def test_current_scope_reuses_verified_token_and_saves_real_project_name(project_provider):
    provider = project_provider
    provider.conn.access.project_name = "Current project"
    metadata = await projects.resolve_project_scope(provider.conn, provider.user, provider.a, ["foreign-role"])
    assert metadata == [{"id": provider.a, "name": "Current project", "roles": ["member"], "can_write": True}]
    assert provider.rescopes == [] and provider.discoveries == []
    assert not provider.conn.closed


async def test_membership_discovery_excludes_disabled_projects_and_checks_actual_owner(project_provider):
    provider = project_provider
    provider.memberships.append({"id": provider.c, "name": "Disabled", "enabled": False})
    assert await projects.caller_membership_projects(provider.conn, provider.user) == [
        {"id": provider.a, "name": "A"},
        {"id": provider.b, "name": "B"},
    ]
    provider.conn.access.user_id = "foreign-owner"
    with pytest.raises(authority.McpAuthorityError, match="authenticated connection"):
        await projects.caller_membership_projects(provider.conn, provider.user)
    assert len(provider.discoveries) == 1


@pytest.mark.db
async def test_owner_locked_pending_reservation_consumes_capacity_before_creation(project_owner, monkeypatch):
    owner = project_owner
    monkeypatch.setattr(
        authority,
        "get_settings",
        lambda: SimpleNamespace(
            mcp_default_grant_ttl_days=30,
            mcp_max_grant_ttl_days=90,
            mcp_max_delegated_grants=1,
            mcp_max_personal_tokens=1,
        ),
    )
    started, finish = threading.Event(), threading.Event()

    def delayed():
        started.set()
        assert finish.wait(10)

    owner.delays[owner.a] = delayed
    pending = asyncio.create_task(issue(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        with pytest.raises(authority.McpGrantLimitError, match="maximum"):
            await issue(owner)
        async with owner.factory() as session:
            grants = (
                await session.scalars(select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.user))
            ).all()
            assert len(grants) == 1 and grants[0].status == "pending"
            assert (
                await session.get(McpProjectCredential, {"grant_id": grants[0].id, "project_id": owner.b}) is not None
            )
    finally:
        finish.set()
    issued = await pending
    assert [target for target, token, values in owner.created] == [owner.a, owner.b]
    assert issued.grant_id == grants[0].id


@pytest.mark.parametrize("role_ids", [[], [""], [None], ["role-member", "unexpected-extra"]])
async def test_target_token_requires_exact_role_id_name_pairs(project_provider, role_ids):
    provider = project_provider
    provider.conn.access.role_ids = role_ids
    with pytest.raises(authority.McpAuthorityError, match="invalid role identities"):
        await projects.project_connection(provider.conn, provider.user, provider.a)
    assert provider.created == []


async def test_stale_token_admin_never_becomes_current_project_delegation(project_provider):
    provider = project_provider
    provider.conn.access.role_names = ["admin", "member", "reader"]
    provider.conn.access.role_ids = ["role-admin", "role-member", "role-reader"]
    provider.current_role_overrides[provider.a] = [
        {"id": "role-member", "name": "member", "inherited_role_ids": ["role-reader"]},
        {"id": "role-reader", "name": "reader", "inherited_role_ids": []},
    ]
    prepared = await authority._prepare_connection_projects(
        provider.conn, provider.user, provider.a, ["admin"], "current", None, "manage"
    )
    assert prepared[0].roles == [{"id": "role-member", "name": "member"}, {"id": "role-reader", "name": "reader"}]
    assert prepared[0].can_write is True
    assert prepared[0].conn._afterglow_delegation_narrowed is True
    assert provider.created == []


async def test_current_graph_cannot_expand_delegation_beyond_authenticated_roles(project_provider):
    provider = project_provider
    provider.conn.access.role_names = ["member", "reader"]
    provider.conn.access.role_ids = ["role-member", "role-reader"]
    provider.current_role_overrides[provider.a] = [
        {"id": "role-member", "name": "member", "inherited_role_ids": ["role-reader", "new-role"]},
        {"id": "role-reader", "name": "reader", "inherited_role_ids": []},
        {"id": "new-role", "name": "new-capability", "inherited_role_ids": []},
    ]
    prepared = await authority._prepare_connection_projects(
        provider.conn, provider.user, provider.a, ["member"], "current", None, "manage"
    )
    assert prepared[0].roles == [{"id": "role-member", "name": "member"}, {"id": "role-reader", "name": "reader"}]
    assert prepared[0].can_write is True
    assert prepared[0].conn._afterglow_delegation_narrowed is False
    credential = authority.create_restricted_application_credential(
        prepared[0].conn,
        owner_user_id=provider.user,
        owner_project_id=provider.a,
        upstream_name="graph-added-descendant",
        expires_at=None,
        roles=prepared[0].roles,
    )
    assert credential["roles"] == prepared[0].roles
    assert "roles" not in provider.created[0][2]
