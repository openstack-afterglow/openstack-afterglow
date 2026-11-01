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

    def _read(self, service, path, params, deadline, *, missing_ok=False):
        key = _request_key(service, path, params)
        if self.native is None:
            if key not in self.records:
                raise flavor_capacity._AuthorityError("capacity shape has not been observed")
            value = self.records[key]
            if value is None and not missing_ok:
                raise flavor_capacity._AuthorityError("required capacity observation is missing")
            return value
        if service == "compute":
            value = self.native.compute(path, params, deadline)
        else:
            value = self.native.placement(path, params, deadline, missing_ok=missing_ok)
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


def _observe(conn, flavors, policy):
    """Collect each project-independent Placement shape once; project/AZ fitting stays local."""
    client = _RecordedClient(flavor_capacity._Client(conn))
    snapshot = flavor_capacity._Snapshot()
    demands, _ = flavor_capacity._parse_all(flavors, policy["gpu_profiles"])
    deadline = time.monotonic() + flavor_capacity._DEADLINE_SECONDS
    snapshot.facts(client, deadline)
    snapshot.provider_roots(client, deadline)
    shapes = {demand.shape for demand in demands.values() if demand is not None}
    for shape in sorted(shapes, key=lambda shape: repr(shape)):
        if time.monotonic() >= deadline:
            break
        try:
            view = snapshot.shape(client, deadline, shape)
            # Fetch CPU/RAM max_unit even for tenant-restricted hosts. The stored
            # facts, not an arbitrary warmup tenant, determine their later visibility.
            for candidates in view.roots.values():
                for amounts in candidates:
                    for provider, resource in amounts:
                        if resource in (shape.cpu_class, "MEMORY_MB"):
                            snapshot.max_unit(client, deadline, provider, resource)
        except Exception:
            _logger.warning("Flavor discovery shape unavailable", exc_info=False)
    return client.records


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
