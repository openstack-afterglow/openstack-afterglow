"""B3: session ownership 이중 검증 / 동시 세션 갱신 보안 필드 보존 테스트"""

import json
from unittest.mock import patch

import pytest


class TestDeleteSessionOwned:
    """Run real Redis Lua ownership checks, including a corrupted user index."""

    @pytest.mark.asyncio
    async def test_mismatched_user_id_returns_false(self, _fake_redis_global):
        from app.services.session_store import delete_session_owned

        await _fake_redis_global.sadd("afterglow:user-sessions:my-user", "some-jti")
        await _fake_redis_global.set("afterglow:refresh:some-jti", json.dumps({"user_id": "other-user"}))
        assert await delete_session_owned("my-user", "some-jti", revoke_keystone=False) is False
        assert await _fake_redis_global.exists("afterglow:refresh:some-jti")

    @pytest.mark.asyncio
    async def test_matching_user_id_returns_true(self, _fake_redis_global):
        from app.services.session_store import delete_session_owned

        await _fake_redis_global.sadd("afterglow:user-sessions:my-user", "some-jti")
        await _fake_redis_global.set("afterglow:refresh:some-jti", json.dumps({"user_id": "my-user"}))
        assert await delete_session_owned("my-user", "some-jti", revoke_keystone=False) is True
        assert not await _fake_redis_global.exists("afterglow:refresh:some-jti")

    @pytest.mark.asyncio
    async def test_not_in_index_returns_false(self):
        from app.services.session_store import delete_session_owned

        assert await delete_session_owned("my-user", "some-jti", revoke_keystone=False) is False

    @pytest.mark.asyncio
    async def test_stale_raw_missing_still_deletes(self, _fake_redis_global):
        from app.services.session_store import delete_session_owned

        await _fake_redis_global.sadd("afterglow:user-sessions:my-user", "some-jti")
        assert await delete_session_owned("my-user", "some-jti", revoke_keystone=False) is True
        assert not await _fake_redis_global.sismember("afterglow:user-sessions:my-user", "some-jti")


class TestSessionConcurrency:
    """동시 세션 토큰/활동/블랙리스트 갱신 시 보안 필드 유실 방지 테스트"""

    @pytest.mark.asyncio
    async def test_concurrent_session_updates_preserve_security_fields(self):
        """controlled Redis schedule로 동시 update_session_token, touch_session_seen, blacklist_session 실행 시
        새 Keystone 토큰, 블랙리스트 상태, last_seen 필드가 모두 보존되어야 한다."""
        import asyncio
        import time

        from app.services.session_store import (
            _get_redis,
            blacklist_session,
            get_session,
            store_session,
            touch_session_seen,
            update_session_token,
        )

        jti = "jti-concurrent-test"
        exp = int(time.time()) + 3600
        await store_session(jti, "ks-token-original", "proj-1", "user-1", exp)

        r = await _get_redis()
        original_get = r.get

        read_barrier = asyncio.Event()
        read_count = 0

        async def controlled_get(name, *args, **kwargs):
            res = await original_get(name, *args, **kwargs)
            name_str = name.decode() if isinstance(name, bytes) else str(name)
            if jti in name_str:
                nonlocal read_count
                read_count += 1
                if read_count == 3:
                    read_barrier.set()
                else:
                    await read_barrier.wait()
            return res

        with patch.object(r, "get", side_effect=controlled_get):
            await asyncio.gather(
                update_session_token(jti, "ks-token-NEW-ROTATED"),
                touch_session_seen(jti, "192.168.1.100", "fp-12345"),
                blacklist_session(jti, "security violation"),
            )

        sess = await get_session(jti)
        assert sess is not None
        # 새로 회전된 Keystone 토큰이 stale read writeback에 의해 덮어씌워지지 않고 보존되어야 함
        assert sess.get("keystone_token") == "ks-token-NEW-ROTATED"
        # 블랙리스트 상태가 보존되어야 함
        assert sess.get("blacklisted") is True
        # last_ip activity 정보가 보존되어야 함
        assert sess.get("last_ip") == "192.168.1.100"
