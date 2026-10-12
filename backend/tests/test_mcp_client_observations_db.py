"""Durable observations with the real owner/grant fences and installed MCP SDK."""

from __future__ import annotations

import asyncio
import hashlib
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.models.mcp_authority import McpDelegatedGrant, McpOwnerLock, McpPersonalToken
from app.services.mcp_control_plane import authentication, authority, clients, transport
from app.services.mcp_control_plane.authentication import McpAuthenticationError, McpPrincipal
from app.services.mcp_control_plane.crypto import encrypt_application_credential
from tests.test_mcp_tool_call_cache import running_mcp as _running_mcp

running_mcp = _running_mcp
pytestmark = [pytest.mark.db, pytest.mark.asyncio]


@pytest.fixture(scope="module")
def db_tables():
    url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")
    tables = [table for table in Base.metadata.sorted_tables if table.name.startswith("mcp_")]

    async def schema(create):
        engine = create_async_engine(url)
        try:
            async with engine.begin() as conn:
                operation = Base.metadata.create_all if create else Base.metadata.drop_all
                await conn.run_sync(lambda sync: operation(sync, tables=tables))
        finally:
            await engine.dispose()

    asyncio.run(schema(True))
    yield url
    asyncio.run(schema(False))


@pytest.fixture
async def owner(db_tables, monkeypatch):
    engine = create_async_engine(db_tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(clients, "get_session_factory", lambda: factory)
    monkeypatch.setattr(authentication, "get_session_factory", lambda: factory)
    user, anchor, target, grant_id = (str(uuid4()) for _ in range(4))
    raw_token = "mcp-afgl-" + uuid4().hex + uuid4().hex
    async with factory() as session, session.begin():
        session.add(McpOwnerLock(owner_user_id=user, owner_project_id=anchor))
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id=user,
                owner_project_id=anchor,
                upstream_credential_name=f"observation-{grant_id}",
                display_name="Observed grant",
                source="personal_token",
                access_level="read",
                project_scope="selected",
                status="active",
                approved_projects=[
                    {"id": project, "name": project, "roles": ["reader"], "can_write": False}
                    for project in (anchor, target)
                ],
                application_credential_id=str(uuid4()),
                credential_epoch=1,
                credential_ciphertext=encrypt_application_credential(
                    "synthetic-keystone-secret", grant_id=grant_id, owner_user_id=user, owner_project_id=anchor
                ),
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await session.flush()
        session.add(
            McpPersonalToken(
                grant_id=grant_id, visible_prefix="synthetic", token_hash=hashlib.sha256(raw_token.encode()).hexdigest()
            )
        )
    principal = McpPrincipal(
        grant_id=grant_id,
        user_id=user,
        project_id=target,
        owner_project_id=anchor,
        credential_epoch=1,
        source="personal_token",
        scopes=frozenset({"mcp:read"}),
    )
    try:
        yield SimpleNamespace(factory=factory, principal=principal, raw_token=raw_token)
    finally:
        await engine.dispose()


async def _stored(owner):
    async with owner.factory() as session:
        grant = await session.get(McpDelegatedGrant, owner.principal.grant_id)
        return clients.public_client_observations(grant.client_observations)


async def test_store_is_durable_multiclient_bounded_and_uses_owner_anchor(owner):
    assert await _stored(owner) == []
    for index in range(12):
        await clients.record_client_observation(
            owner.principal,
            clients.client_observation({"name": f"client-{index}", "version": "1"}, "Chrome/130.0 (Windows)"),
        )
    records = await _stored(owner)
    assert len(records) == 10
    assert [item["client_name"] for item in records] == [f"client-{index}" for index in range(2, 12)]
    first = records[0]["first_seen_at"]
    await clients.record_client_observation(
        owner.principal, clients.client_observation({"name": "client-2", "version": "1"}, "Chrome/130.0 (Windows)")
    )
    records = await _stored(owner)
    assert len(records) == 10 and records[-1]["client_name"] == "client-2"
    assert records[-1]["first_seen_at"] == first
    assert records[-1]["last_seen_at"] >= first
    async with owner.factory() as session:
        assert (
            await session.get(
                McpOwnerLock, {"owner_user_id": owner.principal.user_id, "owner_project_id": owner.principal.project_id}
            )
            is None
        )


@pytest.mark.parametrize("invalidated", ["epoch", "grant", "expiry", "token", "owner", "anchor"])
async def test_current_authority_is_revalidated_before_observation_commit(owner, invalidated):
    principal = owner.principal
    evidence = clients.client_observation({"name": "Codex", "version": "1"}, None)
    await clients.record_client_observation(principal, evidence)
    before = await _stored(owner)
    async with owner.factory() as session, session.begin():
        await authority.lock_owner(
            session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id
        )
        grant = await session.get(McpDelegatedGrant, principal.grant_id, with_for_update=True)
        if invalidated == "epoch":
            grant.credential_epoch += 1
        elif invalidated == "grant":
            grant.status = "revoked"
        elif invalidated == "expiry":
            grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        elif invalidated == "token":
            token = await session.scalar(
                select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id).with_for_update()
            )
            token.revoked_at = datetime.now(UTC)
        elif invalidated == "owner":
            principal = replace(principal, user_id=str(uuid4()))
        else:
            principal = replace(principal, owner_project_id=str(uuid4()))
    with pytest.raises(McpAuthenticationError):
        await clients.record_client_observation(
            principal, clients.client_observation({"name": "Cursor", "version": "1"}, None)
        )
    assert await _stored(owner) == before


async def test_raced_revocation_wins_over_captured_initialize_principal(owner, monkeypatch):
    entered = asyncio.Event()
    original_lock = authentication.lock_principal_grant

    async def waiting_lock(session, principal):
        entered.set()
        return await original_lock(session, principal)

    monkeypatch.setattr(authentication, "lock_principal_grant", waiting_lock)
    principal = owner.principal
    async with owner.factory() as session, session.begin():
        await authority.lock_owner(
            session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id
        )
        grant = await session.get(McpDelegatedGrant, principal.grant_id, with_for_update=True)
        pending = asyncio.create_task(
            clients.record_client_observation(
                principal, clients.client_observation({"name": "Codex", "version": "1"}, None)
            )
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        grant.status = "revoked"
        grant.credential_epoch += 1
    with pytest.raises(McpAuthenticationError):
        await asyncio.wait_for(pending, timeout=3)
    assert await _stored(owner) == []


async def test_real_sdk_and_real_bearer_initialize_store_then_reject_revoked_key(owner, running_mcp, monkeypatch):
    params = {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "Codex", "version": "1.2"}}
    headers = {"Authorization": f"Bearer {owner.raw_token}", "Accept": "application/json, text/event-stream"}
    async with running_mcp() as client:
        monkeypatch.setattr(transport, "verify_mcp_bearer", authentication.verify_mcp_bearer)
        response = await client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
        )
        assert response.status_code == 200, response.text
        assert response.json()["result"]["serverInfo"]["name"] == "afterglow-consumer-mcp"
        records = await _stored(owner)
        assert len(records) == 1 and records[0]["client_name"] == "Codex"
        principal = owner.principal
        async with owner.factory() as session, session.begin():
            await authority.lock_owner(
                session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id
            )
            grant = await session.get(McpDelegatedGrant, principal.grant_id, with_for_update=True)
            grant.status = "revoked"
            grant.credential_epoch += 1
        rejected = await client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "initialize",
                "params": {**params, "clientInfo": {"name": "Cursor", "version": "1"}},
            },
        )
        assert rejected.status_code == 401
        assert await _stored(owner) == records
