"""인스턴스 헬스체크 서비스 + API 테스트."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from app.models.instance_health import InstanceHealthReport, ShareHealth
from app.services import instance_health as svc

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _now_iso(offset_minutes: int = 0) -> str:
    dt = datetime.now(UTC) + timedelta(minutes=offset_minutes)
    return dt.isoformat()


def _make_report(**kwargs) -> InstanceHealthReport:
    defaults = dict(
        overlay_mounted=True,
        upper_used_bytes=1_000_000,
        upper_total_bytes=10_000_000,
        upper_usage_pct=10.0,
        shares=[],
        kernel="6.1.0",
        uptime_seconds=300.0,
        reported_at=_now_iso(),
    )
    defaults.update(kwargs)
    return InstanceHealthReport(**defaults)


def _callback_reasons(caplog) -> list[str]:
    from app.utils.log import SensitiveDataFilter
    from app.utils.structured_logging import JSONFormatter

    records = [record for record in caplog.records if record.name == "app.api.compute.instance_health"]
    sanitizer = SensitiveDataFilter()
    formatter = JSONFormatter()
    reasons = []
    for record in records:
        sanitizer.filter(record)
        payload = json.loads(formatter.format(record))
        reasons.append(payload["diagnostic_reason"])
        assert "exception" not in payload
    return reasons


# ---------------------------------------------------------------------------
# FakeRedis 픽스처
# ---------------------------------------------------------------------------


class FakeRedis:
    """단순 인메모리 Redis mock."""

    def __init__(self):
        self._store: dict[str, tuple[str, float | None]] = {}  # key → (value, expiry_ts|None)

    def _expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, exp = self._store[key]
        if exp is None:
            return False
        import time

        return time.time() > exp

    async def get(self, key: str):
        if self._expired(key):
            self._store.pop(key, None)
            return None
        return self._store[key][0]

    async def setex(self, key: str, ttl: int, value: str):
        import time

        self._store[key] = (value, time.time() + ttl)

    async def set(self, key: str, value: str):
        self._store[key] = (value, None)

    async def expire(self, key: str, ttl: int):
        import time

        if key in self._store:
            v, _ = self._store[key]
            self._store[key] = (v, time.time() + ttl)

    async def delete(self, *keys: str):
        for k in keys:
            self._store.pop(k, None)

    async def scan_iter(self, pattern: str = "*"):
        import fnmatch

        for k in list(self._store.keys()):
            if not self._expired(k) and fnmatch.fnmatch(k, pattern):
                yield k


@pytest.fixture
def fake_redis(monkeypatch):
    r = FakeRedis()

    async def _get_client():
        return r

    monkeypatch.setattr("app.services.instance_health._redis", _get_client)
    monkeypatch.setattr("app.services.cache._get_client", _get_client)
    return r


# ---------------------------------------------------------------------------
# 토큰 발급/검증 라운드트립
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_and_verify_token(fake_redis):
    token = await svc.issue_report_token("inst-1", "proj-1")
    assert token

    data = await svc.verify_report_token(token)
    assert data is not None
    assert data["instance_id"] == "inst-1"
    assert data["project_id"] == "proj-1"


@pytest.mark.asyncio
async def test_invalid_token_returns_none(fake_redis):
    result = await svc.verify_report_token("bad-token-xyz")
    assert result is None


@pytest.mark.asyncio
async def test_revoke_token_by_instance(fake_redis):
    token = await svc.issue_report_token("inst-2", "proj-1")
    await svc.revoke_report_token_by_instance("inst-2")

    result = await svc.verify_report_token(token)
    assert result is None


@pytest.mark.asyncio
async def test_reissue_revokes_old_token(fake_redis):
    old_token = await svc.issue_report_token("inst-3", "proj-1")
    _new_token = await svc.issue_report_token("inst-3", "proj-1")

    # 기존 토큰은 폐기됨
    assert await svc.verify_report_token(old_token) is None


@pytest.mark.asyncio
async def test_token_ttl_is_seven_days(fake_redis):
    """절대 만료 7일 — 이전 30일 sliding 에서 단축됨."""
    assert svc._TOKEN_TTL == 86400 * 7


@pytest.mark.asyncio
async def test_verify_does_not_extend_ttl(fake_redis):
    """sliding TTL 갱신 제거 검증 — verify 후에도 TTL 변하지 않음."""
    import time

    token = await svc.issue_report_token("inst-sliding", "proj-1")
    key = f"{svc._TOKEN_PREFIX}{token}"
    expiry_before = fake_redis._store[key][1]

    # 1초 sleep 후 verify — sliding 이라면 expiry 가 갱신되어야 했지만 제거됨
    time.sleep(0.05)
    await svc.verify_report_token(token)
    expiry_after = fake_redis._store[key][1]

    # expire 가 호출됐다면 expiry_after > expiry_before. 호출되지 않으면 동일.
    assert expiry_after == expiry_before


# ---------------------------------------------------------------------------
# 헬스 결과 캐시
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_and_get_health_result(fake_redis):
    report = _make_report()
    await svc.store_health_result("inst-4", report)

    result = await svc.get_health_result("inst-4")
    assert result is not None
    assert result.overlay_mounted is True
    assert result.status == "healthy"


@pytest.mark.asyncio
async def test_get_health_result_miss(fake_redis):
    result = await svc.get_health_result("nonexistent-inst")
    assert result is None


# ---------------------------------------------------------------------------
# status 판정
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_error_when_overlay_not_mounted(fake_redis):
    report = _make_report(overlay_mounted=False)
    await svc.store_health_result("inst-5", report)

    result = await svc.get_health_result("inst-5")
    assert result is not None
    assert result.status == "error"
    assert any("OverlayFS" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_status_error_at_95pct(fake_redis):
    report = _make_report(upper_usage_pct=95.0)
    await svc.store_health_result("inst-6", report)

    result = await svc.get_health_result("inst-6")
    assert result is not None
    assert result.status == "error"


@pytest.mark.asyncio
async def test_status_warning_at_90pct(fake_redis):
    report = _make_report(upper_usage_pct=90.0)
    await svc.store_health_result("inst-7", report)

    result = await svc.get_health_result("inst-7")
    assert result is not None
    assert result.status == "warning"


@pytest.mark.asyncio
async def test_status_error_on_unreachable_share(fake_redis):
    share = ShareHealth(name="torch", proto="NFS", mounted=False, status="unreachable")
    report = _make_report(shares=[share])
    await svc.store_health_result("inst-8", report)

    result = await svc.get_health_result("inst-8")
    assert result is not None
    assert result.status == "error"
    assert any("torch" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_status_stale_when_old(fake_redis):
    old_time = _now_iso(-20)  # 20분 전
    report = _make_report(reported_at=old_time)
    await svc.store_health_result("inst-9", report)

    result = await svc.get_health_result("inst-9")
    assert result is not None
    assert result.status == "stale"


# ---------------------------------------------------------------------------
# 리스트 조회
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_health_results(fake_redis):
    r1 = _make_report()
    r2 = _make_report(overlay_mounted=False)
    await svc.store_health_result("inst-a", r1)
    await svc.store_health_result("inst-b", r2)

    results = await svc.list_health_results(["inst-a", "inst-b", "inst-missing"])
    assert len(results) == 2
    ids = {r.instance_id for r in results}
    assert "inst-a" in ids
    assert "inst-b" in ids


# ---------------------------------------------------------------------------
# API 엔드포인트 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("authorization", [None, "Bearer ", "Basic invalid"])
async def test_report_endpoint_unauthorized(client, authorization, caplog):
    resp = await client.post(
        "/api/v1/instances/some-id/health/report",
        headers={"Authorization": authorization} if authorization is not None else {},
        json=_make_report().model_dump(),
    )
    assert resp.status_code == 401
    assert "X-Afterglow-Error-Code" not in resp.headers
    assert "health_credential_missing" in _callback_reasons(caplog)


@pytest.mark.asyncio
async def test_report_endpoint_invalid_token(fake_redis, client, caplog):
    resp = await client.post(
        "/api/v1/instances/some-id/health/report",
        headers={"Authorization": "Bearer invalid-token"},
        json=_make_report().model_dump(),
    )
    assert resp.status_code == 401
    assert "X-Afterglow-Error-Code" not in resp.headers
    assert "health_credential_expired_or_unknown" in _callback_reasons(caplog)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("operation", "route"),
    [("get", "health/report"), ("setex", "health/report"), ("get", "credentials/rotate-cephx")],
)
async def test_callback_store_outage_preserves_credential(fake_redis, client, monkeypatch, caplog, operation, route):
    token = await svc.issue_report_token("outage-instance", "outage-project")
    before = dict(fake_redis._store)
    original = getattr(fake_redis, operation)

    async def unavailable(*_args, **_kwargs):
        raise ConnectionError(f"secret diagnostic {token} outage-instance outage-project")

    monkeypatch.setattr(fake_redis, operation, unavailable)
    response = await client.post(
        f"/api/v1/instances/outage-instance/{route}",
        headers={"Authorization": f"Bearer {token}"},
        json=_make_report().model_dump() if route == "health/report" else None,
    )
    assert response.status_code == 503
    assert "X-Afterglow-Error-Code" not in response.headers
    assert "health_store_unavailable" not in response.text
    assert "health_store_unavailable" in _callback_reasons(caplog)
    assert fake_redis._store == before
    assert token not in caplog.text
    assert "secret diagnostic" not in caplog.text
    callback_logs = [record.getMessage() for record in caplog.records if record.name.startswith("app.")]
    assert all("outage-instance" not in message and "outage-project" not in message for message in callback_logs)
    monkeypatch.setattr(fake_redis, operation, original)
    assert await svc.verify_report_token(token) == {"instance_id": "outage-instance", "project_id": "outage-project"}


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["not-json", "[]", '{"instance_id": "inst-corrupt"}'])
async def test_callback_corrupt_store_record_is_not_invalid_credential(fake_redis, client, raw, caplog):
    token = await svc.issue_report_token("inst-corrupt", "proj-1")
    await fake_redis.setex(f"{svc._TOKEN_PREFIX}{token}", svc._TOKEN_TTL, raw)
    before = dict(fake_redis._store)
    response = await client.post(
        "/api/v1/instances/inst-corrupt/health/report",
        headers={"Authorization": f"Bearer {token}"},
        json=_make_report().model_dump(),
    )
    assert response.status_code == 503
    assert "X-Afterglow-Error-Code" not in response.headers
    assert "health_credential_record_invalid" not in response.text
    assert "health_credential_record_invalid" in _callback_reasons(caplog)
    assert fake_redis._store == before


@pytest.mark.asyncio
async def test_callback_expiry_does_not_renew_or_replace_credential(fake_redis, client, caplog):
    token = await svc.issue_report_token("inst-expired", "proj-1")
    token_key = f"{svc._TOKEN_PREFIX}{token}"
    raw, _ = fake_redis._store[token_key]
    fake_redis._store[token_key] = (raw, 0)
    response = await client.post(
        "/api/v1/instances/inst-expired/health/report",
        headers={"Authorization": f"Bearer {token}"},
        json=_make_report().model_dump(),
    )
    assert response.status_code == 401
    assert "X-Afterglow-Error-Code" not in response.headers
    assert "health_credential_expired_or_unknown" in _callback_reasons(caplog)
    assert token_key not in fake_redis._store
    assert await fake_redis.get(f"{svc._INSTANCE_PREFIX}inst-expired") == token


@pytest.mark.asyncio
async def test_report_endpoint_wrong_instance(fake_redis, client, caplog):
    token = await svc.issue_report_token("inst-x", "proj-1")
    resp = await client.post(
        "/api/v1/instances/wrong-id/health/report",
        headers={"Authorization": f"Bearer {token}"},
        json=_make_report().model_dump(),
    )
    assert resp.status_code == 403
    assert "X-Afterglow-Error-Code" not in resp.headers
    assert "health_credential_instance_mismatch" in _callback_reasons(caplog)


@pytest.mark.asyncio
async def test_report_endpoint_success(fake_redis, client):
    token = await svc.issue_report_token("inst-ok", "proj-1")
    resp = await client.post(
        "/api/v1/instances/inst-ok/health/report",
        headers={"Authorization": f"Bearer {token}"},
        json=_make_report().model_dump(),
    )
    assert resp.status_code == 204

    # Redis에 저장됐는지 확인
    result = await svc.get_health_result("inst-ok")
    assert result is not None
    assert result.status == "healthy"


@pytest.mark.asyncio
async def test_get_health_endpoint_not_found(client):
    with patch("app.services.nova.get_server", side_effect=Exception("not found")):
        resp = await client.get("/api/v1/instances/nonexistent/health")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# rotate-cephx 엔드포인트 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_cephx_no_bearer_token(client):
    """Authorization 헤더 없으면 401."""
    resp = await client.post("/api/v1/instances/inst-1/credentials/rotate-cephx")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rotate_cephx_invalid_token(fake_redis, client):
    """유효하지 않은 토큰이면 401."""
    resp = await client.post(
        "/api/v1/instances/inst-1/credentials/rotate-cephx",
        headers={"Authorization": "Bearer invalid-token-xyz"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rotate_cephx_disabled(fake_redis, client):
    """union_cephx_rotate_hours=0이면 503."""
    token = await svc.issue_report_token("inst-disabled", "proj-1")
    with patch("app.api.compute.instance_health.get_settings") as mock_settings:
        mock_cfg = mock_settings.return_value
        mock_cfg.union_cephx_rotate_hours = 0
        resp = await client.post(
            "/api/v1/instances/inst-disabled/credentials/rotate-cephx",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 503
