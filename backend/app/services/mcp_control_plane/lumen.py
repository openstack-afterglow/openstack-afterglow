"""Resolve Lumen's selected delegated grant without exposing its credential.

A Lumen binding freezes this snapshot in its server-only closure.  Each execution
re-reads the owner lock, selection, personal token, and grant so switching or
revoking a selection invalidates a paused durable run before any cloud call.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.database import get_session_factory
from app.models.mcp_authority import McpDelegatedGrant, McpLumenSelection, McpOwnerLock, McpPersonalToken
from app.services.mcp_control_plane.authentication import McpPrincipal
from app.services.mcp_control_plane.authority import (
    McpGrantStateError,
    _as_utc,
    approved_project_metadata,
    default_grant_project,
    grant_is_expired,
    grant_scopes,
    validate_grant_project,
    validate_lumen_grant,
)


class McpLumenAuthorityError(RuntimeError):
    """No currently dispatchable delegated grant is selected for this chat scope."""


@dataclass(frozen=True)
class LumenGrantSnapshot:
    grant_id: str
    user_id: str
    project_id: str
    credential_epoch: int
    selection_generation: int


def snapshot_payload(snapshot: LumenGrantSnapshot) -> dict[str, object]:
    """Serialize only opaque grant state for the encrypted durable run payload."""
    return {
        "grant_id": snapshot.grant_id,
        "user_id": snapshot.user_id,
        "project_id": snapshot.project_id,
        "credential_epoch": snapshot.credential_epoch,
        "selection_generation": snapshot.selection_generation,
    }


def frozen_snapshot(value: object) -> LumenGrantSnapshot | None:
    """Parse a server-authored frozen run snapshot, rejecting malformed payloads."""
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {
        "grant_id",
        "user_id",
        "project_id",
        "credential_epoch",
        "selection_generation",
    }:
        raise McpLumenAuthorityError("Lumen delegated MCP snapshot is invalid")
    grant_id = value["grant_id"]
    user_id = value["user_id"]
    project_id = value["project_id"]
    credential_epoch = value["credential_epoch"]
    selection_generation = value["selection_generation"]
    if (
        not all(isinstance(item, str) and item for item in (grant_id, user_id, project_id))
        or type(credential_epoch) is not int
        or credential_epoch < 1
        or type(selection_generation) is not int
        or selection_generation < 0
    ):
        raise McpLumenAuthorityError("Lumen delegated MCP snapshot is invalid")
    return LumenGrantSnapshot(
        grant_id=grant_id,
        user_id=user_id,
        project_id=project_id,
        credential_epoch=credential_epoch,
        selection_generation=selection_generation,
    )


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise McpLumenAuthorityError("Lumen MCP authority storage is unavailable")
    return factory


def _validate_selected_row(
    *,
    selection: McpLumenSelection | None,
    grant: McpDelegatedGrant | None,
    token: McpPersonalToken | None,
    owner_lock: McpOwnerLock | None,
    user_id: str,
    project_id: str,
) -> LumenGrantSnapshot:
    if (
        selection is None
        or grant is None
        or owner_lock is None
        or selection.grant_id != grant.id
        or grant.owner_user_id != user_id
        or grant.status != "active"
        or grant.source not in {"personal_token", "lumen"}
        or (
            grant.source == "personal_token"
            and (token is None or token.grant_id != grant.id or token.revoked_at is not None)
        )
        or grant_is_expired(grant)
    ):
        raise McpLumenAuthorityError("Lumen has no active delegated MCP grant")
    try:
        validate_lumen_grant(grant, project_id)
        validate_grant_project(grant, default_grant_project(grant))
    except McpGrantStateError as exc:
        raise McpLumenAuthorityError("Lumen delegated MCP scope is unavailable") from exc
    return LumenGrantSnapshot(
        grant_id=str(grant.id),
        user_id=user_id,
        project_id=project_id,
        credential_epoch=grant.credential_epoch,
        selection_generation=owner_lock.lumen_selection_generation,
    )


async def selected_lumen_snapshot(*, user_id: str, project_id: str) -> LumenGrantSnapshot | None:
    """Return the current selected grant snapshot, or no Lumen cloud bindings."""
    if not user_id or not project_id:
        return None
    try:
        async with _factory()() as session:
            row = (
                await session.execute(
                    select(McpLumenSelection, McpDelegatedGrant, McpPersonalToken, McpOwnerLock)
                    .join(McpDelegatedGrant, McpDelegatedGrant.id == McpLumenSelection.grant_id)
                    .outerjoin(McpPersonalToken, McpPersonalToken.grant_id == McpDelegatedGrant.id)
                    .join(
                        McpOwnerLock,
                        (McpOwnerLock.owner_user_id == McpLumenSelection.owner_user_id)
                        & (McpOwnerLock.owner_project_id == McpLumenSelection.owner_project_id),
                    )
                    .where(
                        McpLumenSelection.owner_user_id == user_id,
                        McpLumenSelection.owner_project_id == project_id,
                    )
                )
            ).one_or_none()
    except McpLumenAuthorityError:
        raise
    except Exception as exc:
        raise McpLumenAuthorityError("Lumen MCP authority storage is unavailable") from exc
    if row is None:
        return None
    selection, grant, token, owner_lock = row
    try:
        return _validate_selected_row(
            selection=selection,
            grant=grant,
            token=token,
            owner_lock=owner_lock,
            user_id=user_id,
            project_id=project_id,
        )
    except McpLumenAuthorityError:
        return None


async def _resolve_snapshot_grant(snapshot: LumenGrantSnapshot) -> tuple[McpDelegatedGrant, LumenGrantSnapshot]:
    """Load one selected grant and reject stale persisted snapshot authority."""
    try:
        async with _factory()() as session:
            row = (
                await session.execute(
                    select(McpLumenSelection, McpDelegatedGrant, McpPersonalToken, McpOwnerLock)
                    .join(McpDelegatedGrant, McpDelegatedGrant.id == McpLumenSelection.grant_id)
                    .outerjoin(McpPersonalToken, McpPersonalToken.grant_id == McpDelegatedGrant.id)
                    .join(
                        McpOwnerLock,
                        (McpOwnerLock.owner_user_id == McpLumenSelection.owner_user_id)
                        & (McpOwnerLock.owner_project_id == McpLumenSelection.owner_project_id),
                    )
                    .where(
                        McpLumenSelection.owner_user_id == snapshot.user_id,
                        McpLumenSelection.owner_project_id == snapshot.project_id,
                    )
                )
            ).one_or_none()
    except Exception as exc:
        raise McpLumenAuthorityError("Lumen MCP authority storage is unavailable") from exc
    if row is None:
        raise McpLumenAuthorityError("Lumen delegated MCP selection changed")
    selection, grant, token, owner_lock = row
    current = _validate_selected_row(
        selection=selection,
        grant=grant,
        token=token,
        owner_lock=owner_lock,
        user_id=snapshot.user_id,
        project_id=snapshot.project_id,
    )
    if current != snapshot:
        raise McpLumenAuthorityError("Lumen delegated MCP selection changed")
    return grant, current


async def selected_lumen_metadata(snapshot: LumenGrantSnapshot) -> dict[str, object]:
    """Public-safe saved selection metadata for authenticated cloud-tool discovery."""
    grant, _ = await _resolve_snapshot_grant(snapshot)
    projects = approved_project_metadata(grant)
    project_id = default_grant_project(grant)
    project = next(item for item in projects if item["id"] == project_id)
    return {
        "access_level": grant.access_level,
        "project_id": project_id,
        "project_name": project["name"],
        "source": grant.source,
        "allowed_projects": projects,
        "selection_name": None if grant.source == "lumen" else grant.display_name,
        "expires_at": _as_utc(grant.expires_at).isoformat() if grant.expires_at is not None else None,
    }


async def resolve_lumen_principal(snapshot: LumenGrantSnapshot) -> McpPrincipal:
    """Revalidate an opaque snapshot immediately before registry execution."""
    grant, current = await _resolve_snapshot_grant(snapshot)
    try:
        scopes = frozenset(grant_scopes(grant.access_level))
    except McpGrantStateError as exc:
        raise McpLumenAuthorityError("Lumen delegated MCP grant is unavailable") from exc
    return McpPrincipal(
        grant_id=current.grant_id,
        user_id=current.user_id,
        project_id=default_grant_project(grant),
        owner_project_id=grant.owner_project_id,
        selection_project_id=current.project_id,
        credential_epoch=current.credential_epoch,
        scopes=scopes,
        source="lumen",
        selection_generation=current.selection_generation,
    )
