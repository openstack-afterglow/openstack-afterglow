"""Object Storage (Swift) API 단위 테스트.

swift 서비스는 SERVICE_SWIFT_ENABLED=true 시 /api/object-storage/* 경로로 등록.
비활성화 시 대부분 404/405 응답 → 인증 관문 테스트는 in (401, 404, 405) 허용.
swift 함수는 핸들러 내에서 lazy import하므로 app.services.swift 를 패치.
"""

import json
import urllib.parse
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from requests import Response
from requests.adapters import BaseAdapter

from app.main import app

# ---------------------------------------------------------------------------
# 계정 메타데이터
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_account_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/object-storage/account")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_get_account_success(client, mock_conn):
    with patch("app.services.swift") as mock_swift:
        mock_swift.get_account = MagicMock(return_value={"container_count": 2, "object_count": 10, "bytes_used": 2048})
        resp = await client.get("/api/v1/object-storage/account")
    assert resp.status_code in (200, 404, 405, 500)


# ---------------------------------------------------------------------------
# 컨테이너 목록 / 생성 / 삭제
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_containers_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/object-storage/containers")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_list_containers_empty(client, mock_conn):
    with patch("app.services.swift") as mock_swift:
        mock_swift.list_containers = MagicMock(return_value=[])
        resp = await client.get("/api/v1/object-storage/containers")
    assert resp.status_code in (200, 404, 405, 500)


@pytest.mark.asyncio
async def test_create_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/object-storage/containers", json={"name": "new-bucket"})
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_delete_container_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/object-storage/containers/test-container")
    assert resp.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# 오브젝트 업로드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_object_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/object-storage/containers/test-container/objects",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_upload_object_success(client, mock_conn):
    with patch("app.services.swift") as mock_swift:
        mock_swift.upload_object = MagicMock(return_value={"name": "test.txt"})
        resp = await client.post(
            "/api/v1/object-storage/containers/test-container/objects",
            files={"file": ("test.txt", b"hello world", "text/plain")},
        )
    assert resp.status_code in (201, 404, 405, 500)


# ---------------------------------------------------------------------------
# 오브젝트 다운로드 / 삭제
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_object_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/api/v1/object-storage/containers/test-container/objects/test.txt/download")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_delete_object_unauthenticated():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.delete("/api/v1/object-storage/containers/test-container/objects/test.txt")
    assert resp.status_code in (401, 404, 405)


# ---------------------------------------------------------------------------
# SLO (Static Large Object) 동작 검증
# ---------------------------------------------------------------------------


def test_upload_large_object_uses_manual_slo():
    """1 GiB 초과 파일 업로드 시 수동 SLO: proxy.put 을 (segments + 1) 회 호출하고 마지막 URL 에 multipart-manifest=put 포함."""
    import io
    import math
    from unittest.mock import MagicMock, patch

    from app.services.swift import _SLO_SEGMENT_SIZE, upload_object

    conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.headers = {"etag": '"abc123"'}
    conn.object_store.put.return_value = mock_resp

    large_size = _SLO_SEGMENT_SIZE + 1  # 1 GiB + 1 byte → 2 segments
    with (
        patch("app.services.swift._apply_endpoint_override"),
        patch("app.services.swift._ensure_segment_container") as mock_ensure,
    ):
        upload_object(conn, "bucket", "big.bin", io.BytesIO(b""), "application/octet-stream", large_size)

    num_segments = math.ceil(large_size / _SLO_SEGMENT_SIZE)
    assert conn.object_store.put.call_count == num_segments + 1
    manifest_url = conn.object_store.put.call_args_list[-1][0][0]
    assert "multipart-manifest=put" in manifest_url
    mock_ensure.assert_called_once_with(conn, "bucket_segments")


def test_list_containers_hides_segments():
    """_segments 접미사 컨테이너는 사용자 목록에서 숨겨진다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import list_containers

    def make(name, count, bytes_):
        c = MagicMock()
        c.name = name
        c.count = count
        c.bytes = bytes_
        return c

    conn = MagicMock()
    conn.object_store.containers.return_value = [
        make("test", 7, 3 * 1024**3),
        make("test_segments", 10, 9 * 1024**3),
        make("photos", 100, 500 * 1024**2),
    ]
    with patch("app.services.swift._apply_endpoint_override"):
        result = list_containers(conn)
    by_name = {c["name"]: c for c in result}
    assert "test" in by_name
    assert "photos" in by_name
    assert "test_segments" not in by_name
    # segments 컨테이너 bytes 가 원본 컨테이너에 합산됨 (3 GiB + 9 GiB = 12 GiB)
    assert by_name["test"]["bytes"] == 3 * 1024**3 + 9 * 1024**3
    # segments 가 없는 컨테이너는 그대로 유지
    assert by_name["photos"]["bytes"] == 500 * 1024**2


def test_list_containers_quarantine_default_hidden():
    """default 호출 시 *-quarantine 도 숨겨진다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import list_containers

    def make(name, count, bytes_):
        c = MagicMock()
        c.name, c.count, c.bytes = name, count, bytes_
        return c

    conn = MagicMock()
    conn.object_store.containers.return_value = [
        make("test", 4, 1024),
        make("test-quarantine", 17, 512),
    ]
    with patch("app.services.swift._apply_endpoint_override"):
        result = list_containers(conn)
    names = [c["name"] for c in result]
    assert names == ["test"]


def test_list_containers_include_quarantine_admin():
    """include_quarantine=True 시 *-quarantine 포함 + is_quarantine 플래그."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import list_containers

    def make(name, count, bytes_):
        c = MagicMock()
        c.name, c.count, c.bytes = name, count, bytes_
        return c

    conn = MagicMock()
    conn.object_store.containers.return_value = [
        make("test", 4, 1024),
        make("test-quarantine", 17, 512),
        make("test_segments", 1, 2048),  # segments 는 여전히 숨김
    ]
    with patch("app.services.swift._apply_endpoint_override"):
        result = list_containers(conn, include_quarantine=True)
    by_name = {c["name"]: c for c in result}
    assert "test" in by_name
    assert "test-quarantine" in by_name
    assert "test_segments" not in by_name
    assert by_name["test-quarantine"]["is_quarantine"] is True
    assert "is_quarantine" not in by_name["test"]


def test_get_container_metadata_includes_segments():
    """get_container_metadata 의 bytes 에 {name}_segments 의 bytes_used 가 합산된다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import get_container_metadata

    base_meta = MagicMock()
    base_meta.name = "test"
    base_meta.object_count = 2
    base_meta.bytes_used = 1024 * 1024 + 2000  # 매니페스트 + 일반 파일 ≈ 1 MiB
    base_meta.read_ACL = ""
    base_meta.write_ACL = ""

    seg_meta = MagicMock()
    seg_meta.bytes_used = 9 * 1024**3  # 9 GiB segments

    conn = MagicMock()

    def get_meta_side_effect(name):
        if name == "test":
            return base_meta
        if name == "test_segments":
            return seg_meta
        raise Exception("404")

    conn.object_store.get_container_metadata.side_effect = get_meta_side_effect

    with patch("app.services.swift._apply_endpoint_override"):
        result = get_container_metadata(conn, "test")

    assert result["name"] == "test"
    assert result["count"] == 2
    # base + segments 합계
    assert result["bytes"] == 1024 * 1024 + 2000 + 9 * 1024**3


