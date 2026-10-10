"""Browser-facing Drover action gates mirroring the native oslo.policy rules.

Drover remains authoritative for project/cluster ownership, the editor's
principal-bound workload namespace, credential issuance and shell tickets.
This gate refuses actions the caller's current exact service leaves cannot
perform before any transport. The K3s callback is a machine passthrough and
the shell WebSocket is ticket-authenticated; neither is a browser proxy action.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Mapping

from fastapi import HTTPException, Request

from app.services.service_permissions import require_any_service_permission, require_service_permission

INVENTORY = "drover-inventory_reader"
ACCESS_USER = "drover-access_user"
CLUSTERS_EDITOR = "drover-clusters_editor"
WORKLOADS_EDITOR = "drover-workloads_editor"
CLUSTERS_ADMIN = "drover-clusters_admin"
ACCESS_ADMIN = "drover-access_admin"

# Native drover:workloads:write and drover:access:get rules accept any one listed leaf.
_WORKLOADS_WRITE = (WORKLOADS_EDITOR, ACCESS_ADMIN)
_ACCESS_GET = (ACCESS_USER, WORKLOADS_EDITOR, ACCESS_ADMIN)
# Credential grade is explicit; the native default is user and a missing grade never escalates.
_CREDENTIAL_GRADES = {
    "user": (ACCESS_USER, ACCESS_ADMIN),
    "editor": _WORKLOADS_WRITE,
    "admin": (ACCESS_ADMIN,),
}

_SEGMENT = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]*")
_ANY = None
_SYSTEM = "system"

Check = Callable[[Request, Mapping], Awaitable[None]]


def _unknown() -> HTTPException:
    return HTTPException(status_code=403, detail="알 수 없는 Drover 작업입니다")


def _segments(upstream_path: str) -> tuple[str, ...]:
    """Reject encoded separators, dot segments and empty segments instead of normalizing them."""
    if not upstream_path.startswith("/v1/"):
        raise _unknown()
    rest = upstream_path[len("/v1/") :]
    rest = rest[:-1] if rest.endswith("/") else rest
    if not rest:
        return ()
    parts = tuple(rest.split("/"))
    if not all(_SEGMENT.fullmatch(part) for part in parts):
        raise _unknown()
    return parts


def _all(*leaves: str) -> Check:
    async def check(_request: Request, principal: Mapping) -> None:
        require_service_permission(principal, *leaves)

    return check


def _any(*leaves: str) -> Check:
    async def check(_request: Request, principal: Mapping) -> None:
        require_any_service_permission(principal, *leaves)

    return check


async def _json_object(request: Request) -> dict:
    try:
        body = await request.json()
    except (ValueError, RecursionError):
        # The native schema rejects a malformed body; no action is performed.
        return {}
    return body if isinstance(body, dict) else {}


async def _kubeconfig(request: Request, principal: Mapping) -> None:
    grades = request.query_params.getlist("grade")
    if len(grades) > 1:
        raise HTTPException(status_code=422, detail="grade는 한 번만 지정할 수 있습니다")
    leaves = _CREDENTIAL_GRADES.get(grades[0] if grades else "user")
    if leaves is None:
        raise HTTPException(status_code=422, detail="grade는 user, editor, admin 중 하나여야 합니다")
    require_any_service_permission(principal, *leaves)


async def _create_cluster(request: Request, principal: Mapping) -> None:
    require_service_permission(principal, CLUSTERS_EDITOR)
    if (await _json_object(request)).get("key_name"):
        # Node SSH can read the stored K3s administrator certificate/key.
        require_service_permission(principal, ACCESS_ADMIN)


async def _write_secret(request: Request, principal: Mapping) -> None:
    require_any_service_permission(principal, *_WORKLOADS_WRITE)
    if (await _json_object(request)).get("type", "Opaque") != "Opaque":
        require_service_permission(principal, ACCESS_ADMIN)


async def _own_credentials(_request: Request, _principal: Mapping) -> None:
    """Native drover:clusters:retire_credentials is owner-scoped: Drover deletes only the caller's credentials."""


_CLUSTER = ("clusters", _ANY)
_NAMESPACE = (*_CLUSTER, "namespaces", _ANY)

