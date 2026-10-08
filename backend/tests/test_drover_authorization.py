"""Consumer-visible Drover browser action gates; only the upstream transport is faked."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api import deps
from app.api.drover.admin import router as drover_admin_router
from app.api.drover.proxy import router as drover_proxy_router
from app.services import project_service, service_proxy
from app.services.drover_authorization import authorize_drover_request

PROJECT = "11111111111141118111111111111111"
USER = "33333333333343338333333333333333"
CLUSTER = "44444444-4444-4444-8444-444444444444"
INVENTORY = "drover-inventory_reader"
ACCESS_USER = "drover-access_user"
CLUSTERS_EDITOR = "drover-clusters_editor"
WORKLOADS_EDITOR = "drover-workloads_editor"
CLUSTERS_ADMIN = "drover-clusters_admin"
ACCESS_ADMIN = "drover-access_admin"
USER_GRADE = [INVENTORY, ACCESS_USER]
EDITOR_GRADE = [*USER_GRADE, CLUSTERS_EDITOR, WORKLOADS_EDITOR]
ADMIN_GRADE = [*EDITOR_GRADE, CLUSTERS_ADMIN, ACCESS_ADMIN]
C = f"/v1/clusters/{CLUSTER}"
NS = f"{C}/namespaces/drover-workload-abc"


def _request(method: str, body: bytes = b"", query: bytes = b"") -> Request:
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    scope = {
        "type": "http",
        "method": method,
        "path": "/",
        "query_string": query,
        "headers": [(b"content-type", b"application/json")],
    }
    return Request(scope, receive)


async def _status(
    method: str, path: str, roles: list[str], body: bytes = b"", query: bytes = b"", *, system: bool = False
) -> int:
    principal = {"user_id": USER, "project_id": PROJECT, "roles": roles, "is_system_admin": system}
    try:
        await authorize_drover_request(_request(method, body, query), path, principal)
    except HTTPException as exc:
        return exc.status_code
    return 204


async def _allowed(
    method: str, path: str, roles: list[str], body: bytes = b"", query: bytes = b"", *, system: bool = False
) -> bool:
    status = await _status(method, path, roles, body, query, system=system)
    assert status in {204, 403}
    return status == 204


ALL_ROUTES = [
    ("GET", "/v1/", [INVENTORY]),
    ("GET", "/v1/health", [INVENTORY]),
    ("GET", "/v1/health/live", [INVENTORY]),
    ("GET", "/v1/clusters/health", [INVENTORY]),
    ("GET", f"{C}/health", [INVENTORY]),
    ("POST", f"{C}/health/check", [INVENTORY]),
    ("GET", "/v1/clusters", [INVENTORY]),
    ("GET", C, [INVENTORY]),
    ("GET", f"{C}/nodes/vm-1/interfaces", [INVENTORY]),
    ("GET", f"{C}/stampede", [INVENTORY]),
    ("GET", f"{C}/stampede/status", [INVENTORY]),
    ("GET", f"{C}/stampede/events", [INVENTORY]),
    ("GET", f"{C}/authorization", [INVENTORY]),
    ("GET", f"{C}/namespaces", [INVENTORY]),
    ("GET", f"{NS}/pods", [INVENTORY]),
    ("GET", f"{NS}/services", [INVENTORY]),
    ("GET", f"{NS}/deployments", [INVENTORY]),
    ("GET", f"{NS}/replicasets", [INVENTORY]),
    ("GET", f"{C}/nodegroups", [INVENTORY]),
    ("GET", f"{C}/nodegroups/ng-1", [INVENTORY]),
    ("GET", f"{C}/ca-certificate", [INVENTORY]),
    ("GET", f"{C}/certificate-expiry", [INVENTORY]),
    ("GET", "/v1/cluster-templates", [INVENTORY]),
    ("GET", "/v1/cluster-templates/t-1", [INVENTORY]),
    ("GET", "/v1/operations/op-1", [INVENTORY]),
    ("GET", "/v1/operations/op-1/events", [INVENTORY]),
    ("GET", "/v1/stats/clusters", [INVENTORY]),
    ("POST", "/v1/clusters/async", [CLUSTERS_EDITOR]),
    ("PATCH", f"{C}/scale", [CLUSTERS_EDITOR]),
    ("POST", f"{C}/nodes/vm-1/interfaces", [CLUSTERS_EDITOR]),
    ("POST", f"{C}/stampede/enable", [CLUSTERS_EDITOR]),
    ("POST", f"{C}/stampede/disable", [CLUSTERS_EDITOR]),
    ("POST", f"{C}/nodegroups", [CLUSTERS_EDITOR]),
    ("PATCH", f"{C}/nodegroups/ng-1", [CLUSTERS_EDITOR]),
    ("DELETE", C, [CLUSTERS_ADMIN]),
    ("POST", f"{C}/delete-async", [CLUSTERS_ADMIN]),
    ("DELETE", f"{C}/nodes/vm-1/interfaces/port-1", [CLUSTERS_ADMIN]),
    ("DELETE", f"{C}/nodegroups/ng-1", [CLUSTERS_ADMIN]),
    ("POST", f"{C}/rotate-certs", [CLUSTERS_ADMIN]),
    ("POST", f"{C}/authorization", [CLUSTERS_ADMIN]),
]


async def test_owner_credential_retirement_reaches_native_owner_check():
    """Retiring one's own superseded credentials only reduces authority; Drover enforces ownership."""
    assert await _allowed("POST", f"{C}/authorization/retire", ["member"])
    assert not await _allowed("GET", f"{C}/authorization/retire", ["member", *ADMIN_GRADE])
    assert not await _allowed("POST", f"{C}/authorization/rotate", ["member", *ADMIN_GRADE])


