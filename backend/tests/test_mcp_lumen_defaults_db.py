"""Explicit Lumen consent lifecycle against a disposable MariaDB schema."""

from __future__ import annotations

import asyncio
import os
import threading
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.activity import ActivityLog
from app.models.mcp_authority import McpDelegatedGrant, McpLumenSelection, McpOwnerLock, McpPersonalToken
from app.services.mcp_control_plane import authority, defaults, lumen, registry
from app.services.mcp_control_plane.crypto import encrypt_application_credential

pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest.fixture(scope="module")
def db_tables():
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
async def owner(db_tables, monkeypatch):
    engine = create_async_engine(db_tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(defaults, "get_session_factory", lambda: factory)
    monkeypatch.setattr(lumen, "get_session_factory", lambda: factory)
    user_id, project_id = str(uuid4()), str(uuid4())
    state = SimpleNamespace(
        factory=factory,
        info={
            "user_id": user_id,
            "project_id": project_id,
            "username": "consent-owner",
            "token": "synthetic-owner-token",
            "roles": ["member"],
        },
        roles=["member"],
        created=[],
        deleted=[],
        listed=[],
        remote={},
        prepared=[],
        closed=[],
    )

    class Identity:
        def create_application_credential(self, **values):
            assert values["user"] == state.conn._afterglow_user_id
            assert values["unrestricted"] is False
            assert "roles" not in values
            credential = SimpleNamespace(
                id=str(uuid4()),
                name=values["name"],
                secret="synthetic-keystone-secret",
                user_id=values["user"],
                project_id=state.conn._afterglow_project_id,
                roles=[{"id": "role-" + role, "name": role} for role in state.roles],
            )
            state.created.append(values)
            state.remote[credential.id] = credential
            return credential

        def application_credentials(self, user):
            assert user == state.conn._afterglow_user_id
            state.listed.append((user, state.conn._afterglow_project_id))
            return iter(
                [
                    credential
                    for credential in state.remote.values()
                    if credential.user_id == user and credential.project_id == state.conn._afterglow_project_id
                ]
            )

        def find_application_credential(self, user, value, **kwargs):
            assert kwargs == {"ignore_missing": True}
            return next(
                (
                    credential
                    for credential in self.application_credentials(user)
                    if value in {credential.id, credential.name}
                ),
                None,
            )

        def delete_application_credential(self, user, value, **kwargs):
            assert user == state.conn._afterglow_user_id
            assert kwargs == {"ignore_missing": True}
            credential = state.remote.get(value)
            if credential is not None:
                assert (credential.user_id, credential.project_id) == (user, state.conn._afterglow_project_id)
                del state.remote[value]
            state.deleted.append((user, state.conn._afterglow_project_id, value))

    state.conn = SimpleNamespace(
        _afterglow_user_id=user_id,
        _afterglow_project_id=project_id,
        identity=Identity(),
        close=lambda: state.closed.append(True),
    )

    async def prepare(token_info, *, project_scope="current", project_ids=None, access_level="read"):
        assert project_scope == "current" and project_ids is None
        assert token_info["token"] == state.info["token"]
        state.prepared.append(access_level)
        roles = authority._role_snapshot([{"id": "role-" + role, "name": role} for role in state.roles])
        can_write = bool({role["name"].casefold() for role in roles} & {"admin", "member"})
        if access_level == "manage" and not can_write:
            raise authority.McpGrantPrivilegeError("selected project does not allow management")
        return [
            authority.ApprovedProject(
                id=state.info["project_id"],
                name="Current owner project",
                roles=roles,
                can_write=can_write,
                conn=state.conn,
                owns_connection=False,
            )
        ]

    monkeypatch.setattr(authority, "prepare_project_authority", prepare)
    try:
        yield state
        assert state.closed == [], "borrowed owner connections must not be closed"
    finally:
        await engine.dispose()


async def selected(owner):
    return await lumen.selected_lumen_snapshot(user_id=owner.info["user_id"], project_id=owner.info["project_id"])


async def approve(owner, access_level="read"):
    await defaults.approve_lumen_grant(token_info=owner.info, access_level=access_level)
    snapshot = await selected(owner)
    assert snapshot is not None
    return snapshot


async def generation(owner):
    async with owner.factory() as session:
        row = await session.get(
            McpOwnerLock, {"owner_user_id": owner.info["user_id"], "owner_project_id": owner.info["project_id"]}
        )
        return row.lumen_selection_generation


async def internal_grants(owner):
    async with owner.factory() as session:
        return (
            await session.scalars(
                select(McpDelegatedGrant).where(
                    McpDelegatedGrant.owner_user_id == owner.info["user_id"],
                    McpDelegatedGrant.owner_project_id == owner.info["project_id"],
                    McpDelegatedGrant.source == "lumen",
                )
            )
        ).all()


async def personal_selection(owner):
    user_id, project_id = owner.info["user_id"], owner.info["project_id"]
    grant_id = str(uuid4())
    now = datetime.now(UTC)
    async with owner.factory() as session, session.begin():
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id=user_id,
                owner_project_id=project_id,
                upstream_credential_name="manual-" + grant_id,
                display_name="Manual manage",
                source="personal_token",
                access_level="manage",
                status="active",
                application_credential_id="manual-credential-" + grant_id,
                expires_at=now + timedelta(days=1),
                credential_ciphertext=encrypt_application_credential(
                    "manual-secret",
                    grant_id=grant_id,
                    owner_user_id=user_id,
                    owner_project_id=project_id,
                ),
            )
        )
        await session.flush()
        session.add(
            McpPersonalToken(
                grant_id=grant_id, visible_prefix="mcp-afgl-test", token_hash=grant_id.replace("-", "") * 2
            )
        )
    await authority.set_lumen_selection(
        owner.factory, owner_user_id=user_id, owner_project_id=project_id, username="manual-owner", grant_id=grant_id
    )
    return grant_id


