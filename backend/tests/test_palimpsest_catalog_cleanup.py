"""Real SQL/journal catalog cleanup through ordinary and admin delete hooks."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi import HTTPException
from openstack.exceptions import ResourceNotFound

from app.models.db import LayerConsume
from app.services import palimpsest_catalog_cleanup as cleanup
from tests.test_palimpsest_catalog import DIGEST, OTHER, PROJECT, USER
from tests.test_palimpsest_catalog import catalog_client as catalog_client
from tests.test_palimpsest_catalog import catalog_db as catalog_db


@pytest.fixture
async def cleanup_state(catalog_db, monkeypatch):
    from app.services import cache, keystone, manila, palimpsest_catalog_consume

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(palimpsest_catalog_consume, "current_writer", AsyncMock())
    monkeypatch.setattr("app.api.deps.require_admin", AsyncMock(side_effect=lambda info: info))
    state = SimpleNamespace(
        deletes=[],
        denied=[],
        port_exists=True,
        server_exists=True,
        deny_pending=False,
        unknown_server=False,
        rule={
            "id": "exact-rule",
            "share_id": "exact-share",
            "access_type": "ip",
            "access_level": "ro",
            "access_to": "10.0.0.9",
        },
    )
    async with catalog_db() as session:
        row = LayerConsume(
            profile_name="old-unpublished-profile",
            project_id=PROJECT,
            server_id="exact-server",
            port_id="exact-port",
            server_name="exact-name",
            share_id="",
            artifact_ids=[123],
            transport="nfs",
            status="active",
            resource_snapshot={
                "catalog_revision": DIGEST,
                "consumer_project": {"id": PROJECT},
                "openstack.service_project": {"id": OTHER},
                "catalog_artifact_sources": [{"id": 123, "share_id": "exact-share", "blob_digest": DIGEST}],
            },
        )
        session.add(row)
        await session.commit()
        state.consume_id = row.id
    state.marker = {
        "afterglow_catalog_consume_id": str(row.id),
        "afterglow_consume_id": str(row.id),
        "afterglow_consume_token": "exact-token",
        "afterglow_owner_project_id": PROJECT,
    }
    state.server = SimpleNamespace(
        id="exact-server",
        name="exact-name",
        project_id=PROJECT,
        metadata=state.marker,
        union_upper_volume_id=None,
        union_share_ids=[],
        union_strategy=None,
    )

    def server_get(identity):
        assert identity == "exact-server"
        if not state.server_exists:
            raise ResourceNotFound("absent")
        return state.server

    def server_delete(identity, **kwargs):
        state.deletes.append(("server", identity))
        if state.unknown_server:
            raise TimeoutError("acceptance unknown")
        state.server_exists = False

    def port_get(identity):
        assert identity == "exact-port"
        if not state.port_exists:
            raise ResourceNotFound("absent")
        return SimpleNamespace(
            id=identity,
            name="afterglow-layer-consume-exact-token",
            project_id=PROJECT,
            device_id="exact-server" if state.server_exists else "",
            fixed_ips=[{"ip_address": "10.0.0.9"}],
            description=json.dumps(state.marker),
        )

    def port_delete(identity, **kwargs):
        state.deletes.append(("port", identity))
        state.port_exists = False

    state.conn = SimpleNamespace(
        compute=SimpleNamespace(get_server=server_get, delete_server=server_delete),
        network=SimpleNamespace(get_port=port_get, delete_port=port_delete, ips=lambda **kwargs: []),
    )
    state.share = SimpleNamespace(session=SimpleNamespace(get_project_id=lambda: OTHER), close=lambda: None)
    monkeypatch.setattr(
        keystone,
        "get_admin_connection_for_project",
        lambda identity: state.share if identity == OTHER else pytest.fail("wrong service owner"),
    )
    monkeypatch.setattr(manila, "get_file_storage", lambda conn, identity: SimpleNamespace(project_id=OTHER))
    monkeypatch.setattr(manila, "get_access_rule", lambda conn, share, rule: state.rule)

    def deny(conn, share, rule):
        assert conn is state.share and share == "exact-share" and rule == "exact-rule"
        state.denied.append((share, rule))
        if not state.deny_pending:
            state.rule = None

    monkeypatch.setattr(manila, "revoke_access_rule", deny)
    await redis.set(
        f"afterglow:builds:journal:consume:{row.id}",
        json.dumps(
            {
                "consumer": {"id": row.id, "token": "exact-token", "fixed_ip": "10.0.0.9"},
                "observed_ids": {f"consumer:{row.id}:rule:exact-share": "exact-rule"},
            }
        ),
    )
    await redis.set(
        f"afterglow:builds:journal:consume:{row.id}:submit:consumer:{row.id}:rule:exact-share",
        json.dumps({"state": "accepted", "result": {"id": "exact-rule"}}),
    )
    await redis.set(
        f"afterglow:builds:journal:consume:{row.id}:submit:consumer:{row.id}:port",
        json.dumps({"state": "accepted", "result": {"id": "exact-port"}}),
    )
    await redis.set(
        f"afterglow:builds:journal:consume:{row.id}:submit:consumer:{row.id}:server",
        json.dumps({"state": "accepted", "result": {"id": "exact-server"}}),
    )
    state.info = {"project_id": PROJECT, "user_id": USER, "token": "native", "is_system_admin": False}
    state.redis = redis
    yield state
    await redis.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_normal_and_admin_shared_hook_revoke_exact_service_rule_before_server_delete(
    cleanup_state, catalog_db, admin
):
    from app.api.compute.instances import _revoke_instance_storage_grants

    state = cleanup_state
    info = {**state.info, "is_system_admin": admin}
    if admin:
        info["project_id"] = OTHER  # Actor workspace is not target ownership.
    await _revoke_instance_storage_grants(state.conn, "exact-server", state.server, info)
    assert state.denied == [("exact-share", "exact-rule")] and state.deletes == []
    assert await cleanup.submit_instance_delete(state.conn, "exact-server", state.server, info)
    await cleanup.finish_instance_delete(state.conn, "exact-server", state.server, info)
    assert state.deletes == [("server", "exact-server"), ("port", "exact-port")]
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        assert row.status == "deleted" and row.resources["catalog_cleanup_complete"]


@pytest.mark.asyncio
async def test_changed_exact_rule_or_wrong_owner_never_revokes(cleanup_state):
    state = cleanup_state
    with pytest.raises(HTTPException) as owner:
        await cleanup.revoke_before_instance_delete(
            state.conn, "exact-server", state.server, {**state.info, "project_id": OTHER}
        )
    assert owner.value.status_code == 404 and state.denied == []
    state.rule["access_to"] = "10.0.0.10"
    with pytest.raises(HTTPException) as changed:
        await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert changed.value.status_code == 409 and state.denied == [] and state.deletes == []


@pytest.mark.asyncio
async def test_unknown_delete_requires_new_exact_observation_before_explicit_retry(cleanup_state, catalog_db):
    from app.api.union.layer_ops import _is_blocking_consume

    state = cleanup_state
    await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    state.unknown_server = True
    with pytest.raises(HTTPException):
        await cleanup.submit_instance_delete(state.conn, "exact-server", state.server, state.info)
    await cleanup._delete_once(
        state.redis,
        f"afterglow:catalog-cleanup:{state.consume_id}:server:exact-server",
        state.conn.compute.delete_server,
        "exact-server",
        ignore_missing=False,
    )
    assert state.deletes == [("server", "exact-server")]  # No automatic/unobserved replay.
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        assert row.status == "indeterminate" and _is_blocking_consume(row)
    state.unknown_server = False
    assert await cleanup.submit_instance_delete(state.conn, "exact-server", state.server, state.info)
    await cleanup.finish_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert state.deletes == [("server", "exact-server"), ("server", "exact-server"), ("port", "exact-port")]


@pytest.mark.asyncio
async def test_live_provisioning_lease_prevents_any_cleanup(cleanup_state):
    state = cleanup_state
    await state.redis.set(
        f"afterglow:catalog-consume:{state.consume_id}:lease:consume:{state.consume_id}", "live-owner"
    )
    with pytest.raises(HTTPException) as live:
        await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert live.value.status_code == 409 and state.denied == [] and state.deletes == []


@pytest.mark.asyncio
async def test_ordinary_bulk_delete_actually_invokes_catalog_lifecycle(cleanup_state, monkeypatch):
    from app.api.compute import instances
    from app.services import layer_consume_resources

    state = cleanup_state
    monkeypatch.setattr(layer_consume_resources, "lookup_for_server", AsyncMock(return_value=[]))
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    monkeypatch.setattr(
        instances.nova, "delete_server", lambda *a: pytest.fail("catalog deletes use their nonreplayable receipt")
    )
    monkeypatch.setattr(instances.neutron, "cleanup_floating_ips", lambda *a, **k: None, raising=False)
    await instances._bulk_delete_one(state.conn, state.info, state.server, "exact-server", PROJECT)
    assert state.denied == [("exact-share", "exact-rule")]
    assert state.deletes == [("server", "exact-server"), ("port", "exact-port")]


@pytest.mark.asyncio
async def test_explicit_deny_retry_requires_fresh_exact_rule_observation(cleanup_state, catalog_db, monkeypatch):
    state = cleanup_state
    state.deny_pending = True

    monkeypatch.setattr(cleanup.asyncio, "sleep", AsyncMock())
    for _ in range(2):
        with pytest.raises(HTTPException):
            await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert state.denied == [("exact-share", "exact-rule"), ("exact-share", "exact-rule")] and state.deletes == []
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        assert row.status == "active" and not (row.resources or {}).get("catalog_cleanup_complete")


@pytest.mark.asyncio
async def test_ordinary_single_delete_calls_same_revoke_submit_and_finish(cleanup_state, monkeypatch):
    from fastapi import Request

    from app.api.compute import instances
    from app.services import layer_consume_resources

    state = cleanup_state
    state.conn._afterglow_project_id = PROJECT
    monkeypatch.setattr(layer_consume_resources, "lookup_for_server", AsyncMock(return_value=[]))
    monkeypatch.setattr(instances, "assert_instance_owner", lambda *a: None)
    monkeypatch.setattr(instances.nova, "get_server", lambda *a: state.server)
    monkeypatch.setattr(
        instances.nova, "delete_server", lambda *a: pytest.fail("journaled catalog server delete required")
    )
    monkeypatch.setattr(instances, "invalidate", AsyncMock())
    monkeypatch.setattr(instances.cache_invalidation, "invalidate_mutation_count", AsyncMock())
    monkeypatch.setattr(instances, "rec", AsyncMock())
    request = Request({"type": "http", "method": "DELETE", "path": "/instances/exact-server", "headers": []})
    await instances.delete_instance(request, "exact-server", state.conn, state.info)
    assert state.denied == [("exact-share", "exact-rule")]
    assert state.deletes == [("server", "exact-server"), ("port", "exact-port")]


@pytest.mark.asyncio
async def test_interrupted_create_binds_exact_native_server_before_cleanup(cleanup_state, catalog_db):
    state = cleanup_state
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        row.server_id = None
        await session.commit()
    await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    async with catalog_db() as session:
        assert (await session.get(LayerConsume, state.consume_id)).server_id == "exact-server"
    assert state.denied == [("exact-share", "exact-rule")]


@pytest.mark.asyncio
async def test_serverless_interruption_reclaims_exact_grant_and_port(cleanup_state, catalog_db):
    state = cleanup_state
    state.server_exists = False
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        row.server_id = None
        row.status = "indeterminate"
        await session.commit()
    await state.redis.delete(
        f"afterglow:builds:journal:consume:{state.consume_id}:submit:consumer:{state.consume_id}:server"
    )
    result = await cleanup.cleanup_consume(state.conn, state.consume_id, state.info)
    assert result["status"] == "deleted"
    assert state.denied == [("exact-share", "exact-rule")] and state.deletes == [("port", "exact-port")]


@pytest.mark.asyncio
async def test_unknown_create_authoritative_empty_observation_allows_safe_reclaim(cleanup_state, catalog_db):
    state = cleanup_state
    async with catalog_db() as session:
        row = await session.get(LayerConsume, state.consume_id)
        row.server_id = None
        await session.commit()
    await state.redis.set(
        f"afterglow:builds:journal:consume:{state.consume_id}:submit:consumer:{state.consume_id}:server",
        json.dumps({"state": "unknown"}),
    )
    state.conn.compute.servers = lambda **kwargs: []
    state.server_exists = False
    result = await cleanup.cleanup_consume(state.conn, state.consume_id, state.info)
    assert result["status"] == "deleted"
    assert state.denied == [("exact-share", "exact-rule")] and state.deletes == [("port", "exact-port")]


@pytest.mark.asyncio
async def test_external_deletion_without_dashboard_receipt_revokes_recorded_grants(cleanup_state):
    state = cleanup_state
    state.server_exists = False
    assert await cleanup.recover_missing_instance(state.conn, "exact-server", state.info)
    assert state.denied == [("exact-share", "exact-rule")] and state.deletes == [("port", "exact-port")]


@pytest.mark.asyncio
async def test_changed_current_port_ip_does_not_strand_exact_old_rule(cleanup_state):
    state = cleanup_state
    original = state.conn.network.get_port

    def changed(identity):
        port = original(identity)
        port.fixed_ips = [{"ip_address": "10.0.0.10"}]
        return port

    state.conn.network.get_port = changed
    await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert state.denied == [("exact-share", "exact-rule")]


@pytest.mark.asyncio
async def test_definite_rejected_delete_can_retry_but_unknown_never_replays(cleanup_state):
    state = cleanup_state
    calls = []

    class Rejected(Exception):
        status_code = 409

    def reject():
        calls.append("rejected")
        raise Rejected()

    with pytest.raises(HTTPException):
        await cleanup._delete_once(state.redis, "rejected-key", reject)
    await cleanup._delete_once(state.redis, "rejected-key", lambda: calls.append("accepted"))
    await cleanup._delete_once(state.redis, "rejected-key", lambda: calls.append("must-not-replay"))
    assert calls == ["rejected", "accepted"]


@pytest.mark.asyncio
async def test_catalog_floating_ip_is_deleted_before_its_port_is_released(cleanup_state):
    state = cleanup_state
    addresses = {"floating": SimpleNamespace(id="floating", project_id=PROJECT, port_id="exact-port")}
    state.conn.network.ips = lambda **kwargs: list(addresses.values())

    def delete(identity, **kwargs):
        assert state.port_exists
        state.deletes.append(("floating-ip", identity))
        addresses.pop(identity)

    state.conn.network.delete_ip = delete
    state.conn.network.get_ip = lambda identity: addresses.get(identity)
    await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert state.deletes == [("floating-ip", "floating")]


@pytest.mark.asyncio
async def test_assignment_is_republished_before_original_hash_expiry(monkeypatch):
    import asyncio

    from app.services import palimpsest_catalog_consume as consumer
    from app.services.work_dispatcher import WorkDispatcher, work_lease

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(consumer, "_ASSIGNMENT_REFRESH_SECONDS", 0.01)
    async with WorkDispatcher(redis, "catalog-renew-regression") as dispatcher:
        await dispatcher.publish(["consume:1"])
        claim = await dispatcher.claim(90)
        async with work_lease(dispatcher, *claim) as lease:
            await redis.expire(dispatcher._assignments_key, 1)
            renewal = asyncio.create_task(consumer._keep_assignment(dispatcher, "consume:1"))
            try:
                await asyncio.sleep(1.1)
                await lease.check()
                assert await redis.ttl(dispatcher._assignments_key) > 1
            finally:
                renewal.cancel()
                await asyncio.gather(renewal, return_exceptions=True)
    await redis.close()


@pytest.mark.asyncio
async def test_operation_card_cleanup_endpoint_reclaims_failed_admission(catalog_client, cleanup_state, monkeypatch):
    from app.api import deps
    from tests.test_palimpsest_catalog import BASE

    state = cleanup_state

    async def scope(request, info):
        yield state.conn

    monkeypatch.setattr(deps, "get_os_conn", scope)
    client, _, _ = catalog_client
    response = await client.delete(BASE + f"/environments/consumes/{state.consume_id}")
    assert response.status_code == 200 and response.json()["status"] == "deleted"
    assert state.denied == [("exact-share", "exact-rule")]
    assert state.deletes == [("server", "exact-server"), ("port", "exact-port")]


@pytest.mark.asyncio
async def test_mcp_catalog_delete_uses_same_exact_cleanup_without_browser_credential(cleanup_state, monkeypatch):
    from app.services import project_service
    from app.services.mcp_control_plane import compute

    state = cleanup_state
    state.server.status = "ACTIVE"
    state.conn._afterglow_user_id = USER
    state.conn.session = SimpleNamespace(
        auth=SimpleNamespace(
            get_access=lambda session: SimpleNamespace(user_id=USER, project_id=PROJECT, role_names=["member"])
        )
    )
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(return_value={"roles": ["member"]}))
    response = await compute.request_project_server_delete(state.conn, project_id=PROJECT, server_id="exact-server")
    assert response["requested_action"] == "delete"
    assert state.denied == [("exact-share", "exact-rule")]
    assert state.deletes == [("server", "exact-server"), ("port", "exact-port")]


@pytest.mark.asyncio
@pytest.mark.parametrize("rule_present", [False, True])
async def test_unknown_grant_is_observed_only_under_original_owned_ip(cleanup_state, monkeypatch, rule_present):
    from app.services import manila

    state = cleanup_state
    key = f"afterglow:builds:journal:consume:{state.consume_id}"
    journal = json.loads(await state.redis.get(key))
    journal["observed_ids"] = {}
    await state.redis.set(key, json.dumps(journal))
    await state.redis.set(
        f"{key}:submit:consumer:{state.consume_id}:rule:exact-share", json.dumps({"state": "unknown"})
    )
    if not rule_present:
        state.rule = None
    monkeypatch.setattr(manila, "list_access_rules", lambda *args, **kwargs: [state.rule] if state.rule else [])
    await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert state.denied == ([("exact-share", "exact-rule")] if rule_present else [])


@pytest.mark.asyncio
async def test_unknown_grant_cannot_be_adopted_after_original_ip_leaves_port(cleanup_state, monkeypatch):
    from app.services import manila

    state = cleanup_state
    key = f"afterglow:builds:journal:consume:{state.consume_id}"
    journal = json.loads(await state.redis.get(key))
    journal["observed_ids"] = {}
    await state.redis.set(key, json.dumps(journal))
    await state.redis.set(
        f"{key}:submit:consumer:{state.consume_id}:rule:exact-share", json.dumps({"state": "unknown"})
    )
    get_port = state.conn.network.get_port

    def changed(identity):
        port = get_port(identity)
        port.fixed_ips = [{"ip_address": "10.0.0.10"}]
        return port

    state.conn.network.get_port = changed
    monkeypatch.setattr(
        manila,
        "list_access_rules",
        lambda *args, **kwargs: pytest.fail("No IP-only adoption without original owned IP"),
    )
    with pytest.raises(HTTPException) as blocked:
        await cleanup.revoke_before_instance_delete(state.conn, "exact-server", state.server, state.info)
    assert blocked.value.status_code == 409 and state.denied == [] and state.deletes == []


@pytest.mark.asyncio
async def test_mcp_preserves_explicit_catalog_cleanup_uncertainty(cleanup_state, monkeypatch):
    from app.services.mcp_control_plane import compute

    state = cleanup_state
    state.server.status = "ACTIVE"
    state.conn._afterglow_user_id = USER
    state.conn.session = SimpleNamespace(
        auth=SimpleNamespace(
            get_access=lambda session: SimpleNamespace(user_id=USER, project_id=PROJECT, role_names=["member"])
        )
    )
    monkeypatch.setattr(
        "app.services.project_service.get_project_access", AsyncMock(return_value={"roles": ["member"]})
    )

    async def uncertain(*args, **kwargs):
        raise HTTPException(409, "Catalog cleanup acceptance is unknown; observe before retrying")

    monkeypatch.setattr(cleanup, "cleanup_consume", uncertain)
    with pytest.raises(compute.McpComputeError, match="acceptance is unknown"):
        await compute.request_project_server_delete(state.conn, project_id=PROJECT, server_id="exact-server")


@pytest.mark.asyncio
@pytest.mark.parametrize("body_failure", [False, True])
async def test_cleanup_commit_failure_preserves_explicit_unknown_outcome(monkeypatch, body_failure):
    session = AsyncMock()
    session.__aenter__.return_value = session
    session.commit.side_effect = RuntimeError("synthetic SQL unavailable")
    monkeypatch.setattr(cleanup.catalog, "factory", lambda: lambda: session)
    with pytest.raises(HTTPException) as failure:
        async with cleanup._cleanup_session():
            if body_failure:
                raise HTTPException(409, "Catalog deletion acceptance is unknown")
    assert failure.value.status_code == (409 if body_failure else 503)
    if body_failure:
        assert failure.value.detail == "Catalog deletion acceptance is unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("admin", [False, True])
async def test_removed_native_marker_cannot_bypass_known_sql_catalog_delete(
    cleanup_state, catalog_db, monkeypatch, admin
):
    from app.api.compute import instances
    from app.services import layer_consume_resources

    state = cleanup_state
    state.server.metadata = {}
    info = {**state.info, "is_system_admin": admin}
    if admin:
        info["project_id"] = OTHER
    monkeypatch.setattr(layer_consume_resources, "lookup_for_server", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        instances.nova, "delete_server", lambda *args: pytest.fail("No ordinary fallback for a known catalog row")
    )
    with pytest.raises(HTTPException) as blocked:
        await instances._bulk_delete_one(state.conn, info, state.server, "exact-server", PROJECT)
    assert blocked.value.status_code == 409 and state.denied == [] and state.deletes == []
    async with catalog_db() as session:
        assert (await session.get(LayerConsume, state.consume_id)).status == "active"


@pytest.mark.asyncio
async def test_catalog_lookup_foreign_owner_is_indistinguishable_from_missing_instance(cleanup_state):
    state = cleanup_state
    failures = []
    for identity in ("exact-server", "missing-server"):
        with pytest.raises(HTTPException) as hidden:
            await cleanup.lookup_catalog_consume(identity, state.server, {**state.info, "project_id": OTHER})
        failures.append((hidden.value.status_code, hidden.value.detail))
    assert failures == [(404, "Instance not found"), (404, "Instance not found")]


@pytest.mark.asyncio
async def test_mcp_removed_marker_cannot_fall_back_to_ordinary_delete(cleanup_state, monkeypatch):
    from app.services.mcp_control_plane import compute

    state = cleanup_state
    state.server.status = "ACTIVE"
    state.server.metadata = {}
    state.conn._afterglow_user_id = USER
    state.conn.session = SimpleNamespace(
        auth=SimpleNamespace(
            get_access=lambda session: SimpleNamespace(user_id=USER, project_id=PROJECT, role_names=["member"])
        )
    )
    monkeypatch.setattr(
        "app.services.project_service.get_project_access", AsyncMock(return_value={"roles": ["member"]})
    )
    observed = []
    get_server = state.conn.compute.get_server

    def snapshot(identity):
        observed.append(identity)
        return get_server(identity)

    state.conn.compute.get_server = snapshot
    with pytest.raises(compute.McpComputeError, match="marker differs"):
        await compute.request_project_server_delete(state.conn, project_id=PROJECT, server_id="exact-server")
    assert observed == ["exact-server"] and state.denied == [] and state.deletes == []


@pytest.mark.asyncio
async def test_removed_marker_never_falls_back_when_sql_authority_is_unavailable(cleanup_state, monkeypatch):
    state = cleanup_state
    state.server.metadata = {}
    monkeypatch.setattr(cleanup.catalog, "get_session_factory", lambda: None)
    with pytest.raises(HTTPException) as unavailable:
        await cleanup.lookup_catalog_consume("exact-server", state.server, state.info)
    assert unavailable.value.status_code == 503 and state.denied == [] and state.deletes == []
