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
    McpToolInvocation,
)
from app.services.mcp_control_plane.crypto import decrypt_application_credential, encrypt_application_credential

PERSONAL_TOKEN_PREFIX = "mcp-afgl-"
PERSONAL_TOKEN_BYTES = 32
DEFAULT_GRANT_LIFETIME = timedelta(days=30)
MAX_GRANT_LIFETIME = timedelta(days=90)
MAX_ACTIVE_PERSONAL_TOKENS = 10
MAX_ACTIVE_GRANTS = 20
PENDING_ORPHAN_RECOVERY_GRACE = timedelta(minutes=15)


class McpAuthorityError(RuntimeError):
    """Safe domain error; API adapters decide its transport representation."""


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
    expires_at: datetime
    access_level: str


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


def _grant_expiry(*, expires_at: datetime | None, now: datetime) -> datetime:
    deadline = expires_at or now + default_grant_lifetime()
    if deadline.tzinfo is None:
        raise McpAuthorityError("token expiry must include a timezone")
    deadline = deadline.astimezone(UTC)
    if deadline <= now:
        raise McpAuthorityError("token expiry must be in the future")
    if deadline > now + max_grant_lifetime():
        raise McpAuthorityError(f"token expiry may not exceed {get_settings().mcp_max_grant_ttl_days} days")
    return deadline


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
                McpDelegatedGrant.status.in_(("pending", "active")),
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
                McpDelegatedGrant.status.in_(("pending", "active")),
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
    names: list[str] = []
    if isinstance(roles, list):
        for item in roles:
            name = item.get("name") if isinstance(item, dict) else item
            if isinstance(name, str) and name and name not in names:
                names.append(name)
    if not names:
        raise McpAuthorityError("the current project has no usable Keystone role")
    return [{"name": name} for name in names]