def pause_creation(owner, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    original_create = owner.conn.identity.create_application_credential

    def delayed(**values):
        started.set()
        if not finish.wait(10):
            raise TimeoutError("fixture did not release creation")
        return original_create(**values)

    monkeypatch.setattr(owner.conn.identity, "create_application_credential", delayed)
    return started, finish


async def test_before_approval_stays_off_without_creating_credentials(owner):
    assert await selected(owner) is None
    assert await selected(owner) is None
    assert owner.created == owner.deleted == owner.listed == owner.prepared == []
    assert await internal_grants(owner) == []


@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_explicit_consent_uses_actual_roles_without_personal_bearer(owner, access_level):
    owner.info["roles"] = ["admin", "logical-role-not-held"]
    snapshot = await approve(owner, access_level)
    principal = await lumen.resolve_lumen_principal(snapshot)
    expected = {"mcp:read"} if access_level == "read" else {"mcp:read", "mcp:write"}
    assert principal.scopes == frozenset(expected)
    assert principal.can_write is (access_level == "manage")
    if access_level == "read":
        assert all(entry.effect == "read" for entry in registry.enabled_entries(principal))
    assert len(owner.created) == 1
    assert "roles" not in owner.created[0]
    assert owner.created[0]["user"] == owner.info["user_id"]
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, snapshot.grant_id)
        assert grant.source == "lumen" and grant.status == "active"
        assert grant.access_level == access_level and grant.consented_at is not None
        assert grant.approved_projects == [
            {"id": owner.info["project_id"], "name": "Current owner project", "roles": ["member"], "can_write": True}
        ]
        assert not grant.cleanup_pending
        assert grant.application_credential_id in owner.remote
        assert grant.credential_ciphertext is not None
        assert (
            await session.scalar(
                select(func.count()).select_from(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id)
            )
            == 0
        )


async def test_reader_roles_attenuate_read_and_refuse_manage_despite_logical_admin(owner):
    owner.roles = ["reader"]
    owner.info["roles"] = ["admin"]
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await approve(owner, "manage")
    assert owner.created == []
    assert await internal_grants(owner) == []
    assert await selected(owner) is None
    snapshot = await approve(owner, "read")
    assert not (await lumen.resolve_lumen_principal(snapshot)).can_write
    assert "roles" not in owner.created[0]
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, snapshot.grant_id)
        assert grant.approved_projects[0]["can_write"] is False
    with pytest.raises(authority.McpAuthorityError, match="management"):
        await approve(owner, "manage")
    assert await selected(owner) == snapshot
    assert len(owner.created) == 1


@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_same_explicit_approval_is_idempotent(owner, access_level):
    first = await approve(owner, access_level)
    async with owner.factory() as session:
        consented_at = (await session.get(McpDelegatedGrant, first.grant_id)).consented_at
    assert await approve(owner, access_level) == first
    assert len(owner.created) == 1
    assert owner.deleted == []
    async with owner.factory() as session:
        assert (await session.get(McpDelegatedGrant, first.grant_id)).consented_at == consented_at


