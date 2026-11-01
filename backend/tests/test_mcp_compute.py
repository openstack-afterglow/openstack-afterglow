from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.mcp_control_plane.compute import (
    McpComputeError,
    get_project_server,
    list_project_server_interfaces,
    list_project_servers,
    preview_project_server_action,
    preview_project_server_create,
    preview_project_server_delete,
    project_server_overview,
    request_project_server_action,
    request_project_server_create,
    request_project_server_delete,
)
from tests.test_palimpsest_catalog import catalog_db as catalog_db


@pytest.mark.asyncio
async def test_vm_list_filters_provider_query_and_returns_only_safe_owned_fields():
    calls: list[dict[str, object]] = []

    class Compute:
        def servers(self, **kwargs):
            calls.append(kwargs)
            return [
                SimpleNamespace(
                    id="server-a",
                    name="web-a",
                    status="ACTIVE",
                    project_id="project-a",
                    created_at="2026-07-27T00:00:00Z",
                    updated_at="2026-07-27T00:01:00Z",
                    admin_password="secret",
                    console_url="https://private.example.test/console",
                )
            ]

    result = await list_project_servers(SimpleNamespace(compute=Compute()), project_id="project-a", limit=50)

    assert calls == [{"details": True, "project_id": "project-a"}]
    assert result == [
        {
            "id": "server-a",
            "name": "web-a",
            "status": "ACTIVE",
            "created_at": "2026-07-27T00:00:00Z",
            "updated_at": "2026-07-27T00:01:00Z",
        }
    ]


@pytest.mark.asyncio
async def test_vm_list_denies_missing_or_foreign_ownership_proof():
    class Compute:
        def servers(self, **_kwargs):
            return [SimpleNamespace(id="server-b", name="web-b", status="ACTIVE", project_id="project-b")]

    with pytest.raises(McpComputeError, match="ownership"):
        await list_project_servers(SimpleNamespace(compute=Compute()), project_id="project-a", limit=50)


@pytest.mark.asyncio
async def test_vm_get_proves_owner_and_omits_sensitive_provider_fields():
    calls: list[str] = []

    class Compute:
        def get_server(self, server_id):
            calls.append(server_id)
            return SimpleNamespace(
                id=server_id,
                name="web-a",
                status="ACTIVE",
                tenant_id="project-a",
                created="2026-07-27T00:00:00Z",
                updated="2026-07-27T00:01:00Z",
                admin_pass="secret",
                metadata={"credential": "secret"},
            )

    result = await get_project_server(
        SimpleNamespace(compute=Compute()),
        project_id="project-a",
        server_id="12345678-1234-1234-1234-123456789abc",
    )

    assert calls == ["12345678-1234-1234-1234-123456789abc"]
    assert result == {
        "id": "12345678-1234-1234-1234-123456789abc",
        "name": "web-a",
        "status": "ACTIVE",
        "created_at": "2026-07-27T00:00:00Z",
        "updated_at": "2026-07-27T00:01:00Z",
    }


@pytest.mark.asyncio
async def test_vm_action_previews_and_dispatches_only_owned_allowed_state():
    calls: list[tuple[str, object]] = []

    class Compute:
        def get_server(self, server_id):
            calls.append(("get_server", server_id))
            return SimpleNamespace(
                id=server_id,
                name="web-a",
                status="ACTIVE",
                project_id="project-a",
                created_at="2026-07-27T00:00:00Z",
                updated_at="2026-07-27T00:01:00Z",
            )

        def stop_server(self, server_id):
            calls.append(("stop_server", server_id))

    conn = SimpleNamespace(compute=Compute())

    preview = await preview_project_server_action(
        conn,
        project_id="project-a",
        server_id="server-a",
        action="stop",
    )
    result = await request_project_server_action(
        conn,
        project_id="project-a",
        server_id="server-a",
        action="stop",
    )

    assert preview["requested_action"] == "stop"
    assert result["requested_action"] == "stop"
    assert calls == [
        ("get_server", "server-a"),
        ("get_server", "server-a"),
        ("stop_server", "server-a"),
    ]


