from __future__ import annotations

import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from requests import Response
from requests.adapters import BaseAdapter
from starlette.websockets import WebSocketDisconnect

from app.api.cloud_shell import router as cloud_shell_router
from app.api.deps import get_token_info
from app.config import Settings
from app.services import cloud_shell, zun

PROJECT_ID = "11111111-1111-4111-8111-111111111111"
SERVICE_PROJECT_ID = "22222222-2222-4222-8222-222222222222"


def cloud_settings(**overrides) -> Settings:
    values = {
        "service_zun_enabled": True,
        "service_cloud_shell_enabled": True,
        "cloud_shell_service_project_id": SERVICE_PROJECT_ID,
        "cloud_shell_image": "registry.example.test/cloud-shell:dev",
        "cloud_shell_network_id": "network-id",
        "cloud_shell_security_group": "egress-only",
        "cloud_shell_auth_url": "http://127.0.0.1:5000/v3",
        "cloud_shell_zun_websocket_origin": "ws://127.0.0.1:6784",
        "os_service_project_id": PROJECT_ID,
        "secret_key": "test-cloud-shell-secret-that-is-long-enough",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def token_info() -> dict:
    return {
        "token": "caller-token",
        "user_id": "user-a",
        "username": "alice",
        "project_id": PROJECT_ID,
        "project_name": "project-a",
        "roles": ["member"],
    }


def scoped_token() -> dict:
    return {
        "token": "rescoped-token",
        "user_id": "user-a",
        "username": "alice",
        "project_id": PROJECT_ID,
        "project_name": "project-a",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "roles": ["member"],
    }


def test_enabled_cloud_shell_requires_dedicated_service_project():
    with pytest.raises(ValueError, match="dedicated service project"):
        cloud_settings(cloud_shell_service_project_id=PROJECT_ID)


def test_enabled_cloud_shell_requires_zun_and_bounded_resources():
    with pytest.raises(ValueError, match="services.zun=true"):
        cloud_settings(service_zun_enabled=False)
    with pytest.raises(ValueError, match="memory_mib"):
        cloud_settings(cloud_shell_memory_mib=128)
    with pytest.raises(ValueError, match="max_session_seconds"):
        cloud_settings(cloud_shell_idle_timeout_seconds=1200, cloud_shell_max_session_seconds=600)


@pytest.mark.asyncio
async def test_ticket_reservation_is_user_global_atomic_and_single_use():
    settings = cloud_settings()
    with (
        patch("app.services.cloud_shell.get_settings", return_value=settings),
        patch("app.services.cloud_shell.keystone.validate_token", return_value=scoped_token()),
    ):
        issued = await cloud_shell.issue_cloud_shell_ticket(token_info())
        assert set(issued) == {"ticket", "websocket_path", "expires_at"}
        assert "rescoped-token" not in json.dumps(issued)
        with pytest.raises(cloud_shell.CloudShellConflict, match="already active or pending"):
            await cloud_shell.issue_cloud_shell_ticket(token_info())

        lease = await cloud_shell.consume_cloud_shell_ticket(issued["ticket"])
        assert lease.token == "rescoped-token"
        assert lease.project_id == PROJECT_ID
        with pytest.raises(cloud_shell.CloudShellUnauthorized, match="missing or expired"):
            await cloud_shell.consume_cloud_shell_ticket(issued["ticket"])

        await cloud_shell.abandon_lease(lease)
        replacement = await cloud_shell.issue_cloud_shell_ticket(token_info())
        assert replacement["ticket"] != issued["ticket"]


@pytest.mark.asyncio
async def test_ticket_reservation_blocks_same_user_in_another_project():
    other_project = "33333333-3333-4333-8333-333333333333"

    def validate(_token, project_id):
        return {**scoped_token(), "project_id": project_id, "project_name": project_id}

    first = token_info()
    second = {**token_info(), "project_id": other_project, "project_name": "project-b"}
    with (
        patch("app.services.cloud_shell.get_settings", return_value=cloud_settings()),
        patch("app.services.cloud_shell.keystone.validate_token", side_effect=validate),
    ):
        issued = await cloud_shell.issue_cloud_shell_ticket(first)
        with pytest.raises(cloud_shell.CloudShellConflict, match="already active or pending"):
            await cloud_shell.issue_cloud_shell_ticket(second)
        lease = await cloud_shell.consume_cloud_shell_ticket(issued["ticket"])
        await cloud_shell.abandon_lease(lease)


@pytest.mark.asyncio
async def test_ticket_rejects_scope_mismatch_before_reservation():
    invalid = {**scoped_token(), "project_id": "other-project"}
    with (
        patch("app.services.cloud_shell.get_settings", return_value=cloud_settings()),
        patch("app.services.cloud_shell.keystone.validate_token", return_value=invalid),
    ):
        with pytest.raises(cloud_shell.CloudShellUnauthorized, match="does not match"):
            await cloud_shell.issue_cloud_shell_ticket(token_info())


class FakeResource(dict):
    def to_dict(self):
        return dict(self)


class FakeBlockStorage:
    def __init__(self, volumes=None):
        self.items = list(volumes or [])
        self.created_kwargs = None
        self.deleted = []

    def volumes(self, **_kwargs):
        return list(self.items)

    def create_volume(self, **kwargs):
        self.created_kwargs = kwargs
        volume = FakeResource(
            id="volume-new",
            name=kwargs["name"],
            status="creating",
            size=kwargs["size"],
            metadata=kwargs["metadata"],
            attachments=[],
        )
        self.items.append(volume)
        return volume

    def wait_for_status(self, volume, **_kwargs):
        volume["status"] = "available"
        return volume

    def get_volume(self, volume_id):
        return next((volume for volume in self.items if volume["id"] == volume_id), None)

    def delete_volume(self, volume_id, **_kwargs):
        self.deleted.append(volume_id)
        self.items = [volume for volume in self.items if volume["id"] != volume_id]


class FakeConnection:
    def __init__(self, volumes=None):
        self.block_storage = FakeBlockStorage(volumes)
        self.closed = False

    def close(self):
        self.closed = True


def managed_volume(
    workspace_fp: str,
    *,
    volume_id: str = "volume-a",
    status: str = "available",
    settings: Settings | None = None,
):
    settings = settings or cloud_settings()
    return FakeResource(
        id=volume_id,
        name=f"afterglow-cloud-shell-home-{workspace_fp[:16]}",
        status=status,
        size=5,
        metadata=cloud_shell._workspace_metadata(workspace_fp, settings),
        attachments=[],
    )


def test_workspace_discovery_refuses_name_collision_and_duplicates():
    settings = cloud_settings()
    workspace_fp = cloud_shell.workspace_fingerprint("user-a", PROJECT_ID)
    collision = managed_volume(workspace_fp)
    collision["metadata"] = {}
    with pytest.raises(cloud_shell.CloudShellConflict, match="collides"):
        cloud_shell._discover_workspace_sync(FakeConnection([collision]), workspace_fp, settings)

    duplicate = managed_volume(workspace_fp, volume_id="volume-b")
    with pytest.raises(cloud_shell.CloudShellConflict, match="Multiple"):
        cloud_shell._discover_workspace_sync(
            FakeConnection([managed_volume(workspace_fp), duplicate]), workspace_fp, settings
        )


@pytest.mark.asyncio
async def test_workspace_reset_is_verified_and_idempotent():
    settings = cloud_settings()
    workspace_fp = cloud_shell.workspace_fingerprint("user-a", PROJECT_ID)
    conn = FakeConnection([managed_volume(workspace_fp)])
    with (
        patch("app.services.cloud_shell.get_settings", return_value=settings),
        patch("app.services.cloud_shell.keystone.get_cloud_shell_project_connection", return_value=conn),
    ):
        assert await cloud_shell.reset_workspace(token_info()) is True
        assert conn.block_storage.deleted == ["volume-a"]

    second_conn = FakeConnection()
    with (
        patch("app.services.cloud_shell.get_settings", return_value=settings),
        patch("app.services.cloud_shell.keystone.get_cloud_shell_project_connection", return_value=second_conn),
    ):
        assert await cloud_shell.reset_workspace(token_info()) is False


@pytest.mark.asyncio
async def test_workspace_reset_refuses_attached_home():
    settings = cloud_settings()
    workspace_fp = cloud_shell.workspace_fingerprint("user-a", PROJECT_ID)
    attached = managed_volume(workspace_fp)
    attached["attachments"] = [{"server_id": "service-container"}]
    conn = FakeConnection([attached])
    with (
        patch("app.services.cloud_shell.get_settings", return_value=settings),
        patch("app.services.cloud_shell.keystone.get_cloud_shell_project_connection", return_value=conn),
    ):
        with pytest.raises(cloud_shell.CloudShellConflict, match="attached"):
            await cloud_shell.reset_workspace(token_info())
    assert conn.block_storage.deleted == []


def response(body: dict, status: int = 200):
    result = MagicMock()
    result.status_code = status
    result.content = b"json"
    result.json.return_value = body
    return result


class _StockZunMemberApi(BaseAdapter):
    """Upstream Zun microversion gates and default policy, as seen by a project member."""

    FIELD_VERSIONS = {
        "auto_remove": (1, 3),
        "runtime": (1, 5),
        "hostname": (1, 9),
        "mounts": (1, 11),
        "privileged": (1, 21),
        "healthcheck": (1, 22),
        "exposed_ports": (1, 24),
        "tty": (1, 36),
    }

    def __init__(self):
        super().__init__()
        self.created: list[dict] = []
        self.containers: dict[str, dict] = {}

    def send(self, request, **kwargs):
        service, _, number = request.headers.get("OpenStack-API-Version", "container 1.1").partition(" ")
        assert service == "container"
        version = tuple(int(part) for part in number.split("."))
        url = urlsplit(request.url)
        query = dict(parse_qsl(url.query))
        if request.method == "POST" and url.path == "/v1/containers":
            body = json.loads(request.body)
            if any(body.get(field) is not None and version < needed for field, needed in self.FIELD_VERSIONS.items()):
                return self._reply(request, 406)
            if body.get("privileged") is not None:  # container:create:privileged is RULE_DENY_EVERYBODY
                return self._reply(request, 403)
            command_needs = (1, 20) if isinstance(body.get("command"), list) else (1, 1)
            mounts_need = (1, 23) if any("type" in mount for mount in body.get("mounts") or []) else (1, 1)
            if version < max(command_needs, mounts_need):
                return self._reply(request, 400)
            self.created.append(body)
            self.containers["container-a"] = {"uuid": "container-a", "status": "Running", "labels": body["labels"]}
            return self._reply(request, 202, {"uuid": "container-a", "status": "Creating"})
        container = self.containers.get(url.path.removeprefix("/v1/containers/").removesuffix("/stop"))
        if container is None:
            return self._reply(request, 404, {"errors": [{"title": "Not Found"}]})
        if request.method == "GET":
            return self._reply(request, 200, container)
        if request.method == "POST" and url.path.endswith("/stop"):
            container["status"] = "Stopped"
            return self._reply(request, 202)
        if request.method == "DELETE":
            if query.get("force") == "true":  # container:delete_force is admin-only from 1.7
                return self._reply(request, 406 if version < (1, 7) else 403)
            if query.get("stop") == "true" and version < (1, 12):
                return self._reply(request, 406)
            del self.containers[container["uuid"]]
            return self._reply(request, 204)
        raise AssertionError(f"unexpected Zun request {request.method} {request.url}")

    def _reply(self, request, status, body=None):
        result = Response()
        result.status_code = status
        result._content = b"" if body is None else json.dumps(body).encode()
        result.headers["Content-Type"] = "application/json"
        result.url = request.url
        result.request = request
        return result

    def close(self):
        pass


def test_cloud_shell_zun_lifecycle_passes_stock_member_api_gates():
    import requests
    from keystoneauth1 import session as ks_session
    from keystoneauth1.noauth import NoAuth

    api = _StockZunMemberApi()
    http = requests.Session()
    http.mount("http://zun.test/", api)
    session = ks_session.Session(auth=NoAuth(endpoint="http://zun.test"), session=http)
    conn = SimpleNamespace(config=None, session=session)
    settings = cloud_settings()
    lease = cloud_shell.CloudShellLease(
        session_id="session-a",
        user_id="user-a",
        username="alice",
        project_id=PROJECT_ID,
        project_name="project-a",
        token="target-token",
        token_expires_at=int(time.time()) + 600,
        user_fingerprint=cloud_shell.user_fingerprint("user-a"),
        workspace_fingerprint=cloud_shell.workspace_fingerprint("user-a", PROJECT_ID),
        active_value="active",
    )
    labels = cloud_shell._container_labels(lease, int(time.time()) + 600, settings)

    created = zun.create_cloud_shell_container(
        conn,
        name="afterglow-cloud-shell-session",
        image="registry.example.test/cloud-shell@sha256:" + "a" * 64,
        cpu=1.0,
        memory_mib=1024,
        network_id="network-a",
        security_group="security-group-a",
        volume_id="volume-a",
        labels=labels,
    )
    # Exact cleanup stops, deletes, then must treat the 404 that proves deletion as success.
    cloud_shell._delete_exact_container_sync(conn, created["uuid"], labels, settings)

    assert api.containers == {}
    assert "target-token" not in json.dumps(api.created)


def test_container_cleanup_refuses_tampered_managed_labels():
    settings = cloud_settings()
    lease = cloud_shell.CloudShellLease(
        session_id="session-a",
        user_id="user-a",
        username="alice",
        project_id=PROJECT_ID,
        project_name="project-a",
        token="target-token",
        token_expires_at=int(time.time()) + 600,
        user_fingerprint=cloud_shell.user_fingerprint("user-a"),
        workspace_fingerprint=cloud_shell.workspace_fingerprint("user-a", PROJECT_ID),
        active_value="active",
    )
    labels = cloud_shell._container_labels(lease, int(time.time()) + 600, settings)
    tampered = {**labels, "afterglow.signature": "0" * 64}
    with (
        patch("app.services.cloud_shell.zun.get_container_raw", return_value={"status": "RUNNING", "labels": tampered}),
        patch("app.services.cloud_shell.zun.delete_container_strict") as delete,
    ):
        with pytest.raises(cloud_shell.CloudShellConflict, match="ownership"):
            cloud_shell._delete_exact_container_sync(MagicMock(), "container-a", labels, settings)
    delete.assert_not_called()


def test_zun_exec_proxy_requires_exact_trusted_origin_and_query_contract():
    conn = MagicMock()
    conn.config.get_interface.return_value = "internal"
    conn.session.get_endpoint.return_value = "https://zun.example.test"
    proxy_url = "wss://proxy.example.test/attach?token=opaque&uuid=container-a&exec_id=exec-a"
    conn.session.post.return_value = response({"proxy_url": proxy_url, "exec_id": "exec-a"})

    session = zun.create_exec_session(
        conn,
        "container-a",
        trusted_websocket_origin="wss://proxy.example.test",
        command="/usr/local/bin/afterglow-cloud-shell-bootstrap",
    )
    assert session.websocket_url == proxy_url
    assert session.exec_id == "exec-a"
    execute_request = conn.session.post.call_args
    assert execute_request.kwargs["json"] == {
        "command": "/usr/local/bin/afterglow-cloud-shell-bootstrap",
        "run": False,
        "interactive": True,
    }
    conn.session.post.reset_mock()
    conn.session.post.return_value = response({})
    zun.resize_exec_session(conn, "container-a", exec_id="exec-a", cols=120, rows=40)
    resize_request = conn.session.post.call_args
    assert resize_request.args[0].endswith("/v1/containers/container-a/execute_resize?exec_id=exec-a&w=120&h=40")
    assert "json" not in resize_request.kwargs

    conn.session.post.return_value = response(
        {
            "proxy_url": proxy_url + "&unexpected=value",
            "uuid": "container-a",
            "exec_id": "exec-a",
        }
    )
    with pytest.raises(zun.ZunApiError, match="untrusted"):
        zun.create_exec_session(
            conn,
            "container-a",
            trusted_websocket_origin="wss://proxy.example.test",
        )


@pytest.mark.asyncio
async def test_reconciler_does_not_delete_when_redis_is_uncertain():
    delete = MagicMock()
    with (
        patch("app.services.cloud_shell.get_settings", return_value=cloud_settings()),
        patch("app.services.cloud_shell._get_redis", new=AsyncMock(side_effect=RuntimeError("down"))),
        patch("app.services.cloud_shell._delete_exact_container_sync", delete),
    ):
        with pytest.raises(cloud_shell.CloudShellUnavailable):
            await cloud_shell.reconcile_once()
    delete.assert_not_called()


def test_ticket_endpoint_returns_only_opaque_transport_fields():
    app = FastAPI()
    app.include_router(cloud_shell_router, prefix="/api/v1/cloud-shell")
    app.dependency_overrides[get_token_info] = token_info
    issued = {
        "ticket": "opaque-ticket-value",
        "websocket_path": "/api/v1/cloud-shell/ws",
        "expires_at": int(time.time()) + 60,
    }
    with (
        patch("app.api.cloud_shell.cloud_shell.issue_cloud_shell_ticket", new=AsyncMock(return_value=issued)),
        patch("app.api.cloud_shell.cloud_shell.record_audit", new=AsyncMock()),
        TestClient(app) as client,
    ):
        result = client.post("/api/v1/cloud-shell/tickets")
    assert result.status_code == 201
    assert result.json() == issued
    assert "token" not in json.dumps(result.json())


def test_websocket_rejects_untrusted_origin_before_ticket_consumption():
    app = FastAPI()
    app.include_router(cloud_shell_router, prefix="/api/v1/cloud-shell")
    consume = AsyncMock()
    with (
        patch("app.api.cloud_shell.cloud_shell.consume_cloud_shell_ticket", consume),
        TestClient(app) as client,
    ):
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                "/api/v1/cloud-shell/ws?ticket=opaque-ticket-value",
                headers={"origin": "https://attacker.example"},
            ) as websocket:
                websocket.receive_json()
    assert closed.value.code == 4403
    consume.assert_not_awaited()


