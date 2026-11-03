"""Real isolated SQL transitions; synthetic native authority and SMTP boundaries."""

import asyncio
import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from sqlalchemy import Integer, MetaData, func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import deps
from app.api.identity import admin_announcements, admin_mail_delivery, profile_mail
from app.models.activity import ActivityLog
from app.models.announcement import Announcement
from app.models.email_delivery import EmailDelivery, EmailNotificationCursor, EmailOperation, EmailPreference
from app.services import (
    admin_password_reset,
    announcements,
    domain_iam,
    domain_projects,
    email_service,
    keystone,
    mail_crypto,
    mail_settings,
)
from app.services import mail_delivery as svc

USER = "1" * 32
OTHER = "2" * 32
ADMIN = "a" * 32
NOW = datetime(2026, 11, 3, 12, tzinfo=UTC)


@pytest_asyncio.fixture
async def state(monkeypatch, tmp_path):
    state = SimpleNamespace(
        users={
            USER: {"id": USER, "domain_id": "home", "name": "alice", "email": "alice@example.test", "enabled": True},
            OTHER: {"id": OTHER, "domain_id": "home", "name": "bob", "email": "bob@example.test", "enabled": True},
        },
        memberships={(USER, "project"), (OTHER, "project")},
        admin=True,
        sent=[],
        service_users=set(),
        disabled_homes=set(),
        status="accepted",
        transport_hook=None,
        actor={"user_id": ADMIN, "username": "operator", "identity_domain_id": "home", "is_system_admin": True},
        current_user={"user_id": USER, "identity_domain_id": "home"},
        settings=SimpleNamespace(
            revision=1,
            smtp=SimpleNamespace(enabled=True, from_address="sender@example.test", from_name="Afterglow"),
            notifications=SimpleNamespace(announcements_enabled=True, resource_alerts_enabled=False),
        ),
    )
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mail.sqlite'}")
    metadata = MetaData()
    for model in (EmailOperation, EmailDelivery, EmailPreference, EmailNotificationCursor, Announcement, ActivityLog):
        table = model.__table__.to_metadata(metadata)
        # SQLite autoincrement requires exactly INTEGER; production keeps BIGINT.
        if model in (Announcement, ActivityLog):
            table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(metadata.create_all)
    state.factory = async_sessionmaker(engine, expire_on_commit=False)
    for module in (svc, announcements):
        monkeypatch.setattr(module, "get_session_factory", lambda: state.factory)
        monkeypatch.setattr(module, "is_db_available", lambda: True)
    monkeypatch.setattr(svc, "_now", lambda: NOW)
    monkeypatch.setattr(mail_crypto, "derive_encryption_subkey", lambda context: b"m" * 32)
    monkeypatch.setattr(admin_password_reset, "get_settings", lambda: SimpleNamespace(os_username="operator-service"))

    def get_user(uid):
        if uid not in state.users:
            raise HTTPException(404, "not found")
        return copy.deepcopy(state.users[uid])

    def assignments(**kwargs):
        if kwargs.get("effective") and kwargs.get("user") in state.service_users:
            return [
                {"user": {"id": kwargs["user"]}, "role": {"id": "service"}, "scope": {"project": {"id": "project"}}}
            ]
        return []

    roles = [{"id": name, "name": name, "domain_id": None} for name in ("service", "reader", "admin")]
    state.ks = SimpleNamespace(
        users=SimpleNamespace(get=get_user),
        domains=SimpleNamespace(get=lambda did: {"id": did, "enabled": did not in state.disabled_homes}),
        roles=SimpleNamespace(list=lambda: roles),
        inference_rules=SimpleNamespace(list_inference_roles=lambda: []),
        role_assignments=SimpleNamespace(list=assignments),
        groups=SimpleNamespace(list=lambda **kw: []),
        session=SimpleNamespace(session=SimpleNamespace(close=lambda: None)),
    )
    monkeypatch.setattr(keystone, "_get_admin_ks_client", lambda: state.ks)
    monkeypatch.setattr(keystone, "_is_system_admin", lambda uid: state.admin and uid == ADMIN)
    monkeypatch.setattr(
        domain_iam, "_account_rows", lambda ks, domain: [copy.deepcopy(u) for u in state.users.values()]
    )

    def membership(uid, pid, **kwargs):
        if (uid, pid) not in state.memberships:
            raise HTTPException(403, "membership denied")

    monkeypatch.setattr(domain_projects, "assert_project_membership", membership)

    async def effective_settings(**kwargs):
        return state.settings

    async def send_message(message, *, smtp=None):
        async with state.factory() as session:
            delivery = await session.scalar(
                select(EmailDelivery).where(EmailDelivery.message_id == message["Message-ID"])
            )
            assert delivery.status == "dispatching"  # committed before any SMTP
        if state.transport_hook:
            await state.transport_hook(message)
        state.sent.append(message)
        return SimpleNamespace(status=state.status, code="smtp_rejected" if state.status == "failed" else None)

    monkeypatch.setattr(mail_settings, "effective_settings", effective_settings)
    monkeypatch.setattr(email_service, "send_message", send_message)
    yield state
    await engine.dispose()


