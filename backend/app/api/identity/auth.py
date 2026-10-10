import asyncio
import hmac
import logging
import os
from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.api.deps import (
    CacheMode,
    _check_session_timeout,
    cache_mode,
    get_token_info,
    has_project_write_permission,
    invalidate_token_cache,
)
from app.config import get_settings
from app.models.auth import GitLabCallbackRequest, LoginRequest, ProjectInfo, TokenResponse, UserInfo
from app.rate_limit import limiter
from app.services import activity as activity_svc
from app.services import cache, jwt_service, keystone, login_guard, session_store
from app.services.cache import cached_call, keys, ttl_fast, ttl_normal, ttl_static
from app.services.identity_roles import visible_role_names
from app.services.recent_projects import get_recent_project_ids, record_project_access

_logger = logging.getLogger(__name__)
_PROJECTS_TTL = 120  # 프로젝트 목록 캐시 2분

_GITLAB_OIDC_STATE_COOKIE = "afterglow_gitlab_oidc_state"
_GITLAB_OIDC_STATE_COOKIE_PATH = "/api/v1/auth/gitlab/callback"
_GITLAB_OIDC_STATE_TTL_SECONDS = 600


def _gitlab_oidc_cookie_secure(settings) -> bool:
    return (
        os.environ.get("AFTERGLOW_ENV", "development").strip().lower() == "production"
        or urlsplit(getattr(settings, "public_api_base", "")).scheme == "https"
    )


class GroupInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    domain_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ProjectScopeRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=255)


async def _build_token_response(
    *,
    keystone_token: str,
    project_id: str,
    project_name: str,
    user_id: str,
    username: str,
    roles: list[str],
    is_system_admin: bool,
    default_project_id: str = "",
    auth_method: str = "password",
    origin_ip: str = "",
    origin_fp: str = "",
    device_type: str = "",
    os: str = "",
) -> TokenResponse:
    """Keystone 토큰으로 JWT access+refresh 쌍을 발급하고 TokenResponse를 반환."""
    public_roles = await visible_role_names(roles, is_system_admin)
    can_write = has_project_write_permission({"roles": roles, "is_system_admin": is_system_admin})
    refresh_str, r_jti, r_exp = jwt_service.sign_refresh(user_id)
    access_str, _, a_exp = jwt_service.sign_access(
        user_id=user_id,
        username=username,
        project_id=project_id,
        project_name=project_name,
        refresh_jti=r_jti,
    )
    await session_store.store_session(
        jti=r_jti,
        keystone_token=keystone_token,
        project_id=project_id,
        user_id=user_id,
        exp=r_exp,
        auth_method=auth_method,
        origin_ip=origin_ip,
        origin_fp=origin_fp,
        device_type=device_type,
        os=os,
    )
    exp_dt = datetime.fromtimestamp(a_exp, tz=UTC)
    return TokenResponse(
        token=access_str,
        refresh_token=refresh_str,
        project_id=project_id,
        project_name=project_name,
        user_id=user_id,
        username=username,
        expires_at=exp_dt.isoformat(),
        roles=public_roles,
        default_project_id=default_project_id,
        is_system_admin=is_system_admin,
        can_write=can_write,
        auth_method=auth_method,
    )


router = APIRouter()