@pytest.mark.asyncio
async def test_marker_gate_discards_pre_ack_output_and_bounds_buffer():
    class Upstream:
        def __init__(self, frames):
            self.frames = iter(frames)

        async def recv(self):
            return next(self.frames)

    from app.api.cloud_shell import _wait_for_marker

    await _wait_for_marker(
        Upstream([b"sensitive preface", cloud_shell.BOOTSTRAP_READY_MARKER + b"discard me"]),
        cloud_shell.BOOTSTRAP_READY_MARKER,
    )
    with pytest.raises(cloud_shell.CloudShellUnavailable, match="bootstrap failed"):
        await _wait_for_marker(Upstream([cloud_shell.BOOTSTRAP_ERROR_MARKER]), cloud_shell.BOOTSTRAP_OK_MARKER)
    with pytest.raises(cloud_shell.CloudShellUnavailable, match="exceeded"):
        await _wait_for_marker(Upstream([b"x" * (65 * 1024)]), b"never")


class _CloudNetworkAdapter(BaseAdapter):
    def __init__(self, *, owner=SERVICE_PROJECT_ID, shared=False, gateway=True, groups=None):
        self.network = {
            "id": "network-id",
            "project_id": owner,
            "name": "Default",
            "subnets": ["subnet-a"],
            "admin_state_up": True,
            "shared": shared,
            "router:external": False,
        }
        self.groups = (
            groups
            if groups is not None
            else [
                {
                    "id": "service-default",
                    "project_id": SERVICE_PROJECT_ID,
                    "name": "default",
                    "security_group_rules": [{"direction": "ingress", "remote_group_id": "service-default"}],
                }
            ]
        )
        self.gateway = gateway

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        query = dict(parse_qsl(url.query))
        assert request.method == "GET", "network defaults must not rewrite security-group rules"
        if url.path.rstrip("/") == "/v2.0":
            body = {
                "version": {
                    "id": "v2.0",
                    "status": "CURRENT",
                    "links": [{"rel": "self", "href": "http://neutron.test/v2.0/"}],
                }
            }
        elif url.path == "/v2.0/networks/network-id":
            body = {"network": self.network}
        elif url.path == "/v2.0/security-groups":
            # Deliberately return broader results as an administrative endpoint can.
            body = {"security_groups": self.groups}
        elif url.path == "/v2.0/ports":
            body = {
                "ports": [
                    {
                        "id": "port-a",
                        "device_id": "router-a",
                        "device_owner": "network:router_interface",
                        "fixed_ips": [{"subnet_id": "subnet-a"}],
                    }
                ]
                if query.get("device_owner") == "network:router_interface"
                else []
            }
        elif url.path == "/v2.0/routers":
            body = {
                "routers": [
                    {
                        "id": "router-a",
                        "project_id": SERVICE_PROJECT_ID,
                        "external_gateway_info": {"network_id": "external-a"} if self.gateway else {},
                    }
                ]
            }
        else:
            raise AssertionError(request.url)
        result = Response()
        result.status_code = 200
        result._content = json.dumps(body).encode()
        result.headers["Content-Type"] = "application/json"
        result.url = request.url
        result.request = request
        return result

    def close(self):
        pass