@pytest_asyncio.fixture
async def client(state):
    app = FastAPI()
    app.include_router(admin_mail_delivery.router, prefix="/api/v1/admin")
    app.include_router(admin_announcements.router, prefix="/api/v1/admin/announcements")
    app.include_router(profile_mail.router, prefix="/api/v1/profile")

    async def actor():
        if not state.admin:
            raise HTTPException(403, "administrator revoked")
        return state.actor

    async def token_info():
        return state.current_user

    app.dependency_overrides[deps.require_admin] = actor
    app.dependency_overrides[deps.get_token_info] = token_info
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://local.test") as http:
        yield http


async def individual(state, **changes):
    values = {
        "actor_id": ADMIN,
        "operation_id": str(uuid4()),
        "user_ids": [USER],
        "subject": "Hello <script>",
        "body": "Private <b>body</b>",
    }
    values.update(changes)
    return await svc.send_individual(**values)


async def rows(state):
    async with state.factory() as session:
        return list((await session.scalars(select(EmailDelivery).order_by(EmailDelivery.id))).all())


async def announcement(state, **changes):
    values = {
        "title": "Notice",
        "body": "Text only <b>notice</b>",
        "severity": "info",
        "target_type": "all",
        "target_id": None,
        "starts_at": None,
        "ends_at": None,
        "created_by_user_id": ADMIN,
        "created_by_username": "operator",
    }
    values.update(changes)
    result = await announcements.create_announcement(**values)
    if values.get("send_email") and (not values["starts_at"] or values["starts_at"] <= NOW):
        await svc._expand_announcements(NOW)
        async with state.factory() as session:
            operation = await session.scalar(
                select(EmailOperation).where(
                    EmailOperation.actor_id == ADMIN, EmailOperation.operation_id == values["email_operation_id"]
                )
            )
            result["email_operation"] = await svc._summary(session, operation)
    return result


async def test_encrypted_intent_and_stable_message_id_sql_dispatch(state):
    summary = await individual(state)
    delivery = (await rows(state))[0]
    assert summary["counts"]["pending"] == 1
    assert delivery.payload_encrypted.startswith("v3:")
    assert "Private" not in delivery.payload_encrypted and "Hello" not in delivery.payload_encrypted
    assert svc._payload(delivery)["body"] == "Private <b>body</b>"
    await svc._dispatch_one(delivery.id)
    await svc._dispatch_one(delivery.id)
    assert len(state.sent) == 1
    assert state.sent[0]["Message-ID"] == delivery.message_id
    assert "&lt;b&gt;" in state.sent[0].get_body(preferencelist=("html",)).get_content()
    dto = await svc.get_delivery(delivery.id)
    assert dto["status"] == "accepted" and "body" not in dto and "payload_encrypted" not in dto


async def test_actor_operation_dedup_and_conflicting_payload(state):
    operation_id = str(uuid4())
    first = await individual(state, operation_id=operation_id)
    second = await individual(state, operation_id=operation_id)
    assert first == second and len(await rows(state)) == 1
    with pytest.raises(HTTPException) as caught:
        await individual(state, operation_id=operation_id, body="Different content")
    assert caught.value.status_code == 409
    await individual(state, operation_id=operation_id, actor_id=OTHER)
    assert len(await rows(state)) == 2


async def test_duplicate_native_uuid_forms_are_one_recipient(state):
    await individual(state, user_ids=[USER, str(UUID(USER))])
    assert len(await rows(state)) == 1


