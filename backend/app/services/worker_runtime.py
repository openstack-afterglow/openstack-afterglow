"""Explicit runtime adapters for Afterglow background workers.

The default adapter is intentionally static: it reports the configured desired worker
shape but never mutates Docker Compose, Kubernetes, or Kolla deployments unless an
operator opts into a concrete runtime manager mode.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol

import httpx

from app.config import Settings, get_settings
from app.models.worker_runtime import WorkerName, WorkerRuntimeStatus, WorkerRuntimeWorkerStatus
from app.services.work_dispatcher import DispatcherUnavailable, WorkDispatcher, checkpoint, run_roles, work_lease

_logger = logging.getLogger(__name__)

_runtime_identity: ContextVar[tuple[str, str] | None] = ContextVar("runtime_identity", default=None)


async def _send_owned_request(adapter, client, method, path, kwargs):
    if method not in {"GET", "HEAD", "OPTIONS"}:
        await checkpoint()
        expected = _runtime_identity.get()
        if expected is not None:
            mode, identity = expected
            if mode == "docker":
                observed = await adapter._request("GET", "/info")
                observed.raise_for_status()
                current = observed.json().get("ID")
            else:
                deployment = adapter._deployment_name("notion_worker")
                observed = await adapter._request(
                    "GET", f"/apis/apps/v1/namespaces/{adapter.config.namespace}/deployments/{deployment}"
                )
                observed.raise_for_status()
                current = observed.json().get("metadata", {}).get("uid")
            if current != identity:
                raise DispatcherUnavailable("worker runtime target incarnation changed")
        await checkpoint()
    return await client.request(method, path, **kwargs)


async def _drain_request(request):
    while not request.done():
        try:
            await asyncio.shield(request)
        except asyncio.CancelledError:
            continue
        except Exception:
            break
    if not request.cancelled():
        request.exception()


_MANAGED_LABEL = "afterglow.worker-runtime.managed"
_WORKER_LABEL = "afterglow.worker"
_DESIRED_KEY = "afterglow:worker_runtime:desired"


@dataclass(frozen=True)
class WorkerSpec:
    name: WorkerName
    module: str
    enabled: bool
    desired_replicas: int
    max_replicas: int


@dataclass(frozen=True)
class WorkerDesired:
    name: WorkerName
    desired_replicas: int


@dataclass(frozen=True)
class DockerRuntimeConfig:
    socket_path: str
    image: str
    network: str
    config_mount: str
    config_host_path: str
    gpu_config_mount: str
    gpu_config_host_path: str
    logs_mount: str
    logs_host_path: str
    env_allowlist: tuple[str, ...]


@dataclass(frozen=True)
class KubernetesRuntimeConfig:
    namespace: str
    service_account_token_path: str
    service_account_ca_path: str
    manage_deployments: bool


class WorkerRuntimeAdapter(Protocol):
    async def get_status(self, specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus: ...

    async def reconcile(self, desired: Sequence[WorkerDesired], specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus: ...


def build_worker_specs(settings: Settings | None = None) -> list[WorkerSpec]:
    """Build the Afterglow-owned worker registry from settings."""
    cfg = settings or get_settings()
    return [
        WorkerSpec(
            name="notion_worker",
            module=cfg.worker_runtime_notion_worker_module,
            enabled=cfg.worker_runtime_notion_worker_enabled,
            desired_replicas=cfg.worker_runtime_notion_worker_desired_replicas,
            max_replicas=cfg.worker_runtime_notion_worker_max_replicas,
        )
    ]


def desired_from_specs(specs: Sequence[WorkerSpec]) -> list[WorkerDesired]:
    return [
        WorkerDesired(name=spec.name, desired_replicas=spec.desired_replicas if spec.enabled else 0) for spec in specs
    ]


def _worker_status(
    *,
    spec: WorkerSpec,
    mode: str,
    capable: bool,
    reason: str | None,
    observed_replicas: int | None,
    desired_replicas: int | None = None,
) -> WorkerRuntimeWorkerStatus:
    return WorkerRuntimeWorkerStatus(
        name=spec.name,
        enabled=spec.enabled,
        module=spec.module,
        desired_replicas=spec.desired_replicas if desired_replicas is None else desired_replicas,
        max_replicas=spec.max_replicas,
        observed_replicas=observed_replicas,
        mode=mode,  # type: ignore[arg-type]
        capable=capable,
        reason=reason,
    )


def _status_unavailable(mode: str, specs: Sequence[WorkerSpec], reason: str) -> WorkerRuntimeStatus:
    return WorkerRuntimeStatus(
        mode=mode,  # type: ignore[arg-type]
        capable=False,
        reason=reason,
        workers=[
            _worker_status(spec=spec, mode=mode, capable=False, reason=reason, observed_replicas=None) for spec in specs
        ],
    )


class StaticWorkerRuntimeAdapter:
    async def get_status(self, specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        reason = "runtime_manager_disabled"
        return WorkerRuntimeStatus(
            mode="static",
            capable=False,
            reason=reason,
            workers=[
                _worker_status(
                    spec=spec,
                    mode="static",
                    capable=False,
                    reason=reason,
                    observed_replicas=None,
                )
                for spec in specs
            ],
        )

    async def reconcile(self, desired: Sequence[WorkerDesired], specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        return await self.get_status(specs)


class DockerWorkerRuntimeAdapter:
    """Docker Engine API adapter over a configured Unix socket."""

    def __init__(self, config: DockerRuntimeConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client

    def _configured_reason(self) -> str | None:
        if not self.config.socket_path:
            return "docker_socket_not_configured"
        if not self.config.image:
            return "docker_image_not_configured"
        socket = Path(self.config.socket_path)
        if not socket.exists():
            return "docker_socket_unavailable"
        if not self.config.config_host_path:
            return "docker_mount_not_configured"
        if not Path(self.config.config_host_path).exists():
            return "docker_invalid_mount_config"
        if self.config.gpu_config_host_path and not Path(self.config.gpu_config_host_path).exists():
            return "docker_invalid_mount_config"
        if self.config.logs_host_path and not Path(self.config.logs_host_path).exists():
            return "docker_invalid_mount_config"
        if not self._container_env():
            return "docker_env_not_configured"
        return None

    def _make_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        transport = httpx.AsyncHTTPTransport(uds=self.config.socket_path)
        return httpx.AsyncClient(transport=transport, base_url="http://docker")

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if method not in {"GET", "HEAD", "OPTIONS"}:
            await checkpoint()
        client = self._make_client()
        close_client = self._client is None
        try:
            request = asyncio.create_task(_send_owned_request(self, client, method, path, kwargs))
            try:
                response = await asyncio.shield(request)
            except asyncio.CancelledError:
                await _drain_request(request)
                raise
        except PermissionError as exc:
            raise RuntimeError("docker_permission_denied") from exc
        except httpx.ConnectError as exc:
            message = str(exc).lower()
            if "permission" in message or "denied" in message:
                raise RuntimeError("docker_permission_denied") from exc
            raise RuntimeError("docker_socket_unavailable") from exc
        finally:
            if close_client:
                await client.aclose()
        if response.status_code in {401, 403}:
            raise RuntimeError("docker_permission_denied")
        if response.status_code >= 500:
            raise RuntimeError("docker_socket_unavailable")
        return response

    async def _list_managed(self) -> list[dict]:
        filters = {"label": [f"{_MANAGED_LABEL}=true"]}
        response = await self._request(
            "GET",
            "/containers/json",
            params={"all": "true", "filters": json.dumps(filters)},
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    async def _ping(self) -> str | None:
        reason = self._configured_reason()
        if reason:
            return reason
        response = await self._request("GET", "/_ping")
        if response.status_code != 200:
            return "docker_socket_unavailable"
        return None

    def _container_env(self) -> list[str]:
        env: list[str] = []
        for key in self.config.env_allowlist:
            if not key:
                continue
            value = os.environ.get(key)
            if value is not None:
                env.append(f"{key}={value}")
        if not any(item.startswith("AFTERGLOW_ENV=") for item in env):
            env.append("AFTERGLOW_ENV=production")
        if not any(item.startswith(("SECRET_KEY=", "AFTERGLOW_ALLOW_INSECURE=")) for item in env):
            return []
        return env

    async def get_status(self, specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        try:
            reason = await self._ping()
            if reason:
                return _status_unavailable("docker", specs, reason)
            containers = await self._list_managed()
        except RuntimeError as exc:
            reason = str(exc) if str(exc) else "docker_socket_unavailable"
            return _status_unavailable("docker", specs, reason)
        except Exception:
            _logger.warning("worker-runtime Docker status failed", exc_info=True)
            return _status_unavailable("docker", specs, "docker_socket_unavailable")
        counts = _docker_counts_by_worker(containers)
        return WorkerRuntimeStatus(
            mode="docker",
            capable=True,
            reason=None,
            workers=[
                _worker_status(
                    spec=spec,
                    mode="docker",
                    capable=True,
                    reason=None,
                    observed_replicas=counts.get(spec.name, 0),
                )
                for spec in specs
            ],
        )

    async def reconcile(self, desired: Sequence[WorkerDesired], specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        try:
            reason = await self._ping()
            if reason:
                return _status_unavailable("docker", specs, reason)
            containers = await self._list_managed()
            for container in _docker_stopped_managed_containers(containers):
                container_id = str(container.get("Id") or "")
                if container_id:
                    await self._request("DELETE", f"/containers/{container_id}", params={"force": "true"})
            by_worker = _docker_containers_by_worker(containers)
            desired_map = {item.name: item.desired_replicas for item in desired}
            spec_map = {spec.name: spec for spec in specs}
            for name, spec in spec_map.items():
                target = desired_map.get(name, spec.desired_replicas if spec.enabled else 0)
                target = min(max(target, 0), spec.max_replicas)
                current = by_worker.get(name, [])
                if len(current) < target:
                    used_slots = _docker_used_slots(name, current)
                    missing_slots = [slot for slot in range(target) if slot not in used_slots]
                    for slot in missing_slots[: target - len(current)]:
                        await self._create_worker(spec, slot)
                elif len(current) > target:
                    for container in current[target:]:
                        container_id = str(container.get("Id") or "")
                        if container_id:
                            await self._request("DELETE", f"/containers/{container_id}", params={"force": "true"})
        except RuntimeError as exc:
            reason = str(exc) if str(exc) else "docker_socket_unavailable"
            return _status_unavailable("docker", specs, reason)
        except Exception:
            _logger.warning("worker-runtime Docker reconcile failed", exc_info=True)
            return _status_unavailable("docker", specs, "docker_socket_unavailable")
        return await self.get_status(specs)

    async def _create_worker(self, spec: WorkerSpec, slot: int) -> None:
        labels = {
            _MANAGED_LABEL: "true",
            _WORKER_LABEL: spec.name,
        }
        binds: list[str] = [f"{self.config.config_host_path}:{self.config.config_mount}:ro"]
        if self.config.gpu_config_host_path:
            binds.append(f"{self.config.gpu_config_host_path}:{self.config.gpu_config_mount}:ro")
        if self.config.logs_host_path:
            binds.append(f"{self.config.logs_host_path}:{self.config.logs_mount}")
        body: dict = {
            "Image": self.config.image,
            "Cmd": ["python", "-m", spec.module],
            "Labels": labels,
            "Env": self._container_env(),
            "HostConfig": {"Binds": binds},
        }
        if self.config.network:
            body["HostConfig"]["NetworkMode"] = self.config.network
        name = f"afterglow-managed-{spec.name.replace('_', '-')}-{slot}"
        response = await self._request("POST", "/containers/create", params={"name": name}, json=body)
        if response.status_code == 404:
            raise RuntimeError("docker_image_unavailable")
        response.raise_for_status()
        container_id = response.json().get("Id")
        if container_id:
            start_response = await self._request("POST", f"/containers/{container_id}/start")
            if start_response.status_code not in {204, 304}:
                start_response.raise_for_status()


class KubernetesWorkerRuntimeAdapter:
    """Kubernetes Deployment replica adapter using the in-cluster HTTP API."""

    def __init__(self, config: KubernetesRuntimeConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self._client = client

    def _deployment_name(self, worker: WorkerName) -> str:
        return "notion-worker" if worker == "notion_worker" else worker

    def _configured_reason(self) -> str | None:
        if not self.config.namespace:
            return "kubernetes_api_unavailable"
        if not Path(self.config.service_account_token_path).exists():
            return "kubernetes_service_account_missing"
        if not Path(self.config.service_account_ca_path).exists():
            return "kubernetes_service_account_missing"
        return None

    def _make_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        token = Path(self.config.service_account_token_path).read_text(encoding="utf-8").strip()
        headers = {"Authorization": f"Bearer {token}"}
        return httpx.AsyncClient(
            base_url="https://kubernetes.default.svc",
            headers=headers,
            verify=self.config.service_account_ca_path,
            timeout=10,
        )

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if method not in {"GET", "HEAD", "OPTIONS"}:
            await checkpoint()
        client = self._make_client()
        close_client = self._client is None
        try:
            request = asyncio.create_task(_send_owned_request(self, client, method, path, kwargs))
            try:
                response = await asyncio.shield(request)
            except asyncio.CancelledError:
                await _drain_request(request)
                raise
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.TransportError) as exc:
            raise RuntimeError("kubernetes_api_unavailable") from exc
        finally:
            if close_client:
                await client.aclose()
        if response.status_code in {401, 403}:
            raise RuntimeError("kubernetes_rbac_forbidden")
        return response

    async def get_status(self, specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        reason = self._configured_reason()
        if reason:
            return _status_unavailable("kubernetes", specs, reason)
        workers: list[WorkerRuntimeWorkerStatus] = []
        try:
            for spec in specs:
                response = await self._request(
                    "GET",
                    f"/apis/apps/v1/namespaces/{self.config.namespace}/deployments/{self._deployment_name(spec.name)}",
                )
                if response.status_code == 404:
                    return _status_unavailable("kubernetes", specs, "kubernetes_deployment_not_found")
                response.raise_for_status()
                payload = response.json()
                observed = payload.get("status", {}).get("replicas")
                if observed is None:
                    observed = payload.get("spec", {}).get("replicas", 0)
                workers.append(
                    _worker_status(
                        spec=spec,
                        mode="kubernetes",
                        capable=True,
                        reason=None,
                        observed_replicas=int(observed or 0),
                    )
                )
        except RuntimeError as exc:
            return _status_unavailable("kubernetes", specs, str(exc) or "kubernetes_api_unavailable")
        except Exception:
            _logger.warning("worker-runtime Kubernetes status failed", exc_info=True)
            return _status_unavailable("kubernetes", specs, "kubernetes_api_unavailable")
        return WorkerRuntimeStatus(mode="kubernetes", capable=True, reason=None, workers=workers)

    async def reconcile(self, desired: Sequence[WorkerDesired], specs: Sequence[WorkerSpec]) -> WorkerRuntimeStatus:
        if self.config.manage_deployments:
            return _status_unavailable("kubernetes", specs, "kubernetes_managed_deployments_unsupported")
        reason = self._configured_reason()
        if reason:
            return _status_unavailable("kubernetes", specs, reason)
        desired_map = {item.name: item.desired_replicas for item in desired}
        try:
            for spec in specs:
                replicas = min(max(desired_map.get(spec.name, spec.desired_replicas), 0), spec.max_replicas)
                deployment_path = (
                    f"/apis/apps/v1/namespaces/{self.config.namespace}/deployments/{self._deployment_name(spec.name)}"
                )
                current = await self._request("GET", deployment_path)
                if current.status_code == 404:
                    return _status_unavailable("kubernetes", specs, "kubernetes_deployment_not_found")
                current.raise_for_status()
                metadata = current.json().get("metadata", {})
                if not metadata.get("uid") or not metadata.get("resourceVersion"):
                    return _status_unavailable("kubernetes", specs, "kubernetes_target_precondition_unavailable")
                response = await self._request(
                    "PATCH",
                    f"/apis/apps/v1/namespaces/{self.config.namespace}/deployments/{self._deployment_name(spec.name)}/scale",
                    headers={"Content-Type": "application/merge-patch+json"},
                    json={
                        "metadata": {"uid": metadata["uid"], "resourceVersion": metadata["resourceVersion"]},
                        "spec": {"replicas": replicas},
                    },
                )
                if response.status_code == 404:
                    return _status_unavailable("kubernetes", specs, "kubernetes_deployment_not_found")
                response.raise_for_status()
        except DispatcherUnavailable:
            raise
        except RuntimeError as exc:
            return _status_unavailable("kubernetes", specs, str(exc) or "kubernetes_api_unavailable")
        except Exception:
            _logger.warning("worker-runtime Kubernetes reconcile failed", exc_info=True)
            return _status_unavailable("kubernetes", specs, "kubernetes_api_unavailable")
        return await self.get_status(specs)


def _docker_is_running(container: dict) -> bool:
    return str(container.get("State") or "").lower() == "running"


def _docker_counts_by_worker(containers: Sequence[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for container in containers:
        if not _docker_is_running(container):
            continue
        labels = container.get("Labels") or {}
        if labels.get(_MANAGED_LABEL) != "true":
            continue
        worker = labels.get(_WORKER_LABEL)
        if worker:
            counts[worker] = counts.get(worker, 0) + 1
    return counts


def _docker_stopped_managed_containers(containers: Sequence[dict]) -> list[dict]:
    stopped: list[dict] = []
    for container in containers:
        labels = container.get("Labels") or {}
        if labels.get(_MANAGED_LABEL) == "true" and not _docker_is_running(container):
            stopped.append(container)
    return stopped


def _docker_used_slots(worker: str, containers: Sequence[dict]) -> set[int]:
    prefix = f"afterglow-managed-{worker.replace('_', '-')}-"
    slots: set[int] = set()
    for container in containers:
        for raw_name in container.get("Names") or []:
            name = str(raw_name).lstrip("/")
            if not name.startswith(prefix):
                continue
            suffix = name[len(prefix) :]
            if suffix.isdigit():
                slots.add(int(suffix))
    return slots


def _docker_containers_by_worker(containers: Sequence[dict]) -> dict[str, list[dict]]:
    by_worker: dict[str, list[dict]] = {}
    for container in containers:
        if not _docker_is_running(container):
            continue
        labels = container.get("Labels") or {}
        if labels.get(_MANAGED_LABEL) != "true":
            continue
        worker = labels.get(_WORKER_LABEL)
        if worker:
            by_worker.setdefault(worker, []).append(container)
    for items in by_worker.values():
        items.sort(key=lambda item: str(item.get("Names") or item.get("Id") or ""))
    return by_worker


def get_adapter(settings: Settings | None = None) -> WorkerRuntimeAdapter:
    cfg = settings or get_settings()
    if cfg.worker_runtime_mode == "docker":
        return DockerWorkerRuntimeAdapter(
            DockerRuntimeConfig(
                socket_path=cfg.worker_runtime_docker_socket_path,
                image=cfg.worker_runtime_docker_image,
                network=cfg.worker_runtime_docker_network,
                config_mount=cfg.worker_runtime_docker_config_mount,
                config_host_path=cfg.worker_runtime_docker_config_host_path,
                gpu_config_mount=cfg.worker_runtime_docker_gpu_config_mount,
                gpu_config_host_path=cfg.worker_runtime_docker_gpu_config_host_path,
                logs_mount=cfg.worker_runtime_docker_logs_mount,
                logs_host_path=cfg.worker_runtime_docker_logs_host_path,
                env_allowlist=tuple(
                    item.strip() for item in cfg.worker_runtime_docker_env_allowlist.split(",") if item.strip()
                ),
            )
        )
    if cfg.worker_runtime_mode == "kubernetes":
        return KubernetesWorkerRuntimeAdapter(
            KubernetesRuntimeConfig(
                namespace=cfg.worker_runtime_kubernetes_namespace,
                service_account_token_path=cfg.worker_runtime_kubernetes_service_account_token_path,
                service_account_ca_path=cfg.worker_runtime_kubernetes_service_account_ca_path,
                manage_deployments=cfg.worker_runtime_kubernetes_manage_deployments,
            )
        )
    return StaticWorkerRuntimeAdapter()


async def _read_desired_overrides() -> dict[str, int]:
    from app.services.cache import _get_redis

    redis = await _get_redis()
    raw = await redis.get(_DESIRED_KEY)
    if raw is None:
        return {}
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return {str(key): int(value) for key, value in data.items()}


async def _write_desired_overrides(overrides: dict[str, int]) -> None:
    from app.services.cache import _get_redis

    redis = await _get_redis()
    await redis.set(_DESIRED_KEY, json.dumps(overrides, sort_keys=True))


async def desired_with_overrides(specs: Sequence[WorkerSpec]) -> list[WorkerDesired]:
    desired = {item.name: item.desired_replicas for item in desired_from_specs(specs)}
    try:
        overrides = await _read_desired_overrides()
    except Exception:
        _logger.warning("worker-runtime desired override read failed; falling back to config", exc_info=True)
        overrides = {}
    spec_map = {spec.name: spec for spec in specs}
    for name, replicas in overrides.items():
        spec = spec_map.get(name)  # type: ignore[arg-type]
        if spec is None:
            continue
        desired[name] = min(max(replicas, 0), spec.max_replicas)
    return [WorkerDesired(name=spec.name, desired_replicas=desired[spec.name]) for spec in specs]


async def get_runtime_status(settings: Settings | None = None) -> WorkerRuntimeStatus:
    cfg = settings or get_settings()
    specs = build_worker_specs(cfg)
    desired = await desired_with_overrides(specs)
    status = await get_adapter(cfg).get_status(specs)
    desired_map = {item.name: item.desired_replicas for item in desired}
    status.workers = [
        worker.model_copy(update={"desired_replicas": desired_map.get(worker.name, worker.desired_replicas)})
        for worker in status.workers
    ]
    return status


async def patch_desired_counts(updates: dict[WorkerName, int], settings: Settings | None = None) -> WorkerRuntimeStatus:
    cfg = settings or get_settings()
    specs = build_worker_specs(cfg)
    spec_map = {spec.name: spec for spec in specs}
    for name, replicas in updates.items():
        spec = spec_map[name]
        if replicas > spec.max_replicas:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=400, detail=f"{name} desired_replicas exceeds max_replicas={spec.max_replicas}"
            )
    try:
        overrides = await _read_desired_overrides()
    except Exception as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=503, detail="worker runtime desired store unavailable") from exc
    overrides.update({name: replicas for name, replicas in updates.items()})
    await _write_desired_overrides(overrides)
    return await get_runtime_status(cfg)


async def _coordination_prefix(adapter, settings: Settings) -> str:
    """The Engine/Deployment identity, not a container hostname, owns this target."""
    if settings.worker_runtime_mode == "docker":
        response = await adapter._request("GET", "/info")
        response.raise_for_status()
        identity = response.json().get("ID")
    else:
        deployment = adapter._deployment_name("notion_worker")
        response = await adapter._request(
            "GET", f"/apis/apps/v1/namespaces/{adapter.config.namespace}/deployments/{deployment}"
        )
        response.raise_for_status()
        identity = response.json().get("metadata", {}).get("uid")
    if not isinstance(identity, str) or not identity:
        raise RuntimeError("worker runtime target identity unavailable")
    _runtime_identity.set((settings.worker_runtime_mode, identity))
    digest = hashlib.sha256(identity.encode()).hexdigest()
    return f"afterglow:worker_runtime:{settings.worker_runtime_mode}:{digest}"


async def reconcile_once_with_lock(settings: Settings | None = None) -> WorkerRuntimeStatus | None:
    """Best-effort immediate reconcile using the background target's execution lease."""
    from app.services.cache import _get_redis

    cfg = settings or get_settings()
    if cfg.worker_runtime_mode == "static":
        return await get_runtime_status(cfg)
    try:
        adapter = get_adapter(cfg)
        prefix = await _coordination_prefix(adapter, cfg)
        async with WorkDispatcher(await _get_redis(), prefix, roles=("reconcile",)) as dispatcher:
            if await dispatcher.is_leader():
                await dispatcher.publish(["reconcile"])
            claimed = await dispatcher.claim(90)
            if claimed is None:
                return None
            async with work_lease(dispatcher, *claimed):
                specs = build_worker_specs(cfg)
                desired = await desired_with_overrides(specs)
                return await adapter.reconcile(desired, specs)
    except Exception:
        _logger.warning("worker-runtime reconcile skipped: target or coordination unavailable", exc_info=True)
        return None


