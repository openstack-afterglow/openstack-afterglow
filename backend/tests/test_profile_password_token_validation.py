"""Actual Keystoneclient GET errors must preserve subject-vs-service authority."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from keystoneauth1 import session as native_session
from keystoneauth1 import token_endpoint
from keystoneclient.v3 import client as native_client

from tests.test_account_recovery import REPLACEMENT, persisted
from tests.test_account_recovery import directory as directory
from tests.test_profile_password_creation import BASE, COMPLETE, issue
from tests.test_profile_password_creation import creation as creation
from tests.test_profile_password_creation import creation_client as creation_client
from tests.test_profile_password_creation import recoveries as recoveries

pytestmark = pytest.mark.asyncio


@pytest.fixture
def native_token_http(creation):
    state = SimpleNamespace(status=200, message="", requests=[], user="external", home="home")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            state.requests.append(
                (self.command, self.path, self.headers.get("X-Auth-Token"), self.headers.get("X-Subject-Token"))
            )
            if state.status == 200:
                body = {
                    "token": {
                        "methods": ["mapped"],
                        "user": {"id": state.user, "name": "external", "domain": {"id": state.home}},
                        "issued_at": "2026-10-29T00:00:00.000000Z",
                        "expires_at": "2030-01-01T00:00:00.000000Z",
                    }
                }
            else:
                body = {"error": {"code": state.status, "message": state.message, "title": "Synthetic native error"}}
            raw = json.dumps(body).encode()
            self.send_response(state.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}/v3"
    session = native_session.Session(auth=token_endpoint.Token(base, "synthetic-service-token"))
    client = native_client.Client(session=session, endpoint=base)
    creation.ks.tokens = client.tokens
    try:
        yield state
    finally:
        session.session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.parametrize(
    "status,message,expected,code",
    [
        (404, "Failed to validate token", 401, "password_create_session_invalid"),
        (404, "Could not recognize Fernet token", 401, "password_create_session_invalid"),
        (404, "Proxy upstream route not found", 503, "password_create_session_unavailable"),
        (401, "Service credential expired", 503, "password_create_session_unavailable"),
        (403, "Service validation forbidden", 503, "password_create_session_unavailable"),
    ],
)
async def test_native_token_error_classification_before_create(
    creation, creation_client, native_token_http, status, message, expected, code
):
    native_token_http.status, native_token_http.message = status, message
    response = await creation_client.post(BASE + "/create/request", json={})
    assert response.status_code == expected
    assert response.json()["detail"]["code"] == code
    assert not creation.sent and not creation.posts
    assert native_token_http.requests == [
        ("GET", "/v3/auth/tokens?nocatalog", "synthetic-service-token", creation.actor["session_token"])
    ]


@pytest.mark.parametrize(
    "status,message,expected,code",
    [
        (404, "Failed to validate token", 401, "password_create_session_invalid"),
        (404, "Could not recognize Fernet token", 401, "password_create_session_invalid"),
        (404, "Proxy upstream route not found", 503, "password_create_session_unavailable"),
        (401, "Service credential expired", 503, "password_create_session_unavailable"),
        (403, "Service validation forbidden", 503, "password_create_session_unavailable"),
    ],
)
async def test_native_token_error_after_mail_never_consumes_or_writes(
    creation, creation_client, native_token_http, recoveries, status, message, expected, code
):
    token = await issue(creation_client, creation)
    native_token_http.status, native_token_http.message = status, message
    response = await creation_client.post(COMPLETE, json={"token": token, "new_password": REPLACEMENT})
    assert response.status_code == expected
    assert response.json()["detail"]["code"] == code
    assert not creation.posts
    assert (await persisted(recoveries, token)).status == "pending"


@pytest.mark.parametrize("stage", ["before_mail", "after_mail"])
async def test_actual_native_get_validates_returned_subject_not_echoed_token(
    creation, creation_client, native_token_http, recoveries, stage
):
    token = await issue(creation_client, creation) if stage == "after_mail" else None
    native_token_http.user = "other-user"
    response = (
        await creation_client.post(COMPLETE, json={"token": token, "new_password": REPLACEMENT})
        if token
        else await creation_client.post(BASE + "/create/request", json={})
    )
    assert response.status_code == 403
    assert not creation.posts
    if token:
        assert (await persisted(recoveries, token)).status == "pending"
    else:
        assert not creation.sent
