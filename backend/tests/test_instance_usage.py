"""Native metadata policy, concurrency fences, and cancellation resource ownership."""

import asyncio
import copy
import hashlib
import secrets
import threading
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.instance_usage import (
    UsageScheduleExtension,
    UsageScheduleInfo,
    UsageScheduleRequest,
    UsageScheduleUpdate,
)
from app.services import instance_usage as usage

START = datetime(2026, 1, 31, 12, 34, 56, tzinfo=UTC)
P = usage.METADATA_PREFIX
SMALL = {"name": "cpu.small", "vcpus": 2, "ram": 4096, "extra_specs": {}}
LARGE = {**SMALL, "vcpus": 12}


@pytest.mark.parametrize(
    ("clock", "expected"),
    [
        (START, datetime(2026, 2, 28, 12, 34, 56, tzinfo=UTC)),
        (datetime(2028, 1, 31, tzinfo=UTC), datetime(2028, 2, 29, tzinfo=UTC)),
        (datetime(2026, 12, 31, tzinfo=UTC), datetime(2027, 1, 31, tzinfo=UTC)),
        (datetime(2026, 3, 31, tzinfo=UTC), datetime(2026, 4, 30, tzinfo=UTC)),
        (datetime(2026, 5, 1, 1, tzinfo=timezone(timedelta(hours=9))), datetime(2026, 5, 30, 16, tzinfo=UTC)),
    ],
)
def test_calendar_month_clamps_in_utc(clock, expected):
    assert usage.calendar_month_after(clock) == expected


def test_calendar_month_refuses_naive_time():
    with pytest.raises(ValueError):
        usage.calendar_month_after(datetime(2026, 1, 31))


@pytest.mark.parametrize(
    ("flavor", "required"),
    [
        (SMALL, False),
        ({**SMALL, "vcpus": 11, "ram": 65535}, False),
        ({**SMALL, "vcpus": 12}, True),
        ({**SMALL, "ram": 65536}, True),
        ({**SMALL, "vcpus": "12"}, True),
        ({**SMALL, "name": "cpu.999c_999g"}, False),
        ({**SMALL, "extra_specs": {"afterglow:usage_schedule_required": "true"}}, True),
        ({**SMALL, "extra_specs": {"afterglow:usage_schedule_required": "ON"}}, True),
        ({**LARGE, "extra_specs": {"afterglow:usage_schedule_required": "false"}}, True),
        ({**SMALL, "extra_specs": {"resources:VGPU": "1"}}, True),
        ({**SMALL, "extra_specs": {"resources1:PGPU": "2"}}, True),
        ({**SMALL, "extra_specs": {"resources:VGPU": "0"}}, False),
        ({**SMALL, "extra_specs": {"pci_passthrough:alias": "RTX3090:1"}}, True),
        ({**SMALL, "extra_specs": {"pci_passthrough:alias": "sriov-nic:1"}}, False),
        ({**SMALL, "is_gpu": True}, True),
        ({**SMALL, "name": "gpu.small", "extra_specs": {"afterglow:usage_schedule_required": "false"}}, True),
    ],
)
def test_gpu_thresholds_and_additive_designation(flavor, required):
    assert usage.requires_schedule(flavor) is required
    assert usage.requires_schedule(SimpleNamespace(**flavor)) is required


def test_flavor_computed_projection_does_not_recurse():
    from app.models.compute import FlavorInfo

    flavor = FlavorInfo(id="cpu12", name="cpu12", vcpus=12, ram=4096, disk=0)
    assert usage.requires_schedule(flavor)
    assert flavor.usage_schedule_required


def test_explicit_required_creation_and_one_time_adoption_grace():
    with pytest.raises(HTTPException) as error:
        usage.creation_metadata(LARGE, None, now=START)
    assert error.value.status_code == 422
    assert usage.creation_metadata(SMALL, None, now=START) == {}
    created = usage.creation_metadata(LARGE, UsageScheduleRequest(), now=START)
    adopted = usage.adoption_metadata(now=START)
    assert created[P + "source"] == "created"
    assert adopted[P + "source"] == "adopted"
    assert created[P + "expires_at"] == adopted[P + "expires_at"] == "2026-02-28T12:34:56+00:00"
    assert adopted[P + "starts_at"] == START.isoformat()
    assert adopted[P + "action"] == "shelve"
    assert adopted[P + "delete_volumes"] == "false"
    assert created[P + "revision"] != adopted[P + "revision"]
    assert all(isinstance(value, str) and len(value.encode()) <= 255 for value in created.values())


@pytest.mark.parametrize(
    ("reference", "enrollment", "expiry"),
    [
        ("2026-01-31T12:34:56Z", START + timedelta(days=7), "2026-02-28T12:34:56+00:00"),
        ("2028-01-31T00:00:00Z", datetime(2028, 2, 20, tzinfo=UTC), "2028-02-29T00:00:00+00:00"),
        ("2026-05-01T01:00:00+09:00", datetime(2026, 5, 10, tzinfo=UTC), "2026-05-30T16:00:00+00:00"),
        ("2026-12-31T00:00:00Z", datetime(2027, 1, 10, tzinfo=UTC), "2027-01-31T00:00:00+00:00"),
        # A future common baseline is not capped to the per-enrollment month.
        ("2026-02-10T00:00:00Z", START, "2026-03-10T00:00:00+00:00"),
    ],
)
def test_adoption_common_reference_uses_exact_utc_calendar_month(reference, enrollment, expiry):
    values = usage.adoption_metadata(now=enrollment, reference_at=reference)
    assert values[P + "starts_at"] == enrollment.isoformat()
    assert values[P + "expires_at"] == expiry
    assert values[P + "action"] == "shelve"
    assert values[P + "delete_volumes"] == "false"
    assert usage.parse_schedule({"id": "adopted", "metadata": values}).source == "adopted"


