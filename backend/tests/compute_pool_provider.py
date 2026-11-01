"""Synthetic native identity for legacy consumers that have no compute pool.

The production projection/parser still runs against installed SDK transport.
Pool-specific tests override the operator with their own mutable native cloud.
"""

import json
from contextlib import asynccontextmanager
from urllib.parse import unquote, urlsplit

import requests
from keystoneauth1 import noauth
from keystoneauth1 import session as ks_session
from openstack.connection import Connection


class UnmanagedIdentity(requests.adapters.BaseAdapter):
    def __init__(self, domain_policies=None):
        self.domain_policies = domain_policies if domain_policies is not None else {}
        super().__init__()

    def send(self, request, **kwargs):
        path = urlsplit(request.url).path.rstrip("/")
        if path == "/identity/v3":
            body = {
                "version": {
                    "id": "v3.14",
                    "status": "stable",
                    "links": [
                        {"rel": "self", "href": "http://unmanaged-pool.test/identity/v3/"},
                    ],
                }
            }
        elif path.startswith("/identity/v3/projects/"):
            key = unquote(path.rsplit("/", 1)[1])
            body = {"project": {"id": key, "domain_id": "legacy-domain", "enabled": True}}
        elif path.startswith("/identity/v3/domains/"):
            domain_id = unquote(path.rsplit("/", 1)[1])
            body = {"domain": {"id": domain_id, "name": "Legacy", "enabled": True}}
            if domain_id in self.domain_policies:
                body["domain"]["afterglow_compute_pool"] = self.domain_policies[domain_id]
        else:
            raise AssertionError(f"Unexpected unmanaged pool provider request: {request.method} {path}")
        if request.method != "GET":
            raise AssertionError("Legacy pool fixture is read-only")
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        response.url, response.request = request.url, request
        response._content_consumed = True
        return response

    def close(self):
        pass


@asynccontextmanager
async def unmanaged_pool_operator(domain_policies=None):
    transport = requests.Session()
    transport.mount("http://unmanaged-pool.test/", UnmanagedIdentity(domain_policies))
    conn = Connection(
        session=ks_session.Session(auth=noauth.NoAuth(), session=transport),
        identity_endpoint_override="http://unmanaged-pool.test/identity/v3",
        compute_endpoint_override="http://unmanaged-pool.test/compute/v2.1",
        placement_endpoint_override="http://unmanaged-pool.test/placement",
    )
    try:
        yield conn
    finally:
        conn.close()
