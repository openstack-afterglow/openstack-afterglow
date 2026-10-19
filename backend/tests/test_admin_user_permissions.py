"""Admin display snapshots use real scope/role IDs, never authorization inputs.

Common HTTP/auth fixtures are reused. Keystone is mocked at its SDK boundary;
RoleAssignment resources exercise the installed SDK's effective response shape.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from keystoneauth1 import noauth, session
from openstack.connection import Connection
from openstack.exceptions import HttpException, ResourceNotFound
from openstack.identity.v3.role_assignment import RoleAssignment
from requests import Response

URL = "/api/v1/admin/users/user-1/permissions?domain_id=child"


def graph_response(inferences=None, status=200):
    response = Response()
    response.status_code = status
    response.url = "https://keystone.invalid/v3/role_inferences"
    response._content = json.dumps({"role_inferences": inferences or []}).encode()
    return response


def grant(role="parent", scope=None, user="user-1", **extras):
    return RoleAssignment(
        user={"id": user},
        role={"id": role},
        scope=scope if scope is not None else {"project": {"id": "child", "name": "Child project"}},
        **extras,
    )


@pytest.fixture
def permissions_provider(mock_conn):
    mock_conn.identity.get_domain.return_value = SimpleNamespace(id="child", name="Selected domain")
    mock_conn.identity.get_user.return_value = SimpleNamespace(id="user-1", name="Subject", domain_id="child")
    mock_conn.identity.projects.return_value = [
        SimpleNamespace(id=pid, name=pid, domain_id="child") for pid in ("child", "project-2")
    ]
    mock_conn.identity.roles.return_value = [
        SimpleNamespace(id=rid, name=name, domain_id=None, description="")
        for rid, name in (
            ("parent", "Project grade"),
            ("left", "Same name"),
            ("right", "Same name"),
            ("leaf", "Read leaf"),
        )
    ]
    mock_conn.identity.get.return_value = graph_response(
        [
            {"prior_role": {"id": "parent"}, "implies": [{"id": "left"}, {"id": "right"}]},
            {"prior_role": {"id": "left"}, "implies": [{"id": "leaf"}]},
            {"prior_role": {"id": "right"}, "implies": [{"id": "leaf"}]},
        ]
    )
    mock_conn.identity.role_assignments.return_value = []
    return mock_conn.identity


@pytest.fixture
def inherited_keystone():
    """Real SDK requests against Keystone's effective inherited scope wire shape."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            path = urlsplit(self.path).path.rstrip("/")
            payloads = {
                "/v3": {
                    "version": {"id": "v3.14", "status": "stable", "links": [{"rel": "self", "href": endpoint + "/"}]}
                },
                "/v3/domains/child": {"domain": {"id": "child", "name": "Selected domain", "enabled": True}},
                "/v3/users/user-1": {"user": {"id": "user-1", "name": "Subject", "domain_id": "child"}},
                "/v3/projects": {"projects": [{"id": "child", "name": "Child project", "domain_id": "child"}]},
                "/v3/roles": {
                    "roles": [{"id": "parent", "name": "Project grade"}, {"id": "leaf", "name": "Read leaf"}]
                },
                "/v3/role_inferences": {
                    "role_inferences": [{"prior_role": {"id": "parent"}, "implies": [{"id": "leaf"}]}]
                },
                "/v3/role_assignments": {
                    "role_assignments": [
                        {
                            "user": {"id": "user-1"},
                            "role": {"id": "parent", "name": "Project grade"},
                            "scope": {
                                "OS-INHERIT:inherited_to": "projects",
                                "project": {"id": "child", "name": "Child project"},
                            },
                            "links": {
                                "assignment": endpoint
                                + "/OS-INHERIT/domains/root/groups/team/roles/parent/inherited_to_projects"
                            },
                        }
                    ]
                },
            }
            body = json.dumps(payloads.get(path, {"error": "unknown fixture endpoint"})).encode()
            self.send_response(200 if path in payloads else 404)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    endpoint = f"http://127.0.0.1:{server.server_port}/v3"
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    conn = Connection(
        session=session.Session(auth=noauth.NoAuth()), identity_endpoint_override=endpoint, identity_api_version="3"
    )
    try:
        yield conn
    finally:
        conn.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.asyncio
async def test_user_permissions_keystone_inherited_scope_over_real_sdk_http(
    admin_client, mock_conn, inherited_keystone
):
    mock_conn.identity = inherited_keystone.identity
    response = await admin_client.get(URL)
    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    (item,) = payload["items"]
    roles = item.pop("roles")
    assert item == {"scope_type": "project", "scope_id": "child", "scope_name": "Child project"}
    assert {(role["id"], role["name"]) for role in roles} == {("parent", "Project grade"), ("leaf", "Read leaf")}


@pytest.mark.asyncio
async def test_user_permissions_requires_admin(non_admin_client, permissions_provider):
    response = await non_admin_client.get(URL)
    assert response.status_code == 403
    permissions_provider.get_user.assert_not_called()
    permissions_provider.role_assignments.assert_not_called()