@pytest.mark.parametrize("reference", [None, ""])
def test_adoption_unset_reference_preserves_per_enrollment_month(reference):
    values = usage.adoption_metadata(now=START, reference_at=reference)
    assert values[P + "expires_at"] == usage.calendar_month_after(START).isoformat()


@pytest.mark.parametrize(
    "reference",
    [
        "not-a-date",
        "2026-01-01",
        "2026-01-01T00:00:00",
        "2026-02-30T00:00:00Z",
        "9999-12-01T00:00:00Z",
        "2025-12-31T12:34:56Z",  # Expiry equals enrollment.
        "2025-12-31T12:34:55Z",  # Expiry precedes enrollment.
    ],
)
def test_adoption_rejects_invalid_or_expired_common_reference(reference):
    with pytest.raises(ValueError, match="Usage adoption reference"):
        usage.adoption_metadata(now=START, reference_at=reference)


def test_creation_requires_future_date_and_reason_beyond_calendar_month():
    for expiry in (START, START - timedelta(seconds=1)):
        with pytest.raises(HTTPException) as error:
            usage.creation_metadata(LARGE, UsageScheduleRequest(expires_at=expiry), now=START)
        assert error.value.status_code == 422
    later = usage.calendar_month_after(START) + timedelta(seconds=1)
    with pytest.raises(HTTPException):
        usage.creation_metadata(LARGE, UsageScheduleRequest(expires_at=later), now=START)
    values = usage.creation_metadata(
        LARGE, UsageScheduleRequest(expires_at=later, reason="  finish training  "), now=START
    )
    assert values[P + "reason"] == "finish training"


@pytest.mark.parametrize(
    "fields",
    [
        {"expires_at": "2026-02-01T12:00:00"},
        {"expires_at": 1760000000},
        {"delete_volumes": "false"},
        {"delete_volumes": 1, "expiry_action": "delete"},
        {"delete_volumes": True},
        {"expiry_action": "stop"},
        {"reason": "a\nb"},
        {"reason": "a\x00b"},
        {"reason": "\ud800"},
        {"reason": "한" * 86},
        {"unexpected": True},
    ],
)
def test_request_validation_rejects_unsafe_values(fields):
    with pytest.raises(ValidationError):
        UsageScheduleRequest(**fields)


def test_utf8_byte_limit_trim_and_explicit_deletion_consent():
    reason = "한" * 85
    request = UsageScheduleRequest(reason=f"  {reason}  ", expiry_action="delete", delete_volumes=True)
    values = usage.creation_metadata(SMALL, request, now=START)
    assert values[P + "reason"] == reason
    assert len(reason.encode()) == 255
    assert values[P + "delete_volumes"] == "true"


def test_extension_model_requires_reason_revision_and_aware_date():
    valid = {"expires_at": "2026-03-01T00:00:00Z", "reason": "more time", "revision": "a" * 32}
    assert UsageScheduleExtension(**valid).expires_at.tzinfo == UTC
    for overrides in ({"reason": " "}, {"revision": "bad"}, {"expires_at": "2026-03-01"}):
        with pytest.raises(ValidationError):
            UsageScheduleExtension(**(valid | overrides))


def test_metadata_roundtrip_and_unrelated_keys():
    values = usage.adoption_metadata(now=START)
    parsed = usage.parse_schedule({"id": "vm", "metadata": {**values, "owner": "unrelated"}})
    assert parsed.source == "adopted"
    assert parsed.state == "active"
    assert parsed.last_error is None
    assert usage.parse_schedule(SimpleNamespace(id="vm", metadata={"owner": "unrelated"})) is None
    assert UsageScheduleInfo.model_validate(parsed.model_dump()) == parsed


@pytest.mark.parametrize(
    "override",
    [
        {"version": "2"},
        {"state": "executing"},
        {"source": "database"},
        {"delete_volumes": "1"},
        {"delete_volumes": True},
        {"delete_volumes": "true", "action": "shelve"},
        {"starts_at": "2026-01-01"},
        {"expires_at": START.isoformat()},
        {"reason": " native untrimmed "},
        {"reason": "a\nb"},
        {"reason": "한" * 86},
        {"reason": "\ud800"},
        {"revision": "bad"},
        {"unsupported": "value"},
        {"extended_at": START.isoformat()},
        {"state": "delete_requested", "action": "shelve"},
        {"state": "shelve_requested", "action": "delete"},
    ],
)
def test_partial_or_malformed_native_metadata_is_never_absent(override):
    values = usage.adoption_metadata(now=START)
    values.update({P + key: value for key, value in override.items()})
    with pytest.raises(HTTPException) as error:
        usage.parse_schedule({"id": "vm", "metadata": values})
    assert error.value.status_code == 409


def test_partial_metadata_and_unknown_key_fail_closed():
    for metadata in ({P + "reason": "only one"}, {P + "future_version": "1"}, []):
        with pytest.raises(HTTPException) as error:
            usage.parse_schedule({"id": "vm", "metadata": metadata})
        assert error.value.status_code == 409


