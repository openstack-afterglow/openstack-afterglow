"""Current directory failures never fall back to cached browser token roles."""

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request

from app.api.deps import get_token_info
from app.api.lumen.proxy import router
from app.services import identity_roles, project_service, service_authorization, service_permissions, service_proxy
from app.services.service_permissions import ROLE_IMPLICATIONS, ROLE_PRESETS


@pytest.fixture
async def boundary(monkeypatch):
    def rid(name):
        return f"id-{name}"

    names = ["admin", "manager", "member", "reader", *(row["name"] for row in ROLE_PRESETS)]
    rows = [{"id": rid(name), "name": name} for name in names]
    edges = [
        {"prior_role": {"id": rid(prior)}, "implies": [{"id": rid(implied)}]} for prior, implied in ROLE_IMPLICATIONS
    ]
    state = SimpleNamespace(grants=["project_member"], catalog=identity_roles._catalog(rows, edges), admitted=[])

    def assignments(**kwargs):
        assert kwargs == {"project": "project", "effective": True}
        return [
            {"user": {"id": "actor"}, "role": {"id": rid(name)}, "scope": {"project": {"id": "project"}}}
            for name in state.grants
        ]

    monkeypatch.setattr(
        project_service.keystone,
        "_get_admin_ks_client",
        lambda: SimpleNamespace(role_assignments=SimpleNamespace(list=assignments)),
    )
    monkeypatch.setattr(identity_roles, "_trusted_catalog", lambda: state.catalog)
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *_: "http://native/v1")
    upstream = FastAPI()

    @upstream.post("/v1/temp-completions", status_code=202)
    async def admission(request: Request):
        body = await request.json()
        state.admitted.append(body["parts"][0]["text"])
        return {"run_id": "run-1", "status": "queued"}

    @upstream.get("/v1/chat/models")
    async def models():
        return [{"id": "model"}]

    client_type = httpx.AsyncClient
    monkeypatch.setattr(
        service_proxy.httpx,
        "AsyncClient",
        lambda **kwargs: client_type(transport=httpx.ASGITransport(app=upstream), **kwargs),
    )
    bff = FastAPI()
    bff.include_router(router, prefix="/api/v1/chat")

    async def authenticated(request: Request):
        # Stale project-owner claims must not replace the current directory lookup.
        principal = {
            "token": "synthetic",
            "user_id": "actor",
            "project_id": "project",
            "roles": ["project_owner", "project_admin", "project_member", "member"],
            "is_system_admin": False,
        }
        request.state.token_info = principal
        return principal

    bff.dependency_overrides[get_token_info] = authenticated
    async with client_type(transport=httpx.ASGITransport(app=bff), base_url="http://browser") as client:
        yield state, client


@pytest.mark.asyncio
async def test_directory_outage_does_not_use_stale_token_parent(boundary, monkeypatch):
    state, client = boundary

    def unavailable():
        raise RuntimeError("directory unavailable")

    monkeypatch.setattr(identity_roles, "_trusted_catalog", unavailable)
    assert (await client.get("/api/v1/chat/models")).status_code == 503
    assert state.admitted == []


EXPECTED_CAPABILITIES = {
    "waygate": (
        "waygate-inventory_reader",
        "waygate-connect_user",
        "waygate-clients_editor",
        "waygate-gateways_editor",
        "waygate-clients_admin",
        "waygate-gateways_admin",
        "waygate-routing_admin",
    ),
    "lumen": (
        "lumen-inventory_reader",
        "lumen-history_reader",
        "lumen-chat_user",
        "lumen-images_user",
        "lumen-audio_user",
        "lumen-tools_user",
        "lumen-assets_editor",
        "lumen-agents_editor",
        "lumen-mcp_editor",
        "lumen-keys_editor",
        "lumen-history_editor",
        "lumen-resources_admin",
    ),
    "drover": (
        "drover-inventory_reader",
        "drover-access_user",
        "drover-clusters_editor",
        "drover-workloads_editor",
        "drover-clusters_admin",
        "drover-access_admin",
    ),
    "palimpsest": (
        "palimpsest-inventory_reader",
        "palimpsest-download_user",
        "palimpsest-publish_editor",
        "palimpsest-keys_editor",
        "palimpsest-keys_admin",
    ),
}


