"""Exact-user deletion through the real router/guards, disposable SQL and Redis.

Native SDK/Keystone are in-memory only. Account deletion never cascades into
project/resource cleanup; native Personal ownership and provisioning block it.
"""

import asyncio
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.deps import get_admin_os_conn, get_os_conn, get_token_info
from app.api.identity import admin_identity
from app.database import Base
from app.models.account_spaces import AccountIdentityTransfer, PersonalProjectIntent
from app.models.domain_iam import DomainEnrollment
from app.models.project_ownership import ProjectOwnershipTransfer
from app.services import (
    account_spaces,
    domain_auth,
    domain_iam,
    domain_scope,
    identity_roles,
    keystone,
    project_ownership_journal,
    session_store,
)
from tests.test_domain_projects import Directory, grant, row


class NativeError(Exception):
    def __init__(self, status):
        super().__init__("provider-secret-never-public")
        self.status_code = status


@pytest_asyncio.fixture
async def deletion_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                tables=[
                    ProjectOwnershipTransfer.__table__,
                    AccountIdentityTransfer.__table__,
                    PersonalProjectIntent.__table__,
                    DomainEnrollment.__table__,
                ],
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(project_ownership_journal, "get_session_factory", lambda: factory)
    monkeypatch.setattr(domain_auth, "_factory", lambda: factory)
    monkeypatch.setattr(account_spaces, "_factory", lambda: factory)
    try:
        yield factory
    finally:
        await engine.dispose()