class NativeCompute:
    """SDK-shaped boundary: shared provider state, per-invocation adapter policy."""

    def __init__(self, state):
        self.state = state

    def request(self, *args, **kwargs):
        self.state.request_options.append(kwargs)
        return SimpleNamespace(status_code=200)

    def get_server(self, identifier):
        if self.state.read_error:
            raise self.state.read_error
        return copy.deepcopy(self.state.server)

    def set_server_metadata(self, identifier, **values):
        self.request("servers/metadata", method="POST", json={"metadata": values})
        self.state.writes.append(dict(values))
        self.state.server.metadata.update(values)
        if self.state.write_error:
            raise self.state.write_error
        if self.state.readback_override:
            self.state.server.metadata.update(self.state.readback_override)
        return self.state.server


class Cloud:
    def __init__(self, *, metadata=None, endpoint="https://identity.example/v3"):
        self._afterglow_project_id = "project-" + secrets.token_hex(6)
        self._afterglow_authenticated_project_id = self._afterglow_project_id
        self.server = SimpleNamespace(
            id="vm-" + secrets.token_hex(6),
            project_id=self._afterglow_project_id,
            metadata=metadata
            if metadata is not None
            else {**usage.adoption_metadata(now=START), "unrelated": "retain me"},
        )
        self.endpoint = endpoint
        self.writes, self.request_options = [], []
        self.read_error = self.write_error = self.readback_override = None
        self.compute = NativeCompute(self)

    def endpoint_for(self, service):
        assert service == "identity"
        return self.endpoint


@pytest.fixture
async def lease_redis(_fake_redis_global):
    from app.services.cache import _get_redis

    return await _get_redis()


def revision(cloud):
    return cloud.server.metadata[P + "revision"]


@pytest.mark.asyncio
async def test_update_native_readback_preserves_metadata_and_disables_replays(lease_redis):
    cloud = Cloud()
    original_request = cloud.compute.request
    result = await usage.update_schedule(
        cloud,
        cloud.server,
        UsageScheduleUpdate(revision=revision(cloud), expiry_action="delete"),
        user_id="user-a",
        now=START,
        redis=lease_redis,
    )
    assert result.expiry_action == "delete"
    assert result.delete_volumes is False
    assert result.expires_at == "2026-02-28T12:34:56+00:00"
    assert cloud.server.metadata["unrelated"] == "retain me"
    assert cloud.compute.request == original_request
    assert len(cloud.writes) == 1
    options = cloud.request_options[0]
    assert options["redirect"] is False
    assert options["allow_reauth"] is False
    assert options["connect_retries"] == options["status_code_retries"] == 0


@pytest.mark.asyncio
async def test_reasoned_extension_preserves_existing_delete_consent_and_latest_reason(lease_redis):
    cloud = Cloud(
        metadata=usage.creation_metadata(
            SMALL, UsageScheduleRequest(expiry_action="delete", delete_volumes=True), now=START
        )
    )
    original_revision = revision(cloud)
    result = await usage.extend_schedule(
        cloud,
        cloud.server,
        UsageScheduleExtension(
            revision=original_revision, expires_at=datetime(2026, 3, 28, tzinfo=UTC), reason="finish experiment"
        ),
        user_id="user-a",
        now=START + timedelta(days=3),
        redis=lease_redis,
    )
    assert result.expiry_action == "delete" and result.delete_volumes
    assert result.reason == "finish experiment"
    assert result.extended_by == "user-a"
    assert result.extended_at == (START + timedelta(days=3)).isoformat()
    assert result.revision != original_revision
    result = await usage.update_schedule(
        cloud,
        cloud.server,
        UsageScheduleUpdate(revision=result.revision, reason=""),
        user_id="user-a",
        now=START + timedelta(days=4),
        redis=lease_redis,
    )
    assert result.reason == "finish experiment"


@pytest.mark.asyncio
async def test_stale_revision_and_native_executing_states_never_dispatch_update(lease_redis):
    for state in (
        "shelve_requested",
        "offload_requested",
        "stop_requested",
        "volume_flags_requested",
        "volumes_ready",
        "delete_requested",
        "unknown",
    ):
        cloud = Cloud()
        cloud.server.metadata[P + "state"] = state
        if state in {"stop_requested", "volume_flags_requested", "volumes_ready", "delete_requested"}:
            cloud.server.metadata[P + "action"] = "delete"
        with pytest.raises(HTTPException) as error:
            await usage.extend_schedule(
                cloud,
                cloud.server,
                UsageScheduleExtension(
                    revision=revision(cloud), expires_at=datetime(2026, 3, 1, tzinfo=UTC), reason="retain"
                ),
                user_id="user-a",
                now=START,
                redis=lease_redis,
            )
        assert error.value.status_code == 409 and not cloud.writes
    cloud = Cloud()
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud, cloud.server, UsageScheduleUpdate(revision="0" * 32), user_id="u", now=START, redis=lease_redis
        )
    assert error.value.status_code == 409 and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["blocked", "complete"])
