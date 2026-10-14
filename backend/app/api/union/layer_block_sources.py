"""Admin-only publication of exact sealed artifact bytes, not arbitrary images."""

from __future__ import annotations

import asyncio
import hashlib
import re
import tempfile
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from keystoneauth1.exceptions import ClientException
from openstack.exceptions import SDKException
from requests.exceptions import RequestException
from sqlalchemy import select

from app.api.deps import require_admin
from app.database import get_session_factory
from app.models.db import LayerArtifact
from app.services import glance, layer_block
from app.services.keystone import get_service_project_connection

router = APIRouter(dependencies=[Depends(require_admin)])


def _entry(row) -> dict:
    return {
        key: getattr(row, key)
        for key in (
            "id",
            "parent_id",
            "chain_id",
            "blob_digest",
            "size_bytes",
            "is_sealed",
            "digest_state",
            "block_source",
        )
    }


async def _locked(session, artifact_id):
    row = (
        await session.execute(
            select(LayerArtifact)
            .where(LayerArtifact.id == artifact_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "artifact not found")
    try:
        layer_block.artifact_identity(_entry(row))
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return row


async def verify_upload(request, output, entry) -> None:
    """Bound spool length while hashing; complete verification precedes cloud allocation."""
    digest = hashlib.sha256()
    length = 0
    async for chunk in request.stream():
        length += len(chunk)
        if length > entry["size_bytes"]:
            raise HTTPException(422, "upload length exceeds sealed artifact")
        digest.update(chunk)
        await asyncio.to_thread(output.write, chunk)
    if length != entry["size_bytes"] or "sha256:" + digest.hexdigest() != entry["blob_digest"]:
        raise HTTPException(422, "upload SHA256/length differs from sealed artifact")
    await asyncio.to_thread(output.seek, 0)


def _new_source(entry, owner, members, store_id, abandoned=None):
    return {
        **layer_block.artifact_identity(entry),
        "state": "pending",
        "image_id": str(uuid.uuid4()),
        "upload_id": str(uuid.uuid4()),
        "owner_project_id": owner,
        "member_project_ids": members,
        "store_id": store_id,
        "abandoned_image_ids": list(abandoned or []),
    }


async def _reserve(artifact_id, entry, owner, members, store_id):
    async with get_session_factory()() as session:
        row = await _locked(session, artifact_id)
        current = _entry(row)
        if layer_block.artifact_identity(current) != layer_block.artifact_identity(entry):
            raise HTTPException(409, "sealed artifact changed during upload")
        source = row.block_source
        if source:
            identity = layer_block.artifact_identity(entry)
            if any(source.get(key) != value for key, value in identity.items()):
                raise HTTPException(409, "cannot replace published source with different bytes/lineage")
            if (
                source.get("owner_project_id") != owner
                or source.get("member_project_ids") != members
                or source.get("store_id") != store_id
            ):
                raise HTTPException(
                    409, "source owner/members/store are immutable; use the existing publication identity"
                )
        else:
            source = _new_source(entry, owner, members, store_id)
            row.block_source = source
        # Recoverable UUID is durable before even the Glance metadata allocation.
        await session.commit()
        return dict(source)


async def _publish(artifact_id, conn, entry, source, data):
    async with get_session_factory()() as session:
        row = await _locked(session, artifact_id)
        if row.block_source != source:
            raise HTTPException(409, "source publication changed; retry with its current identity")
        if layer_block.artifact_identity(_entry(row)) != layer_block.artifact_identity(entry):
            raise HTTPException(409, "sealed artifact identity changed")
        image = await asyncio.to_thread(glance.get_source_image, conn, source["image_id"])
        if source["state"] == "ready" and image is None:
            raise HTTPException(409, "immutable source is missing; replacement is forbidden")
        if image is not None:
            layer_block.validate_source_image(entry, source, image, active=False)
            if image.get("status") == "killed" and source["state"] == "pending":
                # Retain the failed protected image for recovery/audit; never delete
                # anything that could be in-flight. Reserve the new attempt first.
                abandoned = source.get("abandoned_image_ids", []) + [source["image_id"]]
                source = _new_source(
                    entry, source["owner_project_id"], source["member_project_ids"], source["store_id"], abandoned
                )
                row.block_source = source
                await session.commit()
                row = await _locked(session, artifact_id)
                if row.block_source != source:
                    raise HTTPException(409, "source attempt changed")
                image = None
        if image is None:
            image = await asyncio.to_thread(
                glance.allocate_source_image,
                conn,
                source["image_id"],
                f"layer-artifact-{artifact_id}",
                layer_block.source_properties(entry, source),
            )
            layer_block.validate_source_image(entry, source, image, active=False)
        if image.get("status") == "queued" and source["state"] == "pending":
            await asyncio.to_thread(
                glance.upload_source_image, conn, source["image_id"], data, entry["size_bytes"], source["store_id"]
            )
            image = await asyncio.to_thread(glance.get_source_image, conn, source["image_id"])
        if image.get("status") != "active":
            raise HTTPException(409, "source upload incomplete; retry after provider finishes; no unsafe replacement")
        layer_block.validate_source_image(entry, source, image)
        await asyncio.to_thread(
            glance.verify_source_bytes, conn, source["image_id"], entry["blob_digest"], entry["size_bytes"]
        )
        existing = await asyncio.to_thread(glance.list_image_members, conn, source["image_id"])
        existing_ids = {member["member_id"] for member in existing}
        if existing_ids - set(source["member_project_ids"]):
            raise HTTPException(409, "unexpected source members; refusing publication")
        for member_id in source["member_project_ids"]:
            if member_id not in existing_ids:
                await asyncio.to_thread(glance.add_image_member, conn, source["image_id"], member_id)
        row.block_source = {**source, "state": "ready"}
        await session.commit()
        return row.block_source


@router.put("/artifacts/{artifact_id}/block-source")
async def publish_block_source(
    artifact_id: int,
    request: Request,
    store_id: str = Query(..., min_length=1, max_length=255),
    member_project_id: list[str] = Query(default=[]),
) -> dict:
    """Raw octet-stream exact squashfs bytes; members must accept through Glance as themselves."""
    if any(not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", value) for value in member_project_id):
        raise HTTPException(422, "invalid member project id")
    members = sorted(set(member_project_id))
    async with get_session_factory()() as session:
        row = await _locked(session, artifact_id)
        entry = _entry(row)
    # TemporaryFile is disk-backed, bounded by sealed length, and closed on failure.
    with tempfile.TemporaryFile(mode="w+b") as data:
        await verify_upload(request, data, entry)
        conn = await asyncio.to_thread(get_service_project_connection)
        try:
            owner = layer_block.project_id(conn)
            await asyncio.to_thread(glance.validate_rbd_store, conn, store_id)
            source = await _reserve(artifact_id, entry, owner, members, store_id)
            return await _publish(artifact_id, conn, entry, source, data)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        except (SDKException, ClientException, RequestException) as exc:
            raise HTTPException(
                502, "source provider operation failed; durable upload identity retained for retry"
            ) from exc
        finally:
            await asyncio.to_thread(conn.close)


@router.get("/artifacts/{artifact_id}/block-source")
async def get_block_source(artifact_id: int) -> dict:
    async with get_session_factory()() as session:
        row = await session.get(LayerArtifact, artifact_id)
        if row is None:
            raise HTTPException(404, "artifact not found")
        return {"block_source": row.block_source}