@pytest.fixture
def deletion(deletion_store, monkeypatch):
    native = Directory()
    native.user_rows["target"] = row(
        id="target", name="gitlab-unknown", enabled=True, domain_id="home", federated=[{"idp_id": "gitlab"}]
    )
    native.user_rows["executor"] = row(id="executor", name="executor", enabled=True, domain_id="home")
    native.raw.append(row(user={"id": "operator"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    conn = MagicMock()
    conn.endpoint_for.return_value = "https://keystone.invalid/v3"
    conn.session.auth.get_access.return_value = SimpleNamespace(user_id="executor")
    conn.identity.get_domain.side_effect = native.domain_rows.get
    # Real openstacksdk User objects omit undeclared Keystone extras.
    conn.identity.get_user.side_effect = lambda user_id: (
        None
        if (user := native.user_rows.get(user_id)) is None
        else row(**{k: v for k, v in vars(user).items() if not k.startswith("afterglow_")})
    )
    conn.identity.roles.side_effect = lambda: iter(native.role_rows)
    conn.identity.get.return_value.json.side_effect = lambda: {"role_inferences": native.edges}
    native.deleted = []

    def delete(user_id, *, ignore_missing):
        assert ignore_missing is False
        if user_id not in native.user_rows:
            raise NativeError(404)
        native.deleted.append(user_id)
        del native.user_rows[user_id]
        native.raw = [r for r in native.raw if getattr(r, "user", {}).get("id") != user_id]
        for members in native.members.values():
            members.discard(user_id)

    conn.identity.delete_user.side_effect = delete
    info = {
        "user_id": "operator",
        "username": "operator",
        "token": "operator-native-token",
        "project_id": "personal-project",
        "connection_project_id": "personal-project",
        "domain_id": "tenant-a",
        "identity_domain_id": "home",
        "is_system_admin": True,
    }
    app = FastAPI()
    app.include_router(admin_identity.router, prefix="/api/v1/admin")
    caller_connection = MagicMock(side_effect=AssertionError("Personal-member transport must not be used"))
    app.dependency_overrides[get_os_conn] = caller_connection
    app.dependency_overrides[get_admin_os_conn] = lambda: conn
    app.dependency_overrides[get_token_info] = lambda: info
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: native)
    monkeypatch.setattr(keystone, "_resolve_admin_role_id", lambda: "admin")
    current_admin = MagicMock(return_value=True)
    monkeypatch.setattr(keystone, "_is_system_admin", current_admin)
    monkeypatch.setattr(domain_scope, "domain_context", lambda *args: {"is_system_admin": True})
    monkeypatch.setattr(
        keystone,
        "validate_token",
        lambda *args, **kwargs: {
            "user_id": "operator",
            "domain_id": "home",
            "identity_domain_id": "home",
            "project_id": "personal-project",
            "roles": ["member"],
        },
    )
    monkeypatch.setattr(domain_scope, "assert_token_context", lambda *args, **kwargs: None)
    monkeypatch.setattr(keystone, "revoke_token", MagicMock())
    monkeypatch.setattr(identity_roles.activity, "record", AsyncMock())
    return SimpleNamespace(
        app=app,
        native=native,
        conn=conn,
        info=info,
        current_admin=current_admin,
        caller_connection=caller_connection,
        store=deletion_store,
    )


async def remove(deletion, user_id="target", domain="home"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=deletion.app), base_url="http://test") as http:
        return await http.delete(
            f"/api/v1/admin/users/{user_id}", params={} if domain is None else {"domain_id": domain}
        )


async def login_session(user_id):
    jti = f"session-{user_id}"
    assert await session_store.store_session(
        jti,
        f"native-{user_id}",
        "personal-project",
        user_id,
        int(time.time()) + 3600,
        domain_id="home",
        identity_domain_id="home",
    )
    return jti


@pytest.mark.asyncio
async def test_delete_exact_federated_user_preserves_projects_and_revokes_sessions(deletion):
    target_jti, actor_jti = await login_session("target"), await login_session("operator")
    project = row(id="unowned", name="shared-project", domain_id="home", enabled=True, parent_id="home")
    deletion.native.project_rows[project.id] = project
    deletion.native.raw.append(grant("member", user="target", project=project.id))
    projects = dict(deletion.native.project_rows)
    redis = await session_store._get_redis()
    keys = [
        "afterglow:admin:users:home",
        "afterglow:admin:identity:summary",
        "afterglow:session:old:personal",
        "afterglow:user:target:domain:home:projects",
        "afterglow:identity:domain-context:target:home",
    ]
    for key in keys:
        await redis.set(key, "stale")
    response = await remove(deletion)
    assert response.status_code == 204 and response.content == b""
    assert deletion.native.deleted == ["target"]
    deletion.conn.identity.delete_user.assert_called_once_with("target", ignore_missing=False)
    deletion.conn.identity.get_domain.assert_called_once_with("home")
    deletion.conn.identity.get_user.assert_called_once_with("target")
    deletion.caller_connection.assert_not_called()
    assert deletion.native.project_rows == projects
    assert deletion.native.calls == []
    assert await session_store.get_session(target_jti) is None
    assert await session_store.get_session(actor_jti) is not None
    keystone.revoke_token.assert_called_once_with("native-target")
    assert all([await redis.get(key) is None for key in keys])
    recorded = identity_roles.activity.record.call_args.kwargs
    assert recorded["action"] == "admin_user_delete" and recorded["status"] == "success"
    assert recorded["extra"] == {"user_id": "target", "domain_id": "home"}


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["member", "revoked", "native-session"])
async def test_delete_requires_fresh_native_system_admin(deletion, monkeypatch, mode):
    if mode == "member":
        deletion.info["is_system_admin"] = False
    elif mode == "revoked":
        deletion.current_admin.return_value = False
    else:
        from keystoneauth1.exceptions.http import Unauthorized

        monkeypatch.setattr(keystone, "validate_token", MagicMock(side_effect=Unauthorized()))
    response = await remove(deletion)
    assert response.status_code == (401 if mode == "native-session" else 403)
    deletion.conn.identity.delete_user.assert_not_called()
    assert "target" in deletion.native.user_rows