def _network_connection(**kwargs):
    import openstack.connection
    import requests
    from keystoneauth1 import session as ks_session
    from keystoneauth1.noauth import NoAuth

    adapter = _CloudNetworkAdapter(**kwargs)
    http = requests.Session()
    http.mount("http://neutron.test/", adapter)
    endpoint = "http://neutron.test/v2.0"
    conn = openstack.connection.Connection(
        session=ks_session.Session(auth=NoAuth(endpoint=endpoint), session=http),
        network_endpoint_override=endpoint,
        network_api_version="2",
    )
    conn._afterglow_project_id = SERVICE_PROJECT_ID
    return conn, adapter


@pytest.mark.asyncio
async def test_cloud_network_defaults_use_service_scope_and_own_default_group_rules():
    foreign_default = {"id": "caller-default", "project_id": PROJECT_ID, "name": "default"}
    conn, adapter = _network_connection()
    adapter.groups.insert(0, foreign_default)
    settings = cloud_settings(cloud_shell_network_id="", cloud_shell_security_group="")

    async def project_default(project_id):
        return {SERVICE_PROJECT_ID: "network-id", PROJECT_ID: "caller-network"}[project_id]

    with patch("app.services.default_network.get_default_network_id", new=project_default):
        assert await cloud_shell._resolve_networking(conn, settings) == ("network-id", "service-default")
    conn.close()


