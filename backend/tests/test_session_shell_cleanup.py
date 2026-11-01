"""Session/receipt Lua transitions with synthetic native revocation failures.

The same private namespaces run against fakeredis or AFTERGLOW_TEST_REAL_REDIS.
"""

from __future__ import annotations

import hashlib
import json
import time
from uuid import uuid4

import pytest
import pytest_asyncio

from app.services import cloud_shell_authority as authority
from app.services import keystone, session_store


@pytest_asyncio.fixture(autouse=True)
async def redis_client(_fake_redis_global, monkeypatch):
    client = _fake_redis_global or await session_store._get_redis()
    namespace = f"afterglow:session-shell-cleanup:{uuid4().hex}:"
    for attribute in ("_PREFIX", "_USER_INDEX_PREFIX", "_FAMILY_PREFIX", "_FAMILY_ALIAS_PREFIX"):
        monkeypatch.setattr(
            session_store, attribute, getattr(session_store, attribute).replace("afterglow:", namespace)
        )
    for attribute in ("_ROTATE_SESSION_SCRIPT", "_REVOKE_USER_SCRIPT", "_DELETE_SESSION_SCRIPT"):
        monkeypatch.setattr(
            session_store, attribute, getattr(session_store, attribute).replace("afterglow:", namespace)
        )
    for attribute in ("INDEX", "PREFIX", "USER_PREFIX", "OWNER_PREFIX"):
        monkeypatch.setattr(authority, attribute, getattr(authority, attribute).replace("afterglow:", namespace))
    try:
        yield client
    finally:
        keys = [key async for key in client.scan_iter(match=f"{namespace}*")]
        if keys:
            await client.delete(*keys)


async def login_with_receipt(jti="a"):
    exp = int(time.time()) + 600
    assert await session_store.store_session(
        jti, f"native-{jti}", "project", "user", exp, domain_id="domain", identity_domain_id="home"
    )
    session = await session_store.get_session(jti)
    binding = authority.binding_for(session, "project")
    payload = {
        **binding,
        "session_id": f"shell-{jti}",
        "username": "alice",
        "project_name": "fixture",
        "token": f"derived-{jti}",
        "token_expires_at": exp,
        "user_fingerprint": hashlib.sha256(b"cloud-shell-v1\0user").hexdigest(),
        "workspace_fingerprint": hashlib.sha256(b"workspace").hexdigest(),
        "active_value": f"shell-{jti}:workspace",
    }
    await authority.store_receipt(payload, int(time.time()) + 60)
    return exp, binding


def failing_native(monkeypatch, *, root=False, derived=True):
    attempted = []

    def revoke(token):
        attempted.append(token)
        if (root and token.startswith("native-")) or (derived and token.startswith("derived-")):
            raise RuntimeError("synthetic native revocation unavailable")

    monkeypatch.setattr(keystone, "revoke_token", revoke)
    return attempted


async def assert_pending(client, jti="a"):
    record = await authority.receipt(f"shell-{jti}")
    assert record["lease"]["token"] == f"derived-{jti}"
    assert record["lease"]["family_id"] == jti
    assert record["cleanup_requested"] is True
    assert record["token_revoked"] is False
    assert await client.zscore(authority.INDEX, f"shell-{jti}") == 0
    assert await client.zscore(authority.USER_PREFIX + record["lease"]["user_fingerprint"], f"shell-{jti}")
    assert await client.ttl(authority.PREFIX + f"shell-{jti}") > 0


async def assert_denied(binding, jti):
    with pytest.raises(authority.ShellAuthorityError):
        await authority.require_login(binding)
    with pytest.raises(authority.ShellAuthorityError):
        await authority.bind_login({**binding, "refresh_jti": jti})


@pytest.mark.asyncio
@pytest.mark.parametrize("switch_domain", [False, True])
async def test_scope_rotation_returns_committed_session_when_derived_cleanup_fails(
    switch_domain, redis_client, monkeypatch, caplog
):
    exp, old_binding = await login_with_receipt()
    attempted = failing_native(monkeypatch)
    target_domain = "target-domain" if switch_domain else "domain"
    assert await session_store.store_session(
        "b",
        "native-b",
        "project" if switch_domain else "target-project",
        "user",
        exp,
        domain_id=target_domain,
        identity_domain_id="home",
        previous_domain_id="domain",
        previous_jti="a",
        timeout_seconds=3600,
    )
    assert await session_store.get_session("a") is None
    current = await session_store.get_session("b")
    assert current["keystone_token"] == "native-b"
    assert current["family_id"] == "a" and current["scope_revision"] == 1
    assert await redis_client.get(session_store._FAMILY_PREFIX + "a") == "b"
    assert await redis_client.smembers(session_store._user_index_key("user")) == {"b"}
    binding = authority.binding_for(current, current["project_id"])
    assert (await authority.bind_login({**binding, "refresh_jti": "b"}))["keystone_token"] == "native-b"
    await assert_denied(old_binding, "a")
    assert not await session_store.store_session(
        "stale",
        "native-stale",
        "project",
        "user",
        exp,
        domain_id="domain",
        identity_domain_id="home",
        previous_jti="a",
        timeout_seconds=3600,
    )
    assert await session_store.get_session("stale") is None
    await assert_pending(redis_client)
    assert attempted == ["derived-a"]
    assert "Cloud Shell credential cleanup pending" in caplog.text
    assert "native-b" not in caplog.text and "derived-a" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["all", "owned", "logout", "blacklist"])