def create_restricted_application_credential(
    conn: Any,
    *,
    owner_user_id: str,
    owner_project_id: str,
    upstream_name: str,
    expires_at: datetime,
    roles: object,
) -> dict[str, str]:
    """Create one restricted credential through the caller's scoped connection only."""
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    created = conn.identity.create_application_credential(
        user=owner_user_id,
        name=upstream_name,
        description="Afterglow inbound MCP delegated authority",
        roles=_role_snapshot(roles),
        expires_at=isotime(_as_utc(expires_at), subsecond=True),
        unrestricted=False,
    )
    credential_id = getattr(created, "id", None)
    secret = getattr(created, "secret", None)
    if not isinstance(credential_id, str) or not credential_id or not isinstance(secret, str) or not secret:
        raise McpAuthorityError("Keystone returned an incomplete application credential")
    return {"id": credential_id, "secret": secret}


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
) -> IssuedPersonalToken:
    """Reserve capacity, create a restricted credential, then atomically activate it."""
    now = _now()
    display_name = _validate_display_name(display_name)
    access_level = _validate_access_level(access_level)
    deadline = _grant_expiry(expires_at=expires_at, now=now)
    # Reject local identity/role failures before consuming a durable capacity slot.
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")
    _role_snapshot(roles)
    await recover_stale_pending_orphans(
        session_factory,
        conn=conn,
        owner_user_id=owner_user_id,
        owner_project_id=owner_project_id,
        username=username,
    )
    grant_id = str(uuid4())
    upstream_name = f"afterglow-mcp-{grant_id}"

    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        settings = get_settings()
        if (
            await _count_dispatchable_grants(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
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
                upstream_credential_name=upstream_name,
                display_name=display_name,
                source="personal_token",
                access_level=access_level,
                status="pending",
                expires_at=deadline,
                cleanup_pending=True,
                orphan_recovery_after=now + PENDING_ORPHAN_RECOVERY_GRACE,
            )
        )

    # A crash or ambiguous remote result leaves a counted, non-dispatchable
    # reservation. Definitive pre-creation failures release it under the owner lock.
    try:
        created = await asyncio.to_thread(
            create_restricted_application_credential,
            conn,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            upstream_name=upstream_name,
            expires_at=deadline,
            roles=roles,
        )
    except Exception as exc:
        if _definitively_not_created(exc):
            await _release_pending_reservation(
                session_factory, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
        else:
            # A timeout or transport failure may have created the deterministic
            # upstream credential. Keep the reservation non-dispatchable until a
            # later same-owner recovery confirms its exact name is absent.
            async with session_factory() as session, session.begin():
                await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
                grant = await _lock_grant(
                    session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
                )
                if grant.status == "pending":
                    grant.cleanup_pending = True
        raise
    try:
        ciphertext = encrypt_application_credential(
            created["secret"], grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
    except Exception:
        async with session_factory() as session, session.begin():
            await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
            grant = await _lock_grant(
                session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
            )
            grant.application_credential_id = created["id"]
            grant.cleanup_pending = True
        raise
    token = _new_personal_token()
    token_id = str(uuid4())

    activation_changed = False
    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        if grant.status != "pending" or grant.orphan_recovery_nonce is not None:
            # A cleanup claim won the race. Preserve the returned remote ID on a
            # locally revoked row, then confirm deletion outside this transaction.
            if grant.application_credential_id is None:
                grant.application_credential_id = created["id"]
            if grant.status == "pending":
                grant.status = "revoked"
                grant.revoked_at = now
                grant.credential_epoch += 1
            grant.cleanup_pending = True
            grant.orphan_recovery_after = None
            grant.orphan_recovery_nonce = None
            activation_changed = True
        else:
            grant.application_credential_id = created["id"]
            grant.credential_ciphertext = ciphertext
            grant.status = "active"
            grant.issued_at = now
            grant.cleanup_pending = False
            grant.orphan_recovery_after = None
            grant.orphan_recovery_nonce = None
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
                    "credential_epoch": grant.credential_epoch,
                },
            )
    if activation_changed:
        await confirm_keystone_cleanup(
            session_factory,
            conn=conn,
            grant_id=grant_id,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            application_credential_id=created["id"],
        )
        raise McpGrantStateError("MCP grant was changed before activation")
    return IssuedPersonalToken(
        token=token, token_id=token_id, grant_id=grant_id, expires_at=deadline, access_level=access_level
    )


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
        or _as_utc(grant.expires_at) <= now
        or not grant.application_credential_id
        or not grant.credential_ciphertext
    ):
        raise McpGrantNotFoundError("MCP token is inactive")
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
        if grant.status not in {"revoked", "expired"}:
            grant.status = "revoked"
            grant.revoked_at = now
            grant.credential_epoch += 1
        grant.cleanup_pending = bool(grant.application_credential_id) or grant.cleanup_pending
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
    """Replace or clear the selected active personal token, always advancing generation."""
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
                grant.source != "personal_token"
                or grant.status != "active"
                or _as_utc(grant.expires_at) <= now
                or token is None
                or token.revoked_at
            ):
                raise McpGrantStateError("Lumen selection requires an active personal token grant")
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