@pytest.mark.asyncio
async def test_delete_revalidates_actor_after_inventory_before_native_write(deletion):
    deletion.current_admin.side_effect = [True, False]
    response = await remove(deletion)
    assert response.status_code == 403
    assert "target" in deletion.native.user_rows
    assert deletion.native.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_id,domain,status,detail",
    [
        ("target", None, 422, None),
        ("target", "", 422, None),
        ("target", "tenant-a", 403, "identity_domain_mismatch"),
        ("target", "absent", 404, "identity_domain_not_found"),
        ("missing", "home", 404, "identity_not_found"),
        ("operator", "home", 409, "identity_self_delete_forbidden"),
        ("executor", "home", 409, "identity_service_delete_forbidden"),
    ],
)
async def test_delete_exact_boundaries_fail_without_mutation(deletion, user_id, domain, status, detail):
    response = await remove(deletion, user_id, domain)
    assert response.status_code == status
    if detail:
        assert response.json()["detail"] == detail
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_rejects_unverified_target_or_executor(deletion):
    deletion.conn.identity.get_user.side_effect = lambda _: row(id="different", domain_id="home")
    response = await remove(deletion)
    assert response.status_code == 503
    deletion.conn.identity.delete_user.assert_not_called()
    deletion.conn.identity.get_user.side_effect = deletion.native.user_rows.get
    deletion.conn.session.auth.get_access.return_value = SimpleNamespace(user_id=None)
    assert (await remove(deletion)).status_code == 503
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["project", "system", "group-system", "group-project", "inherited"])
async def test_delete_protects_native_implied_service_authority(deletion, kind):
    native = deletion.native
    native.role_rows.extend([row(id="service-id", name="service", domain_id=None)])
    native.edges.append({"prior_role": {"id": "alias"}, "implies": [{"id": "service-id"}]})
    if kind.startswith("group"):
        native.group_rows["services"] = row(id="services", name="services", domain_id="home")
        native.members["services"] = {"target"}
    if kind in {"system", "group-system"}:
        source = {
            "group" if kind == "group-system" else "user": {"id": "services" if kind == "group-system" else "target"}
        }
        native.raw.append(row(role={"id": "alias"}, scope={"system": {"all": True}}, **source))
    elif kind == "inherited":
        native.raw.append(grant("alias", user="target", domain="tenant-b", inherited=True))
    else:
        native.raw.append(
            grant(
                "alias", **({"group": "services"} if kind == "group-project" else {"user": "target"}), project="work-b"
            )
        )
    response = await remove(deletion)
    assert response.status_code == 409 and response.json()["detail"] == "identity_service_delete_forbidden"
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_service_named_human_is_not_a_service_identity(deletion):
    deletion.native.user_rows["target"].name = "nova"
    assert (await remove(deletion)).status_code == 204


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["direct", "group", "inherited"])
async def test_delete_cannot_erase_project_ownership(deletion, kind):
    native = deletion.native
    if kind == "group":
        native.group_rows["owners"] = row(id="owners", name="owners", domain_id="home")
        native.members["owners"] = {"target"}
        native.raw.append(grant("project_owner", group="owners", project="work-b"))
    elif kind == "inherited":
        native.raw.append(grant("project_owner", user="target", domain="tenant-b", inherited=True))
    else:
        native.raw.append(grant("project_owner", user="target", project="work-b"))
    response = await remove(deletion)
    assert response.status_code == 409 and "ownership" in response.json()["detail"]
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_keeps_last_enabled_domain_manager(deletion):
    response = await remove(deletion, "creator")
    assert response.status_code == 409 and response.json()["detail"] == "last_domain_manager"
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("spare", [False, True])
async def test_delete_privileged_admin_requires_guarded_role_removal_first(deletion, spare):
    native = deletion.native
    native.raw = [r for r in native.raw if "system" not in r.scope]
    native.raw.append(row(user={"id": "target"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    if spare:
        native.raw.append(row(user={"id": "second"}, role={"id": "admin"}, scope={"system": {"all": True}}))
    response = await remove(deletion)
    assert response.status_code == (409 if spare else 422)
    assert deletion.native.deleted == []


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["from", "to"])
async def test_delete_blocks_unfinished_project_ownership_journal(deletion, participant):
    async with deletion.store() as db:
        db.add(
            ProjectOwnershipTransfer(
                project_id="work-b",
                id="transfer",
                domain_id="tenant-b",
                status="unknown",
                stage="native_outcome_unknown",
                from_user_id="target" if participant == "from" else "other",
                to_user_id="target" if participant == "to" else "other",
            )
        )
        await db.commit()
    response = await remove(deletion)
    assert response.status_code == 409
    assert response.json()["detail"] == "project_ownership_native_operation_unresolved"
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["source", "target"])
@pytest.mark.parametrize("status", ["applying", "attached", "unknown", "committed", "rolled_back"])
async def test_delete_fences_active_account_identity_transfers(deletion, participant, status):
    async with deletion.store() as db:
        db.add(
            AccountIdentityTransfer(
                binding_key="binding",
                status=status,
                snapshot_ciphertext="encrypted-receipt",
                source_user_id="target" if participant == "source" else "other",
                target_user_id="target" if participant == "target" else "other",
            )
        )
        await db.commit()
    response = await remove(deletion)
    resolved = status in {"committed", "rolled_back"}
    assert response.status_code == (204 if resolved else 409)
    assert deletion.native.deleted == (["target"] if resolved else [])
    if not resolved:
        assert response.json()["detail"] == "identity_transfer_recovery_required"


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary", ["journal", "authority", "session"])
async def test_delete_fails_closed_when_safety_prerequisite_unavailable(deletion, monkeypatch, boundary):
    if boundary == "journal":

        def unavailable():
            raise domain_auth.DomainAuthUnavailable("private")

        monkeypatch.setattr(domain_auth, "_factory", unavailable)
    elif boundary == "authority":
        deletion.native.role_assignments.list = MagicMock(side_effect=NativeError(503))
    else:
        redis = await session_store._get_redis()
        monkeypatch.setattr(redis, "ping", AsyncMock(side_effect=RuntimeError("private")))
    response = await remove(deletion)
    assert response.status_code == 503
    assert "private" not in response.text
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("status,expected", [(401, 403), (403, 403), (404, 404), (409, 409), (500, 503)])
async def test_delete_native_failures_are_visible_and_fence_sessions(deletion, status, expected):
    jti = await login_session("target")
    deletion.conn.identity.delete_user.side_effect = NativeError(status)
    response = await remove(deletion)
    assert response.status_code == expected and "provider-secret" not in response.text
    assert deletion.native.deleted == []
    assert await session_store.get_session(jti) is None
    deletion.conn.identity.delete_user.assert_called_once_with("target", ignore_missing=False)
    assert identity_roles.activity.record.call_args.kwargs["status"] == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["cancel", "lost-reply"])
