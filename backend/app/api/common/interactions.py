"""Untrusted browser observations, not native operation or authorization evidence."""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import get_token_info
from app.rate_limit import limiter
from app.services import activity
from app.services.interaction_policy import canonical_page, interaction_id, public_page

router = APIRouter()
MAX_BODY_BYTES = 16 * 1024


class Interaction(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    kind: Literal["click", "submit", "navigation", "client_error", "request_failed"]
    page: str = Field(max_length=255)
    control: (
        Literal["button", "link", "form", "summary", "combobox", "checkbox", "switch", "option", "other"] | None
    ) = None
    ordinal: int | None = Field(default=None, ge=0, le=10000)
    destination: str | None = Field(default=None, max_length=255)
    interaction_id: str = Field(min_length=36, max_length=36)

    @field_validator("page")
    @classmethod
    def safe_page(cls, value: str) -> str:
        return canonical_page(value)

    @field_validator("destination")
    @classmethod
    def safe_destination(cls, value: str | None) -> str | None:
        return value if value in (None, "external") else canonical_page(value)

    @field_validator("interaction_id")
    @classmethod
    def safe_id(cls, value: str) -> str:
        parsed = interaction_id(value)
        if parsed is None:
            raise ValueError("Invalid interaction identifier")
        return parsed


class InteractionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    events: list[Interaction] = Field(min_length=1, max_length=20)


async def _bounded_batch(request: Request) -> InteractionBatch:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise HTTPException(415, "Interaction observations require JSON")
    length = request.headers.get("content-length")
    if length is not None:
        try:
            if int(length) < 0 or int(length) > MAX_BODY_BYTES:
                raise HTTPException(413, "Interaction batch is too large")
        except ValueError:
            raise HTTPException(400, "Invalid content length") from None
    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > MAX_BODY_BYTES:
            raise HTTPException(413, "Interaction batch is too large")
        body.extend(chunk)
    try:
        return InteractionBatch.model_validate(json.loads(body))
    except (ValueError, ValidationError, UnicodeDecodeError, RecursionError):
        # Never reflect Pydantic input/ctx or malformed JSON content.
        raise HTTPException(422, "Invalid interaction observations") from None


@router.post("/interactions", status_code=201)
@limiter.limit("60/minute")
async def ingest_interactions(request: Request) -> dict:
    batch = await _bounded_batch(request)
    authorization = request.headers.get("authorization")
    actor = {}
    if authorization is not None:
        # A supplied invalid or unavailable credential must never be downgraded
        # into anonymous ingestion. Actor and project come only from live auth.
        actor = await get_token_info(request, authorization, request.headers.get("x-project-id"))
    elif any(not public_page(event.page) for event in batch.events):
        raise HTTPException(401, "Authentication is required for this page")
    try:
        await activity.record_interactions(
            actor=actor, events=[event.model_dump(exclude_none=True) for event in batch.events]
        )
    except (activity.ActivityDatabaseUnavailable, SQLAlchemyError):
        raise HTTPException(503, "Activity database is unavailable") from None
    return {"accepted": len(batch.events)}
