"""Exact caller-owned catalog reclamation, including interrupted/serverless jobs.

SQL ownership and immutable source receipts plus non-replayable allocation
journals authorize cleanup, never mutable publication or IP/name-only matching.
CREATE outcomes are observed, never replayed. A new explicit cleanup may repeat
an idempotent DELETE only after fresh exact ownership observation and SQL lock.
Blockers release only after every exact native absence is confirmed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException
from openstack.exceptions import ResourceNotFound
from sqlalchemy import select

from app.models.db import LayerConsume
from app.services import palimpsest_catalog as catalog
from app.services.work_dispatcher import close_connection, open_connection, run_sync


@asynccontextmanager
async def _cleanup_session():
    """Keep the SQL owner lock through provider drain, including uncertain exits."""
    from app.services.build_work import drain

    async with catalog.factory()() as session:
        try:
            yield session
        except BaseException:
            try:
                await drain(asyncio.create_task(session.commit()))
            except Exception as exc:
                logging.getLogger(__name__).warning(
                    "Catalog cleanup outcome persistence failed (%s)", type(exc).__name__
                )
            raise
        else:
            try:
                await drain(asyncio.create_task(session.commit()))
            except Exception as exc:
                raise HTTPException(
                    503, "Catalog cleanup persistence is unavailable; completion is not confirmed"
                ) from exc


@dataclass(frozen=True)
class McpCleanupAuthority:
    connection: object
    user_id: str
    project_id: str


def _catalog_id(server):
    from app.services.layer_consume_resources import value

    metadata = value(server, "metadata")
    value = metadata.get("afterglow_catalog_consume_id") if isinstance(metadata, dict) else None
    if value is None:
        return None
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal() or int(value) <= 0:
        raise HTTPException(409, "Catalog consume metadata is inconsistent")
    return int(value)


async def lookup_catalog_consume(instance_id, server, info):
    """Native metadata is a hint; an exact durable owner receipt cannot be bypassed."""
    from app.services.layer_consume_resources import value

    owner = value(server, "project_id") or value(server, "tenant_id")
    caller = info.project_id if isinstance(info, McpCleanupAuthority) else info.get("project_id")
    admin = not isinstance(info, McpCleanupAuthority) and info.get("is_system_admin") is True
    if not owner or (not admin and owner != caller):
        raise HTTPException(404, "Instance not found")
    hint = _catalog_id(server)
    if catalog.get_session_factory() is None:
        raise HTTPException(503, "Catalog ownership authority is unavailable")
    try:
        async with catalog.factory()() as session:
            rows = (
                (
                    await session.execute(
                        select(LayerConsume).where(
                            LayerConsume.server_id == instance_id, LayerConsume.project_id == owner
                        )
                    )
                )
                .scalars()
                .all()
            )
            rows = [row for row in rows if (row.resource_snapshot or {}).get("catalog_revision")]
            if not rows and hint is not None:
                row = (
                    await session.execute(
                        select(LayerConsume).where(
                            LayerConsume.id == hint, LayerConsume.project_id == owner, LayerConsume.server_id.is_(None)
                        )
                    )
                ).scalar_one_or_none()
                if row is not None and (row.resource_snapshot or {}).get("catalog_revision"):
                    rows = [row]  # The allocating journal/native marker still must bind it.
            if not rows:
                if hint is not None:
                    raise HTTPException(404, "Instance not found")
                return None
            if len(rows) != 1:
                raise HTTPException(409, "Catalog server ownership receipts are ambiguous")
            await _authority(info, owner)
            if hint != rows[0].id:
                raise HTTPException(409, "Catalog server marker differs from its durable ownership receipt")
            return rows[0].id
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(503, "Catalog ownership authority is unavailable") from exc


async def _authority(info, owner):
    if isinstance(info, McpCleanupAuthority):
        from app.api.deps import require_project_write
        from app.services.mcp_control_plane.sdk import check_mutation_dispatch
        from app.services.project_service import get_project_access

        check_mutation_dispatch()
        if not info.user_id:
            raise HTTPException(403, "MCP native credential owner is unavailable")
        if info.project_id != owner:
            raise HTTPException(403, "MCP cleanup project differs from catalog owner")
        access = await run_sync(info.connection.session.auth.get_access, info.connection.session)
        if access.user_id != info.user_id or access.project_id != owner:
            raise HTTPException(403, "MCP native credential owner/project changed")
        credential_roles = getattr(access, "role_names", None)
        if not isinstance(credential_roles, list):
            raise HTTPException(503, "MCP native credential roles are unavailable")
        require_project_write({"project_id": owner, "roles": credential_roles, "is_system_admin": False})
        current = await get_project_access(owner, info.user_id)
        require_project_write({"project_id": owner, "roles": current["roles"], "is_system_admin": False})
        return
    if info.get("is_system_admin") is True:
        from app.api.deps import require_admin

        await require_admin(info)
    else:
        from app.services.palimpsest_catalog_consume import current_writer

        if info.get("project_id") != owner:
            raise HTTPException(403, "Catalog consume belongs to another project")
        await current_writer(info)


async def _submission(redis, consume_id, step):
    raw = await redis.get(f"afterglow:builds:journal:consume:{consume_id}:submit:consumer:{consume_id}:{step}")
    return json.loads(raw) if raw else None


def _recorded_id(state, submitted, consume_id, step):
    return (state.get("observed_ids") or {}).get(f"consumer:{consume_id}:{step}") or (
        (submitted or {}).get("result") or {}
    ).get("id")


async def _context(session, consume_id, info):
    from app.services.cache import _get_redis

    row = (
        await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Catalog consume not found")
    snapshot = row.resource_snapshot or {}
    if not row.project_id or row.transport != "nfs" or not snapshot.get("catalog_revision"):
        raise HTTPException(409, "Catalog consume ownership receipt is unavailable")
    if (snapshot.get("consumer_project") or {}).get("id") != row.project_id:
        raise HTTPException(409, "Catalog consume owner snapshot is inconsistent")
    await _authority(info, row.project_id)
    redis = await _get_redis()
    if await redis.get(f"afterglow:catalog-consume:{consume_id}:lease:consume:{consume_id}"):
        raise HTTPException(409, "Catalog provisioning still owns this admission")
    raw = await redis.get(f"afterglow:builds:journal:consume:{consume_id}")
    state = json.loads(raw) if raw else {}
    consumer = state.get("consumer") or {}
    sources = snapshot.get("catalog_artifact_sources")
    if (
        not isinstance(sources, list)
        or any(not isinstance(source, dict) for source in sources)
        or {source.get("id") for source in sources} != set(row.artifact_ids or [])
        or len(sources) != len(row.artifact_ids or [])
    ):
        raise HTTPException(409, "Catalog consume source receipt is unavailable")
    has_submission = any([await _submission(redis, row.id, step) for step in ("port", "upper", "server")])
    if has_submission and (consumer.get("id") != consume_id or not consumer.get("token")):
        raise HTTPException(409, "Catalog allocation journal is unavailable")
    marker = {
        "afterglow_catalog_consume_id": str(consume_id),
        "afterglow_consume_id": str(consume_id),
        "afterglow_consume_token": str(consumer.get("token", "")),
        "afterglow_owner_project_id": row.project_id,
    }
    return row, snapshot, redis, state, consumer, marker, sources


async def _server(conn, row, redis, state, consumer, marker, *, instance_id=None, server=None):
    """Bind an interrupted accepted/unknown create only by exact native evidence."""
    from app.services import layer_build

    submitted = await _submission(redis, row.id, "server")
    recorded = _recorded_id(state, submitted, row.id, "server")
    identity = row.server_id or recorded or instance_id
    if row.server_id and instance_id and row.server_id != instance_id:
        raise HTTPException(409, "Catalog server differs from its SQL receipt")
    if recorded and identity != recorded:
        raise HTTPException(409, "Catalog server differs from its allocation journal")
    if identity and submitted is None:
        raise HTTPException(409, "Catalog server has no allocation submission receipt")
    if submitted is None:
        return None  # No server CREATE intent was ever admitted.
    if submitted.get("state") == "rejected" and not identity:
        return None
    name = consumer.get("server_name") or row.server_name
    if not name or not consumer.get("token"):
        raise HTTPException(409, "Catalog server identity is incomplete")
    # After the allocating lease is gone, a complete marker-bound native
    # observation can prove absence without replaying the unknown CREATE.
    try:
        current = await run_sync(
            layer_build._layer_resource,
            conn,
            "server",
            identity,
            name=name,
            project_id=row.project_id,
            marker=marker,
            allow_absent=identity is None,
        )
    except Exception as exc:
        raise HTTPException(409, "Catalog server allocation outcome cannot be resolved") from exc
    if current is not None:
        native_id = getattr(current, "id", None)
        if not native_id or (instance_id and native_id != instance_id):
            raise HTTPException(409, "Catalog native server differs from requested instance")
        if server is not None:
            metadata = getattr(server, "metadata", None) or {}
            if any(str(metadata.get(key, "")) != expected for key, expected in marker.items()):
                raise HTTPException(409, "Catalog server metadata differs from its durable owner")
        row.server_id = native_id
        row.server_name = name
    elif identity and row.server_id is None:
        row.server_id = identity  # Exact ID GET proved absence, not guessed name adoption.
    return current


async def _resource(conn, kind, row, redis, state, consumer, marker):
    from app.services import layer_build

    step = "upper" if kind == "volume" else "port"
    submitted = await _submission(redis, row.id, step)
    recorded = _recorded_id(state, submitted, row.id, step)
    recovered = (row.resources or {}).get("catalog_recovered_ids", {})
    identity = row.port_id if kind == "port" else recovered.get(step, recorded)
    if recorded and identity and identity != recorded:
        raise HTTPException(409, "Catalog resource SQL/journal identity differs")
    identity = identity or recorded
    if submitted is None:
        if identity:
            raise HTTPException(409, "Catalog resource lacks submission authority")
        return None
    if submitted.get("state") == "rejected" and not identity:
        return None
    name = (
        f"afterglow-root-upper-{consumer['token']}"
        if kind == "volume"
        else f"afterglow-layer-consume-{consumer['token']}"
    )
    resource = await run_sync(
        layer_build._layer_resource,
        conn,
        kind,
        identity,
        name=name,
        project_id=row.project_id,
        marker=marker,
        allow_absent=identity is None,
    )
    if not identity:
        if resource is None:
            return None
        if not getattr(resource, "id", None):
            raise HTTPException(409, "Catalog resource allocation observation is incomplete")
        identity = resource.id
        row.resources = {**(row.resources or {}), "catalog_recovered_ids": {**recovered, step: identity}}
    if kind == "port" and row.port_id is None:
        row.port_id = identity
    return resource


async def _delete_once(redis, key, fn, *args, observed=False, **kwargs):
    """Only a new explicit call with a fresh exact observation can repeat DELETE."""
    raw = await redis.get(key)
    if raw is None:
        admitted = await redis.set(key, json.dumps({"state": "submitting"}), nx=True)
    else:
        try:
            previous = json.loads(raw)
        except (ValueError, TypeError):
            previous = {}
        if previous.get("state") != "rejected" and not observed:
            return
        admitted = await redis.eval(
            "if redis.call('GET',KEYS[1]) == ARGV[1] then redis.call('SET',KEYS[1],ARGV[2]); return 1 end return 0",
            1,
            key,
            raw,
            json.dumps({"state": "submitting"}),
        )
    if not admitted:
        return
    try:
        from app.services.layer_consume_resources import _create_once
        from app.services.mcp_control_plane.sdk import check_mutation_dispatch

        def dispatch():
            check_mutation_dispatch()
            return _create_once(fn, *args, **kwargs)

        await run_sync(dispatch)
    except (Exception, asyncio.CancelledError) as exc:
        status = (
            getattr(exc, "status_code", None)
            or getattr(exc, "http_status", None)
            or getattr(getattr(exc, "response", None), "status_code", None)
        )
        rejected = type(status) is int and 400 <= status < 500 and status != 408
        await redis.set(key, json.dumps({"state": "rejected" if rejected else "unknown", "status": status}))
        raise HTTPException(
            409,
            "Catalog cleanup was rejected"
            if rejected
            else "Catalog cleanup acceptance is unknown; observe before retrying",
        ) from exc
    await redis.set(key, json.dumps({"state": "accepted"}))


async def _revoke_rules(conn, row, snapshot, redis, state, consumer, sources, marker):
    from app.services import keystone, layer_block, layer_build, manila

    share_conn = None
    try:
        for source in sources:
            share_id = source.get("share_id")
            if not share_id:
                raise HTTPException(409, "Catalog source share receipt is incomplete")
            submitted = await _submission(redis, row.id, f"rule:{share_id}")
            rule_id = _recorded_id(state, submitted, row.id, f"rule:{share_id}") or (row.resources or {}).get(
                "catalog_recovered_rule_ids", {}
            ).get(share_id)
            if submitted is None:
                if rule_id:
                    raise HTTPException(409, "Catalog rule lacks submission authority")
                continue
            if submitted.get("state") == "rejected" and not rule_id:
                continue
            if not consumer.get("fixed_ip"):
                raise HTTPException(409, "Catalog grant allocation outcome is unknown")
            service_project = (snapshot.get("openstack.service_project") or {}).get("id")
            if not service_project:
                raise HTTPException(409, "Catalog share service owner is unavailable")
            if share_conn is None:
                share_conn = await open_connection(keystone.get_admin_connection_for_project, service_project)
                await run_sync(layer_block.project_id, share_conn, expected=service_project)
            if not rule_id:
                share = await run_sync(manila.get_file_storage, share_conn, share_id)
                if getattr(share, "project_id", None) != service_project:
                    raise HTTPException(409, "Catalog share owner changed")
                port = await _resource(conn, "port", row, redis, state, consumer, marker)
                if port is None or consumer["fixed_ip"] not in {
                    entry.get("ip_address") for entry in getattr(port, "fixed_ips", [])
                }:
                    raise HTTPException(409, "Unknown grant requires the original owned port and captured IP")
                try:
                    discovered = await run_sync(
                        layer_build._layer_rule,
                        share_conn,
                        share_id,
                        consumer["fixed_ip"],
                        "ro",
                        None,
                        allow_absent=True,
                    )
                except Exception as exc:
                    raise HTTPException(409, "Catalog grant observation is ambiguous or unavailable") from exc
                if discovered is None:
                    continue
                rule_id = discovered["id"]
                recovered = (row.resources or {}).get("catalog_recovered_rule_ids", {})
                row.resources = {
                    **(row.resources or {}),
                    "catalog_recovered_rule_ids": {**recovered, share_id: rule_id},
                }
            rule = await run_sync(manila.get_access_rule, share_conn, share_id, rule_id)
            if rule is None:
                continue
            if (
                rule.get("access_type") != "ip"
                or rule.get("access_level") != "ro"
                or rule.get("access_to") != consumer["fixed_ip"]
            ):
                raise HTTPException(409, "Catalog grant authority changed")
            share = await run_sync(manila.get_file_storage, share_conn, share_id)
            if getattr(share, "project_id", None) != service_project:
                raise HTTPException(409, "Catalog share owner changed")
            await _delete_once(
                redis,
                f"afterglow:catalog-cleanup:{row.id}:rule:{rule_id}",
                manila.revoke_access_rule,
                share_conn,
                share_id,
                rule_id,
                observed=True,
            )
            for _ in range(10):
                if await run_sync(manila.get_access_rule, share_conn, share_id, rule_id) is None:
                    break
                await asyncio.sleep(0.2)
            else:
                raise HTTPException(409, "Catalog grant revocation is not confirmed")
        row.resources = {**(row.resources or {}), "catalog_grants_revoked": True}
    finally:
        if share_conn is not None:
            await close_connection(share_conn)


async def _floating_ips(conn, row, redis):
    if not row.port_id:
        return
    for ip in await run_sync(lambda: list(conn.network.ips(port_id=row.port_id))):
        if getattr(ip, "port_id", None) != row.port_id or getattr(ip, "project_id", None) != row.project_id:
            raise HTTPException(409, "Catalog floating IP ownership differs")
        identity = ip.id
        try:
            ip = await run_sync(conn.network.get_ip, identity)
        except ResourceNotFound:
            continue
        if ip is None:
            continue
        if getattr(ip, "port_id", None) != row.port_id or getattr(ip, "project_id", None) != row.project_id:
            raise HTTPException(409, "Catalog floating IP binding changed")
        await _delete_once(
            redis,
            f"afterglow:catalog-cleanup:{row.id}:fip:{identity}",
            conn.network.delete_ip,
            identity,
            ignore_missing=False,
            observed=True,
        )
        try:
            remaining = await run_sync(conn.network.get_ip, identity)
        except ResourceNotFound:
            remaining = None
        if remaining is not None:
            raise HTTPException(409, "Catalog floating IP deletion is not confirmed")


async def revoke_before_instance_delete(conn, instance_id, server, info):
    consume_id = await lookup_catalog_consume(instance_id, server, info)
    if consume_id is None:
        return
    async with _cleanup_session() as session:
        context = await _context(session, consume_id, info)
        row, snapshot, redis, state, consumer, marker, sources = context
        await _server(conn, row, redis, state, consumer, marker, instance_id=instance_id, server=server)
        port = await _resource(conn, "port", row, redis, state, consumer, marker)
        if port is not None and getattr(port, "device_id", None) not in {"", instance_id}:
            raise HTTPException(409, "Catalog port is attached to another server")
        # Changing the port's current IP does not authorize keeping the old exact grant.
        await _revoke_rules(conn, row, snapshot, redis, state, consumer, sources, marker)
        await _floating_ips(conn, row, redis)


async def submit_instance_delete(conn, instance_id, server, info):
    consume_id = await lookup_catalog_consume(instance_id, server, info)
    if consume_id is None:
        return False
    async with _cleanup_session() as session:
        row, _, redis, state, consumer, marker, _ = await _context(session, consume_id, info)
        current = await _server(conn, row, redis, state, consumer, marker, instance_id=instance_id, server=server)
        if not (row.resources or {}).get("catalog_grants_revoked"):
            raise HTTPException(409, "Catalog grant revocation is not confirmed")
        row.status = "indeterminate"
        if current is not None:
            await _delete_once(
                redis,
                f"afterglow:catalog-cleanup:{row.id}:server:{row.server_id}",
                conn.compute.delete_server,
                row.server_id,
                ignore_missing=False,
                observed=True,
            )
        return True


async def finish_instance_delete(conn, instance_id, server, info):
    consume_id = await lookup_catalog_consume(instance_id, server, info)
    if consume_id is not None:
        await cleanup_consume(conn, consume_id, info, delete_server=False, instance_id=instance_id)


async def cleanup_consume(conn, consume_id, info, *, delete_server=True, instance_id=None):
    async with _cleanup_session() as session:
        row, snapshot, redis, state, consumer, marker, sources = await _context(session, consume_id, info)
        current = await _server(conn, row, redis, state, consumer, marker, instance_id=instance_id)
        port = await _resource(conn, "port", row, redis, state, consumer, marker)
        if port is not None and getattr(port, "device_id", None) not in {"", row.server_id}:
            raise HTTPException(409, "Catalog port is attached outside this admission")
        await _revoke_rules(conn, row, snapshot, redis, state, consumer, sources, marker)
        await _floating_ips(conn, row, redis)
        row.status = "indeterminate"
        if current is not None and delete_server:
            await _delete_once(
                redis,
                f"afterglow:catalog-cleanup:{row.id}:server:{row.server_id}",
                conn.compute.delete_server,
                row.server_id,
                ignore_missing=False,
                observed=True,
            )
        if current is not None:
            for _ in range(10):
                try:
                    remaining = await run_sync(conn.compute.get_server, row.server_id)
                except ResourceNotFound:
                    remaining = None
                if remaining is None:
                    break
                await asyncio.sleep(0.2)
            else:
                raise HTTPException(409, "Catalog server deletion is not confirmed")
        for kind in ("port", "volume"):
            resource = await _resource(conn, kind, row, redis, state, consumer, marker)
            if resource is None:
                continue
            if kind == "port":
                if getattr(resource, "device_id", None) != "":
                    raise HTTPException(409, "Catalog port is still attached")
                proxy, deletion, getter = conn.network, "delete_port", "get_port"
            else:
                if getattr(resource, "attachments", None) != []:
                    raise HTTPException(409, "Catalog upper is still attached")
                proxy, deletion, getter = conn.block_storage, "delete_volume", "get_volume"
            identity = resource.id
            await _delete_once(
                redis,
                f"afterglow:catalog-cleanup:{row.id}:{kind}:{identity}",
                getattr(proxy, deletion),
                identity,
                ignore_missing=False,
                observed=True,
            )
            try:
                remaining = await run_sync(getattr(proxy, getter), identity)
            except ResourceNotFound:
                remaining = None
            if remaining is not None:
                raise HTTPException(409, "Catalog resource deletion is not confirmed")
        row.status = "deleted"
        row.completed_at = datetime.now(UTC)
        row.resources = {**(row.resources or {}), "catalog_cleanup_complete": True}
        return catalog.consume_dto(row)


async def recover_missing_instance(conn, instance_id, info):
    """External CLI/Horizon/MCP deletion needs no prior dashboard cleanup receipt."""
    if catalog.get_session_factory() is None:
        return False
    async with catalog.factory()() as session:
        stmt = select(LayerConsume.id, LayerConsume.resource_snapshot).where(LayerConsume.server_id == instance_id)
        if info.get("is_system_admin") is not True:
            stmt = stmt.where(LayerConsume.project_id == info.get("project_id"))
        rows = [
            row for row in (await session.execute(stmt)).all() if (row.resource_snapshot or {}).get("catalog_revision")
        ]
        if not rows:
            return False
        if len(rows) != 1:
            raise HTTPException(409, "Catalog server receipts are ambiguous")
        consume_id = rows[0].id
    # Never delete a VM just because a preceding UI read failed. Prove exact absence.
    try:
        current = await run_sync(conn.compute.get_server, instance_id)
    except ResourceNotFound:
        current = None
    if current is not None:
        raise HTTPException(409, "Catalog instance still exists; retry its normal deletion")
    await cleanup_consume(conn, consume_id, info, delete_server=False, instance_id=instance_id)
    return True