async def _prewarm_dashboard(token: str, project_id: str):
    """로그인 후 백그라운드에서 대시보드 캐시를 미리 워밍."""
    try:
        conn = keystone.get_openstack_connection(token, project_id)
        from app.api.common.dashboard import _list_flavors_as_dicts, _list_servers_as_dicts
        from app.services import cinder, nova

        await asyncio.gather(
            cached_call(f"afterglow:nova:{project_id}:servers", ttl_fast(), lambda: _list_servers_as_dicts(conn)),
            cached_call(f"afterglow:nova:{project_id}:limits", ttl_normal(), lambda: nova.get_project_limits(conn)),
            cached_call(f"afterglow:cinder:{project_id}:limits", ttl_normal(), lambda: cinder.get_volume_limits(conn)),
            cached_call(f"afterglow:nova:{project_id}:flavors", ttl_static(), lambda: _list_flavors_as_dicts(conn)),
        )
    except Exception:
        pass  # best-effort: 실패해도 로그인에는 영향 없음

    # Default network provisioning remains best-effort for login latency, but
    # never substitutes an arbitrary external network or deployment selector.
    settings = get_settings()
    if settings.default_network_enabled:
        try:
            from app.services.default_network import ensure_default_network
            from app.services.resource_policy_store import resolve_policies

            conn2 = keystone.get_openstack_connection(token, project_id)
            policies = await resolve_policies(conn=conn2, keys=("nova.default_external_network",))
            await ensure_default_network(
                conn2,
                project_id,
                external_network_id=policies["nova.default_external_network"],
                cidr=settings.default_network_cidr,
            )
        except Exception:
            _logger.warning("default network prewarm failed", exc_info=True)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, req: LoginRequest, background_tasks: BackgroundTasks):
    domain = req.domain_name or "Default"

    # 잠금 확인 (HTTPException 429 발생 가능)
    await login_guard.check_locked(req.username, domain)

    try:
        data = keystone.authenticate(
            username=req.username,
            password=req.password,
            project_name=req.project_name,
            domain_name=req.domain_name,
        )
    except Exception:
        asyncio.create_task(login_guard.record_failure(req.username, domain))
        raise HTTPException(status_code=401, detail="인증 실패")

    # 사용자의 default_project_id 조회
    default_project_id = ""
    try:
        conn = keystone.get_openstack_connection(data["token"], data["project_id"])
        u = conn.identity.get_user(data["user_id"])
        default_project_id = getattr(u, "default_project_id", None) or ""
    except Exception:
        pass

    # 로그인 출처 + 기기 정보 기록
    from app.services.token_binding import get_origin, parse_device

    origin_ip, origin_fp = get_origin(request)
    device_type, os_name = parse_device(request.headers.get("User-Agent", ""))

    # 성공 시 실패 카운트 초기화 (fire-and-forget)
    asyncio.create_task(login_guard.record_success(req.username, domain))

    # 대시보드 캐시 프리워밍 + 최근 프로젝트 기록 (백그라운드)
    background_tasks.add_task(_prewarm_dashboard, data["token"], data["project_id"])
    background_tasks.add_task(record_project_access, data["user_id"], data["project_id"])

    response = await _build_token_response(
        keystone_token=data["token"],
        project_id=data["project_id"],
        project_name=data["project_name"],
        user_id=data["user_id"],
        username=data["username"],
        roles=data.get("roles", []),
        is_system_admin=data.get("is_system_admin", False),
        default_project_id=default_project_id,
        auth_method="password",
        origin_ip=origin_ip,
        origin_fp=origin_fp,
        device_type=device_type,
        os=os_name,
    )
    await activity_svc.record(
        project_id=data["project_id"],
        user_id=data["user_id"],
        username=data["username"],
        resource_type="auth",
        action="login",
        status="success",
        source="afterglow",
        service="keystone",
    )
    return response


@router.get("/me", response_model=UserInfo)
async def me(token_info: dict = Depends(get_token_info)):
    return UserInfo(
        user_id=token_info["user_id"],
        username=token_info["username"],
        project_id=token_info["project_id"],
        project_name=token_info["project_name"],
        roles=await visible_role_names(token_info["roles"], token_info.get("is_system_admin", False)),
        is_system_admin=token_info.get("is_system_admin", False),
        can_write=has_project_write_permission(token_info),
        auth_method=token_info.get("auth_method", "password"),
    )


