"""Signed OIDC callback waits without re-exchanging one-use provider code."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import fakeredis.aioredis
import pytest

from app.services import domain_auth, domain_iam, identity_roles, keystone, session_store
from tests.test_domain_auth import db as db
from tests.test_domain_auth import env as env
from tests.test_domain_auth import keystone_admin as keystone_admin
from tests.test_domain_auth import oidc_fields, start
from tests.test_domain_auth import public_dns as public_dns
from tests.test_domain_auth import settings as settings
from tests.test_domain_auth import wire as wire

_IAM_WRITE = domain_iam._iam_write


@pytest.mark.asyncio
async def test_verified_provider_callback_waits_once_and_rechecks_policy(env, monkeypatch):
    provider = await domain_auth.create_provider("dom-a", actor_user_id="mgr", fields=oidc_fields())
    state, binding = await start(env.wire.idp, provider["id"])
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    conn = SimpleNamespace(endpoint_for=lambda _: "https://provider-identity.test/v3", close=lambda: None)
    monkeypatch.setattr(keystone, "get_admin_project_connection", lambda: conn)
    monkeypatch.setattr(identity_roles, "load_catalog", lambda _: env.keystone.catalog)
    monkeypatch.setattr(session_store, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(domain_iam, "_iam_write", _IAM_WRITE)
    request = None
    try:
        async with identity_roles._graph_lock(conn) as holder:
            request = asyncio.create_task(domain_auth.complete_authorization("good-code", state, binding))
            async with asyncio.timeout(3):
                while not await holder.waiters_pending():
                    await asyncio.sleep(0.01)
            assert not request.done() and env.wire.federation.calls == []
        result = await asyncio.wait_for(request, 5)
        assert result.user_id == "fed-user" and result.unscoped_token == "unscoped-fed"
        assert len(env.wire.federation.calls) == 1
        assert sum(r.method == "POST" for r in env.wire.idp.requests) == 1
        with pytest.raises(domain_auth.DomainAuthUnauthenticated):
            await domain_auth.complete_authorization("good-code", state, binding)
    finally:
        if request is not None and not request.done():
            request.cancel()
            await asyncio.gather(request, return_exceptions=True)
        await redis.close()
