"""Explicit, current-project Lumen cloud consent through the logged-in caller.

No personal bearer is minted. Durable pending reservations precede Keystone I/O;
owner generations fence later selection/disable actions, and ambiguous creations
remain nondispatchable until same-owner orphan recovery confirms their absence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database import get_session_factory
from app.models.activity import ActivityLog
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


def _require_exact_scope(token_info: dict) -> tuple[str, str]:
    user_id, project_id = token_info["user_id"], token_info["project_id"]
    if token_info.get("connection_project_id", project_id) != project_id:
        # Logical system-admin overrides are not actual project delegations.
        raise authority.McpAuthorityError("Lumen cloud tools require the caller's exact project scope")
    return user_id, project_id


def _current_project(
    projects: list[authority.ApprovedProject], *, user_id: str, project_id: str, access_level: str
) -> authority.ApprovedProject:
    if len(projects) != 1 or projects[0].id != project_id:
        raise authority.McpAuthorityError("Lumen cloud tools require the caller's exact project scope")
    project = projects[0]
    if (
        getattr(project.conn, "_afterglow_user_id", None) != user_id
        or getattr(project.conn, "_afterglow_project_id", None) != project_id
    ):
        raise authority.McpAuthorityError("Lumen cloud tools require the caller's exact project scope")
    if access_level == "manage" and not project.can_write:
        raise authority.McpGrantPrivilegeError("selected project does not allow management")
    return project


async def _internal_grants(session: AsyncSession, *, user_id: str, project_id: str) -> list[McpDelegatedGrant]:
    return (
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


def _retire(
    session: AsyncSession,
    grant: McpDelegatedGrant,
    *,
    user_id: str,
    project_id: str,
    username: str,
    now: datetime,
) -> None:
    if grant.status not in {"revoked", "expired"}:
        grant.status = "expired" if authority.grant_is_expired(grant, now=now) else "revoked"
        grant.revoked_at = now if grant.status == "revoked" else grant.revoked_at
        grant.credential_epoch += 1
    grant.cleanup_pending = True
    authority._audit(
        session,
        owner_user_id=user_id,
        owner_project_id=project_id,
        username=username,
        action="mcp_grant.revoke",
        grant=grant,
        extra={"source": "lumen", "credential_epoch": grant.credential_epoch},
    )


async def _cleanup(
    factory: async_sessionmaker[AsyncSession],
    *,
    conn: Any,
    grant_ids: list[str],
    user_id: str,
    project_id: str,
    username: str,
) -> None:
    for grant_id in grant_ids:
        await authority.confirm_keystone_cleanup(
            factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=user_id,
            owner_project_id=project_id,
            username=username,
            application_credential_id=None,
        )


async def approve_lumen_grant(*, token_info: dict, access_level: str) -> None:
    """Explicitly approve current-project authority; never run during chat or discovery."""
    access_level = authority._validate_access_level(access_level)
    user_id, project_id = _require_exact_scope(token_info)
    factory = _factory()
    username = token_info.get("username", user_id)
    # Consent is ordered before remote role preparation/recovery too: a later
    # clear or selection must win even before a pending grant can be reserved.
    async with factory() as session, session.begin():
        owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
        requested_generation = owner_lock.lumen_selection_generation
    projects = await authority.prepare_project_authority(token_info, project_scope="current", access_level=access_level)
    grant_id = str(uuid4())
    credentials_ready = False
    try:
        project = _current_project(projects, user_id=user_id, project_id=project_id, access_level=access_level)
        await authority.recover_stale_pending_orphans(
            factory, conn=project.conn, owner_user_id=user_id, owner_project_id=project_id, username=username
        )
        now = authority._now()
        deadline = now + authority.default_grant_lifetime()
        async with factory() as session, session.begin():
            owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
            if owner_lock.lumen_selection_generation != requested_generation:
                raise authority.McpGrantStateError("Lumen cloud authority changed before activation")
            _, snapshot = await _selected(session, owner_lock=owner_lock, user_id=user_id, project_id=project_id)
            internal = await _internal_grants(session, user_id=user_id, project_id=project_id)
            for grant in internal:
                if grant.status == "pending" or (
                    grant.cleanup_pending
                    and grant.application_credential_id is None
                    and grant.orphan_recovery_after is not None
                    and authority._as_utc(grant.orphan_recovery_after) > now
                ):
                    raise authority.McpGrantStateError("Lumen cloud authority is still being prepared")
            for grant in internal:
                if (
                    snapshot is not None
                    and snapshot.grant_id == grant.id
                    and grant.consented_at is not None
                    and grant.access_level == access_level
                    and not grant.cleanup_pending
                    and grant.application_credential_id
                    and grant.credential_ciphertext
                ):
                    return
                if grant.status == "active" and authority.grant_is_expired(grant, now=now):
                    _retire(session, grant, user_id=user_id, project_id=project_id, username=username, now=now)
            if (
                await authority._count_dispatchable_grants(session, owner_user_id=user_id, owner_project_id=project_id)
                >= authority.get_settings().mcp_max_delegated_grants
            ):
                raise authority.McpGrantLimitError("The project has the maximum number of active MCP grants")
            generation = owner_lock.lumen_selection_generation
            session.add(
                McpDelegatedGrant(
                    id=grant_id,
                    owner_user_id=user_id,
                    owner_project_id=project_id,
                    upstream_credential_name=f"afterglow-mcp-{grant_id}",
                    display_name="Lumen cloud tools",
                    source="lumen",
                    access_level=access_level,
                    project_scope="current",
                    status="pending",
                    expires_at=deadline,
                    consented_at=now,
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
                projects=projects,
                expires_at=deadline,
            )
        except authority.McpGrantStateError:
            raise
        except Exception as exc:
            raise authority.McpAuthorityError("Lumen cloud delegation could not be created") from exc
        credentials_ready = True
        cleanup_ids = []
        async with factory() as session, session.begin():
            owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
            grant = await authority._lock_grant(
                session, grant_id=grant_id, owner_user_id=user_id, owner_project_id=project_id
            )
            if (
                owner_lock.lumen_selection_generation != generation
                or grant.status != "pending"
                or grant.orphan_recovery_nonce is not None
                or grant.consented_at is None
                or authority.grant_is_expired(grant)
                or not grant.application_credential_id
                or not grant.credential_ciphertext
            ):
                raise authority.McpGrantStateError("Lumen cloud authority changed before activation")
            for previous in await _internal_grants(session, user_id=user_id, project_id=project_id):
                if previous.id != grant_id:
                    _retire(
                        session,
                        previous,
                        user_id=user_id,
                        project_id=project_id,
                        username=username,
                        now=authority._now(),
                    )
                    cleanup_ids.append(previous.id)
            grant.status = "active"
            grant.issued_at = authority._now()
            grant.cleanup_pending = False
            grant.orphan_recovery_after = None
            selection = await session.get(
                McpLumenSelection,
                {"owner_user_id": user_id, "owner_project_id": project_id},
                with_for_update=True,
            )
            _select(
                session, selection=selection, owner_lock=owner_lock, grant=grant, user_id=user_id, project_id=project_id
            )
            authority._audit(
                session,
                owner_user_id=user_id,
                owner_project_id=project_id,
                username=username,
                action="mcp_grant.create",
                grant=grant,
                extra={"source": "lumen", "access_level": access_level, "credential_epoch": grant.credential_epoch},
            )
        # Activation committed: later cleanup failure must not undo current consent.
        credentials_ready = False
        await _cleanup(
            factory, conn=project.conn, grant_ids=cleanup_ids, user_id=user_id, project_id=project_id, username=username
        )
    except BaseException:
        if credentials_ready:
            await authority.abandon_grant_credentials(
                factory,
                conn=projects[0].conn,
                grant_id=grant_id,
                owner_user_id=user_id,
                owner_project_id=project_id,
                username=username,
            )
        raise
    finally:
        await authority.close_project_authority(projects)


async def disable_lumen_grant(*, token_info: dict) -> None:
    """Fence local authority before cleanup, including an approval still in flight."""
    user_id, project_id = _require_exact_scope(token_info)
    factory = _factory()
    username = token_info.get("username", user_id)
    cleanup_ids = []
    async with factory() as session, session.begin():
        owner_lock = await authority.lock_owner(session, owner_user_id=user_id, owner_project_id=project_id)
        selection = await session.get(
            McpLumenSelection,
            {"owner_user_id": user_id, "owner_project_id": project_id},
            with_for_update=True,
        )
        if selection is not None:
            await session.delete(selection)
        owner_lock.lumen_selection_generation += 1
        for grant in await _internal_grants(session, user_id=user_id, project_id=project_id):
            _retire(session, grant, user_id=user_id, project_id=project_id, username=username, now=authority._now())
            cleanup_ids.append(grant.id)
        session.add(
            ActivityLog(
                project_id=project_id,
                user_id=user_id,
                username=username,
                resource_type="mcp_lumen_selection",
                resource_id=None,
                resource_name=None,
                action="mcp_lumen_selection.clear",
                status="success",
                extra={"generation": owner_lock.lumen_selection_generation, "grant_id": None},
            )
        )
    if not cleanup_ids:
        return
    projects = await authority.prepare_project_authority(token_info, project_scope="current", access_level="read")
    try:
        project = _current_project(projects, user_id=user_id, project_id=project_id, access_level="read")
        await _cleanup(
            factory, conn=project.conn, grant_ids=cleanup_ids, user_id=user_id, project_id=project_id, username=username
        )
    finally:
        await authority.close_project_authority(projects)