def test_capability_registry_is_separate_from_assignable_project_role_hierarchy():
    assert service_permissions.SERVICE_CAPABILITIES == EXPECTED_CAPABILITIES
    expected_roles = {
        "project_owner",
        "project_admin",
        "project_member",
        "project_reader",
    }
    assert {row["name"] for row in ROLE_PRESETS} == expected_roles
    assert set(ROLE_IMPLICATIONS) == {
        ("project_owner", "project_admin"),
        ("project_admin", "project_member"),
        ("project_member", "project_reader"),
        ("project_member", "member"),
        ("project_reader", "reader"),
    }
    expected_retired = {
        f"{service}_{grade}" for service in EXPECTED_CAPABILITIES for grade in ("reader", "user", "editor", "admin")
    } | {action for actions in EXPECTED_CAPABILITIES.values() for action in actions}
    assert service_permissions.RETIRED_SERVICE_ROLE_NAMES == expected_retired
    assert expected_roles.isdisjoint(expected_retired)
    preview = service_permissions.preset_preview()
    assert preview["roles"] == []
    assert {row["name"] for row in preview["project_roles"]} == expected_roles


@pytest.mark.parametrize("name", sorted(service_permissions.RETIRED_SERVICE_ROLE_NAMES))
def test_retired_service_role_names_cannot_be_recreated(name):
    with pytest.raises(ValueError, match="Retired service roles"):
        service_permissions.normalize_role_name(name.upper())


@pytest.mark.parametrize("name", ["project_owner", "project_admin", "project_member", "project_reader", "lumen_custom"])
def test_standard_and_unrelated_custom_roles_remain_valid(name):
    assert service_permissions.normalize_role_name(name) == name


@pytest.mark.parametrize("projected", [None, [], "lumen-chat_user"])
def test_invalid_capability_projection_does_not_use_project_or_retired_roles(projected):
    principal = {
        "roles": ["project_owner", "member", "lumen_admin", "lumen-chat_user"],
        "is_system_admin": True,
        "service_permissions": projected,
    }
    assert service_permissions.service_permissions(principal) == {service: [] for service in EXPECTED_CAPABILITIES}
    with pytest.raises(HTTPException) as denied:
        service_permissions.require_service_permission(principal, "lumen-chat_user")
    assert denied.value.status_code == 403


def test_native_projection_filters_unknown_cross_service_and_role_names_without_mutation():
    projected = {
        "lumen": ["lumen-tools_user", "lumen-chat_user", "lumen-tools_user", "drover-access_user", "lumen_admin"],
        "drover": ["drover-access_user", "drover-future_admin", "project_owner"],
        "unknown": ["waygate-connect_user"],
    }
    principal = {"roles": ["project_reader"], "service_permissions": projected}
    assert service_permissions.service_permissions(principal) == {
        "waygate": [],
        "lumen": ["lumen-chat_user", "lumen-tools_user"],
        "drover": ["drover-access_user"],
        "palimpsest": [],
    }
    service_permissions.require_service_permission(principal, "lumen-chat_user", "drover-access_user")
    with pytest.raises(HTTPException) as denied:
        service_permissions.require_service_permission(principal, "lumen-chat_user", "waygate-connect_user")
    assert denied.value.status_code == 403
    assert projected["lumen"].count("lumen-tools_user") == 2
    assert projected["unknown"] == ["waygate-connect_user"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "roles",
    [
        ["project_owner", "project_admin", "project_member", "project_reader", "member", "reader"],
        ["lumen_admin", "lumen-chat_user", "drover_admin", "waygate_admin", "palimpsest_admin"],
    ],
)
async def test_native_policy_outage_never_fabricates_capabilities_from_roles(monkeypatch, roles):
    monkeypatch.setattr(
        service_authorization,
        "service_policy_availability",
        lambda: {service: True for service in EXPECTED_CAPABILITIES},
    )
    principal = {"token": "original-subject", "project_id": "project", "roles": roles, "is_system_admin": True}
    observed = []

    async def unavailable(service, actual):
        assert actual is principal
        observed.append(service)
        raise service_proxy.NativePolicyError(503, "policy_unreachable")

    monkeypatch.setattr(service_proxy, "get_policy_capabilities", unavailable)
    permissions, errors = await service_authorization.service_permission_snapshot(principal)
    assert permissions == {service: [] for service in EXPECTED_CAPABILITIES}
    assert errors == {service: "policy_unreachable" for service in EXPECTED_CAPABILITIES}
    assert set(observed) == set(EXPECTED_CAPABILITIES)


