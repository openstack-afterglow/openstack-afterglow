"""Internal K3s service endpoints for Afterglow integration."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import hmac
import json
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_session
from app.models.db import K3sProvisioningIntent
from app.services import cinder, nova
from app.services.cache import invalidate
from app.services.cache import invalidation as cache_invalidation
from app.services.gpu_inventory import (
    GpuQuotaDenied,
    GpuQuotaUnavailable,
    require_gpu_quota,
)
from app.services.keystone import get_admin_connection_for_project

_logger = logging.getLogger(__name__)

_RESOURCE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

router = APIRouter()


class GpuAdmissionRequest(BaseModel):
    project_id: str
    flavor_id: str


class GpuAdmissionResponse(BaseModel):
    gpu_required: bool


def _require_gpu_admission_token(
    x_afterglow_k3s_admission_token: str | None = Header(None, alias="X-Afterglow-K3s-Admission-Token"),
) -> None:
    configured_token = get_settings().k3s_gpu_admission_token.strip()
    candidate = x_afterglow_k3s_admission_token.strip() if isinstance(x_afterglow_k3s_admission_token, str) else ""
    if (
        not configured_token
        or not candidate
        or not hmac.compare_digest(
            configured_token.encode("utf-8"),
            candidate.encode("utf-8"),
        )
    ):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/gpu-admission", response_model=GpuAdmissionResponse)
async def k3s_gpu_admission(
    req: GpuAdmissionRequest,
    _: None = Depends(_require_gpu_admission_token),
) -> dict[str, bool]:
    """Validate internal K3s node GPU admission against Afterglow quota authority."""

    project_id = req.project_id.strip() if isinstance(req.project_id, str) else ""
    flavor_id = req.flavor_id.strip() if isinstance(req.flavor_id, str) else ""
    if not _RESOURCE_ID_RE.fullmatch(project_id) or not _RESOURCE_ID_RE.fullmatch(flavor_id):
        raise HTTPException(status_code=400, detail="Invalid project_id or flavor_id")

    try:
        conn = await asyncio.to_thread(get_admin_connection_for_project, project_id)
    except Exception as exc:
        _logger.error(
            "Failed to connect to OpenStack for project %s: %s",
            project_id,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=503, detail="OpenStack service connection unavailable") from exc

    conn._afterglow_project_id = project_id

    try:
        try:
            flavors = await asyncio.to_thread(nova.list_flavors, conn)
        except Exception as exc:
            _logger.error(
                "Failed to list flavors for project %s: %s",
                project_id,
                exc,
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="OpenStack compute service unavailable") from exc

        flavor = next(
            (
                f
                for f in flavors
                if getattr(f, "id", None) == flavor_id or (isinstance(f, dict) and f.get("id") == flavor_id)
            ),
            None,
        )
        if flavor is None:
            raise HTTPException(status_code=400, detail="Flavor not found")

        try:
            gpu_required = await require_gpu_quota(conn, flavor)
        except GpuQuotaDenied as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GpuQuotaUnavailable as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except HTTPException:
            raise
        except Exception as exc:
            _logger.error("Unexpected error checking GPU quota: %s", exc, exc_info=True)
            raise HTTPException(status_code=503, detail="GPU quota decision failed") from exc

        return {"gpu_required": bool(gpu_required)}
    finally:
        await asyncio.to_thread(conn.close)


_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SAFE_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._:@/+,-]{0,127}$")
_MAX_METADATA_ITEMS = 32
_MAX_METADATA_BYTES = 4096
_MAX_USERDATA_BYTES = 1024 * 1024


class K3sProvisioningIntentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(..., min_length=1, max_length=128, pattern=_IDEMPOTENCY_KEY_RE.pattern)
    project_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    cluster_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    nodegroup_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    name: str = Field(..., min_length=1, max_length=128, pattern=_NAME_RE.pattern)
    flavor_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    image_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    network_id: str = Field(..., min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    boot_volume_size_gb: int = Field(..., ge=1, le=16384)
    volume_availability_zone: str = Field(..., min_length=1, max_length=128, pattern=_SAFE_TEXT_RE.pattern)
    security_group_id: str | None = Field(None, min_length=1, max_length=64, pattern=_RESOURCE_ID_RE.pattern)
    metadata: dict[str, str] | None = None
    config_drive: StrictBool = False

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if len(value) > _MAX_METADATA_ITEMS:
            raise ValueError("metadata has too many entries")
        if any(
            not re.fullmatch(r"^[A-Za-z0-9_.-]{1,64}$", key)
            or len(item) > 255
            or any(ord(char) < 0x20 or ord(char) == 0x7F for char in item)
            for key, item in value.items()
        ):
            raise ValueError("metadata keys and values are invalid")
        if len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > _MAX_METADATA_BYTES:
            raise ValueError("metadata is too large")
        return value


class K3sProvisioningSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userdata: str = Field(..., min_length=4, max_length=1_398_104)

    @field_validator("userdata")
    @classmethod
    def validate_userdata(cls, value: str) -> str:
        try:
            decoded = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("userdata must be valid base64") from exc
        if not decoded or len(decoded) > _MAX_USERDATA_BYTES:
            raise ValueError("userdata is outside the permitted size")
        return value


def _require_provisioning_token(header_token: str | None) -> None:
    configured = get_settings().k3s_provisioning_token.strip()
    candidate = header_token.strip() if isinstance(header_token, str) else ""
    if not configured or not hmac.compare_digest(configured.encode("utf-8"), candidate.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _intent_hash(req: K3sProvisioningIntentRequest) -> str:
    payload = req.model_dump(mode="json")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _intent_dict(row: K3sProvisioningIntent) -> dict[str, Any]:
    return {
        "idempotency_key": row.idempotency_key,
        "project_id": row.project_id,
        "cluster_id": row.cluster_id,
        "nodegroup_id": row.nodegroup_id,
        "name": row.name,
        "state": row.state,
        "error": row.error_message,
        "server_id": row.server_id,
        "volume_id": row.boot_volume_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "submitted_at": row.submitted_at.isoformat() if row.submitted_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _resource_id(value: object) -> str | None:
    candidate = value.get("id") if isinstance(value, dict) else getattr(value, "id", None)
    return candidate if isinstance(candidate, str) and candidate else None


async def _invalidate_provisioning_caches(project_id: str) -> None:
    await invalidate(f"afterglow:nova:{project_id}:instances")
    await invalidate(f"afterglow:cinder:{project_id}:volumes:v2")
    await cache_invalidation.invalidate_mutation_count("nova", project_id)
    await cache_invalidation.invalidate_mutation_count("cinder", project_id)


async def _mark_intent_failed(session: AsyncSession, row: K3sProvisioningIntent, message: str) -> None:
    row.state = "failed"
    row.error_message = message[:2000]
    row.completed_at = datetime.now(UTC)
    await session.commit()


_SUBMIT_LEASE = timedelta(minutes=30)


async def _recover_submitting_intent(session: AsyncSession, row: K3sProvisioningIntent) -> dict[str, Any] | None:
    """Reconcile a stale submission before allowing its durable retry."""
    submitted_at = row.submitted_at
    now = datetime.now(UTC)
    if submitted_at and submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=UTC)

    conn = None
    try:
        conn = await asyncio.to_thread(get_admin_connection_for_project, row.project_id)
        intent_key = row.idempotency_key
        servers = await asyncio.to_thread(lambda: list(conn.compute.servers(details=True)))
        for server in servers:
            metadata = getattr(server, "metadata", None) or {}
            if metadata.get("afterglow:k3s-provisioning-intent") != intent_key:
                continue
            server_id = _resource_id(server)
            if server_id is None:
                continue
            row.server_id = server_id
            row.state = "succeeded"
            row.error_message = None
            row.completed_at = now
            await session.commit()
            return {
                "state": "succeeded",
                "server_id": server_id,
                "volume_id": row.boot_volume_id,
                "name": row.name,
            }

        if submitted_at and now - submitted_at < _SUBMIT_LEASE:
            raise HTTPException(status_code=409, detail={"state": "submitting", "no_duplicate": True})

        if row.boot_volume_id is None:
            volumes = await asyncio.to_thread(cinder.list_volumes, conn)
            volume = next((item for item in volumes if getattr(item, "name", None) == f"{row.name}-boot"), None)
            if volume is not None:
                row.boot_volume_id = _resource_id(volume)
        row.state = "pending"
        row.error_message = "Reclaimed expired submission lease"
        row.submitted_at = None
        await session.commit()
        return None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="OpenStack recovery unavailable") from exc
    finally:
        if conn is not None:
            await asyncio.to_thread(conn.close)


async def _submit_intent(session: AsyncSession, row: K3sProvisioningIntent, userdata: str) -> dict[str, Any]:
    conn = None
    try:
        try:
            conn = await asyncio.to_thread(get_admin_connection_for_project, row.project_id)
        except Exception as exc:
            await _mark_intent_failed(session, row, "OpenStack service connection unavailable")
            raise HTTPException(status_code=503, detail="OpenStack service connection unavailable") from exc
        conn._afterglow_project_id = row.project_id
        try:
            flavors = await asyncio.to_thread(nova.list_flavors, conn)
        except Exception as exc:
            await _mark_intent_failed(session, row, "OpenStack compute service unavailable")
            raise HTTPException(status_code=503, detail="OpenStack compute service unavailable") from exc
        flavor = next((item for item in flavors if _resource_id(item) == row.flavor_id), None)
        if flavor is None:
            await _mark_intent_failed(session, row, "Flavor not found")
            raise HTTPException(status_code=400, detail="Flavor not found")
        try:
            await require_gpu_quota(conn, flavor)
        except GpuQuotaDenied as exc:
            await _mark_intent_failed(session, row, str(exc))
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except GpuQuotaUnavailable as exc:
            await _mark_intent_failed(session, row, str(exc))
            raise HTTPException(status_code=503, detail=str(exc)) from exc

        volume_id = row.boot_volume_id
        if volume_id is None:
            volume = await asyncio.to_thread(
                cinder.create_volume_from_image,
                conn,
                f"{row.name}-boot",
                row.image_id,
                row.boot_volume_size_gb,
                row.volume_availability_zone,
            )
            volume_id = _resource_id(volume)
            if volume_id is None:
                await _mark_intent_failed(session, row, "Boot volume creation returned no resource ID")
                raise HTTPException(status_code=502, detail="Boot volume creation failed")
            row.boot_volume_id = volume_id
            await session.commit()

        metadata = dict(row.resource_metadata or {})
        metadata["afterglow:k3s-provisioning-intent"] = row.idempotency_key
        server = await asyncio.to_thread(
            nova.create_server,
            conn,
            name=row.name,
            flavor_id=row.flavor_id,
            network_id=row.network_id,
            boot_volume_id=volume_id,
            userdata=userdata,
            availability_zone=row.volume_availability_zone,
            metadata=metadata,
            security_groups=[row.security_group_id] if row.security_group_id else None,
            config_drive=row.config_drive,
        )
        server_id = _resource_id(server)
        if server_id is None:
            raise RuntimeError("Nova server creation returned no resource ID")
        row.server_id = server_id
        row.state = "succeeded"
        row.error_message = None
        row.completed_at = datetime.now(UTC)
        await session.commit()
        return {"state": "succeeded", "server_id": server_id, "volume_id": volume_id, "name": row.name}
    except HTTPException:
        raise
    except Exception as exc:
        if row.boot_volume_id and conn is not None:
            try:
                await asyncio.to_thread(cinder.delete_volume, conn, row.boot_volume_id)
            except Exception:
                _logger.warning("Failed to roll back K3s provisioning volume for intent %s", row.idempotency_key)
        await _mark_intent_failed(session, row, "OpenStack provisioning failed")
        raise HTTPException(status_code=502, detail="OpenStack provisioning failed") from exc
    finally:
        if conn is not None:
            await asyncio.to_thread(conn.close)


@router.post("/provisioning-intents", status_code=201)
async def create_k3s_provisioning_intent(
    req: K3sProvisioningIntentRequest,
    response: Response,
    x_afterglow_k3s_provisioning_token: str | None = Header(None, alias="X-Afterglow-K3s-Provisioning-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_provisioning_token(x_afterglow_k3s_provisioning_token)
    request_hash = _intent_hash(req)
    existing = (
        await session.execute(
            select(K3sProvisioningIntent).where(K3sProvisioningIntent.idempotency_key == req.idempotency_key)
        )
    ).scalar_one_or_none()
    if existing is not None:
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise HTTPException(status_code=409, detail="Idempotency key already used for a different request")
        response.status_code = 200
        return _intent_dict(existing)
    values = req.model_dump()
    values["resource_metadata"] = values.pop("metadata")
    row = K3sProvisioningIntent(**values, request_hash=request_hash, state="pending")
    session.add(row)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (
            await session.execute(
                select(K3sProvisioningIntent).where(K3sProvisioningIntent.idempotency_key == req.idempotency_key)
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=503, detail="Provisioning intent storage unavailable")
        if not hmac.compare_digest(existing.request_hash, request_hash):
            raise HTTPException(status_code=409, detail="Idempotency key already used for a different request")
        response.status_code = 200
        return _intent_dict(existing)
    return _intent_dict(row)


@router.get("/provisioning-intents/{idempotency_key}")
async def get_k3s_provisioning_intent(
    idempotency_key: str = Path(..., pattern=_IDEMPOTENCY_KEY_RE.pattern),
    x_afterglow_k3s_provisioning_token: str | None = Header(None, alias="X-Afterglow-K3s-Provisioning-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_provisioning_token(x_afterglow_k3s_provisioning_token)
    row = (
        await session.execute(
            select(K3sProvisioningIntent).where(K3sProvisioningIntent.idempotency_key == idempotency_key)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Provisioning intent not found")
    return _intent_dict(row)


@router.post("/provisioning-intents/{idempotency_key}/submit")
async def submit_k3s_provisioning_intent(
    req: K3sProvisioningSubmitRequest,
    idempotency_key: str = Path(..., pattern=_IDEMPOTENCY_KEY_RE.pattern),
    x_afterglow_k3s_provisioning_token: str | None = Header(None, alias="X-Afterglow-K3s-Provisioning-Token"),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_provisioning_token(x_afterglow_k3s_provisioning_token)
    row = (
        await session.execute(
            select(K3sProvisioningIntent)
            .where(K3sProvisioningIntent.idempotency_key == idempotency_key)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Provisioning intent not found")
    if row.state == "succeeded":
        return {"state": "succeeded", "server_id": row.server_id, "volume_id": row.boot_volume_id, "name": row.name}
    if row.state == "submitting":
        recovered = await _recover_submitting_intent(session, row)
        if recovered is not None:
            await _invalidate_provisioning_caches(row.project_id)
            return recovered
    if row.state != "pending":
        raise HTTPException(status_code=409, detail={"state": row.state, "no_duplicate": True})
    row.state = "submitting"
    row.submitted_at = datetime.now(UTC)
    await session.commit()
    result = await _submit_intent(session, row, req.userdata)
    await _invalidate_provisioning_caches(row.project_id)
    return result
