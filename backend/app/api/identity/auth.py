import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from keystoneauth1.exceptions.http import Unauthorized
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    _check_session_timeout,
    get_token_info,
    has_project_write_permission,
    invalidate_token_cache,
)
from app.config import get_settings
from app.models.auth import DomainInfo, LoginRequest, ProjectInfo, TokenResponse, UserInfo, WorkspaceInfo
from app.rate_limit import limiter
from app.services import (
    account_spaces,
    domain_projects,
    jwt_service,
    keystone,
    login_guard,
    project_display,
    project_service,
    session_store,
)
from app.services import activity as activity_svc
from app.services.cache import cached_call, ttl_fast, ttl_normal, ttl_static
from app.services.domain_auth import DomainAuthError, domain_auth_error_response
from app.services.domain_scope import (
    assert_domain_resource,
    assert_project_domain,
    assert_token_context,
    domain_context,
    resolve_domain,
)
from app.services.identity_roles import _field, visible_role_names
from app.services.native_operation import NativeOperation
from app.services.recent_projects import get_recent_project_ids, record_project_access
from app.utils.auth_diagnostics import authentication_operation, authentication_step

_logger = logging.getLogger(__name__)


class GroupInfo(BaseModel):
    id: str
    name: str
    description: str | None = None
    domain_id: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class ProjectScopeRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=255)


class DomainScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    domain_id: str = Field(min_length=1, max_length=255)


class WorkspaceScopeRequest(DomainScopeRequest):
    project_id: str = Field(max_length=255)


class DomainCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=4096)


def _visible_domains(user_id: str, *, operation: NativeOperation) -> list[dict]:
    from keystoneauth1.exceptions.http import NotFound
    from keystoneclient.exceptions import NotFound as ClientNotFound

    try:
        identity = keystone.get_identity_user(user_id, operation=operation)
        resolve_domain(identity["domain_id"], operation=operation)
        return domain_projects.accessible_domains(user_id, operation=operation)
    except (Unauthorized, NotFound, ClientNotFound) as exc:
        raise HTTPException(401, "Identity is disabled or unavailable; log in again") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Domain directory is unavailable") from exc


def _workspace_context(user_id: str, domain_id: str, *, operation: NativeOperation) -> dict:
    """User-console scope requires real membership, not global observation authority."""
    context = domain_context(user_id, domain_id, operation=operation)
    domain_projects.assert_membership(user_id, domain_id, operation=operation)
    return context


async def _domain_metadata(user_id: str, identity_domain_id: str, is_system_admin: bool, *, operation=None) -> dict:

    if operation is None:
        async with NativeOperation() as operation:
            return await _domain_metadata(user_id, identity_domain_id, is_system_admin, operation=operation)

    with authentication_step("domain_metadata"):
        domains = await operation.run(_visible_domains, user_id, operation=operation)
        can_create = get_settings().auth.organization_creation_enabled
        return {"available_domains": domains, "can_create_domain": bool(can_create)}


async def _build_token_response(
    *,
    keystone_token: str,
    project_id: str,
    project_name: str,
    user_id: str,
    username: str,
    roles: list[str],
    is_system_admin: bool,
    domain_id: str,
    domain_name: str,
    is_domain_manager: bool,
    identity_domain_id: str,
    identity_domain_name: str,
    provider_id: str = "",
    provider_revision: int | None = None,
    provider_domain_id: str = "",
    login_email: str = "",
    default_project_id: str = "",
    auth_method: str = "password",
    origin_ip: str = "",
    origin_fp: str = "",
    device_type: str = "",
    os: str = "",
    started_at: float | None = None,
    native_expires_at: str = "",
    previous_jti: str | None = None,
    previous_domain_id: str | None = None,
    connection_project_id: str | None = None,
    initial_workspace: dict | None = None,
    remember_workspace: bool = False,
    operation=None,
) -> TokenResponse:
    """Keystone 토큰으로 JWT access+refresh 쌍을 발급하고 TokenResponse를 반환."""
    with authentication_step("session_publication"):
        if not project_id:
            roles = []
        public_roles = await visible_role_names(roles, is_system_admin)
        if not domain_id or not domain_name or not identity_domain_id or not identity_domain_name:
            raise HTTPException(status_code=401, detail="Canonical working and identity domains are required")
        metadata = await _domain_metadata(user_id, identity_domain_id, is_system_admin, operation=operation)
        native_project_id = project_id if connection_project_id is None else connection_project_id
        if connection_project_id is not None:
            if not is_system_admin or not await asyncio.to_thread(keystone._is_system_admin, user_id):
                raise HTTPException(403, "Current system administrator authority is required")
            fresh = await asyncio.to_thread(domain_context, user_id, domain_id)
            assert_domain_resource(identity_domain_id, fresh["identity_domain_id"])
            if project_id:
                await asyncio.to_thread(assert_project_domain, domain_id, project_id)
        can_write = has_project_write_permission({"project_id": project_id, "roles": roles, "is_system_admin": False})
        now = datetime.now(UTC).timestamp()
        deadline = int((now if started_at is None else started_at) + get_settings().session_timeout_seconds)
        if native_expires_at:
            try:
                native_expiry = datetime.fromisoformat(native_expires_at)
                if native_expiry.tzinfo is None:
                    raise ValueError("Native expiry must include its timezone")
                deadline = min(deadline, int(native_expiry.timestamp()))
            except (TypeError, ValueError, OverflowError) as exc:
                raise HTTPException(503, "Native session lifetime is unavailable") from exc
        if deadline <= now:
            raise HTTPException(401, "Native or browser session has expired")
        refresh_str, r_jti, r_exp = jwt_service.sign_refresh(user_id, expires_at=deadline)
        access_str, _, a_exp = jwt_service.sign_access(
            user_id=user_id,
            username=username,
            project_id=native_project_id,
            project_name=project_name if connection_project_id is None else "",
            refresh_jti=r_jti,
            expires_at=deadline,
        )
        try:
            stored = await session_store.store_session(
                jti=r_jti,
                keystone_token=keystone_token,
                project_id=native_project_id,
                user_id=user_id,
                exp=r_exp,
                domain_id=domain_id,
                identity_domain_id=identity_domain_id,
                previous_domain_id=previous_domain_id,
                target_project_id=project_id if connection_project_id is not None else None,
                target_project_name=project_name if connection_project_id is not None else "",
                provider_id=provider_id,
                provider_revision=provider_revision,
                provider_domain_id=provider_domain_id,
                login_email=login_email,
                auth_method=auth_method,
                origin_ip=origin_ip,
                origin_fp=origin_fp,
                device_type=device_type,
                os=os,
                started_at=started_at,
                previous_jti=previous_jti,
                timeout_seconds=get_settings().session_timeout_seconds if previous_jti else None,
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Session publication is unavailable") from exc
        if stored is False:
            raise HTTPException(status_code=401, detail="세션이 만료되거나 이미 갱신되었습니다. 다시 로그인해 주세요.")
        if remember_workspace and project_id:
            from app.services import login_preferences

            await login_preferences.record(user_id, identity_domain_id, domain_id, project_id)
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
            domain_id=domain_id,
            domain_name=domain_name,
            is_domain_manager=is_domain_manager,
            identity_domain_id=identity_domain_id,
            identity_domain_name=identity_domain_name,
            **metadata,
            can_write=can_write,
            auth_method=auth_method,
            initial_workspace=initial_workspace,
        )


