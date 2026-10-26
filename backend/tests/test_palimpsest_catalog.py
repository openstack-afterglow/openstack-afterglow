"""Catalog reads/admission with real isolated SQL; native authorities are synthetic."""

from __future__ import annotations

import asyncio
from datetime import UTC
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import Text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.palimpsest import catalog, packages
from app.models.db import LayerArtifact, LayerBuild, LayerConsume, LayerImportJob, LayerProfile
from app.services import palimpsest_catalog as service
from app.services import palimpsest_catalog_consume as consume
from app.services.palimpsest_digest import compute_chain_id
from tests.test_layer_build_ownership import IMAGE
from tests.test_layer_build_ownership import PROJECT as PROVIDER_PROJECT
from tests.test_layer_build_ownership import layer_provider as layer_provider

PROJECT = "11111111111141118111111111111111"
OTHER = "22222222222242228222222222222222"
USER = "33333333333343338333333333333333"
BASE = "/api/v1/palimpsest/catalog"
ADMIN = "/api/v1/admin/palimpsest/catalog"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture
async def catalog_db(monkeypatch, tmp_path):
    monkeypatch.setattr(LayerImportJob.__table__.c.dockerfile_text, "type", Text())
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalog.sqlite'}")
    async with engine.begin() as connection:
        for model in (LayerBuild, LayerArtifact, LayerConsume, LayerImportJob, LayerProfile):
            await connection.run_sync(model.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(service, "get_session_factory", lambda: factory)
    monkeypatch.setattr("app.database.get_session_factory", lambda: factory)
    yield factory
    await engine.dispose()


async def seed(factory):
    async with factory() as session:
        root = LayerArtifact(
            name="root",
            kind="python",
            sqsh_filename="root.sqsh",
            share_id="share-root",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image",
            blob_digest=DIGEST,
            chain_id=compute_chain_id(None, DIGEST),
            digest_state="ready",
            is_sealed=True,
            is_published=True,
            size_bytes=1024,
        )
        session.add(root)
        await session.flush()
        digest = "sha256:" + "b" * 64
        child = LayerArtifact(
            name="torch",
            kind="pip",
            sqsh_filename="torch.sqsh",
            share_id="share-torch",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image",
            blob_digest=digest,
            chain_id=compute_chain_id(root.chain_id, digest),
            parent_id=root.id,
            digest_state="ready",
            is_sealed=True,
            is_published=True,
            size_bytes=2048,
        )
        session.add(child)
        profile = LayerProfile(name="torch-cuda", layers=["torch"], is_published=True)
        session.add(profile)
        await session.commit()
        return root.id, child.id, profile.id


@pytest.fixture
async def catalog_client(catalog_db, monkeypatch):
    app = FastAPI()
    app.include_router(catalog.router, prefix=BASE)
    app.include_router(catalog.admin_router, prefix=ADMIN)
    state = SimpleNamespace(project=PROJECT, admin=True, action=True, paths=[], payload=None)

    async def identity(request: Request):
        info = {
            "project_id": state.project,
            "user_id": USER,
            "token": "original-native",
            "roles": ["member"],
            "is_system_admin": state.admin,
        }
        request.state.token_info = info
        return info

    async def admin(request: Request):
        info = await identity(request)
        if not state.admin:
            raise HTTPException(403, "fresh system authority required")
        return info

    async def action(*args):
        if not state.action:
            raise HTTPException(403, "native policy denied")

    async def transport(request, path, **kwargs):
        state.paths.append((path, kwargs, request.state.token_info["token"]))
        return JSONResponse(state.payload)

    app.dependency_overrides[packages.package_browser_identity] = identity
    app.dependency_overrides[catalog.admin_identity] = admin
    app.dependency_overrides[catalog.cleanup_identity] = identity
    monkeypatch.setattr(catalog, "admin_native_read", transport)
    monkeypatch.setattr(consume, "require_action", action)
    monkeypatch.setattr("app.services.palimpsest_authorization.authorize_current_package_request", AsyncMock())
    monkeypatch.setattr(catalog, "package_browser_request", transport)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, state, app


@pytest.mark.asyncio
async def test_environment_snapshot_expands_public_ancestry_and_hides_paths(catalog_client, catalog_db):
    client, _, _ = catalog_client
    await seed(catalog_db)
    response = await client.get(BASE + "/environments?q=TORCH")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["layer_count"] == 2 and item["size_bytes"] == 3072
    assert item["revision"] == item["chain_id"] and item["cloud_supported"]
    assert item["download_allowed"] is False
    assert not {"share_id", "sqsh_filename", "resource_snapshot", "source_metadata"} & item.keys()
    assert (await client.get(BASE + "/environments?q=%25")).json()["items"] == []
    assert (await client.get(BASE + "/environments?q=a&q=b")).status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["private-parent", "cycle", "missing-parent", "unsealed-parent", "digest-drift"])
