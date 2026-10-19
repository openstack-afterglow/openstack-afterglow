"""Live exact-scope role-ID graph regressions; Keystone directory is synthetic."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from keystoneauth1 import noauth, session
from keystoneclient.v3.client import Client

from app.services import keystone
from app.services.domain_scope import domain_context, has_scope_authority, resolve_domain


def assignment(scope, role="admin-role", user="user-1", **extra):
    return {"scope": scope, "role": {"id": role}, "user": {"id": user}, **extra}


def test_exact_system_all_admin_authorizes(auth_directory):
    auth_directory.assignments = [assignment({"system": {"all": True}})]
    assert keystone._is_system_admin("user-1") is True
    assert has_scope_authority("user-1", domain_id="default") is False


@pytest.mark.parametrize(
    "scope",
    [
        {"project": {"id": "admin-project"}},
        {"domain": {"id": "default"}},
        {"system": {"all": False}},
        {"system": {"all": "true"}},
        {"system": {"all": True}, "project": {"id": "admin-project"}},
        {"system": {"all": True}, "OS-INHERIT:inherited_to": "projects"},
    ],
)
def test_project_domain_and_malformed_system_roles_never_authorize(auth_directory, scope):
    auth_directory.assignments = [assignment(scope)]
    assert keystone._is_system_admin("user-1") is False


def test_inferred_domain_manager_does_not_replace_default_project_authority(auth_directory):
    auth_directory.roles.append({"id": "custom", "name": "operators", "domain_id": None})
    auth_directory.inferences = [{"prior_role": {"id": "custom"}, "implies": [{"id": "manager-role"}]}]
    auth_directory.assignments = [
        assignment({"domain": {"id": "default"}}, role="custom", links={"assignment": "/groups/g/roles/custom"})
    ]
    assert domain_context("user-1", "default")["is_domain_manager"] is False
    assert keystone._is_system_admin("user-1") is False
    auth_directory.assignments[0]["scope"] = {"project": {"id": "p"}}
    assert domain_context("user-1", "default")["is_domain_manager"] is False


@pytest.mark.parametrize(
    "scope",
    [
        {"domain": {"id": "tenant-b"}},
        {"domain": {"id": "default"}, "OS-INHERIT:inherited_to": "projects"},
    ],
)
def test_foreign_and_inherited_domain_grants_never_manage(auth_directory, scope):
    auth_directory.assignments = [assignment(scope, role="manager-role")]
    assert domain_context("user-1", "default")["is_domain_manager"] is False


def test_other_subject_and_unresolved_group_never_authorize(auth_directory):
    auth_directory.assignments = [assignment({"system": {"all": True}}, user="other")]
    assert keystone._is_system_admin("user-1") is False
    auth_directory.assignments = [
        {"scope": {"system": {"all": True}}, "role": {"id": "admin-role"}, "group": {"id": "g"}}
    ]
    assert keystone._is_system_admin("user-1") is False


def test_domain_role_named_admin_is_not_canonical_system_admin(auth_directory):
    auth_directory.roles.append({"id": "fake-admin", "name": "admin", "domain_id": "tenant-b"})
    auth_directory.assignments = [assignment({"system": {"all": True}}, role="fake-admin")]
    with pytest.raises(HTTPException) as exc:
        keystone._is_system_admin("user-1")
    assert exc.value.status_code == 503


def test_missing_domain_never_defaults_and_disabled_domain_denied(auth_directory):
    with pytest.raises(HTTPException) as exc:
        resolve_domain("")
    assert exc.value.status_code == 400
    assert resolve_domain("Default")["id"] == "default"
    auth_directory.domains["default"]["enabled"] = False
    with pytest.raises(HTTPException) as exc:
        domain_context("user-1", "default")
    assert exc.value.status_code == 403


def test_system_inventory_uses_explicit_caller_system_scope(auth_directory, monkeypatch):
    auth_directory.assignments = [assignment({"system": {"all": True}})]
    captured = {}

    class Token:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def get_access(self, session):
            return SimpleNamespace(user_id="user-1", system_scoped=True)

    monkeypatch.setattr(keystone.v3, "Token", Token)
    monkeypatch.setattr(
        "keystoneclient.v3.client.Client",
        lambda **kwargs: SimpleNamespace(
            domains=SimpleNamespace(
                list=lambda: [
                    SimpleNamespace(id="default", name="Default"),
                    SimpleNamespace(id="tenant-b", name="Tenant B"),
                ]
            ),
            projects=SimpleNamespace(
                list=lambda: [
                    SimpleNamespace(id="own", name="Own", description="", domain_id="default", enabled=True),
                    SimpleNamespace(id="foreign", name="Foreign", description="", domain_id="tenant-b", enabled=True),
                ]
            ),
        ),
    )
    projects = keystone.list_system_projects("actual-caller-token")
    assert captured["token"] == "actual-caller-token"
    assert captured["system_scope"] == "all"
    assert {p["domain_id"] for p in projects} == {"default", "tenant-b"}
    auth_directory.assignments = [assignment({"project": {"id": "own"}})]
    with pytest.raises(HTTPException) as exc:
        keystone.list_system_projects("actual-caller-token")
    assert exc.value.status_code == 403


@pytest.fixture
def native_system_directory(monkeypatch):
    """Installed SDK over HTTP, with Keystone's raw/effective system distinction.

    Keystone assignment.core.Manager.list_role_assignments sends effective
    requests through the project/domain-only expansion path, not the raw path
    that adds system grants. Never emulate that response with a keyword echo.
    See https://docs.openstack.org/keystone/2026.2/_modules/keystone/assignment/core.html
    """
    state = SimpleNamespace(
        assignments=[],
        groups=[{"id": "operators"}],
        roles=[{"id": "admin-role", "name": "admin"}, {"id": "custom", "name": "operators"}],
        inferences=[{"prior_role": {"id": "custom"}, "implies": [{"id": "admin-role"}]}],
        requests=[],
        failure=None,
        failure_status=503,
        users={"user-1": {"id": "user-1", "enabled": True}},
        members={"operators": [{"id": "user-1"}]},
    )

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            state.requests.append((url.path, query))
            status = 200
            if url.path == state.failure:
                status, payload = state.failure_status, {"error": {"message": "synthetic directory outage"}}
            elif url.path == "/v3/users/user-1/groups":
                payload = {"groups": state.groups}
            elif url.path.startswith("/v3/groups/") and url.path.endswith("/users"):
                gid = url.path.split("/")[3]
                payload = {"users": state.members.get(gid, [])}
            elif url.path.startswith("/v3/users/"):
                uid = url.path.split("/")[3]
                payload = {"user": state.users[uid]}
            elif url.path == "/v3/role_assignments":
                if "effective" in query:
                    # Matches the provider path: system rows are omitted even
                    # when the incoming request includes scope.system=all.
                    rows = [row for row in state.assignments if "system" not in row["scope"]]
                else:
                    rows = state.assignments
                for principal in ("user", "group"):
                    if principal + ".id" in query:
                        selected = query[principal + ".id"][0]
                        rows = [row for row in rows if row.get(principal, {}).get("id") == selected]
                payload = {"role_assignments": rows}
            elif url.path == "/v3/roles":
                payload = {"roles": state.roles}
            elif url.path == "/v3/role_inferences":
                payload = {"role_inferences": state.inferences}
            else:
                status, payload = 404, {"error": {"message": "unknown fixture endpoint"}}
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sdk_session = session.Session(auth=noauth.NoAuth())
    native = Client(session=sdk_session, endpoint_override=f"http://127.0.0.1:{server.server_port}/v3")
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    state.native = native
    try:
        yield state
    finally:
        sdk_session.session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("group,inferred", [(False, False), (True, False), (False, True), (True, True)])
def test_native_sdk_raw_system_grants_restore_direct_group_and_inferred_admin(native_system_directory, group, inferred):
    state = native_system_directory
    row = assignment({"system": {"all": True}}, role="custom" if inferred else "admin-role")
    if group:
        row["group"] = {"id": "operators"}
        del row["user"]
    state.assignments = [row, assignment({"project": {"id": "project-1"}})]
    effective = state.native.role_assignments.list(user="user-1", effective=True, system="all")
    assert [row.scope for row in effective] == [{"project": {"id": "project-1"}}]
    state.requests.clear()
    assert keystone._is_system_admin("user-1") is True
    queries = [query for path, query in state.requests if path == "/v3/role_assignments"]
    assert all(query["scope.system"] == ["all"] and "effective" not in query for query in queries)
    assert any(query.get("user.id") == ["user-1"] for query in queries)
    assert any(query.get("group.id") == ["operators"] for query in queries)


@pytest.mark.parametrize(
    "scope",
    [
        {"project": {"id": "project-1"}},
        {"domain": {"id": "default"}},
        {"system": {"all": False}},
        {"system": {"all": "true"}},
        {"system": {"all": True, "other": True}},
        {"system": {"all": True}, "domain": {"id": "default"}},
        {"system": {"all": True}, "OS-INHERIT:inherited_to": "projects"},
    ],
)
def test_native_sdk_non_system_or_malformed_grants_cannot_escalate(native_system_directory, scope):
    native_system_directory.assignments = [assignment(scope, role="custom")]
    assert keystone._is_system_admin("user-1") is False


def test_native_sdk_group_grant_requires_actual_membership_and_one_principal(native_system_directory):
    state = native_system_directory
    state.assignments = [
        {"scope": {"system": {"all": True}}, "role": {"id": "admin-role"}, "group": {"id": "foreign"}},
        assignment({"system": {"all": True}}, user="other"),
        assignment({"system": {"all": True}}, group={"id": "operators"}),
    ]
    assert keystone._is_system_admin("user-1") is False


@pytest.mark.parametrize("status", [403, 404, 503])
@pytest.mark.parametrize(
    "path", ["/v3/role_assignments", "/v3/users/user-1/groups", "/v3/roles", "/v3/role_inferences"]
)
def test_native_sdk_authority_directory_failures_are_503(native_system_directory, path, status):
    state = native_system_directory
    state.assignments = [assignment({"system": {"all": True}})]
    state.failure = path
    state.failure_status = status
    with pytest.raises(HTTPException) as exc:
        keystone._is_system_admin("user-1")
    assert exc.value.status_code == 503
    assert exc.value.__cause__ is not None


@pytest.mark.parametrize("group,inferred", [(False, False), (True, False), (False, True), (True, True)])
def test_native_last_admin_guard_counts_raw_user_group_and_implied_grants(native_system_directory, group, inferred):
    from app.services import identity_roles

    state = native_system_directory
    row = assignment({"system": {"all": True}}, role="custom" if inferred else "admin-role")
    if group:
        row["group"] = {"id": "operators"}
        del row["user"]
    state.assignments = [row]
    assert set(identity_roles.enabled_system_admins()) == {"user-1"}
    with pytest.raises(HTTPException) as exc:
        identity_roles.assert_system_admin_remains(users={"user-1"})
    assert exc.value.status_code == 422
    state.users["user-1"]["enabled"] = False
    assert identity_roles.enabled_system_admins() == {}


@pytest.mark.parametrize("path", ["/v3/role_assignments", "/v3/groups/operators/users", "/v3/users/user-1"])
def test_native_last_admin_guard_membership_failures_are_not_zero_admins(native_system_directory, path):
    from app.services import identity_roles

    state = native_system_directory
    state.assignments = [{"scope": {"system": {"all": True}}, "role": {"id": "custom"}, "group": {"id": "operators"}}]
    state.failure = path
    with pytest.raises(HTTPException) as exc:
        identity_roles.enabled_system_admins()
    assert exc.value.status_code == 503


@pytest.mark.parametrize("malformed", [False, "true", 1, None])
def test_native_sdk_malformed_system_all_never_grants_authority(native_system_directory, malformed):
    from app.services import identity_roles

    native_system_directory.assignments = [assignment({"system": {"all": malformed}})]
    assert keystone._is_system_admin("user-1") is False
    with pytest.raises(HTTPException) as exc:
        identity_roles.enabled_system_admins()
    assert exc.value.status_code == 503


@pytest.mark.parametrize("failure", ["unknown-role", "cycle", "domain-admin", "noncanonical-admin", "membership"])
def test_native_sdk_untrusted_role_graph_and_membership_fail_closed(native_system_directory, failure):
    state = native_system_directory
    state.assignments = [assignment({"system": {"all": True}}, role="custom")]
    if failure == "unknown-role":
        state.assignments[0]["role"]["id"] = "missing"
    elif failure == "cycle":
        state.inferences.append({"prior_role": {"id": "admin-role"}, "implies": [{"id": "custom"}]})
    elif failure == "domain-admin":
        state.roles[0]["domain_id"] = "tenant-b"
    elif failure == "noncanonical-admin":
        state.roles.append({"id": "fake-admin", "name": "ADMIN"})
    else:
        state.groups = [{"name": "unresolved"}]
    with pytest.raises(HTTPException) as exc:
        keystone._is_system_admin("user-1")
    assert exc.value.status_code == 503
