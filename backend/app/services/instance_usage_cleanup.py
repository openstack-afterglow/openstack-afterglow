"""Resource-only deletion receipts; schedule authority remains exclusively in Nova.

The scheduler alone changes BDM flags and submits Nova DELETE. Existing consume
receipts fence ordinary reclaimers, including after the server metadata is gone.
This module never deletes a server, volume, snapshot, image, or Manila share.
"""

from __future__ import annotations

import copy
import json
import logging
from datetime import UTC, datetime
from functools import partial
from types import SimpleNamespace

from openstack.exceptions import ResourceNotFound
from sqlalchemy import or_, select

from app.database import get_session_factory
from app.models.db import LayerConsume
from app.services import instance_usage as usage
from app.services.layer_consume_resources import fence, owner, value

RECEIPT = "usage_resource_cleanup"
_GRANT_PENDING = "Managed grant revocation requested; observation required"
_SAFE = dict(redirect=False, allow_reauth=False, connect_retries=0, status_code_retries=0)
_QUIESCENT = {"SHUTOFF", "SHELVED", "SHELVED_OFFLOADED"}
_logger = logging.getLogger(__name__)


async def _lease(lease):
    if lease is None or not await lease.current():
        raise RuntimeError("Managed cleanup lease is unavailable")


def _proxy(proxy):
    local = copy.copy(proxy)
    local.request = partial(proxy.request, **_SAFE)
    return local


async def _get(getter, identity):
    try:
        resource = await usage.sdk_call(getter, identity)
    except ResourceNotFound:
        return None
    if resource is None:
        # A successful null response is not an exact native 404.
        raise RuntimeError("Native resource absence is not proven")
    if value(resource, "id") != identity:
        raise RuntimeError("Native resource identity changed")
    return resource


async def _absent(conn, server_id):
    return await _get(usage.safe_compute_proxy(conn).get_server, server_id) is None


def _grants(server):
    from app.services import manila

    result = []
    for key, raw in (value(server, "metadata", {}) or {}).items():
        if not key.startswith(manila.INSTANCE_STORAGE_GRANT_PREFIX):
            continue
        try:
            grant = json.loads(raw)
            if (
                not isinstance(grant, dict)
                or set(grant) != {"s", "i", "t", "a", "l", "m"}
                or type(grant["m"]) is not bool
                or any(not isinstance(grant[k], str) or not grant[k] for k in ("s", "i", "t", "a", "l"))
                or grant["t"] not in {"ip", "cephx"}
                or grant["l"] not in {"ro", "rw"}
            ):
                raise ValueError("invalid grant")
        except (ValueError, TypeError, KeyError) as exc:
            raise RuntimeError("Managed Manila grant receipt is invalid") from exc
        if grant["m"]:
            result.append(grant)
    return result


def _rule_matches(rule, grant, server_id, *, tracked=True):
    return (
        rule.get("id") == grant["i"]
        and rule.get("access_type") == grant["t"]
        and rule.get("access_to") == grant["a"]
        and rule.get("access_level") == grant["l"]
        and (not tracked or (rule.get("metadata") or {}).get("afterglow_instance_id") == server_id)
    )


async def _grant_observation(conn, grant, server_id, *, tracked=True):
    from app.services import manila

    rule = await usage.sdk_call(manila.get_access_rule, conn, grant["s"], grant["i"])
    if rule is None:
        return None
    share = await usage.sdk_call(manila.get_file_storage, conn, grant["s"])
    if value(share, "id") != grant["s"] or owner(share) != usage._target_project(conn):
        raise RuntimeError("Managed Manila share owner changed")
    if not _rule_matches(rule, grant, server_id, tracked=tracked):
        raise RuntimeError("Managed Manila grant authority changed")
    return rule


