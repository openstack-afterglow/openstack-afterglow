"""Focused ownership, authoritative inventory, IAM, quota and dry-run contracts."""

from __future__ import annotations

import asyncio
import fnmatch
import json
import threading
from contextlib import asynccontextmanager
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import backup_account_reconciler as service
from app.services import backup_system_account as account


class Redis:
    def __init__(self):
        self.values = {}
        self.sets = {}
        self.writes = []
        self.clock = 1000
        self.ttls = {}
        self.expires = {}
        self.renewed = asyncio.Event()

    async def get(self, key):
        if key in self.expires and self.clock >= self.expires[key]:
            self.values.pop(key, None)
            self.expires.pop(key, None)
        return self.values.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and await self.get(key) is not None:
            return None
        self.writes.append(("set", key))
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex
            self.expires[key] = self.clock + ex
        else:
            self.expires.pop(key, None)
        return True

    async def delete(self, key):
        self.writes.append(("delete", key))
        self.values.pop(key, None)

    async def smembers(self, key):
        return self.sets.get(key, set()).copy()

    async def scan_iter(self, *, match):
        for key in sorted(self.values):
            if fnmatch.fnmatchcase(key, match):
                yield key

    async def time(self):
        return self.clock, 0

    async def eval(self, script, count, key, owner, *args):
        assert count == 1
        assert key == service.MUTATION_LEASE_KEY
        if await self.get(key) != owner:
            return 0
        if script == service._RENEW_MUTATION:
            self.writes.append(("expire", key))
            self.ttls[key] = args[0]
            self.expires[key] = self.clock + args[0]
            self.renewed.set()
            return 1
        assert script == service._RELEASE_MUTATION
        await self.delete(key)
        return 1


def policy(redis, project_id="p1", volume_id="v1", *, enabled=False, lane=0):
    from app.services.auto_backup import build_policy

    prefix = service._LANES[lane]
    member = f"{project_id}:{volume_id}"
    redis.sets.setdefault(f"{prefix}:all_configs", set()).add(member)
    redis.values[f"{prefix}:config:{member}"] = json.dumps(build_policy(project_id, volume_id, enabled=enabled))


def journal(redis, project_id="p1", volume_id="v1", *, lane=0):
    prefix = service._LANES[lane]
    member = f"{project_id}:{volume_id}"
    redis.sets.setdefault(f"{prefix}:all_configs", set()).add(member)
    redis.values[f"{prefix}:active:{member}"] = json.dumps(
        {
            "slot": f"{prefix}:slot:{member}:2026-11-15T03:00:00+00:00",
            "revision": "revision1",
            "status": "creating",
            "submitted_at": "2026-11-15T03:00:01+00:00",
        }
    )


class Native:
    def __init__(self, projects=("p1",)):
        self.projects = list(projects)
        self.grants = {pid: set() for pid in projects}
        self.foreign = []
        self.groups = []
        self.mutations = []
        self.quotas = {
            pid: {
                "id": pid,
                "gigabytes": 10868,
                "backup_gigabytes": 32604,
                "backups": 10,
                "gigabytes_fast": 500,
                "backups_fast": 7,
            }
            for pid in projects
        }
        self.user = {
            "id": "machine1",
            "name": account.ACCOUNT_NAME,
            "domain_id": "domain1",
            "enabled": True,
            "options": {**account.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []},
            "afterglow_system_account": "auto_backup:v1",
        }
        self.identity = SimpleNamespace(
            projects=lambda: [
                {"id": pid, "name": "DMSLAB" if pid == "p1" else pid, "domain_id": "domain1"} for pid in self.projects
            ],
            roles=lambda: [{"id": "member1", "name": "member", "domain_id": None}],
            domains=lambda **kwargs: [{"id": "domain1", "name": "Default"}],
            users=lambda **kwargs: [self.user] if self.user else [],
            get=self.identity_get,
            role_assignments=self.assignments,
            assign_project_role_to_user=self.grant,
            unassign_project_role_from_user=self.revoke,
        )
        self.block_storage = SimpleNamespace(get_endpoint=lambda: "http://cinder/v3/admin")
        self.session = SimpleNamespace(get=self.get, put=self.put)
        self.close = MagicMock()

    def identity_get(self, url):
        assert url == "/users/machine1/groups"
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"groups": list(self.groups), "links": {}})

    def assignments(self, *, user_id):
        return [
            {"user": {"id": user_id}, "role": {"id": rid}, "scope": {"project": {"id": pid}}}
            for pid, roles in self.grants.items()
            for rid in sorted(roles)
        ] + self.foreign

    def grant(self, project_id, user_id, role_id):
        assert user_id == "machine1"
        assert role_id == "member1"
        self.mutations.append(("grant", project_id, role_id))
        self.grants[project_id].add(role_id)

    def revoke(self, project_id, user_id, role_id):
        assert user_id == "machine1"
        self.mutations.append(("revoke", project_id, role_id))
        self.grants[project_id].discard(role_id)

    def get(self, url):
        quota = deepcopy(self.quotas[url.rsplit("/", 1)[1]])
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"quota_set": quota})

    def put(self, url, *, json, connect_retries, status_code_retries):
        assert connect_retries == status_code_retries == 0
        assert set(json["quota_set"]) == {"backup_gigabytes"}
        project_id = url.rsplit("/", 1)[1]
        self.mutations.append(("quota", project_id, deepcopy(json)))
        self.quotas[project_id].update(json["quota_set"])
        return SimpleNamespace(raise_for_status=lambda: None)


