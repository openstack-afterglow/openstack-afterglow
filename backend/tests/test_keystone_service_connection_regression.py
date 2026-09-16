"""Regression coverage for SDK-owned service routing on Keystone connections."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import requests
from keystoneauth1 import access

from app.services import keystone

_SERVICE_ENDPOINTS = {
    "waygate": "https://waygate.internal.test/v1",
    "drover": "https://drover.internal.test/v1",
    "lumen": "https://lumen.internal.test/v1",
    "palimpsest": "https://palimpsest.internal.test/v1",
}


def _settings(**overrides):
    values = {
        "os_auth_url": "https://identity.internal.test/v3",
        "os_username": "afterglow",
        "os_password": "secret",
        "os_project_name": "afterglow-admin",
        "os_user_domain_name": "Default",
        "os_project_domain_name": "Default",
        "os_region_name": "RegionOne",
        "os_interface": "internal",
        "ssl_verify": "/etc/ssl/certs/internal-ca.pem",
        **{f"service_{service_type}_internal_url": endpoint for service_type, endpoint in _SERVICE_ENDPOINTS.items()},
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.parametrize(
    ("factory", "factory_args", "auth_method", "project_scope"),
    [
        (keystone.get_openstack_connection, ("caller-token", "caller-project"), "token", {"id": "caller-project"}),
        (keystone.get_admin_connection_for_project, ("target-project",), "password", {"id": "target-project"}),
        (keystone.get_admin_project_connection, (), "password", {"name": "afterglow-admin"}),
    ],
)
@pytest.mark.parametrize(
    ("service_type", "register", "invoke", "endpoint", "expected_url", "expected_payload"),
    [
        (
            "waygate",
            keystone.get_waygate_proxy,
            lambda proxy: proxy.servers(),
            "https://waygate.internal.test/v1",
            "https://waygate.internal.test/v1/servers",
            {"servers": []},
        ),
        (
            "drover",
            keystone.get_drover_proxy,
            lambda proxy: proxy.clusters(),
            "https://drover.internal.test",
            "https://drover.internal.test/v1/clusters",
            {"clusters": []},
        ),
    ],
)
def test_installed_sdk_uses_configured_destination_without_discovery(
    monkeypatch,
    service_type,
    register,
    invoke,
    endpoint,
    expected_url,
    expected_payload,
    factory,
    factory_args,
    auth_method,
    project_scope,
):
    """Configured SDK calls authenticate and use root or ``/v1`` endpoints without probing them."""
    monkeypatch.delenv("SERVICE_DROVER_INTERNAL_URL", raising=False)
    calls = []

    def request(_session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = requests.Response()
        response.url = url
        if url == "https://identity.internal.test/v3":
            response.status_code = 200
            response._content = json.dumps(
                {"version": {"id": "v3.14", "status": "stable", "links": [{"rel": "self", "href": url + "/"}]}}
            ).encode()
        elif url == "https://identity.internal.test/v3/auth/tokens":
            response.status_code = 201
            response.headers["X-Subject-Token"] = "scoped-token"
            response._content = json.dumps(_token_body(project_id=project_scope.get("id", "admin-project"))).encode()
        elif url == expected_url:
            response.status_code = 200
            response._content = json.dumps(expected_payload).encode()
        else:
            response.status_code = 404
            response._content = b"{}"
        return response

    monkeypatch.setattr(requests.sessions.Session, "request", request)
    settings = _settings(**{f"service_{service_type}_internal_url": endpoint})
    with patch("app.services.keystone.get_settings", return_value=settings):
        conn = factory(*factory_args)

    try:
        assert invoke(register(conn)) == expected_payload
    finally:
        conn.close()

    service_calls = [
        (url, kwargs) for _method, url, kwargs in calls if not url.startswith("https://identity.internal.test/")
    ]
    assert [url for url, _kwargs in service_calls] == [expected_url]
    auth_request = next(kwargs for _method, url, kwargs in calls if url.endswith("/auth/tokens"))
    auth_body = json.loads(auth_request["data"])["auth"]
    assert auth_body["identity"]["methods"] == [auth_method]
    assert all(auth_body["scope"]["project"][key] == value for key, value in project_scope.items())
    if auth_method == "token":
        assert auth_body["identity"]["token"]["id"] == "caller-token"
    assert service_calls[0][1]["headers"]["X-Auth-Token"] == "scoped-token"


@pytest.mark.parametrize(
    ("service_type", "register", "invoke", "catalog_endpoint", "expected_url", "expected_payload"),
    [
        (
            "waygate",
            keystone.get_waygate_proxy,
            lambda proxy: proxy.servers(),
            "https://waygate.catalog.test",
            "https://waygate.catalog.test/v1/servers",
            {"servers": []},
        ),
        (
            "drover",
            keystone.get_drover_proxy,
            lambda proxy: proxy.clusters(),
            "https://drover.catalog.test/v1",
            "https://drover.catalog.test/v1/clusters",
            {"clusters": []},
        ),
    ],
)
def test_installed_sdk_preserves_catalog_destination_when_no_override(
    monkeypatch, service_type, register, invoke, catalog_endpoint, expected_url, expected_payload
):
    """Empty settings leave endpoint selection to the authenticated Keystone catalog."""
    calls = []

    def request(_session, method, url, **kwargs):
        calls.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 200 if url == expected_url else 404
        response.url = url
        response._content = json.dumps(expected_payload).encode()
        return response

    monkeypatch.setattr(requests.sessions.Session, "request", request)
    settings = _settings(**{f"service_{service_type}_internal_url": ""})
    with patch("app.services.keystone.get_settings", return_value=settings):
        conn = keystone.get_openstack_connection("caller-token", "caller-project")

    try:
        auth = conn.config.get_auth()
        auth.auth_ref = access.create(
            body=_token_body(project_id="caller-project", catalog_service=(service_type, catalog_endpoint)),
            auth_token="catalog-token",
        )
        proxy = register(conn)
        assert invoke(proxy) == expected_payload
    finally:
        conn.close()

    assert [url for _method, url, _kwargs in calls] == [expected_url]
    assert calls[0][2]["headers"]["X-Auth-Token"] == "catalog-token"


def _token_body(*, project_id, catalog_service=None):
    catalog = []
    if catalog_service:
        service_type, endpoint = catalog_service
        catalog.append(
            {
                "type": service_type,
                "name": service_type,
                "endpoints": [{"interface": "internal", "region": "RegionOne", "url": endpoint}],
            }
        )
    return {
        "token": {
            "methods": ["token"],
            "issued_at": "2026-01-01T00:00:00.000000Z",
            "expires_at": "2099-01-01T00:00:00.000000Z",
            "user": {"id": "user-1", "domain": {"id": "default", "name": "Default"}},
            "project": {"id": project_id, "domain": {"id": "default", "name": "Default"}},
            "catalog": catalog,
        }
    }