async def test_future_extension_resumes_without_native_unshelve(lease_redis, state):
    cloud = Cloud()
    cloud.server.metadata[P + "state"] = state
    cloud.server.metadata[P + "last_error"] = "Previous precheck blocked"
    with pytest.raises(HTTPException):
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud)),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
    result = await usage.extend_schedule(
        cloud,
        cloud.server,
        UsageScheduleExtension(
            revision=revision(cloud), expires_at=datetime(2026, 3, 28, tzinfo=UTC), reason="continue"
        ),
        user_id="u",
        now=START,
        redis=lease_redis,
    )
    assert result.state == "active" and result.last_error is None
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_concurrent_extensions_have_one_winner(lease_redis):
    cloud = Cloud()
    request = UsageScheduleExtension(
        revision=revision(cloud), expires_at=datetime(2026, 3, 28, tzinfo=UTC), reason="more compute"
    )
    results = await asyncio.gather(
        *(
            usage.extend_schedule(cloud, cloud.server, request, user_id="u", now=START, redis=lease_redis)
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, UsageScheduleInfo) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_dispatch_and_extension_share_exact_cloud_project_server_lock(lease_redis):
    cloud = Cloud()
    async with usage.usage_lease(
        cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis
    ) as dispatcher_lease:
        assert await dispatcher_lease.current()
        with pytest.raises(HTTPException) as error:
            await usage.update_schedule(
                cloud,
                cloud.server,
                UsageScheduleUpdate(revision=revision(cloud)),
                user_id="u",
                now=START,
                redis=lease_redis,
            )
        assert error.value.status_code == 409
        await usage.write_schedule_metadata(
            cloud, cloud.server, {P + "state": "shelve_requested"}, lease=dispatcher_lease
        )
    assert cloud.server.metadata[P + "state"] == "shelve_requested"
    assert await lease_redis.get(dispatcher_lease.key) is None


@pytest.mark.asyncio
async def test_cross_cloud_leases_do_not_collide_and_stale_release_is_cas(lease_redis):
    first, second = Cloud(), Cloud(endpoint="https://other-identity.example/v3")
    second._afterglow_project_id = second._afterglow_authenticated_project_id = first._afterglow_project_id
    second.server.id = first.server.id
    async with usage.usage_lease(first, first._afterglow_project_id, first.server.id, redis=lease_redis) as a:
        async with usage.usage_lease(second, second._afterglow_project_id, second.server.id, redis=lease_redis) as b:
            assert a.key != b.key and await a.current() and await b.current()
        await lease_redis.set(a.key, "new-owner", ex=90)
        assert not await a.current()
    assert await lease_redis.get(a.key) in ("new-owner", b"new-owner")
    await lease_redis.delete(a.key)


@pytest.mark.asyncio
async def test_missing_redis_and_cross_project_scope_fail_closed():
    class Unavailable:
        async def set(self, *args, **kwargs):
            raise OSError("unavailable")

    cloud = Cloud()
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud)),
            user_id="u",
            now=START,
            redis=Unavailable(),
        )
    assert error.value.status_code == 409 and not cloud.writes
    cloud.server.project_id = "another-project"
    with pytest.raises(HTTPException) as error:
        usage.require_server_scope(cloud, cloud.server)
    assert error.value.status_code == 403
    cloud.server.project_id = cloud._afterglow_project_id
    cloud._afterglow_authenticated_project_id = "system-or-other"
    with pytest.raises(HTTPException) as error:
        usage.require_server_scope(cloud, cloud.server)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_adoption_does_not_overwrite_partial_or_preexisting_metadata(lease_redis):
    cloud = Cloud(metadata={P + "state": "active", "unrelated": "retain"})
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, cloud.server, usage.adoption_metadata(now=START), lease=lease)
    assert error.value.status_code == 409 and not cloud.writes
    cloud = Cloud(metadata={"unrelated": "retain"})
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        result = await usage.write_schedule_metadata(
            cloud, cloud.server, usage.adoption_metadata(now=START), lease=lease
        )
    assert usage.parse_schedule(result).source == "adopted"
    assert result.metadata["unrelated"] == "retain"
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, result, usage.adoption_metadata(now=START), lease=lease)
    assert error.value.status_code == 409 and len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_native_change_since_snapshot_is_not_overwritten(lease_redis):
    cloud = Cloud()
    snapshot = copy.deepcopy(cloud.server)
    cloud.server.metadata[P + "revision"] = "b" * 32
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, snapshot, {P + "state": "shelve_requested"}, lease=lease)
    assert error.value.status_code == 409 and not cloud.writes


@pytest.mark.asyncio
async def test_uncertain_native_write_retains_marker_without_replay(lease_redis):
    cloud = Cloud()
    cloud.server.metadata[P + "action"] = "delete"
    cloud.write_error = TimeoutError("possibly accepted")
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, cloud.server, {P + "state": "delete_requested"}, lease=lease)
    assert error.value.status_code == 502
    assert cloud.server.metadata[P + "state"] == "delete_requested"
    assert len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_readback_mismatch_and_postwrite_lease_loss_are_unknown_not_success(lease_redis):
    cloud = Cloud()
    cloud.readback_override = {P + "state": "active"}
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, cloud.server, {P + "state": "shelve_requested"}, lease=lease)
    assert error.value.status_code == 502 and len(cloud.writes) == 1
    cloud = Cloud()
    calls = 0

    async def current():
        nonlocal calls
        calls += 1
        return calls < 3

    lease = SimpleNamespace(
        project_id=cloud._afterglow_project_id,
        instance_id=cloud.server.id,
        cloud=hashlib.sha256(cloud.endpoint.encode()).hexdigest(),
        current=current,
    )
    with pytest.raises(HTTPException) as error:
        await usage.write_schedule_metadata(cloud, cloud.server, {P + "state": "shelve_requested"}, lease=lease)
    assert error.value.status_code == 502 and len(cloud.writes) == 1
    assert cloud.server.metadata[P + "state"] == "shelve_requested"