@pytest.fixture
def setup(monkeypatch):
    redis = Redis()
    native = Native()
    saved = {"id": "machine1", "domain_id": "domain1", "name": account.ACCOUNT_NAME}
    monkeypatch.setattr(account, "load_account", AsyncMock(return_value=saved))
    monkeypatch.setattr(account, "ensure_account", AsyncMock(return_value=saved))
    monkeypatch.setattr(account, "_cached_domain", None)
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=True))
    dispatcher = SimpleNamespace(is_leader=AsyncMock(return_value=True))
    token = service._current.set(dispatcher)
    budget = service._budget.set([0])
    stable = service._mutation_lease.set(SimpleNamespace(check=AsyncMock()))
    try:
        yield redis, native, dispatcher
    finally:
        service._budget.reset(budget)
        service._mutation_lease.reset(stable)
        service._current.reset(token)


@pytest.mark.asyncio
async def test_nonleader_never_provisions_or_claims(setup):
    redis, native, dispatcher = setup
    dispatcher.redis = redis
    dispatcher.is_leader.return_value = False
    dispatcher.publish = AsyncMock()
    dispatcher.claim = AsyncMock()
    await service.scheduler_tick(dispatcher)
    account.load_account.assert_awaited_once_with(redis)
    account.ensure_account.assert_not_awaited()
    dispatcher.publish.assert_not_awaited()
    dispatcher.claim.assert_not_awaited()
    assert not native.mutations and not redis.writes


@pytest.mark.asyncio
async def test_leader_publishes_own_role_and_holds_lease(setup, monkeypatch):
    redis, native, dispatcher = setup
    dispatcher.redis = redis
    dispatcher.worker_id = "worker1"
    dispatcher.publish = AsyncMock(return_value=True)
    dispatcher.claim = AsyncMock(return_value=("worker1", "owner1"))
    held = []

    @asynccontextmanager
    async def lease(*args):
        held.append(True)
        try:
            yield SimpleNamespace(revoke=MagicMock())
        finally:
            held.pop()

    async def reconcile(*args):
        assert held
        return {"state": "reconciled", "writes": 0}

    monkeypatch.setattr(service.work, "work_lease", lease)
    monkeypatch.setattr(service.work, "open_connection", AsyncMock(return_value=native))
    monkeypatch.setattr(service, "reconcile", reconcile)
    await service.scheduler_tick(dispatcher)
    dispatcher.publish.assert_awaited_once_with(["worker1"], rebalance=True)
    native.close.assert_called_once()
    assert json.loads(redis.values[service.STATUS_KEY])["state"] == "reconciled"


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["paused", "backup_journal", "snapshot", "snapshot_journal"])
async def test_paused_policies_and_active_journals_keep_member(setup, source):
    redis, native, _ = setup
    if source == "paused":
        policy(redis)
    elif source == "snapshot":
        policy(redis, lane=1)
    else:
        journal(redis, lane=int(source == "snapshot_journal"))
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    ready = json.loads(redis.values[f"{service.PREFIX}:ready:p1"])
    assert ready["user_id"] == "machine1"
    assert ready["backup_gigabytes"] == 32604
    assert redis.ttls[f"{service.PREFIX}:ready:p1"] == 120


