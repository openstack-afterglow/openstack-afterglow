"""Identity filtering/order boundaries against an isolated creation-event store."""

import asyncio
import json
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import fakeredis.aioredis
import pytest
from requests import Response
from sqlalchemy import Integer, MetaData, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.activity import ActivityLog
from app.services import activity, keystone, session_store


@pytest.fixture
async def creation_db(monkeypatch):
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


@pytest.fixture
async def group_authority(mock_conn, monkeypatch):
    """Supply native catalog/assignments; keep owner protection and Redis locking real."""
    roles = [
        {"id": name, "name": name, "domain_id": None, "description": ""}
        for name in ("member", "project_owner", "owner_bridge", "owner_alias")
    ]
    edges = [("owner_alias", "owner_bridge"), ("owner_bridge", "project_owner")]

    def graph(path):
        assert path == "/role_inferences"
        response = Response()
        response.status_code = 200
        response._content = json.dumps(
            {"role_inferences": [{"prior_role": {"id": prior}, "implies": [{"id": child}]} for prior, child in edges]}
        ).encode()
        return response

    assignments = []

    def group_assignments(*, group_id):
        return iter(row for row in assignments if row["group"]["id"] == group_id)

    mock_conn.endpoint_for.return_value = "https://keystone.invalid/v3"
    mock_conn.identity.roles.side_effect = lambda: iter(roles)
    mock_conn.identity.get.side_effect = graph
    mock_conn.identity.role_assignments.side_effect = group_assignments
    mock_conn.identity.group_users.side_effect = lambda group_id: iter([SimpleNamespace(id="group-member")])
    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def get_redis():
        return redis

    revoke_token = MagicMock()
    monkeypatch.setattr(session_store, "_get_redis", get_redis)
    monkeypatch.setattr(keystone, "revoke_token", revoke_token)
    try:
        yield SimpleNamespace(assignments=assignments, revoke_token=revoke_token)
    finally:
        await redis.close()


@pytest.fixture
def empty_project_resources(mock_conn):
    """Verified-empty cloud for identity-inventory deletes; blocking cases live in test_project_deletion."""

    def empty(*args, **kwargs):
        return iter(())

    for proxy, methods in (
        (mock_conn.compute, ("servers",)),
        (mock_conn.block_storage, ("volumes", "snapshots", "backups")),
        (mock_conn.network, ("networks", "subnets", "routers", "ports", "ips", "security_groups")),
        (mock_conn.image, ("images",)),
    ):
        for method in methods:
            getattr(proxy, method).side_effect = empty
    mock_conn.compute.get.return_value.json.return_value = {"server_groups": []}
    access = mock_conn.session.auth.get_access.return_value
    access.service_catalog.catalog = []
    access.role_names = ["admin"]
    access.is_admin_project = True


async def _group_sessions():
    for user_id in ("group-member", "unaffected-user"):
        await session_store.store_session(
            "session-" + user_id, "token-" + user_id, "project", user_id, int(time.time()) + 3600
        )


def resource(id, *, name=None, description="", domain="default", enabled=True, created_at=None):
    return SimpleNamespace(
        id=id,
        name=name or id,
        description=description,
        domain_id=domain,
        is_enabled=enabled,
        created_at=created_at,
    )


@pytest.mark.asyncio
async def test_projects_order_complete_inventory_before_pagination(admin_client, mock_conn):
    rows = [
        resource("a-old", created_at="2026-09-30T20:00:00Z"),
        resource("z-unknown"),
        resource("b-offset", created_at="2026-10-01T10:00:00+09:00"),
        resource("c-newer", created_at="2026-10-01T01:00:00.000001Z"),
        resource("d-invalid", created_at="not-a-date"),
    ]
    mock_conn.identity.projects.side_effect = lambda: iter(rows)
    first = await admin_client.get("/api/v1/admin/projects?limit=2")
    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == ["c-newer", "b-offset"]
    assert first.json()["total"] == 5
    second = await admin_client.get("/api/v1/admin/projects?limit=2&marker=b-offset")
    assert [item["id"] for item in second.json()["items"]] == ["a-old", "z-unknown"]
    assert second.json()["items"][-1]["created_at"] is None
    last = await admin_client.get("/api/v1/admin/projects?limit=2&marker=z-unknown")
    assert [item["id"] for item in last.json()["items"]] == ["d-invalid"]
    assert last.json()["next_marker"] is None
    assert last.json()["count"] == 1
    assert last.json()["items"][0]["created_at"] is None