@pytest.mark.asyncio
async def test_cancellation_drains_sdk_before_releasing_lease_even_when_cancelled_twice(lease_redis):
    entered, settle = threading.Event(), threading.Event()
    cloud = Cloud()
    lease_key = None

    def native_write():
        entered.set()
        settle.wait(10)

    async def operation():
        nonlocal lease_key
        async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
            lease_key = lease.key
            await usage.sdk_call(native_write)

    task = asyncio.create_task(operation())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        assert await lease_redis.get(lease_key) is not None
    finally:
        settle.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await lease_redis.get(lease_key) is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        {"expires_at": START},
        {"expires_at": datetime(2026, 3, 1, tzinfo=UTC)},
    ],
)
async def test_update_rejects_nonfuture_shortening_or_extension_without_reason(lease_redis, fields):
    cloud = Cloud()
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud), **fields),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
    assert error.value.status_code == 422 and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["shelve", "delete"])
async def test_future_shortening_preserves_policy_and_extension_attribution(lease_redis, action):
    metadata = usage.creation_metadata(
        SMALL,
        UsageScheduleRequest(expiry_action=action, delete_volumes=action == "delete", reason="finish experiment"),
        now=START,
    )
    metadata.update({P + "extended_at": START.isoformat(), P + "extended_by": "original-user"})
    cloud = Cloud(metadata={**metadata, "unrelated": "retain me"})
    original_revision = revision(cloud)
    result = await usage.update_schedule(
        cloud,
        cloud.server,
        UsageScheduleUpdate(revision=original_revision, expires_at=START + timedelta(days=5)),
        user_id="shortening-user",
        now=START + timedelta(days=2),
        redis=lease_redis,
    )
    assert result.expires_at == (START + timedelta(days=5)).isoformat()
    assert result.expiry_action == action
    assert result.delete_volumes is (action == "delete")
    assert result.state == "active" and result.revision != original_revision
    assert result.reason == "finish experiment"
    assert result.extended_at == START.isoformat() and result.extended_by == "original-user"
    assert cloud.server.metadata["unrelated"] == "retain me"
    assert len(cloud.writes) == 1
    assert P + "extended_at" not in cloud.writes[0] and P + "extended_by" not in cloud.writes[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expiry",
    [START - timedelta(seconds=1), START, START + timedelta(days=1), START + timedelta(days=2)],
)
async def test_shortening_must_follow_clock_and_enrollment(lease_redis, expiry):
    cloud = Cloud()
    original = copy.deepcopy(cloud.server.metadata)
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud), expires_at=expiry),
            user_id="u",
            now=START + timedelta(days=2),
            redis=lease_redis,
        )
    assert error.value.status_code == 422
    assert cloud.server.metadata == original and not cloud.writes


@pytest.mark.asyncio
async def test_shortening_cannot_precede_enrollment_even_with_earlier_clock(lease_redis):
    cloud = Cloud()
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud), expires_at=START),
            user_id="u",
            now=START - timedelta(seconds=1),
            redis=lease_redis,
        )
    assert error.value.status_code == 422 and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "blocked",
        "complete",
        "shelve_requested",
        "offload_requested",
        "stop_requested",
        "volume_flags_requested",
        "volumes_ready",
        "delete_requested",
        "unknown",
    ],
)
async def test_shortening_never_reactivates_fenced_schedule(lease_redis, state):
    cloud = Cloud()
    cloud.server.metadata[P + "state"] = state
    cloud.server.metadata[P + "last_error"] = "Keep the execution outcome"
    if state in {"stop_requested", "volume_flags_requested", "volumes_ready", "delete_requested"}:
        cloud.server.metadata[P + "action"] = "delete"
    original = copy.deepcopy(cloud.server.metadata)
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud), expires_at=START + timedelta(days=5)),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
    assert error.value.status_code == 409
    assert cloud.server.metadata == original and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("extension_only", [False, True])
@pytest.mark.parametrize("beyond_limit", [False, True])
@pytest.mark.parametrize(
    ("previous", "limit"),
    [
        (datetime(2026, 1, 31, 12, tzinfo=UTC), datetime(2026, 2, 28, 12, tzinfo=UTC)),
        (datetime(2028, 1, 31, 12, tzinfo=UTC), datetime(2028, 2, 29, 12, tzinfo=UTC)),
        (datetime(2026, 2, 28, 12, tzinfo=UTC), datetime(2026, 3, 28, 12, tzinfo=UTC)),
        (datetime(2026, 12, 31, 12, tzinfo=UTC), datetime(2027, 1, 31, 12, tzinfo=UTC)),
        (
            datetime(2026, 5, 1, 1, tzinfo=timezone(timedelta(hours=9))),
            datetime(2026, 5, 30, 16, tzinfo=UTC),
        ),
    ],
)
async def test_both_mutations_enforce_calendar_month_from_existing_expiry(
    lease_redis, previous, limit, beyond_limit, extension_only
):
    cloud = Cloud(
        metadata=usage.creation_metadata(
            SMALL, UsageScheduleRequest(expires_at=previous), now=previous - timedelta(days=10)
        )
    )
    expiry = limit + timedelta(seconds=int(beyond_limit))
    request_type = UsageScheduleExtension if extension_only else UsageScheduleUpdate
    mutate = usage.extend_schedule if extension_only else usage.update_schedule
    request = request_type(revision=revision(cloud), expires_at=expiry, reason="finish experiment")
    arguments = {"user_id": "u", "now": previous - timedelta(days=1), "redis": lease_redis}
    if beyond_limit:
        original = copy.deepcopy(cloud.server.metadata)
        with pytest.raises(HTTPException) as error:
            await mutate(cloud, cloud.server, request, **arguments)
        assert error.value.status_code == 422
        assert cloud.server.metadata == original and not cloud.writes
    else:
        result = await mutate(cloud, cloud.server, request, **arguments)
        assert result.expires_at == limit.isoformat()
        assert result.extended_by == "u" and len(cloud.writes) == 1


