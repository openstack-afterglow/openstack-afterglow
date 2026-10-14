"""Narrow per-host token routes and a pre-parse payload limit."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Response

from app.models.infrastructure_topology import HostId, Observation, TraceResult
from app.services import infrastructure_topology as service

MAX_BODY_BYTES = 256 * 1024
router = APIRouter()


def observer(host_id: HostId, authorization: Annotated[str | None, Header()] = None):
    return service.authenticate_observer(host_id, authorization)


@router.post("/host-observations/{host_id}/reports", status_code=202)
async def report(host_id: HostId, body: Observation, response: Response, settings=Depends(observer)):
    response.headers["Cache-Control"] = "no-store"
    return await service.ingest(host_id, body, settings=settings)


@router.get("/host-observations/{host_id}/jobs")
async def poll(host_id: HostId, response: Response, claim: bool = True, settings=Depends(observer)):
    """Busy observers use claim=false to refresh peers without taking a job."""
    response.headers["Cache-Control"] = "no-store"
    return await service.poll_job(host_id, claim=claim, settings=settings)


@router.post("/host-observations/{host_id}/jobs/{job_id}/result", status_code=202)
async def result(host_id: HostId, job_id: UUID, body: TraceResult, response: Response, settings=Depends(observer)):
    response.headers["Cache-Control"] = "no-store"
    return await service.finish_trace(host_id, str(job_id), body, settings=settings)


class HostObservationBodyLimit:
    """Reject excessive chunked/declared bodies before JSON/Pydantic allocation.

    Install outside FastAPI route execution using app.add_middleware(...).
    The bounded body is replayed once; all other paths stream untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/monitoring/host-observations/"):
            return await self.app(scope, receive, send)
        headers = dict(scope.get("headers", []))
        if headers.get(b"content-encoding", b"identity") != b"identity":
            return await self._reject(send, 415, b'{"detail":"content_encoding_not_supported"}')
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await self._reject(send, 400, b'{"detail":"content_length_invalid"}')
        if not 0 <= declared <= MAX_BODY_BYTES:
            return await self._reject(send, 413, b'{"detail":"observation_payload_too_large"}')
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                return await self._reject(send, 413, b'{"detail":"observation_payload_too_large"}')
            body.extend(chunk)
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send, status, body):
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", b"application/json"), (b"cache-control", b"no-store")],
            }
        )
        await send({"type": "http.response.body", "body": body})
