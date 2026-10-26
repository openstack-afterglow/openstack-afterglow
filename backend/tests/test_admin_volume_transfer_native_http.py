"""Real SDK/HTTP checks for the token project that actually receives a volume."""

import json
import threading
from contextlib import asynccontextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_admin_os_conn, require_admin
from app.api.identity.admin import _volume_transfer_router
from app.services import keystone

TRANSFER = "11111111-1111-4111-8111-111111111111"
VOLUME = "22222222-2222-4222-8222-222222222222"
SOURCE, TARGET, EXECUTOR = "source-dmslab", "target-dmslab", "afterglow-service"
DOMAIN = "selected-domain"
KEY = "synthetic-once-only-transfer-key"
CREATE = f"/api/v1/admin/volumes/{VOLUME}/transfer"
ACCEPT = f"/api/v1/admin/volumes/transfer/{TRANSFER}/accept"
BODY = {"auth_key": KEY, "target_domain_id": DOMAIN, "target_project_id": TARGET}


@pytest.fixture
async def native_transfer(monkeypatch):
    state = {
        "owner": SOURCE,
        "pending": False,
        "tokens": {},
        "exchanges": [],
        "creates": [],
        "accepts": [],
        "deny_scope": False,
        "native_status": 202,
        "wrong_identity": None,
        "accepted_owner": None,
        "redirect_status": None,
        "redirected": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value, token=None, location=None):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            if token:
                self.send_header("X-Subject-Token", token)
            if location:
                self.send_header("Location", location)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            if path in {"/identity", "/identity/v3", "/cinder", "/cinder/v3"} or path in {
                f"/cinder/v3/{EXECUTOR}",
                f"/cinder/v3/{TARGET}",
            }:
                identity = path.startswith("/identity")
                return self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.14" if identity else "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [
                                {"rel": "self", "href": endpoint + ("/identity/v3/" if identity else "/cinder/v3/")}
                            ],
                        }
                    },
                )
            if path == f"/identity/v3/projects/{TARGET}":
                return self.reply(
                    200, {"project": {"id": TARGET, "name": "DMSLAB", "domain_id": DOMAIN, "enabled": True}}
                )
            if path == f"/identity/v3/domains/{DOMAIN}":
                return self.reply(200, {"domain": {"id": DOMAIN, "name": "dmslab", "enabled": True}})
            if path.endswith(f"/volumes/{VOLUME}"):
                return self.reply(
                    200,
                    {
                        "volume": {
                            "id": VOLUME,
                            "size": 200,
                            "status": "awaiting-transfer" if state["pending"] else "available",
                            "attachments": [],
                            "metadata": {},
                            "os-vol-tenant-attr:tenant_id": state["owner"],
                        }
                    },
                )
            if path.endswith(f"/os-volume-transfer/{TRANSFER}") or path.endswith(f"/volume-transfers/{TRANSFER}"):
                if state["pending"]:
                    return self.reply(200, {"transfer": {"id": TRANSFER, "volume_id": VOLUME}})
            return self.reply(404, {"itemNotFound": {"message": "missing"}})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            path = urlsplit(self.path).path
            if path == "/identity/v3/auth/tokens":
                supplied = body["auth"]["identity"]["token"]["id"]
                project = body["auth"]["scope"]["project"]["id"]
                state["exchanges"].append((supplied, project))
                if supplied not in {"executor-root", "human-unscoped-root"} or (
                    supplied == "human-unscoped-root" and state["deny_scope"]
                ):
                    return self.reply(403, {"error": {"code": 403, "title": "Forbidden"}})
                user, home, domain = (
                    ("executor", "Default", "Default") if project == EXECUTOR else ("human", "accounts", DOMAIN)
                )
                if supplied == "human-unscoped-root":
                    defect = state["wrong_identity"]
                    user = "different-human" if defect == "user" else user
                    home = "other-accounts" if defect == "home" else home
                    project = EXECUTOR if defect == "project" else project
                    domain = "Default" if defect in {"project", "domain"} else domain
                token = f"issued-{len(state['exchanges'])}"
                state["tokens"][token] = project
                return self.reply(
                    201,
                    {
                        "token": {
                            "methods": ["token"],
                            "issued_at": "2026-01-01T00:00:00Z",
                            "expires_at": "2099-01-01T00:00:00Z",
                            "user": {"id": user, "name": user, "domain": {"id": home, "name": home}},
                            "project": {"id": project, "name": "DMSLAB", "domain": {"id": domain, "name": domain}},
                            "roles": [{"id": "member", "name": "member"}],
                            "catalog": [
                                {
                                    "type": service,
                                    "name": service,
                                    "endpoints": [{"interface": "public", "region": "fixture", "url": url}],
                                }
                                for service, url in [
                                    ("identity", endpoint + "/identity/v3"),
                                    ("volumev3", f"{endpoint}/cinder/v3/{project}"),
                                ]
                            ],
                        }
                    },
                    token,
                )
            token = self.headers.get("X-Auth-Token")
            project = state["tokens"].get(token)
            observed = {"project": project, "path": path, "project_header": self.headers.get("X-Project-Id")}
            if path.endswith("/accept"):
                state["accepts"].append(observed)
                if state["redirect_status"]:
                    return self.reply(state["redirect_status"], {}, location=redirect_endpoint)
                if state["native_status"] != 202:
                    return self.reply(state["native_status"], {"error": {"message": "native refusal"}})
                if body.get("accept", {}).get("auth_key") != KEY:
                    return self.reply(400, {"badRequest": {"message": "Invalid auth key"}})
                # Cinder assigns the token's project, never X-Project-Id.
                state.update(owner=state["accepted_owner"] or project, pending=False)
                return self.reply(202, {"transfer": {"id": TRANSFER, "volume_id": VOLUME}})
            if path.endswith("/os-volume-transfer") or path.endswith("/volume-transfers"):
                state["creates"].append(observed)
                if state["redirect_status"]:
                    return self.reply(state["redirect_status"], {}, location=redirect_endpoint)
                if state["native_status"] != 202:
                    return self.reply(state["native_status"], {"error": {"message": "native refusal"}})
                if project != EXECUTOR or body.get("transfer", {}).get("volume_id") != VOLUME:
                    return self.reply(403, {"error": {"message": "not authorized"}})
                state["pending"] = True
                return self.reply(202, {"transfer": {"id": TRANSFER, "volume_id": VOLUME, "auth_key": KEY}})
            return self.reply(404, {"error": {"message": "unsupported"}})

    class RedirectSink(Handler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            token = self.headers.get("X-Auth-Token")
            state["redirected"].append({"token": token, "body": body})
            if "accept" in body:
                state.update(owner=state["tokens"].get(token), pending=False)
            else:
                state["pending"] = True
            self.reply(202, {"transfer": {"id": TRANSFER, "volume_id": VOLUME, "auth_key": KEY}})

    redirect_server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSink)
    redirect_endpoint = f"http://127.0.0.1:{redirect_server.server_port}/redirected-transfer"
    redirect_thread = threading.Thread(target=redirect_server.serve_forever, daemon=True)
    redirect_thread.start()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    settings = SimpleNamespace(
        os_auth_url=endpoint + "/identity/v3", os_region_name="fixture", os_interface="public", ssl_verify=True
    )
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    operator = keystone.get_openstack_connection("executor-root", EXECUTOR)
    principal = {
        "token": "human-current-project-token",
        "session_token": "human-unscoped-root",
        "user_id": "human",
        "identity_domain_id": "accounts",
        "is_system_admin": True,
    }
    application = FastAPI()
    application.include_router(_volume_transfer_router, prefix="/api/v1/admin")
    application.dependency_overrides[require_admin] = lambda: principal
    application.dependency_overrides[get_admin_os_conn] = lambda: operator
    ledger_session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))

    @asynccontextmanager
    async def ledger():
        yield ledger_session

    monkeypatch.setattr("app.database.get_session_factory", lambda: ledger)
    for name in ("_invalidate_transfer_accept", "_invalidate_volume_recovery_caches", "rec"):
        monkeypatch.setattr(f"app.api.identity.admin.{name}", AsyncMock())
    try:
        async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
            yield SimpleNamespace(client=client, state=state, principal=principal, application=application)
    finally:
        operator.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        redirect_server.shutdown()
        redirect_server.server_close()
        redirect_thread.join(timeout=5)


