from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from drover_sdk.proxy import Proxy as DroverProxy
from fastapi import HTTPException
from keystoneauth1 import session as ks_session
from keystoneauth1.exceptions.http import NotFound, Unauthorized
from keystoneauth1.identity import v3
from waygate_sdk.proxy import Proxy as WaygateProxy

from app.config import get_settings
from app.utils.auth_diagnostics import authentication_step

if TYPE_CHECKING:
    import openstack

_logger = logging.getLogger(__name__)
_NATIVE_INVALID_TOKEN_MESSAGES = frozenset({"Failed to validate token", "Could not recognize Fernet token"})


def list_all_project_ids() -> set[str]:
    """admin 자격으로 전체 프로젝트 ID 셋 반환. 캐싱 없음 — orphan 스캔처럼 호출 빈도 낮은 경로용."""
    ks = _get_admin_ks_client()
    return {p.id for p in ks.projects.list()}


def _get_admin_ks_client():
    """서비스 admin 크리덴셜로 Keystone v3 Client 생성.

    사용자 세션은 OpenStack policy 때문에 role_assignments 조회가 제한될 수 있으므로,
    시스템 admin 판별은 서비스 크리덴셜로 수행한다.
    """
    from keystoneclient.v3 import client as ks_client

    settings = get_settings()
    admin_auth = v3.Password(
        auth_url=settings.os_auth_url,
        username=settings.os_username,
        password=settings.os_password,
        project_name=settings.os_project_name,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
    )
    admin_sess = ks_session.Session(auth=admin_auth, timeout=15, verify=settings.ssl_verify)
    return ks_client.Client(session=admin_sess, interface=settings.os_interface, region_name=settings.os_region_name)


def _resolve_admin_role_id() -> str:
    """Resolve the unique canonical global admin role, independent of any project."""
    from fastapi import HTTPException

    from app.services.identity_roles import _field

    roles = list(_get_admin_ks_client().roles.list(name="admin"))
    roles = [r for r in roles if _field(r, "domain_id") is None and _field(r, "name", "").casefold() == "admin"]
    if len(roles) != 1 or _field(roles[0], "name") != "admin" or not _field(roles[0], "id"):
        raise HTTPException(status_code=503, detail="Canonical system admin role is unavailable")
    return _field(roles[0], "id")


def _has_system_admin_role(user_id: str, *, operation=None) -> bool:
    """Only a live exact system:all effective canonical admin grant authorizes."""
    from app.services.domain_scope import has_scope_authority

    return has_scope_authority(user_id, operation=operation) if operation is not None else has_scope_authority(user_id)


def _is_system_admin(user_id: str, *, operation=None) -> bool:
    return (
        _has_system_admin_role(user_id, operation=operation)
        if operation is not None
        else _has_system_admin_role(user_id)
    )


def get_identity_user(user_id: str, *, operation=None) -> dict:
    """Read the real identity domain/email, not a username-shaped email guess."""
    from app.services.identity_roles import _field
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return get_identity_user(user_id, operation=operation)
    user = operation.get("users", user_id)
    if _field(user, "id") != user_id or _field(user, "enabled") is not True:
        raise Unauthorized(message="User is disabled or unavailable")
    domain_id = _field(user, "domain_id")
    if not isinstance(domain_id, str) or not domain_id:
        raise Unauthorized(message="User domain is unavailable")
    email = _field(user, "email") or ""
    return {
        "id": user_id,
        "domain_id": domain_id,
        "email": email if isinstance(email, str) else "",
        "default_project_id": _field(user, "default_project_id") or "",
    }