async def reconcile_loop() -> None:
    cfg = get_settings()
    interval = cfg.worker_runtime_reconcile_interval
    if cfg.worker_runtime_mode == "static" or interval <= 0:
        return

    async def run_owned(adapter) -> None:
        while True:
            try:
                await checkpoint()
                specs = build_worker_specs(cfg)
                desired = await desired_with_overrides(specs)
                status = await adapter.reconcile(desired, specs)
                if not status.capable:
                    _logger.warning(
                        "worker-runtime reconcile unavailable", extra={"mode": status.mode, "reason": status.reason}
                    )
            except Exception:
                _logger.warning("worker-runtime reconcile failed", exc_info=True)
            await asyncio.sleep(interval)

    async def watch_target(adapter, prefix):
        while True:
            await asyncio.sleep(min(interval, 5))
            if await _coordination_prefix(adapter, cfg) != prefix:
                return

    while True:
        try:
            adapter = get_adapter(cfg)
            prefix = await _coordination_prefix(adapter, cfg)
            roles = asyncio.create_task(run_roles({"reconcile": partial(run_owned, adapter)}, prefix=prefix))
            target_watch = asyncio.create_task(watch_target(adapter, prefix))
            try:
                done, _ = await asyncio.wait((roles, target_watch), return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    await task
            finally:
                roles.cancel()
                target_watch.cancel()
                await asyncio.gather(roles, target_watch, return_exceptions=True)
        except Exception:
            _logger.warning("worker-runtime target coordination unavailable", exc_info=True)
        await asyncio.sleep(interval)
