"""Real SDK account requests retain the fixed executor credential, never tenant rescope."""

import json
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from fastapi import HTTPException
from keystoneauth1 import session
from keystoneauth1.identity import v3
from openstack.connection import Connection
from requests.adapters import BaseAdapter

from app.api.deps import get_admin_os_conn, get_os_conn, get_token_info, require_admin
from app.main import app
from app.services import swift


class AccountProvider(BaseAdapter):
    """In-process HTTP provider; Keystone never grants executor membership in tenants."""

    def __init__(self):
        self.requests = []
        self.failure = None
        self.accounts = {
            "a": [
                {"name": "bucket", "count": 2, "bytes": 10},
                {"name": "bucket_segments", "count": 1, "bytes": 20},
                {"name": "bucket-quarantine", "count": 3, "bytes": 30},
                {"name": "bucket-trash", "count": 4, "bytes": 40},
            ],
            "b": [{"name": "bucket", "count": 1, "bytes": 50}],
            "foreign": [{"name": "private", "count": 9, "bytes": 90}],
            "empty": [],
        }

    def send(self, request, **_kwargs):
        self.requests.append(request)
        path = urlsplit(request.url).path.rstrip("/")
        status, body = 200, {}
        headers = {}
        if request.method == "POST" and path == "/v3/auth/tokens":
            auth = json.loads(request.body)["auth"]
            assert auth["scope"] == {"project": {"id": "executor"}}
            status, headers = 201, {"X-Subject-Token": "fixed-admin-token"}
            body = {
                "token": {
                    "methods": ["token"],
                    "expires_at": "2099-01-01T00:00:00Z",
                    "issued_at": "2026-01-01T00:00:00Z",
                    "user": {"id": "operator", "domain": {"id": "default", "name": "Default"}},
                    "project": {"id": "executor", "name": "admin", "domain": {"id": "default", "name": "Default"}},
                    "is_admin_project": True,
                    "roles": [{"id": "admin-role", "name": "admin"}],
                    "catalog": [
                        {
                            "id": "swift",
                            "name": "swift",
                            "type": "object-store",
                            "endpoints": [
                                {
                                    "id": "swift-public",
                                    "interface": "public",
                                    "region": "RegionOne",
                                    "url": "http://native.test/swift/v1/AUTH_executor",
                                }
                            ],
                        }
                    ],
                }
            }
        elif path.startswith("/swift/v1/AUTH_") and request.method == "GET":
            assert request.headers["X-Auth-Token"] == "fixed-admin-token"
            pid = path.rsplit("AUTH_", 1)[1]
            if self.failure is not None:
                status, body = self.failure, {"error": "private provider failure"}
            elif pid == "empty":
                status, body = 404, {}
            else:
                marker = parse_qs(urlsplit(request.url).query).get("marker", [""])[0]
                rows = sorted(self.accounts[pid], key=lambda row: row["name"])
                body = [row for row in rows if row["name"] > marker][:2]
                headers["X-Account-Container-Count"] = str(len(rows))
        else:
            raise AssertionError(f"Unexpected native request: {request.method} {path}")
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers.update({"Content-Type": "application/json", **headers})
        response.url, response.request = request.url, request
        response.reason = "synthetic"
        return response

    def close(self):
        pass


@contextmanager
def native_connection():
    provider = AccountProvider()
    http = requests.Session()
    http.mount("http://native.test/", provider)
    auth = v3.Token(auth_url="http://native.test/v3", token="operator-subject", project_id="executor")
    conn = Connection(
        session=session.Session(auth=auth, session=http),
        object_store_endpoint_override="http://native.test/swift/v1/AUTH_executor",
        object_store_api_version="1",
        connect_retries=0,
    )
    conn._afterglow_authenticated_project_id = "executor"
    try:
        yield conn, provider
    finally:
        conn.close()


def test_admin_swift_native_account_targeting_and_pagination():
    with native_connection() as (conn, provider), patch.object(swift, "_get_swift_endpoint", return_value=None):
        original = conn.object_store.get_endpoint()
        rows = swift.list_project_containers(conn, "a", True, True)
        other = swift.list_project_containers(conn, "b")
        assert swift.list_project_containers(conn, "empty") == []
        assert conn.object_store.get_endpoint() == original
    assert rows == [
        {"name": "bucket", "count": 2, "bytes": 30},
        {"name": "bucket-quarantine", "count": 3, "bytes": 30, "is_quarantine": True},
        {"name": "bucket-trash", "count": 4, "bytes": 40, "is_trash": True},
    ]
    assert other == [{"name": "bucket", "count": 1, "bytes": 50}]
    auth_requests = [request for request in provider.requests if request.method == "POST"]
    assert len(auth_requests) == 1
    assert any("marker=" in request.url for request in provider.requests)
    assert all("AUTH_executor" not in request.url for request in provider.requests if request.method == "GET")


