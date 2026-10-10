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
    principal = McpPrincipal(
        grant_id=issued.grant_id,
        user_id="owner-" + issued.grant_id,
        project_id="project",
        credential_epoch=1,
        scopes=frozenset(("mcp:read", "mcp:write")),
        source="oauth",
    )
    invocation_id = str(uuid4())
    now = datetime.now(UTC)
    async with issued.factory() as session, session.begin():
        grant = await session.get(McpDelegatedGrant, issued.grant_id)
        grant.access_level = "manage"
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


async def test_refresh_wrong_resource_cannot_rotate_or_revoke(issued_refresh):
    before = await security_state(issued_refresh)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id, resource=_URLS.resource + "/other")
    assert rejected.status_code == 400
    assert await security_state(issued_refresh) == before


async def test_oauth_revocation_blocks_access_and_refresh(issued_refresh):
    from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token

    revoked = await issued_refresh.client.post("/api/v1/mcp/oauth/revoke", data={"token": issued_refresh.access_token})
    assert revoked.status_code == 200
    async with issued_refresh.factory() as session, session.begin():
        with pytest.raises(McpOAuthAuthorityError, match="invalid"):
            await resolve_oauth_access_token(session, raw_token=issued_refresh.access_token, resource=_URLS.resource)
    rejected = await refresh(issued_refresh, client_id=issued_refresh.client_id)
    assert rejected.status_code == 400


@pytest.fixture
async def oauth_consent(issued_refresh, monkeypatch):
    from app.services import k3s_crypto, keystone
    from app.services.mcp_control_plane.oauth_authority import (
        create_authorization_ticket,
        load_consent_ticket,
        register_public_client,
    )

    monkeypatch.setattr(k3s_crypto, "get_settings", lambda: SimpleNamespace(k3s_kubeconfig_encryption_key="a" * 64))
    monkeypatch.setattr(
        "app.config.get_settings", lambda: SimpleNamespace(os_auth_url="https://keystone.example.test/v3")
    )
    owner = "consent-" + str(uuid4())
    memberships = {"A": ["member"], "B": ["reader"]}
    created = []
    connections = []
    remote = {}

    class CallerConnection:
        def __init__(self, project_id):
            self._afterglow_user_id = owner
            self._afterglow_project_id = project_id
            self._afterglow_token = "caller-token"
            self.closed = False
            self.identity = self
            self.session = SimpleNamespace(
                auth=SimpleNamespace(
                    get_access=lambda session: SimpleNamespace(
                        user_id=owner,
                        project_id=project_id,
                        project_name="Project " + project_id,
                        role_names=memberships[project_id],
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
                    "projects": [{"id": project_id, "name": "Project " + project_id} for project_id in memberships]
                },
            )

        def create_application_credential(self, **kwargs):
            assert kwargs["user"] == owner
            assert kwargs["unrestricted"] is False
            assert kwargs["roles"] == [{"name": role} for role in memberships[self._afterglow_project_id]]
            credential = SimpleNamespace(
                id=str(uuid4()),
                secret="secret-" + self._afterglow_project_id,
                name=kwargs["name"],
                project_id=self._afterglow_project_id,
            )
            created.append((self._afterglow_project_id, kwargs["name"], credential.id))
            remote[credential.id] = credential
            return credential

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