async def test_unavailable_ancestor_is_not_disclosed(catalog_client, catalog_db, mutation):
    root_id, child_id, _ = await seed(catalog_db)
    async with catalog_db() as session:
        root = await session.get(LayerArtifact, root_id)
        child = await session.get(LayerArtifact, child_id)
        if mutation == "private-parent":
            root.is_published = False
        elif mutation == "cycle":
            root.parent_id = child_id
        elif mutation == "missing-parent":
            child.parent_id = 999999
        elif mutation == "unsealed-parent":
            root.is_sealed = False
        else:
            root.blob_digest = "sha256:" + "f" * 64
        await session.commit()
    client, _, _ = catalog_client
    assert (await client.get(BASE + "/environments")).json()["items"] == []


@pytest.mark.asyncio
async def test_new_private_namesake_never_substitutes_old_public_layer(catalog_db):
    _, child_id, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        first = await service.published_snapshot(session, profile_id)
        child = await session.get(LayerArtifact, child_id)
        session.add(
            LayerArtifact(
                name=child.name,
                kind=child.kind,
                sqsh_filename="private",
                share_id="private",
                is_sealed=True,
                is_published=False,
            )
        )
        await session.commit()
    async with catalog_db() as session:
        with pytest.raises(HTTPException) as failure:
            await service.published_snapshot(session, profile_id)
        assert failure.value.status_code == 409
        assert first["revision"].startswith("sha256:")


@pytest.mark.asyncio
async def test_revision_changes_on_profile_precedence_and_exact_artifact_replacement(catalog_db):
    _, _, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        first = await service.published_snapshot(session, profile_id)
        profile = await session.get(LayerProfile, profile_id)
        profile.layers = ["torch", "root"]
        await session.commit()
    async with catalog_db() as session:
        second = await service.published_snapshot(session, profile_id)
        assert first["revision"] != second["revision"]
        assert [x["id"] for x in first["artifacts"]] == [x["id"] for x in second["artifacts"]]


@pytest.mark.asyncio
async def test_managed_projection_is_read_only_unknown_origin_and_real_edges(catalog_client, catalog_db, monkeypatch):
    root_id, child_id, _ = await seed(catalog_db)
    monkeypatch.setattr(
        "app.api.union.layer_ops._sync_artifact_rows_with_nova",
        AsyncMock(side_effect=AssertionError("must not synchronize")),
        raising=False,
    )
    client, _, _ = catalog_client
    response = await client.get(ADMIN + f"/{child_id}")
    assert response.status_code == 200
    detail = response.json()
    assert detail["parent_id"] == str(root_id) and [x["id"] for x in detail["ancestors"]] == [str(root_id)]
    assert detail["origin"]["kind"] == "unknown" and detail["project_id"] is None
    assert detail["bundles"] == ["torch-cuda"]
    async with catalog_db() as session:
        assert list((await session.execute(select(LayerConsume))).scalars()) == []


@pytest.mark.asyncio
async def test_cached_reference_does_not_invent_new_build_provenance(catalog_db):
    _, child_id, _ = await seed(catalog_db)
    async with catalog_db() as session:
        build = LayerBuild(layer_name="torch", share_id="share-torch", status="complete")
        session.add(build)
        await session.flush()
        child = await session.get(LayerArtifact, child_id)
        child.build_id = build.id
        cached = LayerImportJob(
            layer_prefix="cached",
            profile_name="cached",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image",
            source_type="github_dockerfile",
            artifact_ids=[child_id],
            build_ids=[],
        )
        session.add(cached)
        await session.commit()
    detail = await service.managed_detail(str(child_id))
    assert detail["origin"] == {
        "kind": "build",
        "source": "recipe",
        "evidence": "recorded",
        "build_id": str(build.id),
        "job_id": None,
        "revision": None,
    }