async def test_delete_settles_native_work_and_cleanup_before_unlock(deletion, failure):
    jti = await login_session("target")
    entered, release = threading.Event(), threading.Event()
    original = deletion.conn.identity.delete_user.side_effect

    def delete(user_id, **kwargs):
        entered.set()
        assert release.wait(5)
        original(user_id, **kwargs)
        if failure == "lost-reply":
            raise ConnectionError("private lost response")

    deletion.conn.identity.delete_user.side_effect = delete
    request = asyncio.create_task(remove(deletion))
    try:
        assert await asyncio.to_thread(entered.wait, 5)
        if failure == "cancel":
            request.cancel()
        assert (await remove(deletion, "second")).status_code == 409
        release.set()
        if failure == "cancel":
            with pytest.raises(asyncio.CancelledError):
                await request
        else:
            assert (await request).status_code == 503
    finally:
        release.set()
    assert deletion.native.deleted == ["target"]
    assert await session_store.get_session(jti) is None
    redis = await session_store._get_redis()
    assert await redis.keys("afterglow:identity-role-graph:*") == []
    assert (await remove(deletion)).status_code == 404
    deletion.conn.identity.delete_user.assert_called_once_with("target", ignore_missing=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["domain", "user"])
@pytest.mark.parametrize("status,expected", [(401, 403), (403, 403), (404, 404), (500, 503)])
async def test_delete_native_boundary_denial_never_falls_back(deletion, operation, status, expected):
    getattr(deletion.conn.identity, f"get_{operation}").side_effect = NativeError(status)
    response = await remove(deletion)
    assert response.status_code == expected and "provider-secret" not in response.text
    deletion.conn.identity.delete_user.assert_not_called()
    deletion.caller_connection.assert_not_called()