# Native drover:workloads:write accepts either leaf; neither inventory nor access_user suffices.
WORKLOAD_ROUTES = [
    ("GET", f"{C}/configmaps"),
    ("POST", f"{NS}/configmaps"),
    ("GET", f"{NS}/configmaps/cm"),
    ("PUT", f"{NS}/configmaps/cm"),
    ("DELETE", f"{NS}/configmaps/cm"),
    ("GET", f"{C}/secrets"),
    ("POST", f"{NS}/secrets"),
    ("GET", f"{NS}/secrets/s"),
    ("PUT", f"{NS}/secrets/s"),
    ("DELETE", f"{NS}/secrets/s"),
    ("DELETE", f"{NS}/pods/p"),
    ("DELETE", f"{NS}/services/svc"),
    ("POST", f"{NS}/deployments/web/restart"),
    ("PATCH", f"{NS}/deployments/web/scale"),
    ("POST", f"{C}/shell-ticket"),
]


@pytest.mark.parametrize("method,path,leaves", ALL_ROUTES)
async def test_exact_native_leaves_without_parent_or_raw_admin_shortcut(method, path, leaves):
    assert await _allowed(method, path, ["member", *leaves])
    assert not await _allowed(method, path, ["member"])
    assert not await _allowed(method, path, ["member", "drover_admin", "project_owner", "project_admin"])
    assert not await _allowed(method, path, ["member", "admin", *leaves])
    assert not await _allowed(method, path, ["member", "manager", *leaves])


@pytest.mark.parametrize("method,path", WORKLOAD_ROUTES)
async def test_workloads_and_shell_need_workloads_editor_or_access_admin(method, path):
    assert await _allowed(method, path, ["member", WORKLOADS_EDITOR])
    assert await _allowed(method, path, ["member", ACCESS_ADMIN])
    assert not await _allowed(method, path, ["member", *USER_GRADE, CLUSTERS_EDITOR, CLUSTERS_ADMIN])
    assert not await _allowed(method, path, ["member", "drover_editor", "drover_admin"])


async def test_pod_log_is_access_get():
    path = f"{NS}/pods/p/log"
    for leaf in (ACCESS_USER, WORKLOADS_EDITOR, ACCESS_ADMIN):
        assert await _allowed("GET", path, ["member", leaf])
    assert not await _allowed("GET", path, ["member", INVENTORY, CLUSTERS_EDITOR, CLUSTERS_ADMIN])


