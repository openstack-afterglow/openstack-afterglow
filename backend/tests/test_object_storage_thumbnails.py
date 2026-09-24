"""Authenticated thumbnail rendering for the object browser grid."""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.services import thumbnails


def image_bytes(size: tuple[int, int] = (1000, 600), fmt: str = "PNG", mode: str = "RGB") -> bytes:
    buffer = io.BytesIO()
    color = (0, 128, 96, 255) if mode == "RGBA" else (0, 128, 96)
    Image.new(mode, size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def pdf_bytes() -> bytes:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    document.new_page(612, 792)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def swift_stub(payload: bytes, content_type: str, size: int | None = None) -> MagicMock:
    swift = MagicMock()
    swift.get_object_metadata.return_value = {
        "content_type": content_type,
        "bytes": len(payload) if size is None else size,
        "etag": "etag-1",
    }
    swift.stream_object.return_value = (iter([payload]), content_type, len(payload))
    return swift


# ---------------------------------------------------------------------------
# render_thumbnail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["PNG", "JPEG", "GIF", "WEBP", "BMP", "TIFF"])
def test_renders_every_supported_image_format(fmt):
    thumbnail = thumbnails.render_thumbnail(
        image_bytes(fmt=fmt), f"image/{fmt.lower()}" if fmt != "JPEG" else "image/jpeg"
    )
    assert thumbnail is not None
    rendered = Image.open(io.BytesIO(thumbnail))
    assert rendered.format == "WEBP"
    assert max(rendered.size) == thumbnails.THUMBNAIL_EDGE


def test_preserves_transparency_of_an_rgba_source():
    source = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    source.putpixel((10, 10), (255, 0, 0, 255))
    buffer = io.BytesIO()
    source.save(buffer, format="PNG")

    thumbnail = thumbnails.render_thumbnail(buffer.getvalue(), "image/png")
    rendered = Image.open(io.BytesIO(thumbnail))
    assert rendered.mode in ("RGBA", "LA")
    assert rendered.convert("RGBA").getpixel((0, 0))[3] == 0


def test_renders_first_pdf_page():
    thumbnail = thumbnails.render_thumbnail(pdf_bytes(), "application/pdf")
    assert thumbnail is not None
    assert max(Image.open(io.BytesIO(thumbnail)).size) == thumbnails.THUMBNAIL_EDGE


def test_returns_none_for_undecodable_content():
    assert thumbnails.render_thumbnail(b"not an image at all", "image/png") is None
    assert thumbnails.render_thumbnail(b"%PDF-1.4 broken", "application/pdf") is None


def test_refuses_unsupported_and_oversized_sources():
    assert thumbnails.render_thumbnail(b"plain text", "text/plain") is None
    assert thumbnails.render_thumbnail(b"x" * (thumbnails.MAX_SOURCE_BYTES + 1), "image/png") is None


def test_eligibility_spans_the_documented_range():
    assert thumbnails.is_thumbnailable("image/tiff", 40 * 1024 * 1024)
    assert thumbnails.is_thumbnailable("image/bmp", thumbnails.MAX_SOURCE_BYTES)
    assert not thumbnails.is_thumbnailable("image/bmp", thumbnails.MAX_SOURCE_BYTES + 1)
    assert not thumbnails.is_thumbnailable("image/svg+xml", 1024)
    assert not thumbnails.is_thumbnailable("image/png", 0)


def test_refuses_decompression_bomb_dimensions():
    buffer = io.BytesIO()
    Image.new("L", (7000, 7000)).save(buffer, format="PNG")
    assert thumbnails.render_thumbnail(buffer.getvalue(), "image/png") is None


# ---------------------------------------------------------------------------
# GET /{container}/objects/{name}/thumbnail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thumbnail_endpoint_returns_webp(client, mock_conn):
    with patch("app.services.swift", swift_stub(image_bytes(), "image/png")):
        resp = await client.get("/api/v1/object-storage/test/objects/a.png/thumbnail")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "image/webp"
    assert resp.headers["cache-control"].startswith("private")
    assert Image.open(io.BytesIO(resp.content)).format == "WEBP"


@pytest.mark.asyncio
async def test_thumbnail_is_cached_per_etag(client, mock_conn):
    swift = swift_stub(image_bytes(), "image/png")
    with patch("app.services.swift", swift):
        first = await client.get("/api/v1/object-storage/test/objects/a.png/thumbnail")
        second = await client.get("/api/v1/object-storage/test/objects/a.png/thumbnail")

    assert first.status_code == 200 and second.status_code == 200
    assert first.content == second.content
    assert swift.stream_object.call_count == 1


@pytest.mark.asyncio
async def test_thumbnail_rejects_unsupported_type(client, mock_conn):
    with patch("app.services.swift", swift_stub(b"notes", "text/plain")):
        resp = await client.get("/api/v1/object-storage/test/objects/a.txt/thumbnail")
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_thumbnail_rejects_oversized_object_without_reading_it(client, mock_conn):
    swift = swift_stub(b"x", "image/png", size=thumbnails.MAX_SOURCE_BYTES + 1)
    with patch("app.services.swift", swift):
        resp = await client.get("/api/v1/object-storage/test/objects/big.png/thumbnail")
    assert resp.status_code == 413
    swift.stream_object.assert_not_called()


@pytest.mark.asyncio
async def test_thumbnail_reports_missing_object(client, mock_conn):
    swift = MagicMock()
    swift.get_object_metadata.side_effect = Exception("not found")
    with patch("app.services.swift", swift):
        resp = await client.get("/api/v1/object-storage/test/objects/ghost.png/thumbnail")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_thumbnail_reports_undecodable_object(client, mock_conn):
    with patch("app.services.swift", swift_stub(b"corrupt bytes", "image/png")):
        resp = await client.get("/api/v1/object-storage/test/objects/broken.png/thumbnail")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_thumbnail_handles_nested_object_paths(client, mock_conn):
    swift = swift_stub(image_bytes(), "image/png")
    with patch("app.services.swift", swift):
        resp = await client.get("/api/v1/object-storage/test/objects/docs/2026/a.png/thumbnail")

    assert resp.status_code == 200
    assert swift.get_object_metadata.call_args[0][2] == "docs/2026/a.png"
