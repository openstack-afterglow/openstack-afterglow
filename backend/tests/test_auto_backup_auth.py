"""Target-token ownership and shared failure windows, without cloud credentials."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from keystoneauth1.exceptions.http import Forbidden, Unauthorized

from app.services import auto_backup as ab
from app.services import auto_snapshot, backup_system_account
from tests.test_auto_backup import PROJECT, START, VOLUME, BackupCloud, due, save
from tests.test_auto_backup import policy_redis as policy_redis


@pytest.fixture(autouse=True)
def prepared_system_account(monkeypatch):
    from unittest.mock import AsyncMock

    monkeypatch.setattr(backup_system_account, "ensure_project", AsyncMock())


class TokenOwnedCloud(BackupCloud):
    """Cinder assigns new recovery points to the authenticated token's project."""

    def __init__(self, token_project):
        super().__init__()
        self.token_project = token_project
        access = SimpleNamespace(project_id=token_project, project_scoped=True, system_scoped=False)
        self.session = SimpleNamespace(auth=SimpleNamespace(get_access=lambda _: access))

    def create_backup(self, **kwargs):
        record = super().create_backup(**kwargs)
        record.project_id = self.token_project
        return record

    def create_snapshot(self, **kwargs):
        self.submissions.append(kwargs)
        return self.add(
            "new-snapshot",
            kwargs["name"],
            status="creating",
            project_id=self.token_project,
            metadata=kwargs["metadata"],
        )

    def get_snapshot(self, point_id):
        return self.records[point_id]

    def snapshots(self, **kwargs):
        return list(self.records.values())


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["backup", "snapshot"])
async def test_default_factory_keeps_token_in_target_and_reconciles(policy_redis, monkeypatch, kind):
    cloud = TokenOwnedCloud(PROJECT)
    calls = []

    def connect(project_id):
        calls.append(project_id)
        return cloud

    monkeypatch.setattr(backup_system_account, "get_connection_for_project", connect)
    if kind == "snapshot":
        monkeypatch.setattr(auto_snapshot, "_PREFIX", ab._PREFIX + ":snapshot")
        monkeypatch.setattr(auto_snapshot, "_ALL_KEY", auto_snapshot._PREFIX + ":all_configs")
    service = ab if kind == "backup" else auto_snapshot
    enable = ab.enable_auto_backup if kind == "backup" else auto_snapshot.enable_auto_snapshot
    get_config = ab.get_auto_backup_config if kind == "backup" else auto_snapshot.get_auto_snapshot_config
    config = await enable(PROJECT, VOLUME, now=START)
    await service.scheduler_tick(now=due(config))
    point = next(iter(cloud.records.values()))
    assert point.project_id == PROJECT
    point.status = "available"
    await service.scheduler_tick(now=due(config))
    result = await get_config(PROJECT, VOLUME)
    assert result["last_status"] == "available"
    assert len(cloud.submissions) == 1
    assert calls == [PROJECT, PROJECT]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["backup", "snapshot"])
async def test_admin_token_would_create_foreign_point_and_cannot_reconcile(policy_redis, monkeypatch, kind):
    cloud = TokenOwnedCloud("admin-project")
    if kind == "snapshot":
        monkeypatch.setattr(auto_snapshot, "_PREFIX", ab._PREFIX + ":snapshot")
        monkeypatch.setattr(auto_snapshot, "_ALL_KEY", auto_snapshot._PREFIX + ":all_configs")
        service = auto_snapshot
        config = await service.enable_auto_snapshot(PROJECT, VOLUME, now=START)
    else:
        service = ab
        config = await save()
    if kind == "backup":
        await service.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    else:
        await service.run_snapshot_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert next(iter(cloud.records.values())).project_id == "admin-project"
    await service.scheduler_tick(now=due(config), connection_factory=lambda _: cloud)
    get_config = ab.get_auto_backup_config if kind == "backup" else auto_snapshot.get_auto_snapshot_config
    result = await get_config(PROJECT, VOLUME)
    assert result["last_status"] == "unknown"
    assert cloud.deleted == []
    assert len(cloud.submissions) == 1


@pytest.mark.parametrize("binding", [False, True])
def test_default_factory_rejects_admin_or_bound_operator_token(monkeypatch, binding):
    cloud = TokenOwnedCloud("admin-project")
    if binding:
        cloud._afterglow_usage_operator_scope = object()
    monkeypatch.setattr(backup_system_account, "get_connection_for_project", lambda _: cloud)
    with pytest.raises(RuntimeError):
        ab._make_proxy(PROJECT)
    assert cloud.closed == 1


