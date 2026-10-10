"""Exercise saved runtime authority, target binding, credential loading and replay."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

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
def runtime(monkeypatch):
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
    return state


def mutation_entry():
    return registry.entry_by_name("afterglow_vm_action")


def mutation_arguments(project_id=None):
    return registry.VmActionArguments(
        server_id="12345678-1234-1234-1234-123456789abc", action="stop", project_id=project_id
    )


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
    runtime.token = None
    principal = replace(
        runtime.principal, source="lumen", selection_generation=4, selection_project_id="chat", project_id="b"
    )
    assert await connection._load_credential(principal) == ("credential-b", "secret-b")
    claim = await ledger.claim_mutation(
        principal, entry=mutation_entry(), arguments={"action": "stop"}, idempotency_key="lumen-key", source="lumen"
    )
    assert runtime.token_reads == 0
    assert {("user", "a"), ("user", "chat")} == set(runtime.locks)
    assert all(key["owner_project_id"] == "chat" for key in runtime.selection_keys)
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
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "chat", 1, 4)
    if change == "pat_revoked":
        runtime.token.revoked_at = datetime.now(UTC)
    else:
        runtime.grant.source = "lumen"
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
    runtime.grant.source = "lumen"
    runtime.token = None
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
        runtime.grant.source = "lumen"
        runtime.token = None
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
        runtime.grant.source = "lumen"
        runtime.token = None
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
    snapshot = lumen.LumenGrantSnapshot("grant", "user", "chat", 1, 4)
    assert await lumen.selected_lumen_metadata(snapshot) == {
        "access_level": "manage",
        "project_id": "a",
        "project_name": "Alpha",
        "source": source,
        "allowed_projects": [{"id": "a", "name": "Alpha"}, {"id": "b", "name": "Beta"}],
        "selection_name": None if source == "lumen" else "Selected grant",
    }
    runtime.owner_lock.lumen_selection_generation += 1
    with pytest.raises(lumen.McpLumenAuthorityError):
        await lumen.selected_lumen_metadata(snapshot)