@pytest.mark.asyncio
async def test_vm_action_rejects_foreign_or_invalid_state_before_provider_call():
    calls: list[str] = []

    class Compute:
        def get_server(self, server_id):
            return SimpleNamespace(id=server_id, name="web-a", status="SHUTOFF", project_id="project-a")

        def stop_server(self, server_id):
            calls.append(server_id)

    with pytest.raises(McpComputeError, match="state"):
        await request_project_server_action(
            SimpleNamespace(compute=Compute()),
            project_id="project-a",
            server_id="server-a",
            action="stop",
        )

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action,status", [("start", "SHUTOFF"), ("unshelve", "SHELVED_OFFLOADED")])
@pytest.mark.parametrize("schedule_state,expired", [("active", True), ("complete", False), ("unknown", False)])
async def test_vm_action_resume_rejects_expired_or_nonactive_schedule_without_native_action(
    action, status, schedule_state, expired
):
    from app.models.instance_usage import UsageScheduleRequest
    from app.services.instance_usage import creation_metadata

    now = datetime.now(UTC).replace(microsecond=0)
    metadata = creation_metadata(
        {"vcpus": 12},
        UsageScheduleRequest(expires_at=now + timedelta(days=7), reason="study"),
        now=now - timedelta(days=2),
    )
    metadata["afterglow_usage_state"] = schedule_state
    if expired:
        metadata["afterglow_usage_expires_at"] = (now - timedelta(seconds=1)).isoformat()
    server = SimpleNamespace(id="server-a", name="scheduled", project_id="project-a", status=status, metadata=metadata)
    calls = []
    conn = SimpleNamespace(
        compute=SimpleNamespace(
            get_server=lambda _id: server,
            start_server=lambda _id: calls.append("start"),
            unshelve_server=lambda _id: calls.append("unshelve"),
        )
    )
    for operation in (preview_project_server_action, request_project_server_action):
        with pytest.raises(McpComputeError, match="[Ee]xtend"):
            await operation(conn, project_id="project-a", server_id="server-a", action=action)
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action,status", [("start", "SHUTOFF"), ("unshelve", "SHELVED_OFFLOADED")])
@pytest.mark.parametrize("scheduled", [False, True])
async def test_vm_action_resume_allows_absent_or_reason_extended_active_future_schedule(action, status, scheduled):
    from app.models.instance_usage import UsageScheduleRequest
    from app.services.instance_usage import creation_metadata

    now = datetime.now(UTC).replace(microsecond=0)
    metadata = {}
    if scheduled:
        metadata = creation_metadata(
            {"vcpus": 12}, UsageScheduleRequest(expires_at=now + timedelta(days=60), reason="extend study"), now=now
        )
        metadata.update(
            {
                "afterglow_usage_extended_at": now.isoformat(),
                "afterglow_usage_extended_by": "user-a",
            }
        )
    server = SimpleNamespace(id="server-a", name="scheduled", project_id="project-a", status=status, metadata=metadata)
    calls = []
    conn = SimpleNamespace(
        compute=SimpleNamespace(
            get_server=lambda _id: server,
            start_server=lambda _id: calls.append("start"),
            unshelve_server=lambda _id: calls.append("unshelve"),
        )
    )
    preview = await preview_project_server_action(conn, project_id="project-a", server_id="server-a", action=action)
    result = await request_project_server_action(conn, project_id="project-a", server_id="server-a", action=action)
    assert preview["requested_action"] == result["requested_action"] == action
    assert calls == [action]


