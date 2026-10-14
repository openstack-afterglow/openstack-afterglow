"""Project-bound personal-token delegated authority.

Only this module creates, decrypts, or revokes server-held Keystone application
credentials.  Callers supply a connection already scoped to the exact owner
and project; no manager or administrator connection is ever used here.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from keystoneclient.utils import isotime
from sqlalchemy import func, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.models.activity import ActivityLog
from app.models.mcp_authority import (
    McpDelegatedGrant,
    McpLumenSelection,
    McpOwnerLock,
    McpPersonalToken,
    McpProjectCredential,
    McpToolInvocation,
)
from app.services.mcp_control_plane.clients import public_client_observations
from app.services.mcp_control_plane.crypto import decrypt_application_credential, encrypt_application_credential
from app.services.mcp_control_plane.sdk import _drain

PERSONAL_TOKEN_PREFIX = "mcp-afgl-"
PERSONAL_TOKEN_BYTES = 32
DEFAULT_GRANT_LIFETIME = timedelta(days=30)
MAX_GRANT_LIFETIME = timedelta(days=90)
MAX_PERSONAL_TOKEN_LIFETIME = timedelta(days=366)
MAX_ACTIVE_PERSONAL_TOKENS = 10
MAX_ACTIVE_GRANTS = 20
PENDING_ORPHAN_RECOVERY_GRACE = timedelta(minutes=15)


class McpAuthorityError(RuntimeError):
    """Safe domain error; API adapters decide its transport representation."""


class McpGrantPrivilegeError(McpAuthorityError):
    """The requested delegated access exceeds the owner's project privilege."""


class McpGrantLimitError(McpAuthorityError):
    pass


class McpGrantNotFoundError(McpAuthorityError):
    pass


class McpGrantStateError(McpAuthorityError):
    pass


