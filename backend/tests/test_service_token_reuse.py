"""Service-account token reuse against a loopback Keystone (real keystoneauth/keystoneclient)."""

from __future__ import annotations

import json
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.services import keystone
from app.services.native_operation import NativeOperation


class _Keystone:
    def __init__(self):
        self.lock = threading.Lock()
        self.password_logins = 0
        self.valid: set[str] = set()
        self.lifetime = timedelta(hours=1)
        self.base = ""

    def issue(self) -> tuple[str, dict]:
        with self.lock:
            self.password_logins += 1
            token = f"service-{self.password_logins}"
            self.valid.add(token)
        expires = (datetime.now(UTC) + self.lifetime).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        endpoint = {"interface": "public", "region": "RegionOne", "region_id": "RegionOne", "url": self.base}
        body = {
            "token": {
                "methods": ["password"],
                "expires_at": expires,
                "issued_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.000000Z"),
                "user": {"id": "svc", "name": "afterglow", "domain": {"id": "default", "name": "Default"}},
                "project": {"id": "admin-p", "name": "admin", "domain": {"id": "default", "name": "Default"}},
                "roles": [{"id": "admin-role", "name": "admin"}],
                "catalog": [{"type": "identity", "name": "keystone", "id": "ks", "endpoints": [endpoint]}],
            }
        }
        return token, body

    def revoke_all(self):
        with self.lock:
            self.valid.clear()


@pytest.fixture
def native(monkeypatch):
    state = _Keystone()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def _send(self, status, body=None, headers=None):
            payload = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.rstrip("/") != "/v3/auth/tokens":
                return self._send(404)
            token, body = state.issue()
            self._send(201, body, {"X-Subject-Token": token})

        def do_GET(self):
            if self.headers.get("X-Auth-Token") not in state.valid:
                return self._send(401, {"error": {"code": 401, "message": "unauthorized"}})
            if self.path.startswith("/v3/domains"):
                return self._send(200, {"domains": [{"id": "default", "name": "Default", "enabled": True}]})
            self._send(404)

    class Server(ThreadingHTTPServer):
        request_queue_size = 32

    server = Server(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state.base = f"http://127.0.0.1:{server.server_port}/v3"
    settings = SimpleNamespace(
        os_auth_url=state.base,
        os_username="afterglow",
        os_password="secret",
        os_project_name="admin",
        os_user_domain_name="Default",
        os_project_domain_name="Default",
        ssl_verify=False,
        os_interface="public",
        os_region_name="RegionOne",
    )
    state.settings = settings
    monkeypatch.setattr(keystone, "get_settings", lambda: settings)
    monkeypatch.setattr(keystone, "_service_cache", None, raising=False)
    try:
        yield state
    finally:
        server.shutdown()
        server.server_close()


def _list_domains():
    with NativeOperation() as operation:
        return [d.id for d in operation.ks.domains.list()]


def test_independent_operations_reuse_one_service_login(native):
    for _ in range(5):
        assert _list_domains() == ["default"]
    standalone = keystone._get_admin_ks_client()
    assert [d.id for d in standalone.domains.list()] == ["default"]
    assert native.password_logins == 1


def test_concurrent_first_use_logs_in_once(native):
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _list_domains(), range(16)))
    assert results == [["default"]] * 16
    assert native.password_logins == 1


def test_rejected_service_token_is_replaced_once_and_shared(native):
    assert _list_domains() == ["default"]
    native.revoke_all()
    assert _list_domains() == ["default"]
    assert native.password_logins == 2
    for _ in range(3):
        assert _list_domains() == ["default"]
    assert native.password_logins == 2


def test_token_inside_renewal_window_is_renewed_before_use(native):
    native.lifetime = timedelta(seconds=keystone._ServiceTokenCache.RENEW_BEFORE_SECONDS - 60)
    _list_domains()
    _list_domains()
    assert native.password_logins == 2


def test_credential_change_never_reuses_previous_service_token(native):
    _list_domains()
    native.settings.os_password = "rotated"
    _list_domains()
    assert native.password_logins == 2


def test_failed_renewal_is_shared_by_concurrent_waiters_and_can_recover(native, monkeypatch):
    """One failed native login fans out to waiters, rather than ten serial logins."""
    cache = keystone._service_token_cache(native.settings)
    all_waiting = threading.Event()
    barrier = threading.Barrier(10)
    lock = threading.Lock()
    waiting = 0
    attempts = 0

    class ObservedFuture(Future):
        def result(self, timeout=None):
            nonlocal waiting
            with lock:
                waiting += 1
                if waiting == 9:
                    all_waiting.set()
            return super().result(timeout=5)

    def unavailable():
        nonlocal attempts
        attempts += 1
        assert all_waiting.wait(5), "concurrent callers did not join the pending login"
        raise RuntimeError("native unavailable")

    def call(_):
        barrier.wait(timeout=5)
        with pytest.raises(RuntimeError, match="native unavailable"):
            cache.access()

    original = cache._login
    monkeypatch.setattr(keystone, "Future", ObservedFuture)
    monkeypatch.setattr(cache, "_login", unavailable)
    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(call, range(10)))
    assert attempts == 1
    monkeypatch.setattr(cache, "_login", original)
    assert _list_domains() == ["default"]
    assert native.password_logins == 1


def test_late_rejection_of_old_service_token_does_not_evict_new_one(native):
    cache = keystone._service_token_cache(native.settings)
    old = cache.access()
    cache.invalidate(old)
    replacement = cache.access()
    assert replacement.auth_token != old.auth_token
    cache.invalidate(old)
    assert cache.access().auth_token == replacement.auth_token
    assert native.password_logins == 2
