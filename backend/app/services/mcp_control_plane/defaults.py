"""Lazy, read-only Lumen cloud authority created through the logged-in caller.

No personal bearer is minted. A durable reservation precedes Keystone I/O; an
ambiguous creation remains nondispatchable until same-owner orphan recovery.
The owner lock serializes creation and preserves explicit personal selections.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy import select

from app.database import get_session_factory
from app.models.mcp_authority import McpDelegatedGrant, McpLumenSelection, McpPersonalToken
from app.services.mcp_control_plane import authority, lumen


def _factory():
    factory = get_session_factory()
    if factory is None:
        raise authority.McpAuthorityError("Lumen cloud authority storage is unavailable")
    return factory


async def _selected(session, *, owner_lock, user_id: str, project_id: str):
    selection = await session.get(
        McpLumenSelection,
        {"owner_user_id": user_id, "owner_project_id": project_id},
        with_for_update=True,
    )
    if selection is None:
        return None, None
    grant = await authority._lock_grant(
        session, grant_id=selection.grant_id, owner_user_id=user_id, owner_project_id=project_id
    )
    token = None
    if grant.source == "personal_token":
        token = await session.scalar(
            select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id).with_for_update()
        )
    try:
        snapshot = lumen._validate_selected_row(
            selection=selection,
            grant=grant,
            token=token,
            owner_lock=owner_lock,
            user_id=user_id,
            project_id=project_id,
        )
    except lumen.McpLumenAuthorityError:
        return selection, None
    return selection, snapshot


def _select(session, *, selection, owner_lock, grant, user_id: str, project_id: str) -> None:
    if selection is None:
        session.add(McpLumenSelection(owner_user_id=user_id, owner_project_id=project_id, grant_id=grant.id))
    else:
        selection.grant_id = grant.id
        selection.updated_at = authority._now()
    owner_lock.lumen_selection_generation += 1


async def ensure_default_lumen_grant(*, conn: Any, token_info: dict) -> None:
    """Ensure current-project cloud reads; never replace a valid explicit selection."""
    user_id, project_id = token_info["user_id"], token_info["project_id"]
    if (
        getattr(conn, "_afterglow_user_id", None) != user_id
        or getattr(conn, "_afterglow_project_id", None) != project_id
        or token_info.get("connection_project_id", project_id) != project_id
    ):
        # Logical system-admin project overrides are not project delegations.
        raise authority.McpAuthorityError("Lumen cloud tools require the caller's exact project scope")
    factory = _factory()
    username = token_info.get("username", user_id)
    await authority.recover_stale_pending_orphans(
        factory, conn=conn, owner_user_id=user_id, owner_project_id=project_id, username=username
    )
    now = authority._now()
    grant_id = str(uuid4())
    deadline = now + authority.default_grant_lifetime()
    upstream_name = f"afterglow-mcp-{grant_id}"
    async with factory() as session, session.begin():
        owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
        selection, snapshot = await _selected(session, owner_lock=owner_lock, user_id=user_id, project_id=project_id)
        if snapshot is not None:
            return
        internal = (
            await session.scalars(
                select(McpDelegatedGrant)
                .where(
                    McpDelegatedGrant.owner_user_id == user_id,
                    McpDelegatedGrant.owner_project_id == project_id,
                    McpDelegatedGrant.source == "lumen",
                    (McpDelegatedGrant.status.in_(("active", "pending"))) | McpDelegatedGrant.cleanup_pending.is_(True),
                )
                .order_by(McpDelegatedGrant.created_at)
                .with_for_update()
            )
        ).all()
        for grant in internal:
            if grant.status == "pending" or (
                grant.cleanup_pending
                and grant.application_credential_id is None
                and grant.orphan_recovery_after is not None
                and authority._as_utc(grant.orphan_recovery_after) > now
            ):
                raise authority.McpGrantStateError("Lumen cloud authority is still being prepared")
            if grant.status != "active":
                continue
            if authority._as_utc(grant.expires_at) <= now:
                grant.status = "expired"
                grant.credential_epoch += 1
                grant.cleanup_pending = True
                continue
            if not grant.application_credential_id or not grant.credential_ciphertext or grant.access_level != "read":
                raise authority.McpGrantStateError("Lumen cloud authority is unavailable")
            _select(
                session,
                selection=selection,
                owner_lock=owner_lock,
                grant=grant,
                user_id=user_id,
                project_id=project_id,
            )
            return
        if (
            await authority._count_dispatchable_grants(session, owner_user_id=user_id, owner_project_id=project_id)
            >= authority.get_settings().mcp_max_delegated_grants
        ):
            raise authority.McpGrantLimitError("The project has the maximum number of active MCP grants")
        project = authority.ApprovedProject(
            id=project_id,
            name=token_info.get("project_name") or project_id,
            roles=authority._role_snapshot(token_info.get("roles", [])),
            can_write=False,
            conn=conn,
            owns_connection=False,
        )
        session.add(
            McpDelegatedGrant(
                id=grant_id,
                owner_user_id=user_id,
                owner_project_id=project_id,
                upstream_credential_name=upstream_name,
                display_name="Lumen cloud tools",
                source="lumen",
                access_level="read",
                status="pending",
                expires_at=deadline,
                approved_projects=[project.metadata()],
                cleanup_pending=True,
                orphan_recovery_after=now + authority.PENDING_ORPHAN_RECOVERY_GRACE,
            )
        )

    try:
        await authority.create_grant_credentials(
            factory,
            grant_id=grant_id,
            owner_user_id=user_id,
            owner_project_id=project_id,
            username=username,
            projects=[project],
            expires_at=deadline,
        )
    except Exception as exc:
        raise authority.McpAuthorityError("Lumen cloud delegation could not be created") from exc

    changed = False
    async with factory() as session, session.begin():
        owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
        grant = await authority._lock_grant(
            session, grant_id=grant_id, owner_user_id=user_id, owner_project_id=project_id
        )
        if grant.status != "pending" or grant.orphan_recovery_nonce is not None:
            if grant.status == "pending":
                grant.status = "revoked"
                grant.revoked_at = authority._now()
                grant.credential_epoch += 1
            grant.cleanup_pending = True
            changed = True
        else:
            grant.status = "active"
            grant.issued_at = now
            grant.cleanup_pending = False
            grant.orphan_recovery_after = None
            grant.orphan_recovery_nonce = None
            selection, snapshot = await _selected(
                session, owner_lock=owner_lock, user_id=user_id, project_id=project_id
            )
            if snapshot is None:
                _select(
                    session,
                    selection=selection,
                    owner_lock=owner_lock,
                    grant=grant,
                    user_id=user_id,
                    project_id=project_id,
                )
            authority._audit(
                session,
                owner_user_id=user_id,
                owner_project_id=project_id,
                username=username,
                action="mcp_grant.create",
                grant=grant,
                extra={"source": "lumen", "access_level": "read", "credential_epoch": grant.credential_epoch},
            )
    if changed:
        await authority.abandon_grant_credentials(
            factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=user_id,
            owner_project_id=project_id,
            username=username,
        )
        raise authority.McpGrantStateError("Lumen cloud authority changed before activation")