async def _enforce_session_policy(session: dict, identity: dict) -> None:
    from app.services.domain_auth import enforce_email, get_policy, require_password, require_provider

    identity_domain_id = identity["identity_domain_id"]
    expected = session.get("identity_domain_id") or session.get("domain_id")
    if expected:
        assert_domain_resource(expected, identity_domain_id)
    email = identity["email"]
    password_method = session.get("auth_method", "password") == "password"
    if password_method:
        await require_password(identity_domain_id, email)
    else:
        provider_id = session.get("provider_id")
        revision = session.get("provider_revision")
        email = session.get("login_email")
        if not provider_id or type(revision) is not int or not email:
            raise HTTPException(status_code=401, detail="Provider session context is unavailable; log in again")
        provider_domain_id = session.get("provider_domain_id")
        if not provider_domain_id:
            raise HTTPException(status_code=401, detail="Provider origin is unavailable; log in again")
        provider = await require_provider(provider_domain_id, provider_id, revision, email)
        if getattr(provider, "_organization", None) is not None:
            from app.services import organization_provisioning

            ks = await asyncio.to_thread(keystone._get_admin_ks_client)
            await organization_provisioning.require_current(provider, ks=ks, user_id=identity["user_id"])
    policy_origin = identity_domain_id if password_method else provider_domain_id
    if identity["domain_id"] != policy_origin:
        policy = await get_policy(identity["domain_id"])
        if policy.allowed_email_domains:
            enforce_email(policy, email)


async def _exchange_native_scope(token: str, project_id: str, *, operation=None) -> dict:
    with authentication_step("native_exchange"):
        try:
            kwargs = {"operation": operation} if operation is not None else {}
            run = operation.run if operation is not None else asyncio.to_thread
            return await run(keystone.validate_session, token, project_id=project_id, **kwargs)
        except Unauthorized as exc:
            raise HTTPException(401, "Native login proof was rejected") from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Native session exchange is unavailable") from exc


async def _prepare_initial_session(data: dict, *, operation=None) -> dict:
    """Choose a human's project-only personal landing without changing native identity."""
    if operation is None:
        async with NativeOperation() as operation:
            return await _prepare_initial_session(data, operation=operation)
    primary = None
    try:
        primary = await account_spaces.ensure_personal_project(data["user_id"], operation=operation)
    except HTTPException as exc:
        if exc.status_code == 503:
            recovery = await account_spaces.personal_recovery_status(data["user_id"], data["identity_domain_id"])
            if recovery is not None:
                raise HTTPException(503, recovery) from exc
        if exc.status_code != 403 or exc.detail != "service_identity_personal_forbidden":
            raise
    operation.invalidate()
    if primary is not None:
        from app.services import login_preferences

        preference = await login_preferences.read(data["user_id"], data["identity_domain_id"])
        if preference["remember_last_workspace"]:
            did, pid = preference["domain_id"], preference["project_id"]
            try:
                await operation.run(_workspace_context, data["user_id"], did, operation=operation)
                await operation.run(assert_project_domain, did, pid, operation=operation)
                await operation.run(
                    domain_projects.assert_project_membership, data["user_id"], pid, operation=operation
                )
            except HTTPException as exc:
                if exc.status_code not in {403, 404}:
                    raise
                operation.invalidate()
            else:
                # Only a stale authority hint may fall back. A rejected or
                # substituted native exchange remains a terminal login error.
                selected = await _prepare_domain_session(
                    data, did, requested_project_id=pid, ensure_access=False, operation=operation
                )
                selected["initial_workspace"] = {"kind": "remembered", "domain_id": did, "project_id": pid}
                return selected
        selected = await _prepare_domain_session(
            data, primary["domain_id"], requested_project_id=primary["id"], operation=operation
        )
        selected["initial_workspace"] = {
            "kind": "personal",
            "domain_id": primary["domain_id"],
            "project_id": primary["id"],
        }
        return selected
    home = await operation.run(resolve_domain, data["identity_domain_id"], operation=operation)
    if home.get("kind") == "account":
        # A projectless system administrator still cannot select identity-only account.
        domains = await operation.run(_visible_domains, data["user_id"], operation=operation)
        if not domains:
            raise HTTPException(403, "working_domain_required")
        selected = _administrator_workspace(data, domains[0]["id"], "", operation=operation)
        return {**selected, "session_token": data.get("session_token") or data["token"]}
    return await _prepare_domain_session(data, home["id"], operation=operation)