@pytest.mark.asyncio
async def test_native_assets_exact_route_and_original_subject_with_response_allowlist(catalog_client):
    client, state, _ = catalog_client
    state.payload = {
        "items": [
            {
                "id": DIGEST,
                "name": "Torch",
                "kind": "layer-bundle",
                "blob_digest": DIGEST,
                "chain_id": DIGEST,
                "arch": "amd64",
                "ubuntu_base": "ubuntu-24.04",
                "size_bytes": 1,
                "created_at": None,
                "visibility": "shared",
                "layer_count": 1,
                "chain_complete": True,
                "download_allowed": False,
                "base_image_digest": None,
                "local_supported": False,
                "local_reason": "base-image-required",
                "secret": "never",
            }
        ],
        "offset": 3,
        "has_more": False,
        "next_offset": None,
    }
    response = await client.get(BASE + "/assets?q=torch&offset=3&limit=4")
    assert response.status_code == 200 and "secret" not in response.text
    assert state.paths == [
        ("/v1/catalog/assets", {"query": {"q": "torch", "offset": "3", "limit": "4"}}, "original-native")
    ]
    state.payload["offset"] = 0
    assert (await client.get(BASE + "/assets?offset=3")).status_code == 503


@pytest.mark.asyncio
async def test_admin_policy_denial_and_consume_owner_fence(catalog_client, catalog_db):
    client, state, _ = catalog_client
    state.admin = False
    assert (await client.get(ADMIN)).status_code == 403
    state.admin = True
    state.action = False
    assert (await client.get(ADMIN)).status_code == 200  # Managed SQL does not depend on native policy/Hub.
    state.action = True
    async with catalog_db() as session:
        row = LayerConsume(
            profile_name="private",
            project_id=OTHER,
            share_id="",
            status="active",
            resource_snapshot={"catalog_revision": DIGEST},
        )
        session.add(row)
        await session.commit()
    assert (await client.get(BASE + f"/environments/consumes/{row.id}")).status_code == 404
    state.project = OTHER
    result = await client.get(BASE + f"/environments/consumes/{row.id}")
    assert result.status_code == 200 and result.json()["ready"] is True


@pytest.mark.asyncio
async def test_request_does_not_accept_mutable_profile_or_project_selector(catalog_client):
    client, _, _ = catalog_client
    body = {"revision": DIGEST, "flavor_id": "m1.small", "network_id": "network", "server_name": "torch"}
    for extra in ({"profile_name": "private"}, {"project_id": OTHER}, {"transport": "block"}):
        assert (await client.post(BASE + "/environments/1/consume", json={**body, **extra})).status_code == 422


@pytest.mark.asyncio
async def test_current_writer_rechecks_native_scope_membership_and_reader(monkeypatch):
    from app.services import keystone, project_service

    info = {"project_id": PROJECT, "user_id": USER, "token": "native", "roles": ["member"], "is_system_admin": True}
    monkeypatch.setattr(keystone, "validate_token", lambda *a, **k: {"project_id": PROJECT, "user_id": USER})
    access = {"roles": ["reader"]}
    monkeypatch.setattr(project_service, "get_project_access", AsyncMock(side_effect=lambda *a: access))
    with pytest.raises(HTTPException) as denied:
        await consume.current_writer(info)
    assert denied.value.status_code == 403
    access["roles"] = ["member"]
    await consume.current_writer(info)
    with pytest.raises(HTTPException):
        await consume.current_writer({**info, "connection_project_id": OTHER})


@pytest.mark.asyncio
async def test_private_inventory_forwards_search_without_changing_scope(monkeypatch):
    app = FastAPI()
    app.include_router(packages.router, prefix="/packages")
    app.dependency_overrides[packages.package_browser_identity] = lambda: {"project_id": PROJECT}
    scoped = AsyncMock(return_value=JSONResponse({"items": []}))
    monkeypatch.setattr(packages, "scoped_read", scoped)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/packages?q=Torch%25&limit=10")).status_code == 200
        assert scoped.call_args.args[3] == {"q": "Torch%", "limit": "10"}
        assert (await client.get("/packages?q=" + "x" * 201)).status_code == 422