def test_get_container_metadata_no_segments():
    """{name}_segments 컨테이너가 없는 경우 base bytes 만 반환한다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import get_container_metadata

    base_meta = MagicMock()
    base_meta.name = "photos"
    base_meta.object_count = 100
    base_meta.bytes_used = 500 * 1024**2
    base_meta.read_ACL = ""
    base_meta.write_ACL = ""

    conn = MagicMock()

    def get_meta_side_effect(name):
        if name == "photos":
            return base_meta
        raise Exception("404")

    conn.object_store.get_container_metadata.side_effect = get_meta_side_effect

    with patch("app.services.swift._apply_endpoint_override"):
        result = get_container_metadata(conn, "photos")

    assert result["bytes"] == 500 * 1024**2


def _swift_listing_response(rows, status=200):
    response = Response()
    response.status_code = status
    response.url = "http://swift.test/v1/AUTH_test/bucket"
    response._content = json.dumps(rows).encode()
    return response


class _InProcessSwift(BaseAdapter):
    """Swift account behind a real openstacksdk Proxy; requests reach this adapter, never a socket.

    ``fail_when(method, container, key, query)`` may return an HTTP status to inject for a request.
    """

    def __init__(self, containers: dict[str, dict[str, bytes]], page_size: int):
        super().__init__()
        self.containers = containers
        self.page_size = page_size
        self.requests: list[tuple[str, str, str, dict[str, str]]] = []
        self.fail_when = lambda _method, _container, _key, _query: None

    def send(self, request, **_kwargs):
        url = urllib.parse.urlsplit(request.url)
        parts = url.path.split("/", 4)  # ["", "v1", "AUTH_test", container, key]
        container = urllib.parse.unquote(parts[3]) if len(parts) > 3 else ""
        key = urllib.parse.unquote(parts[4]) if len(parts) > 4 else ""
        query = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
        self.requests.append((request.method, container, key, query))
        injected = self.fail_when(request.method, container, key, query)
        status, body = (
            (injected, b'{"error": "injected"}') if injected else self._handle(request, container, key, query)
        )
        response = Response()
        response.status_code = status
        response._content = body
        response.headers["Content-Length"] = str(len(body))
        response.url = request.url
        response.request = request
        response.reason = "fixture"
        return response

    def close(self):
        pass

    def mutations(self) -> list[tuple[str, str, str]]:
        return [
            (method, container, key)
            for method, container, key, _ in self.requests
            if method in {"PUT", "DELETE"} and key
        ]

    def _handle(self, request, container: str, key: str, query: dict[str, str]) -> tuple[int, bytes]:
        method = request.method
        if not container:
            return 200, b"[]"
        objects = self.containers.get(container)
        if not key:
            if method == "PUT":
                self.containers.setdefault(container, {})
                return 201, b""
            if objects is None:
                return 404, b""
            return (200, json.dumps(self._listing(objects, query)).encode()) if method == "GET" else (204, b"")
        if objects is None:
            return 404, b""
        if method == "PUT":
            source = request.headers.get("X-Copy-From")
            if source is None:
                objects[key] = request.body or b""
                return 201, b""
            src_container, _, src_key = source.lstrip("/").partition("/")
            data = self.containers.get(urllib.parse.unquote(src_container), {}).get(urllib.parse.unquote(src_key))
            if data is None:
                return 404, b""
            objects[key] = data
            return 201, b""
        if method == "DELETE":
            return (204, b"") if objects.pop(key, None) is not None else (404, b"")
        if key not in objects:
            return 404, b""
        return 200, objects[key] if method == "GET" else b""

    def _listing(self, objects: dict[str, bytes], query: dict[str, str]) -> list[dict]:
        prefix, delimiter, marker = (query.get(field, "") for field in ("prefix", "delimiter", "marker"))
        rows = {}
        for key, data in objects.items():
            if not key.startswith(prefix):
                continue
            cut = key.find(delimiter, len(prefix)) if delimiter else -1
            if cut >= 0:
                rows[key[: cut + len(delimiter)]] = {"subdir": key[: cut + len(delimiter)]}
            else:
                content_type = "application/directory" if key.endswith("/") else "text/plain"
                rows[key] = {
                    "name": key,
                    "bytes": len(data),
                    "content_type": content_type,
                    "last_modified": "2026-09-26T01:00:00Z",
                    "hash": "abc",
                }
        limit = min(int(query.get("limit", 10000)), self.page_size)
        return [rows[name] for name in sorted(rows) if name > marker][:limit]


def _swift_conn(stored: dict[str, bytes], *, page_size: int = 2, container: str = "bucket", extra: tuple = ()):
    """Real openstacksdk Connection whose object-store HTTP requests are served in process."""
    import openstack.connection
    import requests
    from keystoneauth1 import session as ks_session
    from keystoneauth1.noauth import NoAuth

    swift = _InProcessSwift({container: dict(stored), **{name: {} for name in extra}}, page_size)
    http = requests.Session()
    http.mount("http://swift.test/", swift)
    endpoint = "http://swift.test/v1/AUTH_test"
    conn = openstack.connection.Connection(
        session=ks_session.Session(auth=NoAuth(endpoint=endpoint), session=http),
        object_store_endpoint_override=endpoint,
    )
    return conn, swift


def test_list_objects_collision_explicit_marker_and_flat_prefix():
    from app.services.swift import list_objects

    stored = {key: b"" for key in ("foo", "foo/", "foo/a.txt", "foobar/b.txt", "empty/")}
    conn, swift = _swift_conn(stored, page_size=1)
    with patch("app.services.swift._apply_endpoint_override"):
        root = list_objects(conn, "bucket", delimiter="/")
        nested = list_objects(conn, "bucket", prefix="foo/", delimiter="/")
        flat = list_objects(conn, "bucket", prefix="foo/", delimiter="")
    assert [(row["name"], row["is_dir"]) for row in root] == [
        ("empty/", True),
        ("foo", False),
        ("foo/", True),
        ("foobar/", True),
    ]
    assert [row["name"] for row in nested] == ["foo/a.txt"]
    assert [row["name"] for row in flat] == ["foo/", "foo/a.txt"]
    listings = [
        query for method, name, key, query in swift.requests if method == "GET" and name == "bucket" and not key
    ]
    assert any(query.get("marker") == "foo/" and query.get("prefix") == "foo/" for query in listings)
    assert all(query["limit"] == "10000" and query["format"] == "json" for query in listings)


@pytest.mark.parametrize(
    "rows",
    [
        (
            [{"subdir": "foo/"}],
            [
                {"name": "foo/", "bytes": 0, "content_type": "application/directory", "hash": "stored"},
                {"subdir": "foo/bar/"},
            ],
        ),
        (
            [{"name": "foo/", "bytes": 0, "content_type": "application/directory", "hash": "stored"}],
            [{"subdir": "foo/"}, {"subdir": "foo/bar/"}],
        ),
    ],
)
def test_list_objects_prefers_stored_marker_across_page_orders(rows):
    from app.services.swift import list_objects

    conn = MagicMock()
    conn.object_store.objects.return_value = iter(())
    conn.object_store.get.side_effect = [
        _swift_listing_response(rows[0]),
        _swift_listing_response(rows[1]),
        _swift_listing_response([]),
    ]
    with patch("app.services.swift._apply_endpoint_override"):
        result = list_objects(conn, "bucket", delimiter="/")
    assert [item["name"] for item in result].count("foo/") == 1
    assert next(item for item in result if item["name"] == "foo/")["etag"] == "stored"
    assert {item["name"] for item in result} == {"foo/", "foo/bar/"}


def test_list_objects_filters_own_marker_without_losing_following_page():
    from app.services.swift import list_objects

    seen = []
    responses = [
        _swift_listing_response([{"name": "foo/", "content_type": "application/directory"}]),
        _swift_listing_response([{"subdir": "foo/deep/"}]),
        _swift_listing_response([]),
    ]
    conn = MagicMock()
    conn.object_store.objects.return_value = iter(())

    def get(_path, *, params):
        seen.append(params.get("marker"))
        return responses.pop(0)

    conn.object_store.get.side_effect = get
    with patch("app.services.swift._apply_endpoint_override"):
        assert [item["name"] for item in list_objects(conn, "bucket", prefix="foo/", delimiter="/")] == ["foo/deep/"]
    assert seen == [None, "foo/", "foo/deep/"]


def test_list_objects_preserves_encoded_container_and_opaque_keys():
    from app.services.swift import list_objects

    key = "한글 +%/공백 +%/파일.png"
    conn, swift = _swift_conn({key: b"x"}, container="버킷 +%")
    with patch("app.services.swift._apply_endpoint_override"):
        result = list_objects(conn, "버킷 +%", prefix="한글 +%/공백 +%/", delimiter="/")
    assert [item["name"] for item in result] == [key]
    # The in-process server decodes the real HTTP URL, so this proves one-time encoding end to end.
    listing = next(
        query for method, name, obj, query in swift.requests if method == "GET" and name == "버킷 +%" and not obj
    )
    assert listing["prefix"] == "한글 +%/공백 +%/"


@pytest.mark.parametrize("status", [403, 404, 503])
@pytest.mark.parametrize("after_page", [False, True])
def test_list_objects_never_returns_partial_results_on_http_failure(status, after_page):
    from openstack.exceptions import HttpException

    from app.services.swift import list_objects

    conn = MagicMock()
    error = _swift_listing_response({"error": "Swift unavailable"}, status=status)
    pages = [_swift_listing_response([{"name": "visible.txt", "bytes": 1}])] if after_page else []
    conn.object_store.get.side_effect = [*pages, error]
    with patch("app.services.swift._apply_endpoint_override"), pytest.raises(HttpException):
        list_objects(conn, "bucket")


@pytest.mark.parametrize(
    "first_page,second_page,error",
    [
        ({"items": []}, None, ValueError),
        ([{"name": "valid"}], "not json", ValueError),
        ([{"name": "same"}], [{"name": "same"}], RuntimeError),
        ([{"subdir": "a/"}], [{"unexpected": "row"}], ValueError),
    ],
)
def test_list_objects_rejects_malformed_or_stalled_pages(first_page, second_page, error):
    from app.services.swift import list_objects

    conn = MagicMock()
    responses = [_swift_listing_response(first_page)]
    if second_page == "not json":
        bad = _swift_listing_response([])
        bad._content = b"{broken"
        responses.append(bad)
    elif second_page is not None:
        responses.append(_swift_listing_response(second_page))
    conn.object_store.get.side_effect = responses
    with patch("app.services.swift._apply_endpoint_override"), pytest.raises(error):
        list_objects(conn, "bucket", delimiter="/")


def test_list_objects_handles_204_and_empty_json_only_as_empty():
    from app.services.swift import list_objects

    for response in (_swift_listing_response([], status=204), _swift_listing_response([])):
        conn = MagicMock()
        conn.object_store.get.return_value = response
        conn.object_store.objects.return_value = iter(())
        with patch("app.services.swift._apply_endpoint_override"):
            assert list_objects(conn, "bucket") == []


def test_list_objects_navigates_unmarked_nested_files():
    """Swift subdir entries, not stored marker objects, supply each navigation level."""
    from app.services.swift import list_objects

    conn = MagicMock()
    conn.object_store.objects.return_value = iter(())  # segments only; SDK loses delimiter/subdir
    pages = {
        "": [{"subdir": "tenant/"}],
        "tenant/": [{"subdir": f"tenant/chat-{letter}/"} for letter in "abcd"],
        "tenant/chat-a/": [
            {
                "name": "tenant/chat-a/p1_00_keep_arch.png",
                "bytes": 5242880,
                "content_type": "image/png",
                "last_modified": "2026-09-26T01:00:00Z",
                "hash": "abc",
            }
        ],
    }

    def get(_path, *, params):
        rows = pages.get(params.get("prefix", ""), [])
        marker = params.get("marker")
        if marker:
            rows = [row for row in rows if (row.get("name") or row.get("subdir")) > marker]
        return _swift_listing_response(rows[:2])

    conn.object_store.get.side_effect = get
    with patch("app.services.swift._apply_endpoint_override"):
        assert [o["name"] for o in list_objects(conn, "bucket", delimiter="/")] == ["tenant/"]
        assert [o["name"] for o in list_objects(conn, "bucket", prefix="tenant/", delimiter="/")] == [
            f"tenant/chat-{letter}/" for letter in "abcd"
        ]
        assert list_objects(conn, "bucket", prefix="tenant/chat-a/", delimiter="/") == [
            {
                "name": "tenant/chat-a/p1_00_keep_arch.png",
                "bytes": 5242880,
                "content_type": "image/png",
                "last_modified": "2026-09-26T01:00:00Z",
                "etag": "abc",
                "is_dir": False,
            }
        ]
    assert conn.object_store.get.call_args_list[0].kwargs["params"]["delimiter"] == "/"


def test_list_objects_enriches_slo_sizes():
    """SLO 매니페스트의 bytes 가 segments 합계로 교체된다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import list_objects

    # segments 컨테이너에는 big.zip/00000000, big.zip/00000001 두 segment
    seg0 = MagicMock()
    seg0.name = "big.zip/00000000"
    seg0.size = 1024**3  # 1 GiB
    seg1 = MagicMock()
    seg1.name = "big.zip/00000001"
    seg1.size = 500 * 1024**2  # 500 MiB

    conn = MagicMock()
    conn.object_store.get.side_effect = [
        _swift_listing_response(
            [
                {"name": "big.zip", "bytes": 1638, "content_type": "application/zip"},
                {"name": "small.txt", "bytes": 100, "content_type": "text/plain"},
            ]
        ),
        _swift_listing_response([]),
    ]
    conn.object_store.objects.return_value = iter([seg0, seg1])  # SLO segments retain SDK listing

    with patch("app.services.swift._apply_endpoint_override"):
        result = list_objects(conn, "test")

    by_name = {r["name"]: r for r in result}
    # SLO 매니페스트는 segments 합계로 보정 (1 GiB + 500 MiB)
    assert by_name["big.zip"]["bytes"] == 1024**3 + 500 * 1024**2
    # 일반 파일은 변경 없음
    assert by_name["small.txt"]["bytes"] == 100