async def _prepare_domain_session(
    data: dict,
    domain_id: str,
    *,
    requested_project_id: str | None = None,
    ensure_access: bool = True,
    operation=None,
) -> dict:
    """Provision only verified membership, then exchange the caller's native token."""
    with authentication_step("domain_preparation"):
        kwargs = {"operation": operation} if operation is not None else {}
        run = operation.run if operation is not None else asyncio.to_thread
        with authentication_step("domain_context"):
            context = await run(domain_context, data["user_id"], domain_id, **kwargs)
            assert_domain_resource(data["identity_domain_id"], context["identity_domain_id"])
        if requested_project_id:
            await run(assert_project_domain, domain_id, requested_project_id, **kwargs)
            await run(domain_projects.assert_project_membership, data["user_id"], requested_project_id, **kwargs)
        if ensure_access:
            with authentication_step("login_access"):
                await domain_projects.ensure_login_access(data["user_id"], domain_id, **kwargs)
        with authentication_step("default_project"):
            # Provisioning may have created Default or repaired membership. Read
            # the final directory for both password and provider login paths.
            if context.get("domain_kind") == "personal":
                default = await run(account_spaces.personal_project, data["user_id"], **kwargs)
            else:
                default = await run(domain_projects.default_project, domain_id, **kwargs)
        with authentication_step("native_projects"):
            if (
                context.get("domain_kind") == "personal"
                and default is not None
                and requested_project_id == default["id"]
            ):
                # The exact primary already passed canonical provenance and live
                # membership checks. Enumerating every native membership cannot
                # strengthen this explicit target; the scoped exchange below
                # still independently proves native access and subject identity.
                projects = [default]
            else:
                try:
                    projects = await run(keystone.list_projects, data["token"], domain_id, **kwargs)
                except HTTPException:
                    raise
                except Exception as exc:
                    raise HTTPException(503, "Native project membership is unavailable") from exc
        # A saved user preference wins only within the enabled, accessible
        # projects of this domain. Canonical Default is the onboarding fallback.
        default_id = next(
            (p["id"] for p in projects if p["id"] == data.get("default_project_id")),
            default["id"] if default else "",
        )
        if requested_project_id is not None:
            matches = [p for p in projects if p["id"] == requested_project_id]
            if requested_project_id and len(matches) != 1 or not requested_project_id and projects:
                raise HTTPException(403, "Project is not accessible in the selected domain")
            target = matches[0] if matches else None
        else:
            target = next((p for p in projects if p["id"] == default_id), projects[0] if projects else None)
        project_id = target["id"] if target else ""
        if not data["project_id"] and not project_id:
            # The verified unscoped subject already is the final projectless token.
            native = {**data, **context}
        else:
            native = await _exchange_native_scope(data.get("session_token") or data["token"], project_id, **kwargs)
        await run(
            assert_token_context,
            native,
            user_id=data["user_id"],
            domain_id=domain_id,
            identity_domain_id=data["identity_domain_id"],
            project_id=project_id,
            **kwargs,
        )
        native["default_project_id"] = default_id if any(p["id"] == default_id for p in projects) else ""
        native["session_token"] = native.get("session_token") or data.get("session_token") or data["token"]
        return native


class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            # Source endpoint names only: never use a URL, input or client request ID.
            with authentication_operation(self.endpoint.__name__):
                try:
                    with authentication_step("request"):
                        response = await handler(request)
                except RequestValidationError:
                    response = JSONResponse({"detail": "Invalid authentication input"}, status_code=422)
                except DomainAuthError as exc:
                    response = domain_auth_error_response(exc)
                except HTTPException as exc:
                    response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
                response.headers.update({"Cache-Control": "no-store, private", "Pragma": "no-cache"})
                return response

        return guarded


router = APIRouter(route_class=AuthRoute)


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
    async with NativeOperation() as operation:
        return await _login(request, req, background_tasks, operation)


@router.post("/personal-project/recovery", response_model=TokenResponse)
@limiter.limit("10/minute")
async def recover_personal_project(request: Request, req: LoginRequest, background_tasks: BackgroundTasks):
    """Fresh password/subject proof precedes safe resume; unknown calls stay fenced."""
    async with NativeOperation() as operation:
        return await _login(request, req, background_tasks, operation)