@pytest.mark.asyncio
async def test_caller_dispatcher_runs_real_consume_and_sql_with_distinct_service_scope(
    catalog_db, layer_provider, monkeypatch
):
    from fakeredis.aioredis import FakeRedis

    from app.services import flavor_eligibility
    from app.services.work_dispatcher import WorkDispatcher

    state, connection = layer_provider
    caller = connection()
    share = connection()
    monkeypatch.setattr(consume, "current_writer", AsyncMock())
    monkeypatch.setattr(consume, "require_action", AsyncMock())
    monkeypatch.setattr(flavor_eligibility, "release_admission", AsyncMock())
    state["shares"]["catalog-root"] = {
        "id": "catalog-root",
        "name": "catalog-root",
        "project_id": PROVIDER_PROJECT,
        "status": "available",
    }
    async with catalog_db() as session:
        artifact = LayerArtifact(
            name="catalog-root",
            kind="dockerfile-root",
            share_id="catalog-root",
            sqsh_filename="root.sqsh",
            is_published=True,
            is_sealed=True,
            digest_state="ready",
            blob_digest=DIGEST,
            chain_id=compute_chain_id(None, DIGEST),
            base_image_id=IMAGE,
            ubuntu_base="ubuntu-24.04-server-2026-04-15",
            size_bytes=4096,
        )
        profile = LayerProfile(name="catalog-profile", layers=["catalog-root"], is_published=True)
        session.add_all([artifact, profile])
        await session.commit()
        snapshot = await service.published_snapshot(session, profile.id)
        resources = {
            "network": {"id": "catalog-network"},
            "flavor": {"id": "catalog-flavor"},
            "openstack.service_project": {"id": "different-service-project"},
            "consumer_project": {"id": PROVIDER_PROJECT},
            "catalog_revision": snapshot["revision"],
            "catalog_profile_id": profile.id,
        }
        row = LayerConsume(
            profile_name=profile.name,
            project_id=PROVIDER_PROJECT,
            artifact_ids=[artifact.id],
            share_id="",
            status="creating",
            server_name="catalog-caller",
            transport="nfs",
            resource_snapshot=resources,
        )
        session.add(row)
        await session.commit()
        consume_id = row.id
    closed = []

    async def caller_scope():
        try:
            yield caller
        finally:
            caller.close()
            closed.append(True)

    scope = caller_scope()
    await anext(scope)
    redis = FakeRedis(decode_responses=True)
    dispatcher = WorkDispatcher(redis, "afterglow:test:catalog-dispatch")
    await dispatcher.__aenter__()
    await dispatcher.publish([f"consume:{consume_id}"])
    claim = await dispatcher.claim(90)
    spec = SimpleNamespace(
        revision=snapshot["revision"],
        server_name="catalog-caller",
        flavor_id="catalog-flavor",
        network_id="catalog-network",
        ssh_username="ubuntu",
    )
    try:
        await consume._execute(
            dispatcher,
            claim,
            scope,
            caller,
            share,
            object(),
            {},
            profile.id,
            spec,
            snapshot["artifacts"],
            resources,
            None,
        )
        async with catalog_db() as session:
            stored = await session.get(LayerConsume, consume_id)
            assert stored.status == "active" and stored.server_id
            assert stored.project_id == PROVIDER_PROJECT and stored.artifact_ids == [artifact.id]
        assert [kind for kind, _ in state["creates"]] == ["port", "rule", "volume", "server"]
        metadata = state["servers"][stored.server_id]["metadata"]
        assert metadata["afterglow_owner_project_id"] == PROVIDER_PROJECT
        assert metadata["afterglow_catalog_consume_id"] == str(consume_id)
        assert "afterglow_import_id" not in metadata and closed == [True]
        assert state["unexpected"] == []
    finally:
        await redis.close()