@pytest.mark.asyncio
async def test_delete_does_not_count_disabled_spare_system_admin(deletion):
    native = deletion.native
    native.raw = [r for r in native.raw if "system" not in r.scope]
    native.user_rows["second"].enabled = False
    native.raw.extend(
        row(user={"id": uid}, role={"id": "admin"}, scope={"system": {"all": True}}) for uid in ("target", "second")
    )
    assert (await remove(deletion)).status_code == 422
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_does_not_block_unrelated_identity_transfer(deletion):
    async with deletion.store() as db:
        db.add(
            AccountIdentityTransfer(
                binding_key="other-binding",
                status="applying",
                snapshot_ciphertext="encrypted-receipt",
                source_user_id="other",
                target_user_id="second",
            )
        )
        await db.commit()
    assert (await remove(deletion)).status_code == 204


@pytest.mark.asyncio
async def test_delete_cleanup_failure_is_not_reported_as_success(deletion, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise RuntimeError("private session store failure")

    monkeypatch.setattr(session_store, "revoke_user_sessions", unavailable)
    response = await remove(deletion)
    assert response.status_code == 503 and "private" not in response.text
    assert deletion.native.deleted == ["target"]
    assert identity_roles.activity.record.call_args.kwargs["action"] == "admin_user_delete"
    deletion.conn.identity.delete_user.assert_called_once_with("target", ignore_missing=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("primary", [True, False])
async def test_delete_blocks_member_only_native_personal_owner(deletion, primary):
    native = deletion.native
    native.domain_rows["personal-home"] = row(id="personal-home", name="Personal", enabled=True)
    native.project_rows["owned-personal"] = row(
        id="owned-personal",
        name="personal-target",
        domain_id="personal-home",
        enabled=True,
        parent_id="personal-home",
        afterglow_personal_user_id="target",
        afterglow_personal_primary=primary,
    )
    native.raw.append(grant("member", user="target", project="owned-personal"))
    response = await remove(deletion)
    assert response.status_code == 409 and "Personal projects" in response.json()["detail"]
    deletion.conn.identity.delete_user.assert_not_called()
    assert "owned-personal" in native.project_rows


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,uncertain,allowed",
    [
        ("deferred", False, True),
        ("cancelled", False, True),
        ("accepted", False, True),
        ("creating", False, False),
        ("activating", False, False),
        ("deferred", True, False),
    ],
)
async def test_delete_personal_provisioning_requires_settled_empty_intent(deletion, status, uncertain, allowed):
    async with deletion.store() as db:
        db.add(
            PersonalProjectIntent(
                token_hash="personal-intent",
                user_id="target",
                primary_user_id="target",
                primary=True,
                status=status,
                identity_domain_id="home",
                personal_domain_id="personal-home",
                personal_project_name="personal-target",
                personal_quotas={},
                added_grants=[],
                project_creation_uncertain=uncertain,
            )
        )
        await db.commit()
    response = await remove(deletion)
    assert response.status_code == (204 if allowed else 409)
    assert deletion.native.deleted == (["target"] if allowed else [])


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["granting", "recovery_required", "accepted"])
async def test_delete_fences_unfinished_enrollment_not_accepted_empty_receipt(deletion, status):
    from datetime import UTC, datetime, timedelta

    async with deletion.store() as db:
        db.add(
            DomainEnrollment(
                id=1,
                kind="managed_create",
                email="target@test.invalid",
                token_hash="enrollment-target",
                user_id="target",
                new_user=True,
                status=status,
                added_grants=[],
                added_role_ids=[],
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await db.commit()
    response = await remove(deletion)
    assert response.status_code == (204 if status == "accepted" else 409)
    assert deletion.native.deleted == (["target"] if status == "accepted" else [])


@pytest.mark.asyncio
async def test_delete_personal_inventory_failure_is_not_absence(deletion):
    deletion.native.projects.list = MagicMock(side_effect=NativeError(503))
    deletion.native.domain_rows["personal-home"] = row(id="personal-home", name="Personal", enabled=True)
    assert (await remove(deletion)).status_code == 503
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_enrollment_native_marker_fences_unknown_create_reply(deletion):
    from datetime import UTC, datetime, timedelta

    deletion.native.user_rows["target"].afterglow_enrollment_id = "uncertain-enrollment"
    async with deletion.store() as db:
        db.add(
            DomainEnrollment(
                id=1,
                kind="managed_create",
                email="target@test.invalid",
                token_hash="uncertain-enrollment",
                user_id=None,
                new_user=True,
                status="recovery_required",
                creation_uncertain=True,
                expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
        )
        await db.commit()
    response = await remove(deletion)
    assert response.status_code == 409 and "enrollment" in response.json()["detail"]
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_completed_personal_intent_still_protects_live_project_without_marker(deletion):
    native = deletion.native
    native.domain_rows["personal-home"] = row(id="personal-home", name="Personal", enabled=True)
    native.project_rows["receipt-project"] = row(
        id="receipt-project",
        name="personal-target",
        domain_id="personal-home",
        enabled=True,
        parent_id="personal-home",
    )
    async with deletion.store() as db:
        db.add(
            PersonalProjectIntent(
                token_hash="accepted-intent",
                user_id="target",
                primary_user_id="target",
                primary=True,
                status="accepted",
                identity_domain_id="home",
                personal_domain_id="personal-home",
                personal_project_id="receipt-project",
                personal_project_name="personal-target",
                personal_quotas={},
                added_grants=[],
                project_creation_uncertain=False,
            )
        )
        await db.commit()
    assert (await remove(deletion)).status_code == 409
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_protects_admin_only_native_service_account(deletion):
    native = deletion.native
    native.user_rows["target"].name = "nova"
    native.project_rows["native-service"] = row(
        id="native-service",
        name="service",
        domain_id="home",
        enabled=True,
        parent_id="home",
    )
    native.raw.append(grant("admin", user="target", project="native-service"))
    assert all(role.name != "service" for role in native.role_rows)
    response = await remove(deletion)
    assert response.status_code == 409
    assert response.json()["detail"] == "identity_service_delete_forbidden"
    deletion.conn.identity.delete_user.assert_not_called()


@pytest.mark.asyncio
async def test_delete_privileged_user_becomes_deletable_after_native_role_removed(deletion):
    native = deletion.native
    assigned = grant("admin", user="target", project="work-b")
    native.raw.append(assigned)
    assert (await remove(deletion)).status_code == 409
    native.raw.remove(assigned)
    assert (await remove(deletion)).status_code == 204


@pytest.mark.asyncio
async def test_raw_system_service_protection_is_deletion_opt_in(deletion):
    native = deletion.native
    native.role_rows.append(row(id="service-only", name="service", domain_id=None))
    native.raw.append(row(user={"id": "target"}, role={"id": "service-only"}, scope={"system": {"all": True}}))
    target = native.user_rows["target"]
    assert await domain_iam.protected_user(target, "home", credentials=False) is False
    assert await domain_iam.protected_user(target, "home", credentials=False, system_services=True) is True
    deletion.conn.identity.delete_user.assert_not_called()
