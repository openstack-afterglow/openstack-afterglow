"""Public refresh requests against the real MariaDB authority and token endpoint."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from urllib.parse import urlsplit
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
    McpLumenSelection,
    McpOAuthAuthorizationRequest,
    McpOAuthClient,
    McpOAuthCode,
    McpOAuthToken,
    McpOAuthTokenFamily,
    McpOwnerLock,
    McpPersonalToken,
    McpProjectCredential,
    McpToolInvocation,
)
from app.services.keystone import get_openstack_connection
from app.services.mcp_control_plane.oauth import hash_oauth_value, oauth_urls, pkce_s256

pytestmark = [pytest.mark.db, pytest.mark.asyncio]

_TABLES = [
    model.__table__
    for model in (
        McpOwnerLock,
        McpDelegatedGrant,
        McpProjectCredential,
        McpOAuthAuthorizationRequest,
        McpOAuthCode,
        McpOAuthClient,
        McpOAuthTokenFamily,
        McpOAuthToken,
        McpPersonalToken,
        McpLumenSelection,
        McpToolInvocation,
        ActivityLog,
    )
]
_URLS = oauth_urls("", public_mcp_url="https://cloud.example.test/mcp", production=True)


def _oauth_reasons(caplog) -> list[str]:
    return [record.diagnostic_reason for record in caplog.records if record.name == "app.api.mcp"]


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
                access_token=exchange.json()["access_token"],
            )
    finally:
        await engine.dispose()


async def refresh(issued, *, client_id=None, token=None, scope=None, resource=None):
    form = {
        "grant_type": "refresh_token",
        "refresh_token": token or issued.refresh_token,
        "resource": _URLS.resource if resource is None else resource,
    }
    if client_id is not None:
        form["client_id"] = client_id
    if scope is not None:
        form["scope"] = scope
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


@pytest.mark.parametrize("client_id", [None, "another-client", ""])
async def test_mismatched_refresh_client_cannot_rotate_or_revoke(issued_refresh, client_id, caplog):
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=client_id)
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_grant"
    assert await security_state(issued_refresh) == before
    assert "client_invalid" in _oauth_reasons(caplog)
    assert issued_refresh.refresh_token not in caplog.text
    assert rejected.json()["error_description"] == "OAuth grant is invalid"

    accepted = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert accepted.status_code == 200
    assert accepted.json()["refresh_token"] != issued_refresh.refresh_token
    assert accepted.json()["scope"] == "mcp:read"


async def test_refresh_omitting_client_id_cannot_rotate_or_revoke(issued_refresh):
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh)
    assert rejected.status_code == 400
    assert rejected.json()["error"] == "invalid_grant"
    assert await security_state(issued_refresh) == before


async def mutation_fixture(issued, monkeypatch, *, status="dispatch_authorized", expired=True, key="original-key"):
    from app.services.mcp_control_plane import ledger, operations
    from app.services.mcp_control_plane.authentication import McpPrincipal

    monkeypatch.setattr(ledger, "get_session_factory", lambda: issued.factory)
    monkeypatch.setattr(operations, "get_session_factory", lambda: issued.factory)
    async with issued.factory() as session:
        family_id = await session.scalar(
            select(McpOAuthTokenFamily.id).where(McpOAuthTokenFamily.grant_id == issued.grant_id)
        )
    principal = McpPrincipal(
        grant_id=issued.grant_id,
        user_id="owner-" + issued.grant_id,
        project_id="project",
        credential_epoch=1,
        scopes=frozenset(("mcp:read", "mcp:write")),
        source="oauth",
        oauth_family_id=family_id,
    )
    invocation_id = str(uuid4())
    now = datetime.now(UTC)
    async with issued.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        grant.access_level = "manage"
        for issued_token in (
            await session.scalars(select(McpOAuthToken).where(McpOAuthToken.family_id == family_id))
        ).all():
            issued_token.scopes = ["mcp:read", "mcp:write"]
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=issued.grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key=key,
                arguments_hash=ledger.canonical_arguments_hash(
                    ledger.canonical_target_arguments(principal, {"action": "reboot", "server_id": "server-a"})
                ),
                registry_version="test",
                status=status,
                lease_expires_at=now + timedelta(minutes=-1 if expired else 5),
                created_at=now,
            )
        )
    return principal, invocation_id


async def test_operation_poll_reconciles_stale_lease_and_preserves_invocation(issued_refresh, monkeypatch):
    from app.services.mcp_control_plane import operations

    principal, invocation_id = await mutation_fixture(issued_refresh, monkeypatch)
    view = await operations.get_operation(principal, invocation_id=invocation_id)
    assert view.status == "unknown"
    async with issued_refresh.factory() as session:
        row = await session.get(McpToolInvocation, invocation_id)
        assert row.status == "unknown"
        assert row.lease_expires_at is None
        assert row.idempotency_key == "original-key"
    assert (await operations.get_operation(principal, invocation_id=invocation_id)).status == "unknown"


async def test_foreign_grant_cannot_poll_or_change_stale_invocation(issued_refresh, monkeypatch):
    from dataclasses import replace

    from app.services.mcp_control_plane import operations

    principal, invocation_id = await mutation_fixture(issued_refresh, monkeypatch)
    with pytest.raises(operations.McpOperationError):
        await operations.get_operation(replace(principal, grant_id=str(uuid4())), invocation_id=invocation_id)
    async with issued_refresh.factory() as session:
        assert (await session.get(McpToolInvocation, invocation_id)).status == "dispatch_authorized"


@pytest.mark.parametrize("status", ["claimed", "dispatch_authorized", "unknown"])
async def test_new_key_cannot_duplicate_unresolved_mutation(issued_refresh, monkeypatch, status):
    from app.services.mcp_control_plane import ledger

    principal, invocation_id = await mutation_fixture(issued_refresh, monkeypatch, status=status)
    with pytest.raises(ledger.McpInvocationError, match="unresolved outcome"):
        await ledger.claim_mutation(
            principal,
            entry=SimpleNamespace(effect="external_mutation", name="afterglow_vm_action"),
            arguments={"action": "reboot", "server_id": "server-a"},
            idempotency_key="fresh-retry-key",
        )
    async with issued_refresh.factory() as session:
        rows = (
            await session.scalars(select(McpToolInvocation).where(McpToolInvocation.grant_id == principal.grant_id))
        ).all()
        assert [row.id for row in rows] == [invocation_id]


async def test_cleanup_reconciles_only_expired_mutation_leases(issued_refresh, monkeypatch):
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    _, expired_id = await mutation_fixture(issued_refresh, monkeypatch)
    _, active_id = await mutation_fixture(
        issued_refresh, monkeypatch, expired=False, status="claimed", key="active-key"
    )
    counts = await sweep_delegated_authority(issued_refresh.factory)
    assert counts.expired_mutation_leases >= 1
    async with issued_refresh.factory() as session:
        assert (await session.get(McpToolInvocation, expired_id)).status == "unknown"
        assert (await session.get(McpToolInvocation, active_id)).status == "claimed"


async def test_concurrent_new_keys_have_one_claim_winner(issued_refresh, monkeypatch):
    from app.services.mcp_control_plane import ledger

    principal, invocation_id = await mutation_fixture(issued_refresh, monkeypatch, status="succeeded")
    entry = SimpleNamespace(effect="external_mutation", name="afterglow_vm_action")
    claims = await asyncio.gather(
        *(
            ledger.claim_mutation(
                principal, entry=entry, arguments={"action": "stop", "server_id": "another-server"}, idempotency_key=key
            )
            for key in ("concurrent-key-one", "concurrent-key-two")
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(value, ledger.MutationClaim) for value in claims) == 1
    assert sum(isinstance(value, ledger.McpInvocationError) for value in claims) == 1
    async with issued_refresh.factory() as session:
        rows = (
            await session.scalars(
                select(McpToolInvocation).where(
                    McpToolInvocation.grant_id == principal.grant_id, McpToolInvocation.id != invocation_id
                )
            )
        ).all()
        assert len(rows) == 1
        assert rows[0].status == "claimed"


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
async def test_supplied_client_fails_closed_without_unique_issuing_code(issued_refresh, binding, caplog):
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
    assert "authority_invariant" in _oauth_reasons(caplog)
    assert rejected.json()["error_description"] == "OAuth grant is invalid"
    assert issued_refresh.refresh_token not in caplog.text


async def test_correct_client_replay_still_revokes_but_other_client_does_not(issued_refresh, caplog):
    rotated = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rotated.status_code == 200
    before = await security_state(issued_refresh)
    wrong_client = await refresh(issued_refresh, client_id="another-client")
    assert wrong_client.status_code == 400
    assert await security_state(issued_refresh) == before

    replay = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert replay.status_code == 400
    assert "credential_reused" in _oauth_reasons(caplog)
    assert replay.json()["error_description"] == "OAuth grant is invalid"
    assert issued_refresh.refresh_token not in caplog.text
    state = await security_state(issued_refresh)
    assert state[0] == "revoked"
    assert state[1] == before[1] + 1
    assert state[2] is not None
    assert state[4] is not None
    # Family revocation is authoritative; no unbounded token-row rewrite is required.
    assert state[5] == before[5]
    denied = await refresh(
        issued_refresh,
        client_id=issued_refresh.client_id,
        token=rotated.json()["refresh_token"],
    )
    assert denied.status_code == 400


async def test_refresh_attenuation_cannot_regain_grant_write_scope(issued_refresh):
    async with issued_refresh.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued_refresh.grant_id)
        grant.access_level = "manage"
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant.id))
        for token in (await session.scalars(select(McpOAuthToken).where(McpOAuthToken.family_id == family.id))).all():
            token.scopes = ["mcp:read", "mcp:write"]

    narrowed = await refresh(issued_refresh, client_id=issued_refresh.client_id, scope="mcp:read")
    assert narrowed.status_code == 200
    assert narrowed.json()["scope"] == "mcp:read"
    token = narrowed.json()["refresh_token"]
    before = await security_state(issued_refresh)
    expanded = await refresh(
        issued_refresh, client_id=issued_refresh.client_id, token=token, scope="mcp:read mcp:write"
    )
    assert expanded.status_code == 400
    assert await security_state(issued_refresh) == before
    inherited = await refresh(issued_refresh, client_id=issued_refresh.client_id, token=token)
    assert inherited.status_code == 200
    assert inherited.json()["scope"] == "mcp:read"


async def test_refresh_wrong_resource_cannot_rotate_or_revoke(issued_refresh, caplog):
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id, resource=_URLS.resource + "/other")
    assert rejected.status_code == 400
    assert await security_state(issued_refresh) == before
    assert "resource_mismatch" in _oauth_reasons(caplog)
    assert rejected.json()["error_description"] == "OAuth grant is invalid"
    assert issued_refresh.refresh_token not in caplog.text


@pytest.mark.parametrize(
    ("token", "reason"), [("unknown-synthetic-credential", "credential_unknown"), ("", "invalid_shape")]
)
async def test_unknown_refresh_diagnostic_never_mutates_other_authority(issued_refresh, caplog, token, reason):
    before = await security_state(issued_refresh)
    rejected = await issued_refresh.client.post(
        "/api/v1/mcp/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": token,
            "client_id": issued_refresh.client_id,
            "resource": _URLS.resource,
        },
    )
    assert rejected.status_code == 400
    assert rejected.json() == {"error": "invalid_grant", "error_description": "OAuth grant is invalid"}
    assert reason in _oauth_reasons(caplog)
    assert "unknown-synthetic-credential" not in caplog.text
    assert await security_state(issued_refresh) == before


async def test_expired_refresh_diagnostic_preserves_revocation_and_no_replay(issued_refresh, caplog):
    async with issued_refresh.factory() as session, session.begin():
        token = await session.scalar(
            select(McpOAuthToken).where(McpOAuthToken.token_hash == hash_oauth_value(issued_refresh.refresh_token))
        )
        token.expires_at = datetime.now(UTC) - timedelta(seconds=5)
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rejected.status_code == 400
    assert rejected.json() == {"error": "invalid_grant", "error_description": "OAuth grant is invalid"}
    assert "credential_expired" in _oauth_reasons(caplog)
    assert issued_refresh.refresh_token not in caplog.text
    after = await security_state(issued_refresh)
    assert after[0] == "revoked" and after[1] == before[1] + 1
    assert after[4] is not None
    assert after[5] == before[5]
    assert (await refresh(issued_refresh, client_id=issued_refresh.client_id)).status_code == 400


@pytest.mark.parametrize(
    ("verifier", "reason"),
    [("short", "invalid_shape"), ("é" * 43, "invalid_shape"), ("z" * 43, "authentication_failed")],
)
async def test_code_authentication_diagnostic_does_not_consume_or_replay(oauth_consent, caplog, verifier, reason):
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    consent = oauth_consent
    result = await approve_consent_ticket(
        consent.factory,
        ticket=consent.ticket,
        owner_user_id=consent.owner,
        owner_project_id="A",
        username="owner",
        roles=["member"],
        conn=consent.conn,
        access_level="read",
    )
    form = {
        "grant_type": "authorization_code",
        "code": result.code,
        "client_id": consent.client_id,
        "redirect_uri": result.redirect_uri,
        "resource": _URLS.resource,
        "code_verifier": verifier,
    }
    rejected = await consent.client.post("/api/v1/mcp/oauth/token", data=form)
    assert rejected.status_code == 400
    assert rejected.json() == {"error": "invalid_grant", "error_description": "OAuth grant is invalid"}
    assert reason in _oauth_reasons(caplog)
    assert result.code not in caplog.text
    async with consent.factory() as session:
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.code_hash == hash_oauth_value(result.code)))
        assert code.used_at is None
        assert (
            await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == code.grant_id))
            is None
        )
    accepted = await consent.client.post("/api/v1/mcp/oauth/token", data={**form, "code_verifier": consent.verifier})
    assert accepted.status_code == 200
    replay = await consent.client.post("/api/v1/mcp/oauth/token", data={**form, "code_verifier": consent.verifier})
    assert replay.status_code == 400
    assert "credential_reused" in _oauth_reasons(caplog)


async def test_oauth_revocation_blocks_access_and_refresh(issued_refresh):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token

    revoked = await issued_refresh.client.post("/api/v1/mcp/oauth/revoke", data={"token": issued_refresh.access_token})
    assert revoked.status_code == 200
    async with issued_refresh.factory() as session, session.begin():
        with pytest.raises(McpOAuthAuthorityError, match="invalid"):
            await resolve_oauth_access_token(session, raw_token=issued_refresh.access_token, resource=_URLS.resource)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rejected.status_code == 400


@pytest.mark.parametrize("source", ["personal_token", "oauth"])
@pytest.mark.parametrize("expired", [False, True], ids=["active", "expired"])
@pytest.mark.parametrize("cleanup_fails", [False, True], ids=["cleanup-confirmed", "cleanup-pending"])
@pytest.mark.parametrize("selected_project", ["project", "other-domain-project", ""])
async def test_browser_revocation_removes_access_but_preserves_tombstone(
    issued_refresh, monkeypatch, source, expired, cleanup_fails, selected_project
):
    from app.api.deps import get_os_conn, get_token_info
    from app.api.identity import mcp_access
    from app.main import app
    from app.services.mcp_control_plane import authority
    from app.services.mcp_control_plane.crypto import encrypt_application_credential
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token

    factory = issued_refresh.factory
    now = datetime.now(UTC)
    raw_token = "mcp-afgl-" + uuid4().hex
    async with factory() as session, session.begin():
        oauth_grant = await session.get(McpDelegatedGrant, issued_refresh.grant_id)
        owner = oauth_grant.owner_user_id
        if source == "oauth":
            grant = oauth_grant
        else:
            grant = McpDelegatedGrant(
                id=str(uuid4()),
                owner_user_id=owner,
                owner_project_id="project",
                upstream_credential_name="personal-" + str(uuid4()),
                display_name="Personal test",
                source=source,
                access_level="read",
                status="active",
                expires_at=now + timedelta(days=30),
            )
            session.add(grant)
        grant.application_credential_id = "credential-" + grant.id
        grant.credential_ciphertext = encrypt_application_credential(
            "synthetic-secret", grant_id=grant.id, owner_user_id=owner, owner_project_id="project"
        )
        if expired:
            grant.status = "expired"
            grant.expires_at = now - timedelta(days=1)
            grant.revoked_at = now - timedelta(hours=1)
        await session.flush()
        grant_id, credential_id, epoch = grant.id, grant.application_credential_id, grant.credential_epoch
        if source == "personal_token":
            token = McpPersonalToken(
                id=str(uuid4()),
                grant_id=grant_id,
                visible_prefix=raw_token[:20],
                token_hash=authority._token_hash(raw_token),
            )
            session.add(token)
            session.add(McpLumenSelection(owner_user_id=owner, owner_project_id="project", grant_id=grant_id))
            record_id = token.id
        else:
            record_id = grant_id

    remote = {credential_id}

    class Identity:
        def delete_application_credential(self, user, value, **kwargs):
            assert user == owner
            if cleanup_fails:
                raise RuntimeError("synthetic provider unavailable")
            remote.discard(value)

        def find_application_credential(self, user, value, **kwargs):
            assert user == owner
            return SimpleNamespace(id=value) if value in remote else None

    caller = {"user_id": owner, "project_id": selected_project, "username": "owner"}
    monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: caller)
    monkeypatch.setitem(
        app.dependency_overrides, get_os_conn, lambda: SimpleNamespace(_afterglow_user_id=owner, identity=Identity())
    )
    monkeypatch.setattr(mcp_access, "_session_factory", lambda: factory)
    monkeypatch.setattr(
        mcp_access,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=True,
            frontend_base_url="https://app.example.test",
            public_api_base="https://api.example.test",
            cors_origin_list=(),
        ),
    )
    path = "/api/v1/auth/" + ("mcp-tokens" if source == "personal_token" else "mcp-oauth/grants")
    headers = {"Origin": "https://app.example.test", "Sec-Fetch-Site": "same-site"}
    client = issued_refresh.client
    listed = await client.get(path)
    assert listed.status_code == 200
    assert {record["id"] for record in listed.json()} == {record_id}
    caller["user_id"] = "other-user-" + str(uuid4())
    assert (await client.get(path)).json() == []
    assert (await client.delete(f"{path}/{record_id}", headers=headers)).status_code == 404
    async with factory() as session:
        untouched = await session.get(McpDelegatedGrant, grant_id)
        assert untouched.status == ("expired" if expired else "active")
        assert untouched.credential_epoch == epoch
        assert untouched.application_credential_id == credential_id
    assert remote == {credential_id}
    caller["user_id"] = owner
    revoked = await client.delete(f"{path}/{record_id}", headers=headers)
    assert revoked.status_code == 204
    assert (await client.get(path)).json() == []
    assert (await client.delete(f"{path}/{record_id}", headers=headers)).status_code == 204
    assert (await client.get(path)).json() == []
    async with factory() as session:
        tombstone = await session.get(McpDelegatedGrant, grant_id)
        assert tombstone.status == "revoked"
        assert tombstone.credential_epoch == epoch + 1
        assert tombstone.revoked_at is not None
        assert tombstone.cleanup_pending is cleanup_fails
        assert bool(tombstone.application_credential_id) is cleanup_fails
        assert tombstone.owner_user_id == owner and tombstone.owner_project_id == "project"
        assert tombstone.project_scope == "current" and tombstone.approved_projects is None
        audits = (await session.scalars(select(ActivityLog).where(ActivityLog.resource_id == grant_id))).all()
        assert audits and {audit.project_id for audit in audits} == {"project"}
        assert {audit.user_id for audit in audits} == {owner}
        assert (
            await session.get(McpOwnerLock, {"owner_user_id": owner, "owner_project_id": "other-domain-project"})
            is None
        )
        actions = set(await session.scalars(select(ActivityLog.action).where(ActivityLog.resource_id == grant_id)))
        assert actions == (
            {"mcp_grant.revoke"} if cleanup_fails else {"mcp_grant.revoke", "mcp_grant.cleanup_confirmed"}
        )
        if source == "personal_token":
            assert (await session.get(McpPersonalToken, record_id)).revoked_at is not None
            assert await session.get(McpLumenSelection, {"owner_user_id": owner, "owner_project_id": "project"}) is None
            assert (
                await session.get(McpOwnerLock, {"owner_user_id": owner, "owner_project_id": "project"})
            ).lumen_selection_generation == 1
    async with factory() as session, session.begin():
        if source == "personal_token":
            with pytest.raises(authority.McpGrantNotFoundError):
                await authority.resolve_personal_token(session, raw_token)
        else:
            with pytest.raises(McpOAuthAuthorityError):
                await resolve_oauth_access_token(
                    session, raw_token=issued_refresh.access_token, resource=_URLS.resource
                )
    if source == "oauth":
        assert (await refresh(issued_refresh, client_id=issued_refresh.client_id)).status_code == 400
    assert remote == ({credential_id} if cleanup_fails else set())


@pytest.mark.parametrize("source", ["personal_token", "oauth"])
async def test_browser_access_lists_omit_revocations_without_crossing_owner_scope(issued_refresh, monkeypatch, source):
    from app.api.deps import get_token_info
    from app.api.identity import mcp_access
    from app.main import app
    from app.services.mcp_control_plane.authority import _token_hash

    factory = issued_refresh.factory
    owner = "list-owner-" + str(uuid4())
    expected = set()
    async with factory() as session, session.begin():
        for status, user, project, token_revoked in (
            ("active", owner, "project", False),
            ("expired", owner, "project", False),
            ("revoked", owner, "project", False),
            ("active", "foreign-" + str(uuid4()), "project", False),
            ("active", owner, "foreign-project", False),
            *(([("expired", owner, "project", True)]) if source == "personal_token" else []),
        ):
            grant_id = str(uuid4())
            grant = McpDelegatedGrant(
                id=grant_id,
                owner_user_id=user,
                owner_project_id=project,
                upstream_credential_name="listing-" + grant_id,
                display_name=status,
                source=source,
                approved_projects=[
                    {"id": project, "name": f"Saved {project}", "roles": ["reader"], "can_write": False}
                ],
                access_level="read",
                status=status,
                expires_at=datetime.now(UTC) + timedelta(days=30),
                client_observations=[
                    {
                        "client_name": "claude-code",
                        "client_version": "1.2.3",
                        "product": "Claude Code",
                        "kind": "agent",
                        "identity_source": "client_info",
                        "browser": None,
                        "os": "macOS",
                        "first_seen_at": "2026-10-12T00:00:00+00:00",
                        "last_seen_at": "2026-10-12T01:00:00+00:00",
                        "signature": "private-internal-signature",
                        "user_agent": "private-raw-user-agent",
                        "token_hash": "private-token-hash",
                    }
                ],
            )
            session.add(grant)
            await session.flush()
            record_id = grant_id
            if source == "personal_token":
                record_id = str(uuid4())
                session.add(
                    McpPersonalToken(
                        id=record_id,
                        grant_id=grant_id,
                        visible_prefix="mcp-afgl-test",
                        token_hash=_token_hash(grant_id),
                        revoked_at=datetime.now(UTC) if token_revoked else None,
                    )
                )
            if status != "revoked" and user == owner and not token_revoked:
                expected.add(record_id)
    caller = {"user_id": owner, "project_id": "project", "username": "owner"}
    monkeypatch.setitem(app.dependency_overrides, get_token_info, lambda: caller)
    monkeypatch.setattr(mcp_access, "_session_factory", lambda: factory)
    monkeypatch.setattr(mcp_access, "get_settings", lambda: SimpleNamespace(service_mcp_enabled=True))
    path = "/api/v1/auth/" + ("mcp-tokens" if source == "personal_token" else "mcp-oauth/grants")
    for project, domain in (("project", "domain-a"), ("foreign-project", "domain-b"), ("", "domain-b")):
        caller.update(project_id=project, domain_id=domain)
        response = await issued_refresh.client.get(path)
        assert response.status_code == 200
        assert {record["id"] for record in response.json()} == expected
        assert {record["owner_project_id"] for record in response.json()} == {"project", "foreign-project"}
        for record in response.json():
            assert record["owner_project_name"] == f"Saved {record['owner_project_id']}"
            assert record["project_ids"] == [record["owner_project_id"]]
            assert record["projects"] == [{"id": record["owner_project_id"], "name": record["owner_project_name"]}]
    assert response.status_code == 200
    assert {record["id"] for record in response.json()} == expected
    assert {record["status"] for record in response.json()} == {"active", "expired"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"
    public_fields = {
        "client_name",
        "client_version",
        "product",
        "kind",
        "identity_source",
        "browser",
        "os",
        "first_seen_at",
        "last_seen_at",
    }
    for record in response.json():
        observed = record["client_observations"]
        assert len(observed) == 1
        assert set(observed[0]) == public_fields
        assert observed[0]["client_name"] == "claude-code"
        assert observed[0]["product"] == "Claude Code"
        assert observed[0]["kind"] == "agent"
        assert observed[0]["first_seen_at"] == "2026-10-12T00:00:00Z"
        assert observed[0]["last_seen_at"] == "2026-10-12T01:00:00Z"
    assert "private-" not in response.text


@pytest.fixture
async def oauth_consent(issued_refresh, monkeypatch):
    from app.services import k3s_crypto, keystone, project_service
    from app.services.mcp_control_plane.oauth_authority import (
        create_authorization_ticket,
        load_consent_ticket,
        register_public_client,
    )

    monkeypatch.setattr(k3s_crypto, "get_settings", lambda: SimpleNamespace(k3s_kubeconfig_encryption_key="a" * 64))
    runtime_settings = keystone.get_settings().model_copy(update={"os_auth_url": "https://keystone.example.test/v3"})
    monkeypatch.setattr("app.config.get_settings", lambda: runtime_settings)
    owner = "consent-" + str(uuid4())
    memberships = {"A": ["member"], "B": ["reader"]}
    current_role_overrides = {}

    async def current_roles(project_id, owner_user_id):
        assert owner_user_id == owner
        return current_role_overrides.get(
            project_id,
            [{"id": "role-" + name, "name": name, "inherited_role_ids": []} for name in memberships[project_id]],
        )

    monkeypatch.setattr(project_service, "get_project_delegation_roles", current_roles)
    created = []
    connections = []
    remote = {}

    class CallerConnection:
        def __init__(self, project_id):
            self._afterglow_user_id = owner
            self._afterglow_project_id = project_id
            self._afterglow_token = "caller-token"
            self._afterglow_domain_id = "default"
            self._afterglow_identity_domain_id = "default"
            self.closed = False
            self.identity = self
            self.session = SimpleNamespace(
                auth=SimpleNamespace(
                    get_access=lambda session: SimpleNamespace(
                        _data={"token": {"methods": ["token", "password"]}},
                        user_id=owner,
                        user_domain_id="default",
                        project_domain_id="default",
                        project_id=project_id,
                        project_name="Project " + project_id,
                        role_names=memberships[project_id],
                        role_ids=["role-" + role for role in memberships[project_id]],
                        auth_token="caller-token",
                    )
                ),
                get=self.get,
            )
            connections.append(self)

        def get(self, url, **kwargs):
            assert url == "https://keystone.example.test/v3/auth/projects"
            assert kwargs == {"headers": {"X-Auth-Token": self._afterglow_token}, "authenticated": False}
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {
                    "projects": [
                        {"id": project_id, "name": "Project " + project_id, "domain_id": "default"}
                        for project_id in memberships
                    ]
                },
            )

        def create_application_credential(self, **kwargs):
            assert kwargs["user"] == owner
            assert kwargs["unrestricted"] is False
            assert "roles" not in kwargs
            credential = SimpleNamespace(
                id=str(uuid4()),
                secret="secret-" + self._afterglow_project_id,
                name=kwargs["name"],
                project_id=self._afterglow_project_id,
                roles=[{"id": "role-" + role, "name": role} for role in memberships[self._afterglow_project_id]],
                unrestricted=kwargs["unrestricted"],
                expires_at=kwargs.get("expires_at"),
            )
            created.append((self._afterglow_project_id, kwargs["name"], credential.id))
            remote[credential.id] = credential
            return credential

        def get_application_credential(self, user, value):
            assert user == owner
            return remote[value]

        def find_application_credential(self, user, value, **kwargs):
            assert user == owner
            return next(
                (credential for credential in remote.values() if value in {credential.id, credential.name}), None
            )

        def delete_application_credential(self, user, value, **kwargs):
            assert user == owner
            remote.pop(value, None)

        def close(self):
            self.closed = True

    monkeypatch.setattr(keystone, "get_openstack_connection", lambda token, project_id: CallerConnection(project_id))
    client = await register_public_client(
        issued_refresh.factory,
        metadata={
            "client_name": "Scope regression",
            "redirect_uris": ["https://client.example.test/callback"],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
        },
    )
    verifier = "b" * 43
    ticket = await create_authorization_ticket(
        issued_refresh.factory,
        urls=_URLS,
        client_id=client.client_id,
        response_type="code",
        redirect_uri="https://client.example.test/callback",
        resource=_URLS.resource,
        scope="mcp:read mcp:write",
        state="bound-state",
        code_challenge=pkce_s256(verifier),
        code_challenge_method="S256",
    )
    await load_consent_ticket(issued_refresh.factory, ticket=ticket.ticket, owner_user_id=owner, owner_project_id="A")
    return SimpleNamespace(
        factory=issued_refresh.factory,
        client=issued_refresh.client,
        ticket=ticket.ticket,
        client_id=client.client_id,
        owner=owner,
        conn=CallerConnection("A"),
        memberships=memberships,
        current_role_overrides=current_role_overrides,
        created=created,
        connections=connections,
        remote=remote,
        verifier=verifier,
    )


async def approve_and_exchange(consent, **choices):
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    result = await approve_consent_ticket(
        consent.factory,
        ticket=consent.ticket,
        owner_user_id=consent.owner,
        owner_project_id="A",
        username="owner",
        roles=["member"],
        conn=consent.conn,
        **choices,
    )
    assert result.state == "bound-state"
    assert result.effective_ongoing is choices.get("ongoing", False)
    exchange = await consent.client.post(
        "/api/v1/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": result.code,
            "client_id": consent.client_id,
            "redirect_uri": result.redirect_uri,
            "resource": _URLS.resource,
            "code_verifier": consent.verifier,
        },
    )
    assert exchange.status_code == 200
    async with consent.factory() as session:
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.code_hash == hash_oauth_value(result.code)))
        grant_id = code.grant_id
    return result, exchange.json(), grant_id


@pytest.mark.parametrize("project_scope", ["selected", "all"])
async def test_oauth_write_consent_narrowed_to_read_freezes_projects_through_refresh(oauth_consent, project_scope):
    from app.services.mcp_control_plane.authority import (
        McpAuthorityError,
        approved_project_metadata,
        validate_grant_project,
    )
    from app.services.mcp_control_plane.oauth_authority import resolve_oauth_access_token

    consent = oauth_consent
    result, tokens, grant_id = await approve_and_exchange(
        consent,
        project_scope=project_scope,
        project_ids=["A", "B"] if project_scope == "selected" else None,
        access_level="read",
    )
    assert tokens["scope"] == "mcp:read"
    assert [project for project, _, _ in consent.created] == ["A", "B"]
    assert all(connection.closed for connection in consent.connections if connection is not consent.conn)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.access_level == "read"
        assert grant.project_scope == project_scope
        saved = approved_project_metadata(grant)
        assert [project["id"] for project in saved] == ["A", "B"]
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant_id))
        assert code.scopes == ["mcp:read"]
        extra = await session.get(McpProjectCredential, {"grant_id": grant_id, "project_id": "B"})
        assert extra.application_credential_id and extra.credential_ciphertext

    consent.memberships["C"] = ["member"]
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    refreshed = await refresh(issued, client_id=issued.client_id)
    assert refreshed.status_code == 200
    assert refreshed.json()["scope"] == "mcp:read"
    async with consent.factory() as session, session.begin():
        grant, scopes = await resolve_oauth_access_token(
            session, raw_token=refreshed.json()["access_token"], resource=_URLS.resource
        )
        assert scopes == ("mcp:read",)
        assert approved_project_metadata(grant) == saved
        for target in ("A", "B"):
            validate_grant_project(grant, target)
            with pytest.raises(McpAuthorityError, match="management"):
                validate_grant_project(grant, target, write=True)
        with pytest.raises(McpAuthorityError, match="outside"):
            validate_grant_project(grant, "C")

    replay = await consent.client.post(
        "/api/v1/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": result.code,
            "client_id": consent.client_id,
            "redirect_uri": result.redirect_uri,
            "resource": _URLS.resource,
            "code_verifier": consent.verifier,
        },
    )
    assert replay.status_code == 400


async def test_oauth_manage_consent_uses_actual_target_roles_not_home_roles(oauth_consent):
    from app.services.mcp_control_plane.authority import McpAuthorityError
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    consent = oauth_consent
    with pytest.raises(McpAuthorityError, match="management"):
        await approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["admin"],
            conn=consent.conn,
            project_scope="selected",
            project_ids=["A", "B"],
            access_level="manage",
        )
    assert consent.created == []
    async with consent.factory() as session:
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        assert request.status == "pending"
        assert request.grant_id is None
    _, tokens, _ = await approve_and_exchange(consent, project_scope="selected", project_ids=["B"], access_level="read")
    assert tokens["scope"] == "mcp:read"


async def test_oauth_ticket_expiring_during_credential_creation_revokes_and_cleans(oauth_consent, monkeypatch):
    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, approve_consent_ticket

    consent = oauth_consent
    clock = SimpleNamespace(now=oauth_authority._now())
    connection_type = type(consent.conn)
    original_create = connection_type.create_application_credential

    def expire_during_creation(connection, **kwargs):
        credential = original_create(connection, **kwargs)
        clock.now += timedelta(hours=2)
        return credential

    monkeypatch.setattr(oauth_authority, "_now", lambda: clock.now)
    monkeypatch.setattr(connection_type, "create_application_credential", expire_during_creation)
    with pytest.raises(McpOAuthAuthorityError, match="ticket changed before activation"):
        await approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["member"],
            conn=consent.conn,
            project_scope="selected",
            project_ids=["A", "B"],
            access_level="read",
        )
    assert len(consent.created) == 2
    async with consent.factory() as session:
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        assert request.status == "pending"
        grant = await session.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked"
        assert grant.cleanup_pending is False
        assert grant.application_credential_id is None
        assert grant.credential_ciphertext is None
        children = (
            await session.scalars(select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id))
        ).all()
        assert [child.project_id for child in children] == ["B"]
        assert all(
            not child.cleanup_pending
            and child.application_credential_id is None
            and child.credential_ciphertext is None
            for child in children
        )
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id))
        assert code is None
    assert consent.remote == {}


@pytest.fixture
async def sdk_oauth_consent(oauth_consent, monkeypatch):
    """Only HTTP responses are synthetic; SDK auth/rescope/creation and SQL are real."""
    import requests
    from oslo_utils import timeutils

    from app.services import keystone

    consent = oauth_consent
    consent.remote.clear()
    state = SimpleNamespace(
        returned_roles=None,
        override_roles=False,
        creates=[],
        deletes=[],
        auth_scopes=[],
        foreign_subject=False,
        omit_anchor=False,
        returned_project=None,
        current_role_names={},
        methods=["token"],
        delegated_metadata={},
        returned_unrestricted=False,
        returned_expiry=None,
        omit_create_unrestricted=False,
        omit_get_unrestricted=False,
        credential_reads=[],
    )
    endpoint = "https://keystone.example.test/v3"
    production_connect = get_openstack_connection
    runtime_settings = keystone.get_settings().model_copy(
        update={"os_auth_url": endpoint, "os_region_name": "RegionOne", "os_interface": "public"}
    )
    monkeypatch.setattr(keystone, "get_settings", lambda: runtime_settings)
    connections = []

    def send(_session, request, **kwargs):
        url = urlsplit(request.url)
        assert url.netloc == "keystone.example.test", "test must not contact real Keystone"
        path = url.path.rstrip("/")
        headers = {}
        status = 200
        if request.method == "GET" and path == "/v3":
            payload = {"version": {"id": "v3.14", "status": "stable", "links": [{"rel": "self", "href": endpoint}]}}
        elif request.method == "POST" and path == "/v3/auth/tokens":
            body = json.loads(request.body)["auth"]
            assert body["identity"]["methods"] == ["token"]
            target = body["scope"]["project"]["id"]
            assert target in consent.memberships
            state.auth_scopes.append(target)
            now = datetime.now(UTC)
            payload = {
                "token": {
                    "methods": state.methods,
                    **state.delegated_metadata,
                    "issued_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "user": {
                        "id": "foreign" if state.foreign_subject else consent.owner,
                        "name": "owner",
                        "domain": {"id": "default"},
                    },
                    "project": {"id": target, "name": "Project " + target, "domain": {"id": "default"}},
                    "roles": [{"id": "role-" + role, "name": role} for role in consent.memberships[target]],
                    "catalog": [
                        {
                            "type": "identity",
                            "name": "keystone",
                            "endpoints": [
                                {
                                    "interface": "public",
                                    "region": "RegionOne",
                                    "url": endpoint,
                                }
                            ],
                        }
                    ],
                }
            }
            status = 201
            headers["X-Subject-Token"] = "sdk-scoped-" + target
        elif request.method == "GET" and path == "/v3/auth/projects":
            payload = {
                "projects": [
                    {"id": target, "name": "Project " + target, "domain_id": "default"}
                    for target in consent.memberships
                    if not (state.omit_anchor and target == "A")
                ]
            }
        else:
            prefix = "/v3/users/" + consent.owner + "/application_credentials"
            assert path == prefix or path.startswith(prefix + "/")
            if request.method == "POST":
                target = request.headers["X-Auth-Token"].removeprefix("sdk-scoped-")
                assert target in consent.memberships
                value = json.loads(request.body)["application_credential"]
                assert value["unrestricted"] is False
                if "expires_at" in value:
                    assert timeutils.parse_isotime(value["expires_at"]).astimezone(UTC) > datetime.now(UTC)
                # Explicit roles are accepted only for a verified closed subset;
                # the normal path still detects current-graph expansion hazards.
                requested = value.get("roles")
                current_names = state.current_role_names.get(target)
                allowed_narrowing = current_names is not None and requested == [
                    {"id": "role-" + name} for name in current_names
                ]
                if (requested is not None or current_names is not None) and not allowed_narrowing:
                    status = 400
                    payload = {
                        "error": {
                            "code": 400,
                            "title": "Bad Request",
                            "message": "Invalid application credential: Could not find role assignment with role: role-admin",
                        }
                    }
                else:
                    roles = [
                        {"id": "role-" + role, "name": role} for role in (current_names or consent.memberships[target])
                    ]
                    if state.override_roles:
                        roles = state.returned_roles
                    credential = {
                        **value,
                        "id": str(uuid4()),
                        "secret": "sdk-secret-" + target,
                        "roles": roles,
                        "project_id": state.returned_project or target,
                        "user_id": consent.owner,
                        "unrestricted": state.returned_unrestricted,
                        "expires_at": state.returned_expiry or value.get("expires_at"),
                    }
                    consent.remote[credential["id"]] = credential
                    consent.created.append((target, value["name"], credential["id"]))
                    state.creates.append(value)
                    payload = {
                        "application_credential": {
                            key: item
                            for key, item in credential.items()
                            if not (state.omit_create_unrestricted and key == "unrestricted")
                        }
                    }
                    status = 201
            elif request.method == "DELETE":
                credential_id = path.rsplit("/", 1)[-1]
                consent.remote.pop(credential_id, None)
                state.deletes.append(credential_id)
                payload = {}
                status = 204
            elif request.method == "GET" and path == prefix:
                payload = {
                    "application_credentials": [
                        {key: value for key, value in credential.items() if key != "secret"}
                        for credential in consent.remote.values()
                    ],
                    "links": {"next": None},
                }
            elif request.method == "GET":
                credential = consent.remote.get(path.rsplit("/", 1)[-1])
                state.credential_reads.append(path.rsplit("/", 1)[-1])
                status = 200 if credential else 404
                payload = (
                    {
                        "application_credential": {
                            key: item
                            for key, item in credential.items()
                            if not (state.omit_get_unrestricted and key == "unrestricted")
                        }
                    }
                    if credential
                    else {"error": {"code": 404, "title": "Not Found", "message": "absent"}}
                )
            else:
                raise AssertionError((request.method, path))
        response = requests.Response()
        response.status_code = status
        response.request = request
        response.headers.update({"Content-Type": "application/json", **headers})
        response._content = json.dumps(payload).encode()
        return response

    monkeypatch.setattr(requests.Session, "send", send)

    def connect(token, project_id):
        conn = production_connect(token, project_id)
        conn._afterglow_user_id = consent.owner
        conn._afterglow_project_id = project_id
        conn._afterglow_token = token
        conn._afterglow_domain_id = "default"
        conn._afterglow_identity_domain_id = "default"
        connections.append(conn)
        return conn

    monkeypatch.setattr(keystone, "get_openstack_connection", connect)
    consent.conn = connect("synthetic-caller", "A")
    consent.sdk = state
    try:
        yield consent
    finally:
        for conn in connections:
            conn.close()


@pytest.mark.parametrize("access_level", ["read", "manage"])
@pytest.mark.parametrize(
    "project_scope,omit_anchor",
    [("current", False), ("selected", False), ("selected", True), ("all", False), ("all", True)],
)
async def test_oauth_sdk_native_roles_support_each_scope_without_inference_expansion(
    sdk_oauth_consent, access_level, project_scope, omit_anchor
):
    from app.services.mcp_control_plane.authority import (
        default_grant_project,
        grant_credential_for_project,
        validate_grant_project,
    )
    from app.services.mcp_control_plane.oauth_authority import resolve_oauth_access_token

    consent = sdk_oauth_consent
    consent.memberships["B"] = ["member"] if access_level == "manage" else ["reader"]
    # Today's DAG gained a descendant absent from these still-valid tokens.
    # The native omitted-role path must retain their original authority.
    for target, names in consent.memberships.items():
        consent.current_role_overrides[target] = [
            *[{"id": "role-" + name, "name": name, "inherited_role_ids": ["new-role"]} for name in names],
            {"id": "new-role", "name": "new-capability", "inherited_role_ids": []},
        ]
    if omit_anchor and project_scope == "all":
        # The browser's authenticated anchor need not be in /auth/projects.
        # It can remain a logical issuance/ownership anchor only.
        consent.sdk.omit_anchor = True
    choices = {"project_scope": project_scope, "access_level": access_level}
    if project_scope == "selected":
        choices["project_ids"] = ["B"] if omit_anchor else ["A", "B"]
    _, tokens, grant_id = await approve_and_exchange(consent, **choices)
    expected = ["A"] if project_scope == "current" else (["B"] if omit_anchor else ["A", "B"])
    assert [project for project, _, _ in consent.created] == expected
    assert all("roles" not in value and value["unrestricted"] is False for value in consent.sdk.creates)
    async with consent.factory() as db, db.begin():
        grant, scopes = await resolve_oauth_access_token(db, raw_token=tokens["access_token"], resource=_URLS.resource)
        assert scopes == (("mcp:read", "mcp:write") if access_level == "manage" else ("mcp:read",))
        assert default_grant_project(grant) == expected[0]
        assert grant.owner_project_id == "A" and grant.cleanup_pending is False
        assert bool(grant.application_credential_id) == ("A" in expected)
        for target in expected:
            credential_id, _ = await grant_credential_for_project(db, grant, target)
            assert consent.remote[credential_id]["project_id"] == target
            assert [role["id"] for role in consent.remote[credential_id]["roles"]] == [
                "role-" + role for role in consent.memberships[target]
            ]
            validate_grant_project(grant, target, write=access_level == "manage")


@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_oauth_sdk_stale_admin_role_narrows_to_current_selected_project(sdk_oauth_consent, access_level):
    from app.services.mcp_control_plane.oauth_authority import resolve_oauth_access_token

    consent = sdk_oauth_consent
    consent.memberships["B"] = ["admin", "member", "reader"]
    consent.sdk.current_role_names["B"] = ["member", "reader"]
    consent.current_role_overrides["B"] = [
        {"id": "role-member", "name": "member", "inherited_role_ids": ["role-reader"]},
        {"id": "role-reader", "name": "reader", "inherited_role_ids": []},
    ]
    _, tokens, grant_id = await approve_and_exchange(
        consent, project_scope="selected", project_ids=["B"], access_level=access_level
    )
    assert len(consent.created) == 1 and consent.created[0][0] == "B"
    credential = consent.remote[consent.created[0][2]]
    assert [role["id"] for role in credential["roles"]] == ["role-member", "role-reader"]
    async with consent.factory() as db, db.begin():
        grant, scopes = await resolve_oauth_access_token(db, raw_token=tokens["access_token"], resource=_URLS.resource)
        assert grant.id == grant_id and grant.status == "active"
        assert grant.approved_projects == [
            {"id": "B", "name": "Project B", "roles": ["member", "reader"], "can_write": True}
        ]
        assert scopes == (("mcp:read", "mcp:write") if access_level == "manage" else ("mcp:read",))


async def test_oauth_sdk_role_revoked_during_creation_returns_safe_error_and_cleans_partial_grant(
    sdk_oauth_consent, monkeypatch
):
    from app.api.identity import mcp_access
    from app.main import app

    consent = sdk_oauth_consent
    consent.memberships["B"] = ["member"]
    # Readback still saw member; Keystone revokes it before the second create.
    consent.sdk.current_role_names["B"] = ["reader"]
    monkeypatch.setattr(
        mcp_access,
        "get_settings",
        lambda: SimpleNamespace(
            service_mcp_enabled=True,
            frontend_base_url="http://test",
            public_api_base="http://test",
            cors_origin_list=[],
        ),
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        mcp_api.get_token_info,
        lambda: {"user_id": consent.owner, "project_id": "A", "username": "owner", "roles": ["member"]},
    )
    monkeypatch.setitem(app.dependency_overrides, mcp_api.get_os_conn, lambda: consent.conn)
    response = await consent.client.post(
        f"/api/v1/auth/mcp-oauth/consents/{consent.ticket}/approve",
        json={"project_scope": "selected", "project_ids": ["A", "B"], "access_level": "manage"},
        headers={"Origin": "http://test", "Sec-Fetch-Site": "same-origin"},
    )
    assert response.status_code == 400
    assert all(value not in response.text for value in (consent.owner, "role-admin", "sdk-secret-"))
    assert [target for target, _, _ in consent.created] == ["A"]
    assert consent.sdk.deletes == [consent.created[0][2]]
    assert consent.remote == {}
    async with consent.factory() as db:
        request = await db.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        grant = await db.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked" and grant.application_credential_id is None
        assert await db.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id)) is None


@pytest.mark.parametrize(
    "returned_roles",
    [
        None,
        [],
        [{"id": "foreign-role", "name": "member"}],
        [{"name": "member"}],
        [{"id": [], "name": "member"}],
        [{"id": "role-reader", "name": "reader"}, {"id": "foreign-role", "name": "admin"}],
    ],
)
async def test_oauth_sdk_unapproved_returned_roles_revoke_and_cleanup_saved_id(sdk_oauth_consent, returned_roles):
    from app.services.mcp_control_plane.authority import McpAuthorityError
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    consent = sdk_oauth_consent
    consent.sdk.returned_roles = returned_roles
    consent.sdk.override_roles = True
    with pytest.raises(McpAuthorityError, match="roles do not match"):
        await approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["admin"],
            conn=consent.conn,
            project_scope="selected",
            project_ids=["B"],
            access_level="read",
        )
    assert len(consent.created) == 1
    assert consent.sdk.deletes == [consent.created[0][2]]
    assert consent.remote == {}
    async with consent.factory() as db:
        request = await db.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        grant = await db.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending is False
        assert await db.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id)) is None


@pytest.mark.parametrize("denial", ["foreign-subject", "unknown-target", "reader-manage"])
async def test_oauth_sdk_denied_target_never_creates_credentials(sdk_oauth_consent, denial):
    from app.services.mcp_control_plane.authority import McpAuthorityError
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    consent = sdk_oauth_consent
    consent.sdk.foreign_subject = denial == "foreign-subject"
    with pytest.raises(McpAuthorityError):
        await approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["admin"],
            conn=consent.conn,
            project_scope="selected",
            project_ids=["unknown" if denial == "unknown-target" else "B"],
            access_level="manage" if denial == "reader-manage" else "read",
        )
    assert consent.created == []
    async with consent.factory() as db:
        request = await db.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        assert request.status == "pending" and request.grant_id is None


@pytest.mark.parametrize("project_scope", ["selected", "all"])
async def test_oauth_sdk_ticket_expiry_before_activation_cleans_without_anchor(
    sdk_oauth_consent, monkeypatch, project_scope
):
    from app.services.mcp_control_plane import oauth_authority

    consent = sdk_oauth_consent
    consent.sdk.omit_anchor = True
    clock = SimpleNamespace(now=oauth_authority._now())
    monkeypatch.setattr(oauth_authority, "_now", lambda: clock.now)
    original_create = type(consent.conn.identity).create_application_credential

    def expire_after_creation(identity_proxy, *args, **kwargs):
        credential = original_create(identity_proxy, *args, **kwargs)
        clock.now += timedelta(hours=2)
        return credential

    monkeypatch.setattr(type(consent.conn.identity), "create_application_credential", expire_after_creation)
    with pytest.raises(oauth_authority.McpOAuthAuthorityError, match="ticket changed before activation"):
        await oauth_authority.approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["admin"],
            conn=consent.conn,
            project_scope=project_scope,
            project_ids=["B"] if project_scope == "selected" else None,
            access_level="read",
        )
    assert [project for project, _, _ in consent.created] == ["B"]
    assert consent.remote == {}
    assert consent.sdk.deletes == [consent.created[0][2]]
    async with consent.factory() as db:
        request = await db.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        grant = await db.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending is False
        assert grant.application_credential_id is None
        assert await db.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id)) is None


async def test_oauth_sdk_wrong_returned_project_cleans_by_saved_id(sdk_oauth_consent):
    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.authority import McpAuthorityError

    consent = sdk_oauth_consent
    consent.sdk.returned_project = "foreign-project"
    with pytest.raises(McpAuthorityError, match="project does not match"):
        await oauth_authority.approve_consent_ticket(
            consent.factory,
            ticket=consent.ticket,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            roles=["admin"],
            conn=consent.conn,
            project_scope="selected",
            project_ids=["B"],
            access_level="read",
        )
    assert consent.remote == {}
    assert consent.sdk.deletes == [consent.created[0][2]]
    async with consent.factory() as db:
        request = await db.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        grant = await db.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending is False
        assert await db.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id)) is None


async def test_ongoing_native_consent_rotates_past_old_deadline_without_authority_expansion(
    sdk_oauth_consent, monkeypatch
):
    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.authority import validate_grant_project
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = sdk_oauth_consent
    consent.sdk.methods = ["token", "password"]
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, project_scope="all", access_level="manage")
    assert all("expires_at" not in value and value["unrestricted"] is False for value in consent.sdk.creates)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.expires_at is None and grant.oauth_ongoing is True
        assert grant.consented_at is not None
        ceiling = grant.issued_role_ceiling
        assert ceiling == {
            "A": [{"id": "role-member", "name": "member"}],
            "B": [{"id": "role-reader", "name": "reader"}],
        }
        original_deadline = await session.scalar(
            select(McpOAuthAuthorizationRequest.grant_deadline).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
    later = datetime.now(UTC) + timedelta(days=400)
    monkeypatch.setattr(oauth_authority, "_now", lambda: later)
    consent.memberships["C"] = ["admin"]
    await sweep_delegated_authority(consent.factory, now=later)
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    first = await refresh(issued, client_id=issued.client_id, scope="mcp:read")
    assert first.status_code == 200
    next_tokens = first.json()
    assert 0 < next_tokens["expires_in"] <= 3600
    assert next_tokens["scope"] == "mcp:read"
    rejected = await refresh(
        issued, client_id=issued.client_id, token=next_tokens["refresh_token"], scope="mcp:read mcp:write"
    )
    assert rejected.status_code == 400
    second = await refresh(issued, client_id=issued.client_id, token=next_tokens["refresh_token"])
    assert second.status_code == 200 and second.json()["scope"] == "mcp:read"
    async with consent.factory() as session, session.begin():
        grant, scopes = await oauth_authority.resolve_oauth_access_token(
            session, raw_token=second.json()["access_token"], resource=_URLS.resource
        )
        assert grant.id == grant_id and scopes == ("mcp:read",)
        assert grant.issued_role_ceiling == ceiling and grant.expires_at is None
        assert [project["id"] for project in grant.approved_projects] == ["A", "B"]
        with pytest.raises(oauth_authority.McpAuthorityError, match="outside"):
            validate_grant_project(grant, "C")
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id))
        refresh_rows = (
            await session.scalars(
                select(McpOAuthToken).where(McpOAuthToken.family_id == family.id, McpOAuthToken.token_type == "refresh")
            )
        ).all()
        assert len(refresh_rows) == 3 and all(row.expires_at is None for row in refresh_rows)
        client = await session.scalar(select(McpOAuthClient).where(McpOAuthClient.client_id == consent.client_id))
        assert client.revoked_at is None
        assert original_deadline.replace(tzinfo=UTC) < later
    replay = await refresh(issued, client_id=issued.client_id)
    assert replay.status_code == 400
    async with consent.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending
        with pytest.raises(oauth_authority.McpOAuthAuthorityError):
            await oauth_authority.resolve_oauth_access_token(
                session, raw_token=second.json()["access_token"], resource=_URLS.resource
            )


@pytest.mark.parametrize(
    "methods,delegation",
    [
        (["token"], {}),
        (["application_credential"], {}),
        (["token", "password", "application_credential"], {}),
        (["token", "password"], {"OS-TRUST:trust": {"id": "trust"}}),
        (["token", "openid"], {"application_credential": {"id": "delegated"}}),
        (["token", "password"], {"OAuth1": {"consumer_id": "delegated"}}),
        (["token", "password"], {"OS-OAUTH1": {"access_token_id": "delegated"}}),
        (["token", "password"], {"oauth2_credential": {"id": "delegated"}}),
        (["token", "password"], {"access_rules": [{"path": "/limited"}]}),
        (["token", "password"], {"bind": {"kerberos": "bound-user"}}),
    ],
)
async def test_ongoing_native_consent_refuses_unproven_or_delegated_authentication(
    sdk_oauth_consent, methods, delegation
):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError

    consent = sdk_oauth_consent
    consent.sdk.methods = methods
    consent.sdk.delegated_metadata = delegation
    with pytest.raises(McpOAuthAuthorityError, match="human project authentication"):
        await approve_and_exchange(consent, ongoing=True, access_level="read")
    assert consent.sdk.creates == [] and consent.remote == {}
    async with consent.factory() as session:
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        assert request.status == "pending" and request.grant_id is None


@pytest.mark.parametrize("methods", [["token", "mapped"], ["token", "openid"]])
async def test_ongoing_native_consent_accepts_human_federated_lineage(sdk_oauth_consent, methods):
    sdk_oauth_consent.sdk.methods = methods
    _, _, grant_id = await approve_and_exchange(sdk_oauth_consent, ongoing=True, access_level="read")
    async with sdk_oauth_consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.oauth_ongoing and grant.expires_at is None


@pytest.mark.parametrize("failure", ["role-name", "unrestricted", "expiry"])
async def test_ongoing_native_response_must_match_exact_restricted_unbounded_approval(sdk_oauth_consent, failure):
    from app.services.mcp_control_plane.authority import McpAuthorityError

    consent = sdk_oauth_consent
    consent.sdk.methods = ["token", "password"]
    if failure == "role-name":
        consent.sdk.override_roles = True
        consent.sdk.returned_roles = [{"id": "role-member", "name": "admin"}]
    elif failure == "unrestricted":
        consent.sdk.returned_unrestricted = True
    else:
        consent.sdk.returned_expiry = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    with pytest.raises(McpAuthorityError):
        await approve_and_exchange(consent, ongoing=True, access_level="read")
    assert len(consent.created) == 1 and consent.remote == {}
    assert consent.sdk.deletes == [consent.created[0][2]]
    async with consent.factory() as session:
        request = await session.scalar(
            select(McpOAuthAuthorizationRequest).where(
                McpOAuthAuthorizationRequest.ticket_hash == hash_oauth_value(consent.ticket)
            )
        )
        grant = await session.get(McpDelegatedGrant, request.grant_id)
        assert grant.status == "revoked" and not grant.cleanup_pending
        assert await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant.id)) is None


async def test_ongoing_dispatch_rechecks_role_ids_even_when_names_are_reused(oauth_consent, monkeypatch):
    from app.services.mcp_control_plane import authentication, connection

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    monkeypatch.setattr(connection, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    principal = await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
    await connection._validate_current_roles(consent.conn, principal)
    consent.current_role_overrides["A"] = [{"id": "replacement-member", "name": "member"}]
    with pytest.raises(connection.McpConsumerConnectionError, match="no longer delegated"):
        await connection._validate_current_roles(consent.conn, principal)
    consent.current_role_overrides["A"] = [
        {"id": "replacement-member", "name": "member"},
        {"id": "role-member", "name": "member"},
    ]
    old_access = consent.conn.session.auth.get_access(consent.conn.session)
    old_access.role_ids = ["replacement-member"]
    consent.conn.session.auth.get_access = lambda session: old_access
    with pytest.raises(connection.McpConsumerConnectionError, match="issued role ceiling"):
        await connection._validate_current_roles(consent.conn, principal)


async def test_ongoing_refresh_replay_race_revokes_winner_and_preserves_frozen_ceiling(oauth_consent):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    results = await asyncio.gather(*[refresh(issued, client_id=issued.client_id) for _ in range(2)])
    assert sorted(response.status_code for response in results) == [200, 400]
    winner = next(response.json() for response in results if response.status_code == 200)
    async with consent.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.credential_epoch == 2
        assert grant.issued_role_ceiling == {"A": [{"id": "role-member", "name": "member"}]}
        with pytest.raises(McpOAuthAuthorityError):
            await resolve_oauth_access_token(session, raw_token=winner["access_token"], resource=_URLS.resource)


async def test_ongoing_revoked_client_cannot_refresh_or_dispatch(oauth_consent):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token

    consent = oauth_consent
    _, tokens, _ = await approve_and_exchange(consent, ongoing=True, access_level="read")
    async with consent.factory() as session, session.begin():
        client = await session.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == consent.client_id).with_for_update()
        )
        client.revoked_at = datetime.now(UTC)
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    assert (await refresh(issued, client_id=issued.client_id)).status_code == 400
    async with consent.factory() as session, session.begin():
        with pytest.raises(McpOAuthAuthorityError, match="client is inactive"):
            await resolve_oauth_access_token(session, raw_token=tokens["access_token"], resource=_URLS.resource)


async def test_default_finite_native_consent_never_renews_past_original_deadline(sdk_oauth_consent, monkeypatch):
    from app.services.mcp_control_plane import oauth_authority

    consent = sdk_oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, access_level="read")
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        deadline = grant.expires_at.replace(tzinfo=UTC)
        assert not grant.oauth_ongoing and grant.issued_role_ceiling is None
        assert all(value["expires_at"] for value in consent.sdk.creates)
    monkeypatch.setattr(oauth_authority, "_now", lambda: deadline + timedelta(seconds=1))
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    assert (await refresh(issued, client_id=issued.client_id)).status_code == 400
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.expires_at.replace(tzinfo=UTC) == deadline
        assert not grant.oauth_ongoing and grant.status != "active"


async def test_ongoing_refresh_and_owner_revoke_serialize_without_resurrection(oauth_consent):
    from app.services.mcp_control_plane.oauth_authority import (
        McpOAuthAuthorityError,
        resolve_oauth_access_token,
        revoke_oauth_token,
    )

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    refreshed, _ = await asyncio.gather(
        refresh(issued, client_id=issued.client_id),
        revoke_oauth_token(consent.factory, token=tokens["access_token"]),
    )
    assert refreshed.status_code in {200, 400}
    async with consent.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id))
        assert family.revoked_at is not None
        for raw in [
            tokens["access_token"],
            *([refreshed.json()["access_token"]] if refreshed.status_code == 200 else []),
        ]:
            with pytest.raises(McpOAuthAuthorityError):
                await resolve_oauth_access_token(session, raw_token=raw, resource=_URLS.resource)


async def test_ongoing_refresh_tombstones_survive_until_terminal_retention(oauth_consent):
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority
    from app.services.mcp_control_plane.oauth_authority import revoke_oauth_token

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    rotated = await refresh(issued, client_id=issued.client_id)
    assert rotated.status_code == 200
    async with consent.factory() as session:
        original_id = await session.scalar(
            select(McpOAuthToken.id).where(McpOAuthToken.token_hash == hash_oauth_value(tokens["refresh_token"]))
        )
    future = datetime.now(UTC) + timedelta(days=100)
    await sweep_delegated_authority(consent.factory, now=future)
    async with consent.factory() as session:
        old = await session.scalar(
            select(McpOAuthToken).where(McpOAuthToken.token_hash == hash_oauth_value(tokens["refresh_token"]))
        )
        assert old is not None and old.id == original_id and old.expires_at is None and old.rotated_at is not None
    # The 100-day sweep has legitimately removed expired access hashes.
    # Revoke with the still-live, unrotated ongoing refresh token instead.
    await revoke_oauth_token(consent.factory, token=rotated.json()["refresh_token"])
    await sweep_delegated_authority(consent.factory, now=future)
    async with consent.factory() as session:
        assert (
            await session.scalar(
                select(McpOAuthToken).where(McpOAuthToken.token_hash == hash_oauth_value(tokens["refresh_token"]))
            )
            is None
        )
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.oauth_ongoing


@pytest.mark.parametrize(
    "omit_create,omit_get,allowed", [(True, False, True), (True, True, False), (False, True, False)]
)
async def test_ongoing_restriction_proof_uses_fresh_get_not_seeded_create_fields(
    sdk_oauth_consent, omit_create, omit_get, allowed
):
    from app.services.mcp_control_plane.authority import McpAuthorityError

    consent = sdk_oauth_consent
    consent.sdk.methods = ["token", "password"]
    consent.sdk.omit_create_unrestricted = omit_create
    consent.sdk.omit_get_unrestricted = omit_get
    if allowed:
        await approve_and_exchange(consent, ongoing=True, access_level="read")
    else:
        with pytest.raises(McpAuthorityError, match="did not confirm"):
            await approve_and_exchange(consent, ongoing=True, access_level="read")
        assert consent.remote == {}
    assert consent.sdk.credential_reads


async def test_cimd_client_stale_cleanup_refetch_allows_fresh_legacy_finite_consent(oauth_consent, monkeypatch):
    from unittest.mock import AsyncMock

    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = oauth_consent
    client_id = "https://client.example.test/client.json"
    metadata = {
        "client_id": client_id,
        "client_name": "CIMD client",
        "redirect_uris": ["https://client.example.test/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_method": "none",
    }
    now = datetime.now(UTC)
    async with consent.factory() as session, session.begin():
        session.add(
            McpOAuthClient(
                client_id=client_id,
                metadata_json=metadata,
                redirect_uris=metadata["redirect_uris"],
                client_id_issued_at=now - timedelta(days=40),
                expires_at=now - timedelta(days=10),
            )
        )
    await sweep_delegated_authority(consent.factory, now=now)
    async with consent.factory() as session:
        stale = await session.scalar(select(McpOAuthClient).where(McpOAuthClient.client_id == client_id))
        assert stale.revoked_at is not None
    monkeypatch.setattr(oauth_authority, "fetch_cimd", AsyncMock(return_value=metadata))
    ticket = await oauth_authority.create_authorization_ticket(
        consent.factory,
        client_id=client_id,
        redirect_uri=metadata["redirect_uris"][0],
        response_type="code",
        resource=_URLS.resource,
        urls=_URLS,
        scope="mcp:read",
        code_challenge=pkce_s256(consent.verifier),
        code_challenge_method="S256",
        state="bound-state",
    )
    await oauth_authority.load_consent_ticket(
        consent.factory,
        ticket=ticket.ticket,
        owner_user_id=consent.owner,
        owner_project_id="A",
    )
    consent.client_id, consent.ticket = client_id, ticket.ticket
    _, _, grant_id = await approve_and_exchange(consent, access_level="read")
    async with consent.factory() as session:
        refreshed = await session.scalar(select(McpOAuthClient).where(McpOAuthClient.client_id == client_id))
        assert refreshed.revoked_at is None and refreshed.expires_at.replace(tzinfo=UTC) > now
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.expires_at is not None and not grant.oauth_ongoing


async def test_refresh_attenuation_invalidates_captured_write_principal_at_final_dispatch(oauth_consent, monkeypatch):
    from app.services.mcp_control_plane import authentication, ledger

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="manage")
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(ledger, "get_session_factory", lambda: consent.factory)
    principal = await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
    assert principal.can_write and principal.oauth_family_id is not None
    invocation_id = str(uuid4())
    async with consent.factory() as session, session.begin():
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key="captured-write",
                arguments_hash="a" * 64,
                registry_version="test",
                status="claimed",
                lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
            )
        )
    issued = SimpleNamespace(client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"])
    narrowed = await refresh(issued, client_id=issued.client_id, scope="mcp:read")
    assert narrowed.status_code == 200
    with pytest.raises(ledger.McpInvocationError) as denied:
        await ledger.authorize_mutation_dispatch(principal, invocation_id=invocation_id)
    assert isinstance(denied.value.__cause__, authentication.McpAuthenticationError)
    async with consent.factory() as session:
        invocation = await session.get(McpToolInvocation, invocation_id)
        assert invocation.status == "claimed" and invocation.sent_at is None
    fresh = await authentication.verify_mcp_bearer(narrowed.json()["access_token"], urls=_URLS)
    assert not fresh.can_write and fresh.oauth_family_id == principal.oauth_family_id


async def test_ongoing_access_retention_is_bounded_without_rewriting_refresh_tombstones(oauth_consent):
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority
    from app.services.mcp_control_plane.oauth_authority import revoke_oauth_token

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    now = datetime.now(UTC)
    async with consent.factory() as session, session.begin():
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id))
        session.add_all(
            [
                McpOAuthToken(
                    family_id=family.id,
                    token_hash=hash_oauth_value("expired-access-" + str(uuid4())),
                    token_type="access",
                    resource=_URLS.resource,
                    scopes=["mcp:read"],
                    generation=1,
                    expires_at=now - timedelta(days=100),
                )
                for _ in range(200)
            ]
        )
        old_hashes = [hash_oauth_value("refresh-tombstone-" + str(uuid4())) for _ in range(200)]
        session.add_all(
            [
                McpOAuthToken(
                    family_id=family.id,
                    token_hash=digest,
                    token_type="refresh",
                    resource=_URLS.resource,
                    scopes=["mcp:read"],
                    generation=0,
                    expires_at=None,
                    rotated_at=now - timedelta(days=100),
                )
                for digest in old_hashes
            ]
        )
    swept = await sweep_delegated_authority(consent.factory, now=now)
    assert swept.deleted_access_tokens >= 200 and swept.deleted_refresh_tombstones == 0
    await revoke_oauth_token(consent.factory, token=tokens["access_token"])
    async with consent.factory() as session:
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id))
        assert family.revoked_at is not None
        rows = (await session.scalars(select(McpOAuthToken).where(McpOAuthToken.token_hash.in_(old_hashes)))).all()
        assert len(rows) == 200
        assert all(row.revoked_at is None for row in rows)


@pytest.mark.parametrize("revoke_path", ["token", "replay", "owner"])
async def test_terminal_ongoing_grants_schedule_durable_owner_recovery_without_losing_secrets(
    oauth_consent, monkeypatch, revoke_path
):
    from app.services.mcp_control_plane import authority, oauth_authority

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    if revoke_path == "token":
        await oauth_authority.revoke_oauth_token(consent.factory, token=tokens["access_token"])
    elif revoke_path == "replay":
        issued = SimpleNamespace(
            client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"]
        )
        assert (await refresh(issued, client_id=issued.client_id)).status_code == 200
        assert (await refresh(issued, client_id=issued.client_id)).status_code == 400
    else:
        await authority.revoke_grant(
            consent.factory,
            grant_id=grant_id,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
        )
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending
        assert grant.orphan_recovery_after is not None
        assert grant.application_credential_id and grant.credential_ciphertext
        credential_id = grant.application_credential_id
        recover_at = grant.orphan_recovery_after.replace(tzinfo=UTC) + timedelta(seconds=1)
    assert credential_id in consent.remote
    monkeypatch.setattr(authority, "_now", lambda: recover_at)
    recovered = await authority.recover_stale_pending_orphans(
        consent.factory,
        conn=consent.conn,
        owner_user_id=consent.owner,
        owner_project_id="A",
        username="owner",
    )
    assert recovered == 1 and consent.remote == {}
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert not grant.cleanup_pending and grant.credential_ciphertext is None
        assert grant.application_credential_id is None and grant.orphan_recovery_after is None


async def test_owner_recovery_preserves_live_write_lease_and_retries_keystone_failure(oauth_consent, monkeypatch):
    from app.services.mcp_control_plane import authority, oauth_authority

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="manage")
    invocation_id = str(uuid4())
    async with consent.factory() as session, session.begin():
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key="active-lease",
                arguments_hash="a" * 64,
                registry_version="test",
                status="dispatch_authorized",
                lease_expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
    await oauth_authority.revoke_oauth_token(consent.factory, token=tokens["access_token"])
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        credential_id, ciphertext = grant.application_credential_id, grant.credential_ciphertext
        recover_at = grant.orphan_recovery_after.replace(tzinfo=UTC) + timedelta(seconds=1)
    monkeypatch.setattr(authority, "_now", lambda: recover_at)

    async def recover():
        return await authority.recover_stale_pending_orphans(
            consent.factory,
            conn=consent.conn,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
        )

    assert await recover() == 0 and credential_id in consent.remote
    async with consent.factory() as session, session.begin():
        invocation = await session.get(McpToolInvocation, invocation_id, with_for_update=True)
        invocation.status = "unknown"
        invocation.lease_expires_at = None
    original_delete = consent.conn.delete_application_credential

    def unavailable(*args, **kwargs):
        raise RuntimeError("synthetic Keystone unavailable")

    monkeypatch.setattr(consent.conn, "delete_application_credential", unavailable)
    assert await recover() == 0
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.cleanup_pending and grant.application_credential_id == credential_id
        assert grant.credential_ciphertext == ciphertext and grant.orphan_recovery_after is not None
    monkeypatch.setattr(consent.conn, "delete_application_credential", original_delete)
    assert await recover() == 1 and consent.remote == {}


async def test_expired_unexchanged_ongoing_code_retires_credential_and_cannot_be_reused(oauth_consent):
    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = oauth_consent
    result = await oauth_authority.approve_consent_ticket(
        consent.factory,
        ticket=consent.ticket,
        owner_user_id=consent.owner,
        owner_project_id="A",
        username="owner",
        roles=["member"],
        conn=consent.conn,
        ongoing=True,
        access_level="read",
    )
    assert result.effective_ongoing is True
    async with consent.factory() as session:
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.code_hash == hash_oauth_value(result.code)))
        grant_id = code.grant_id
        after_code = code.expires_at.replace(tzinfo=UTC) + timedelta(seconds=1)
    await sweep_delegated_authority(consent.factory, now=after_code)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == "revoked" and grant.cleanup_pending and grant.orphan_recovery_after is not None
        assert grant.application_credential_id and grant.credential_ciphertext is None
        assert await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id)) is None
    # Existing exchanged families are covered by the past-deadline/cleanup test;
    # code sweeping must never turn a consumed code into fresh authorization.
    denied = await consent.client.post(
        "/api/v1/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": result.code,
            "client_id": consent.client_id,
            "redirect_uri": result.redirect_uri,
            "resource": _URLS.resource,
            "code_verifier": consent.verifier,
        },
    )
    assert denied.status_code == 400


async def test_expired_code_sweep_does_not_retire_exchanged_ongoing_family(oauth_consent):
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = oauth_consent
    _, _, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="read")
    async with consent.factory() as session:
        code = await session.scalar(select(McpOAuthCode).where(McpOAuthCode.grant_id == grant_id))
        after_code = code.expires_at.replace(tzinfo=UTC) + timedelta(seconds=1)
    await sweep_delegated_authority(consent.factory, now=after_code)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        family = await session.scalar(select(McpOAuthTokenFamily).where(McpOAuthTokenFamily.grant_id == grant_id))
        assert grant.status == "active" and not grant.cleanup_pending
        assert family is not None and family.revoked_at is None


async def test_terminal_ongoing_ciphertext_is_scrubbed_only_after_successful_drain_and_owner_can_delete(
    oauth_consent, monkeypatch
):
    from app.services.mcp_control_plane import authentication, authority, ledger, oauth_authority
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(
        consent,
        ongoing=True,
        project_scope="all",
        access_level="manage",
    )
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(ledger, "get_session_factory", lambda: consent.factory)
    principal = await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
    invocation_id = str(uuid4())
    async with consent.factory() as session, session.begin():
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key="scrub-drain",
                arguments_hash="a" * 64,
                registry_version="test",
                status="dispatch_authorized",
                lease_expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
    await oauth_authority.revoke_oauth_token(consent.factory, token=tokens["access_token"])
    await sweep_delegated_authority(consent.factory)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        extra = await session.get(McpProjectCredential, {"grant_id": grant_id, "project_id": "B"})
        assert grant.credential_ciphertext and extra.credential_ciphertext
        remote_ids = {grant.application_credential_id, extra.application_credential_id}
        retry_at = grant.orphan_recovery_after.replace(tzinfo=UTC) + timedelta(seconds=1)
    # This is the normal post-provider completion path; it works after revoke
    # without restoring authority or pretending an unknown outcome succeeded.
    await ledger.complete_mutation(principal, invocation_id=invocation_id, result={"accepted": True})
    await sweep_delegated_authority(consent.factory)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        extra = await session.get(McpProjectCredential, {"grant_id": grant_id, "project_id": "B"})
        assert grant.credential_ciphertext is None and extra.credential_ciphertext is None
        assert {grant.application_credential_id, extra.application_credential_id} == remote_ids
        assert grant.cleanup_pending and extra.cleanup_pending and grant.orphan_recovery_after is not None
    assert set(consent.remote) == remote_ids
    await sweep_delegated_authority(consent.factory)
    async with consent.factory() as session:
        retired = (
            await session.scalars(
                select(ActivityLog.id).where(
                    ActivityLog.resource_id == grant_id,
                    ActivityLog.action == "mcp_grant.secret_retire",
                )
            )
        ).all()
        assert len(retired) == 1
    monkeypatch.setattr(authority, "_now", lambda: retry_at)
    assert (
        await authority.recover_stale_pending_orphans(
            consent.factory,
            conn=consent.conn,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
        )
        == 1
    )
    assert consent.remote == {}
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.application_credential_id is None and not grant.cleanup_pending


@pytest.mark.parametrize("state", ["claimed", "dispatch_authorized", "unknown"])
async def test_terminal_unknown_keeps_outcome_but_not_local_secret_after_no_live_lease(
    oauth_consent, monkeypatch, state
):
    from app.services.mcp_control_plane import authentication, authority, connection, ledger, oauth_authority
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="manage")
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(connection, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(ledger, "get_session_factory", lambda: consent.factory)
    principal = await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
    already_loaded = await connection._load_credential(principal)
    invocation_id = str(uuid4())
    async with consent.factory() as session, session.begin():
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key="unknown-scrub",
                arguments_hash="a" * 64,
                registry_version="test",
                status="dispatch_authorized" if state == "unknown" else state,
                lease_expires_at=datetime.now(UTC) - timedelta(days=100),
            )
        )
    if state == "unknown":
        await ledger.complete_mutation(
            principal,
            invocation_id=invocation_id,
            error="Synthetic worker drained with an uncertain provider outcome",
        )
    await oauth_authority.revoke_oauth_token(consent.factory, token=tokens["access_token"])
    with pytest.raises(connection.McpConsumerConnectionError):
        await connection._load_credential(principal)
    await sweep_delegated_authority(consent.factory)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        invocation = await session.get(McpToolInvocation, invocation_id)
        assert grant.cleanup_pending and grant.application_credential_id == already_loaded[0]
        assert grant.credential_ciphertext is None and grant.orphan_recovery_after is not None
        assert invocation.status == "unknown" and invocation.result is None
        retry_at = grant.orphan_recovery_after.replace(tzinfo=UTC) + timedelta(seconds=1)
    # SQL erasure does not cancel or revoke an already-loaded native session.
    assert already_loaded[1] and already_loaded[0] in consent.remote
    monkeypatch.setattr(authority, "_now", lambda: retry_at)
    assert (
        await authority.recover_stale_pending_orphans(
            consent.factory,
            conn=consent.conn,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
        )
        == 1
    )
    assert consent.remote == {}
    async with consent.factory() as session:
        invocation = await session.get(McpToolInvocation, invocation_id)
        assert invocation.status == "unknown" and invocation.result is None


@pytest.mark.parametrize(
    "stage,change,expected_writes",
    [
        ("preview", "same-scope-refresh", 1),
        ("preview", "narrow-refresh", 0),
        ("authorized", "same-scope-refresh", 1),
        ("authorized", "narrow-refresh", 1),
        ("authorized", "access-expiry", 1),
        ("authorized", "commit-ambiguity", 0),
    ],
)
async def test_oauth_mutation_linearization_survives_rotation_without_false_unknown(
    oauth_consent, monkeypatch, stage, change, expected_writes
):
    """Real SQL/transport/ledger and loopback HTTP write; identity fixture is synthetic."""
    import threading
    from contextlib import asynccontextmanager
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.request import Request, urlopen

    from app.services.mcp_control_plane import authentication, connection, ledger, oauth_authority, registry, transport
    from app.services.mcp_control_plane.sdk import run_sdk

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="manage")
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(connection, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(ledger, "get_session_factory", lambda: consent.factory)
    principal = await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
    barrier, release = asyncio.Event(), asyncio.Event()
    writes = []

    class Provider(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            assert self.path == "/mutation"
            writes.append(self.rfile.read(int(self.headers["Content-Length"])))
            payload = b'{"accepted":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    provider = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    worker = threading.Thread(target=provider.serve_forever, daemon=True)
    worker.start()

    class Arguments(registry.McpDomainArguments):
        resource: str

    class Output(registry.McpDomainOutput):
        accepted: bool

    @asynccontextmanager
    async def owned_connection(context):
        # Exercise the real credential-load and role fences which previously
        # rejected rotation/expiry after the ledger admission had committed.
        await connection._load_credential(context.principal)
        await connection._validate_current_roles(consent.conn, context.principal)
        yield consent.conn

    async def preview(_context, _arguments):
        if stage == "preview":
            barrier.set()
            await release.wait()
        return registry.McpMutationPreview(
            resource_identity="synthetic-resource",
            current_state="ready",
            intended_transition="change",
            dependent_resources=[],
            destructive=False,
            estimated_effect="one local HTTP write",
            fingerprint="fixture",
        )

    def native_write():
        request = Request(
            f"http://127.0.0.1:{provider.server_port}/mutation",
            data=b'{"resource":"fixture"}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            return Output.model_validate_json(response.read())

    async def handler(context, _arguments):
        async with context.openstack_connection():
            return await run_sdk(native_write)

    entry = registry.RegistryEntry(
        name="afterglow_admission_fixture",
        description="isolated admission fixture",
        arguments=Arguments,
        output=Output,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=1024,
        handler=handler,
        preview_builder=preview,
    )
    monkeypatch.setattr(registry, "entry_by_name", lambda name: entry if name == entry.name else None)
    monkeypatch.setattr(transport, "entry_by_name", lambda name: entry if name == entry.name else None)
    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", owned_connection)
    real_authorize = ledger.authorize_mutation_dispatch

    async def authorize(current, **kwargs):
        admitted = await real_authorize(current, **kwargs)
        if stage == "authorized":
            barrier.set()
            await release.wait()
        if change == "commit-ambiguity":
            raise ledger.McpInvocationError("synthetic lost authorization commit receipt")
        return admitted

    monkeypatch.setattr(transport, "authorize_mutation_dispatch", authorize)
    arguments = {"resource": "fixture", "project_id": "A", "idempotency_key": "linearization-fixture"}
    token = transport._current_principal.set(principal)
    pending = asyncio.create_task(transport._call_tool(entry.name, arguments))
    transport._current_principal.reset(token)
    try:
        await asyncio.wait_for(barrier.wait(), timeout=10)
        issued = SimpleNamespace(
            client=consent.client, client_id=consent.client_id, refresh_token=tokens["refresh_token"]
        )
        next_tokens = None
        if change == "access-expiry":
            async with consent.factory() as session:
                expires_at = await session.scalar(
                    select(McpOAuthToken.expires_at).where(
                        McpOAuthToken.token_hash == hash_oauth_value(tokens["access_token"])
                    )
                )
            after_expiry = expires_at.replace(tzinfo=UTC) + timedelta(seconds=1)
            monkeypatch.setattr(oauth_authority, "_now", lambda: after_expiry)
            with pytest.raises(authentication.McpAuthenticationError):
                await authentication.verify_mcp_bearer(tokens["access_token"], urls=_URLS)
        else:
            rotated = await refresh(
                issued,
                client_id=issued.client_id,
                scope="mcp:read" if change == "narrow-refresh" else None,
            )
            assert rotated.status_code == 200
            next_tokens = rotated.json()
        release.set()
        if expected_writes:
            result = await pending
            assert result == {"accepted": True}
        elif change == "commit-ambiguity":
            with pytest.raises(ledger.McpInvocationError) as failure:
                await pending
            assert not isinstance(failure.value, ledger.McpMutationAuthorizationDenied)
        else:
            with pytest.raises(ledger.McpMutationAuthorizationDenied):
                await pending
        assert len(writes) == expected_writes
        async with consent.factory() as session:
            invocation = await session.scalar(
                select(McpToolInvocation).where(
                    McpToolInvocation.grant_id == grant_id,
                    McpToolInvocation.idempotency_key == "linearization-fixture",
                )
            )
            expected_state = (
                "dispatch_authorized"
                if change == "commit-ambiguity"
                else ("succeeded" if expected_writes else "failed")
            )
            assert invocation.status == expected_state
            assert (invocation.sent_at is not None) is (bool(expected_writes) or change == "commit-ambiguity")
        if change == "access-expiry":
            rotated = await refresh(issued, client_id=issued.client_id)
            assert rotated.status_code == 200
            next_tokens = rotated.json()
        replay_principal = await authentication.verify_mcp_bearer(next_tokens["access_token"], urls=_URLS)
        token = transport._current_principal.set(replay_principal)
        try:
            if change == "narrow-refresh":
                with pytest.raises(ValueError, match="unavailable"):
                    await transport._call_tool(entry.name, arguments)
            elif change == "commit-ambiguity":
                with pytest.raises(ledger.McpInvocationError):
                    await transport._call_tool(entry.name, arguments)
            else:
                assert await transport._call_tool(entry.name, arguments) == {"accepted": True}
        finally:
            transport._current_principal.reset(token)
        assert len(writes) == expected_writes
    finally:
        release.set()
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        await asyncio.to_thread(provider.shutdown)
        provider.server_close()
        worker.join(timeout=5)


@pytest.mark.parametrize("producer", ["mcp", "lumen"])
async def test_expired_preview_lease_commits_known_failure_and_requires_new_key(oauth_consent, monkeypatch, producer):
    from fastapi import HTTPException

    from app.api import mcp_lumen
    from app.services.mcp_control_plane import authentication, authority, ledger, registry, transport

    consent = oauth_consent
    issued = await authority.issue_personal_token(
        consent.factory,
        conn=consent.conn,
        owner_user_id=consent.owner,
        owner_project_id="A",
        username="owner",
        roles=["member"],
        display_name="lease proof",
        access_level="manage",
    )
    monkeypatch.setattr(authentication, "get_session_factory", lambda: consent.factory)
    monkeypatch.setattr(ledger, "get_session_factory", lambda: consent.factory)
    if producer == "lumen":
        generation = await authority.set_lumen_selection(
            consent.factory,
            owner_user_id=consent.owner,
            owner_project_id="A",
            username="owner",
            grant_id=issued.grant_id,
        )
        principal = authentication.McpPrincipal(
            grant_id=issued.grant_id,
            user_id=consent.owner,
            project_id="A",
            credential_epoch=1,
            scopes=frozenset({"mcp:read", "mcp:write"}),
            source="lumen",
            selection_generation=generation,
        )
    else:
        principal = await authentication.verify_mcp_bearer(issued.token, urls=_URLS)
    writes, terminalization_calls = [], []
    first_preview = True

    class Output(registry.McpDomainOutput):
        accepted: bool

    async def preview(_context, _arguments):
        nonlocal first_preview
        if first_preview:
            first_preview = False
            async with consent.factory() as session, session.begin():
                invocation = await session.scalar(
                    select(McpToolInvocation)
                    .where(
                        McpToolInvocation.grant_id == issued.grant_id,
                        McpToolInvocation.idempotency_key == "expired-preview-key",
                    )
                    .with_for_update()
                )
                invocation.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        return registry.McpMutationPreview(
            resource_identity="fixture",
            current_state="ready",
            intended_transition="change",
            dependent_resources=[],
            destructive=False,
            estimated_effect=None,
            fingerprint="fixture",
        )

    async def handler(_context, _arguments):
        writes.append("accepted synthetic provider mutation")
        return Output(accepted=True)

    entry = registry.RegistryEntry(
        name="afterglow_expired_preview_fixture",
        description="lease proof",
        arguments=registry.McpDomainArguments,
        output=Output,
        minimum_scope="mcp:write",
        effect="external_mutation",
        service_flag=None,
        timeout_seconds=10,
        result_max_bytes=1024,
        handler=handler,
        preview_builder=preview,
    )
    monkeypatch.setattr(transport, "entry_by_name", lambda name: entry if name == entry.name else None)
    real_fail = ledger.fail_pre_dispatch

    async def fail(*args, **kwargs):
        terminalization_calls.append(kwargs["invocation_id"])
        return await real_fail(*args, **kwargs)

    monkeypatch.setattr(ledger, "fail_pre_dispatch", fail)
    monkeypatch.setattr(transport, "fail_pre_dispatch", fail)

    async def invoke(key):
        if producer == "lumen":
            return await mcp_lumen._execute_tool(
                principal,
                entry=entry,
                body=mcp_lumen._ExecuteRequest(
                    snapshot={},
                    name=entry.name,
                    arguments={"project_id": "A"},
                    idempotency_key=key,
                ),
            )
        token = transport._current_principal.set(principal)
        try:
            return await transport._call_tool(entry.name, {"project_id": "A", "idempotency_key": key})
        finally:
            transport._current_principal.reset(token)

    if producer == "lumen":
        with pytest.raises(HTTPException) as denied:
            await invoke("expired-preview-key")
        assert denied.value.status_code == 409
        assert isinstance(denied.value.__cause__, ledger.McpMutationPreDispatchExpired)
    else:
        with pytest.raises(ledger.McpMutationPreDispatchExpired):
            await invoke("expired-preview-key")
    assert writes == [] and terminalization_calls == []
    async with consent.factory() as session:
        failed = await session.scalar(
            select(McpToolInvocation).where(
                McpToolInvocation.grant_id == issued.grant_id,
                McpToolInvocation.idempotency_key == "expired-preview-key",
            )
        )
        assert failed.status == "failed" and "lease expired" in failed.error
        assert failed.sent_at is None and failed.dispatch_authorized_at is None and failed.lease_expires_at is None
    with pytest.raises(HTTPException if producer == "lumen" else ledger.McpInvocationError):
        await invoke("expired-preview-key")
    assert writes == [] and terminalization_calls == []
    assert await invoke("explicit-new-preview-key") == {"accepted": True}
    assert await invoke("explicit-new-preview-key") == {"accepted": True}
    assert len(writes) == 1 and terminalization_calls == []


@pytest.mark.parametrize("state", ["claimed", "dispatch_authorized"])
async def test_local_scrub_candidate_with_missing_live_lease_remains_unresolved(oauth_consent, state):
    from app.services.mcp_control_plane import oauth_authority
    from app.services.mcp_control_plane.cleanup import _scrub_terminal_ongoing_secrets

    consent = oauth_consent
    _, tokens, grant_id = await approve_and_exchange(consent, ongoing=True, access_level="manage")
    invocation_id = str(uuid4())
    async with consent.factory() as session, session.begin():
        session.add(
            McpToolInvocation(
                id=invocation_id,
                grant_id=grant_id,
                source="mcp",
                tool_name="afterglow_vm_action",
                idempotency_key="missing-live-lease",
                arguments_hash="a" * 64,
                registry_version="test",
                status=state,
                lease_expires_at=None,
            )
        )
    await oauth_authority.revoke_oauth_token(consent.factory, token=tokens["access_token"])
    await _scrub_terminal_ongoing_secrets(consent.factory, now=datetime.now(UTC))
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        invocation = await session.get(McpToolInvocation, invocation_id)
        assert grant.credential_ciphertext and grant.cleanup_pending
        assert invocation.status == state and invocation.lease_expires_at is None


@pytest.mark.parametrize(
    "status,nonce,grace_future",
    [("pending", True, False), ("revoked", True, False), ("revoked", False, True)],
)
async def test_local_scrub_preserves_uncertain_unactivated_ongoing_issuance(oauth_consent, status, nonce, grace_future):
    from app.services.mcp_control_plane.cleanup import sweep_delegated_authority
    from app.services.mcp_control_plane.crypto import encrypt_application_credential

    consent = oauth_consent
    grant_id, credential_id = str(uuid4()), "partial-" + str(uuid4())
    recovery_nonce = str(uuid4()) if nonce else None
    ciphertext = encrypt_application_credential(
        "partial-issuance-fixture",
        grant_id=grant_id,
        owner_user_id=consent.owner,
        owner_project_id="A",
    )
    async with consent.factory() as session, session.begin():
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id=consent.owner,
                owner_project_id="A",
                upstream_credential_name="afterglow-mcp-" + grant_id,
                display_name="partial issuance SQL snapshot",
                source="oauth",
                access_level="manage",
                project_scope="current",
                approved_projects=[{"id": "A", "name": "Project A", "roles": ["member"], "can_write": True}],
                oauth_ongoing=True,
                issued_role_ceiling={"A": [{"id": "role-member", "name": "member"}]},
                status=status,
                expires_at=None,
                issued_at=None,
                cleanup_pending=True,
                application_credential_id=credential_id,
                credential_ciphertext=ciphertext,
                orphan_recovery_nonce=recovery_nonce,
                orphan_recovery_after=datetime.now(UTC) + timedelta(hours=1 if grace_future else -1),
            )
        )
    await sweep_delegated_authority(consent.factory)
    async with consent.factory() as session:
        grant = await session.get(McpDelegatedGrant, grant_id)
        assert grant.status == status and grant.issued_at is None
        assert grant.credential_ciphertext == ciphertext and grant.application_credential_id == credential_id
        assert grant.cleanup_pending and grant.orphan_recovery_nonce == recovery_nonce


@pytest.mark.parametrize("project_scope", ["selected", "all"])
async def test_oauth_consent_never_combines_projects_from_multiple_domains(oauth_consent, monkeypatch, project_scope):
    from app.services.mcp_control_plane.authority import McpAuthorityError
    from app.services.mcp_control_plane.oauth_authority import approve_consent_ticket

    consent = oauth_consent
    original_get = consent.conn.session.get

    def memberships(url, **kwargs):
        response = original_get(url, **kwargs)
        payload = response.json()
        for project in payload["projects"]:
            if project["id"] == "B":
                project["domain_id"] = "other-domain"
        return SimpleNamespace(raise_for_status=response.raise_for_status, json=lambda: payload)

    monkeypatch.setattr(consent.conn.session, "get", memberships)
    if project_scope == "selected":
        with pytest.raises(McpAuthorityError, match="selected project"):
            await approve_consent_ticket(
                consent.factory,
                ticket=consent.ticket,
                owner_user_id=consent.owner,
                owner_project_id="A",
                username="owner",
                roles=["member"],
                conn=consent.conn,
                access_level="read",
                project_scope="selected",
                project_ids=["A", "B"],
            )
        assert consent.created == [] and consent.remote == {}
    else:
        _, _, grant_id = await approve_and_exchange(consent, access_level="read", project_scope="all")
        async with consent.factory() as session:
            grant = await session.get(McpDelegatedGrant, grant_id)
            assert [project["id"] for project in grant.approved_projects] == ["A"]
        assert [project for project, _, _ in consent.created] == ["A"]
