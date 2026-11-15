"""Opt-in, elected reconciliation of the managed Cinder protection principal.

Reports perform reads only. Request markers are wake-up hints, never authority.
Policies (including paused policies) and active journals alone justify membership.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from collections.abc import Mapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from anyio import CancelScope

from app.config import get_settings
from app.services import work_dispatcher as work
from app.services.backup_quota import derive_backup_gigabytes
from app.services.backup_system_account import AccountUnavailable
from app.services.cache import _get_redis

PREFIX = "afterglow:backup_account"
STATUS_KEY = f"{PREFIX}:status"
MUTATION_LEASE_KEY = f"{PREFIX}:mutation-lease"
MUTATION_LEASE_SECONDS = 90
MUTATION_RENEW_SECONDS = 10
MAX_WRITES = 20
GRACE_SECONDS = 300
POLL_SECONDS = 15
_LANES = ("afterglow:auto_backup", "afterglow:auto_snapshot")
_ID = re.compile(r"[A-Za-z0-9_-]+\Z")
_logger = logging.getLogger(__name__)
_current: ContextVar[object | None] = ContextVar("backup_account_leader", default=None)
_budget: ContextVar[list[int] | None] = ContextVar("backup_account_write_budget", default=None)
_mutation_lease: ContextVar[object | None] = ContextVar("backup_account_mutation_lease", default=None)
_RENEW_MUTATION = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_MUTATION = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class InventoryUnavailable(ValueError):
    """Absence or authority cannot be established; do not mutate."""


class ProjectNeedChanged(InventoryUnavailable):
    """A valid concurrent policy change; retry this project, not the whole census."""


class WriteBudgetExhausted(RuntimeError):
    """Continue from the durable cursor on the next reconciliation cycle."""


def _text(raw) -> str:
    return raw.decode() if isinstance(raw, bytes) else raw or ""


def _field(value, key, default=None):
    return value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)


def _identifier(value) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise InventoryUnavailable("invalid_identifier")
    return value


def _dump(value) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


async def checkpoint_leader() -> None:
    """Fence every write with both elected leadership and current work ownership."""
    dispatcher = _current.get()
    if dispatcher is None or not await dispatcher.is_leader():
        raise work.DispatcherUnavailable("Backup account leadership unavailable")
    await work.checkpoint()
    mutation = _mutation_lease.get()
    if mutation is None:
        raise work.DispatcherUnavailable("Backup account mutation lease unavailable")
    await mutation.check()


class MutationLease:
    """One stable cross-incarnation lock, retained independently through drain."""

    def __init__(self, redis, execution_lease):
        self.redis = redis
        self.execution_lease = execution_lease
        self.owner = secrets.token_hex(24)
        self.deadline = time.monotonic() + MUTATION_LEASE_SECONDS
        self.lost = False

    def revoke(self):
        self.lost = True
        self.execution_lease.revoke()

    async def check(self):
        try:
            if self.lost or time.monotonic() >= self.deadline:
                raise work.DispatcherUnavailable("Backup account mutation lease expired")
            async with asyncio.timeout(max(0, self.deadline - time.monotonic())):
                owner = await self.redis.get(MUTATION_LEASE_KEY)
            if _text(owner) != self.owner or self.lost or time.monotonic() >= self.deadline:
                raise work.DispatcherUnavailable("Backup account mutation lease lost")
        except Exception:
            self.revoke()
            raise work.DispatcherUnavailable("Backup account mutation lease unavailable") from None

    async def renew_once(self):
        started = time.monotonic()
        try:
            if self.lost or started >= self.deadline:
                raise work.DispatcherUnavailable("Backup account mutation lease expired")
            async with asyncio.timeout(min(MUTATION_RENEW_SECONDS, self.deadline - started)):
                retained = await self.redis.eval(
                    _RENEW_MUTATION, 1, MUTATION_LEASE_KEY, self.owner, MUTATION_LEASE_SECONDS
                )
            if not retained or time.monotonic() >= self.deadline:
                raise work.DispatcherUnavailable("Backup account mutation lease lost")
            self.deadline = started + MUTATION_LEASE_SECONDS
        except Exception:
            self.revoke()

    async def renew(self):
        while not self.lost:
            await asyncio.sleep(MUTATION_RENEW_SECONDS)
            await self.renew_once()


@asynccontextmanager
async def mutation_lease(redis, execution_lease):
    """Acquire only under the work lease; release only after its SDK body drains."""
    dispatcher = _current.get()
    if dispatcher is None or not await dispatcher.is_leader():
        raise work.DispatcherUnavailable("Backup account leadership unavailable")
    await work.checkpoint()
    lease = MutationLease(redis, execution_lease)
    if not await redis.set(MUTATION_LEASE_KEY, lease.owner, nx=True, ex=MUTATION_LEASE_SECONDS):
        yield None
        return
    renewal = asyncio.create_task(lease.renew())
    token = _mutation_lease.set(lease)
    try:
        await lease.check()
        yield lease
    finally:
        # The caller closes/drains its connection before leaving this body.
        # Keep renewing even when its membership/work lease has been revoked.
        with CancelScope(shield=True):
            renewal.cancel()
            interrupted = await work.drain_task(renewal)
            release = asyncio.create_task(redis.eval(_RELEASE_MUTATION, 1, MUTATION_LEASE_KEY, lease.owner))
            interrupted = await work.drain_task(release) or interrupted
            _mutation_lease.reset(token)
        if interrupted:
            raise asyncio.CancelledError


async def run_write(fn, *args, **kwargs):
    """Shared account/role/quota native-write budget; never usable from a request."""
    await checkpoint_leader()
    budget = _budget.get()
    if budget is None or budget[0] >= MAX_WRITES:
        raise WriteBudgetExhausted("Backup account mutation budget exhausted")
    budget[0] += 1
    return await work.run_sync(fn, *args, **kwargs)


@dataclass(frozen=True)
class PolicyInventory:
    needed: frozenset[str]


async def policy_inventory(redis) -> PolicyInventory:
    """Read both authoritative registries and their actual, non-normalized bytes.

    Enumerating keys detects orphan journals/configs omitted from a damaged set.
    A changed registry, missing record or malformed bytes makes absence unknown.
    No TTL, normalized values, status or key repairs are persisted here.
    """
    needed = set()
    from app.services.auto_backup import _normalize

    for prefix in _LANES:
        members = {_text(item) for item in await redis.smembers(f"{prefix}:all_configs")}
        keys = set()
        for kind in ("config", "active"):
            async for raw_key in redis.scan_iter(match=f"{prefix}:{kind}:*"):
                keys.add(_text(raw_key))
        expected = set()
        for member in sorted(members):
            project_id, separator, volume_id = member.partition(":")
            if not separator:
                raise InventoryUnavailable("invalid_registry_member")
            _identifier(project_id)
            _identifier(volume_id)
            present = False
            for kind in ("config", "active"):
                key = f"{prefix}:{kind}:{member}"
                raw = _text(await redis.get(key))
                if not raw:
                    continue
                present = True
                expected.add(key)
                try:
                    record = json.loads(raw)
                    if not isinstance(record, dict):
                        raise ValueError
                    if kind == "config":
                        if record.get("project_id") != project_id or record.get("volume_id") != volume_id:
                            raise ValueError
                        if record.get("schema_version") not in (None, 1, 2):
                            raise ValueError
                        if type(record.get("enabled")) is not bool:
                            raise ValueError
                        # Reuse the scheduler's persisted-record validation on
                        # an isolated decoded copy; never store its normalization.
                        _normalize(raw, project_id, volume_id, datetime.now(UTC))
                    elif (
                        record.get("status") not in ("unknown", "creating", "available", "error", "skipped")
                        or not isinstance(record.get("revision"), str)
                        or not record["revision"]
                        or not isinstance(record.get("slot"), str)
                        or not record["slot"].startswith(f"{prefix}:slot:{member}:")
                    ):
                        raise ValueError
                except (ValueError, TypeError, KeyError):
                    raise InventoryUnavailable("malformed_policy_or_journal") from None
                needed.add(project_id)
            if not present:
                raise InventoryUnavailable("missing_policy_and_journal")
        if keys != expected:
            raise InventoryUnavailable("incomplete_policy_registry")
        if members != {_text(item) for item in await redis.smembers(f"{prefix}:all_configs")}:
            raise InventoryUnavailable("changed_policy_registry")
    return PolicyInventory(frozenset(needed))


def _projects(admin) -> list[dict]:
    result = []
    seen = set()
    for project in admin.identity.projects():
        project_id = _identifier(_field(project, "id"))
        if project_id in seen:
            raise InventoryUnavailable("duplicate_native_project")
        seen.add(project_id)
        if _field(project, "is_domain", False):
            continue
        result.append(
            {"id": project_id, "name": _field(project, "name", ""), "domain_id": _field(project, "domain_id")}
        )
    return sorted(result, key=lambda row: row["id"])


def _member_role(admin) -> str:
    roles = [
        role for role in admin.identity.roles() if _field(role, "name") == "member" and not _field(role, "domain_id")
    ]
    if len(roles) != 1:
        raise InventoryUnavailable("canonical_member_role_unavailable")
    return _identifier(_field(roles[0], "id"))


def _direct_roles(admin, user_id: str, project_ids: set[str]) -> dict[str, set[str]]:
    # Even a group with no present grants is foreign authority we must not edit.
    if list(admin.identity.user_groups(user_id)):
        raise InventoryUnavailable("unsupported_group_authority")
    result = {project_id: set() for project_id in project_ids}
    for assignment in admin.identity.role_assignments(user_id=user_id):
        user = _field(assignment, "user", {})
        scope = _field(assignment, "scope", {})
        if (
            not isinstance(user, dict)
            or user.get("id") != user_id
            or _field(assignment, "group")
            or not isinstance(scope, dict)
            or set(scope) != {"project"}
            or not isinstance(scope["project"], dict)
            or scope["project"].get("id") not in project_ids
            or _field(assignment, "inherited_to")
            or _field(assignment, "os_inherit:inherited_to")
            or _field(assignment, "is_inherited", False)
        ):
            raise InventoryUnavailable("unsupported_foreign_authority")
        role_id = _identifier(_field(_field(assignment, "role", {}), "id"))
        result[scope["project"]["id"]].add(role_id)
    return result


def _account_observation(admin, account):
    from app.services import backup_system_account as managed

    domain_id = managed._resolve_domain(admin.identity)
    rows = managed._user_rows(admin, domain_id)
    if not rows:
        return None
    user = rows[0]
    user_id = _identifier(_field(user, "id"))
    if not (account and account["id"] == user_id) and _field(user, "afterglow_system_account") != "auto_backup:v1":
        raise InventoryUnavailable("managed_account_name_conflict")
    return {
        "id": user_id,
        "domain_id": domain_id,
        "enabled": managed._field(user, "enabled", False),
        "options": _field(user, "options", {}) or {},
    }


def _quota(admin, project_id: str) -> dict:
    endpoint = admin.block_storage.get_endpoint()
    if not isinstance(endpoint, str) or not endpoint:
        raise InventoryUnavailable("cinder_endpoint_unavailable")
    response = admin.session.get(f"{endpoint.rstrip('/')}/os-quota-sets/{project_id}")
    response.raise_for_status()
    payload = response.json()
    quota = payload.get("quota_set") if isinstance(payload, dict) else None
    if not isinstance(quota, dict):
        raise InventoryUnavailable("malformed_cinder_quota")
    for key in ("gigabytes", "backup_gigabytes", "backups"):
        if type(quota.get(key)) is not int or quota[key] < -1:
            raise InventoryUnavailable("incomplete_cinder_quota")
    if quota.get("id", project_id) != project_id:
        raise InventoryUnavailable("foreign_cinder_quota")
    return quota


def _put_quota(admin, project_id: str, desired: int):
    work.checkpoint_sync()
    response = admin.session.put(
        f"{admin.block_storage.get_endpoint().rstrip('/')}/os-quota-sets/{project_id}",
        json={"quota_set": {"backup_gigabytes": desired}},
        connect_retries=0,
        status_code_retries=0,
    )
    response.raise_for_status()


async def _snapshot(redis, admin) -> dict:
    from app.services import backup_system_account

    inventory = await policy_inventory(redis)
    projects = await work.run_sync(_projects, admin)
    ids = {row["id"] for row in projects}
    if inventory.needed - ids:
        raise InventoryUnavailable("policy_project_not_in_native_inventory")
    role_id = await work.run_sync(_member_role, admin)
    saved_account = await backup_system_account.load_account(redis)
    account = await work.run_sync(_account_observation, admin, saved_account)
    user_id = _identifier(account["id"]) if account else None
    assignments = await work.run_sync(_direct_roles, admin, user_id, ids) if user_id else {pid: set() for pid in ids}
    rows = []
    for project in projects:
        quota = await work.run_sync(_quota, admin, project["id"])
        desired = derive_backup_gigabytes(quota["gigabytes"])
        rows.append(
            {
                **project,
                "needed": project["id"] in inventory.needed,
                "roles": sorted(assignments[project["id"]]),
                "quota": quota,
                "desired_backup_gigabytes": desired,
            }
        )
    return {"inventory": inventory, "projects": rows, "member_role_id": role_id, "account": account}


async def read_report(redis=None, admin=None) -> dict:
    """Read-only administrator dry run. Never joins dispatcher or writes Redis."""
    from app.services.keystone import get_admin_project_connection

    redis = redis if redis is not None else await _get_redis()
    owned = admin is None
    if owned:
        admin = await work.open_connection(get_admin_project_connection)
    try:
        try:
            snapshot = await _snapshot(redis, admin)
        except Exception as exc:
            return {
                "mode": "report",
                "complete": False,
                "error": type(exc).__name__,
                "reason": str(exc)
                if isinstance(exc, (InventoryUnavailable, AccountUnavailable))
                else "native_inventory_unavailable",
                "intended_writes": [],
                "projects": [],
            }
        from app.services.backup_system_account import ACCOUNT_OPTIONS

        account = snapshot["account"]
        options = {**ACCOUNT_OPTIONS, "multi_factor_auth_rules": []}
        writes = []
        if account is None:
            writes.append({"action": "create_managed_account", "enabled": True, "options": options})
        elif (
            account["enabled"] is not True
            or any(account["options"].get(key) is not value for key, value in ACCOUNT_OPTIONS.items())
            or account["options"].get("multi_factor_auth_rules")
        ):
            writes.append({"action": "repair_managed_account_options", "enabled": True, "options": options})
        rows = []
        for row in snapshot["projects"]:
            project_id = row["id"]
            roles = set(row["roles"])
            member = snapshot["member_role_id"]
            if row["needed"] and member not in roles:
                writes.append({"action": "grant_member", "project_id": project_id})
            for role_id in sorted(roles - {member}):
                writes.append({"action": "remove_direct_role_drift", "project_id": project_id, "role_id": role_id})
            if not row["needed"] and member in roles:
                since = await redis.get(f"{PREFIX}:no_need:{project_id}")
                writes.append(
                    {
                        "action": "revoke_member_after_grace",
                        "project_id": project_id,
                        "no_need_since": _text(since) or None,
                        "grace_seconds": GRACE_SECONDS,
                    }
                )
            if row["quota"]["backup_gigabytes"] != row["desired_backup_gigabytes"]:
                writes.append(
                    {
                        "action": "update_backup_gigabytes",
                        "project_id": project_id,
                        "before": row["quota"]["backup_gigabytes"],
                        "after": row["desired_backup_gigabytes"],
                    }
                )
            rows.append(
                {key: value for key, value in row.items() if key != "quota"}
                | {"gigabytes": row["quota"]["gigabytes"], "backup_gigabytes": row["quota"]["backup_gigabytes"]}
            )
        return {
            "mode": "report",
            "complete": True,
            "enabled": get_settings().backup_system_account_enabled,
            "managed_user_id": account["id"] if account else None,
            "intended_writes": writes,
            "projects": rows,
        }
    finally:
        if owned:
            await work.close_connection(admin)


async def status(redis=None) -> dict:
    """Return only the secret-free active reconciler receipt; no status writes."""
    redis = redis if redis is not None else await _get_redis()
    raw = await redis.get(STATUS_KEY)
    receipt = json.loads(_text(raw)) if raw else {"state": "not_observed"}
    return {**receipt, "enabled": get_settings().backup_system_account_enabled}


async def _persist(redis, key, value, **kwargs):
    await checkpoint_leader()
    return await redis.set(key, value, **kwargs)


async def _delete(redis, key):
    await checkpoint_leader()
    return await redis.delete(key)


async def _fresh_policy(redis, project_id: str, *, needed: bool) -> PolicyInventory:
    current = await policy_inventory(redis)
    if (project_id in current.needed) != needed:
        raise ProjectNeedChanged("project_policy_need_changed")
    return current


async def reconcile(redis, admin) -> dict:
    """Reconcile one bounded cycle under the caller's elected work lease."""
    from app.services import backup_system_account

    await checkpoint_leader()
    snapshot = await _snapshot(redis, admin)  # All reads succeed before any native mutation.
    inventory = snapshot["inventory"]
    # An unreadable cycle cannot prove continuous absence. Restart its grace
    # periods after a complete inventory, rather than reusing stale timestamps.
    if await redis.get(f"{PREFIX}:grace_uncertain"):
        async for key in redis.scan_iter(match=f"{PREFIX}:no_need:*"):
            await _delete(redis, _text(key))
        await _delete(redis, f"{PREFIX}:grace_uncertain")
    # Clear every observed need, including projects beyond this cycle's budget.
    for project_id in sorted(inventory.needed):
        if await redis.get(f"{PREFIX}:no_need:{project_id}") is not None:
            await _delete(redis, f"{PREFIX}:no_need:{project_id}")
    account = await backup_system_account.ensure_account(redis, admin)
    user_id = _identifier(account["id"])
    ids = {row["id"] for row in snapshot["projects"]}
    await work.run_sync(_direct_roles, admin, user_id, ids)  # Detect foreign authority after account creation too.
    cursor = _text(await redis.get(f"{PREFIX}:cursor"))
    rows = snapshot["projects"]
    rows = [row for row in rows if row["id"] > cursor] + [row for row in rows if row["id"] <= cursor]
    seconds, microseconds = await redis.time()
    now = seconds + microseconds / 1_000_000
    processed = 0
    for row in rows:
        if _budget.get()[0] >= MAX_WRITES:
            break
        project_id = row["id"]
        previous_cursor = cursor
        cursor = project_id
        # Set cursor before starting: a failed provider cannot starve later projects.
        await _persist(redis, f"{PREFIX}:cursor", project_id)
        try:
            quota = await work.run_sync(_quota, admin, project_id)
            desired = derive_backup_gigabytes(quota["gigabytes"])
            roles = (await work.run_sync(_direct_roles, admin, user_id, ids))[project_id]
            member = snapshot["member_role_id"]
            needed = project_id in inventory.needed
            if not needed or roles != {member} or quota["backup_gigabytes"] != desired:
                await _delete(redis, f"{PREFIX}:ready:{project_id}")
            if quota["backup_gigabytes"] != desired:
                await run_write(_put_quota, admin, project_id, desired)
                observed = await work.run_sync(_quota, admin, project_id)
                if observed["backup_gigabytes"] != desired or any(
                    observed.get(key) != value for key, value in quota.items() if key != "backup_gigabytes"
                ):
                    raise InventoryUnavailable("quota_readback_mismatch")
            if needed and member not in roles:
                await _fresh_policy(redis, project_id, needed=True)
                await run_write(admin.identity.assign_project_role_to_user, project_id, user_id, member)
                roles = (await work.run_sync(_direct_roles, admin, user_id, ids))[project_id]
                if member not in roles:
                    raise InventoryUnavailable("member_grant_readback_mismatch")
            for role_id in sorted(roles - {member}):
                await _fresh_policy(redis, project_id, needed=needed)
                await run_write(admin.identity.unassign_project_role_from_user, project_id, user_id, role_id)
                roles = (await work.run_sync(_direct_roles, admin, user_id, ids))[project_id]
                if role_id in roles:
                    raise InventoryUnavailable("direct_role_removal_readback_mismatch")
            if not needed and member in roles:
                key = f"{PREFIX}:no_need:{project_id}"
                raw = await redis.get(key)
                if raw is None:
                    await _persist(redis, key, str(now))  # Durable, deliberately no TTL.
                else:
                    try:
                        since = float(_text(raw))
                    except ValueError:
                        raise InventoryUnavailable("invalid_no_need_timestamp") from None
                    if 0 <= since <= now - GRACE_SECONDS:
                        # Re-read Cinder immediately before removing authority.
                        await work.run_sync(_quota, admin, project_id)
                        await _fresh_policy(redis, project_id, needed=False)
                        await run_write(admin.identity.unassign_project_role_from_user, project_id, user_id, member)
                        roles = (await work.run_sync(_direct_roles, admin, user_id, ids))[project_id]
                        if member in roles:
                            raise InventoryUnavailable("member_revoke_readback_mismatch")
            if needed:
                final_quota = await work.run_sync(_quota, admin, project_id)
                final_roles = (await work.run_sync(_direct_roles, admin, user_id, ids))[project_id]
                if final_roles == {member} and final_quota["backup_gigabytes"] == derive_backup_gigabytes(
                    final_quota["gigabytes"]
                ):
                    await _persist(
                        redis,
                        f"{PREFIX}:ready:{project_id}",
                        _dump(
                            {"user_id": user_id, "checked_at": now, "backup_gigabytes": final_quota["backup_gigabytes"]}
                        ),
                        ex=120,
                    )
                    await _delete(redis, f"{PREFIX}:requests:{project_id}")
                else:
                    await _delete(redis, f"{PREFIX}:ready:{project_id}")
            processed += 1
        except WriteBudgetExhausted:
            # Resume an unfinished row first instead of delaying it a full rotation.
            await _persist(redis, f"{PREFIX}:cursor", previous_cursor)
            break
        except ProjectNeedChanged:
            await _delete(redis, f"{PREFIX}:ready:{project_id}")
            await _delete(redis, f"{PREFIX}:no_need:{project_id}")
        except work.DispatcherUnavailable:
            raise
        except Exception:
            await _delete(redis, f"{PREFIX}:ready:{project_id}")
            raise
    return {
        "state": "reconciled",
        "projects": len(rows),
        "processed": processed,
        "writes": _budget.get()[0],
        "managed_user_id": user_id,
        "checked_at": datetime.now(UTC).isoformat(),
    }


