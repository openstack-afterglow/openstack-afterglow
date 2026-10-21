import json

import pytest
from _pytest._io.saferepr import saferepr
from httpx import AsyncClient, MockTransport, Response

from tests.integration import conftest as integration
from tests.integration.conftest import (
    IntegrationAuthSession,
    RedactedCredentials,
    RedactedMapping,
    RedactedSecret,
    password_login_payload,
)


def test_integration_auth_session_repr_never_exposes_credentials_or_tokens():
    session = IntegrationAuthSession(
        credentials={"username": "test-user", "password": "secret-password"},
        label="integration user",
        token_data={"token": "access-token", "refresh_token": "refresh-token"},
    )

    rendered = repr(session)

    assert rendered == "IntegrationAuthSession(label='integration user', authenticated=True)"
    assert "secret-password" not in rendered
    assert "access-token" not in rendered
    assert "refresh-token" not in rendered


def test_integration_credentials_repr_never_exposes_mapping_values():
    credentials = RedactedCredentials({"username": "test-user", "password": "secret-password"})
    bad_credentials = RedactedCredentials({**credentials, "password": "wrong-password"})

    for rendered in (repr(credentials), repr(bad_credentials)):
        assert rendered.startswith("RedactedCredentials(keys=")
        assert "test-user" not in rendered
        assert "secret-password" not in rendered
        assert "wrong-password" not in rendered


def test_pytest_safe_repr_redacts_auth_response_and_token_values():
    auth_data = RedactedMapping({"token": "access-token", "refresh_token": "refresh-token"})
    token = RedactedSecret("access-token")

    for rendered in (saferepr(auth_data), saferepr(token)):
        assert "access-token" not in rendered
        assert "refresh-token" not in rendered


def test_password_payload_preserves_native_credentials_and_redacts_secrets():
    native = RedactedCredentials(
        username="unique-user", password="native-secret", domain_name="Organization", project_name="Work"
    )
    payload = password_login_payload(native)
    assert payload == {"username": "unique-user", "password": "native-secret"}
    assert native["domain_name"] == "Organization" and native["project_name"] == "Work"
    assert "native-secret" not in saferepr(payload)
    assert "unique-user" not in saferepr(payload)


@pytest.mark.asyncio
async def test_integration_login_without_workspace_target_keeps_automatic_home(monkeypatch):
    requests = []
    home = {
        "token": "home-token",
        "refresh_token": "home-refresh",
        "user_id": "native-user",
        "domain_id": "personal-home",
        "identity_domain_id": "accounts",
        "identity_domain_name": "Accounts",
        "project_id": "home-project",
    }

    def handle(request):
        requests.append(request.url.path)
        assert request.method == "POST" and request.url.path == "/api/v1/auth/login"
        assert json.loads(request.content) == {"username": "unique-user", "password": "native-secret"}
        return Response(200, json=home)

    monkeypatch.setattr(
        integration,
        "AsyncClient",
        lambda **_: AsyncClient(transport=MockTransport(handle), base_url="http://test"),
    )
    session = IntegrationAuthSession({"username": "unique-user", "password": "native-secret"}, "home")
    assert await session.get_token_data() == home
    assert requests == ["/api/v1/auth/login"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        None,
        "domains",
        "projects",
        "selection",
        "ambiguous_domain",
        "ambiguous_project",
        "missing_domain",
        "missing_project",
        "subject",
        "home",
        "target",
        "native_denied",
        "native_subject",
        "native_home",
        "native_target",
    ],
)
async def test_integration_selects_configured_workspace_after_home_login_or_fails(monkeypatch, failure):
    native = RedactedCredentials(
        username="unique-user", password="native-secret", domain_name="Organization", project_name="Work"
    )
    home = {
        "token": "home-token",
        "refresh_token": "home-refresh",
        "user_id": "native-user",
        "domain_id": "personal-home",
        "identity_domain_id": "accounts",
        "identity_domain_name": "Accounts",
        "project_id": "home-project",
    }
    selected = {
        **home,
        "token": "workspace-token",
        "refresh_token": "workspace-refresh",
        "domain_id": "organization",
        "project_id": "work-project",
    }
    native_scoped = {**selected, "token": "native-project-token", "refresh_token": "native-project-refresh"}
    if failure == "native_subject":
        native_scoped["user_id"] = "substituted-user"
    elif failure == "native_home":
        native_scoped["identity_domain_id"] = "substituted-home"
    elif failure == "native_target":
        native_scoped["project_id"] = "substituted-project"
    if failure == "subject":
        selected["user_id"] = "substituted-user"
    elif failure == "home":
        selected["identity_domain_id"] = "substituted-home"
    elif failure == "target":
        selected["project_id"] = "substituted-project"
    requests = []

    def handle(request):
        path = request.url.path
        requests.append(path)
        if path == "/api/v1/auth/login":
            assert request.method == "POST"
            assert json.loads(request.content) == {"username": "unique-user", "password": "native-secret"}
            return Response(200, json=home)
        if path == "/api/v1/auth/token/project":
            assert request.method == "POST"
            assert request.headers["Authorization"] == "Bearer workspace-token"
            assert json.loads(request.content) == {"project_id": "work-project"}
            if failure == "native_denied":
                return Response(403, json={"detail": "Native project membership required"})
            return Response(200, json=native_scoped)
        assert request.headers["Authorization"] == "Bearer home-token"
        if path == "/api/v1/auth/domains":
            assert request.method == "GET"
            if failure == "domains":
                return Response(503, json={"detail": "Directory unavailable"})
            domain = {"id": "organization", "name": "Organization"}
            rows = [domain]
            if failure == "missing_domain":
                rows = []
            elif failure == "ambiguous_domain":
                rows.append(domain)
            return Response(200, json=rows)
        if path == "/api/v1/auth/workspaces":
            assert request.method == "GET" and request.url.params["domain_id"] == "organization"
            if failure == "projects":
                return Response(503, json={"detail": "Directory unavailable"})
            project = {"id": "work-project", "name": "Work"}
            rows = [project]
            if failure == "missing_project":
                rows = []
            elif failure == "ambiguous_project":
                rows.append(project)
            return Response(
                200,
                json={"domain": {"id": "organization", "name": "Organization"}, "projects": rows},
            )
        assert request.method == "POST" and path == "/api/v1/auth/token/workspace"
        assert json.loads(request.content) == {"domain_id": "organization", "project_id": "work-project"}
        if failure == "selection":
            return Response(403, json={"detail": "Access revoked"})
        return Response(200, json=selected)

    monkeypatch.setattr(
        integration,
        "AsyncClient",
        lambda **_: AsyncClient(transport=MockTransport(handle), base_url="http://test"),
    )
    session = IntegrationAuthSession(native, "workspace")
    if failure:
        with pytest.raises(AssertionError):
            await session.get_token_data()
        assert session.token_data is None
    else:
        assert await session.get_token_data() == native_scoped
        assert requests == [
            "/api/v1/auth/login",
            "/api/v1/auth/domains",
            "/api/v1/auth/workspaces",
            "/api/v1/auth/token/workspace",
            "/api/v1/auth/token/project",
        ]
    assert native["domain_name"] == "Organization" and native["project_name"] == "Work"