def _access_info(access, *, operation=None) -> dict:
    from app.services.domain_scope import assert_domain_resource, domain_context, resolve_domain

    with authentication_step("native_identity_subject"):
        user = get_identity_user(access.user_id, operation=operation)
        assert_domain_resource(user["domain_id"], access.user_domain_id)
    project_id = access.project_id or ""
    working_domain = access.project_domain_id if project_id else user["domain_id"]
    with authentication_step("native_domain_authority"):
        home = resolve_domain(user["domain_id"], operation=operation)
        if not project_id and home.get("kind") == "account":
            # An unscoped identity proof may originate in account; it is never a workspace grant.
            context = {
                "identity_domain_id": home["id"],
                "identity_domain_name": home["name"],
                "domain_id": home["id"],
                "domain_name": home["name"],
                "domain_kind": "account",
                "is_domain_manager": False,
            }
        else:
            context = domain_context(access.user_id, working_domain, operation=operation)
    if project_id:
        from app.services.domain_projects import assert_project_membership

        with authentication_step("native_project_authority"):
            assert_project_membership(access.user_id, project_id, operation=operation)
    with authentication_step("native_system_authority"):
        is_system_admin = _is_system_admin(access.user_id, operation=operation)
    return {
        "token": access.auth_token,
        "project_id": project_id,
        "project_name": access.project_name or "",
        "user_id": access.user_id,
        "username": access.username or "",
        "expires_at": access.expires.isoformat() if access.expires else "",
        # An unscoped subject must never inherit domain roles as project roles.
        "roles": list(access.role_names or []) if project_id else [],
        "is_system_admin": is_system_admin,
        "email": user["email"],
        "default_project_id": user["default_project_id"],
        "project_domain_id": access.project_domain_id if project_id else "",
        **context,
    }


class PasswordRejected(Unauthorized):
    """Only the password authentication stage rejected the supplied credential."""


def authenticate(
    username: str, password: str, project_name: str, domain_name: str, *, operation=None, unscoped_only: bool = False
) -> dict:
    """Verify a password; login may defer scope selection until Default is ready.

    Other callers retain the historical initial-project selection contract.
    """
    from app.services.domain_scope import assert_domain_resource, assert_token_context, resolve_domain
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return authenticate(
                username, password, project_name, domain_name, operation=operation, unscoped_only=unscoped_only
            )
    with authentication_step("native_domain_resolution"):
        domain = resolve_domain(domain_name, operation=operation)
    settings = get_settings()
    auth = v3.Password(
        auth_url=settings.os_auth_url,
        username=username,
        password=password,
        user_domain_id=domain["id"],
        unscoped=True,
    )
    sess = operation.own_session(ks_session.Session(auth=auth, timeout=30, verify=settings.ssl_verify))
    try:
        with authentication_step("native_password_exchange"):
            access = auth.get_access(sess)
    except Unauthorized as exc:
        raise PasswordRejected(message="Password authentication failed") from exc
    with authentication_step("native_password_subject"):
        user = get_identity_user(access.user_id, operation=operation)
        assert_domain_resource(domain["id"], user["domain_id"])
        assert_domain_resource(domain["id"], access.user_domain_id)
        if access.project_id:
            raise Unauthorized(message="Password authentication did not return an unscoped subject")
    operation.subjects[access.auth_token] = (access, sess)
    if unscoped_only:
        return _access_info(access, operation=operation)
    projects = list_projects(access.auth_token, domain["id"], operation=operation)
    if project_name:
        matches = [p for p in projects if p["name"] == project_name]
        if len(matches) != 1:
            raise Unauthorized(message="Project is not accessible in the chosen domain")
        target = matches[0]
    else:
        target = next((p for p in projects if p["id"] == user["default_project_id"]), projects[0] if projects else None)
    if target:
        data = validate_token(access.auth_token, target["id"], operation=operation)
    else:
        data = _access_info(access, operation=operation)
    assert_token_context(
        data,
        user_id=access.user_id,
        domain_id=domain["id"],
        identity_domain_id=user["domain_id"],
        project_id=target["id"] if target else "",
        operation=operation,
    )
    if data["default_project_id"] not in {p["id"] for p in projects}:
        data["default_project_id"] = ""
    return data


