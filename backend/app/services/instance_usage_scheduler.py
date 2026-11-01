"""Native Nova usage schedules; Redis holds coordination, never schedule records.

Requested markers mean a write MAY have happened. They are reconciled by native
status/readback, never retried, including after a process restart. A failed flag
preparation can require operator reconciliation; safety wins over auto-cleanup.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import secrets
from collections.abc import Mapping
from contextlib import asynccontextmanager, nullcontext, suppress
from datetime import UTC, datetime
from functools import partial

from fastapi import HTTPException
from openstack.exceptions import ResourceNotFound

from app.services import instance_usage as usage
from app.services.cache import _get_redis
from app.services.nova import flavor_extra_specs
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher, checkpoint, work_lease

_logger = logging.getLogger(__name__)
_PREFIX = "afterglow:instance_usage"
_POLL_SECONDS = 60
_LEASE_SECONDS = 90
_REQUESTED = {"shelve_requested", "offload_requested", "stop_requested", "delete_requested", "volume_flags_requested"}
_IN_FLIGHT = _REQUESTED | {"unknown", "volumes_ready"}
_SAFE_REQUEST = dict(redirect=False, allow_reauth=False, connect_retries=0, status_code_retries=0)


def _value(resource, key, default=None):
    return resource.get(key, default) if isinstance(resource, Mapping) else getattr(resource, key, default)


def _clock(now=None):
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        raise ValueError("Usage scheduler requires an aware clock")
    return now.astimezone(UTC)


def _project(server):
    return _value(server, "project_id") or _value(server, "tenant_id")


def _identifier(value):
    return isinstance(value, str) and bool(value) and all(c.isalnum() or c in "-_." for c in value)


def _safe_proxy(proxy):
    local = copy.copy(proxy)
    local.request = partial(proxy.request, **_SAFE_REQUEST)
    return local


@asynccontextmanager
async def _connection(factory, *args):
    # A cancelled factory still owns sockets when its thread eventually returns.
    task = asyncio.create_task(asyncio.to_thread(factory, *args))
    conn = None
    try:
        conn = await asyncio.shield(task)
        yield conn
    finally:
        if conn is None:
            while not task.done():
                try:
                    await asyncio.shield(task)
                except asyncio.CancelledError:
                    continue
                except Exception:
                    break
            if not task.cancelled():
                with suppress(Exception):
                    conn = task.result()
        if conn is not None:
            await usage.sdk_call(conn.close)


def _prove_project(conn, project_id):
    access = conn.session.auth.get_access(conn.session)
    if access.project_id != project_id or access.project_scoped is not True or access.system_scoped is not False:
        raise RuntimeError("Native credentials do not prove the exact scheduled project")
    conn._afterglow_project_id = project_id
    conn._afterglow_authenticated_project_id = project_id


def _catalog(conn):
    catalog = {}
    proxy = usage.safe_compute_proxy(conn)
    for flavor in proxy.flavors(details=True, is_public=None):
        body = getattr(getattr(flavor, "_body", None), "attributes", None)
        specs = flavor_extra_specs(proxy, flavor)
        identifier = body.get("id") if isinstance(body, Mapping) else _value(flavor, "id")
        if not _identifier(identifier):
            raise RuntimeError("Native flavor catalog UUID is unavailable")
        catalog[identifier] = dict(
            id=identifier, name=flavor.name, vcpus=flavor.vcpus, ram=flavor.ram, extra_specs=dict(specs)
        )
    return catalog


def _native_flavor(server):
    # SDK Flavor.id falls back to original_name, and to_dict also materializes
    # absent CPU/RAM defaults. Read only the fields Nova actually returned.
    native = getattr(server, "flavor", None)
    body = getattr(getattr(native, "_body", None), "attributes", None)
    if isinstance(body, Mapping):
        return dict(body)
    return _value(server, "flavor")


def _embedded_flavor(flavor):
    return "original_name" in flavor or "vcpus" in flavor or "ram" in flavor


def _required(server, catalog):
    flavor = _native_flavor(server)
    if not isinstance(flavor, Mapping):
        return False
    if usage.requires_schedule(dict(flavor)):
        return True
    if _embedded_flavor(flavor):
        return False
    selected = catalog.get(str(flavor.get("id", "")))
    return selected is not None and usage.requires_schedule(selected)


def _needs_flavor_identity(server, catalog):
    flavor = _native_flavor(server)
    if not isinstance(flavor, Mapping) or (not _embedded_flavor(flavor) and flavor.get("id")):
        return False
    # Shape is only a query filter, never identity proof. CPU/RAM cannot change
    # on an existing Nova flavor; absent native dimensions remain uncertain.
    return any(
        usage.requires_schedule({**entry, "vcpus": 0, "ram": 0})
        and all(flavor.get(key) is None or flavor[key] == entry[key] for key in ("vcpus", "ram"))
        for entry in catalog.values()
    )


def _legacy_census_ids(conn, candidates):
    proxy = usage.safe_compute_proxy(conn)
    proxy.default_microversion = "2.46"
    result, seen = {}, set()
    for server in proxy.servers(details=True, all_projects=True):
        key = (_project(server), _value(server, "id"))
        if key not in candidates:
            continue
        if key in seen:
            result.pop(key, None)
            continue
        seen.add(key)
        if any(_value(server, field) not in {None, key[0]} for field in ("project_id", "tenant_id")):
            continue
        flavor = _native_flavor(server)
        if isinstance(flavor, Mapping) and not _embedded_flavor(flavor) and _identifier(flavor.get("id")):
            result[key] = flavor["id"]
    return result


def _resolve_required(conn, server, catalog):
    if _required(server, catalog):
        return True
    if not _needs_flavor_identity(server, catalog):
        return False
    proxy = usage.safe_compute_proxy(conn)
    proxy.default_microversion = "2.46"
    exact = proxy.get_server(_value(server, "id"))
    if _value(exact, "id") != _value(server, "id") or _project(exact) != _project(server):
        raise RuntimeError("Legacy flavor identity read changed native server identity or ownership")
    if any(_value(exact, key) not in {None, _project(server)} for key in ("project_id", "tenant_id")):
        raise RuntimeError("Legacy flavor identity read returned conflicting ownership")
    actual = _native_flavor(exact)
    if not isinstance(actual, Mapping) or _embedded_flavor(actual) or not _identifier(actual.get("id")):
        raise RuntimeError("Native flavor UUID cannot be proven")
    selected = catalog.get(actual["id"])
    return selected is not None and usage.requires_schedule(selected)


def _census(conn, now=None):
    clock = _clock(now)
    catalog = _catalog(conn)
    runnable = []
    candidates = set()
    for server in usage.safe_compute_proxy(conn).servers(details=True, all_projects=True):
        project_id, server_id = _project(server), _value(server, "id")
        if not _identifier(project_id) or not _identifier(server_id):
            _logger.warning("Usage census encountered an unidentifiable native server")
            continue
        try:
            schedule = usage.parse_schedule(server)
        except Exception:
            _logger.warning("Usage census refused invalid schedule (server=%s)", server_id)
            continue
        if schedule is None:
            due = _required(server, catalog)
            if not due and _needs_flavor_identity(server, catalog):
                candidates.add((project_id, server_id))
        else:
            due = datetime.fromisoformat(schedule.expires_at.replace("Z", "+00:00")) <= clock
            if schedule.state == "complete":
                # A native resume without changing the expired schedule is a
                # fresh shelve intent, not a retry of an unknown old request.
                due = due and schedule.expiry_action == "shelve" and _status(server) != "SHELVED_OFFLOADED"
        if due:
            runnable.append(f"{project_id}:{server_id}")
    if candidates:
        try:
            identities = _legacy_census_ids(conn, candidates)
        except Exception:
            _logger.warning("Usage census cannot prove legacy native flavor identities")
        else:
            for (project_id, server_id), flavor_id in identities.items():
                selected = catalog.get(flavor_id)
                if selected is not None and usage.requires_schedule(selected):
                    runnable.append(f"{project_id}:{server_id}")
    return runnable


async def _current(conn, lease, project_id, server_id, *, revision=None, due=None):
    await checkpoint()
    if not await lease.current():
        raise DispatcherUnavailable("Usage schedule lease was lost")
    await usage.sdk_call(_prove_project, conn, project_id)
    server = await usage.sdk_call(usage.safe_compute_proxy(conn).get_server, server_id)
    if _value(server, "id") != server_id or _project(server) != project_id:
        raise RuntimeError("Scheduled server identity or ownership changed")
    usage.require_server_scope(conn, server, server_id)
    info = usage.parse_schedule(server)
    if revision is not None and (info is None or info.revision != revision):
        raise RuntimeError("Usage schedule changed before operation")
    if due is not None and (info is None or datetime.fromisoformat(info.expires_at.replace("Z", "+00:00")) > due):
        raise RuntimeError("Usage schedule is no longer expired")
    await checkpoint()
    if not await lease.current():
        raise DispatcherUnavailable("Usage schedule lease was lost during native read")
    return server, info


async def _mark(conn, server, lease, state, error=""):
    await checkpoint()
    previous = usage.parse_schedule(server)
    server, _ = await _current(conn, lease, _project(server), _value(server, "id"), revision=previous.revision)
    if previous.state == state and (previous.last_error or "") == error:
        return server
    return await usage.write_schedule_metadata(
        conn,
        server,
        {
            usage.METADATA_PREFIX + "state": state,
            usage.METADATA_PREFIX + "revision": secrets.token_hex(16),
            usage.METADATA_PREFIX + "last_error": error,
        },
        lease=lease,
    )


def _status(server):
    status = _value(server, "status")
    task = _value(server, "task_state", _value(server, "OS-EXT-STS:task_state"))
    return status if isinstance(status, str) and not task else "BUSY"


def _attachment_id(attachment):
    return _value(attachment, "volume_id") or _value(attachment, "volumeId") or _value(attachment, "id")


def _volume_proof(conn, server_id, project_id, proxy):
    """Prove ALL attached volumes including boot, with no Cinder mutation."""
    attachments = list(proxy.volume_attachments(server_id))
    server = proxy.get_server(server_id)
    if _value(server, "id") != server_id or _project(server) != project_id:
        raise RuntimeError("Volume proof server identity or ownership changed")
    usage.require_server_scope(conn, server, server_id)
    attached = _value(server, "attached_volumes", _value(server, "os-extended-volumes:volumes_attached"))
    if not isinstance(attached, list):
        raise RuntimeError("Native server attached-volume inventory is unavailable")
    attached_ids = [_value(item, "id") for item in attached]
    if len(set(attached_ids)) != len(attached_ids):
        raise RuntimeError("Native server attached-volume inventory is ambiguous")
    volumes = {}
    for attachment in attachments:
        volume_id = _attachment_id(attachment)
        if not _identifier(volume_id) or volume_id in volumes:
            raise RuntimeError("Native volume attachment inventory is ambiguous")
        volume = _safe_proxy(conn.block_storage).get_volume(volume_id)
        owner = _value(volume, "project_id") or _value(volume, "os-vol-tenant-attr:tenant_id")
        links = _value(volume, "attachments")
        if _value(volume, "id") != volume_id or owner != project_id or not isinstance(links, list) or len(links) != 1:
            raise RuntimeError("Volume ownership or sole attachment cannot be proven")
        if any(_value(volume, key) not in {None, project_id} for key in ("project_id", "os-vol-tenant-attr:tenant_id")):
            raise RuntimeError("Conflicting native volume ownership fields")
        if (
            _value(links[0], "server_id") != server_id
            or _value(volume, "is_multiattach", _value(volume, "multiattach")) is not False
        ):
            raise RuntimeError("Shared or unknown volume attachment cannot be changed")
        if _value(attachment, "server_id") not in {None, server_id}:
            raise RuntimeError("Native volume attachment belongs to another server")
        flag = _value(attachment, "delete_on_termination")
        if type(flag) is not bool:
            raise RuntimeError("Nova 2.85 attachment deletion flag is unavailable")
        volumes[volume_id] = flag
    if set(volumes) != set(attached_ids):
        raise RuntimeError("Nova volume inventories disagree")
    return volumes


def _attachment_proxy(conn):
    proxy = usage.safe_compute_proxy(conn)
    proxy.default_microversion = "2.85"
    return proxy


async def _managed_prepare(conn, server, info, lease):
    from app.services.instance_usage_cleanup import prepare_managed_delete

    await checkpoint()
    if not await lease.current():
        raise DispatcherUnavailable("Usage lease lost before managed deletion proof")
    protected = await prepare_managed_delete(conn, server, info.delete_volumes, lease)
    if not isinstance(protected, set) or any(not _identifier(item) for item in protected):
        raise RuntimeError("Managed source-volume protection proof is invalid")
    return protected


async def _prepare_volumes(conn, server, info, lease, project_id, server_id, clock):
    proxy = _attachment_proxy(conn)
    protected = await _managed_prepare(conn, server, info, lease)
    before = await usage.sdk_call(_volume_proof, conn, server_id, project_id, proxy)
    # Mark BEFORE the first BDM write; restart never replays a possibly sent PUT.
    if info.state != "volume_flags_requested":
        server = await _mark(conn, server, lease, "volume_flags_requested")
        info = usage.parse_schedule(server)
        for volume_id, flag in before.items():
            desired = info.delete_volumes and volume_id not in protected
            if flag == desired:
                continue
            server, info = await _current(conn, lease, project_id, server_id, revision=info.revision, due=clock)
            if info.state != "volume_flags_requested" or _status(server) not in {
                "SHUTOFF",
                "SHELVED",
                "SHELVED_OFFLOADED",
            }:
                raise RuntimeError("Server changed during volume preparation")
            if await _managed_prepare(conn, server, info, lease) != protected:
                raise RuntimeError("Managed source-volume protection changed during preparation")
            fresh = await usage.sdk_call(_volume_proof, conn, server_id, project_id, proxy)
            if fresh.keys() != before.keys():
                raise RuntimeError("Native attachment inventory changed during preparation")
            # The current flag can have been changed externally; only the exact
            # inspected original value authorizes this one update.
            if fresh[volume_id] != flag:
                raise RuntimeError("Volume deletion flag changed during preparation")
            server, info = await _current(conn, lease, project_id, server_id, revision=info.revision, due=clock)
            if info.state != "volume_flags_requested" or _status(server) not in {
                "SHUTOFF",
                "SHELVED",
                "SHELVED_OFFLOADED",
            }:
                raise RuntimeError("Server changed immediately before attachment mutation")
            await checkpoint()
            if not await lease.current():
                raise DispatcherUnavailable("Usage lease lost before attachment mutation")
            await usage.sdk_call(proxy.update_volume_attachment, server_id, volume_id, delete_on_termination=desired)
    verified = await usage.sdk_call(_volume_proof, conn, server_id, project_id, proxy)
    if verified.keys() != before.keys() or any(
        flag != (info.delete_volumes and volume_id not in protected) for volume_id, flag in verified.items()
    ):
        raise RuntimeError("Volume deletion flags require manual reconciliation; no write replay")
    server, info = await _current(conn, lease, project_id, server_id, revision=info.revision, due=clock)
    if _status(server) not in {"SHUTOFF", "SHELVED", "SHELVED_OFFLOADED"}:
        raise RuntimeError("Server changed before deletion")
    return await _mark(conn, server, lease, "volumes_ready")


async def _dispatch(conn, server, info, lease, project_id, server_id, clock, state, method):
    server = await _mark(conn, server, lease, state)
    marked = usage.parse_schedule(server)
    server, marked = await _current(conn, lease, project_id, server_id, revision=marked.revision, due=clock)
    if marked.state != state:
        raise RuntimeError("Usage operation marker changed")
    allowed = {
        "shelve_requested": {"ACTIVE", "SHUTOFF"},
        "stop_requested": {"ACTIVE"},
        "offload_requested": {"SHELVED"},
        "delete_requested": {"SHUTOFF", "SHELVED", "SHELVED_OFFLOADED"},
    }
    if _status(server) not in allowed[state]:
        raise RuntimeError("Native status changed before lifecycle dispatch")
    if state == "delete_requested":
        # Re-prove every volume after the delete marker, immediately before DELETE.
        protected = await _managed_prepare(conn, server, marked, lease)
        flags = await usage.sdk_call(_volume_proof, conn, server_id, project_id, _attachment_proxy(conn))
        if any(value != (marked.delete_volumes and volume_id not in protected) for volume_id, value in flags.items()):
            raise RuntimeError("Deletion flag proof changed before server deletion")
        server, marked = await _current(conn, lease, project_id, server_id, revision=marked.revision, due=clock)
        if marked.state != state or _status(server) not in allowed[state]:
            raise RuntimeError("Server changed immediately before deletion")
        from app.services.instance_usage_cleanup import finalize_managed_delete_preflight

        server = await finalize_managed_delete_preflight(conn, server, lease)
        marked = usage.parse_schedule(server)
        server, marked = await _current(conn, lease, project_id, server_id, revision=marked.revision, due=clock)
        if marked.state != state or _status(server) not in allowed[state]:
            raise RuntimeError("Server changed after managed grant finalization")
        protected = await _managed_prepare(conn, server, marked, lease)
        flags = await usage.sdk_call(_volume_proof, conn, server_id, project_id, _attachment_proxy(conn))
        if any(value != (marked.delete_volumes and volume_id not in protected) for volume_id, value in flags.items()):
            raise RuntimeError("Deletion flag proof changed after managed grant finalization")
        server, marked = await _current(conn, lease, project_id, server_id, revision=marked.revision, due=clock)
        if marked.state != state or _status(server) not in allowed[state]:
            raise RuntimeError("Server changed immediately before finalized deletion")
    await checkpoint()
    if not await lease.current():
        raise DispatcherUnavailable("Usage lease lost before lifecycle mutation")
    await usage.sdk_call(method, server_id)
    if state == "delete_requested":
        try:
            await _current(conn, lease, project_id, server_id, revision=marked.revision, due=clock)
        except ResourceNotFound:
            from app.services.instance_usage_cleanup import finish_managed_delete

            await finish_managed_delete(conn, server_id, project_id, lease=lease)
    # No blind status polling or compensating cleanup. The next census reconciles.


class _DispatchLease:
    """Every core metadata write also fences the dispatcher claim, not just Redis's VM lock."""

    def __init__(self, lease):
        self.lease = lease

    def __getattr__(self, name):
        return getattr(self.lease, name)

    async def current(self):
        if self.lost:
            return False
        await checkpoint()
        return await self.lease.current()


