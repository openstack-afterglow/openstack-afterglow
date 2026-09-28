"""CRUD 자동 로깅 미들웨어 및 path 레지스트리 단위 테스트."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse

import app.main as _main_module
from app.main import _resource_for_path, activity_audit_middleware
from app.services.activity import _audit_ctx

# ─── 헬퍼 ─────────────────────────────────────────────────────────────────────


def _make_request(method: str, path: str, token_info: dict | None = None) -> Request:
    """테스트용 최소 Starlette Request 를 생성한다."""
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
    }
    req = Request(scope)
    if token_info is not None:
        req.state.token_info = token_info

    return req


_DEFAULT_TOKEN_INFO = {
    "project_id": "proj-test",
    "user_id": "user-test",
    "username": "testuser",
}


# ─── _resource_for_path 단위 테스트 ──────────────────────────────────────────


def test_resource_for_path_instances_no_id():
    assert _resource_for_path("/api/v1/instances") == ("instance", None)


def test_resource_for_path_instances_with_id():
    assert _resource_for_path("/api/v1/instances/abc-123") == ("instance", "abc-123")


def test_resource_for_path_volume_backups_longer_prefix_wins():
    """/api/v1/volumes/backups は /api/volumes より長い prefix を優先する."""
    rtype, rid = _resource_for_path("/api/v1/volumes/backups/bid-1")
    assert rtype == "volume_backup"
    assert rid == "bid-1"


def test_resource_for_path_volumes_short():
    rtype, rid = _resource_for_path("/api/v1/volumes/vol-1")
    assert rtype == "volume"
    assert rid == "vol-1"


def test_resource_for_path_keypairs():
    rtype, _ = _resource_for_path("/api/v1/keypairs/key-1")
    assert rtype == "keypair"


def test_resource_for_path_admin_projects():
    rtype, rid = _resource_for_path("/api/v1/admin/projects/proj-abc")
    assert rtype == "project"
    assert rid == "proj-abc"


def test_admin_volume_failure_is_classified_as_volume():
    assert _resource_for_path("/api/v1/admin/volumes/vol-1/extend") == ("volume", "vol-1")


def test_resource_for_path_not_in_allowlist_auth():
    assert _resource_for_path("/api/v1/auth/login") is None


def test_resource_for_path_not_in_allowlist_dashboard():
    assert _resource_for_path("/api/v1/dashboard/notifications") is None


def test_resource_for_path_not_in_allowlist_metrics():
    assert _resource_for_path("/api/v1/metrics") is None


def test_resource_for_path_not_in_allowlist_profile():
    assert _resource_for_path("/api/v1/profile/activity") is None


def test_resource_for_path_not_in_allowlist_sd():
    assert _resource_for_path("/api/v1/sd/targets") is None


# ─── 미들웨어 동작 통합 테스트 ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_log_created_when_no_manual_log():
    """수동 rec() 없는 성공 mutation → _record_activity 자동 1회 호출."""
    req = _make_request("POST", "/api/v1/instances", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        # 핸들러가 record() 를 호출하지 않는다 — holder["logged"] 는 False 유지.
        return JSONResponse({"ok": True}, status_code=201)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        resp = await activity_audit_middleware(req, call_next)

    assert resp.status_code == 201
    mock_rec.assert_awaited_once()
    kw = mock_rec.call_args.kwargs
    assert kw["resource_type"] == "instance"
    assert kw["action"] == "instance.create"
    assert kw["project_id"] == "proj-test"
    assert kw["user_id"] == "user-test"
    assert kw["status"] == "success"


@pytest.mark.asyncio
async def test_auto_log_suppressed_when_manual_log_present():
    """명시적인 성공 기록이 있을 때 집계 중복 행을 만들지 않는다."""
    req = _make_request("PATCH", "/api/v1/instances/inst-1", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        holder = _audit_ctx.get()
        if holder is not None:
            holder["logged"] = True
            holder["recorded_status"] = "success"
        return JSONResponse({"ok": True}, status_code=200)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        resp = await activity_audit_middleware(req, call_next)

    assert resp.status_code == 200
    mock_rec.assert_not_awaited()  # 중복 방지: 자동 로그 미생성


@pytest.mark.asyncio
async def test_started_event_does_not_hide_terminal_failure():
    req = _make_request("POST", "/api/v1/instances", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        holder = _audit_ctx.get()
        holder["logged"] = True
        holder["recorded_status"] = "started"
        r.state.audit_error = "인스턴스 배치 시도 횟수 초과"
        return JSONResponse({"detail": "인스턴스 배치 시도 횟수 초과"}, status_code=503)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)
    assert mock_rec.call_args.kwargs["status"] == "failed"
    assert mock_rec.call_args.kwargs["error_message"] == "인스턴스 배치 시도 횟수 초과"


@pytest.mark.asyncio
async def test_unhandled_authenticated_mutation_is_recorded_without_exception_text():
    req = _make_request("POST", "/api/v1/volumes", _DEFAULT_TOKEN_INFO)

    async def call_next(_request):
        raise RuntimeError("token=do-not-store")

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        with pytest.raises(RuntimeError):
            await activity_audit_middleware(req, call_next)

    mock_rec.assert_awaited_once()
    assert mock_rec.call_args.kwargs["status"] == "failed"
    assert mock_rec.call_args.kwargs["http_status"] == 500
    assert mock_rec.call_args.kwargs["error_message"] is None


@pytest.mark.asyncio
async def test_failed_mutation_is_searchable_by_actor_and_failure():
    req = _make_request("POST", "/api/v1/volumes", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        r.state.audit_error = "최대 시도 횟수 초과"
        return JSONResponse({"detail": "최대 시도 횟수 초과"}, status_code=409)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        resp = await activity_audit_middleware(req, call_next)

    assert resp.status_code == 409
    assert resp.headers["X-Request-Id"] == mock_rec.call_args.kwargs["request_id"]
    assert mock_rec.call_args.kwargs["status"] == "failed"
    assert mock_rec.call_args.kwargs["http_status"] == 409
    assert mock_rec.call_args.kwargs["error_message"] == "최대 시도 횟수 초과"
    assert mock_rec.call_args.kwargs["project_id"] == "proj-test"


@pytest.mark.asyncio
async def test_stream_handshake_is_not_mistaken_for_successful_creation():
    req = _make_request("POST", "/api/v1/instances/async", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        return JSONResponse({}, headers={"content-type": "text/event-stream"})

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)
    mock_rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_log_skipped_when_unauthenticated():
    """token_info 없는 요청(미인증)은 자동 로그를 생성하지 않는다."""
    req = _make_request("POST", "/api/v1/instances")  # token_info 미세팅

    async def call_next(r):
        return JSONResponse({"ok": True}, status_code=201)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)

    mock_rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_log_skipped_for_get_request():
    """GET 요청은 mutation 이 아니므로 자동 로그 대상이 아니다."""
    req = _make_request("GET", "/api/v1/instances", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        return JSONResponse([], status_code=200)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)

    mock_rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_log_skipped_for_unregistered_path():
    """allowlist 에 없는 경로는 자동 로그를 생성하지 않는다."""
    req = _make_request("POST", "/api/v1/auth/login", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        return JSONResponse({"token": "x"}, status_code=200)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)

    mock_rec.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_log_delete_action():
    """삭제 이력을 리소스 유형과 함께 검색할 수 있다."""
    req = _make_request("DELETE", "/api/v1/keypairs/key-xyz", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        return JSONResponse(None, status_code=204)

    with patch.object(_main_module, "_record_activity", new=AsyncMock()) as mock_rec:
        await activity_audit_middleware(req, call_next)

    mock_rec.assert_awaited_once()
    assert mock_rec.call_args.kwargs["action"] == "keypair.delete"
    assert mock_rec.call_args.kwargs["resource_id"] == "key-xyz"


@pytest.mark.asyncio
async def test_auto_log_does_not_block_response_on_record_error():
    """_record_activity 자체가 예외를 던져도 응답을 차단하지 않는다 (best-effort)."""
    req = _make_request("POST", "/api/v1/networks", _DEFAULT_TOKEN_INFO)

    async def call_next(r):
        return JSONResponse({"id": "net-1"}, status_code=201)

    async def _fail_record(**_kw):
        raise RuntimeError("DB down")

    with patch.object(_main_module, "_record_activity", new=AsyncMock(side_effect=_fail_record)):
        resp = await activity_audit_middleware(req, call_next)

    # 응답이 정상 반환돼야 한다
    assert resp.status_code == 201
