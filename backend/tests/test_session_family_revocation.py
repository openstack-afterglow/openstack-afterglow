"""Real Redis Lua session-family revocation schedules; native revocation is synthetic."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from uuid import uuid4

import pytest
import pytest_asyncio

from app.services import keystone, session_store


@pytest_asyncio.fixture(autouse=True)
async def redis_client(_fake_redis_global, monkeypatch):
    """Run identical Lua schedules with fake or real Redis in a private namespace."""
    client = _fake_redis_global or await session_store._get_redis()
    namespace = f"afterglow:session-race:{uuid4().hex}:"
    for attribute in ("_PREFIX", "_USER_INDEX_PREFIX", "_FAMILY_PREFIX", "_FAMILY_ALIAS_PREFIX"):
        monkeypatch.setattr(
            session_store, attribute, getattr(session_store, attribute).replace("afterglow:", namespace)
        )
    for attribute in ("_ROTATE_SESSION_SCRIPT", "_REVOKE_USER_SCRIPT", "_DELETE_SESSION_SCRIPT"):
        monkeypatch.setattr(
            session_store, attribute, getattr(session_store, attribute).replace("afterglow:", namespace)
        )
    try:
        yield client
    finally:
        keys = [key async for key in client.scan_iter(match=f"{namespace}*")]
        if keys:
            await client.delete(*keys)


async def initial():
    exp = int(time.time()) + 600
    assert await session_store.store_session("a", "native-a", "project", "user", exp, domain_id="domain")
    return exp


async def rotate(
    exp,
    old="a",
    new="b",
    *,
    domain_id="domain",
    identity_domain_id="domain",
    previous_domain_id=None,
    user_id="user",
):
    return await session_store.store_session(
        new,
        "native-" + new,
        "project",
        user_id,
        exp,
        domain_id=domain_id,
        identity_domain_id=identity_domain_id,
        previous_domain_id=previous_domain_id,
        previous_jti=old,
        timeout_seconds=3600,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["user", "single", "logout"])
@pytest.mark.parametrize("switch_domain", [False, True])
async def test_revocation_started_before_rotation_removes_rotated_family(
    kind, switch_domain, redis_client, monkeypatch
):
    exp = await initial()
    started, release = asyncio.Event(), asyncio.Event()
    original_eval = redis_client.eval
    target = session_store._REVOKE_USER_SCRIPT if kind == "user" else session_store._DELETE_SESSION_SCRIPT

    async def scheduled(script, *args):
        if script == target:
            started.set()
            await release.wait()
        return await original_eval(script, *args)

    monkeypatch.setattr(redis_client, "eval", scheduled)
    if kind == "user":
        operation = session_store.revoke_user_sessions("user", revoke_keystone=False)
    elif kind == "single":
        operation = session_store.delete_session_owned("user", "a", revoke_keystone=False)
    else:
        operation = session_store.delete_session("a")
    pending = asyncio.create_task(operation)
    await started.wait()
    try:
        if switch_domain:
            assert await rotate(exp, domain_id="target", previous_domain_id="domain")
            assert await rotate(exp, "b", "c", domain_id="third", previous_domain_id="target")
        else:
            assert await rotate(exp)
            assert await rotate(exp, "b", "c")
    finally:
        release.set()
    result = await pending
    if kind != "logout":
        assert result == 1
    assert await session_store.get_session("a") is None
    assert await session_store.get_session("b") is None
    assert await session_store.get_session("c") is None
    assert await session_store.list_user_sessions("user") == []
    assert not await rotate(
        exp,
        "c",
        "d",
        domain_id="fourth" if switch_domain else "domain",
        previous_domain_id="third" if switch_domain else None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["user", "single"])
async def test_native_revocation_wait_cannot_leave_refresh_survivor(kind, monkeypatch):
    exp = await initial()
    started, release = threading.Event(), threading.Event()
    native_tokens = []

    def native_revoke(token):
        native_tokens.append(token)
        started.set()
        assert release.wait(timeout=5)

    monkeypatch.setattr(keystone, "revoke_token", native_revoke)
    operation = (
        session_store.revoke_user_sessions("user")
        if kind == "user"
        else session_store.delete_session_owned("user", "a")
    )
    pending = asyncio.create_task(operation)
    assert await asyncio.to_thread(started.wait, 5)
    try:
        assert await session_store.get_session("a") is None
        assert not await rotate(exp)
        assert await session_store.get_session("b") is None
    finally:
        release.set()
    assert await pending == 1
    assert native_tokens == ["native-a"]


@pytest.mark.asyncio
async def test_stale_jti_family_revocation_cannot_revoke_other_user(redis_client):
    exp = await initial()
    assert await rotate(exp)
    await redis_client.sadd(session_store._user_index_key("attacker"), "a", "b")
    assert not await session_store.delete_session_owned("attacker", "a", revoke_keystone=False)
    assert (await session_store.get_session("b"))["user_id"] == "user"
    assert await session_store.delete_session_owned("user", "a", revoke_keystone=False)
    assert await session_store.get_session("b") is None


@pytest.mark.asyncio
async def test_user_revoke_protects_foreign_row_in_corrupt_index(redis_client):
    exp = await initial()
    await session_store.store_session("other", "native-other", "project", "other-user", exp, domain_id="domain")
    await redis_client.sadd(session_store._user_index_key("user"), "other")
    assert await session_store.revoke_user_sessions("user", revoke_keystone=False) == 1
    assert (await session_store.get_session("other"))["user_id"] == "other-user"
    assert await session_store.get_session("a") is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"domain_id": "target"},
        {"domain_id": "target", "previous_domain_id": "foreign"},
        {"domain_id": "target", "previous_domain_id": ""},
        {"domain_id": "target", "previous_domain_id": "domain", "identity_domain_id": "foreign"},
        {"domain_id": "target", "previous_domain_id": "domain", "user_id": "foreign-user"},
        {"domain_id": "", "previous_domain_id": "domain"},
        {"identity_domain_id": "foreign"},
    ],
)
async def test_rotation_denies_untrusted_domain_or_identity_without_publication(fields, redis_client):
    exp = await initial()
    original = await session_store.get_session("a")
    assert original["identity_domain_id"] == "domain"
    assert not await rotate(exp, **fields)
    assert await session_store.get_session("a") == original
    assert await session_store.get_session("b") is None
    assert await redis_client.get(f"{session_store._FAMILY_PREFIX}a") == "a"
    assert await redis_client.smembers(session_store._user_index_key("user")) == {"a"}
    assert not await redis_client.exists(f"{session_store._FAMILY_ALIAS_PREFIX}b")
    assert not await redis_client.exists(session_store._user_index_key("foreign-user"))


@pytest.mark.asyncio
async def test_explicit_switch_preserves_latest_identity_origin_and_absolute_lifetime(redis_client):
    exp = int(time.time()) + 600
    assert await session_store.store_session(
        "a",
        "native-a",
        "project",
        "user",
        exp,
        domain_id="domain",
        identity_domain_id="identity-home",
    )
    # Simulate a concurrent update after the caller took its validation snapshot.
    original = await session_store.get_session("a")
    preserved = {
        "origin_ip": "192.0.2.10",
        "origin_fp": "original-fingerprint",
        "device_type": "desktop",
        "os": "original-os",
        "auth_method": "oidc",
        "provider_id": "original-provider",
        "provider_revision": 7,
        "login_email": "original@example.test",
        "started_at": int(time.time()) - 120,
    }
    original.update(preserved)
    await redis_client.set(session_store._key("a"), json.dumps(original), keepttl=True)
    assert await session_store.store_session(
        "b",
        "native-b",
        "target-project",
        "user",
        exp,
        domain_id="target",
        identity_domain_id="identity-home",
        previous_domain_id="domain",
        previous_jti="a",
        timeout_seconds=3600,
        started_at=int(time.time()),
        origin_ip="198.51.100.20",
        origin_fp="new-fingerprint",
        device_type="mobile",
        os="new-os",
        auth_method="password",
        provider_id="new-provider",
        provider_revision=99,
        login_email="new@example.test",
    )
    current = await session_store.get_session("b")
    assert current["domain_id"] == "target"
    assert current["identity_domain_id"] == "identity-home"
    assert current["keystone_token"] == "native-b"
    assert current["project_id"] == "target-project"
    assert current["exp"] == exp
    assert current["family_id"] == "a"
    assert {field: current[field] for field in preserved} == preserved
    assert 0 < await redis_client.ttl(session_store._key("b")) <= exp - int(time.time()) + 1
    assert await session_store.get_session("a") is None
    assert await redis_client.smembers(session_store._user_index_key("user")) == {"b"}
    assert await redis_client.get(f"{session_store._FAMILY_PREFIX}a") == "b"
    for jti in ("a", "b"):
        assert await redis_client.get(f"{session_store._FAMILY_ALIAS_PREFIX}{jti}") == "a"

    # A validated stale old-domain context cannot switch the current replacement.
    assert not await rotate(
        exp, "b", "stale", domain_id="third", identity_domain_id="identity-home", previous_domain_id="domain"
    )
    assert await session_store.get_session("stale") is None
    # Ordinary refresh in the new working domain still retains the identity home.
    assert await rotate(exp, "b", "c", domain_id="target", identity_domain_id="identity-home")
    assert (await session_store.get_session("c"))["identity_domain_id"] == "identity-home"


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_identity", [None, ""])
async def test_legacy_identity_normalizes_only_from_old_domain(legacy_identity, redis_client):
    exp = await initial()
    original = await session_store.get_session("a")
    if legacy_identity is None:
        original.pop("identity_domain_id")
    else:
        original["identity_domain_id"] = legacy_identity
    await redis_client.set(session_store._key("a"), json.dumps(original), keepttl=True)
    # Supplying the target as identity cannot rebind a pre-multidomain session.
    assert not await rotate(exp, domain_id="target", identity_domain_id="target", previous_domain_id="domain")
    assert not await rotate(exp, domain_id="target", identity_domain_id="", previous_domain_id="domain")
    assert await session_store.get_session("a") == original
    assert await session_store.get_session("b") is None
    assert await rotate(exp, domain_id="target", previous_domain_id="domain")
    assert (await session_store.get_session("b"))["identity_domain_id"] == "domain"


@pytest.mark.asyncio
async def test_concurrent_domain_switch_consumes_old_jti_once(redis_client):
    exp = await initial()
    results = await asyncio.gather(
        rotate(exp, new="b", domain_id="target-b", previous_domain_id="domain"),
        rotate(exp, new="c", domain_id="target-c", previous_domain_id="domain"),
    )
    assert sorted(results) == [False, True]
    winner, loser = ("b", "c") if results[0] else ("c", "b")
    assert (await session_store.get_session(winner))["identity_domain_id"] == "domain"
    assert await session_store.get_session(loser) is None
    assert await session_store.get_session("a") is None
    assert await redis_client.smembers(session_store._user_index_key("user")) == {winner}
    assert await redis_client.get(f"{session_store._FAMILY_PREFIX}a") == winner
    assert not await rotate(exp, new="replay", domain_id="target", previous_domain_id="domain")
    assert await session_store.get_session("replay") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["user", "single", "logout"])
async def test_switched_family_revocation_resolves_old_alias(kind):
    exp = await initial()
    assert await rotate(exp, domain_id="target", previous_domain_id="domain")
    if kind == "user":
        assert await session_store.revoke_user_sessions("user", revoke_keystone=False) == 1
    elif kind == "single":
        assert await session_store.delete_session_owned("user", "a", revoke_keystone=False)
    else:
        assert (await session_store.delete_session("a"))["keystone_token"] == "native-b"
    assert await session_store.get_session("b") is None
    assert await session_store.list_user_sessions("user") == []
    assert not await rotate(exp, "b", "c", domain_id="third", previous_domain_id="target")


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["expired", "blacklisted", "stale-family"])
async def test_domain_switch_cannot_revive_invalid_session(invalid, redis_client):
    exp = await initial()
    original = await session_store.get_session("a")
    if invalid == "expired":
        original["started_at"] = int(time.time()) - 3600
    elif invalid == "blacklisted":
        original["blacklisted"] = True
    else:
        await redis_client.set(f"{session_store._FAMILY_PREFIX}a", "newer-jti", ex=600)
    await redis_client.set(session_store._key("a"), json.dumps(original), keepttl=True)
    assert not await rotate(exp, domain_id="target", previous_domain_id="domain")
    assert await session_store.get_session("b") is None
    assert not await redis_client.exists(f"{session_store._FAMILY_ALIAS_PREFIX}b")
    if invalid == "expired":
        assert await session_store.get_session("a") is None
        assert await redis_client.smembers(session_store._user_index_key("user")) == set()
    else:
        assert await session_store.get_session("a") == original


@pytest.mark.asyncio
async def test_ordinary_legacy_caller_may_omit_identity_domain():
    exp = await initial()
    assert await session_store.store_session(
        "b",
        "native-b",
        "project",
        "user",
        exp,
        domain_id="domain",
        previous_jti="a",
        timeout_seconds=3600,
    )
    assert (await session_store.get_session("b"))["identity_domain_id"] == "domain"