@pytest.mark.asyncio
async def test_foreign_source_rejected_before_submission(policy_redis):
    cloud = TokenOwnedCloud(PROJECT)
    cloud.volume.project_id = "foreign-project"
    config = await save()
    await ab.scheduler_tick(now=due(config), connection_factory=lambda _: cloud)
    assert cloud.submissions == []
    assert (await ab.get_auto_backup_config(PROJECT, VOLUME))["last_status"] == "skipped"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [Unauthorized, Forbidden])
async def test_unauthorized_window_survives_worker_change_and_keeps_sibling_running(policy_redis, caplog, failure):
    config = await save()
    healthy = TokenOwnedCloud(PROJECT)
    await ab.enable_auto_backup("unreachable-project", "unreachable-volume", now=START)
    calls = []

    def factory(project_id):
        calls.append(project_id)
        if project_id == "unreachable-project":
            raise failure("private upstream credential must never be logged")
        return healthy

    clock = due(config)
    await ab.scheduler_tick(now=clock, connection_factory=factory)
    config_key = ab._key("config", "unreachable-project", "unreachable-volume")
    failed_raw = await policy_redis.get(config_key)
    failed = await ab.get_auto_backup_config("unreachable-project", "unreachable-volume")
    assert failed["last_status"] == "error"
    assert failed["last_error"] == ab._AUTH_ERROR
    assert failed["last_run_at"] is None
    for offset in (15, 30, 299):
        # Each standalone tick has a fresh dispatcher incarnation.
        await ab.scheduler_tick(now=clock + timedelta(seconds=offset), connection_factory=factory)
    assert calls.count("unreachable-project") == 1
    assert len(healthy.submissions) == 1
    assert healthy.closed >= 1
    assert len([r for r in caplog.records if "retry deferred" in r.message]) == 1
    warning = next(r for r in caplog.records if "retry deferred" in r.message)
    assert warning.project_id == "unreachable-project"
    assert warning.retry_after_seconds == 300
    assert "check whether service account has no role in project" in warning.message
    assert "private upstream" not in caplog.text
    retry_key = ab._key("retry", "unreachable-project", "unreachable-volume")
    assert 0 < await policy_redis.ttl(retry_key) <= 300
    assert await policy_redis.get(config_key) == failed_raw
    await ab.scheduler_tick(now=clock + timedelta(seconds=300), connection_factory=factory)
    assert calls.count("unreachable-project") == 2
    assert len([r for r in caplog.records if "retry deferred" in r.message]) == 2
    assert (await ab.get_auto_backup_config("unreachable-project", "unreachable-volume"))["next_run_at"] == config[
        "next_run_at"
    ]


@pytest.mark.asyncio
async def test_reconcile_native_error_preserves_fence_without_auth_backoff(policy_redis, caplog):
    cloud = TokenOwnedCloud(PROJECT)
    config = await save()
    await ab.scheduler_tick(now=due(config), connection_factory=lambda _: cloud)
    cloud.read_error = Unauthorized("private provider")
    for offset in (15, 30, 299):
        await ab.scheduler_tick(now=due(config) + timedelta(seconds=offset), connection_factory=lambda _: cloud)
    assert cloud.closed == 4
    assert len(cloud.submissions) == 1
    assert (await ab.get_auto_backup_config(PROJECT, VOLUME))["last_status"] == "unknown"
    assert await policy_redis.exists(ab._key("active", PROJECT, VOLUME))
    assert not await policy_redis.exists(ab._key("retry", PROJECT, VOLUME))
    assert not [r for r in caplog.records if "retry deferred" in r.message]
    cloud.read_error = None
    cloud.records["new-backup"].status = "available"
    await ab.scheduler_tick(now=due(config) + timedelta(seconds=300), connection_factory=lambda _: cloud)
    assert (await ab.get_auto_backup_config(PROJECT, VOLUME))["last_status"] == "available"


@pytest.mark.asyncio
async def test_auth_error_clears_after_success_without_changing_due_or_history(policy_redis):
    config = await save()

    def denied(_):
        raise Unauthorized("private identity")

    await ab.scheduler_tick(now=due(config), connection_factory=denied)
    failed = await ab.get_auto_backup_config(PROJECT, VOLUME)
    assert failed["last_status"] == "error" and failed["last_error"] == ab._AUTH_ERROR
    assert failed["revision"] == config["revision"]
    assert failed["next_run_at"] == config["next_run_at"]
    cloud = TokenOwnedCloud(PROJECT)
    await ab.scheduler_tick(now=due(config) + timedelta(seconds=300), connection_factory=lambda _: cloud)
    recovered = await ab.get_auto_backup_config(PROJECT, VOLUME)
    assert recovered["last_status"] == "creating" and recovered["last_error"] is None
    assert not await policy_redis.exists(ab._key("retry", PROJECT, VOLUME))
    assert len(cloud.submissions) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fence", ["revision", "lease"])