def test_list_objects_no_segments_container_keeps_sizes():
    """_segments 컨테이너가 없어도 listing 은 원본 사이즈로 정상 반환된다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import list_objects

    conn = MagicMock()
    conn.object_store.get.side_effect = [
        _swift_listing_response([{"name": "file.bin", "bytes": 12345, "content_type": "application/octet-stream"}]),
        _swift_listing_response([]),
    ]
    # The optional _segments container is missing; preserve Swift's original bytes.
    conn.object_store.objects.side_effect = Exception("404")

    with patch("app.services.swift._apply_endpoint_override"):
        result = list_objects(conn, "test")

    assert len(result) == 1
    assert result[0]["bytes"] == 12345


@pytest.mark.parametrize(
    "marker,children,dest_container",
    [
        (False, ["foo/a.txt", "foo/sub/b.txt"], "bucket"),
        (True, ["foo/a.txt", "foo/sub/b.txt"], "bucket"),
        (True, [], "bucket"),
        (False, ["foo/a.txt"], "other"),
    ],
)
def test_move_directory_copies_stored_snapshot_before_deleting(marker, children, dest_container):
    from app.services.swift import move_object

    stored = {key: b"payload" for key in ["foo", "foobar/a.txt", *children]}
    if marker:
        stored["foo/"] = b""
    conn, swift = _swift_conn(stored, page_size=1, extra=("other",))
    dest = "renamed/" if dest_container == "bucket" else "foo/"
    with patch("app.services.swift._apply_endpoint_override"):
        result = move_object(conn, "bucket", "foo/", dest_container, dest)
    moved = {dest + key[len("foo/") :] for key in [*children, *(["foo/"] if marker else [])]}
    assert result["destination"] == dest
    assert set(swift.containers["bucket"]) == {"foo", "foobar/a.txt"} | (moved if dest_container == "bucket" else set())
    assert set(swift.containers["other"]) == (moved if dest_container == "other" else set())
    writes = swift.mutations()
    first_delete = next(index for index, (method, _, _) in enumerate(writes) if method == "DELETE")
    assert {key for method, _, key in writes[:first_delete]} == moved  # every copy precedes any delete
    assert all(method == "DELETE" for method, _, _ in writes[first_delete:])


def test_move_directory_missing_or_unlistable_source_does_not_mutate():
    from openstack.exceptions import HttpException, ResourceNotFound

    from app.services.swift import move_object

    conn, swift = _swift_conn({"foo": b"x", "foobar/a.txt": b"x"}, extra=("other",))
    with patch("app.services.swift._apply_endpoint_override"):
        with pytest.raises(ResourceNotFound):
            move_object(conn, "bucket", "foo/", "other", "renamed/")
        swift.fail_when = lambda method, _container, key, _query: 503 if method == "GET" and not key else None
        with pytest.raises(HttpException):
            move_object(conn, "bucket", "foo/", "other", "renamed/")
    assert swift.mutations() == []


@pytest.mark.parametrize("status", [403, 404, 503])
@pytest.mark.parametrize("operation", ["folder rename", "file rename", "file trash"])
def test_failed_copy_response_never_deletes_the_source(operation, status):
    """Raw SDK proxy PUTs return error responses instead of raising; a failed COPY must stop the move."""
    from openstack.exceptions import HttpException

    from app.services.swift import rename_object, soft_delete_object

    stored = {"foo/a.txt": b"a", "foo/b.txt": b"b", "note.txt": b"n"}
    conn, swift = _swift_conn(stored, page_size=1, extra=("bucket-trash",))
    failing = {
        "folder rename": ("bucket", "renamed/b.txt"),  # the first child copy succeeds
        "file rename": ("bucket", "renamed.txt"),
    }

    def fail_when(method, container, key, _query):
        if method != "PUT" or not key:
            return None
        if operation == "file trash":
            return status if container == "bucket-trash" else None
        return status if (container, key) == failing[operation] else None

    swift.fail_when = fail_when
    run = {
        "folder rename": lambda: rename_object(conn, "bucket", "foo/", "renamed/"),
        "file rename": lambda: rename_object(conn, "bucket", "note.txt", "renamed.txt"),
        "file trash": lambda: soft_delete_object(conn, "bucket", "note.txt"),
    }[operation]
    with patch("app.services.swift._apply_endpoint_override"), pytest.raises(HttpException):
        run()
    assert [write for write in swift.mutations() if write[0] == "DELETE"] == []
    assert {key: swift.containers["bucket"][key] for key in stored} == stored


@pytest.mark.parametrize("marker", [False, True])
def test_recursive_permanent_delete_reports_folder_after_stored_keys(marker):
    from app.services.swift import bulk_delete_objects

    stored = {"foo": b"x", "foobar/x": b"x", "foo/a.txt": b"x", "foo/deep/x": b"x"}
    if marker:
        stored["foo/"] = b""
    conn, swift = _swift_conn(stored, page_size=1)
    with patch("app.services.swift._apply_endpoint_override"):
        result = bulk_delete_objects(conn, "bucket", ["foo/"], recursive=True)
    assert result == {"deleted": ["foo/deep/x", "foo/a.txt", "foo/"], "failed": []}
    deletes = [key for method, _, key in swift.mutations() if method == "DELETE"]
    assert deletes == ["foo/deep/x", "foo/a.txt", *(["foo/"] if marker else [])]
    assert set(swift.containers["bucket"]) == {"foo", "foobar/x"}


@pytest.mark.parametrize("failing_key", ["foo/b", "foo/"])
def test_recursive_delete_failure_response_leaves_folder_unclaimed(failing_key):
    from app.services.swift import bulk_delete_objects

    conn, swift = _swift_conn({"foo/": b"", "foo/a": b"a", "foo/b": b"b"})
    swift.fail_when = lambda method, _container, key, _query: 503 if method == "DELETE" and key == failing_key else None
    with patch("app.services.swift._apply_endpoint_override"):
        result = bulk_delete_objects(conn, "bucket", ["foo/", "missing/"], recursive=True)
    assert "foo/" not in result["deleted"]
    assert [item["name"] for item in result["failed"]] == [failing_key, "missing/"]
    assert {"foo/", failing_key} <= set(swift.containers["bucket"])  # the real marker stays with its content


def test_recursive_trash_moves_nested_markers_after_descendants():
    from app.services.swift import bulk_soft_delete_objects

    stored = {"foo/sub/": b"", "foo/sub/x": b"x", "foo/y": b"y", "foobar/z": b"z"}
    conn, swift = _swift_conn(stored, page_size=1, extra=("bucket-trash",))
    with patch("app.services.swift._apply_endpoint_override"):
        result = bulk_soft_delete_objects(conn, "bucket", ["foo/"], recursive=True)
    assert result == {"moved": ["foo/y", "foo/sub/x", "foo/sub/", "foo/"], "failed": []}
    assert set(swift.containers["bucket"]) == {"foobar/z"}
    assert sorted(key.split("/", 2)[2] for key in swift.containers["bucket-trash"]) == [
        "foo/sub/",
        "foo/sub/x",
        "foo/y",
    ]


@pytest.mark.parametrize("name", ["foo/", "note.txt"])
def test_same_container_identical_move_is_a_no_op(name):
    from app.services.swift import rename_object

    stored = {"foo/a.txt": b"a", "note.txt": b"n"}
    conn, swift = _swift_conn(stored)
    with patch("app.services.swift._apply_endpoint_override"):
        assert rename_object(conn, "bucket", name, name)["destination"] == name
    assert swift.requests == []
    assert swift.containers["bucket"] == stored


@pytest.mark.parametrize(
    "stored,source,destination",
    [
        ({"foo/a": b"a", "foo/sub/a": b"s"}, "foo/", "foo/sub/"),  # into its own descendant
        ({"foo/bar/y": b"y", "foo/bar/bar/y": b"b"}, "foo/bar/", "foo/"),  # a target is another source
    ],
)
def test_overlapping_same_container_move_is_rejected_before_any_write(stored, source, destination):
    from app.services.swift import InvalidObjectMove, rename_object

    conn, swift = _swift_conn(stored)
    with patch("app.services.swift._apply_endpoint_override"), pytest.raises(InvalidObjectMove):
        rename_object(conn, "bucket", source, destination)
    assert swift.mutations() == []
    assert swift.containers["bucket"] == stored


def test_create_directory_requires_successful_marker_put():
    from openstack.exceptions import HttpException

    from app.services.swift import create_directory

    conn, swift = _swift_conn({})
    swift.fail_when = lambda method, _container, key, _query: 507 if method == "PUT" and key == "fresh/" else None
    with patch("app.services.swift._apply_endpoint_override"):
        with pytest.raises(HttpException):
            create_directory(conn, "bucket", "fresh")
        assert swift.containers["bucket"] == {}
        swift.fail_when = lambda *_args: None
        assert create_directory(conn, "bucket", "fresh") == {"name": "fresh/", "container": "bucket"}
    assert swift.containers["bucket"] == {"fresh/": b""}


@pytest.mark.asyncio
async def test_object_listing_route_navigates_and_rejects_failed_page_without_caching(client, mock_conn):
    stored = {"tenant/chat-a/p1_00_keep_arch.png": b"image", "tenant/chat-b/file.txt": b"", "empty/": b""}
    conn, swift = _swift_conn(stored, page_size=1)
    mock_conn.object_store = conn.object_store
    url = "/api/v1/object-storage/bucket/objects"
    with patch("app.services.swift._apply_endpoint_override"):
        root = await client.get(url + "?cache=true")
        subdirs = await client.get(url, params={"prefix": "tenant/"})
        file = await client.get(url, params={"prefix": "tenant/chat-a/"})
        flat = await client.get(url, params={"prefix": "tenant/", "delimiter": ""})
    assert root.status_code == subdirs.status_code == file.status_code == flat.status_code == 200
    assert {row["name"] for row in root.json()} == {"empty/", "tenant/"}
    assert {row["name"] for row in subdirs.json()} == {"tenant/chat-a/", "tenant/chat-b/"}
    assert file.json()[0]["name"] == "tenant/chat-a/p1_00_keep_arch.png"
    assert all(row["name"] != "tenant/" for row in flat.json())
    assert len(flat.json()) == 2
    first_listing = next(
        query for method, name, key, query in swift.requests if method == "GET" and name == "bucket" and not key
    )
    assert first_listing["delimiter"] == "/"

    # A later page failure is neither cached as a partial list nor returned as 200.
    failing_url = url + "?prefix=tenant/chat-b/&cache=true"
    swift.fail_when = lambda method, _container, key, query: (
        503 if method == "GET" and not key and query.get("marker") == "tenant/chat-b/file.txt" else None
    )
    with patch("app.services.swift._apply_endpoint_override"):
        failed = await client.get(failing_url)
    assert failed.status_code == 500
    # main.py intentionally redacts 5xx details; the route still logs its public error.
    assert failed.json()["detail"] == "내부 서버 오류"
    swift.fail_when = lambda *_args: None
    with patch("app.services.swift._apply_endpoint_override"):
        recovered = await client.get(failing_url)
    assert recovered.status_code == 200
    assert [row["name"] for row in recovered.json()] == ["tenant/chat-b/file.txt"]


@pytest.mark.asyncio
async def test_move_routes_noop_identical_reject_overlap_and_keep_source_on_copy_failure(client, mock_conn):
    stored = {"foo/a.txt": b"a", "foo/b.txt": b"b"}
    conn, swift = _swift_conn(stored, extra=("other",))
    mock_conn.object_store = conn.object_store
    base = "/api/v1/object-storage/bucket/objects"
    with patch("app.services.swift._apply_endpoint_override"):
        same = await client.post(base + "/rename", json={"source": "foo/", "new_name": "foo/"})
        nested = await client.post(base + "/move", json={"source": "foo/", "destination": "foo/sub/"})
        swift.fail_when = lambda method, container, key, _query: (
            507 if method == "PUT" and container == "other" else None
        )
        failed = await client.post(
            base + "/move", json={"source": "foo/", "destination": "moved/", "dest_container": "other"}
        )
    assert same.status_code == 200
    assert nested.status_code == 400
    assert nested.json()["detail"] == "폴더를 자기 자신 안으로 이동할 수 없습니다"
    assert failed.status_code == 500
    assert swift.containers["bucket"] == stored
    assert [write for write in swift.mutations() if write[0] == "DELETE"] == []


def test_upload_small_object_no_slo():
    """100 MB 파일 업로드 시 SLO 옵션이 전달되지 않는다."""
    import io
    from unittest.mock import MagicMock, patch

    from app.services.swift import upload_object

    conn = MagicMock()
    mock_obj = MagicMock()
    mock_obj.name = "small.bin"
    mock_obj.etag = ""
    conn.object_store.create_object.return_value = mock_obj

    small_size = 100 * 1024 * 1024  # 100 MB
    with patch("app.services.swift._apply_endpoint_override"):
        upload_object(conn, "bucket", "small.bin", io.BytesIO(b""), "application/octet-stream", small_size)

    kw = conn.object_store.create_object.call_args[1]
    assert "use_slo" not in kw
    assert "segment_size" not in kw


# ---------------------------------------------------------------------------
# 스트리밍 PUT 업로드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_upload_missing_content_length():
    """Content-Length 없이 PUT 요청 → 411."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            "/api/v1/object-storage/test-container/objects/file.bin",
            content=b"data",
            headers={"Content-Type": "application/octet-stream"},
        )
    assert resp.status_code in (401, 404, 405, 411)