@pytest.mark.asyncio
async def test_request_hint_never_justifies_grant(setup):
    redis, native, _ = setup
    redis.values[f"{service.PREFIX}:requests:p1"] = "requested"
    await service.reconcile(redis, native)
    assert not native.grants["p1"]
    assert f"{service.PREFIX}:ready:p1" not in redis.values


@pytest.mark.asyncio
async def test_extra_exact_direct_role_removed_after_member_grant(setup):
    redis, native, _ = setup
    policy(redis)
    native.grants["p1"] = {"admin1", "reader1"}
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    assert native.mutations[0] == ("grant", "p1", "member1")
    assert ("revoke", "p1", "admin1") in native.mutations


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope",
    [
        {"domain": {"id": "domain1"}},
        {"system": {"all": True}},
        {"project": {"id": "p1"}, "OS-INHERIT:inherited_to": "projects"},
    ],
)
async def test_foreign_authority_blocks_without_broad_deletion(setup, scope):
    redis, native, _ = setup
    native.foreign = [{"user": {"id": "machine1"}, "role": {"id": "admin1"}, "scope": scope}]
    with pytest.raises(service.InventoryUnavailable, match="unsupported_foreign_authority"):
        await service.reconcile(redis, native)
    account.ensure_account.assert_not_awaited()
    assert not native.mutations


@pytest.mark.asyncio
async def test_group_authority_fails_closed(setup):
    redis, native, _ = setup
    native.groups = [{"id": "group1"}]
    with pytest.raises(service.InventoryUnavailable, match="unsupported_group_authority"):
        await service.reconcile(redis, native)
    assert not native.mutations


@pytest.mark.asyncio
async def test_revoke_requires_durable_grace_and_fresh_inventory(setup):
    redis, native, _ = setup
    native.grants["p1"] = {"member1"}
    await service.reconcile(redis, native)
    key = f"{service.PREFIX}:no_need:p1"
    assert redis.values[key] == "1000.0"
    assert key not in redis.ttls
    assert native.grants["p1"] == {"member1"}
    redis.clock = 1299
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    redis.clock = 1300
    await service.reconcile(redis, native)
    assert native.grants["p1"] == set()


@pytest.mark.asyncio
async def test_reappearing_paused_policy_clears_grace(setup):
    redis, native, _ = setup
    native.grants["p1"] = {"member1"}
    redis.values[f"{service.PREFIX}:no_need:p1"] = "100"
    policy(redis, enabled=False)
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    assert f"{service.PREFIX}:no_need:p1" not in redis.values


@pytest.mark.asyncio
@pytest.mark.parametrize("damage", ["missing_record", "orphan_config", "orphan_journal", "malformed", "wrong_project"])
async def test_incomplete_inventory_never_revokes(setup, damage):
    redis, native, _ = setup
    native.grants["p1"] = {"member1"}
    redis.values[f"{service.PREFIX}:no_need:p1"] = "100"
    policy(redis)
    key = f"{service._LANES[0]}:config:p1:v1"
    if damage == "missing_record":
        del redis.values[key]
    elif damage == "orphan_config":
        redis.sets.clear()
    elif damage == "orphan_journal":
        journal(redis, volume_id="v2")
        redis.sets[f"{service._LANES[0]}:all_configs"].remove("p1:v2")
    elif damage == "malformed":
        redis.values[key] = "{broken"
    else:
        redis.values[key] = json.dumps({"project_id": "foreign", "volume_id": "v1", "enabled": False})
    with pytest.raises(service.InventoryUnavailable):
        await service.reconcile(redis, native)
    assert not native.mutations
    assert native.grants["p1"] == {"member1"}


