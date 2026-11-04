"""Installed openstacksdk database proxy: a provider outage is a failure, never an empty inventory."""

import json
import urllib.parse

import pytest
import requests
from keystoneauth1 import session as ks_session
from keystoneauth1.noauth import NoAuth
from openstack.connection import Connection
from requests import Response
from requests.adapters import BaseAdapter

from app.services import trove

ENDPOINT = "http://trove.test/v1.0/test-project"
PRIVATE_BODY = "PRIVATE_NATIVE_TROVE_BODY"
_DISCOVERY_PATHS = {"", "/v1.0", "/v1.0/test-project"}
_VERSION_DOCUMENT = {
    "version": {
        "id": "v1.0",
        "status": "CURRENT",
        "links": [{"rel": "self", "href": "http://trove.test/v1.0/"}],
    }
}


class _InProcessTrove(BaseAdapter):
    """Trove behind the real SDK database Proxy; requests reach this adapter, never a socket.

    SDK version discovery is answered normally; only native reads receive the configured outcome.
    """

    def __init__(self, status: int, body: dict):
        super().__init__()
        self.status = status
        self.body = body
        self.requests: list[tuple[str, str]] = []

    def send(self, request, **_kwargs):
        path = urllib.parse.urlsplit(request.url).path
        if path.rstrip("/") in _DISCOVERY_PATHS:
            status, body = 200, _VERSION_DOCUMENT
        else:
            self.requests.append((request.method, path))
            status, body = self.status, self.body
        payload = json.dumps(body).encode()
        response = Response()
        response.status_code = status
        response._content = payload
        response.headers["Content-Type"] = "application/json"
        response.headers["Content-Length"] = str(len(payload))
        response.url = request.url
        response.request = request
        response.reason = "fixture"
        return response


def _connection(status: int, body: dict):
    provider = _InProcessTrove(status, body)
    http = requests.Session()
    http.mount("http://trove.test/", provider)
    conn = Connection(
        session=ks_session.Session(auth=NoAuth(endpoint=ENDPOINT), session=http),
        database_endpoint_override=ENDPOINT,
        database_api_version="1",
    )
    return conn, provider


# name -> (reader, native path suffix, valid empty body)
_READS = {
    "flavors": (trove.list_flavors, "/flavors", {"flavors": []}),
    "datastores": (trove.list_datastores, "/datastores", {"datastores": []}),
    "configurations": (trove.list_configurations, "/configurations", {"configurations": []}),
    "instances": (trove.list_instances, "/instances", {"instances": []}),
    "backups": (trove.list_backups, "/backups", {"backups": []}),
    "users": (lambda conn: trove.list_users(conn, "inst-1"), "/instances/inst-1/users", {"users": []}),
    "databases": (lambda conn: trove.list_databases(conn, "inst-1"), "/instances/inst-1/databases", {"databases": []}),
}


@pytest.mark.parametrize("status", [401, 403, 404, 500, 503, 504])
@pytest.mark.parametrize("name", list(_READS))
def test_failed_native_read_is_an_error_not_an_empty_inventory(name, status):
    reader, suffix, _ = _READS[name]
    conn, provider = _connection(status, {"error": PRIVATE_BODY})

    with pytest.raises(Exception) as raised:
        reader(conn)

    assert PRIVATE_BODY not in str(raised.value)
    assert provider.requests
    assert all(path.endswith(suffix) for _, path in provider.requests)


@pytest.mark.parametrize("name", list(_READS))
def test_valid_empty_native_read_is_an_empty_inventory_from_one_request(name):
    reader, suffix, empty = _READS[name]
    conn, provider = _connection(200, empty)

    assert reader(conn) == []
    assert [path.endswith(suffix) for _, path in provider.requests] == [True]
