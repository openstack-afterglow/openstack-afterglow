from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane.operations import reconcile_expired_invocation


@pytest.mark.parametrize("status", ["claimed", "dispatch_authorized"])
@pytest.mark.parametrize("lease", [None, "expired", "future"])
def test_reconcile_mutation_lease_without_authorizing_retry(status, lease):
    now = datetime.now(UTC)
    deadline = None if lease is None else now + timedelta(seconds=1 if lease == "future" else -1)
    row = SimpleNamespace(status=status, lease_expires_at=deadline, idempotency_key="original-key", error=None)
    assert reconcile_expired_invocation(row, now=now) is (lease != "future")
    assert row.status == (status if lease == "future" else "unknown")
    assert row.idempotency_key == "original-key"


@pytest.mark.parametrize("status,key", [("succeeded", "key"), ("failed", "key"), ("unknown", "key"), ("claimed", None)])
def test_reconcile_preserves_terminal_and_read_invocations(status, key):
    now = datetime.now(UTC)
    row = SimpleNamespace(status=status, idempotency_key=key, lease_expires_at=now - timedelta(seconds=1))
    assert not reconcile_expired_invocation(row, now=now)
    assert row.status == status


@pytest.mark.asyncio
@pytest.mark.parametrize("invalidated", ["project_removed", "revoked", "expired", "pat_revoked", "selection"])
@pytest.mark.parametrize("non_expiring", [False, True])
async def test_operation_poll_locks_home_and_rechecks_saved_target(monkeypatch, invalidated, non_expiring):
    from app.models.mcp_authority import McpDelegatedGrant, McpPersonalToken, McpToolInvocation
    from app.services.mcp_control_plane import authentication, operations

    now = datetime.now(UTC)
    grant = SimpleNamespace(
        id="grant",
        owner_user_id="user",
        owner_project_id="A",
        source="personal_token",
        status="active",
        expires_at=None if non_expiring else now + timedelta(hours=1),
        credential_epoch=1,
        access_level="read",
        approved_projects=[{"id": "B", "name": "Beta", "roles": ["reader"], "can_write": False}],
    )
    token = SimpleNamespace(revoked_at=None)
    selection = SimpleNamespace(grant_id="grant")
    owner_lock = SimpleNamespace(lumen_selection_generation=2)
    row = SimpleNamespace(
        id="operation",
        grant_id="grant",
        status="succeeded",
        tool_name="afterglow_vm_action",
        created_at=now,
        resource_ref=None,
        operation_ref=None,
        idempotency_key="original-key",
    )
    locks = []
    reads = []

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def begin(self):
            return self

        async def get(self, model, key, **kwargs):
            return selection

        async def scalar(self, statement):
            model = statement.column_descriptions[0]["entity"]
            if model is McpDelegatedGrant:
                params = statement.compile().params
                assert params["owner_project_id_1"] == "A"
                return grant
            if model is McpPersonalToken:
                return token
            assert model is McpToolInvocation
            reads.append("operation")
            return row

    async def lock(session, *, owner_user_id, owner_project_id):
        locks.append((owner_user_id, owner_project_id))
        return owner_lock

    monkeypatch.setattr(authentication, "lock_owner", lock)
    monkeypatch.setattr(operations, "get_session_factory", lambda: Session)
    principal = authentication.McpPrincipal(
        grant_id="grant",
        user_id="user",
        project_id="B",
        owner_project_id="A",
        credential_epoch=1,
        scopes=frozenset({"mcp:read"}),
        source="lumen" if invalidated == "selection" else "personal_token",
        selection_generation=2 if invalidated == "selection" else None,
        selection_project_id="A" if invalidated == "selection" else None,
    )
    view = await operations.get_operation(principal, invocation_id="operation")
    assert view.invocation_id == "operation"
    assert locks == [("user", "A")]
    assert reads == ["operation"]
    if invalidated == "project_removed":
        grant.approved_projects = [{"id": "A", "name": "Alpha", "roles": ["reader"], "can_write": False}]
    elif invalidated == "revoked":
        grant.status = "revoked"
    elif invalidated == "expired":
        grant.expires_at = now - timedelta(seconds=1)
    elif invalidated == "pat_revoked":
        token.revoked_at = now
    else:
        owner_lock.lumen_selection_generation += 1
    with pytest.raises(operations.McpOperationError):
        await operations.get_operation(principal, invocation_id="operation")
    assert reads == ["operation"]
    assert row.status == "succeeded"