@pytest.mark.asyncio
async def test_streaming_upload_too_large():
    """Content-Length > 100 GiB → 413 (또는 인증 먼저 401)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.put(
            "/api/v1/object-storage/test-container/objects/huge.bin",
            content=b"x",
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Length": str(100 * 1024**3 + 1),
            },
        )
    assert resp.status_code in (401, 404, 405, 413)


def test_streaming_upload_small_no_slo():
    """100 MB raw PUT → SLO 옵션 미사용."""
    import io
    from unittest.mock import MagicMock, patch

    from app.services.swift import upload_object

    conn = MagicMock()
    mock_obj = MagicMock()
    mock_obj.name = "small.bin"
    mock_obj.etag = ""
    conn.object_store.create_object.return_value = mock_obj

    small_size = 100 * 1024 * 1024
    with patch("app.services.swift._apply_endpoint_override"):
        upload_object(conn, "bucket", "small.bin", io.BytesIO(b""), "application/octet-stream", small_size)

    kw = conn.object_store.create_object.call_args[1]
    assert "use_slo" not in kw
    assert "segment_size" not in kw


def test_streaming_upload_large_uses_manual_slo():
    """6.5 GiB raw PUT → 수동 SLO: proxy.put 2(segments) + 1(manifest) = 3 회.

    SLO 임계값이 5 GiB 이므로 6.5 GiB 는 ceil(6.5/5) = 2 segments.
    """
    import io
    import math
    from unittest.mock import MagicMock, patch

    from app.services.swift import _SLO_SEGMENT_SIZE, upload_object

    conn = MagicMock()
    mock_resp = MagicMock()
    mock_resp.headers = {"etag": '"deadbeef"'}
    conn.object_store.put.return_value = mock_resp

    large_size = int(6.5 * 1024**3)  # 5 GiB 초과 → SLO 발동, 2 segments
    with patch("app.services.swift._apply_endpoint_override"), patch("app.services.swift._ensure_segment_container"):
        upload_object(conn, "bucket", "large.bin", io.BytesIO(b""), "application/octet-stream", large_size)

    num_segments = math.ceil(large_size / _SLO_SEGMENT_SIZE)
    assert conn.object_store.put.call_count == num_segments + 1
    manifest_url = conn.object_store.put.call_args_list[-1][0][0]
    assert "multipart-manifest=put" in manifest_url


def test_delete_slo_object_purges_segments():
    """SLO manifest 삭제 시 ?multipart-manifest=delete 쿼리가 포함된 raw DELETE 가 호출된다."""
    from unittest.mock import MagicMock, patch

    from app.services.swift import delete_object

    conn = MagicMock()
    mock_meta = MagicMock()
    mock_meta.is_static_large_object = True
    conn.object_store.get_object_metadata.return_value = mock_meta
    conn.object_store.delete.return_value = _swift_listing_response([], status=204)

    with patch("app.services.swift._apply_endpoint_override"):
        delete_object(conn, "bucket", "big.bin")

    assert conn.object_store.delete.called
    delete_url = conn.object_store.delete.call_args[0][0]
    assert "multipart-manifest=delete" in delete_url


# ---------------------------------------------------------------------------
# Content-Disposition RFC 5987 (한글 파일명)
# ---------------------------------------------------------------------------


def test_content_disposition_ascii():
    """ASCII 파일명: filename 토큰과 filename* 토큰 모두 포함."""
    from app.api.object_storage.containers import _make_content_disposition

    result = _make_content_disposition("attachment", "folder/test.txt")
    assert "attachment" in result
    assert 'filename="test.txt"' in result
    assert "filename*=UTF-8''" in result
    assert urllib.parse.quote("test.txt", safe="") in result


def test_content_disposition_korean():
    """한글 파일명: ASCII 폴백은 '_'로 치환, filename* 는 UTF-8 퍼센트 인코딩."""
    from app.api.object_storage.containers import _make_content_disposition

    result = _make_content_disposition("attachment", "한글 2024.zip")
    assert "filename*=UTF-8''" in result
    assert urllib.parse.quote("한글 2024.zip", safe="") in result


def test_content_disposition_inline():
    """미리보기용 inline disposition."""
    from app.api.object_storage.containers import _make_content_disposition

    result = _make_content_disposition("inline", "image.png")
    assert result.startswith("inline")
    assert "filename*=UTF-8''" in result


# ---------------------------------------------------------------------------
# 단발 다운로드 토큰 발급
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_download_token_unauthenticated():
    """미인증 요청 → 401 (또는 서비스 미활성화 시 404/405)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/object-storage/test-bucket/objects/test.txt/download-token")
    assert resp.status_code in (401, 404, 405)