async def test_individual_mail_preserves_federated_keystone_id(client, state):
    user_id = "f" * 64
    state.users[user_id] = {**state.users[USER], "id": user_id, "email": "federated@example.test"}
    operation_id = str(uuid4())
    request = {"operation_id": operation_id, "user_ids": [user_id, user_id], "subject": "Hello", "body": "Private"}
    response = await client.post("/api/v1/admin/email/messages", json=request)
    assert response.status_code == 202, response.text
    replay = await client.post("/api/v1/admin/email/messages", json=request)
    assert replay.json() == response.json()
    deliveries = await rows(state)
    assert [row.user_id for row in deliveries] == [user_id]
    await svc._dispatch_one(deliveries[0].id)
    assert (await svc.get_delivery(deliveries[0].id))["status"] == "accepted"
    assert str(state.sent[0]["To"]) == "federated@example.test"


@pytest.mark.parametrize(
    "change", ["email", "home", "disabled", "service", "duplicate", "home_disabled", "deleted", "sender_revoked"]
)
async def test_dispatch_revalidates_identity_uniqueness_human_and_sender(state, change):
    await individual(state)
    if change == "email":
        state.users[USER]["email"] = "changed@example.test"
    elif change == "home":
        state.users[USER]["domain_id"] = "other-home"
    elif change == "disabled":
        state.users[USER]["enabled"] = False
    elif change == "service":
        state.service_users.add(USER)
    elif change == "duplicate":
        state.users[OTHER]["email"] = "ALICE@example.test"
    elif change == "home_disabled":
        state.disabled_homes.add("home")
    elif change == "deleted":
        del state.users[USER]
    else:
        state.admin = False
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    assert not state.sent
    assert (await svc.get_delivery(delivery.id))["status"] == "cancelled"


@pytest.mark.parametrize("outcome", ["failed", "unknown"])
async def test_failed_and_uncertain_smtp_are_never_replayed(state, outcome):
    state.status = outcome
    await individual(state)
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    await svc._dispatch_one(delivery.id)
    assert len(state.sent) == 1
    assert (await svc.get_delivery(delivery.id))["status"] == outcome


async def test_committed_crash_fence_is_recovered_without_smtp(state):
    await individual(state)
    delivery = (await rows(state))[0]
    await svc._set_status(delivery.id, "dispatching", expected="pending")
    await svc.scheduler_tick(recover_dispatching=True)
    assert not state.sent
    assert (await svc.get_delivery(delivery.id))["status"] == "unknown"


async def test_cancellation_drains_late_smtp_and_persists_acceptance(state):
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(message):
        entered.set()
        await release.wait()

    state.transport_hook = slow
    await individual(state)
    delivery = (await rows(state))[0]
    task = asyncio.create_task(svc._dispatch_one(delivery.id))
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert (await svc.get_delivery(delivery.id))["status"] == "accepted"
    assert len(state.sent) == 1


async def test_smtp_disabled_leaves_explicit_intent_pending(state):
    await individual(state)
    state.settings.smtp.enabled = False
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    assert not state.sent and (await svc.get_delivery(delivery.id))["status"] == "pending"
    state.settings.smtp.enabled = True
    await svc._dispatch_one(delivery.id)
    assert len(state.sent) == 1


async def test_announcement_create_mail_atomic_and_idempotent(state):
    operation_id = str(uuid4())
    first = await announcement(state, send_email=True, email_operation_id=operation_id)
    second = await announcement(state, send_email=True, email_operation_id=operation_id)
    assert first["id"] == second["id"] and first["email_operation"] == second["email_operation"]
    async with state.factory() as session:
        assert await session.scalar(select(func.count()).select_from(Announcement)) == 1
    assert len(await rows(state)) == 2


async def test_announcement_failure_rolls_back_announcement_and_intent(state, monkeypatch):
    async def unavailable(*args, **kwargs):
        raise ValueError("mail_intent_unavailable")

    monkeypatch.setattr(svc, "_persist", unavailable)
    with pytest.raises(ValueError):
        await announcement(state, send_email=True, email_operation_id=str(uuid4()))
    async with state.factory() as session:
        assert await session.scalar(select(func.count()).select_from(Announcement)) == 0
        assert await session.scalar(select(func.count()).select_from(EmailOperation)) == 0
        assert await session.scalar(select(func.count()).select_from(EmailDelivery)) == 0


async def test_announcement_audience_is_complete_not_ui_truncated(state):
    for index in range(3, 108):
        uid = f"{index:032x}"
        state.users[uid] = {
            "id": uid,
            "domain_id": "home",
            "name": f"user-{index}",
            "email": f"u{index}@example.test",
            "enabled": True,
        }
    created = await announcement(state, send_email=True, email_operation_id=str(uuid4()))
    assert created["email_operation"]["counts"]["pending"] == 107


