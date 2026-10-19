"""Create short-lived, exact-grant OpenStack connections for consumer MCP tools."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3
from sqlalchemy import select

from app.config import get_settings
from app.database import get_session_factory
from app.models.mcp_authority import McpProjectCredential
from app.services.mcp_control_plane.authentication import McpPrincipal, lock_principal_grant
from app.services.mcp_control_plane.authority import McpGrantStateError, decrypt_grant_secret
from app.services.mcp_control_plane.sdk import run_sdk


class McpConsumerConnectionError(RuntimeError):
    """A grant cannot safely yield an OpenStack connection."""


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


def _build_connection(application_credential_id: str, application_credential_secret: str, principal: McpPrincipal):
    """Construct without using any manager/admin helper or browser credential."""
    import openstack

    settings = get_settings()
    auth = v3.ApplicationCredential(
        auth_url=settings.os_auth_url,
        application_credential_id=application_credential_id,
        application_credential_secret=application_credential_secret,
    )
    session = ks_session.Session(auth=auth, timeout=30, verify=settings.ssl_verify)
    try:
        access = auth.get_access(session)
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
    except Exception as exc:
        raise McpConsumerConnectionError("MCP cloud connection is unavailable") from exc
    try:
        yield conn
    finally:
        await run_sdk(conn.close, allow_after_cancel=True)
