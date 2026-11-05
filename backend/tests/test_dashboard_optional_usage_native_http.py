"""Full quota partial reads through installed SDKs and loopback native protocols.

Authentication/core quotas/pool authority are synthetic; Trove GET and Swift HEAD
use the installed openstacksdk against a disposable HTTP server, never a cloud.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from keystoneauth1 import session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.api.common import dashboard
from app.services import cache, swift, trove

QUOTA = {"limit": 10, "in_use": 2, "reserved": 0}
ZERO_SWIFT = {"container_count": 0, "object_count": 0, "bytes_used": 0}
POPULATED_SWIFT = {"container_count": 3, "object_count": 7, "bytes_used": 4096}


@pytest.fixture
def native_usage(mock_conn, monkeypatch):
    state = {"trove": "zero", "swift": "zero", "requests": []}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, body=None, headers=None):
            payload = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for name, value in (headers or {}).items():
                self.send_header(name, str(value))
            self.send_header("Content-Length", str(len(payload)) if self.command != "HEAD" else "0")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        def do_GET(self):
            if self.path.rstrip("/") in ("/v1.0", "/v1.0/project", "/v1/AUTH_project"):
                service_path = "/v1/AUTH_project" if "/AUTH_" in self.path else "/v1.0/"
                return self.respond(
                    200,
                    {
                        "version": {
                            "id": "v1.0",
                            "status": "CURRENT",
                            "links": [{"rel": "self", "href": endpoint + service_path}],
                        }
                    },
                )
            state["requests"].append(("GET", self.path))
            if urlsplit(self.path).path != "/v1.0/project/instances":
                return self.respond(404)
            mode = state["trove"]
            if isinstance(mode, int):
                return self.respond(mode, {"error": "PRIVATE_PROVIDER_FAILURE"})
            if mode == "malformed":
                return self.respond(200, {"other": []})
            if mode == "row_bound":
                return self.respond(200, {"instances": [{"id": str(index)} for index in range(10001)]})
            if mode.startswith("continuation_"):
                marker = parse_qs(urlsplit(self.path).query).get("marker", [None])[0]
                if marker is not None and mode != "continuation_page_bound":
                    if mode == "continuation_failure":
                        return self.respond(503, {"error": "PRIVATE_PROVIDER_FAILURE"})
                    if mode == "continuation_redirect":
                        return self.respond(302, headers={"Location": "http://127.0.0.1:1/private"})
                    if mode == "continuation_malformed":
                        return self.respond(200, {"other": []})
                    if mode == "continuation_empty":
                        return self.respond(200, {"instances": []})
                    if mode != "continuation_loop":
                        return self.respond(
                            200, {"instances": [{"id": "second", "deleted": mode == "continuation_zero"}]}
                        )
                last_id = "deleted"
                if mode == "continuation_page_bound":
                    last_id = str(int(marker) + 1) if marker else "1"
                body = {"instances": [{"id": last_id, "deleted": 1}]}
                next_url = endpoint + f"/v1.0/project/instances?marker={last_id}"
                if mode == "continuation_foreign":
                    next_url = "http://127.0.0.1:1/v1.0/project/instances?marker=deleted"
                elif mode == "continuation_wrong_project":
                    next_url = endpoint + "/v1.0/other/instances?marker=deleted"
                elif mode == "continuation_wrong_marker":
                    next_url = endpoint + "/v1.0/project/instances?marker=not-last"
                elif mode == "continuation_relative":
                    next_url = "?marker=deleted&limit=1"
                elif mode == "continuation_native_https":
                    # Trove stable/2025.2 AppUrl.change_query_params forces HTTPS.
                    next_url = next_url.replace("http://", "https://", 1)
                if mode in ("continuation_links", "continuation_instances_links", "continuation_native_https"):
                    field = "instances_links" if mode == "continuation_instances_links" else "links"
                    body[field] = [{"rel": "next", "href": next_url}]
                else:
                    body["next"] = True if mode == "continuation_bad_next" else next_url
                return self.respond(200, body)
            rows = [] if mode == "zero" else [{"id": "live", "name": "live"}, {"id": "deleted", "deleted": 1}]
            return self.respond(200, {"instances": rows})

        def do_HEAD(self):
            state["requests"].append(("HEAD", self.path.rstrip("/")))
            if self.path.rstrip("/") != "/v1/AUTH_project":
                return self.respond(404)
            mode = state["swift"]
            if isinstance(mode, int):
                return self.respond(mode)
            values = POPULATED_SWIFT if mode == "populated" else ZERO_SWIFT
            headers = {
                "X-Account-Container-Count": values["container_count"],
                "X-Account-Object-Count": values["object_count"],
                "X-Account-Bytes-Used": values["bytes_used"],
            }
            if mode == "missing":
                headers.pop("X-Account-Object-Count")
            if mode == "negative":
                headers["X-Account-Object-Count"] = -1
            return self.respond(204, headers=headers)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=session.Session(auth=Token(endpoint, "synthetic-quota-native-token")),
        database_endpoint_override=endpoint + "/v1.0/project",
        database_api_version="1",
        object_store_endpoint_override=endpoint + "/v1/AUTH_project",
        object_store_api_version="1",
        connect_retries=0,
        status_code_retries=0,
    )
    mock_conn.database = conn.database
    mock_conn.object_store = conn.object_store
    monkeypatch.setattr(swift, "_get_swift_endpoint", lambda _conn: None)
    settings = SimpleNamespace(service_manila_enabled=True, service_trove_enabled=True, service_swift_enabled=True)
    monkeypatch.setattr(dashboard, "get_settings", lambda: settings)
    monkeypatch.setattr(
        dashboard.nova, "get_project_quota", lambda *_args, **_kw: {"compute": QUOTA, "native_compute": QUOTA}
    )
    monkeypatch.setattr(dashboard.cinder, "get_volume_quota", lambda *_args: QUOTA)
    monkeypatch.setattr(dashboard.neutron_svc, "get_network_quota", lambda *_args: QUOTA)
    monkeypatch.setattr(dashboard.manila_svc, "get_file_storage_quota", lambda *_args: QUOTA)
    monkeypatch.setattr(dashboard.compute_pools, "project_pool_snapshot", AsyncMock(return_value={}))
    monkeypatch.setattr(dashboard, "_with_compute_pool", AsyncMock(return_value=(QUOTA, None)))
    monkeypatch.setattr("app.services.gpu_quota.get_effective_gpu_quota_status", AsyncMock(return_value=[]))
    try:
        yield state, settings
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join()


def assert_core(data):
    for field in ("compute", "native_compute", "storage", "network", "file_storage"):
        assert data[field] == QUOTA
    assert data["gpu"] == []
    assert data["gpu_available"] is True
    assert "PRIVATE_PROVIDER_FAILURE" not in json.dumps(data)


@pytest.mark.asyncio
@pytest.mark.parametrize("trove_mode", ["zero", "populated", 503])
@pytest.mark.parametrize("swift_mode", ["zero", "populated", 404, 503])
async def test_full_quotas_keep_independent_native_usage(client, native_usage, trove_mode, swift_mode):
    state, _settings = native_usage
    state.update(trove=trove_mode, swift=swift_mode)
    response = await client.get("/api/v1/dashboard/quotas")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    assert data["database"] == {"instances_count": None if trove_mode == 503 else int(trove_mode == "populated")}
    assert data["object_storage"] == (
        None if swift_mode == 503 else POPULATED_SWIFT if swift_mode == "populated" else ZERO_SWIFT
    )
    assert data["unavailable_sections"] == [
        name for name, failed in (("database", trove_mode == 503), ("object_storage", swift_mode == 503)) if failed
    ]
    assert data["disabled_sections"] == []
    assert sorted(state["requests"]) == [("GET", "/v1.0/project/instances"), ("HEAD", "/v1/AUTH_project")]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "section,mode",
    [("trove", 403), ("trove", "malformed"), ("swift", 403), ("swift", "missing"), ("swift", "negative")],
)
async def test_invalid_or_denied_usage_is_unknown_not_zero(client, native_usage, section, mode):
    state, _settings = native_usage
    state[section] = mode
    response = await client.get("/api/v1/dashboard/quotas")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    unavailable = "database" if section == "trove" else "object_storage"
    assert data["unavailable_sections"] == [unavailable]
    assert data["database"]["instances_count"] is (None if section == "trove" else 0)
    assert data["object_storage"] == (None if section == "swift" else ZERO_SWIFT)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "continuation_next",
        "continuation_links",
        "continuation_native_https",
        "continuation_instances_links",
        "continuation_relative",
        "continuation_zero",
    ],
)
async def test_trove_count_exhausts_scoped_pages_before_filtering_deleted(client, native_usage, mock_conn, mode):
    state, _settings = native_usage
    state["trove"] = mode
    response = await client.get("/api/v1/dashboard/quotas")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    assert data["database"] == {"instances_count": 0 if mode == "continuation_zero" else 1}
    assert data["object_storage"] == ZERO_SWIFT
    assert data["unavailable_sections"] == []
    assert [path for method, path in state["requests"] if method == "GET"] == [
        "/v1.0/project/instances",
        "/v1.0/project/instances?marker=deleted",
    ]
    # Existing optional consumers retain their non-strict first-page behavior.
    assert trove.count_instances(mock_conn) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,expected_pages",
    [
        ("continuation_failure", 2),
        ("continuation_redirect", 2),
        ("continuation_malformed", 2),
        ("continuation_empty", 2),
        ("continuation_loop", 2),
        ("continuation_foreign", 1),
        ("continuation_wrong_project", 1),
        ("continuation_wrong_marker", 1),
        ("continuation_bad_next", 1),
        ("continuation_page_bound", 100),
        ("row_bound", 1),
    ],
)
async def test_incomplete_trove_pages_never_publish_partial_counts(client, native_usage, mode, expected_pages):
    state, _settings = native_usage
    state["trove"] = mode
    response = await client.get("/api/v1/dashboard/quotas")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    assert data["database"] == {"instances_count": None}
    assert data["object_storage"] == ZERO_SWIFT
    assert data["unavailable_sections"] == ["database"]
    requests = [path for method, path in state["requests"] if method == "GET"]
    assert len(requests) == expected_pages
    assert all(urlsplit(path).path == "/v1.0/project/instances" for path in requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("trove_enabled,swift_enabled", [(False, True), (True, False), (False, False)])
async def test_disabled_usage_is_explicit_without_native_reads(client, native_usage, trove_enabled, swift_enabled):
    state, settings = native_usage
    settings.service_trove_enabled = trove_enabled
    settings.service_swift_enabled = swift_enabled
    response = await client.get("/api/v1/dashboard/quotas")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    assert data["unavailable_sections"] == []
    assert data["disabled_sections"] == [
        name for name, enabled in (("database", trove_enabled), ("object_storage", swift_enabled)) if not enabled
    ]
    assert data["database"] == {"instances_count": 0 if trove_enabled else None}
    assert data["object_storage"] == (ZERO_SWIFT if swift_enabled else None)
    assert len(state["requests"]) == int(trove_enabled) + int(swift_enabled)


@pytest.mark.asyncio
async def test_legacy_cached_fake_zero_is_not_served(client, native_usage, mock_conn):
    state, _settings = native_usage
    state.update(trove=503, swift=503)
    legacy_key = f"afterglow:dashboard:{mock_conn._afterglow_project_id}:quotas:native-v1"
    await cache.cached_call(
        legacy_key,
        60,
        lambda: [{"compute": QUOTA, "native_compute": QUOTA}, QUOTA, QUOTA, QUOTA, 0, ZERO_SWIFT],
    )
    response = await client.get("/api/v1/dashboard/quotas?cache=true")
    assert response.status_code == 200
    data = response.json()
    assert_core(data)
    assert data["database"] == {"instances_count": None}
    assert data["object_storage"] is None
    assert data["unavailable_sections"] == ["database", "object_storage"]
    assert len(state["requests"]) == 2
    # The new partial payload is itself safe to cache and contains no exceptions.
    second = await client.get("/api/v1/dashboard/quotas?cache=true")
    assert second.json() == data
    assert len(state["requests"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["compute_policy", "compute_pool", "domain_quota"])
async def test_mutation_invalidation_refreshes_seeded_full_quota_cache(
    admin_client, native_usage, mock_conn, monkeypatch, mutation
):
    from app.services import compute_pools, domain_quotas

    state, _settings = native_usage
    project_id = mock_conn._afterglow_project_id
    first = await admin_client.get("/api/v1/dashboard/quotas?cache=true")
    assert first.status_code == 200
    assert first.json()["database"] == {"instances_count": 0}
    assert first.json()["object_storage"] == ZERO_SWIFT
    assert len(state["requests"]) == 2

    # A native provider update remains cached until the actual mutation
    # invalidation boundary runs. No cache/invalidate function is mocked.
    state.update(trove="populated", swift="populated")
    cached = await admin_client.get("/api/v1/dashboard/quotas?cache=true")
    assert cached.json() == first.json()
    assert len(state["requests"]) == 2
    if mutation == "compute_policy":
        mock_conn.identity.get_domain.return_value = SimpleNamespace(id="default", name="Default")
        mock_conn.identity.get_project.return_value = SimpleNamespace(id=project_id, domain_id="default")
        setter = AsyncMock()
        monkeypatch.setattr("app.services.gpu_quota.set_project_gpu_quota", setter)
        response = await admin_client.put(
            f"/api/v1/admin/compute-policy/{project_id}?domain_id=default",
            json={"gpu_quotas": {"A10": 2}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        setter.assert_awaited_once_with(mock_conn, project_id, "A10", 2)
    elif mutation == "compute_pool":
        await compute_pools._invalidate_projections({project_id})
    else:
        await domain_quotas._invalidate(project_id)

    fresh = await admin_client.get("/api/v1/dashboard/quotas?cache=true")
    assert fresh.status_code == 200
    assert_core(fresh.json())
    assert fresh.json()["database"] == {"instances_count": 1}
    assert fresh.json()["object_storage"] == POPULATED_SWIFT
    assert len(state["requests"]) == 4


def test_non_strict_trove_counter_preserves_optional_fallback(mock_conn):
    mock_conn.database.get.side_effect = RuntimeError("optional service missing")
    assert trove.count_instances(mock_conn) == 0
    with pytest.raises(RuntimeError, match="optional service missing"):
        trove.count_instances(mock_conn, strict=True)


@pytest.mark.parametrize(
    "source_scheme,target_scheme,target_authority",
    [
        ("https", "http", "native.example:8779"),
        ("http", "ftp", "native.example:8779"),
        ("http", "https", "native.example:443"),
        ("http", "https", "other.example:8779"),
    ],
)
def test_trove_continuation_never_downgrades_or_changes_authority(source_scheme, target_scheme, target_authority):
    source = f"{source_scheme}://native.example:8779/v1.0/project/instances"
    body = {
        "links": [{"rel": "next", "href": f"{target_scheme}://{target_authority}/v1.0/project/instances?marker=last"}]
    }
    with pytest.raises(ValueError, match="out-of-scope"):
        trove._instance_page_marker(body, source, "last")