@pytest.mark.parametrize("status", [401, 403, 500, 503])
def test_admin_swift_native_provider_failure_is_not_empty(status):
    from keystoneauth1.exceptions.http import HttpError
    from openstack.exceptions import HttpException

    with native_connection() as (conn, provider), patch.object(swift, "_get_swift_endpoint", return_value=None):
        provider.failure = status
        with pytest.raises((HttpException, HttpError)):
            swift.list_project_containers(conn, "a")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://native.test/swift/v1/AUTH_foreign",
        "http://native.test/swift/v1",
        "http://native.test/swift/v1/AUTH_executor?redirect=foreign",
        "http://user:secret@native.test/swift/v1/AUTH_executor",
        "http://native.test/swift/v1/AUTH_foreign/AUTH_executor",
        "http://native.test/swift/v1/AUTH_executor/../AUTH_executor",
    ],
)
def test_admin_swift_rejects_unverified_account_endpoint(endpoint):
    with native_connection() as (conn, provider), patch.object(swift, "_get_swift_endpoint", return_value=endpoint):
        with pytest.raises(ValueError, match="unverified"):
            swift.list_project_containers(conn, "a")
        assert provider.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,owners",
    [
        ("", {"a", "b", "foreign"}),
        ("&domain_id=domain-a", {"a", "b"}),
        ("&domain_id=domain-a&project_id=b", {"b"}),
        ("&project_id=foreign", {"foreign"}),
        ("&domain_id=domain-a&project_id=foreign", set()),
    ],
)
async def test_admin_swift_projectless_caller_and_exact_owner_filter(admin_client, query, owners):
    from types import SimpleNamespace

    async def projectless():
        return {
            "token": "human-system-token",
            "project_id": "",
            "connection_project_id": "",
            "user_id": "human",
            "domain_id": "domain-a",
            "domain_name": "A",
            "identity_domain_id": "accounts",
            "is_system_admin": True,
        }

    async def consumer_must_not_run():
        raise AssertionError("Admin inventory attempted caller project connection")

    app.dependency_overrides.pop(get_admin_os_conn)
    app.dependency_overrides[get_token_info] = projectless
    app.dependency_overrides[get_os_conn] = consumer_must_not_run
    projects = {
        pid: {"id": pid, "name": pid, "domain_id": "domain-b" if pid == "foreign" else "domain-a"}
        for pid in ("a", "b", "foreign")
    }
    with (
        native_connection() as (conn, provider),
        patch("app.services.keystone.get_admin_project_connection", return_value=conn),
        patch("app.api.object_storage.containers.inventory_directory", return_value=SimpleNamespace(projects=projects)),
        patch(
            "app.api.object_storage.containers._get_deleted_containers",
            AsyncMock(side_effect=lambda pid: {"bucket": 123} if pid == "a" else {}),
        ),
        patch.object(swift, "_get_swift_endpoint", return_value=None),
    ):
        # Identity provider scope proof is deliberately separate from Swift's native account wire fixture.
        conn._proxies["identity"] = SimpleNamespace(
            get_domain=lambda did: {"id": did}, projects=lambda **_: projects.values()
        )
        result = await admin_client.get(
            "/api/v1/admin/object-storage?include_quarantine=true&include_trash=true&include_deleted=true" + query
        )
    assert result.status_code == 200
    body = result.json()
    assert {row["project_id"] for row in body["items"]} == owners
    assert body["partial"] is False
    assert body["project_count"] == len(owners)
    assert body["unavailable_projects"] == []
    assert any(row.get("is_deleted") and row["deleted_at"] == 123 for row in body["items"]) == ("a" in owners)
    assert {
        urlsplit(request.url).path.rstrip("/").rsplit("AUTH_", 1)[1]
        for request in provider.requests
        if request.method == "GET"
    } == owners


@pytest.mark.asyncio
async def test_admin_swift_revoked_authority_stops_native_executor(admin_client):
    async def revoked():
        raise HTTPException(403, "native_authority_revoked")

    app.dependency_overrides.pop(get_admin_os_conn)
    app.dependency_overrides[require_admin] = revoked
    with patch("app.services.keystone.get_admin_project_connection") as executor:
        result = await admin_client.get("/api/v1/admin/object-storage")
    assert result.status_code == 403
    executor.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query", ["all_projects=true", "all_projects=false", "domain_id=domain-a", "project_id=foreign"]
)
async def test_consumer_swift_rejects_obsolete_inventory_conditions(client, query):
    with patch("app.services.swift.list_containers") as listing:
        result = await client.get("/api/v1/object-storage?" + query)
    assert result.status_code == 403
    listing.assert_not_called()