def validate_token(token: str, project_id: str = "", *, operation=None) -> dict:
    """
    토큰 유효성 검증. 유효하면 토큰 정보 반환, 아니면 예외 발생.
    """
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return validate_token(token, project_id, operation=operation)
    settings = get_settings()

    kwargs = {"auth_url": settings.os_auth_url, "token": token}
    if project_id:
        kwargs["project_id"] = project_id
    else:
        kwargs["unscoped"] = True

    auth_plugin = v3.Token(**kwargs)
    sess = operation.own_session(ks_session.Session(auth=auth_plugin, timeout=30, verify=settings.ssl_verify))
    try:
        with authentication_step("native_session_exchange"):
            access = auth_plugin.get_access(sess)
    except NotFound as exc:
        # TokenNotFound also covers unreadable/expired Fernet tokens. Do not
        # mistake an arbitrary endpoint/proxy 404 for invalid credentials.
        if exc.message.partition(" (HTTP ")[0] in _NATIVE_INVALID_TOKEN_MESSAGES:
            raise Unauthorized(message="Invalid Keystone token", request_id=exc.request_id) from exc
        raise

    operation.subjects[access.auth_token] = (access, sess)
    return _access_info(access, operation=operation)


class ProjectAccessDenied(HTTPException):
    """The login remains valid but the requested project's authority is gone."""

    def __init__(self):
        super().__init__(403, "Native project access was rejected")


def validate_session(token: str, project_id: str = "", *, operation=None) -> dict:
    """Verify/renew caller-owned login proof before deriving any project token.

    A scoped legacy credential is converted before its project authority can be
    changed. Only a rejected login proof is Unauthorized; a rejected project is
    an authorization failure and must not destroy the browser login.
    """
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return validate_session(token, project_id, operation=operation)
    subject = operation.subjects.get(token)
    root = (
        _access_info(subject[0], operation=operation)
        if subject is not None and not subject[0].project_id and not getattr(subject[0], "scoped", False)
        else validate_token(token, operation=operation)
    )
    root_subject = operation.subjects.get(root.get("token"))
    if root_subject is not None and getattr(root_subject[0], "scoped", False):
        raise Unauthorized(message="Native login proof is not unscoped")
    if root.get("project_id") or not root.get("token") or not root.get("user_id"):
        raise Unauthorized(message="Native login proof is not unscoped")
    if not project_id:
        return {**root, "session_token": root["token"]}
    from app.services.domain_projects import assert_project_membership

    try:
        assert_project_membership(root["user_id"], project_id, operation=operation)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise ProjectAccessDenied() from exc
        raise
    try:
        scoped = validate_token(root["token"], project_id, operation=operation)
    except Unauthorized as exc:
        # A concurrent user/native-login revocation must not be downgraded to
        # project denial merely because it reached the scoped exchange first.
        operation.invalidate()
        fresh = validate_session(root["token"], operation=operation)
        if fresh["user_id"] != root["user_id"] or fresh["identity_domain_id"] != root["identity_domain_id"]:
            raise HTTPException(403, "Native login identity changed") from exc
        raise ProjectAccessDenied() from exc
    if (
        scoped.get("user_id") != root["user_id"]
        or scoped.get("identity_domain_id") != root.get("identity_domain_id")
        or scoped.get("project_id") != project_id
    ):
        raise HTTPException(403, "Keystone token subject or project does not match")
    return {**scoped, "session_token": root["token"]}


_OWN_SERVICE_ENDPOINT_FIELDS: dict[str, str] = {
    "waygate": "service_waygate_internal_url",
    "drover": "service_drover_internal_url",
    "lumen": "service_lumen_internal_url",
    "palimpsest": "service_palimpsest_internal_url",
}


class _OwnedWaygateProxy(WaygateProxy):
    def request(self, url, method, *args, **kwargs):
        endpoint = self.endpoint_override or self.get_endpoint()
        if endpoint and endpoint.rstrip("/").endswith("/v1") and url.startswith("/v1/"):
            url = url[3:]
        return super().request(url, method, *args, **kwargs)


def _owned_service_connection_options(settings) -> dict[str, str]:
    """Build OpenStack SDK options for trusted, configured sibling-service endpoints."""
    options: dict[str, str] = {}
    for service_type, field_name in _OWN_SERVICE_ENDPOINT_FIELDS.items():
        endpoint = getattr(settings, field_name, "")
        if not isinstance(endpoint, str) or not (endpoint := endpoint.strip()):
            continue
        options[f"{service_type}_endpoint_override"] = endpoint
    return options