@pytest.mark.asyncio
async def test_each_extension_uses_latest_expiry_not_request_clock(lease_redis):
    cloud = Cloud()
    expiry = datetime(2026, 2, 28, 12, 34, 56, tzinfo=UTC)
    for _ in range(2):
        expiry = usage.calendar_month_after(expiry)
        result = await usage.extend_schedule(
            cloud,
            cloud.server,
            UsageScheduleExtension(revision=revision(cloud), expires_at=expiry, reason="finish experiment"),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
        assert result.expires_at == expiry.isoformat()
    assert len(cloud.writes) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("extension_only", [False, True])
@pytest.mark.parametrize("past_or_equal", [False, True])
async def test_expired_schedule_extension_requires_future_within_original_month(
    lease_redis, extension_only, past_or_equal
):
    cloud = Cloud()
    previous = datetime.fromisoformat(cloud.server.metadata[P + "expires_at"])
    now = usage.calendar_month_after(previous)
    expiry = now if past_or_equal else now + timedelta(seconds=1)
    request_type = UsageScheduleExtension if extension_only else UsageScheduleUpdate
    mutate = usage.extend_schedule if extension_only else usage.update_schedule
    with pytest.raises(HTTPException) as error:
        await mutate(
            cloud,
            cloud.server,
            request_type(revision=revision(cloud), expires_at=expiry, reason="finish experiment"),
            user_id="u",
            now=now,
            redis=lease_redis,
        )
    assert error.value.status_code == 422 and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [START + timedelta(days=5), datetime(2026, 2, 28, 12, 34, 56, tzinfo=UTC)])
async def test_extension_endpoint_still_rejects_shortening_and_unchanged_expiry(lease_redis, expiry):
    cloud = Cloud()
    with pytest.raises(HTTPException) as error:
        await usage.extend_schedule(
            cloud,
            cloud.server,
            UsageScheduleExtension(revision=revision(cloud), expires_at=expiry, reason="finish experiment"),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
    assert error.value.status_code == 422 and not cloud.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["active", "blocked", "complete"])
async def test_recently_expired_schedule_allows_reasoned_future_extension_within_month(lease_redis, state):
    cloud = Cloud()
    cloud.server.metadata[P + "state"] = state
    previous = datetime.fromisoformat(cloud.server.metadata[P + "expires_at"])
    now = previous + timedelta(days=1)
    expiry = usage.calendar_month_after(previous)
    result = await usage.extend_schedule(
        cloud,
        cloud.server,
        UsageScheduleExtension(revision=revision(cloud), expires_at=expiry, reason="finish experiment"),
        user_id="u",
        now=now,
        redis=lease_redis,
    )
    assert result.expires_at == expiry.isoformat() and result.state == "active"
    assert result.extended_at == now.isoformat() and len(cloud.writes) == 1


def test_shared_update_validator_returns_effective_expiry_without_mutating_schedule():
    cloud = Cloud()
    schedule = usage.parse_schedule(cloud.server)
    original_schedule = schedule.model_dump()
    original_metadata = copy.deepcopy(cloud.server.metadata)
    shortened = START + timedelta(days=5)
    expiry = usage.validate_schedule_update(
        schedule, UsageScheduleUpdate(revision=schedule.revision, expires_at=shortened), now=START
    )
    assert expiry == shortened
    assert schedule.model_dump() == original_schedule
    assert cloud.server.metadata == original_metadata and not cloud.writes
    assert usage.validate_schedule_update(
        schedule, UsageScheduleUpdate(revision=schedule.revision), now=START
    ) == datetime.fromisoformat(schedule.expires_at)


@pytest.mark.asyncio
async def test_lost_lease_and_wrong_resource_lease_never_mutate(lease_redis):
    cloud = Cloud()
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        await lease_redis.set(lease.key, "another-owner", ex=90)
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, cloud.server, {P + "state": "shelve_requested"}, lease=lease)
        assert error.value.status_code == 409 and not cloud.writes
        await lease_redis.delete(lease.key)
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, "different-server", redis=lease_redis) as lease:
        with pytest.raises(HTTPException) as error:
            await usage.write_schedule_metadata(cloud, cloud.server, {P + "state": "shelve_requested"}, lease=lease)
    assert error.value.status_code == 409 and not cloud.writes


@pytest.mark.asyncio
async def test_writer_cannot_write_unowned_keys_or_invalid_action_state(lease_redis):
    cloud = Cloud()
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as lease:
        for changes in ({"owner": "overwritten"}, {P + "reason": "x" * 256}, {P + "state": "delete_requested"}):
            with pytest.raises(HTTPException):
                await usage.write_schedule_metadata(cloud, cloud.server, changes, lease=lease)
    assert not cloud.writes


