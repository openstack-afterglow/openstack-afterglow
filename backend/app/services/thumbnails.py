"""Bounded raster thumbnails for the object browser grid.

Pure functions over bytes the caller is already authorized to read.
"""

from __future__ import annotations

import io
import threading

THUMBNAIL_EDGE = 320
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
CACHE_TTL_SECONDS = 86_400

THUMBNAILABLE_TYPES = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "image/bmp",
        "image/tiff",
        "application/pdf",
    }
)

# PDFium keeps process-global state; asyncio.to_thread may render concurrently.
_PDF_RENDER_LOCK = threading.Lock()


def is_thumbnailable(content_type: str, size: int) -> bool:
    return content_type in THUMBNAILABLE_TYPES and 0 < size <= MAX_SOURCE_BYTES


def render_thumbnail(data: bytes, content_type: str) -> bytes | None:
    """Return WebP bytes, or None when the source cannot be decoded safely."""
    if not is_thumbnailable(content_type, len(data)):
        return None
    try:
        image = _render_pdf(data) if content_type == "application/pdf" else _open_image(data)
        if image is None:
            return None
        with image:
            image.thumbnail((THUMBNAIL_EDGE, THUMBNAIL_EDGE))
            buffer = io.BytesIO()
            image.save(buffer, format="WEBP", quality=80, method=4)
        return buffer.getvalue()
    except Exception:
        return None


def _open_image(data: bytes):
    from PIL import Image, ImageOps

    source = Image.open(io.BytesIO(data))
    if source.width * source.height > MAX_IMAGE_PIXELS:
        source.close()
        return None
    # Animated GIF / multi-page TIFF: the first frame is the thumbnail.
    if getattr(source, "n_frames", 1) > 1:
        source.seek(0)
    oriented = ImageOps.exif_transpose(source) or source
    # Transparency is part of the image; flattening it onto an implicit black
    # background would misrepresent PNG and GIF sources.
    mode = "RGBA" if oriented.mode in ("RGBA", "LA", "P") else "RGB"
    converted = oriented.convert(mode)
    if oriented is not source:
        oriented.close()
    source.close()
    return converted


def _render_pdf(data: bytes):
    import pypdfium2 as pdfium

    with _PDF_RENDER_LOCK:
        document = pdfium.PdfDocument(data)
        try:
            if len(document) == 0:
                return None
            page = document[0]
            try:
                scale = THUMBNAIL_EDGE / max(page.get_width(), page.get_height(), 1)
                return page.render(scale=scale).to_pil().convert("RGB")
            finally:
                page.close()
        finally:
            document.close()