@pytest.mark.asyncio
@pytest.mark.parametrize("action,status", [("start", "SHUTOFF"), ("unshelve", "SHELVED_OFFLOADED")])
async def test_vm_action_resume_revalidates_schedule_after_preview_before_dispatch(action, status):
    from app.models.instance_usage import UsageScheduleRequest
    from app.services.instance_usage import creation_metadata

    now = datetime.now(UTC).replace(microsecond=0)
    metadata = creation_metadata(
        {"vcpus": 12},
        UsageScheduleRequest(expires_at=now + timedelta(days=7), reason="study"),
        now=now - timedelta(days=2),
    )
    server = SimpleNamespace(id="server-a", name="scheduled", project_id="project-a", status=status, metadata=metadata)
    calls = []
    conn = SimpleNamespace(
        compute=SimpleNamespace(
            get_server=lambda _id: server,
            start_server=lambda _id: calls.append("start"),
            unshelve_server=lambda _id: calls.append("unshelve"),
        )
    )
    await preview_project_server_action(conn, project_id="project-a", server_id="server-a", action=action)
    metadata["afterglow_usage_expires_at"] = (now - timedelta(seconds=1)).isoformat()
    with pytest.raises(McpComputeError, match="extend"):
        await request_project_server_action(conn, project_id="project-a", server_id="server-a", action=action)
    assert calls == []


@pytest.mark.asyncio
async def test_cloud_overview_counts_only_exact_project_provider_records():
    calls: list[dict[str, object]] = []

    class Compute:
        def servers(self, **kwargs):
            calls.append(kwargs)
            return [
                SimpleNamespace(id="server-active", name="a", status="ACTIVE", project_id="project-a"),
                SimpleNamespace(id="server-off", name="b", status="SHUTOFF", project_id="project-a"),
                SimpleNamespace(id="server-error", name="c", status="ERROR", project_id="project-a"),
            ]

    result = await project_server_overview(SimpleNamespace(compute=Compute()), project_id="project-a")

    assert calls == [{"details": True, "project_id": "project-a"}]
    assert result == {"total": 3, "active": 1, "shutoff": 1, "error": 1}


@pytest.mark.asyncio
async def test_vm_delete_previews_and_deletes_only_owned_server_without_force(catalog_db):
    calls: list[tuple[str, object]] = []

    class Compute:
        def get_server(self, server_id):
            calls.append(("get_server", server_id))
            return SimpleNamespace(
                id=server_id,
                name="web-a",
                status="SHUTOFF",
                project_id="project-a",
                created_at="2026-07-27T00:00:00Z",
                updated_at="2026-07-27T00:01:00Z",
            )

        def delete_server(self, server_id, **kwargs):
            calls.append(("delete_server", (server_id, kwargs)))

    conn = SimpleNamespace(compute=Compute())

    preview = await preview_project_server_delete(conn, project_id="project-a", server_id="server-a")
    result = await request_project_server_delete(conn, project_id="project-a", server_id="server-a")

    assert preview["requested_action"] == "delete"
    assert result["requested_action"] == "delete"
    assert calls == [
        ("get_server", "server-a"),
        ("get_server", "server-a"),
        ("delete_server", ("server-a", {"ignore_missing": False, "force": False})),
    ]


@pytest.mark.asyncio
async def test_vm_interfaces_require_owned_server_and_each_attached_port():
    calls: list[tuple[str, object]] = []

    class Compute:
        def get_server(self, server_id):
            calls.append(("get_server", server_id))
            return SimpleNamespace(id=server_id, name="web-a", status="ACTIVE", project_id="project-a")

        def server_interfaces(self, server_id):
            calls.append(("server_interfaces", server_id))
            return [SimpleNamespace(port_id="port-a", mac_addr="fa:16:3e:00:00:01")]

    class Network:
        def get_port(self, port_id):
            calls.append(("get_port", port_id))
            return SimpleNamespace(id=port_id, project_id="project-a", fixed_ips=[{"ip_address": "10.0.0.5"}])

    result = await list_project_server_interfaces(
        SimpleNamespace(compute=Compute(), network=Network()),
        project_id="project-a",
        server_id="server-a",
        limit=50,
    )

    assert result == [{"port_id": "port-a", "mac_address": "fa:16:3e:00:00:01"}]
    assert calls == [
        ("get_server", "server-a"),
        ("server_interfaces", "server-a"),
        ("get_port", "port-a"),
    ]