@pytest.mark.asyncio
async def test_cinder_failure_prevents_any_role_removal(setup, monkeypatch):
    redis, native, _ = setup
    native.grants["p1"] = {"member1", "admin1"}
    redis.values[f"{service.PREFIX}:no_need:p1"] = "100"
    monkeypatch.setattr(native.session, "get", MagicMock(side_effect=RuntimeError("unavailable")))
    with pytest.raises(RuntimeError):
        await service.reconcile(redis, native)
    assert not native.mutations


@pytest.mark.asyncio
@pytest.mark.parametrize("disk,backup,desired", [(10868, 1000, 32604), (-1, 1000, -1), (0, -1, 0)])
async def test_global_capacity_rule_keeps_counts_and_typed_limits(setup, disk, backup, desired):
    redis, native, _ = setup
    native.quotas["p1"].update(gigabytes=disk, backup_gigabytes=backup)
    before = deepcopy(native.quotas["p1"])
    await service.reconcile(redis, native)
    assert native.quotas["p1"] == {**before, "backup_gigabytes": desired}
    assert native.mutations == [("quota", "p1", {"quota_set": {"backup_gigabytes": desired}})]


@pytest.mark.asyncio
async def test_rotating_cursor_bounds_native_writes_and_avoids_starvation(setup):
    redis, _, _ = setup
    native = Native(tuple(f"p{index:02d}" for index in range(30)))
    for quota in native.quotas.values():
        quota["backup_gigabytes"] = 1000
    receipt = await service.reconcile(redis, native)
    assert receipt["writes"] == service.MAX_WRITES
    assert len(native.mutations) == service.MAX_WRITES
    first = {row[1] for row in native.mutations}
    service._budget.get()[0] = 0
    await service.reconcile(redis, native)
    assert all(quota["backup_gigabytes"] == 32604 for quota in native.quotas.values())
    assert len(native.mutations) == 30
    assert {row[1] for row in native.mutations[20:]} - first


@pytest.mark.asyncio
async def test_leader_loss_fences_native_writes(setup):
    redis, native, dispatcher = setup
    policy(redis)
    dispatcher.is_leader.return_value = False
    with pytest.raises(service.work.DispatcherUnavailable):
        await service.reconcile(redis, native)
    assert not native.mutations and not redis.writes
    account.ensure_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_dry_run_reports_dmslab_32604_and_performs_zero_writes(setup):
    redis, native, _ = setup
    policy(redis)
    native.quotas["p1"]["backup_gigabytes"] = 1000
    before = deepcopy(redis.values)
    report = await service.read_report(redis=redis, admin=native)
    assert report["complete"] is True
    assert report["mode"] == "report"
    assert report["projects"][0]["name"] == "DMSLAB"
    assert report["projects"][0]["desired_backup_gigabytes"] == 32604
    assert {"action": "update_backup_gigabytes", "project_id": "p1", "before": 1000, "after": 32604} in report[
        "intended_writes"
    ]
    assert {"action": "grant_member", "project_id": "p1"} in report["intended_writes"]
    assert not native.mutations and not redis.writes
    assert redis.values == before
    account.ensure_account.assert_not_awaited()
    assert "password" not in json.dumps(report)


@pytest.mark.asyncio
async def test_dry_run_lists_account_creation_options_without_creating(setup):
    redis, native, _ = setup
    native.user = None
    account.load_account.return_value = None
    report = await service.read_report(redis=redis, admin=native)
    action = report["intended_writes"][0]
    assert action["action"] == "create_managed_account"
    assert action["options"] == {**account.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []}
    assert not native.mutations and not redis.writes
    account.ensure_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_name_collision_report_is_read_only_and_fail_closed(setup):
    redis, native, _ = setup
    account.load_account.return_value = None
    native.user.pop("afterglow_system_account")
    report = await service.read_report(redis=redis, admin=native)
    assert report["complete"] is False
    assert report["reason"] == "managed_account_name_conflict"
    assert not report["intended_writes"]
    assert not native.mutations and not redis.writes


@pytest.mark.asyncio
async def test_status_reads_receipt_and_current_enabled_flag_without_writes(setup):
    redis, _, _ = setup
    redis.values[service.STATUS_KEY] = json.dumps({"state": "reconciled", "writes": 2})
    assert await service.status(redis) == {"state": "reconciled", "writes": 2, "enabled": True}
    assert not redis.writes


