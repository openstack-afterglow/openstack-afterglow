"""Consumer-visible authorization and availability boundaries for cloud tools."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_token_info
from app.api.identity import mcp_access
from app.api.lumen import proxy as proxy_module
from app.services import service_proxy
from app.services.mcp_control_plane import authority, defaults, lumen

_PATH = "/api/v1/chat/cloud-tools"
_BROWSER_HEADERS = {"Origin": "https://app.example.test", "Sec-Fetch-Site": "same-site"}


@pytest.fixture
def cloud_app(monkeypatch):
    app = FastAPI()
    app.include_router(proxy_module.router, prefix="/api/v1/chat")
    app.state.cloud_token_roles = ["member"]
    current_access = AsyncMock(return_value={"roles": ["member"], "is_manager": False})
    app.state.cloud_access = current_access
    monkeypatch.setattr("app.services.project_service.get_project_access", current_access)

    async def token_info(request: Request):
        info = {
            "user_id": "user-a",
            "project_id": "project-a",
            "project_name": "Project A",
            "token": "synthetic-caller-token",
            "roles": app.state.cloud_token_roles,
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[get_token_info] = token_info
    settings = SimpleNamespace(
        service_mcp_enabled=True,
        lumen_mcp_service_token="synthetic-workload-token",
        frontend_base_url="https://app.example.test",
        public_api_base="https://api.example.test",
        cors_origin_list=[],
    )
    app.state.cloud_settings = settings
    monkeypatch.setattr(proxy_module, "get_settings", lambda: settings)
    monkeypatch.setattr(mcp_access, "get_settings", lambda: settings)
    return app


@pytest.fixture
def cloud_permission(monkeypatch):
    native = AsyncMock(return_value={"service": "lumen", "capabilities": ["lumen-tools_user"], "actions": []})
    monkeypatch.setattr(proxy_module, "get_policy_capabilities", native)
    return native


@pytest.fixture
def cloud_delegation(monkeypatch):
    selected = AsyncMock(return_value=None)
    approve = AsyncMock(return_value={"token": "synthetic-personal-bearer"})
    disable = AsyncMock(return_value={"credential_ciphertext": "synthetic-ciphertext"})
    create_credentials = AsyncMock()
    monkeypatch.setattr(lumen, "selected_lumen_snapshot", selected)
    monkeypatch.setattr(defaults, "approve_lumen_grant", approve)
    monkeypatch.setattr(defaults, "disable_lumen_grant", disable)
    monkeypatch.setattr(authority, "create_grant_credentials", create_credentials)
    return SimpleNamespace(selected=selected, approve=approve, disable=disable, create_credentials=create_credentials)


def _selected_catalogue(monkeypatch, *, access_level="read", source="lumen"):
    snapshot = lumen.LumenGrantSnapshot("grant-a", "user-a", "project-a", 3, 7)
    target_id, target_name = ("project-b", "Project B") if source == "personal_token" else ("project-a", "Project A")
    principal = SimpleNamespace(can_write=access_level == "manage", project_id=target_id)
    metadata = {
        "access_level": access_level,
        "project_id": target_id,
        "project_name": target_name,
        "source": source,
        "allowed_projects": [{"id": target_id, "name": target_name}],
        "selection_name": "My explicit key" if source == "personal_token" else None,
        "expires_at": "2026-10-12T00:00:00+00:00",
    }
    resolve = AsyncMock(return_value=principal)
    describe = AsyncMock(return_value=metadata)
    monkeypatch.setattr(lumen, "resolve_lumen_principal", resolve)
    monkeypatch.setattr(lumen, "selected_lumen_metadata", describe)
    monkeypatch.setattr(
        proxy_module.registry, "enabled_entries", lambda actual: ("read", "manage") if actual.can_write else ("read",)
    )
    return SimpleNamespace(
        snapshot=snapshot, principal=principal, metadata=metadata, resolve=resolve, describe=describe
    )


def _assert_no_store(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def _assert_secret_free(response):
    for secret in (
        "synthetic-caller-token",
        "synthetic-workload-token",
        "synthetic-application-secret",
        "synthetic-personal-bearer",
        "synthetic-ciphertext",
    ):
        assert secret not in response.text
    for field in ("credential_ciphertext", "application_credential_secret", "token", "snapshot", "grant_id"):
        assert f'"{field}"' not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("roles", [["member"], ["lumen-user"], ["lumen-tools_user"]])
async def test_cloud_catalogue_requires_native_tool_permission_not_token_roles(
    cloud_app, cloud_permission, cloud_delegation, roles
):
    cloud_app.state.cloud_token_roles = roles
    cloud_app.state.cloud_access.return_value = {"roles": roles, "is_manager": False}
    cloud_permission.return_value = {"service": "lumen", "capabilities": ["lumen-chat_user"], "actions": []}
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        denied = await client.get("/api/v1/chat/cloud-tools")
    assert denied.status_code == 403
    assert "lumen-tools_user" in denied.json()["detail"]
    cloud_permission.assert_awaited_once()
    service, principal = cloud_permission.await_args.args
    assert service == "lumen"
    assert principal["token"] == "synthetic-caller-token"
    assert principal["user_id"] == "user-a"
    assert principal["project_id"] == "project-a"
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(denied)
    _assert_secret_free(denied)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_cloud_tools_require_current_membership_even_when_native_policy_allows(
    cloud_app, cloud_permission, cloud_delegation, method
):
    cloud_app.state.cloud_token_roles = ["member", "lumen-tools_user"]
    cloud_app.state.cloud_access.return_value = {"roles": [], "is_manager": False}
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "read"} if method == "POST" else None, headers=_BROWSER_HEADERS
        )
    assert response.status_code == 403
    assert response.json()["detail"] == "Current project membership is required"
    cloud_permission.assert_not_awaited()
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["GET", "POST", "DELETE"])
async def test_native_policy_outage_never_falls_back_to_token_roles_or_cloud_selection(
    cloud_app, cloud_permission, cloud_delegation, method
):
    cloud_app.state.cloud_token_roles = ["member", "lumen-tools_user"]
    cloud_permission.side_effect = HTTPException(status_code=503, detail="Native service policy is unavailable")
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "manage"} if method == "POST" else None, headers=_BROWSER_HEADERS
        )
    assert response.status_code == 503
    assert "enabled" not in response.json()
    cloud_permission.assert_awaited_once()
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
async def test_cloud_authority_outage_does_not_claim_available_catalogue(cloud_app, cloud_permission, cloud_delegation):
    cloud_delegation.selected.side_effect = lumen.McpLumenAuthorityError("synthetic-application-secret")
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        unavailable = await client.get("/api/v1/chat/cloud-tools")
    assert unavailable.status_code == 503
    assert "enabled" not in unavailable.json()
    cloud_delegation.selected.assert_awaited_once_with(user_id="user-a", project_id="project-a")
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(unavailable)
    _assert_secret_free(unavailable)


@pytest.mark.asyncio
async def test_cloud_catalogue_is_off_before_explicit_approval(cloud_app, cloud_permission, cloud_delegation):
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.get(_PATH)
    assert response.status_code == 200
    assert response.json() == {
        "enabled": False,
        "available": True,
        "access_level": "read",
        "project_id": "project-a",
        "project_name": "Project A",
        "source": "lumen",
        "allowed_projects": [],
        "selection_name": None,
        "expires_at": None,
        "tool_count": 0,
    }
    cloud_delegation.selected.assert_awaited_once_with(user_id="user-a", project_id="project-a")
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["lumen", "personal_token"])
@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_cloud_catalogue_preserves_valid_selection_metadata(
    cloud_app, cloud_permission, cloud_delegation, monkeypatch, source, access_level
):
    catalogue = _selected_catalogue(monkeypatch, access_level=access_level, source=source)
    cloud_delegation.selected.return_value = catalogue.snapshot
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.get(_PATH)
    assert response.status_code == 200
    assert response.json() == {
        **catalogue.metadata,
        "enabled": True,
        "available": True,
        "tool_count": 2 if access_level == "manage" else 1,
    }
    catalogue.resolve.assert_awaited_once_with(catalogue.snapshot)
    catalogue.describe.assert_awaited_once_with(catalogue.snapshot)
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["resolve_lumen_principal", "selected_lumen_metadata"])
async def test_cloud_catalogue_rejects_selection_changed_during_discovery(
    cloud_app, cloud_permission, cloud_delegation, monkeypatch, boundary
):
    catalogue = _selected_catalogue(monkeypatch)
    cloud_delegation.selected.return_value = catalogue.snapshot
    changed_selection = AsyncMock(side_effect=lumen.McpLumenAuthorityError("synthetic-application-secret"))
    monkeypatch.setattr(lumen, boundary, changed_selection)
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.get(_PATH)
    assert response.status_code == 503
    assert "enabled" not in response.json()
    changed_selection.assert_awaited_once_with(catalogue.snapshot)
    cloud_delegation.selected.assert_awaited_once_with(user_id="user-a", project_id="project-a")
    if boundary == "resolve_lumen_principal":
        catalogue.describe.assert_not_awaited()
    else:
        catalogue.resolve.assert_awaited_once_with(catalogue.snapshot)
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ["service", "workload_token"])
async def test_cloud_catalogue_reports_unavailable_without_loading_selection(
    cloud_app, cloud_permission, cloud_delegation, unavailable
):
    if unavailable == "service":
        cloud_app.state.cloud_settings.service_mcp_enabled = False
    else:
        cloud_app.state.cloud_settings.lumen_mcp_service_token = ""
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.get(_PATH)
    assert response.status_code == 200
    assert response.json()["available"] is False
    assert response.json()["enabled"] is False
    assert response.json()["tool_count"] == 0
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.approve.assert_not_awaited()
    _assert_no_store(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("allowed", [False, True], ids=["denied", "allowed"])
@pytest.mark.parametrize(
    "path",
    ["temp-completions", "conversations/conversation-a/completions", "conversations/conversation-a/regenerate"],
)
async def test_native_chat_preserves_native_policy_decision_without_creating_cloud_credential(
    cloud_app, cloud_delegation, monkeypatch, allowed, path
):
    # The action handler, not a BFF role/route table, owns current native policy
    # and reduced-credential ceilings. Both decisions use the same caller roles.
    native_body = {"accepted": True} if allowed else {"detail": "Native tool policy denied"}
    native_status = 202 if allowed else 403
    monkeypatch.setattr(service_proxy, "_get_internal_endpoint", lambda *args: "http://lumen.example.test")
    forwarded = AsyncMock(return_value=JSONResponse(native_body, status_code=native_status))
    monkeypatch.setattr(service_proxy, "_forward", forwarded)
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/chat/{path}", json={"features": {"tool_policy": {"mode": "agent_default"}}}
        )
    assert response.status_code == native_status
    assert response.json() == native_body
    forwarded.assert_awaited_once()
    args, kwargs = forwarded.await_args
    assert args[0] == "lumen"
    assert args[2] == f"/v1/{path}"
    assert kwargs["headers"]["x-auth-token"] == "synthetic-caller-token"
    assert kwargs["headers"]["x-project-id"] == "project-a"
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("access_level", ["read", "manage"])
async def test_explicit_cloud_approval_and_disable_route_shared_delegation(
    cloud_app, cloud_permission, cloud_delegation, monkeypatch, access_level
):
    catalogue = _selected_catalogue(monkeypatch, access_level=access_level)

    async def approve(**kwargs):
        cloud_delegation.selected.return_value = catalogue.snapshot
        return {"application_credential_secret": "synthetic-application-secret"}

    async def disable(**kwargs):
        cloud_delegation.selected.return_value = None
        return {"token": "synthetic-personal-bearer"}

    cloud_delegation.approve.side_effect = approve
    cloud_delegation.disable.side_effect = disable
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        before = await client.get(_PATH)
        approved = await client.post(_PATH, json={"access_level": access_level}, headers=_BROWSER_HEADERS)
        disabled = await client.delete(_PATH, headers=_BROWSER_HEADERS)
    assert before.status_code == 200
    assert before.json()["enabled"] is False
    assert approved.status_code == 200
    assert approved.json()["enabled"] is True
    assert approved.json()["access_level"] == access_level
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["available"] is True
    assert disabled.json()["allowed_projects"] == []
    assert disabled.json()["tool_count"] == 0
    info = {
        "user_id": "user-a",
        "project_id": "project-a",
        "project_name": "Project A",
        "token": "synthetic-caller-token",
        "roles": ["member"],
    }
    cloud_delegation.approve.assert_awaited_once_with(token_info=info, access_level=access_level)
    cloud_delegation.disable.assert_awaited_once_with(token_info=info)
    cloud_delegation.create_credentials.assert_not_awaited()
    for response in (before, approved, disabled):
        _assert_no_store(response)
        _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://app.example.test"},
        {"Origin": "https://attacker.example.test", "Sec-Fetch-Site": "same-site"},
        {"Origin": "https://app.example.test", "Sec-Fetch-Site": "cross-site"},
        {"Origin": "null", "Sec-Fetch-Site": "same-origin"},
    ],
)
async def test_cloud_mutations_require_same_site_browser(
    cloud_app, cloud_permission, cloud_delegation, method, headers
):
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "read"} if method == "POST" else None, headers=headers
        )
    assert response.status_code == 403
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "DELETE"])
async def test_cloud_mutations_require_current_tool_permission(cloud_app, cloud_permission, cloud_delegation, method):
    cloud_permission.return_value = {"service": "lumen", "capabilities": ["lumen-chat_user"], "actions": []}
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "read"} if method == "POST" else None, headers=_BROWSER_HEADERS
        )
    assert response.status_code == 403
    assert "lumen-tools_user" in response.json()["detail"]
    cloud_permission.assert_awaited_once()
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize("unavailable", ["service", "workload_token"])
async def test_cloud_mutations_refuse_unavailable_service(
    cloud_app, cloud_permission, cloud_delegation, method, unavailable
):
    if unavailable == "service":
        cloud_app.state.cloud_settings.service_mcp_enabled = False
    else:
        cloud_app.state.cloud_settings.lumen_mcp_service_token = ""
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "read"} if method == "POST" else None, headers=_BROWSER_HEADERS
        )
    assert response.status_code == 503
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.disable.assert_not_awaited()
    cloud_delegation.selected.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [{}, {"access_level": "admin"}, {"access_level": None}, {"access_level": True}])
async def test_cloud_approval_accepts_only_literal_read_or_manage(cloud_app, cloud_permission, cloud_delegation, body):
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.post(_PATH, json=body, headers=_BROWSER_HEADERS)
    assert response.status_code == 422
    cloud_delegation.approve.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["POST", "DELETE"])
@pytest.mark.parametrize(
    "error_type, expected",
    [
        (authority.McpGrantPrivilegeError, 403),
        (authority.McpGrantStateError, 409),
        (authority.McpGrantLimitError, 409),
        (authority.McpAuthorityError, 503),
    ],
)
async def test_cloud_mutation_errors_are_safe_and_state_conflicts_are_409(
    cloud_app, cloud_permission, cloud_delegation, method, error_type, expected
):
    mutation = cloud_delegation.approve if method == "POST" else cloud_delegation.disable
    mutation.side_effect = error_type("synthetic-application-secret synthetic-personal-bearer")
    async with AsyncClient(transport=ASGITransport(app=cloud_app), base_url="http://test") as client:
        response = await client.request(
            method, _PATH, json={"access_level": "manage"} if method == "POST" else None, headers=_BROWSER_HEADERS
        )
    assert response.status_code == expected
    assert (
        response.json()["detail"]
        == {
            403: "Lumen cloud management is not permitted",
            409: "Lumen cloud authority changed or is pending",
            503: "Lumen cloud authority is unavailable",
        }[expected]
    )
    mutation.assert_awaited_once()
    cloud_delegation.selected.assert_not_awaited()
    cloud_delegation.create_credentials.assert_not_awaited()
    _assert_no_store(response)
    _assert_secret_free(response)