@pytest.mark.asyncio
async def test_vm_interfaces_reject_foreign_attached_port():
    calls: list[str] = []

    class Compute:
        def get_server(self, server_id):
            return SimpleNamespace(id=server_id, name="web-a", status="ACTIVE", project_id="project-a")

        def server_interfaces(self, _server_id):
            return [SimpleNamespace(port_id="port-a", mac_addr="fa:16:3e:00:00:01")]

    class Network:
        def get_port(self, port_id):
            calls.append(port_id)
            return SimpleNamespace(id=port_id, project_id="project-b")

    with pytest.raises(McpComputeError, match="port ownership"):
        await list_project_server_interfaces(
            SimpleNamespace(compute=Compute(), network=Network()),
            project_id="project-a",
            server_id="server-a",
            limit=50,
        )

    assert calls == ["port-a"]


@pytest.fixture
def create_cloud(monkeypatch):
    from app.services import resource_policy_store
    from app.services.mcp_control_plane import compute

    image = {
        "id": "image-a",
        "owner": "project-a",
        "visibility": "private",
        "status": "active",
        "min_disk": 10,
        "min_ram": 2048,
    }
    flavor = {"id": "1", "name": "cpu.nano", "vcpus": 2, "ram": 4096, "disk": 0, "extra_specs": {}}
    network = {
        "id": "network-a",
        "project_id": "project-a",
        "status": "ACTIVE",
        "is_admin_state_up": True,
        "is_shared": False,
    }
    keypair = {"name": "my-key", "user_id": "user-a", "private_key": "provider-secret"}
    state = {
        "servers": {},
        "volumes": [],
        "denied": False,
        "reservations": set(),
        "after_admission": None,
        "created_owner": None,
        "get_override": None,
        "admissions": 0,
        "eligibility_checks": 0,
        "create_bodies": [],
    }

    class Compute:
        def get_flavor(self, _id, **_kwargs):
            return flavor.copy()

        def get_keypair(self, _name, **_kwargs):
            return keypair

        def servers(self, **_kwargs):
            return list(state["servers"].values())

        def create_server(self, **body):
            state["create_bodies"].append(body)
            mapping = body["block_device_mapping"][0]
            state["volumes"].append(
                {
                    "source_image": mapping["uuid"],
                    "size": mapping["volume_size"],
                    "delete_with_server": mapping["delete_on_termination"],
                }
            )
            state["servers"]["server-new"] = {
                "id": "server-new",
                "project_id": "project-a",
                "name": body["name"],
                "status": "BUILD",
                "created": "2026-10-11T00:00:00Z",
                "updated": None,
                "adminPass": "provider-secret",
                "metadata": {"secret": "provider-secret"},
            }
            return {
                "id": "server-new",
                "adminPass": "provider-secret",
                **({"project_id": state["created_owner"]} if state["created_owner"] else {}),
            }

        def get_server(self, _id):
            if state["get_override"] is not None:
                return state["get_override"]
            return state["servers"].get(_id)

    async def eligible(*_args, **_kwargs):
        state["eligibility_checks"] += 1
        if state["denied"]:
            raise RuntimeError("quota authority provider-secret")

    async def admit(*args, **kwargs):
        state["admissions"] += 1
        await eligible(*args, **kwargs)
        state["reservations"].add("gpu-reservation")
        if state["after_admission"]:
            state["after_admission"]()
        return SimpleNamespace(reservation_id="gpu-reservation")

    async def release(admission):
        state["reservations"].discard(admission.reservation_id)

    async def zones(**_kwargs):
        return {"nova.default_compute_availability_zone": "nova"}

    monkeypatch.setattr(compute.flavor_eligibility, "require_flavor_eligible", eligible)
    monkeypatch.setattr(compute.flavor_eligibility, "admit_flavor", admit)
    monkeypatch.setattr(compute.flavor_eligibility, "release_admission", release)
    monkeypatch.setattr(resource_policy_store, "resolve_policies", zones)
    conn = SimpleNamespace(
        compute=Compute(),
        image=SimpleNamespace(get_image=lambda _id: image),
        network=SimpleNamespace(get_network=lambda _id: network),
    )
    arguments = dict(
        project_id="project-a",
        user_id="user-a",
        name="my-vm",
        image_id="image-a",
        flavor_id="1",
        network_id="network-a",
        boot_volume_size_gb=20,
        key_name="my-key",
    )
    return conn, arguments, state, image, flavor, network, keypair


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_with_server", [False, True])
async def test_vm_create_accepts_one_owned_volume_boot_without_exposing_credentials(create_cloud, delete_with_server):
    conn, arguments, state, *_ = create_cloud
    arguments["delete_boot_volume_on_termination"] = delete_with_server
    preview = await preview_project_server_create(conn, **arguments)
    assert preview["boot_volume_size_gb"] == 20
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()
    result = await request_project_server_create(conn, **arguments)
    assert result == {
        "id": "server-new",
        "name": "my-vm",
        "status": "BUILD",
        "created_at": "2026-10-11T00:00:00Z",
        "updated_at": None,
        "requested_action": "create",
    }
    assert state["volumes"] == [{"source_image": "image-a", "size": 20, "delete_with_server": delete_with_server}]
    assert state["reservations"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capacity",
    [
        {"vcpus": 12},
        {"ram": 65536},
        {"extra_specs": {"resources:VGPU": "1"}},
        {"extra_specs": {"afterglow:usage_schedule_required": "true"}},
        {"vcpus": 12, "extra_specs": {"afterglow:usage_schedule_required": "false"}},
    ],
)
async def test_vm_create_required_schedule_rejected_before_quota_or_compute_mutation(create_cloud, capacity):
    conn, arguments, state, _, flavor, *_ = create_cloud
    flavor.update(capacity)
    for operation in (preview_project_server_create, request_project_server_create):
        with pytest.raises(McpComputeError):
            await operation(conn, **arguments)
    assert state["admissions"] == state["eligibility_checks"] == 0
    assert state["create_bodies"] == [] and state["servers"] == {} and state["volumes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "schedule",
    [
        {},
        {"expires_at": "2000-01-01T00:00:00Z"},
        {"expires_at": "2099-01-01T00:00:00Z", "reason": "   "},
        {"expires_at": "2099-01-01T00:00:00Z", "reason": "study", "delete_volumes": True},
        {"expires_at": "2099-01-01T00:00:00Z", "reason": "study", "expiry_action": "delete", "delete_volumes": "true"},
        {"expires_at": "2099-01-01T00:00:00Z", "reason": "bad\nreason"},
        {"expires_at": "2099-01-01T00:00:00", "reason": "study"},
    ],
)
async def test_vm_create_invalid_schedule_and_consent_never_reaches_quota_or_compute_mutation(create_cloud, schedule):
    conn, arguments, state, *_ = create_cloud
    for operation in (preview_project_server_create, request_project_server_create):
        with pytest.raises(McpComputeError):
            await operation(conn, **arguments, usage_schedule=schedule)
    assert state["admissions"] == state["eligibility_checks"] == 0
    assert state["create_bodies"] == [] and state["servers"] == {} and state["volumes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("action,delete_volumes", [("shelve", False), ("delete", False), ("delete", True)])
async def test_vm_create_first_native_create_contains_validated_schedule(create_cloud, action, delete_volumes):
    from app.models.instance_usage import UsageScheduleRequest
    from app.services.instance_usage import parse_schedule

    conn, arguments, state, _, flavor, *_ = create_cloud
    flavor["vcpus"] = 12
    requested = UsageScheduleRequest(
        expires_at=datetime.now(UTC) + timedelta(days=7),
        expiry_action=action,
        delete_volumes=delete_volumes,
        reason="scheduled study",
    ).model_dump(mode="json")
    preview = await preview_project_server_create(conn, **arguments, usage_schedule=requested)
    assert state["create_bodies"] == []
    assert preview["usage_schedule"] == requested
    result = await request_project_server_create(conn, **arguments, usage_schedule=requested)
    assert len(state["create_bodies"]) == 1
    schedule = parse_schedule({"id": result["id"], "metadata": state["create_bodies"][0]["metadata"]})
    assert datetime.fromisoformat(schedule.expires_at) == datetime.fromisoformat(requested["expires_at"])
    assert schedule.expiry_action == action and schedule.delete_volumes is delete_volumes
    assert schedule.reason == "scheduled study" and schedule.source == "created" and schedule.state == "active"
    assert state["reservations"] == set()


@pytest.mark.asyncio
async def test_vm_create_rechecks_expiry_after_quota_before_first_native_create(create_cloud, monkeypatch):
    from app.services import instance_usage

    conn, arguments, state, *_ = create_cloud
    now = datetime(2035, 1, 1, tzinfo=UTC)
    clock = [now]
    monkeypatch.setattr(instance_usage, "_clock", lambda _now=None: clock[0])
    state["after_admission"] = lambda: clock.__setitem__(0, now + timedelta(days=2))
    with pytest.raises(McpComputeError):
        await request_project_server_create(
            conn, **arguments, usage_schedule={"expires_at": (now + timedelta(days=1)).isoformat()}
        )
    assert state["admissions"] == 1 and state["reservations"] == set()
    assert state["create_bodies"] == [] and state["servers"] == {} and state["volumes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("name", " "),
        ("name", "bad/name"),
        ("boot_volume_size_gb", 0),
        ("boot_volume_size_gb", 16385),
        ("boot_volume_size_gb", True),
        ("boot_volume_size_gb", "20"),
        ("availability_zone", "nova:host"),
        ("availability_zone", " "),
        ("delete_boot_volume_on_termination", "true"),
    ],
)
async def test_vm_create_rejects_invalid_creation_input_without_resources(create_cloud, field, value):
    conn, arguments, state, *_ = create_cloud
    arguments[field] = value
    with pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency,changes",
    [
        ("image", {"status": "queued"}),
        ("image", {"owner": "foreign", "visibility": "private"}),
        ("image", {"min_disk": 21}),
        ("image", {"min_ram": 8192}),
        ("image", {"id": "different"}),
        ("flavor", {"id": "different"}),
        ("flavor", {"extra_specs": None}),
        ("network", {"project_id": "foreign"}),
        ("network", {"status": "DOWN"}),
        ("keypair", {"user_id": "foreign"}),
        ("keypair", {"user_id": None}),
    ],
)
async def test_vm_create_rejects_ineligible_or_foreign_dependencies(create_cloud, dependency, changes):
    conn, arguments, state, image, flavor, network, keypair = create_cloud
    {"image": image, "flavor": flavor, "network": network, "keypair": keypair}[dependency].update(changes)
    with pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["public", "community", "shared"])