@pytest.mark.parametrize(
    "method,path,user,editor",
    [
        ("GET", f"{C}/kubeconfig", True, True),
        ("POST", "/v1/clusters/async", False, True),
        ("PATCH", f"{C}/scale", False, True),
        ("POST", f"{C}/shell-ticket", False, True),
        ("DELETE", C, False, False),
        ("POST", f"{C}/delete-async", False, False),
        ("DELETE", f"{C}/nodegroups/ng-1", False, False),
        ("POST", f"{C}/rotate-certs", False, False),
    ],
)
async def test_grade_bundles_access_edit_and_admin_actions(method, path, user, editor):
    assert await _allowed(method, path, ["member", *USER_GRADE]) is user
    assert await _allowed(method, path, ["member", *EDITOR_GRADE]) is editor
    assert await _allowed(method, path, ["member", *ADMIN_GRADE])


@pytest.mark.parametrize(
    "query,allowed_leaves",
    [
        (b"", {ACCESS_USER, ACCESS_ADMIN}),
        (b"grade=user", {ACCESS_USER, ACCESS_ADMIN}),
        (b"grade=editor", {WORKLOADS_EDITOR, ACCESS_ADMIN}),
        (b"grade=admin", {ACCESS_ADMIN}),
    ],
)
@pytest.mark.parametrize("method", ["GET", "HEAD"])
async def test_kubeconfig_grade_is_explicit_without_max_fallback(method, query, allowed_leaves):
    path = f"{C}/kubeconfig"
    for leaf in (INVENTORY, ACCESS_USER, CLUSTERS_EDITOR, WORKLOADS_EDITOR, CLUSTERS_ADMIN, ACCESS_ADMIN):
        assert await _allowed(method, path, ["member", leaf], query=query) is (leaf in allowed_leaves)


@pytest.mark.parametrize("query", [b"grade=root", b"grade=", b"grade=user&grade=admin", b"grade=admin&grade=user"])
async def test_ambiguous_or_unknown_credential_grade_is_rejected(query):
    assert await _status("GET", f"{C}/kubeconfig", ["member", *ADMIN_GRADE], query=query) == 422


@pytest.mark.parametrize(
    "body,roles,allowed",
    [
        (b'{"name": "k"}', [CLUSTERS_EDITOR], True),
        (b'{"name": "k", "key_name": null}', [CLUSTERS_EDITOR], True),
        (b'{"name": "k", "key_name": ""}', [CLUSTERS_EDITOR], True),
        (b'{"name": "k", "key_name": "ops"}', [CLUSTERS_EDITOR], False),
        (b'{"name": "k", "key_name": "ops"}', [CLUSTERS_EDITOR, WORKLOADS_EDITOR], False),
        (b'{"name": "k", "key_name": "ops"}', [ACCESS_ADMIN], False),
        (b'{"name": "k", "key_name": "ops"}', [CLUSTERS_EDITOR, ACCESS_ADMIN], True),
    ],
)
async def test_cluster_create_key_name_injection_needs_access_admin(body, roles, allowed):
    assert await _allowed("POST", "/v1/clusters/async", ["member", *roles], body) is allowed


@pytest.mark.parametrize("method,path", [("POST", f"{NS}/secrets"), ("PUT", f"{NS}/secrets/s")])
async def test_non_opaque_secret_writes_need_access_admin(method, path):
    assert await _allowed(method, path, ["member", WORKLOADS_EDITOR], b'{"name": "s", "data": {}}')
    assert await _allowed(method, path, ["member", WORKLOADS_EDITOR], b'{"type": "Opaque"}')
    tls = b'{"type": "kubernetes.io/tls"}'
    assert not await _allowed(method, path, ["member", WORKLOADS_EDITOR], tls)
    assert await _allowed(method, path, ["member", ACCESS_ADMIN], tls)


