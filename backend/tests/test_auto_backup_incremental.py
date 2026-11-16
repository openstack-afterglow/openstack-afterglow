"""Daily Cinder chains preserve manual points and durable unknown submissions."""

import json
from datetime import timedelta

import pytest
from openstack.exceptions import HttpException

from app.services import auto_backup as ab
from tests.test_auto_backup import PROJECT, VOLUME, BackupCloud, current, due, save
from tests.test_auto_backup import policy_redis as policy_redis


class ChainCloud(BackupCloud):
    """Model Cinder's available-parent selection and dependency delete guard."""

    def __init__(self):
        super().__init__()
        self.parents = {}
        self.defer_deletion = False

    def create_backup(self, **kwargs):
        self.submissions.append(kwargs)
        parent = None
        if kwargs["is_incremental"]:
            available = [
                point
                for point in self.records.values()
                if point.volume_id == kwargs["volume_id"]
                and point.project_id == PROJECT
                and point.status == "available"
            ]
            if not available:
                raise HttpException(http_status=400, message="No available parent")
            parent = max(available, key=lambda point: getattr(point, "data_timestamp", point.created_at))
            parent.has_dependent_backups = True
        backup_id = f"submitted-{len(self.submissions)}"
        point = self.add(
            backup_id,
            kwargs["name"],
            status="creating",
            is_incremental=kwargs["is_incremental"],
            created_at=f"2026-06-{len(self.submissions):02d}T03:00:00+00:00",
        )
        self.parents[backup_id] = parent.id if parent else None
        if self.submit_error:
            raise self.submit_error
        return point

    def delete_backup(self, backup_id, **kwargs):
        if self.records[backup_id].has_dependent_backups:
            raise HttpException(http_status=400, message="Dependent backups exist")
        if self.defer_deletion:
            self.records[backup_id].status = "deleting"
            self.deleted.append(backup_id)
            return
        super().delete_backup(backup_id, **kwargs)
        parent = self.parents.pop(backup_id, None)
        if parent in self.records:
            self.records[parent].has_dependent_backups = any(value == parent for value in self.parents.values())

    def managed(self, backup_id, tier, day, *, parent=None):
        point = self.add(
            backup_id,
            f"afterglow_auto_{PROJECT}_{VOLUME}_{tier}_202605{day:02d}T030000Z",
            created_at=f"2026-05-{day:02d}T03:00:00+00:00",
            is_incremental=parent is not None,
        )
        self.parents[backup_id] = parent
        if parent:
            self.records[parent].has_dependent_backups = True
        return point


async def complete(cloud, config):
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    cloud.records[f"submitted-{len(cloud.submissions)}"].status = "available"
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))


@pytest.mark.asyncio
async def test_first_daily_full_then_incremental_within_retention_window(policy_redis):
    cloud = ChainCloud()
    config = await save(max_daily=2, max_weekly=0, max_monthly=0)
    assert "method" not in config  # Existing stored policies need no new setting or migration.
    await complete(cloud, config)
    assert cloud.submissions[0]["is_incremental"] is False
    assert (await current())["last_full_fallback"] is True
    config = await current()
    await complete(cloud, config)
    assert cloud.submissions[1]["is_incremental"] is True
    assert cloud.parents["submitted-2"] == "submitted-1"
    assert cloud.deleted == []
    result = await current()
    assert result["last_status"] == "available"
    assert result["last_backup_method"] == "incremental"
    assert result["last_full_fallback"] is False
    assert result["retained_over_limit"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tier,counts", [("weekly", (0, 1, 0)), ("monthly", (0, 0, 1))])
async def test_weekly_monthly_are_full_even_with_usable_base(policy_redis, tier, counts):
    cloud = ChainCloud()
    cloud.add("manual-base", "manual")
    config = await save(max_daily=counts[0], max_weekly=counts[1], max_monthly=counts[2])
    assert config["next_tier"] == tier
    await complete(cloud, config)
    assert cloud.submissions[0]["is_incremental"] is False
    assert (await current())["last_backup_method"] == "full"
    assert (await current())["last_full_fallback"] is False
    assert "manual-base" in cloud.records


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"status": "error"},
        {"status": "creating"},
        {"project_id": "other"},
        {"volume_id": "other"},
        {"is_incremental": None},
    ],
)
async def test_daily_full_fallback_requires_available_exact_owned_full(policy_redis, fields):
    cloud = ChainCloud()
    cloud.add("unusable-base", "manual", **fields)
    cloud.add("orphan-incremental", "manual-incremental", is_incremental=True)
    config = await save(max_daily=3, max_weekly=0, max_monthly=0)
    await complete(cloud, config)
    assert cloud.submissions[0]["is_incremental"] is False
    assert (await current())["last_full_fallback"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 3])
async def test_manual_latest_backup_starts_full_instead_of_extending_uncertain_chain(policy_redis, count):
    cloud = ChainCloud()
    cloud.managed("owned-base", "daily", 1)
    cloud.add("manual-latest", "operator-copy", created_at="2026-05-30T03:00:00+00:00", is_incremental=True)
    cloud.parents["manual-latest"] = "owned-base"
    cloud.records["owned-base"].has_dependent_backups = True
    config = await save(max_daily=count, max_weekly=0, max_monthly=0)
    await complete(cloud, config)
    assert cloud.submissions[0]["is_incremental"] is False
    assert cloud.parents["submitted-1"] is None
    assert cloud.deleted == []
    assert (await current())["retained_over_limit"] == (["owned-base"] if count == 1 else [])
    assert (await current())["last_status"] == "available"