@pytest.mark.asyncio
async def test_project_filters_apply_globally_and_compose_before_page_slice(admin_client, mock_conn):
    rows = [
        resource("early", name="CV production", domain="prod", created_at="2026-10-01T03:00:00Z"),
        resource("disabled", name="CV disabled", domain="research", enabled=False),
        resource("by-name", name="CV Lab", domain="research", created_at="2026-10-01T02:00:00Z"),
        resource("cv-by-id", name="Other Lab", domain="research", created_at="2026-10-01T01:00:00Z"),
        resource("by-description", name="Old Lab", description="Models for Cv", domain="research"),
    ]
    mock_conn.identity.projects.side_effect = lambda: iter(rows)
    query = {"search": "  cV  ", "enabled": "true", "domain_id": "research", "limit": 2}
    first = (await admin_client.get("/api/v1/admin/projects", params=query)).json()
    assert [item["id"] for item in first["items"]] == ["by-name", "cv-by-id"]
    assert first["total"] == 3
    assert first["domain_ids"] == ["prod", "research"]
    second = (await admin_client.get("/api/v1/admin/projects", params={**query, "marker": first["next_marker"]})).json()
    assert [item["id"] for item in second["items"]] == ["by-description"]
    assert second["next_marker"] is None
    missing = (await admin_client.get("/api/v1/admin/projects?search=does-not-exist")).json()
    assert missing["items"] == []
    assert missing["total"] == 0
    assert missing["next_marker"] is None
    assert (await admin_client.get("/api/v1/admin/projects?marker=deleted-project")).status_code == 400


@pytest.mark.asyncio
async def test_creation_dates_exclude_updates_failures_and_other_resource_types(creation_db):
    base = datetime(2026, 9, 1, tzinfo=UTC)
    async with creation_db() as session:
        for index, (kind, id, action, status) in enumerate(
            [
                ("project", "p", "project.update", "success"),
                ("project", "p", "project.create", "failed"),
                ("project", "p", "project_create", "started"),
                ("group", "p", "group.create", "success"),
                ("project", "p", "project_create", "success"),
                ("project", "p", "identity.project.created", "success"),
                ("project", "only-update", "project.update", "success"),
                ("project", "unrequested", "project.create", "success"),
            ]
        ):
            session.add(
                ActivityLog(
                    project_id="admin",
                    user_id="operator",
                    username="operator",
                    resource_type=kind,
                    resource_id=id,
                    action=action,
                    status=status,
                    created_at=base + timedelta(days=index),
                )
            )
        await session.commit()
    dates = await activity.get_resource_creation_times("project", ["p", "only-update"])
    assert dates == {"p": "2026-09-05T00:00:00+00:00"}


@pytest.mark.asyncio
async def test_groups_use_native_dates_then_creation_events_without_mutating_cached_inventory(
    admin_client, mock_conn, creation_db
):
    mock_conn.identity.groups.side_effect = lambda: iter(
        [
            resource("native", created_at="2026-10-01T00:00:00Z"),
            resource("recorded"),
            resource("unknown"),
        ]
    )
    async with creation_db() as session:
        session.add_all(
            [
                ActivityLog(
                    project_id="admin",
                    user_id="u",
                    username="u",
                    resource_type="group",
                    resource_id=id,
                    action="identity.group.created",
                    status="success",
                    created_at=date,
                )
                for id, date in [
                    ("native", datetime(2026, 8, 1, tzinfo=UTC)),
                    ("recorded", datetime(2026, 9, 1, tzinfo=UTC)),
                ]
            ]
        )
        await session.commit()
    for _ in range(2):
        response = await admin_client.get("/api/v1/admin/groups?cache=true")
        assert response.status_code == 200
        assert [item["id"] for item in response.json()] == ["native", "recorded", "unknown"]
        assert response.json()[1]["created_at"] == "2026-09-01T00:00:00.000000+00:00"
        assert response.json()[2]["created_at"] is None


