"""Manila 에러 노출 개선 테스트.

- extract_manila_error: 응답 본문에서 메시지 추출 회귀
- create_file_storage: 'Share type not found' 404 시 가용 type 목록 첨부
- format_error_message: enrichment 여부에 따른 메시지 선택
"""

from unittest.mock import MagicMock

import httpx
import pytest

# ---------------------------------------------------------------------------
# extract_manila_error 회귀
# ---------------------------------------------------------------------------


def _make_http_error(
    status: int, body: bytes | str, url: str = "https://manila.example.com/v2/proj/shares"
) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", url)
    response = httpx.Response(status, content=body if isinstance(body, bytes) else body.encode())
    return httpx.HTTPStatusError("original", request=request, response=response)


def test_extract_manila_error_item_not_found():
    """itemNotFound 형식 본문에서 메시지 추출."""
    from app.services.manila import extract_manila_error

    body = b'{"itemNotFound": {"code": 404, "message": "Share type not found."}}'
    exc = _make_http_error(404, body)
    status, message = extract_manila_error(exc)

    assert status == 404
    assert message == "Share type not found."


def test_extract_manila_error_bad_request():
    """badRequest 형식 본문 추출."""
    from app.services.manila import extract_manila_error

    body = b'{"badRequest": {"code": 400, "message": "Invalid share size."}}'
    exc = _make_http_error(400, body)
    status, message = extract_manila_error(exc)

    assert status == 400
    assert message == "Invalid share size."


def test_extract_manila_error_non_json_fallback():
    """JSON 파싱 실패 시 plain text fallback."""
    from app.services.manila import extract_manila_error

    exc = _make_http_error(500, b"Internal Server Error")
    status, message = extract_manila_error(exc)

    assert status == 500
    assert "Internal Server Error" in message


# ---------------------------------------------------------------------------
# format_error_message
# ---------------------------------------------------------------------------


def test_format_error_message_enriched():
    """create_file_storage enrichment 후 args[0]이 'Manila API'로 시작하면 그대로 반환."""
    from app.services.manila import format_error_message

    body = b'{"itemNotFound": {"code": 404, "message": "Share type not found."}}'
    exc = _make_http_error(404, body)
    enriched = httpx.HTTPStatusError(
        "Manila API 404: Share type not found. 가용 share type: ['nfstype', 'cephfs']",
        request=exc.request,
        response=exc.response,
    )
    result = format_error_message(enriched)

    assert "Share type not found" in result
    assert "nfstype" in result
    assert result.startswith("Manila API")


def test_format_error_message_plain():
    """enrichment 없는 기본 HTTPStatusError는 extract_manila_error 결과 반환."""
    from app.services.manila import format_error_message

    body = b'{"forbidden": {"code": 403, "message": "Access denied."}}'
    exc = _make_http_error(403, body)
    result = format_error_message(exc)

    assert "Manila API 403" in result
    assert "Access denied" in result


# ---------------------------------------------------------------------------
# create_file_storage — share type not found 404 enrichment
# ---------------------------------------------------------------------------


def _mock_http_post_404_share_type():
    """POST /shares → 404 Share type not found 응답을 흉내 낸 MagicMock client."""
    request = httpx.Request("POST", "https://manila.example.com/v2/proj/shares")
    response = httpx.Response(
        404,
        content=b'{"itemNotFound": {"code": 404, "message": "Share type not found."}}',
    )
    error = httpx.HTTPStatusError("original", request=request, response=response)

    client = MagicMock()
    client.post.side_effect = error
    return client


def test_create_file_storage_share_type_not_found_lists_available_types(monkeypatch):
    """404 Share type not found 시 list_share_types를 호출하고 가용 목록을 에러에 첨부."""
    from app.services import manila

    mock_client = _mock_http_post_404_share_type()
    monkeypatch.setattr(manila, "get_client", lambda conn: mock_client)
    monkeypatch.setattr(
        manila,
        "list_share_types",
        lambda conn: [{"name": "nfstype"}, {"name": "cephfs"}],
    )

    conn = MagicMock()
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        manila.create_file_storage(conn, "test-share", 10, "", "cephfstype", "NFS")

    exc = exc_info.value
    # 예외 타입 보존 (file_storage.py:132, manila.py:436 의존)
    assert isinstance(exc, httpx.HTTPStatusError)
    # status_code 보존
    assert exc.response.status_code == 404
    # 가용 type 목록이 메시지에 포함
    msg = str(exc)
    assert "nfstype" in msg
    assert "cephfs" in msg
    assert "Share type not found" in msg


def test_create_file_storage_share_type_list_fails_gracefully(monkeypatch):
    """list_share_types 조회 실패 시 가용 목록 없이 enriched 에러 raise."""
    from app.services import manila

    mock_client = _mock_http_post_404_share_type()
    monkeypatch.setattr(manila, "get_client", lambda conn: mock_client)
    monkeypatch.setattr(
        manila,
        "list_share_types",
        MagicMock(side_effect=Exception("network error")),
    )

    conn = MagicMock()
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        manila.create_file_storage(conn, "test-share", 10, "", "cephfstype", "NFS")

    exc = exc_info.value
    assert exc.response.status_code == 404
    # 가용 목록 없이도 에러 raise
    assert "Share type not found" in str(exc)


def test_create_file_storage_other_404_reraises_unchanged(monkeypatch):
    """'Share type not found'가 아닌 404는 enrichment 없이 그대로 re-raise."""
    from app.services import manila

    request = httpx.Request("POST", "https://manila.example.com/v2/proj/shares")
    response = httpx.Response(
        404,
        content=b'{"itemNotFound": {"code": 404, "message": "Share not found."}}',
    )
    original_exc = httpx.HTTPStatusError("original", request=request, response=response)

    mock_client = MagicMock()
    mock_client.post.side_effect = original_exc
    monkeypatch.setattr(manila, "get_client", lambda conn: mock_client)

    conn = MagicMock()
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        manila.create_file_storage(conn, "test-share", 10, "", "cephfstype", "NFS")

    # list_share_types가 호출되지 않았어야 함 → enrichment 없이 원본 re-raise
    assert exc_info.value is original_exc


def test_submit_file_storage_returns_accepted_identity_without_poll_or_cleanup(monkeypatch):
    """A caller can journal the provider ID even while readiness reads are unavailable."""
    from app.services import manila

    class SubmissionClient:
        def __init__(self):
            self.posts = 0

        def post(self, path, body):
            assert path == "shares"
            assert body["share"]["share_proto"] == "CEPHFS"
            assert "share_network_id" not in body["share"]
            self.posts += 1
            return {"share": {"id": "accepted-share", "status": "creating"}}

        def get(self, *args, **kwargs):
            raise AssertionError("raw submission must not wait for readiness")

        def delete(self, *args, **kwargs):
            raise AssertionError("raw submission must not perform error cleanup")

    client = SubmissionClient()
    monkeypatch.setattr(manila, "get_client", lambda conn: client)
    share = manila.submit_file_storage(object(), "build-output", 5, "not-for-cephfs")
    assert share == {"id": "accepted-share", "status": "creating"}
    assert client.posts == 1