async def test_explicit_approval_is_isolated_by_user_and_project(owner):
    first = await approve(owner)
    owner.info = {**owner.info, "project_id": str(uuid4())}
    owner.conn._afterglow_project_id = owner.info["project_id"]
    assert await selected(owner) is None
    second = await approve(owner, "manage")
    owner.info = {**owner.info, "user_id": str(uuid4())}
    owner.conn._afterglow_user_id = owner.info["user_id"]
    assert await selected(owner) is None
    third = await approve(owner)
    assert len({first.grant_id, second.grant_id, third.grant_id}) == 3
    await defaults.disable_lumen_grant(token_info=owner.info)
    assert await selected(owner) is None
    assert (await lumen.resolve_lumen_principal(first)).project_id == first.project_id
    assert (await lumen.resolve_lumen_principal(second)).can_write
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(third)
    assert len(owner.deleted) == 1
    assert owner.deleted[0][:2] == (third.user_id, third.project_id)
    assert len(owner.remote) == 2


async def test_pat_is_preserved_without_action_and_replaced_only_by_explicit_approval(owner):
    manual_id = await personal_selection(owner)
    manual = await selected(owner)
    assert await selected(owner) == manual
    assert (await lumen.resolve_lumen_principal(manual)).can_write
    assert owner.created == []
    assert await internal_grants(owner) == []
    current = await approve(owner, "read")
    assert current.grant_id != manual_id
    assert not (await lumen.resolve_lumen_principal(current)).can_write
    assert len(owner.created) == 1
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(manual)
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, manual_id)
        token = await session.scalar(select(McpPersonalToken).where(McpPersonalToken.grant_id == manual_id))
        assert grant.status == "active" and grant.revoked_at is None
        assert token.revoked_at is None