async def test_vm_create_accepts_native_visible_images_and_shared_networks(create_cloud, visibility):
    conn, arguments, state, image, _, network, _ = create_cloud
    image.update(owner="image-owner", visibility=visibility)
    conn.image.get_member = lambda _member, _image: {"member_id": "project-a", "status": "accepted"}
    network.update(project_id="network-owner", is_shared=True)
    result = await request_project_server_create(conn, **arguments)
    assert result["status"] == "BUILD" and state["servers"][result["id"]]["project_id"] == "project-a"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "member", [{"member_id": "foreign", "status": "accepted"}, {"member_id": "project-a", "status": "pending"}, None]
)
async def test_vm_create_requires_accepted_exact_project_image_membership(create_cloud, member):
    conn, arguments, state, image, *_ = create_cloud
    image.update(owner="image-owner", visibility="shared")
    conn.image.get_member = lambda _member, _image: member
    with pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert state["servers"] == {} and state["volumes"] == []


@pytest.mark.asyncio
async def test_vm_create_preserves_quota_capacity_failure_before_native_write(create_cloud):
    conn, arguments, state, *_ = create_cloud
    state["denied"] = True
    for action in (preview_project_server_create, request_project_server_create):
        with pytest.raises(McpComputeError) as failure:
            await action(conn, **arguments)
        assert "provider-secret" not in str(failure.value)
    assert state["servers"] == {} and state["volumes"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dependency,changes",
    [
        ("image", {"status": "deleted"}),
        ("flavor", {"ram": 8192}),
        ("flavor", {"vcpus": 12}),
        ("flavor", {"extra_specs": {"afterglow:usage_schedule_required": "true"}}),
        ("network", {"project_id": "foreign"}),
        ("keypair", {"user_id": "foreign"}),
    ],
)
async def test_vm_create_revalidates_dependencies_after_admission(create_cloud, dependency, changes):
    conn, arguments, state, image, flavor, network, keypair = create_cloud
    state["after_admission"] = lambda: {"image": image, "flavor": flavor, "network": network, "keypair": keypair}[
        dependency
    ].update(changes)
    with pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["create-owner", "get-owner", "get-id", "get-missing-owner"])
