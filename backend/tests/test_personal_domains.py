"""Personal identities: SQL journals, real API requests and native SDK wire data.

Synthetic native directories never grant authority by token claim. No live cloud
is contacted; the native display test uses installed clients over loopback HTTP.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import noauth
from keystoneauth1 import session as native_session
from keystoneclient.v3.client import Client
from openstack.identity.v3.domain import Domain
from sqlalchemy import select

from app.api.deps import get_token_info, require_domain_manager
from app.api.identity import iam, onboarding
from app.database import get_session
from app.models.domain_iam import DomainEnrollment
from app.services import (
    domain_display,
    domain_iam,
    domain_projects,
    domain_scope,
    keystone,
    project_service,
)
from tests.test_domain_iam import PASSWORD, email_token, manager
from tests.test_domain_iam import directory as directory
from tests.test_domain_iam import enrollments as enrollments
from tests.test_project_membership_roles import rid


@pytest.fixture
def enrollment_app(directory, enrollments):
    app = FastAPI()
    app.include_router(iam.router, prefix="/api/v1/iam")
    app.include_router(onboarding.router, prefix="/api/v1/auth")
    app.dependency_overrides[require_domain_manager] = lambda: manager()
    app.dependency_overrides[get_token_info] = lambda: manager("foreign", "other")

    async def session_dep():
        async with enrollments() as session:
            yield session

    app.dependency_overrides[get_session] = session_dep
    return app


@pytest.mark.asyncio
async def test_email_only_invite_creates_personal_home_and_immediate_target_reader(
    directory,
    enrollments,
    enrollment_app,
):
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        issued = await client.post("/api/v1/iam/invitations", json={"email": "new@test.invalid"})
        assert issued.status_code == 201 and issued.json()["project_id"] is None
        token = email_token(directory.sent[-1])
        assert not directory.creates and not directory.personal_domains
        public = await client.get(f"/api/v1/auth/invitations/{token}")
        assert public.status_code == 200 and public.json()["project_name"] == ""
        assert public.json()["account_exists"] is False
        body = {"token": token, "name": "new", "password": PASSWORD, "personal_domain_name": "My Space"}
        accepted = await client.post("/api/v1/auth/invitations/accept", json=body)
        assert accepted.status_code == 200, accepted.text
        result = accepted.json()
        uid, home = result["user_id"], result["identity_domain_id"]
        assert home != "domain" and result["identity_domain_name"] == "My Space"
        assert directory.users[uid].domain_id == home
        assert directory.users[uid].afterglow_local_password is True
        assert project_service._direct_ids(directory.default_direct, uid) == {rid("project_reader")}
        assert not project_service._direct_ids(directory.direct, uid)
        assert domain_projects.has_manager(uid, home)
        personal_default = domain_projects.default_project(home)
        assert project_service._direct_ids(directory.personal_direct, uid) == {
            rid("manager"),
            rid("project_owner"),
            rid("project_reader"),
        }
        assert personal_default["domain_id"] == home and personal_default["enabled"]
        listed = await client.get("/api/v1/iam/users")
        foreign = next(row for row in listed.json()["items"] if row["id"] == uid)
        assert foreign["protected"] and foreign["domain_id"] == home
        assert not {"password", "application_credentials", "afterglow_enrollment_id"} & set(foreign)
        replay = await client.post("/api/v1/auth/invitations/accept", json=body)
        assert replay.status_code == 410 and len(directory.creates) == 1
    async with enrollments() as session:
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "accepted" and row.identity_domain_id == home
        assert not row.creation_uncertain
        assert not row.domain_creation_uncertain and not row.project_creation_uncertain


@pytest.mark.asyncio
async def test_existing_email_only_invite_preserves_identity_and_preexisting_reader(
    directory,
    enrollments,
    enrollment_app,
):
    original = vars(directory.users["foreign"]).copy()
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        issued = await client.post("/api/v1/iam/invitations", json={"email": "foreign@test.invalid"})
        token = email_token(directory.sent[-1])
        inspected = await client.get(f"/api/v1/auth/invitations/{token}")
        assert inspected.status_code == 200
        assert inspected.json()["account_exists"] is True
        assert inspected.json()["identity_domain_id"] == "other"
        assert not directory.personal_domains and not directory.creates
        response = await client.post("/api/v1/auth/invitations/accept-existing", json={"token": token})
        assert response.status_code == 200, response.text
        assert response.json()["identity_domain_id"] == "other"
        assert vars(directory.users["foreign"]) == original
        assert not directory.personal_domains and not directory.personal_projects and not directory.creates
    async with enrollments() as session:
        row = await session.get(DomainEnrollment, issued.json()["id"])
        assert row.status == "accepted" and row.added_grants == [] and not row.new_user


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("personal_domain_name", None), ("personal_domain_name", "   ")])
async def test_new_human_request_requires_personal_display_name(directory, enrollment_app, field, value):
    body = {"name": "new", "email": "new@test.invalid", "password": PASSWORD}
    if value is not None:
        body[field] = value
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        response = await client.post("/api/v1/iam/users", json=body)
    assert response.status_code == 422 and PASSWORD not in response.text
    assert not directory.personal_domains and not directory.creates


@pytest.mark.asyncio
async def test_signup_api_provisions_only_personal_home_without_old_domain_admission(directory, enrollment_app):
    directory.settings.auth.public_signup_enabled = True
    directory.settings.auth.signup_email_domains = ["test.invalid"]
    async with AsyncClient(transport=ASGITransport(app=enrollment_app), base_url="http://test") as client:
        issued = await client.post("/api/v1/auth/registrations", json={"email": "signup@test.invalid"})
        assert issued.status_code == 202
        token = email_token(directory.sent[-1])
        response = await client.post(
            "/api/v1/auth/registrations/accept",
            json={
                "token": token,
                "name": "signup",
                "password": PASSWORD,
                "personal_domain_name": "Shared",
            },
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["domain_id"] == result["identity_domain_id"] != "domain"
        assert not project_service._direct_ids(directory.default_direct, result["user_id"])
        assert not project_service._direct_ids(directory.direct, result["user_id"])
        assert domain_projects.has_manager(result["user_id"], result["identity_domain_id"])
        assert directory.users[result["user_id"]].afterglow_local_password is True


@pytest.mark.asyncio
async def test_system_managed_humans_get_distinct_homes_with_same_display_label(directory, enrollments):
    attrs = {
        "name": "same-name",
        "email": "first@test.invalid",
        "password": PASSWORD,
        "personal_domain_name": "Shared",
        "enabled": True,
    }
    async with enrollments() as session:
        with pytest.raises(HTTPException) as forged:
            await domain_iam.create_managed_user(
                attrs, "domain", {**manager("member"), "is_system_admin": True}, session
            )
        assert forged.value.status_code == 403 and not directory.personal_domains
        first = await domain_iam.create_managed_user(attrs, "domain", manager("system-admin"), session)
        second = await domain_iam.create_managed_user(
            {**attrs, "email": "second@test.invalid"},
            "domain",
            manager("system-admin"),
            session,
        )
        assert first["identity_domain_id"] != second["identity_domain_id"]
        assert first["identity_domain_name"] == second["identity_domain_name"] == "Shared"
        assert len({d.name for d in directory.personal_domains.values()}) == 2
        for account in (first, second):
            uid, home = account["id"], account["identity_domain_id"]
            assert directory.users[uid].domain_id == home and domain_projects.has_manager(uid, home)
            assert rid("project_reader") in project_service._direct_ids(directory.default_direct, uid)
        assert directory.users["operator"].domain_id == "domain"


@pytest.mark.asyncio
@pytest.mark.parametrize("resource", ["domains", "projects"])
async def test_lost_personal_create_reply_recovers_exact_marked_resources(directory, enrollments, resource):
    async with enrollments() as session:
        issued = await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        native = getattr(directory.ks, resource)
        create = native.create

        def lost_reply(**attrs):
            create(**attrs)
            raise ConnectionError("Synthetic native create committed, reply lost")

        native.create = lost_reply
        with pytest.raises(HTTPException) as failed:
            await domain_iam.redeem(
                token, "invitation", session, name="new", password=PASSWORD, personal_domain_name="Same"
            )
        assert failed.value.status_code == 503
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "failed"
        assert not directory.personal_domains and not directory.personal_projects
        assert not [u for u in directory.users.values() if getattr(u, "afterglow_enrollment_id", None)]
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(
                token, "invitation", session, name="new", password=PASSWORD, personal_domain_name="Same"
            )
        assert replay.value.status_code == 410


@pytest.mark.asyncio
async def test_unavailable_project_inventory_preserves_durable_admin_recovery(directory, enrollments, monkeypatch):
    monkeypatch.setattr(
        project_service,
        "inspect_project_empty",
        AsyncMock(
            return_value={
                "can_delete": False,
                "resources": [{"status": "unavailable", "count": None}],
            }
        ),
    )
    native_update = directory.ks.users.update

    def lost_activation(uid, **attrs):
        updated = native_update(uid, **attrs)
        if attrs.get("enabled") is True:
            raise ConnectionError("Activation committed but reply lost")
        return updated

    directory.ks.users.update = lost_activation
    async with enrollments() as session:
        with pytest.raises(HTTPException) as failed:
            await domain_iam.create_managed_user(
                {
                    "name": "human",
                    "email": "human@test.invalid",
                    "password": PASSWORD,
                    "personal_domain_name": "Home",
                    "enabled": True,
                },
                "domain",
                manager("system-admin"),
                session,
            )
        assert failed.value.status_code == 503
        row = (await session.execute(select(DomainEnrollment))).scalar_one()
        assert row.status == "recovery_required" and not directory.users[row.user_id].enabled
        assert (
            row.identity_domain_id in directory.personal_domains
            and row.personal_project_id in directory.personal_projects
        )
        listed = await domain_iam.list_invitations(
            manager("system-admin"), session, operations=True, system_domain_id="domain"
        )
        assert listed["items"][0]["id"] == row.id and listed["items"][0]["recovery_required"]
        with pytest.raises(HTTPException) as denied:
            await domain_iam.revoke(row.id, manager("member"), session, operation=True, system_domain_id="domain")
        assert denied.value.status_code == 403
        monkeypatch.setattr(project_service, "inspect_project_empty", AsyncMock(return_value={"can_delete": True}))
        await domain_iam.revoke(row.id, manager("system-admin"), session, operation=True, system_domain_id="domain")
        assert row.status == "revoked" and not directory.personal_domains and not directory.personal_projects


@pytest.mark.asyncio
async def test_unknown_domain_create_stays_durable_and_never_replays(directory, enrollments):
    async with enrollments() as session:
        issued = await domain_iam.invite({"email": "new@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        calls = []

        def unknown(**attrs):
            calls.append(attrs)
            raise ConnectionError("No authoritative creation result")

        directory.ks.domains.create = unknown
        with pytest.raises(HTTPException):
            await domain_iam.redeem(
                token, "invitation", session, name="new", password=PASSWORD, personal_domain_name="Same"
            )
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.status == "recovery_required" and row.domain_creation_uncertain
        assert row.identity_native_name.startswith("afterglow-") and row.identity_domain_id is None
        with pytest.raises(HTTPException) as recovery:
            await domain_iam.revoke(row.id, manager(), session)
        assert recovery.value.status_code == 503
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(
                token, "invitation", session, name="new", password=PASSWORD, personal_domain_name="Same"
            )
        assert replay.value.status_code == 410 and len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["delayed_commit", "readback_failure", "process_interrupted"])
async def test_unsettled_grant_never_compensates_from_absence_or_replays(directory, enrollments, outcome):
    class ProcessInterrupted(BaseException):
        pass

    native_grant = directory.ks.roles.grant
    native_assignments = directory.ks.role_assignments.list
    dispatched = []
    pending = []
    readback_failed = False

    def grant(role_id, **attrs):
        dispatched.append((role_id, attrs))
        if outcome == "process_interrupted":
            raise ProcessInterrupted()
        if outcome == "delayed_commit":
            pending.append((role_id, attrs))
            raise ConnectionError("Native request remains in progress after lost response")
        return native_grant(role_id, **attrs)

    def assignments(**attrs):
        nonlocal readback_failed
        if (
            outcome == "readback_failure"
            and dispatched
            and not readback_failed
            and attrs.get("project") == "default-project"
        ):
            readback_failed = True
            raise ConnectionError("Native grant reply succeeded but readback is unavailable")
        return native_assignments(**attrs)

    directory.ks.roles.grant = grant
    directory.ks.role_assignments.list = assignments
    original = vars(directory.users["member"]).copy()
    async with enrollments() as session:
        issued = await domain_iam.invite({"email": "member@test.invalid"}, manager(), session)
        token = email_token(directory.sent[-1])
        error = ProcessInterrupted if outcome == "process_interrupted" else HTTPException
        with pytest.raises(error):
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        row = await session.get(DomainEnrollment, issued["id"])
        assert row.added_grants[-1]["phase"] == ("applying" if outcome == "process_interrupted" else "unknown")
        if outcome != "process_interrupted":
            assert row.status == "recovery_required"
        if outcome != "readback_failure":
            assert not project_service._direct_ids(directory.default_direct, "member")
        with pytest.raises(HTTPException) as no_proof:
            await domain_iam.revoke(row.id, manager(), session)
        assert no_proof.value.status_code == 503 and row.status == "recovery_required"
        assert not [call for call in directory.calls if call[0] == "revoke"]
        assert not domain_iam.enrollment_dto(row)["native_writes_settled"]
        with pytest.raises(HTTPException) as replay:
            await domain_iam.redeem(token, "invitation", session, token_info=manager("member"))
        assert replay.value.status_code == 410 and len(dispatched) == 1
        for invalid_ack in (False, "true", 1, None):
            with pytest.raises(HTTPException) as rejected:
                await domain_iam.settle_enrollment_native_writes(
                    row.id,
                    manager("system-admin"),
                    session,
                    domain_id="domain",
                    native_writes_settled=invalid_ack,
                )
            assert rejected.value.status_code == 422
        with pytest.raises(HTTPException) as forbidden:
            await domain_iam.settle_enrollment_native_writes(
                row.id,
                manager("member"),
                session,
                domain_id="domain",
                native_writes_settled=True,
            )
        assert forbidden.value.status_code == 403
        # The provider completes outside the request. A role that was absent at
        # failure time can appear later, without any Afterglow replay.
        for role_id, attrs in pending:
            native_grant(role_id, **attrs)
        settled = await domain_iam.settle_enrollment_native_writes(
            row.id,
            manager("system-admin"),
            session,
            domain_id="domain",
            native_writes_settled=True,
        )
        assert settled["native_writes_settled"] and row.added_grants[-1]["phase"] == "settled"
        assert row.added_grants[-1]["settled_by"] == "system-admin"
        await domain_iam.revoke(row.id, manager(), session)
        assert row.status == "revoked" and not project_service._direct_ids(directory.default_direct, "member")
        assert vars(directory.users["member"]) == original and len(dispatched) == 1


@pytest.mark.asyncio
async def test_joined_directory_drops_revoked_foreign_membership_and_keeps_disabled_home(directory):
    directory.users["member"].enabled = False
    directory.default_direct.append(
        {
            "user": {"id": "foreign"},
            "role": {"id": rid("project_reader")},
            "scope": {"project": {"id": "default-project"}},
        }
    )
    assert {u.id for u in await domain_iam.directory_users("domain")} >= {"foreign", "member"}
    directory.default_direct.clear()
    assert "foreign" not in {u.id for u in await domain_iam.directory_users("domain")}
    assert directory.users["foreign"].domain_id == "other"


def test_real_native_sdk_duplicate_display_names_and_lossy_sdk_resolution(monkeypatch):
    domains, requests = {}, []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append((self.command, self.path, body))
            attrs = body["domain"]
            if any(d["name"] == attrs["name"] for d in domains.values()):
                return self.respond(409, {"error": {"message": "Native domain name must be unique"}})
            did = f"domain-{len(domains)}"
            domains[did] = {"id": did, **attrs}
            self.respond(201, {"domain": domains[did]})

        def do_GET(self):
            path = urlsplit(self.path).path
            requests.append((self.command, path, None))
            if path == "/v3/domains":
                return self.respond(200, {"domains": list(domains.values())})
            did = path.removeprefix("/v3/domains/")
            if did not in domains:
                return self.respond(404, {"error": {"message": "Domain not found"}})
            self.respond(200, {"domain": domains[did]})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    transport = native_session.Session(auth=noauth.NoAuth())
    native = Client(session=transport, endpoint_override=f"http://127.0.0.1:{server.server_port}/v3")
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    try:
        first = native.domains.create(name=domain_display.native_name(), enabled=True, afterglow_display_name="Shared")
        second = native.domains.create(name=domain_display.native_name(), enabled=True, afterglow_display_name="Shared")
        assert first.id != second.id and first.name != second.name
        assert domain_scope.resolve_domain(first.id)["name"] == "Shared"
        assert domain_scope.resolve_domain(second.id)["name"] == "Shared"
        with pytest.raises(HTTPException) as ambiguous:
            domain_scope.resolve_domain("Shared")
        assert ambiguous.value.status_code == 409 and "domain ID" in ambiguous.value.detail
        lossy = Domain(**domains[first.id])
        assert domain_display.display_name(lossy) == "Shared"
        domains[second.id].pop("afterglow_display_name")
        assert domain_scope.resolve_domain(second.name)["id"] == second.id
        assert len([r for r in requests if r[0] == "POST"]) == 2
    finally:
        transport.session.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