@dataclass(frozen=True)
class IssuedPersonalToken:
    token: str
    token_id: str
    grant_id: str
    expires_at: datetime | None
    access_level: str
    project_scope: str = "current"
    approved_projects: tuple[dict[str, object], ...] = ()


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime) -> datetime:
    """MariaDB DATETIME rows are naive; interpret stored grant deadlines as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _audit(
    session: AsyncSession,
    *,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    action: str,
    grant: McpDelegatedGrant,
    extra: dict[str, object],
) -> None:
    """Make security state and its required audit evidence commit atomically."""
    session.add(
        ActivityLog(
            project_id=owner_project_id,
            user_id=owner_user_id,
            username=username,
            resource_type="mcp_grant",
            resource_id=grant.id,
            resource_name=grant.display_name,
            action=action,
            status="success",
            extra=extra,
        )
    )


def _token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _new_personal_token() -> str:
    return PERSONAL_TOKEN_PREFIX + base64.urlsafe_b64encode(secrets.token_bytes(PERSONAL_TOKEN_BYTES)).rstrip(
        b"="
    ).decode("ascii")


def _validate_display_name(value: str) -> str:
    value = value.strip()
    if not 1 <= len(value) <= 100 or any(ord(char) < 32 for char in value):
        raise McpAuthorityError("token name must contain 1 to 100 printable characters")
    return value


def _validate_access_level(value: str) -> str:
    if value not in {"read", "manage"}:
        raise McpAuthorityError("access level must be read or manage")
    return value


def grant_scopes(access_level: str) -> tuple[str, ...]:
    _validate_access_level(access_level)
    return ("mcp:read",) if access_level == "read" else ("mcp:read", "mcp:write")


def default_grant_lifetime() -> timedelta:
    return timedelta(days=get_settings().mcp_default_grant_ttl_days)


def max_grant_lifetime() -> timedelta:
    return timedelta(days=get_settings().mcp_max_grant_ttl_days)


def _grant_expiry(*, expires_at: datetime | None, now: datetime, maximum: timedelta | None = None) -> datetime:
    deadline = expires_at or now + default_grant_lifetime()
    if deadline.tzinfo is None:
        raise McpAuthorityError("token expiry must include a timezone")
    deadline = deadline.astimezone(UTC)
    if deadline <= now:
        raise McpAuthorityError("token expiry must be in the future")
    maximum = maximum or max_grant_lifetime()
    if deadline > now + maximum:
        raise McpAuthorityError(f"token expiry may not exceed {maximum.days} days")
    return deadline


def grant_is_expired(grant: McpDelegatedGrant, *, now: datetime | None = None) -> bool:
    """Only an explicitly issued personal grant may have no absolute deadline."""
    if grant.expires_at is None:
        return grant.source != "personal_token"
    return _as_utc(grant.expires_at) <= (now or _now())


def _personal_token_expiry(*, expires_at: datetime | None, non_expiring: bool, now: datetime) -> datetime | None:
    if non_expiring:
        if expires_at is not None:
            raise McpAuthorityError("non-expiring tokens cannot also specify an expiry")
        return None
    return _grant_expiry(expires_at=expires_at, now=now, maximum=max(MAX_PERSONAL_TOKEN_LIFETIME, max_grant_lifetime()))


async def lock_owner(session: AsyncSession, *, owner_user_id: str, owner_project_id: str) -> McpOwnerLock:
    """Bootstrap then lock the exact serialization row in this transaction."""
    if not owner_user_id or not owner_project_id:
        raise McpAuthorityError("MCP owner identity is incomplete")
    await session.execute(
        mysql_insert(McpOwnerLock)
        .values(owner_user_id=owner_user_id, owner_project_id=owner_project_id, lumen_selection_generation=0)
        .on_duplicate_key_update(lumen_selection_generation=McpOwnerLock.lumen_selection_generation)
    )
    row = await session.scalar(
        select(McpOwnerLock)
        .where(McpOwnerLock.owner_user_id == owner_user_id, McpOwnerLock.owner_project_id == owner_project_id)
        .with_for_update()
    )
    if row is None:
        raise McpAuthorityError("MCP owner lock is unavailable")
    return row


async def _count_dispatchable_grants(session: AsyncSession, *, owner_user_id: str, owner_project_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(McpDelegatedGrant)
            .where(
                McpDelegatedGrant.owner_user_id == owner_user_id,
                McpDelegatedGrant.owner_project_id == owner_project_id,
                McpDelegatedGrant.status.in_(("pending", "active")) | McpDelegatedGrant.cleanup_pending.is_(True),
            )
        )
        or 0
    )


async def _count_dispatchable_personal_tokens(
    session: AsyncSession, *, owner_user_id: str, owner_project_id: str
) -> int:
    """Pending personal-grant reservations consume the same ten-token capacity."""
    return int(
        await session.scalar(
            select(func.count())
            .select_from(McpDelegatedGrant)
            .where(
                McpDelegatedGrant.owner_user_id == owner_user_id,
                McpDelegatedGrant.owner_project_id == owner_project_id,
                McpDelegatedGrant.source == "personal_token",
                McpDelegatedGrant.status.in_(("pending", "active")) | McpDelegatedGrant.cleanup_pending.is_(True),
            )
        )
        or 0
    )


async def _lock_grant(
    session: AsyncSession, *, grant_id: str, owner_user_id: str, owner_project_id: str
) -> McpDelegatedGrant:
    grant = await session.scalar(
        select(McpDelegatedGrant)
        .where(
            McpDelegatedGrant.id == grant_id,
            McpDelegatedGrant.owner_user_id == owner_user_id,
            McpDelegatedGrant.owner_project_id == owner_project_id,
        )
        .with_for_update()
    )
    if grant is None:
        raise McpGrantNotFoundError("MCP grant was not found")
    return grant


def _role_snapshot(roles: object) -> list[dict[str, str]]:
    snapshot: list[dict[str, str]] = []
    if isinstance(roles, list):
        for item in roles:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name:
                role = {"name": name}
                if isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"]:
                    role["id"] = item["id"]
                if role not in snapshot:
                    snapshot.append(role)
    if not snapshot:
        raise McpAuthorityError("the current project has no usable Keystone role")
    return snapshot


def _approved_project_authority(grant: McpDelegatedGrant) -> list[dict[str, object]]:
    """Saved allowlist only; NULL legacy rows remain a singleton forever."""
    saved = getattr(grant, "approved_projects", None)
    if saved is None:
        project_id = grant.owner_project_id
        return [{"id": project_id, "name": project_id, "roles": [], "can_write": grant.access_level == "manage"}]
    if not isinstance(saved, list) or not saved:
        raise McpGrantStateError("MCP approved projects are invalid")
    result = []
    seen = set()
    for item in saved:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not item["id"]
            or item["id"] in seen
            or not isinstance(item.get("name"), str)
            or not isinstance(item.get("roles"), list)
            or any(not isinstance(role, str) or not role for role in item["roles"])
            or not isinstance(item.get("can_write"), bool)
        ):
            raise McpGrantStateError("MCP approved projects are invalid")
        seen.add(item["id"])
        result.append(
            {"id": item["id"], "name": item["name"], "roles": list(item["roles"]), "can_write": item["can_write"]}
        )
    return result


def approved_project_metadata(grant: McpDelegatedGrant) -> list[dict[str, str]]:
    """Public-safe snapshot projection; never disclose Keystone role authority."""
    return [{"id": project["id"], "name": project["name"]} for project in _approved_project_authority(grant)]


def validate_grant_project(grant: McpDelegatedGrant, project_id: str, *, write: bool = False) -> dict[str, object]:
    for metadata in _approved_project_authority(grant):
        if metadata["id"] == project_id:
            if write and (grant.access_level != "manage" or not metadata["can_write"]):
                raise McpGrantStateError("MCP project does not allow management")
            return metadata
    raise McpGrantStateError("project is outside the MCP approved scope")


def grant_project_ids(grant: McpDelegatedGrant) -> tuple[str, ...]:
    return tuple(project["id"] for project in approved_project_metadata(grant))


def default_grant_project(grant: McpDelegatedGrant) -> str:
    projects = grant_project_ids(grant)
    return grant.owner_project_id if grant.owner_project_id in projects else projects[0]


def validate_lumen_grant(grant: McpDelegatedGrant, project_id: str) -> None:
    """Internal Lumen grants require explicit consent to the owner's exact project."""
    if grant.source != "lumen":
        return
    if (
        getattr(grant, "consented_at", None) is None
        or grant.owner_project_id != project_id
        or getattr(grant, "project_scope", None) != "current"
        or grant_project_ids(grant) != (project_id,)
        or not getattr(grant, "application_credential_id", None)
        or not getattr(grant, "credential_ciphertext", None)
        or getattr(grant, "cleanup_pending", True)
    ):
        raise McpGrantStateError("Lumen grant requires explicit consent for the current project")


