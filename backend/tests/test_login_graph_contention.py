"""Real HTTP login/session/personal consumers with isolated Redis graph contention."""

import asyncio
import hashlib

import fakeredis.aioredis
import pytest

from app.services import account_spaces, identity_roles, jwt_service, session_store
from tests.ownership_journal import ownership_journal as ownership_journal
from tests.test_domain_projects import domain_native as domain_native
from tests.test_login_native_operation import login, provider_login
from tests.test_login_native_operation import native_login as native_login

_GRAPH_LOCK = identity_roles._graph_lock


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["password", "provider"])
async def test_login_waits_for_graph_without_replaying_auth_or_skipping_personal(native_login, monkeypatch, method):
    client, native = native_login
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    registered = asyncio.Event()
    queue = "afterglow:identity-role-graph:" + hashlib.sha256(b"https://native.test/v3").hexdigest() + ":waiters"
    original_pipeline = redis.pipeline

    def pipeline(*args, **kwargs):
        pipe = original_pipeline(*args, **kwargs)
        execute = pipe.execute

        async def commit(*args, **kwargs):
            result = await execute(*args, **kwargs)
            if await redis.zcard(queue):
                registered.set()
            return result

        pipe.execute = commit
        return pipe

    async def store():
        return redis

    monkeypatch.setattr(session_store, "_get_redis", store)
    monkeypatch.setattr(identity_roles, "_graph_lock", _GRAPH_LOCK)
    monkeypatch.setattr(redis, "pipeline", pipeline)
    native.conn.endpoint_for = lambda _: "https://native.test/v3"
    request = None
    try:
        async with _GRAPH_LOCK(native.conn) as holder:
            request = asyncio.create_task(
                login(client) if method == "password" else provider_login(client, monkeypatch)
            )
            await asyncio.wait_for(registered.wait(), 3)
            assert not request.done()
            assert not any(
                getattr(p, "afterglow_personal_user_id", None) == "ordinary" for p in native.project_rows.values()
            )
            await holder.assert_owned()
        response = await asyncio.wait_for(request, 5)
        assert response.status_code == 200, response.text
        body = response.json()
        primary = account_spaces.personal_project("ordinary", ks=native)
        assert body["project_id"] == primary["id"]
        assert body["identity_domain_id"] == "account"
        assert jwt_service.verify_access(body["token"])["project_id"] == primary["id"]
        refresh = jwt_service.verify_refresh(body["refresh_token"])
        assert (await session_store.get_session(refresh["jti"]))["project_id"] == primary["id"]
        assert sum(kind == "password" for kind, _ in native.exchanges) == (1 if method == "password" else 0)
        assert not await redis.keys("afterglow:identity-role-graph:*")
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        await redis.close()
