"""Endpoint regressions for exact readback and native key-authorized transfer."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from openstack.block_storage.v3.transfer import Transfer
from openstack.block_storage.v3.volume import Volume
from openstack.exceptions import BadRequestException, ForbiddenException, HttpException, ResourceNotFound

from app.api.deps import get_token_info
from app.main import app
from app.services import cinder
from tests.conftest import make_token_info

TRANSFER_ID = "11111111-1111-4111-8111-111111111111"
VOLUME_ID = "22222222-2222-4222-8222-222222222222"
DESTINATION = "test-project-123"
SOURCE = "source-project-other-domain"
DOMAIN = "source-domain-other"
KEY = "native-once-only-key"


@pytest.fixture
def transfer_provider(monkeypatch, auth_directory, mock_conn):
    """Native-shaped provider boundary; endpoint/service/SDK wrappers stay real."""
    auth_directory.domains["destination-domain"] = {
        "id": "destination-domain",
        "name": "Destination",
        "enabled": True,
    }
    auth_directory.users["test-user-123"] = {
        "id": "test-user-123",
        "name": "recipient",
        "domain_id": "destination-domain",
        "enabled": True,
    }
    auth_directory.projects[DESTINATION]["domain_id"] = "destination-domain"
    mock_conn._afterglow_domain_id = "destination-domain"
    mock_conn._afterglow_identity_domain_id = "destination-domain"
    monkeypatch.setitem(
        app.dependency_overrides, get_token_info, lambda: make_token_info(domain_id="destination-domain")
    )
    state = {
        "owner": SOURCE,
        "status": "awaiting-transfer",
        "attachments": [],
        "volume_id": VOLUME_ID,
        "exists": True,
        "domain": DOMAIN,
    }
    caller = MagicMock()
    operator = MagicMock()
    caller.session.auth.get_access.return_value = SimpleNamespace(
        user_id="test-user-123",
        project_id=DESTINATION,
        user_domain_id="destination-domain",
        project_domain_id="destination-domain",
    )
    caller.session.get_token.return_value = "genuinely-destination-scoped-token"
    caller.block_storage.connect_retries = 1
    caller.block_storage.status_code_retries = 1

    def volume(volume_id):
        if volume_id != VOLUME_ID:
            raise ResourceNotFound("missing volume", http_status=404)
        return Volume(
            id=VOLUME_ID,
            name="source disk",
            status=state["status"],
            size=12,
            volume_type="fast",
            attachments=state["attachments"],
            **{"os-vol-tenant-attr:tenant_id": state["owner"]},
            metadata={"project_id": "spoofed-project", "domain_id": "spoofed-domain", "secret": KEY},
        )

    def transfer(transfer_id):
        if transfer_id != TRANSFER_ID or not state["exists"]:
            raise ResourceNotFound("missing transfer", http_status=404)
        return Transfer(
            id=TRANSFER_ID,
            name="not-an-owner",
            volume_id=state["volume_id"],
            created_at="2026-10-14T00:00:00Z",
            auth_key=KEY,
            links=[{"href": "https://private.invalid/secret"}],
        )

    def create_transfer(**attrs):
        assert attrs["volume_id"] == VOLUME_ID
        state["status"] = "awaiting-transfer"
        return Transfer(
            id=TRANSFER_ID,
            name=attrs.get("name", ""),
            volume_id=VOLUME_ID,
            created_at="2026-10-14T00:00:00Z",
            auth_key=KEY,
        )

    def accept_transfer(transfer_id, auth_key):
        assert transfer_id == TRANSFER_ID
        if auth_key != KEY:
            raise BadRequestException(
                message=None,
                details=f"Invalid auth key: Attempt to transfer {transfer_id} with invalid auth key.",
                http_status=400,
            )
        state["owner"] = DESTINATION
        state["status"] = "available"
        state["exists"] = False
        return Transfer(id=TRANSFER_ID, name="not-an-owner", volume_id=VOLUME_ID)

    def delete_transfer(transfer_id, *, ignore_missing):
        assert transfer_id == TRANSFER_ID and ignore_missing is False
        state["exists"] = False
        state["status"] = "available"

    for conn in (caller, operator):
        conn.block_storage.get_transfer.side_effect = transfer
        conn.block_storage.get_volume.side_effect = volume
    caller.block_storage.transfers.side_effect = lambda **kwargs: [transfer(TRANSFER_ID)] if state["exists"] else []
    caller.block_storage.create_transfer.side_effect = create_transfer
    caller.block_storage.accept_transfer.side_effect = accept_transfer
    caller.block_storage.delete_transfer.side_effect = delete_transfer
    operator.identity.get_project.side_effect = lambda pid: {
        "id": pid,
        "name": "actual source project",
        "domain_id": state["domain"],
    }
    operator.identity.get_domain.side_effect = lambda did: {"id": did, "name": "actual source domain"}
    caller_factory = MagicMock(return_value=caller)
    operator_factory = MagicMock(return_value=operator)
    monkeypatch.setattr("app.services.keystone.get_openstack_connection", caller_factory)
    monkeypatch.setattr("app.services.keystone.get_admin_project_connection", operator_factory)
    record, invalidate = AsyncMock(), AsyncMock()
    monkeypatch.setattr("app.api.storage.volumes.rec", record)
    monkeypatch.setattr("app.api.storage.volumes.invalidate", invalidate)

    async def invalidate_project(project_id, service):
        await invalidate(f"afterglow:{service}:{project_id}:*")

    monkeypatch.setattr("app.api.storage.volumes.invalidate_project", invalidate_project)
    monkeypatch.setattr("app.api.storage.volumes.invalidation.invalidate_mutation_count", AsyncMock())
    return SimpleNamespace(
        state=state,
        caller=caller,
        operator=operator,
        caller_factory=caller_factory,
        operator_factory=operator_factory,
        record=record,
        invalidate=invalidate,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("domain", ["destination-domain", DOMAIN])
async def test_exact_lookup_displays_actual_source_without_secrets_or_enumeration(client, transfer_provider, domain):
    p = transfer_provider
    p.state["domain"] = domain
    response = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 200
    assert response.json() == {
        "id": TRANSFER_ID,
        "name": "not-an-owner",
        "volume_id": VOLUME_ID,
        "created_at": "2026-10-14T00:00:00Z",
        "volume_name": "source disk",
        "size": 12,
        "volume_type": "fast",
        "status": "awaiting-transfer",
        "source_project": {"id": SOURCE, "name": "actual source project"},
        "source_domain": {"id": domain, "name": "actual source domain"},
    }
    assert KEY not in response.text and "spoofed" not in response.text and "private.invalid" not in response.text
    p.operator.block_storage.get_transfer.assert_called_once_with(TRANSFER_ID)
    p.operator.block_storage.get_volume.assert_called_once_with(VOLUME_ID)
    p.operator.identity.get_project.assert_called_once_with(SOURCE)
    p.operator.identity.get_domain.assert_called_once_with(domain)
    p.operator.block_storage.transfers.assert_not_called()
    p.operator.block_storage.find_transfer.assert_not_called()
    p.operator.identity.projects.assert_not_called()
    p.operator.identity.domains.assert_not_called()
    p.operator.close.assert_called_once()
    p.caller_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "identifier",
    ["partial", TRANSFER_ID[:8], "{11111111-1111-4111-8111-111111111111}", "11111111111141118111111111111111"],
)
async def test_lookup_rejects_noncanonical_ids_before_operator_io(client, transfer_provider, identifier):
    response = await client.get(f"/api/v1/volumes/transfer/{identifier}")
    assert response.status_code == 422
    transfer_provider.operator_factory.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_missing_or_consumed_is_404_and_closes_operator(client, transfer_provider):
    p = transfer_provider
    p.state["exists"] = False
    response = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 404
    p.operator.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["available", "in-use", "error", None])
async def test_lookup_refuses_nonpending_volume(client, transfer_provider, status):
    transfer_provider.state["status"] = status
    response = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 404
    transfer_provider.operator.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "defect",
    [
        "owner_missing",
        "owner_conflicting",
        "transfer_id",
        "volume_id",
        "project_id",
        "domain_id",
        "attachments_missing",
    ],
)
async def test_lookup_fails_closed_on_unverifiable_provider_identity(client, transfer_provider, defect):
    p = transfer_provider
    if defect == "owner_missing":
        p.state["owner"] = None
    elif defect == "owner_conflicting":
        p.operator.block_storage.get_volume.side_effect = None
        p.operator.block_storage.get_volume.return_value = {
            "id": VOLUME_ID,
            "project_id": SOURCE,
            "os-vol-tenant-attr:tenant_id": DESTINATION,
            "status": "awaiting-transfer",
            "attachments": [],
        }
    elif defect == "transfer_id":
        p.operator.block_storage.get_transfer.side_effect = None
        p.operator.block_storage.get_transfer.return_value = {"id": VOLUME_ID, "volume_id": VOLUME_ID}
    elif defect == "volume_id":
        p.operator.block_storage.get_volume.side_effect = None
        p.operator.block_storage.get_volume.return_value = {"id": TRANSFER_ID}
    elif defect == "project_id":
        p.operator.identity.get_project.side_effect = None
        p.operator.identity.get_project.return_value = {"id": DESTINATION, "name": "wrong", "domain_id": DOMAIN}
    elif defect == "domain_id":
        p.operator.identity.get_domain.side_effect = None
        p.operator.identity.get_domain.return_value = {"id": "wrong", "name": "wrong"}
    else:
        p.state["attachments"] = None
    response = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 502
    assert KEY not in response.text
    p.operator.close.assert_called_once()


@pytest.mark.asyncio
async def test_lookup_operator_outage_is_not_empty_success(client, transfer_provider):
    p = transfer_provider
    p.operator.block_storage.get_transfer.side_effect = ForbiddenException("operator lacks policy", http_status=403)
    response = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 503
    p.operator.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,attachments",
    [("in-use", [{"server_id": "vm"}]), ("available", [{"attachment_id": "orphan"}]), ("error", [])],
)
async def test_create_refuses_attached_or_nonavailable_without_detach(
    client, transfer_provider, mock_conn, status, attachments
):
    p = transfer_provider
    p.state.update(owner=DESTINATION, status=status, attachments=attachments)
    response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={})
    assert response.status_code == 409
    p.caller.block_storage.create_transfer.assert_not_called()
    mock_conn.compute.delete_volume_attachment.assert_not_called()
    mock_conn.compute.create_volume_attachment.assert_not_called()
    p.caller.block_storage.wait_for_status.assert_not_called()


@pytest.mark.asyncio
async def test_create_issues_native_key_once_and_invalidates_source(client, transfer_provider):
    p = transfer_provider
    p.state.update(owner=DESTINATION, status="available")
    response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={"name": "offering"})
    assert response.status_code == 201
    assert response.json() == {
        "id": TRANSFER_ID,
        "name": "offering",
        "volume_id": VOLUME_ID,
        "created_at": "2026-10-14T00:00:00Z",
        "auth_key": KEY,
    }
    assert response.headers["cache-control"] == "no-store, private"
    assert response.headers["pragma"] == "no-cache"
    p.caller.block_storage.create_transfer.assert_called_once_with(volume_id=VOLUME_ID, name="offering")
    p.invalidate.assert_awaited_once_with(f"afterglow:cinder:{DESTINATION}:volumes*")
    p.caller.close.assert_called_once()
    assert KEY not in str(p.record.call_args)
    assert p.caller.block_storage.connect_retries == 1
    assert p.caller.block_storage.status_code_retries == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_create_foreign_owner_is_refused_even_for_system_admin(client, transfer_provider, admin):
    app.dependency_overrides[get_token_info] = lambda: make_token_info(
        is_system_admin=admin, domain_id="destination-domain"
    )
    response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={})
    assert response.status_code == 404
    transfer_provider.caller.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_own_list_static_route_is_project_scoped_and_secret_free(client, transfer_provider):
    p = transfer_provider
    p.state["owner"] = DESTINATION
    response = await client.get("/api/v1/volumes/transfers")
    assert response.status_code == 200
    assert response.json() == [
        {"id": TRANSFER_ID, "name": "not-an-owner", "volume_id": VOLUME_ID, "created_at": "2026-10-14T00:00:00Z"}
    ]
    assert KEY not in response.text
    p.caller.block_storage.transfers.assert_called_once_with(details=True, all_projects=False)
    p.operator_factory.assert_not_called()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
async def test_own_list_refuses_provider_cross_project_leak_even_for_admin(client, transfer_provider):
    app.dependency_overrides[get_token_info] = lambda: make_token_info(
        is_system_admin=True, domain_id="destination-domain"
    )
    response = await client.get("/api/v1/volumes/transfers")
    assert response.status_code == 502
    assert SOURCE not in response.text and KEY not in response.text


@pytest.mark.asyncio
async def test_own_list_provider_failure_does_not_return_empty_success(client, transfer_provider):
    transfer_provider.caller.block_storage.transfers.side_effect = RuntimeError("provider secret " + KEY)
    response = await client.get("/api/v1/volumes/transfers")
    assert response.status_code == 502 and KEY not in response.text
    transfer_provider.caller.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "accept", "cancel"])
async def test_transfer_mutations_refuse_reader_before_provider_io(client, transfer_provider, operation):
    app.dependency_overrides[get_token_info] = lambda: make_token_info(roles=["reader"], domain_id="destination-domain")
    if operation == "create":
        response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={})
    elif operation == "accept":
        response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    else:
        response = await client.delete(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 403
    transfer_provider.caller_factory.assert_not_called()
    transfer_provider.operator_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["", "   ", "x" * 513])
async def test_accept_validates_key_before_any_transfer_io(client, transfer_provider, key):
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": key})
    assert response.status_code == 422
    assert "input" not in response.json() and "auth_key" not in response.text
    assert response.headers["cache-control"] == "no-store, private"
    transfer_provider.caller_factory.assert_not_called()
    transfer_provider.operator_factory.assert_not_called()


@pytest.mark.asyncio
async def test_accept_wrong_native_key_is_403_never_disclosed_or_recorded(client, transfer_provider):
    p = transfer_provider
    response = await client.post(
        f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": "wrong-secret-key"}
    )
    assert response.status_code == 403
    assert "wrong-secret-key" not in response.text and KEY not in response.text
    assert p.state["owner"] == SOURCE and p.state["exists"] is True
    p.caller.block_storage.accept_transfer.assert_called_once_with(TRANSFER_ID, "wrong-secret-key")
    p.record.assert_not_awaited()
    p.operator.block_storage.accept_transfer.assert_not_called()
    p.operator.close.assert_called_once()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
async def test_accept_rescopes_admin_caller_to_selected_destination_and_confirms_native_owner(
    client, transfer_provider, mock_conn
):
    p = transfer_provider
    info = make_token_info(is_system_admin=True, domain_id="destination-domain")
    info["connection_project_id"] = "admin-home-project"
    app.dependency_overrides[get_token_info] = lambda: info
    mock_conn._afterglow_authenticated_project_id = "admin-home-project"
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 200
    assert response.json() == {"id": TRANSFER_ID, "name": "not-an-owner", "volume_id": VOLUME_ID}
    assert p.state["owner"] == DESTINATION and p.state["exists"] is False
    p.caller_factory.assert_called_once_with("test-token", DESTINATION)
    p.caller.session.auth.get_access.assert_called_once_with(p.caller.session)
    assert p.caller._afterglow_token == "genuinely-destination-scoped-token"
    p.caller.block_storage.accept_transfer.assert_called_once_with(TRANSFER_ID, KEY)
    mock_conn.block_storage.accept_transfer.assert_not_called()
    p.operator.block_storage.accept_transfer.assert_not_called()
    p.operator.block_storage.get_volume.assert_any_call(VOLUME_ID)
    assert p.operator.block_storage.get_volume.call_count == 2
    assert {call.args[0] for call in p.invalidate.await_args_list} == {
        f"afterglow:cinder:{SOURCE}:*",
        f"afterglow:cinder:{DESTINATION}:*",
    }
    assert KEY not in response.text and KEY not in str(p.record.call_args)


@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,project_id", [("other-user", DESTINATION), ("test-user-123", "admin-home-project")])
async def test_accept_scope_identity_mismatch_fails_before_operator_or_mutation(
    client, transfer_provider, user_id, project_id
):
    p = transfer_provider
    p.caller.session.auth.get_access.return_value = SimpleNamespace(user_id=user_id, project_id=project_id)
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 403
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.operator_factory.assert_not_called()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
async def test_accept_same_source_target_conflicts(client, transfer_provider):
    p = transfer_provider
    p.state["owner"] = DESTINATION
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 409
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.operator.close.assert_called_once()


@pytest.mark.asyncio
async def test_accept_rechecks_state_changed_since_lookup(client, transfer_provider):
    p = transfer_provider
    lookup = await client.get(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert lookup.status_code == 200
    p.state["status"] = "in-use"
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 409
    p.caller.block_storage.accept_transfer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(400, 409), (403, 403), (409, 409), (413, 413), (500, 502)])
async def test_accept_preserves_native_refusal_without_secret_exceptions(client, transfer_provider, status, expected):
    p = transfer_provider
    p.caller.block_storage.accept_transfer.side_effect = HttpException("unsafe " + KEY, http_status=status)
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == expected and KEY not in response.text
    p.caller.block_storage.accept_transfer.assert_called_once()
    p.record.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_ambiguous_post_is_not_retried_and_invalidates_both_projects(client, transfer_provider):
    p = transfer_provider

    def lost_reply(*args):
        p.state.update(owner=DESTINATION, status="available", exists=False)
        raise RuntimeError("accepted but response lost " + KEY)

    p.caller.block_storage.accept_transfer.side_effect = lost_reply
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 502 and KEY not in response.text
    p.caller.block_storage.accept_transfer.assert_called_once()
    assert {call.args[0] for call in p.invalidate.await_args_list} == {
        f"afterglow:cinder:{SOURCE}:*",
        f"afterglow:cinder:{DESTINATION}:*",
    }
    p.operator.close.assert_called_once()


@pytest.mark.asyncio
async def test_accept_success_without_native_destination_owner_is_not_success(client, transfer_provider):
    p = transfer_provider
    p.caller.block_storage.accept_transfer.side_effect = None
    p.caller.block_storage.accept_transfer.return_value = Transfer(id=TRANSFER_ID, volume_id=VOLUME_ID, name="offer")
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 502
    assert p.state["owner"] == SOURCE
    p.caller.block_storage.accept_transfer.assert_called_once()
    p.record.assert_not_awaited()
    assert p.invalidate.await_count == 2


@pytest.mark.asyncio
async def test_cancel_owned_pending_native_transfer_and_invalidates_source(client, transfer_provider):
    p = transfer_provider
    p.state["owner"] = DESTINATION
    response = await client.delete(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 204 and response.content == b""
    assert p.state["exists"] is False and p.state["status"] == "available"
    p.caller.block_storage.delete_transfer.assert_called_once_with(TRANSFER_ID, ignore_missing=False)
    p.operator_factory.assert_not_called()
    p.invalidate.assert_awaited_once_with(f"afterglow:cinder:{DESTINATION}:volumes*")


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_cancel_foreign_source_refuses_even_system_admin(client, transfer_provider, admin):
    app.dependency_overrides[get_token_info] = lambda: make_token_info(
        is_system_admin=admin, domain_id="destination-domain"
    )
    response = await client.delete(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 404
    transfer_provider.caller.block_storage.delete_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_nonpending_state_does_not_mutate(client, transfer_provider):
    p = transfer_provider
    p.state.update(owner=DESTINATION, status="available")
    response = await client.delete(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 409
    p.caller.block_storage.delete_transfer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["accept", "cancel"])
async def test_mutation_rejects_malformed_transfer_id_before_scoping(client, transfer_provider, operation):
    if operation == "accept":
        response = await client.post("/api/v1/volumes/transfer/partial/accept", json={"auth_key": KEY})
    else:
        response = await client.delete("/api/v1/volumes/transfer/partial")
    assert response.status_code == 422
    transfer_provider.caller_factory.assert_not_called()
    transfer_provider.operator_factory.assert_not_called()


@pytest.mark.asyncio
async def test_own_pending_list_without_volumes_is_verified_empty(client, transfer_provider):
    p = transfer_provider
    p.state["exists"] = False
    response = await client.get("/api/v1/volumes/transfers")
    assert response.status_code == 200 and response.json() == []
    p.caller.block_storage.transfers.assert_called_once_with(details=True, all_projects=False)
    p.caller.block_storage.volumes.assert_not_called()
    p.operator_factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["accept", "cancel"])
async def test_consumed_or_cancelled_transfer_cannot_mutate(client, transfer_provider, operation):
    p = transfer_provider
    p.state["exists"] = False
    if operation == "accept":
        response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    else:
        response = await client.delete(f"/api/v1/volumes/transfer/{TRANSFER_ID}")
    assert response.status_code == 404
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.caller.block_storage.delete_transfer.assert_not_called()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
async def test_accept_operator_read_refusal_is_service_failure_not_caller_denial(client, transfer_provider):
    p = transfer_provider
    p.operator.block_storage.get_transfer.side_effect = ForbiddenException("private policy failure", http_status=403)
    response = await client.post(f"/api/v1/volumes/transfer/{TRANSFER_ID}/accept", json={"auth_key": KEY})
    assert response.status_code == 503
    p.caller.block_storage.accept_transfer.assert_not_called()
    p.operator.close.assert_called_once()
    p.caller.close.assert_called_once()


@pytest.mark.asyncio
async def test_create_missing_or_inconsistent_native_owner_fails_closed(client, transfer_provider):
    p = transfer_provider
    p.state.update(owner=None, status="available")
    response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={})
    assert response.status_code == 502
    p.caller.block_storage.create_transfer.assert_not_called()


@pytest.mark.asyncio
async def test_create_provider_failure_never_rolls_back_attachment_or_exposes_key(client, transfer_provider, mock_conn):
    p = transfer_provider
    p.state.update(owner=DESTINATION, status="available")
    p.caller.block_storage.create_transfer.side_effect = RuntimeError("provider leaked " + KEY)
    response = await client.post(f"/api/v1/volumes/{VOLUME_ID}/transfer", json={})
    assert response.status_code == 502 and KEY not in response.text
    p.caller.block_storage.create_transfer.assert_called_once()
    mock_conn.compute.create_volume_attachment.assert_not_called()
    p.record.assert_not_awaited()


@pytest.mark.parametrize("operation", ["create", "accept"])
def test_native_transfer_lost_reply_never_replays_accepted_mutation(operation):
    import json
    import socket
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import urlsplit

    from keystoneauth1.session import Session
    from keystoneauth1.token_endpoint import Token
    from openstack.connection import Connection

    state = {"posts": 0, "volume_owner": SOURCE, "pending": operation == "accept"}
    record = {"id": TRANSFER_ID, "volume_id": VOLUME_ID, "auth_key": KEY}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, body):
            payload = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            if path in ("/v3", "/v3/" + DESTINATION):
                self.reply(
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [{"rel": "self", "href": endpoint + "/v3/"}],
                        }
                    }
                )
            elif path.endswith("/volumes/" + VOLUME_ID):
                self.reply(
                    {
                        "volume": {
                            "id": VOLUME_ID,
                            "status": "awaiting-transfer" if state["pending"] else "available",
                            "os-vol-tenant-attr:tenant_id": state["volume_owner"],
                        }
                    }
                )
            else:
                self.reply({"transfer": record})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["posts"] += 1
            if operation == "create":
                assert body["transfer"]["volume_id"] == VOLUME_ID
                state["pending"] = True
            else:
                assert body["accept"]["auth_key"] == KEY
                state["pending"] = False
                state["volume_owner"] = DESTINATION
            if state["posts"] == 1:
                self.connection.shutdown(socket.SHUT_RDWR)
                self.connection.close()
                self.close_connection = True
            else:
                self.reply({"transfer": record})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=Session(auth=Token(endpoint=endpoint, token="synthetic-transfer-only")),
        block_storage_endpoint_override=endpoint + "/v3/" + DESTINATION,
        block_storage_api_version="3",
    )
    try:
        with pytest.raises(Exception):
            if operation == "create":
                cinder.create_volume_transfer(conn, VOLUME_ID)
            else:
                cinder.accept_volume_transfer(conn, TRANSFER_ID, KEY)
        observed = conn.block_storage.get_volume(VOLUME_ID)
        assert state["posts"] == 1
        assert observed.project_id == (SOURCE if operation == "create" else DESTINATION)
        assert observed.status == ("awaiting-transfer" if operation == "create" else "available")
    finally:
        conn.close()
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