async def test_committed_revocation_survives_derived_cleanup_failure(operation, redis_client, monkeypatch):
    exp, binding = await login_with_receipt()
    _, other_binding = await login_with_receipt("other")
    # An old alias must target the rotated current row, never authenticate itself.
    assert await session_store.store_session(
        "b",
        "native-b",
        "project",
        "user",
        exp,
        domain_id="domain",
        identity_domain_id="home",
        previous_jti="a",
        timeout_seconds=3600,
    )
    attempted = failing_native(monkeypatch, root=True)
    if operation == "all":
        assert await session_store.revoke_user_sessions("user") == 2
    elif operation == "owned":
        assert await session_store.delete_session_owned("user", "a") is True
    elif operation == "logout":
        removed = await session_store.delete_session("a")
        assert removed["keystone_token"] == "native-b"
        assert removed["cloud_shell_cleanup_pending"] is True
    else:
        assert await session_store.blacklist_session("a", "origin_mismatch") is None
        assert (await session_store.get_session("b"))["blacklisted"] is True
        assert (await session_store.get_session("b"))["blacklist_reason"] == "origin_mismatch"
    assert await session_store.get_session("a") is None
    await assert_denied(binding, "b")
    assert not await session_store.update_session_token("b", "replacement")
    assert not await session_store.store_session(
        "c",
        "native-c",
        "project",
        "user",
        exp,
        domain_id="domain",
        identity_domain_id="home",
        previous_jti="b",
        timeout_seconds=3600,
    )
    assert await session_store.get_session("c") is None
    await assert_pending(redis_client)
    assert "derived-a" in attempted
    if operation == "all":
        assert set(attempted) == {"native-b", "native-other", "derived-a", "derived-other"}
        assert await session_store.list_user_sessions("user") == []
        await assert_denied(other_binding, "other")
        await assert_pending(redis_client, "other")
    else:
        assert (await authority.require_login(other_binding))["keystone_token"] == "native-other"
        assert (await authority.receipt("shell-other"))["cleanup_requested"] is False
    if operation != "blacklist":
        assert await session_store.get_session("b") is None
        assert not await redis_client.exists(session_store._FAMILY_PREFIX + "a")


@pytest.mark.asyncio
@pytest.mark.parametrize("root_failure,derived_failure", [(True, False), (False, True), (True, True)])
async def test_strict_revocation_reports_cleanup_failure_after_all_sessions_are_deleted(
    root_failure, derived_failure, redis_client, monkeypatch
):
    _, binding = await login_with_receipt()
    _, other_binding = await login_with_receipt("other")
    # A possibly admitted CREATE keeps resource cleanup authoritative even after token revocation.
    for jti in ("a", "other"):
        assert await authority.update_receipt(f"shell-{jti}", creation_attempted=True)
    attempted = failing_native(monkeypatch, root=root_failure, derived=derived_failure)
    error = authority.ShellAuthorityError if derived_failure else RuntimeError
    with pytest.raises(error, match="revocation"):
        await session_store.revoke_user_sessions("user", strict_keystone=True)
    assert set(attempted) == {"native-a", "native-other", "derived-a", "derived-other"}
    assert await session_store.list_user_sessions("user") == []
    for jti, original in (("a", binding), ("other", other_binding)):
        assert await session_store.get_session(jti) is None
        assert not await redis_client.exists(session_store._FAMILY_PREFIX + jti)
        await assert_denied(original, jti)
        if derived_failure:
            await assert_pending(redis_client, jti)
        else:
            record = await authority.receipt(f"shell-{jti}")
            assert record["cleanup_requested"] is True and record["token_revoked"] is True
            assert await redis_client.zscore(authority.INDEX, f"shell-{jti}") == 0


@pytest.mark.asyncio
async def test_origin_mismatch_blacklists_exact_legacy_record_without_family_mapping(redis_client):
    exp = int(time.time()) + 600
    legacy = {
        "user_id": "legacy-user",
        "keystone_token": "legacy-native",
        "project_id": "project",
        "domain_id": "domain",
        "identity_domain_id": "home",
        "exp": exp,
        "started_at": int(time.time()),
        "origin_ip": "192.0.2.1",
        "origin_fp": "original",
        "blacklisted": False,
    }
    await redis_client.setex(session_store._key("legacy"), 600, json.dumps(legacy))
    assert await session_store.blacklist_session("legacy", "origin_mismatch") is None
    current = await session_store.get_session("legacy")
    assert current["blacklisted"] is True and current["blacklist_reason"] == "origin_mismatch"
    assert current["origin_ip"] == legacy["origin_ip"] and current["origin_fp"] == legacy["origin_fp"]
    assert 0 < await redis_client.ttl(session_store._key("legacy")) <= 600
    assert not await redis_client.exists(session_store._FAMILY_PREFIX + "legacy")
    assert not await session_store.update_session_token("legacy", "replacement")
    assert not await session_store.store_session(
        "resurrected",
        "replacement",
        "project",
        "legacy-user",
        exp,
        domain_id="domain",
        identity_domain_id="home",
        previous_jti="legacy",
        timeout_seconds=3600,
    )
    assert await session_store.get_session("resurrected") is None
    await session_store.blacklist_session("missing", "origin_mismatch")
    assert await session_store.get_session("missing") is None