async def test_project_audience_and_membership_revocation(state):
    state.memberships.remove((OTHER, "project"))
    created = await announcement(
        state, target_type="project", target_id="project", send_email=True, email_operation_id=str(uuid4())
    )
    assert created["email_operation"]["counts"]["pending"] == 1
    state.memberships.clear()
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    assert not state.sent and (await svc.get_delivery(delivery.id))["status"] == "cancelled"


@pytest.mark.parametrize("change", ["content", "audience", "schedule", "disabled", "deleted", "expired"])
async def test_announcement_dispatch_fences_exact_version_and_active_bounds(state, change):
    created = await announcement(
        state, target_type="user", target_id=USER, send_email=True, email_operation_id=str(uuid4())
    )
    async with state.factory() as session, session.begin():
        row = await session.get(Announcement, created["id"])
        if change == "content":
            row.body = "replacement"
        elif change == "audience":
            row.target_id = OTHER
        elif change == "schedule":
            row.starts_at = NOW + timedelta(days=1)
        elif change == "disabled":
            row.is_active = False
        elif change == "deleted":
            await session.delete(row)
    delivery = (await rows(state))[0]
    if change == "expired":
        # An unchanged announcement with a bound finite window expires in queue.
        async with state.factory() as session, session.begin():
            row = await session.get(Announcement, created["id"])
            row.ends_at = NOW + timedelta(seconds=1)
            await session.flush()
            payload = svc._payload(delivery)
            payload["announcement_fingerprint"] = svc._announcement_fingerprint(row)
            await session.execute(
                update(EmailDelivery)
                .where(EmailDelivery.id == delivery.id)
                .values(
                    payload_encrypted=mail_crypto.encrypt_secret(svc._json(payload), purpose="delivery:" + delivery.id)
                )
            )
    await svc._dispatch_one(delivery.id, now=NOW + timedelta(seconds=2))
    assert not state.sent and (await svc.get_delivery(delivery.id))["status"] == "cancelled"


async def test_scheduled_announcement_waits_without_blocking_direct_mail(state):
    created = await announcement(
        state,
        target_type="user",
        target_id=USER,
        starts_at=NOW + timedelta(hours=1),
        send_email=True,
        email_operation_id=str(uuid4()),
    )
    await individual(state)
    await svc.scheduler_tick(now=NOW)
    assert len(state.sent) == 1 and state.sent[0]["Subject"] == "Hello <script>"
    await svc.scheduler_tick(now=NOW + timedelta(hours=1))
    assert len(state.sent) == 2 and state.sent[1]["Subject"] == created["title"]


async def test_notification_preferences_global_gates_and_direct_bypass(state):
    await svc.preferences(state.current_user, values={"announcements": False, "resource_alerts": False})
    await announcement(state, target_type="user", target_id=USER, send_email=True, email_operation_id=str(uuid4()))
    await individual(state)
    await svc.scheduler_tick()
    assert len(state.sent) == 1 and state.sent[0]["Subject"] == "Hello <script>"
    assert (
        await svc.enqueue_notification(
            user_id=USER, project_id="project", event_key="future:one", subject="Safe", body="Safe"
        )
        is None
    )
    state.settings.notifications.resource_alerts_enabled = True
    assert (
        await svc.enqueue_notification(
            user_id=USER, project_id="project", event_key="future:one", subject="Safe", body="Safe"
        )
        is None
    )
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    first = await svc.enqueue_notification(
        user_id=USER, project_id="project", event_key="future:one", subject="Safe", body="Safe"
    )
    second = await svc.enqueue_notification(
        user_id=USER, project_id="project", event_key="future:one", subject="Safe", body="Safe"
    )
    assert first == second
    state.settings.notifications.resource_alerts_enabled = False
    delivery = next(row for row in await rows(state) if row.kind == "resource_alert")
    await svc._dispatch_one(delivery.id)
    assert (await svc.get_delivery(delivery.id))["status"] == "cancelled"