async def test_manual_selection_during_approval_wins_and_created_grant_is_cleaned(owner, monkeypatch):
    started, finish = pause_creation(owner, monkeypatch)
    preparing = asyncio.create_task(approve(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        manual_id = await personal_selection(owner)
        manual = await selected(owner)
    finally:
        finish.set()
        with pytest.raises(authority.McpGrantStateError, match="changed before activation"):
            await preparing
    assert (await selected(owner)).grant_id == manual_id
    assert await selected(owner) == manual
    assert (await lumen.resolve_lumen_principal(manual)).can_write
    (grant,) = await internal_grants(owner)
    assert grant.status == "revoked" and grant.revoked_at is not None
    assert not grant.cleanup_pending
    assert grant.application_credential_id is None and grant.credential_ciphertext is None
    assert len(owner.created) == len(owner.deleted) == 1
    assert owner.remote == {}
    assert owner.deleted[0][:2] == (owner.info["user_id"], owner.info["project_id"])


@pytest.mark.parametrize("competing_level", ["read", "manage"])
async def test_concurrent_approval_conflicts_with_pending_reservation(owner, monkeypatch, competing_level):
    started, finish = pause_creation(owner, monkeypatch)
    preparing = asyncio.create_task(approve(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        assert await selected(owner) is None
        (grant,) = await internal_grants(owner)
        assert grant.status == "pending" and grant.consented_at is not None
        with pytest.raises(authority.McpGrantStateError, match="being prepared"):
            await approve(owner, competing_level)
    finally:
        finish.set()
        snapshot = await preparing
    assert await selected(owner) == snapshot
    assert len(owner.created) == 1
    assert owner.deleted == []


@pytest.mark.parametrize("had_selection", [False, True])
async def test_disable_during_pending_approval_cancels_activation_and_fences_snapshots(
    owner, monkeypatch, had_selection
):
    old = await approve(owner) if had_selection else None
    started, finish = pause_creation(owner, monkeypatch)
    preparing = asyncio.create_task(approve(owner, "manage"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        before = await generation(owner)
        await defaults.disable_lumen_grant(token_info=owner.info)
        assert await generation(owner) > before
        assert await selected(owner) is None
        if old is not None:
            with pytest.raises(lumen.McpLumenAuthorityError):
                await lumen.resolve_lumen_principal(old)
    finally:
        finish.set()
        with pytest.raises(authority.McpAuthorityError):
            await preparing
    assert await selected(owner) is None
    grants = await internal_grants(owner)
    assert all(grant.status == "revoked" and not grant.cleanup_pending for grant in grants)
    assert all(grant.application_credential_id is None and grant.credential_ciphertext is None for grant in grants)
    assert owner.remote == {}
    assert len(owner.deleted) == len(owner.created) == (2 if had_selection else 1)


@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_disable_stays_off_until_explicit_reapproval(owner, access_level):
    old = await approve(owner, access_level)
    await defaults.disable_lumen_grant(token_info=owner.info)
    assert await selected(owner) is None
    assert await selected(owner) is None
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    disabled_generation = await generation(owner)
    await defaults.disable_lumen_grant(token_info=owner.info)
    assert await generation(owner) > disabled_generation
    assert await selected(owner) is None
    assert len(owner.created) == 1 and owner.remote == {}
    (grant,) = await internal_grants(owner)
    assert grant.status == "revoked" and not grant.cleanup_pending
    current = await approve(owner, access_level)
    assert current.grant_id != old.grant_id
    assert current.selection_generation > old.selection_generation
    assert len(owner.created) == 2
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)


async def test_disable_clears_pat_selection_without_revoking_pat(owner):
    manual_id = await personal_selection(owner)
    old = await selected(owner)
    await defaults.disable_lumen_grant(token_info=owner.info)
    assert await selected(owner) is None
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, manual_id)
        token = await session.scalar(select(McpPersonalToken).where(McpPersonalToken.grant_id == manual_id))
        assert grant.status == "active" and token.revoked_at is None
    assert owner.created == owner.deleted == []


async def test_expiry_stays_off_until_explicit_reapproval_and_fences_old_run(owner):
    old = await approve(owner)
    async with owner.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, old.grant_id)
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert await selected(owner) is None
    assert await selected(owner) is None
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    assert len(owner.created) == 1
    await authority.mark_expired_grants_for_cleanup(owner.factory)
    assert await selected(owner) is None
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, old.grant_id)
        assert grant.status == "expired" and grant.cleanup_pending
        assert grant.credential_epoch > old.credential_epoch
    current = await approve(owner)
    assert current.grant_id != old.grant_id
    assert current.selection_generation > old.selection_generation
    assert len(owner.created) == 2
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)


async def test_legacy_implicit_grant_is_nondispatchable_and_reapproval_creates_new_grant(owner):
    user_id, project_id = owner.info["user_id"], owner.info["project_id"]
    grant_id = str(uuid4())
    credential = owner.conn.identity.create_application_credential(
        user=user_id, name="afterglow-mcp-" + grant_id, unrestricted=False
    )
    async with owner.factory() as session, session.begin():
        owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
        owner_lock.lumen_selection_generation += 1
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id=user_id,
                owner_project_id=project_id,
                upstream_credential_name=credential.name,
                display_name="Legacy implicit Lumen",
                source="lumen",
                access_level="read",
                status="active",
                consented_at=None,
                application_credential_id=credential.id,
                expires_at=datetime.now(UTC) + timedelta(days=1),
                credential_ciphertext=encrypt_application_credential(
                    credential.secret, grant_id=grant_id, owner_user_id=user_id, owner_project_id=project_id
                ),
            )
        )
        await session.flush()
        session.add(McpLumenSelection(owner_user_id=user_id, owner_project_id=project_id, grant_id=grant_id))
        old = lumen.LumenGrantSnapshot(grant_id, user_id, project_id, 1, owner_lock.lumen_selection_generation)
    assert await selected(owner) is None
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    assert len(owner.created) == 1
    current = await approve(owner)
    assert current.grant_id != grant_id
    assert len(owner.created) == 2
    assert (await lumen.resolve_lumen_principal(current)).scopes == frozenset({"mcp:read"})
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    async with owner.factory() as session:
        assert (await session.get(McpDelegatedGrant, grant_id)).consented_at is None
        assert (await session.get(McpDelegatedGrant, current.grant_id)).consented_at is not None


@pytest.mark.parametrize("mismatch", ["user", "project", "missing_user", "missing_project"])
async def test_missing_exact_owner_scope_refuses_approval_before_credentials(owner, mismatch):
    attribute = "_afterglow_user_id" if mismatch.endswith("user") else "_afterglow_project_id"
    if mismatch.startswith("missing"):
        delattr(owner.conn, attribute)
    else:
        setattr(owner.conn, attribute, str(uuid4()))
    with pytest.raises(authority.McpAuthorityError):
        await approve(owner)
    assert owner.created == []
    assert await selected(owner) is None
    assert await internal_grants(owner) == []


