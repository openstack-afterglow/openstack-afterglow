"""Lifecycle-only refresh of the existing database resource-policy authority."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping

from app.services import resource_policies
from app.services import resource_policy_store as store
from app.services.work_dispatcher import checkpoint, close_connection, open_connection, run_sync

_logger = logging.getLogger(__name__)
_AZ_KINDS = {"compute_availability_zone", "volume_availability_zone"}


def _available_zones(conn, spec: resource_policies.PolicySpec) -> tuple[set[str], list[dict[str, str]]]:
    """Exhaust a native catalog before trusting uniqueness or definitive absence.

    Interactive discovery accepts older responses lacking zone state. Automatic
    selection is deliberately stricter: unknown availability is not authority to
    replace an administrator's default.
    """
    api = conn.compute if spec.resource_kind == "compute_availability_zone" else conn.block_storage
    options: list[dict[str, str]] = []
    names: set[str] = set()
    for zone in api.availability_zones():
        if isinstance(zone, Mapping):
            name = zone.get("name") or zone.get("zoneName")
            state = zone.get("state") or zone.get("zoneState")
        else:
            name = getattr(zone, "name", None) or getattr(zone, "zoneName", None)
            state = getattr(zone, "state", None) or getattr(zone, "zoneState", None)
        if not isinstance(name, str) or not name.strip() or name != name.strip() or name in names:
            raise resource_policies.ResourcePolicyValidationError("native availability-zone catalog is incomplete")
        if name.lower() == "internal":
            continue
        names.add(name)
        if not isinstance(state, Mapping) or type(state.get("available")) is not bool:
            raise resource_policies.ResourcePolicyValidationError("native availability-zone state is incomplete")
        if state["available"]:
            options.append({"id": name, "name": name})
    return names, options


async def reconcile_once(conn) -> int:
    """Refresh eleven local policies; initialize/repair only unambiguous AZ IDs.

    Discovery holds no SQL session or row lock. Each changed observation is then
    fenced against its detached full-row snapshot, including service scope.
    """
    await checkpoint()
    snapshot = await store.reconciliation_snapshot()
    service_project = snapshot["openstack.service_project"]
    service_conn = None
    service_attempted = False
    changes: list[tuple[str, dict[str, str]]] = []
    try:
        for spec in resource_policies.list_specs():
            await checkpoint()
            previous = snapshot[spec.key]
            # A persisted null is an explicit administrator clear, not fresh DB.
            if previous is not None and previous.resource_id is None:
                continue
            if previous is None and spec.resource_kind not in _AZ_KINDS:
                continue
            try:
                execution_conn = conn
                if spec.execution_scope == "service":
                    if not service_attempted:
                        service_attempted = True
                        if service_project is not None and service_project.resource_id:
                            service_conn = await store.get_service_project_connection(service_project.resource_id)
                    if service_conn is None:
                        continue
                    execution_conn = service_conn
                if spec.resource_kind in _AZ_KINDS:
                    names, options = await run_sync(_available_zones, execution_conn, spec)
                    selected = next(
                        (option for option in options if previous is not None and option["id"] == previous.resource_id),
                        None,
                    )
                    if selected is None:
                        # A present but temporarily down zone is still the
                        # administrator's selection, not a deleted default.
                        if previous is not None and previous.resource_id in names:
                            continue
                        if len(options) != 1:
                            continue
                        selected = options[0]
                else:
                    selected = await run_sync(
                        resource_policies._validate_existing_sync, execution_conn, spec, previous.resource_id
                    )
                    if selected["id"] != previous.resource_id:
                        continue
                if previous is None or (previous.resource_id, previous.resource_name) != (
                    selected["id"],
                    selected["name"],
                ):
                    changes.append((spec.key, selected))
            except Exception:
                # Missing, invalid, incomplete, or unavailable native authority
                # never clears a row or replaces non-AZ selections.
                _logger.debug("Resource policy observation unavailable: %s", spec.key, exc_info=True)
    finally:
        if service_conn is not None:
            await close_connection(service_conn)

    changed = 0
    # Refresh the parent display name last so child observations can compare the
    # original scope snapshot. Each transaction locks parent before child.
    for key, selected in sorted(changes, key=lambda change: (change[0] == "openstack.service_project", change[0])):
        changed += await store.apply_reconciled_policy(
            key=key,
            expected=snapshot[key],
            resource_id=selected["id"],
            resource_name=selected["name"],
            service_project=service_project,
        )
    return changed


async def reconciliation_loop() -> None:
    """Run immediately on dispatcher acquisition, then retry every sixty seconds."""
    from app.services.keystone import get_admin_project_connection

    while True:
        try:
            await checkpoint()
            # Avoid creating an SDK connection while SQL authority is unavailable.
            store._require_db()
            conn = await open_connection(get_admin_project_connection)
            try:
                await reconcile_once(conn)
            finally:
                await close_connection(conn)
        except asyncio.CancelledError:
            raise
        except Exception:
            _logger.warning("Resource policy background reconciliation unavailable", exc_info=True)
        await asyncio.sleep(60)