async def test_activity_cursor_future_only_dedup_and_safe_projection(state):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})

    async def activity(
        *, source="openstack", resource_type="instance", method=None, created_at=NOW + timedelta(seconds=1)
    ):
        async with state.factory() as session, session.begin():
            session.add(
                ActivityLog(
                    created_at=created_at,
                    project_id="project",
                    user_id=USER,
                    username="private-name",
                    resource_type=resource_type,
                    resource_id="resource-id",
                    action="create",
                    status="failed",
                    source=source,
                    error_message="secret-token-do-not-copy",
                    extra={"password": "never-copy", "method": method},
                )
            )

    await activity(created_at=NOW - timedelta(days=5))
    await svc._collect_notifications(state.settings, NOW, 100)
    assert not await rows(state)
    await activity()  # supported future native event
    await activity(source="afterglow")
    await activity(source="browser")
    await activity(resource_type="auth")
    await activity(source="afterglow", method="GET")  # dashboard reads do not trigger mail
    await activity(created_at=NOW - timedelta(days=1))  # late historical ingestion
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=2), 100)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=3), 100)
    deliveries = await rows(state)
    assert len(deliveries) == 2
    for row in deliveries:
        payload = svc._payload(row)
        assert (
            "secret-token" not in str(payload) and "password" not in str(payload) and "private-name" not in str(payload)
        )
    state.settings.notifications.resource_alerts_enabled = False
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=4), 100)
    await activity()
    state.settings.notifications.resource_alerts_enabled = True
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=5), 100)
    assert len(await rows(state)) == 2  # enabling skips the disabled interval


async def test_current_home_preferences_never_follow_target_substitution(state, client):
    response = await client.get("/api/v1/profile/email-notifications")
    assert response.json() == {"announcements": True, "resource_alerts": False}
    rejected = await client.put(
        "/api/v1/profile/email-notifications", json={"user_id": OTHER, "announcements": False, "resource_alerts": True}
    )
    assert rejected.status_code == 422
    state.current_user["identity_domain_id"] = "wrong-home"
    assert (await client.get("/api/v1/profile/email-notifications")).status_code == 401


async def test_admin_intent_history_test_and_no_body_disclosure(state, client):
    operation_id = str(uuid4())
    response = await client.post(
        "/api/v1/admin/email/messages",
        json={"operation_id": operation_id, "user_ids": [USER], "subject": "Private", "body": "body-never-in-history"},
    )
    assert response.status_code == 202
    history = await client.get("/api/v1/admin/email/deliveries")
    assert history.status_code == 200 and history.json()["total"] == 1
    assert "body-never" not in history.text and "no-store" in history.headers["cache-control"]
    test = await client.post(
        "/api/v1/admin/email/test-message", json={"operation_id": str(uuid4()), "recipient_email": "test@example.test"}
    )
    assert test.status_code == 202
    target = next(row for row in await rows(state) if row.kind == "test")
    assert (await svc.get_receipt_target(target.id))["kind"] == "test"
    assert (await client.get("/api/v1/admin/email/deliveries/" + target.id)).status_code == 200
    state.admin = False
    assert (await client.get("/api/v1/admin/email/deliveries")).status_code == 403
    assert (
        await client.post(
            "/api/v1/admin/email/test-message", json={"operation_id": str(uuid4()), "recipient_email": "x@example.test"}
        )
    ).status_code == 403


async def test_explicit_existing_announcement_api_and_missing_operation_fence(state, client):
    invalid = await client.post(
        "/api/v1/admin/announcements", json={"title": "Title", "body": "Body", "target_type": "all", "send_email": True}
    )
    assert invalid.status_code == 422
    created = await announcement(state, target_type="user", target_id=USER)
    response = await client.post(
        f"/api/v1/admin/announcements/{created['id']}/email", json={"operation_id": str(uuid4())}
    )
    assert response.status_code == 202 and response.json()["status"] == "pending"
    assert response.json()["counts"]["pending"] == 0  # current audience is resolved by the worker
    await svc._expand_announcements(NOW)
    assert len(await rows(state)) == 1


async def test_disabled_database_scheduler_does_not_touch_other_services(state, monkeypatch):
    monkeypatch.setattr(svc, "is_db_available", lambda: False)
    await svc.scheduler_tick(recover_dispatching=True)
    assert not state.sent


async def test_concurrent_workers_consume_one_sql_dispatch(state):
    await individual(state)
    delivery = (await rows(state))[0]
    await asyncio.gather(svc._dispatch_one(delivery.id), svc._dispatch_one(delivery.id))
    assert len(state.sent) == 1
    assert (await svc.get_delivery(delivery.id))["status"] == "accepted"