async def test_peeked_create_body_remains_replayable_for_forwarding():
    body = b'{"name": "k", "key_name": "ops"}'
    request = _request("POST", body)
    principal = {"roles": ["member", CLUSTERS_EDITOR, ACCESS_ADMIN], "is_system_admin": False}
    await authorize_drover_request(request, "/v1/clusters/async", principal)
    assert b"".join([chunk async for chunk in request.stream()]) == body


async def test_reader_baseline_admits_inventory_but_not_credentials():
    assert await _allowed("GET", "/v1/clusters", ["reader", INVENTORY])
    assert not await _allowed("GET", f"{C}/kubeconfig", ["reader", INVENTORY, ACCESS_USER])


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/v1/cluster-templates"),
        ("PATCH", "/v1/cluster-templates/t-1"),
        ("DELETE", "/v1/cluster-templates/t-1"),
        ("GET", "/v1/admin/clusters"),
        ("GET", f"/v1/admin/clusters/{CLUSTER}/kubeconfig"),
        ("DELETE", f"/v1/admin/clusters/{CLUSTER}"),
        ("POST", f"/v1/admin/clusters/{CLUSTER}/rotate-certs"),
        ("GET", "/v1/admin/cluster-templates"),
        ("GET", "/v1/admin/managed-resources"),
        ("GET", "/v1/admin/resource-policies"),
        ("GET", "/v1/admin/resource-policies/catalog/k3s.flavor"),
        ("PUT", "/v1/admin/resource-policies/k3s.flavor"),
        ("GET", "/v1/admin/runtime-settings"),
        ("PUT", "/v1/admin/runtime-settings/k3s.version"),
    ],
)
async def test_templates_and_global_config_are_verified_system_only(method, path):
    assert not await _allowed(method, path, ["member", *ADMIN_GRADE])
    assert not await _allowed(method, path, ["member", "admin", *ADMIN_GRADE])
    assert await _allowed(method, path, [], system=True)


async def test_verified_system_admin_bypasses_project_grade_gates():
    assert await _allowed("DELETE", C, [], system=True)
    assert await _allowed("GET", f"{C}/kubeconfig", [], query=b"grade=admin", system=True)


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/v1/callback"),
        ("GET", f"{C}/shell"),
        ("POST", "/v1/admin/clusters"),
        ("GET", f"{C}/namespaces/drover-workload-abc"),
        ("GET", "/v2/clusters"),
        ("GET", f"{C}/../../admin/clusters"),
        ("DELETE", f"/v1/clusters/{CLUSTER}%2Fnodegroups%2Fng-1"),
        ("GET", f"{C}//kubeconfig"),
        ("GET", f"{C}?grade=admin/kubeconfig"),
        ("GET", "/v1/v1/clusters"),
    ],
)
async def test_unknown_machine_and_ambiguous_paths_fail_closed_even_for_system(method, path):
    assert not await _allowed(method, path, ["member", *ADMIN_GRADE])
    assert not await _allowed(method, path, [], system=True)


async def test_options_preflight_has_no_action_guard():
    assert await _allowed("OPTIONS", C, [])