async def _cycle(conn, project_id, server_id, clock, redis):
    await usage.sdk_call(_prove_project, conn, project_id)
    async with usage.usage_lease(conn, project_id, server_id, redis=redis) as lease:
        if lease is None:
            return
        lease = _DispatchLease(lease)
        try:
            server, info = await _current(conn, lease, project_id, server_id)
        except ResourceNotFound:
            from app.services.instance_usage_cleanup import finish_managed_delete

            await finish_managed_delete(conn, server_id, project_id, lease=lease)
            return  # Exact scoped native 404 only; no inventory row is an authority.
        if info is None:
            catalog = await usage.sdk_call(_catalog, conn)
            if not await usage.sdk_call(_resolve_required, conn, server, catalog):
                return
            server, info = await _current(conn, lease, project_id, server_id)
            if info is not None or not await usage.sdk_call(_resolve_required, conn, server, catalog):
                return
            # Grace starts when this first native enrollment succeeds, not birth.
            await checkpoint()
            await usage.write_schedule_metadata(conn, server, usage.adoption_metadata(now=clock), lease=lease)
            return
        if datetime.fromisoformat(info.expires_at.replace("Z", "+00:00")) > clock:
            return
        if info.state == "complete" and (info.expiry_action != "shelve" or _status(server) == "SHELVED_OFFLOADED"):
            return
        server, info = await _current(conn, lease, project_id, server_id, revision=info.revision, due=clock)
        status = _status(server)
        proxy = usage.safe_compute_proxy(conn)
        try:
            if info.expiry_action == "shelve":
                if status == "SHELVED_OFFLOADED":
                    await _mark(conn, server, lease, "complete")
                elif status == "SHELVED" and info.state in {"active", "blocked", "complete", "shelve_requested"}:
                    await _dispatch(
                        conn,
                        server,
                        info,
                        lease,
                        project_id,
                        server_id,
                        clock,
                        "offload_requested",
                        proxy.shelve_offload_server,
                    )
                elif status in {"ACTIVE", "SHUTOFF"} and info.state in {"active", "blocked", "complete"}:
                    await _dispatch(
                        conn, server, info, lease, project_id, server_id, clock, "shelve_requested", proxy.shelve_server
                    )
                elif info.state in _IN_FLIGHT:
                    return  # Requested/unknown markers are read-only until native status advances.
                else:
                    await _mark(
                        conn, server, lease, "blocked", "Native server is busy or not in a supported shelve state"
                    )
            else:
                if info.state == "delete_requested":
                    return  # Never replay DELETE or overwrite managed grant operation markers.
                elif status == "ACTIVE" and info.state in {"active", "blocked"}:
                    await _managed_prepare(conn, server, info, lease)
                    await _dispatch(
                        conn, server, info, lease, project_id, server_id, clock, "stop_requested", proxy.stop_server
                    )
                elif status in {"SHUTOFF", "SHELVED", "SHELVED_OFFLOADED"} and info.state in {
                    "active",
                    "blocked",
                    "stop_requested",
                    "volume_flags_requested",
                    "volumes_ready",
                }:
                    if info.state != "volumes_ready":
                        server = await _prepare_volumes(conn, server, info, lease, project_id, server_id, clock)
                        info = usage.parse_schedule(server)
                    await _dispatch(
                        conn,
                        server,
                        info,
                        lease,
                        project_id,
                        server_id,
                        clock,
                        "delete_requested",
                        partial(proxy.delete_server, ignore_missing=False, force=False),
                    )
                elif info.state in _IN_FLIGHT:
                    return  # Preserve the exact durable operation marker across restarts.
                else:
                    await _mark(
                        conn, server, lease, "blocked", "Native server is busy or not in a supported delete state"
                    )
        except (DispatcherUnavailable, asyncio.CancelledError):
            raise
        except Exception as exc:
            if isinstance(exc, HTTPException) and exc.status_code == 502:
                # The marker write itself may have an unknown result. Do not
                # issue a second metadata POST merely to describe its failure.
                raise
            # A requested marker MUST survive an uncertain action or flag write.
            # Never reset it to a state that authorizes another native request.
            with suppress(Exception):
                fresh, current = await _current(conn, lease, project_id, server_id)
                if (
                    current is not None
                    and current.state not in _IN_FLIGHT
                    and current.revision == usage.parse_schedule(server).revision
                ):
                    await _mark(
                        conn,
                        fresh,
                        lease,
                        "blocked",
                        "Native operation or safety proof failed; inspect native status before reconciliation",
                    )
            raise


