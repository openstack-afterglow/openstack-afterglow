"""Consumer-visible login/terminal revocation transitions; native identity is synthetic."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI
from starlette.websockets import WebSocketDisconnect

from app.api.cloud_shell import _relay_terminal, router
from app.api.deps import get_token_info
from app.services import cloud_shell, keystone, session_store
from app.services import cloud_shell_authority as authority
from tests.test_cloud_shell import PROJECT_ID, FakeConnection, cloud_settings, managed_volume

HOME = "identity-home"
DOMAIN = "working-domain"


@pytest.fixture
async def shell_login(monkeypatch):
    settings = cloud_settings(frontend_base_url="https://console.example.test")
    monkeypatch.setattr(cloud_shell, "get_settings", lambda: settings)
    monkeypatch.setattr(authority, "get_settings", lambda: settings)
    monkeypatch.setattr("app.api.cloud_shell.get_settings", lambda: settings)
    exp = int(time.time()) + 600
    await session_store.store_session(
        "shell-login-a", "login-root", PROJECT_ID, "user-a", exp, domain_id=DOMAIN, identity_domain_id=HOME
    )
    tokens = {}
    revoked = []

    def exchange(root, project):
        token = f"derived-shell-{len(tokens) + 1}"
        tokens[token] = project
        return {
            "token": token,
            "user_id": "user-a",
            "project_id": project,
            "username": "alice",
            "project_name": "fixture",
            "expires_at": "2099-01-01T00:00:00Z",
        }

    def inspect(token, binding):
        if token in revoked or tokens.get(token) != binding["project_id"]:
            raise authority.ShellAuthorityError("Native credential is unavailable")
        return {"user_id": "user-a", "domain_id": DOMAIN, "identity_domain_id": HOME, "email": "alice@example.test"}

    def revoke(token):
        revoked.append(token)

    monkeypatch.setattr(keystone, "validate_token", exchange)
    monkeypatch.setattr(keystone, "revoke_token", revoke)
    monkeypatch.setattr(authority, "inspect_native_token", inspect)
    monkeypatch.setattr("app.api.identity.auth._enforce_session_policy", AsyncMock())
    principal = {
        "user_id": "user-a",
        "username": "alice",
        "project_id": PROJECT_ID,
        "project_name": "fixture",
        "token": "caller-project-token",
        "refresh_jti": "shell-login-a",
        "domain_id": DOMAIN,
        "identity_domain_id": HOME,
        "roles": ["member"],
    }
    return SimpleNamespace(settings=settings, principal=principal, tokens=tokens, revoked=revoked, exp=exp)


async def approved(principal):
    ticket = await cloud_shell.issue_cloud_shell_ticket(principal)
    return ticket, await cloud_shell.consume_cloud_shell_ticket(ticket["ticket"])


@pytest.mark.asyncio
async def test_refresh_keeps_shell_but_revoked_rotated_family_cannot_reconnect(shell_login):
    ticket = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert await session_store.store_session(
        "shell-login-b",
        "new-login-root",
        PROJECT_ID,
        "user-a",
        shell_login.exp,
        domain_id=DOMAIN,
        identity_domain_id=HOME,
        previous_jti="shell-login-a",
        timeout_seconds=3600,
    )
    lease = await cloud_shell.consume_cloud_shell_ticket(ticket["ticket"])
    await cloud_shell.assert_session_authority(lease, native=True)
    assert lease.token != "login-root"
    assert await session_store.delete_session_owned("user-a", "shell-login-a")
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease)
    assert lease.token in shell_login.revoked
    assert await session_store.get_session("shell-login-b") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["logout", "single", "all", "blacklist"])
@pytest.mark.parametrize("active", [False, True])
async def test_revocation_invalidates_pending_and_active_shell_credentials(shell_login, operation, active):
    ticket = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    if active:
        lease = await cloud_shell.consume_cloud_shell_ticket(ticket["ticket"])
    token = next(iter(shell_login.tokens))
    if operation == "logout":
        await session_store.delete_session("shell-login-a")
    elif operation == "single":
        await session_store.delete_session_owned("user-a", "shell-login-a")
    elif operation == "all":
        await session_store.revoke_user_sessions("user-a")
    else:
        await session_store.blacklist_session("shell-login-a", "operator")
    assert token in shell_login.revoked
    if active:
        with pytest.raises(cloud_shell.CloudShellUnauthorized):
            await cloud_shell.assert_session_authority(lease)
    else:
        with pytest.raises(cloud_shell.CloudShellUnauthorized):
            await cloud_shell.consume_cloud_shell_ticket(ticket["ticket"])
        replacement = {**shell_login.principal, "refresh_jti": "new-login"}
        await session_store.store_session(
            "new-login", "new-root", PROJECT_ID, "user-a", shell_login.exp, domain_id=DOMAIN, identity_domain_id=HOME
        )
        await cloud_shell.issue_cloud_shell_ticket(replacement)


@pytest.mark.asyncio
async def test_project_aba_does_not_restore_old_shell_authority(shell_login):
    _, lease = await approved(shell_login.principal)
    other = "33333333-3333-4333-8333-333333333333"
    assert await session_store.store_session(
        "shell-login-b",
        "root-b",
        other,
        "user-a",
        shell_login.exp,
        domain_id=DOMAIN,
        identity_domain_id=HOME,
        previous_jti="shell-login-a",
        timeout_seconds=3600,
    )
    assert await session_store.store_session(
        "shell-login-c",
        "root-c",
        PROJECT_ID,
        "user-a",
        shell_login.exp,
        domain_id=DOMAIN,
        identity_domain_id=HOME,
        previous_jti="shell-login-b",
        timeout_seconds=3600,
    )
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease)
    assert lease.token in shell_login.revoked
    assert (await session_store.get_session("shell-login-c"))["scope_revision"] == 2


@pytest.mark.asyncio
async def test_abandoned_ticket_revokes_exact_derived_token_and_preserves_home(shell_login):
    ticket = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    redis = await authority._get_redis()
    ids = await redis.zrange(authority.INDEX, 0, -1)
    sid = ids[0].decode() if isinstance(ids[0], bytes) else ids[0]
    record = await authority.receipt(sid)
    await authority.update_receipt(sid, ticket_deadline=int(time.time()) - 1)
    await redis.zadd(authority.INDEX, {sid: 0})
    assert await cloud_shell._reconcile_credentials(None, [], shell_login.settings) == 1
    assert record["lease"]["token"] in shell_login.revoked
    assert "login-root" not in shell_login.revoked
    assert await authority.receipt(sid) is None
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.consume_cloud_shell_ticket(ticket["ticket"])


@pytest.mark.asyncio
async def test_native_revocation_failure_retains_cleanup_receipt_and_blocks_input(shell_login, monkeypatch):
    _, lease = await approved(shell_login.principal)
    monkeypatch.setattr(keystone, "revoke_token", lambda token: (_ for _ in ()).throw(RuntimeError("unavailable")))
    removed = await session_store.delete_session("shell-login-a")
    assert removed["cloud_shell_cleanup_pending"] is True
    record = await authority.receipt(lease.session_id)
    assert record["cleanup_requested"] is True and record["token_revoked"] is False
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease)
    monkeypatch.setattr(keystone, "revoke_token", shell_login.revoked.append)
    assert await cloud_shell._reconcile_credentials(None, [], shell_login.settings) == 1
    assert lease.token in shell_login.revoked
    assert await authority.receipt(lease.session_id) is None


@pytest.mark.asyncio
async def test_relay_rejects_input_after_server_revokes_login_even_if_browser_stays_open(shell_login):
    _, lease = await approved(shell_login.principal)
    browser_queue = asyncio.Queue()
    upstream_queue = asyncio.Queue()
    sent = []
    browser = SimpleNamespace(
        receive=browser_queue.get, send_text=AsyncMock(), send_bytes=AsyncMock(), close=AsyncMock()
    )
    upstream = SimpleNamespace(recv=upstream_queue.get, send=AsyncMock(side_effect=sent.append))
    runtime = SimpleNamespace(lease=lease, expires_at=int(time.time()) + 60)
    relay = asyncio.create_task(_relay_terminal(browser, upstream, runtime))
    await session_store.delete_session("shell-login-a")
    await browser_queue.put({"type": "websocket.receive", "bytes": b"must-not-execute\n"})
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await asyncio.wait_for(relay, timeout=3)
    assert sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_fails", [False, True])
async def test_cancelled_issuance_tracks_native_revocation_failure(shell_login, monkeypatch, revoke_fails):
    import threading

    entered, release = threading.Event(), threading.Event()

    def blocked_exchange(root, project):
        entered.set()
        assert release.wait(5)
        shell_login.tokens["cancelled-derived"] = project
        return {
            "token": "cancelled-derived",
            "user_id": "user-a",
            "project_id": project,
            "username": "alice",
            "project_name": "fixture",
            "expires_at": "2099-01-01T00:00:00Z",
        }

    monkeypatch.setattr(keystone, "validate_token", blocked_exchange)
    if revoke_fails:
        monkeypatch.setattr(keystone, "revoke_token", lambda token: (_ for _ in ()).throw(RuntimeError("unavailable")))
    operation = asyncio.create_task(cloud_shell.issue_cloud_shell_ticket(shell_login.principal))
    assert await asyncio.to_thread(entered.wait, 5)
    operation.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    redis = await authority._get_redis()
    ids = await redis.zrange(authority.INDEX, 0, -1)
    if revoke_fails:
        assert len(ids) == 1
        record = await authority.receipt(ids[0])
        assert record["lease"]["token"] == "cancelled-derived" and record["cleanup_requested"]
        assert not record["token_revoked"]
    else:
        assert "cancelled-derived" in shell_login.revoked
        assert ids == []
    assert "login-root" not in shell_login.revoked


@pytest.mark.asyncio
async def test_ticket_http_refuses_stale_login_context_after_revocation(shell_login, monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/cloud-shell")
    app.dependency_overrides[get_token_info] = lambda: shell_login.principal
    monkeypatch.setattr(cloud_shell, "record_audit", AsyncMock())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://console.example.test"
    ) as client:
        issued = await client.post("/api/v1/cloud-shell/tickets")
        assert issued.status_code == 201
        assert not any(secret in issued.text for secret in ["login-root", *shell_login.tokens])
        await session_store.delete_session_owned("user-a", "shell-login-a")
        denied = await client.post("/api/v1/cloud-shell/tickets")
    assert denied.status_code == 401
    assert denied.json()["detail"]["code"] == "session_revoked"


@pytest.mark.asyncio
async def test_missing_login_family_cannot_be_recreated_by_ticket_issuance(shell_login):
    redis = await session_store._get_redis()
    await redis.delete(session_store._FAMILY_PREFIX + "shell-login-a")
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert shell_login.tokens == {}


@pytest.mark.asyncio
async def test_native_policy_loss_rejects_existing_shell_before_more_authorized_execution(shell_login, monkeypatch):
    _, lease = await approved(shell_login.principal)

    def denied(token, binding):
        raise authority.ShellAuthorityError("Project write grant removed")

    monkeypatch.setattr(authority, "inspect_native_token", denied)
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease, native=True)


@pytest.mark.asyncio
async def test_stale_reconciler_snapshot_cannot_retire_a_promoted_ticket(shell_login, monkeypatch):
    issued = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    redis = await authority._get_redis()
    sid = (await redis.zrange(authority.INDEX, 0, -1))[0]
    stale = await authority.receipt(sid)
    stale["ticket_deadline"] = int(time.time()) - 1
    lease = await cloud_shell.consume_cloud_shell_ticket(issued["ticket"])
    await redis.zadd(authority.INDEX, {sid: 0})
    original = authority.receipt
    reads = 0

    async def observed(session_id):
        nonlocal reads
        reads += 1
        return stale if reads == 1 else await original(session_id)

    monkeypatch.setattr(authority, "receipt", observed)
    assert await cloud_shell._reconcile_credentials(None, [], shell_login.settings) == 0
    await cloud_shell.assert_session_authority(lease)
    assert lease.token not in shell_login.revoked


@pytest.mark.asyncio
async def test_retiring_unknown_create_cannot_drop_receipt_or_unlock_another_shell(shell_login):
    _, lease = await approved(shell_login.principal)
    assert await authority.update_receipt(lease.session_id, creation_attempted=True)
    assert await authority.revoke_credential(lease.session_id)
    assert not await authority.finish_receipt(lease.session_id)
    assert await authority.receipt(lease.session_id) is not None
    with pytest.raises(cloud_shell.CloudShellConflict):
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)


@pytest.mark.asyncio
async def test_blacklist_racing_rotation_revokes_the_current_login_family(shell_login):
    _, lease = await approved(shell_login.principal)
    assert await session_store.store_session(
        "shell-login-b",
        "root-b",
        PROJECT_ID,
        "user-a",
        shell_login.exp,
        domain_id=DOMAIN,
        identity_domain_id=HOME,
        previous_jti="shell-login-a",
        timeout_seconds=3600,
    )
    await session_store.blacklist_session("shell-login-a", "operator")
    assert (await session_store.get_session("shell-login-b"))["blacklisted"] is True
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease)
    assert lease.token in shell_login.revoked


@pytest.mark.asyncio
async def test_disconnect_before_native_create_releases_slot_and_preserves_home(shell_login, monkeypatch):
    _, lease = await approved(shell_login.principal)
    home = managed_volume(lease.workspace_fingerprint, settings=shell_login.settings)
    conn = FakeConnection([home])
    monkeypatch.setattr(keystone, "get_cloud_shell_project_connection", lambda: conn)
    monkeypatch.setattr(cloud_shell, "_resolve_networking", AsyncMock(return_value=("network-a", "group-a")))
    create = MagicMock(side_effect=AssertionError("Native CREATE must not start after browser disconnect"))
    monkeypatch.setattr(cloud_shell.zun, "create_cloud_shell_container", create)

    async def status(phase):
        if phase == "container":
            raise WebSocketDisconnect()

    with pytest.raises(cloud_shell.CloudShellUnavailable):
        await cloud_shell.provision_session(lease, status)
    await cloud_shell.abandon_lease(lease)
    assert await cloud_shell._reconcile_credentials(conn, [], shell_login.settings) == 0
    assert await authority.receipt(lease.session_id) is None
    assert conn.block_storage.items == [home] and conn.block_storage.deleted == []
    assert lease.token in shell_login.revoked
    replacement = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert (await cloud_shell.consume_cloud_shell_ticket(replacement["ticket"])).session_id != lease.session_id


@pytest.mark.asyncio
async def test_heartbeat_renewal_fences_stale_retirement_and_cleanup_blocks_renewal(shell_login):
    _, lease = await approved(shell_login.principal)
    stale = await authority.receipt(lease.session_id)
    assert await cloud_shell.refresh_heartbeat(lease)
    assert not await authority.update_receipt(
        lease.session_id, expected_version=stale["version"], cleanup_requested=True
    )
    await cloud_shell.assert_session_authority(lease)
    assert lease.token not in shell_login.revoked
    current = await authority.receipt(lease.session_id)
    assert await authority.update_receipt(lease.session_id, expected_version=current["version"], cleanup_requested=True)
    assert not await cloud_shell.refresh_heartbeat(lease)
    with pytest.raises(cloud_shell.CloudShellUnauthorized):
        await cloud_shell.assert_session_authority(lease)


@pytest.mark.asyncio
async def test_fallback_stale_heartbeat_cannot_delete_receipt_backed_live_container(shell_login, monkeypatch):
    _, lease = await approved(shell_login.principal)
    now = int(time.time())
    labels = cloud_shell._container_labels(lease, now + 300, shell_login.settings)
    labels["afterglow.created_at"] = str(now - cloud_shell.CREATION_GRACE_SECONDS - 1)
    container = {"uuid": "live-container", "labels": labels, "status": "RUNNING"}
    redis = await authority._get_redis()
    await redis.zadd(authority.INDEX, {lease.session_id: now + 300})
    observed = False

    class StaleHeartbeatObservation:
        def __getattr__(self, name):
            return getattr(redis, name)

        async def get(self, key):
            nonlocal observed
            value = await redis.get(key)
            if key == lease.heartbeat_key and not observed:
                observed = True
                assert await cloud_shell.refresh_heartbeat(lease)
                return None
            return value

    monkeypatch.setattr(cloud_shell, "_get_redis", AsyncMock(return_value=StaleHeartbeatObservation()))
    conn = FakeConnection()
    monkeypatch.setattr("app.services.work_dispatcher.open_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr("app.services.work_dispatcher.close_connection", AsyncMock())
    monkeypatch.setattr("app.services.work_dispatcher.run_sync", AsyncMock(side_effect=lambda fn, *args: fn(*args)))
    monkeypatch.setattr(cloud_shell.zun, "list_containers_raw", lambda connection: [container])
    delete = MagicMock(side_effect=AssertionError("Stale fallback must not delete live session"))
    monkeypatch.setattr(cloud_shell, "_delete_exact_container_sync", delete)

    result = await cloud_shell.reconcile_once()
    assert observed and result == {"examined": 1, "deleted": 0}
    await cloud_shell.assert_session_authority(lease)
    assert lease.token not in shell_login.revoked


@pytest.mark.asyncio
async def test_coordination_outage_does_not_misreport_revoked_login_or_issue_native_token(shell_login, monkeypatch):
    monkeypatch.setattr(authority, "bind_login", AsyncMock(side_effect=ConnectionError("fixture outage")))
    with pytest.raises(cloud_shell.CloudShellUnavailable) as error:
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert error.value.code == "authority_unavailable"
    assert shell_login.tokens == {}


@pytest.mark.asyncio
async def test_slow_preparation_keeps_active_ownership_past_initial_heartbeat_ttl(shell_login, monkeypatch):
    monkeypatch.setattr(cloud_shell, "HEARTBEAT_TTL_SECONDS", 1)
    monkeypatch.setattr(cloud_shell, "HEARTBEAT_INTERVAL_SECONDS", 0.2)
    _, lease = await approved(shell_login.principal)
    keeper = asyncio.create_task(cloud_shell.renew_preparation_liveness(lease))
    try:
        await asyncio.sleep(1.2)
        await cloud_shell.assert_session_authority(lease)
        assert not keeper.done()
        assert await cloud_shell.refresh_heartbeat(lease)
    finally:
        keeper.cancel()
        await asyncio.gather(keeper, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelled_home_create_holds_workspace_lock_until_native_result_is_resolved(shell_login, monkeypatch):
    import threading

    _, lease = await approved(shell_login.principal)
    conn = FakeConnection()
    entered, release = threading.Event(), threading.Event()

    def blocked_create(connection, fingerprint, settings):
        entered.set()
        assert release.wait(5)
        home = managed_volume(fingerprint, settings=settings)
        connection.block_storage.items.append(home)
        return cloud_shell._workspace_record(home)

    monkeypatch.setattr(cloud_shell, "_create_workspace_sync", blocked_create)
    operation = asyncio.create_task(cloud_shell._ensure_workspace(conn, lease, AsyncMock()))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        operation.cancel()
        await asyncio.sleep(0)
        assert not operation.done()
        with pytest.raises(cloud_shell.CloudShellConflict):
            async with cloud_shell._redis_lock(
                cloud_shell._workspace_lock_key(lease.workspace_fingerprint), ttl_seconds=10, wait_seconds=0
            ):
                pytest.fail("Cancelled native write released its workspace lock early")
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await operation
    record = await authority.receipt(lease.session_id)
    assert record["home_creation_attempted"] and record["home_resolved"]
    await cloud_shell.abandon_lease(lease)
    assert len(conn.block_storage.items) == 1 and conn.block_storage.deleted == []
    replacement = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert (await cloud_shell.consume_cloud_shell_ticket(replacement["ticket"])).session_id != lease.session_id


@pytest.mark.asyncio
@pytest.mark.parametrize("revoke_fails", [False, True])
async def test_revocation_during_ticket_promotion_preserves_authority_error_and_cleanup(
    shell_login, monkeypatch, revoke_fails
):
    issued = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    native_token = next(iter(shell_login.tokens))
    if revoke_fails:
        monkeypatch.setattr(
            keystone, "revoke_token", lambda token: (_ for _ in ()).throw(RuntimeError("fixture unavailable"))
        )
    original = authority.update_receipt
    session_id = None

    async def revoke_before_promotion(sid, **changes):
        nonlocal session_id
        if changes.get("active"):
            session_id = sid
            await session_store.delete_session("shell-login-a")
        return await original(sid, **changes)

    monkeypatch.setattr(authority, "update_receipt", revoke_before_promotion)
    with pytest.raises(cloud_shell.CloudShellUnauthorized) as denied:
        await cloud_shell.consume_cloud_shell_ticket(issued["ticket"])
    assert denied.value.code == "session_revoked"
    record = await authority.receipt(session_id)
    if revoke_fails:
        assert record["cleanup_requested"] and not record["token_revoked"]
    else:
        assert record is None and native_token in shell_login.revoked


@pytest.mark.asyncio
@pytest.mark.parametrize("broken", ["not-json", "{}", '{"lease":null}'])
async def test_malformed_receipt_does_not_block_healthy_credential_cleanup(shell_login, broken):
    await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    redis = await authority._get_redis()
    sid = (await redis.zrange(authority.INDEX, 0, -1))[0]
    await authority.update_receipt(sid, ticket_deadline=int(time.time()) - 1)
    await redis.zadd(authority.INDEX, {sid: 0, "malformed": -1})
    await redis.set(authority.PREFIX + "malformed", broken, ex=600)
    assert await cloud_shell._reconcile_credentials(None, [], shell_login.settings) == 1
    assert await redis.get(authority.PREFIX + "malformed") == broken
    assert await authority.receipt(sid) is None
    assert next(iter(shell_login.tokens)) in shell_login.revoked


@pytest.mark.asyncio
async def test_unknown_create_blocks_replacement_after_all_liveness_keys_expire(shell_login):
    _, lease = await approved(shell_login.principal)
    await authority.update_receipt(lease.session_id, creation_attempted=True)
    await authority.revoke_credential(lease.session_id)
    redis = await authority._get_redis()
    await redis.delete(lease.active_key, lease.heartbeat_key)
    with pytest.raises(cloud_shell.CloudShellConflict):
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert await authority.receipt(lease.session_id) is not None


@pytest.mark.asyncio
async def test_unknown_resource_owner_blocks_home_reset_without_liveness(shell_login, monkeypatch):
    _, lease = await approved(shell_login.principal)
    home = managed_volume(lease.workspace_fingerprint, settings=shell_login.settings)
    conn = FakeConnection([home])
    monkeypatch.setattr(keystone, "get_cloud_shell_project_connection", lambda: conn)
    await authority.update_receipt(lease.session_id, creation_attempted=True)
    redis = await authority._get_redis()
    await redis.delete(lease.active_key, lease.heartbeat_key)
    with pytest.raises(cloud_shell.CloudShellConflict):
        await cloud_shell.reset_workspace(shell_login.principal)
    assert conn.block_storage.items == [home] and conn.block_storage.deleted == []


@pytest.mark.asyncio
async def test_corrupt_peer_does_not_prevent_exact_other_token_revocation(shell_login):
    _, lease = await approved(shell_login.principal)
    await authority.update_receipt(lease.session_id, creation_attempted=True)
    redis = await authority._get_redis()
    await redis.set(authority.PREFIX + "malformed-peer", "not-json", ex=600)
    await redis.zadd(authority.USER_PREFIX + lease.user_fingerprint, {"malformed-peer": 0})
    with pytest.raises(authority.ShellAuthorityError):
        await authority.revoke_login_credentials(lease.user_id)
    assert lease.token in shell_login.revoked
    assert (await authority.receipt(lease.session_id))["cleanup_requested"]
    assert await redis.get(authority.PREFIX + "malformed-peer") == "not-json"


@pytest.mark.asyncio
async def test_corrupt_receipt_does_not_prevent_unrelated_signed_orphan_cleanup(shell_login, monkeypatch):
    from dataclasses import replace

    _, lease = await approved(shell_login.principal)
    now = int(time.time())
    orphan = replace(
        lease,
        session_id="orphan-session",
        user_id="user-b",
        user_fingerprint=cloud_shell.user_fingerprint("user-b"),
        workspace_fingerprint=cloud_shell.workspace_fingerprint("user-b", PROJECT_ID),
    )
    rows = {
        "corrupt-container": {
            "uuid": "corrupt-container",
            "status": "STOPPED",
            "labels": cloud_shell._container_labels(lease, now - 1, shell_login.settings),
        },
        "orphan-container": {
            "uuid": "orphan-container",
            "status": "STOPPED",
            "labels": cloud_shell._container_labels(orphan, now - 1, shell_login.settings),
        },
    }
    redis = await authority._get_redis()
    await redis.set(authority.PREFIX + lease.session_id, "not-json", ex=600)
    await redis.zadd(authority.INDEX, {lease.session_id: 0})
    conn = FakeConnection()
    monkeypatch.setattr("app.services.work_dispatcher.open_connection", AsyncMock(return_value=conn))
    monkeypatch.setattr("app.services.work_dispatcher.close_connection", AsyncMock())
    monkeypatch.setattr("app.services.work_dispatcher.run_sync", AsyncMock(side_effect=lambda fn, *args: fn(*args)))
    monkeypatch.setattr("app.services.work_dispatcher.checkpoint", AsyncMock())
    monkeypatch.setattr(cloud_shell.zun, "list_containers_raw", lambda connection: list(rows.values()))
    monkeypatch.setattr(cloud_shell.zun, "get_container_raw", lambda connection, cid: rows.get(cid))
    monkeypatch.setattr(cloud_shell.zun, "delete_container_strict", lambda connection, cid: rows.pop(cid))
    assert await cloud_shell.reconcile_once() == {"examined": 2, "deleted": 1}
    assert set(rows) == {"corrupt-container"}
    assert await redis.get(authority.PREFIX + lease.session_id) == "not-json"


@pytest.mark.asyncio
async def test_concurrent_tickets_cannot_replace_the_persistent_resource_owner(shell_login):
    attempts = await asyncio.gather(
        *(cloud_shell.issue_cloud_shell_ticket(shell_login.principal) for _ in range(4)), return_exceptions=True
    )
    winners = [result for result in attempts if isinstance(result, dict)]
    assert len(winners) == 1
    assert all(
        isinstance(result, cloud_shell.CloudShellConflict) for result in attempts if not isinstance(result, dict)
    )
    lease = await cloud_shell.consume_cloud_shell_ticket(winners[0]["ticket"])
    await cloud_shell.assert_session_authority(lease)
    await cloud_shell.abandon_lease(lease)
    replacement = await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert (await cloud_shell.consume_cloud_shell_ticket(replacement["ticket"])).session_id != lease.session_id


@pytest.mark.asyncio
async def test_lost_cleanup_receipt_never_silently_unlocks_unknown_native_owner(shell_login):
    _, lease = await approved(shell_login.principal)
    redis = await authority._get_redis()
    await redis.delete(authority.PREFIX + lease.session_id, lease.active_key, lease.heartbeat_key)
    with pytest.raises(cloud_shell.CloudShellConflict):
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)


@pytest.mark.asyncio
async def test_missing_creation_flag_cannot_discard_uncertain_resource_ownership(shell_login):
    import json

    _, lease = await approved(shell_login.principal)
    await authority.update_receipt(lease.session_id, creation_attempted=True)
    assert await authority.revoke_credential(lease.session_id)
    record = await authority.receipt(lease.session_id)
    del record["creation_attempted"]
    redis = await authority._get_redis()
    await redis.set(authority.PREFIX + lease.session_id, json.dumps(record), ex=600)
    with pytest.raises(ValueError):
        await authority.finish_receipt(lease.session_id)
    await redis.delete(lease.active_key, lease.heartbeat_key)
    with pytest.raises(cloud_shell.CloudShellConflict):
        await cloud_shell.issue_cloud_shell_ticket(shell_login.principal)
    assert await redis.get(lease.ownership_key) == lease.active_value


@pytest.mark.asyncio
async def test_missing_active_flag_cannot_bypass_live_ownership_check(shell_login):
    import json

    _, lease = await approved(shell_login.principal)
    record = await authority.receipt(lease.session_id)
    del record["active"]
    redis = await authority._get_redis()
    await redis.set(authority.PREFIX + lease.session_id, json.dumps(record), ex=600)
    await redis.delete(lease.active_key, lease.heartbeat_key)
    with pytest.raises(cloud_shell.CloudShellUnavailable):
        await cloud_shell.assert_session_authority(lease)