def get_drover_proxy(conn: openstack.connection.Connection) -> DroverProxy:
    """Use the caller's authenticated session without probing version discovery."""
    return DroverProxy(
        session=conn.session,
        service_type="drover",
        interface=conn.config.get_interface("drover"),
        region_name=conn.config.get_region_name("drover"),
        endpoint_override=conn.config.get_endpoint("drover"),
    )


def get_waygate_proxy(conn: openstack.connection.Connection) -> WaygateProxy:
    """Use the same scoped session for root or versioned Waygate endpoints."""
    return _OwnedWaygateProxy(
        session=conn.session,
        service_type="waygate",
        interface=conn.config.get_interface("waygate"),
        region_name=conn.config.get_region_name("waygate"),
        endpoint_override=conn.config.get_endpoint("waygate"),
    )


def get_openstack_connection(
    token: str, project_id: str, *, system_scope: bool = False
) -> openstack.connection.Connection:
    """
    검증된 토큰으로 openstacksdk Connection 객체 반환.
    load_envvars=False 로 OS_* 환경변수를 무시해 v3.Token에 불필요한 인자가
    전달되는 오류를 방지한다.
    """
    import openstack

    settings = get_settings()
    if system_scope and project_id:
        raise ValueError("System scope cannot be combined with a project")
    auth_scope = (
        {"system_scope": "all"}
        if system_scope
        else {"project_id": project_id or None, "unscoped": not bool(project_id)}
    )

    return openstack.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=settings.os_auth_url,
        auth_type="token",
        token=token,
        **auth_scope,
        region_name=settings.os_region_name,
        interface=settings.os_interface,
        api_timeout=30,
        verify=settings.ssl_verify,
        **_owned_service_connection_options(settings),
    )


def get_admin_connection_for_project(project_id: str) -> openstack.connection.Connection:
    """관리자 크리덴셜로 특정 프로젝트에 스코프된 OpenStack 연결 반환.

    콜백 등 사용자 토큰이 없는 상황에서 프로젝트 리소스를 조작할 때 사용.
    """
    import openstack

    settings = get_settings()
    return openstack.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=settings.os_auth_url,
        auth_type="password",
        username=settings.os_username,
        password=settings.os_password,
        project_id=project_id,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
        region_name=settings.os_region_name,
        interface=settings.os_interface,
        api_timeout=30,
        verify=settings.ssl_verify,
        **_owned_service_connection_options(settings),
    )


def get_cloud_shell_project_connection() -> openstack.connection.Connection:
    """Return a service-account connection scoped only to the dedicated shell project.

    Caller tokens are never used for Zun/Cinder lifecycle operations. The project
    scope is deployment configuration, not request input, so tenant data cannot
    redirect service credentials into an arbitrary project.
    """
    import openstack

    settings = get_settings()
    project_id = settings.cloud_shell_service_project_id.strip()
    if not project_id:
        raise RuntimeError("Cloud Shell service project is not configured")
    conn = openstack.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=settings.cloud_shell_auth_url,
        auth_type="password",
        username=settings.os_username,
        password=settings.os_password,
        project_id=project_id,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
        region_name=settings.os_region_name,
        interface=settings.cloud_shell_interface,
        api_timeout=30,
        verify=settings.ssl_verify,
        app_name="afterglow-cloud-shell",
        **_owned_service_connection_options(settings),
    )
    conn._afterglow_project_id = project_id
    return conn


def get_admin_project_connection() -> openstack.connection.Connection:
    """afterglow admin 크리덴셜로 admin 프로젝트에 스코프된 연결.

    Barbican project-quotas 등 admin 프로젝트 스코프가 필요한 cross-project 관리 API에 사용.
    사용자의 현재 프로젝트 선택과 무관하게 항상 admin 프로젝트로 스코프됨.
    """
    import openstack

    settings = get_settings()
    return openstack.connect(
        load_envvars=False,
        load_yaml_config=False,
        auth_url=settings.os_auth_url,
        auth_type="password",
        username=settings.os_username,
        password=settings.os_password,
        project_name=settings.os_project_name,
        user_domain_name=settings.os_user_domain_name,
        project_domain_name=settings.os_project_domain_name,
        region_name=settings.os_region_name,
        interface=settings.os_interface,
        api_timeout=30,
        verify=settings.ssl_verify,
        **_owned_service_connection_options(settings),
    )