@pytest.mark.parametrize(
    "column,value",
    [
        ("user_id", OTHER),
        ("identity_domain_id", "other-home"),
        ("project_id", "different-project"),
        ("recipient_email", "mallory@example.test"),
    ],
)
async def test_encrypted_payload_binds_exact_recipient_columns(state, column, value):
    await individual(state)
    delivery = (await rows(state))[0]
    async with state.factory() as session, session.begin():
        await session.execute(update(EmailDelivery).where(EmailDelivery.id == delivery.id).values({column: value}))
    await svc._dispatch_one(delivery.id)
    saved = (await rows(state))[0]
    assert saved.status == "failed" and saved.error_code == "payload_unavailable"
    assert not state.sent
    history = await svc.list_deliveries()
    assert history["total"] == 1 and history["items"][0]["subject"] == "[Content unavailable]"
    assert (await svc.get_delivery(delivery.id))["status"] == "failed"


async def test_announcement_edit_restore_aba_cannot_revive_old_intent(state):
    created = await announcement(
        state, target_type="user", target_id=USER, send_email=True, email_operation_id=str(uuid4())
    )
    await announcements.update_announcement(created["id"], body="Replacement")
    await announcements.update_announcement(created["id"], body=created["body"])
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    assert not state.sent and (await svc.get_delivery(delivery.id))["status"] == "cancelled"


async def test_optout_then_optin_does_not_revive_queued_notification(state):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    await svc.enqueue_notification(
        user_id=USER, project_id="project", event_key="future:event", subject="Safe", body="Safe"
    )
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": False})
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    delivery = (await rows(state))[0]
    await svc._dispatch_one(delivery.id)
    assert not state.sent and (await svc.get_delivery(delivery.id))["status"] == "cancelled"


async def test_notification_home_binding_rejects_stale_subscriber(state):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    with pytest.raises(HTTPException) as caught:
        await svc.enqueue_notification(
            user_id=USER,
            expected_identity_domain_id="old-home",
            project_id="project",
            event_key="future:event",
            subject="Safe",
            body="Safe",
        )
    assert caught.value.status_code == 409 and not await rows(state)


async def test_body_and_address_validation_never_echoes_submitted_input(state, client):
    response = await client.post(
        "/api/v1/admin/email/messages",
        json={
            "operation_id": "invalid-secret-value",
            "user_ids": [USER],
            "subject": "Header\nInjected",
            "body": "sensitive-draft",
        },
    )
    assert response.status_code == 422
    assert "sensitive-draft" not in response.text and "invalid-secret-value" not in response.text
    arbitrary = await client.post(
        "/api/v1/admin/email/messages",
        json={
            "operation_id": str(uuid4()),
            "user_ids": [USER],
            "subject": "Hi",
            "body": "Hi",
            "recipient_email": "mallory@example.test",
        },
    )
    assert arbitrary.status_code == 422 and not await rows(state)


async def test_cursor_replay_after_enqueue_commit_has_durable_event_dedup(state):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    await svc._collect_notifications(state.settings, NOW, 100)
    async with state.factory() as session, session.begin():
        session.add(
            ActivityLog(
                created_at=NOW + timedelta(seconds=1),
                project_id="project",
                user_id=USER,
                username="alice",
                resource_type="volume",
                resource_id="resource-id",
                action="create",
                status="failed",
                source="afterglow",
            )
        )
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=2), 100)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=3), 100)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=3), 100)
    assert len(await rows(state)) == 1


@pytest.mark.parametrize("target_type", ["all", "project"])
async def test_scheduled_announcement_resolves_users_joining_before_active_dispatch(state, target_type):
    starts = NOW + timedelta(hours=1)
    created = await announcement(
        state,
        target_type=target_type,
        target_id="project" if target_type == "project" else None,
        starts_at=starts,
        send_email=True,
        email_operation_id=str(uuid4()),
    )
    assert created["email_operation"]["status"] == "pending" and not await rows(state)
    assert created["email_operation"]["audience_pending"] is True
    newcomer = "3" * 32
    state.users[newcomer] = {
        "id": newcomer,
        "domain_id": "home",
        "name": "newcomer",
        "email": "newcomer@example.test",
        "enabled": True,
    }
    state.memberships.add((newcomer, "project"))
    if target_type == "project":
        state.memberships.remove((OTHER, "project"))
    await svc.scheduler_tick(now=starts)
    targets = {str(message["To"]) for message in state.sent}
    assert "newcomer@example.test" in targets and "alice@example.test" in targets
    assert ("bob@example.test" in targets) == (target_type == "all")
    async with state.factory() as session:
        operation = await session.scalar(select(EmailOperation).where(EmailOperation.announcement_id == created["id"]))
        summary = await svc._summary(session, operation)
        assert summary["audience_pending"] is False
        assert summary["status"] == "accepted"


