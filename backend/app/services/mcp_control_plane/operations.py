"""Owner-scoped safe views over durable MCP invocation state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select

from app.database import get_session_factory
from app.models.mcp_authority import McpToolInvocation
from app.services.mcp_control_plane.authentication import McpPrincipal, lock_principal_grant
from app.services.mcp_control_plane.authority import _as_utc, _now


class McpOperationError(RuntimeError):
    """The operation ledger cannot safely answer the caller."""


@dataclass(frozen=True)
class McpOperationView:
    invocation_id: str
    status: str
    tool_name: str
    created_at: datetime
    resource_ref: str | None
    operation_ref: str | None


def reconcile_expired_invocation(row: McpToolInvocation, *, now: datetime) -> bool:
    """Under the owner/grant/invocation locks, fence stale claims without resending."""
    if row.idempotency_key is None or row.status not in {"claimed", "dispatch_authorized"}:
        return False
    if row.lease_expires_at is not None and _as_utc(row.lease_expires_at) > now:
        return False
    row.status = "unknown"
    row.lease_expires_at = None
    row.error = "MCP mutation lease expired; verify provider state before further changes"
    return True


async def get_operation(principal: McpPrincipal, *, invocation_id: str) -> McpOperationView:
    """Return metadata only for the exact grant that created an invocation."""
    factory = get_session_factory()
    if factory is None:
        raise McpOperationError("MCP invocation storage is unavailable")
    try:
        async with factory() as session, session.begin():
            await lock_principal_grant(session, principal)
            row = await session.scalar(
                select(McpToolInvocation)
                .where(
                    McpToolInvocation.id == invocation_id,
                    McpToolInvocation.grant_id == principal.grant_id,
                    McpToolInvocation.source == "mcp",
                )
                .with_for_update()
            )
            if row is None:
                raise McpOperationError("MCP operation was not found")
            reconcile_expired_invocation(row, now=_now())
            view = McpOperationView(
                invocation_id=row.id,
                status=row.status,
                tool_name=row.tool_name,
                created_at=row.created_at,
                resource_ref=row.resource_ref,
                operation_ref=row.operation_ref,
            )
    except McpOperationError:
        raise
    except Exception as exc:
        raise McpOperationError("MCP invocation storage is unavailable") from exc
    return view