@pytest.mark.asyncio
async def test_user_permissions_effective_groups_inheritance_dag_and_duplicate_grants(
    admin_client, permissions_provider
):
    provider = permissions_provider

    def effective_assignments(**query):
        # Native effective mode substitutes group members and descendant scopes.
        # Source links must not be mistaken for the assignment's actual scope.
        assert query == {"user_id": "user-1", "effective": True, "include_names": True}
        return iter(
            [
                grant(links={"assignment": "https://keystone.invalid/v3/projects/ancestor/groups/team/roles/parent"}),
                grant(
                    links={
                        "assignment": "https://keystone.invalid/v3/OS-INHERIT/domains/root/users/user-1/roles/parent/inherited_to_projects"
                    }
                ),
                grant(),
                grant(role="leaf"),
                grant(role="left", scope={"domain": {"id": "child", "name": "Domain with same ID"}}),
                grant(role="right", scope={"system": {"all": True}}),
            ]
        )

    provider.role_assignments.side_effect = effective_assignments
    response = await admin_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {
                "scope_type": "domain",
                "scope_id": "child",
                "scope_name": "Domain with same ID",
                "roles": [{"id": "leaf", "name": "Read leaf"}, {"id": "left", "name": "Same name"}],
            },
            {
                "scope_type": "project",
                "scope_id": "child",
                "scope_name": "Child project",
                "roles": [
                    {"id": "leaf", "name": "Read leaf"},
                    {"id": "left", "name": "Same name"},
                    {"id": "parent", "name": "Project grade"},
                    {"id": "right", "name": "Same name"},
                ],
            },
            {
                "scope_type": "system",
                "scope_id": "all",
                "scope_name": "all",
                "roles": [{"id": "leaf", "name": "Read leaf"}, {"id": "right", "name": "Same name"}],
            },
        ],
        "count": 3,
    }
    assert provider.get_user.call_count == 2
    provider.get_user.assert_called_with("user-1")
    provider.get_project.assert_not_called()
    provider.get_domain.assert_called_once_with("child")
    provider.users.assert_not_called()
    provider.projects.assert_called_once_with(domain_id="child")
    provider.groups.assert_not_called()
    provider.group_users.assert_not_called()
    provider.create_role.assert_not_called()


@pytest.mark.asyncio
async def test_user_permissions_resolves_each_unique_scope_once(admin_client, permissions_provider):
    p = permissions_provider
    project = {"project": {"id": "project-2"}}
    domain = {"domain": {"id": "child"}}
    p.role_assignments.return_value = [
        grant(scope=project),
        grant(role="leaf", scope=project),
        grant(scope=domain),
        grant(scope=domain),
    ]
    p.get_project.return_value = SimpleNamespace(id="project-2", name="Resolved project", domain_id="child")
    p.get_domain.side_effect = [
        SimpleNamespace(id="child", name="Selected domain"),
        SimpleNamespace(id="child", name="Resolved domain"),
    ]
    response = await admin_client.get(URL)
    assert response.status_code == 200
    assert response.json()["count"] == 2
    assert [item["scope_name"] for item in response.json()["items"]] == ["Resolved domain", "Resolved project"]
    p.get_project.assert_called_once_with("project-2")
    assert p.get_domain.call_count == 2
    p.get_domain.assert_called_with("child")
    p.users.assert_not_called()
    p.projects.assert_called_once_with(domain_id="child")
    p.domains.assert_not_called()


@pytest.mark.asyncio
async def test_user_permissions_verified_empty_snapshot(admin_client, permissions_provider):
    response = await admin_client.get(URL)
    assert response.status_code == 200
    assert response.json() == {"items": [], "count": 0}
    assert permissions_provider.get_user.call_count == 2
    permissions_provider.get_user.assert_called_with("user-1")
    permissions_provider.get.assert_called_once_with("/role_inferences")
    permissions_provider.role_assignments.assert_called_once_with(user_id="user-1", effective=True, include_names=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["get_user", "roles", "get", "role_assignments", "get_project", "get_domain"])
async def test_user_permissions_provider_outage_never_returns_empty(admin_client, permissions_provider, source):
    p = permissions_provider
    if source in ("get_project", "get_domain"):
        kind = "project" if source == "get_project" else "domain"
        p.role_assignments.return_value = [grant(scope={kind: {"id": "scope-2"}})]
    getattr(p, source).side_effect = RuntimeError("provider outage")
    response = await admin_client.get(URL)
    assert response.status_code == 503
    assert "detail" in response.json()
    assert "items" not in response.json()


@pytest.mark.asyncio
async def test_user_permissions_partial_iterator_failure_is_not_partial_success(admin_client, permissions_provider):
    def assignments(**query):
        yield grant()
        raise RuntimeError("next page failed")

    permissions_provider.role_assignments.side_effect = assignments
    response = await admin_client.get(URL)
    assert response.status_code == 503
    assert "items" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(400, 422), (403, 403), (404, 404), (409, 409), (500, 503)])