@pytest.mark.asyncio
async def test_cloud_security_group_id_wins_over_same_named_group():
    conn, _ = _network_connection(
        groups=[
            {"id": "sg-id", "project_id": SERVICE_PROJECT_ID, "name": "custom"},
            {"id": "other-id", "project_id": SERVICE_PROJECT_ID, "name": "sg-id"},
        ]
    )
    settings = cloud_settings(cloud_shell_security_group="sg-id")
    assert await cloud_shell._resolve_networking(conn, settings) == ("network-id", "sg-id")
    conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "groups",
    [
        [{"id": "foreign", "project_id": PROJECT_ID, "name": "default"}],
        [
            {"id": "a", "project_id": SERVICE_PROJECT_ID, "name": "default"},
            {"id": "b", "project_id": SERVICE_PROJECT_ID, "name": "default"},
        ],
    ],
)
async def test_cloud_security_group_rejects_foreign_or_ambiguous_default(groups):
    conn, _ = _network_connection(groups=groups)
    with pytest.raises(cloud_shell.CloudShellUnavailable) as error:
        await cloud_shell._resolve_networking(conn, cloud_settings(cloud_shell_security_group="default"))
    assert error.value.code == "security_group_unavailable"
    conn.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("owner,gateway", [(PROJECT_ID, True), (SERVICE_PROJECT_ID, False)])