async def _warn(redis, reason: str):
    if await _persist(redis, f"{PREFIX}:warning", reason, nx=True, ex=300):
        _logger.warning("Backup account reconciliation unavailable", extra={"reason": reason, "retry_seconds": 300})


async def scheduler_tick(dispatcher) -> None:
    """Only the elected participant advertises and claims its singleton role."""
    from app.services import backup_system_account
    from app.services.keystone import get_admin_project_connection

    await backup_system_account.load_account(dispatcher.redis)
    if not get_settings().backup_system_account_enabled or not await dispatcher.is_leader():
        return
    if not await dispatcher.publish([dispatcher.worker_id], rebalance=True):
        return
    claimed = await dispatcher.claim(90)
    if claimed is None:
        return
    target, owner = claimed
    if target != dispatcher.worker_id:
        raise work.DispatcherUnavailable("Unexpected backup account singleton target")
    async with work.work_lease(dispatcher, target, owner) as execution_lease:
        token = _current.set(dispatcher)
        budget_token = _budget.set([0])
        try:
            async with mutation_lease(dispatcher.redis, execution_lease) as mutation:
                if mutation is None:
                    return
                admin = None
                try:
                    await checkpoint_leader()
                    admin = await work.open_connection(get_admin_project_connection)
                    receipt = await reconcile(dispatcher.redis, admin)
                    await _persist(dispatcher.redis, STATUS_KEY, _dump(receipt))
                except work.DispatcherUnavailable:
                    raise
                except Exception as exc:
                    reason = (
                        str(exc) if isinstance(exc, (InventoryUnavailable, AccountUnavailable)) else type(exc).__name__
                    )
                    await _persist(dispatcher.redis, f"{PREFIX}:grace_uncertain", "1")
                    await _persist(
                        dispatcher.redis,
                        STATUS_KEY,
                        _dump(
                            {
                                "state": "blocked",
                                "reason": reason,
                                "writes": _budget.get()[0],
                                "checked_at": datetime.now(UTC).isoformat(),
                            }
                        ),
                    )
                    await _warn(dispatcher.redis, reason)
                finally:
                    if admin is not None:
                        await work.close_connection(admin)
        finally:
            _budget.reset(budget_token)
            _current.reset(token)


async def scheduler_loop() -> None:
    """Join only when explicitly enabled; retain membership through SDK drain."""
    while True:
        if not get_settings().backup_system_account_enabled:
            await asyncio.sleep(POLL_SECONDS)
            continue
        try:
            redis = await _get_redis()
            worker_id = f"backup-account:{secrets.token_hex(24)}"
            async with work.WorkDispatcher(redis, PREFIX, worker_id=worker_id, roles=(worker_id,)) as dispatcher:
                while not dispatcher.lost and get_settings().backup_system_account_enabled:
                    await scheduler_tick(dispatcher)
                    await asyncio.sleep(POLL_SECONDS)
        except Exception:
            # Redis may be unavailable, so rate-limit this process-local fallback.
            now = time.monotonic()
            previous = getattr(scheduler_loop, "_last_warning", -300.0)
            if now - previous >= 300:
                _logger.warning("Backup account dispatcher unavailable", extra={"retry_seconds": 300})
                scheduler_loop._last_warning = now
        await asyncio.sleep(POLL_SECONDS)