@pytest.mark.asyncio
@pytest.mark.parametrize("services", [None, (), ("drover", "waygate"), ("unknown",)])
async def test_native_policy_snapshot_service_filter_is_opt_in_and_preserves_availability(monkeypatch, services):
    availability = {"lumen": True, "drover": True, "waygate": False}
    monkeypatch.setattr(service_authorization, "service_policy_availability", lambda: availability)
    observed = []

    async def policy(service, principal):
        assert principal == {"token": "exact-subject"}
        observed.append(service)
        return {"capabilities": [service + "-inventory_reader"]}

    monkeypatch.setattr(service_proxy, "get_policy_capabilities", policy)
    permissions, errors = await service_authorization.service_permission_snapshot(
        {"token": "exact-subject"}, services=services
    )
    expected = {
        service: [service + "-inventory_reader"] if enabled else []
        for service, enabled in availability.items()
        if services is None or service in services
    }
    assert permissions == expected and errors == {}
    assert set(observed) == {service for service in expected if availability[service]}
    assert service_authorization.service_policy_availability() == {"lumen": True, "drover": True, "waygate": False}


@pytest.mark.asyncio
async def test_native_policy_snapshot_timeout_is_opt_in_and_preserves_other_services(monkeypatch):
    availability = {"lumen": True, "drover": True, "waygate": False}
    monkeypatch.setattr(service_authorization, "service_policy_availability", lambda: availability)
    started = asyncio.Event()
    release = asyncio.Event()
    canceled = asyncio.Event()
    observed = []

    async def policy(service, principal, *, timeout=None):
        assert principal == {"token": "exact-subject"}
        observed.append(service)
        if service == "lumen":
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                canceled.set()
                raise
        return {"capabilities": [service + "-inventory_reader"]}

    monkeypatch.setattr(service_proxy, "get_policy_capabilities", policy)
    permissions, errors = await service_authorization.service_permission_snapshot(
        {"token": "exact-subject"}, timeout=0.01
    )
    assert permissions == {"lumen": [], "drover": ["drover-inventory_reader"], "waygate": []}
    assert errors == {"lumen": "policy_timeout"} and canceled.is_set()
    assert "waygate" not in observed

    started.clear()
    canceled.clear()
    task = asyncio.create_task(service_authorization.service_permission_snapshot({"token": "exact-subject"}))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        assert not task.done()
        assert not canceled.is_set()
    finally:
        release.set()
    permissions, errors = await task
    assert permissions["lumen"] == ["lumen-inventory_reader"] and errors == {}


@pytest.mark.asyncio
async def test_preview_policy_failure_is_sanitized_without_changing_default_consumers(monkeypatch):
    monkeypatch.setattr(service_authorization, "service_policy_availability", lambda: {"lumen": True})

    async def unavailable(service, principal, *, timeout=None):
        raise RuntimeError("native-token-private-endpoint")

    monkeypatch.setattr(service_proxy, "get_policy_capabilities", unavailable)
    assert await service_authorization.service_permission_snapshot({}, timeout=5.0) == (
        {"lumen": []},
        {"lumen": "permission_check_unavailable"},
    )
    with pytest.raises(RuntimeError, match="native-token-private-endpoint"):
        await service_authorization.service_permission_snapshot({})


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_preview_policy_catalog_thread_is_transport_bounded_and_drained(monkeypatch, cancel):
    timeout = 5.0 if cancel else 0.02
    entered, finished, closed = threading.Event(), threading.Event(), threading.Event()
    release = threading.Event()
    monkeypatch.setattr(service_authorization, "service_policy_availability", lambda: {"drover": True})
    monkeypatch.setattr(service_proxy, "_configured_internal_endpoint", lambda service: None)
    monkeypatch.setattr(service_proxy, "get_settings", lambda: SimpleNamespace(ssl_verify=True))

    def connect(token, project_id, *, api_timeout=30):
        assert (token, project_id, api_timeout) == ("exact-subject", "project", timeout)

        def endpoint(**kwargs):
            assert kwargs == {"service_type": "drover", "interface": "internal"}
            entered.set()
            try:
                release.wait(2 if cancel else api_timeout)
                return None
            finally:
                finished.set()

        def close():
            assert finished.is_set()
            closed.set()

        return SimpleNamespace(session=SimpleNamespace(get_endpoint=endpoint), close=close)

    monkeypatch.setattr(service_proxy.keystone, "get_openstack_connection", connect)
    task = asyncio.create_task(
        service_authorization.service_permission_snapshot(
            {"token": "exact-subject", "project_id": "project"}, timeout=timeout
        )
    )
    try:
        assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), timeout=3)
        if cancel:
            task.cancel()
            await asyncio.sleep(0)
            assert not task.done() and not closed.is_set()
    finally:
        if cancel:
            release.set()
    if cancel:
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        assert await task == ({"drover": []}, {"drover": "policy_timeout"})
    assert finished.is_set() and closed.is_set()
