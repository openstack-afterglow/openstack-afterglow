"""Profile image HTTP paths through a real SDK identity proxy and native JSON transport."""

import base64
import copy
import hashlib
import io
import json
from urllib.parse import urlsplit

import openstack.connection
import pytest
import requests
from httpx import ASGITransport, AsyncClient
from keystoneauth1 import session as ks_session
from keystoneauth1.noauth import NoAuth
from PIL import Image, PngImagePlugin
from requests.adapters import BaseAdapter

from app.api.deps import get_token_info
from app.main import app
from app.services.profile_images import MAX_UPLOAD_BYTES
from tests.conftest import make_token_info


class NativeImages(BaseAdapter):
    def __init__(self):
        self.users = {
            "test-user-123": {
                "id": "test-user-123",
                "domain_id": "default",
                "enabled": True,
                "email": " MyEmailAddress@example.com ",
                "unrelated": {"preserve": True},
            },
            "other": {"id": "other", "domain_id": "foreign-home", "enabled": True, "email": "other@example.com"},
        }
        self.requests = []
        self.authorities = []
        self.foreign_requests = []
        self.redirect_path = None
        self.home_enabled = True
        self.writer_foreign = False
        self.patch_status = 200
        self.return_foreign = False
        self.return_wrong_home = False
        self.confirm_write = True

    def send(self, request, **kwargs):
        url = urlsplit(request.url)
        path = url.path
        self.requests.append((request.method, path, request.body))
        service = request.headers.get("X-Test-Authority") == "service"
        self.authorities.append((request.method, service))
        if url.netloc != "native.test":
            self.foreign_requests.append((request.method, request.url, dict(request.headers), request.body))
            response = requests.Response()
            response.status_code = 200
            response._content = b"{}"
            response.request = request
            response.url = request.url
            return response
        status = 200
        if path.rstrip("/") == "/v3":
            body = {
                "version": {
                    "id": "v3.14",
                    "status": "stable",
                    "links": [{"rel": "self", "href": "http://native.test/v3/"}],
                }
            }
        elif "/domains/" in path:
            body = {"domain": {"id": path.rsplit("/", 1)[-1], "enabled": self.home_enabled}}
        else:
            user_id = path.rsplit("/", 1)[-1]
            user = self.users[user_id]
            if request.method == "PATCH":
                status = self.patch_status if service else 403
                if status == 200 and self.confirm_write:
                    user.update(json.loads(request.body)["user"])
            body = {
                "user": copy.deepcopy(
                    self.users["other"] if self.return_foreign or service and self.writer_foreign else user
                )
            }
            if self.return_wrong_home:
                body["user"]["domain_id"] = "wrong-home"
        if path == self.redirect_path:
            status = 302
        response = requests.Response()
        response.status_code = status
        response._content = json.dumps(body).encode()
        response.headers["Content-Type"] = "application/json"
        if status == 302:
            response.headers["Location"] = "http://attacker.invalid/collect"
        response.request = request
        response.url = request.url
        return response

    def close(self):
        pass


@pytest.fixture
def native_images(mock_conn, monkeypatch):
    adapter = NativeImages()

    def connection(*, service=False):
        transport = requests.Session()
        transport.mount("http://", adapter)
        transport.mount("https://", adapter)
        if service:
            transport.headers["X-Test-Authority"] = "service"
        endpoint = "http://native.test/v3"
        return openstack.connection.Connection(
            session=ks_session.Session(auth=NoAuth(endpoint=endpoint), session=transport),
            identity_endpoint_override=endpoint,
            identity_api_version="3",
        )

    conn = connection()
    mock_conn.identity = conn.identity
    monkeypatch.setattr(
        "app.services.profile_images.keystone.get_admin_project_connection", lambda: connection(service=True)
    )
    yield adapter
    conn.close()


def raster(size=(48, 32), format="PNG", **kwargs):
    output = io.BytesIO()
    image = Image.new("RGB", size, (45, 110, 160))
    image.save(output, format=format, **kwargs)
    return output.getvalue()