async def _login(request: Request, req: LoginRequest, background_tasks: BackgroundTasks, operation: NativeOperation):
    from app.services.account_identity import authenticate_password, password_account
    from app.services.domain_auth import DomainAuthDenied, get_policy, require_password

    try:
        with authentication_step("resolve"):
            account = await operation.run(password_account, req.username, operation=operation)
        with authentication_step("password_method_policy"):
            if not (await get_policy(account["domain_id"])).password_enabled:
                raise DomainAuthDenied("Password login is disabled for this account", code="password_disabled")
        with authentication_step("authenticate"):
            data = await authenticate_password(account, req.password, operation=operation)
    except keystone.PasswordRejected as exc:
        raise HTTPException(status_code=401, detail="인증 실패") from exc
    except Unauthorized as exc:
        # A disabled subject/denied project is not a bad-password attempt.
        raise HTTPException(status_code=401, detail="인증 실패") from exc
    except (HTTPException, DomainAuthError):
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="인증 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from exc

    assert_domain_resource(account["domain_id"], data.get("identity_domain_id"))
    if data.get("user_id") != account["id"]:
        raise HTTPException(401, "Native account subject changed")

    with authentication_step("password_policy"):
        await require_password(account["domain_id"], data["email"])
    # Policy I/O must not carry pre-proof directory authority into provisioning.
    operation.invalidate()
    data = await _prepare_initial_session(data, operation=operation)
    default_project_id = data.get("default_project_id", "")

    # 로그인 출처 + 기기 정보 기록
    from app.services.token_binding import get_origin, parse_device

    origin_ip, origin_fp = get_origin(request)
    device_type, os_name = parse_device(request.headers.get("User-Agent", ""))

    # Only an exact, policy-valid canonical native proof clears its account guard.
    await login_guard.record_success(account["name"], account["domain_id"])

    # 대시보드 캐시 프리워밍 + 최근 프로젝트 기록 (백그라운드)
    if data["project_id"]:
        background_tasks.add_task(_prewarm_dashboard, data["token"], data["project_id"])
        background_tasks.add_task(record_project_access, data["user_id"], data["project_id"])

    response = await _build_token_response(
        keystone_token=data["session_token"],
        project_id=data["project_id"],
        project_name=data["project_name"],
        user_id=data["user_id"],
        username=data["username"],
        roles=data.get("roles", []),
        native_expires_at=data.get("session_expires_at") or data.get("expires_at", ""),
        is_system_admin=data.get("is_system_admin", False),
        domain_id=data["domain_id"],
        domain_name=data["domain_name"],
        is_domain_manager=data["is_domain_manager"],
        identity_domain_id=data["identity_domain_id"],
        identity_domain_name=data["identity_domain_name"],
        default_project_id=default_project_id,
        initial_workspace=data.get("initial_workspace"),
        connection_project_id=data.get("connection_project_id"),
        auth_method="password",
        origin_ip=origin_ip,
        origin_fp=origin_fp,
        device_type=device_type,
        os=os_name,
        operation=operation,
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
    metadata = await _domain_metadata(
        token_info["user_id"], token_info["identity_domain_id"], token_info.get("is_system_admin") is True
    )
    return UserInfo(
        user_id=token_info["user_id"],
        username=token_info["username"],
        project_id=token_info["project_id"],
        project_name=token_info["project_name"],
        roles=await visible_role_names(token_info["roles"], token_info.get("is_system_admin", False)),
        is_system_admin=token_info.get("is_system_admin", False),
        can_write=has_project_write_permission({**token_info, "is_system_admin": False}),
        auth_method=token_info.get("auth_method", "password"),
        domain_id=token_info["domain_id"],
        domain_name=token_info["domain_name"],
        is_domain_manager=token_info.get("is_domain_manager", False),
        identity_domain_id=token_info["identity_domain_id"],
        identity_domain_name=token_info["identity_domain_name"],
        **metadata,
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
                raise HTTPException(status_code=403, detail="세션 소유권이 일치하지 않습니다.")
            removed = await session_store.delete_session(refresh_jti)
            if isinstance(removed, dict):
                if removed.get("user_id") != token_info["user_id"]:
                    raise HTTPException(status_code=403, detail="세션 소유권이 일치하지 않습니다.")
                keystone_token = removed.get("keystone_token") or keystone_token
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=503, detail="세션 폐기를 확인할 수 없습니다. 잠시 후 다시 시도해 주세요."
            ) from exc

    if keystone_token:
        try:
            await asyncio.to_thread(keystone.revoke_token, keystone_token)
        except Exception as exc:
            await invalidate_token_cache(token, pid)
            raise HTTPException(
                status_code=503, detail="인증 토큰 폐기를 확인할 수 없습니다. 다시 로그인해 주세요."
            ) from exc
    await invalidate_token_cache(token, pid)
    return {"message": "로그아웃 완료"}


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_token(request: Request, req: RefreshRequest):
    async with NativeOperation() as operation:
        return await _refresh_token(request, req, operation=operation)


async def _refresh_token(request: Request, req: RefreshRequest, *, operation: NativeOperation):
    """refresh JWT로 새 access JWT + refresh JWT 발급 (토큰 회전).

    기존 refresh JTI는 즉시 삭제되므로 같은 refresh 토큰으로 두 번 호출하면 두 번째는 401.
    """
    try:
        r_payload = jwt_service.verify_refresh(req.refresh_token)
    except Exception:
        raise HTTPException(status_code=401, detail="유효하지 않은 refresh 토큰")

    r_jti = r_payload["jti"]
    with authentication_step("session_lookup"):
        try:
            sess = await session_store.get_session(r_jti)
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=503, detail="세션 저장소 연결 실패") from exc

    if sess is None:
        raise HTTPException(status_code=401, detail="세션이 만료되었습니다. 다시 로그인해 주세요.")
    if sess.get("user_id") != r_payload.get("sub"):
        raise HTTPException(status_code=401, detail="refresh 토큰의 세션 소유권이 일치하지 않습니다.")
    if not isinstance(sess.get("domain_id"), str) or not sess["domain_id"]:
        raise HTTPException(status_code=401, detail="세션의 도메인을 확인할 수 없습니다. 다시 로그인해 주세요.")

    # 블랙리스트 세션은 refresh 갱신도 거부
    if sess.get("blacklisted"):
        raise HTTPException(status_code=401, detail="세션이 차단되었습니다.")

    # ── 세션 타임아웃 검증 ─────────────────────────────────────────────────────
    import hashlib as _hl

    _rjti_hash = _hl.sha256(r_jti.encode()).hexdigest()
    started_at = await _check_session_timeout(
        _rjti_hash,
        sess.get("project_id", ""),
        refresh_jti=r_jti,
        session=sess,
        issued_at=r_payload.get("iat", 0),
    )

    # A refresh credential must obey the same origin policy as access requests.
    from app.services.token_binding import check_binding, get_origin

    try:
        cur_ip, cur_fp = get_origin(request)
        action, reason = check_binding(sess, cur_ip, cur_fp, get_settings().token_ip_binding_mode)
        if action == "block":
            await session_store.blacklist_session(r_jti, reason)
            raise HTTPException(status_code=401, detail="토큰 출처가 일치하지 않습니다.")
        if action == "log":
            await activity_svc.record(
                project_id=sess.get("project_id", ""),
                user_id=sess.get("user_id", ""),
                username="",
                resource_type="auth",
                action="token_origin_mismatch",
                status="success",
                extra={"ip": cur_ip, "origin_ip": sess.get("origin_ip", ""), "reason": reason, "blocked": False},
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="토큰 바인딩 검사를 완료할 수 없습니다. 잠시 후 다시 시도해 주세요."
        ) from exc

    # 최초 로그인 origin과 기기 정보를 회전 너머로 그대로 운반 (재파싱 금지)
    origin_ip = sess.get("origin_ip", "")
    origin_fp = sess.get("origin_fp", "")
    device_type = sess.get("device_type", "")
    os_name = sess.get("os", "")

    # Verify the independent login before checking its current project authority.
    operation.invalidate()
    try:
        root = await _exchange_native_scope(sess["keystone_token"], "", operation=operation)
    except HTTPException as exc:
        if exc.status_code == 401:
            await session_store.delete_session(r_jti)
        raise
    if root["user_id"] != sess["user_id"] or root["identity_domain_id"] != (
        sess.get("identity_domain_id") or sess["domain_id"]
    ):
        raise HTTPException(403, "Native login identity does not match the session")
    context = await operation.run(domain_context, sess["user_id"], sess["domain_id"], operation=operation)
    assert_domain_resource(root["identity_domain_id"], context["identity_domain_id"])
    await _enforce_session_policy(sess, {**root, **context})
    logical_workspace = isinstance(sess.get("target_project_id"), str)
    try:
        kc_info = await _exchange_native_scope(root["session_token"], sess["project_id"], operation=operation)
    except keystone.ProjectAccessDenied:
        kc_info = {**root, "project_id": "", "project_name": "", "roles": []}
    operation.invalidate()
    native_domain_id = root["identity_domain_id"]
    if kc_info["project_id"]:
        native_domain_id = kc_info["domain_id"] if logical_workspace else sess["domain_id"]
    await operation.run(
        assert_token_context,
        kc_info,
        user_id=sess["user_id"],
        domain_id=native_domain_id,
        project_id=kc_info["project_id"],
        identity_domain_id=sess.get("identity_domain_id") or sess["domain_id"],
        operation=operation,
    )
    if not kc_info["project_id"]:
        # Only after native subject/home checks may selected-domain authority
        # replace the home-derived working domain of an unscoped result.
        kc_info = {**kc_info, **context}
    connection_project_id = kc_info["project_id"]
    if logical_workspace:
        kc_info = await operation.run(
            _administrator_workspace, kc_info, sess["domain_id"], sess["target_project_id"], operation=operation
        )
    await _enforce_session_policy(sess, kc_info)

    # Redis consumes the old record and publishes its replacement atomically.
    try:
        operation.invalidate()
        token_resp = await _build_token_response(
            keystone_token=kc_info["session_token"],
            project_id=kc_info["project_id"],
            project_name=kc_info["project_name"],
            user_id=kc_info["user_id"],
            username=kc_info["username"],
            roles=kc_info.get("roles", []),
            is_system_admin=kc_info.get("is_system_admin", False),
            domain_id=kc_info["domain_id"],
            domain_name=kc_info["domain_name"],
            is_domain_manager=kc_info["is_domain_manager"],
            identity_domain_id=kc_info["identity_domain_id"],
            identity_domain_name=kc_info["identity_domain_name"],
            provider_id=sess.get("provider_id", ""),
            provider_revision=sess.get("provider_revision"),
            provider_domain_id=sess.get("provider_domain_id", ""),
            login_email=sess.get("login_email", ""),
            auth_method=sess.get("auth_method", "password"),
            origin_ip=origin_ip,
            origin_fp=origin_fp,
            device_type=device_type,
            os=os_name,
            started_at=started_at,
            native_expires_at=kc_info.get("session_expires_at", ""),
            previous_jti=r_jti,
            connection_project_id=connection_project_id if logical_workspace else None,
            operation=operation,
        )
        return token_resp
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail="세션 갱신 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
        ) from exc


