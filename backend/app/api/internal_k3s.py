"""Internal K3s service endpoints for Afterglow integration."""

from __future__ import annotations

import asyncio
import hmac
import logging
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.services import nova
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