@pytest.mark.asyncio
async def test_blocked_cycle_restarts_uncertain_absence_grace(setup):
    redis, native, _ = setup
    native.grants["p1"] = {"member1"}
    redis.values[f"{service.PREFIX}:no_need:p1"] = "100"
    redis.values[f"{service.PREFIX}:grace_uncertain"] = "1"
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    assert redis.values[f"{service.PREFIX}:no_need:p1"] == "1000.0"
    assert f"{service.PREFIX}:grace_uncertain" not in redis.values


@pytest.mark.asyncio
async def test_policy_change_before_revoke_fails_closed(setup, monkeypatch):
    redis, native, _ = setup
    native.grants["p1"] = {"member1"}
    redis.values[f"{service.PREFIX}:no_need:p1"] = "100"
    original = service._fresh_policy
    reads = 0

    async def changed(redis, project_id, *, needed):
        nonlocal reads
        reads += 1
        if reads == 1:
            policy(redis, enabled=False)
        return await original(redis, project_id, needed=needed)

    monkeypatch.setattr(service, "_fresh_policy", changed)
    await service.reconcile(redis, native)
    assert not native.mutations
    assert native.grants["p1"] == {"member1"}


@pytest.mark.asyncio
async def test_missing_member_readback_never_publishes_ready(setup, monkeypatch):
    redis, native, _ = setup
    policy(redis)
    monkeypatch.setattr(native.identity, "assign_project_role_to_user", MagicMock())
    with pytest.raises(service.InventoryUnavailable, match="member_grant_readback_mismatch"):
        await service.reconcile(redis, native)
    assert f"{service.PREFIX}:ready:p1" not in redis.values


@pytest.mark.asyncio
async def test_dry_run_reports_repairs_without_changing_user(setup):
    redis, native, _ = setup
    native.user["enabled"] = False
    native.user["options"] = {"multi_factor_auth_rules": [["password", "totp"]]}
    before = deepcopy(native.user)
    report = await service.read_report(redis=redis, admin=native)
    repair = report["intended_writes"][0]
    assert repair["action"] == "repair_managed_account_options"
    assert repair["enabled"] is True
    assert repair["options"]["multi_factor_auth_rules"] == []
    assert native.user == before
    assert not native.mutations and not redis.writes


@pytest.mark.asyncio
async def test_disabled_setting_never_joins_mutation_path(setup, monkeypatch):
    redis, _, dispatcher = setup
    dispatcher.redis = redis
    dispatcher.publish = AsyncMock()
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(backup_system_account_enabled=False))
    await service.scheduler_tick(dispatcher)
    dispatcher.publish.assert_not_awaited()
    account.ensure_account.assert_not_awaited()
    assert not redis.writes


def test_settings_flag_is_false_by_default_and_toml_opt_in(monkeypatch):
    from app import config

    assert config.Settings.model_fields["backup_system_account_enabled"].default is False
    monkeypatch.setattr(config, "load_raw_toml", lambda: {"backup_system_account": {"enabled": True}})
    assert config._load_toml()["backup_system_account_enabled"] is True


def test_installed_managed_user_resource_keeps_options_and_provenance():
    user = account._ManagedUser(
        id="machine1",
        name=account.ACCOUNT_NAME,
        domain_id="domain1",
        enabled=True,
        options={**account.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []},
        afterglow_system_account="auto_backup:v1",
    )
    assert account._field(user, "enabled") is True
    assert user.options == {**account.ACCOUNT_OPTIONS, "multi_factor_auth_rules": []}
    assert user.afterglow_system_account == "auto_backup:v1"
    body = user.to_dict(original_names=True)
    assert body["enabled"] is True
    assert body["options"]["ignore_password_expiry"] is True
    assert body["afterglow_system_account"] == "auto_backup:v1"


