"""Create short-lived, exact-grant OpenStack connections for consumer MCP tools."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from keystoneauth1 import session as ks_session
from keystoneauth1.identity import v3

from app.config import get_settings
from app.database import get_session_factory
from app.models.mcp_authority import McpLumenSelection
from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.authority import McpGrantStateError, _lock_grant, decrypt_grant_secret, lock_owner


class McpConsumerConnectionError(RuntimeError):
    """A grant cannot safely yield an OpenStack connection."""


async def _load_credential(principal: McpPrincipal) -> tuple[str, str]:
    factory = get_session_factory()
    if factory is None:
        raise McpConsumerConnectionError("MCP authority storage is unavailable")
    try:
        async with factory() as session, session.begin():
            owner_lock = await lock_owner(
                session, owner_user_id=principal.user_id, owner_project_id=principal.project_id
            )
            if getattr(principal, "source", None) == "lumen":
                selection = await session.get(
                    McpLumenSelection,
                    {"owner_user_id": principal.user_id, "owner_project_id": principal.project_id},
                    with_for_update=True,
                )
                if (
                    selection is None
                    or selection.grant_id != principal.grant_id
                    or principal.selection_generation != owner_lock.lumen_selection_generation
                ):
                    raise McpConsumerConnectionError("Lumen MCP selection changed before cloud dispatch")
            grant = await _lock_grant(
                session,
                grant_id=principal.grant_id,
                owner_user_id=principal.user_id,
                owner_project_id=principal.project_id,
            )
            if grant.credential_epoch != principal.credential_epoch:
                raise McpConsumerConnectionError("MCP grant changed before cloud dispatch")
            secret = decrypt_grant_secret(grant)
            assert grant.application_credential_id is not None
            return grant.application_credential_id, secret
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
    conn._afterglow_is_system_admin = False
    return conn


@asynccontextmanager
async def consumer_connection(principal: McpPrincipal) -> AsyncIterator[object]:
    """Yield one connection and always close it without exposing its secret upstream."""
    application_credential_id, application_credential_secret = await _load_credential(principal)
    try:
        conn = await asyncio.to_thread(
            _build_connection,
            application_credential_id,
            application_credential_secret,
            principal,
        )
    except Exception as exc:
        raise McpConsumerConnectionError("MCP cloud connection is unavailable") from exc
    try:
        yield conn
    finally:
        await asyncio.to_thread(conn.close)
