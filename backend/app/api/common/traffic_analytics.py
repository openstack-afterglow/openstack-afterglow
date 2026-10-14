"""Admin aggregate reads and a separate, narrowly scoped frontend service writer."""

import hmac
import json
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import ValidationError

from app.api.deps import require_admin
from app.config import get_settings
from app.models.traffic_analytics import LegacyTrafficEvent, OriginFilter, TrafficEvent, TrafficSnapshot
from app.services.traffic_analytics import record_event, snapshot

admin_router = APIRouter(dependencies=[Depends(require_admin)])
ingest_router = APIRouter()


@admin_router.get("", response_model=TrafficSnapshot)
async def traffic_snapshot(
    response: Response,
    range: Literal["24h", "7d", "30d"] = Query("24h"),
    source: Literal["backend", "frontend"] = Query("backend"),
    origin: OriginFilter = Query("all"),
):
    response.headers["Cache-Control"] = "no-store"
    return await snapshot(source, range, origin)


def require_frontend_writer(request: Request):
    settings = get_settings().traffic_analytics
    if not settings.enabled:
        raise HTTPException(404, "Traffic observation is disabled")
    configured = settings.frontend_ingest_key.get_secret_value()
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer ") or not hmac.compare_digest(
        authorization[7:].encode(), configured.encode()
    ):
        raise HTTPException(401, "Invalid traffic writer credential")


@ingest_router.post("/events", dependencies=[Depends(require_frontend_writer)])
async def ingest_traffic(request: Request, response: Response):
    # Authenticate before consuming input. No automatic FastAPI validation response
    # can echo an IP/secret-bearing body, and chunked bodies are bounded too.
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > 2048:
            raise HTTPException(413, "Traffic event exceeds size limit")
        body.extend(chunk)
    try:
        data = json.loads(body)
        # Backend-first rollout: old reporters are accepted only as unclassified.
        # New v2 reporters must never be deployed ahead of v2 ingestion backends.
        model = TrafficEvent if isinstance(data, dict) and "schema_version" in data else LegacyTrafficEvent
        event = model.model_validate(data)
    except (ValidationError, ValueError):
        raise HTTPException(422, "Invalid traffic observation") from None
    if abs(time.time() - event.at) > 120:
        raise HTTPException(422, "Traffic observation outside freshness window")
    accepted = await record_event(event, "frontend")
    response.headers["Cache-Control"] = "no-store"
    if not accepted:
        raise HTTPException(503, "Traffic aggregation unavailable or capacity exceeded")
    return {"accepted": True}