@pytest.mark.asyncio
async def test_cross_domain_acceptance_uses_automatically_issued_target_token(native_transfer):
    p = native_transfer
    created = await p.client.post(CREATE, json={})
    assert created.status_code == 201 and created.json()["auth_key"] == KEY
    response = await p.client.post(ACCEPT, json=BODY)
    assert response.status_code == 200 and KEY not in response.text
    assert p.state["owner"] == TARGET and not p.state["pending"]
    assert ("human-unscoped-root", TARGET) in p.state["exchanges"]
    assert all(root != "human-current-project-token" for root, _ in p.state["exchanges"])
    assert [row["project"] for row in p.state["creates"]] == [EXECUTOR]
    [accepted] = p.state["accepts"]
    assert accepted["project"] == TARGET and accepted["project_header"] is None
    assert accepted["path"].startswith(f"/cinder/v3/{TARGET}/")
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.asyncio
async def test_target_authentication_denial_never_falls_back_to_executor(native_transfer):
    p = native_transfer
    assert (await p.client.post(CREATE, json={})).status_code == 201
    p.state["deny_scope"] = True
    response = await p.client.post(ACCEPT, json=BODY)
    assert response.status_code == 403 and KEY not in response.text
    assert p.state["owner"] == SOURCE and p.state["pending"]
    assert p.state["accepts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["user", "home", "project", "domain"])
async def test_native_minted_identity_mismatch_is_rejected_before_cinder(native_transfer, defect):
    p = native_transfer
    assert (await p.client.post(CREATE, json={})).status_code == 201
    p.state["wrong_identity"] = defect
    response = await p.client.post(ACCEPT, json=BODY)
    assert response.status_code == 403
    assert p.state["owner"] == SOURCE and p.state["pending"]
    assert p.state["accepts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(401, 403), (403, 403), (413, 413)])
async def test_native_accept_refusal_never_reauthenticates_or_replays(native_transfer, status, expected):
    p = native_transfer
    assert (await p.client.post(CREATE, json={})).status_code == 201
    p.state["native_status"] = status
    response = await p.client.post(ACCEPT, json=BODY)
    assert response.status_code == expected and KEY not in response.text
    assert p.state["owner"] == SOURCE and p.state["pending"]
    assert [row["project"] for row in p.state["accepts"]] == [TARGET]
    assert [root for root, _ in p.state["exchanges"]].count("human-unscoped-root") == 1


@pytest.mark.asyncio
async def test_native_create_401_is_not_reauthenticated_or_replayed(native_transfer):
    p = native_transfer
    p.state["native_status"] = 401
    response = await p.client.post(CREATE, json={})
    assert response.status_code == 403
    assert p.state["owner"] == SOURCE and not p.state["pending"]
    assert [row["project"] for row in p.state["creates"]] == [EXECUTOR]
    assert p.state["exchanges"] == [("executor-root", EXECUTOR)]


@pytest.mark.asyncio
async def test_cinder_success_into_service_project_is_not_reported_as_transfer_success(native_transfer):
    p = native_transfer
    assert (await p.client.post(CREATE, json={})).status_code == 201
    p.state["accepted_owner"] = EXECUTOR
    response = await p.client.post(ACCEPT, json=BODY)
    assert response.status_code == 502 and KEY not in response.text
    assert p.state["owner"] == EXECUTOR and not p.state["pending"]
    assert [row["project"] for row in p.state["accepts"]] == [TARGET]
    assert response.headers["cache-control"] == "no-store, private"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["create", "accept"])
@pytest.mark.parametrize("status", [307, 308])
async def test_transfer_redirect_never_reposts_or_forwards_native_token_and_key(native_transfer, operation, status):
    p = native_transfer
    if operation == "accept":
        assert (await p.client.post(CREATE, json={})).status_code == 201
    p.state["redirect_status"] = status
    response = await p.client.post(
        CREATE if operation == "create" else ACCEPT, json={} if operation == "create" else BODY
    )
    assert p.state["redirected"] == []
    assert response.status_code == 502 and KEY not in response.text
    assert p.state["owner"] == SOURCE and p.state["pending"] is (operation == "accept")
    assert [row["project"] for row in p.state["creates" if operation == "create" else "accepts"]] == [
        EXECUTOR if operation == "create" else TARGET
    ]
    assert response.headers["cache-control"] == "no-store, private"
