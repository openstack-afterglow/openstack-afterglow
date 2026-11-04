"""Read-only, dispatcher-warmed flavor metadata and reusable host observations.

Stored data is advisory. Native visibility and tenant quotas remain request-owned;
create admission never uses this observation in place of fresh native reads.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from datetime import UTC, datetime

from app.config import get_settings
from app.models.compute import FlavorInfo
from app.services import cache, flavor_automation_policy, flavor_capacity, keystone, nova
from app.services.work_dispatcher import checkpoint, close_connection, open_connection, run_sync
from app.utils.log import exception_metadata

_logger = logging.getLogger(__name__)
_REFRESH_SECONDS = 10
_CAPACITY_MAX_AGE = 30
_CATALOG_MAX_AGE = 90
_MAX_BYTES = 16 * 1024 * 1024
_MAX_FLAVORS = 4096


def _key(kind):
    settings = get_settings()
    source = [
        settings.os_auth_url,
        settings.os_region_name,
        settings.os_interface,
        settings.os_username,
        settings.os_user_domain_name,
        settings.os_project_name,
        settings.os_project_domain_name,
    ]
    identity = hashlib.sha256(json.dumps(source, separators=(",", ":")).encode()).hexdigest()
    if kind == "catalog":
        return f"afterglow:nova:discovery-v1-{identity}:flavors"
    return f"afterglow:flavor-discovery:v1:{identity}:{kind}"


def _profile_key(policy):
    return hashlib.sha256(
        json.dumps(policy["gpu_profiles"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _request_key(service, path, params):
    pairs = sorted((params or {}).items()) if isinstance(params, dict) else list(params or [])
    return json.dumps([service, path, pairs], separators=(",", ":"))


class _RecordedClient:
    def __init__(self, native=None, records=None, observed_at=None):
        self.native = native
        self.records = {} if records is None else records
        self.observed_at = observed_at
        # These are native method attempts, not dispatched HTTP GET counts:
        # the client's deadline guard can reject an attempt before transport I/O.
        self.native_reads_attempted = 0
        self.native_reads_completed = 0
        self.native_reads_failed = 0

    def _read(self, service, path, params, deadline, *, missing_ok=False):
        key = _request_key(service, path, params)
        if self.native is None:
            if key not in self.records:
                raise flavor_capacity._AuthorityError("capacity shape has not been observed")
            value = self.records[key]
            if value is None and not missing_ok:
                raise flavor_capacity._AuthorityError("required capacity observation is missing")
            return value
        self.native_reads_attempted += 1
        try:
            if service == "compute":
                value = self.native.compute(path, params, deadline)
            else:
                value = self.native.placement(path, params, deadline, missing_ok=missing_ok)
        except Exception:
            self.native_reads_failed += 1
            raise
        self.native_reads_completed += 1
        self.records[key] = value
        return value

    def compute(self, path, params, deadline):
        return self._read("compute", path, params, deadline)

    def placement(self, path, params, deadline, *, missing_ok=False):
        return self._read("placement", path, params, deadline, missing_ok=missing_ok)


async def _load(kind, maximum_age):
    try:
        raw = await cache.get_backend().get(_key(kind))
        if raw is None or len(raw) > _MAX_BYTES:
            return None
        value = json.loads(raw)
        timestamp = value.get("observed_at")
        if (
            value.get("schema") != 1
            or type(timestamp) not in (int, float)
            or not 0 <= time.time() - timestamp < maximum_age
        ):
            return None
        return value
    except Exception:
        _logger.warning("Flavor discovery observation unavailable", exc_info=True)
        return None


async def _store(kind, value, ttl):
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode()) > _MAX_BYTES:
        raise ValueError("flavor discovery observation exceeds size bound")
    await checkpoint()
    await cache.get_backend().set(_key(kind), raw, ttl)


async def list_flavors(conn):
    """Return metadata intersected with current native target visibility, never cached ACLs."""
    value = await _load("catalog", _CATALOG_MAX_AGE)
    if value is None:
        return await run_sync(nova.list_flavors, conn)
    try:
        rows = value["flavors"]
        if not isinstance(rows, list) or len(rows) > _MAX_FLAVORS:
            raise ValueError("invalid flavor discovery catalog")
        flavors = [FlavorInfo.model_validate(row) for row in rows]
        if len({flavor.id for flavor in flavors}) != len(flavors):
            raise ValueError("duplicate flavor discovery identity")
    except (KeyError, TypeError, ValueError):
        return await run_sync(nova.list_flavors, conn)
    visible = await run_sync(nova.project_flavor_visibility, conn)
    if visible.keys() - {flavor.id for flavor in flavors}:
        return await run_sync(nova.list_flavors, conn)
    return [flavor.model_copy(update={"is_public": visible[flavor.id]}) for flavor in flavors if flavor.id in visible]


async def capacity_client(policy):
    value = await _load("capacity", _CAPACITY_MAX_AGE)
    if value is None or value.get("profiles") != _profile_key(policy) or not isinstance(value.get("records"), dict):
        return None
    return _RecordedClient(
        records=value["records"], observed_at=datetime.fromtimestamp(value["observed_at"], UTC).isoformat()
    )


def _failure_reason(exc, deadline):
    if time.monotonic() >= deadline:
        return "deadline"
    # Structural diagnostics preserve chained transport errors without touching
    # exception messages, response bodies, endpoints, or credential properties.
    metadata = exception_metadata((type(exc), exc, exc.__traceback__))
    types = {metadata["type"], *(node["type"] for node in metadata["causes"])}
    if types & {"TimeoutError", "Timeout", "ConnectTimeout", "ReadTimeout"}:
        return "timeout"
    if types & {"ConnectionError", "ConnectFailure", "ConnectionFailure", "ConnectError"}:
        return "transport"
    if isinstance(exc, flavor_capacity._AuthorityError):
        return "observation_rejected"
    return "unexpected"


def _observe(conn, flavors, policy):
    """Collect each project-independent Placement shape once; project/AZ fitting stays local."""
    started = time.monotonic()
    deadline = started + flavor_capacity._DEADLINE_SECONDS
    client = None
    shapes = set()
    attempted = succeeded = 0
    failures = {}
    stage = "client"

    def failed(exc):
        reason = _failure_reason(exc, deadline)
        group = (stage, reason)
        if group not in failures:
            metadata = exception_metadata((type(exc), exc, exc.__traceback__))
            failures[group] = {
                "stage": stage,
                "reason": reason,
                "count": 0,
                "exception_type": metadata["type"],
            }
            for key in ("status_code", "http_status", "status", "errno"):
                if key in metadata:
                    failures[group][key] = metadata[key]
        failures[group]["count"] += 1

    try:
        client = _RecordedClient(flavor_capacity._Client(conn))
        snapshot = flavor_capacity._Snapshot()
        stage = "parse"
        demands, _ = flavor_capacity._parse_all(flavors, policy["gpu_profiles"])
        shapes = {demand.shape for demand in demands.values() if demand is not None}
        stage = "host_facts"
        snapshot.facts(client, deadline)
        stage = "provider_roots"
        snapshot.provider_roots(client, deadline)
        for shape in sorted(shapes, key=lambda shape: repr(shape)):
            if time.monotonic() >= deadline:
                break
            attempted += 1
            try:
                stage = "allocation_candidates"
                view = snapshot.shape(client, deadline, shape)
                # Fetch CPU/RAM max_unit even for tenant-restricted hosts. The stored
                # facts, not an arbitrary warmup tenant, determine their later visibility.
                stage = "inventories"
                for candidates in view.roots.values():
                    for amounts in candidates:
                        for provider, resource in amounts:
                            if resource in (shape.cpu_class, "MEMORY_MB"):
                                snapshot.max_unit(client, deadline, provider, resource)
                succeeded += 1
            except Exception as exc:
                failed(exc)
        return client.records
    except Exception as exc:
        failed(exc)
        raise
    finally:
        skipped = len(shapes) - attempted
        if failures or skipped:
            _logger.warning(
                "Flavor discovery observation incomplete",
                extra={
                    "shapes_total": len(shapes),
                    "shapes_attempted": attempted,
                    "shapes_succeeded": succeeded,
                    "shapes_failed": attempted - succeeded,
                    "shapes_skipped": skipped,
                    "deadline_exhausted": time.monotonic() >= deadline,
                    "native_reads_attempted": client.native_reads_attempted if client is not None else 0,
                    "native_reads_completed": client.native_reads_completed if client is not None else 0,
                    "native_reads_failed": client.native_reads_failed if client is not None else 0,
                    "observations_recorded": len(client.records) if client is not None else 0,
                    "duration_ms": round((time.monotonic() - started) * 1000, 1),
                    "failures": list(failures.values()),
                },
            )


async def refresh_once(conn):
    started = time.time()
    flavors = await run_sync(nova.list_catalog_flavors, conn)
    if len(flavors) > _MAX_FLAVORS:
        raise ValueError("flavor discovery catalog exceeds bound")
    await _store(
        "catalog",
        {"schema": 1, "observed_at": started, "flavors": [flavor.model_dump() for flavor in flavors]},
        _CATALOG_MAX_AGE,
    )
    policy = await flavor_automation_policy.load_policy()
    await flavor_capacity._refresh_gpu_catalog()
    observed_at = time.time()
    records = await run_sync(_observe, conn, flavors, policy)
    if _profile_key(await flavor_automation_policy.load_policy()) != _profile_key(policy):
        raise ValueError("GPU approval changed during flavor observation")
    await _store(
        "capacity",
        {"schema": 1, "observed_at": observed_at, "profiles": _profile_key(policy), "records": records},
        _CAPACITY_MAX_AGE,
    )


async def discovery_loop():
    while True:
        try:
            await checkpoint()
            conn = await open_connection(keystone.get_admin_project_connection)
            try:
                await refresh_once(conn)
            finally:
                await close_connection(conn)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Background flavor discovery unavailable", exc_info=True)
            await checkpoint()
            await cache.get_backend().delete(_key("capacity"))
        await asyncio.sleep(_REFRESH_SECONDS)