@pytest.mark.parametrize("prepared_scope", ["missing", "foreign", "multiple"])
async def test_missing_exact_current_project_approval_refuses_credentials(owner, monkeypatch, prepared_scope):
    original_prepare = authority.prepare_project_authority

    async def prepare(*args, **kwargs):
        projects = await original_prepare(*args, **kwargs)
        if prepared_scope == "missing":
            return []
        current = projects[0]
        foreign = authority.ApprovedProject(
            id=str(uuid4()),
            name="Foreign project",
            roles=current.roles,
            can_write=current.can_write,
            conn=current.conn,
            owns_connection=False,
        )
        return [foreign] if prepared_scope == "foreign" else [current, foreign]

    monkeypatch.setattr(authority, "prepare_project_authority", prepare)
    with pytest.raises(authority.McpAuthorityError):
        await approve(owner)
    assert owner.created == []
    assert await selected(owner) is None
    assert await internal_grants(owner) == []


async def test_ambiguous_creation_is_not_retried_and_only_same_owner_orphan_recovery_unblocks_approval(
    owner, monkeypatch
):
    original_create = owner.conn.identity.create_application_credential

    def ambiguous(**values):
        original_create(**values)
        raise TimeoutError("unknown remote outcome after Keystone accepted creation")

    monkeypatch.setattr(owner.conn.identity, "create_application_credential", ambiguous)
    with pytest.raises(authority.McpAuthorityError, match="could not be created"):
        await approve(owner)
    (grant,) = await internal_grants(owner)
    assert grant.status == "revoked" and grant.cleanup_pending
    assert grant.consented_at is not None and grant.orphan_recovery_after is not None
    assert grant.application_credential_id is None and grant.credential_ciphertext is None
    (orphan,) = owner.remote.values()
    assert orphan.name == grant.upstream_credential_name
    assert authority._as_utc(grant.orphan_recovery_after) > datetime.now(UTC)
    with pytest.raises(authority.McpGrantStateError, match="being prepared"):
        await approve(owner)
    assert len(owner.created) == 1
    assert await selected(owner) is None
    user_id, project_id = owner.info["user_id"], owner.info["project_id"]

    async def recover(user=user_id, project=project_id):
        return await authority.recover_stale_pending_orphans(
            owner.factory,
            conn=owner.conn,
            owner_user_id=user,
            owner_project_id=project,
            username=owner.info["username"],
        )

    assert await recover() == 0
    assert owner.deleted == owner.listed == []
    async with owner.factory() as session, session.begin():
        stored = await session.get(McpDelegatedGrant, grant.id)
        stored.orphan_recovery_after = datetime.now(UTC) - timedelta(seconds=1)
    assert await recover(user=str(uuid4())) == 0
    assert await recover(project=str(uuid4())) == 0
    assert owner.deleted == owner.listed == []

    unrelated = original_create(user=user_id, name="afterglow-mcp-unrelated", unrestricted=False)
    foreign_user = SimpleNamespace(id=str(uuid4()), name=orphan.name, user_id=str(uuid4()), project_id=project_id)
    foreign_project = SimpleNamespace(id=str(uuid4()), name=orphan.name, user_id=user_id, project_id=str(uuid4()))
    owner.remote[foreign_user.id] = foreign_user
    owner.remote[foreign_project.id] = foreign_project
    assert await recover() == 1
    assert owner.deleted == [(user_id, project_id, orphan.id)]
    assert owner.listed and all(scope == (user_id, project_id) for scope in owner.listed)
    assert set(owner.remote) == {unrelated.id, foreign_user.id, foreign_project.id}
    assert await selected(owner) is None
    assert await recover() == 0
    async with owner.factory() as session:
        stored = await session.get(McpDelegatedGrant, grant.id)
        assert stored.status == "revoked" and not stored.cleanup_pending
        assert stored.application_credential_id is None and stored.credential_ciphertext is None
        assert stored.orphan_recovery_after is None and stored.orphan_recovery_nonce is None
    monkeypatch.setattr(owner.conn.identity, "create_application_credential", original_create)
    current = await approve(owner)
    assert current.grant_id != grant.id
    assert len(owner.created) == 3  # Failed creation, unrelated credential, explicit reapproval.
    assert (await lumen.resolve_lumen_principal(current)).scopes == frozenset({"mcp:read"})
    assert {unrelated.id, foreign_user.id, foreign_project.id} <= set(owner.remote)