@pytest.mark.parametrize("kind", ["project", "group"])
@pytest.mark.asyncio
async def test_creation_edit_and_delete_refresh_cached_inventory_preserving_creation_date(
    admin_client, mock_conn, creation_db, kind, group_authority, empty_project_resources
):
    rows = [resource("old", created_at="2000-01-01T00:00:00Z")]
    identity = mock_conn.identity
    getattr(identity, f"{kind}s").side_effect = lambda: iter(rows)
    if kind == "group":
        group_authority.assignments.append(
            {"group": {"id": "new"}, "role": {"id": "member"}, "scope": {"project": {"id": "project"}}}
        )
        await _group_sessions()

    def create(**kwargs):
        item = resource("new", name=kwargs["name"], description=kwargs.get("description", ""))
        rows.append(item)
        return item

    def update(id, **kwargs):
        item = next(item for item in rows if item.id == id)
        for key, value in kwargs.items():
            setattr(item, key, value)
        return item

    def delete(id, **kwargs):
        rows[:] = [item for item in rows if item.id != id]
        if kind == "group":
            group_authority.assignments[:] = [row for row in group_authority.assignments if row["group"]["id"] != id]

    getattr(identity, f"create_{kind}").side_effect = create
    getattr(identity, f"update_{kind}").side_effect = update
    getattr(identity, f"delete_{kind}").side_effect = delete
    url = f"/api/v1/admin/{kind}s"

    async def inventory():
        response = await admin_client.get(url + "?cache=true")
        assert response.status_code == 200
        return response.json()["items"] if kind == "project" else response.json()

    assert [item["id"] for item in await inventory()] == ["old"]
    assert (await admin_client.post(url, json={"name": "New Lab"})).status_code == 201
    created = await inventory()
    assert [item["id"] for item in created] == ["new", "old"]
    assert created[0]["created_at"] is not None
    assert (await admin_client.patch(url + "/new", json={"name": "Renamed Lab"})).status_code == 200
    edited = await inventory()
    assert edited[0]["name"] == "Renamed Lab"
    assert edited[0]["created_at"] == created[0]["created_at"]
    assert (await admin_client.delete(url + "/new")).status_code == 204
    assert [item["id"] for item in await inventory()] == ["old"]
    if kind == "group":
        identity.role_assignments.assert_called_once_with(group_id="new")
        identity.group_users.assert_called_once_with("new")
        identity.delete_group.assert_called_once_with("new", ignore_missing=False)
        assert group_authority.assignments == []
        assert await session_store.get_session("session-group-member") is None
        assert await session_store.get_session("session-unaffected-user") is not None
        group_authority.revoke_token.assert_called_once_with("token-group-member")
        async with creation_db() as session:
            events = (
                (await session.execute(select(ActivityLog).where(ActivityLog.action == "group_delete"))).scalars().all()
            )
        assert len(events) == 1
        assert events[0].status == "success"
        assert events[0].user_id == "test-user-123"


@pytest.mark.parametrize("mutation", ["create", "update", "delete"])
@pytest.mark.asyncio
async def test_project_mutation_detaches_overlapping_get_and_preserves_current_cache(
    admin_client, mock_conn, creation_db, mutation, empty_project_resources
):
    """Exercise CRUD invalidation, ordinary cache=true reads, and late stale completion."""
    rows = [
        resource("keep", name="Keep Lab", created_at="2000-01-01T00:00:00Z"),
        resource("target", name="Original Lab", created_at="2000-01-02T00:00:00Z"),
    ]
    before = {item.id: item.name for item in rows}
    started = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    calls = 0

    def projects():
        nonlocal calls
        calls += 1
        first = calls == 1
        # Copy resources so an update cannot accidentally alter the old snapshot.
        snapshot = [SimpleNamespace(**vars(item)) for item in rows]
        yield from snapshot
        if first:
            # Block after the endpoint has converted all old rows to dictionaries,
            # but before cached_call can store or return the old inventory.
            loop.call_soon_threadsafe(started.set)
            if not release.wait(5):
                raise TimeoutError("old project inventory was not released")

    def create(**kwargs):
        item = resource("created", name=kwargs["name"])
        rows.append(item)
        return item

    def update(id, **kwargs):
        item = next(item for item in rows if item.id == id)
        item.name = kwargs["name"]
        return item

    def delete(id, **kwargs):
        rows[:] = [item for item in rows if item.id != id]

    mock_conn.identity.projects.side_effect = projects
    mock_conn.identity.create_project.side_effect = create
    mock_conn.identity.update_project.side_effect = update
    mock_conn.identity.delete_project.side_effect = delete
    url = "/api/v1/admin/projects"

    async def inventory():
        response = await admin_client.get(url + "?cache=true")
        assert response.status_code == 200
        payload = response.json()
        assert payload["total"] == payload["count"] == len(payload["items"])
        return {item["id"]: item["name"] for item in payload["items"]}

    old = asyncio.create_task(inventory())
    try:
        await asyncio.wait_for(started.wait(), 2)
        if mutation == "create":
            response = await admin_client.post(url, json={"name": "Created Lab"})
            assert response.status_code == 201
            expected = {**before, "created": "Created Lab"}
        elif mutation == "update":
            response = await admin_client.patch(url + "/target", json={"name": "Renamed Lab"})
            assert response.status_code == 200
            expected = {**before, "target": "Renamed Lab"}
        else:
            response = await admin_client.delete(url + "/target")
            assert response.status_code == 204
            expected = {"keep": "Keep Lab"}

        # This is an ordinary cached GET, not refresh=true. It must complete
        # without joining the pre-mutation request that is still blocked.
        assert await asyncio.wait_for(inventory(), 2) == expected
        assert not old.done()
        release.set()
        assert await asyncio.wait_for(old, 2) == before
        # Late old completion must not resurrect a deleted row, undo a rename,
        # hide a created row, or evict the fresh flight's cached inventory.
        assert await inventory() == expected
        assert calls == 2
    finally:
        release.set()
        await asyncio.gather(old, return_exceptions=True)


