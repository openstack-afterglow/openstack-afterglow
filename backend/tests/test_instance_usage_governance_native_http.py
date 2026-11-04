"""Installed Keystoneauth/OpenStack SDK over real loopback HTTP.

The service authenticates only to its real admin project; the synthetic Keystone
explicitly refuses tenant rescope. Human grants and SQL are isolated fixtures.
This proves transport/scope fences, not deployed Nova policy authorization.
"""

import json
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException
from keystoneauth1.identity import v3
from keystoneauth1.session import Session
from openstack.connection import Connection
from sqlalchemy import select

from app.models.instance_usage_governance import InstanceUsageExtensionRequest as Extension
from app.models.instance_usage_governance import InstanceUsagePolicy as Policy
from app.models.instance_usage_governance import UsageExtensionReview
from app.services import instance_usage as usage
from app.services import instance_usage_governance as governance
from tests import test_instance_usage_routes as usage_fixtures
from tests.test_instance_usage_scheduler_native_http import Redis

governance_store = usage_fixtures.governance_store

PROJECT = "review-owned-project"
ADMIN_PROJECT = "native-admin-project"
SERVER = "review-native-server"
DOMAIN = "default"


@pytest.fixture
def native_review():
    now = datetime.now(UTC).replace(microsecond=0)
    state = {
        "metadata": {**usage.adoption_metadata(now=now), "unrelated": "preserve"},
        "owner": PROJECT,
        "admin": True,
        "auth_scopes": [],
        "posts": [],
        "metadata_status": 200,
        "connections": [],
        "native_gets": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body, *, token=None):
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if token:
                self.send_header("X-Subject-Token", token)
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            if path.endswith(f"/servers/{SERVER}"):
                state["native_gets"].append((path, self.headers.get("X-Auth-Token")))
                return self.reply(
                    200,
                    {
                        "server": {
                            "id": SERVER,
                            "tenant_id": state["owner"],
                            "name": "native review fixture",
                            "status": "ACTIVE",
                            "metadata": state["metadata"],
                        }
                    },
                )
            if "identity" in path:
                return self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.14",
                            "status": "stable",
                            "links": [{"rel": "self", "href": endpoint + "/identity/v3/"}],
                        }
                    },
                )
            return self.reply(
                200,
                {
                    "version": {
                        "id": "v2.1",
                        "status": "CURRENT",
                        "min_version": "2.1",
                        "version": "2.96",
                        "links": [{"rel": "self", "href": endpoint + f"/compute/v2.1/{ADMIN_PROJECT}/"}],
                    }
                },
            )

        def do_POST(self):
            path = urlsplit(self.path).path.rstrip("/")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
            if path.endswith("/auth/tokens"):
                project = body.get("auth", {}).get("scope", {}).get("project", {}).get("id")
                state["auth_scopes"].append(project)
                if project != ADMIN_PROJECT:
                    return self.reply(401, {"error": {"message": "service has no tenant project membership"}})

                def stamp(value):
                    return value.isoformat().replace("+00:00", "Z")

                return self.reply(
                    201,
                    {
                        "token": {
                            "methods": ["password"],
                            "issued_at": stamp(now - timedelta(minutes=1)),
                            "expires_at": stamp(now + timedelta(days=1)),
                            "audit_ids": ["synthetic-audit"],
                            "is_admin_project": state["admin"],
                            "user": {
                                "id": "native-service-user",
                                "name": "service",
                                "domain": {"id": DOMAIN, "name": DOMAIN},
                            },
                            "project": {"id": ADMIN_PROJECT, "name": "admin", "domain": {"id": DOMAIN, "name": DOMAIN}},
                            "roles": [{"id": "native-admin-role", "name": "admin"}],
                            "catalog": [
                                {
                                    "id": "compute",
                                    "name": "nova",
                                    "type": "compute",
                                    "endpoints": [
                                        {
                                            "id": "compute-public",
                                            "interface": "public",
                                            "region": "RegionOne",
                                            "url": endpoint + f"/compute/v2.1/{ADMIN_PROJECT}",
                                        }
                                    ],
                                },
                                {
                                    "id": "identity",
                                    "name": "keystone",
                                    "type": "identity",
                                    "endpoints": [
                                        {
                                            "id": "identity-public",
                                            "interface": "public",
                                            "region": "RegionOne",
                                            "url": endpoint + "/identity/v3",
                                        }
                                    ],
                                },
                            ],
                        }
                    },
                    token="native-service-token",
                )
            if path.endswith(f"/servers/{SERVER}/metadata"):
                state["posts"].append({"path": path, "token": self.headers.get("X-Auth-Token"), "body": body})
                if state["metadata_status"] != 200:
                    return self.reply(state["metadata_status"], {"error": {"message": "synthetic native denial"}})
                if self.headers.get("X-Auth-Token") != "native-service-token":
                    return self.reply(401, {"error": {"message": "wrong token"}})
                state["metadata"].update(body["metadata"])
                return self.reply(200, {"metadata": state["metadata"]})
            self.reply(404, {"error": {"message": "not found"}})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{httpd.server_port}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def factory():
        auth = v3.Password(
            auth_url=endpoint + "/identity/v3",
            username="service",
            password="synthetic-password",
            user_domain_id=DOMAIN,
            project_id=ADMIN_PROJECT,
        )
        conn = Connection(
            session=Session(auth=auth, connect_retries=2),
            compute_endpoint_override=endpoint + f"/compute/v2.1/{ADMIN_PROJECT}",
            compute_api_version="2",
            identity_endpoint_override=endpoint + "/identity/v3",
            compute_status_code_retries=2,
            compute_connect_retries=2,
            region_name="RegionOne",
            interface="public",
            api_timeout=2,
        )
        state["connections"].append(conn)
        return conn

    try:
        yield SimpleNamespace(state=state, factory=factory, now=now)
    finally:
        for conn in state["connections"]:
            conn.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