@pytest.mark.parametrize("initial_level,next_level", [("read", "manage"), ("manage", "read")])
async def test_access_change_requires_new_explicit_approval_and_fences_previous_snapshot(
    owner, initial_level, next_level
):
    old = await approve(owner, initial_level)
    assert await selected(owner) == old
    assert len(owner.created) == 1
    current = await approve(owner, next_level)
    assert current.grant_id != old.grant_id
    assert current.selection_generation > old.selection_generation
    assert (await lumen.resolve_lumen_principal(current)).can_write is (next_level == "manage")
    assert len(owner.created) == 2
    assert await approve(owner, next_level) == current
    assert len(owner.created) == 2
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)


async def test_logical_project_override_refuses_approval_before_preparation(owner):
    owner.info["connection_project_id"] = str(uuid4())
    with pytest.raises(authority.McpAuthorityError, match="exact project scope"):
        await approve(owner)
    assert owner.prepared == owner.created == []
    assert await selected(owner) is None
    assert await internal_grants(owner) == []


async def test_manual_clear_without_previous_selection_cancels_pending_activation(owner, monkeypatch):
    started, finish = pause_creation(owner, monkeypatch)
    preparing = asyncio.create_task(approve(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        before = await generation(owner)
        cleared_generation = await authority.set_lumen_selection(
            owner.factory,
            owner_user_id=owner.info["user_id"],
            owner_project_id=owner.info["project_id"],
            username=owner.info["username"],
            grant_id=None,
        )
        assert cleared_generation > before
        assert await selected(owner) is None
        (pending,) = await internal_grants(owner)
        assert pending.status == "pending", "the generation fence alone must cancel activation"
    finally:
        finish.set()
        with pytest.raises(authority.McpGrantStateError, match="changed before activation"):
            await preparing
    assert await selected(owner) is None
    (grant,) = await internal_grants(owner)
    assert grant.status == "revoked" and not grant.cleanup_pending
    assert grant.application_credential_id is None and grant.credential_ciphertext is None
    assert len(owner.created) == len(owner.deleted) == 1
    assert owner.remote == {}


async def test_selected_read_reapproval_conflicts_while_manage_approval_is_pending(owner, monkeypatch):
    old = await approve(owner, "read")
    started, finish = pause_creation(owner, monkeypatch)
    preparing = asyncio.create_task(approve(owner, "manage"))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        with pytest.raises(authority.McpGrantStateError, match="being prepared"):
            await approve(owner, "read")
    finally:
        finish.set()
        current = await preparing
    assert current.grant_id != old.grant_id
    assert (await lumen.resolve_lumen_principal(current)).can_write
    assert len(owner.created) == 2
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)


@pytest.mark.parametrize("later_action", ["disable", "clear", "personal_selection"])
async def test_later_selection_action_during_role_preparation_cancels_approval(owner, monkeypatch, later_action):
    started, finish = asyncio.Event(), asyncio.Event()
    original_prepare = authority.prepare_project_authority

    async def delayed_prepare(*args, **kwargs):
        started.set()
        await finish.wait()
        return await original_prepare(*args, **kwargs)

    monkeypatch.setattr(authority, "prepare_project_authority", delayed_prepare)
    preparing = asyncio.create_task(approve(owner))
    manual_id = None
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        before = await generation(owner)
        if later_action == "disable":
            await defaults.disable_lumen_grant(token_info=owner.info)
        elif later_action == "clear":
            await authority.set_lumen_selection(
                owner.factory,
                owner_user_id=owner.info["user_id"],
                owner_project_id=owner.info["project_id"],
                username=owner.info["username"],
                grant_id=None,
            )
        else:
            manual_id = await personal_selection(owner)
        assert await generation(owner) > before
    finally:
        finish.set()
        with pytest.raises(authority.McpGrantStateError, match="changed before activation"):
            await preparing
    assert await internal_grants(owner) == []
    assert owner.created == owner.deleted == []
    current = await selected(owner)
    if manual_id is None:
        assert current is None
    else:
        assert current.grant_id == manual_id
        assert (await lumen.resolve_lumen_principal(current)).can_write
