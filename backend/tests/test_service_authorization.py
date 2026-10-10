"""Current graph and independent media/tool gates at registered browser HTTP routes."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, Request

from app.api.deps import get_token_info
from app.api.lumen.proxy import router
from app.services import identity_roles, project_service, service_proxy
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
async def test_deleted_current_parent_edge_denies_new_run_but_keeps_discovery(boundary):
    state, client = boundary
    payload = {
        "model_id": "model",
        "parts": [{"type": "text", "text": "first"}],
        "features": {"memory": False, "tool_policy": {"mode": "none"}},
    }
    assert (await client.post("/api/v1/chat/temp-completions", json=payload)).status_code == 202
    parent = next(row for row in state.catalog if row["name"] == "lumen_user")
    parent["implied_role_ids"].remove("id-lumen-chat_user")
    payload["parts"][0]["text"] = "must not start"
    assert (await client.post("/api/v1/chat/temp-completions", json=payload)).status_code == 403
    assert state.admitted == ["first"]
    assert (await client.get("/api/v1/chat/models")).json() == [{"id": "model"}]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [
        {"features": {"output_modalities": ["text", "image"]}},
        {"features": {"output_modalities": ["text", "audio"]}},
        {"features": {"web_search": {"enabled": True}}},
        {"features": {"tool_policy": {"mode": "agent_default"}}},
        {"plugin_tool_ids": ["selected-tool"]},
        {"skill_ids": [1]},
        {"execution_mode": "code"},
    ],
)
async def test_chat_only_cannot_smuggle_media_or_tools_into_text_endpoint(boundary, extra):
    state, client = boundary
    state.grants = ["project_member", "lumen-chat_user"]
    payload = {
        "model_id": "model",
        "parts": [{"type": "text", "text": "plain text"}],
        "features": {"memory": False, "tool_policy": {"mode": "none"}},
    }
    assert (await client.post("/api/v1/chat/temp-completions", json=payload)).status_code == 202
    payload["features"].update(extra.get("features", {}))
    payload.update({key: value for key, value in extra.items() if key != "features"})
    assert (await client.post("/api/v1/chat/temp-completions", json=payload)).status_code == 403
    assert state.admitted == ["plain text"]


@pytest.mark.asyncio
async def test_project_owner_is_not_service_entitlement(boundary):
    state, client = boundary
    state.grants = ["project_owner"]
    assert (await client.get("/api/v1/chat/models")).status_code == 403
    assert state.admitted == []


@pytest.mark.asyncio
async def test_directory_outage_does_not_use_stale_token_parent(boundary, monkeypatch):
    state, client = boundary

    def unavailable():
        raise RuntimeError("directory unavailable")

    monkeypatch.setattr(identity_roles, "_trusted_catalog", unavailable)
    assert (await client.get("/api/v1/chat/models")).status_code == 503
    assert state.admitted == []
