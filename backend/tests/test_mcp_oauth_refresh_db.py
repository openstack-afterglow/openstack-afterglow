"""Public refresh requests against the real MariaDB authority and token endpoint."""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import mcp as mcp_api
from app.database import Base
from app.models.activity import ActivityLog
from app.models.mcp_authority import (
    McpDelegatedGrant,
    McpOAuthAuthorizationRequest,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpOwnerLock,
)
from app.services.mcp_control_plane.oauth import hash_oauth_value, oauth_urls, pkce_s256

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_TABLES = [
    model.__table__
    for model in (
        McpOwnerLock,
        McpDelegatedGrant,
        McpOAuthAuthorizationRequest,
        McpOAuthCode,
        McpOAuthTokenFamily,
        McpOAuthToken,
        ActivityLog,
    )
]
_URLS = oauth_urls("", public_mcp_url="https://cloud.example.test/mcp", production=True)


@pytest.fixture(scope="module")
def db_tables():
    database_url = os.environ.get("AFTERGLOW_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("AFTERGLOW_TEST_DATABASE_URL is required")

    async def schema(create):
        engine = create_async_engine(database_url)
        try:
            async with engine.begin() as connection:
                operation = Base.metadata.create_all if create else Base.metadata.drop_all
                await connection.run_sync(lambda sync: operation(sync, tables=_TABLES))
        finally:
            await engine.dispose()

    asyncio.run(schema(True))
    yield database_url
    asyncio.run(schema(False))


@pytest.fixture
async def issued_refresh(db_tables, monkeypatch):
    from app.main import app

    engine = create_async_engine(db_tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(mcp_api, "_require_enabled", lambda: None)
    monkeypatch.setattr(mcp_api, "_session_factory", lambda: factory)
    monkeypatch.setattr(mcp_api, "_urls", lambda: _URLS)
    now = datetime.now(UTC)
    grant_id = str(uuid4())
    client_id = "issuing-client"
    verifier = "a" * 43
    code = "code-" + grant_id
    redirect_uri = "http://127.0.0.1:8100/callback"
    async with factory() as session, session.begin():
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id="owner-" + grant_id,
                owner_project_id="project",
                upstream_credential_name="refresh-test-" + grant_id,
                display_name="Refresh test",
                source="oauth",
                access_level="read",
                status="active",
                expires_at=now + timedelta(days=30),
            )
        )
        await session.flush()
        session.add(
            McpOAuthCode(
                code_hash=hash_oauth_value(code),
                grant_id=grant_id,
                client_id=client_id,
                redirect_uri=redirect_uri,
                resource=_URLS.resource,
                scopes=["mcp:read"],
                code_challenge=pkce_s256(verifier),
                expires_at=now + timedelta(minutes=5),
            )
        )
        session.add(
            McpOAuthAuthorizationRequest(
                ticket_hash=hash_oauth_value("ticket-" + grant_id),
                client_id=client_id,
                client_fingerprint="a" * 64,
                redirect_uri=redirect_uri,
                resource=_URLS.resource,
                scopes=["mcp:read"],
                code_challenge=pkce_s256(verifier),
                grant_id=grant_id,
                status="approved",
                expires_at=now + timedelta(minutes=10),
                used_at=now,
            )
        )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            exchange = await client.post(
                "/api/v1/mcp/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "resource": _URLS.resource,
                    "code_verifier": verifier,
                },
            )
            assert exchange.status_code == 200
            yield SimpleNamespace(
                client=client,
                factory=factory,
                grant_id=grant_id,
                client_id=client_id,
                refresh_token=exchange.json()["refresh_token"],
            )
    finally:
        await engine.dispose()


async def refresh(issued, *, client_id=None, token=None):
    form = {
        "grant_type": "refresh_token",
        "refresh_token": token or issued.refresh_token,
        "resource": _URLS.resource,
    }
    if client_id is not None:
        form["client_id"] = client_id
    return await issued.client.post("/api/v1/mcp/oauth/token", data=form)


async def security_state(issued):
    async with issued.factory() as session:
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant.id))
        tokens = (await session.scalars(select(McpOAuthToken).where(McpOAuthToken.family_id == family.id))).all()
        return (
            grant.status,
            grant.credential_epoch,
            grant.revoked_at,
            family.generation,
            family.revoked_at,
            sorted((token.id, token.rotated_at, token.revoked_at) for token in tokens),
        )


@pytest.mark.parametrize("client_id", ["another-client", ""])
async def test_mismatched_refresh_client_cannot_rotate_or_revoke(issued_refresh, client_id):
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=client_id)
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_grant"
    assert await security_state(issued_refresh) == before

    accepted = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert accepted.status_code == 200
    assert accepted.json()["refresh_token"] != issued_refresh.refresh_token
    assert accepted.json()["scope"] == "mcp:read"


async def test_refresh_omitting_client_id_remains_supported(issued_refresh):
    accepted = await refresh(issued_refresh)
    assert accepted.status_code == 200
    assert accepted.json()["refresh_token"] != issued_refresh.refresh_token
    assert accepted.json()["scope"] == "mcp:read"


async def test_refresh_binding_survives_code_expiry_and_ticket_cleanup(issued_refresh):
    async with issued_refresh.factory() as session, session.begin():
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == issued_refresh.grant_id))
        code.expires_at = datetime.now(UTC) - timedelta(days=2)
        ticket = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(McpOAuthAuthorizationRequest.grant_id == issued_refresh.grant_id)
        )
        await session.delete(ticket)
    accepted = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert accepted.status_code == 200
    assert accepted.json()["refresh_token"] != issued_refresh.refresh_token


@pytest.mark.parametrize("binding", ["missing", "ambiguous"])
async def test_supplied_client_fails_closed_without_unique_issuing_code(issued_refresh, binding):
    async with issued_refresh.factory() as session, session.begin():
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == issued_refresh.grant_id))
        if binding == "missing":
            await session.delete(code)
        else:
            session.add(
                McpOAuthCode(
                    code_hash=hash_oauth_value("extra-" + issued_refresh.grant_id),
                    grant_id=code.grant_id,
                    client_id=code.client_id,
                    redirect_uri=code.redirect_uri,
                    resource=code.resource,
                    scopes=code.scopes,
                    code_challenge=code.code_challenge,
                    expires_at=code.expires_at,
                    used_at=code.used_at,
                )
            )
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_grant"
    assert await security_state(issued_refresh) == before


async def test_correct_client_replay_still_revokes_but_other_client_does_not(issued_refresh):
    rotated = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rotated.status_code == 200
    before = await security_state(issued_refresh)
    wrong_client = await refresh(issued_refresh, client_id="another-client")
    assert wrong_client.status_code == 400
    assert await security_state(issued_refresh) == before

    replay = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert replay.status_code == 400
    state = await security_state(issued_refresh)
    assert state[0] == "revoked"
    assert state[1] == before[1] + 1
    assert state[2] is not None
    assert state[4] is not None
    assert all(revoked_at is not None for _, _, revoked_at in state[5])
    denied = await refresh(
        issued_refresh,
        client_id=issued_refresh.client_id,
        token=rotated.json()["refresh_token"],
    )
    assert denied.status_code == 400
