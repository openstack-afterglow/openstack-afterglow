"""백엔드 프록시 업로드: 검사 → quarantine → 저장 검증 → 승격."""

from __future__ import annotations

import hashlib
import io
import threading
import zipfile
from unittest.mock import MagicMock

import pytest
from PIL import Image


def png_bytes(size: tuple[int, int] = (40, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, "navy").save(buffer, format="PNG")
    return buffer.getvalue()


def zip_bytes(name: str = "notes/readme.txt") -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, "hello")
    return buffer.getvalue()


class FakeS3:
    """Minimal RGW stand-in that stores bytes and replays S3 ETag semantics."""

    def __init__(self, corrupt: bytes | None = None) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.types: dict[tuple[str, str], str] = {}
        self.metadata: dict[tuple[str, str], dict] = {}
        self.corrupt = corrupt
        self.copies: list[dict] = []
        self.deleted: list[tuple[str, str]] = []

    def head_bucket(self, Bucket):
        return {}

    def put_bucket_cors(self, **kwargs):
        return {}

    def delete_bucket_cors(self, **kwargs):
        return {}

    def upload_fileobj(self, Fileobj, Bucket, Key, ExtraArgs=None, Config=None, Callback=None):
        data = Fileobj.read()
        if Callback:
            Callback(len(data))
        self.objects[(Bucket, Key)] = self.corrupt if self.corrupt is not None else data
        self.types[(Bucket, Key)] = (ExtraArgs or {}).get("ContentType", "")
        self.metadata[(Bucket, Key)] = (ExtraArgs or {}).get("Metadata", {})

    def head_object(self, Bucket, Key):
        data = self.objects[(Bucket, Key)]
        return {
            "ContentLength": len(data),
            "ETag": f'"{hashlib.md5(data).hexdigest()}"',
            "ContentType": self.types.get((Bucket, Key), ""),
            "Metadata": self.metadata.get((Bucket, Key), {}),
        }

    def copy(self, CopySource, Bucket, Key, ExtraArgs=None):
        src = (CopySource["Bucket"], CopySource["Key"])
        self.copies.append({"source": CopySource, "bucket": Bucket, "key": Key, "extra": ExtraArgs})
        self.objects[(Bucket, Key)] = self.objects[src]
        # MetadataDirective defaults to COPY: type and user metadata ride along.
        self.types[(Bucket, Key)] = self.types.get(src, "")
        self.metadata[(Bucket, Key)] = self.metadata.get(src, {})

    def delete_object(self, Bucket, Key):
        self.deleted.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


def install_upload_stubs(monkeypatch, fake_s3) -> None:
    monkeypatch.setattr("app.api.object_storage.upload.s3_svc.get_user_s3_client", lambda *a, **kw: fake_s3)
    monkeypatch.setattr(
        "app.api.object_storage.upload.swift_svc.get_container_metadata",
        lambda *a, **kw: {"name": "test"},
    )


# ---------------------------------------------------------------------------
# stream_upload_to_quarantine / verify_quarantine_object / move_to_target
# ---------------------------------------------------------------------------


def test_stream_upload_uses_transfer_config_and_content_type():
    from app.services import s3 as s3_svc

    fake = MagicMock()
    stream = MagicMock()
    s3_svc.stream_upload_to_quarantine(fake, "test-quarantine", "obj.bin", stream, "application/zip")

    kwargs = fake.upload_fileobj.call_args.kwargs
    assert kwargs["Bucket"] == "test-quarantine"
    assert kwargs["Key"] == "obj.bin"
    assert kwargs["Fileobj"] is stream
    assert kwargs["ExtraArgs"] == {"ContentType": "application/zip"}
    cfg = kwargs["Config"]
    assert cfg.multipart_threshold == s3_svc.MULTIPART_THRESHOLD
    assert cfg.multipart_chunksize == s3_svc.MULTIPART_CHUNKSIZE
    assert cfg.max_concurrency == 4


def test_stream_upload_attaches_metadata_at_upload_time():
    from app.services import s3 as s3_svc

    fake = MagicMock()
    s3_svc.stream_upload_to_quarantine(
        fake, "q", "k", MagicMock(), "image/png", metadata={"sha256": "abc", "detected-content-type": "image/png"}
    )

    extra = fake.upload_fileobj.call_args.kwargs["ExtraArgs"]
    assert extra["ContentType"] == "image/png"
    assert extra["Metadata"] == {"sha256": "abc", "detected-content-type": "image/png"}