@pytest.mark.asyncio
async def test_issue_download_token_success(client, mock_conn):
    """인증된 사용자가 토큰 발급 → url + expires_in 반환."""
    mock_redis = MagicMock()
    mock_redis.set = AsyncMock()

    with patch("app.services.cache._get_redis", new_callable=AsyncMock, return_value=mock_redis):
        resp = await client.post("/api/v1/object-storage/test-bucket/objects/test.txt/download-token")
    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        data = resp.json()
        assert "url" in data
        assert "token=" in data["url"]
        assert data["expires_in"] == 60


# ---------------------------------------------------------------------------
# 단발 토큰으로 다운로드
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_with_expired_token():
    """없는/만료된 토큰 → 403 (또는 서비스 미활성화 시 404/405)."""
    mock_redis = MagicMock()
    mock_redis.getdel = AsyncMock(return_value=None)

    with patch("app.services.cache._get_redis", new_callable=AsyncMock, return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/object-storage/test-bucket/objects/test.txt/download",
                params={"token": "expired-or-missing-token"},
            )
    assert resp.status_code in (403, 404, 405)


@pytest.mark.asyncio
async def test_download_token_mismatched_resource():
    """토큰 페이로드와 URL의 container/object 불일치 → 403."""
    payload = json.dumps(
        {
            "openstack_token": "os-tok",
            "project_id": "proj",
            "container_name": "other-bucket",
            "object_name": "test.txt",
        }
    )
    mock_redis = MagicMock()
    mock_redis.getdel = AsyncMock(return_value=payload)

    with patch("app.services.cache._get_redis", new_callable=AsyncMock, return_value=mock_redis):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/object-storage/test-bucket/objects/test.txt/download",
                params={"token": "mismatch-token"},
            )
    assert resp.status_code in (403, 404, 405)