def test_conflicting_native_project_fields_fail_closed():
    cloud = Cloud()
    cloud.server.tenant_id = "other-project"
    with pytest.raises(HTTPException) as error:
        usage.require_server_scope(cloud, cloud.server)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_settings_update_requires_clearing_existing_volume_deletion_consent(lease_redis):
    cloud = Cloud(
        metadata=usage.creation_metadata(
            SMALL,
            UsageScheduleRequest(expiry_action="delete", delete_volumes=True),
            now=START,
        )
    )
    with pytest.raises(HTTPException) as error:
        await usage.update_schedule(
            cloud,
            cloud.server,
            UsageScheduleUpdate(revision=revision(cloud), expiry_action="shelve"),
            user_id="u",
            now=START,
            redis=lease_redis,
        )
    assert error.value.status_code == 422 and not cloud.writes
    result = await usage.update_schedule(
        cloud,
        cloud.server,
        UsageScheduleUpdate(revision=revision(cloud), expiry_action="shelve", delete_volumes=False),
        user_id="u",
        now=START,
        redis=lease_redis,
    )
    assert result.expiry_action == "shelve" and result.delete_volumes is False


@pytest.mark.asyncio
async def test_subsecond_enrollment_and_browser_roundtrip_do_not_shorten_expiry(lease_redis):
    instant = START.replace(microsecond=987654)
    metadata = usage.adoption_metadata(now=instant)
    assert metadata[P + "starts_at"] == START.isoformat()
    assert metadata[P + "expires_at"] == "2026-02-28T12:34:56+00:00"
    cloud = Cloud(metadata=metadata)
    shown = datetime.fromisoformat(metadata[P + "expires_at"]).isoformat(timespec="milliseconds")
    result = await usage.update_schedule(
        cloud,
        cloud.server,
        UsageScheduleUpdate(revision=revision(cloud), expires_at=shown),
        user_id="u",
        now=instant,
        redis=lease_redis,
    )
    assert result.expires_at == metadata[P + "expires_at"]
    assert UsageScheduleRequest(expires_at=instant).expires_at == START


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("status", [301, 302, 303, 307, 308, 401, 403, 500, None])
def test_safe_proxy_rejects_every_unconfirmed_mutation_without_replay(method, status):
    attempts = []

    class Adapter:
        def request(self, url, request_method, **kwargs):
            attempts.append((url, request_method, kwargs))
            return SimpleNamespace(status_code=status)

    native = Adapter()
    proxy = usage.safe_compute_proxy(SimpleNamespace(compute=native))
    with pytest.raises(HTTPException) as error:
        proxy.request(
            "servers/vm/action", method, redirect=True, allow_reauth=True, connect_retries=4, status_code_retries=4
        )
    assert error.value.status_code == 502
    assert len(attempts) == 1
    assert attempts[0][2] == {
        "redirect": False,
        "allow_reauth": False,
        "connect_retries": 0,
        "status_code_retries": 0,
    }


@pytest.mark.parametrize("status", [200, 201, 202, 204])
def test_safe_proxy_accepts_confirmed_native_mutation(status):
    class Adapter:
        def request(self, url, method, **kwargs):
            return SimpleNamespace(status_code=status)

    proxy = usage.safe_compute_proxy(SimpleNamespace(compute=Adapter()))
    assert proxy.request("servers/vm", "DELETE").status_code == status


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_safe_proxy_redirected_get_is_not_absence(status):
    class Adapter:
        def request(self, url, method, **kwargs):
            return SimpleNamespace(status_code=status)

    proxy = usage.safe_compute_proxy(SimpleNamespace(compute=Adapter()))
    with pytest.raises(HTTPException) as error:
        proxy.request("servers/vm", "GET")
    assert error.value.status_code == 502


def test_safe_proxy_keeps_native_get_not_found_handling():
    class Adapter:
        def request(self, url, method, **kwargs):
            return SimpleNamespace(status_code=404)

    proxy = usage.safe_compute_proxy(SimpleNamespace(compute=Adapter()))
    assert proxy.request("servers/vm", "GET").status_code == 404


def test_resume_without_schedule_keeps_existing_small_instance_behavior():
    assert usage.require_resume_schedule({"id": "vm", "metadata": {}}, now=START) is None


def test_resume_allows_future_active_schedule():
    metadata = usage.adoption_metadata(now=START)
    assert usage.require_resume_schedule({"id": "vm", "metadata": metadata}, now=START) is None


@pytest.mark.parametrize(
    "state",
    [
        "blocked",
        "complete",
        "unknown",
        "shelve_requested",
        "offload_requested",
        "stop_requested",
        "volume_flags_requested",
        "volumes_ready",
        "delete_requested",
    ],
)
def test_resume_denies_nonactive_or_inflight_schedule(state):
    metadata = usage.adoption_metadata(now=START)
    metadata[P + "state"] = state
    if state in {"stop_requested", "volume_flags_requested", "volumes_ready", "delete_requested"}:
        metadata[P + "action"] = "delete"
    with pytest.raises(HTTPException) as error:
        usage.require_resume_schedule({"id": "vm", "metadata": metadata}, now=START)
    assert error.value.status_code == 409