async def finalize_managed_delete_preflight(conn, server, lease):
    """Revoke metadata-only grants once, stopped and durably delete-requested.

    A requested marker survives rejection/reply loss; another tick may observe
    absence but must not automatically repeat an uncertain deny request.
    """
    project = usage.require_server_scope(conn, server)
    identity = value(server, "id")
    await _lease(lease)
    current = await _get(usage.safe_compute_proxy(conn).get_server, identity)
    if current is None:
        raise RuntimeError("Scheduled server disappeared before final preflight")
    usage.require_server_scope(conn, current, identity)
    schedule = usage.parse_schedule(current)
    if schedule is None or schedule.state != "delete_requested" or value(current, "status") not in _QUIESCENT:
        raise RuntimeError("Managed grant revocation requires quiescent delete-requested server")
    if value(current, "task_state", value(current, "OS-EXT-STS:task_state")):
        raise RuntimeError("Scheduled server has an active task")
    await _prepare_managed_delete(conn, current, schedule.delete_volumes, lease, arm=True)
    health_id = (value(current, "metadata", {}) or {}).get("union_health_id")
    if health_id:
        await _lease(lease)
        await _revoke_health(health_id, project, identity)
    grants = _grants(current)
    remaining = [grant for grant in grants if await _grant_observation(conn, grant, identity) is not None]
    if not remaining:
        return current
    if schedule.last_error == _GRANT_PENDING:
        raise RuntimeError("Managed grant revocation outcome unresolved; no automatic replay")
    current = await usage.write_schedule_metadata(
        conn, current, {usage.METADATA_PREFIX + "last_error": _GRANT_PENDING}, lease=lease
    )
    from app.services import manila

    for grant in remaining:
        await _lease(lease)
        fresh = await _get(usage.safe_compute_proxy(conn).get_server, identity)
        if (
            fresh is None
            or usage.require_server_scope(conn, fresh, identity) != project
            or value(fresh, "status") not in _QUIESCENT
        ):
            raise RuntimeError("Scheduled server changed during grant revocation")
        if usage.parse_schedule(fresh).state != "delete_requested":
            raise RuntimeError("Scheduled deletion marker changed")
        rule = await _grant_observation(conn, grant, identity)
        if rule is not None:
            await _lease(lease)
            # ManilaClient uses direct httpx without redirects, auth or status retries.
            await usage.sdk_call(manila.revoke_access_rule, conn, grant["s"], grant["i"])
        if await _grant_observation(conn, grant, identity) is not None:
            raise RuntimeError("Managed grant revocation is not confirmed")
    return current


async def _health_proof(health_id, project, server_id):
    """Read-only owner proof before dispatch, repeated at revocation."""
    from app.services import instance_health

    redis = await instance_health._redis()
    token = await redis.get(instance_health._INSTANCE_PREFIX + health_id)
    if isinstance(token, bytes):
        token = token.decode()
    if not token:
        return redis, None, None
    raw = await redis.get(instance_health._TOKEN_PREFIX + token)
    payload = json.loads(raw) if raw else None
    if payload is None or payload.get("project_id") != project or payload.get("instance_id") != health_id:
        raise RuntimeError("Health credential owner differs")
    if payload.get("server_id", payload.get("instance_id")) != server_id:
        raise RuntimeError("Health credential lacks an exact native server binding")
    return redis, token, raw


async def _revoke_health(health_id, project, server_id):
    """CAS the exact existing credential, never a concurrent replacement."""
    from app.services import instance_health

    redis, token, raw = await _health_proof(health_id, project, server_id)
    if not token:
        return
    removed = await redis.eval(
        "if redis.call('GET',KEYS[1]) ~= ARGV[1] or redis.call('GET',KEYS[2]) ~= ARGV[2] then return 0 end "
        "redis.call('DEL',KEYS[1],KEYS[2]); return 1",
        2,
        instance_health._INSTANCE_PREFIX + health_id,
        instance_health._TOKEN_PREFIX + token,
        token,
        raw,
    )
    if (
        removed != 1
        or await redis.get(instance_health._INSTANCE_PREFIX + health_id)
        or await redis.get(instance_health._TOKEN_PREFIX + token)
    ):
        raise RuntimeError("Health credential revocation changed or is not confirmed")


