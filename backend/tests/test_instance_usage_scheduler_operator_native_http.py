"""Default scheduler factories, installed SDK/Password auth, real loopback HTTP.

Keystone and Nova below are synthetic native services, not a production cloud.
Only coordinator/Redis state, the clock, configuration and the empty managed
receipt store are fixtures. No connection factory, auth plugin, provider proxy,
operator binding or native scope proof is replaced. Human authority is not tested.
"""

import json
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi import HTTPException

from app.services import instance_usage as usage
from app.services import instance_usage_cleanup as cleanup
from app.services import instance_usage_scheduler as scheduler
from app.services import keystone

PROJECT = "scheduled-tenant"
ADMIN_PROJECT = "fixed-admin-project"
ADMIN_NAME = "synthetic-admin"
USER = "synthetic-operator"
SERVER = "scheduled-server"
FOREIGN_SERVER = "foreign-server"
FOREIGN_PROJECT = "foreign-tenant"
NOW = datetime(2026, 10, 31, 12, tzinfo=UTC)


class CoordinationRedis:
    """Finite owner-checked usage-lock fixture; no schedule data is stored here."""

    def __init__(self):
        self.items = {}

    async def set(self, key, owner, **_):
        if key in self.items:
            return False
        self.items[key] = owner
        return True

    async def eval(self, script, _, key, owner, *_args):
        if self.items.get(key) != owner:
            return 0
        if "redis.call('del'" in script:
            self.items.pop(key)
        return 1


class Coordinator:
    """Single-participant queue fixture, not a Redis/HA qualification."""

    prefix = scheduler._PREFIX

    def __init__(self):
        self.redis = CoordinationRedis()
        self.queue = []
        self.published = []

    async def is_leader(self):
        return True

    async def publish(self, members):
        self.published.append(list(members))
        self.queue = list(members)

    async def pending(self):
        return len(self.queue)

    async def claim(self, _seconds):
        return (self.queue.pop(0), "synthetic-claim") if self.queue else None