def test_resume_denies_expired_and_malformed_metadata():
    metadata = usage.adoption_metadata(now=START)
    expiry = datetime.fromisoformat(metadata[P + "expires_at"])
    for invalid in (metadata, {P + "state": "active"}):
        with pytest.raises(HTTPException) as error:
            usage.require_resume_schedule({"id": "vm", "metadata": invalid}, now=expiry)
        assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_completed_instance_can_resume_only_after_reasoned_future_extension(lease_redis):
    cloud = Cloud()
    cloud.server.metadata[P + "state"] = "complete"
    with pytest.raises(HTTPException):
        usage.require_resume_schedule(cloud.server, now=START)
    await usage.extend_schedule(
        cloud,
        cloud.server,
        UsageScheduleExtension(
            revision=revision(cloud), expires_at=datetime(2026, 3, 28, tzinfo=UTC), reason="resume experiment"
        ),
        user_id="u",
        now=START,
        redis=lease_redis,
    )
    assert usage.require_resume_schedule(cloud.server, now=START) is None


def test_final_creation_guard_preserves_frozen_enrollment_and_rejects_expiry():
    metadata = usage.creation_metadata(LARGE, UsageScheduleRequest(), now=START)
    original = dict(metadata)
    assert usage.require_creation_schedule_current(metadata, now=START + timedelta(minutes=3)) is None
    assert metadata == original
    expiry = datetime.fromisoformat(metadata[P + "expires_at"])
    with pytest.raises(HTTPException) as error:
        usage.require_creation_schedule_current(metadata, now=expiry)
    assert error.value.status_code == 422
    assert metadata == original


def test_final_creation_guard_handles_small_unscheduled_and_invalid_enrollment():
    assert usage.require_creation_schedule_current({"unrelated": "keep"}, now=START) is None
    with pytest.raises(HTTPException) as error:
        usage.require_creation_schedule_current({P + "state": "active"}, now=START)
    assert error.value.status_code == 409
    for metadata in (
        usage.adoption_metadata(now=START),
        {**usage.creation_metadata(LARGE, UsageScheduleRequest(), now=START), P + "state": "complete"},
    ):
        with pytest.raises(HTTPException) as error:
            usage.require_creation_schedule_current(metadata, now=START)
        assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_volume_mutation_uses_scheduler_exact_lock_until_native_write_drains(lease_redis):
    cloud = Cloud()
    entered, settle = threading.Event(), threading.Event()

    def mutate_flags():
        entered.set()
        settle.wait(10)

    async def manual_mutation():
        async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis) as lease:
            assert await lease.current()
            await usage.sdk_call(mutate_flags)

    operation = asyncio.create_task(manual_mutation())
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        async with usage.usage_lease(
            cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis
        ) as scheduler:
            assert scheduler is None
        operation.cancel()
        await asyncio.sleep(0)
        async with usage.usage_lease(
            cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis
        ) as scheduler:
            assert scheduler is None
    finally:
        settle.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as scheduler:
        assert scheduler is not None


@pytest.mark.asyncio
async def test_scheduler_flag_proof_lease_blocks_manual_volume_flags(lease_redis):
    cloud = Cloud()
    async with usage.usage_lease(cloud, cloud._afterglow_project_id, cloud.server.id, redis=lease_redis) as scheduler:
        assert scheduler is not None
        with pytest.raises(HTTPException) as error:
            async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis):
                pytest.fail("Manual mutation entered during scheduler ownership")
        assert error.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    [
        "complete",
        "unknown",
        "shelve_requested",
        "offload_requested",
        "stop_requested",
        "volume_flags_requested",
        "volumes_ready",
        "delete_requested",
    ],
)
async def test_volume_mutation_cannot_change_flags_after_operation_marker(lease_redis, state):
    cloud = Cloud()
    cloud.server.metadata[P + "state"] = state
    if state in {"stop_requested", "volume_flags_requested", "volumes_ready", "delete_requested"}:
        cloud.server.metadata[P + "action"] = "delete"
    with pytest.raises(HTTPException) as error:
        async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis):
            pytest.fail("Manual mutation entered after operation marker")
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_authorized_fixed_admin_executor_volume_lock_uses_native_owner(lease_redis):
    cloud = Cloud()
    owner = cloud.server.project_id
    cloud._afterglow_project_id = cloud._afterglow_authenticated_project_id = "fixed-admin-project"
    async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis) as lease:
        assert lease.project_id == owner and lease.instance_id == cloud.server.id
        assert await lease.current()
        cloud._afterglow_project_id = owner
        async with usage.usage_lease(cloud, owner, cloud.server.id, redis=lease_redis) as scheduler:
            assert scheduler is None


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{}, {P + "state": "partial"}])
async def test_volume_mutation_preserves_absent_policy_but_blocks_corruption(lease_redis, metadata):
    cloud = Cloud(metadata=metadata)
    if metadata:
        with pytest.raises(HTTPException) as error:
            async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis):
                pytest.fail("Corrupt policy authorized volume mutation")
        assert error.value.status_code == 409
    else:
        async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis) as lease:
            assert await lease.current()


@pytest.mark.asyncio
async def test_volume_mutation_fresh_identity_and_ownership_are_mandatory(lease_redis):
    cloud = Cloud()
    snapshot = copy.deepcopy(cloud.server)
    cloud.server.project_id = "changed-owner"
    with pytest.raises(HTTPException) as error:
        async with usage.volume_mutation_lease(cloud, snapshot, redis=lease_redis):
            pytest.fail("Changed native ownership authorized mutation")
    assert error.value.status_code == 502
    cloud.server.tenant_id = "conflicting-owner"
    with pytest.raises(HTTPException) as error:
        async with usage.volume_mutation_lease(cloud, cloud.server, redis=lease_redis):
            pytest.fail("Conflicting native ownership authorized mutation")
    assert error.value.status_code == 502