def get_service_project_connection() -> openstack.connection.Connection:
    """Union Mount 전용 service 프로젝트로 스코프된 admin 자격 conn.

    os_service_project_id가 미설정이면 RuntimeError로 fail-fast.
    admin 프로젝트로 조용히 fallback하지 않는다.
    """
    settings = get_settings()
    if not settings.os_service_project_id:
        raise RuntimeError(
            "os_service_project_id 설정이 없습니다. "
            "afterglow.conf [openstack] service_project_id 또는 OS_SERVICE_PROJECT_ID 환경변수를 설정하세요."
        )
    return get_admin_connection_for_project(settings.os_service_project_id)


def revoke_token(token: str) -> None:
    """Revoke the exact subject token with authenticated operator authority.

    Password resets may already invalidate the subject credential, so it cannot
    authenticate its own revocation. Never substitute this admin token in a user
    login/session. Authorization and directory failures remain visible to callers.
    """
    from app.services.native_operation import NativeOperation

    with NativeOperation() as operation:
        try:
            operation.ks.tokens.revoke_token(token)
        except NotFound as exc:
            # Exact native TokenNotFound means reset/expiry already invalidated
            # this captured credential. Generic proxy/directory 404 is not proof.
            if exc.message.partition(" (HTTP ")[0] not in _NATIVE_INVALID_TOKEN_MESSAGES:
                raise


def get_user(conn: openstack.connection.Connection, user_id: str) -> dict:
    """user_id로 사용자 상세 정보 조회 (이름, 이메일 등)."""
    u = conn.identity.get_user(user_id)
    return {
        "id": u.id,
        "name": u.name or "",
        "email": getattr(u, "email", None) or "",
    }


def list_user_groups(token: str, user_id: str) -> list[dict]:
    """사용자가 속한 keystone 그룹 목록.

    keystone policy 거부, API 오류, SDK 예외 등 어떤 실패도 PermissionError 로
    변환해 호출부가 graceful 빈 리스트로 응답할 수 있게 한다. 정확한 원인은
    서버 로그(traceback)에 남긴다.
    """
    settings = get_settings()
    auth_plugin = v3.Token(auth_url=settings.os_auth_url, token=token)
    sess = ks_session.Session(auth=auth_plugin, verify=settings.ssl_verify)
    from keystoneclient.v3 import client as ks_client

    ks = ks_client.Client(session=sess, interface=settings.os_interface, region_name=settings.os_region_name)
    try:
        groups = ks.groups.list(user=user_id)
    except Exception as e:
        _logger.exception("list_user_groups 실패 (user_id=%s)", user_id)
        raise PermissionError(str(e)) from e
    return [
        {
            "id": g.id,
            "name": g.name,
            "description": getattr(g, "description", None),
            "domain_id": g.domain_id,
        }
        for g in groups
    ]


def ensure_ec2_credentials(token: str, user_id: str, project_id: str) -> dict:
    """Keystone EC2 credential 자동 발급 + 인메모리 캐시.

    Returns: {"access": str, "secret": str}
    """
    import httpx

    settings = get_settings()
    base = settings.os_auth_url.rstrip("/")
    # /v3/... 형태이면 그대로, 없으면 /v3 붙이기
    if not base.endswith("/v3"):
        base = base

    headers = {"X-Auth-Token": token}
    url = f"{base}/users/{user_id}/credentials/OS-EC2"

    try:
        resp = httpx.get(url, headers=headers, verify=settings.ssl_verify, timeout=15)
        resp.raise_for_status()
        existing = resp.json().get("credentials", [])
    except Exception:
        _logger.warning("EC2 credentials 조회 실패, 신규 발급 시도", exc_info=True)
        existing = []

    cred = next((c for c in existing if c.get("tenant_id") == project_id), None)

    if not cred:
        try:
            post_resp = httpx.post(
                url,
                json={"tenant_id": project_id},
                headers=headers,
                verify=settings.ssl_verify,
                timeout=15,
            )
            post_resp.raise_for_status()
            cred = post_resp.json().get("credential", {})
        except Exception as e:
            _logger.exception("EC2 credential 발급 실패: user=%s project=%s", user_id, project_id)
            raise RuntimeError(f"EC2 credential 발급 실패: {e}") from e

    return {"access": cred["access"], "secret": cred["secret"]}