async def test_deferred_announcement_creation_performs_no_native_audience_reads(state, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("HTTP submission must not traverse the native audience")

    monkeypatch.setattr(svc, "_audience", forbidden)
    created = await announcements.create_announcement(
        title="Future",
        body="Body",
        severity="info",
        target_type="all",
        target_id=None,
        starts_at=NOW + timedelta(hours=1),
        ends_at=None,
        created_by_user_id=ADMIN,
        created_by_username="operator",
        send_email=True,
        email_operation_id=str(uuid4()),
    )
    assert created["email_operation"]["status"] == "pending" and not await rows(state)


@pytest.mark.parametrize("ineligible", ["disabled", "service", "not_opted_in"])
async def test_cursor_skips_ineligible_409_or_unsubscribed_before_eligible_user(state, ineligible):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    if ineligible != "not_opted_in":
        await svc.preferences(
            {"user_id": OTHER, "identity_domain_id": "home"}, values={"announcements": True, "resource_alerts": True}
        )
    if ineligible == "disabled":
        state.users[OTHER]["enabled"] = False
    elif ineligible == "service":
        state.service_users.add(OTHER)
    await svc._collect_notifications(state.settings, NOW, 100)
    async with state.factory() as session, session.begin():
        for number, user_id in [(10, OTHER), (20, USER)]:
            session.add(
                ActivityLog(
                    id=number,
                    created_at=NOW + timedelta(seconds=1),
                    project_id="project",
                    user_id=user_id,
                    username="user",
                    resource_type="instance",
                    resource_id="resource-id",
                    action="create",
                    status="failed",
                    source="afterglow",
                )
            )
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=5), 100)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 100)
    deliveries = await rows(state)
    assert len(deliveries) == 1 and deliveries[0].user_id == USER
    async with state.factory() as session:
        markers = (
            await session.scalars(
                select(EmailOperation.notification_activity_id).where(
                    EmailOperation.notification_activity_id.is_not(None)
                )
            )
        ).all()
        assert set(markers) == {10, 20}


async def test_unseen_marker_collects_lower_id_after_newer_event_already_processed(state):
    state.settings.notifications.resource_alerts_enabled = True
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    await svc._collect_notifications(state.settings, NOW, 100)

    async def insert(number):
        async with state.factory() as session, session.begin():
            session.add(
                ActivityLog(
                    id=number,
                    created_at=NOW + timedelta(seconds=1),
                    project_id="project",
                    user_id=USER,
                    username="user",
                    resource_type="volume",
                    resource_id=f"volume-{number}",
                    action="create",
                    status="failed",
                    source="openstack",
                )
            )

    await insert(20)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=5), 100)
    assert len(await rows(state)) == 1
    await insert(10)  # represents an earlier allocated transaction committing later
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 100)
    assert len(await rows(state)) == 2


async def test_unsubscribed_events_skip_native_identity_reads(state, monkeypatch):
    state.settings.notifications.resource_alerts_enabled = True

    async def forbidden(*args, **kwargs):
        raise AssertionError("unsubscribed event performed a native read")

    monkeypatch.setattr(svc, "_recipient", forbidden)
    assert (
        await svc.enqueue_notification(
            user_id=USER, project_id="project", event_key="future:one", subject="Safe", body="Safe"
        )
        is None
    )


async def test_disabled_smtp_skips_pending_native_authority_reads(state, monkeypatch):
    await individual(state)
    state.settings.smtp.enabled = False

    async def forbidden(*args, **kwargs):
        raise AssertionError("disabled SMTP performed a pending native read")

    monkeypatch.setattr(svc, "_recipient", forbidden)
    monkeypatch.setattr(svc, "_actor_allowed", forbidden)
    await svc.scheduler_tick()
    assert not state.sent and (await rows(state))[0].status == "pending"