async def test_user_permissions_preserves_provider_error_handling(admin_client, permissions_provider, status, expected):
    permissions_provider.role_assignments.side_effect = HttpException("rejected", http_status=status)
    response = await admin_client.get(URL)
    assert response.status_code == expected
    assert "detail" in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("subject,expected", [(None, 404), ({"id": "other-user"}, 503), ({}, 503), ({"id": 1}, 503)])
async def test_user_permissions_verifies_requested_subject(admin_client, permissions_provider, subject, expected):
    permissions_provider.get_user.return_value = subject
    response = await admin_client.get(URL)
    assert response.status_code == expected
    permissions_provider.role_assignments.assert_not_called()


@pytest.mark.asyncio
async def test_user_permissions_missing_user_is_404(admin_client, permissions_provider):
    permissions_provider.get_user.side_effect = ResourceNotFound("missing", http_status=404)
    response = await admin_client.get(URL)
    assert response.status_code == 404
    permissions_provider.role_assignments.assert_not_called()


@pytest.mark.asyncio
async def test_user_permissions_invalid_requested_id(admin_client, permissions_provider):
    permissions_provider.get_user.return_value = SimpleNamespace(id=" ", domain_id="child")
    response = await admin_client.get("/api/v1/admin/users/%20/permissions?domain_id=child")
    assert response.status_code == 422
    permissions_provider.get_user.assert_called_once_with(" ")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "assignment",
    [
        grant(user="other-user"),
        {"role": {"id": "parent"}, "group": {"id": "team"}, "scope": {"project": {"id": "child"}}},
        grant(group={"id": "team"}),
        {"user": {"id": "user-1"}, "role": {"id": "parent"}},
        grant(role="missing"),
        {"user": {"id": "user-1"}, "role": {"id": "parent", "name": "Wrong name"}, "scope": {"system": {"all": True}}},
        grant(scope={}),
        grant(scope={"project": {"id": "child"}, "domain": {"id": "root"}}),
        grant(scope={"project": {"id": " "}}),
        grant(scope={"project": {"id": 1}}),
        grant(scope={"project": {"id": "child", "name": None}}),
        grant(scope={"project": {"id": "child", "name": " "}}),
        grant(scope={"project": "child"}),
        grant(scope={"unknown": {"id": "child"}}),
        grant(scope={"system": {"all": False}}),
        grant(scope={"system": {"all": 1}}),
        grant(scope={"project": {"id": "child", "name": "Child project"}, "OS-INHERIT:inherited_to": "domains"}),
        grant(scope={"project": {"id": "child", "name": "Child project"}, "OS-INHERIT:inherited_to": None}),
        grant(scope={"project": {"id": "child", "name": "Child project"}, "OS-INHERIT:inherited_to": ["projects"]}),
        grant(scope={"domain": {"id": "root", "name": "Root"}, "OS-INHERIT:inherited_to": "projects"}),
        grant(scope={"system": {"all": True}, "OS-INHERIT:inherited_to": "projects"}),
        grant(scope={"project": {"id": "child", "name": "Child project"}, "unexpected": True}),
    ],
)
async def test_user_permissions_rejects_mixed_subjects_and_invalid_metadata(
    admin_client, permissions_provider, assignment
):
    permissions_provider.role_assignments.return_value = [grant(), assignment]
    response = await admin_client.get(URL)
    assert response.status_code == 503
    assert "items" not in response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["project", "domain"])
@pytest.mark.parametrize(
    "resolved", [None, {"id": "different", "name": "Wrong scope"}, {"id": "child"}, {"id": "child", "name": 1}]
)
async def test_user_permissions_validates_resolved_scope_identity_and_name(
    admin_client, permissions_provider, kind, resolved
):
    permissions_provider.role_assignments.return_value = [grant(scope={kind: {"id": "child"}})]
    if kind == "domain":
        permissions_provider.get_domain.side_effect = [SimpleNamespace(id="child", name="Selected domain"), resolved]
    else:
        permissions_provider.get_project.return_value = resolved
    response = await admin_client.get(URL)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_user_permissions_rejects_conflicting_scope_names(admin_client, permissions_provider):
    permissions_provider.role_assignments.return_value = [
        grant(),
        grant(scope={"project": {"id": "child", "name": "Different project"}}),
    ]
    response = await admin_client.get(URL)
    assert response.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["missing_api", "unknown_edge", "cycle", "invalid_role"])
async def test_user_permissions_reuses_catalog_validation_even_when_empty(admin_client, permissions_provider, failure):
    p = permissions_provider
    if failure == "missing_api":
        p.get.return_value = graph_response(status=404)
    elif failure == "unknown_edge":
        p.get.return_value = graph_response([{"prior_role": {"id": "unknown"}, "implies": []}])
    elif failure == "cycle":
        p.get.return_value = graph_response([{"prior_role": {"id": "parent"}, "implies": [{"id": "parent"}]}])
    else:
        p.roles.return_value = [{"id": "parent", "name": None}]
    response = await admin_client.get(URL)
    assert response.status_code == 503
    assert "items" not in response.json()