@pytest.mark.asyncio
async def test_retention_deletes_cross_tier_children_before_full_parent(policy_redis):
    cloud = ChainCloud()
    cloud.managed("base", "monthly", 1)
    cloud.managed("middle", "daily", 2, parent="base")
    cloud.managed("leaf", "daily", 3, parent="middle")
    cloud.managed("kept-daily", "daily", 4)
    config = await save(max_daily=1, max_weekly=0, max_monthly=1)
    await complete(cloud, config)
    assert cloud.deleted == ["leaf", "middle", "base"]
    assert (await current())["retained_over_limit"] == []


@pytest.mark.asyncio
async def test_manual_dependent_keeps_owned_full_without_failing_cycle(policy_redis):
    cloud = ChainCloud()
    cloud.managed("base", "monthly", 1)
    cloud.add("manual-child", "manual", is_incremental=True)
    cloud.parents["manual-child"] = "base"
    cloud.records["base"].has_dependent_backups = True
    config = await save(max_daily=0, max_weekly=0, max_monthly=1)
    await complete(cloud, config)
    assert cloud.deleted == []
    assert (await current())["retained_over_limit"] == ["base"]
    assert (await current())["last_status"] == "available"
    assert not await policy_redis.exists(ab._key("active", PROJECT, VOLUME))


@pytest.mark.asyncio
async def test_async_child_deletion_keeps_parent_until_native_dependencies_clear(policy_redis):
    cloud = ChainCloud()
    cloud.managed("base", "monthly", 1)
    cloud.managed("leaf", "daily", 2, parent="base")
    cloud.managed("kept-daily", "daily", 3)
    cloud.defer_deletion = True
    config = await save(max_daily=1, max_weekly=0, max_monthly=1)
    await complete(cloud, config)
    assert cloud.deleted == ["leaf"]
    assert cloud.records["base"].has_dependent_backups is True
    assert (await current())["retained_over_limit"] == ["base"]


@pytest.mark.asyncio
async def test_manual_child_racing_delete_is_retained_not_a_cycle_failure(policy_redis, monkeypatch):
    cloud = ChainCloud()
    cloud.managed("base", "monthly", 1)
    original = cloud.delete_backup

    def concurrent_child(backup_id, **kwargs):
        cloud.records[backup_id].has_dependent_backups = True
        original(backup_id, **kwargs)

    monkeypatch.setattr(cloud, "delete_backup", concurrent_child)
    config = await save(max_daily=0, max_weekly=0, max_monthly=1)
    await complete(cloud, config)
    assert cloud.deleted == []
    assert (await current())["last_status"] == "available"
    assert (await current())["retained_over_limit"] == ["base"]


@pytest.mark.asyncio
async def test_incremental_lost_reply_reconciles_exact_slot_without_replaying(policy_redis):
    cloud = ChainCloud()
    cloud.managed("owned-base", "daily", 1)
    cloud.submit_error = TimeoutError("lost accepted incremental reply")
    config = await save(max_daily=3, max_weekly=0, max_monthly=0)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    active = json.loads(await policy_redis.get(ab._key("active", PROJECT, VOLUME)))
    assert active["backup_method"] == "incremental"
    assert active["status"] == "unknown"
    cloud.records["submitted-1"].status = "available"
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config) + timedelta(hours=1))
    assert len(cloud.submissions) == 1
    assert (await current())["last_backup_method"] == "incremental"
    assert (await current())["last_backup_id"] == "submitted-1"
    assert (await current())["last_status"] == "available"


@pytest.mark.asyncio
async def test_parent_disappearing_before_post_rejects_once_without_full_retry(policy_redis, monkeypatch):
    cloud = ChainCloud()
    cloud.managed("owned-base", "daily", 1)
    original = cloud.create_backup

    def gone(**kwargs):
        cloud.records.clear()
        return original(**kwargs)

    monkeypatch.setattr(cloud, "create_backup", gone)
    config = await save(max_daily=3, max_weekly=0, max_monthly=0)
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    await ab.run_backup_cycle(cloud, PROJECT, VOLUME, now=due(config))
    assert len(cloud.submissions) == 1
    assert cloud.submissions[0]["is_incremental"] is True
    assert (await current())["last_status"] == "error"


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [1, 2, 3, 5])
async def test_daily_only_rotates_full_and_converges_with_bounded_chain_slack(policy_redis, count):
    cloud = ChainCloud()
    config = await save(max_daily=count, max_weekly=0, max_monthly=0)
    for day in range(3 * count + 1):
        await complete(cloud, config)
        assert cloud.submissions[-1]["is_incremental"] is (day % count != 0)
        assert len(cloud.records) <= count + count - 1
        config = await current()
        assert config["last_status"] == "available"
        if (day + 1) % count == 0:
            assert len(cloud.records) == count
            assert config["retained_over_limit"] == []
    for point in cloud.records:
        depth = 1
        parent = cloud.parents[point]
        while parent:
            depth += 1
            parent = cloud.parents[parent]
        assert depth <= count


@pytest.mark.asyncio
async def test_weekly_full_resets_daily_chain_length_and_daily_rotation_still_applies(policy_redis):
    cloud = ChainCloud()
    config = await save(max_daily=3, max_weekly=1, max_monthly=0)
    methods = []
    for _ in range(9):
        await complete(cloud, config)
        methods.append((config["next_tier"], cloud.submissions[-1]["is_incremental"]))
        config = await current()
    assert methods == [
        ("weekly", False),
        ("daily", True),
        ("daily", True),
        ("daily", False),
        ("daily", True),
        ("daily", True),
        ("daily", False),
        ("weekly", False),
        ("daily", True),
    ]
    assert len(cloud.records) <= 3 + 1 + 2
