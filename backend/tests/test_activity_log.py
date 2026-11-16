"""활동 로그 API 및 서비스 테스트."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from sqlalchemy import Integer, MetaData
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.models.activity import ActivityLog
from app.services import activity
from app.services.openstack_notifications import normalize_notification


@pytest.fixture
async def activity_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    table = ActivityLog.__table__.to_metadata(MetaData())
    table.c.id.type = Integer()
    async with engine.begin() as connection:
        await connection.run_sync(table.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(activity, "is_db_available", lambda: True)
    monkeypatch.setattr(activity, "get_session_factory", lambda: factory)
    try:
        yield factory
    finally:
        await engine.dispose()


async def seed_activity(factory, rows):
    async with factory() as session:
        for id_, values in enumerate(rows, start=1):
            session.add(
                ActivityLog(
                    **{
                        "id": id_,
                        "created_at": datetime(2026, 11, 16, tzinfo=UTC),
                        "project_id": "test-project-123",
                        "user_id": "test-user-123",
                        "username": "testuser",
                        "resource_type": "instance",
                        "resource_id": f"resource-{id_}",
                        "status": "success",
                        **values,
                    }
                )
            )
        await session.commit()


@pytest.mark.asyncio
async def test_profile_activity_filters_persisted_telemetry_and_reads(client, activity_db):
    mutations = [
        ("instance", "instance.create"),
        ("instance", "instance.delete"),
        ("instance", "instance.start"),
        ("instance", "instance.stop"),
        ("instance", "instance.resize"),
        ("instance", "instance.attach_volume"),
        ("instance", "instance.detach_interface"),
        ("instance", "instance.usage.extension.request"),
        ("volume", "volume.rename"),
        ("volume_snapshot", "volume.auto_snapshot_enable"),
        ("network", "create"),
        ("floating_ip", "disassociate"),
        ("security_group", "add_rule"),
        ("router", "remove_interface"),
        ("secret_container", "container.delete"),
        ("auth", "session_delete"),
        ("auth", "logout_all"),
        ("mcp_grant", "mcp_grant.create"),
        ("mcp_grant", "mcp_grant.revoke"),
        ("keypair", "keypair.create"),
        ("user", "password_reset_email"),
        ("project", "project_create"),
        ("instance", "admin.attach_admin_instance_volume"),
        ("instance", "bulk_reboot"),
        ("mcp_lumen_selection", "mcp_lumen_selection.set"),
    ]
    telemetry = [
        ("request", "request.read"),
        ("request", "request.stage"),
        ("request", "request.create"),
        ("instance", "instance.read"),
        ("instance", "instance.list"),
        ("instance", "instance.stage"),
        ("instance", "instance.inspect"),
        ("instance", "instance.update.stage"),
        ("ui", "ui.action"),
        ("ui", "ui.create"),
        ("experience", "view"),
        ("experience", "export"),
        ("auth", "login"),
        ("auth", "refresh"),
        ("auth", "auth.stage"),
        ("auth", "token_origin_mismatch"),
        ("mcp_grant", "mcp_grant.verify"),
        ("mcp_grant", "mcp_grant.expire"),
        ("hypervisor", "hypervisor.removal_check"),
        ("unknown", "create"),
        ("instance", "instance.create_preview"),
        ("instance", "instance.future_operation"),
    ]
    await seed_activity(
        activity_db,
        [{"resource_type": resource, "action": action} for resource, action in mutations + telemetry]
        + [
            {"action": "instance.create", "user_id": "another-user"},
            {"action": "instance.delete", "project_id": "other-project", "status": "failed"},
        ],
    )
    response = await client.get("/api/v1/profile/activity?limit=200")
    assert response.status_code == 200
    result = response.json()
    assert [(row["resource_type"], row["action"]) for row in result] == [
        ("instance", "instance.delete"),
        *reversed(mutations),
    ]
    assert result[0]["project_id"] == "other-project"
    assert result[0]["status"] == "failed"


@pytest.mark.asyncio
async def test_profile_activity_keeps_user_intents_and_legacy_mutations_not_native_echoes(client, activity_db):
    await seed_activity(
        activity_db,
        [
            {"action": "instance.create", "source": None},
            {"action": "instance.read", "source": None},
            {"resource_type": "request", "action": "request.stage", "source": None},
        ],
    )
    for resource, action in (
        ("instance", "instance.create"),
        ("instance", "instance.delete"),
        ("volume_backup", "volume_backup.create"),
        ("volume_backup", "volume.auto_backup_enable"),
        ("volume_backup", "volume.auto_backup_disable"),
        ("volume_snapshot", "volume.auto_snapshot_enable"),
    ):
        await activity.record(
            project_id="test-project-123",
            user_id="test-user-123",
            username="testuser",
            resource_type=resource,
            action=action,
            status="success",
        )

    # The collector attributes native echoes to context.user_id. That can be
    # the human for state transitions, or the managed account for a cron backup.
    notifications = [
        ("nova", "compute.instance.create.end", "test-user-123", {"instance_id": "vm-1"}),
        ("nova", "compute.instance.update", "test-user-123", {"instance_id": "vm-1"}),
        ("neutron", "port.update.end", "test-user-123", {"port_id": "port-1"}),
        ("cinder", "backup.create.end", "backup-system-user", {"backup_id": "backup-1"}),
    ]
    async with activity_db() as session:
        for service, event, user_id, payload in notifications:
            values = normalize_notification(
                json.dumps(
                    {
                        "event_type": event,
                        "payload": payload,
                        "context": {"user_id": user_id, "project_id": "test-project-123"},
                    }
                ).encode(),
                service,
            )
            session.add(ActivityLog(**values))
        await session.commit()

    response = await client.get("/api/v1/profile/activity?limit=200")
    assert response.status_code == 200
    assert [(row["source"], row["action"]) for row in response.json()] == [
        ("afterglow", "volume.auto_snapshot_enable"),
        ("afterglow", "volume.auto_backup_disable"),
        ("afterglow", "volume.auto_backup_enable"),
        ("afterglow", "volume_backup.create"),
        ("afterglow", "instance.delete"),
        ("afterglow", "instance.create"),
        ("afterglow", "instance.create"),  # NULL source is serialized as legacy Afterglow.
    ]


@pytest.mark.asyncio
async def test_account_intent_feed_classifies_real_middleware_route_operations(client, activity_db):
    import httpx

    from app.main import activity_audit_middleware, app

    application = FastAPI()
    application.middleware("http")(activity_audit_middleware)

    async def native_mutation_boundary(request: Request):
        request.state.token_info = {
            "project_id": "test-project-123",
            "user_id": "test-user-123",
            "username": "testuser",
        }
        return JSONResponse({"ok": True})

    # Reuse current registered route templates; run the production middleware
    # and persistence, replacing only native resource handlers.
    routes = [
        ("PUT", "/api/v1/iam/projects/{project_id}/members/{user_id}/roles"),
        ("PUT", "/api/v1/instances/{instance_id}/name"),
        ("POST", "/api/v1/instances/{instance_id}/confirm-resize"),
        ("POST", "/api/v1/instances/github-users/lookup"),
        ("POST", "/api/v1/instances/{instance_id}/storage-attachments/{file_storage_id}/connection-info"),
        ("POST", "/api/v1/admin/hypervisors/{hypervisor_id}/removal-check"),
    ]
    for method, template in routes:
        registered = next(route for route in app.routes if getattr(route, "path", None) == template)
        assert method in registered.methods
        application.add_api_route(registered.path, native_mutation_boundary, methods=[method])

    # Chat endpoints share the middleware's resource-prefix map. Conversation
    # and run churn is not cloud resource history, but credential changes are.
    for method, template in (
        ("POST", "/api/v1/chat/conversations"),
        ("DELETE", "/api/v1/chat/conversations/{conversation_id}"),
        ("POST", "/api/v1/chat/runs"),
        ("POST", "/api/v1/chat/api-keys"),
        ("DELETE", "/api/v1/chat/git-credentials/{credential_id}"),
    ):
        application.add_api_route(template, native_mutation_boundary, methods=[method])

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://activity.test"
    ) as producer:
        for method, path in (
            ("PUT", "/api/v1/iam/projects/project-a/members/user-a/roles"),
            ("PUT", "/api/v1/instances/vm-a/name"),
            ("POST", "/api/v1/instances/vm-a/confirm-resize"),
            ("POST", "/api/v1/instances/github-users/lookup"),
            ("POST", "/api/v1/instances/vm-a/storage-attachments/share-a/connection-info"),
            ("POST", "/api/v1/admin/hypervisors/host-a/removal-check"),
            ("POST", "/api/v1/chat/conversations"),
            ("DELETE", "/api/v1/chat/conversations/conversation-a"),
            ("POST", "/api/v1/chat/runs"),
            ("POST", "/api/v1/chat/api-keys"),
            ("DELETE", "/api/v1/chat/git-credentials/credential-a"),
        ):
            assert (await producer.request(method, path)).status_code == 200

    response = await client.get("/api/v1/profile/activity?limit=200")
    assert response.status_code == 200
    assert [(row["resource_type"], row["action"]) for row in response.json()] == [
        ("chat_git_credential", "chat_git_credential.delete"),
        ("chat_api_key", "chat_api_key.create"),
        ("instance", "instance.confirm-resize"),
        ("instance", "instance.name"),
        ("project", "project.roles"),
    ]


@pytest.mark.asyncio
async def test_profile_activity_cursor_pages_over_filtered_rows(client, activity_db):
    await seed_activity(
        activity_db,
        [
            {"action": "instance.create"},
            {"resource_type": "request", "action": "request.read"},
            {"action": "instance.delete"},
            {"action": "instance.stage"},
            {"action": "instance.stop", "status": "failed"},
            {"resource_type": "request", "action": "request.stage"},
            {"action": "instance.start", "status": "started"},
            {"resource_type": "request", "action": "request.read"},
        ],
    )
    first = await client.get("/api/v1/profile/activity?limit=3")
    assert first.status_code == 200
    assert [row["id"] for row in first.json()] == [7, 5, 3]
    second = await client.get("/api/v1/profile/activity?limit=3&before_id=3")
    assert second.status_code == 200
    assert [row["id"] for row in second.json()] == [1]
    assert (await client.get("/api/v1/profile/activity?limit=3&before_id=1")).json() == []
    resource = await client.get("/api/v1/profile/activity?resource_type=instance&limit=2")
    assert [row["id"] for row in resource.json()] == [7, 5]
    action = await client.get("/api/v1/profile/activity?action=instance.create")
    assert [row["id"] for row in action.json()] == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    ["resource_type=request", "action=request.read", "action=instance.read", "action=instance.stage"],
)
async def test_profile_activity_explicit_filters_cannot_restore_telemetry(client, activity_db, query):
    await seed_activity(
        activity_db,
        [
            {"resource_type": "request", "action": "request.read"},
            {"action": "instance.read"},
            {"action": "instance.stage"},
            {"action": "instance.create"},
        ],
    )
    response = await client.get(f"/api/v1/profile/activity?{query}")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_admin_activity_retains_persisted_reads_and_request_telemetry(admin_client, activity_db):
    rows = [
        {"action": "compute.instance.create.end", "source": "openstack", "username": ""},
        {"resource_type": "request", "action": "request.read"},
        {"resource_type": "request", "action": "request.stage"},
        {"action": "instance.read", "user_id": "another-user"},
        {"resource_type": "ui", "action": "ui.action"},
    ]
    await seed_activity(activity_db, rows)
    url = "/api/v1/admin/projects/test-project-123/activity"
    response = await admin_client.get(url + "?limit=3")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [5, 4, 3]
    page = await admin_client.get(url + "?limit=3&before_id=3")
    assert [row["id"] for row in page.json()] == [2, 1]
    filtered = await admin_client.get(url + "?resource_type=request&action=request.read")
    assert [row["id"] for row in filtered.json()] == [2]
    events = await admin_client.get("/api/v1/admin/events")
    assert events.status_code == 200
    assert [row["id"] for row in events.json()] == [5, 4, 3, 2, 1]
    stats = await admin_client.get("/api/v1/admin/events/stats")
    assert stats.status_code == 200
    assert stats.json()["total"] == len(rows)


@pytest.mark.asyncio
async def test_profile_activity_returns_list(client):
    """일반 사용자 본인 활동 조회 — 200 + 빈 리스트."""
    with patch(
        "app.api.identity.profile_activity.svc.list_for_user",
        new=AsyncMock(return_value=[]),
    ):
        r = await client.get("/api/v1/profile/activity")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_profile_activity_with_results(client):
    """결과가 있을 때 목록 반환."""
    fake_row = {
        "id": 1,
        "created_at": "2025-01-01T00:00:00+00:00",
        "project_id": "p1",
        "user_id": "u1",
        "username": "user1",
        "resource_type": "instance",
        "resource_id": "inst-1",
        "resource_name": "web-server",
        "action": "instance.create",
        "status": "success",
        "error_message": None,
        "extra": None,
    }
    with patch(
        "app.api.identity.profile_activity.svc.list_for_user",
        new=AsyncMock(return_value=[fake_row]),
    ):
        r = await client.get("/api/v1/profile/activity")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["action"] == "instance.create"
    assert data[0]["status"] == "success"


@pytest.mark.asyncio
async def test_admin_activity_requires_admin(client):
    """일반 사용자는 admin activity API 에 접근 불가."""
    r = await client.get("/api/v1/admin/projects/p1/activity")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_admin_activity_ok_for_admin(admin_client):
    """admin 사용자는 프로젝트 활동 조회 가능."""
    with patch(
        "app.api.identity.admin_activity.svc.list_for_project",
        new=AsyncMock(return_value=[]),
    ):
        r = await admin_client.get("/api/v1/admin/projects/p1/activity")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_admin_activity_query_params(admin_client):
    """query 파라미터가 서비스 함수에 전달된다."""
    mock_fn = AsyncMock(return_value=[])
    with patch("app.api.identity.admin_activity.svc.list_for_project", new=mock_fn):
        await admin_client.get(
            "/api/v1/admin/projects/my-project/activity?limit=10&resource_type=volume&action=volume.create&user_id=u1"
        )
    mock_fn.assert_called_once_with(
        "my-project",
        limit=10,
        before_id=None,
        resource_type="volume",
        action="volume.create",
        user_id="u1",
    )


@pytest.mark.asyncio
async def test_record_skipped_when_db_unavailable():
    """DB 미가용 시 record 가 예외 없이 skip."""
    from app.services import activity as svc

    with patch("app.services.activity.is_db_available", return_value=False):
        await svc.record(
            project_id="p",
            user_id="u",
            username="x",
            resource_type="instance",
            action="instance.create",
            status="success",
        )


@pytest.mark.asyncio
async def test_record_skipped_when_factory_none():
    """session_factory 가 None 이어도 예외 없이 skip."""
    from app.services import activity as svc

    with (
        patch("app.services.activity.is_db_available", return_value=True),
        patch("app.services.activity.get_session_factory", return_value=None),
    ):
        await svc.record(
            project_id="p",
            user_id="u",
            username="x",
            resource_type="instance",
            action="instance.create",
            status="success",
        )


@pytest.mark.asyncio
async def test_record_writes_row_when_db_available():
    """DB 가용 시 ActivityLog row 를 session.add 한다."""
    from app.services import activity as svc

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    mock_factory = MagicMock(return_value=mock_session)

    with (
        patch("app.services.activity.is_db_available", return_value=True),
        patch("app.services.activity.get_session_factory", return_value=mock_factory),
    ):
        await svc.record(
            project_id="p",
            user_id="u",
            username="testuser",
            resource_type="volume",
            action="volume.create",
            status="success",
            resource_id="vol-123",
            resource_name="my-volume",
        )

    mock_session.add.assert_called_once()
    added = mock_session.add.call_args[0][0]
    assert added.resource_type == "volume"
    assert added.action == "volume.create"
    assert added.status == "success"
    assert added.resource_name == "my-volume"
