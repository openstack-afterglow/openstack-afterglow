from __future__ import annotations

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
async def test_vm_delete_previews_and_deletes_only_owned_server_without_force():
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
    }

    class Compute:
        def get_flavor(self, _id, **_kwargs):
            return flavor.copy()

        def get_keypair(self, _name, **_kwargs):
            return keypair

        def servers(self, **_kwargs):
            return list(state["servers"].values())

        def create_server(self, **body):
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
        if state["denied"]:
            raise RuntimeError("quota authority provider-secret")

    async def admit(*args, **kwargs):
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
