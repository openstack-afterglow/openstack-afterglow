from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.union import layer_ops, layer_public
from app.main import _resource_for_path, app
from app.models.db import LayerArtifact, LayerConsume, LayerProfile


def _artifact(**overrides):
    data = {
        "id": 1,
        "name": "uv-base",
        "kind": "uv",
        "python_version": None,
        "pip_packages": [],
        "apt_packages": [],
        "ubuntu_base": "ubuntu-24.04-server-2026-04-15",
        "base_image_id": "img-24",
        "base_image_name": "ubuntu-24.04",
        "base_image_checksum": "sum",
        "base_image_os_hash_algo": "sha512",
        "base_image_os_hash_value": "hash",
        "base_image_min_disk": 20,
        "base_image_visibility": "shared",
        "base_image_owner": "admin",
        "parent_id": None,
        "share_id": "share-1",
        "sqsh_filename": "uv-base-latest.sqsh",
        "build_id": None,
        "size_bytes": 1234,
        "is_published": True,
        "is_sealed": True,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def _profile(**overrides):
    data = {
        "id": 1,
        "name": "default",
        "layers": ["uv-base"],
        "is_published": False,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 1, 2, tzinfo=UTC),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_public_consume_request_requires_exactly_one_selector() -> None:
    with pytest.raises(ValidationError):
        layer_public.PublicLayerConsumeRequest(server_name="vm", flavor_id="m1.small")
    with pytest.raises(ValidationError):
        layer_public.PublicLayerConsumeRequest(
            profile_name="prof",
            artifact_ids=[1],
            server_name="vm",
            flavor_id="m1.small",
        )


def test_public_consume_request_allows_empty_server_name_for_auto_generation() -> None:
    req = layer_public.PublicLayerConsumeRequest(profile_name="prof", server_name="", flavor_id="m1.small")
    assert req.server_name is None


def test_public_artifact_dict_strips_service_owned_mount_fields() -> None:
    data = layer_public._artifact_public_dict(_artifact(parent_id=7))
    assert data["id"] == 1
    assert data["parent_id"] == 7
    assert data["base_image_id"] == "img-24"
    assert "share_id" not in data
    assert "sqsh_filename" not in data


def test_profile_resolution_rejects_missing_or_duplicate_names() -> None:
    unique = layer_public._single_published_by_name([_artifact(name="root"), _artifact(id=2, name="leaf")])
    profile = SimpleNamespace(layers=["root", "leaf"])
    assert [row.name for row in layer_public._profile_artifacts(profile, unique)] == ["root", "leaf"]

    duplicate = layer_public._single_published_by_name([_artifact(name="root"), _artifact(id=3, name="root")])
    assert layer_public._profile_artifacts(SimpleNamespace(layers=["root"]), duplicate) is None


def test_public_router_registered_before_legacy_libraries_router() -> None:
    paths = [route.path for route in app.routes]
    assert "/api/v1/libraries/squashfs/consume" in paths
    assert paths.index("/api/v1/libraries/squashfs/consume") < paths.index("/api/v1/libraries")
    assert _resource_for_path("/api/v1/libraries/squashfs/consume") == ("union_layer", "consume")


def test_publication_and_consume_owner_columns_exist() -> None:
    assert hasattr(LayerArtifact, "is_published")
    assert hasattr(LayerProfile, "is_published")
    assert hasattr(LayerConsume, "project_id")
    assert hasattr(LayerConsume, "artifact_ids")


class _FakeScalarResult:
    def __init__(self, rows: list[object] | None = None, scalar: object | None = None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self) -> list[object]:
        return self._rows

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class _FakeSession:
    def __init__(self, results: list[_FakeScalarResult], added: list[object]):
        self._results = results
        self._added = added

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, _stmt):
        return self._results.pop(0)

    def add(self, row: object) -> None:
        self._added.append(row)

    async def commit(self) -> None:
        return None

    async def refresh(self, row: object) -> None:
        row.id = 41