async def _legacy_union_preflight(conn, server, lease):
    """Historical name-only CephX rules cannot authorize automatic revocation."""
    from app.services import keystone, manila
    from app.services.work_dispatcher import close_connection, open_connection

    metadata = value(server, "metadata", {}) or {}
    shares = [
        identity for identity in metadata.get("union_share_ids", "").split(",") if identity and identity != "none"
    ]
    if not shares or metadata.get("union_strategy") == "dynamic":
        return
    service = None
    try:
        service = await open_connection(keystone.get_service_project_connection)
        access = await usage.sdk_call(service.session.auth.get_access, service.session)
        await usage.sdk_call(usage.prove_project_scope, service, access.project_id)
        tracked = {(grant["s"], grant["i"]) for grant in _grants(server)}
        for share_id in shares:
            await _lease(lease)
            share = await usage.sdk_call(manila.get_file_storage, service, share_id)
            if owner(share) != service._afterglow_project_id:
                raise RuntimeError("Legacy Union source owner differs")
            for rule in await usage.sdk_call(manila.list_access_rules, service, share_id, strict=True):
                if (
                    rule.get("access_type") == "cephx"
                    and rule.get("access_to", "").startswith("union-ro-" + str(value(server, "name")) + "-")
                    and (share_id, rule.get("id")) not in tracked
                ):
                    raise RuntimeError("Legacy Union CephX rule lacks an exact instance ownership receipt")
    finally:
        if service is not None:
            await close_connection(service)


async def _rows(session, identity, project):
    # Native server_id bindings are indexed. Block CREATE receipts may precede
    # that denormalized binding, so include their JSON ledger without locking
    # unrelated consumers; each actual mutation takes its own row lock later.
    rows = (
        (
            await session.execute(
                select(LayerConsume).where(or_(LayerConsume.server_id == identity, LayerConsume.transport == "block"))
            )
        )
        .scalars()
        .all()
    )
    found = []
    for row in rows:
        bound = row.server_id == identity or (
            isinstance(row.resources, list)
            and any(item.get("kind") == "server" and item.get("id") == identity for item in row.resources)
        )
        if bound:
            if row.project_id != project:
                raise RuntimeError("Managed server has a foreign consume receipt")
            found.append(row)
    return found


async def _catalog_preflight(conn, row, server, lease):
    from app.services import palimpsest_catalog_cleanup as cleanup

    authority = cleanup.ScheduledCleanupAuthority(conn, lease)
    async with cleanup._cleanup_session() as session:
        context = await cleanup._context(session, row.id, authority)
        saved, snapshot, redis, state, consumer, marker, sources = context
        current = await cleanup._server(
            conn,
            saved,
            redis,
            state,
            consumer,
            marker,
            instance_id=value(server, "id"),
            server=SimpleNamespace(metadata=value(server, "metadata")),
        )
        if current is None:
            raise RuntimeError("Catalog native binding is absent")
        port = await cleanup._resource(conn, "port", saved, redis, state, consumer, marker)
        upper = await cleanup._resource(conn, "volume", saved, redis, state, consumer, marker)
        rules = []
        for source in sources:
            share_id = source.get("share_id")
            if not share_id:
                raise RuntimeError("Catalog immutable source share receipt missing")
            submitted = await cleanup._submission(redis, row.id, f"rule:{share_id}")
            rule_id = cleanup._recorded_id(state, submitted, row.id, f"rule:{share_id}") or (saved.resources or {}).get(
                "catalog_recovered_rule_ids", {}
            ).get(share_id)
            if submitted is None or submitted.get("state") == "rejected":
                if rule_id:
                    raise RuntimeError("Catalog rule lacks allocation authority")
                continue
            if not rule_id or not consumer.get("fixed_ip"):
                raise RuntimeError("Catalog grant allocation remains unknown")
            rules.append(dict(s=share_id, i=rule_id, t="ip", a=consumer["fixed_ip"], l="ro", m=True))
        return {
            "port_ids": [value(port, "id")] if port is not None else [],
            "managed_volume_ids": [value(upper, "id")] if upper is not None else [],
            "rules": rules,
            "share_project_id": (snapshot.get("openstack.service_project") or {}).get("id"),
        }


async def prepare_managed_delete(conn, server, delete_volumes, lease) -> set[str]:
    """Read-only native/ledger preparation; final stopped preflight arms retention."""
    return await _prepare_managed_delete(conn, server, delete_volumes, lease, arm=False)


