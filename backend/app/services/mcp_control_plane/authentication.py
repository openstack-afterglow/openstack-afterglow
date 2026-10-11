"""Verified inbound MCP principals; browser and chat API tokens are never accepted."""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import get_session_factory
from app.models.mcp_authority import McpLumenSelection, McpPersonalToken
from app.services.mcp_control_plane.authority import (
    McpAuthorityError,
    McpGrantNotFoundError,
    McpGrantStateError,
    _lock_grant,
    default_grant_project,
    grant_is_expired,
    grant_scopes,
    lock_owner,
    resolve_personal_token,
    validate_grant_project,
    validate_lumen_grant,
)
from app.services.mcp_control_plane.oauth import McpOAuthUrls
from app.services.mcp_control_plane.oauth_authority import McpOAuthAuthorityError, resolve_oauth_access_token


class McpAuthenticationError(RuntimeError):
    """Authentication failed without exposing grant or credential state."""


@dataclass(frozen=True)
class McpPrincipal:
    grant_id: str
    user_id: str
    project_id: str
    credential_epoch: int
    scopes: frozenset[str]
    source: str
    selection_generation: int | None = None
    owner_project_id: str | None = None
    selection_project_id: str | None = None

    @property
    def anchor_project_id(self) -> str:
        return self.owner_project_id or self.project_id

    @property
    def can_write(self) -> bool:
        return "mcp:write" in self.scopes


def _factory() -> async_sessionmaker:
    factory = get_session_factory()
    if factory is None:
        raise McpAuthenticationError("MCP authority storage is unavailable")
    return factory


async def lock_principal_grant(session, principal: McpPrincipal, *, write: bool = False):
    """Fence saved authority before any target dispatch or secret loading."""
    owner_lock = await lock_owner(
        session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id
    )
    if principal.source == "lumen":
        selection_project = principal.selection_project_id or principal.anchor_project_id
        if selection_project != principal.anchor_project_id:
            owner_lock = await lock_owner(session, owner_user_id=principal.user_id, owner_project_id=selection_project)
        selection = await session.get(
            McpLumenSelection,
            {"owner_user_id": principal.user_id, "owner_project_id": selection_project},
            with_for_update=True,
        )
        if (
            selection is None
            or selection.grant_id != principal.grant_id
            or principal.selection_generation is None
            or principal.selection_generation != owner_lock.lumen_selection_generation
        ):
            raise McpAuthenticationError("Lumen MCP selection changed before dispatch")
    grant = await _lock_grant(
        session,
        grant_id=principal.grant_id,
        owner_user_id=principal.user_id,
        owner_project_id=principal.anchor_project_id,
    )
    if (
        grant.status != "active"
        or grant_is_expired(grant)
        or grant.credential_epoch != principal.credential_epoch
        or "mcp:read" not in principal.scopes
        or (write and not principal.can_write)
    ):
        raise McpAuthenticationError("MCP grant changed before dispatch")
    if (
        principal.source not in {"personal_token", "oauth", "lumen"}
        or (principal.source == "lumen" and grant.source not in {"personal_token", "lumen"})
        or (principal.source != "lumen" and principal.source != grant.source)
    ):
        raise McpAuthenticationError("MCP grant source changed before dispatch")
    try:
        validate_lumen_grant(grant, principal.project_id)
        if principal.source == "lumen":
            validate_lumen_grant(grant, principal.selection_project_id or principal.anchor_project_id)
    except McpGrantStateError as exc:
        raise McpAuthenticationError("Lumen MCP consent is unavailable before dispatch") from exc
    if grant.source == "personal_token":
        token = await session.scalar(
            select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id).with_for_update()
        )
        if token is None or token.revoked_at is not None:
            raise McpAuthenticationError("MCP personal token is no longer active")
    validate_grant_project(grant, principal.project_id, write=write)
    return grant


async def resolve_principal_target(
    principal: McpPrincipal, project_id: str | None = None, *, write: bool = False
) -> McpPrincipal:
    target = principal.project_id if project_id is None else project_id
    resolved = replace(principal, project_id=target, owner_project_id=principal.anchor_project_id)
    async with _factory()() as session, session.begin():
        await lock_principal_grant(session, resolved, write=write)
    return resolved


async def verify_mcp_bearer(raw_token: str, *, urls: McpOAuthUrls) -> McpPrincipal:
    """Accept exactly Afterglow PATs and exact-audience OAuth access tokens."""
    if not isinstance(raw_token, str) or not raw_token or raw_token.startswith(("sk-afgl-", "Bearer ")):
        raise McpAuthenticationError("MCP bearer token is invalid")
    try:
        async with _factory()() as session, session.begin():
            if raw_token.startswith("mcp-afgl-"):
                grant = await resolve_personal_token(session, raw_token)
                scopes = frozenset(grant_scopes(grant.access_level))
                source = "personal_token"
            else:
                grant, oauth_scopes = await resolve_oauth_access_token(
                    session, raw_token=raw_token, resource=urls.resource
                )
                scopes = frozenset(oauth_scopes)
                source = "oauth"
    except (McpAuthorityError, McpGrantNotFoundError, McpOAuthAuthorityError) as exc:
        raise McpAuthenticationError("MCP bearer token is invalid") from exc
    return McpPrincipal(
        grant_id=str(grant.id),
        user_id=grant.owner_user_id,
        project_id=default_grant_project(grant),
        owner_project_id=grant.owner_project_id,
        credential_epoch=grant.credential_epoch,
        scopes=scopes,
        source=source,
    )
