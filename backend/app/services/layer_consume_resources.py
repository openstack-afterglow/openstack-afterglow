"""Owner/run-fenced durable disposition of block consumer resources.

The service identity is used only for reclamation, never consumer allocation.
Intent names and provider metadata close the create-response/DB-commit gap.
Failed/unknown deletions stay pending; there is no force-delete fallback.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from copy import copy
from datetime import UTC, datetime, timedelta
from functools import partial

from keystoneauth1.exceptions import ClientException
from openstack.exceptions import HttpException, ResourceNotFound
from openstack.proxy import Proxy
from sqlalchemy import or_, select, update

from app.database import get_session_factory
from app.models.db import LayerConsume
from app.services import manila, neutron
from app.services.work_dispatcher import checkpoint, close_connection, open_connection, run_sync

_logger = logging.getLogger(__name__)
STALE_AFTER = timedelta(hours=1)
REJECTED_CREATE_STATUSES = frozenset(set(range(400, 500)) - {408, 409, 425, 429})


def value(resource, key, default=None):
    if isinstance(resource, dict):
        return resource.get(key, default)
    return getattr(resource, key, default)


def owner(resource):
    return (
        value(resource, "project_id") or value(resource, "tenant_id") or value(resource, "os-vol-tenant-attr:tenant_id")
    )


def fence(resource, metadata: dict, *, port=False):
    if owner(resource) != metadata["afterglow_project_id"]:
        raise RuntimeError("foreign consumer resource project")
    recorded = value(resource, "metadata", {}) or {}
    if port:
        try:
            recorded = json.loads(value(resource, "description", ""))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("consumer port ownership evidence missing") from exc
    if not isinstance(recorded, dict) or any(
        str(recorded.get(key, "")) != str(expected) for key, expected in metadata.items()
    ):
        raise RuntimeError("foreign consumer resource run/lineage")


def resource_identity(resource_id):
    """Normalize real provider UUIDs; invalid responses never close an intent."""
    if not isinstance(resource_id, str):
        raise RuntimeError("provider resource identity is not a UUID")
    try:
        return str(uuid.UUID(resource_id))
    except ValueError as exc:
        raise RuntimeError("provider resource identity is not a UUID") from exc


async def begin(consume_id: int | None, project_id: str, artifact_ids: list[int]) -> str:
    factory = get_session_factory()
    if consume_id is None or factory is None or not project_id:
        raise RuntimeError("block consume requires durable project-bound tracking")
    async with factory() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one()
        if row.project_id not in (None, project_id) or list(row.artifact_ids or []) != artifact_ids:
            raise RuntimeError("consumer owner/artifact snapshot mismatch")
        if (
            row.run_id
            or row.resources not in (None, [])
            or row.server_id
            or row.port_id
            or row.status != "creating"
            or row.cleanup_state is not None
        ):
            raise RuntimeError("consumer run already claimed; cleanup before creating a new run")
        run_id = uuid.uuid4().hex
        claimed = await session.execute(
            update(LayerConsume)
            .where(
                LayerConsume.id == consume_id,
                LayerConsume.run_id.is_(None),
                LayerConsume.cleanup_state.is_(None),
                LayerConsume.status == "creating",
            )
            .values(
                project_id=project_id,
                transport="block",
                run_id=run_id,
                resources=[],
                cleanup_state="allocating",
                updated_at=datetime.now(UTC),
            )
        )
        if claimed.rowcount != 1:
            raise RuntimeError("consumer run already claimed; cleanup before creating a new run")
        await session.commit()
        return run_id


async def fail_unclaimed(consume_id: int, project_id: str, error_message: str) -> bool:
    """Fail only our never-claimed, provably allocation-free admission."""
    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one_or_none()
        if (
            row is None
            or row.project_id != project_id
            or row.transport != "block"
            or row.run_id is not None
            or row.resources not in (None, [])
            or row.server_id
            or row.port_id
            or row.status != "creating"
            or row.cleanup_state is not None
        ):
            return False
        result = await session.execute(
            update(LayerConsume)
            .where(
                LayerConsume.id == consume_id,
                LayerConsume.project_id == project_id,
                LayerConsume.transport == "block",
                LayerConsume.run_id.is_(None),
                LayerConsume.cleanup_state.is_(None),
                LayerConsume.status == "creating",
                LayerConsume.updated_at == row.updated_at,
            )
            .values(
                status="error",
                error_message=error_message,
                cleanup_state="complete",
                completed_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        if result.rowcount != 1:
            return False
        await session.commit()
        return True


def run_metadata(consume_id: int, run_id: str, project_id: str) -> dict:
    return {"afterglow_consume_id": str(consume_id), "afterglow_run_id": run_id, "afterglow_project_id": project_id}


async def record(consume_id: int, run_id: str, *, kind: str, name: str, metadata: dict, resource_id=None):
    if resource_id is not None:
        resource_id = resource_identity(resource_id)
    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one()
        if (
            row.run_id != run_id
            or row.project_id != metadata["afterglow_project_id"]
            or row.cleanup_state != "allocating"
        ):
            raise RuntimeError("consumer allocation lease lost")
        resources = [dict(item) for item in row.resources or []]
        existing = next((item for item in resources if item["kind"] == kind and item["name"] == name), None)
        if existing is None:
            resources.append(
                {
                    "kind": kind,
                    "name": name,
                    "metadata": metadata,
                    "id": resource_id,
                    "state": "allocated" if resource_id is not None else "intent",
                }
            )
        else:
            if resource_id is None:
                raise RuntimeError("consumer allocation already attempted; outcome may be unknown")
            if existing["metadata"] != metadata or existing["id"] not in (None, resource_id):
                raise RuntimeError("consumer resource identity changed")
            existing["id"] = resource_id
            existing["state"] = "allocated"
        result = await session.execute(
            update(LayerConsume)
            .where(
                LayerConsume.id == consume_id,
                LayerConsume.run_id == run_id,
                LayerConsume.cleanup_state == "allocating",
            )
            .values(resources=resources, updated_at=datetime.now(UTC))
        )
        if result.rowcount != 1:
            raise RuntimeError("consumer allocation lease lost")
        await session.commit()


def _create_once(create, *args, **kwargs):
    adapter = getattr(create, "__self__", None)
    if isinstance(adapter, Proxy):
        # Proxy.request defaults to one connection retry even when its Session
        # disables retries. Scope overrides to this allocation, never the shared
        # caller connection: a lost response may already have created a resource.
        adapter = copy(adapter)
        adapter.request = partial(adapter.request, connect_retries=0, status_code_retries=0)
        return create.__func__(adapter, *args, **kwargs)
    return create(*args, **kwargs)


async def allocate(
    consume_id, run_id, create, *args, resource_kind, resource_name, owner_metadata, preflight=None, **kwargs
):
    """Persist intent and returned identity; only definitive rejection proves no allocation."""
    # Preflight is explicitly outside the sent-request boundary. It must not mutate
    # the provider; validation failure here proves CREATE was never attempted.
    if preflight is not None:
        await asyncio.to_thread(preflight)
    await record(consume_id, run_id, kind=resource_kind, name=resource_name, metadata=owner_metadata)
    try:
        resource = await asyncio.to_thread(_create_once, create, *args, **kwargs)
    except (HttpException, ClientException) as exc:
        status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
        if status in REJECTED_CREATE_STATUSES:
            async with get_session_factory()() as session:
                row = (
                    await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
                ).scalar_one()
                if (
                    row.run_id != run_id
                    or row.project_id != owner_metadata["afterglow_project_id"]
                    or row.cleanup_state not in {"allocating", "pending"}
                ):
                    raise RuntimeError("consumer rejection owner/run mismatch") from exc
                items = [dict(item) for item in row.resources or []]
                item = next(item for item in items if item["kind"] == resource_kind and item["name"] == resource_name)
                if item["id"] is not None or item["state"] != "intent":
                    raise RuntimeError("consumer rejection conflicts with allocated identity") from exc
                item["state"] = "rejected"
                item["response_status"] = status
                result = await session.execute(
                    update(LayerConsume)
                    .where(
                        LayerConsume.id == consume_id,
                        LayerConsume.run_id == run_id,
                        LayerConsume.cleanup_state == row.cleanup_state,
                        LayerConsume.updated_at == row.updated_at,
                    )
                    .values(resources=items, updated_at=datetime.now(UTC))
                )
                if result.rowcount != 1:
                    raise RuntimeError("consumer rejection lease lost") from exc
                await session.commit()
        raise
    resource_id = resource_identity(value(resource, "id"))
    await record(
        consume_id,
        run_id,
        kind=resource_kind,
        name=resource_name,
        metadata=owner_metadata,
        resource_id=resource_id,
    )
    return resource


async def disposition(consume_id: int, run_id: str, state: str, *, status=None, error_message=None, completed=False):
    """Worker disposition and user-visible status share the allocating lease."""
    if state not in {"active", "pending"}:
        raise ValueError("worker disposition must be active or pending")
    fields = {"cleanup_state": state, "updated_at": datetime.now(UTC)}
    if status is not None:
        fields["status"] = status
    if error_message is not None:
        fields["error_message"] = error_message
    if completed:
        fields["completed_at"] = datetime.now(UTC)
    await _allocation_update(consume_id, run_id, fields)


async def _allocation_update(consume_id, run_id, fields):
    async with get_session_factory()() as session:
        result = await session.execute(
            update(LayerConsume)
            .where(
                LayerConsume.id == consume_id,
                LayerConsume.run_id == run_id,
                LayerConsume.cleanup_state == "allocating",
            )
            .values(**fields)
        )
        if result.rowcount != 1:
            raise RuntimeError("consumer allocation lease lost")
        await session.commit()


async def update_allocation(consume_id: int, run_id: str, **fields):
    """Persist runner bindings only while this worker owns allocation."""
    if not fields or set(fields) - {"server_name", "port_id", "server_id"}:
        raise ValueError("unsupported consumer allocation field")
    for key in {"server_id", "port_id"} & fields.keys():
        fields[key] = resource_identity(fields[key])
    await _allocation_update(consume_id, run_id, {**fields, "updated_at": datetime.now(UTC)})


async def heartbeat(consume_id: int, run_id: str):
    """Raise on DB/lease loss; the runner must supervise, not discard, failure."""
    while True:
        await asyncio.sleep(30)
        await _allocation_update(consume_id, run_id, {"updated_at": datetime.now(UTC)})


def _get(conn, kind, resource_id):
    expected = resource_identity(resource_id)
    try:
        if kind == "server":
            resource = conn.compute.get_server(expected)
        elif kind == "port":
            resource = conn.network.get_port(expected)
        else:
            resource = conn.block_storage.get_volume(expected)
    except ResourceNotFound:
        return None
    if resource is not None and resource_identity(value(resource, "id")) != expected:
        raise RuntimeError("consumer GET identity mismatch")
    return resource


def _discover(conn, item):
    if item["kind"] == "server":
        candidates = conn.compute.servers(name=item["name"], all_projects=False)
    elif item["kind"] == "port":
        candidates = conn.network.ports(name=item["name"], project_id=item["metadata"]["afterglow_project_id"])
    else:
        candidates = conn.block_storage.volumes(details=True, name=item["name"])
    matches = []
    for resource in candidates:
        if value(resource, "name") != item["name"]:
            continue
        # Never delete a same-name foreign resource, even if an allocation failed.
        fence(resource, item["metadata"], port=item["kind"] == "port")
        resource_identity(value(resource, "id"))
        matches.append(resource)
    if len(matches) > 1:
        raise RuntimeError("ambiguous consumer allocation intent")
    return matches[0] if matches else None


async def _save_resources(consume_id, run_id, resources):
    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one()
        if row.run_id != run_id or row.cleanup_state != "pending":
            raise RuntimeError("consumer cleanup lease lost")
        current = {(item["kind"], item["name"]): dict(item) for item in row.resources or []}
        if set(current) != {(item["kind"], item["name"]) for item in resources}:
            raise RuntimeError("consumer cleanup resource inventory changed")
        merged = []
        for proposed in resources:
            saved = current[(proposed["kind"], proposed["name"])]
            if saved["metadata"] != proposed["metadata"] or (
                saved["id"] is not None and proposed["id"] not in (None, saved["id"])
            ):
                raise RuntimeError("consumer cleanup resource identity changed")
            if saved["state"] in {"rejected", "deleted"}:
                if saved["state"] == "rejected" and proposed["id"] is not None:
                    raise RuntimeError("consumer cleanup conflicts with CREATE rejection")
                combined = saved
            else:
                combined = {**saved, **proposed}
                if saved["id"] is not None and proposed["id"] is None:
                    combined["id"] = saved["id"]
                    combined["state"] = saved["state"]
                if combined["id"] is not None and combined["state"] == "intent":
                    combined["state"] = "allocated"
            merged.append(combined)
        row.resources = merged
        row.updated_at = datetime.now(UTC)
        await session.commit()
        # Preserve references held by the cleanup iteration while refreshing
        # any concurrent definitive rejection or already-observed deletion.
        for proposed, saved in zip(resources, merged, strict=True):
            proposed.clear()
            proposed.update(saved)


async def _revoke_storage_before_cleanup(resource, revoke_grants):
    metadata = value(resource, "metadata", {}) or {}
    if any(key.startswith(manila.INSTANCE_STORAGE_GRANT_PREFIX) for key in metadata):
        if revoke_grants is None:
            raise RuntimeError("storage grants require authenticated deletion; cleanup remains pending")
        await revoke_grants(resource)


async def cleanup(conn, consume_id: int, *, project_id: str, automatic: bool = False, revoke_grants=None):
    """Reclaim only this run, server first; attached/foreign resources fail closed."""
    await checkpoint()
    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one_or_none()
        if row is None or row.transport != "block" or row.project_id != project_id:
            raise RuntimeError("consumer cleanup owner mismatch")
        from app.services.layer_block import project_id as connection_project_id

        connection_project_id(conn, expected=row.project_id)
        if row.cleanup_state == "complete":
            return
        if not row.run_id:
            if await _recover_unclaimed(session, row):
                return
            raise RuntimeError("consumer cleanup run missing or unclaimed admission is not provably empty")
        if automatic and row.status not in {"error", "deleted"}:
            if row.cleanup_state == "allocating":
                touched = row.updated_at
                touched = touched.replace(tzinfo=UTC) if touched and touched.tzinfo is None else touched
                if touched is None or datetime.now(UTC) - touched <= STALE_AFTER:
                    return
            if (
                row.cleanup_state == "active"
                and row.server_id
                and await run_sync(_get, conn, "server", row.server_id) is not None
            ):
                return
        run_id = row.run_id
        resources = [dict(item) for item in row.resources or []]
        expected_run = run_metadata(consume_id, run_id, project_id)
        for item in resources:
            if any(item.get("metadata", {}).get(key) != expected for key, expected in expected_run.items()):
                raise RuntimeError("consumer ledger resource owner/run mismatch")
        # Admission must not retire a live allocation lease while managed
        # authorization denial is pending. Recheck again at destructive use.
        for item in resources:
            if item["kind"] != "server" or item["state"] in {"rejected", "deleted"}:
                continue
            server = (
                await run_sync(_get, conn, "server", resource_identity(item["id"]))
                if item["id"] is not None
                else await run_sync(_discover, conn, item)
            )
            if server is not None:
                fence(server, item["metadata"])
                await _revoke_storage_before_cleanup(server, revoke_grants)
        claimed = await session.execute(
            update(LayerConsume)
            .where(
                LayerConsume.id == consume_id,
                LayerConsume.run_id == run_id,
                LayerConsume.cleanup_state == row.cleanup_state,
                LayerConsume.updated_at == row.updated_at,
            )
            .values(cleanup_state="pending", updated_at=datetime.now(UTC))
        )
        if claimed.rowcount != 1:
            raise RuntimeError("consumer cleanup lease lost")
        await session.commit()
    try:
        for item in sorted(resources, key=lambda item: {"server": 0, "layer": 1, "upper": 1, "port": 2}[item["kind"]]):
            if item["state"] == "deleted":
                continue
            if item["state"] == "rejected":
                if item["id"] is not None or item.get("response_status") not in REJECTED_CREATE_STATUSES:
                    raise RuntimeError("consumer allocation rejection evidence is invalid")
                continue
            resource = (
                await run_sync(_get, conn, item["kind"], resource_identity(item["id"]))
                if item["id"] is not None
                else await run_sync(_discover, conn, item)
            )
            if resource is None and item["id"] is None:
                # A timed-out POST may still be accepted. Absence is not proof
                # of rejection: retain this intent and discover on later runs.
                raise RuntimeError("allocation outcome unknown; intent remains pending")
            if resource is not None:
                fence(resource, item["metadata"], port=item["kind"] == "port")
                item["id"] = resource_identity(value(resource, "id"))
                await _save_resources(consume_id, run_id, resources)
                if item["kind"] == "server":
                    await _revoke_storage_before_cleanup(resource, revoke_grants)
                    await run_sync(neutron.cleanup_instance_fips, conn, item["id"], strict=True)
                    await run_sync(conn.compute.delete_server, item["id"], ignore_missing=True)
                elif item["kind"] == "port":
                    device_id = value(resource, "device_id")
                    if not isinstance(device_id, str) or device_id != "":
                        raise RuntimeError("consumer port detachment evidence missing or still attached")
                    await run_sync(conn.network.delete_port, item["id"], ignore_missing=True)
                else:
                    attachments = value(resource, "attachments")
                    if not isinstance(attachments, list) or attachments:
                        raise RuntimeError(
                            "consumer volume detachment evidence missing or still attached; cleanup remains pending"
                        )
                    if value(resource, "status") not in {"available", "error", "error_restoring", "error_extending"}:
                        raise RuntimeError("consumer volume not deletable; cleanup remains pending")
                    await run_sync(conn.block_storage.delete_volume, item["id"], ignore_missing=True)
                for _ in range(60):
                    if await run_sync(_get, conn, item["kind"], item["id"]) is None:
                        break
                    await asyncio.sleep(2)
                else:
                    raise RuntimeError("consumer resource deletion not observed")
            item["state"] = "deleted"
            await _save_resources(consume_id, run_id, resources)
        async with get_session_factory()() as session:
            row = (
                await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
            ).scalar_one()
            result = await session.execute(
                update(LayerConsume)
                .where(
                    LayerConsume.id == consume_id,
                    LayerConsume.run_id == run_id,
                    LayerConsume.cleanup_state == "pending",
                )
                .values(
                    cleanup_state="complete",
                    status="error" if row.status == "error" else "deleted",
                    completed_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )
            if result.rowcount != 1:
                raise RuntimeError("consumer cleanup lease lost at completion")
            await session.commit()
    except Exception:
        _logger.warning("Block consumer cleanup remains pending: consume=%s", consume_id, exc_info=True)
        raise


async def lookup_for_server(server_id: str, project_id: str, *, require_block=False) -> list[int]:
    """Read-only authoritative binding lookup before managed-grant revocation."""
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("block consumer tracking database unavailable")
    server_id = resource_identity(server_id)
    async with factory() as session:
        rows = (await session.execute(select(LayerConsume).where(LayerConsume.transport == "block"))).scalars().all()
        ids = []
        unknown_binding = False
        for row in rows:
            # Include the CREATE ledger: response recording can precede the
            # runner's denormalized server_id binding transaction.
            bound = row.server_id == server_id or any(
                item.get("kind") == "server" and item.get("id") == server_id for item in row.resources or []
            )
            if bound:
                if row.project_id != project_id:
                    raise RuntimeError("foreign block consumer deletion")
                ids.append(row.id)
            elif (
                row.project_id == project_id
                and row.cleanup_state != "complete"
                and any(
                    item.get("kind") == "server"
                    and item.get("id") is None
                    and item.get("state") not in {"rejected", "not_sent"}
                    for item in row.resources or []
                )
            ):
                unknown_binding = True
        if not ids and require_block:
            raise RuntimeError("block consumer tracking record missing")
        if not ids and unknown_binding:
            raise RuntimeError("block consumer server binding unknown")
    return ids


async def cleanup_for_server(conn, server_id: str, project_id: str, *, require_block=False) -> bool:
    """Reclaim a proven binding; callers must first finish managed-grant revocation."""
    ids = await lookup_for_server(server_id, project_id, require_block=require_block)
    for consume_id in ids:
        await cleanup(conn, consume_id, project_id=project_id)
    return bool(ids)


async def _recover_unclaimed(session, row):
    """Terminalize stale admissions only with proof that no CREATE was recorded."""
    touched = row.updated_at
    touched = touched.replace(tzinfo=UTC) if touched and touched.tzinfo is None else touched
    if (
        row.run_id is not None
        or row.resources not in (None, [])
        or row.server_id
        or row.port_id
        or row.cleanup_state is not None
        or row.status not in {"creating", "error"}
        or touched is None
        or datetime.now(UTC) - touched <= STALE_AFTER
    ):
        return False
    result = await session.execute(
        update(LayerConsume)
        .where(
            LayerConsume.id == row.id,
            LayerConsume.run_id.is_(None),
            LayerConsume.cleanup_state.is_(None),
            LayerConsume.status == row.status,
            LayerConsume.updated_at == row.updated_at,
        )
        .values(
            cleanup_state="complete",
            status="error",
            error_message="Unclaimed block admission expired before allocation",
            completed_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    if result.rowcount != 1:
        return False
    await session.commit()
    return True


async def reconcile_once():
    """Restart/externally deleted/error reclamation with owner-fenced admin I/O only.

    A one-hour stale allocation threshold avoids stealing live multi-worker runs;
    each allocation stage renews updated_at. Successful active VMs are retained.
    """
    await checkpoint()
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        rows = (
            (
                await session.execute(
                    select(LayerConsume).where(
                        LayerConsume.transport == "block",
                        or_(LayerConsume.cleanup_state.is_(None), LayerConsume.cleanup_state != "complete"),
                    )
                )
            )
            .scalars()
            .all()
        )
        claimed_rows = []
        for row in rows:
            if row.run_id is None:
                await _recover_unclaimed(session, row)
            else:
                claimed_rows.append(row)
        snapshots = [
            (row.id, row.project_id, row.status, row.cleanup_state, row.server_id, row.updated_at)
            for row in claimed_rows
        ]
    from app.services.keystone import get_admin_connection_for_project

    for consume_id, project_id, status, state, server_id, touched in snapshots:
        conn = None
        try:
            if not project_id:
                raise RuntimeError("block resource owner missing")
            touched = touched.replace(tzinfo=UTC) if touched and touched.tzinfo is None else touched
            stale = touched is not None and datetime.now(UTC) - touched > STALE_AFTER
            if state == "allocating" and not stale and status != "error":
                continue
            conn = await open_connection(get_admin_connection_for_project, project_id)
            if (
                state == "active"
                and status not in {"error", "deleted"}
                and server_id
                and await run_sync(_get, conn, "server", server_id) is not None
            ):
                continue
            await cleanup(conn, consume_id, project_id=project_id, automatic=True)
        except Exception:
            _logger.warning("Block consumer reconciliation deferred: consume=%s", consume_id, exc_info=True)
        finally:
            if conn is not None:
                await close_connection(conn)


async def reconciliation_loop():
    while True:
        try:
            await reconcile_once()
        except Exception:
            _logger.warning("Block consumer reconciliation unavailable", exc_info=True)
        await asyncio.sleep(60)