async def _prepare_managed_delete(conn, server, delete_volumes, lease, *, arm) -> set[str]:
    """Only the stopped delete-requested finalizer may arm a resource receipt."""
    project = usage.require_server_scope(conn, server)
    identity = value(server, "id")
    await _lease(lease)
    if type(delete_volumes) is not bool:
        raise ValueError("Volume consent must be explicit boolean")
    metadata = value(server, "metadata", {}) or {}
    for grant in _grants(server):
        await _grant_observation(conn, grant, identity)
    if metadata.get("union_health_id"):
        await _health_proof(metadata["union_health_id"], project, identity)
    await _legacy_union_preflight(conn, server, lease)
    factory = get_session_factory()
    managed = any(
        key in metadata for key in ("layer_transport", "afterglow_consume_id", "afterglow_catalog_consume_id")
    )
    if factory is None:
        if managed:
            raise RuntimeError("Managed resource receipt store is unavailable")
        return set()
    # Native attachment inventory includes root and every data disk. The
    # scheduler independently proves exclusive ownership and BDM flag readback.
    attachments = await usage.sdk_call(lambda: list(usage.safe_compute_proxy(conn).volume_attachments(identity)))
    volume_ids = {value(item, "volume_id") or value(item, "volumeId") or value(item, "id") for item in attachments}
    if any(not isinstance(item, str) or not item for item in volume_ids):
        raise RuntimeError("Native attachment identity is incomplete")
    baseline = {}
    for attachment in attachments:
        volume_id = value(attachment, "volume_id") or value(attachment, "volumeId") or value(attachment, "id")
        volume = await _get(_proxy(conn.block_storage).get_volume, volume_id)
        if volume is None or owner(volume) != project:
            raise RuntimeError("Managed attached volume project cannot be proven")
        attached = value(volume, "attachments")
        if not isinstance(attached, list) or len(attached) != 1 or value(attached[0], "server_id") != identity:
            raise RuntimeError("Managed attached volume is foreign or multiply attached")
        if value(volume, "is_multiattach", value(volume, "multiattach", False)) is not False:
            raise RuntimeError("Managed attached volume permits multiple attachments")
        flag = value(attachment, "delete_on_termination")
        if type(flag) is not bool:
            raise RuntimeError("Managed attachment termination flag is unknown")
        baseline[volume_id] = flag
    async with factory() as session:
        rows = await _rows(session, identity, project)
        if metadata.get("layer_transport") in {"block", "nfs"} and not rows:
            raise RuntimeError("Managed consume receipt is missing")
        ids = [row.id for row in rows]
    protected = set()
    for consume_id in ids:
        async with factory() as session:
            row = await session.get(LayerConsume, consume_id)
            snapshot = row.resource_snapshot or {}
            is_catalog = bool(snapshot.get("catalog_revision"))
        details = await _catalog_preflight(conn, row, server, lease) if is_catalog else {}
        async with factory() as session:
            row = (
                await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
            ).scalar_one()
            snapshot = dict(row.resource_snapshot or {})
            if row.cleanup_state in {"allocating", "pending"} and RECEIPT not in snapshot:
                raise RuntimeError("Managed consume allocation/cleanup still owns this server")
            if row.transport == "block":
                if not row.run_id or not isinstance(row.resources, list):
                    raise RuntimeError("Managed block run receipt missing")
                expected = {
                    "afterglow_consume_id": str(row.id),
                    "afterglow_run_id": row.run_id,
                    "afterglow_project_id": project,
                }
                fence(server, expected)
                if any(
                    item.get("id") is None or item.get("state") not in {"allocated", "deleted", "retained"}
                    for item in row.resources
                ):
                    raise RuntimeError("Managed block allocation outcome unresolved")
                details = {
                    "port_ids": [item["id"] for item in row.resources if item["kind"] == "port"],
                    "managed_volume_ids": [item["id"] for item in row.resources if item["kind"] in {"layer", "upper"}],
                    "layer_volume_ids": [item["id"] for item in row.resources if item["kind"] == "layer"],
                    "rules": [],
                }
            elif not is_catalog:
                details = await _nfs_receipt(conn, row, server)
            # Explicit consent applies ONLY to attached volumes. Detached managed
            # data is retained, never opportunistically Cinder-deleted.
            managed_volumes = set(details.get("managed_volume_ids", []))
            retained = managed_volumes - volume_ids if delete_volumes else managed_volumes
            prior = snapshot.get(RECEIPT)
            if prior and prior.get("complete"):
                raise RuntimeError("Managed resource cleanup already completed")
            receipt = {
                **details,
                "server_id": identity,
                "project_id": project,
                "baseline_delete_on_termination": (prior or {}).get("baseline_delete_on_termination", baseline),
                "volume_ids": sorted(volume_ids),
                "retained_volume_ids": sorted(retained),
                "deleted_volume_ids": sorted((managed_volumes & volume_ids) if delete_volumes else set()),
                # A kept overlay upper still needs its immutable lower stack,
                # including catalog/NFS consumers. Observe all kept managed
                # disks gone before releasing these existing artifact refs.
                "retained_source_volume_ids": sorted(retained if row.artifact_ids else set()),
                "health_id": metadata.get("union_health_id") or identity,
                "steps": (prior or {}).get("steps", {}),
                "complete": False,
            }
            if arm:
                snapshot[RECEIPT] = receipt
                row.resource_snapshot = snapshot
                row.updated_at = datetime.now(UTC)
                await _lease(lease)
                await session.commit()
    # Published source images and snapshots are not attached consumer copies;
    # neither is ever a cleanup target. No attached source authority is inferred.
    return protected


