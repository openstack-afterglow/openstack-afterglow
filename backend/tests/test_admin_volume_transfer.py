"""Consumer-observable admin transfer routes, native scope and recovery safety."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from openstack.exceptions import ForbiddenException
from openstack.identity.v3.domain import Domain
from openstack.identity.v3.project import Project

from app.api.deps import get_admin_os_conn, require_admin
from app.main import app
from tests.test_volume_transfer import (  # noqa: F401 -- imported pytest fixture
    DESTINATION,
    DOMAIN,
    KEY,
    SOURCE,
    TRANSFER_ID,
    VOLUME_ID,
)
from tests.test_volume_transfer import (
    transfer_provider as transfer_provider,
)

TARGET_DOMAIN = "destination-domain"


@pytest.fixture
def admin_transfer(monkeypatch, transfer_provider):
    p = transfer_provider
    p.state.update(status="available", exists=False)
    admin = {
        "token": "original-human-token",
        "session_token": "original-unscoped-proof",
        "user_id": "test-user-123",
        "is_system_admin": True,
        "identity_domain_id": TARGET_DOMAIN,
        "project_id": "admin-home",
    }
    p.principal = admin

    def scope_from_root(token, _project_id):
        if token != admin["session_token"]:
            raise ForbiddenException("Scoped token rescope is disabled", http_status=403)
        return p.caller

    p.caller_factory.side_effect = scope_from_root
    # transfer_provider depends on client, whose teardown clears these entries.
    app.dependency_overrides[require_admin] = lambda: admin
    app.dependency_overrides[get_admin_os_conn] = lambda: p.operator
    p.operator.block_storage.create_transfer.side_effect = p.caller.block_storage.create_transfer.side_effect
    p.operator.block_storage.delete_transfer.side_effect = p.caller.block_storage.delete_transfer.side_effect
    p.operator.block_storage._list.side_effect = lambda *_args, **_: (
        [p.operator.block_storage.get_transfer(TRANSFER_ID)] if p.state["exists"] else []
    )
    create = p.operator.block_storage.create_transfer.side_effect
    monkeypatch.setattr("app.services.volume_transfers.utils.supports_microversion", lambda *_: False)

    def create_pending(**kwargs):
        p.state["exists"] = True
        return create(**kwargs)

    p.operator.block_storage.create_transfer.side_effect = create_pending
    p.operator.identity.get_project.side_effect = lambda pid: Project(
        id=pid,
        name=pid,
        domain_id=TARGET_DOMAIN if pid == DESTINATION else DOMAIN,
        enabled=True,
    )
    p.operator.identity.get_domain.side_effect = lambda did: Domain(id=did, name=did, enabled=True)
    p.ledger = []
    session = MagicMock()
    session.execute = AsyncMock(side_effect=lambda _: SimpleNamespace(all=lambda: p.ledger))

    @asynccontextmanager
    async def factory():
        yield session

    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    p.admin_invalidate = AsyncMock()
    monkeypatch.setattr("app.api.identity.admin._invalidate_volume_recovery_caches", p.admin_invalidate)
    monkeypatch.setattr("app.api.identity.admin.rec", p.record)
    return p


async def issue(client):
    return await client.post(f"/api/v1/admin/volumes/{VOLUME_ID}/transfer", json={})


async def accept(client, key=KEY, **overrides):
    return await client.post(
        f"/api/v1/admin/volumes/transfer/{TRANSFER_ID}/accept",
        json={
            "auth_key": key,
            "target_domain_id": TARGET_DOMAIN,
            "target_project_id": DESTINATION,
            **overrides,
        },
    )


@pytest.mark.asyncio
async def test_foreign_source_to_selected_foreign_domain_uses_real_human_target_token(client, admin_transfer):
    p = admin_transfer
    response = await issue(client)
    assert response.status_code == 201 and response.json()["auth_key"] == KEY
    assert response.headers["cache-control"] == "no-store, private"
    p.caller_factory.assert_not_called()  # Fixed executor may issue, never accepts into its own project.
    response = await accept(client)
    assert response.status_code == 200 and p.state["owner"] == DESTINATION
    p.caller_factory.assert_called_once_with("original-unscoped-proof", DESTINATION)
    p.caller.session.auth.get_access.assert_called_once_with(p.caller.session)
    p.caller.session.get_token.assert_called_once()
    p.caller.block_storage.accept_transfer.assert_called_once_with(TRANSFER_ID, KEY)
    p.operator.session.post.assert_not_called()
    p.operator.block_storage.accept_transfer.assert_not_called()
    assert KEY not in response.text
    assert {call.args[0] for call in p.invalidate.await_args_list} >= {
        f"afterglow:cinder:{SOURCE}:*",
        f"afterglow:cinder:{DESTINATION}:*",
    }
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("root", [None, ""])
async def test_missing_session_root_never_falls_back_to_scoped_or_operator_token(client, admin_transfer, root):
    p = admin_transfer
    await issue(client)
    p.principal["session_token"] = root
    response = await accept(client)
    assert response.status_code == 403
    assert p.state["owner"] == SOURCE and p.state["exists"]
    p.caller_factory.assert_not_called()
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.operator.block_storage.accept_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_supplied_key_accept_does_not_generate_second_transfer(client, admin_transfer):
    p = admin_transfer
    p.state.update(status="awaiting-transfer", exists=True)
    response = await accept(client)
    assert response.status_code == 200
    p.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["user", "project", "domain", "identity_domain", "no_token", "native_denial"])
async def test_destination_must_be_cryptographically_authenticated_not_header_impersonation(
    client, admin_transfer, defect
):
    p = admin_transfer
    await issue(client)
    access = p.caller.session.auth.get_access.return_value
    if defect == "native_denial":
        p.caller.session.auth.get_access.side_effect = ForbiddenException("private " + KEY, http_status=403)
    elif defect == "no_token":
        p.caller.session.get_token.return_value = ""
    else:
        setattr(
            access,
            {
                "user": "user_id",
                "project": "project_id",
                "domain": "project_domain_id",
                "identity_domain": "user_domain_id",
            }[defect],
            "wrong",
        )
    response = await accept(client)
    assert response.status_code == 403 and KEY not in response.text
    assert p.state["owner"] == SOURCE and p.state["exists"]
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.operator.block_storage.delete_transfer.assert_not_called()
    p.operator.identity.assign_project_role_to_user.assert_not_called()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["foreign_domain", "disabled_project", "disabled_domain"])
async def test_destination_directory_validation_precedes_scoping(client, admin_transfer, defect):
    p = admin_transfer
    await issue(client)
    if defect == "foreign_domain":
        p.operator.identity.get_project.side_effect = lambda pid: {"id": pid, "domain_id": "other", "enabled": True}
    elif defect == "disabled_project":
        p.operator.identity.get_project.side_effect = lambda pid: {
            "id": pid,
            "domain_id": TARGET_DOMAIN,
            "enabled": False,
        }
    else:
        p.operator.identity.get_domain.side_effect = lambda did: {"id": did, "enabled": False}
    response = await accept(client)
    assert response.status_code == 409
    p.caller_factory.assert_not_called()
    p.caller.block_storage.accept_transfer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "accept"])
async def test_native_mutation_denial_remains_denial_and_never_cancels(client, admin_transfer, operation):
    p = admin_transfer
    if operation == "accept":
        await issue(client)
        p.caller.block_storage.accept_transfer.side_effect = ForbiddenException("private " + KEY, http_status=403)
        response = await accept(client)
    else:
        p.operator.block_storage.create_transfer.side_effect = ForbiddenException("private " + KEY, http_status=403)
        response = await issue(client)
    assert response.status_code == 403 and KEY not in response.text
    p.operator.block_storage.delete_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_native_quota_denial_is_not_retried(client, admin_transfer):
    from openstack.exceptions import HttpException

    p = admin_transfer
    await issue(client)
    p.caller.block_storage.accept_transfer.side_effect = HttpException("private " + KEY, http_status=413)
    response = await accept(client)
    assert response.status_code == 413 and KEY not in response.text
    p.caller.block_storage.accept_transfer.assert_called_once()
    p.operator.block_storage.delete_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_recover_exact_volume_pending_id_without_key_then_explicit_cancel(client, admin_transfer):
    p = admin_transfer
    await issue(client)
    response = await client.get(f"/api/v1/admin/volumes/{VOLUME_ID}/transfers")
    assert response.status_code == 200 and response.json()[0]["id"] == TRANSFER_ID
    assert KEY not in response.text
    assert response.headers["cache-control"] == "no-store, private"
    p.operator.block_storage.delete_transfer.assert_not_called()
    response = await client.delete(f"/api/v1/admin/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 204 and p.state["status"] == "available"
    p.operator.block_storage.delete_transfer.assert_called_once_with(TRANSFER_ID, ignore_missing=False)
    args, kwargs = p.operator.block_storage._list.call_args
    assert args[0].__name__ == "_AdminTransfer"
    assert kwargs == {"base_path": "/os-volume-transfer/detail", "all_projects": True}


@pytest.mark.asyncio
async def test_pending_volume_hidden_by_native_listing_is_not_success_empty(client, admin_transfer):
    p = admin_transfer
    p.state.update(status="awaiting-transfer", exists=True)
    p.operator.block_storage._list.side_effect = lambda *_args, **_kwargs: []
    response = await client.get(f"/api/v1/admin/volumes/{VOLUME_ID}/transfers")
    assert response.status_code == 502
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.asyncio
async def test_historic_catalog_row_without_journal_does_not_block_unrelated_volume(
    client, admin_transfer, monkeypatch
):
    p = admin_transfer
    p.ledger = [(9, SOURCE, {}, {"catalog_revision": 1}, None)]
    redis = SimpleNamespace(get=AsyncMock(return_value=None))
    monkeypatch.setattr("app.services.cache._get_redis", AsyncMock(return_value=redis))
    response = await issue(client)
    assert response.status_code == 201
    p.record.assert_awaited_once()
    assert KEY not in str(p.record.call_args)
    p.admin_invalidate.assert_awaited_once_with(SOURCE)


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["in-use", "error", "awaiting-transfer"])
async def test_source_state_and_attachments_cannot_be_overridden_by_admin(client, admin_transfer, state):
    p = admin_transfer
    p.state["status"] = state
    response = await issue(client)
    assert response.status_code == 409
    p.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_attached_available_source_cannot_transfer(client, admin_transfer):
    admin_transfer.state["attachments"] = [{"server_id": "existing-server"}]
    assert (await issue(client)).status_code == 409
    admin_transfer.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "accept"])
async def test_palimpsest_durable_ledger_prevents_transfer_even_without_native_marker(
    client, admin_transfer, operation
):
    p = admin_transfer
    p.ledger = [(9, SOURCE, [{"kind": "upper", "id": VOLUME_ID, "state": "allocated"}], {}, "active")]
    if operation == "accept":
        p.state.update(status="awaiting-transfer", exists=True)
        response = await accept(client)
    else:
        response = await issue(client)
    assert response.status_code == 409
    p.operator.block_storage.create_transfer.assert_not_called()
    p.caller.block_storage.accept_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_unresolved_palimpsest_create_does_not_imply_unmanaged(client, admin_transfer):
    p = admin_transfer
    p.ledger = [(9, SOURCE, [{"kind": "upper", "id": None, "state": "intent"}], {}, "allocating")]
    assert (await issue(client)).status_code == 409
    p.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_missing_ledger_authority_fails_closed(client, admin_transfer, monkeypatch):
    monkeypatch.setattr("app.database.get_session_factory", lambda: None)
    assert (await issue(client)).status_code == 503
    admin_transfer.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_native_palimpsest_marker_is_conservative_blocker(client, admin_transfer):
    p = admin_transfer
    original = p.operator.block_storage.get_volume.side_effect

    def volume(vid):
        row = original(vid)
        row.metadata = {"afterglow_consume_id": "9"}
        return row

    p.operator.block_storage.get_volume.side_effect = volume
    assert (await issue(client)).status_code == 409


@pytest.mark.asyncio
async def test_lost_accept_reply_never_replays_or_cancels_and_invalidates_both(client, admin_transfer):
    p = admin_transfer
    await issue(client)
    p.invalidate.reset_mock()

    def lost(*_):
        p.state.update(owner=DESTINATION, status="available", exists=False)
        raise RuntimeError("lost " + KEY)

    p.caller.block_storage.accept_transfer.side_effect = lost
    response = await accept(client)
    assert response.status_code == 502 and KEY not in response.text
    p.caller.block_storage.accept_transfer.assert_called_once()
    p.operator.block_storage.delete_transfer.assert_not_called()
    assert {call.args[0] for call in p.invalidate.await_args_list} == {
        f"afterglow:cinder:{SOURCE}:*",
        f"afterglow:cinder:{DESTINATION}:*",
        f"afterglow:dashboard:{SOURCE}:quotas*",
        f"afterglow:dashboard:{DESTINATION}:quotas*",
    }


@pytest.mark.asyncio
async def test_wrong_success_readback_is_not_accepted(client, admin_transfer):
    p = admin_transfer
    await issue(client)
    p.caller.block_storage.accept_transfer.side_effect = None
    p.caller.block_storage.accept_transfer.return_value = SimpleNamespace(
        id=TRANSFER_ID, volume_id=VOLUME_ID, name="offer"
    )
    response = await accept(client)
    assert response.status_code == 502
    p.caller.block_storage.accept_transfer.assert_called_once()


@pytest.mark.asyncio
async def test_key_validation_is_private_and_obsolete_header_flow_is_rejected(client, admin_transfer):
    response = await accept(client, key="", arbitrary_secret=KEY)
    assert response.status_code == 422 and KEY not in response.text
    assert response.headers["cache-control"] == "no-store, private"
    response = await client.post(f"/api/v1/admin/volumes/{VOLUME_ID}/transfer", json={"target_project_id": DESTINATION})
    assert response.status_code == 422  # Obsolete direct header impersonation payload is not silently accepted.
    admin_transfer.operator.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_non_system_admin_cannot_generate_or_accept(client, admin_transfer, monkeypatch):
    async def deny():
        raise HTTPException(403, "system_admin_required")

    app.dependency_overrides[require_admin] = deny
    assert (await issue(client)).status_code == 403
    assert (await accept(client)).status_code == 403
    admin_transfer.operator.block_storage.create_transfer.assert_not_called()
    admin_transfer.caller.block_storage.accept_transfer.assert_not_called()