@router.post("/token/project", response_model=TokenResponse)
async def scope_project(req: ProjectScopeRequest, token_info: dict = Depends(get_token_info)):
    async with NativeOperation() as operation:
        return await _scope_project(req, token_info, operation=operation)


async def _scope_project(req: ProjectScopeRequest, token_info: dict, *, operation: NativeOperation):
    """접근 가능한 프로젝트로 새 토큰 쌍 발급 (rescope)."""
    keystone_token = token_info["session_token"]
    await operation.run(assert_project_domain, token_info["domain_id"], req.project_id, operation=operation)

    await operation.run(
        domain_projects.assert_project_membership, token_info["user_id"], req.project_id, operation=operation
    )
    operation.invalidate()
    kc_info = await _exchange_native_scope(keystone_token, req.project_id, operation=operation)
    operation.invalidate()
    await operation.run(
        assert_token_context,
        kc_info,
        user_id=token_info["user_id"],
        domain_id=token_info["domain_id"],
        project_id=req.project_id,
        identity_domain_id=token_info["identity_domain_id"],
        operation=operation,
    )
    await _enforce_session_policy(token_info, kc_info)

    old_rjti = token_info.get("refresh_jti")
    await record_project_access(kc_info["user_id"], kc_info["project_id"])
    try:
        operation.invalidate()
        return await _build_token_response(
            keystone_token=kc_info["session_token"],
            project_id=kc_info["project_id"],
            project_name=kc_info["project_name"],
            user_id=kc_info["user_id"],
            username=kc_info["username"],
            roles=kc_info.get("roles", []),
            is_system_admin=kc_info.get("is_system_admin", False),
            domain_id=kc_info["domain_id"],
            domain_name=kc_info["domain_name"],
            is_domain_manager=kc_info["is_domain_manager"],
            identity_domain_id=kc_info["identity_domain_id"],
            identity_domain_name=kc_info["identity_domain_name"],
            provider_id=token_info.get("provider_id", ""),
            provider_revision=token_info.get("provider_revision"),
            provider_domain_id=token_info.get("provider_domain_id", ""),
            login_email=token_info.get("login_email", ""),
            auth_method=token_info.get("auth_method", "password"),
            # 기존 세션의 origin·기기 정보를 그대로 운반 (프로젝트 전환 시 재파싱 금지)
            origin_ip=token_info.get("origin_ip", ""),
            origin_fp=token_info.get("origin_fp", ""),
            device_type=token_info.get("device_type", ""),
            os=token_info.get("os", ""),
            started_at=token_info.get("started_at"),
            previous_jti=old_rjti,
            native_expires_at=kc_info.get("session_expires_at", ""),
            remember_workspace=True,
            operation=operation,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="프로젝트 세션 갱신을 완료할 수 없습니다. 다시 시도해 주세요.")