def test_stream_upload_callback_raises_when_cancel_event_set():
    from app.services import s3 as s3_svc

    captured: dict = {}
    fake = MagicMock()
    fake.upload_fileobj.side_effect = lambda **kw: captured.update(kw)

    cancel_event = threading.Event()
    s3_svc.stream_upload_to_quarantine(fake, "q", "k", MagicMock(), "text/plain", cancel_event=cancel_event)

    captured["Callback"](1024)
    cancel_event.set()
    with pytest.raises(s3_svc.UploadCanceled):
        captured["Callback"](1024)


def test_verify_quarantine_object_accepts_matching_single_part_etag():
    from app.services import s3 as s3_svc

    payload = b"hello!\n"
    fake = FakeS3()
    fake.objects[("q", "k")] = payload
    head = s3_svc.verify_quarantine_object(
        fake, "q", "k", expected_size=len(payload), expected_md5=hashlib.md5(payload).hexdigest()
    )
    assert head["ContentLength"] == len(payload)


def test_verify_quarantine_object_rejects_size_and_etag_mismatch():
    from app.services import s3 as s3_svc

    payload = b"hello!\n"
    fake = FakeS3()
    fake.objects[("q", "k")] = payload

    with pytest.raises(s3_svc.IntegrityError):
        s3_svc.verify_quarantine_object(fake, "q", "k", expected_size=99, expected_md5=hashlib.md5(payload).hexdigest())
    with pytest.raises(s3_svc.IntegrityError):
        s3_svc.verify_quarantine_object(fake, "q", "k", expected_size=len(payload), expected_md5="0" * 32)


def test_verify_quarantine_object_checks_multipart_part_count():
    from app.services import s3 as s3_svc

    size = 20 * 1024 * 1024  # 8 MiB chunks -> 3 parts
    fake = MagicMock()
    fake.head_object.return_value = {"ContentLength": size, "ETag": '"abc-3"'}
    assert s3_svc.verify_quarantine_object(fake, "q", "k", expected_size=size, expected_md5="ignored")

    fake.head_object.return_value = {"ContentLength": size, "ETag": '"abc-2"'}
    with pytest.raises(s3_svc.IntegrityError):
        s3_svc.verify_quarantine_object(fake, "q", "k", expected_size=size, expected_md5="ignored")


def test_verify_quarantine_object_does_not_download_the_object():
    from app.services import s3 as s3_svc

    payload = b"hello!\n"
    fake = MagicMock()
    fake.head_object.return_value = {"ContentLength": len(payload), "ETag": f'"{hashlib.md5(payload).hexdigest()}"'}
    s3_svc.verify_quarantine_object(
        fake, "q", "k", expected_size=len(payload), expected_md5=hashlib.md5(payload).hexdigest()
    )
    fake.get_object.assert_not_called()


def test_move_to_target_copies_then_deletes_quarantine():
    from app.services import s3 as s3_svc

    fake = MagicMock()
    fake.head_object.return_value = {"ContentLength": 1234, "ETag": '"abc123"', "ContentType": "application/pdf"}

    meta = s3_svc.move_to_target(fake, "test-quarantine", "test", "report.pdf")

    fake.copy.assert_called_once_with(
        CopySource={"Bucket": "test-quarantine", "Key": "report.pdf"}, Bucket="test", Key="report.pdf"
    )
    fake.delete_object.assert_called_once_with(Bucket="test-quarantine", Key="report.pdf")
    assert meta == {"name": "report.pdf", "bytes": 1234, "etag": "abc123", "content_type": "application/pdf"}


def test_move_to_target_removes_a_target_whose_size_disagrees():
    from app.services import s3 as s3_svc

    fake = MagicMock()
    fake.head_object.return_value = {"ContentLength": 10, "ETag": '"e"', "ContentType": "text/plain"}

    with pytest.raises(s3_svc.IntegrityError):
        s3_svc.move_to_target(fake, "test-quarantine", "test", "k", expected_size=11)

    fake.delete_object.assert_called_once_with(Bucket="test", Key="k")