class _LayerOpsSession:
    def __init__(
        self,
        *,
        artifact: object | None = None,
        results: list[_FakeScalarResult] | None = None,
    ):
        self._artifact = artifact
        self._results = list(results or [])

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, model, key):
        if model is LayerArtifact and self._artifact is not None and getattr(self._artifact, "id", None) == key:
            return self._artifact
        return None

    async def execute(self, _stmt):
        return self._results.pop(0)

    async def commit(self) -> None:
        return None

    async def refresh(self, _row: object) -> None:
        return None


@pytest.mark.asyncio
async def test_admin_artifact_publication_invalidates_union_layer_cache(monkeypatch) -> None:
    artifact = _artifact(id=7, is_published=False, is_sealed=True)
    invalidate_mock = AsyncMock()

    def factory():
        return _LayerOpsSession(artifact=artifact)

    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(layer_ops, "invalidate", invalidate_mock)

    result = await layer_ops.set_layer_artifact_publication(7, layer_ops.PublicationRequest(is_published=True))

    assert result["id"] == 7
    assert result["is_published"] is True
    invalidate_mock.assert_awaited_once_with("afterglow:union_layer:*")


@pytest.mark.asyncio
async def test_admin_profile_publication_requires_public_sealed_layers(monkeypatch) -> None:
    profile = _profile(name="prof", layers=["root"])
    invalidate_mock = AsyncMock()

    def factory():
        return _LayerOpsSession(results=[_FakeScalarResult(scalar=profile), _FakeScalarResult(rows=[])])

    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(layer_ops, "invalidate", invalidate_mock)

    with pytest.raises(HTTPException) as exc:
        await layer_ops.set_layer_profile_publication("prof", layer_ops.PublicationRequest(is_published=True))

    assert exc.value.status_code == 400
    assert "공개/봉인" in str(exc.value.detail)
    invalidate_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_profile_publication_invalidates_union_layer_cache(monkeypatch) -> None:
    profile = _profile(name="prof", layers=["root"])
    root = _artifact(name="root")
    invalidate_mock = AsyncMock()

    def factory():
        return _LayerOpsSession(results=[_FakeScalarResult(scalar=profile), _FakeScalarResult(rows=[root])])

    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)
    monkeypatch.setattr(layer_ops, "invalidate", invalidate_mock)

    result = await layer_ops.set_layer_profile_publication("prof", layer_ops.PublicationRequest(is_published=True))

    assert result["name"] == "prof"
    assert result["is_published"] is True
    invalidate_mock.assert_awaited_once_with("afterglow:union_layer:*")


@pytest.mark.asyncio
async def test_admin_profile_publication_rejects_unimported_legacy_base_image(monkeypatch) -> None:
    profile = _profile(name="prof", layers=["legacy-root"])
    root = _artifact(name="legacy-root", base_image_id=None, base_image_name=None, ubuntu_base="ubuntu-24.04")

    def factory():
        return _LayerOpsSession(results=[_FakeScalarResult(scalar=profile), _FakeScalarResult(rows=[root])])

    monkeypatch.setattr(layer_ops, "get_session_factory", lambda: factory)

    with pytest.raises(HTTPException, match="base image를 확인할 수 없습니다"):
        await layer_ops.set_layer_profile_publication("prof", layer_ops.PublicationRequest(is_published=True))


@pytest.mark.asyncio
async def test_public_profile_listing_omits_unimported_legacy_base_image(monkeypatch) -> None:
    profile = _profile(name="prof", layers=["legacy-root"], is_published=True)
    root = _artifact(name="legacy-root", base_image_id=None, base_image_name=None, ubuntu_base="ubuntu-24.04")
    added: list[object] = []
    results = [_FakeScalarResult(rows=[profile]), _FakeScalarResult(rows=[root])]

    def factory():
        return _FakeSession(results, added)

    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)

    assert await layer_public.list_public_squashfs_profiles(_token_info={"project_id": "project-a"}) == []