@pytest.mark.asyncio
async def test_worker_revalidates_revision_before_any_provider_create(catalog_db, monkeypatch):
    from fakeredis.aioredis import FakeRedis

    from app.services import flavor_eligibility, layer_build
    from app.services.work_dispatcher import WorkDispatcher

    _, _, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        snapshot = await service.published_snapshot(session, profile_id)
        row = LayerConsume(
            profile_name="torch-cuda",
            project_id=PROJECT,
            artifact_ids=[1, 2],
            share_id="",
            status="creating",
            resource_snapshot={
                "catalog_revision": snapshot["revision"],
                "consumer_project": {"id": PROJECT},
                "catalog_profile_id": profile_id,
            },
        )
        session.add(row)
        profile = await session.get(LayerProfile, profile_id)
        profile.layers = ["torch", "root"]
        await session.commit()
    monkeypatch.setattr(consume, "current_writer", AsyncMock())
    monkeypatch.setattr(consume, "require_action", AsyncMock())
    monkeypatch.setattr(flavor_eligibility, "release_admission", AsyncMock())
    runner = AsyncMock()
    monkeypatch.setattr(layer_build, "run_layer_consume", runner)
    conn = SimpleNamespace(close=lambda: None)

    async def caller_scope():
        yield conn

    scope = caller_scope()
    await anext(scope)
    redis = FakeRedis(decode_responses=True)
    dispatcher = WorkDispatcher(redis, "afterglow:test:catalog-revision")
    await dispatcher.__aenter__()
    await dispatcher.publish([f"consume:{row.id}"])
    try:
        await consume._execute(
            dispatcher,
            await dispatcher.claim(90),
            scope,
            conn,
            conn,
            object(),
            {},
            profile_id,
            SimpleNamespace(revision=snapshot["revision"]),
            snapshot["artifacts"],
            {},
            None,
        )
        runner.assert_not_awaited()
        async with catalog_db() as session:
            assert (await session.get(LayerConsume, row.id)).status == "error"
    finally:
        await redis.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("race", [False, True])
async def test_consume_endpoint_admits_exact_snapshot_or_rejects_race_before_row(
    catalog_client, catalog_db, monkeypatch, race
):
    from fakeredis.aioredis import FakeRedis

    from app.api import deps
    from app.services import cache, flavor_eligibility, keystone, layer_build, nova, resource_policy_store

    _, _, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        snapshot = await service.published_snapshot(session, profile_id)
    closed = []
    conn = SimpleNamespace(
        network=SimpleNamespace(
            get_network=lambda identity: SimpleNamespace(id=identity, name="net", project_id=PROJECT)
        ),
        close=lambda: closed.append("share"),
    )

    async def scope(request, info):
        try:
            yield conn
        finally:
            closed.append("caller")

    async def validate(*args):
        if race:
            async with catalog_db() as session:
                profile = await session.get(LayerProfile, profile_id)
                profile.layers = ["torch", "root"]
                await session.commit()

    async def runner(**kwargs):
        assert kwargs["compute_conn"] is conn and kwargs["share_conn"] is conn
        assert kwargs["resource_snapshot"]["consumer_project"]["id"] == PROJECT
        assert kwargs["resolved_artifacts"] == snapshot["artifacts"]
        async with catalog_db() as session:
            row = await session.get(LayerConsume, kwargs["consume_db_id"])
            row.status, row.server_id = "active", "caller-server"
            await session.commit()
        return "caller-server"

    redis = FakeRedis(decode_responses=True)
    monkeypatch.setattr(cache, "_get_redis", AsyncMock(return_value=redis))
    monkeypatch.setattr(deps, "get_os_conn", scope)
    monkeypatch.setattr(consume, "current_writer", AsyncMock())
    monkeypatch.setattr(layer_build, "validate_consume_image_identity", validate)
    monkeypatch.setattr(layer_build, "run_layer_consume", runner)
    monkeypatch.setattr(nova, "list_flavors", lambda *_: [SimpleNamespace(id="small", name="small")])
    monkeypatch.setattr(
        resource_policy_store,
        "get_policy_snapshot",
        AsyncMock(return_value={"openstack.service_project": {"id": OTHER}}),
    )
    monkeypatch.setattr(keystone, "get_admin_connection_for_project", lambda project: conn)
    monkeypatch.setattr(flavor_eligibility, "admit_flavor", AsyncMock(return_value=object()))
    monkeypatch.setattr(flavor_eligibility, "release_admission", AsyncMock())
    client, _, _ = catalog_client
    try:
        response = await client.post(
            BASE + f"/environments/{profile_id}/consume",
            json={
                "revision": snapshot["revision"],
                "flavor_id": "small",
                "network_id": "caller-net",
                "server_name": "torch",
            },
        )
        if race:
            assert response.status_code == 409
            async with catalog_db() as session:
                assert list((await session.execute(select(LayerConsume))).scalars()) == []
        else:
            assert response.status_code == 202 and response.json()["ready"] is False
            assert response.json()["server_id"] is None
            await asyncio.gather(*list(consume._tasks))
            status = await client.get(BASE + f"/environments/consumes/{response.json()['consume_id']}")
            assert status.status_code == 200 and status.json()["server_id"] == "caller-server"
            assert status.json()["ready"] is True
        assert sorted(closed) == ["caller", "share"]
    finally:
        await asyncio.gather(*list(consume._tasks), return_exceptions=True)
        await redis.close()


