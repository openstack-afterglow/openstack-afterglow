"""Read-only managed catalog and immutable published environment snapshots.

Only explicit POST admission creates rows. Public DTOs never serialize provider
paths, recipes, resource snapshots or service credentials.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.config import get_settings
from app.database import get_session_factory
from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerImportJob, LayerProfile
from app.services.palimpsest_digest import compute_chain_id, normalize_digest


def factory():
    value = get_session_factory()
    if value is None:
        raise HTTPException(503, "Managed catalog database is unavailable")
    return value


def page(items, offset, limit, *, source=None):
    more = len(items) > limit
    result = {
        "items": items[:limit],
        "offset": offset,
        "has_more": more,
        "next_offset": offset + limit if more else None,
    }
    if source is not None:
        result["source"] = source
    return result


def iso(value):
    if value is None:
        return None
    return value.replace(tzinfo=UTC).isoformat() if value.tzinfo is None else value.astimezone(UTC).isoformat()


async def ancestry(session, row, *, public=False):
    chain, seen = [], set()
    while row is not None:
        if row.id in seen or (public and not (row.is_published and row.is_sealed)):
            return list(reversed(chain)), False
        seen.add(row.id)
        chain.append(row)
        if row.parent_id is None:
            return list(reversed(chain)), True
        row = await session.get(LayerArtifact, row.parent_id)
    return list(reversed(chain)), False


async def origin(session, row):
    cache = session.info.setdefault("catalog_origins", {})
    if row.id in cache:
        return cache[row.id]
    result = {
        "kind": "unknown",
        "source": "unknown",
        "evidence": "unrecorded",
        "build_id": None,
        "job_id": None,
        "revision": None,
    }
    cache[row.id] = result
    if row.build_id and "catalog_origin_builds" not in session.info:
        session.info["catalog_origin_builds"] = {
            build.id: build for build in (await session.execute(select(LayerBuild.id, LayerBuild.kind))).all()
        }
    build = session.info.get("catalog_origin_builds", {}).get(row.build_id)
    # The artifact's own build link is authority, never a referencing cached job.
    if build is None:
        return result
    result.update(
        kind="build",
        source="unknown" if build.kind in {"dockerfile", "dockerfile-root"} else "recipe",
        evidence="recorded",
        build_id=str(build.id),
    )
    if "catalog_origin_jobs" not in session.info:
        # Session/request-owned, metadata-only projection, loaded once for the
        # entire page including ancestry/children. Never load recipe/config text.
        session.info["catalog_origin_jobs"] = (
            await session.execute(
                select(
                    LayerImportJob.id,
                    LayerImportJob.source_type,
                    LayerImportJob.artifact_ids,
                    LayerImportJob.build_ids,
                    LayerImportJob.commit_sha,
                    LayerImportJob.dockerfile_digest,
                ).order_by(LayerImportJob.id)
            )
        ).all()
    for job in session.info["catalog_origin_jobs"]:
        if row.id in (job.artifact_ids or []) and build.id in (job.build_ids or []):
            result.update(
                source={"inline_dockerfile": "dockerfile-inline", "github_dockerfile": "github-dockerfile"}.get(
                    job.source_type, "unknown"
                ),
                job_id=str(job.id),
                revision=job.commit_sha or job.dockerfile_digest,
            )
            break
    return result


async def layer(session, row):
    chain, complete = await ancestry(session, row)
    parent = await session.get(LayerArtifact, row.parent_id) if row.parent_id else None
    return {
        "id": str(row.id),
        "name": row.name,
        "blob_digest": row.blob_digest,
        "parent_id": str(row.parent_id) if row.parent_id else None,
        "parent_digest": parent.blob_digest if parent else None,
        "kind": row.kind,
        "arch": None,
        "ubuntu_base": row.ubuntu_base,
        "size_bytes": row.size_bytes,
        "created_at": iso(row.created_at),
        "project_id": None,
        "visibility": "public" if row.is_published else "private",
        "chain_complete": complete
        and all(x.is_sealed and x.digest_state == "ready" and normalize_digest(x.blob_digest) for x in chain),
        "origin": await origin(session, row),
    }


async def managed_layers(q, offset, limit):
    async with factory()() as session:
        stmt = select(LayerArtifact)
        if q:
            stmt = stmt.where(
                or_(
                    LayerArtifact.name.icontains(q, autoescape=True),
                    LayerArtifact.blob_digest.icontains(q, autoescape=True),
                )
            )
        rows = (
            (await session.execute(stmt.order_by(LayerArtifact.id.desc()).offset(offset).limit(limit + 1)))
            .scalars()
            .all()
        )
        return page([await layer(session, row) for row in rows], offset, limit, source="managed")


async def managed_detail(identity):
    if not identity.isdecimal() or int(identity) <= 0:
        raise HTTPException(422, "Managed layer ID must be a positive decimal ID")
    async with factory()() as session:
        row = await session.get(LayerArtifact, int(identity))
        if row is None:
            raise HTTPException(404, "Managed layer not found")
        chain, _ = await ancestry(session, row)
        children = (
            (
                await session.execute(
                    select(LayerArtifact).where(LayerArtifact.parent_id == row.id).order_by(LayerArtifact.id).limit(51)
                )
            )
            .scalars()
            .all()
        )
        profiles = (await session.execute(select(LayerProfile.name, LayerProfile.layers))).all()
        names = {
            name
            for profile in profiles
            for name in (profile.layers if isinstance(profile.layers, list) else [])
            if isinstance(name, str)
        }
        # Resolve latest names in one metadata query, not once per profile.
        ranked = (
            select(
                LayerArtifact.id.label("artifact_id"),
                func.row_number()
                .over(
                    partition_by=LayerArtifact.name, order_by=(LayerArtifact.created_at.desc(), LayerArtifact.id.desc())
                )
                .label("position"),
            )
            .where(LayerArtifact.name.in_(names), LayerArtifact.is_sealed.is_(True))
            .subquery()
        )
        selected = (
            (
                await session.execute(
                    select(LayerArtifact)
                    .join(ranked, ranked.c.artifact_id == LayerArtifact.id)
                    .where(ranked.c.position == 1)
                )
            )
            .scalars()
            .all()
            if names
            else []
        )
        memberships = {}
        for artifact in selected:
            members, _ = await ancestry(session, artifact)
            memberships[artifact.name] = {member.id for member in members}
        bundles = [
            profile.name
            for profile in profiles
            if any(
                row.id in memberships.get(name, set())
                for name in (profile.layers if isinstance(profile.layers, list) else [])
                if isinstance(name, str)
            )
        ]
        return {
            **await layer(session, row),
            "ancestors": [await layer(session, x) for x in chain if x.id != row.id],
            "children": [await layer(session, x) for x in children[:50]],
            "children_has_more": len(children) > 50,
            "bundles": bundles,
        }


async def published_snapshot(session, profile_id, *, lock=False):
    """Resolve latest exact names, then all published ancestors; no old-public fallback."""
    stmt = select(LayerProfile).where(LayerProfile.id == profile_id)
    if lock:
        stmt = stmt.with_for_update()
    profile = (await session.execute(stmt)).scalar_one_or_none()
    if profile is None or not profile.is_published:
        raise HTTPException(404, "Published environment not found")
    if (
        not isinstance(profile.layers, list)
        or not profile.layers
        or any(not isinstance(n, str) for n in profile.layers)
    ):
        raise HTTPException(409, "Published environment has no valid layer selection")
    selected = []
    for name in profile.layers:
        stmt = (
            select(LayerArtifact)
            .where(LayerArtifact.name == name, LayerArtifact.is_sealed.is_(True))
            .order_by(LayerArtifact.created_at.desc(), LayerArtifact.id.desc())
            .limit(1)
        )
        if lock:
            stmt = stmt.with_for_update()
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise HTTPException(409, "Published environment layer is unavailable")
        selected.append(row)
    selected_ids = [row.id for row in selected]
    if len(set(selected_ids)) != len(selected_ids):
        raise HTTPException(409, "Published environment has duplicate layers")
    lineage, included = [], set()
    for row in reversed(selected):
        chain, complete = await ancestry(session, row, public=True)
        if not complete:
            raise HTTPException(409, "Published environment ancestry is unavailable")
        if lock:
            # Same locks as artifact publication/deletion; refreshed rows below.
            ids = [x.id for x in chain]
            locked_rows = (
                (
                    await session.execute(
                        select(LayerArtifact)
                        .where(LayerArtifact.id.in_(ids))
                        .order_by(LayerArtifact.id)
                        .with_for_update()
                        .execution_options(populate_existing=True)
                    )
                )
                .scalars()
                .all()
            )
            by_id = {art.id: art for art in locked_rows}
            if set(by_id) != set(ids):
                raise HTTPException(409, "Published environment ancestry changed during admission")
            chain = [by_id[identity] for identity in ids]
        for art in chain:
            if art.id not in included:
                if (
                    not art.is_published
                    or not art.is_sealed
                    or art.digest_state != "ready"
                    or not normalize_digest(art.blob_digest)
                ):
                    raise HTTPException(409, "Published environment contains an unavailable layer")
                included.add(art.id)
                lineage.append(art)
    if selected_ids != [art.id for art in reversed(lineage) if art.id in set(selected_ids)]:
        raise HTTPException(409, "Published environment precedence conflicts with ancestry")
    # Multiple roots/branches cannot be advertised as one complete content chain.
    parent_chain = None
    for index, art in enumerate(lineage):
        expected_parent = lineage[index - 1].id if index else None
        if art.parent_id != expected_parent or art.chain_id != compute_chain_id(parent_chain, art.blob_digest):
            raise HTTPException(409, "Published environment chain identity is inconsistent")
        parent_chain = art.chain_id
    from app.services.layer_build import _consumer_artifact_entry

    entries = [_consumer_artifact_entry(row, get_settings()) for row in lineage]
    # No legacy configured image fallback: only a durable common recorded image.
    image_fields = (
        "base_image_id",
        "base_image_checksum",
        "base_image_os_hash_algo",
        "base_image_os_hash_value",
        "ubuntu_base",
    )
    from app.services.layer_build import _LAYER_NAME_RE

    compatible = _LAYER_NAME_RE.fullmatch(profile.name) is not None and all(
        row.base_image_id and row.share_id and row.sqsh_filename for row in lineage
    )
    compatible = compatible and all(len({getattr(row, field) for row in lineage}) == 1 for field in image_fields)
    root_mode = any(row.kind in {"dockerfile-root", "dockerfile"} for row in lineage)
    compatible = compatible and (
        not root_mode or (lineage[0].kind == "dockerfile-root" and all(x.kind == "dockerfile" for x in lineage[1:]))
    )
    content = {
        "profile_id": profile.id,
        "name": profile.name,
        "layers": profile.layers,
        "updated_at": iso(profile.updated_at),
        "artifacts": entries,
    }
    revision = (
        "sha256:" + hashlib.sha256(json.dumps(content, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    )
    return {
        "profile": profile,
        "artifacts": entries,
        "revision": revision,
        "cloud_supported": bool(compatible),
        "cloud_reason": None
        if compatible
        else "Recorded profile name, common base image, NFS source or runtime lineage is unavailable",
    }


def environment(snapshot):
    entries, profile = snapshot["artifacts"], snapshot["profile"]
    return {
        "source": "managed",
        "id": str(profile.id),
        "name": profile.name,
        "kind": "layer-bundle",
        "blob_digest": entries[-1]["blob_digest"],
        "chain_id": snapshot["revision"],
        "revision": snapshot["revision"],
        "arch": None,
        "ubuntu_base": entries[-1]["ubuntu_base"],
        "size_bytes": sum(x["size_bytes"] for x in entries)
        if all(x["size_bytes"] is not None for x in entries)
        else None,
        "created_at": iso(profile.created_at),
        "visibility": "public",
        "layer_count": len(entries),
        "chain_complete": True,
        "download_allowed": False,
        "base_image_digest": None,
        "local_supported": False,
        "local_reason": "hub-registration-required",
        "cloud_supported": snapshot["cloud_supported"],
        "cloud_reason": snapshot["cloud_reason"],
    }


async def environments(q, offset, limit):
    async with factory()() as session:
        stmt = select(LayerProfile).where(LayerProfile.is_published.is_(True))
        if q:
            stmt = stmt.where(LayerProfile.name.icontains(q, autoescape=True))
        profiles = (
            (await session.execute(stmt.order_by(LayerProfile.id).offset(offset).limit(limit + 1))).scalars().all()
        )
        candidates = profiles[:limit]
        items = []
        for profile in candidates:
            try:
                items.append(environment(await published_snapshot(session, profile.id)))
            except HTTPException as exc:
                if exc.status_code not in {404, 409}:
                    raise
                # Invalid/private chains are not public assets, even in partial form.
        has_more = len(profiles) > limit
        return {
            "items": items,
            "offset": offset,
            "has_more": has_more,
            "next_offset": offset + len(candidates) if has_more else None,
        }


def consume_dto(row):
    snapshot = row.resource_snapshot or {}
    return {
        "consume_id": row.id,
        "server_id": row.server_id,
        "server_name": row.server_name,
        "project_id": row.project_id,
        "revision": snapshot.get("catalog_revision"),
        "status": row.status,
        "ready": row.status == "active",
        "transport": row.transport,
        "created_at": iso(row.created_at),
        "completed_at": iso(row.completed_at),
        "error_message": "Provisioning did not complete; inspect this job before retrying"
        if row.status in {"error", "indeterminate"}
        else None,
    }


async def consume_status(consume_id, project_id):
    async with factory()() as session:
        row = (
            await session.execute(
                select(LayerConsume).where(LayerConsume.id == consume_id, LayerConsume.project_id == project_id)
            )
        ).scalar_one_or_none()
        if row is None or not (row.resource_snapshot or {}).get("catalog_revision"):
            raise HTTPException(404, "Environment consume not found")
        result = consume_dto(row)
        if row.status == "creating":
            from app.services.cache import _get_redis

            try:
                redis = await _get_redis()
                live = await redis.get(f"afterglow:catalog-consume:{consume_id}:lease:consume:{consume_id}")
            except Exception as exc:
                raise HTTPException(503, "Consume worker authority is unavailable") from exc
            if not live:
                result.update(
                    status="indeterminate",
                    ready=False,
                    error_message="The provisioning owner is no longer present; inspect this job before retrying",
                )
        return result