async def _schedule_tick(dispatcher, census_connection_factory=None, now=None):
    if not await dispatcher.is_leader():
        return
    if census_connection_factory is None:
        from app.services.keystone import get_admin_project_connection

        census_connection_factory = get_admin_project_connection
    async with _connection(census_connection_factory) as conn:
        runnable = await usage.sdk_call(_census, conn, now)
    await dispatcher.publish(runnable)


async def _execute_tick(dispatcher, clock, connection_factory=None, redis=None):
    if connection_factory is None:
        from app.services.keystone import get_admin_connection_for_project

        connection_factory = get_admin_connection_for_project
    for _ in range(await dispatcher.pending()):
        claimed = await dispatcher.claim(_LEASE_SECONDS)
        if claimed is None:
            break
        member, owner = claimed
        project_id, separator, server_id = member.partition(":")
        if not separator or not _identifier(project_id) or not _identifier(server_id):
            continue
        try:
            async with (
                work_lease(dispatcher, member, owner, seconds=_LEASE_SECONDS),
                _connection(connection_factory, project_id) as conn,
            ):
                await _cycle(conn, project_id, server_id, clock, redis if redis is not None else dispatcher.redis)
        except DispatcherUnavailable:
            raise
        except Exception:
            _logger.warning("Usage schedule cycle failed (server=%s)", server_id, exc_info=True)


