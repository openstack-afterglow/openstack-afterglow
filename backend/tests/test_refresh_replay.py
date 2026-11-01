"""Lost refresh responses replay only while their exact replacement is valid.

Real HTTP routes, JWT signatures and fakeredis Lua run without a native network.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from redis.exceptions import TimeoutError as RedisTimeoutError

from app.api.identity import auth
from app.services import jwt_service, session_store
from tests.test_auth_rotation_security import _login, _session
from tests.test_auth_rotation_security import security_client as security_client

pytestmark = pytest.mark.asyncio


async def _refresh(client, tokens, **kwargs):
    return await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}, **kwargs)


async def _write_receipt(redis, old_jti, record):
    record = dict(record)
    record["response_json"] = json.dumps(record.pop("response"))
    await redis.set(session_store._refresh_replay_key(old_jti), json.dumps(record), ex=30)


@pytest.fixture
async def rotation(security_client):
    old = await _login(security_client)
    response = await _refresh(security_client, old)
    assert response.status_code == 200, response.text
    new = response.json()
    old_jti = jwt_service.verify_refresh(old["refresh_token"])["jti"]
    new_jti, session = await _session(new)
    return old, new, old_jti, new_jti, session


async def test_retry_returns_identical_response_without_session_or_lifetime_extension(
    security_client, rotation, _fake_redis_global
):
    old, new, old_jti, new_jti, session = rotation
    replay_key = session_store._refresh_replay_key(old_jti)
    assert replay_key == f"afterglow:refresh-replay:{hashlib.sha256(old_jti.encode()).hexdigest()}"
    assert 0 < await _fake_redis_global.ttl(replay_key) <= session_store.REFRESH_REPLAY_SECONDS
    await _fake_redis_global.pexpire(replay_key, 15000)
    before = await _fake_redis_global.get(session_store._key(new_jti))
    session_ttl = await _fake_redis_global.pttl(session_store._key(new_jti))
    with patch.object(session_store, "store_session", AsyncMock(side_effect=AssertionError("Replay must not rotate"))):
        response = await _refresh(security_client, old)
    assert response.status_code == 200, response.text
    assert response.json() == new
    assert await session_store.get_session(old_jti) is None
    assert await _fake_redis_global.get(session_store._key(new_jti)) == before
    assert await _fake_redis_global.pttl(session_store._key(new_jti)) <= session_ttl
    assert 0 < await _fake_redis_global.pttl(replay_key) <= 15000
    assert await _fake_redis_global.keys("afterglow:refresh:*") == [session_store._key(new_jti)]
    assert await _fake_redis_global.smembers(session_store._user_index_key(session["user_id"])) == {new_jti}


@pytest.mark.parametrize(
    "change",
    ["logout", "rotation", "scope", "blacklist", "absent", "expired", "user", "session_user", "family", "revision"],
)
async def test_retry_rejects_invalidated_replacement(security_client, rotation, _fake_redis_global, change):
    old, new, old_jti, new_jti, session = rotation
    replay_key = session_store._refresh_replay_key(old_jti)
    if change == "logout":
        with patch.object(auth.keystone, "revoke_token"):
            response = await security_client.post(
                "/api/v1/auth/logout", headers={"Authorization": f"Bearer {new['token']}"}
            )
        assert response.status_code == 200, response.text
        assert await session_store.get_session(new_jti) is None
    elif change == "rotation":
        response = await _refresh(security_client, new)
        assert response.status_code == 200, response.text
        assert await session_store.get_session(new_jti) is None
    elif change == "scope":
        response = await security_client.post(
            "/api/v1/auth/token/project",
            json={"project_id": "second-project"},
            headers={"Authorization": f"Bearer {new['token']}"},
        )
        assert response.status_code == 200, response.text
    elif change == "blacklist":
        await session_store.blacklist_session(new_jti, "synthetic revocation")
    elif change == "absent":
        await _fake_redis_global.delete(replay_key)
    elif change == "expired":
        await _fake_redis_global.expire(replay_key, 0)
    elif change == "user":
        record = await session_store.get_refresh_replay(old_jti)
        record["user_id"] = "another-user"
        await _write_receipt(_fake_redis_global, old_jti, record)
    elif change in {"session_user", "family", "revision"}:
        field = {"session_user": "user_id", "family": "family_id", "revision": "scope_revision"}[change]
        session[field] = 99 if change == "revision" else "another-identity"
        await _fake_redis_global.set(session_store._key(new_jti), json.dumps(session), ex=3600)
    response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text
    assert "refresh_token" not in response.json()


async def test_retry_checks_replacement_absolute_timeout(security_client, rotation, _fake_redis_global):
    old, _, _, new_jti, session = rotation
    session["started_at"] = time.time() - 3601
    await _fake_redis_global.set(session_store._key(new_jti), json.dumps(session), ex=3600)
    response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text
    # A tampered absolute start no longer matches the immutable receipt.
    assert await session_store.get_session(new_jti) is not None


async def test_retry_binding_mismatch_blacklists_replacement(security_client, rotation):
    old, _, _, new_jti, _ = rotation
    response = await _refresh(security_client, old, headers={"User-Agent": "stolen-device"})
    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "토큰 출처가 일치하지 않습니다."
    assert (await session_store.get_session(new_jti))["blacklisted"] is True
    assert (await _refresh(security_client, old)).status_code == 401


@pytest.mark.parametrize("value", ["not-json", "[]", "null", '{"user_id":"security-user","new_jti":"jti"}'])
async def test_malformed_record_is_denied(security_client, rotation, _fake_redis_global, value):
    old, _, old_jti, _, _ = rotation
    await _fake_redis_global.set(session_store._refresh_replay_key(old_jti), value, ex=30)
    response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text


@pytest.mark.parametrize("token", ["not-a-jwt", "old-refresh"])
async def test_record_with_invalid_or_mismatched_refresh_is_denied(
    security_client, rotation, _fake_redis_global, token
):
    old, _, old_jti, _, _ = rotation
    record = await session_store.get_refresh_replay(old_jti)
    record["response"]["refresh_token"] = old["refresh_token"] if token == "old-refresh" else token
    await _write_receipt(_fake_redis_global, old_jti, record)
    response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text


async def test_lost_eval_reply_recovers_exact_atomic_attempt(security_client, _fake_redis_global, monkeypatch, caplog):
    old = await _login(security_client)
    old_jti, original = await _session(old)
    original_eval = _fake_redis_global.eval
    attempts = []

    async def lose_reply(script, *args):
        if script != session_store._ROTATE_SESSION_SCRIPT:
            return await original_eval(script, *args)
        attempts.append(args)
        result = await original_eval(script, *args)
        if len(attempts) == 1:
            assert await session_store.get_session(old_jti) is None
            assert await session_store.get_refresh_replay(old_jti) is not None
            raise RedisTimeoutError("synthetic-lost-reply-secret")
        return result

    monkeypatch.setattr(_fake_redis_global, "eval", lose_reply)
    with patch.object(session_store, "_revoke_shell_credentials", AsyncMock()) as cleanup:
        response = await _refresh(security_client, old)
    assert response.status_code == 200, response.text
    assert len(attempts) == 2 and attempts[0] == attempts[1]
    cleanup.assert_not_awaited()
    new_jti, session = await _session(response.json())
    assert session["started_at"] == original["started_at"]
    assert session["scope_revision"] == original["scope_revision"]
    receipt = await session_store.get_refresh_replay(old_jti)
    assert receipt["response"] == response.json()
    assert receipt["new_jti"] == new_jti
    assert (await _refresh(security_client, old)).json() == response.json()
    assert "synthetic-lost-reply-secret" not in caplog.text


@pytest.mark.parametrize("failure", ["record", "session"])
async def test_replay_redis_lookup_failure_reports_503(security_client, rotation, failure):
    old, _, _, new_jti, _ = rotation
    original = session_store.get_session

    async def lookup(jti):
        if jti == new_jti:
            raise ConnectionError("synthetic Redis outage")
        return await original(jti)

    target = "get_refresh_replay" if failure == "record" else "get_session"
    replacement = AsyncMock(side_effect=ConnectionError("synthetic Redis outage")) if failure == "record" else lookup
    with patch.object(session_store, target, replacement):
        response = await _refresh(security_client, old)
    assert response.status_code == 503, response.text
    assert await session_store.get_session(new_jti) is not None


@pytest.mark.parametrize("kind", ["policy", "policy_outage", "native", "native_outage"])
async def test_replay_requires_current_policy_and_native_proof(security_client, rotation, kind):
    from app.services import domain_auth

    old, _, _, new_jti, _ = rotation
    if kind.startswith("policy"):
        target, attribute = domain_auth, "require_password"
        error = (
            domain_auth.DomainAuthDenied("Password login disabled", code="password_disabled")
            if kind == "policy"
            else HTTPException(503, "Policy unavailable")
        )
    else:
        target, attribute = auth, "_exchange_native_scope"
        error = HTTPException(401 if kind == "native" else 503, "Native proof unavailable")
    with patch.object(target, attribute, AsyncMock(side_effect=error)) as live_check:
        response = await _refresh(security_client, old)
    assert response.status_code == {"policy": 403, "policy_outage": 503, "native": 401, "native_outage": 503}[kind]
    live_check.assert_awaited()
    assert "refresh_token" not in response.json()
    if kind == "native":
        assert await session_store.get_session(new_jti) is None


@pytest.mark.parametrize("status", [403, 503])
async def test_replay_rechecks_current_provider(security_client, _fake_redis_global, status):
    from app.services import domain_auth

    old = await _login(security_client)
    old_jti, session = await _session(old)
    session.update(
        auth_method="oidc",
        provider_id="provider",
        provider_revision=3,
        provider_domain_id="accounts",
        login_email="actual@example.test",
    )
    await _fake_redis_global.set(session_store._key(old_jti), json.dumps(session), keepttl=True)
    with patch.object(domain_auth, "require_provider", AsyncMock(return_value=SimpleNamespace(_organization=None))):
        response = await _refresh(security_client, old)
    assert response.status_code == 200, response.text
    with patch.object(
        domain_auth, "require_provider", AsyncMock(side_effect=HTTPException(status, "Provider revoked"))
    ) as check:
        replay = await _refresh(security_client, old)
    assert replay.status_code == status, replay.text
    check.assert_awaited_once_with("accounts", "provider", 3, "actual@example.test")
    assert "refresh_token" not in replay.json()


async def test_replay_fences_logout_during_current_policy_read(security_client, rotation):
    old, _, _, new_jti, _ = rotation
    original = auth._enforce_session_policy

    async def revoke(session, identity):
        await original(session, identity)
        await session_store.delete_session(new_jti)

    with patch.object(auth, "_enforce_session_policy", revoke):
        response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text


async def test_scope_switch_never_publishes_refresh_receipt(security_client, _fake_redis_global):
    old = await _login(security_client)
    old_jti, _ = await _session(old)
    response = await security_client.post(
        "/api/v1/auth/token/project",
        json={"project_id": "second-project"},
        headers={"Authorization": f"Bearer {old['token']}"},
    )
    assert response.status_code == 200, response.text
    assert await _fake_redis_global.get(session_store._refresh_replay_key(old_jti)) is None
    assert (await _refresh(security_client, old)).status_code == 401


async def test_response_loss_after_atomic_publication_replays_committed_response(security_client):
    old = await _login(security_client)
    old_jti, _ = await _session(old)
    original = auth._build_token_response
    committed = None

    async def lose_response(**kwargs):
        nonlocal committed
        committed = await original(**kwargs)
        raise HTTPException(503, "Synthetic response loss after commit")

    with patch.object(auth, "_build_token_response", lose_response):
        lost = await _refresh(security_client, old)
    assert lost.status_code == 503
    receipt = await session_store.get_refresh_replay(old_jti)
    assert receipt["response"] == committed.model_dump(mode="json")
    replay = await _refresh(security_client, old)
    assert replay.status_code == 200, replay.text
    assert replay.json() == committed.model_dump(mode="json")


@pytest.mark.parametrize("change", ["blacklist", "old_jti", "attempt", "family_current"])
async def test_lost_eval_reply_cannot_recover_unbound_or_revoked_receipt(
    security_client, _fake_redis_global, monkeypatch, change
):
    old = await _login(security_client)
    old_jti, _ = await _session(old)
    original_eval = _fake_redis_global.eval
    interrupted = False

    async def lose_reply(script, *args):
        nonlocal interrupted
        result = await original_eval(script, *args)
        if script == session_store._ROTATE_SESSION_SCRIPT and not interrupted:
            interrupted = True
            receipt = await session_store.get_refresh_replay(old_jti)
            if change == "blacklist":
                await session_store.blacklist_session(receipt["new_jti"], "revoked before reply")
            elif change == "family_current":
                await _fake_redis_global.set(
                    session_store._FAMILY_PREFIX + receipt["session"]["family_id"], "unrelated", ex=30
                )
            else:
                receipt[change] = "unrelated"
                await _write_receipt(_fake_redis_global, old_jti, receipt)
            raise RedisTimeoutError("synthetic lost reply")
        return result

    monkeypatch.setattr(_fake_redis_global, "eval", lose_reply)
    response = await _refresh(security_client, old)
    # Attempt identity guards the internal EVAL retry. A changed attempt field
    # alone does not invalidate the independently signed HTTP replay response.
    assert response.status_code == (200 if change == "attempt" else 401), response.text


async def test_receipt_lifetime_is_capped_by_absolute_session_deadline(_fake_redis_global):
    now = int(time.time())
    assert await session_store.store_session(
        "short-old", "native", "project", "user", now + 8, domain_id="domain", started_at=now
    )
    assert await session_store.store_session(
        "short-new",
        "native",
        "project",
        "user",
        now + 8,
        domain_id="domain",
        started_at=now,
        previous_jti="short-old",
        timeout_seconds=3600,
        previous_refresh_exp=now + 8,
        refresh_replay={"roles": [], "available_domains": [], "nullable": None},
    )
    assert 0 < await _fake_redis_global.ttl(session_store._refresh_replay_key("short-old")) <= 8
    receipt = await session_store.get_refresh_replay("short-old")
    assert receipt["response"] == {"roles": [], "available_domains": [], "nullable": None}


async def test_expired_signed_old_refresh_never_uses_receipt(security_client, rotation):
    old, _, _, _, _ = rotation
    payload = jwt_service.verify_refresh(old["refresh_token"])
    with patch("jwt.api_jwt.datetime") as clock:
        clock.now.return_value = datetime.fromtimestamp(payload["exp"] + 1, UTC)
        with patch.object(auth, "_exchange_native_scope", AsyncMock()) as native:
            response = await _refresh(security_client, old)
    assert response.status_code == 401, response.text
    native.assert_not_awaited()


async def test_legacy_record_rotates_and_replays_without_family_metadata(security_client, _fake_redis_global):
    old = await _login(security_client)
    old_jti, session = await _session(old)
    family = session["family_id"]
    for field in ("family_id", "scope_revision", "started_at"):
        session.pop(field, None)
    await _fake_redis_global.delete(session_store._FAMILY_PREFIX + family)
    await _fake_redis_global.set(session_store._key(old_jti), json.dumps(session), keepttl=True)
    response = await _refresh(security_client, old)
    assert response.status_code == 200, response.text
    new_jti, current = await _session(response.json())
    assert current["family_id"] == old_jti and current["scope_revision"] == 0
    assert current["started_at"] <= jwt_service.verify_refresh(old["refresh_token"])["iat"]
    replay = await _refresh(security_client, old)
    assert replay.status_code == 200 and replay.json() == response.json()
    assert await session_store.get_session(old_jti) is None
    assert await session_store.get_session(new_jti) is not None


async def test_scope_rotation_does_not_retry_lost_eval_reply(_fake_redis_global, monkeypatch):
    now = int(time.time())
    assert await session_store.store_session("scope-old", "native", "project", "user", now + 600, domain_id="domain")
    original_eval = _fake_redis_global.eval
    calls = 0

    async def lose_reply(script, *args):
        nonlocal calls
        if script != session_store._ROTATE_SESSION_SCRIPT:
            return await original_eval(script, *args)
        calls += 1
        await original_eval(script, *args)
        raise RedisTimeoutError("synthetic lost scope reply")

    monkeypatch.setattr(_fake_redis_global, "eval", lose_reply)
    with pytest.raises(RedisTimeoutError):
        await session_store.store_session(
            "scope-new",
            "native",
            "project",
            "user",
            now + 600,
            domain_id="domain",
            previous_jti="scope-old",
            timeout_seconds=3600,
        )
    assert calls == 1
    assert await session_store.get_session("scope-new") is not None
    assert await _fake_redis_global.get(session_store._refresh_replay_key("scope-old")) is None


@pytest.mark.parametrize("status", [401, 503])
async def test_replay_rejects_changed_or_unavailable_native_deadline(security_client, rotation, status):
    old, _, _, _, _ = rotation
    original = auth._exchange_native_scope

    async def changed_deadline(*args, **kwargs):
        identity = await original(*args, **kwargs)
        identity["session_expires_at"] = (
            datetime.fromtimestamp(time.time() + 60, UTC).isoformat() if status == 401 else "invalid-expiry"
        )
        return identity

    with patch.object(auth, "_exchange_native_scope", changed_deadline):
        response = await _refresh(security_client, old)
    assert response.status_code == status, response.text
    assert "refresh_token" not in response.json()


async def test_lost_eval_reply_rechecks_policy_before_recovering_response(
    security_client, _fake_redis_global, monkeypatch
):
    from app.services import domain_auth

    old = await _login(security_client)
    original_eval = _fake_redis_global.eval
    interrupted = False
    revoked = AsyncMock(side_effect=domain_auth.DomainAuthDenied("Password disabled after commit"))

    async def lose_reply(script, *args):
        nonlocal interrupted
        result = await original_eval(script, *args)
        if script == session_store._ROTATE_SESSION_SCRIPT and not interrupted:
            interrupted = True
            monkeypatch.setattr(domain_auth, "require_password", revoked)
            raise RedisTimeoutError("synthetic lost reply")
        return result

    monkeypatch.setattr(_fake_redis_global, "eval", lose_reply)
    response = await _refresh(security_client, old)
    assert response.status_code == 403, response.text
    revoked.assert_awaited_once()
    assert "refresh_token" not in response.json()


async def test_concurrent_legacy_refresh_recovers_consumed_start_migration(
    security_client, _fake_redis_global, monkeypatch
):
    old = await _login(security_client)
    old_jti, session = await _session(old)
    session.pop("started_at")
    await _fake_redis_global.set(session_store._key(old_jti), json.dumps(session), keepttl=True)
    original_eval = _fake_redis_global.eval
    loser_queued = asyncio.Event()
    release_loser = asyncio.Event()
    start_calls = 0

    async def queue_legacy_migration(script, *args):
        nonlocal start_calls
        if script == session_store._START_SESSION_SCRIPT:
            start_calls += 1
            if start_calls == 1:
                loser_queued.set()
                await asyncio.wait_for(release_loser.wait(), 5)
        return await original_eval(script, *args)

    monkeypatch.setattr(_fake_redis_global, "eval", queue_legacy_migration)
    loser = asyncio.create_task(_refresh(security_client, old))
    await asyncio.wait_for(loser_queued.wait(), 5)
    try:
        winner = await _refresh(security_client, old)
        assert winner.status_code == 200, winner.text
        assert await session_store.get_session(old_jti) is None
    finally:
        release_loser.set()
    recovered = await loser
    assert recovered.status_code == 200, recovered.text
    assert recovered.json() == winner.json()
    assert start_calls == 2
    new_jti, current = await _session(winner.json())
    assert current["started_at"] <= jwt_service.verify_refresh(old["refresh_token"])["iat"]
    assert await _fake_redis_global.smembers(session_store._user_index_key(current["user_id"])) == {new_jti}