# ---------------------------------------------------------------------------
# POST /upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_normal_flow(client, mock_conn, monkeypatch):
    """An inspected file is published with its verified digest and detected type."""
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = b"hello!\n"

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("hello.txt", payload, "text/plain")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["name"] == "hello.txt"
    assert body["bytes"] == 7
    assert body["sha256"] == hashlib.sha256(payload).hexdigest()
    assert body["detected_content_type"] == ""
    assert body["content_type"] == "text/plain"
    assert fake_s3.objects[("test", "hello.txt")] == payload
    assert ("test-quarantine", "hello.txt") not in fake_s3.objects


@pytest.mark.asyncio
async def test_upload_records_digest_and_detected_type_as_object_metadata(client, mock_conn, monkeypatch):
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = png_bytes()

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("photo.png", payload, "image/png")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["detected_content_type"] == "image/png"
    stored = fake_s3.metadata[("test", "photo.png")]
    assert stored["sha256"] == hashlib.sha256(payload).hexdigest()
    assert stored["detected-content-type"] == "image/png"
    # MetadataDirective defaults to COPY, so the inspected type survives promotion.
    assert fake_s3.types[("test", "photo.png")] == "image/png"


@pytest.mark.asyncio
async def test_upload_without_browser_checksum_is_accepted(client, mock_conn, monkeypatch):
    """Files above the browser hashing cap still upload; storage is still verified."""
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("hello.txt", b"hello!\n", "text/plain")},
    )

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_upload_rejects_nonexistent_container(client, mock_conn, monkeypatch):
    monkeypatch.setattr(
        "app.api.object_storage.upload.swift_svc.get_container_metadata",
        MagicMock(side_effect=Exception("not found")),
    )

    resp = await client.post(
        "/api/v1/object-storage/other-bucket/upload",
        files={"file": ("x.bin", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_upload_rejects_spoofed_png_before_touching_storage(client, mock_conn, monkeypatch):
    fake_s3 = MagicMock()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = zip_bytes()

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("x.png", payload, "image/png")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("보안 검사 실패")
    fake_s3.upload_fileobj.assert_not_called()


@pytest.mark.asyncio
async def test_upload_rejects_disguised_executable(client, mock_conn, monkeypatch):
    fake_s3 = MagicMock()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = b"MZ\x90\x00" + b"\x00" * 64

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("notes.txt", payload, "text/plain")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 400
    fake_s3.upload_fileobj.assert_not_called()


@pytest.mark.asyncio
async def test_upload_accepts_an_office_document(client, mock_conn, monkeypatch):
    """A DOCX is a ZIP container; the policy must not refuse it."""
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = zip_bytes("[Content_Types].xml")

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={
            "file": (
                "contract.docx",
                payload,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 200, resp.text
    assert ("test", "contract.docx") in fake_s3.objects


@pytest.mark.asyncio
async def test_upload_accepts_an_honestly_named_executable(client, mock_conn, monkeypatch):
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = b"MZ\x90\x00" + b"\x00" * 64

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("tool.exe", payload, "application/octet-stream")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_upload_rejects_browser_checksum_mismatch(client, mock_conn, monkeypatch):
    fake_s3 = MagicMock()
    install_upload_stubs(monkeypatch, fake_s3)

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("hello.txt", b"hello!\n", "text/plain")},
        data={"sha256": hashlib.sha256(b"different").hexdigest()},
    )

    assert resp.status_code == 400
    assert resp.json()["detail"].startswith("무결성 검증 실패")
    fake_s3.upload_fileobj.assert_not_called()


@pytest.mark.asyncio
async def test_upload_rejects_malformed_browser_checksum(client, mock_conn, monkeypatch):
    fake_s3 = MagicMock()
    install_upload_stubs(monkeypatch, fake_s3)

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("hello.txt", b"hello!\n", "text/plain")},
        data={"sha256": "not-a-digest"},
    )

    assert resp.status_code == 422
    fake_s3.upload_fileobj.assert_not_called()


@pytest.mark.asyncio
async def test_upload_reports_bad_gateway_when_storage_differs(client, mock_conn, monkeypatch):
    """Stored bytes that disagree with the upload never reach the target bucket."""
    fake_s3 = FakeS3(corrupt=b"corrupted-by-storage")
    install_upload_stubs(monkeypatch, fake_s3)
    payload = b"hello!\n"

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("hello.txt", payload, "text/plain")},
        data={"sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 502
    assert not fake_s3.copies
    assert ("test-quarantine", "hello.txt") in fake_s3.deleted


@pytest.mark.asyncio
async def test_upload_stream_exception_cleans_quarantine(client, mock_conn, monkeypatch):
    fake_s3 = MagicMock()
    fake_s3.upload_fileobj.side_effect = RuntimeError("RGW 네트워크 오류")
    install_upload_stubs(monkeypatch, fake_s3)

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("crash.txt", b"data", "text/plain")},
    )

    assert resp.status_code == 500
    fake_s3.delete_object.assert_called_once_with(Bucket="test-quarantine", Key="crash.txt")