@dataclass(frozen=True)
class ApprovedProject:
    id: str
    name: str
    roles: list[dict[str, str]]
    can_write: bool
    conn: Any
    owns_connection: bool = True

    def metadata(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "roles": [role["name"] for role in self.roles],
            "can_write": self.can_write,
        }


async def prepare_project_authority(
    token_info: dict,
    *,
    project_scope: str = "current",
    project_ids: list[str] | None = None,
    access_level: str = "read",
) -> list[ApprovedProject]:
    from app.services import keystone

    conn = await asyncio.to_thread(keystone.get_openstack_connection, token_info["token"], token_info["project_id"])
    conn._afterglow_user_id = token_info["user_id"]
    conn._afterglow_project_id = token_info["project_id"]
    conn._afterglow_token = token_info["token"]
    try:
        projects = await _prepare_connection_projects(
            conn,
            token_info["user_id"],
            token_info["project_id"],
            token_info.get("roles", []),
            project_scope,
            project_ids,
            access_level,
        )
    except BaseException:
        await asyncio.to_thread(conn.close)
        raise
    for project in projects:
        if project.conn is conn:
            return [ApprovedProject(p.id, p.name, p.roles, p.can_write, p.conn, True) for p in projects]
    await asyncio.to_thread(conn.close)
    return projects


async def _prepare_connection_projects(
    conn: Any,
    user_id: str,
    project_id: str,
    roles: object,
    project_scope: str,
    project_ids: list[str] | None,
    access_level: str,
) -> list[ApprovedProject]:
    from app.services.mcp_control_plane.projects import project_candidates, project_connection

    _validate_access_level(access_level)
    metadata = await project_candidates(conn, user_id, project_id, project_scope, project_ids)
    result = []
    try:
        for project in metadata:
            scoped = await project_connection(conn, user_id, project["id"])
            role_snapshot = scoped._afterglow_roles
            can_write = bool({role["name"].casefold() for role in role_snapshot} & {"admin", "member"})
            if access_level == "manage" and not can_write:
                if scoped is not conn:
                    await asyncio.to_thread(scoped.close)
                raise McpGrantPrivilegeError("selected project does not allow management")
            project_name = scoped._afterglow_project_name if project_scope == "current" else project["name"]
            result.append(
                ApprovedProject(project["id"], project_name, role_snapshot, can_write, scoped, scoped is not conn)
            )
        return result
    except BaseException:
        await close_project_authority(result)
        raise


async def close_project_authority(projects: list[ApprovedProject]) -> None:
    async def close_all() -> None:
        for project in projects:
            if project.owns_connection:
                await asyncio.to_thread(project.conn.close)

    task = asyncio.create_task(close_all())
    await _drain(task)
    task.result()


async def grant_credential_for_project(
    session: AsyncSession, grant: McpDelegatedGrant, project_id: str
) -> tuple[str, str]:
    validate_grant_project(grant, project_id)
    credential = None
    if project_id != grant.owner_project_id:
        credential = await session.get(
            McpProjectCredential, {"grant_id": grant.id, "project_id": project_id}, with_for_update=True
        )
        if credential is None:
            raise McpGrantStateError("MCP project credential is unavailable")
    secret = decrypt_grant_secret(grant, project_id=project_id, credential=credential)
    return (credential or grant).application_credential_id, secret


