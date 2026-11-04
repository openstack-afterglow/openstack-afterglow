"""HTTP usage contracts execute real metadata validation and revision updates."""

from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.compute import instances, usage_schedules
from app.api.identity import admin_instances
from app.models.compute import FlavorInfo
from app.models.instance_usage_governance import InstanceUsageExtensionRequest, InstanceUsagePolicy
from app.services import instance_usage as usage
from app.services import instance_usage_governance as governance
from tests.conftest import make_token_info

PROJECT = "test-project-123"
INSTANCE = "usage-instance"
NOW = datetime.now(UTC)
ROUTES = ["/api/v1/instances", "/api/v1/instances/async", "/api/v1/admin/instances/async"]


@pytest.fixture
async def governance_store(monkeypatch):
    """Real SQL intent transactions; native authority/graph transport is isolated."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync: InstanceUsagePolicy.metadata.create_all(
                sync, tables=[InstanceUsagePolicy.__table__, InstanceUsageExtensionRequest.__table__]
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def sessions():
        async with factory() as session:
            yield session

    @asynccontextmanager
    async def graph():
        yield SimpleNamespace(assert_owned=AsyncMock())

    monkeypatch.setattr(governance, "session_scope", sessions)
    monkeypatch.setattr(governance, "governance_lock", graph)
    monkeypatch.setattr(governance, "cloud_id", AsyncMock(return_value="c" * 64))
    monkeypatch.setattr(governance, "project_domain", AsyncMock(return_value="default"))
    monkeypatch.setattr(
        governance,
        "live_access",
        AsyncMock(
            return_value={
                "manager": False,
                "write": True,
                "review": False,
                "read": True,
            }
        ),
    )
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
async def usage_cloud(monkeypatch, mock_conn, governance_store):
    native = SimpleNamespace(
        id=INSTANCE,
        project_id=PROJECT,
        tenant_id=PROJECT,
        name="usage-vm",
        status="ACTIVE",
        metadata={"preserve": "unrelated"},
    )
    native.metadata.update(usage.adoption_metadata(now=NOW))

    def get_server(server_id):
        from openstack.exceptions import ResourceNotFound

        if server_id != INSTANCE:
            raise ResourceNotFound()
        return deepcopy(native)

    def set_metadata(server_id, **fields):
        assert server_id == INSTANCE
        native.metadata.update(fields)
        return deepcopy(native)

    compute = SimpleNamespace(
        get_server=get_server,
        set_server_metadata=MagicMock(side_effect=set_metadata),
        servers=lambda **_kwargs: [deepcopy(native)],
    )
    mock_conn.compute = compute
    mock_conn._afterglow_authenticated_project_id = PROJECT
    mock_conn.endpoint_for.return_value = "http://127.0.0.1/v3"
    monkeypatch.setattr(usage, "safe_compute_proxy", lambda conn: conn.compute)
    monkeypatch.setattr(usage_schedules, "rec", AsyncMock())
    monkeypatch.setattr(usage_schedules, "invalidate", AsyncMock())
    monkeypatch.setattr(admin_instances, "_make_admin_conn", lambda *_args: mock_conn)

    def fixed_operator():
        access = SimpleNamespace(
            project_scoped=True,
            system_scoped=False,
            project_id="native-admin-project",
            user_id="native-service-user",
            auth_token="native-service-token",
            is_admin_project=True,
            role_names=["admin"],
            _data={"token": {"is_admin_project": True}},
        )
        return SimpleNamespace(
            compute=compute,
            endpoint_for=mock_conn.endpoint_for,
            close=lambda: None,
            session=SimpleNamespace(auth=SimpleNamespace(get_access=lambda _session: access)),
        )

    monkeypatch.setattr(governance.keystone, "get_admin_project_connection", fixed_operator)
    from app.main import app

    app.dependency_overrides[usage_schedules.get_governance_conn] = lambda: mock_conn
    try:
        yield native
    finally:
        app.dependency_overrides.pop(usage_schedules.get_governance_conn, None)


@pytest.mark.asyncio
async def test_schedule_roundtrip_and_reasoned_extension(client, mock_conn, usage_cloud):
    first = await client.get(f"/api/v1/instances/{INSTANCE}/usage-schedule")
    assert first.status_code == 200
    assert first.headers["cache-control"] == "no-store"
    current = first.json()
    new_expiry = datetime.fromisoformat(current["expires_at"]) + timedelta(days=10)
    extended = await client.post(
        f"/api/v1/instances/{INSTANCE}/usage-schedule/extend",
        json={
            "expires_at": new_expiry.isoformat(),
            "reason": "모델 평가가 진행 중입니다",
            "revision": current["revision"],
        },
    )
    assert extended.status_code == 200
    assert datetime.fromisoformat(extended.json()["expires_at"]) == new_expiry
    assert extended.json()["extended_by"] == "test-user-123"
    assert usage_cloud.metadata["preserve"] == "unrelated"
    # A new API read derives the date from Nova, not a request echo or SQL shadow.
    again = await client.get(f"/api/v1/instances/{INSTANCE}/usage-schedule")
    assert again.json()["expires_at"] == extended.json()["expires_at"]
    stale = await client.post(
        f"/api/v1/instances/{INSTANCE}/usage-schedule/extend",
        json={
            "expires_at": (new_expiry + timedelta(days=1)).isoformat(),
            "reason": "stale",
            "revision": current["revision"],
        },
    )
    assert stale.status_code == 409
    assert usage.parse_schedule(usage_cloud).expires_at == extended.json()["expires_at"]


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["", "   ", "\n"])
async def test_extension_without_reason_leaves_native_schedule_unchanged(client, mock_conn, usage_cloud, reason):
    before = deepcopy(usage_cloud.metadata)
    current = usage.parse_schedule(usage_cloud)
    response = await client.post(
        f"/api/v1/instances/{INSTANCE}/usage-schedule/extend",
        json={"expires_at": (NOW + timedelta(days=90)).isoformat(), "reason": reason, "revision": current.revision},
    )
    assert response.status_code == 422
    assert usage_cloud.metadata == before
    mock_conn.compute.set_server_metadata.assert_not_called()


@pytest.mark.asyncio
async def test_destructive_setting_requires_delete_action_and_defaults_to_keep(client, usage_cloud):
    schedule = usage.parse_schedule(usage_cloud)
    rejected = await client.put(
        f"/api/v1/instances/{INSTANCE}/usage-schedule",
        json={"revision": schedule.revision, "expiry_action": "shelve", "delete_volumes": True},
    )
    assert rejected.status_code == 422
    accepted = await client.put(
        f"/api/v1/instances/{INSTANCE}/usage-schedule",
        json={"revision": schedule.revision, "expiry_action": "delete"},
    )
    assert accepted.status_code == 200
    saved = usage.parse_schedule(usage_cloud)
    assert saved.expiry_action == "delete" and saved.delete_volumes is False


@pytest.mark.asyncio
async def test_project_scope_cannot_read_or_update_foreign_schedule(client, usage_cloud):
    usage_cloud.project_id = usage_cloud.tenant_id = "other-project"
    for method in ("get", "put"):
        kwargs = {} if method == "get" else {"json": {"revision": usage.parse_schedule(usage_cloud).revision}}
        response = await getattr(client, method)(f"/api/v1/instances/{INSTANCE}/usage-schedule", **kwargs)
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_keeps_malformed_metadata_as_explicit_error(client, usage_cloud):
    usage_cloud.metadata.pop("afterglow_usage_expires_at")
    response = await client.get("/api/v1/instances/usage-schedules")
    assert response.status_code == 200
    assert response.json()["schedules"] == []
    assert response.json()["errors"][0]["instance_id"] == INSTANCE
    detail = await client.get(f"/api/v1/instances/{INSTANCE}/usage-schedule")
    assert detail.status_code == 409


@pytest.mark.asyncio
async def test_committed_dispatch_cannot_be_extended(client, usage_cloud):
    usage_cloud.metadata["afterglow_usage_state"] = "shelve_requested"
    schedule = usage.parse_schedule(usage_cloud)
    response = await client.post(
        f"/api/v1/instances/{INSTANCE}/usage-schedule/extend",
        json={"expires_at": (NOW + timedelta(days=90)).isoformat(), "reason": "late", "revision": schedule.revision},
    )
    assert response.status_code == 409
    assert usage.parse_schedule(usage_cloud).state == "shelve_requested"


@pytest.mark.asyncio
async def test_reader_can_see_schedule_but_cannot_change_it(client, usage_cloud):
    from app.api.deps import get_token_info
    from app.main import app

    app.dependency_overrides[get_token_info] = lambda: make_token_info(roles=["reader"])
    assert (await client.get(f"/api/v1/instances/{INSTANCE}/usage-schedule")).status_code == 200
    response = await client.put(
        f"/api/v1/instances/{INSTANCE}/usage-schedule",
        json={"revision": usage.parse_schedule(usage_cloud).revision, "expiry_action": "delete"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_schedule_is_derived_from_observed_owner(admin_client, usage_cloud):
    first = await admin_client.get(f"/api/v1/admin/instances/{INSTANCE}/usage-schedule")
    assert first.status_code == 200
    response = await admin_client.put(
        f"/api/v1/admin/instances/{INSTANCE}/usage-schedule",
        json={"revision": first.json()["revision"], "expiry_action": "delete", "delete_volumes": True},
    )
    assert response.status_code == 200
    assert usage.parse_schedule(usage_cloud).delete_volumes is True


@pytest.mark.asyncio
async def test_member_cannot_access_global_schedule_surface(client, usage_cloud):
    response = await client.get(f"/api/v1/admin/instances/{INSTANCE}/usage-schedule")
    assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize(
    "flavor",
    [
        FlavorInfo(id="scheduled", name="cpu.large", vcpus=12, ram=4096, disk=0),
        FlavorInfo(id="scheduled", name="memory.large", vcpus=2, ram=65536, disk=0),
        FlavorInfo(id="scheduled", name="gpu.small", vcpus=2, ram=4096, disk=0),
    ],
)
async def test_required_schedule_rejected_before_allocation(admin_client, monkeypatch, mock_conn, route, flavor):
    monkeypatch.setattr(instances.nova, "list_flavors", lambda _conn: [flavor])
    monkeypatch.setattr(admin_instances, "_make_admin_conn", lambda *_args: mock_conn)
    monkeypatch.setattr(instances, "preflight_password", lambda *_args: SimpleNamespace(windows=False))
    monkeypatch.setattr(admin_instances, "preflight_password", lambda *_args: SimpleNamespace(windows=False))
    monkeypatch.setattr("app.services.instance_names.ensure_unique_instance_name", lambda *_args: "scheduled-vm")
    placement = AsyncMock()
    monkeypatch.setattr(instances, "_resolve_create_placement", placement)
    allocation = MagicMock()
    monkeypatch.setattr(instances.cinder, "create_volume_from_image", allocation)
    body = {"name": "scheduled-vm", "flavor_id": flavor.id, "image_id": "image", "network_id": "network"}
    if "/admin/" in route:
        body["project_id"] = PROJECT
    response = await admin_client.post(route, json=body)
    assert response.status_code == 422
    placement.assert_not_awaited()
    allocation.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "delete", "patch"])
async def test_manual_volume_change_cannot_pass_scheduler_lease_or_pending_marker(
    client, mock_conn, usage_cloud, monkeypatch, method
):
    attach, detach, flag = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr(instances.nova, "attach_volume", attach)
    monkeypatch.setattr(instances.nova, "detach_volume", detach)
    monkeypatch.setattr(instances.nova, "update_volume_attachment_delete_flag", flag)
    path = f"/api/v1/instances/{INSTANCE}/volumes"
    if method == "post":
        fields = {"json": {"volume_id": "volume-one"}}
    else:
        path += "/volume-one"
        fields = {"json": {"delete_on_termination": True}} if method == "patch" else {}
    async with usage.usage_lease(mock_conn, PROJECT, INSTANCE) as lease:
        assert await lease.current()
        response = await getattr(client, method)(path, **fields)
        assert response.status_code == 409
    usage_cloud.metadata["afterglow_usage_action"] = "delete"
    usage_cloud.metadata["afterglow_usage_state"] = "delete_requested"
    response = await getattr(client, method)(path, **fields)
    assert response.status_code == 409
    attach.assert_not_called()
    detach.assert_not_called()
    flag.assert_not_called()
