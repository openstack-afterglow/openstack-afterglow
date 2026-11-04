"""Strict opt-in browser observations; no implicit credential downgrade."""

from __future__ import annotations

import json
import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_token_info
from app.models.experience import ExperienceBatch
from app.rate_limit import limiter
from app.services import experience
from app.services.activity import _audit_ctx
from app.services.interaction_policy import public_page
from app.utils.version import read_app_version

MAX_BODY_BYTES = 32768


def require_experience() -> None:
    if not experience.enabled():
        raise HTTPException(404, "Not found")


router = APIRouter(dependencies=[Depends(require_experience)])


async def _bounded_batch(request: Request) -> ExperienceBatch:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Experience observations require JSON")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            size = int(length)
        except ValueError:
            raise HTTPException(400, "Invalid content length") from None
        if size < 0 or size > MAX_BODY_BYTES:
            raise HTTPException(413, "Experience batch is too large")
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Experience batch is too large")
        body.extend(chunk)
    try:
        return ExperienceBatch.model_validate(json.loads(body))
    except (ValueError, ValidationError, UnicodeDecodeError, RecursionError):
        raise HTTPException(422, "Invalid experience observations") from None


@router.get("/experience-contract")
async def contract() -> dict:
    return {
        "schema_version": 2,
        "enabled": True,
        "backend_build": read_app_version(),
        "redaction_revision": 1,
        "max_batch_events": 20,
        "max_body_bytes": MAX_BODY_BYTES,
    }


@router.post("/experience-events", status_code=201)
@limiter.limit("60/minute")
async def ingest_events(request: Request, response: Response) -> dict:
    batch = await _bounded_batch(request)
    actor = {}
    authorization = request.headers.get("authorization")
    if authorization is not None:
        actor = await get_token_info(request, authorization, request.headers.get("x-project-id"))
    elif any(not public_page(event.route) for event in batch.events):
        raise HTTPException(401, "Authentication is required for this page")
    # Diagnostic routes are excluded from recursive activity middleware. Reuse
    # its server-owned ID when present; otherwise mint this receipt's own ID.
    candidate = getattr(request.state, "request_id", None) or (_audit_ctx.get() or {}).get("request_id")
    request_id = (
        candidate
        if isinstance(candidate, str) and re.fullmatch(r"req-[a-f0-9]{32}", candidate)
        else f"req-{uuid4().hex}"
    )
    response.headers["X-Request-Id"] = request_id
    try:
        return await experience.ingest(actor=actor, events=batch.events, request_id=request_id)
    except experience.ExperienceConflict:
        raise HTTPException(409, "Experience event identity conflict") from None
    except ValueError:
        raise HTTPException(422, "Invalid experience context") from None
    except (experience.ExperienceUnavailable, SQLAlchemyError):
        raise HTTPException(503, "Experience database is unavailable") from None