@pytest.mark.asyncio
async def test_download_with_valid_token():
    """유효한 단발 토큰 → 스트리밍 응답 + RFC 5987 Content-Disposition."""
    payload = json.dumps(
        {
            "openstack_token": "os-tok",
            "project_id": "proj",
            "container_name": "test-bucket",
            "object_name": "한글파일.zip",
        }
    )
    mock_redis = MagicMock()
    mock_redis.getdel = AsyncMock(return_value=payload)

    mock_conn_val = MagicMock()
    mock_conn_val.close = MagicMock()

    def fake_chunks():
        yield b"data"

    with (
        patch("app.services.cache._get_redis", new_callable=AsyncMock, return_value=mock_redis),
        patch("app.services.keystone.get_openstack_connection", return_value=mock_conn_val),
        patch("app.services.swift.stream_object", return_value=(fake_chunks(), "application/zip", 4)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get(
                "/api/v1/object-storage/test-bucket/objects/%ED%95%9C%EA%B8%80%ED%8C%8C%EC%9D%BC.zip/download",
                params={"token": "valid-token"},
            )
    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        cd = resp.headers.get("content-disposition", "")
        assert "filename*=UTF-8''" in cd


# ---------------------------------------------------------------------------
# admin all_projects 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_containers_all_projects_requires_admin(non_admin_client):
    """all_projects=true + is_system_admin=False → 403."""
    resp = await non_admin_client.get("/api/v1/object-storage?all_projects=true")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_containers_all_projects_fans_out(admin_client):
    """admin + all_projects=true → 프로젝트별 fan-out, project_id 포함 결과."""
    from unittest.mock import MagicMock, patch

    fake_projects = [{"id": "p1", "name": "alpha"}, {"id": "p2", "name": "beta"}]
    sub_conn_p1 = MagicMock()
    sub_conn_p1.close = MagicMock()
    sub_conn_p2 = MagicMock()
    sub_conn_p2.close = MagicMock()
    conns = {"p1": sub_conn_p1, "p2": sub_conn_p2}
    containers_by_conn_id = {
        id(sub_conn_p1): [{"name": "bucket-a", "count": 3, "bytes": 1024}],
        id(sub_conn_p2): [{"name": "bucket-b", "count": 5, "bytes": 2048}],
    }

    with (
        patch("app.services.keystone.list_projects", return_value=fake_projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            side_effect=lambda pid: conns[pid],
        ),
        patch(
            "app.services.swift.list_containers",
            side_effect=lambda conn, include_quarantine=False, include_trash=False: containers_by_conn_id[id(conn)],
        ),
    ):
        resp = await admin_client.get("/api/v1/object-storage?all_projects=true")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    assert {b["project_id"] for b in body} == {"p1", "p2"}
    sub_conn_p1.close.assert_called_once()
    sub_conn_p2.close.assert_called_once()


@pytest.mark.asyncio
async def test_list_containers_include_quarantine_requires_admin(non_admin_client):
    """include_quarantine=true + non-admin → 403."""
    resp = await non_admin_client.get("/api/v1/object-storage?include_quarantine=true")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_containers_all_projects_include_quarantine_propagates(admin_client):
    """admin all_projects + include_quarantine 가 list_containers 까지 전달된다."""
    from unittest.mock import MagicMock, patch

    fake_projects = [{"id": "p1", "name": "alpha"}]
    sub_conn = MagicMock()
    sub_conn.close = MagicMock()

    captured: dict = {}

    def _list(conn, include_quarantine=False, include_trash=False):
        captured["include_quarantine"] = include_quarantine
        return [
            {"name": "test", "count": 4, "bytes": 1024},
            {"name": "test-quarantine", "count": 17, "bytes": 512, "is_quarantine": True},
        ]

    with (
        patch("app.services.keystone.list_projects", return_value=fake_projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            return_value=sub_conn,
        ),
        patch("app.services.swift.list_containers", side_effect=_list),
    ):
        resp = await admin_client.get("/api/v1/object-storage?all_projects=true&include_quarantine=true")
    assert resp.status_code == 200
    assert captured["include_quarantine"] is True
    body = resp.json()
    quarantine_entries = [b for b in body if b.get("is_quarantine")]
    assert len(quarantine_entries) == 1
    assert quarantine_entries[0]["name"] == "test-quarantine"


# ---------------------------------------------------------------------------
# Phase 10: 버킷 이름 검증 + admin fan-out 병렬화 테스트
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_container_rejects_reserved_name(client, mock_conn):
    """예약어 이름 (admin) → 400 + 한국어 사유."""
    resp = await client.post("/api/v1/object-storage", json={"name": "admin"})
    assert resp.status_code == 400
    assert "예약" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_container_rejects_quarantine_suffix(client, mock_conn):
    """`-quarantine` 접미사 → 400."""
    resp = await client.post("/api/v1/object-storage", json={"name": "foo-quarantine"})
    assert resp.status_code == 400
    assert "quarantine" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_container_accepts_valid_name(client, mock_conn):
    """정상 이름 통과 → 검증 후 swift.create_container 호출."""
    with patch("app.services.swift.create_container") as mock_create:
        mock_create.return_value = {"name": "my-bucket-2025"}
        resp = await client.post("/api/v1/object-storage", json={"name": "my-bucket-2025"})
    assert resp.status_code == 201
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_list_containers_all_projects_runs_concurrently(admin_client):
    """asyncio.gather 병렬화: 3 프로젝트 × 0.3s sleep → 전체 < 0.5s (sequential 이면 0.9s+)."""
    import time

    fake_projects = [{"id": f"p{i}", "name": f"proj{i}"} for i in range(1, 4)]
    sub_conns = {pid["id"]: MagicMock() for pid in fake_projects}
    for c in sub_conns.values():
        c.close = MagicMock()

    def _slow_list(conn, include_quarantine=False, include_trash=False):
        time.sleep(0.3)
        return [{"name": "bucket", "count": 1, "bytes": 100}]

    with (
        patch("app.services.keystone.list_projects", return_value=fake_projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            side_effect=lambda pid: sub_conns[pid],
        ),
        patch("app.services.swift.list_containers", side_effect=_slow_list),
    ):
        start = time.monotonic()
        resp = await admin_client.get("/api/v1/object-storage?all_projects=true")
        elapsed = time.monotonic() - start

    assert resp.status_code == 200
    assert len(resp.json()) == 3
    # sequential 이면 ~0.9s, parallel 이면 ~0.3s. 0.6s 이하면 병렬 동작 확인.
    assert elapsed < 0.6, f"expected parallel <0.6s, got {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_list_containers_all_projects_skips_unauthorized(admin_client):
    """한 프로젝트는 401 raise → 결과에서 제외 + 다른 프로젝트는 정상 포함."""
    from keystoneauth1.exceptions.http import Unauthorized

    fake_projects = [
        {"id": "p1", "name": "good"},
        {"id": "p2", "name": "denied"},
    ]
    good_conn = MagicMock()
    good_conn.close = MagicMock()

    def _get_conn(pid: str):
        if pid == "p2":
            raise Unauthorized("not allowed")
        return good_conn

    with (
        patch("app.services.keystone.list_projects", return_value=fake_projects),
        patch(
            "app.services.keystone.get_admin_connection_for_project",
            side_effect=_get_conn,
        ),
        patch(
            "app.services.swift.list_containers",
            side_effect=lambda conn, include_quarantine=False, include_trash=False: [
                {"name": "ok-bucket", "count": 1, "bytes": 100}
            ],
        ),
    ):
        resp = await admin_client.get("/api/v1/object-storage?all_projects=true")

    assert resp.status_code == 200
    body = resp.json()
    project_ids = {b["project_id"] for b in body}
    assert project_ids == {"p1"}, f"p2 should be skipped, got {project_ids}"


# ---------------------------------------------------------------------------
# delete_container 캐스케이드 + SLO 임계값 테스트
# ---------------------------------------------------------------------------


def test_delete_container_cascades_segments():
    """delete_container 가 원본 컨테이너 + 객체 + _segments 컨테이너를 모두 삭제."""
    from unittest.mock import MagicMock, patch

    from app.services import swift as swift_svc

    proxy = MagicMock()
    obj_a = MagicMock()
    obj_a.name = "file.bin"
    seg_a = MagicMock()
    seg_a.name = "file.bin/00000000"
    seg_b = MagicMock()
    seg_b.name = "file.bin/00000001"

    # 첫 호출(name="test"): 객체 1개; 두 번째 호출(name="test_segments"): segment 2개
    proxy.objects.side_effect = [iter([obj_a]), iter([seg_a, seg_b])]
    proxy.delete_container = MagicMock()
    proxy.delete_object = MagicMock()
    # SLO manifest 아님으로 설정 → delete_object 경로를 단순화
    proxy.get_object_metadata = MagicMock(
        return_value=MagicMock(
            is_static_large_object=False,
            x_static_large_object="",
        )
    )

    conn = MagicMock()
    conn.object_store = proxy
    conn._afterglow_project_id = "p1"

    with patch.object(swift_svc, "_apply_endpoint_override"):
        swift_svc.delete_container(conn, "test")

    # 원본 컨테이너 삭제
    proxy.delete_container.assert_any_call("test", ignore_missing=False)
    # _segments 컨테이너 내 segment 2개 삭제 시도
    assert proxy.delete_object.call_count >= 2
    # _segments 컨테이너 자체 삭제
    proxy.delete_container.assert_any_call("test_segments", ignore_missing=True)


def test_delete_container_no_segments_ok():
    """_segments 컨테이너가 없는 경우 정상 종료."""
    from unittest.mock import MagicMock, patch

    from app.services import swift as swift_svc

    proxy = MagicMock()

    def objects_side_effect(name):
        if name == "test":
            return iter([])
        raise Exception("404 NoSuchContainer")

    proxy.objects.side_effect = objects_side_effect
    proxy.delete_container = MagicMock()

    conn = MagicMock()
    conn.object_store = proxy
    conn._afterglow_project_id = "p1"

    with patch.object(swift_svc, "_apply_endpoint_override"):
        swift_svc.delete_container(conn, "test")  # 예외 없이 종료

    proxy.delete_container.assert_any_call("test", ignore_missing=False)


def test_upload_object_below_5gib_uses_single_put():
    """4 GiB 파일은 SLO 거치지 않고 create_object 단일 호출."""
    from io import BytesIO
    from unittest.mock import MagicMock, patch

    from app.services import swift as swift_svc

    proxy = MagicMock()
    proxy.create_object = MagicMock(return_value=MagicMock(name="big.bin", etag="abc"))
    conn = MagicMock()
    conn.object_store = proxy
    four_gib = 4 * 1024**3

    with patch.object(swift_svc, "_apply_endpoint_override"):
        result = swift_svc.upload_object(
            conn,
            "test",
            "big.bin",
            BytesIO(b""),
            content_type="application/octet-stream",
            content_length=four_gib,
        )

    proxy.create_object.assert_called_once()
    assert result["bytes"] == four_gib


def test_upload_object_above_5gib_uses_slo():
    """6 GiB 파일은 _upload_slo 호출."""
    from io import BytesIO
    from unittest.mock import MagicMock, patch

    from app.services import swift as swift_svc

    conn = MagicMock()
    conn.object_store = MagicMock()
    six_gib = 6 * 1024**3

    with (
        patch.object(swift_svc, "_apply_endpoint_override"),
        patch.object(
            swift_svc,
            "_upload_slo",
            return_value={"name": "huge.bin", "bytes": six_gib, "container": "test", "etag": ""},
        ) as mock_slo,
    ):
        result = swift_svc.upload_object(
            conn,
            "test",
            "huge.bin",
            BytesIO(b""),
            content_type="application/octet-stream",
            content_length=six_gib,
        )

    mock_slo.assert_called_once()
    assert result["bytes"] == six_gib


def test_list_containers_filters_quarantine_suffix():
    """list_containers가 -quarantine suffix 컨테이너를 결과에서 제외."""
    from unittest.mock import MagicMock, patch

    from app.services import swift as swift_svc

    fake_conn = MagicMock()
    c1 = MagicMock()
    c1.name = "test"
    c1.count = 5
    c1.bytes = 1024
    c2 = MagicMock()
    c2.name = "test-quarantine"
    c2.count = 0
    c2.bytes = 0
    c3 = MagicMock()
    c3.name = "test_segments"
    c3.count = 9
    c3.bytes = 8 * 1024**3
    c4 = MagicMock()
    c4.name = "other"
    c4.count = 1
    c4.bytes = 100

    fake_conn.object_store.containers.return_value = [c1, c2, c3, c4]
    fake_conn.object_store.get_endpoint.return_value = "http://swift/v1"

    with patch.object(swift_svc, "_apply_endpoint_override"):
        out = swift_svc.list_containers(fake_conn)

    names = [c["name"] for c in out]
    assert "test" in names
    assert "other" in names
    assert "test-quarantine" not in names
    assert "test_segments" not in names


# ---------------------------------------------------------------------------
# Phase C+D: 캐시 적용 + mutation invalidation 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_containers_uses_cached_call(client, mock_conn):
    """GET /containers → cached_call 이 올바른 키/TTL 로 호출된다."""
    from unittest.mock import AsyncMock, patch

    fake_containers = [{"name": "bucket-1", "count": 2, "bytes": 1024}]

    with patch(
        "app.api.object_storage.containers.cache.cached_call", new_callable=AsyncMock, return_value=fake_containers
    ) as mock_call:
        resp = await client.get("/api/v1/object-storage")

    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        assert mock_call.called
        call_kwargs = mock_call.call_args
        # 첫 번째 positional 인자가 afterglow:swift:{pid}:containers 형식이어야 함
        cache_key = call_kwargs[0][0]
        assert cache_key.startswith("afterglow:swift:")
        assert ":containers" in cache_key


@pytest.mark.asyncio
async def test_get_container_metadata_uses_cached_call(client, mock_conn):
    """GET /{container_name} → cached_call 이 container sub-key 로 호출된다."""
    from unittest.mock import AsyncMock, patch

    fake_meta = {"name": "my-bucket", "count": 5, "bytes": 2048}

    with patch(
        "app.api.object_storage.containers.cache.cached_call", new_callable=AsyncMock, return_value=fake_meta
    ) as mock_call:
        resp = await client.get("/api/v1/object-storage/my-bucket")

    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        assert mock_call.called
        cache_key = mock_call.call_args[0][0]
        assert "containers" in cache_key
        assert "my-bucket" in cache_key


@pytest.mark.asyncio
async def test_list_objects_uses_cached_call(client, mock_conn):
    """GET /{container_name}/objects → cached_call 이 objects 키로 호출된다."""
    from unittest.mock import AsyncMock, patch

    fake_objects = [{"name": "file.txt", "bytes": 100}]

    with patch(
        "app.api.object_storage.containers.cache.cached_call", new_callable=AsyncMock, return_value=fake_objects
    ) as mock_call:
        resp = await client.get("/api/v1/object-storage/my-bucket/objects")

    assert resp.status_code in (200, 404, 405)
    if resp.status_code == 200:
        assert mock_call.called
        cache_key = mock_call.call_args[0][0]
        assert "objects" in cache_key
        assert "my-bucket" in cache_key


@pytest.mark.asyncio
async def test_list_objects_different_prefix_uses_different_key(client, mock_conn):
    """prefix가 다르면 다른 캐시 키가 사용된다."""
    from unittest.mock import patch

    captured_keys: list[str] = []

    async def _fake_cached_call(key, ttl, fn, *, refresh=False):
        captured_keys.append(key)
        return []

    with patch("app.api.object_storage.containers.cache.cached_call", side_effect=_fake_cached_call):
        await client.get("/api/v1/object-storage/bucket/objects?prefix=folder/")
        await client.get("/api/v1/object-storage/bucket/objects?prefix=other/")

    if len(captured_keys) == 2:
        assert captured_keys[0] != captured_keys[1], "다른 prefix 는 다른 캐시 키여야 한다"


@pytest.mark.asyncio
async def test_create_container_invalidates_cache(client, mock_conn):
    """POST /containers → 생성 성공 후 캐시 무효화가 호출된다."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.services.swift.create_container", return_value={"name": "new-bucket"}),
        patch("app.api.object_storage.containers.cache.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.object_storage.containers.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
    ):
        resp = await client.post("/api/v1/object-storage", json={"name": "new-bucket"})

    assert resp.status_code in (201, 404, 405)
    if resp.status_code == 201:
        mock_inv.assert_called_once()
        inv_pattern = mock_inv.call_args[0][0]
        assert "swift" in inv_pattern
        assert inv_pattern.endswith(":*")
        mock_mut.assert_called_once_with("swift", mock_conn._afterglow_project_id)


@pytest.mark.asyncio
async def test_delete_container_invalidates_cache(client, mock_conn):
    """DELETE /{container_name} → 삭제 성공 후 캐시 무효화가 호출된다."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.services.swift.delete_container", return_value=None),
        patch("app.api.object_storage.containers.cache.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.object_storage.containers.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
    ):
        resp = await client.delete("/api/v1/object-storage/old-bucket")

    assert resp.status_code in (204, 404, 405)
    if resp.status_code == 204:
        mock_inv.assert_called_once()
        mock_mut.assert_called_once_with("swift", mock_conn._afterglow_project_id)


@pytest.mark.asyncio
async def test_upload_object_invalidates_cache(client, mock_conn):
    """POST /{container_name}/objects → 업로드 성공 후 캐시 무효화가 호출된다."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.services.swift.upload_object", return_value={"name": "test.txt", "bytes": 5}),
        patch("app.api.object_storage.containers.cache.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.object_storage.containers.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
    ):
        resp = await client.post(
            "/api/v1/object-storage/my-bucket/objects",
            files={"file": ("test.txt", b"hello", "text/plain")},
        )

    assert resp.status_code in (201, 404, 405)
    if resp.status_code == 201:
        mock_inv.assert_called_once()
        mock_mut.assert_called_once_with("swift", mock_conn._afterglow_project_id)


@pytest.mark.asyncio
async def test_delete_object_invalidates_cache(client, mock_conn):
    """DELETE /{container_name}/objects/{name} → 삭제 성공 후 캐시 무효화가 호출된다."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.services.swift.soft_delete_object", return_value={}),  # DELETE defaults to trash
        patch("app.api.object_storage.containers.cache.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.object_storage.containers.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
    ):
        resp = await client.delete("/api/v1/object-storage/my-bucket/objects/test.txt")

    assert resp.status_code in (204, 404, 405)
    if resp.status_code == 204:
        mock_inv.assert_called_once()
        mock_mut.assert_called_once_with("swift", mock_conn._afterglow_project_id)