@pytest.fixture
def operator_native_http(monkeypatch):
    state = {
        "metadata": {"unrelated": "preserve"},
        "foreign_metadata": {"unrelated": "foreign-preserve"},
        "failure": None,
        "auth_requests": [],
        "issued_identities": [],
        "gets": [],
        "exact_gets": 0,
        "writes": [],
        "unexpected": [],
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value, *, token=None):
            payload = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            if token:
                self.send_header("X-Subject-Token", token)
            self.end_headers()
            self.wfile.write(payload)

        def body(self):
            return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")

        def native_server(self, *, census=False, foreign=False):
            identity = FOREIGN_SERVER if foreign else SERVER
            owner = FOREIGN_PROJECT if foreign else PROJECT
            if not foreign and not census:
                if state["failure"] == "foreign-owner" or (
                    state["failure"] == "owner-drift" and state["exact_gets"] >= 3
                ):
                    owner = FOREIGN_PROJECT
                if state["failure"] == "server-drift" and state["exact_gets"] >= 3:
                    identity = FOREIGN_SERVER
            return {
                "id": identity,
                "tenant_id": owner,
                "name": "synthetic native server",
                "status": "ACTIVE",
                "metadata": dict(state["foreign_metadata"] if foreign else state["metadata"]),
                "flavor": {
                    "original_name": "small" if foreign else "large",
                    "vcpus": 1 if foreign else 12,
                    "ram": 8192,
                    "disk": 0,
                    "extra_specs": {},
                },
                "OS-EXT-STS:task_state": None,
                "os-extended-volumes:volumes_attached": [],
            }

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            state["gets"].append(path)
            if path in {"/identity", "/identity/v3"}:
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
            if path in {"/compute", "/compute/v2.1", f"/compute/v2.1/{ADMIN_PROJECT}"}:
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
            if self.headers.get("X-Auth-Token") != "synthetic-operator-token":
                return self.reply(401, {"error": {"message": "synthetic token required"}})
            if path == f"/compute/v2.1/{ADMIN_PROJECT}/servers/detail":
                return self.reply(200, {"servers": [self.native_server(census=True), self.native_server(foreign=True)]})
            if path == f"/compute/v2.1/{ADMIN_PROJECT}/flavors/detail":
                return self.reply(
                    200,
                    {
                        "flavors": [
                            {
                                "id": "large",
                                "name": "large",
                                "vcpus": 12,
                                "ram": 8192,
                                "disk": 0,
                                "extra_specs": {},
                                "os-flavor-access:is_public": True,
                            }
                        ]
                    },
                )
            if path == f"/compute/v2.1/{ADMIN_PROJECT}/servers/{SERVER}":
                state["exact_gets"] += 1
                return self.reply(200, {"server": self.native_server()})
            state["unexpected"].append(("GET", path))
            self.reply(404, {"error": {"message": "unexpected synthetic endpoint"}})

        def do_POST(self):
            path = urlsplit(self.path).path.rstrip("/")
            body = self.body()
            if path == "/identity/v3/auth/tokens":
                # Every value is fixture-owned, including this captured password.
                state["auth_requests"].append(body)
                auth = body.get("auth", {})
                project = auth.get("scope", {}).get("project", {})
                password = auth.get("identity", {}).get("password", {}).get("user", {})
                if project != {"name": ADMIN_NAME, "domain": {"name": "Default"}}:
                    return self.reply(401, {"error": {"message": "operator has no tenant membership"}})
                if (
                    auth.get("identity", {}).get("methods") != ["password"]
                    or password.get("name") != USER
                    or password.get("password") != "synthetic-password"
                    or password.get("domain") != {"name": "Default"}
                ):
                    return self.reply(401, {"error": {"message": "wrong synthetic identity"}})
                now = datetime.now(UTC)
                # Valid short-lived responses exercise actual KSA refresh; after
                # the second exact Nova GET the next real token changes identity.
                refreshing = state["failure"] in {"user-drift", "scope-drift"}
                drifted = refreshing and state["exact_gets"] >= 2
                user_id = "different-operator" if drifted and state["failure"] == "user-drift" else USER
                project_id = FOREIGN_PROJECT if drifted and state["failure"] == "scope-drift" else ADMIN_PROJECT
                state["issued_identities"].append((project_id, user_id))
                catalog = [
                    {
                        "id": kind,
                        "name": name,
                        "type": kind,
                        "endpoints": [
                            {
                                "id": kind + "-public",
                                "interface": "public",
                                "region": "RegionOne",
                                "url": endpoint + suffix,
                            }
                        ],
                    }
                    for kind, name, suffix in (
                        ("identity", "keystone", "/identity/v3"),
                        ("compute", "nova", f"/compute/v2.1/{ADMIN_PROJECT}"),
                    )
                ]
                role = "reader" if state["failure"] == "admin-role" else "admin"
                return self.reply(
                    201,
                    {
                        "token": {
                            "methods": ["password"],
                            "issued_at": (now - timedelta(minutes=1)).isoformat(),
                            "expires_at": (now + timedelta(seconds=30 if refreshing else 3600)).isoformat(),
                            "audit_ids": ["synthetic-audit"],
                            "is_admin_project": state["failure"] != "admin-claim",
                            "user": {"id": user_id, "name": USER, "domain": {"id": "default", "name": "Default"}},
                            "project": {
                                "id": project_id,
                                "name": ADMIN_NAME,
                                "domain": {"id": "default", "name": "Default"},
                            },
                            "roles": [{"id": "synthetic-role", "name": role}],
                            "catalog": catalog,
                        }
                    },
                    token="synthetic-operator-token",
                )
            self.mutate(path, body)

        def mutate(self, path, body):
            state["writes"].append((self.command, path, body))
            # Installed SDK 3.3 set_server_metadata uses Nova's merge POST,
            # not PUT (which replaces the complete native metadata collection).
            if (
                self.command == "POST"
                and path == f"/compute/v2.1/{ADMIN_PROJECT}/servers/{SERVER}/metadata"
                and self.headers.get("X-Auth-Token") == "synthetic-operator-token"
            ):
                state["metadata"].update(body["metadata"])
                return self.reply(200, {"metadata": state["metadata"]})
            self.reply(403, {"error": {"message": "non-adoption mutation forbidden"}})

        def do_PUT(self):
            self.mutate(urlsplit(self.path).path.rstrip("/"), self.body())

        do_DELETE = do_PUT
        do_PATCH = do_PUT

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{httpd.server_port}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    settings = SimpleNamespace(
        os_auth_url=endpoint + "/identity/v3",
        os_username=USER,
        os_password="synthetic-password",
        os_project_name=ADMIN_NAME,
        os_user_domain_name="Default",
        os_project_domain_name="Default",
        os_region_name="RegionOne",
        os_interface="public",
        ssl_verify=True,
        instance_usage_adoption_reference_at="",
    )
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "get_settings", lambda: settings)
    monkeypatch.setattr(scheduler, "_clock", lambda now=None: now or NOW)
    # No managed delete receipts exist in this enrollment-only scenario.
    monkeypatch.setattr(cleanup, "get_session_factory", lambda: None)

    @asynccontextmanager
    async def coordinator_lease(_dispatcher, member, owner, *, seconds):
        assert member == f"{PROJECT}:{SERVER}" and owner == "synthetic-claim" and seconds > 0
        yield

    monkeypatch.setattr(scheduler, "work_lease", coordinator_lease)
    try:
        yield SimpleNamespace(state=state, coordinator=Coordinator())
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def assert_only_fixed_admin_auth(state):
    assert state["auth_requests"]
    for body in state["auth_requests"]:
        assert body["auth"]["scope"] == {"project": {"name": ADMIN_NAME, "domain": {"name": "Default"}}}
    assert state["foreign_metadata"] == {"unrelated": "foreign-preserve"}
    assert state["unexpected"] == []


