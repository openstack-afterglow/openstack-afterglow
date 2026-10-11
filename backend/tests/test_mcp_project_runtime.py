"""Exercise saved runtime authority, target binding, credential loading and replay."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest
from fastapi import HTTPException

from app.api import mcp_lumen
from app.models.mcp_authority import McpDelegatedGrant, McpPersonalToken, McpProjectCredential, McpToolInvocation
from app.services.mcp_control_plane import (
    authentication,
    authority,
    connection,
    crypto,
    ledger,
    limits,
    lumen,
    registry,
    transport,
)


class MemorySession:
    """Only storage is substituted; production authority and dispatch run unchanged."""

    def __init__(self, state):
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def begin(self):
        return self

    async def get(self, model, key, **kwargs):
        self.state.selection_keys.append(key)
        return self.state.selection

    async def scalar(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        params = statement.compile().params
        if entity is McpDelegatedGrant:
            assert params["owner_project_id_1"] == self.state.grant.owner_project_id
            return self.state.grant
        if entity is McpPersonalToken:
            self.state.token_reads += 1
            return self.state.token
        if entity is McpProjectCredential:
            target = params["project_id_1"]
            self.state.credential_reads.append(target)
            return self.state.credentials.get(target)
        if entity is McpToolInvocation:
            for row in self.state.invocations:
                if "id_1" in params and row.id == params["id_1"]:
                    return row
                if "idempotency_key_1" in params and row.idempotency_key == params["idempotency_key_1"]:
                    return row
                if (
                    "arguments_hash_1" in params
                    and row.arguments_hash == params["arguments_hash_1"]
                    and row.status in {"claimed", "dispatch_authorized", "unknown"}
                ):
                    return row
            return None
        raise AssertionError(entity)

    async def execute(self, statement):
        return SimpleNamespace(
            one_or_none=lambda: (self.state.selection, self.state.grant, self.state.token, self.state.owner_lock)
        )

    def add(self, row):
        self.state.invocations.append(row)


@pytest.fixture
async def runtime(monkeypatch):
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def redis_client():
        return redis

    monkeypatch.setattr(limits, "_get_redis", redis_client)
    monkeypatch.setattr(crypto, "derive_encryption_subkey", lambda _: b"k" * 32)
    saved = [
        {"id": "a", "name": "Alpha", "roles": ["member"], "can_write": True},
        {"id": "b", "name": "Beta", "roles": ["member"], "can_write": True},
    ]
    grant = SimpleNamespace(
        id="grant",
        owner_user_id="user",
        owner_project_id="a",
        source="personal_token",
        status="active",
        access_level="manage",
        credential_epoch=1,
        project_scope="selected",
        consented_at=None,
        cleanup_pending=False,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        approved_projects=saved,
        application_credential_id="credential-a",
        credential_ciphertext=crypto.encrypt_application_credential(
            "secret-a", grant_id="grant", owner_user_id="user", owner_project_id="a"
        ),
    )
    credential = SimpleNamespace(
        grant_id="grant",
        project_id="b",
        application_credential_id="credential-b",
        cleanup_pending=False,
        credential_ciphertext=crypto.encrypt_application_credential(
            "secret-b", grant_id="grant", owner_user_id="user", owner_project_id="b"
        ),
    )
    state = SimpleNamespace(
        grant=grant,
        token=SimpleNamespace(grant_id="grant", revoked_at=None),
        credentials={"b": credential},
        selection=SimpleNamespace(grant_id="grant"),
        owner_lock=SimpleNamespace(lumen_selection_generation=4),
        locks=[],
        selection_keys=[],
        credential_reads=[],
        token_reads=0,
        invocations=[],
    )

    def factory():
        return MemorySession(state)

    for module in (authentication, connection, registry, ledger, lumen):
        monkeypatch.setattr(module, "get_session_factory", lambda: factory)

    async def lock(session, *, owner_user_id, owner_project_id):
        state.locks.append((owner_user_id, owner_project_id))
        return state.owner_lock

    monkeypatch.setattr(authentication, "lock_owner", lock)
    monkeypatch.setattr(ledger, "lock_owner", lock)
    state.principal = authentication.McpPrincipal(
        grant_id="grant",
        user_id="user",
        project_id="a",
        owner_project_id="a",
        credential_epoch=1,
        scopes=frozenset({"mcp:read", "mcp:write"}),
        source="personal_token",
    )
    try:
        yield state
    finally:
        await redis.close()


def mutation_entry():
    return registry.entry_by_name("afterglow_vm_action")


def mutation_arguments(project_id=None):
    return registry.VmActionArguments(
        server_id="12345678-1234-1234-1234-123456789abc", action="stop", project_id=project_id
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "implicit",
        "missing_marker",
        "selected",
        "all",
        "multiple",
        "foreign_selection",
        "missing_credential_id",
        "missing_ciphertext",
        "cleanup_pending",
    ],
)
async def test_internal_lumen_selection_requires_explicit_exact_current_project_consent(runtime, invalid):
    runtime.grant.source = "lumen"
    runtime.grant.project_scope = "current"
    runtime.grant.consented_at = datetime.now(UTC)
    runtime.token = None
    projects = runtime.grant.approved_projects
    runtime.grant.approved_projects = projects[:1]
    project_id = "a"
    if invalid == "implicit":
        runtime.grant.consented_at = None
    elif invalid == "missing_marker":
        del runtime.grant.consented_at
    elif invalid in {"selected", "all"}:
        runtime.grant.project_scope = invalid
    elif invalid == "multiple":
        runtime.grant.approved_projects = projects
    elif invalid == "missing_credential_id":
        runtime.grant.application_credential_id = None
    elif invalid == "missing_ciphertext":
        runtime.grant.credential_ciphertext = None
    elif invalid == "cleanup_pending":
        runtime.grant.cleanup_pending = True
    else:
        project_id = "chat"
    assert await lumen.selected_lumen_snapshot(user_id="user", project_id=project_id) is None
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.resolve_lumen_principal(lumen.LumenGrantSnapshot("grant", "user", project_id, 1, 4))
    principal = replace(runtime.principal, source="lumen", selection_generation=4, selection_project_id=project_id)
    with pytest.raises(authentication.McpAuthenticationError, match="consent"):
        await authentication.lock_principal_grant(MemorySession(runtime), principal)


@pytest.mark.asyncio
async def test_frozen_pre_cutover_lumen_principal_cannot_load_secret_preview_or_execute(runtime):
    runtime.grant.source = "lumen"
    runtime.grant.project_scope = "current"
    runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
    runtime.token = None
    # A durable principal issued by the pre-consent writer has valid epochs and
    # generation, but its persisted grant has no explicit approval marker.
    frozen = replace(runtime.principal, source="lumen", selection_generation=4, selection_project_id="a")
    called = AsyncMock(side_effect=AssertionError("implicit authority reached cloud work"))
    entry = replace(mutation_entry(), handler=called, preview_builder=called)
    for invoke in (registry.dispatch, registry.build_mutation_preview):
        with pytest.raises(authentication.McpAuthenticationError, match="consent"):
            await invoke(registry.ConsumerCloudContext(frozen), entry=entry, arguments=mutation_arguments("a"))
    with pytest.raises(connection.McpConsumerConnectionError):
        await connection._load_credential(frozen)
    with pytest.raises(ledger.McpInvocationError):
        await ledger.claim_mutation(
            frozen,
            entry=entry,
            arguments={"action": "stop", "project_id": "a"},
            idempotency_key="pre-cutover",
            source="lumen",
        )
    called.assert_not_awaited()
    assert runtime.invocations == []
    assert runtime.credential_reads == []


@pytest.mark.asyncio
async def test_lumen_consent_is_rechecked_at_locked_mutation_dispatch(runtime):
    runtime.grant.source = "lumen"
    runtime.grant.project_scope = "current"
    runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
    runtime.grant.consented_at = datetime.now(UTC)
    runtime.token = None
    frozen = replace(runtime.principal, source="lumen", selection_generation=4, selection_project_id="a")
    claim = await ledger.claim_mutation(
        frozen,
        entry=mutation_entry(),
        arguments={"action": "stop", "project_id": "a"},
        idempotency_key="consented-claim",
        source="lumen",
    )
    runtime.grant.consented_at = None
    with pytest.raises(ledger.McpInvocationError):
        await ledger.authorize_mutation_dispatch(frozen, invocation_id=claim.invocation_id, source="lumen")
    assert runtime.invocations[0].status == "claimed"


@pytest.mark.asyncio
async def test_consented_internal_lumen_cannot_target_another_project(runtime):
    runtime.grant.source = "lumen"
    runtime.grant.project_scope = "current"
    runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
    runtime.grant.consented_at = datetime.now(UTC)
    runtime.token = None
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "a", 1, 4)
    principal = await lumen.resolve_lumen_principal(snapshot)
    assert principal.project_id == principal.anchor_project_id == principal.selection_project_id == "a"
    with pytest.raises(authentication.McpAuthenticationError, match="consent"):
        await authentication.resolve_principal_target(principal, "b", write=True)
    with pytest.raises(connection.McpConsumerConnectionError):
        await connection._load_credential(replace(principal, project_id="b"))
    assert runtime.credential_reads == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["a", "b"])
async def test_saved_scope_routes_target_but_locks_owner_anchor(runtime, target):
    principal = await authentication.resolve_principal_target(runtime.principal, target)
    assert principal.project_id == target
    assert principal.anchor_project_id == "a"
    assert await connection._load_credential(principal) == (f"credential-{target}", f"secret-{target}")
    assert set(runtime.locks) == {("user", "a")}
    assert runtime.credential_reads == ([] if target == "a" else ["b"])


@pytest.mark.asyncio
async def test_selected_scope_rejects_unapproved_target_before_preview_dispatch_or_secret(runtime):
    called = AsyncMock()
    entry = replace(mutation_entry(), handler=called, preview_builder=called)
    context = registry.ConsumerCloudContext(runtime.principal)
    for invoke in (registry.dispatch, registry.build_mutation_preview):
        with pytest.raises(authority.McpGrantStateError, match="approved scope"):
            await invoke(context, entry=entry, arguments=mutation_arguments("c"))
    with pytest.raises(authority.McpGrantStateError):
        await connection._load_credential(replace(runtime.principal, project_id="c"))
    called.assert_not_awaited()
    assert runtime.credential_reads == []


@pytest.mark.asyncio
async def test_read_token_and_saved_read_project_reject_mutation(runtime):
    read = replace(runtime.principal, scopes=frozenset({"mcp:read"}))
    with pytest.raises(authentication.McpAuthenticationError):
        await authentication.resolve_principal_target(read, "b", write=True)
    runtime.grant.approved_projects[1]["can_write"] = False
    with pytest.raises(authority.McpGrantStateError, match="management"):
        await authentication.resolve_principal_target(runtime.principal, "b", write=True)
    runtime.grant.access_level = "read"
    with pytest.raises(authority.McpGrantStateError, match="management"):
        await authentication.resolve_principal_target(runtime.principal, "a", write=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["a", "b"])
@pytest.mark.parametrize("change", ["revoked", "expired", "epoch", "pat_revoked"])
async def test_stale_or_inactive_authority_blocks_every_target(runtime, target, change):
    if change == "revoked":
        runtime.grant.status = "revoked"
    elif change == "expired":
        runtime.grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    elif change == "epoch":
        runtime.grant.credential_epoch += 1
    else:
        runtime.token.revoked_at = datetime.now(UTC)
    with pytest.raises(authentication.McpAuthenticationError):
        await authentication.resolve_principal_target(runtime.principal, target)
    with pytest.raises((authority.McpGrantStateError, connection.McpConsumerConnectionError)):
        await connection._load_credential(replace(runtime.principal, project_id=target))
    with pytest.raises(ledger.McpInvocationError):
        await ledger.claim_mutation(
            replace(runtime.principal, project_id=target),
            entry=mutation_entry(),
            arguments={"action": "stop"},
            idempotency_key="blocked-key",
        )
    assert runtime.credential_reads == []
    assert runtime.invocations == []


@pytest.mark.asyncio
async def test_mutation_default_target_replays_but_other_project_cannot(runtime):
    entry = mutation_entry()
    claim = await ledger.claim_mutation(
        runtime.principal, entry=entry, arguments={"action": "stop"}, idempotency_key="same-key"
    )
    await ledger.authorize_mutation_dispatch(runtime.principal, invocation_id=claim.invocation_id)
    await ledger.complete_mutation(runtime.principal, invocation_id=claim.invocation_id, result={"status": "accepted"})
    replay = await ledger.claim_mutation(
        runtime.principal, entry=entry, arguments={"action": "stop", "project_id": "a"}, idempotency_key="same-key"
    )
    assert replay.state == "replay" and replay.result == {"status": "accepted"}
    with pytest.raises(ledger.McpInvocationError, match="different arguments"):
        await ledger.claim_mutation(
            replace(runtime.principal, project_id="b"),
            entry=entry,
            arguments={"action": "stop", "project_id": "b"},
            idempotency_key="same-key",
        )
    assert len(runtime.invocations) == 1


@pytest.mark.asyncio
async def test_internal_lumen_without_pat_fences_selection_at_connection_and_ledger(runtime):
    runtime.grant.source = "lumen"
    runtime.grant.consented_at = datetime.now(UTC)
    runtime.grant.project_scope = "current"
    runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
    runtime.token = None
    principal = replace(runtime.principal, source="lumen", selection_generation=4, selection_project_id="a")
    assert await connection._load_credential(principal) == ("credential-a", "secret-a")
    claim = await ledger.claim_mutation(
        principal, entry=mutation_entry(), arguments={"action": "stop"}, idempotency_key="lumen-key", source="lumen"
    )
    assert runtime.token_reads == 0
    assert {("user", "a")} == set(runtime.locks)
    assert all(key["owner_project_id"] == "a" for key in runtime.selection_keys)
    runtime.owner_lock.lumen_selection_generation += 1
    with pytest.raises(connection.McpConsumerConnectionError):
        await connection._load_credential(principal)
    with pytest.raises(ledger.McpInvocationError):
        await ledger.authorize_mutation_dispatch(principal, invocation_id=claim.invocation_id, source="lumen")
    assert runtime.invocations[0].status == "claimed"


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["a", "b"])
@pytest.mark.parametrize("change", ["selection", "revoked", "expired", "epoch", "pat_revoked"])
async def test_stale_lumen_snapshot_cannot_execute_any_target(runtime, target, change):
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "a", 1, 4)
    if change == "pat_revoked":
        runtime.token.revoked_at = datetime.now(UTC)
    else:
        runtime.grant.source = "lumen"
        runtime.grant.consented_at = datetime.now(UTC)
        runtime.grant.project_scope = "current"
        runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
        runtime.token = None
        if change == "selection":
            runtime.owner_lock.lumen_selection_generation += 1
        elif change == "revoked":
            runtime.grant.status = "revoked"
        elif change == "expired":
            runtime.grant.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        else:
            runtime.grant.credential_epoch += 1
    with pytest.raises(HTTPException) as rejected:
        await mcp_lumen.execute(
            mcp_lumen._ExecuteRequest(
                snapshot=lumen.snapshot_payload(snapshot),
                name="afterglow_vm_action",
                arguments=mutation_arguments(target).model_dump(mode="json"),
                idempotency_key="snapshot-key",
            ),
            None,
        )
    assert rejected.value.status_code == 403


@pytest.mark.asyncio
async def test_lumen_snapshot_shape_retains_actor_anchor_not_target(runtime):
    runtime.grant.approved_projects = runtime.grant.approved_projects[1:]
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "chat", 1, 4)
    principal = await lumen.resolve_lumen_principal(snapshot)
    assert principal.project_id == "b" and principal.anchor_project_id == "a"
    assert principal.selection_project_id == "chat"
    assert set(lumen.snapshot_payload(snapshot)) == {
        "grant_id",
        "user_id",
        "project_id",
        "credential_epoch",
        "selection_generation",
    }
    assert lumen.snapshot_payload(snapshot)["project_id"] == "chat"


@pytest.mark.asyncio
async def test_projects_tool_returns_only_saved_public_metadata(runtime):
    entry = registry.entry_by_name("afterglow_projects_list")
    result = await registry.dispatch(
        registry.ConsumerCloudContext(runtime.principal), entry=entry, arguments=entry.arguments()
    )
    assert registry.output_payload(entry, result) == {
        "projects": [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}]
    }
    runtime.grant.approved_projects = None
    result = await registry.dispatch(
        registry.ConsumerCloudContext(runtime.principal), entry=entry, arguments=entry.arguments()
    )
    assert [item.id for item in result.projects] == ["a"]
    with pytest.raises(authority.McpGrantStateError):
        await authentication.resolve_principal_target(runtime.principal, "b")


def test_every_tool_schema_accepts_optional_project_id_without_widening_outputs():
    for entry in registry.registry_entries():
        schema = entry.input_schema()
        assert "project_id" in schema["properties"]
        assert "project_id" not in schema.get("required", [])
        assert schema["additionalProperties"] is False
        with pytest.raises(Exception):
            entry.arguments.model_validate({"project_id": ""})


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
async def test_transport_binds_canonical_target_before_mutation_claim(runtime, monkeypatch, surface):
    claim = AsyncMock(return_value=ledger.MutationClaim("replay", "invocation", {"status": "accepted"}))
    arguments = mutation_arguments("b").model_dump(mode="json")
    if surface == "mcp":
        monkeypatch.setattr(transport, "claim_mutation", claim)
        token = transport._current_principal.set(runtime.principal)
        try:
            await transport._call_tool("afterglow_vm_action", {**arguments, "idempotency_key": "surface-key"})
        finally:
            transport._current_principal.reset(token)
    else:
        monkeypatch.setattr(ledger, "claim_mutation", claim)
        snapshot = lumen.LumenGrantSnapshot("grant", "user", "a", 1, 4)
        await mcp_lumen.execute(
            mcp_lumen._ExecuteRequest(
                snapshot=lumen.snapshot_payload(snapshot),
                name="afterglow_vm_action",
                arguments=arguments,
                idempotency_key="surface-key",
            ),
            None,
        )
    assert claim.await_args.args[0].project_id == "b"
    assert claim.await_args.args[0].anchor_project_id == "a"
    assert claim.await_args.kwargs["arguments"]["project_id"] == "b"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["missing", "moved", "ciphertext", "cleanup"])
async def test_project_credential_must_match_exact_grant_and_target(runtime, change):
    credential = runtime.credentials["b"]
    if change == "missing":
        runtime.credentials.clear()
    elif change == "moved":
        credential.grant_id = "other-grant"
    elif change == "ciphertext":
        credential.credential_ciphertext = runtime.grant.credential_ciphertext
    else:
        credential.cleanup_pending = True
    with pytest.raises((authority.McpGrantStateError, connection.McpConsumerConnectionError)):
        await connection._load_credential(replace(runtime.principal, project_id="b"))


@pytest.mark.asyncio
async def test_bearer_default_uses_first_saved_project_if_anchor_not_approved(runtime, monkeypatch):
    runtime.grant.approved_projects = runtime.grant.approved_projects[1:]
    monkeypatch.setattr(authentication, "resolve_personal_token", AsyncMock(return_value=runtime.grant))
    principal = await authentication.verify_mcp_bearer("mcp-afgl-synthetic", urls=SimpleNamespace())
    assert principal.project_id == "b" and principal.anchor_project_id == "a"
    with pytest.raises(authority.McpGrantStateError):
        await authentication.resolve_principal_target(principal, "a")


@pytest.mark.asyncio
async def test_all_scope_uses_saved_snapshot_not_future_memberships(runtime):
    runtime.grant.project_scope = "all"
    with pytest.raises(authority.McpGrantStateError):
        await authentication.resolve_principal_target(runtime.principal, "c")
    entry = mutation_entry()
    principal, omitted = await registry.bind_entry_target(
        runtime.principal, entry=entry, arguments=mutation_arguments()
    )
    explicit_principal, explicit = await registry.bind_entry_target(
        runtime.principal, entry=entry, arguments=mutation_arguments("a")
    )
    assert principal == explicit_principal
    assert ledger.canonical_arguments_hash(omitted.model_dump(mode="json")) == ledger.canonical_arguments_hash(
        explicit.model_dump(mode="json")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
async def test_unapproved_target_cannot_reach_transport_mutation_replay(runtime, monkeypatch, surface):
    claim = AsyncMock(side_effect=AssertionError("unapproved target reached replay lookup"))
    arguments = mutation_arguments("c").model_dump(mode="json")
    if surface == "mcp":
        monkeypatch.setattr(transport, "claim_mutation", claim)
        token = transport._current_principal.set(runtime.principal)
        try:
            with pytest.raises(authority.McpGrantStateError):
                await transport._call_tool("afterglow_vm_action", {**arguments, "idempotency_key": "surface-key"})
        finally:
            transport._current_principal.reset(token)
    else:
        monkeypatch.setattr(ledger, "claim_mutation", claim)
        snapshot = lumen.LumenGrantSnapshot("grant", "user", "a", 1, 4)
        with pytest.raises(HTTPException) as rejected:
            await mcp_lumen.execute(
                mcp_lumen._ExecuteRequest(
                    snapshot=lumen.snapshot_payload(snapshot),
                    name="afterglow_vm_action",
                    arguments=arguments,
                    idempotency_key="surface-key",
                ),
                None,
            )
        assert rejected.value.status_code == 422
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_revoked_grant_cannot_replay_completed_mutation(runtime):
    claim = await ledger.claim_mutation(
        runtime.principal, entry=mutation_entry(), arguments={"action": "stop"}, idempotency_key="revoked-key"
    )
    await ledger.authorize_mutation_dispatch(runtime.principal, invocation_id=claim.invocation_id)
    await ledger.complete_mutation(runtime.principal, invocation_id=claim.invocation_id, result={"status": "accepted"})
    runtime.grant.status = "revoked"
    with pytest.raises(ledger.McpInvocationError):
        await ledger.claim_mutation(
            runtime.principal, entry=mutation_entry(), arguments={"action": "stop"}, idempotency_key="revoked-key"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["personal_token", "lumen"])
async def test_lumen_metadata_uses_revalidated_saved_public_projection(runtime, source):
    runtime.grant.source = source
    runtime.grant.display_name = "Selected grant"
    if source == "lumen":
        runtime.token = None
        runtime.grant.consented_at = datetime.now(UTC)
        runtime.grant.project_scope = "current"
        runtime.grant.approved_projects = runtime.grant.approved_projects[:1]
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "a" if source == "lumen" else "chat", 1, 4)
    assert await lumen.selected_lumen_metadata(snapshot) == {
        "access_level": "manage",
        "project_id": "a",
        "project_name": "Alpha",
        "source": source,
        "allowed_projects": [
            {"id": project["id"], "name": project["name"]} for project in runtime.grant.approved_projects
        ],
        "selection_name": None if source == "lumen" else "Selected grant",
        "expires_at": runtime.grant.expires_at.isoformat(),
    }
    runtime.owner_lock.lumen_selection_generation += 1
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.selected_lumen_metadata(snapshot)


_PROVISIONING_SERVER = "11111111-1111-4111-8111-111111111111"
_PROVISIONING_NETWORK = "22222222-2222-4222-8222-222222222222"
_PROVISIONING_IMAGE = "33333333-3333-4333-8333-333333333333"


@pytest.fixture
def provisioning_cloud(runtime, monkeypatch):
    from app.services.mcp_control_plane import compute

    state = SimpleNamespace(servers={}, volumes={}, ports={}, writes=[], uncertain=False)

    @asynccontextmanager
    async def cloud(context):
        project = context.project_id

        def create(kind, value):
            state.writes.append((kind, project))
            if state.uncertain:
                raise TimeoutError("provider-secret: uncertain accepted request")
            return value

        class Compute:
            def get_flavor(self, flavor_id, **_kwargs):
                return {"id": flavor_id, "name": "small", "vcpus": 1, "ram": 2048, "disk": 0, "extra_specs": {}}

            def servers(self, **_kwargs):
                return [server for server in state.servers.values() if server["project_id"] == project]

            def create_server(self, **body):
                state.servers[_PROVISIONING_SERVER] = {
                    "id": _PROVISIONING_SERVER,
                    "project_id": project,
                    "name": body["name"],
                    "status": "BUILD",
                }
                return create("vm", {"id": _PROVISIONING_SERVER, "adminPass": "provider-secret"})

            def get_server(self, server_id):
                return state.servers.get(
                    server_id, {"id": server_id, "project_id": project, "name": "existing-vm", "status": "SHUTOFF"}
                )

            def create_server_interface(self, server_id, **body):
                port = {
                    "id": "port-new",
                    "project_id": project,
                    "network_id": body["net_id"],
                    "device_id": server_id,
                    "mac_address": "fa:16:3e:00:00:01",
                }
                state.ports[port["id"]] = port
                return create("interface", {"port_id": port["id"], "net_id": body["net_id"]})

        class Storage:
            def create_volume(self, **body):
                volume = {
                    "id": "volume-new",
                    "project_id": project,
                    "name": body["name"],
                    "size": body["size"],
                    "status": "creating",
                    "metadata": {"secret": "provider-secret"},
                }
                state.volumes[volume["id"]] = volume
                return create("volume", volume)

        conn = SimpleNamespace(
            compute=Compute(),
            block_storage=Storage(),
            image=SimpleNamespace(
                get_image=lambda image_id: {
                    "id": image_id,
                    "status": "active",
                    "visibility": "public",
                    "min_disk": 1,
                    "min_ram": 0,
                }
            ),
            network=SimpleNamespace(
                get_network=lambda network_id: {"id": network_id, "project_id": project, "status": "ACTIVE"},
                get_port=lambda port_id: state.ports.get(port_id),
            ),
        )
        yield conn

    async def policy(*_args, **_kwargs):
        return None

    monkeypatch.setattr(registry.ConsumerCloudContext, "openstack_connection", cloud)
    monkeypatch.setattr(compute.flavor_eligibility, "require_flavor_eligible", policy)
    monkeypatch.setattr(compute.flavor_eligibility, "admit_flavor", policy)
    monkeypatch.setattr(compute.flavor_eligibility, "release_admission", policy)
    return state


def provisioning_arguments(tool, project="b"):
    if tool == "afterglow_vm_create":
        return {
            "project_id": project,
            "name": "consumer-vm",
            "image_id": _PROVISIONING_IMAGE,
            "flavor_id": "1",
            "network_id": _PROVISIONING_NETWORK,
            "availability_zone": "nova",
        }
    if tool == "afterglow_volume_create":
        return {"project_id": project, "name": "consumer-volume", "size_gb": 10}
    return {"project_id": project, "server_id": _PROVISIONING_SERVER, "network_id": _PROVISIONING_NETWORK}


async def invoke_provisioning(runtime, surface, tool, arguments, key):
    if surface == "mcp":
        token = transport._current_principal.set(runtime.principal)
        try:
            return await transport._call_tool(tool, {**arguments, "idempotency_key": key})
        finally:
            transport._current_principal.reset(token)
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "a", 1, 4)
    return await mcp_lumen.execute(
        mcp_lumen._ExecuteRequest(
            snapshot=lumen.snapshot_payload(snapshot), name=tool, arguments=arguments, idempotency_key=key
        ),
        None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
@pytest.mark.parametrize("tool", ["afterglow_vm_create", "afterglow_volume_create", "afterglow_vm_network_attach"])
async def test_provisioning_target_binding_and_replay_create_only_one_resource(
    runtime, provisioning_cloud, surface, tool
):
    arguments = provisioning_arguments(tool)
    result = await invoke_provisioning(runtime, surface, tool, arguments, "provision-key")
    replay = await invoke_provisioning(runtime, surface, tool, arguments, "provision-key")
    assert replay == result and "provider-secret" not in str(result)
    assert len(provisioning_cloud.writes) == 1 and provisioning_cloud.writes[0][1] == "b"
    assert runtime.invocations[0].status == "succeeded"
    assert set(runtime.locks) == {("user", "a")}
    assert (
        result.get("status")
        == {"afterglow_vm_create": "BUILD", "afterglow_volume_create": "creating", "afterglow_vm_network_attach": None}[
            tool
        ]
    )
    with pytest.raises((HTTPException, ledger.McpInvocationError)):
        await invoke_provisioning(runtime, surface, tool, {**arguments, "project_id": "a"}, "provision-key")
    assert len(provisioning_cloud.writes) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
@pytest.mark.parametrize("tool", ["afterglow_vm_create", "afterglow_volume_create", "afterglow_vm_network_attach"])
async def test_provisioning_uncertain_outcome_blocks_same_and_new_replay_keys(
    runtime, provisioning_cloud, surface, tool
):
    provisioning_cloud.uncertain = True
    arguments = provisioning_arguments(tool)
    for key in ("uncertain-key", "uncertain-key", "different-key"):
        with pytest.raises((HTTPException, ValueError, ledger.McpInvocationError)) as failure:
            await invoke_provisioning(runtime, surface, tool, arguments, key)
        assert "provider-secret" not in str(failure.value)
    assert len(provisioning_cloud.writes) == 1
    assert len(runtime.invocations) == 1 and runtime.invocations[0].status == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", ["mcp", "lumen"])
@pytest.mark.parametrize("tool", ["afterglow_vm_create", "afterglow_volume_create", "afterglow_vm_network_attach"])
@pytest.mark.parametrize("boundary", ["read", "unapproved", "readonly-project"])
async def test_provisioning_requires_saved_write_authority_for_selected_target(
    runtime, provisioning_cloud, surface, tool, boundary
):
    if boundary == "read":
        runtime.principal = replace(runtime.principal, scopes=frozenset({"mcp:read"}))
        runtime.grant.access_level = "read"
    if boundary == "readonly-project":
        runtime.grant.approved_projects[1]["can_write"] = False
    target = "c" if boundary == "unapproved" else "b"
    with pytest.raises((HTTPException, ValueError, authority.McpGrantStateError)):
        await invoke_provisioning(runtime, surface, tool, provisioning_arguments(tool, target), "denied-key")
    assert provisioning_cloud.writes == [] and runtime.invocations == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool,invalid",
    [
        ("afterglow_vm_create", {"adminPass": "provider-secret"}),
        ("afterglow_vm_create", {"user_data": "arbitrary-script"}),
        ("afterglow_vm_create", {"boot_volume_size_gb": "50"}),
        ("afterglow_vm_create", {"delete_boot_volume_on_termination": "false"}),
        ("afterglow_vm_create", {"availability_zone": "nova:host:node"}),
        ("afterglow_volume_create", {"size_gb": True}),
        ("afterglow_volume_create", {"size_gb": 16385}),
        ("afterglow_volume_create", {"image_id": _PROVISIONING_IMAGE}),
        ("afterglow_vm_network_attach", {"port_id": "existing-foreign-port"}),
        ("afterglow_vm_network_attach", {"network_id": "not-a-uuid"}),
    ],
)
async def test_provisioning_strict_arguments_fail_before_ledger_or_provider(runtime, provisioning_cloud, tool, invalid):
    with pytest.raises(ValueError):
        await invoke_provisioning(runtime, "mcp", tool, {**provisioning_arguments(tool), **invalid}, "invalid-key")
    assert provisioning_cloud.writes == [] and runtime.invocations == []
