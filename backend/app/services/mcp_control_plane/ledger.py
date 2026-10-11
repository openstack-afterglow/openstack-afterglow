"""Durable invocation audit and the mutation send-boundary primitives."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.database import get_session_factory
from app.models.mcp_authority import McpToolInvocation
from app.services.mcp_control_plane.authentication import McpPrincipal, lock_principal_grant
from app.services.mcp_control_plane.authority import (
    McpAuthorityError,
    _as_utc,
    _now,
    grant_is_expired,
    lock_owner,
)
from app.services.mcp_control_plane.registry import REGISTRY_VERSION, RegistryEntry


class McpInvocationError(RuntimeError):
    """The ledger is unavailable or a call cannot cross its durable boundary."""


_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
_MUTATION_RESULT_MAX_BYTES = 64 * 1024

_INVOCATION_SOURCES = frozenset(("mcp", "lumen"))


def _invocation_source(value: object) -> Literal["mcp", "lumen"]:
    if value not in _INVOCATION_SOURCES:
        raise McpInvocationError("MCP invocation source is invalid")
    return value  # type: ignore[return-value]


@dataclass(frozen=True)
class MutationClaim:
    """The only states a caller can observe after atomically claiming a mutation."""

    state: Literal["claimed", "replay", "in_progress", "unknown", "failed"]
    invocation_id: str
    result: dict | None = None
    error: str | None = None


def canonical_arguments_hash(arguments: object) -> str:
    """Hash only validated domain arguments with deterministic Unicode JSON."""
    try:
        payload = json.dumps(
            arguments,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise McpInvocationError("MCP arguments cannot be canonically audited") from exc
    normalized = unicodedata.normalize("NFC", payload)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def canonical_target_arguments(principal: McpPrincipal, arguments: object) -> dict:
    if not isinstance(arguments, dict):
        raise McpInvocationError("MCP domain arguments must be an object")
    supplied = arguments.get("project_id")
    if supplied is not None and supplied != principal.project_id:
        raise McpInvocationError("MCP argument target differs from the authorized project")
    return {**arguments, "project_id": principal.project_id}


def validate_idempotency_key(value: object) -> str:
    if not isinstance(value, str) or not _IDEMPOTENCY_KEY_RE.fullmatch(value):
        raise McpInvocationError("MCP mutation idempotency_key is invalid")
    return value


def _validate_active_write_grant(grant, principal: McpPrincipal) -> None:
    if (
        grant.status != "active"
        or grant_is_expired(grant)
        or grant.credential_epoch != principal.credential_epoch
        or "mcp:write" not in principal.scopes
    ):
        raise McpInvocationError("MCP grant changed before mutation dispatch")


def _decode_replay_result(row: McpToolInvocation) -> dict:
    if not row.result:
        raise McpInvocationError("MCP mutation replay result is unavailable")
    try:
        parsed = json.loads(row.result)
    except json.JSONDecodeError as exc:
        raise McpInvocationError("MCP mutation replay result is invalid") from exc
    if not isinstance(parsed, dict):
        raise McpInvocationError("MCP mutation replay result is invalid")
    return parsed


async def claim_mutation(
    principal: McpPrincipal,
    *,
    entry: RegistryEntry,
    arguments: object,
    idempotency_key: object,
    source: Literal["mcp", "lumen"] = "mcp",
) -> MutationClaim:
    """Claim one key under the grant lock; all stale claims become non-retryable."""
    invocation_source = _invocation_source(source)
    if entry.effect != "external_mutation":
        raise McpInvocationError("MCP entry is not a mutation")
    key = validate_idempotency_key(idempotency_key)
    arguments_hash = canonical_arguments_hash(canonical_target_arguments(principal, arguments))
    now = _now()
    try:
        async with _factory()() as session, session.begin():
            grant = await lock_principal_grant(session, principal, write=True)
            _validate_active_write_grant(grant, principal)
            existing = await session.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.grant_id == principal.grant_id,
                    McpToolInvocation.source == invocation_source,
                    McpToolInvocation.tool_name == entry.name,
                    McpToolInvocation.idempotency_key == key,
                )
                .with_for_update()
            )
            if existing is None:
                # A different key must not turn an unresolved identical operation
                # into a second provider dispatch. The grant lock serializes claims.
                unresolved = await session.scalar(
                    select(McpToolInvocation)
                    .where(
                        McpToolInvocation.grant_id == principal.grant_id,
                        McpToolInvocation.source == invocation_source,
                        McpToolInvocation.tool_name == entry.name,
                        McpToolInvocation.arguments_hash == arguments_hash,
                        McpToolInvocation.idempotency_key.is_not(None),
                        McpToolInvocation.status.in_(("claimed", "dispatch_authorized", "unknown")),
                    )
                    .limit(1)
                    .with_for_update()
                )
                if unresolved is not None:
                    raise McpInvocationError("MCP mutation has an unresolved outcome; do not retry with a new key")
                invocation_id = str(uuid4())
                session.add(
                    McpToolInvocation(
                        id=invocation_id,
                        grant_id=principal.grant_id,
                        source=invocation_source,
                        tool_name=entry.name,
                        idempotency_key=key,
                        arguments_hash=arguments_hash,
                        registry_version=REGISTRY_VERSION,
                        status="claimed",
                        lease_expires_at=mutation_lease_expiry(),
                        created_at=now,
                    )
                )
                return MutationClaim(state="claimed", invocation_id=invocation_id)
            if not hmac.compare_digest(existing.arguments_hash, arguments_hash):
                raise McpInvocationError("MCP idempotency key was already used with different arguments")
            if existing.status == "succeeded":
                return MutationClaim(
                    state="replay",
                    invocation_id=existing.id,
                    result=_decode_replay_result(existing),
                )
            if existing.status == "failed":
                return MutationClaim(
                    state="failed",
                    invocation_id=existing.id,
                    error=existing.error or "MCP mutation previously failed",
                )
            if existing.status in {"claimed", "dispatch_authorized"}:
                if existing.lease_expires_at is not None and _as_utc(existing.lease_expires_at) > now:
                    return MutationClaim(state="in_progress", invocation_id=existing.id)
                existing.status = "unknown"
                existing.lease_expires_at = None
            return MutationClaim(
                state="unknown",
                invocation_id=existing.id,
                error=existing.error or "MCP mutation outcome is unknown",
            )
    except (McpAuthorityError, McpInvocationError):
        raise
    except Exception as exc:
        raise McpInvocationError("MCP mutation ledger is unavailable") from exc


async def fail_pre_dispatch(
    principal: McpPrincipal, *, invocation_id: str, error: str, source: Literal["mcp", "lumen"] = "mcp"
) -> None:
    """Terminalize a claimed mutation that failed before dispatch authorization."""
    invocation_source = _invocation_source(source)
    try:
        async with _factory()() as session, session.begin():
            await lock_owner(session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id)
            invocation = await session.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.id == invocation_id,
                    McpToolInvocation.grant_id == principal.grant_id,
                    McpToolInvocation.source == invocation_source,
                )
                .with_for_update()
            )
            if invocation is None or invocation.status != "claimed":
                raise McpInvocationError("MCP mutation is no longer pre-dispatch cancellable")
            invocation.status = "failed"
            invocation.lease_expires_at = None
            invocation.error = error[:1024] or "MCP pre-dispatch validation failed"
    except McpInvocationError:
        raise
    except Exception as exc:
        raise McpInvocationError("MCP mutation pre-dispatch completion is unavailable") from exc


async def authorize_mutation_dispatch(
    principal: McpPrincipal, *, invocation_id: str, source: Literal["mcp", "lumen"] = "mcp"
) -> None:
    """Cross the no-retry send boundary only while the current grant remains valid."""
    invocation_source = _invocation_source(source)
    now = _now()
    try:
        async with _factory()() as session, session.begin():
            grant = await lock_principal_grant(session, principal, write=True)
            _validate_active_write_grant(grant, principal)
            invocation = await session.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.id == invocation_id,
                    McpToolInvocation.grant_id == principal.grant_id,
                    McpToolInvocation.source == invocation_source,
                )
                .with_for_update()
            )
            if (
                invocation is None
                or invocation.status != "claimed"
                or invocation.lease_expires_at is None
                or _as_utc(invocation.lease_expires_at) <= now
            ):
                if invocation is not None and invocation.status == "claimed":
                    invocation.status = "unknown"
                    invocation.lease_expires_at = None
                raise McpInvocationError("MCP mutation is no longer dispatchable")
            invocation.status = "dispatch_authorized"
            invocation.dispatch_authorized_at = now
            invocation.lease_expires_at = mutation_lease_expiry()
            invocation.sent_at = now
    except (McpAuthorityError, McpInvocationError):
        raise
    except Exception as exc:
        raise McpInvocationError("MCP mutation authorization is unavailable") from exc


async def complete_mutation(
    principal: McpPrincipal,
    *,
    invocation_id: str,
    result: dict | None = None,
    error: str | None = None,
    resource_ref: str | None = None,
    operation_ref: str | None = None,
    source: Literal["mcp", "lumen"] = "mcp",
) -> None:
    """Persist a bounded safe result; failures after send are always unknown."""
    invocation_source = _invocation_source(source)
    if (result is None) == (error is None):
        raise McpInvocationError("MCP mutation completion is invalid")
    serialized = None
    if result is not None:
        try:
            serialized = json.dumps(result, allow_nan=False, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise McpInvocationError("MCP mutation result is invalid") from exc
        if len(serialized.encode("utf-8")) > _MUTATION_RESULT_MAX_BYTES:
            raise McpInvocationError("MCP mutation result exceeds the replay limit")
    try:
        async with _factory()() as session, session.begin():
            await lock_owner(session, owner_user_id=principal.user_id, owner_project_id=principal.anchor_project_id)
            invocation = await session.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.id == invocation_id,
                    McpToolInvocation.grant_id == principal.grant_id,
                    McpToolInvocation.source == invocation_source,
                )
                .with_for_update()
            )
            if invocation is None or invocation.status != "dispatch_authorized":
                raise McpInvocationError("MCP mutation completion is unavailable")
            invocation.status = "succeeded" if result is not None else "unknown"
            invocation.sent_at = invocation.sent_at or _now()
            invocation.lease_expires_at = None
            invocation.result = serialized
            invocation.error = (error or "")[:1024] or None
            invocation.resource_ref = (resource_ref or "")[:512] or None
            invocation.operation_ref = (operation_ref or "")[:512] or None
    except McpInvocationError:
        raise
    except Exception as exc:
        raise McpInvocationError("MCP mutation completion is unavailable") from exc


def _factory() -> async_sessionmaker:
    factory = get_session_factory()
    if factory is None:
        raise McpInvocationError("MCP invocation storage is unavailable")
    return factory


async def record_read_invocation(
    principal: McpPrincipal,
    *,
    entry: RegistryEntry,
    arguments: object,
    status: str,
    error: str | None = None,
    source: Literal["mcp", "lumen"] = "mcp",
) -> None:
    """Audit a read without persisting response data, then fail closed on audit loss."""
    invocation_source = _invocation_source(source)
    if entry.effect != "read" or status not in {"succeeded", "failed"}:
        raise McpInvocationError("read invocation audit state is invalid")
    now = _now()
    try:
        async with _factory()() as session, session.begin():
            await lock_principal_grant(session, principal)
            session.add(
                McpToolInvocation(
                    id=str(uuid4()),
                    grant_id=principal.grant_id,
                    source=invocation_source,
                    tool_name=entry.name,
                    idempotency_key=None,
                    arguments_hash=canonical_arguments_hash(canonical_target_arguments(principal, arguments)),
                    registry_version=REGISTRY_VERSION,
                    status=status,
                    error=(error or "")[:1024] or None,
                    created_at=now,
                )
            )
    except (McpAuthorityError, McpInvocationError):
        raise
    except Exception as exc:
        raise McpInvocationError("MCP invocation audit is unavailable") from exc


def mutation_lease_expiry() -> object:
    return _now() + timedelta(minutes=2)
