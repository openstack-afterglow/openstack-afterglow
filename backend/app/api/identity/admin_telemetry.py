"""Mount under /api/v1/admin/telemetry; every request checks fresh admin authority."""

import asyncio
import json
import math
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_os_conn, require_admin
from app.services import telemetry_admin as svc

NO_STORE = {"Cache-Control": "no-store, private", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
MAX_BODY_BYTES = 256 * 1024


class TelemetryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                # Validation input and ctx can contain complete secret action URLs.
                response = JSONResponse({"detail": {"code": "telemetry_invalid_input"}}, status_code=400)
            except svc.Failure as exc:
                # Fixed service-owned code only. Returning directly deliberately
                # retains uncertain-write guidance through the global sanitizer.
                response = JSONResponse({"detail": {"code": exc.code}}, status_code=exc.http_status)
            except StarletteHTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            except Exception:
                response = JSONResponse({"detail": {"code": "telemetry_unavailable"}}, status_code=503)
            response.headers.update(NO_STORE)
            return response

        return guarded


router = APIRouter(route_class=TelemetryRoute, dependencies=[Depends(require_admin)])
State = Literal["ok", "alarm", "insufficient data"]


def reject_constant(_value):
    raise ValueError("nonfinite JSON")


async def body_json(request):
    buffer = bytearray()
    async for chunk in request.stream():
        if len(buffer) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(400, {"code": "telemetry_invalid_alarm"})
        buffer.extend(chunk)
    try:
        return json.loads(buffer, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise HTTPException(400, {"code": "telemetry_invalid_alarm"}) from None


@router.get("/aodh")
async def aodh(
    limit: int = Query(25, ge=1, le=100),
    marker: UUID | None = None,
    state: State | None = None,
    conn=Depends(get_os_conn),
):
    return await asyncio.to_thread(svc.aodh, conn, limit, str(marker) if marker else None, state)


@router.get("/aodh/alarms")
async def alarms(
    limit: int = Query(25, ge=1, le=100),
    marker: UUID | None = None,
    state: State | None = None,
    conn=Depends(get_os_conn),
):
    return await asyncio.to_thread(
        svc.list_alarms, svc.Transport(conn, "alarming"), limit, str(marker) if marker else None, state
    )


@router.get("/aodh/alarms/{alarm_id}")
async def alarm_detail(
    alarm_id: UUID,
    limit: int = Query(25, ge=1, le=100),
    marker: UUID | None = None,
    conn=Depends(get_os_conn),
):
    return await asyncio.to_thread(svc.alarm_detail, conn, str(alarm_id), limit, str(marker) if marker else None)


@router.post("/aodh/alarms", status_code=201)
async def create_alarm(request: Request, conn=Depends(get_os_conn)):
    body = await body_json(request)
    return await asyncio.to_thread(svc.mutate, conn, "POST", body=body)


@router.put("/aodh/alarms/{alarm_id}")
async def update_alarm(alarm_id: UUID, request: Request, conn=Depends(get_os_conn)):
    body = await body_json(request)
    return await asyncio.to_thread(svc.mutate, conn, "PUT", str(alarm_id), body)


@router.delete("/aodh/alarms/{alarm_id}", status_code=204)
async def delete_alarm(alarm_id: UUID, conn=Depends(get_os_conn)):
    await asyncio.to_thread(svc.mutate, conn, "DELETE", str(alarm_id))
    return Response(status_code=204)


@router.get("/gnocchi")
async def gnocchi(conn=Depends(get_os_conn)):
    return await asyncio.to_thread(svc.gnocchi, conn)


@router.get("/gnocchi/resources")
async def resources(
    type: str = Query("generic", min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"),
    limit: int = Query(25, ge=1, le=100),
    marker: UUID | None = None,
    conn=Depends(get_os_conn),
):
    return await asyncio.to_thread(
        svc.page,
        svc.Transport(conn, "metric"),
        "/resource/" + quote(type, safe=""),
        limit,
        str(marker) if marker else None,
        svc.resource,
        "id",
    )


@router.get("/gnocchi/metrics")
async def metrics(
    limit: int = Query(25, ge=1, le=100),
    marker: UUID | None = None,
    conn=Depends(get_os_conn),
):
    return await asyncio.to_thread(
        svc.page,
        svc.Transport(conn, "metric"),
        "/metric",
        limit,
        str(marker) if marker else None,
        svc.metric,
        "id",
    )


@router.get("/gnocchi/metrics/{metric_id}/measures")
async def measures(
    metric_id: UUID,
    hours: int = Query(1, ge=1, le=168),
    aggregation: str = Query("mean", min_length=1, max_length=64, pattern=r"^(rate:)?([a-z]+|[0-9]+(\.[0-9]+)?pct)$"),
    granularity: float | None = Query(None, gt=0),
    conn=Depends(get_os_conn),
):
    if granularity is not None and not math.isfinite(granularity):
        raise HTTPException(400, {"code": "telemetry_invalid_input"})
    return await asyncio.to_thread(svc.measures, conn, str(metric_id), hours, aggregation, granularity)
