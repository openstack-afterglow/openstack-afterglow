"""Authenticated internal bridge for Lumen's delegated MCP execution.

Lumen never receives a personal MCP credential.  It sends only the opaque
selection snapshot persisted with a durable run; this service revalidates that
snapshot under the control-plane locks immediately before listing or executing
a tool.
"""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings
from app.services.mcp_control_plane import ledger, lumen, registry

router = APIRouter()


class _SnapshotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(min_length=1, max_length=64)
    project_id: str = Field(min_length=1, max_length=64)


class _ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: dict[str, Any]
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any]
    idempotency_key: str | None = Field(default=None, max_length=128)


class _PreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: dict[str, Any]
    name: str = Field(min_length=1, max_length=128)
    arguments: dict[str, Any]


def _require_lumen_service_token(authorization: str | None = Header(default=None)) -> None:
    """Authenticate only the configured Lumen workload identity, fail closed."""
    settings = get_settings()
    configured = settings.lumen_mcp_service_token
    provided = authorization.removeprefix("Bearer ") if authorization else ""
    if (
        not getattr(settings, "service_mcp_enabled", False)
        or not configured
        or not provided
        or not hmac.compare_digest(provided, configured)
    ):
        raise HTTPException(status_code=401, detail="Lumen MCP bridge authentication failed")


def _entry_payload(entry: registry.RegistryEntry) -> dict[str, Any]:
    return {
        "name": entry.name,
        "description": entry.description,
        "input_schema": entry.input_schema(),
        "effect": entry.effect,
    }


@router.post("/snapshot")
async def snapshot(body: _SnapshotRequest, _: None = Depends(_require_lumen_service_token)) -> dict[str, Any]:
    """Resolve the active selected grant and its closed registry view."""
    selected = await lumen.selected_lumen_snapshot(user_id=body.user_id, project_id=body.project_id)
    if selected is None:
        return {"snapshot": None, "entries": [], "service_fingerprint": registry.enabled_service_fingerprint()}
    try:
        principal = await lumen.resolve_lumen_principal(selected)
    except lumen.McpLumenAuthorityError:
        return {"snapshot": None, "entries": [], "service_fingerprint": registry.enabled_service_fingerprint()}
    return {
        "snapshot": lumen.snapshot_payload(selected),
        "entries": [_entry_payload(entry) for entry in registry.enabled_entries(principal)],
        "service_fingerprint": registry.enabled_service_fingerprint(),
    }


@router.post("/preview")
async def preview(body: _PreviewRequest, _: None = Depends(_require_lumen_service_token)) -> dict[str, Any]:
    """Return a non-mutating, revalidated control-plane preview for Lumen approval."""
    try:
        selected = lumen.frozen_snapshot(body.snapshot)
        if selected is None:
            raise lumen.McpLumenAuthorityError("Lumen delegated MCP snapshot is missing")
        principal = await lumen.resolve_lumen_principal(selected)
    except lumen.McpLumenAuthorityError as exc:
        raise HTTPException(status_code=403, detail="Lumen delegated MCP selection is unavailable") from exc
    entry = registry.entry_by_name(body.name)
    if entry is None or entry.effect == "read" or not entry.allowed_for(principal):
        raise HTTPException(status_code=404, detail="MCP mutation tool is unavailable")
    try:
        parsed = registry.parse_entry_arguments(entry, body.arguments)
        principal, parsed = await registry.bind_entry_target(principal, entry=entry, arguments=parsed)
        preview_plan = await registry.build_mutation_preview(
            registry.ConsumerCloudContext(principal=principal), entry=entry, arguments=parsed
        )
        return preview_plan.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="MCP mutation preview is unavailable") from exc


@router.post("/execute")
async def execute(body: _ExecuteRequest, _: None = Depends(_require_lumen_service_token)) -> dict[str, Any]:
    """Execute one selected grant tool with the control-plane ledger semantics."""
    try:
        selected = lumen.frozen_snapshot(body.snapshot)
        if selected is None:
            raise lumen.McpLumenAuthorityError("Lumen delegated MCP snapshot is missing")
        principal = await lumen.resolve_lumen_principal(selected)
    except lumen.McpLumenAuthorityError as exc:
        raise HTTPException(status_code=403, detail="Lumen delegated MCP selection is unavailable") from exc

    entry = registry.entry_by_name(body.name)
    if entry is None or not entry.allowed_for(principal):
        raise HTTPException(status_code=404, detail="MCP tool is unavailable")
    try:
        parsed = registry.parse_entry_arguments(entry, body.arguments)
        principal, parsed = await registry.bind_entry_target(principal, entry=entry, arguments=parsed)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="MCP tool arguments are invalid") from exc
    normalized = parsed.model_dump(mode="json")
    context = registry.ConsumerCloudContext(principal=principal)

    if entry.effect == "read":
        try:
            result = await registry.dispatch(context, entry=entry, arguments=parsed)
        except Exception as exc:
            await ledger.record_read_invocation(
                principal, entry=entry, arguments=normalized, status="failed", error=str(exc), source="lumen"
            )
            raise HTTPException(status_code=502, detail="MCP tool execution failed") from exc
        payload = registry.output_payload(entry, result)
        await ledger.record_read_invocation(
            principal, entry=entry, arguments=normalized, status="succeeded", source="lumen"
        )
        return payload

    try:
        key = ledger.validate_idempotency_key(body.idempotency_key)
        claim = await ledger.claim_mutation(
            principal, entry=entry, arguments=normalized, idempotency_key=key, source="lumen"
        )
        if claim.state == "replay":
            assert claim.result is not None
            return claim.result
        if claim.state in {"in_progress", "unknown", "failed"}:
            raise ledger.McpInvocationError(claim.error or "MCP mutation is unavailable")
        try:
            await registry.build_mutation_preview(context, entry=entry, arguments=parsed)
        except Exception:
            await ledger.fail_pre_dispatch(
                principal, invocation_id=claim.invocation_id, error="MCP pre-dispatch validation failed", source="lumen"
            )
            raise
        await ledger.authorize_mutation_dispatch(principal, invocation_id=claim.invocation_id, source="lumen")
        try:
            payload = registry.output_payload(entry, await registry.dispatch(context, entry=entry, arguments=parsed))
            await ledger.complete_mutation(principal, invocation_id=claim.invocation_id, result=payload, source="lumen")
            return payload
        except Exception as exc:
            try:
                await ledger.complete_mutation(
                    principal,
                    invocation_id=claim.invocation_id,
                    error="MCP mutation outcome is unknown after dispatch authorization",
                    source="lumen",
                )
            except ledger.McpInvocationError:
                pass
            raise exc
    except ledger.McpInvocationError as exc:
        raise HTTPException(status_code=409, detail="MCP mutation is unavailable") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail="MCP tool execution failed") from exc