@pytest.mark.asyncio
async def test_public_consume_persists_project_and_uses_split_connections(monkeypatch) -> None:
    root = _artifact(id=1, name="root")
    leaf = _artifact(id=2, name="leaf", parent_id=1, share_id="share-2", sqsh_filename="leaf.sqsh")
    added: list[object] = []
    results = [_FakeScalarResult(rows=[leaf]), _FakeScalarResult(rows=[root, leaf])]

    def factory():
        return _FakeSession(results, added)

    caller_conn = MagicMock()
    caller_conn._afterglow_project_id = "project-a"
    caller_conn._afterglow_authenticated_project_id = "project-a"
    caller_conn.image.get_image.return_value = SimpleNamespace(
        id="img-24", name="ubuntu-24.04", status="active", checksum="sum", os_hash_algo="sha512", os_hash_value="hash"
    )
    service_conn = MagicMock()
    run_mock = AsyncMock(return_value="server-1")
    invalidate_mock = AsyncMock()
    mutation_mock = AsyncMock()

    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)
    monkeypatch.setattr(layer_public, "get_service_project_connection", AsyncMock(return_value=service_conn))
    monkeypatch.setattr(
        "app.services.layer_build.resolve_layer_consume_resource_snapshot",
        AsyncMock(
            return_value={
                "network": {"id": "net-1", "name": "network"},
                "flavor": {"id": "flavor-1", "name": "flavor"},
                "openstack.service_project": {"id": "service", "name": "service"},
            }
        ),
    )
    monkeypatch.setattr("app.services.layer_build.run_layer_consume", run_mock)
    monkeypatch.setattr(layer_public, "invalidate", invalidate_mock)
    monkeypatch.setattr(layer_public.cache_invalidation, "invalidate_mutation_count", mutation_mock)

    result = await layer_public.consume_public_squashfs(
        layer_public.PublicLayerConsumeRequest(
            artifact_ids=[2],
            server_name="vm",
            flavor_id="m1.small",
            image_id="img-24",
        ),
        conn=caller_conn,
        token_info={"project_id": "project-a"},
    )

    assert result == {"consume_id": 41, "server_id": "server-1", "status": "active", "ready": True}
    assert added and getattr(added[0], "project_id") == "project-a"
    assert getattr(added[0], "artifact_ids") == [1, 2]
    run_kwargs = run_mock.await_args.kwargs
    assert run_kwargs["artifact_ids"] == [1, 2]
    assert run_kwargs["compute_conn"] is caller_conn
    assert run_kwargs["share_conn"] is service_conn
    invalidate_mock.assert_awaited_once_with("afterglow:nova:project-a:instances")
    mutation_mock.assert_awaited_once_with("nova", "project-a")


@pytest.mark.asyncio
async def test_public_consume_rejects_unpublished_or_unsealed_before_row(monkeypatch) -> None:
    added: list[object] = []
    results = [_FakeScalarResult(rows=[])]

    def factory():
        return _FakeSession(results, added)

    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)

    with pytest.raises(HTTPException) as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(artifact_ids=[99], server_name="vm", flavor_id="m1.small"),
            conn=SimpleNamespace(_afterglow_authenticated_project_id="project-a"),
            token_info={"project_id": "project-a"},
        )

    assert exc.value.status_code == 404
    assert added == []


@pytest.mark.asyncio
async def test_public_profile_rejects_duplicate_name_drift_before_consume(monkeypatch) -> None:
    profile = SimpleNamespace(name="prof", layers=["dup"], is_published=True)
    added: list[object] = []
    results = [
        _FakeScalarResult(scalar=profile),
        _FakeScalarResult(rows=[_artifact(id=1, name="dup"), _artifact(id=2, name="dup")]),
    ]

    def factory():
        return _FakeSession(results, added)

    monkeypatch.setattr(layer_public, "get_session_factory", lambda: factory)

    with pytest.raises(HTTPException) as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(profile_name="prof", server_name="vm", flavor_id="m1.small"),
            conn=SimpleNamespace(_afterglow_authenticated_project_id="project-a"),
            token_info={"project_id": "project-a"},
        )

    assert exc.value.status_code == 409
    assert added == []