async def create_grant_credentials(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    grant_id: str,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    projects: list[ApprovedProject],
    expires_at: datetime | None,
) -> None:
    """Reserve every deterministic name, drain remote work, and persist before activation."""
    canceled = asyncio.Event()

    async def create_all() -> None:
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            if grant.status != "pending" or grant.orphan_recovery_nonce is not None:
                raise McpGrantStateError("MCP grant was changed before credential creation")
            if [project.metadata() for project in projects] != _approved_project_authority(grant):
                raise McpGrantStateError("project credentials do not match the reserved approval")
            for project in projects:
                if project.id != owner_project_id:
                    session.add(
                        McpProjectCredential(
                            grant_id=grant_id,
                            project_id=project.id,
                            upstream_credential_name=f"afterglow-mcp-{grant_id}-{hashlib.sha256(project.id.encode()).hexdigest()[:32]}",
                            cleanup_pending=True,
                        )
                    )
        for project in projects:
            if canceled.is_set():
                raise asyncio.CancelledError()
            async with session_factory() as session, session.begin():
                await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
                grant = await _lock_grant(
                    session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                if grant.status != "pending" or grant.orphan_recovery_nonce is not None:
                    raise McpGrantStateError("MCP grant was changed before credential creation")
                credential = (
                    grant
                    if project.id == owner_project_id
                    else await session.get(
                        McpProjectCredential, {"grant_id": grant_id, "project_id": project.id}, with_for_update=True
                    )
                )
                name = credential.upstream_credential_name
            created = await asyncio.to_thread(
                create_restricted_application_credential,
                project.conn,
                owner_user_id=owner_user_id,
                owner_project_id=project.id,
                upstream_name=name,
                expires_at=expires_at,
                roles=project.roles,
            )
            # Store the returned ID first: even encryption failure remains recoverable.
            async with session_factory() as session, session.begin():
                await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
                grant = await _lock_grant(
                    session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                credential = (
                    grant
                    if project.id == owner_project_id
                    else await session.get(
                        McpProjectCredential, {"grant_id": grant_id, "project_id": project.id}, with_for_update=True
                    )
                )
                if credential is None:
                    credential = McpProjectCredential(
                        grant_id=grant_id, project_id=project.id, upstream_credential_name=name, cleanup_pending=True
                    )
                    session.add(credential)
                credential.application_credential_id = created["id"]
                credential.cleanup_pending = True
                grant.cleanup_pending = True
            # Persist the remote ID before checking its authority, so even an
            # unexpected role response is rolled back by ID rather than name.
            returned_roles = created["roles"]
            approved_ids = {role["id"] for role in project.roles}
            if (
                not isinstance(returned_roles, list)
                or any(
                    not isinstance(role, dict) or not isinstance(role.get("id"), str) or role["id"] not in approved_ids
                    for role in returned_roles
                )
                or {role["id"] for role in returned_roles} != approved_ids
            ):
                raise McpAuthorityError("Keystone application credential roles do not match the authenticated approval")
            if created["project_id"] != project.id:
                raise McpAuthorityError(
                    "Keystone application credential project does not match the authenticated approval"
                )
            ciphertext = encrypt_application_credential(
                created["secret"], grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=project.id
            )
            async with session_factory() as session, session.begin():
                await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
                grant = await _lock_grant(
                    session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                credential = (
                    grant
                    if project.id == owner_project_id
                    else await session.get(
                        McpProjectCredential, {"grant_id": grant_id, "project_id": project.id}, with_for_update=True
                    )
                )
                if grant.status != "pending" or grant.orphan_recovery_nonce is not None:
                    raise McpGrantStateError("MCP grant was changed during credential creation")
                credential.credential_ciphertext = ciphertext
                if credential is not grant:
                    credential.cleanup_pending = False

    task = asyncio.create_task(create_all())
    try:
        await asyncio.shield(task)
    except BaseException:
        canceled.set()
        await _drain(task)
        await abandon_grant_credentials(
            session_factory,
            conn=projects[0].conn,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
        )
        raise


async def abandon_grant_credentials(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conn: Any,
    grant_id: str,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
) -> bool:
    """Own rollback through repeated caller cancellation without abandoning remote cleanup."""

    async def cleanup() -> bool:
        await revoke_grant(
            session_factory,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
        )
        return await confirm_keystone_cleanup(
            session_factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            application_credential_id=None,
        )

    task = asyncio.create_task(cleanup())
    await _drain(task)
    return task.result()


def create_restricted_application_credential(
    conn: Any,
    *,
    owner_user_id: str,
    owner_project_id: str,
    upstream_name: str,
    expires_at: datetime | None,
    roles: object,
) -> dict[str, Any]:
    """Create one restricted credential through the caller's scoped connection only."""
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    snapshot = _role_snapshot(roles)
    if any("id" not in role for role in snapshot):
        raise McpAuthorityError("application credential roles require authenticated Keystone role IDs")
    created = conn.identity.create_application_credential(
        user=owner_user_id,
        name=upstream_name,
        description="Afterglow inbound MCP delegated authority",
        # Keystone's default is this scoped token's exact role IDs. Explicit
        # roles re-resolve names and expand today's inference graph, which can
        # differ from the authenticated snapshot and reject valid delegation.
        **({"expires_at": isotime(_as_utc(expires_at), subsecond=True)} if expires_at is not None else {}),
        unrestricted=False,
    )
    credential_id = getattr(created, "id", None)
    secret = getattr(created, "secret", None)
    if not isinstance(credential_id, str) or not credential_id or not isinstance(secret, str) or not secret:
        raise McpAuthorityError("Keystone returned an incomplete application credential")
    return {
        "id": credential_id,
        "secret": secret,
        "roles": getattr(created, "roles", None),
        "project_id": getattr(created, "project_id", None),
    }


def delete_and_confirm_application_credential(
    conn: Any,
    *,
    owner_user_id: str,
    application_credential_id: str | None,
    upstream_credential_name: str,
) -> bool:
    """Delete one known ID or one exact deterministic orphan name, then re-read."""
    if application_credential_id:
        conn.identity.delete_application_credential(owner_user_id, application_credential_id, ignore_missing=True)
        return (
            conn.identity.find_application_credential(owner_user_id, application_credential_id, ignore_missing=True)
            is None
        )

    candidate = conn.identity.find_application_credential(owner_user_id, upstream_credential_name, ignore_missing=True)
    if candidate is None:
        return True
    candidate_name = getattr(candidate, "name", None)
    candidate_id = getattr(candidate, "id", None)
    if candidate_name != upstream_credential_name or not isinstance(candidate_id, str) or not candidate_id:
        return False
    conn.identity.delete_application_credential(owner_user_id, candidate_id, ignore_missing=True)
    return (
        conn.identity.find_application_credential(owner_user_id, upstream_credential_name, ignore_missing=True) is None
    )


def _definitively_not_created(exc: Exception) -> bool:
    """Only validated non-race client errors release a pending capacity slot."""
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    return status in {400, 401, 403, 404, 405, 406, 415, 422}


async def _release_pending_reservation(
    session_factory: async_sessionmaker[AsyncSession], *, grant_id: str, owner_user_id: str, owner_project_id: str
) -> None:
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        if grant.status == "pending" and not grant.application_credential_id:
            await session.delete(grant)


async def issue_personal_token(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conn: Any,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    roles: object,
    display_name: str,
    access_level: str,
    expires_at: datetime | None = None,
    non_expiring: bool = False,
    project_scope: str = "current",
    project_ids: list[str] | None = None,
) -> IssuedPersonalToken:
    """Freeze real caller memberships and create one restricted credential per project."""
    now = _now()
    display_name = _validate_display_name(display_name)
    access_level = _validate_access_level(access_level)
    deadline = _personal_token_expiry(expires_at=expires_at, non_expiring=non_expiring, now=now)
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    projects = await _prepare_connection_projects(
        conn, owner_user_id, owner_project_id, roles, project_scope, project_ids, access_level
    )
    grant_id = str(uuid4())
    credentials_ready = False
    try:
        await recover_stale_pending_orphans(
            session_factory,
            conn=conn,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
        )
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            settings = get_settings()
            if (
                await _count_dispatchable_grants(
                    session, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                >= settings.mcp_max_delegated_grants
            ):
                raise McpGrantLimitError("the project already has the maximum number of active MCP grants")
            if (
                await _count_dispatchable_personal_tokens(
                    session, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                >= settings.mcp_max_personal_tokens
            ):
                raise McpGrantLimitError("the project already has the maximum number of active MCP personal tokens")
            session.add(
                McpDelegatedGrant(
                    id=grant_id,
                    owner_user_id=owner_user_id,
                    owner_project_id=owner_project_id,
                    upstream_credential_name=f"afterglow-mcp-{grant_id}",
                    display_name=display_name,
                    source="personal_token",
                    access_level=access_level,
                    project_scope=project_scope,
                    approved_projects=[project.metadata() for project in projects],
                    status="pending",
                    expires_at=deadline,
                    cleanup_pending=True,
                    orphan_recovery_after=now + PENDING_ORPHAN_RECOVERY_GRACE,
                )
            )
        await create_grant_credentials(
            session_factory,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            projects=projects,
            expires_at=deadline,
        )
        credentials_ready = True
        token = _new_personal_token()
        token_id = str(uuid4())
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            if grant.status != "pending" or grant.orphan_recovery_nonce is not None or grant_is_expired(grant):
                raise McpGrantStateError("MCP grant was changed before activation")
            grant.status = "active"
            grant.issued_at = now
            grant.cleanup_pending = False
            grant.orphan_recovery_after = None
            session.add(
                McpPersonalToken(
                    id=token_id,
                    grant_id=grant_id,
                    visible_prefix=token[:20],
                    token_hash=_token_hash(token),
                    issued_at=now,
                )
            )
            _audit(
                session,
                owner_user_id=owner_user_id,
                owner_project_id=owner_project_id,
                username=username,
                action="mcp_grant.create",
                grant=grant,
                extra={
                    "source": "personal_token",
                    "access_level": access_level,
                    "project_scope": project_scope,
                    "project_ids": [project.id for project in projects],
                    "credential_epoch": grant.credential_epoch,
                },
            )
        return IssuedPersonalToken(
            token=token,
            token_id=token_id,
            grant_id=grant_id,
            expires_at=deadline,
            access_level=access_level,
            project_scope=project_scope,
            approved_projects=tuple(project.metadata() for project in projects),
        )
    except BaseException:
        if credentials_ready:
            await abandon_grant_credentials(
                session_factory,
                conn=conn,
                grant_id=grant_id,
                owner_user_id=owner_user_id,
                owner_project_id=owner_project_id,
                username=username,
            )
        raise
    finally:
        await close_project_authority(projects)


async def resolve_personal_token(
    session: AsyncSession, raw_token: str, *, now: datetime | None = None
) -> McpDelegatedGrant:
    """Resolve a PAT while preserving the owner → grant → token lock order."""
    now = now or _now()
    if not isinstance(raw_token, str) or not raw_token.startswith(PERSONAL_TOKEN_PREFIX):
        raise McpGrantNotFoundError("MCP token is invalid")
    digest = _token_hash(raw_token)
    token_hint = await session.scalar(select(McpPersonalToken).where(McpPersonalToken.token_hash == digest))
    if token_hint is None or not hmac.compare_digest(token_hint.token_hash, digest):
        raise McpGrantNotFoundError("MCP token is invalid")
    grant_hint = await session.scalar(select(McpDelegatedGrant).where(McpDelegatedGrant.id == token_hint.grant_id))
    if grant_hint is None:
        raise McpGrantNotFoundError("MCP token is inactive")
    await lock_owner(session, owner_user_id=grant_hint.owner_user_id, owner_project_id=grant_hint.owner_project_id)
    grant = await _lock_grant(
        session,
        grant_id=grant_hint.id,
        owner_user_id=grant_hint.owner_user_id,
        owner_project_id=grant_hint.owner_project_id,
    )
    row = await session.scalar(
        select(McpPersonalToken)
        .where(McpPersonalToken.id == token_hint.id, McpPersonalToken.grant_id == grant.id)
        .with_for_update()
    )
    if (
        row is None
        or not hmac.compare_digest(row.token_hash, digest)
        or row.revoked_at is not None
        or grant.status != "active"
        or grant_is_expired(grant, now=now)
    ):
        raise McpGrantNotFoundError("MCP token is inactive")
    await grant_credential_for_project(session, grant, default_grant_project(grant))
    row.last_used_at = now
    grant.last_used_at = now
    return grant


async def revoke_grant(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    grant_id: str,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
) -> tuple[str | None, bool]:
    """Locally revoke first; external Keystone cleanup is a separately confirmed step."""
    now = _now()
    async with session_factory() as session, session.begin():
        owner_lock = await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        if grant.status != "revoked":
            grant.status = "revoked"
            grant.revoked_at = grant.revoked_at or now
            grant.credential_epoch += 1
        grant.cleanup_pending = bool(grant.application_credential_id) or grant.cleanup_pending
        additional = (
            await session.scalars(
                select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id).with_for_update()
            )
        ).all()
        for credential in additional:
            credential.cleanup_pending = True
        grant.cleanup_pending = grant.cleanup_pending or bool(additional)
        tokens = (
            await session.scalars(
                select(McpPersonalToken).where(McpPersonalToken.grant_id == grant.id).with_for_update()
            )
        ).all()
        for token in tokens:
            token.revoked_at = token.revoked_at or now
        selection = await session.get(
            McpLumenSelection,
            {"owner_user_id": owner_user_id, "owner_project_id": owner_project_id},
            with_for_update=True,
        )
        selection_cleared = selection is not None and selection.grant_id == grant.id
        if selection_cleared:
            await session.delete(selection)
            owner_lock.lumen_selection_generation += 1
        _audit(
            session,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            action="mcp_grant.revoke",
            grant=grant,
            extra={"credential_epoch": grant.credential_epoch, "lumen_selection_cleared": selection_cleared},
        )
        return grant.application_credential_id, selection_cleared


async def set_lumen_selection(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    grant_id: str | None,
) -> int:
    """Replace personal or internal Lumen authority; only personal grants require a PAT."""
    now = _now()
    async with session_factory() as session, session.begin():
        owner_lock = await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        if grant_id is not None:
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            token = await session.scalar(
                select(McpPersonalToken).where(McpPersonalToken.grant_id == grant_id).with_for_update()
            )
            if (
                grant.source not in {"personal_token", "lumen"}
                or grant.status != "active"
                or grant_is_expired(grant, now=now)
                or (grant.source == "personal_token" and (token is None or token.revoked_at is not None))
            ):
                raise McpGrantStateError("Lumen selection requires active delegated authority")
            validate_lumen_grant(grant, owner_project_id)
            await grant_credential_for_project(session, grant, default_grant_project(grant))
        selection = await session.get(
            McpLumenSelection,
            {"owner_user_id": owner_user_id, "owner_project_id": owner_project_id},
            with_for_update=True,
        )
        if grant_id is None:
            if selection is not None:
                await session.delete(selection)
        elif selection is None:
            session.add(
                McpLumenSelection(owner_user_id=owner_user_id, owner_project_id=owner_project_id, grant_id=grant_id)
            )
        else:
            selection.grant_id = grant_id
            selection.updated_at = now
        owner_lock.lumen_selection_generation += 1
        session.add(
            ActivityLog(
                project_id=owner_project_id,
                user_id=owner_user_id,
                username=username,
                resource_type="mcp_lumen_selection",
                resource_id=grant_id,
                resource_name=None,
                action="mcp_lumen_selection.set" if grant_id else "mcp_lumen_selection.clear",
                status="success",
                extra={"generation": owner_lock.lumen_selection_generation, "grant_id": grant_id},
            )
        )
        return owner_lock.lumen_selection_generation


def decrypt_grant_secret(
    grant: McpDelegatedGrant,
    project_id: str | None = None,
    credential: McpProjectCredential | None = None,
) -> str:
    """Refuse moved credentials, out-of-allowlist targets, and inactive authority."""
    target = default_grant_project(grant) if project_id is None else project_id
    validate_lumen_grant(grant, target)
    validate_grant_project(grant, target)
    if target == grant.owner_project_id:
        if credential is not None:
            raise McpGrantStateError("home project credential must be the primary credential")
        source = grant
    else:
        if credential is None or credential.grant_id != grant.id or credential.project_id != target:
            raise McpGrantStateError("MCP credential does not match the target project")
        source = credential
    if (
        grant.status != "active"
        or grant_is_expired(grant)
        or not source.application_credential_id
        or not source.credential_ciphertext
        or (credential is not None and credential.cleanup_pending)
    ):
        raise McpGrantStateError("MCP grant is not dispatchable")
    return decrypt_application_credential(
        source.credential_ciphertext, grant_id=grant.id, owner_user_id=grant.owner_user_id, owner_project_id=target
    )


def grant_public_view(
    grant: McpDelegatedGrant, token: McpPersonalToken | None = None, *, is_lumen_default: bool = False
) -> dict[str, object]:
    """Return management metadata only; no credential, hash, or opaque secret leaves this layer."""
    return {
        "id": token.id if token else grant.id,
        "grant_id": grant.id,
        "name": grant.display_name,
        "source": grant.source,
        "access_level": grant.access_level,
        "project_scope": getattr(grant, "project_scope", None) or "current",
        "project_ids": list(grant_project_ids(grant)),
        "projects": approved_project_metadata(grant),
        "status": grant.status,
        "visible_prefix": token.visible_prefix if token else None,
        "issued_at": grant.issued_at or (token.issued_at if token else None),
        "expires_at": _as_utc(grant.expires_at) if grant.expires_at is not None else None,
        "last_used_at": token.last_used_at if token else grant.last_used_at,
        "revoked_at": grant.revoked_at,
        "is_lumen_default": is_lumen_default,
        "client_observations": public_client_observations(grant.client_observations),
    }


async def list_personal_tokens(
    session: AsyncSession, *, owner_user_id: str, owner_project_id: str
) -> list[dict[str, object]]:
    selected_grant_id = await session.scalar(
        select(McpLumenSelection.grant_id).where(
            McpLumenSelection.owner_user_id == owner_user_id,
            McpLumenSelection.owner_project_id == owner_project_id,
        )
    )
    rows = (
        await session.execute(
            select(McpDelegatedGrant, McpPersonalToken)
            .join(McpPersonalToken, McpPersonalToken.grant_id == McpDelegatedGrant.id)
            .where(
                McpDelegatedGrant.owner_user_id == owner_user_id,
                McpDelegatedGrant.owner_project_id == owner_project_id,
                McpDelegatedGrant.source == "personal_token",
                McpDelegatedGrant.status != "revoked",
                McpPersonalToken.revoked_at.is_(None),
            )
            .order_by(McpPersonalToken.issued_at.desc())
        )
    ).all()
    return [grant_public_view(grant, token, is_lumen_default=grant.id == selected_grant_id) for grant, token in rows]


async def list_oauth_grants(
    session: AsyncSession, *, owner_user_id: str, owner_project_id: str
) -> list[dict[str, object]]:
    grants = (
        await session.scalars(
            select(McpDelegatedGrant)
            .where(
                McpDelegatedGrant.owner_user_id == owner_user_id,
                McpDelegatedGrant.owner_project_id == owner_project_id,
                McpDelegatedGrant.source == "oauth",
                McpDelegatedGrant.status != "revoked",
            )
            .order_by(McpDelegatedGrant.created_at.desc())
        )
    ).all()
    return [grant_public_view(grant) for grant in grants]


async def personal_token_grant_id(
    session: AsyncSession, *, token_id: str, owner_user_id: str, owner_project_id: str
) -> str:
    grant_id = await session.scalar(
        select(McpPersonalToken.grant_id)
        .join(McpDelegatedGrant, McpDelegatedGrant.id == McpPersonalToken.grant_id)
        .where(
            McpPersonalToken.id == token_id,
            McpDelegatedGrant.owner_user_id == owner_user_id,
            McpDelegatedGrant.owner_project_id == owner_project_id,
            McpDelegatedGrant.source == "personal_token",
        )
    )
    if not grant_id:
        raise McpGrantNotFoundError("MCP personal token was not found")
    return str(grant_id)


async def confirm_keystone_cleanup(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conn: Any,
    grant_id: str,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
    application_credential_id: str | None,
) -> bool:
    """Confirm every saved credential absent, recording partial cleanup durably."""
    if getattr(conn, "_afterglow_user_id", None) != owner_user_id:
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        grant.cleanup_last_attempt_at = _now()
        recoverable = (
            grant.status == "pending"
            and grant.cleanup_pending
            and grant.orphan_recovery_after is not None
            and _as_utc(grant.orphan_recovery_after) <= _now()
        )
        live_lease = await session.scalar(
            select(func.count())
            .select_from(McpToolInvocation)
            .where(
                McpToolInvocation.grant_id == grant.id,
                McpToolInvocation.status == "dispatch_authorized",
                McpToolInvocation.lease_expires_at.is_(None) | (McpToolInvocation.lease_expires_at > _now()),
            )
        )
        if (
            (grant.status not in {"revoked", "expired"} and not recoverable)
            or (application_credential_id is not None and grant.application_credential_id != application_credential_id)
            or live_lease
        ):
            return False
        if not grant.cleanup_pending:
            return True
        if recoverable:
            grant.orphan_recovery_nonce = str(uuid4())
        nonce = grant.orphan_recovery_nonce
        epoch = grant.credential_epoch
        additional = (
            await session.scalars(
                select(McpProjectCredential).where(McpProjectCredential.grant_id == grant_id).with_for_update()
            )
        ).all()
        targets = []
        home_approved = owner_project_id in grant_project_ids(grant)
        if home_approved or grant.application_credential_id:
            targets.append((owner_project_id, grant.application_credential_id, grant.upstream_credential_name))
        for credential in additional:
            # A dispatched credential must be cleaned even if a failed attempt had
            # previously marked the secondary record complete.
            if credential.cleanup_pending or credential.application_credential_id:
                targets.append(
                    (credential.project_id, credential.application_credential_id, credential.upstream_credential_name)
                )
        grace = grant.orphan_recovery_after

    outcomes = {}
    for project_id, credential_id, name in targets:
        # Unknown results cannot be declared absent while creation may still settle.
        if credential_id is None and grace is not None and _as_utc(grace) > _now():
            outcomes[project_id] = False
            continue
        try:
            outcomes[project_id] = await asyncio.to_thread(
                delete_and_confirm_application_credential,
                conn,
                owner_user_id=owner_user_id,
                application_credential_id=credential_id,
                upstream_credential_name=name,
            )
        except Exception:
            outcomes[project_id] = False

    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        if grant.credential_epoch != epoch or grant.orphan_recovery_nonce != nonce:
            return False
        if grant.status not in {"revoked", "expired", "pending"}:
            return False
        additional = (
            await session.scalars(
                select(McpProjectCredential).where(McpProjectCredential.grant_id == grant_id).with_for_update()
            )
        ).all()
        by_project = {credential.project_id: credential for credential in additional}
        for project_id, credential_id, name in targets:
            if not outcomes[project_id]:
                continue
            credential = grant if project_id == owner_project_id else by_project.get(project_id)
            if credential is None:
                continue
            # A late returned ID or recreated reservation wins over an older name check.
            if credential.application_credential_id != credential_id or credential.upstream_credential_name != name:
                outcomes[project_id] = False
                continue
            credential.application_credential_id = None
            credential.credential_ciphertext = None
            if credential is not grant:
                credential.cleanup_pending = False
        complete = (
            all(outcomes.values())
            and not grant.application_credential_id
            and not any(credential.cleanup_pending or credential.application_credential_id for credential in additional)
        )
        grant.cleanup_pending = not complete
        grant.cleanup_last_attempt_at = _now()
        if not complete:
            return False
        if grant.status == "pending":
            grant.status = "revoked"
            grant.revoked_at = _now()
            grant.credential_epoch += 1
        grant.orphan_recovery_after = None
        grant.orphan_recovery_nonce = None
        _audit(
            session,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            action="mcp_grant.cleanup_confirmed",
            grant=grant,
            extra={"cleanup_confirmed": True, "orphan_recovery": recoverable, "project_count": len(targets)},
        )
        return True


async def recover_stale_pending_orphans(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    conn: Any,
    owner_user_id: str,
    owner_project_id: str,
    username: str,
) -> int:
    """Recover only grace-expired deterministic reservations for this same owner."""
    now = _now()
    async with session_factory() as session:
        candidates = (
            await session.execute(
                select(McpDelegatedGrant.id, McpDelegatedGrant.application_credential_id)
                .where(
                    McpDelegatedGrant.owner_user_id == owner_user_id,
                    McpDelegatedGrant.owner_project_id == owner_project_id,
                    McpDelegatedGrant.status.in_(("pending", "revoked", "expired")),
                    McpDelegatedGrant.cleanup_pending.is_(True),
                    McpDelegatedGrant.orphan_recovery_after.is_not(None),
                    McpDelegatedGrant.orphan_recovery_after <= now.replace(tzinfo=None),
                )
                .order_by(McpDelegatedGrant.created_at)
            )
        ).all()
    recovered = 0
    for grant_id, application_credential_id in candidates:
        if await confirm_keystone_cleanup(
            session_factory,
            conn=conn,
            grant_id=str(grant_id),
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            application_credential_id=application_credential_id,
        ):
            recovered += 1
    return recovered


async def mark_expired_grants_for_cleanup(
    session_factory: async_sessionmaker[AsyncSession], *, now: datetime | None = None
) -> int:
    """Globally mark expiry under owner locks; external cleanup stays owner-session-only."""
    now = now or _now()
    async with session_factory() as session:
        candidates = (
            await session.execute(
                select(
                    McpDelegatedGrant.id,
                    McpDelegatedGrant.owner_user_id,
                    McpDelegatedGrant.owner_project_id,
                )
                .where(
                    McpDelegatedGrant.status.in_(("pending", "active")),
                    McpDelegatedGrant.expires_at <= now.replace(tzinfo=None),
                )
                .order_by(McpDelegatedGrant.owner_user_id, McpDelegatedGrant.owner_project_id, McpDelegatedGrant.id)
            )
        ).all()
    marked = 0
    for grant_id, owner_user_id, owner_project_id in candidates:
        async with session_factory() as session, session.begin():
            owner_lock = await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            if grant.status not in {"pending", "active"} or not grant_is_expired(grant, now=now):
                continue
            grant.status = "expired"
            grant.revoked_at = now
            grant.credential_epoch += 1
            grant.cleanup_pending = bool(grant.application_credential_id) or grant.cleanup_pending
            additional = (
                await session.scalars(
                    select(McpProjectCredential).where(McpProjectCredential.grant_id == grant.id).with_for_update()
                )
            ).all()
            for credential in additional:
                credential.cleanup_pending = True
            grant.cleanup_pending = grant.cleanup_pending or bool(additional)
            selection = await session.get(
                McpLumenSelection,
                {"owner_user_id": owner_user_id, "owner_project_id": owner_project_id},
                with_for_update=True,
            )
            if selection is not None and selection.grant_id == grant.id:
                await session.delete(selection)
                owner_lock.lumen_selection_generation += 1
            _audit(
                session,
                owner_user_id=owner_user_id,
                owner_project_id=owner_project_id,
                username="system:mcp-cleanup",
                action="mcp_grant.expire",
                grant=grant,
                extra={"credential_epoch": grant.credential_epoch, "cleanup_pending": grant.cleanup_pending},
            )
            marked += 1
    return marked
