"""Installed SDK/native HTTP name recovery under a fixed-admin usage binding.

Identity and provider data are synthetic; native query serialization and owner /
marker checks run unchanged. No cloud writes or administrator fallback are used.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from keystoneauth1.session import Session
from keystoneauth1.token_endpoint import Token
from openstack.connection import Connection

from app.config import get_settings
from app.services import build_work, layer_build
from app.services import instance_usage as usage

PROJECT = "scheduled-target"
ADMIN = "fixed-admin-project"
MARKER = {"afterglow_consume_token": "synthetic-receipt-token"}


@pytest.fixture
def catalog_operator_native(monkeypatch):
    state = SimpleNamespace(calls=[], foreign_only=False)
    access = SimpleNamespace(
        project_id=ADMIN,
        user_id="fixed-operator",
        project_scoped=True,
        system_scoped=False,
        is_admin_project=True,
        auth_token="synthetic-native-token",
        role_names=["admin"],
        _data={"token": {"is_admin_project": True}},
    )

    class OperatorToken(Token):
        def get_access(self, session):
            return access

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, body):
            data = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            request = urlsplit(self.path)
            path, query = request.path.rstrip("/"), parse_qs(request.query)
            kinds = {
                "servers/detail": ("server", "servers"),
                "volumes/detail": ("volume", "volumes"),
                "ports": ("port", "ports"),
                "shares/detail": ("share", "shares"),
            }
            for suffix, (kind, collection) in kinds.items():
                if not path.endswith("/" + suffix):
                    continue
                state.calls.append((kind, query))
                all_projects = str(query.get("all_tenants", [""])[0]).lower() in {"true", "1"}
                target = query.get("project_id") == [PROJECT]
                # Nova/Cinder/Manila otherwise list only the authenticated admin
                # project, not the independently bound usage target.
                if kind != "port" and not (all_projects and target):
                    return self.reply(200, {collection: []})
                owner = "foreign-project" if state.foreign_only else PROJECT
                resource = {"id": kind + "-target", "name": "exact-name", "metadata": dict(MARKER)}
                if kind == "server":
                    resource.update(tenant_id=owner, status="ACTIVE")
                elif kind == "volume":
                    resource["os-vol-tenant-attr:tenant_id"] = owner
                else:
                    resource["project_id"] = owner
                if kind == "port":
                    resource["description"] = json.dumps(MARKER)
                return self.reply(200, {collection: [resource]})
            if path.startswith("/compute"):
                return self.reply(
                    200,
                    {
                        "version": {
                            "id": "v2.1",
                            "status": "CURRENT",
                            "min_version": "2.1",
                            "version": "2.96",
                            "links": [{"rel": "self", "href": endpoint + "/compute/v2.1/"}],
                        }
                    },
                )
            if path.startswith("/volume"):
                return self.reply(
                    200,
                    {
                        "version": {
                            "id": "v3.0",
                            "status": "CURRENT",
                            "min_version": "3.0",
                            "version": "3.70",
                            "links": [{"rel": "self", "href": endpoint + "/volume/v3/"}],
                        }
                    },
                )
            if path.startswith("/network"):
                return self.reply(
                    200,
                    {
                        "version": {
                            "id": "v2.0",
                            "status": "CURRENT",
                            "links": [{"rel": "self", "href": endpoint + "/network/v2.0/"}],
                        }
                    },
                )
            self.reply(404, {"error": "unexpected synthetic endpoint"})

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{httpd.server_port}"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=Session(auth=OperatorToken(endpoint, "synthetic-native-token")),
        compute_endpoint_override=endpoint + f"/compute/v2.1/{ADMIN}",
        compute_api_version="2",
        block_storage_endpoint_override=endpoint + f"/volume/v3/{ADMIN}",
        block_storage_api_version="3",
        network_endpoint_override=endpoint + "/network/v2.0",
        network_api_version="2",
    )
    conn._afterglow_token = "synthetic-native-token"
    monkeypatch.setattr(get_settings(), "os_manila_endpoint", endpoint + f"/manila/v2/{ADMIN}")
    usage.bind_operator_scope(conn, PROJECT)
    state.conn, state.access = conn, access
    try:
        yield state
    finally:
        conn.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("kind", ["server", "volume", "port", "share"])
def test_operator_name_recovery_observes_bound_tenant_instead_of_false_absence(catalog_operator_native, kind):
    state = catalog_operator_native
    found = layer_build._layer_resource(
        state.conn, kind, None, name="exact-name", project_id=PROJECT, marker=MARKER, allow_absent=True
    )
    assert found is not None and (found.get("id") if isinstance(found, dict) else found.id) == kind + "-target"
    assert state.conn._afterglow_project_id == ADMIN


@pytest.mark.parametrize("kind", ["server", "volume", "port", "share"])
def test_operator_name_recovery_never_adopts_provider_foreign_owner(catalog_operator_native, kind):
    state = catalog_operator_native
    state.foreign_only = True
    assert (
        layer_build._layer_resource(
            state.conn, kind, None, name="exact-name", project_id=PROJECT, marker=MARKER, allow_absent=True
        )
        is None
    )


@pytest.mark.parametrize("invalid", ["target", "native-user", "native-project", "binding"])
def test_operator_resource_recovery_rejects_stale_scope_before_native_list(catalog_operator_native, invalid):
    state = catalog_operator_native
    target = PROJECT
    if invalid == "target":
        target = "foreign-project"
    elif invalid == "native-user":
        state.access.user_id = "foreign-operator"
    elif invalid == "native-project":
        state.access.project_id = "foreign-admin"
    else:
        state.conn._afterglow_usage_operator_scope = SimpleNamespace(target_project_id=PROJECT)
    with pytest.raises((HTTPException, build_work.SubmissionUnknown)):
        layer_build._layer_resource(
            state.conn, "server", None, name="exact-name", project_id=target, marker=MARKER, allow_absent=True
        )
    assert state.calls == []