async def _nfs_receipt(conn, row, server):
    """Capture existing import journals; legacy unowned/shared rules stay shared."""
    from app.services import cache

    metadata = value(server, "metadata", {}) or {}
    import_id = metadata.get("afterglow_import_id")
    details = {"port_ids": [row.port_id] if row.port_id else [], "managed_volume_ids": [], "rules": []}
    upper = metadata.get("union_upper_volume_id")
    if upper and upper != "none":
        details["managed_volume_ids"] = [upper]
    if not import_id:
        # Pre-journal legacy NFS CIDR grants are project-shared, not VM-owned.
        return details
    redis = await cache._get_redis()
    if await redis.get(f"afterglow:builds:lease:import:{import_id}"):
        raise RuntimeError("NFS import still owns the consume")
    raw = await redis.get(f"afterglow:builds:journal:import:{import_id}")
    state = json.loads(raw) if raw else {}
    consumer = state.get("consumer") or {}
    if consumer.get("id") != row.id or not consumer.get("token"):
        raise RuntimeError("NFS consumer immutable journal unavailable")
    marker = dict(
        afterglow_import_id=import_id,
        afterglow_consume_id=str(row.id),
        afterglow_consume_token=consumer["token"],
        afterglow_owner_project_id=row.project_id,
    )
    if any(metadata.get(key) != expected for key, expected in marker.items()):
        raise RuntimeError("NFS consumer native marker differs")
    snapshot = row.resource_snapshot or {}
    details["share_project_id"] = (snapshot.get("openstack.service_project") or {}).get("id") or row.project_id
    prefix = f"consumer:{row.id}:rule:"
    observed = state.get("observed_ids") or {}
    journal_prefix = f"afterglow:builds:journal:import:{import_id}:submit:"
    async for native_key in redis.scan_iter(match=journal_prefix + prefix + "*"):
        key = native_key.decode() if isinstance(native_key, bytes) else native_key
        submitted_raw = await redis.get(key)
        submitted = json.loads(submitted_raw) if submitted_raw else {}
        step = key.removeprefix(journal_prefix)
        identity = observed.get(step) or (submitted.get("result") or {}).get("id")
        if submitted.get("state") == "rejected" and not identity:
            continue
        if not identity or not consumer.get("fixed_ip"):
            raise RuntimeError("NFS grant allocation remains unresolved")
        details["rules"].append(
            dict(s=step.removeprefix(prefix), i=identity, t="ip", a=consumer["fixed_ip"], l="ro", m=True)
        )
    if any(
        key.startswith(prefix) and not any(grant["i"] == identity for grant in details["rules"])
        for key, identity in observed.items()
    ):
        raise RuntimeError("NFS observed grant lacks immutable submission authority")
    return details