@router.post("/logout")
async def logout(token_info: dict = Depends(get_token_info)):
    """Delete the refresh session, then revoke its Keystone token when one exists."""
    token = token_info["token"]
    pid = token_info.get("project_id") or "noscope"
    refresh_jti = token_info.get("refresh_jti")
    keystone_token = token if not refresh_jti else None

    if refresh_jti:
        try:
            session = await session_store.get_session(refresh_jti)
            if session and session.get("user_id") == token_info["user_id"]:
                keystone_token = session.get("keystone_token") or None
            elif session:
                _logger.warning("logout session ownership mismatch (jti=%s)", refresh_jti)
            await session_store.delete_session(refresh_jti)
        except Exception:
            _logger.warning("refresh 세션 삭제 실패 (jti=%s)", refresh_jti, exc_info=True)

    if keystone_token:
        try:
            await asyncio.to_thread(keystone.revoke_token, keystone_token)
        except Exception:
            _logger.warning("Keystone revoke 실패 — 캐시는 그대로 invalidate", exc_info=True)
    await invalidate_token_cache(token, pid)
    return {"message": "로그아웃 완료"}


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(request: Request, req: RefreshRequest):
    """refresh JWT로 새 access JWT + refresh JWT 발급 (토큰 회전).

    기존 refresh JTI는 즉시 삭제되므로 같은 refresh 토큰으로 두 번 호출하면 두 번째는 401.
    """
    try:
        r_payload = jwt_service.verify_refresh(req.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 refresh 토큰")

    r_jti = r_payload["jti"]
    try:
        sess = await session_store.get_session(r_jti)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Redis session store lookup failure during refresh: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="세션 저장소 연결 실패")

    if sess is None:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")

    # 블랙리스트 세션은 refresh 갱신도 거부
    if sess.get("blacklisted"):
        raise HTTPException(status_code=401, detail="세션이 차단되었습니다.")

    # ── 세션 타임아웃 검증 ─────────────────────────────────────────────────────
    import hashlib as _hl

    _rjti_hash = _hl.sha256(r_jti.encode()).hexdigest()
    await _check_session_timeout(_rjti_hash, sess.get("project_id", ""))

    # 최초 로그인 origin과 기기 정보를 회전 너머로 그대로 운반 (재파싱 금지)
    origin_ip = sess.get("origin_ip", "")
    origin_fp = sess.get("origin_fp", "")
    device_type = sess.get("device_type", "")
    os_name = sess.get("os", "")

    # Keystone 토큰 유효성 확인 (만료 시 재로그인 필요)
    from keystoneauth1.exceptions.http import Unauthorized

    try:
        kc_info = await asyncio.to_thread(
            keystone.validate_token, sess["keystone_token"], project_id=sess["project_id"]
        )
    except Unauthorized:
        await session_store.delete_session(r_jti)
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Keystone validation failure during refresh (session preserved): %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="인증 검증 서비스 일시적 오류. 잠시 후 다시 시도해 주세요.")

    # 토큰 회전: 새 토큰 발급 및 세션 저장 후 기존 refresh 삭제
    try:
        token_resp = await _build_token_response(
            keystone_token=kc_info["token"],
            project_id=kc_info["project_id"],
            project_name=kc_info["project_name"],
            user_id=kc_info["user_id"],
            username=kc_info["username"],
            roles=kc_info.get("roles", []),
            is_system_admin=kc_info.get("is_system_admin", False),
            auth_method=sess.get("auth_method", "password"),
            origin_ip=origin_ip,
            origin_fp=origin_fp,
            device_type=device_type,
            os=os_name,
        )
        await session_store.delete_session(r_jti)
        return token_resp
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Failed to rotate session during refresh (session preserved): %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="세션 갱신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")


@router.post("/token/project", response_model=TokenResponse)
async def scope_project(req: ProjectScopeRequest, token_info: dict = Depends(get_token_info)):
    """접근 가능한 프로젝트로 새 토큰 쌍 발급 (rescope)."""
    keystone_token = token_info["token"]
    try:
        kc_info = await asyncio.to_thread(keystone.validate_token, keystone_token, project_id=req.project_id)
    except Exception:
        raise HTTPException(status_code=403, detail="해당 프로젝트에 접근 권한이 없습니다")

    # 이전 refresh 세션 정리 (JWT 경로인 경우)
    old_rjti = token_info.get("refresh_jti")
    if old_rjti:
        try:
            await session_store.delete_session(old_rjti)
        except Exception:
            pass

    await record_project_access(kc_info["user_id"], kc_info["project_id"])
    return await _build_token_response(
        keystone_token=kc_info["token"],
        project_id=kc_info["project_id"],
        project_name=kc_info["project_name"],
        user_id=kc_info["user_id"],
        username=kc_info["username"],
        roles=kc_info.get("roles", []),
        is_system_admin=kc_info.get("is_system_admin", False),
        auth_method=token_info.get("auth_method", "password"),
        # 기존 세션의 origin·기기 정보를 그대로 운반 (프로젝트 전환 시 재파싱 금지)
        origin_ip=token_info.get("origin_ip", ""),
        origin_fp=token_info.get("origin_fp", ""),
        device_type=token_info.get("device_type", ""),
        os=token_info.get("os", ""),
    )