@pytest.mark.asyncio
async def test_upload_with_prefix(client, mock_conn, monkeypatch):
    fake_s3 = FakeS3()
    install_upload_stubs(monkeypatch, fake_s3)
    payload = b"x"

    resp = await client.post(
        "/api/v1/object-storage/test/upload",
        files={"file": ("notes.md", payload, "text/markdown")},
        data={"prefix": "docs/", "sha256": hashlib.sha256(payload).hexdigest()},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "docs/notes.md"
    assert ("test", "docs/notes.md") in fake_s3.objects


# ---------------------------------------------------------------------------
# CORS 적용 회귀 (ensure_bucket idempotent)
# ---------------------------------------------------------------------------


def test_ensure_bucket_existing_reapplies_cors():
    from app.services import s3 as s3_svc

    fake = MagicMock()
    fake.head_bucket.return_value = {}
    s3_svc.ensure_bucket(fake, "test-quarantine")

    fake.create_bucket.assert_not_called()
    fake.put_bucket_cors.assert_called_once()


def test_ensure_bucket_creates_when_missing_then_cors():
    from botocore.exceptions import ClientError

    from app.services import s3 as s3_svc

    fake = MagicMock()
    fake.head_bucket.side_effect = ClientError({"Error": {"Code": "NoSuchBucket"}}, "HeadBucket")
    s3_svc.ensure_bucket(fake, "test-quarantine")

    fake.create_bucket.assert_called_once_with(Bucket="test-quarantine")
    fake.put_bucket_cors.assert_called_once()


# ---------------------------------------------------------------------------
# 보안 패치 — path traversal sanitize / CORS 화이트리스트
# ---------------------------------------------------------------------------


def test_sanitize_object_name_strips_path_traversal():
    from app.api.object_storage.containers import _sanitize_object_name

    assert _sanitize_object_name("../../../etc/passwd") == "etc/passwd"
    assert _sanitize_object_name("foo/../bar") == "foo/bar"
    assert _sanitize_object_name("/././etc/foo") == "etc/foo"
    assert _sanitize_object_name("..") == "unnamed"
    assert _sanitize_object_name("/") == "unnamed"


def test_sanitize_object_name_strips_control_chars():
    from app.api.object_storage.containers import _sanitize_object_name

    assert _sanitize_object_name("foo\x00bar") == "foobar"
    assert _sanitize_object_name("foo\nbar") == "foobar"
    assert _sanitize_object_name("foo\x7fbar") == "foobar"


def test_sanitize_object_name_truncates_long():
    from app.api.object_storage.containers import _sanitize_object_name

    assert len(_sanitize_object_name("a" * 2000)) == 1024


def test_put_bucket_cors_uses_origin_whitelist():
    from unittest.mock import patch

    from app.services import s3 as s3_svc

    fake = MagicMock()
    mock_settings = MagicMock()
    mock_settings.cors_origin_list = ["https://app.example.com", "https://staging.example.com"]
    with patch("app.config.get_settings", return_value=mock_settings):
        s3_svc._put_bucket_cors(fake, "test-bucket")

    rule = fake.put_bucket_cors.call_args.kwargs["CORSConfiguration"]["CORSRules"][0]
    assert rule["AllowedOrigins"] == ["https://app.example.com", "https://staging.example.com"]
    assert "*" not in rule["AllowedOrigins"]
    assert "*" not in rule["AllowedHeaders"]


def test_put_bucket_cors_disables_when_no_whitelist():
    from unittest.mock import patch

    from app.services import s3 as s3_svc

    fake = MagicMock()
    mock_settings = MagicMock()
    mock_settings.cors_origin_list = []
    with patch("app.config.get_settings", return_value=mock_settings):
        s3_svc._put_bucket_cors(fake, "test-bucket")

    fake.delete_bucket_cors.assert_called_once_with(Bucket="test-bucket")
    fake.put_bucket_cors.assert_not_called()
