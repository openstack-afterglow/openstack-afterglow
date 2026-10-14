"""Focused regression tests for the worker runtime manager."""

from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import app
from app.models.worker_runtime import WorkerRuntimeStatus
from app.services import worker_runtime as runtime_service


@pytest.fixture
async def anon_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


class FakeDockerAPI:
    def __init__(self, containers: list[dict], *, engine_id: str = "engine-1") -> None:
        self.engine_id = engine_id
        self.containers = [dict(container) for container in containers]
        self.deleted_ids: list[str] = []
        self.created: list[dict] = []
        self.started_ids: list[str] = []

    def _body(self, request: httpx.Request) -> dict:
        raw = request.content.decode("utf-8") if request.content else "{}"
        return json.loads(raw)

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == "/info":
            return httpx.Response(200, request=request, json={"ID": self.engine_id})

        if request.method == "GET" and request.url.path == "/_ping":
            return httpx.Response(200, request=request)

        if request.method == "GET" and request.url.path == "/containers/json":
            return httpx.Response(200, request=request, json=self.containers)

        if request.method == "DELETE" and request.url.path.startswith("/containers/"):
            container_id = request.url.path.split("/")[2]
            self.deleted_ids.append(container_id)
            self.containers = [container for container in self.containers if container["Id"] != container_id]
            return httpx.Response(204, request=request)

        if request.method == "POST" and request.url.path == "/containers/create":
            body = self._body(request)
            name = request.url.params["name"]
            container_id = f"created-{len(self.created)}"
            self.created.append({"name": name, "body": body})
            self.containers.append(
                {
                    "Id": container_id,
                    "Names": [f"/{name}"],
                    "State": "created",
                    "Labels": body["Labels"],
                }
            )
            return httpx.Response(201, request=request, json={"Id": container_id})

        if (
            request.method == "POST"
            and request.url.path.startswith("/containers/")
            and request.url.path.endswith("/start")
        ):
            container_id = request.url.path.split("/")[2]
            self.started_ids.append(container_id)
            for container in self.containers:
                if container["Id"] == container_id:
                    container["State"] = "running"
                    break
            return httpx.Response(204, request=request)

        raise AssertionError(f"Unexpected Docker request: {request.method} {request.url}")


def _worker_specs(settings: Settings | None = None) -> list[runtime_service.WorkerSpec]:
    return runtime_service.build_worker_specs(settings or Settings())


def _status(
    mode: str = "static", capable: bool = False, reason: str | None = "runtime_manager_disabled"
) -> WorkerRuntimeStatus:
    return WorkerRuntimeStatus(mode=mode, capable=capable, reason=reason, workers=[])


def _docker_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, **overrides) -> runtime_service.DockerRuntimeConfig:
    socket_path = tmp_path / "docker.sock"
    socket_path.write_text("", encoding="utf-8")
    config_host_path = tmp_path / "afterglow.conf"
    config_host_path.write_text("[app]\nsite_name = 'Afterglow'\n", encoding="utf-8")
    logs_host_path = tmp_path / "logs"
    logs_host_path.mkdir()
    monkeypatch.setenv("AFTERGLOW_ALLOW_INSECURE", "1")
    base = runtime_service.DockerRuntimeConfig(
        socket_path=str(socket_path),
        image="afterglow/worker:latest",
        network="",
        config_mount="/app/afterglow.conf",
        config_host_path=str(config_host_path),
        gpu_config_mount="/app/config.gpu.toml",
        gpu_config_host_path="",
        logs_mount="/app/logs",
        logs_host_path=str(logs_host_path),
        env_allowlist=("AFTERGLOW_ALLOW_INSECURE",),
    )
    return replace(base, **overrides)


