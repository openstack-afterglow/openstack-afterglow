"""Upload inspection for the browser proxy upload route.

Two jobs, both bounded and offline:

1. **Integrity** — one sequential pass over the already-spooled upload computes
   size, SHA-256 (compared against the browser's value) and MD5 (compared
   against the stored single-part S3 ETag).
2. **Safety** — a narrow, content-based policy. Only two classes of content are
   refused: a renderable extension whose bytes are not that format, and an
   executable image wearing a non-executable extension. Everything else is
   accepted and its detected type recorded. This is not an antivirus engine and
   does not claim an accepted object is malware-free.
"""

from __future__ import annotations

import hashlib
import hmac
import mimetypes
from collections.abc import Callable
from dataclasses import dataclass

import puremagic

from app.services.s3 import UploadCanceled

HEAD_BYTES = 8192
CHUNK_BYTES = 1024 * 1024

# Extensions the product renders inline (thumbnails, preview modal). Content
# that disagrees with one of these is refused, because the browser would be
# asked to interpret it as that format.
RENDERABLE_EXT_MIMES: dict[str, frozenset[str]] = {
    "png": frozenset({"image/png"}),
    "jpg": frozenset({"image/jpeg"}),
    "jpeg": frozenset({"image/jpeg"}),
    "gif": frozenset({"image/gif"}),
    "webp": frozenset({"image/webp"}),
    "bmp": frozenset({"image/bmp", "image/x-ms-bmp"}),
    "pdf": frozenset({"application/pdf"}),
}

# Extensions under which an executable image is honestly named. The empty
# string covers extensionless binaries.
EXECUTABLE_EXTS = frozenset(
    {
        "",
        "exe",
        "dll",
        "sys",
        "com",
        "scr",
        "msi",
        "ocx",
        "cpl",
        "drv",
        "efi",
        "so",
        "o",
        "a",
        "ko",
        "elf",
        "bin",
        "out",
        "dylib",
        "bundle",
    }
)

# CAFEBABE is deliberately absent: it collides with Java class files.
_MACHO_MAGIC = frozenset({b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xce\xfa\xed\xfe", b"\xcf\xfa\xed\xfe"})


class UploadRejected(Exception):
    """Refused by policy. The message is the HTTP 400 detail shown to the uploader."""


class IntegrityMismatch(UploadRejected):
    """The browser-computed SHA-256 does not match the bytes the server read."""


@dataclass(frozen=True)
class UploadInspection:
    size: int
    sha256: str
    md5: str
    declared_content_type: str
    detected_content_type: str
    content_type: str
    executable: str | None


def inspect_upload(
    stream,
    filename: str,
    declared_content_type: str,
    expected_sha256: str | None = None,
    should_cancel: Callable[[], bool] | None = None,
) -> UploadInspection:
    """Hash and classify a spooled upload, leaving the stream rewound."""
    stream.seek(0)
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)

    head = stream.read(HEAD_BYTES)
    sha256.update(head)
    md5.update(head)
    size = len(head)
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        sha256.update(chunk)
        md5.update(chunk)
        size += len(chunk)
        if should_cancel is not None and should_cancel():
            raise UploadCanceled("client disconnected")
    stream.seek(0)

    detected = _detect_mime(head)
    executable = _detect_executable(head)
    ext = _extension(filename)

    allowed = RENDERABLE_EXT_MIMES.get(ext)
    if allowed is not None and detected not in allowed:
        raise UploadRejected(f"보안 검사 실패: .{ext} 파일의 실제 내용이 {detected or '알 수 없는 형식'}입니다")
    if executable is not None and ext not in EXECUTABLE_EXTS:
        raise UploadRejected(f"보안 검사 실패: 실행 파일({executable})이 .{ext} 확장자로 위장되어 있습니다")

    digest = sha256.hexdigest()
    if expected_sha256 is not None and not hmac.compare_digest(expected_sha256, digest):
        raise IntegrityMismatch("무결성 검증 실패: 브라우저에서 계산한 SHA-256과 서버 계산값이 다릅니다")

    declared = (declared_content_type or "").strip()
    if declared in ("", "application/octet-stream"):
        content_type = detected or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    else:
        content_type = declared

    return UploadInspection(
        size=size,
        sha256=digest,
        md5=md5.hexdigest(),
        declared_content_type=declared,
        detected_content_type=detected,
        content_type=content_type,
        executable=executable,
    )


def _extension(filename: str) -> str:
    base = filename.rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[-1].lower() if "." in base else ""


def _detect_mime(head: bytes) -> str:
    """Best-effort content type from leading bytes. Empty string when unknown."""
    # Acrobat tolerates junk before the header, so a signature scan beats a
    # strict prefix test for real-world PDFs.
    if b"%PDF-" in head[:1024]:
        return "application/pdf"
    try:
        matches = puremagic.magic_string(head)
    except (puremagic.PureError, ValueError):
        return ""
    for match in matches:
        mime = (getattr(match, "mime_type", "") or "").strip()
        if mime:
            return mime
    return ""


def _detect_executable(head: bytes) -> str | None:
    if head[:2] == b"MZ":
        return "pe"
    if head[:4] == b"\x7fELF":
        return "elf"
    if head[:4] in _MACHO_MAGIC:
        return "macho"
    return None