@pytest.mark.asyncio
async def test_public_profile_expands_complete_published_root_lineage(monkeypatch) -> None:
    profile = _profile(name="root-profile", layers=["step"], is_published=True)
    ancestor = _artifact(id=1, name="docker-root", kind="dockerfile-root")
    root = _artifact(id=2, name="step", kind="dockerfile", parent_id=1)
    session = _FakeSession(
        [
            _FakeScalarResult(scalar=profile),
            _FakeScalarResult(rows=[ancestor, root]),
            _FakeScalarResult(rows=[root]),
            _FakeScalarResult(rows=[ancestor, root]),
        ],
        [],
    )
    rows = await layer_public._resolve_profile_artifact_ids(session, "root-profile")
    assert [row.id for row in rows] == [1, 2]


@pytest.mark.asyncio
async def test_public_root_rejects_unpublished_ancestor(monkeypatch) -> None:
    root = _artifact(id=2, name="step", kind="dockerfile", parent_id=1)
    ancestor = _artifact(id=1, name="docker-root", kind="dockerfile-root", is_published=False)
    session = _FakeSession([_FakeScalarResult(rows=[root]), _FakeScalarResult(rows=[ancestor, root])], [])
    with pytest.raises(HTTPException, match="ancestor artifact가 공개/봉인"):
        await layer_public._resolve_direct_artifacts(session, [2])


@pytest.mark.asyncio
async def test_public_consume_rejects_cross_project_connection_before_db(monkeypatch) -> None:
    added: list[object] = []
    monkeypatch.setattr(layer_public, "get_session_factory", lambda: lambda: _FakeSession([], added))
    conn = MagicMock()
    conn._afterglow_authenticated_project_id = "project-b"
    with pytest.raises(HTTPException) as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(artifact_ids=[2], flavor_id="m1.small"),
            conn=conn,
            token_info={"project_id": "project-a"},
        )
    assert exc.value.status_code == 401
    assert not added


@pytest.mark.asyncio
async def test_public_consume_rejects_glance_drift_before_db_and_share_access(monkeypatch) -> None:
    root = _artifact(id=1)
    added: list[object] = []
    results = [_FakeScalarResult(rows=[root]), _FakeScalarResult(rows=[root])]
    monkeypatch.setattr(layer_public, "get_session_factory", lambda: lambda: _FakeSession(results, added))
    share_conn = AsyncMock()
    monkeypatch.setattr(layer_public, "get_service_project_connection", share_conn)
    monkeypatch.setattr(
        "app.services.layer_build.resolve_layer_consume_resource_snapshot",
        AsyncMock(
            return_value={
                "network": {"id": "net-1"},
                "flavor": {"id": "flavor-1"},
                "openstack.service_project": {"id": "service"},
            }
        ),
    )
    conn = MagicMock()
    conn._afterglow_authenticated_project_id = "project-a"
    conn.image.get_image.return_value = SimpleNamespace(
        id="img-24",
        name="ubuntu-24.04",
        status="active",
        checksum="drifted",
        os_hash_algo="sha512",
        os_hash_value="hash",
    )
    with pytest.raises(HTTPException, match="identity mismatch") as exc:
        await layer_public.consume_public_squashfs(
            layer_public.PublicLayerConsumeRequest(artifact_ids=[1], flavor_id="m1.small"),
            conn=conn,
            token_info={"project_id": "project-a"},
        )
    assert exc.value.status_code == 400
    assert not added
    share_conn.assert_not_awaited()
