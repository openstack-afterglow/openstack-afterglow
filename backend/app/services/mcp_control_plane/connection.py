"""Create short-lived, exact-grant OpenStack connections for consumer MCP tools."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

from keystoneauth1.exceptions import connection as keystone_connection
from keystoneauth1.identity import v3
from requests import exceptions as requests_exceptions
from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory
from app.models.mcp_authority import McpProjectCredential
from app.services import native_transport
from app.services.mcp_control_plane.authentication import McpPrincipal, lock_principal_grant
from app.services.mcp_control_plane.authority import McpGrantStateError, decrypt_grant_secret, validate_grant_project
from app.services.mcp_control_plane.sdk import run_sdk


class McpConsumerConnectionError(RuntimeError):
    """A grant cannot safely yield an OpenStack connection."""


class McpCredentialInvalidError(McpConsumerConnectionError):
    """Application-credential authentication rejected a saved credential."""


_authenticated_grants: ContextVar[set[str] | None] = ContextVar("mcp_authenticated_grants", default=None)


@contextmanager
def observe_authenticated_grants() -> Iterator[set[str]]:
    """Observe native authentication only within one caller-owned dispatch."""
    grants: set[str] = set()
    token = _authenticated_grants.set(grants)
    try:
        yield grants
    finally:
        _authenticated_grants.reset(token)


def _credential_auth_rejected(exc: BaseException) -> bool:
    """Classify only errors raised by the application-credential auth request."""
    seen: set[int] = set()
    rejected = False
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if isinstance(
            exc,
            (
                ConnectionError,
                TimeoutError,
                keystone_connection.ConnectionError,
                requests_exceptions.ConnectionError,
                requests_exceptions.Timeout,
            ),
        ):
            return False
        status = getattr(exc, "http_status", None) or getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None and status not in {401, 404}:
            return False
        rejected |= status in {401, 404}
        exc = exc.__cause__ or exc.__context__
    return rejected


async def _load_credential(principal: McpPrincipal) -> tuple[str, str]:
    factory = get_session_factory()
    if factory is None:
        raise McpConsumerConnectionError("MCP authority storage is unavailable")
    try:
        async with factory() as session, session.begin():
            grant = await lock_principal_grant(session, principal)
            credential = None
            if principal.project_id != grant.owner_project_id:
                credential = await session.scalar(
                    select(McpProjectCredential)
                    .where(
                        McpProjectCredential.grant_id == grant.id,
                        McpProjectCredential.project_id == principal.project_id,
                    )
                    .with_for_update()
                )
            secret = decrypt_grant_secret(grant, principal.project_id, credential)
            source = credential if credential is not None else grant
            assert source.application_credential_id is not None
            return source.application_credential_id, secret
    except (McpGrantStateError, McpConsumerConnectionError):
        raise
    except Exception as exc:
        raise McpConsumerConnectionError("MCP authority storage is unavailable") from exc


def _prevent_write_replay(session: object) -> None:
    """Keep SDK defaults from replaying an ambiguously accepted native write."""
    from functools import wraps

    from app.services.mcp_control_plane.sdk import check_mutation_dispatch

    original = session.request

    @wraps(original)
    def request(url, method, **kwargs):
        if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
            check_mutation_dispatch()
            # Proxy.request defaults connect_retries=1 even when Connection is
            # configured with zero. Enforce at the actual session boundary.
            kwargs.update(connect_retries=0, status_code_retries=0, allow_reauth=False, redirect=False)
        response = original(url, method, **kwargs)
        if method.upper() not in {"GET", "HEAD", "OPTIONS"} and not 200 <= response.status_code < 300:
            raise McpConsumerConnectionError("MCP native write was not accepted")
        return response

    session.request = request


def _build_connection(application_credential_id: str, application_credential_secret: str, principal: McpPrincipal):
    """Construct without using any manager/admin helper or browser credential."""
    import openstack

    settings = get_settings()
    auth = v3.ApplicationCredential(
        auth_url=settings.os_auth_url,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
    )
    session = native_transport.create_session(auth=auth, timeout=30, verify=settings.ssl_verify)
    try:
        try:
            access = auth.get_access(session)
        except Exception as exc:
            if _credential_auth_rejected(exc):
                raise McpCredentialInvalidError("MCP cloud connection is unavailable") from exc
            raise
        if access.user_id != principal.user_id or access.project_id != principal.project_id:
            raise McpConsumerConnectionError("MCP credential owner/project mismatch")
        identity_domain_id = access.user_domain_id
        domain_id = access.project_domain_id
        if (
            not isinstance(identity_domain_id, str)
            or not identity_domain_id
            or not isinstance(domain_id, str)
            or not domain_id
        ):
            raise McpConsumerConnectionError("MCP credential domain identity is unavailable")
        _prevent_write_replay(session)
        conn = openstack.connection.Connection(
            session=session,
            region_name=settings.os_region_name,
            interface=settings.os_interface,
            app_name="afterglow-consumer-mcp",
        )
    except Exception:
        session.session.close()
        raise
    conn._afterglow_project_id = principal.project_id
    conn._afterglow_user_id = principal.user_id
    conn._afterglow_domain_id = domain_id
    conn._afterglow_identity_domain_id = identity_domain_id
    conn._afterglow_is_system_admin = False
    return conn


async def _validate_current_roles(conn: object, principal: McpPrincipal) -> None:
    """Fence live assignments and the approval snapshot before provider dispatch."""
    from app.services.domain_projects import is_reserved_default_name
    from app.services.project_service import get_project_delegation_roles

    access = await run_sdk(conn.session.auth.get_access, conn.session)
    names, role_ids = list(access.role_names or ()), list(access.role_ids or ())
    if (
        access.user_id != principal.user_id
        or access.project_id != principal.project_id
        or not names
        or len(names) != len(role_ids)
        or len(set(role_ids)) != len(role_ids)
        or any(not isinstance(value, str) or not value for value in [*names, *role_ids])
    ):
        raise McpConsumerConnectionError("MCP credential role identity is unavailable")
    if is_reserved_default_name(getattr(access, "project_name", None)):
        # Pre-migration grants saved the bare project ID as the name, so only the live token can say.
        raise McpConsumerConnectionError("MCP cannot use a domain's Default project")
    current = await get_project_delegation_roles(principal.project_id, principal.user_id)
    live = {role["id"]: role["name"] for role in current}
    if any(live.get(role_id) != name for role_id, name in zip(role_ids, names, strict=True)):
        raise McpConsumerConnectionError("MCP credential roles are no longer delegated")
    factory = get_session_factory()
    if factory is None:
        raise McpConsumerConnectionError("MCP authority storage is unavailable")
    async with factory() as session, session.begin():
        grant = await lock_principal_grant(session, principal)
        approved = validate_grant_project(grant, principal.project_id)
        # Pre-migration singleton grants have no role snapshot. Their existing
        # credential still has to pass the fresh native assignment intersection.
        if grant.approved_projects is not None and not set(names) <= set(approved["roles"]):
            raise McpConsumerConnectionError("MCP credential exceeds approved roles")
        ceiling = getattr(grant, "issued_role_ceiling", None)
        if ceiling is not None and {(role_id, name) for role_id, name in zip(role_ids, names, strict=True)} != {
            (role["id"], role["name"]) for role in ceiling[principal.project_id]
        }:
            raise McpConsumerConnectionError("MCP credential differs from the issued role ceiling")
    # Nova flavor ACL inspection is admin-only. A restricted token can still
    # carry native admin, even though MCP never gains logical system authority.
    conn._afterglow_compute_admin = any(name.lower() == "admin" for name in names)


async def require_native_service_permission(conn: object, project_id: str, service: str, leaf: str) -> None:
    """Evaluate native policy with the exact restricted credential, never a browser fallback."""
    from fastapi import HTTPException

    from app.services.service_permissions import require_service_permission
    from app.services.service_proxy import get_policy_capabilities

    try:
        access = await run_sdk(conn.session.auth.get_access, conn.session)
        if (
            access.project_id != project_id
            or access.user_id != getattr(conn, "_afterglow_user_id", None)
            or project_id != getattr(conn, "_afterglow_project_id", None)
        ):
            raise McpConsumerConnectionError("MCP native policy subject mismatch")
        native = await get_policy_capabilities(
            service,
            {
                "token": access.auth_token,
                "user_id": access.user_id,
                "project_id": project_id,
                "connection_project_id": project_id,
                "is_system_admin": False,
                "_native_access": access,
            },
        )
        require_service_permission({"service_permissions": {service: native["capabilities"]}}, leaf)
    except HTTPException as exc:
        raise McpConsumerConnectionError("MCP native service permission is unavailable") from exc


@asynccontextmanager
async def consumer_connection(principal: McpPrincipal) -> AsyncIterator[object]:
    """Yield one connection and always close it without exposing its secret upstream."""
    application_credential_id, application_credential_secret = await _load_credential(principal)
    try:
        conn = await run_sdk(
            _build_connection,
            application_credential_id,
            application_credential_secret,
            principal,
            cancellation_cleanup=lambda created: created.close(),
        )
    except McpCredentialInvalidError:
        raise
    except Exception as exc:
        raise McpConsumerConnectionError("MCP cloud connection is unavailable") from exc
    try:
        try:
            await _validate_current_roles(conn, principal)
        except McpConsumerConnectionError:
            raise
        except Exception as exc:
            raise McpConsumerConnectionError("MCP current delegation is unavailable") from exc
        if (observed := _authenticated_grants.get()) is not None:
            observed.add(principal.grant_id)
        yield conn
    finally:
        await run_sdk(conn.close, allow_after_cancel=True)
