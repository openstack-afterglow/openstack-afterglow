"""Advertised API metadata is not a provider's installed software release."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from keystoneauth1 import access as ks_access

from app.api.deps import get_os_conn, get_token_info, require_admin
from app.api.identity.admin import router
from app.config import get_settings
from app.services import keystone
from app.services import service_versions as svc
from tests.admin_gate import synthetic_verified_admin


@pytest.fixture
def native(monkeypatch):
    state = SimpleNamespace(calls=[], responses={}, delays={}, active=0, peak=0, lock=threading.Lock())

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            state.calls.append(("POST", self.path, dict(self.headers)))
            self.send_error(403)

        def do_GET(self):
            with state.lock:
                state.calls.append(("GET", self.path, dict(self.headers)))
                state.active += 1
                state.peak = max(state.peak, state.active)
            try:
                time.sleep(state.delays.get(self.path, 0))
                status, body, headers = state.responses.get(self.path, (404, {}, {}))
                encoded = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                for key, value in headers.items():
                    self.send_header(key, value)
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass
            finally:
                with state.lock:
                    state.active -= 1

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    settings = get_settings().model_copy(
        update={
            "os_auth_url": base + "/identity/v3",
            "os_region_name": "RegionOne",
            "os_insecure": False,
            "os_cacert": "",
            "service_palimpsest_enabled": True,
            "service_k3s_enabled": True,
            "service_chat_enabled": True,
            "service_waygate_enabled": True,
            **{f"service_{name}_internal_url": "" for name in ("palimpsest", "drover", "lumen", "waygate")},
        }
    )
    monkeypatch.setattr(svc, "get_settings", lambda: settings)
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    catalog = []
    for service, service_type, _flag in svc._SERVICES:
        suffix = "v2.1/project" if service == "nova" else "v2.0" if service == "neutron" else "v1"
        catalog.append(
            {
                "type": service_type,
                "name": service,
                "endpoints": [{"interface": "internal", "region": "RegionOne", "url": f"{base}/{service}/{suffix}"}],
            }
        )
        state.responses[f"/{service}/" if service == "neutron" else f"/{service}/{suffix.split('/')[0]}/"] = (
            200,
            {"version": {"id": "v1.0", "status": "CURRENT", "version": "1.0"}},
            {},
        )
    token = ks_access.create(
        auth_token="original-native-token",
        body={
            "token": {
                "methods": ["token"],
                "issued_at": datetime.now(UTC).isoformat(),
                "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                "user": {"id": "human", "domain": {"id": "domain"}},
                "project": {"id": "project", "domain": {"id": "domain"}},
                "roles": [{"id": "admin", "name": "admin"}],
                "catalog": catalog,
            }
        },
    )
    conn = keystone.get_openstack_connection(token.auth_token, "project", native_access=token)
    conn._afterglow_token = token.auth_token
    conn._afterglow_authenticated_project_id = "project"
    info = {
        "user_id": "human",
        "identity_domain_id": "domain",
        "domain_id": "domain",
        "project_id": "project",
        "token": token.auth_token,
        "is_system_admin": True,
    }
    state.settings, state.conn, state.info, state.access, state.base = settings, conn, info, token, base
    try:
        yield state
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def rows(result):
    return {entry.service: entry.model_dump() for entry in result.services}


@pytest.mark.asyncio
async def test_actual_http_original_sdk_catalog_discovers_openstack_and_native_api_not_product(native):
    native.responses["/nova/v2.1/"] = (
        200,
        {"version": {"id": "v2.1", "status": "CURRENT", "version": "2.101", "min_version": "2.1"}},
        {},
    )
    native.responses["/neutron/"] = (
        300,
        {"versions": [{"id": "v2.0", "status": "CURRENT", "links": [{"href": "http://forbidden.test/"}]}]},
        {},
    )
    result = rows(await svc.observe_service_versions(native.conn, native.info))
    assert result["nova"]["version"] == "2.101"
    assert result["neutron"]["version"] == "2.0"
    assert result["drover"]["version"] == "1.0"
    assert {row["version_kind"] for row in result.values()} == {"api"}
    assert {row["status"] for row in result.values()} == {"available"}
    assert len(native.calls) == 6
    for method, path, headers in native.calls:
        assert method == "GET"
        assert headers["x-auth-token"] == "original-native-token"
        assert headers["x-project-id"] == "project"
        assert "project" not in path
        assert "Authorization" not in headers


@pytest.mark.asyncio
async def test_partial_timeout_status_malformed_redirect_and_no_leakage(native, monkeypatch):
    monkeypatch.setattr(svc, "_TIMEOUT", 0.15)
    native.delays["/lumen/v1/"] = 0.3
    native.responses["/drover/v1/"] = (403, {"error": "private-token http://private-host"}, {"Server": "private"})
    native.responses["/palimpsest/v1/"] = (200, b"not json private-token", {})
    native.responses["/waygate/v1/"] = (302, {}, {"Location": native.base + "/credential-leak"})
    result = rows(await svc.observe_service_versions(native.conn, native.info))
    assert result["nova"]["status"] == result["neutron"]["status"] == "available"
    for name in ("lumen", "drover", "palimpsest", "waygate"):
        assert result[name] == {"service": name, "status": "unavailable", "version": None, "version_kind": None}
    serialized = json.dumps(result)
    assert "private" not in serialized and "original-native-token" not in serialized
    assert not any(path == "/credential-leak" for _, path, _ in native.calls)
    assert all(method == "GET" for method, _, _ in native.calls)


@pytest.mark.asyncio
async def test_concurrency_is_bounded_and_parallel(native):
    native.delays.update({path: 0.08 for path in native.responses})
    result = await svc.observe_service_versions(native.conn, native.info)
    assert all(row.status == "available" for row in result.services)
    assert native.peak == svc._CONCURRENCY == 3
    assert len(native.calls) == 6


@pytest.mark.asyncio
async def test_disabled_services_never_resolve_or_contact(native, monkeypatch):
    settings = native.settings.model_copy(update={flag: False for _, _, flag in svc._SERVICES if flag})
    monkeypatch.setattr(svc, "get_settings", lambda: settings)
    result = rows(await svc.observe_service_versions(native.conn, native.info))
    assert len(native.calls) == 2
    assert [result[name]["status"] for name in ("palimpsest", "drover", "lumen", "waygate")] == ["disabled"] * 4


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing", "wrong_user", "wrong_token", "wrong_project", "expired"])
async def test_no_reliable_native_identity_never_refreshes_credentials(native, failure):
    info = dict(native.info)
    if failure == "missing":
        native.conn.session.auth.auth_ref = None
    elif failure == "wrong_user":
        info["user_id"] = "other"
    elif failure == "wrong_token":
        native.conn._afterglow_token = "unvalidated-token"
    elif failure == "wrong_project":
        native.conn._afterglow_authenticated_project_id = "other"
    else:
        native.access._data["token"]["expires_at"] = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    result = await svc.observe_service_versions(native.conn, info)
    assert {row.status for row in result.services} == {"unavailable"}
    assert native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"info": {"version": "9.8.7"}},
        {"version": "9.8.7", "service": "drover"},
        {"status": "ok"},
        {"version": {"id": "v1.0", "status": "CURRENT", "version": "private<secret>"}},
        {"version": {"id": "v1.0", "status": "DEPRECATED", "version": "1.0"}},
        {"version": {"id": "garbage", "status": "CURRENT", "version": "9.8.7"}},
    ],
)
async def test_no_fabricated_product_release_from_openapi_health_or_malformed_body(native, payload):
    native.responses["/drover/v1/"] = (200, payload, {"Server": "drover/9.8.7"})
    assert rows(await svc.observe_service_versions(native.conn, native.info))["drover"]["status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,headers", [(b"x" * (svc._MAX_BODY + 1), {}), (b"compressed", {"Content-Encoding": "gzip"})]
)
async def test_response_body_and_compression_are_bounded(native, body, headers):
    native.responses["/drover/v1/"] = (200, body, headers)
    assert rows(await svc.observe_service_versions(native.conn, native.info))["drover"]["status"] == "unavailable"


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://user:secret@127.0.0.1/",
        "http://127.0.0.1/?token=x",
        "http://127.0.0.1/#x",
        "http://127.0.0.1/a/../",
        "http://127.0.0.1/%2e%2e",
        "http://127.0.0.1/\n",
    ],
)
def test_unsafe_configured_endpoint_is_rejected(url):
    with pytest.raises(ValueError):
        svc._discovery_url(url, "drover")


@pytest.mark.asyncio
async def test_trusted_override_and_missing_or_ambiguous_internal_catalog(native, monkeypatch):
    settings = native.settings.model_copy(update={"service_drover_internal_url": native.base + "/explicit/v1"})
    monkeypatch.setattr(svc, "get_settings", lambda: settings)
    native.responses["/explicit/v1/"] = (200, {"version": {"id": "v1.0", "status": "CURRENT"}}, {})
    original = native.access.service_catalog.get_endpoints

    def endpoints(**kwargs):
        if kwargs["service_type"] == "network":
            return {}
        if kwargs["service_type"] == "compute":
            return {"compute": [{"url": native.base + "/first"}, {"url": native.base + "/second"}]}
        return original(**kwargs)

    monkeypatch.setattr(native.access.service_catalog, "get_endpoints", endpoints)
    result = rows(await svc.observe_service_versions(native.conn, native.info))
    assert result["nova"]["status"] == result["neutron"]["status"] == "unavailable"
    assert result["drover"]["version"] == "1.0"
    assert any(path == "/explicit/v1/" for _, path, _ in native.calls)
    assert not any(path in {"/first", "/second"} for _, path, _ in native.calls)


@pytest.mark.asyncio
async def test_admin_endpoint_response_and_no_browser_selected_discovery_url(native):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    app.dependency_overrides[get_token_info] = lambda: native.info
    app.dependency_overrides[require_admin] = synthetic_verified_admin
    app.dependency_overrides[get_os_conn] = lambda: native.conn
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/service-versions?url=http://forbidden.test/")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"services"}
    assert len(payload["services"]) == 6
    assert all(set(row) == {"service", "status", "version", "version_kind"} for row in payload["services"])
    assert len(native.calls) == 6


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_endpoint_keeps_real_authentication_and_admin_guard_before_provider_contact(native, status):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")

    async def identity():
        if status == 401:
            raise HTTPException(401, "Authentication required")
        return {**native.info, "is_system_admin": False}

    def provider():
        pytest.fail("Denied request must not open a provider connection")

    app.dependency_overrides[get_token_info] = identity
    app.dependency_overrides[get_os_conn] = provider
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/service-versions")
    assert response.status_code == status
    assert native.calls == []


@pytest.mark.parametrize(
    "payload,expected",
    [
        (
            {
                "versions": {
                    "values": [
                        {"id": "v2.0", "status": "SUPPORTED"},
                        {"id": "v2.1", "status": "CURRENT", "version": "2.101"},
                    ]
                }
            },
            "2.101",
        ),
        ({"versions": [{"id": "v2.0", "status": "CURRENT"}, {"id": "v10.0", "status": "CURRENT"}]}, "10.0"),
        ({"versions": []}, None),
    ],
)
def test_openstack_discovery_envelopes_and_numeric_order(payload, expected):
    assert svc._api_version(payload) == expected


@pytest.mark.asyncio
async def test_cached_admin_flag_does_not_bypass_fresh_native_authority(native, monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/admin")
    app.dependency_overrides[get_token_info] = lambda: native.info

    def provider():
        pytest.fail("Revoked administrator must not open a provider connection")

    app.dependency_overrides[get_os_conn] = provider
    monkeypatch.setattr("app.services.domain_scope.domain_context", lambda *args, **kwargs: {})
    monkeypatch.setattr("app.services.domain_scope.assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(keystone, "validate_token", lambda *args, **kwargs: {"domain_id": "domain", "roles": ["admin"]})
    monkeypatch.setattr(keystone, "_is_system_admin", lambda *args, **kwargs: False)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/api/v1/admin/service-versions")
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "system_admin_required"
    assert native.calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("system_scoped", [True, False])
async def test_real_projectless_accessinfo_system_scope_and_loopback_discovery(native, system_scoped):
    token_body = dict(native.access._data["token"])
    token_body.pop("project")
    if system_scoped:
        token_body["system"] = {"all": True}
    access = ks_access.create(auth_token="original-system-token", body={"token": token_body})
    native.conn._afterglow_token = access.auth_token
    native.conn._afterglow_authenticated_project_id = ""
    native.conn.session.auth.auth_ref = access
    info = {**native.info, "project_id": "", "token": access.auth_token}
    assert access.project_id is None
    assert access.system_scoped is system_scoped
    result = await svc.observe_service_versions(native.conn, info)
    if system_scoped:
        assert {row.status for row in result.services} == {"available"}
        assert len(native.calls) == 6
        for method, _path, headers in native.calls:
            assert method == "GET"
            assert headers["x-auth-token"] == "original-system-token"
            assert "x-project-id" not in headers
    else:
        assert {row.status for row in result.services} == {"unavailable"}
        assert native.calls == []