@pytest.mark.asyncio
async def test_default_scheduler_adopts_with_fixed_admin_password_scope_once(operator_native_http):
    native = operator_native_http
    # Deliberately omit BOTH native connection factories: this is the consumer
    # regression for the production default, not an injected transport fixture.
    await scheduler.scheduler_tick(now=NOW, dispatcher=native.coordinator)
    state = native.state
    assert_only_fixed_admin_auth(state)
    schedule = usage.parse_schedule({"id": SERVER, "metadata": state["metadata"]})
    assert schedule is not None
    assert schedule.source == "adopted" and schedule.state == "active"
    assert schedule.starts_at == NOW.isoformat()
    assert schedule.expires_at == "2026-11-30T12:00:00+00:00"
    assert schedule.expiry_action == "shelve" and schedule.delete_volumes is False
    assert state["metadata"]["unrelated"] == "preserve"
    assert native.coordinator.published == [[f"{PROJECT}:{SERVER}"]]
    assert len(state["writes"]) == 1
    method, path, body = state["writes"][0]
    assert method == "POST" and path == f"/compute/v2.1/{ADMIN_PROJECT}/servers/{SERVER}/metadata"
    assert set(body) == {"metadata"}
    assert "unrelated" not in body["metadata"]
    assert all(key.startswith(usage.METADATA_PREFIX) for key in body["metadata"])
    original = dict(state["metadata"])
    await scheduler.scheduler_tick(now=NOW, dispatcher=native.coordinator)
    assert state["metadata"] == original and len(state["writes"]) == 1
    assert native.coordinator.published[-1] == []
    assert_only_fixed_admin_auth(state)
    assert all(identity == (ADMIN_PROJECT, USER) for identity in state["issued_identities"])
    assert native.coordinator.redis.items == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "admin-role",
        "admin-claim",
        "foreign-owner",
        "owner-drift",
        "server-drift",
        "user-drift",
        "scope-drift",
    ],
)
async def test_default_scheduler_native_authority_or_owner_drift_never_writes(operator_native_http, failure):
    native = operator_native_http
    native.state["failure"] = failure
    authority_denial = failure in {"admin-role", "admin-claim"}
    try:
        await scheduler.scheduler_tick(now=NOW, dispatcher=native.coordinator)
    except HTTPException as exc:
        # A stricter census may reject the operator before publishing work.
        # Only the invalid native administrator cases may fail at that boundary.
        assert authority_denial and exc.status_code == 503
    state = native.state
    if not authority_denial:
        assert native.coordinator.published == [[f"{PROJECT}:{SERVER}"]]
    assert state["metadata"] == {"unrelated": "preserve"}
    assert state["writes"] == []  # includes metadata, lifecycle and foreign endpoint attempts
    if authority_denial:
        assert state["exact_gets"] == 0
    assert_only_fixed_admin_auth(state)
    if failure in {"user-drift", "scope-drift"}:
        changed = (ADMIN_PROJECT, "different-operator") if failure == "user-drift" else (FOREIGN_PROJECT, USER)
        assert changed in state["issued_identities"]  # real Keystone refresh response, not an injected AccessInfo
    assert native.coordinator.redis.items == {}