_ROUTES: tuple[tuple[str, tuple[str | None, ...], Check | str], ...] = (
    # Version/health metadata discovery.
    ("GET", (), _all(INVENTORY)),
    ("GET", ("health",), _all(INVENTORY)),
    ("GET", ("health", "live"), _all(INVENTORY)),
    # health.py is mounted before clusters.py, so /clusters/health is not a cluster ID.
    ("GET", ("clusters", "health"), _all(INVENTORY)),
    ("GET", (*_CLUSTER, "health"), _all(INVENTORY)),
    ("POST", (*_CLUSTER, "health", "check"), _all(INVENTORY)),
    # clusters.py
    ("GET", ("clusters",), _all(INVENTORY)),
    ("POST", ("clusters", "async"), _create_cluster),
    ("GET", _CLUSTER, _all(INVENTORY)),
    ("GET", (*_CLUSTER, "kubeconfig"), _kubeconfig),
    ("PATCH", (*_CLUSTER, "scale"), _all(CLUSTERS_EDITOR)),
    ("DELETE", _CLUSTER, _all(CLUSTERS_ADMIN)),
    ("POST", (*_CLUSTER, "delete-async"), _all(CLUSTERS_ADMIN)),
    ("GET", (*_CLUSTER, "nodes", _ANY, "interfaces"), _all(INVENTORY)),
    ("POST", (*_CLUSTER, "nodes", _ANY, "interfaces"), _all(CLUSTERS_EDITOR)),
    ("DELETE", (*_CLUSTER, "nodes", _ANY, "interfaces", _ANY), _all(CLUSTERS_ADMIN)),
    ("POST", (*_CLUSTER, "stampede", "enable"), _all(CLUSTERS_EDITOR)),
    ("POST", (*_CLUSTER, "stampede", "disable"), _all(CLUSTERS_EDITOR)),
    ("GET", (*_CLUSTER, "stampede"), _all(INVENTORY)),
    ("GET", (*_CLUSTER, "stampede", "status"), _all(INVENTORY)),
    ("GET", (*_CLUSTER, "stampede", "events"), _all(INVENTORY)),
    # authorization.py: resource-credential status, current-operator reauthorization and owner retirement.
    ("GET", (*_CLUSTER, "authorization"), _all(INVENTORY)),
    ("POST", (*_CLUSTER, "authorization"), _all(CLUSTERS_ADMIN)),
    ("POST", (*_CLUSTER, "authorization", "retire"), _own_credentials),
    # configmaps.py: editors' namespace preparation is a native workloads:write side effect.
    ("GET", (*_CLUSTER, "namespaces"), _all(INVENTORY)),
    ("GET", (*_CLUSTER, "configmaps"), _any(*_WORKLOADS_WRITE)),
    ("POST", (*_NAMESPACE, "configmaps"), _any(*_WORKLOADS_WRITE)),
    ("GET", (*_NAMESPACE, "configmaps", _ANY), _any(*_WORKLOADS_WRITE)),
    ("PUT", (*_NAMESPACE, "configmaps", _ANY), _any(*_WORKLOADS_WRITE)),
    ("DELETE", (*_NAMESPACE, "configmaps", _ANY), _any(*_WORKLOADS_WRITE)),
    # secrets.py: non-Opaque secret types require access admin.
    ("GET", (*_CLUSTER, "secrets"), _any(*_WORKLOADS_WRITE)),
    ("POST", (*_NAMESPACE, "secrets"), _write_secret),
    ("GET", (*_NAMESPACE, "secrets", _ANY), _any(*_WORKLOADS_WRITE)),
    ("PUT", (*_NAMESPACE, "secrets", _ANY), _write_secret),
    ("DELETE", (*_NAMESPACE, "secrets", _ANY), _any(*_WORKLOADS_WRITE)),
    # pods.py, k3s_services.py, workloads.py: reads are inventory, mutations workloads:write.
    ("GET", (*_NAMESPACE, "pods"), _all(INVENTORY)),
    ("DELETE", (*_NAMESPACE, "pods", _ANY), _any(*_WORKLOADS_WRITE)),
    ("GET", (*_NAMESPACE, "pods", _ANY, "log"), _any(*_ACCESS_GET)),
    ("GET", (*_NAMESPACE, "services"), _all(INVENTORY)),
    ("DELETE", (*_NAMESPACE, "services", _ANY), _any(*_WORKLOADS_WRITE)),
    ("GET", (*_NAMESPACE, "deployments"), _all(INVENTORY)),
    ("GET", (*_NAMESPACE, "replicasets"), _all(INVENTORY)),
    ("POST", (*_NAMESPACE, "deployments", _ANY, "restart"), _any(*_WORKLOADS_WRITE)),
    ("PATCH", (*_NAMESPACE, "deployments", _ANY, "scale"), _any(*_WORKLOADS_WRITE)),
    # nodegroups.py
    ("GET", (*_CLUSTER, "nodegroups"), _all(INVENTORY)),
    ("POST", (*_CLUSTER, "nodegroups"), _all(CLUSTERS_EDITOR)),
    ("GET", (*_CLUSTER, "nodegroups", _ANY), _all(INVENTORY)),
    ("PATCH", (*_CLUSTER, "nodegroups", _ANY), _all(CLUSTERS_EDITOR)),
    ("DELETE", (*_CLUSTER, "nodegroups", _ANY), _all(CLUSTERS_ADMIN)),
    # certificates.py
    ("GET", (*_CLUSTER, "ca-certificate"), _all(INVENTORY)),
    ("GET", (*_CLUSTER, "certificate-expiry"), _all(INVENTORY)),
    ("POST", (*_CLUSTER, "rotate-certs"), _all(CLUSTERS_ADMIN)),
    # shell.py: ticket issuance; the WebSocket itself revalidates the ticket's token natively.
    ("POST", (*_CLUSTER, "shell-ticket"), _any(*_WORKLOADS_WRITE)),
    # templates.py: tenant reads, system-managed catalog writes.
    ("GET", ("cluster-templates",), _all(INVENTORY)),
    ("GET", ("cluster-templates", _ANY), _all(INVENTORY)),
    ("POST", ("cluster-templates",), _SYSTEM),
    ("PATCH", ("cluster-templates", _ANY), _SYSTEM),
    ("DELETE", ("cluster-templates", _ANY), _SYSTEM),
    # operations.py, stats.py
    ("GET", ("operations", _ANY), _all(INVENTORY)),
    ("GET", ("operations", _ANY, "events"), _all(INVENTORY)),
    ("GET", ("stats", "clusters"), _all(INVENTORY)),
    # admin.py and resource_policies.py: drover:admin is verified system administration only.
    ("GET", ("admin", "clusters"), _SYSTEM),
    ("GET", ("admin", "clusters", _ANY), _SYSTEM),
    ("GET", ("admin", "clusters", _ANY, "kubeconfig"), _SYSTEM),
    ("PATCH", ("admin", "clusters", _ANY, "scale"), _SYSTEM),
    ("DELETE", ("admin", "clusters", _ANY), _SYSTEM),
    ("POST", ("admin", "clusters", _ANY, "delete-async"), _SYSTEM),
    ("GET", ("admin", "clusters", _ANY, "ca-certificate"), _SYSTEM),
    ("GET", ("admin", "clusters", _ANY, "certificate-expiry"), _SYSTEM),
    ("POST", ("admin", "clusters", _ANY, "rotate-certs"), _SYSTEM),
    ("GET", ("admin", "cluster-templates"), _SYSTEM),
    ("GET", ("admin", "managed-resources"), _SYSTEM),
    ("GET", ("admin", "resources"), _SYSTEM),
    ("GET", ("admin", "inventory"), _SYSTEM),
    ("GET", ("admin", "resource-policies"), _SYSTEM),
    ("GET", ("admin", "resource-policies", "catalog", _ANY), _SYSTEM),
    ("PUT", ("admin", "resource-policies", _ANY), _SYSTEM),
    ("GET", ("admin", "runtime-settings"), _SYSTEM),
    ("PUT", ("admin", "runtime-settings", _ANY), _SYSTEM),
)


def _match(method: str, parts: tuple[str, ...]) -> Check | str | None:
    for route_method, pattern, check in _ROUTES:
        if (
            route_method == method
            and len(pattern) == len(parts)
            and all(expected is _ANY or expected == part for expected, part in zip(pattern, parts, strict=True))
        ):
            return check
    return None


async def authorize_drover_request(request: Request, upstream_path: str, principal: Mapping) -> None:
    if request.method == "OPTIONS":
        return
    method = "GET" if request.method == "HEAD" else request.method
    check = _match(method, _segments(upstream_path))
    if check is None:
        raise _unknown()
    system_admin = principal.get("is_system_admin") is True
    if check == _SYSTEM:
        if not system_admin:
            raise HTTPException(status_code=403, detail="시스템 관리자 권한이 필요합니다")
        return
    if system_admin:
        return
    await check(request, principal)