def _kubernetes_config(tmp_path: Path, **overrides) -> runtime_service.KubernetesRuntimeConfig:
    token_path = tmp_path / "token"
    token_path.write_text("token", encoding="utf-8")
    ca_path = tmp_path / "ca.crt"
    ca_path.write_text("ca", encoding="utf-8")
    base = runtime_service.KubernetesRuntimeConfig(
        namespace="afterglow",
        service_account_token_path=str(token_path),
        service_account_ca_path=str(ca_path),
        manage_deployments=False,
    )
    return replace(base, **overrides)


@pytest.mark.asyncio
async def test_static_worker_runtime_adapter_reports_disabled_status():
    settings = Settings()
    specs = _worker_specs(settings)

    status = await runtime_service.StaticWorkerRuntimeAdapter().get_status(specs)

    assert status.mode == "static"
    assert status.capable is False
    assert status.reason == "runtime_manager_disabled"
    assert {worker.name for worker in status.workers} == {"notion_worker"}
    assert all(worker.mode == "static" for worker in status.workers)
    assert all(worker.capable is False for worker in status.workers)
    assert all(worker.reason == "runtime_manager_disabled" for worker in status.workers)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("overrides", "expected_reason"),
    [
        ({"socket_path": ""}, "docker_socket_not_configured"),
        ({"image": ""}, "docker_image_not_configured"),
        ({"config_host_path": ""}, "docker_mount_not_configured"),
        ({"env_allowlist": ("WORKER_RUNTIME_MISSING_ENV",)}, "docker_env_not_configured"),
    ],
)
async def test_docker_reconcile_returns_stable_unavailable_reasons_without_mutation(
    tmp_path, monkeypatch, overrides, expected_reason
):
    specs = _worker_specs(Settings())
    desired = runtime_service.desired_from_specs(specs)
    config = _docker_config(tmp_path, monkeypatch, **overrides)
    client = AsyncMock(spec=httpx.AsyncClient)
    adapter = runtime_service.DockerWorkerRuntimeAdapter(config, client=client)

    status = await adapter.reconcile(desired, specs)

    assert status.mode == "docker"
    assert status.capable is False
    assert status.reason == expected_reason
    assert all(worker.reason == expected_reason for worker in status.workers)
    client.request.assert_not_awaited()


@pytest.mark.asyncio
async def test_docker_reconcile_recreates_lowest_missing_slot_and_ignores_static_containers(tmp_path, monkeypatch):
    config = _docker_config(tmp_path, monkeypatch)
    docker = FakeDockerAPI(
        [
            {
                "Id": "notion-running-0",
                "Names": ["/afterglow-managed-notion-worker-0"],
                "State": "running",
                "Labels": {
                    "afterglow.worker-runtime.managed": "true",
                    "afterglow.worker": "notion_worker",
                },
            },
            {
                "Id": "notion-exited-1",
                "Names": ["/afterglow-managed-notion-worker-1"],
                "State": "exited",
                "Labels": {
                    "afterglow.worker-runtime.managed": "true",
                    "afterglow.worker": "notion_worker",
                },
            },
            {
                "Id": "notion-running-2",
                "Names": ["/afterglow-managed-notion-worker-2"],
                "State": "running",
                "Labels": {
                    "afterglow.worker-runtime.managed": "true",
                    "afterglow.worker": "notion_worker",
                },
            },
            {
                "Id": "compose-drover-1",
                "Names": ["/drover"],
                "State": "running",
                "Labels": {},
            },
        ]
    )
    client = AsyncClient(transport=httpx.MockTransport(docker.handler), base_url="http://docker")
    adapter = runtime_service.DockerWorkerRuntimeAdapter(config, client=client)
    specs = [
        runtime_service.WorkerSpec(
            name="notion_worker",
            module="app.notion_worker",
            enabled=True,
            desired_replicas=3,
            max_replicas=3,
        )
    ]
    desired = runtime_service.desired_from_specs(specs)

    try:
        status = await adapter.reconcile(desired, specs)
    finally:
        await client.aclose()

    assert status.capable is True
    assert status.workers[0].observed_replicas == 3
    assert docker.deleted_ids == ["notion-exited-1"]
    assert [item["name"] for item in docker.created] == ["afterglow-managed-notion-worker-1"]
    assert docker.started_ids == ["created-0"]

    create_body = docker.created[0]["body"]
    assert create_body["Env"] == ["AFTERGLOW_ALLOW_INSECURE=1", "AFTERGLOW_ENV=production"]
    assert create_body["HostConfig"]["Binds"] == [
        f"{config.config_host_path}:{config.config_mount}:ro",
        f"{config.logs_host_path}:{config.logs_mount}",
    ]
    assert all(container_id != "compose-drover-1" for container_id in docker.deleted_ids)