@pytest.mark.asyncio
async def test_admin_native_transport_preserves_projectless_system_subject(monkeypatch):
    from app.services import service_proxy

    monkeypatch.setattr("app.api.palimpsest.hub._require_palimpsest_enabled", lambda: None)

    request = Request({"type": "http", "method": "GET", "path": ADMIN, "headers": []})
    request.state.token_info = {
        "token": "original-system-subject",
        "project_id": "",
        "connection_project_id": "",
        "_live_system_admin": True,
    }
    transport = AsyncMock(return_value=JSONResponse({"items": []}))
    monkeypatch.setattr(service_proxy, "_package_request", transport)
    monkeypatch.setattr(service_proxy, "_configured_internal_endpoint", lambda _: "https://hub.invalid/v1")
    await catalog.admin_native_read(request, "/v1/admin/catalog/layers")
    assert transport.call_args.kwargs["headers"] == {
        "x-auth-token": "original-system-subject",
        "accept": "application/json",
    }
    assert transport.call_args.kwargs["method"] == "GET"
    assert transport.call_args.args[1] == "/v1/admin/catalog/layers"


@pytest.mark.asyncio
async def test_admin_service_nova_never_terminalizes_caller_catalog_jobs(catalog_db, monkeypatch):
    from datetime import datetime, timedelta

    from app.api.union import layer_ops

    row = SimpleNamespace(
        status="indeterminate",
        transport="nfs",
        project_id=PROJECT,
        server_id=None,
        resource_snapshot={"catalog_revision": DIGEST},
        created_at=datetime.now(UTC) - timedelta(days=3),
        updated_at=None,
    )
    assert layer_ops._is_blocking_consume(row)
    assert not layer_ops._should_terminalize_no_server_consume(row, datetime.now(UTC))
    monkeypatch.setattr(
        "app.services.keystone.get_admin_connection_for_project",
        lambda *a: pytest.fail("caller rows cannot use service Nova"),
    )
    async with catalog_db() as session:
        await layer_ops._sync_consume_rows_with_nova(session, [row])
    assert row.status == "indeterminate"


@pytest.mark.asyncio
async def test_provenance_page_loads_job_and_build_metadata_once_per_session(catalog_db):
    from sqlalchemy import event

    root_id, child_id, _ = await seed(catalog_db)
    async with catalog_db() as session:
        for identity in (root_id, child_id):
            build = LayerBuild(layer_name=f"build-{identity}", kind="python", share_id="share", status="complete")
            session.add(build)
            await session.flush()
            (await session.get(LayerArtifact, identity)).build_id = build.id
        await session.commit()
    statements = []
    engine = catalog_db.kw["bind"].sync_engine

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        result = await service.managed_layers("", 0, 50)
        assert len(result["items"]) == 2
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    job_queries = [statement for statement in statements if "FROM layer_import_jobs" in statement]
    build_queries = [statement for statement in statements if "FROM layer_builds" in statement]
    assert len(job_queries) == len(build_queries) == 1
    assert "dockerfile_text" not in job_queries[0] and "resource_snapshot" not in build_queries[0]


