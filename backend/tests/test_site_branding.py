"""Regression coverage for DB-backed login branding assets."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import get_settings
from app.main import app
from app.services import site_branding

PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"


class _ScalarResult:
    def __init__(self, *, rows: list[object] | None = None, scalar: object | None = None):
        self._rows = rows or []
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self) -> list[object]:
        return self._rows

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class _AsyncNullContext:
    async def __aenter__(self):
        return None

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeBrandingSession:
    def __init__(self, store: dict[str, object]):
        self._store = store

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def begin(self):
        return _AsyncNullContext()

    async def execute(self, stmt):
        params = stmt.compile().params
        selected = next(iter(params.values()), None)
        if isinstance(selected, (list, tuple, set)):
            rows = [self._store[slot] for slot in selected if slot in self._store]
            return _ScalarResult(rows=rows)
        if isinstance(selected, str):
            return _ScalarResult(scalar=self._store.get(selected))
        return _ScalarResult(rows=list(self._store.values()))

    def add(self, row: object) -> None:
        slot = getattr(row, "slot")
        now = datetime.now(UTC)
        if getattr(row, "id", None) is None:
            row.id = len(self._store) + 1
        if getattr(row, "created_at", None) is None:
            row.created_at = now
        row.updated_at = now
        self._store[slot] = row

    async def delete(self, row: object) -> None:
        self._store.pop(getattr(row, "slot"), None)


def _session_factory(store: dict[str, object]):
    def factory():
        return _FakeBrandingSession(store)

    return factory


@pytest.mark.asyncio
async def test_public_site_config_preserves_operator_branding_when_db_is_unavailable(monkeypatch):
    """Offline branding storage must not replace explicit operator configuration."""
    configured_branding = {
        "logo_path": "/operator-logo.png",
        "logo_dark_path": "/operator-dark.png",
        "logo_light_path": "/operator-light.png",
        "favicon_path": "/operator-favicon.ico",
    }
    settings = get_settings()
    for field, path in configured_branding.items():
        monkeypatch.setattr(settings, field, path)
    monkeypatch.setattr(site_branding, "is_db_available", lambda: False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/site-config")

    assert resp.status_code == 200
    payload = resp.json()
    assert {field: payload[field] for field in configured_branding} == configured_branding


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "declared_content_type"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'></svg>", "image/png"),
        (b"<!DOCTYPE html><html>not an image</html>", "image/jpeg"),
    ],
)
async def test_admin_branding_upload_rejects_non_raster_magic_bytes(admin_client, payload, declared_content_type):
    """Upload validation must reject SVG/XML and fake image payloads even when the multipart type claims image/*."""
    resp = await admin_client.post(
        "/api/v1/site-config/admin/branding/logo_dark",
        files={"file": ("login-logo.bin", payload, declared_content_type)},
    )

    assert resp.status_code == 400
    assert "PNG, JPEG, WebP, GIF" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_uploaded_branding_asset_uses_detected_content_type_and_public_asset_url(admin_client, monkeypatch):
    """A valid upload must store the detected media type and surface the DB-backed public asset URL."""
    store: dict[str, object] = {}
    monkeypatch.setattr(site_branding, "is_db_available", lambda: True)
    monkeypatch.setattr(site_branding, "get_session_factory", lambda: _session_factory(store))

    upload = await admin_client.post(
        "/api/v1/site-config/admin/branding/logo_dark",
        files={"file": ("login-logo.dat", PNG_BYTES, "image/jpeg")},
    )

    assert upload.status_code == 200
    payload = upload.json()
    digest = hashlib.sha256(PNG_BYTES).hexdigest()[:12]
    expected_url = f"/api/v1/site-config/assets/logo_dark?v={digest}"

    stored = store["logo_dark"]
    assert stored.content_type == "image/png"
    assert payload["assets"]["logo_dark"]["content_type"] == "image/png"
    assert payload["assets"]["logo_dark"]["url"] == expected_url
    assert payload["effective"]["logo_dark_path"] == expected_url

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        public_config = await ac.get("/api/v1/site-config")
        asset = await ac.get(expected_url)
        mismatched_asset = await ac.get("/api/v1/site-config/assets/logo_dark?v=deadbeefdead")

    assert public_config.status_code == 200
    assert public_config.json()["logo_dark_path"] == expected_url
    assert asset.status_code == 200
    assert asset.content == PNG_BYTES
    assert asset.headers["content-type"].startswith("image/png")
    assert asset.headers["x-content-type-options"] == "nosniff"

    assert mismatched_asset.status_code == 404


@pytest.mark.asyncio
async def test_admin_branding_reset_removes_asset_and_restores_configured_fallback(admin_client, monkeypatch):
    """Reset must remove the DB asset and restore the configured operator logo."""
    store: dict[str, object] = {}
    settings = get_settings()
    monkeypatch.setattr(settings, "logo_light_path", "/operator-light.png")
    configured_fallback = settings.logo_light_path
    monkeypatch.setattr(site_branding, "is_db_available", lambda: True)
    monkeypatch.setattr(site_branding, "get_session_factory", lambda: _session_factory(store))

    upload = await admin_client.post(
        "/api/v1/site-config/admin/branding/logo_light",
        files={"file": ("login-logo.png", PNG_BYTES, "image/png")},
    )
    assert upload.status_code == 200
    digest = hashlib.sha256(PNG_BYTES).hexdigest()[:12]
    expected_url = f"/api/v1/site-config/assets/logo_light?v={digest}"
    assert upload.json()["effective"]["logo_light_path"] == expected_url
    assert "logo_light" in store

    reset = await admin_client.delete("/api/v1/site-config/admin/branding/logo_light")

    assert reset.status_code == 200
    assert "logo_light" not in store
    assert reset.json()["assets"]["logo_light"] is None
    assert reset.json()["effective"]["logo_light_path"] == configured_fallback

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        public_config = await ac.get("/api/v1/site-config")
        old_asset = await ac.get(expected_url)

    assert public_config.status_code == 200
    assert public_config.json()["logo_light_path"] == configured_fallback
    assert old_asset.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "db_available", "factory_available"),
    [
        ("POST", False, True),
        ("POST", True, False),
        ("DELETE", False, True),
        ("DELETE", True, False),
    ],
)
async def test_admin_branding_mutations_return_503_when_storage_is_unavailable(
    admin_client,
    monkeypatch,
    method,
    db_available,
    factory_available,
):
    """Upload and reset must both fail closed when branding storage cannot serve a DB session."""
    monkeypatch.setattr(site_branding, "is_db_available", lambda: db_available)
    monkeypatch.setattr(
        site_branding,
        "get_session_factory",
        lambda: _session_factory({}) if factory_available else None,
    )

    if method == "POST":
        resp = await admin_client.post(
            "/api/v1/site-config/admin/branding/logo_light",
            files={"file": ("login-logo.png", PNG_BYTES, "image/png")},
        )
    else:
        resp = await admin_client.delete("/api/v1/site-config/admin/branding/logo_light")

    assert resp.status_code == 503