def decrypt_grant_secret(grant: McpDelegatedGrant) -> str:
    """Refuse moved, malformed, pending, revoked, or expired grant secrets."""
    if (
        grant.status != "active"
        or _as_utc(grant.expires_at) <= _now()
        or not grant.application_credential_id
        or not grant.credential_ciphertext
    ):
        raise McpGrantStateError("MCP grant is not dispatchable")
    return decrypt_application_credential(
        grant.credential_ciphertext,
        grant_id=grant.id,
        owner_user_id=grant.owner_user_id,
        owner_project_id=grant.owner_project_id,
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
        "status": grant.status,
        "visible_prefix": token.visible_prefix if token else None,
        "issued_at": grant.issued_at or (token.issued_at if token else None),
        "expires_at": grant.expires_at,
        "last_used_at": token.last_used_at if token else grant.last_used_at,
        "revoked_at": grant.revoked_at,
        "is_lumen_default": is_lumen_default,
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
    """Delete after an initial lease check; reconcile local state after external confirmation."""
    if (
        getattr(conn, "_afterglow_user_id", None) != owner_user_id
        or getattr(conn, "_afterglow_project_id", None) != owner_project_id
    ):
        raise McpAuthorityError("scoped connection does not match the MCP grant owner")

    async def has_live_lease(session: AsyncSession, grant: McpDelegatedGrant) -> bool:
        return bool(
            await session.scalar(
                select(func.count())
                .select_from(McpToolInvocation)
                .where(
                    McpToolInvocation.grant_id == grant.id,
                    McpToolInvocation.status == "dispatch_authorized",
                    (McpToolInvocation.lease_expires_at.is_(None) | (McpToolInvocation.lease_expires_at > _now())),
                )
            )
        )

    recovery_nonce: str | None = None

    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        grant.cleanup_last_attempt_at = _now()
        is_orphan_recovery = (
            grant.status == "pending"
            and grant.cleanup_pending
            and grant.orphan_recovery_after is not None
            and _as_utc(grant.orphan_recovery_after) <= _now()
            and (
                (application_credential_id is None and grant.application_credential_id is None)
                or application_credential_id == grant.application_credential_id
            )
        )
        if (
            (grant.status not in {"revoked", "expired"} and not is_orphan_recovery)
            or not grant.cleanup_pending
            or (application_credential_id is not None and grant.application_credential_id != application_credential_id)
            or await has_live_lease(session, grant)
        ):
            grant.cleanup_pending = True
            return False
        upstream_name = grant.upstream_credential_name
        if is_orphan_recovery:
            recovery_nonce = str(uuid4())
            grant.orphan_recovery_nonce = recovery_nonce

    try:
        confirmed_absent = await asyncio.to_thread(
            delete_and_confirm_application_credential,
            conn,
            owner_user_id=owner_user_id,
            application_credential_id=application_credential_id,
            upstream_credential_name=upstream_name,
        )
    except Exception:
        confirmed_absent = False

    async with session_factory() as session, session.begin():
        await lock_owner(session, owner_user_id=owner_user_id, owner_project_id=owner_project_id)
        grant = await _lock_grant(
            session, grant_id=grant_id, owner_user_id=owner_user_id, owner_project_id=owner_project_id
        )
        grant.cleanup_last_attempt_at = _now()
        if (
            grant.status in {"revoked", "expired"}
            and not grant.cleanup_pending
            and grant.application_credential_id is None
            and grant.credential_ciphertext is None
        ):
            return True
        is_orphan_recovery = (
            grant.status == "pending"
            and grant.cleanup_pending
            and grant.orphan_recovery_after is not None
            and _as_utc(grant.orphan_recovery_after) <= _now()
            and (
                (application_credential_id is None and grant.application_credential_id is None)
                or application_credential_id == grant.application_credential_id
            )
            and grant.orphan_recovery_nonce == recovery_nonce
        )
        if (
            not confirmed_absent
            or (grant.status not in {"revoked", "expired"} and not is_orphan_recovery)
            or not grant.cleanup_pending
            or (application_credential_id is not None and grant.application_credential_id != application_credential_id)
        ):
            grant.cleanup_pending = True
            return False
        dispatch_lease_in_flight = await has_live_lease(session, grant)
        if is_orphan_recovery:
            grant.status = "revoked"
            grant.revoked_at = _now()
            grant.credential_epoch += 1
        # Keystone confirmed the credential is absent. A lease that begins in
        # between the two local transactions cannot restore that credential;
        # retain the invocation for its eventual outcome, but never retain a
        # local credential reference that no longer exists upstream.
        grant.cleanup_pending = False
        grant.application_credential_id = None
        grant.credential_ciphertext = None
        grant.orphan_recovery_after = None
        grant.orphan_recovery_nonce = None
        _audit(
            session,
            owner_user_id=owner_user_id,
            owner_project_id=owner_project_id,
            username=username,
            action="mcp_grant.cleanup_confirmed",
            grant=grant,
            extra={
                "cleanup_confirmed": True,
                "orphan_recovery": is_orphan_recovery,
                "dispatch_lease_in_flight": dispatch_lease_in_flight,
            },
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
                    McpDelegatedGrant.status == "pending",
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
            if grant.status not in {"pending", "active"} or _as_utc(grant.expires_at) > now:
                continue
            grant.status = "expired"
            grant.revoked_at = now
            grant.credential_epoch += 1
            grant.cleanup_pending = bool(grant.application_credential_id) or grant.cleanup_pending
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
