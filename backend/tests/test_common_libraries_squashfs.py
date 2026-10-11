from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.union import layer_ops
from app.models.db import LayerArtifact


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


@pytest.mark.asyncio
async def test_public_squashfs_inventory_and_consumption_are_not_available(client) -> None:
    listing = await client.get("/api/v1/libraries/squashfs/artifacts")
    consume = await client.post("/api/v1/libraries/squashfs/consume", json={})
    assert listing.status_code == 404
    assert consume.status_code == 404


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