async def test_cloud_network_failure_precedes_home_creation(owner, gateway):
    conn, _ = _network_connection(owner=owner, gateway=gateway)
    settings = cloud_settings(cloud_shell_security_group="default")
    lease = cloud_shell.CloudShellLease(
        session_id="session-a",
        user_id="user-a",
        username="alice",
        project_id=PROJECT_ID,
        project_name="project-a",
        token="caller-token",
        token_expires_at=int(time.time()) + 600,
        user_fingerprint="user-fingerprint",
        workspace_fingerprint="workspace-fingerprint",
        active_value="active",
    )
    with (
        patch("app.services.cloud_shell.get_settings", return_value=settings),
        patch("app.services.cloud_shell.keystone.get_cloud_shell_project_connection", return_value=conn),
        patch("app.services.cloud_shell._ensure_workspace", new=AsyncMock()) as workspace,
    ):
        with pytest.raises(cloud_shell.CloudShellUnavailable) as error:
            await cloud_shell.provision_session(lease, AsyncMock())
    assert error.value.code == "network_unavailable"
    workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_cloud_default_network_failure_does_not_fall_back_to_another_network():
    conn, _ = _network_connection()
    settings = cloud_settings(cloud_shell_network_id="", cloud_shell_security_group="default")
    with patch(
        "app.services.default_network.get_default_network_id", new=AsyncMock(side_effect=RuntimeError("DB down"))
    ):
        with pytest.raises(cloud_shell.CloudShellUnavailable) as error:
            await cloud_shell._resolve_networking(conn, settings)
    assert error.value.code == "network_unavailable"
    conn.close()


@pytest.mark.asyncio
async def test_cloud_shared_policy_network_is_only_available_through_default_selection():
    conn, _ = _network_connection(owner=PROJECT_ID, shared=True)
    settings = cloud_settings(
        cloud_shell_network_id="", cloud_shell_security_group="default", default_network_enabled=False
    )
    with (
        patch("app.services.default_network.get_default_network_id", new=AsyncMock(return_value=None)),
        patch(
            "app.services.resource_policy_store.resolve_policies",
            new=AsyncMock(return_value={"nova.default_network": "network-id"}),
        ),
    ):
        assert await cloud_shell._resolve_networking(conn, settings) == ("network-id", "service-default")
    with pytest.raises(cloud_shell.CloudShellUnavailable) as error:
        await cloud_shell._resolve_networking(conn, cloud_settings(cloud_shell_security_group="default"))
    assert error.value.code == "network_unavailable"
    conn.close()