@pytest.mark.asyncio
async def test_unrelated_policy_progress_keeps_readiness_and_absence_grace(setup, monkeypatch):
    redis, _, _ = setup
    native = Native(("p1", "p2", "p3"))
    policy(redis, "p1")
    policy(redis, "p2")
    native.grants = {pid: {"member1"} for pid in native.projects}
    ready_key = f"{service.PREFIX}:ready:p1"
    redis.values[ready_key] = json.dumps({"user_id": "machine1", "checked_at": 990})
    grace_key = f"{service.PREFIX}:no_need:p3"
    redis.values[grace_key] = "900"
    original = native.session.get
    reads = 0

    def progressing(url):
        nonlocal reads
        reads += 1
        assert ready_key in redis.values
        if reads > len(native.projects):
            key = f"{service._LANES[0]}:config:p2:v1"
            config = json.loads(redis.values[key])
            config["last_run_at"] = f"progress-{reads}"
            redis.values[key] = json.dumps(config)
        return original(url)

    monkeypatch.setattr(native.session, "get", progressing)
    receipt = await service.reconcile(redis, native)
    assert receipt["state"] == "reconciled"
    assert receipt["processed"] == 3
    assert ("delete", ready_key) not in redis.writes
    assert ready_key in redis.values
    assert redis.values[grace_key] == "900"
    assert not native.mutations


@pytest.mark.asyncio
async def test_budget_exhausted_mid_row_resumes_unfinished_project_first(setup, monkeypatch):
    redis, native, _ = setup
    policy(redis)
    native.quotas["p1"]["backup_gigabytes"] = 1000
    monkeypatch.setattr(service, "MAX_WRITES", 1)
    await service.reconcile(redis, native)
    assert native.quotas["p1"]["backup_gigabytes"] == 32604
    assert not native.grants["p1"]
    assert redis.values[f"{service.PREFIX}:cursor"] == ""
    service._budget.get()[0] = 0
    await service.reconcile(redis, native)
    assert native.grants["p1"] == {"member1"}
    assert f"{service.PREFIX}:ready:p1" in redis.values


@pytest.mark.asyncio
@pytest.mark.parametrize("handoff", ["release", "expiry"])
async def test_stable_old_incarnation_lease_blocks_new_native_writes(setup, monkeypatch, handoff):
    redis, native, dispatcher = setup
    policy(redis)
    dispatcher.redis = redis
    dispatcher.worker_id = "new-incarnation"
    dispatcher.publish = AsyncMock(return_value=True)
    dispatcher.claim = AsyncMock(return_value=("new-incarnation", "new-work-owner"))

    @asynccontextmanager
    async def execution(*args):
        yield SimpleNamespace(revoke=MagicMock())

    monkeypatch.setattr(service.work, "work_lease", execution)
    factory = AsyncMock(return_value=native)
    monkeypatch.setattr(service.work, "open_connection", factory)
    await redis.set(service.MUTATION_LEASE_KEY, "old-incarnation-owner", ex=90)
    await service.scheduler_tick(dispatcher)
    factory.assert_not_awaited()
    account.ensure_account.assert_not_awaited()
    assert not native.mutations
    assert await redis.get(service.MUTATION_LEASE_KEY) == "old-incarnation-owner"
    if handoff == "release":
        await redis.delete(service.MUTATION_LEASE_KEY)
    else:
        redis.clock += 91
    await service.scheduler_tick(dispatcher)
    assert native.grants["p1"] == {"member1"}
    assert await redis.get(service.MUTATION_LEASE_KEY) is None


@pytest.mark.asyncio
async def test_mutation_token_loss_revokes_thread_send_fence(setup):
    redis, _, dispatcher = setup
    dispatcher.lost = False
    dispatcher._active = True
    dispatcher._member_deadline = float("inf")
    execution = SimpleNamespace(
        dispatcher=dispatcher,
        _revoked=False,
        revoked=asyncio.Event(),
        _deadline=float("inf"),
    )

    def revoke():
        execution._revoked = True
        execution.revoked.set()

    execution.revoke = revoke
    async with service.mutation_lease(redis, execution) as lease:
        redis.values[service.MUTATION_LEASE_KEY] = "replacement-owner"
        await lease.renew_once()
        assert execution.revoked.is_set()
        token = service.work._current_lease.set(execution)
        try:
            with pytest.raises(service.work.DispatcherUnavailable):
                service.work.checkpoint_sync()
        finally:
            service.work._current_lease.reset(token)
    # Compare-token release cannot remove another incarnation's lease.
    assert await redis.get(service.MUTATION_LEASE_KEY) == "replacement-owner"


