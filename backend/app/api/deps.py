from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import Depends, Header, HTTPException, Query, Request

from app.config import get_settings
from app.services import keystone
from app.services.cache import invalidate

if TYPE_CHECKING:
    import openstack

_logger = logging.getLogger(__name__)


def validate_keystone_id(value: object) -> str:
    """Validate native package identities without rewriting opaque Keystone IDs."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", value):
        raise HTTPException(status_code=403, detail="Keystone identity is invalid")
    return value


async def _run_best_effort(awaitable, operation: str) -> None:
    """Observe background-task failures without changing the foreground response."""
    try:
        await awaitable
    except Exception:
        _logger.warning("%s failed", operation, exc_info=True)


def _session_key(token_hash: str, project_id: str) -> str:
    return f"afterglow:session_start:{token_hash}:{project_id or 'noscope'}"


def _validate_cache_key(token_hash: str, project_id: str) -> str:
    return f"afterglow:session:{token_hash}:{project_id or 'noscope'}"


async def _cached_validate(token: str, project_id: str, *, operation=None) -> dict:
    """Read current native proof/roles; never reuse a revoked scoped credential."""
    if operation is not None:
        return await operation.run(keystone.validate_session, token, project_id=project_id, operation=operation)
    return await asyncio.to_thread(keystone.validate_session, token, project_id=project_id)


async def invalidate_token_cache(token: str, project_id: str | None) -> None:
    """logout / revoke 직후 호출 — 검증 캐시 + 세션 시작/절대 키를 모두 삭제.

    Redis 장애 시 silent fail (logout 흐름을 막지 않음).
    """
    pid = project_id or "noscope"
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    keys = [
        _validate_cache_key(token_hash, pid),
        _session_key(token_hash, pid),
    ]
    for key in keys:
        try:
            await invalidate(key)
        except Exception:
            _logger.warning("토큰 캐시 invalidate 실패 (%s)", key, exc_info=True)


async def _check_session_timeout(
    token_hash: str,
    project_id: str,
    *,
    refresh_jti: str,
    session: dict,
    issued_at: float,
) -> float:
    """Enforce the original login's lifetime across refresh and project changes.

    Legacy records are migrated from their existing marker or signed JWT iat.
    Deleting an expired refresh record prevents retries from recreating a start.
    """
    from app.services.session_store import delete_session, ensure_session_started_at

    try:
        start = session.get("started_at")
        if start is None:
            if not math.isfinite(float(issued_at)) or float(issued_at) <= 0:
                raise ValueError("Session issue time is invalid")
            start = await ensure_session_started_at(refresh_jti, project_id, issued_at)
            if start is None:
                raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
        start = float(start)
        if not math.isfinite(start) or start <= 0:
            raise ValueError("Session start time is invalid")
        if time.time() >= start + get_settings().session_timeout_seconds:
            await delete_session(refresh_jti)
            raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
        return start
    except HTTPException:
        raise
    except Exception:
        # fail-closed: Redis 장애 시 세션 검증 불가 → 503 반환
        _logger.error("Redis 장애로 세션 타임아웃 검증 불가 — 요청 거부 (fail-closed)", exc_info=True)
        raise HTTPException(status_code=503, detail="세션 유효성을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.")


async def _resolve_jwt_token_info(
    request, bearer_token: str, x_project_id: str | None, *, preserve_original: bool = False
) -> dict:
    from app.services.native_operation import NativeOperation

    async with NativeOperation() as operation:
        principal = await _resolve_jwt_session(
            request, bearer_token, x_project_id, preserve_original=preserve_original, operation=operation
        )
        subject = operation.subjects.get(principal.get("token"))
        if subject is not None:
            request.state._afterglow_native_access = subject[0]
        return principal


async def _resolve_jwt_session(request, bearer_token, x_project_id, *, preserve_original, operation) -> dict:
    """Bearer access JWT 검증 → Redis 세션 조회 → token_info dict 반환.

    Ordinary routes retain Keystone rescope. Native package routes preserve the
    original subject; only a live system administrator may select another target.
    """
    from app.services import jwt_service
    from app.services.session_store import get_session

    try:
        payload = jwt_service.verify_access(bearer_token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 액세스 토큰")

    refresh_jti = payload.get("rjti")
    if not refresh_jti:
        raise HTTPException(status_code=401, detail="액세스 토큰 형식 오류")

    try:
        sess = await get_session(refresh_jti)
    except HTTPException:
        raise
    except Exception as exc:
        _logger.error("Redis session lookup failed in _resolve_jwt_token_info: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="세션 저장소 연결 실패")

    if sess is None:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")

    domain_id = sess.get("domain_id")
    if not isinstance(domain_id, str) or not domain_id:
        raise HTTPException(status_code=401, detail="세션의 도메인을 확인할 수 없습니다. 다시 로그인해 주세요.")
    identity_domain_id = sess.get("identity_domain_id") or domain_id
    if not isinstance(identity_domain_id, str) or not identity_domain_id:
        raise HTTPException(status_code=401, detail="Session identity domain is unavailable")
    if sess.get("user_id") != payload.get("sub") or sess.get("project_id", "") != payload.get("project_id", ""):
        raise HTTPException(status_code=401, detail="세션 범위가 액세스 토큰과 일치하지 않습니다.")
    if sess.get("blacklisted"):
        raise HTTPException(status_code=401, detail="세션이 차단되었습니다.")
    from keystoneauth1.exceptions.http import Unauthorized

    # Migrate legacy scoped records before any endpoint can mutate its own roles.
    # Invalid native login proof wins over project/domain authorization errors.
    try:
        root = await _cached_validate(sess["keystone_token"], "", operation=operation)
    except Unauthorized as exc:
        raise HTTPException(401, "Native login proof is invalid; log in again") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Native login verification is unavailable") from exc
    if root.get("user_id") != payload["sub"] or root.get("identity_domain_id") != identity_domain_id:
        raise HTTPException(403, "Native login identity does not match the session")
    from app.services.session_store import update_session_token

    try:
        persisted = await update_session_token(
            refresh_jti, root["session_token"], expected_token=sess["keystone_token"]
        )
    except Exception as exc:
        raise HTTPException(503, "Native login proof persistence is unavailable") from exc
    if not persisted:
        current = await get_session(refresh_jti)
        if current is None or current.get("blacklisted"):
            raise HTTPException(401, "Session is no longer active")
        immutable = ("user_id", "project_id", "domain_id", "identity_domain_id", "family_id")
        if any(current.get(key) != sess.get(key) for key in immutable):
            raise HTTPException(401, "Session identity changed")
        try:
            root = await _cached_validate(current["keystone_token"], "", operation=operation)
        except Unauthorized as exc:
            raise HTTPException(401, "Native login proof is invalid") from exc
        if root["user_id"] != payload["sub"] or root["identity_domain_id"] != identity_domain_id:
            raise HTTPException(403, "Native login identity does not match the session")
        sess = current
    else:
        sess["keystone_token"] = root["session_token"]
    from app.services.domain_scope import assert_domain_resource, assert_project_domain, domain_context

    # Authority observations belong only to this authentication operation.
    context = await operation.run(domain_context, payload["sub"], domain_id, operation=operation)
    assert_domain_resource(identity_domain_id, context.get("identity_domain_id"))
    # ── 세션 타임아웃 검증 (JWT 경로) ─────────────────────────────────────────
    # 최초 로그인 시작시간은 회전/프로젝트 전환 뒤에도 동일하다.
    _rjti_hash = hashlib.sha256(refresh_jti.encode()).hexdigest()
    _sess_project_id = sess.get("project_id", x_project_id or "")
    started_at = await _check_session_timeout(
        _rjti_hash,
        _sess_project_id,
        refresh_jti=refresh_jti,
        session=sess,
        issued_at=payload.get("iat", 0),
    )

    # ── 블랙리스트 검사 ─────────────────────────────────────────────────────
    if sess.get("blacklisted"):
        raise HTTPException(status_code=401, detail="세션이 차단되었습니다.")

    # ── IP/기기 지문 바인딩 검사 (fail-closed: 오류 시 503 차단) ───────────
    _username = payload.get("username", "")
    try:
        from app.services.token_binding import check_binding, get_origin

        settings = get_settings()
        cur_ip, cur_fp = get_origin(request)
        action, reason = check_binding(sess, cur_ip, cur_fp, settings.token_ip_binding_mode)
        if action == "block":
            from app.services import activity
            from app.services.session_store import blacklist_session

            asyncio.create_task(blacklist_session(refresh_jti, reason))
            asyncio.create_task(
                activity.record(
                    project_id=sess.get("project_id", ""),
                    user_id=sess.get("user_id", ""),
                    username=_username,
                    resource_type="auth",
                    action="token_origin_mismatch",
                    status="failed",
                    extra={"ip": cur_ip, "origin_ip": sess.get("origin_ip", ""), "reason": reason},
                )
            )
            raise HTTPException(status_code=401, detail="토큰 출처가 일치하지 않습니다.")
        elif action == "log":
            from app.services import activity

            asyncio.create_task(
                activity.record(
                    project_id=sess.get("project_id", ""),
                    user_id=sess.get("user_id", ""),
                    username=_username,
                    resource_type="auth",
                    action="token_origin_mismatch",
                    status="success",
                    extra={
                        "ip": cur_ip,
                        "origin_ip": sess.get("origin_ip", ""),
                        "reason": reason,
                        "blocked": False,
                    },
                )
            )
        else:
            # 이미 읽은 세션이 최신이면 Redis EVAL 자체를 생략한다. TTL 경과 뒤의
            # 갱신만 background로 보내 요청 latency와 Redis write load를 분리한다.
            from app.services.session_store import session_seen_needs_touch, touch_session_seen

            if session_seen_needs_touch(sess, cur_ip, cur_fp):
                asyncio.create_task(
                    _run_best_effort(
                        touch_session_seen(refresh_jti, cur_ip, cur_fp),
                        "session last_seen update",
                    )
                )
    except HTTPException:
        raise
    except Exception:
        # fail-closed: 바인딩 검사 실패(Redis 장애·설정 오류) 시 503 반환
        _logger.error("토큰 바인딩 검사 실패 — 요청 거부 (fail-closed)", exc_info=True)
        raise HTTPException(
            status_code=503, detail="토큰 바인딩 검사를 완료할 수 없습니다. 잠시 후 다시 시도해 주세요."
        )

    from app.api.identity.auth import _enforce_session_policy
    from app.services.domain_auth import DomainAuthError

    try:
        await _enforce_session_policy(sess, {**root, **context})
    except DomainAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    if preserve_original:
        selected = x_project_id if x_project_id is not None else sess.get("target_project_id")
        requested_project = payload.get("project_id", "") if selected is None else selected
        system_admin = await operation.run(keystone._is_system_admin, payload["sub"], operation=operation)
        path = getattr(getattr(request, "url", None), "path", "")
        projectless_catalog = (
            requested_project == ""
            and getattr(request, "method", "") == "GET"
            and re.fullmatch(r"/api/v1/admin/palimpsest/catalog(?:/(?:[1-9][0-9]*|sha256:[0-9a-f]{64}))?", path)
            is not None
        )
        # Only these global read handlers may carry an empty logical target.
        # Fresh require_admin below still verifies the original human/native
        # authority; package and all consumer routes retain mandatory IDs.
        project_id = "" if projectless_catalog and system_admin else validate_keystone_id(requested_project)
        if not system_admin and project_id != payload.get("project_id", ""):
            raise HTTPException(403, "Package session/project scope does not match the access JWT")
        if project_id:
            await operation.run(assert_project_domain, domain_id, project_id, operation=operation)
        try:
            native = await _cached_validate(root["session_token"], payload.get("project_id", ""), operation=operation)
        except Unauthorized as exc:
            raise HTTPException(401, "Native login proof is invalid") from exc
        principal = {
            **native,
            **context,
            "session_token": root["session_token"],
            "project_id": project_id,
            "connection_project_id": payload.get("project_id", ""),
            "refresh_jti": refresh_jti,
            "started_at": started_at,
            "auth_method": sess.get("auth_method", "password"),
            "provider_id": sess.get("provider_id", ""),
            "provider_revision": sess.get("provider_revision"),
            "provider_domain_id": sess.get("provider_domain_id", ""),
            "login_email": sess.get("login_email", ""),
        }
        return await require_admin(principal) if system_admin else principal

    home_project_id = payload.get("project_id", "")
    logical_workspace = isinstance(sess.get("target_project_id"), str)
    target_project_id = x_project_id or (sess["target_project_id"] if logical_workspace else home_project_id)
    if x_project_id is not None:
        validate_keystone_id(x_project_id)
    path = getattr(getattr(request, "url", None), "path", "")
    service_path = (
        path.startswith(("/api/v1/chat/", "/api/v1/k3s/", "/api/v1/waygate/", "/api/v1/palimpsest/"))
        or path == "/api/v1/projects/current/permissions"
    )
    context_path = path in {
        "/api/v1/auth/me",
        "/api/v1/auth/domains",
        "/api/v1/auth/workspaces",
        "/api/v1/auth/token/workspace",
        "/api/v1/auth/token/domain",
        "/api/v1/auth/token/project",
        "/api/v1/auth/sessions",
        "/api/v1/auth/projects",
        "/api/v1/auth/projects/recent",
        "/api/v1/auth/logout",
        "/api/v1/auth/logout-all",
    }
    context_path = context_path or (
        request.method == "DELETE" and re.fullmatch(r"/api/v1/auth/sessions/[^/]+", path) is not None
    )
    is_system_admin = await operation.run(keystone._is_system_admin, payload["sub"], operation=operation)
    if logical_workspace and not is_system_admin:
        raise HTTPException(status_code=403, detail="Current system administrator authority is required")
    admin_context = is_system_admin and logical_workspace and context_path
    service_admin = is_system_admin and service_path
    if service_admin:
        await operation.run(assert_project_domain, domain_id, target_project_id, operation=operation)
    admin_target = bool(
        (target_project_id != home_project_id or logical_workspace)
        and is_system_admin
        and (path.startswith("/api/v1/admin/") or service_path or admin_context)
    )
    if target_project_id and not admin_target and not service_admin:
        await operation.run(assert_project_domain, domain_id, target_project_id, operation=operation)
        if not context_path:
            from app.services.domain_projects import assert_project_membership

            await operation.run(assert_project_membership, payload["sub"], target_project_id, operation=operation)
    from keystoneauth1.exceptions.http import Unauthorized

    validation_project_id = home_project_id if admin_target else target_project_id
    try:
        info = await _cached_validate(root["session_token"], validation_project_id, operation=operation)
    except keystone.ProjectAccessDenied:
        explicit_project_change = (
            x_project_id is not None
            and x_project_id != home_project_id
            and (not logical_workspace or x_project_id != target_project_id)
        )
        if not context_path or explicit_project_change or (admin_target and not logical_workspace):
            raise
        # Auth context remains usable to choose another project; no grants or
        # stale project roles are created when only the selected project is lost.
        info = {**root, "project_id": "", "project_name": "", "roles": []}
        validation_project_id = ""
        if admin_target:
            await operation.run(assert_project_domain, domain_id, target_project_id, operation=operation)
        else:
            target_project_id = ""
    except HTTPException:
        raise
    except Unauthorized as exc:
        raise HTTPException(401, "Native login proof is invalid; log in again") from exc
    except Exception:
        _logger.error("Keystone validation unavailable", exc_info=True)
        raise HTTPException(status_code=503, detail="인증 검증 서비스 일시적 오류. 잠시 후 다시 시도해 주세요.")
    if info.get("user_id") != payload["sub"] or info.get("project_id", "") != validation_project_id:
        raise HTTPException(status_code=403, detail="Keystone token subject or project does not match")
    assert_domain_resource(identity_domain_id, info.get("identity_domain_id"))
    if info.get("project_id"):
        if not admin_target:
            assert_domain_resource(domain_id, info.get("domain_id"))
    else:
        # Native unscoped validation derives home, not the selected workspace.
        # Prove that home before applying independently authorized context.
        assert_domain_resource(identity_domain_id, info.get("domain_id"))
        info = {**info, **context}
    from app.api.identity.auth import _enforce_session_policy

    try:
        await _enforce_session_policy(sess, {**info, **context})
    except DomainAuthError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    logical_project_id = target_project_id
    connection_project_id = info.get("project_id", "")
    project_name = "" if admin_target else info.get("project_name", "")
    if admin_target and logical_workspace and target_project_id == sess["target_project_id"]:
        project_name = sess.get("target_project_name", "")

    principal = {
        "token": info["token"],
        "session_token": root["session_token"],
        "user_id": info.get("user_id", payload.get("sub", "")),
        "username": info.get("username", payload.get("username", "")),
        "project_id": logical_project_id,
        "connection_project_id": connection_project_id,
        "project_name": project_name,
        "roles": info.get("roles", []),
        "is_system_admin": is_system_admin,
        **context,
        "refresh_jti": refresh_jti,
        "started_at": started_at,
        "auth_method": sess.get("auth_method", "password"),
        "provider_id": sess.get("provider_id", ""),
        "provider_revision": sess.get("provider_revision"),
        "provider_domain_id": sess.get("provider_domain_id", ""),
        "login_email": sess.get("login_email", ""),
        # 출처 필드 — switch_project 원본 운반용
        "origin_ip": sess.get("origin_ip", ""),
        "origin_fp": sess.get("origin_fp", ""),
        # 기기 정보 — switch_project 운반용
        "device_type": sess.get("device_type", ""),
        "os": sess.get("os", ""),
    }
    if service_admin or admin_context:
        return await require_admin(principal)
    return principal


async def get_token_info(
    request: Request,
    authorization: str | None = Header(None),
    x_project_id: str | None = Header(None),
) -> dict:
    """모든 인증 필요 엔드포인트에서 사용하는 Depends 함수.

    Authorization: Bearer <access_jwt> — JWT 경로만 지원.

    request.state.token_info 를 세팅해 activity_audit_middleware 가 자동 로깅 시
    신원(project_id/user_id/username)을 추출할 수 있게 한다.
    """
    if authorization and authorization.startswith("Bearer "):
        bearer = authorization[7:]
        try:
            info = await _resolve_jwt_token_info(request, bearer, x_project_id)
            request.state.token_info = info
            return info
        except HTTPException:
            raise
        except Exception as exc:
            _logger.error("Unexpected error in get_token_info: %s", exc, exc_info=True)
            raise HTTPException(status_code=503, detail="인증 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")
    raise HTTPException(status_code=401, detail="Authorization Bearer 토큰이 필요합니다")


async def require_admin(token_info: dict = Depends(get_token_info)) -> dict:
    """Never let a cached grant authorize a persistent administrative mutation."""
    from keystoneauth1.exceptions.http import Unauthorized

    from app.services.domain_scope import assert_token_context, domain_context

    denied = {"code": "system_admin_required", "message": "Current system:all administrator authority is required"}
    if token_info.get("is_system_admin") is not True:
        raise HTTPException(status_code=403, detail=denied)
    user_id, domain_id = token_info.get("user_id"), token_info.get("domain_id")
    if not user_id or not domain_id:
        raise HTTPException(status_code=403, detail=denied)
    try:
        from app.services.native_operation import NativeOperation

        # A new guard gets fresh native authority; only its own duplicate reads
        # and service authentication share the short-lived operation.
        async with NativeOperation() as operation:
            context = await operation.run(domain_context, user_id, domain_id, operation=operation)
            project_id = token_info.get("connection_project_id", token_info.get("project_id", ""))
            native = await operation.run(
                keystone.validate_token, token_info["token"], project_id=project_id, operation=operation
            )
            await operation.run(
                assert_token_context,
                native,
                user_id=user_id,
                domain_id=native.get("domain_id"),
                project_id=project_id,
                identity_domain_id=token_info["identity_domain_id"],
                operation=operation,
            )
            if not await operation.run(keystone._is_system_admin, user_id, operation=operation):
                raise HTTPException(status_code=403, detail=denied)
    except Unauthorized as exc:
        raise HTTPException(status_code=401, detail="Native administrator session is invalid; log in again") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Administrator authority is unavailable") from exc
    token_info.update(context)
    token_info["roles"] = native.get("roles", [])
    token_info["is_system_admin"] = True
    token_info["_live_system_admin"] = True
    return token_info


async def require_domain_manager(token_info: dict = Depends(get_token_info)) -> dict:
    from app.services.domain_scope import domain_context

    if not token_info.get("domain_id"):
        raise HTTPException(status_code=403, detail="An authoritative domain context is required")
    context = await asyncio.to_thread(domain_context, token_info["user_id"], token_info["domain_id"])
    if not context["is_domain_manager"]:
        raise HTTPException(status_code=403, detail="Default project manager authority is required")
    return {**token_info, **context}


async def require_project_manager(
    project_id: str,
    token_info: dict = Depends(get_token_info),
) -> dict:
    """Require current Keystone project management; legacy DB rows never authorize."""
    from app.services.domain_scope import assert_project_domain

    await asyncio.to_thread(assert_project_domain, token_info.get("domain_id", ""), project_id)
    if token_info.get("is_system_admin") is True:
        return token_info
    if token_info.get("project_id") != project_id:
        raise HTTPException(status_code=403, detail="프로젝트 관리에는 현재 프로젝트 범위가 필요합니다")
    from app.services.project_service import get_project_access

    access = await get_project_access(project_id, token_info["user_id"])
    if not access["is_manager"]:
        raise HTTPException(status_code=403, detail="프로젝트 관리자 권한이 필요합니다")
    return token_info


def has_project_write_permission(token_info: dict) -> bool:
    """Compute project authority; domain-only sessions never grant project writes."""
    if not token_info.get("project_id"):
        return False
    if token_info.get("is_system_admin") is True:
        return True
    roles = {r.lower() for r in token_info.get("roles", []) if isinstance(r, str)}
    return bool(roles & {"admin", "member"})


def require_project_write(token_info: dict = Depends(get_token_info)) -> dict:
    """프로젝트 내 리소스 생성/수정/삭제(mutation) 권한 검증.

    - system_admin: 허용
    - role에 'admin' 또는 'member'가 포함된 경우: 허용
    - role에 'reader'만 있거나 쓰기 권한이 없는 경우: 403 Forbidden
    """
    if has_project_write_permission(token_info):
        return token_info

    raise HTTPException(
        status_code=403,
        detail="읽기 전용(reader) 권한으로는 리소스를 생성, 수정 또는 삭제할 수 없습니다.",
    )


async def get_caller_project_permissions(
    project_id: str | None = None,
    token_info: dict = Depends(get_token_info),
) -> dict:
    """호출자의 특정 프로젝트(또는 현재 컨텍스트)에 대한 실효 권한과 역할을 반환."""
    effective_project_id = project_id or token_info.get("project_id") or ""
    from app.services.domain_scope import assert_project_domain
    from app.services.project_service import get_project_access
    from app.services.service_authorization import service_permission_snapshot

    if token_info.get("is_system_admin") is True and token_info.get("_live_system_admin") is not True:
        await require_admin(token_info)

    await asyncio.to_thread(assert_project_domain, token_info.get("domain_id", ""), effective_project_id)

    access = await get_project_access(effective_project_id, token_info["user_id"])
    roles = access["roles"]
    is_sys_admin = token_info.get("is_system_admin") is True
    principal = {**token_info, "project_id": effective_project_id, "roles": roles}
    role_set = set(roles)

    can_write = has_project_write_permission({**principal, "is_system_admin": False})
    is_reader = not can_write and ("reader" in role_set or len(role_set) == 0)

    is_mgr = access["is_manager"]

    from app.services.identity_roles import visible_role_names

    native_permissions, permission_errors = await service_permission_snapshot(principal)

    return {
        "project_id": effective_project_id,
        "user_id": token_info.get("user_id", ""),
        "roles": await visible_role_names(roles, is_sys_admin),
        "is_system_admin": is_sys_admin,
        "is_manager": is_mgr,
        "is_owner": access["is_owner"],
        "service_permissions": native_permissions,
        "service_permission_errors": permission_errors,
        "is_reader": is_reader,
        "can_read": True,
        "can_write": can_write,
    }


async def get_os_conn(
    request: Request,
    token_info: dict = Depends(get_token_info),
) -> AsyncGenerator[openstack.connection.Connection, None]:
    """openstacksdk Connection 객체를 반환하는 Depends 함수.
    conn._afterglow_token, conn._afterglow_project_id 에 원본 크리덴셜을 저장해
    Manila 등 openstacksdk 외부 클라이언트에서 그대로 사용할 수 있도록 한다.
    FastAPI가 get_token_info를 요청 단위로 캐시하므로 require_admin 등과 함께
    사용해도 Redis/Keystone 인증 검증을 중복 실행하지 않는다.
    요청 완료 후 Connection을 닫아 리소스 누수를 방지한다.
    """
    scoped_token = token_info["token"]
    project_id = token_info["project_id"]
    connection_project_id = token_info.get("connection_project_id", project_id)
    is_system_admin = token_info.get("is_system_admin", False)
    conn = None
    try:
        if not connection_project_id:
            if not request.url.path.startswith("/api/v1/admin/"):
                raise HTTPException(status_code=403, detail="A project scope is required")
            if token_info.get("_live_system_admin") is not True:
                await require_admin(token_info)
            is_system_admin = True
            conn = await asyncio.to_thread(keystone.get_openstack_connection, scoped_token, "", system_scope=True)
            # Force the caller-token exchange here so denials are classified at
            # the boundary, not deferred until a later native operation.
            access = await asyncio.to_thread(conn.session.auth.get_access, conn.session)
            if (
                access.system_scoped is not True
                or access.user_id != token_info["user_id"]
                or access.user_domain_id != token_info["identity_domain_id"]
            ):
                raise HTTPException(status_code=503, detail="Native system scope does not match the caller")
            scoped_token = access.auth_token
        else:
            native_access = getattr(request.state, "_afterglow_native_access", None)
            if native_access is None:
                conn = keystone.get_openstack_connection(scoped_token, connection_project_id)
            else:
                if (
                    native_access.user_id != token_info["user_id"]
                    or native_access.user_domain_id != token_info["identity_domain_id"]
                ):
                    raise HTTPException(status_code=503, detail="Native connection identity does not match the caller")
                conn = keystone.get_openstack_connection(
                    scoped_token, connection_project_id, native_access=native_access
                )
        conn._afterglow_token = scoped_token
        conn._afterglow_project_id = project_id
        conn._afterglow_authenticated_project_id = connection_project_id
        conn._afterglow_is_system_admin = is_system_admin
        # Native Nova's admin policy can expose all private flavors even without
        # system:all. This flag only adds a target-project ACL check; never authority.
        conn._afterglow_compute_admin = (is_system_admin and not connection_project_id) or any(
            isinstance(role, str) and role.lower() == "admin" for role in token_info.get("roles", [])
        )
        conn._afterglow_domain_id = token_info["domain_id"]
        conn._afterglow_domain_name = token_info["domain_name"]
        conn._afterglow_identity_domain_id = token_info["identity_domain_id"]
        conn._afterglow_user_id = token_info.get("user_id", "")
    except HTTPException:
        if conn is not None:
            await asyncio.to_thread(conn.close)
        raise
    except Exception as exc:
        if conn is not None:
            await asyncio.to_thread(conn.close)
        from keystoneauth1.exceptions.http import Forbidden, Unauthorized

        if isinstance(exc, (Forbidden, Unauthorized)):
            if not connection_project_id:
                try:
                    current_admin = await asyncio.to_thread(keystone._is_system_admin, token_info["user_id"])
                except Exception as authority_error:
                    raise HTTPException(503, "Administrator authority is unavailable") from authority_error
                if not current_admin:
                    raise HTTPException(
                        403,
                        {
                            "code": "system_admin_required",
                            "message": "Current system:all administrator authority is required",
                        },
                    ) from exc
            if isinstance(exc, Unauthorized):
                raise HTTPException(status_code=401, detail="Native authentication session is invalid") from exc
        _logger.error("OpenStack connection creation failed in get_os_conn: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail="OpenStack 연결 생성 실패. 잠시 후 다시 시도해 주세요.")

    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)


async def get_admin_os_conn(
    token_info: dict = Depends(require_admin),
) -> AsyncGenerator[openstack.connection.Connection, None]:
    """Execute provider administration in the configured native admin project.

    Fresh caller system authority authorizes this bounded service execution;
    neither the caller's personal token nor a request-selected project supplies
    the provider credential. Logical workspace and actor metadata stay caller-owned.
    """
    conn = None
    try:
        try:
            conn = await asyncio.to_thread(keystone.get_admin_project_connection)
            access = await asyncio.to_thread(conn.session.auth.get_access, conn.session)
            project_id = access.project_id
            token = access.auth_token
            # Keystone may omit this legacy marker (including for its admin
            # project). AccessInfo supplies the native default True; an explicit
            # false, null or non-boolean marker must still be rejected.
            native_token = access._data.get("token", {})
            if (
                access.project_scoped is not True
                or access.system_scoped is not False
                or not isinstance(project_id, str)
                or not project_id.strip()
                or not isinstance(token, str)
                or not token.strip()
                or access.is_admin_project is not True
                or native_token.get("is_admin_project", True) is not True
                or not any(isinstance(role, str) and role.lower() == "admin" for role in access.role_names or [])
            ):
                raise HTTPException(status_code=503, detail="Native administrator project scope is invalid")
            conn._afterglow_token = token
            conn._afterglow_project_id = token_info["project_id"]
            conn._afterglow_authenticated_project_id = project_id
            conn._afterglow_is_system_admin = True
            conn._afterglow_compute_admin = True
            conn._afterglow_domain_id = token_info["domain_id"]
            conn._afterglow_domain_name = token_info["domain_name"]
            conn._afterglow_identity_domain_id = token_info["identity_domain_id"]
            conn._afterglow_user_id = token_info.get("user_id", "")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="Administrator provider connection is unavailable") from exc
        yield conn
    finally:
        if conn is not None:
            await asyncio.to_thread(conn.close)


async def get_os_conn_write(
    conn: openstack.connection.Connection = Depends(get_os_conn),
    _write_guard: dict = Depends(require_project_write),
) -> openstack.connection.Connection:
    """쓰기(mutation) 전용 openstack Connection 의존성.

    require_project_write를 실행하여 reader 역할의 변경 시도를 403으로 차단한 뒤 conn 반환.
    """
    return conn


async def cache_bypass(refresh: bool = Query(False)) -> bool:
    """`?refresh=true` 쿼리스트링으로 캐시 우회를 허용하는 의존성.

    cached_call(key, ttl, fn, refresh=bypass) 와 페어로 사용한다.

    .. deprecated::
        신규 엔드포인트는 cache_mode / CacheMode 를 사용한다.
    """
    return refresh


@dataclass
class CacheMode:
    """캐시 read/write 모드를 담는 값 객체.

    enabled=True, refresh=False  — opt-in read-through (`?cache=true`)
    enabled=True, refresh=True   — 강제 재조회+재저장 (`?refresh=true`)
    enabled=False, refresh=False — origin 직행, 캐시 미접촉 (기본)
    """

    enabled: bool
    refresh: bool


async def cache_mode(
    cache: bool = Query(False, description="캐시 read-through opt-in"),
    refresh: bool = Query(False, description="캐시 강제 갱신(재조회+재저장)"),
) -> CacheMode:
    """`?cache=true` / `?refresh=true` 쿼리를 읽어 CacheMode 를 반환하는 의존성.

    우선순위: refresh > cache > 기본(origin 직행).
    flip-flop 방지: `?refresh=true` 는 재조회+재저장(enabled=True, refresh=True) 으로
    처리해 다음 `?cache=true` 조회가 stale 로 되돌아가지 않도록 한다.
    """
    if refresh:
        return CacheMode(enabled=True, refresh=True)
    if cache:
        return CacheMode(enabled=True, refresh=False)
    return CacheMode(enabled=False, refresh=False)