async def receipt_owns_cleanup(conn, row):
    """Keep armed uncertain writes fenced; an extended live VM uses old APIs."""
    receipt = (row.resource_snapshot or {}).get(RECEIPT)
    if not receipt:
        return False
    if receipt.get("complete"):
        return True
    server = await _get(usage.safe_compute_proxy(conn).get_server, receipt["server_id"])
    if server is None:
        return True
    usage.require_server_scope(conn, server, receipt["server_id"])
    schedule = usage.parse_schedule(server)
    if schedule is not None and schedule.state == "delete_requested":
        return True
    row.resource_snapshot = {key: val for key, val in row.resource_snapshot.items() if key != RECEIPT}
    return False


async def _save(session, row, receipt):
    row.resource_snapshot = {**(row.resource_snapshot or {}), RECEIPT: receipt}
    row.updated_at = datetime.now(UTC)
    await session.commit()


async def _once(session, row, receipt, key, mutation, lease):
    steps = dict(receipt.get("steps", {}))
    if key in steps:
        raise RuntimeError("Managed cleanup outcome unresolved; no automatic replay")
    steps[key] = "requested"
    receipt["steps"] = steps
    await _lease(lease)
    await _save(session, row, receipt)
    await _lease(lease)
    await mutation()


async def finish_managed_delete(conn, server_id, project_id, lease=None):
    """Observe native absence, then settle existing resource receipts only."""
    if usage._target_project(conn) != project_id:
        raise RuntimeError("Managed cleanup project scope differs")
    if vars(conn).get("_afterglow_usage_operator_scope") is not None:
        await usage.sdk_call(usage._assert_operator_scope, conn)
    await _lease(lease)
    if not await _absent(conn, server_id):
        return
    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        ids = [
            row.id for row in await _rows(session, server_id, project_id) if (row.resource_snapshot or {}).get(RECEIPT)
        ]
    for consume_id in ids:
        await _finish_receipt(conn, consume_id, lease)


