"""Real native HTTP must not replay a credential or forward it to another origin."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from app.services import account_recovery, admin_password_reset


@pytest.mark.parametrize("writer", ["recovery", "admin"])
@pytest.mark.parametrize("status", [307, 401])
def test_password_write_does_not_replay_or_forward_secrets(monkeypatch, writer, status, caplog):
    seen = []
    forwarded = []
    password = "Synthetic-transport-boundary-129!"
    credential = "synthetic-native-credential-529"

    class Sink(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_PATCH(self):
            forwarded.append(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            self.send_response(200)
            self.end_headers()

        do_POST = do_PATCH

    sink = ThreadingHTTPServer(("127.0.0.1", 0), Sink)

    class Native(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_PATCH(self):
            seen.append(
                (self.headers.get("X-Auth-Token"), json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            )
            self.send_response(status)
            if status == 307:
                self.send_header("Location", f"http://127.0.0.1:{sink.server_port}/capture")
            self.end_headers()

        do_POST = do_PATCH

    native = ThreadingHTTPServer(("127.0.0.1", 0), Native)
    threads = [threading.Thread(target=server.serve_forever, daemon=True) for server in (native, sink)]
    for thread in threads:
        thread.start()
    settings = SimpleNamespace(os_auth_url=f"http://127.0.0.1:{native.server_port}/v3", ssl_verify=True)
    module = account_recovery if writer == "recovery" else admin_password_reset
    monkeypatch.setattr(module, "get_settings", lambda: settings)
    try:
        if writer == "recovery":
            response, _ = module._initial_request(
                credential, "POST", "users/target/OS-AFTERGLOW/password-reset", body={"user": {"password": password}}
            )
        else:
            response, _ = module._native_update(credential, "target", password)
        assert response == status
        assert seen == [
            (
                credential,
                {"user": {"password": password, **({"afterglow_local_password": True} if writer == "admin" else {})}},
            )
        ]
        assert forwarded == []
        assert password not in caplog.text and credential not in caplog.text
    finally:
        for server, thread in zip((native, sink), threads):
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)
            assert not thread.is_alive()