def list_projects(token: str, domain_id: str | None = None, *, operation=None) -> list[dict]:
    """List native memberships without exchanging an already verified subject again."""
    from keystoneclient.v3 import client as ks_client

    from app.services.domain_scope import domain_context
    from app.services.native_operation import NativeOperation

    if operation is None:
        with NativeOperation() as operation:
            return list_projects(token, domain_id, operation=operation)
    settings = get_settings()
    subject = operation.subjects.get(token)
    if subject is None:
        auth_plugin = v3.Token(auth_url=settings.os_auth_url, token=token, unscoped=True)
        sess = operation.own_session(ks_session.Session(auth=auth_plugin, timeout=30, verify=settings.ssl_verify))
        access = auth_plugin.get_access(sess)
        operation.subjects[token] = (access, sess)
    else:
        access, sess = subject
    ks = ks_client.Client(session=sess, interface=settings.os_interface, region_name=settings.os_region_name)
    user_id = access.user_id
    projects = operation.read(("native_projects", token), lambda: list(ks.projects.list(user=user_id)))
    user = get_identity_user(user_id, operation=operation)
    from app.services.domain_scope import assert_domain_resource

    assert_domain_resource(user["domain_id"], access.user_domain_id)
    selected = domain_id or (access.project_domain_id if access.project_id else user["domain_id"])
    context = domain_context(user_id, selected, operation=operation)
    from app.services.identity_roles import _field

    result = []
    for project in projects:
        if _field(project, "enabled") is not True or _field(project, "domain_id") != context["domain_id"]:
            continue
        if context.get("domain_kind") == "personal":
            from app.services.domain_projects import assert_project_membership

            try:
                assert_project_membership(user_id, _field(project, "id"), operation=operation)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                continue
        result.append(
            {
                "id": _field(project, "id"),
                "name": _field(project, "name"),
                "description": _field(project, "description") or "",
                "domain_id": _field(project, "domain_id"),
                "domain_name": context["domain_name"],
                "enabled": True,
            }
        )
    return result


def list_system_projects(token: str) -> list[dict]:
    """Whole-cloud inventory only from the caller's real system:all admin token.

    Unlike tenant project selection this explicitly exchanges the caller's native
    subject for system scope. Service-account impersonation is never used.
    """
    from fastapi import HTTPException
    from keystoneclient.v3 import client as ks_client

    settings = get_settings()
    auth = v3.Token(auth_url=settings.os_auth_url, token=token, system_scope="all")
    sess = ks_session.Session(auth=auth, timeout=30, verify=settings.ssl_verify)
    access = auth.get_access(sess)
    if access.system_scoped is not True or not access.user_id or not _is_system_admin(access.user_id):
        raise HTTPException(status_code=403, detail="Current system:all administrator authority is required")
    user = get_identity_user(access.user_id)
    from app.services.domain_scope import resolve_domain

    resolve_domain(user["domain_id"])
    ks = ks_client.Client(session=sess, interface=settings.os_interface, region_name=settings.os_region_name)
    from app.services.domain_display import display_name

    domains = {d.id: display_name(d) for d in ks.domains.list()}
    projects = []
    for project in ks.projects.list():
        if not project.id or not project.domain_id or project.domain_id not in domains:
            raise HTTPException(status_code=503, detail="System project domain metadata is unavailable")
        projects.append(
            {
                "id": project.id,
                "name": project.name,
                "description": project.description or "",
                "domain_id": project.domain_id,
                "domain_name": domains[project.domain_id],
                "enabled": project.enabled,
            }
        )
    return projects