@pytest.fixture
async def bff(monkeypatch):
    """The registered Drover BFF routes; only the Keystone/upstream boundaries are synthetic."""
    real_client = httpx.AsyncClient
    upstream: list[httpx.Request] = []
    current = {"roles": ["member"]}
    session = {"system": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        # Network responses stay unread until the BFF's aiter_raw bridge consumes them.
        return httpx.Response(
            200, stream=httpx.ByteStream(b'{"ok":true}'), headers={"content-type": "application/json"}
        )

    def upstream_client(**kwargs):
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    async def identity(request: Request):
        # Stale session claims carry every leaf; only CURRENT access may authorize.
        info = {
            "token": "keystone-token",
            "project_id": PROJECT,
            "user_id": USER,
            "roles": ["member", *ADMIN_GRADE],
            "is_system_admin": session["system"],
        }
        request.state.token_info = info
        return info

    app = FastAPI()
    app.include_router(drover_proxy_router, prefix="/api/v1/k3s")
    app.include_router(drover_admin_router, prefix="/api/v1/admin")
    app.dependency_overrides[deps.get_token_info] = identity
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(side_effect=lambda *_: dict(current)))
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_: "http://drover.internal")
    monkeypatch.setattr(httpx, "AsyncClient", upstream_client)
    async with real_client(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, current, upstream, session


async def test_kubeconfig_grade_is_forwarded_only_after_exact_gate(bff):
    client, current, upstream, _ = bff
    path = f"/api/v1/k3s/clusters/{CLUSTER}/kubeconfig"
    current["roles"] = ["member", INVENTORY, ACCESS_USER, WORKLOADS_EDITOR]
    assert (await client.get(path, params={"grade": "admin"})).status_code == 403
    assert (await client.get(path, params=[("grade", "user"), ("grade", "admin")])).status_code == 422
    assert upstream == []
    assert (await client.get(path)).status_code == 200
    assert (await client.get(path, params={"grade": "editor"})).status_code == 200
    assert [(request.url.path, request.url.query) for request in upstream] == [
        (f"/v1/clusters/{CLUSTER}/kubeconfig", b""),
        (f"/v1/clusters/{CLUSTER}/kubeconfig", b"grade=editor"),
    ]


async def test_workloads_editor_without_access_leaf_has_no_default_credential(bff):
    client, current, upstream, _ = bff
    current["roles"] = ["member", INVENTORY, WORKLOADS_EDITOR]
    assert (await client.get(f"/api/v1/k3s/clusters/{CLUSTER}/kubeconfig")).status_code == 403
    assert upstream == []


async def test_create_body_is_peeked_and_forwarded_intact(bff):
    client, current, upstream, _ = bff
    body = b'{"name": "k", "key_name": "ops", "network_id": "n"}'
    current["roles"] = ["member", INVENTORY, CLUSTERS_EDITOR]
    response = await client.post(
        "/api/v1/k3s/clusters/async", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 403
    assert upstream == []
    current["roles"].append(ACCESS_ADMIN)
    response = await client.post(
        "/api/v1/k3s/clusters/async", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 200
    assert upstream[-1].content == body


async def test_tenant_catch_all_cannot_reach_admin_or_callback_routes(bff):
    client, current, upstream, _ = bff
    current["roles"] = ["member", *ADMIN_GRADE]
    assert (await client.get("/api/v1/k3s/admin/clusters")).status_code == 403
    assert (await client.get(f"/api/v1/k3s/admin/clusters/{CLUSTER}/kubeconfig")).status_code == 403
    assert (await client.put("/api/v1/k3s/admin/runtime-settings/k3s.version", json={})).status_code == 403
    assert (await client.post("/api/v1/k3s/callback", json={})).status_code == 403
    assert (await client.get(f"/api/v1/k3s/clusters/{CLUSTER}/%252E%252E/admin/clusters")).status_code == 403
    assert upstream == []


async def test_current_downgrade_denies_destructive_actions_before_upstream(bff):
    client, current, upstream, _ = bff
    current["roles"] = ["member", *EDITOR_GRADE]
    assert (await client.delete(f"/api/v1/k3s/clusters/{CLUSTER}")).status_code == 403
    assert (await client.post(f"/api/v1/k3s/clusters/{CLUSTER}/rotate-certs")).status_code == 403
    assert upstream == []
    body = b'{"node_count": 3}'
    response = await client.patch(
        f"/api/v1/k3s/clusters/{CLUSTER}/scale", content=body, headers={"content-type": "application/json"}
    )
    assert response.status_code == 200
    assert upstream[-1].content == body


async def test_verified_system_admin_router_reaches_global_admin_route(bff):
    client, _, upstream, session = bff
    session["system"] = True
    response = await client.get(f"/api/v1/admin/k3s-clusters/{CLUSTER}/kubeconfig")
    assert response.status_code == 200
    assert upstream[-1].url.path == f"/v1/admin/clusters/{CLUSTER}/kubeconfig"
    project_service.get_project_access.assert_not_called()
