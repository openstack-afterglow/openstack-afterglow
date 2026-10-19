"""세션 기기정보 · 개별 삭제 · 관리자 사용자 목록 개선 테스트."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ============================================================================
# parse_device
# ============================================================================


class TestParseDevice:
    """UA 파싱 단위 테스트."""

    def setup_method(self):
        from app.services.token_binding import parse_device

        self.parse = parse_device

    def test_mac_chrome_desktop(self):
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0"
        dt, os_name = self.parse(ua)
        assert dt == "desktop"
        assert os_name == "macOS"

    def test_windows_desktop(self):
        ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0"
        dt, os_name = self.parse(ua)
        assert dt == "desktop"
        assert os_name == "Windows"

    def test_iphone_safari_mobile(self):
        ua = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit Mobile/15E148"
        dt, os_name = self.parse(ua)
        assert dt == "mobile"
        assert os_name == "iOS"

    def test_android_mobile(self):
        ua = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36"
        dt, os_name = self.parse(ua)
        assert dt == "mobile"
        assert os_name == "Android"

    def test_ipad_tablet(self):
        ua = "Mozilla/5.0 (iPad; CPU OS 16_0 like Mac OS X) AppleWebKit/605.1.15"
        dt, os_name = self.parse(ua)
        assert dt == "tablet"
        assert os_name == "iOS"

    def test_linux_desktop(self):
        ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0"
        dt, os_name = self.parse(ua)
        assert dt == "desktop"
        assert os_name == "Linux"

    def test_empty_ua_returns_unknown(self):
        dt, os_name = self.parse("")
        assert dt == "unknown"
        assert os_name == "unknown"

    def test_device_type_stored_in_session(self):
        """parse_device가 반환하는 값이 세션에 저장될 coarse 요약임을 확인."""
        ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0"
        dt, os_name = self.parse(ua)
        # raw UA 문자열이 아닌 coarse 요약만 반환해야 함
        assert ua not in dt
        assert ua not in os_name


# ============================================================================
# delete_session_owned (서비스 계층 단위)
# ============================================================================


@pytest.mark.anyio
async def test_delete_session_owned_success(_fake_redis_global):
    """소유자는 자신의 세션을 삭제할 수 있다 (True 반환, 세션 제거, Keystone revoke 호출)."""
    from app.services import session_store

    jti = "test-owned-jti"
    user_id = "user-A"

    await session_store.store_session(
        jti=jti,
        keystone_token="ks-token-A",
        project_id="proj-1",
        user_id=user_id,
        exp=9_999_999_999,
        auth_method="password",
    )

    with patch("app.services.keystone.revoke_token") as mock_revoke:
        result = await session_store.delete_session_owned(user_id, jti)

    assert result is True
    assert await session_store.get_session(jti) is None
    mock_revoke.assert_called_once_with("ks-token-A")


@pytest.mark.anyio
async def test_delete_session_owned_wrong_user(_fake_redis_global):
    """다른 사용자의 jti로 삭제 시도 → False 반환, 세션 유지됨."""
    from app.services import session_store

    jti = "test-other-jti"
    owner = "user-B"
    attacker = "user-A"

    await session_store.store_session(
        jti=jti,
        keystone_token="ks-token-B",
        project_id="proj-1",
        user_id=owner,
        exp=9_999_999_999,
    )

    with patch("app.services.keystone.revoke_token") as mock_revoke:
        result = await session_store.delete_session_owned(attacker, jti)

    assert result is False
    assert await session_store.get_session(jti) is not None
    mock_revoke.assert_not_called()


@pytest.mark.anyio
async def test_delete_session_owned_nonexistent_jti(_fake_redis_global):
    """존재하지 않는 jti → False 반환."""
    from app.services import session_store

    result = await session_store.delete_session_owned("some-user", "ghost-jti")
    assert result is False


# ============================================================================
# DELETE /api/auth/sessions/{jti} 엔드포인트
# ============================================================================


@pytest.mark.anyio
async def test_delete_session_endpoint_own(client, _fake_redis_global):
    """본인 세션 개별 삭제 → 200, 세션 제거됨."""
    from app.services import session_store

    jti = "endpoint-own-jti"
    await session_store.store_session(
        jti=jti,
        keystone_token="ks-tok-own",
        project_id="test-project-123",
        user_id="test-user-123",  # client 픽스처의 user_id
        exp=9_999_999_999,
    )

    with patch("app.services.keystone.revoke_token"):
        resp = await client.delete(f"/api/v1/auth/sessions/{jti}")

    assert resp.status_code == 200
    assert await session_store.get_session(jti) is None


@pytest.mark.anyio
async def test_delete_session_endpoint_other_user(client, _fake_redis_global):
    """다른 사용자 세션 jti 지정 → 404, 세션 유지됨."""
    from app.services import session_store

    jti = "endpoint-other-jti"
    await session_store.store_session(
        jti=jti,
        keystone_token="ks-tok-other",
        project_id="test-project-123",
        user_id="different-user",  # 호출자(test-user-123)와 다름
        exp=9_999_999_999,
    )

    resp = await client.delete(f"/api/v1/auth/sessions/{jti}")
    assert resp.status_code == 404
    # 세션이 그대로 남아 있어야 함
    assert await session_store.get_session(jti) is not None


# ============================================================================
# store_session — device 필드 저장 확인
# ============================================================================


@pytest.mark.anyio
async def test_store_session_device_fields_saved(_fake_redis_global):
    """store_session이 device_type/os 필드를 세션 JSON에 저장한다."""
    from app.services import session_store

    jti = "device-jti"
    await session_store.store_session(
        jti=jti,
        keystone_token="ks",
        project_id="p1",
        user_id="u1",
        exp=9_999_999_999,
        device_type="desktop",
        os="macOS",
    )

    sess = await session_store.get_session(jti)
    assert sess is not None
    assert sess["device_type"] == "desktop"
    assert sess["os"] == "macOS"


@pytest.mark.anyio
async def test_legacy_session_no_device_fields(_fake_redis_global):
    """device_type/os 없는 레거시 세션도 list_user_sessions가 크래시 없이 반환한다."""
    from app.services.session_store import _key, _user_index_key, list_user_sessions

    jti = "legacy-jti"
    user_id = "legacy-user"

    # device 필드 없이 직접 세션 데이터를 fake Redis에 삽입
    data = {
        "keystone_token": "ks-tok",
        "project_id": "p1",
        "user_id": user_id,
        "exp": 9_999_999_999,
        "auth_method": "password",
        "origin_ip": "1.2.3.4",
        "origin_fp": "abc",
        "last_ip": "1.2.3.4",
        "last_fp": "abc",
        "last_seen": 1_700_000_000,
        "blacklisted": False,
        "blacklist_reason": "",
        # device_type, os 필드 의도적으로 누락
    }
    fake_r = _fake_redis_global
    await fake_r.setex(_key(jti), 3600, json.dumps(data))
    await fake_r.sadd(_user_index_key(user_id), jti)

    sessions = await list_user_sessions(user_id)
    assert len(sessions) == 1
    assert sessions[0]["jti"] == jti
    # 크래시 없이 반환되어야 함 (device 필드 없어도 OK)


# ============================================================================
# list_users — per-user GET 폴백 미호출, activity bounds 포함
# ============================================================================


@pytest.mark.anyio
async def test_list_users_no_per_user_get_and_activity_bounds(admin_client, mock_conn):
    """list_users: per-user get_user() 폴백 호출 없음, first_seen/last_seen 포함."""
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    u = MagicMock()
    u.id = "uid-1"
    u.name = "Alice"
    u.email = "alice@example.com"
    u.is_enabled = True
    u.domain_id = "default"
    u.default_project_id = None
    mock_conn.identity.users.return_value = [u]

    with patch(
        "app.services.activity.get_user_activity_bounds",
        new_callable=AsyncMock,
        return_value={"uid-1": {"first_seen": "2025-01-01T00:00:00", "last_seen": "2025-06-01T00:00:00"}},
    ):
        resp = await admin_client.get("/api/v1/admin/users?domain_id=default&limit=20")

    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    item = data["items"][0]
    assert item["first_seen"] == "2025-01-01T00:00:00"
    assert item["last_seen"] == "2025-06-01T00:00:00"
    assert item["created_at"] == "2025-01-01T00:00:00"  # 하위호환 매핑

    # per-user get_user() 미호출 확인
    mock_conn.identity.get_user.assert_not_called()


@pytest.mark.anyio
async def test_list_users_activity_bounds_missing_user(admin_client, mock_conn):
    """activity bounds에 없는 사용자는 first_seen/last_seen이 None이고 created_at도 None."""
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    u = MagicMock()
    u.id = "uid-no-activity"
    u.name = "Bob"
    u.email = "bob@example.com"
    u.is_enabled = True
    u.domain_id = "default"
    u.default_project_id = None
    mock_conn.identity.users.return_value = [u]

    with patch(
        "app.services.activity.get_user_activity_bounds",
        new_callable=AsyncMock,
        return_value={},  # 활동 기록 없음
    ):
        resp = await admin_client.get("/api/v1/admin/users?domain_id=default&limit=20")

    assert resp.status_code == 200
    item = resp.json()["items"][0]
    assert item["first_seen"] is None
    assert item["last_seen"] is None
    assert item["created_at"] is None


# ============================================================================
# GET /users/stats
# ============================================================================


@pytest.mark.anyio
async def test_get_users_stats_forbidden_for_non_admin(non_admin_client):
    """require_admin 게이트 — 일반 사용자는 403."""
    resp = await non_admin_client.get("/api/v1/admin/users/stats?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_get_users_stats_counts(admin_client, mock_conn):
    """통계: 전체/활성/비활성 수 정확성."""
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    users_mock = []
    for i, enabled in enumerate([True, True, False]):
        u = MagicMock()
        u.id = f"uid-{i}"
        u.name = f"User{i}"
        u.is_enabled = enabled
        u.domain_id = "default"
        users_mock.append(u)
    mock_conn.identity.users.return_value = users_mock

    resp = await admin_client.get("/api/v1/admin/users/stats?domain_id=default")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["enabled"] == 2
    assert data["disabled"] == 1


# ============================================================================
# GET /users/activity
# ============================================================================


@pytest.mark.anyio
async def test_get_users_activity_forbidden_for_non_admin(non_admin_client):
    """require_admin 게이트 — 일반 사용자는 403."""
    resp = await non_admin_client.get("/api/v1/admin/users/activity?domain_id=default")
    assert resp.status_code == 403


@pytest.mark.anyio
async def test_get_users_activity_returns_events(admin_client, mock_conn):
    """변경 로그 카드: resource_type='user' 이벤트를 반환한다."""
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
    mock_conn.identity.users.return_value = [SimpleNamespace(id="uid-1", domain_id="default")]
    sample = [
        {
            "id": 1,
            "created_at": "2025-06-01T00:00:00",
            "username": "admin",
            "action": "create_user",
            "resource_type": "user",
            "resource_id": "uid-1",
            "resource_name": "Alice",
            "status": "success",
            "project_id": "proj-1",
            "user_id": "admin-id",
            "error_message": None,
            "extra": None,
        }
    ]
    with patch(
        "app.services.activity.list_user_management_events",
        new_callable=AsyncMock,
        return_value=sample,
    ) as mock_list:
        resp = await admin_client.get("/api/v1/admin/users/activity?domain_id=default&limit=10")

    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["action"] == "create_user"
    mock_list.assert_awaited_once_with(limit=10, before_id=None, user_ids=["uid-1"])
