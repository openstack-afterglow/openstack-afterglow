"""Upload inspection: integrity hashes plus the narrow content-safety policy.

The policy refuses exactly two things — a renderable extension whose bytes are
not that format, and an executable image wearing a non-executable extension.
Everything else uploads and only records what the bytes looked like.
"""

from __future__ import annotations

import hashlib
import io
import zipfile

import pytest
from PIL import Image

from app.services.s3 import UploadCanceled
from app.services.upload_inspection import IntegrityMismatch, UploadRejected, inspect_upload


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (24, 24)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "teal").save(buffer, format=fmt)
    return buffer.getvalue()


def pdf_bytes(prefix: bytes = b"") -> bytes:
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument.new()
    document.new_page(200, 200)
    buffer = io.BytesIO()
    document.save(buffer)
    return prefix + buffer.getvalue()


def zip_bytes(name: str = "readme.txt") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "hello")
    return buffer.getvalue()


def inspect(payload: bytes, filename: str, declared: str = "application/octet-stream", **kwargs):
    return inspect_upload(io.BytesIO(payload), filename, declared, **kwargs)


# ---------------------------------------------------------------------------
# integrity
# ---------------------------------------------------------------------------


def test_reports_size_and_both_digests_of_the_whole_stream():
    payload = b"hello!\n"
    result = inspect(payload, "hello.txt", "text/plain")

    assert result.size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.md5 == hashlib.md5(payload).hexdigest()


def test_hashes_content_larger_than_one_chunk():
    payload = bytes(range(256)) * 20_000  # > HEAD_BYTES and > CHUNK_BYTES
    result = inspect(payload, "blob.bin")

    assert result.size == len(payload)
    assert result.sha256 == hashlib.sha256(payload).hexdigest()
    assert result.md5 == hashlib.md5(payload).hexdigest()


def test_rewinds_the_stream_for_the_uploader():
    payload = image_bytes()
    stream = io.BytesIO(payload)
    inspect_upload(stream, "photo.png", "image/png")

    assert stream.tell() == 0
    assert stream.read() == payload


def test_matching_browser_digest_is_accepted():
    payload = b"hello!\n"
    result = inspect(payload, "hello.txt", "text/plain", expected_sha256=hashlib.sha256(payload).hexdigest())
    assert result.sha256 == hashlib.sha256(payload).hexdigest()


def test_mismatched_browser_digest_is_an_integrity_failure():
    with pytest.raises(IntegrityMismatch):
        inspect(b"hello!\n", "hello.txt", "text/plain", expected_sha256="0" * 64)


def test_cancellation_stops_the_read():
    with pytest.raises(UploadCanceled):
        inspect(b"x" * (2 * 1024 * 1024), "big.bin", should_cancel=lambda: True)


# ---------------------------------------------------------------------------
# detection and content type
# ---------------------------------------------------------------------------


def test_detects_png_and_fills_in_an_unspecified_content_type():
    result = inspect(image_bytes(), "photo.png", "application/octet-stream")
    assert result.detected_content_type == "image/png"
    assert result.content_type == "image/png"


def test_detects_pdf_even_with_leading_junk():
    result = inspect(pdf_bytes(b"junk" * 30), "doc.pdf", "application/pdf")
    assert result.detected_content_type == "application/pdf"


def test_preserves_a_declared_content_type():
    result = inspect(b"col_a,col_b\n1,2\n", "data.csv", "text/csv")
    assert result.content_type == "text/csv"


def test_falls_back_to_the_filename_when_content_is_unrecognized():
    result = inspect(b"just some notes\n", "notes.txt", "")
    assert result.detected_content_type == ""
    assert result.content_type == "text/plain"


def test_unknown_content_without_a_known_extension_stays_octet_stream():
    result = inspect(b"\x01\x02\x03 opaque payload", "model.weights", "")
    assert result.content_type == "application/octet-stream"


# ---------------------------------------------------------------------------
# policy: what is refused
# ---------------------------------------------------------------------------


def test_rejects_non_image_content_under_a_renderable_extension():
    with pytest.raises(UploadRejected):
        inspect(zip_bytes(), "photo.png", "image/png")


def test_rejects_a_png_renamed_to_jpg():
    with pytest.raises(UploadRejected):
        inspect(image_bytes("PNG"), "photo.jpg", "image/jpeg")


def test_rejects_unrecognized_content_under_a_renderable_extension():
    # Unknown bytes in a .pdf would still be handed to the inline PDF viewer.
    with pytest.raises(UploadRejected):
        inspect(b"\x01\x02\x03 opaque payload", "report.pdf", "application/pdf")


@pytest.mark.parametrize(
    ("magic", "label"),
    [(b"MZ\x90\x00", "pe"), (b"\x7fELF\x02\x01", "elf"), (b"\xcf\xfa\xed\xfe\x07", "macho")],
)
def test_rejects_an_executable_wearing_a_document_extension(magic, label):
    with pytest.raises(UploadRejected) as excinfo:
        inspect(magic + b"\x00" * 64, "quarterly-report.docx")
    assert label in str(excinfo.value)


# ---------------------------------------------------------------------------
# policy: what is deliberately allowed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename", ["tool.exe", "driver.sys", "libcrypto.so", "tool"])
def test_allows_an_executable_under_an_honest_extension(filename):
    result = inspect(b"MZ\x90\x00" + b"\x00" * 64, filename)
    assert result.executable == "pe"


def test_allows_office_documents_which_are_zip_containers():
    result = inspect(zip_bytes("[Content_Types].xml"), "contract.docx")
    assert result.executable is None
    assert result.detected_content_type.startswith("application/")


@pytest.mark.parametrize(
    ("filename", "declared"),
    [
        ("page.html", "text/html"),
        ("logo.svg", "image/svg+xml"),
        ("build.sh", "text/x-shellscript"),
        ("bundle.tar.gz", "application/gzip"),
        ("app.js", "text/javascript"),
    ],
)
def test_allows_ordinary_developer_files(filename, declared):
    # Downloads are attachments and /preview requires an Authorization header,
    # so these are stored as-is rather than refused.
    result = inspect(b"<!DOCTYPE html>\n<html></html>\n", filename, declared)
    assert result.content_type == declared


def test_allows_an_archive_with_an_escaping_member_name():
    result = inspect(zip_bytes("../escape.txt"), "bundle.zip", "application/zip")
    assert result.executable is None


def test_allows_a_large_image_because_size_is_capped_elsewhere():
    payload = image_bytes(size=(2000, 2000))
    result = inspect(payload, "poster.png", "image/png")
    assert result.size == len(payload)
    assert result.content_type == "image/png"