async def test_auth_status_write_and_clear_are_fenced(policy_redis, caplog, fence):
    config = await save()
    key = ab._key("config", PROJECT, VOLUME)
    raw = ab._text(await policy_redis.get(key))
    async with ab._volume_lease(policy_redis, PROJECT, VOLUME) as lease:
        if fence == "revision":
            await ab.enable_auto_backup(PROJECT, VOLUME, enabled=False, now=START)
        else:
            await policy_redis.set(lease.key, "new-owner")
        expected = await policy_redis.get(key)
        await ab._record_auth_failure(policy_redis, lease, PROJECT, VOLUME, raw, due(config), Unauthorized("private"))
        assert await policy_redis.get(key) == expected
        assert not await policy_redis.exists(ab._key("retry", PROJECT, VOLUME))
        assert not [r for r in caplog.records if "retry deferred" in r.message]
        # The same fences also reject a late clear of another policy's status.
        newer = await ab.get_auto_backup_config(PROJECT, VOLUME)
        newer.update(last_status="error", last_error=ab._AUTH_ERROR)
        await policy_redis.set(key, ab._dump(newer))
        expected = await policy_redis.get(key)
        await ab._clear_auth_failure(policy_redis, lease, PROJECT, VOLUME, config["revision"])
        assert await policy_redis.get(key) == expected


@pytest.mark.asyncio
async def test_transient_cinder_volume_read_failure_does_not_back_off(policy_redis, monkeypatch):
    config = await save()
    cloud = TokenOwnedCloud(PROJECT)

    def unavailable(_):
        raise RuntimeError("private native outage")

    monkeypatch.setattr(cloud, "get_volume", unavailable)
    for offset in (0, 15):
        await ab.scheduler_tick(now=due(config) + timedelta(seconds=offset), connection_factory=lambda _: cloud)
    assert cloud.closed == 2
    assert not await policy_redis.exists(ab._key("retry", PROJECT, VOLUME))
    assert cloud.submissions == []


@pytest.mark.asyncio
async def test_successful_deferred_cycle_clears_auth_error_without_fake_completion(policy_redis, monkeypatch):
    config = await save()

    def denied(_):
        raise Unauthorized("private identity")

    await ab.scheduler_tick(now=due(config), connection_factory=denied)
    monkeypatch.setattr(auto_snapshot, "_PREFIX", ab._PREFIX + ":snapshot")
    monkeypatch.setattr(auto_snapshot, "_ALL_KEY", auto_snapshot._PREFIX + ":all_configs")
    await auto_snapshot.enable_auto_snapshot(PROJECT, VOLUME, now=START)
    cloud = TokenOwnedCloud(PROJECT)
    cloud.volume.status = "backing-up"
    await ab.scheduler_tick(now=due(config) + timedelta(seconds=300), connection_factory=lambda _: cloud)
    recovered = await ab.get_auto_backup_config(PROJECT, VOLUME)
    assert recovered["last_error"] is None
    assert recovered["last_status"] == "never"
    assert recovered["next_run_at"] == config["next_run_at"]
    assert cloud.submissions == []


@pytest.mark.asyncio
async def test_default_factory_eager_auth_denial_writes_status_and_closes_lazy_connection(
    policy_redis, monkeypatch, caplog
):
    config = await save()
    cloud = TokenOwnedCloud(PROJECT)
    calls = []

    def denied(_):
        raise Unauthorized("private Keystone response")

    cloud.session.auth.get_access = denied

    def lazy_connection(project_id):
        calls.append(project_id)
        return cloud

    monkeypatch.setattr(backup_system_account, "get_connection_for_project", lazy_connection)
    await ab.scheduler_tick(now=due(config))
    await ab.scheduler_tick(now=due(config) + timedelta(seconds=15))
    result = await ab.get_auto_backup_config(PROJECT, VOLUME)
    assert result["last_status"] == "error" and result["last_error"] == ab._AUTH_ERROR
    assert await policy_redis.exists(ab._key("retry", PROJECT, VOLUME))
    assert calls == [PROJECT]
    assert cloud.closed == 1
    assert cloud.submissions == []
    assert len([r for r in caplog.records if "retry deferred" in r.message]) == 1
    assert "private Keystone" not in caplog.text