async def test_activity_user_optin_cutoff_prevents_late_historical_blast(state, monkeypatch):
    state.settings.notifications.resource_alerts_enabled = True
    await svc._collect_notifications(state.settings, NOW, 100)
    async with state.factory() as session, session.begin():
        session.add(
            ActivityLog(
                id=10,
                created_at=NOW + timedelta(seconds=1),
                project_id="project",
                user_id=USER,
                username="user",
                resource_type="instance",
                resource_id="instance-id",
                action="create",
                status="failed",
                source="afterglow",
            )
        )
    monkeypatch.setattr(svc, "_now", lambda: NOW + timedelta(seconds=5))
    await svc.preferences(state.current_user, values={"announcements": True, "resource_alerts": True})
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 100)
    assert not await rows(state)
    async with state.factory() as session, session.begin():
        assert (
            await session.scalar(select(EmailOperation.id).where(EmailOperation.notification_activity_id == 10))
            is not None
        )
        session.add(
            ActivityLog(
                id=20,
                created_at=NOW + timedelta(seconds=6),
                project_id="project",
                user_id=USER,
                username="user",
                resource_type="instance",
                resource_id="instance-id",
                action="create",
                status="failed",
                source="afterglow",
            )
        )
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 100)
    assert len(await rows(state)) == 1


async def test_transient_native_failure_is_not_marked_and_does_not_block_eligible_event(state, monkeypatch):
    state.settings.notifications.resource_alerts_enabled = True
    for uid in (USER, OTHER):
        await svc.preferences(
            {"user_id": uid, "identity_domain_id": "home"}, values={"announcements": True, "resource_alerts": True}
        )
    await svc._collect_notifications(state.settings, NOW, 100)
    async with state.factory() as session, session.begin():
        for number, uid in [(10, OTHER), (20, USER)]:
            session.add(
                ActivityLog(
                    id=number,
                    created_at=NOW + timedelta(seconds=1),
                    project_id="project",
                    user_id=uid,
                    username="user",
                    resource_type="volume",
                    resource_id="volume-id",
                    action="create",
                    status="failed",
                    source="afterglow",
                )
            )
    original = svc._recipient

    async def temporary(uid, project_id=None):
        if uid == OTHER:
            raise HTTPException(503, {"code": "mail_identity_unavailable"})
        return await original(uid, project_id)

    monkeypatch.setattr(svc, "_recipient", temporary)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=5), 100)
    assert len(await rows(state)) == 1
    async with state.factory() as session:
        assert (
            await session.scalar(select(EmailOperation.id).where(EmailOperation.notification_activity_id == 10)) is None
        )
    monkeypatch.setattr(svc, "_recipient", original)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 100)
    assert len(await rows(state)) == 2


async def test_explicit_test_mail_precedes_older_announcement_backlog(state):
    await announcement(state, send_email=True, email_operation_id=str(uuid4()))
    async with state.factory() as session, session.begin():
        await session.execute(update(EmailDelivery).values(available_at=NOW - timedelta(hours=1)))
    await svc.send_test(actor_id=ADMIN, operation_id=str(uuid4()), recipient_email="test@example.test")
    await svc.scheduler_tick(now=NOW, batch_size=1)
    assert len(state.sent) == 1 and str(state.sent[0]["To"]) == "test@example.test"


async def test_full_transient_page_does_not_starve_later_notification(state, monkeypatch):
    state.settings.notifications.resource_alerts_enabled = True
    for uid in (USER, OTHER):
        await svc.preferences(
            {"user_id": uid, "identity_domain_id": "home"}, values={"announcements": True, "resource_alerts": True}
        )
    await svc._collect_notifications(state.settings, NOW, 50)
    async with state.factory() as session, session.begin():
        for index in range(1, 52):
            session.add(
                ActivityLog(
                    id=index,
                    created_at=NOW + timedelta(seconds=1),
                    project_id="project",
                    user_id=USER if index <= 50 else OTHER,
                    username="user",
                    resource_type="instance",
                    resource_id="instance-id",
                    action="create",
                    status="failed",
                    source="afterglow",
                )
            )
    original = svc._recipient

    async def unavailable(uid, project_id=None):
        if uid == USER:
            raise HTTPException(503, {"code": "mail_identity_unavailable"})
        return await original(uid, project_id)

    monkeypatch.setattr(svc, "_recipient", unavailable)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=5), 50)
    await svc._collect_notifications(state.settings, NOW + timedelta(seconds=10), 50)
    delivered = await rows(state)
    assert [row.user_id for row in delivered] == [OTHER]
    body = svc._payload(delivered[0])["body"]
    assert "\n" in body and r"\n" not in body