async def _finish_receipt(conn, consume_id, lease):
    from app.services import manila
    from app.services.work_dispatcher import close_connection, open_connection

    async with get_session_factory()() as session:
        row = (
            await session.execute(select(LayerConsume).where(LayerConsume.id == consume_id).with_for_update())
        ).scalar_one()
        receipt = dict((row.resource_snapshot or {})[RECEIPT])
        await _lease(lease)
        if not await _absent(conn, receipt["server_id"]):
            return
        retained_sources = []
        for identity in receipt.get("retained_source_volume_ids", []):
            if await _get(_proxy(conn.block_storage).get_volume, identity) is not None:
                retained_sources.append(identity)
        receipt["retained_source_volume_ids"] = retained_sources
        if receipt.get("complete"):
            await _save(session, row, receipt)
            return
        for identity in receipt.get("retained_volume_ids", []):
            volume = await _get(_proxy(conn.block_storage).get_volume, identity)
            if volume is None:
                continue  # The owner may explicitly delete kept data meanwhile.
            attachments = value(volume, "attachments")
            if not isinstance(attachments, list):
                raise RuntimeError("Retained managed volume attachment state is unknown")
            if any(value(attachment, "server_id") == receipt["server_id"] for attachment in attachments):
                raise RuntimeError("Retained managed volume is still attached to the deleted server")
            # Reattachment to another VM or a verified ownership transfer does
            # not authorize us to mutate the volume or strand unrelated grants.
        for identity in receipt.get("deleted_volume_ids", []):
            if await _get(_proxy(conn.block_storage).get_volume, identity) is not None:
                raise RuntimeError("Nova volume deletion is not confirmed; no Cinder replay")
        share_conn = None
        try:
            rules = receipt.get("rules", [])
            if rules:
                service_project = receipt.get("share_project_id")
                if not service_project:
                    raise RuntimeError("Managed source share project receipt missing")
                if service_project == row.project_id:
                    share_conn = conn
                else:
                    share_conn = await open_connection(usage.operator_connection, service_project)
                    await usage.sdk_call(usage.prove_project_scope, share_conn, service_project)
                for grant in rules:
                    rule = await _grant_observation(share_conn, grant, receipt["server_id"], tracked=False)
                    if rule is None:
                        continue
                    await _once(
                        session,
                        row,
                        receipt,
                        "rule:" + grant["i"],
                        lambda grant=grant: usage.sdk_call(
                            manila.revoke_access_rule, share_conn, grant["s"], grant["i"]
                        ),
                        lease,
                    )
                    if await _grant_observation(share_conn, grant, receipt["server_id"], tracked=False) is not None:
                        raise RuntimeError("Managed source grant revocation is not confirmed")
            for identity in receipt.get("port_ids", []):
                proxy = _proxy(conn.network)
                port = await _get(proxy.get_port, identity)
                if port is None:
                    continue
                if owner(port) != row.project_id or value(port, "device_id") != "":
                    raise RuntimeError("Managed port ownership/detachment is not confirmed")
                # Floating IPs have their own exact IDs and project/port fences.
                for ip in await usage.sdk_call(
                    lambda proxy=proxy, identity=identity: list(proxy.ips(port_id=identity))
                ):
                    ip_id = value(ip, "id")
                    ip = await _get(proxy.get_ip, ip_id)
                    if ip is None:
                        continue
                    if owner(ip) != row.project_id or value(ip, "port_id") != identity:
                        raise RuntimeError("Managed floating IP ownership changed")
                    await _once(
                        session,
                        row,
                        receipt,
                        "ip:" + ip_id,
                        lambda ip_id=ip_id, proxy=proxy: usage.sdk_call(proxy.delete_ip, ip_id, ignore_missing=False),
                        lease,
                    )
                    if await _get(proxy.get_ip, ip_id) is not None:
                        raise RuntimeError("Managed floating IP deletion is not confirmed")
                await _once(
                    session,
                    row,
                    receipt,
                    "port:" + identity,
                    lambda identity=identity, proxy=proxy: usage.sdk_call(
                        proxy.delete_port, identity, ignore_missing=False
                    ),
                    lease,
                )
                if await _get(proxy.get_port, identity) is not None:
                    raise RuntimeError("Managed port deletion is not confirmed")
            await _lease(lease)
            await _revoke_health(receipt["health_id"], row.project_id, receipt["server_id"])
            if isinstance(row.resources, list):
                row.resources = [
                    {**item, "state": "retained" if item.get("id") in receipt["retained_volume_ids"] else "deleted"}
                    for item in row.resources
                ]
            elif (row.resource_snapshot or {}).get("catalog_revision"):
                row.resources = {
                    **(row.resources or {}),
                    "catalog_cleanup_complete": True,
                    "catalog_retained_volume_ids": receipt["retained_volume_ids"],
                }
            receipt["complete"] = True
            row.cleanup_state = "complete"
            row.status = "deleted"
            row.completed_at = datetime.now(UTC)
            await _lease(lease)
            await _save(session, row, receipt)
        finally:
            if share_conn is not None and share_conn is not conn:
                await close_connection(share_conn)


async def reconcile_managed_deletes(*, connection_factory=None, redis=None):
    """Restart-safe resource-only scan, independent of Nova schedule census."""
    from app.services.work_dispatcher import close_connection, open_connection

    factory = get_session_factory()
    if factory is None:
        return
    async with factory() as session:
        rows = (await session.execute(select(LayerConsume))).scalars().all()
        pending = {
            (receipt["project_id"], receipt["server_id"])
            for row in rows
            if isinstance(receipt := (row.resource_snapshot or {}).get(RECEIPT), dict)
            and (not receipt.get("complete") or receipt.get("retained_source_volume_ids"))
        }
    for project, identity in pending:
        conn = None
        try:
            conn = await open_connection(connection_factory or usage.operator_connection, project)
            await usage.sdk_call(usage.prove_project_scope, conn, project)
            async with usage.usage_lease(conn, project, identity, redis=redis) as lease:
                if lease is not None:
                    await finish_managed_delete(conn, identity, project, lease)
        except Exception:
            _logger.warning("Managed instance resource cleanup remains unresolved: server=%s", identity, exc_info=True)
        finally:
            if conn is not None:
                await close_connection(conn)