@pytest.mark.asyncio
async def test_group_iterator_failure_is_not_reported_as_a_partial_success(admin_client, mock_conn):
    def broken_groups():
        yield resource("partial")
        raise RuntimeError("provider unavailable")

    mock_conn.identity.groups.side_effect = broken_groups
    response = await admin_client.get("/api/v1/admin/groups?cache=true")
    assert response.status_code == 500


@pytest.mark.asyncio
@pytest.mark.parametrize("role_id", ["project_owner", "owner_alias"])
@pytest.mark.parametrize("inherited", [False, True])
async def test_group_deletion_rejects_owner_grants_without_mutating_inventory_or_sessions(
    admin_client, mock_conn, creation_db, group_authority, role_id, inherited
):
    rows = [resource("protected", created_at="2026-09-01T00:00:00Z")]
    mock_conn.identity.groups.side_effect = lambda: iter(rows)
    scope = (
        {"domain": {"id": "default"}, "OS-INHERIT:inherited_to": "projects"}
        if inherited
        else {"project": {"id": "project"}}
    )
    assignment = {"group": {"id": "protected"}, "role": {"id": role_id}, "scope": scope}
    group_authority.assignments.append(assignment)
    await _group_sessions()
    before = await admin_client.get("/api/v1/admin/groups?cache=true")
    assert before.status_code == 200

    response = await admin_client.delete("/api/v1/admin/groups/protected")

    assert response.status_code == 409
    assert "ownership transition" in response.json()["detail"]
    mock_conn.identity.role_assignments.assert_called_once_with(group_id="protected")
    mock_conn.identity.delete_group.assert_not_called()
    mock_conn.identity.group_users.assert_not_called()
    assert group_authority.assignments == [assignment]
    after = await admin_client.get("/api/v1/admin/groups?cache=true")
    assert after.status_code == 200
    assert after.json() == before.json()
    mock_conn.identity.groups.assert_called_once()
    assert await session_store.get_session("session-group-member") is not None
    assert await session_store.get_session("session-unaffected-user") is not None
    group_authority.revoke_token.assert_not_called()
    async with creation_db() as session:
        events = (await session.execute(select(ActivityLog))).scalars().all()
    assert events == []


@pytest.mark.asyncio
async def test_group_deletion_fails_closed_when_assignment_scope_is_unavailable(
    admin_client, mock_conn, creation_db, group_authority
):
    mock_conn.identity.groups.side_effect = lambda: iter([resource("protected")])
    # A provider response for the wrong group is not evidence that this group is safe to delete.
    mock_conn.identity.role_assignments.side_effect = lambda **kwargs: iter(
        [{"group": {"id": "other-group"}, "role": {"id": "member"}, "scope": {"project": {"id": "project"}}}]
    )
    await _group_sessions()
    before = await admin_client.get("/api/v1/admin/groups?cache=true")
    assert before.status_code == 200

    response = await admin_client.delete("/api/v1/admin/groups/protected")

    assert response.status_code == 503
    mock_conn.identity.delete_group.assert_not_called()
    mock_conn.identity.group_users.assert_not_called()
    after = await admin_client.get("/api/v1/admin/groups?cache=true")
    assert after.status_code == 200
    assert after.json() == before.json()
    mock_conn.identity.groups.assert_called_once()
    assert await session_store.get_session("session-group-member") is not None
    group_authority.revoke_token.assert_not_called()
    async with creation_db() as session:
        events = (await session.execute(select(ActivityLog))).scalars().all()
    assert events == []