@pytest.mark.asyncio
async def test_default_current_email_hash_and_no_email_fallback(client, native_images):
    response = await client.get("/api/v1/profile/image")
    assert response.status_code == 200
    digest = hashlib.sha256(b"myemailaddress@example.com").hexdigest()
    assert response.json() == {"kind": "gravatar", "url": f"https://www.gravatar.com/avatar/{digest}?s=128&d=404"}
    assert response.headers["cache-control"] == "private, no-store"
    native_images.users["test-user-123"]["email"] = "changed@example.com"
    changed = (await client.get("/api/v1/profile/image")).json()
    assert hashlib.sha256(b"changed@example.com").hexdigest() in changed["url"]
    native_images.users["test-user-123"]["email"] = ""
    assert (await client.get("/api/v1/profile/image")).json() == {"kind": "gravatar", "url": None}
    assert all(method == "GET" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_generated_choice_roundtrip_regeneration_and_gravatar_reset(client, native_images):
    first = await client.put("/api/v1/profile/image", json={"kind": "generated"})
    assert first.status_code == 200
    assert first.json()["kind"] == "generated"
    assert first.json()["url"].startswith("data:image/png;base64,")
    assert (await client.get("/api/v1/profile/image")).json() == first.json()
    second = await client.put("/api/v1/profile/image", json={"kind": "generated"})
    assert second.json()["url"] != first.json()["url"]
    assert native_images.users["test-user-123"]["unrelated"] == {"preserve": True}
    assert "afterglow_profile_image" not in native_images.users["other"]
    reset = await client.put("/api/v1/profile/image", json={"kind": "gravatar"})
    assert reset.json()["kind"] == "gravatar"
    assert native_images.users["test-user-123"]["afterglow_profile_image"] == {"kind": "gravatar"}
    assert all(
        path in {"/v3", "/v3/users/test-user-123", "/v3/domains/default"} for _, path, _ in native_images.requests
    )
    assert all(service for method, service in native_images.authorities if method == "PATCH")
    for method, _, body in native_images.requests:
        if method == "PATCH":
            assert set(json.loads(body)["user"]) == {"afterglow_profile_image"}


@pytest.mark.asyncio
@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "GIF"])
async def test_raster_upload_decodes_normalizes_and_roundtrips(client, native_images, format):
    metadata = PngImagePlugin.PngInfo()
    metadata.add_text("private-location", "must disappear")
    source = raster(format=format, **({"pnginfo": metadata} if format == "PNG" else {}))
    response = await client.put(
        "/api/v1/profile/image/upload", content=source, headers={"Content-Type": "application/octet-stream"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["kind"] == "upload"
    content = base64.b64decode(result["url"].split(",", 1)[1])
    with Image.open(io.BytesIO(content)) as image:
        image.load()
        assert image.size == (128, 128)
        assert image.format == "PNG"
        assert image.info == {}
    assert b"must disappear" not in content
    assert (await client.get("/api/v1/profile/image")).json() == result
    assert native_images.users["test-user-123"]["unrelated"] == {"preserve": True}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [b"<svg onload='alert(1)'/>", b"https://attacker.invalid/image.png", b"\x89PNG\r\n\x1a\ninvalid", b"not an image"],
)
async def test_unsafe_or_undecodable_upload_never_writes(client, native_images, body):
    response = await client.put("/api/v1/profile/image/upload", content=body, headers={"Content-Type": "image/png"})
    assert response.status_code == 422
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_bounds_reject_bytes_dimensions_pixels_animation_and_truncation(client, native_images):
    oversized = await client.put("/api/v1/profile/image/upload", content=b"x" * (MAX_UPLOAD_BYTES + 1))
    assert oversized.status_code == 413
    for source in [raster((4097, 1)), raster((2049, 2049)), raster()[:40]]:
        response = await client.put("/api/v1/profile/image/upload", content=source)
        assert response.status_code == 422
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    animated = io.BytesIO()
    frames[0].save(animated, format="GIF", save_all=True, append_images=frames[1:])
    assert (await client.put("/api/v1/profile/image/upload", content=animated.getvalue())).status_code == 422
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_caller_cannot_choose_subject_or_url(client, native_images):
    for body in [
        {"kind": "generated", "user_id": "other"},
        {"kind": "gravatar", "url": "http://attacker.invalid"},
        {"kind": "upload"},
    ]:
        assert (await client.put("/api/v1/profile/image", json=body)).status_code == 422
    response = await client.put("/api/v1/profile/image/other", json={"kind": "generated"})
    assert response.status_code in {404, 405}
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_identity_and_home_mismatch_never_writes(client, native_images):
    native_images.return_foreign = True
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 503
    native_images.return_foreign = False
    native_images.return_wrong_home = True
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 503
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
@pytest.mark.parametrize("status, expected", [(302, 503), (403, 403), (500, 503)])
async def test_service_write_denial_is_not_success_or_retried(client, native_images, status, expected):
    native_images.patch_status = status
    response = await client.put("/api/v1/profile/image", json={"kind": "generated"})
    assert response.status_code == expected
    assert "afterglow_profile_image" not in native_images.users["test-user-123"]
    assert len([row for row in native_images.requests if row[0] == "PATCH"]) == 1
    assert native_images.foreign_requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/v3/users/test-user-123", "/v3/domains/default"])
async def test_native_read_redirect_never_sends_caller_or_service_authority_to_foreign_origin(
    client, native_images, path
):
    native_images.redirect_path = path
    response = await client.put("/api/v1/profile/image", json={"kind": "generated"})
    assert response.status_code == 503
    assert native_images.foreign_requests == []
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_unconfirmed_write_and_poisoned_native_metadata_are_not_published(client, native_images):
    native_images.confirm_write = False
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 503
    native_images.users["test-user-123"]["afterglow_profile_image"] = {
        "kind": "upload",
        "png": "http://attacker.invalid",
    }
    assert (await client.get("/api/v1/profile/image")).status_code == 503


@pytest.mark.asyncio
async def test_other_authenticated_owner_has_independent_preference(client, native_images):
    own = (await client.put("/api/v1/profile/image", json={"kind": "generated"})).json()
    token = make_token_info(domain_id="foreign-home")
    token["user_id"] = "other"
    app.dependency_overrides[get_token_info] = lambda: token
    other = (await client.get("/api/v1/profile/image")).json()
    assert other["kind"] == "gravatar"
    assert other["url"] != own["url"]
    app.dependency_overrides[get_token_info] = lambda: make_token_info()
    assert (await client.get("/api/v1/profile/image")).json() == own


@pytest.mark.asyncio
async def test_disabled_user_home_or_foreign_service_read_prevents_writer_mutation(client, native_images):
    native_images.users["test-user-123"]["enabled"] = False
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 403
    native_images.users["test-user-123"]["enabled"] = True
    native_images.home_enabled = False
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 403
    native_images.home_enabled = True
    native_images.writer_foreign = True
    assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 503
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_native_extra_text_capacity_is_checked_before_writing(client, native_images):
    native_images.users["test-user-123"]["other_metadata"] = "한" * 21_000
    before = copy.deepcopy(native_images.users)
    response = await client.put("/api/v1/profile/image", json={"kind": "generated"})
    assert response.status_code == 422
    assert response.json()["detail"] == "profile_image_metadata_size"
    assert native_images.users == before
    assert not any(method == "PATCH" for method, _, _ in native_images.requests)


@pytest.mark.asyncio
async def test_noisy_alpha_upload_fits_native_text_storage(client, native_images):
    import random

    output = io.BytesIO()
    Image.frombytes("RGBA", (128, 128), random.Random(17).randbytes(128 * 128 * 4)).save(output, format="PNG")
    response = await client.put("/api/v1/profile/image/upload", content=output.getvalue())
    assert response.status_code == 200
    stored = json.dumps(native_images.users["test-user-123"], ensure_ascii=False, separators=(",", ":")).encode()
    assert len(stored) < 60_000
    assert (await client.get("/api/v1/profile/image")).json() == response.json()


@pytest.mark.asyncio
async def test_image_paths_require_authentication():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/profile/image")).status_code == 401
        assert (await client.put("/api/v1/profile/image", json={"kind": "generated"})).status_code == 401
        assert (await client.put("/api/v1/profile/image/upload", content=raster())).status_code == 401