@pytest.mark.asyncio
async def test_cancelled_sdk_and_connection_drain_retain_stable_renewal(setup, monkeypatch):
    redis, native, dispatcher = setup
    dispatcher.redis = redis
    dispatcher.worker_id = "old-incarnation"
    dispatcher.publish = AsyncMock(return_value=True)
    dispatcher.claim = AsyncMock(return_value=("old-incarnation", "old-work-owner"))
    dispatcher._members_key = "members"
    dispatcher._incarnations_key = "incarnations"
    dispatcher._assignments_key = "assignments"
    dispatcher._eval = AsyncMock(return_value=True)
    dispatcher._member_deadline = float("inf")
    dispatcher.lost = False
    dispatcher._active = True
    dispatcher.prefix = service.PREFIX
    send_started = threading.Event()
    release_send = threading.Event()
    close_started = threading.Event()
    release_close = threading.Event()

    @asynccontextmanager
    async def execution(participant, target, owner):
        lease = service.work.WorkLease(participant, target, owner, 90)
        token = service.work._current_lease.set(lease)
        try:
            yield lease
        finally:
            service.work._current_lease.reset(token)

    def blocking_send():
        send_started.set()
        if not release_send.wait(5):
            raise RuntimeError("test send drain was not released")

    def blocking_close():
        close_started.set()
        if not release_close.wait(5):
            raise RuntimeError("test close drain was not released")

    async def reconcile(*args):
        await service.run_write(blocking_send)
        return {"state": "reconciled", "writes": 1}

    monkeypatch.setattr(service, "MUTATION_RENEW_SECONDS", 0.01)
    monkeypatch.setattr(service.work, "work_lease", execution)
    monkeypatch.setattr(service.work, "open_connection", AsyncMock(return_value=native))
    monkeypatch.setattr(service, "reconcile", reconcile)
    native.close = blocking_close
    task = asyncio.create_task(service.scheduler_tick(dispatcher))
    try:
        assert await asyncio.to_thread(send_started.wait, 5)
        task.cancel()
        await asyncio.wait_for(redis.renewed.wait(), 2)
        owner = await redis.get(service.MUTATION_LEASE_KEY)
        assert owner
        assert not task.done()
        assert not close_started.is_set()
        # Losing leadership does not stop retention while an old send drains.
        dispatcher.is_leader.return_value = False
        redis.renewed.clear()
        await asyncio.wait_for(redis.renewed.wait(), 2)
        assert await redis.get(service.MUTATION_LEASE_KEY) == owner
        release_send.set()
        assert await asyncio.to_thread(close_started.wait, 5)
        redis.renewed.clear()
        await asyncio.wait_for(redis.renewed.wait(), 2)
        assert not task.done()
        assert await redis.get(service.MUTATION_LEASE_KEY) == owner
    finally:
        release_send.set()
        release_close.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert await redis.get(service.MUTATION_LEASE_KEY) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["revision", "next_run_at", "next_tier"])
async def test_malformed_persisted_policy_prevents_other_project_revoke(setup, missing):
    redis, _, _ = setup
    native = Native(("p1", "p2"))
    policy(redis, "p1", enabled=True)
    key = f"{service._LANES[0]}:config:p1:v1"
    config = json.loads(redis.values[key])
    config.pop(missing)
    redis.values[key] = json.dumps(config)
    native.grants["p2"] = {"member1"}
    redis.values[f"{service.PREFIX}:no_need:p2"] = "100"
    with pytest.raises(service.InventoryUnavailable, match="malformed_policy_or_journal"):
        await service.reconcile(redis, native)
    assert native.grants["p2"] == {"member1"}
    assert not native.mutations
    account.ensure_account.assert_not_awaited()


def test_fake_identity_surface_exists_on_the_real_sdk_proxy():
    # The fake once offered `user_groups`, which the real SDK proxy lacks; every fake-backed test passed
    # while the production inventory raised AttributeError. A fake method must exist on the real proxy.
    from openstack.identity.v3._proxy import Proxy

    for name in vars(Native().identity):
        assert hasattr(Proxy, name), name
