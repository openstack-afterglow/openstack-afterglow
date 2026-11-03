"""Current directory failures never fall back to cached browser token roles."""

import asyncio
import threading
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import get_token_info
from app.api.lumen.proxy import router
from app.services import identity_roles, project_service, service_authorization, service_proxy
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
    state = SimpleNamespace(
        grants=["project_member", "lumen_user"], catalog=identity_roles._catalog(rows, edges), admitted=[]
    )

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
        # Old token claims intentionally retain the full service parent after a current downgrade.
        principal = {
            "token": "synthetic",
            "user_id": "actor",
            "project_id": "project",
            "roles": ["member", "lumen_admin"],
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
    assert errors == {"lumen": "permission_check_unavailable"} and canceled.is_set()
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
        assert await task == ({"drover": []}, {"drover": "permission_check_unavailable"})
    assert finished.is_set() and closed.is_set()