@router.get("/domains", response_model=list[DomainInfo])
async def list_domains(token_info: dict = Depends(get_token_info)):
    async with NativeOperation() as operation:
        return await operation.run(_visible_domains, token_info["user_id"], operation=operation)


def _workspace_projects(token: str, user_id: str, context: dict, *, operation: NativeOperation) -> list[dict]:
    """Read enabled projects from actual membership or current domain management."""
    domain_id = context["domain_id"]
    ks = operation.ks
    if context["is_domain_manager"]:
        rows = []
        projects = operation.read(
            ("domain_projects", "project_list", domain_id), lambda: list(ks.projects.list(domain=domain_id))
        )
        for project in projects:
            assert_domain_resource(domain_id, _field(project, "domain_id"))
            if _field(project, "enabled") is True:
                rows.append(
                    {
                        "id": _field(project, "id"),
                        "name": project_display.display_name(project, operation=operation),
                        "description": _field(project, "description", "") or "",
                        "domain_id": domain_id,
                        "domain_name": context["domain_name"],
                        "enabled": True,
                    }
                )
    else:
        rows = []
        for project in keystone.list_projects(token, domain_id, operation=operation):
            assert_domain_resource(domain_id, project.get("domain_id"))
            if project.get("enabled") is not True:
                continue
            try:
                domain_projects.assert_project_membership(user_id, project["id"], operation=operation)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                # A stale native manager projection is not real membership.
                continue
            rows.append(project)
    ids = [project.get("id") for project in rows]
    if any(not isinstance(pid, str) or not pid for pid in ids) or len(set(ids)) != len(ids):
        raise HTTPException(503, "Project directory identity is unavailable")
    return sorted(rows, key=lambda project: (project["name"].casefold(), project["id"]))


def _administrator_workspace(
    current: dict, domain_id: str, project_id: str | None, *, operation: NativeOperation
) -> dict:
    user_id = current["user_id"]
    if not keystone._is_system_admin(user_id, operation=operation):
        raise HTTPException(403, "Current system administrator authority is required")
    context = domain_context(user_id, domain_id, operation=operation)
    assert_domain_resource(current["identity_domain_id"], context["identity_domain_id"])
    if project_id is None:
        projects = _workspace_projects(current["token"], user_id, context, operation=operation)
        default = domain_projects.default_project(domain_id, operation=operation)
        project_id = (
            default["id"]
            if default and any(row["id"] == default["id"] for row in projects)
            else (projects[0]["id"] if projects else "")
        )
    name = ""
    if project_id:
        assert_project_domain(domain_id, project_id, operation=operation)
        name = project_display.display_name(operation.get("projects", project_id), operation=operation)
    return {**current, **context, "project_id": project_id, "project_name": name, "roles": [], "is_system_admin": True}