async def seed_request(factory, native):
    schedule = usage.parse_schedule({"id": SERVER, "metadata": native.state["metadata"]})
    async with factory() as session:
        session.add(
            Policy(
                cloud_id="c" * 64,
                domain_id=DOMAIN,
                review_required=True,
                revision="a" * 32,
                updated_by="manager",
                updated_at=native.now,
            )
        )
        session.add(
            Extension(
                id="b" * 32,
                cloud_id="c" * 64,
                domain_id=DOMAIN,
                project_id=PROJECT,
                instance_id=SERVER,
                instance_name="native review fixture",
                requested_by="requester",
                requested_at=native.now,
                expires_at=datetime.fromisoformat(schedule.expires_at) + timedelta(days=7),
                reason="native transport evaluation",
                schedule_revision=schedule.revision,
                policy_revision="a" * 32,
                revision="d" * 32,
                status="pending",
            )
        )
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [None, "owner", "operator", 401, 403, 503])
async def test_review_uses_real_admin_project_sdk_without_tenant_rescope_or_retry(
    governance_store,
    native_review,
    monkeypatch,
    failure,
):
    native = native_review
    await seed_request(governance_store, native)
    if failure == "owner":
        native.state["owner"] = "foreign-project"
    elif failure == "operator":
        native.state["admin"] = False
    elif isinstance(failure, int):
        native.state["metadata_status"] = failure
    monkeypatch.setattr(governance.keystone, "get_admin_project_connection", native.factory)
    monkeypatch.setattr(
        governance.keystone, "get_admin_connection_for_project", lambda *_: pytest.fail("tenant service rescope")
    )
    monkeypatch.setattr(
        governance,
        "live_access",
        AsyncMock(
            return_value={
                "manager": True,
                "review": True,
                "write": True,
                "read": True,
            }
        ),
    )
    monkeypatch.setattr(usage, "_get_redis", AsyncMock(return_value=Redis()))
    req = UsageExtensionReview(decision="approve", revision="d" * 32)
    token_info = {"user_id": "reviewer", "domain_id": DOMAIN}
    if failure is None:
        result = await governance.review_request(None, token_info, "b" * 32, req)
        assert result["status"] == "approved"
        assert len(native.state["posts"]) == 1
        assert native.state["metadata"]["unrelated"] == "preserve"
    else:
        with pytest.raises(HTTPException) as denied:
            await governance.review_request(None, token_info, "b" * 32, req)
        assert denied.value.status_code == (403 if failure == "owner" else 503 if failure == "operator" else 502)
        assert len(native.state["posts"]) == (1 if isinstance(failure, int) else 0)
    assert native.state["auth_scopes"] == [ADMIN_PROJECT]
    for conn in native.state["connections"]:
        if failure != "operator":
            assert conn._afterglow_project_id == conn._afterglow_authenticated_project_id == ADMIN_PROJECT
            assert conn._afterglow_usage_operator_scope.target_project_id == PROJECT
    assert all(path.startswith(f"/compute/v2.1/{ADMIN_PROJECT}/") for path, _ in native.state["native_gets"])
    assert all(post["token"] == "native-service-token" for post in native.state["posts"])
    async with governance_store() as session:
        row = (await session.execute(select(Extension))).scalar_one()
        assert row.status == ("approved" if failure is None else "pending" if isinstance(failure, str) else "uncertain")
        if failure is None or isinstance(failure, int):
            retry = UsageExtensionReview(decision="approve", revision=row.revision)
            with pytest.raises(HTTPException) as replay:
                await governance.review_request(None, token_info, row.id, retry)
            assert replay.value.status_code == 409
    assert native.state["auth_scopes"] == [ADMIN_PROJECT]
    assert len(native.state["posts"]) == (1 if failure is None or isinstance(failure, int) else 0)
