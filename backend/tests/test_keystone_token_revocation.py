"""Installed SDK revocation transport: synthetic HTTP only, no native cloud."""

import json

import pytest
import requests
from keystoneauth1 import session as ks_session
from keystoneauth1 import token_endpoint
from keystoneclient.v3 import client as ks_client

from app.services import keystone


class NativeTokenWire(requests.adapters.BaseAdapter):
    def __init__(self, status, message="Token revocation rejected"):
        self.status = status
        self.message = message
        self.requests = []
        self.closed = False

    def send(self, request, **kwargs):
        self.requests.append(request)
        response = requests.Response()
        response.request = request
        response.url = request.url
        response.status_code = self.status
        response.headers["Content-Type"] = "application/json"
        response._content = (
            b""
            if self.status == 204
            else json.dumps(
                {"error": {"code": self.status, "title": "Native failure", "message": self.message}}
            ).encode()
        )
        return response

    def close(self):
        self.closed = True


def native_client(monkeypatch, status, message="Token revocation rejected"):
    wire = NativeTokenWire(status, message)
    transport = requests.Session()
    transport.mount("https://native.test/", wire)
    auth = token_endpoint.Token(endpoint="https://native.test/v3", token="operator-native-token")
    session = ks_session.Session(auth=auth, session=transport)
    client = ks_client.Client(session=session, endpoint_override="https://native.test/v3")
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: client)
    return wire


def test_native_revocation_uses_operator_auth_and_exact_subject(monkeypatch):
    wire = native_client(monkeypatch, 204)
    keystone.revoke_token("subject-invalidated-by-password-reset")
    assert len(wire.requests) == 1
    request = wire.requests[0]
    assert request.method == "DELETE" and request.url == "https://native.test/v3/auth/tokens"
    assert request.headers["X-Auth-Token"] == "operator-native-token"
    assert request.headers["X-Subject-Token"] == "subject-invalidated-by-password-reset"
    assert wire.closed


@pytest.mark.parametrize("status", [401, 403, 404, 503])
def test_native_revocation_failure_is_not_reported_as_success(monkeypatch, status):
    wire = native_client(monkeypatch, status)
    with pytest.raises(Exception) as caught:
        keystone.revoke_token("owned-native-token")
    assert getattr(caught.value, "http_status", None) == status
    assert wire.requests and wire.requests[-1].headers["X-Auth-Token"] == "operator-native-token"
    assert wire.closed


@pytest.mark.parametrize("message", ["Failed to validate token", "Could not recognize Fernet token"])
def test_native_already_invalid_subject_is_idempotently_revoked(monkeypatch, message):
    wire = native_client(monkeypatch, 404, message)
    keystone.revoke_token("captured-token-already-invalidated-by-reset")
    assert wire.requests[-1].headers["X-Auth-Token"] == "operator-native-token"
    assert wire.requests[-1].headers["X-Subject-Token"] == "captured-token-already-invalidated-by-reset"
    assert wire.closed


@pytest.mark.parametrize(
    "status,message",
    [
        (404, "Proxy upstream route not found"),
        (404, "Failed to validate token from a proxy"),
        (401, "Failed to validate token"),
        (403, "Could not recognize Fernet token"),
    ],
)
def test_proxy_or_unauthorized_token_revocation_is_not_native_absence(monkeypatch, status, message):
    wire = native_client(monkeypatch, status, message)
    with pytest.raises(Exception) as caught:
        keystone.revoke_token("captured-native-token")
    assert getattr(caught.value, "http_status", None) == status
    assert wire.closed