@router.get("/workspaces", response_model=WorkspaceInfo)
async def browse_workspace(
    domain_id: str | None = Query(default=None, min_length=1, max_length=255),
    token_info: dict = Depends(get_token_info),
):
    """Browse an authorized domain without rescoping, creating grants or rotating sessions."""
    user_id = token_info["user_id"]
    target = domain_id if domain_id is not None else token_info["domain_id"]
    async with NativeOperation() as operation:
        context = await operation.run(_workspace_context, user_id, target, operation=operation)
        assert_domain_resource(token_info["identity_domain_id"], context["identity_domain_id"])
        try:
            projects = await operation.run(
                _workspace_projects, token_info["token"], user_id, context, operation=operation
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(503, "Project directory is unavailable") from exc
        if context.get("domain_kind") == "personal":
            default = await operation.run(account_spaces.personal_project, user_id, operation=operation)
        else:
            default = await operation.run(domain_projects.default_project, target, operation=operation)
        can_create = await project_service.can_create_project(user_id, target, operation=operation)
        # Transport may survive the inventory; authority observations must not.
        operation.invalidate()
        fresh = await operation.run(_workspace_context, user_id, target, operation=operation)
        assert_domain_resource(token_info["identity_domain_id"], fresh["identity_domain_id"])
        if fresh["is_domain_manager"] != context["is_domain_manager"]:
            raise HTTPException(403, "Domain authority changed; refresh the resource directory")
        if not fresh["is_domain_manager"]:
            for project in projects:
                await operation.run(
                    domain_projects.assert_project_membership, user_id, project["id"], operation=operation
                )
        return WorkspaceInfo(
            domain=DomainInfo(id=target, name=fresh["domain_name"], kind=fresh.get("domain_kind", "legacy")),
            projects=[ProjectInfo(**project) for project in projects],
            default_project_id=default["id"] if default and any(p["id"] == default["id"] for p in projects) else "",
            is_domain_manager=fresh["is_domain_manager"],
            can_create_project=can_create,
        )


@router.post("/domains", status_code=201)
async def create_domain(req: DomainCreateRequest, token_info: dict = Depends(get_token_info)):
    """Create an organization using live native authority and its independent policy."""

    user_id = token_info["user_id"]
    try:
        identity = await asyncio.to_thread(keystone.get_identity_user, user_id)
    except Unauthorized as exc:
        raise HTTPException(401, "Identity is disabled or unavailable; log in again") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Identity directory is unavailable") from exc
    assert_domain_resource(token_info["identity_domain_id"], identity["domain_id"])
    admin = await asyncio.to_thread(keystone._is_system_admin, user_id)
    if not admin and not get_settings().auth.organization_creation_enabled:
        raise HTTPException(403, "organization_creation_disabled")
    result = await domain_projects.create_domain(
        name=req.name, description=req.description, enabled=True, creator_id=user_id
    )
    await activity_svc.record(
        project_id="",
        user_id=user_id,
        username=token_info.get("username", ""),
        resource_type="domain",
        action="domain.create",
        status="success",
        resource_id=result["id"],
        service="keystone",
        extra={"domain_id": result["id"], "name": result["name"]},
    )
    return result


async def _scope_working_domain(domain_id: str, token_info: dict, *, project_id: str | None = None):
    async with NativeOperation() as operation:
        return await _switch_working_domain(domain_id, token_info, project_id=project_id, operation=operation)


async def _switch_working_domain(
    domain_id: str, token_info: dict, *, project_id: str | None, operation: NativeOperation
):
    """Explicitly switch only working scope; identity, login policy and lifetime persist."""
    user_id = token_info["user_id"]
    context = await operation.run(_workspace_context, user_id, domain_id, operation=operation)
    assert_domain_resource(token_info["identity_domain_id"], context["identity_domain_id"])
    system_admin = await operation.run(keystone._is_system_admin, user_id, operation=operation)
    connection_project_id = token_info.get("connection_project_id", token_info["project_id"])
    if project_id:
        await operation.run(assert_project_domain, domain_id, project_id, operation=operation)
        await operation.run(domain_projects.assert_project_membership, user_id, project_id, operation=operation)
    current = await _exchange_native_scope(
        token_info["session_token"], connection_project_id if system_admin else "", operation=operation
    )
    operation.invalidate()
    await operation.run(
        assert_token_context,
        current,
        user_id=user_id,
        domain_id=current["domain_id"],
        identity_domain_id=token_info["identity_domain_id"],
        project_id=connection_project_id if system_admin else "",
        operation=operation,
    )
    await _enforce_session_policy(token_info, {**current, **context})
    # Check the target again after the current-subject exchange and policy read.
    operation.invalidate()
    data = await _prepare_domain_session(current, domain_id, requested_project_id=project_id, operation=operation)
    await _enforce_session_policy(token_info, data)
    operation.invalidate()
    final_context = await operation.run(_workspace_context, user_id, domain_id, operation=operation)
    assert_domain_resource(token_info["identity_domain_id"], final_context["identity_domain_id"])
    if final_context["is_domain_manager"] != data["is_domain_manager"]:
        raise HTTPException(403, "Domain authority changed during workspace selection")
    if data["project_id"]:
        await operation.run(domain_projects.assert_project_membership, user_id, data["project_id"], operation=operation)
    response = await _build_token_response(
        keystone_token=data["session_token"],
        native_expires_at=data.get("session_expires_at") or data.get("expires_at", ""),
        project_id=data["project_id"],
        project_name=data["project_name"],
        user_id=user_id,
        username=data["username"],
        roles=data["roles"],
        is_system_admin=data["is_system_admin"],
        domain_id=data["domain_id"],
        domain_name=data["domain_name"],
        is_domain_manager=data["is_domain_manager"],
        identity_domain_id=data["identity_domain_id"],
        identity_domain_name=data["identity_domain_name"],
        default_project_id=data.get("default_project_id", ""),
        provider_id=token_info.get("provider_id", ""),
        provider_revision=token_info.get("provider_revision"),
        provider_domain_id=token_info.get("provider_domain_id", ""),
        login_email=token_info.get("login_email", ""),
        auth_method=token_info.get("auth_method", "password"),
        origin_ip=token_info.get("origin_ip", ""),
        origin_fp=token_info.get("origin_fp", ""),
        device_type=token_info.get("device_type", ""),
        os=token_info.get("os", ""),
        started_at=token_info.get("started_at"),
        previous_jti=token_info["refresh_jti"],
        previous_domain_id=token_info["domain_id"],
        remember_workspace=True,
        operation=operation,
    )
    if data["project_id"]:
        await record_project_access(user_id, data["project_id"])
    return response


@router.post("/token/domain", response_model=TokenResponse)
async def scope_domain(req: DomainScopeRequest, token_info: dict = Depends(get_token_info)):
    return await _scope_working_domain(req.domain_id, token_info)


@router.post("/token/workspace", response_model=TokenResponse)
async def scope_workspace(req: WorkspaceScopeRequest, token_info: dict = Depends(get_token_info)):
    """Commit one exact domain/project pair without publishing an intermediate session."""
    return await _scope_working_domain(req.domain_id, token_info, project_id=req.project_id)


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
        return [GroupInfo(**g) for g in groups if g.get("domain_id") == token_info["domain_id"]]
    except PermissionError:
        return []
    except Exception:
        raise HTTPException(status_code=500, detail="그룹 목록 조회 실패")


@router.get("/projects", response_model=list[ProjectInfo])
async def list_projects(token_info: dict = Depends(get_token_info)):
    """Use the same live user membership directory as the resource selector."""
    workspace = await browse_workspace(domain_id=token_info["domain_id"], token_info=token_info)
    return workspace.projects


@router.get("/projects/recent", response_model=list[ProjectInfo])
async def list_projects_recent(token_info: dict = Depends(get_token_info)):
    """최근 접근 순으로 정렬된 프로젝트 목록 반환.

    Redis에 기록된 접근 시각 기준으로 정렬하고, last_accessed_at 필드를 포함한다.
    Redis 기록이 없는 프로젝트는 이름순으로 뒤에 덧붙인다.
    """
    workspace = await browse_workspace(domain_id=token_info["domain_id"], token_info=token_info)
    projects = workspace.projects

    user_id = token_info["user_id"]
    recent_ids = await get_recent_project_ids(user_id)
    recent_map: dict[str, int] = {pid: ts for pid, ts in recent_ids}

    project_infos: list[ProjectInfo] = []
    for project in projects:
        ts = recent_map.get(project.id)
        last_accessed_at = datetime.fromtimestamp(ts / 1000, tz=UTC).isoformat() if ts else None
        project_infos.append(project.model_copy(update={"last_accessed_at": last_accessed_at}))

    # 최근 접근 기록 있는 것 먼저(최신순), 없는 것은 이름순
    def _sort_key(pi: ProjectInfo) -> tuple[int, str]:
        ts = recent_map.get(pi.id, 0)
        return (-ts, pi.name)

    project_infos.sort(key=_sort_key)
    return project_infos


async def issue_federated_login(
    request: Request,
    background_tasks: BackgroundTasks,
    *,
    unscoped_token: str,
    user_id: str,
    username: str,
    domain_id: str,
    domain_name: str,
    provider_id: str,
    provider_revision: int,
    provider_kind: str,
    login_email: str,
) -> TokenResponse:
    """Verify provider-origin policy and canonical subject, then open the personal workspace."""
    async with NativeOperation() as operation:
        with authentication_step("federated_login"):
            with authentication_step("resolve"):
                origin = await operation.run(resolve_domain, domain_id, operation=operation)
                identity = await operation.run(keystone.get_identity_user, user_id, operation=operation)
                context = {"identity_domain_id": identity["domain_id"]}
                if origin["name"] != domain_name:
                    raise HTTPException(status_code=403, detail="Federation domain does not match")
            with authentication_step("native_exchange"):
                data = await operation.run(keystone.validate_session, unscoped_token, operation=operation)
                await operation.run(
                    assert_token_context,
                    data,
                    user_id=user_id,
                    domain_id=data["domain_id"],
                    identity_domain_id=context["identity_domain_id"],
                    project_id="",
                    operation=operation,
                )
            policy_context = {
                "auth_method": "federated",
                "provider_id": provider_id,
                "provider_revision": provider_revision,
                "provider_domain_id": domain_id,
                "login_email": login_email,
            }
            with authentication_step("session_policy"):
                # Provider origin controls authentication, not implicit tenant membership.
                await _enforce_session_policy(
                    policy_context, {**data, **context, "domain_id": context["identity_domain_id"]}
                )
            # Reuse the connection, not authority observed before policy I/O.
            operation.invalidate()
            origin = await operation.run(resolve_domain, domain_id, operation=operation)
            try:
                identity = await operation.run(keystone.get_identity_user, user_id, operation=operation)
            except Unauthorized as exc:
                raise HTTPException(401, "Federated identity is disabled or unavailable") from exc
            assert_domain_resource(context["identity_domain_id"], identity["domain_id"])
            if origin["name"] != domain_name:
                raise HTTPException(status_code=403, detail="Federation domain does not match")
            data = await _prepare_initial_session(data, operation=operation)
            default_project_id = data.get("default_project_id", "")
            from app.services.token_binding import get_origin, parse_device

            origin_ip, origin_fp = get_origin(request)
            device_type, os_name = parse_device(request.headers.get("User-Agent", ""))
            operation.invalidate()
            response = await _build_token_response(
                keystone_token=data["session_token"],
                native_expires_at=data.get("session_expires_at") or data.get("expires_at", ""),
                project_id=data["project_id"],
                project_name=data["project_name"],
                user_id=data["user_id"],
                username=data["username"],
                roles=data["roles"],
                is_system_admin=data["is_system_admin"],
                domain_id=data["domain_id"],
                domain_name=data["domain_name"],
                is_domain_manager=data["is_domain_manager"],
                identity_domain_id=data["identity_domain_id"],
                identity_domain_name=data["identity_domain_name"],
                default_project_id=default_project_id,
                initial_workspace=data.get("initial_workspace"),
                connection_project_id=data.get("connection_project_id"),
                origin_ip=origin_ip,
                origin_fp=origin_fp,
                device_type=device_type,
                os=os_name,
                operation=operation,
                **policy_context,
            )
            if data["project_id"]:
                background_tasks.add_task(_prewarm_dashboard, data["token"], data["project_id"])
                background_tasks.add_task(record_project_access, data["user_id"], data["project_id"])
            await activity_svc.record(
                project_id=data["project_id"],
                user_id=data["user_id"],
                username=data["username"],
                resource_type="auth",
                action="login",
                status="success",
                source="afterglow",
                service="keystone",
                extra={"method": "federated", "provider_kind": provider_kind},
            )
            return response