@pytest.mark.asyncio
async def test_kubernetes_status_requires_service_account_token(tmp_path):
    missing = tmp_path / "missing-token"
    also_missing = tmp_path / "missing-ca"
    config = runtime_service.KubernetesRuntimeConfig(
        namespace="afterglow",
        service_account_token_path=str(missing),
        service_account_ca_path=str(also_missing),
        manage_deployments=False,
    )
    adapter = runtime_service.KubernetesWorkerRuntimeAdapter(config)

    status = await adapter.get_status(_worker_specs(Settings()))

    assert status.mode == "kubernetes"
    assert status.capable is False
    assert status.reason == "kubernetes_service_account_missing"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_reason"),
    [
        (403, "kubernetes_rbac_forbidden"),
        (404, "kubernetes_deployment_not_found"),
    ],
)
async def test_kubernetes_status_maps_api_failures_to_stable_reasons(tmp_path, status_code, expected_reason):
    config = _kubernetes_config(tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    client = AsyncClient(transport=httpx.MockTransport(handler), base_url="https://kubernetes.default.svc")
    adapter = runtime_service.KubernetesWorkerRuntimeAdapter(config, client=client)

    try:
        status = await adapter.get_status(_worker_specs(Settings()))
    finally:
        await client.aclose()

    assert status.mode == "kubernetes"
    assert status.capable is False
    assert status.reason == expected_reason


@pytest.mark.asyncio
async def test_kubernetes_reconcile_patches_only_scale_subresource(tmp_path):
    config = _kubernetes_config(tmp_path)
    observed: dict[str, int] = {"notion-worker": 0}
    patch_calls: list[tuple[str, dict, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "PATCH":
            body = json.loads(request.content.decode("utf-8"))
            patch_calls.append((path, body, request.headers["content-type"]))
            deployment = path.rstrip("/").split("/")[-2]
            observed[deployment] = body["spec"]["replicas"]
            return httpx.Response(200, request=request, json={})

        if request.method == "GET":
            deployment = path.rstrip("/").split("/")[-1]
            return httpx.Response(
                200,
                request=request,
                json={
                    "metadata": {"uid": "deployment-uid", "resourceVersion": "7"},
                    "spec": {"replicas": observed[deployment]},
                    "status": {"replicas": observed[deployment]},
                },
            )

        raise AssertionError(f"Unexpected Kubernetes request: {request.method} {request.url}")

    client = AsyncClient(transport=httpx.MockTransport(handler), base_url="https://kubernetes.default.svc")
    adapter = runtime_service.KubernetesWorkerRuntimeAdapter(config, client=client)
    specs = [
        runtime_service.WorkerSpec(
            name="notion_worker",
            module="app.notion_worker",
            enabled=True,
            desired_replicas=1,
            max_replicas=4,
        )
    ]
    desired = [runtime_service.WorkerDesired(name="notion_worker", desired_replicas=2)]

    try:
        status = await adapter.reconcile(desired, specs)
    finally:
        await client.aclose()

    assert status.capable is True
    assert [path for path, _, _ in patch_calls] == [
        "/apis/apps/v1/namespaces/afterglow/deployments/notion-worker/scale"
    ]
    # UID and resourceVersion make a recreated or concurrently changed Deployment fail closed.
    assert [body for _, body, _ in patch_calls] == [
        {"metadata": {"uid": "deployment-uid", "resourceVersion": "7"}, "spec": {"replicas": 2}}
    ]
    assert all(content_type == "application/merge-patch+json" for _, _, content_type in patch_calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body", "target"),
    [
        (
            "GET",
            "/api/v1/admin/worker-runtime/status",
            None,
            "app.api.identity.admin_worker_runtime.get_runtime_status",
        ),
        (
            "PATCH",
            "/api/v1/admin/worker-runtime/desired",
            {"workers": [{"name": "notion_worker", "desired_replicas": 1}]},
            "app.api.identity.admin_worker_runtime.patch_desired_counts",
        ),
        (
            "POST",
            "/api/v1/admin/worker-runtime/reconcile",
            None,
            "app.api.identity.admin_worker_runtime.reconcile_once_with_lock",
        ),
    ],
)
async def test_worker_runtime_admin_routes_return_401_when_unauthenticated(anon_client, method, path, body, target):
    with patch(target, new=AsyncMock(return_value=_status())) as mocked:
        response = await anon_client.request(method, path, json=body)

    assert response.status_code == 401
    mocked.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "body", "target"),
    [
        (
            "GET",
            "/api/v1/admin/worker-runtime/status",
            None,
            "app.api.identity.admin_worker_runtime.get_runtime_status",
        ),
        (
            "PATCH",
            "/api/v1/admin/worker-runtime/desired",
            {"workers": [{"name": "drover", "desired_replicas": 1}]},
            "app.api.identity.admin_worker_runtime.patch_desired_counts",
        ),
        (
            "POST",
            "/api/v1/admin/worker-runtime/reconcile",
            None,
            "app.api.identity.admin_worker_runtime.reconcile_once_with_lock",
        ),
    ],
)
async def test_worker_runtime_admin_routes_return_403_for_non_admin(non_admin_client, method, path, body, target):
    with patch(target, new=AsyncMock(return_value=_status())) as mocked:
        response = await non_admin_client.request(method, path, json=body)

    assert response.status_code == 403
    mocked.assert_not_awaited()


@pytest.mark.asyncio
async def test_patch_worker_runtime_desired_rejects_counts_above_worker_max(admin_client):
    settings = Settings(worker_runtime_notion_worker_max_replicas=1)
    with patch("app.services.worker_runtime.get_settings", return_value=settings):
        response = await admin_client.patch(
            "/api/v1/admin/worker-runtime/desired",
            json={"workers": [{"name": "notion_worker", "desired_replicas": 2}]},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "notion_worker desired_replicas exceeds max_replicas=1"


@pytest.fixture
async def runtime_coordination(monkeypatch):
    from fakeredis.aioredis import FakeRedis

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr("app.services.cache._get_redis", AsyncMock(return_value=redis))
    yield redis
    await redis.close()


@pytest.mark.asyncio
async def test_runtime_reconcile_same_engine_claims_only_one_create(tmp_path, monkeypatch, runtime_coordination):
    docker = FakeDockerAPI([])
    accepted, release = asyncio.Event(), asyncio.Event()

    async def provider(request):
        response = docker.handler(request)
        if request.method == "POST" and request.url.path == "/containers/create":
            accepted.set()
            await release.wait()
        return response

    settings = Settings(worker_runtime_mode="docker")
    async with AsyncClient(transport=httpx.MockTransport(provider), base_url="http://docker") as client:
        adapter = runtime_service.DockerWorkerRuntimeAdapter(_docker_config(tmp_path, monkeypatch), client=client)
        monkeypatch.setattr(runtime_service, "get_adapter", lambda _: adapter)
        owner = asyncio.create_task(runtime_service.reconcile_once_with_lock(settings))
        try:
            async with asyncio.timeout(5):
                await accepted.wait()
                assert await runtime_service.reconcile_once_with_lock(settings) is None
            assert len(docker.created) == 1
            assert docker.started_ids == []
        finally:
            release.set()
            status = await owner
    assert status.capable is True
    assert docker.started_ids == ["created-0"]
    assert await runtime_coordination.keys("*:lease:*") == []


@pytest.mark.asyncio
async def test_runtime_reconcile_different_engines_do_not_share_ownership(tmp_path, monkeypatch, runtime_coordination):
    first, second = FakeDockerAPI([], engine_id="engine-a"), FakeDockerAPI([], engine_id="engine-b")
    config = _docker_config(tmp_path, monkeypatch)
    async with (
        AsyncClient(transport=httpx.MockTransport(first.handler), base_url="http://docker") as first_client,
        AsyncClient(transport=httpx.MockTransport(second.handler), base_url="http://docker") as second_client,
    ):
        first_adapter = runtime_service.DockerWorkerRuntimeAdapter(config, client=first_client)
        second_adapter = runtime_service.DockerWorkerRuntimeAdapter(config, client=second_client)
        first_settings = Settings(worker_runtime_mode="docker", worker_runtime_docker_image="engine-a")
        second_settings = Settings(worker_runtime_mode="docker", worker_runtime_docker_image="engine-b")
        monkeypatch.setattr(
            runtime_service,
            "get_adapter",
            lambda settings: first_adapter if settings.worker_runtime_docker_image == "engine-a" else second_adapter,
        )
        statuses = await asyncio.gather(
            runtime_service.reconcile_once_with_lock(first_settings),
            runtime_service.reconcile_once_with_lock(second_settings),
        )
    assert all(status.capable for status in statuses)
    assert first.started_ids == ["created-0"]
    assert second.started_ids == ["created-0"]
    assert first.deleted_ids == second.deleted_ids == []


@pytest.mark.asyncio
async def test_runtime_reconcile_without_engine_identity_starts_no_mutation(
    tmp_path, monkeypatch, runtime_coordination
):
    docker = FakeDockerAPI([], engine_id="")
    async with AsyncClient(transport=httpx.MockTransport(docker.handler), base_url="http://docker") as client:
        adapter = runtime_service.DockerWorkerRuntimeAdapter(_docker_config(tmp_path, monkeypatch), client=client)
        monkeypatch.setattr(runtime_service, "get_adapter", lambda _: adapter)
        assert await runtime_service.reconcile_once_with_lock(Settings(worker_runtime_mode="docker")) is None
    assert docker.created == docker.started_ids == docker.deleted_ids == []


@pytest.mark.asyncio
async def test_runtime_cancel_drains_accepted_request_before_releasing_target(
    tmp_path, monkeypatch, runtime_coordination
):
    docker = FakeDockerAPI([])
    accepted, release = asyncio.Event(), asyncio.Event()

    async def provider(request):
        response = docker.handler(request)
        if request.method == "POST" and request.url.path == "/containers/create":
            accepted.set()
            await release.wait()
        return response

    settings = Settings(worker_runtime_mode="docker")
    async with AsyncClient(transport=httpx.MockTransport(provider), base_url="http://docker") as client:
        adapter = runtime_service.DockerWorkerRuntimeAdapter(_docker_config(tmp_path, monkeypatch), client=client)
        monkeypatch.setattr(runtime_service, "get_adapter", lambda _: adapter)
        owner = asyncio.create_task(runtime_service.reconcile_once_with_lock(settings))
        try:
            async with asyncio.timeout(5):
                await accepted.wait()
                owner.cancel()
                # One loop turn delivers cancellation to the actual HTTP await.
                await asyncio.sleep(0)
                assert not owner.done()
                assert await runtime_coordination.keys("*:lease:reconcile")
                assert await runtime_service.reconcile_once_with_lock(settings) is None
            assert len(docker.created) == 1
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await owner
    assert docker.started_ids == []
    assert await runtime_coordination.keys("*:lease:*") == []


@pytest.mark.asyncio
async def test_runtime_same_deployment_uid_serializes_replica_updates(tmp_path, monkeypatch, runtime_coordination):
    accepted, release = asyncio.Event(), asyncio.Event()
    state = {"updates": [], "replicas": 0, "paths": []}
    deployment_path = "/apis/apps/v1/namespaces/afterglow/deployments/notion-worker"

    async def provider(request):
        state["paths"].append(request.url.path)
        if request.method == "GET" and request.url.path == deployment_path:
            return httpx.Response(
                200,
                request=request,
                json={
                    "metadata": {"uid": "deployment-owned-uid", "resourceVersion": "11"},
                    "spec": {"replicas": state["replicas"]},
                    "status": {"replicas": state["replicas"]},
                },
            )
        if request.method == "PATCH" and request.url.path == deployment_path + "/scale":
            body = json.loads(request.content)
            state["updates"].append(body)
            accepted.set()
            await release.wait()
            state["replicas"] = body["spec"]["replicas"]
            return httpx.Response(200, request=request, json=body)
        raise AssertionError(f"Unexpected Kubernetes operation: {request.method} {request.url.path}")

    settings = Settings(worker_runtime_mode="kubernetes")
    async with AsyncClient(
        transport=httpx.MockTransport(provider), base_url="https://kubernetes.default.svc"
    ) as client:
        adapter = runtime_service.KubernetesWorkerRuntimeAdapter(_kubernetes_config(tmp_path), client=client)
        monkeypatch.setattr(runtime_service, "get_adapter", lambda _: adapter)
        owner = asyncio.create_task(runtime_service.reconcile_once_with_lock(settings))
        try:
            async with asyncio.timeout(5):
                await accepted.wait()
                assert await runtime_service.reconcile_once_with_lock(settings) is None
            assert state["updates"] == [
                {"metadata": {"uid": "deployment-owned-uid", "resourceVersion": "11"}, "spec": {"replicas": 1}}
            ]
        finally:
            release.set()
            status = await owner
    assert status.capable and status.workers[0].observed_replicas == 1
    assert set(state["paths"]) == {deployment_path, deployment_path + "/scale"}


@pytest.mark.asyncio
async def test_recreated_deployment_identity_blocks_old_owner_mutation(tmp_path):
    state = {"uid": "original-deployment", "patches": []}
    deployment_path = "/apis/apps/v1/namespaces/afterglow/deployments/notion-worker"

    def provider(request):
        if request.method == "GET" and request.url.path == deployment_path:
            return httpx.Response(
                200,
                request=request,
                json={
                    "metadata": {"uid": state["uid"], "resourceVersion": "3"},
                    "spec": {"replicas": 0},
                    "status": {"replicas": 0},
                },
            )
        if request.method == "PATCH":
            state["patches"].append(json.loads(request.content))
            return httpx.Response(200, request=request, json={})
        raise AssertionError(f"Unexpected Kubernetes operation: {request.method} {request.url.path}")

    specs = runtime_service.build_worker_specs(Settings(worker_runtime_mode="kubernetes"))
    desired = [runtime_service.WorkerDesired(name=spec.name, desired_replicas=1) for spec in specs]
    async with AsyncClient(
        transport=httpx.MockTransport(provider), base_url="https://kubernetes.default.svc"
    ) as client:
        adapter = runtime_service.KubernetesWorkerRuntimeAdapter(_kubernetes_config(tmp_path), client=client)
        await runtime_service._coordination_prefix(adapter, Settings(worker_runtime_mode="kubernetes"))
        state["uid"] = "recreated-deployment"
        with pytest.raises(runtime_service.DispatcherUnavailable):
            await adapter.reconcile(desired, specs)
    assert state["patches"] == []