@router.post("/logout-all")
async def logout_all(token_info: dict = Depends(get_token_info)):
    """현재 사용자의 모든 세션을 폐기 (Keystone 직접 폐기 포함).

    federated 사용자 포함 — 패스워드 여부와 무관하게 세션은 항상 폐기 가능.
    현재 세션도 함께 폐기되므로 호출 후 재로그인이 필요하다.
    """
    user_id = token_info["user_id"]
    count = await session_store.revoke_user_sessions(user_id, revoke_keystone=True)
    # 현재 Keystone 토큰 검증 캐시도 즉시 무효화
    await invalidate_token_cache(token_info["token"], token_info.get("project_id"))
    return {"message": "모든 세션이 폐기되었습니다.", "revoked_count": count}


@router.delete("/sessions/{jti}")
async def delete_session_endpoint(jti: str, token_info: dict = Depends(get_token_info)):
    """개별 세션 삭제 (소유권 확인 필수).

    jti가 현재 사용자의 세션이 아니면 404 반환 (타인 세션 은닉).
    Keystone 토큰도 즉시 폐기한다 (best-effort).
    """
    from app.services import activity as activity_svc

    user_id = token_info["user_id"]
    deleted = await session_store.delete_session_owned(user_id, jti)
    if not deleted:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    await activity_svc.record(
        project_id=token_info.get("project_id", ""),
        user_id=user_id,
        username=token_info.get("username", ""),
        resource_type="auth",
        action="session_delete",
        status="success",
        extra={"deleted_jti": jti},
    )
    return {"message": "세션이 삭제되었습니다."}


@router.get("/sessions")
async def list_sessions(token_info: dict = Depends(get_token_info)):
    """현재 사용자의 활성 세션 목록 반환 (출처 IP·기기·마지막 사용 포함).

    keystone_token 등 민감 필드는 제거된 채 반환된다.
    """
    sessions = await session_store.list_user_sessions(token_info["user_id"])
    return {"sessions": sessions, "count": len(sessions)}


@router.get("/groups", response_model=list[GroupInfo])
async def list_my_groups(token_info: dict = Depends(get_token_info)):
    """현재 사용자가 속한 keystone 그룹 목록. policy 불허 시 빈 리스트 반환."""
    try:
        groups = await asyncio.to_thread(keystone.list_user_groups, token_info["token"], token_info["user_id"])
        return [GroupInfo(**g) for g in groups]
    except PermissionError:
        return []
    except Exception:
        _logger.exception("/api/v1/auth/groups 처리 실패 (user_id=%s)", token_info.get("user_id"))
        raise HTTPException(status_code=500, detail="그룹 목록 조회 실패")


@router.get("/projects", response_model=list[ProjectInfo])
async def list_projects(
    token_info: dict = Depends(get_token_info),
    cm: CacheMode = Depends(cache_mode),
):
    """사용자가 접근 가능한 프로젝트 목록 반환."""
    user_id = token_info["user_id"]
    key = keys.user_key(user_id, "projects")
    try:
        data = await cache.cached_call(
            key,
            _PROJECTS_TTL,
            lambda: keystone.list_projects(token_info["token"]),
            enabled=cm.enabled,
            refresh=cm.refresh,
        )
        return [ProjectInfo(**p) for p in data]
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 목록 조회 실패")


@router.get("/projects/recent", response_model=list[ProjectInfo])
async def list_projects_recent(token_info: dict = Depends(get_token_info)):
    """최근 접근 순으로 정렬된 프로젝트 목록 반환.

    Redis에 기록된 접근 시각 기준으로 정렬하고, last_accessed_at 필드를 포함한다.
    Redis 기록이 없는 프로젝트는 이름순으로 뒤에 덧붙인다.
    """
    try:
        projects = await asyncio.to_thread(keystone.list_projects, token_info["token"])
    except Exception:
        raise HTTPException(status_code=500, detail="프로젝트 목록 조회 실패")

    user_id = token_info["user_id"]
    recent_ids = await get_recent_project_ids(user_id)
    recent_map: dict[str, int] = {pid: ts for pid, ts in recent_ids}

    project_infos: list[ProjectInfo] = []
    for p in projects:
        ts = recent_map.get(p["id"])
        last_accessed_at = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat() if ts else None
        project_infos.append(ProjectInfo(**p, last_accessed_at=last_accessed_at))

    # 최근 접근 기록 있는 것 먼저(최신순), 없는 것은 이름순
    def _sort_key(pi: ProjectInfo) -> tuple[int, str]:
        ts = recent_map.get(pi.id, 0)
        return (-ts, pi.name)

    project_infos.sort(key=_sort_key)
    return project_infos


