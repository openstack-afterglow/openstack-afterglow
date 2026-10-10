"""Default Lumen authority lifecycle against a disposable MariaDB schema."""

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
from app.models.mcp_authority import McpDelegatedGrant, McpPersonalToken
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
    created = []

    class Identity:
        def create_application_credential(self, **values):
            created.append(values)
            return SimpleNamespace(id=str(uuid4()), secret="synthetic-keystone-secret")

    conn = SimpleNamespace(_afterglow_user_id=user_id, _afterglow_project_id=project_id, identity=Identity())
    info = {"user_id": user_id, "project_id": project_id, "username": "default-owner", "roles": ["member"]}
    try:
        yield SimpleNamespace(factory=factory, conn=conn, info=info, created=created)
    finally:
        await engine.dispose()


async def ensure(owner):
    await defaults.ensure_default_lumen_grant(conn=owner.conn, token_info=owner.info)
    return await lumen.selected_lumen_snapshot(user_id=owner.info["user_id"], project_id=owner.info["project_id"])


async def test_first_use_creates_read_authority_once_without_personal_bearer(owner):
    first = await ensure(owner)
    second = await ensure(owner)
    assert first == second
    principal = await lumen.resolve_lumen_principal(first)
    assert principal.scopes == frozenset({"mcp:read"})
    assert all(entry.effect == "read" for entry in registry.enabled_entries(principal))
    assert len(owner.created) == 1
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, first.grant_id)
        assert grant.source == "lumen" and grant.status == "active"
        assert (
            await session.scalar(
                select(func.count()).select_from(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id)
            )
            == 0
        )


async def test_default_authority_is_separate_for_user_and_project(owner):
    first = await ensure(owner)
    owner.info = {**owner.info, "project_id": str(uuid4())}
    owner.conn._afterglow_project_id = owner.info["project_id"]
    second = await ensure(owner)
    owner.info = {**owner.info, "user_id": str(uuid4())}
    owner.conn._afterglow_user_id = owner.info["user_id"]
    third = await ensure(owner)
    assert first.grant_id != second.grant_id != third.grant_id
    assert (first.user_id, first.project_id) != (second.user_id, second.project_id)
    assert (second.user_id, second.project_id) != (third.user_id, third.project_id)
    assert (await lumen.resolve_lumen_principal(first)).project_id == first.project_id


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
                application_credential_id="manual-credential",
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


async def test_default_setup_preserves_explicit_manage_and_fences_replaced_snapshot(owner):
    original = await ensure(owner)
    selected_id = await personal_selection(owner)
    current = await ensure(owner)
    assert current.grant_id == selected_id
    assert (await lumen.resolve_lumen_principal(current)).can_write
    assert len(owner.created) == 1
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(original)


async def test_pending_creation_cannot_duplicate_or_overwrite_manual_choice(owner):
    started, finish = threading.Event(), threading.Event()
    original_create = owner.conn.identity.create_application_credential

    def delayed(**values):
        started.set()
        if not finish.wait(10):
            raise TimeoutError("fixture did not release creation")
        return original_create(**values)

    owner.conn.identity.create_application_credential = delayed
    preparing = asyncio.create_task(ensure(owner))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        with pytest.raises(authority.McpGrantStateError, match="being prepared"):
            await ensure(owner)
        manual_id = await personal_selection(owner)
    finally:
        finish.set()
    selected = await preparing
    assert selected.grant_id == manual_id
    assert len(owner.created) == 1
    async with owner.factory() as session:
        internal = await session.scalar(
            select(McpDelegatedGrant).where(
                McpDelegatedGrant.owner_user_id == owner.info["user_id"], McpDelegatedGrant.source == "lumen"
            )
        )
        assert internal.status == "active" and internal.access_level == "read"


async def test_ambiguous_creation_stays_nondispatchable_and_is_not_retried(owner):
    calls = []

    def ambiguous(**values):
        calls.append(values)
        raise TimeoutError("unknown remote outcome")

    owner.conn.identity.create_application_credential = ambiguous
    with pytest.raises(authority.McpAuthorityError, match="could not be created"):
        await ensure(owner)
    with pytest.raises(authority.McpGrantStateError, match="being prepared"):
        await ensure(owner)
    assert len(calls) == 1
    assert (
        await lumen.selected_lumen_snapshot(user_id=owner.info["user_id"], project_id=owner.info["project_id"]) is None
    )
    async with owner.factory() as session:
        grant = await session.scalar(
            select(McpDelegatedGrant).where(McpDelegatedGrant.owner_user_id == owner.info["user_id"])
        )
        assert grant.status == "revoked" and grant.cleanup_pending
        assert grant.orphan_recovery_after is not None


async def test_expired_default_is_replaced_and_old_run_is_fenced(owner):
    old = await ensure(owner)
    async with owner.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, old.grant_id)
        grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    current = await ensure(owner)
    assert current.grant_id != old.grant_id
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(old)
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, old.grant_id)
        assert grant.status == "expired" and grant.cleanup_pending


async def test_logical_admin_override_cannot_issue_a_foreign_project_default(owner):
    owner.info["connection_project_id"] = "actual-admin-token-project"
    with pytest.raises(authority.McpAuthorityError, match="exact project scope"):
        await ensure(owner)
    assert owner.created == []
    async with owner.factory() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(McpDelegatedGrant)
                .where(McpDelegatedGrant.owner_user_id == owner.info["user_id"])
            )
            == 0
        )