async def scheduler_tick(
    *, now=None, census_connection_factory=None, connection_factory=None, dispatcher=None, redis=None
):
    """One deterministic census/dispatch cycle, with native factories injectable."""
    clock = _clock(now)
    if dispatcher is not None and dispatcher.prefix != _PREFIX:
        raise ValueError("Work dispatcher namespace does not match instance usage scheduling")
    if redis is None:
        redis = dispatcher.redis if dispatcher is not None else await _get_redis()
    context = WorkDispatcher(redis, _PREFIX) if dispatcher is None else nullcontext(dispatcher)
    async with context as participant:
        await _schedule_tick(participant, census_connection_factory, clock)
        await _execute_tick(participant, clock, connection_factory, redis)
        await _cleanup_tick(participant, connection_factory, redis)


async def _cleanup_tick(dispatcher, connection_factory=None, redis=None):
    # Resource receipts, not schedules, survive a deleted Nova server. Their
    # independent scan is essential when an accepted DELETE reply was lost.
    if await dispatcher.is_leader():
        from app.services.instance_usage_cleanup import reconcile_managed_deletes

        await reconcile_managed_deletes(
            connection_factory=connection_factory, redis=redis if redis is not None else dispatcher.redis
        )


async def scheduler_loop():
    """One independently registered loop, drained by normal main shutdown."""
    while True:
        try:
            async with WorkDispatcher(await _get_redis(), _PREFIX) as dispatcher:
                while True:
                    try:
                        await _schedule_tick(dispatcher, now=_clock())
                    except DispatcherUnavailable:
                        raise
                    except Exception:
                        _logger.warning("Instance usage native census failed", exc_info=True)
                    try:
                        await _execute_tick(dispatcher, _clock())
                    except DispatcherUnavailable:
                        raise
                    except Exception:
                        _logger.warning("Instance usage assigned execution failed", exc_info=True)
                    try:
                        await _cleanup_tick(dispatcher)
                    except DispatcherUnavailable:
                        raise
                    except Exception:
                        _logger.warning("Instance usage managed resource reconciliation failed", exc_info=True)
                    await asyncio.sleep(_POLL_SECONDS)
        except Exception:
            _logger.warning("Instance usage coordination unavailable", exc_info=True)
        await asyncio.sleep(_POLL_SECONDS)