# OIDC/OAuth API router - mounted under /api/v1/auth in main.py.
gitlab_router = APIRouter()


@gitlab_router.get("/gitlab/enabled")
async def gitlab_enabled():
    """GitLab OIDC 활성화 여부 반환 (프론트엔드에서 버튼 표시 여부 결정)."""
    settings = get_settings()
    return {"enabled": settings.gitlab_oidc_enabled}


@gitlab_router.get("/gitlab/authorize")
async def gitlab_authorize(response: Response):
    """GitLab OAuth2 authorization URL and browser-bound state cookie."""
    settings = get_settings()
    if not settings.gitlab_oidc_enabled:
        raise HTTPException(status_code=404, detail="GitLab OIDC가 비활성화 상태입니다")
    from app.services.gitlab_oidc import create_authorization_request

    try:
        authorization = await create_authorization_request()
    except Exception:
        raise HTTPException(status_code=500, detail="GitLab 인증 URL 생성 실패")
    response.set_cookie(
        key=_GITLAB_OIDC_STATE_COOKIE,
        value=authorization.state,
        max_age=_GITLAB_OIDC_STATE_TTL_SECONDS,
        httponly=True,
        secure=_gitlab_oidc_cookie_secure(settings),
        samesite="lax",
        path=_GITLAB_OIDC_STATE_COOKIE_PATH,
    )
    return {"authorize_url": authorization.url}


@gitlab_router.post("/gitlab/callback", response_model=TokenResponse)
@limiter.limit("10/minute")
async def gitlab_callback(
    request: Request, req: GitLabCallbackRequest, background_tasks: BackgroundTasks, response: Response
):
    """GitLab OAuth2 콜백: browser-bound authorization code로 Keystone 토큰 발급."""
    settings = get_settings()
    if not settings.gitlab_oidc_enabled:
        raise HTTPException(status_code=404, detail="GitLab OIDC가 비활성화 상태입니다")
    browser_state = request.cookies.get(_GITLAB_OIDC_STATE_COOKIE, "")
    if not browser_state or not hmac.compare_digest(browser_state, req.state):
        raise HTTPException(status_code=401, detail="GitLab 인증 상태가 현재 브라우저와 일치하지 않습니다")
    from app.services.gitlab_oidc import exchange_code

    try:
        data = await exchange_code(req.code, req.state)
    except Exception:
        raise HTTPException(status_code=401, detail="GitLab 인증 실패")

    # exchange_code는 접근 가능한 default_project_id만 채워 응답한다.
    # frontend는 project_id/default_project_id 공통 규칙으로 다음 화면을 결정한다.
    background_tasks.add_task(_prewarm_dashboard, data["token"], data["project_id"])
    background_tasks.add_task(record_project_access, data["user_id"], data["project_id"])

    token_response = await _build_token_response(
        keystone_token=data["token"],
        project_id=data["project_id"],
        project_name=data["project_name"],
        user_id=data["user_id"],
        username=data["username"],
        roles=data.get("roles", []),
        is_system_admin=data.get("is_system_admin", False),
        auth_method="federated",
        default_project_id=data.get("default_project_id", "") or "",
    )
    response.delete_cookie(key=_GITLAB_OIDC_STATE_COOKIE, path=_GITLAB_OIDC_STATE_COOKIE_PATH)
    await activity_svc.record(
        project_id=data["project_id"],
        user_id=data["user_id"],
        username=data["username"],
        resource_type="auth",
        action="login",
        status="success",
        source="afterglow",
        service="keystone",
        extra={"method": "federated"},
    )
    return token_response