async def test_vm_create_output_failure_never_resends_or_deletes_created_resources(create_cloud, failure):
    conn, arguments, state, *_ = create_cloud
    if failure == "create-owner":
        state["created_owner"] = "foreign"
    else:
        state["get_override"] = {
            "id": "other-id" if failure == "get-id" else "server-new",
            "name": "my-vm",
            "status": "BUILD",
            "project_id": "foreign"
            if failure == "get-owner"
            else None
            if failure == "get-missing-owner"
            else "project-a",
        }
    with pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert len(state["servers"]) == 1 and len(state["volumes"]) == 1 and state["reservations"] == set()


@pytest.mark.asyncio
async def test_vm_create_deadline_expiration_prevents_late_send_and_releases_admission(create_cloud, monkeypatch):
    from app.services.mcp_control_plane import sdk

    conn, arguments, state, *_ = create_cloud
    clock = [100.0]
    monkeypatch.setattr(sdk.time, "monotonic", lambda: clock[0])
    state["after_admission"] = lambda: clock.__setitem__(0, 200.0)
    with sdk.sdk_deadline(1), pytest.raises(McpComputeError):
        await request_project_server_create(conn, **arguments)
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()


@pytest.mark.asyncio
async def test_vm_create_cancellation_drains_policy_and_releases_late_gpu_reservation(create_cloud, monkeypatch):
    import asyncio

    from app.services.mcp_control_plane import compute

    conn, arguments, state, *_ = create_cloud
    started, finish = asyncio.Event(), asyncio.Event()

    async def delayed_admission(*_args, **_kwargs):
        started.set()
        await finish.wait()
        state["reservations"].add("late-gpu")
        return SimpleNamespace(reservation_id="late-gpu")

    monkeypatch.setattr(compute.flavor_eligibility, "admit_flavor", delayed_admission)
    task = asyncio.create_task(request_project_server_create(conn, **arguments))
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    await asyncio.sleep(0)
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state["servers"] == {} and state["volumes"] == [] and state["reservations"] == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_owner", [None, "foreign-user", "user-a"])
async def test_vm_create_native_sdk_keypair_requires_provider_owner_not_seeded_attribute(create_cloud, provider_owner):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from keystoneauth1.noauth import NoAuth
    from keystoneauth1.session import Session
    from openstack.connection import Connection

    conn, arguments, state, *_ = create_cloud

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            key = {"name": "my-key", "public_key": "synthetic-public"}
            if provider_owner is not None:
                key["user_id"] = provider_owner
            if "/os-keypairs/" in self.path:
                payload = {"keypair": key}
            else:
                payload = {
                    "version": {
                        "id": "v2.1",
                        "status": "CURRENT",
                        "version": "2.96",
                        "min_version": "2.1",
                        "links": [{"rel": "self", "href": f"http://127.0.0.1:{self.server.server_port}/v2.1/"}],
                    }
                }
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    native = Connection(
        session=Session(auth=NoAuth(), timeout=2),
        compute_endpoint_override=f"http://127.0.0.1:{server.server_port}/v2.1",
        compute_api_version="2",
        compute_default_microversion="2.10",
    )
    try:
        conn.compute.get_keypair = native.compute.get_keypair
        if provider_owner != "user-a":
            with pytest.raises(McpComputeError, match="keypair ownership"):
                await request_project_server_create(conn, **arguments)
            assert state["servers"] == {} and state["volumes"] == []
        else:
            result = await request_project_server_create(conn, **arguments)
            assert result["status"] == "BUILD" and state["servers"][result["id"]]["project_id"] == "project-a"
    finally:
        native.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