@pytest.mark.asyncio
async def test_new_unsealed_build_does_not_replace_current_sealed_profile(catalog_db):
    _, child_id, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        before = await service.published_snapshot(session, profile_id)
        session.add(
            LayerArtifact(
                name="torch",
                kind="pip",
                share_id="building",
                sqsh_filename="building.sqsh",
                is_published=False,
                is_sealed=False,
            )
        )
        await session.commit()
    async with catalog_db() as session:
        current = await service.published_snapshot(session, profile_id)
        assert current["revision"] == before["revision"]
        assert current["artifacts"][-1]["id"] == child_id


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "next_offset,allowed", [(4, False), (3, False), (16, False), (5, True), (15, True), (None, False)]
)
async def test_asset_candidate_page_allows_empty_continuation_only_with_bounded_progress(
    catalog_client, next_offset, allowed
):
    client, state, _ = catalog_client
    state.payload = {"items": [], "offset": 4, "has_more": True, "next_offset": next_offset}
    response = await client.get(BASE + "/assets?offset=4&limit=11")
    assert response.status_code == (200 if allowed else 503)
    if allowed:
        assert response.json()["items"] == [] and response.json()["next_offset"] == next_offset


@pytest.mark.asyncio
async def test_catalog_search_bound_matches_native(catalog_client):
    client, _, _ = catalog_client
    assert (await client.get(BASE + "/assets?q=" + "x" * 129)).status_code == 422
    assert (await client.get(ADMIN + "?q=" + "x" * 129)).status_code == 422


@pytest.mark.asyncio
async def test_runtime_incompatible_profile_name_is_visible_but_cannot_allocate(
    catalog_client, catalog_db, monkeypatch
):
    from app.api import deps

    client, _, _ = catalog_client
    _, _, profile_id = await seed(catalog_db)
    async with catalog_db() as session:
        profile = await session.get(LayerProfile, profile_id)
        profile.name = "Legacy-Uppercase"
        await session.commit()
    native_calls = []
    closed = []

    def unexpected_native_query(*args):
        native_calls.append(args)
        raise AssertionError("incompatible environment must stop before native placement")

    async def scope(request, info):
        try:
            yield SimpleNamespace(network=SimpleNamespace(get_network=unexpected_native_query))
        finally:
            closed.append(True)

    monkeypatch.setattr(deps, "get_os_conn", scope)
    monkeypatch.setattr(consume, "current_writer", AsyncMock())
    response = await client.get(BASE + "/environments?q=legacy")
    assert response.status_code == 200
    asset = response.json()["items"][0]
    assert asset["id"] == str(profile_id) and asset["cloud_supported"] is False
    refused = await client.post(
        f"{BASE}/environments/{profile_id}/consume",
        json={
            "revision": asset["revision"],
            "flavor_id": "small",
            "network_id": "network",
            "server_name": "must-not-allocate",
        },
    )
    assert refused.status_code == 409
    assert not native_calls and closed == [True]
    async with catalog_db() as session:
        assert list((await session.execute(select(LayerConsume))).scalars()) == []


@pytest.mark.asyncio
async def test_managed_candidate_page_preserves_continuation_after_private_chain(catalog_client, catalog_db):
    client, _, _ = catalog_client
    async with catalog_db() as session:
        hidden = LayerArtifact(
            name="private-layer",
            kind="python",
            sqsh_filename="private.sqsh",
            share_id="private-share",
            ubuntu_base="ubuntu-24.04",
            base_image_id="image",
            blob_digest=DIGEST,
            chain_id=DIGEST,
            digest_state="ready",
            is_sealed=True,
            is_published=False,
            size_bytes=1024,
        )
        session.add_all([hidden, LayerProfile(name="broken-public-profile", layers=[hidden.name], is_published=True)])
        await session.commit()
    _, _, visible_id = await seed(catalog_db)
    first = await client.get(BASE + "/environments?limit=1&offset=0")
    assert first.status_code == 200
    assert first.json() == {"items": [], "offset": 0, "has_more": True, "next_offset": 1}
    assert "private-layer" not in first.text and "private-share" not in first.text
    second = await client.get(BASE + "/environments?limit=1&offset=1")
    assert second.status_code == 200
    assert [item["id"] for item in second.json()["items"]] == [str(visible_id)]
    assert second.json()["has_more"] is False and second.json()["next_offset"] is None
