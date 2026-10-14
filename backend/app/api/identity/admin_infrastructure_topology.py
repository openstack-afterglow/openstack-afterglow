"""Admin-only inventory, observed evidence, and configured destination jobs."""

from fastapi import APIRouter, Depends, Response

from app.api.deps import require_admin
from app.models.infrastructure_topology import HostId, TraceRequest
from app.services import infrastructure_topology as service

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/infrastructure-topology")
async def get_infrastructure_topology(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await service.snapshot()


@router.post("/infrastructure-topology/hosts/{host_id}/traces", status_code=202)
async def create_trace(host_id: HostId, body: TraceRequest, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return await service.submit_trace(host_id, body.target)