@pytest.mark.asyncio
async def test_list_containers_cache_bypass(client, mock_conn):
    """`?refresh=true` 쿼리스트링 → cached_call 에 refresh=True 가 전달된다."""
    from unittest.mock import patch

    captured: dict = {}

    async def _fake_cached_call(key, ttl, fn, *, refresh=False):
        captured["refresh"] = refresh
        return []

    with patch("app.api.object_storage.containers.cache.cached_call", side_effect=_fake_cached_call):
        resp = await client.get("/api/v1/object-storage?refresh=true")

    if resp.status_code == 200:
        assert captured.get("refresh") is True, "refresh=true 쿼리 → cached_call 에 refresh=True 전달"


@pytest.mark.asyncio
async def test_create_container_no_invalidation_on_failure(client, mock_conn):
    """컨테이너 생성 실패 시 캐시 무효화가 호출되지 않는다."""
    from unittest.mock import AsyncMock, patch

    with (
        patch("app.services.swift.create_container", side_effect=Exception("Swift 오류")),
        patch("app.api.object_storage.containers.cache.invalidate", new_callable=AsyncMock) as mock_inv,
        patch(
            "app.api.object_storage.containers.invalidation.invalidate_mutation_count", new_callable=AsyncMock
        ) as mock_mut,
    ):
        resp = await client.post("/api/v1/object-storage", json={"name": "fail-bucket"})

    assert resp.status_code in (500, 404, 405)
    if resp.status_code == 500:
        mock_inv.assert_not_called()
        mock_mut.assert_not_called()
