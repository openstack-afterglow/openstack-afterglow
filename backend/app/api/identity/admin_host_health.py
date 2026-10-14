"""Admin-only host-health snapshots; HTTP requests never trigger collection."""

from fastapi import APIRouter, Depends, Response

from app.api.deps import require_admin
from app.services import host_health
from app.services.host_health import HostHealthSnapshot

router = APIRouter(dependencies=[Depends(require_admin)])


@router.get("/host-health", response_model=HostHealthSnapshot)
async def get_host_health(response: Response) -> dict:
    response.headers["Cache-Control"] = "no-store"
    return await host_health.get_snapshot()
