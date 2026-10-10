"""Consumer-visible authorization boundaries; no forwarding/source-text mocks."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request, Response

from app.api.palimpsest import package_keys, packages
from app.config import get_settings
from app.services import keystone, project_service
from app.services.palimpsest_authorization import authorize_palimpsest_request

PROJECT = "11111111111141118111111111111111"
USER = "33333333333343338333333333333333"
IDENTIFIER = "44444444444444448444444444444444"
DIGEST = "sha256:" + "a" * 64
NAMESPACE = "p-" + PROJECT
INVENTORY = "palimpsest-inventory_reader"
DOWNLOAD = "palimpsest-download_user"
PUBLISH = "palimpsest-publish_editor"
KEYS_EDITOR = "palimpsest-keys_editor"
KEYS_ADMIN = "palimpsest-keys_admin"
BASE = "/api/v1/palimpsest"


@pytest.fixture
async def action_client(monkeypatch):
    """Exercise the public authorization API through HTTP, with no transport."""
    principal = {"user_id": USER, "project_id": PROJECT, "roles": ["member"], "is_system_admin": False}
    monkeypatch.setattr(keystone, "_has_system_admin_role", lambda *_: principal.get("verified_system_grant") is True)
    app = FastAPI()

    @app.api_route("/{path:path}", methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
    async def operation(path: str, request: Request):
        await authorize_palimpsest_request(request, "/" + path, principal)
        return Response(status_code=204)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, principal


@pytest.mark.parametrize(
    "method,path,leaves",
    [
        ("GET", "/v1/layers", [INVENTORY]),
        ("GET", "/v1/images", [INVENTORY]),
        ("GET", f"/v1/layers/{DIGEST}", [INVENTORY]),
        ("GET", f"/v1/layers/{DIGEST}/ancestors", [INVENTORY]),
        ("GET", "/v1/image-exports", [INVENTORY]),
        ("GET", f"/v1/image-exports/{IDENTIFIER}", [INVENTORY]),
        ("GET", f"/v1/layers/{DIGEST}/blob", [DOWNLOAD]),
        ("GET", f"/v1/image-exports/{IDENTIFIER}/blob", [DOWNLOAD]),
        ("POST", f"/v1/image-exports/{IDENTIFIER}/download-token", [DOWNLOAD]),
        ("POST", "/v1/bundles", [DOWNLOAD]),
        ("POST", "/v1/bundles/import", [PUBLISH]),
        ("POST", "/v1/image-exports", [PUBLISH]),
        ("DELETE", f"/v1/image-exports/{IDENTIFIER}", [PUBLISH]),
        ("POST", "/v1/uploads", [PUBLISH]),
        *[(method, f"/v1/uploads/{IDENTIFIER}", [PUBLISH]) for method in ("GET", "PATCH", "PUT", "DELETE")],
        ("PUT", f"/v1/projects/{PROJECT}/namespace", [PUBLISH]),
        *[
            ("GET", f"/v1/projects/{NAMESPACE}/{suffix}", [INVENTORY])
            for suffix in ("packages", "package", "versions", "resolve", f"versions/{DIGEST}")
        ],
        ("GET", f"/v1/projects/{NAMESPACE}/versions/{DIGEST}/download", [INVENTORY, DOWNLOAD]),
        ("GET", f"/v1/projects/{NAMESPACE}/versions/{DIGEST}/blobs/{DIGEST}", [INVENTORY, DOWNLOAD]),
        ("GET", f"/v1/projects/{NAMESPACE}/cache/resolve", [DOWNLOAD]),
        ("GET", f"/v1/projects/{NAMESPACE}/cache/archives/{DIGEST}", [DOWNLOAD]),
        *[("POST", f"/v1/projects/{NAMESPACE}/{root}", [PUBLISH]) for root in ("uploads", "cache/uploads")],
        *[
            (method, f"/v1/projects/{NAMESPACE}/{root}/{IDENTIFIER}", [PUBLISH])
            for root in ("uploads", "cache/uploads")
            for method in ("GET", "PATCH", "PUT", "DELETE")
        ],
        ("POST", f"/v1/projects/{NAMESPACE}/keys", [KEYS_EDITOR]),
        ("DELETE", f"/v1/projects/{NAMESPACE}/keys/{IDENTIFIER}", [KEYS_ADMIN]),
    ],
)
async def test_exact_action_leaves_not_method_or_parent_role(action_client, method, path, leaves):
    client, principal = action_client
    principal["roles"] = ["member", *leaves]
    assert (await client.request(method, path)).status_code == 204
    for missing in leaves:
        principal["roles"] = ["member", *[leaf for leaf in leaves if leaf != missing]]
        assert (await client.request(method, path)).status_code == 403
    principal["roles"] = ["member", "palimpsest_admin", "project_owner"]
    assert (await client.request(method, path)).status_code == 403


@pytest.mark.parametrize("leaf", [INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN])
async def test_context_does_not_require_download_or_inventory(action_client, leaf):
    client, principal = action_client
    principal["roles"] = ["member", leaf]
    for path in ("/v1/", "/v1/health", "/v1/projects/current"):
        assert (await client.get(path)).status_code == 204


@pytest.mark.parametrize("leaf", [KEYS_EDITOR, KEYS_ADMIN])
async def test_owner_key_metadata_is_editor_or_admin_not_download(action_client, leaf):
    client, principal = action_client
    principal["roles"] = ["member", leaf]
    assert (await client.get(f"/v1/projects/{NAMESPACE}/keys")).status_code == 204
    principal["roles"] = ["member", INVENTORY, DOWNLOAD, PUBLISH]
    assert (await client.get(f"/v1/projects/{NAMESPACE}/keys")).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [
        ("roles", ["admin", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN]),
        ("roles", ["manager", "member", PUBLISH]),
        ("roles", ["service", "member", PUBLISH]),
        ("is_system_admin", True),
        ("system_scope", True),
        ("domain_scope", True),
        ("connection_project_id", "22222222222242228222222222222222"),
    ],
)
async def test_protected_principal_has_no_package_or_publish_override(action_client, field, value):
    client, principal = action_client
    principal["roles"] = ["member", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN]
    principal[field] = value
    for method, path in [
        ("POST", "/v1/uploads"),
        ("GET", "/v1/projects/current"),
        ("PUT", f"/v1/projects/{PROJECT}/namespace"),
        ("POST", f"/v1/projects/{NAMESPACE}/keys"),
        ("GET", f"/v1/projects/{NAMESPACE}/versions/{DIGEST}/download"),
    ]:
        assert (await client.request(method, path)).status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/builds"),
        ("POST", "/v1/builds"),
        ("GET", f"/v1/builds/{IDENTIFIER}"),
        ("DELETE", f"/v1/layers/{DIGEST}"),
    ],
)
async def test_global_builder_and_gc_are_verified_system_only(action_client, method, path):
    client, principal = action_client
    principal["roles"] = ["member", "palimpsest_admin", PUBLISH, KEYS_ADMIN, "admin"]
    assert (await client.request(method, path)).status_code == 403
    principal["is_system_admin"] = True
    # The compatibility admin-project flag alone is not a system grant.
    assert (await client.request(method, path)).status_code == 403
    principal["verified_system_grant"] = True
    assert (await client.request(method, path)).status_code == 204


async def test_system_exception_is_legacy_reads_only(action_client):
    client, principal = action_client
    principal["roles"] = ["admin"]
    principal["is_system_admin"] = True
    principal["verified_system_grant"] = True
    for method, path in [("GET", "/v1/layers"), ("GET", f"/v1/layers/{DIGEST}/blob"), ("POST", "/v1/bundles")]:
        assert (await client.request(method, path)).status_code == 204
    assert (await client.post("/v1/bundles/import")).status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/v1/unknown"),
        ("GET", "/v1/builds/extra/operation"),
        ("GET", "/v1/admin/layers"),
        ("POST", "/v1/publish"),
        ("GET", f"/v1/projects/{NAMESPACE}/tags"),
        ("PUT", f"/v1/projects/{NAMESPACE}/tags/latest"),
        ("GET", f"/v1/projects/{NAMESPACE}/manifest"),
        ("GET", "/v1/buildcache"),
        ("DELETE", "/v1/layers"),
        ("HEAD", "/v1/layers"),
        ("OPTIONS", "/v1/uploads"),
        ("GET", f"/v1/image-exports/{IDENTIFIER}/download"),
        ("GET", "/v1/v1/layers"),
    ],
)
async def test_unclassified_browser_route_fails_closed_even_for_system(action_client, method, path):
    client, principal = action_client
    principal["roles"] = ["member", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN]
    for system_admin in (False, True):
        principal["is_system_admin"] = system_admin
        assert (await client.request(method, path)).status_code == 403


async def test_package_bearer_never_becomes_browser_keystone_principal(action_client):
    client, principal = action_client
    principal["roles"] = ["member", PUBLISH]
    response = await client.post(
        "/v1/uploads", headers={"authorization": "Bearer " + "ppk_v1_" + IDENTIFIER + "." + "A" * 43}
    )
    assert response.status_code == 403


async def test_reader_inventory_never_gains_publish_or_download(action_client):
    client, principal = action_client
    principal["roles"] = ["reader", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN]
    assert (await client.get("/v1/layers")).status_code == 204
    assert (await client.get(f"/v1/layers/{DIGEST}/blob")).status_code == 403
    assert (await client.post("/v1/uploads")).status_code == 403
    assert (await client.post(f"/v1/projects/{NAMESPACE}/keys")).status_code == 403


@pytest.fixture
async def custom_client(monkeypatch):
    app = FastAPI()
    app.include_router(packages.router, prefix=BASE + "/packages")
    app.include_router(package_keys.router, prefix=BASE + "/package-keys")
    # No upstream is configured. A missed gate yields 503, not the asserted 403;
    # there is no fake forwarding function or network response in these tests.
    monkeypatch.setattr(get_settings(), "service_palimpsest_enabled", True)
    monkeypatch.setattr(get_settings(), "service_palimpsest_internal_url", "")
    current = {"roles": ["member", INVENTORY]}
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(side_effect=lambda *_: dict(current)))
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *_: False)

    async def identity(request: Request):
        info = {
            "project_id": PROJECT,
            "user_id": USER,
            "token": "original-subject",
            "roles": ["member", INVENTORY, DOWNLOAD, PUBLISH, KEYS_EDITOR, KEYS_ADMIN],
        }
        request.state.token_info = info
        return info

    app.dependency_overrides[packages.package_browser_identity] = identity
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, current


@pytest.mark.parametrize(
    "method,path,query",
    [
        ("PUT", "/packages/namespace", None),
        ("POST", "/package-keys", None),
        ("GET", "/package-keys", None),
        ("DELETE", f"/package-keys/{IDENTIFIER}", None),
        ("GET", f"/packages/versions/{DIGEST}/download", {"package": "test"}),
    ],
)
async def test_current_downgrade_denies_custom_paths_before_any_hub_io(custom_client, method, path, query):
    client, current = custom_client
    # Old session roles contain every leaf; current authority has only inventory.
    current["roles"] = ["member", INVENTORY]
    response = await client.request(method, BASE + path, params=query)
    assert response.status_code == 403


@pytest.mark.parametrize(
    "path,query",
    [
        ("/packages/context", None),
        ("/packages", None),
        ("/packages/detail", {"package": "test"}),
        ("/packages/resolve", {"package": "test", "tag": "latest"}),
        ("/packages/versions", {"package": "test"}),
        (f"/packages/versions/{DIGEST}", {"package": "test"}),
    ],
)
async def test_custom_metadata_downgrade_ignores_session_leaf_roles(custom_client, path, query):
    client, current = custom_client
    current["roles"] = ["member"]
    response = await client.get(BASE + path, params=query)
    assert response.status_code == 403


async def test_current_provider_outage_has_no_session_role_fallback(custom_client, monkeypatch):
    client, _ = custom_client
    monkeypatch.setattr(
        project_service,
        "get_project_access",
        AsyncMock(side_effect=HTTPException(503, "Current authority unavailable")),
    )
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == "Current authority unavailable"


async def test_current_system_admin_cannot_issue_custom_package_key(custom_client, monkeypatch):
    client, current = custom_client
    current["roles"] = ["member", KEYS_EDITOR, PUBLISH]
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *_: True)
    response = await client.post(BASE + "/package-keys", json={"name": "ci"})
    assert response.status_code == 403
