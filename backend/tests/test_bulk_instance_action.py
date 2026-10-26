"""인스턴스 일괄 액션(bulk-action) 엔드포인트 단위 테스트.

검증 범위:
  - 화이트리스트 위반 action → 422
  - 빈/초과 instance_ids → 422
  - start/stop/delete 정상 처리 → ok=True 반환
  - IDOR: 타 프로젝트 인스턴스 → ok=False (generic 메시지, 404/403 구분 없음)
  - 부분 실패 시 나머지 항목은 정상 처리
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_URL = "/api/v1/instances/bulk-action"

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _ordinary_consume_dispatch(monkeypatch):
    """Ordinary lifecycle units; real block ledger dispatch is covered separately."""
    monkeypatch.setattr("app.services.layer_consume_resources.lookup_for_server", AsyncMock(return_value=[]))


def _make_server(server_id: str, project_id: str = "test-project-123") -> MagicMock:
    srv = MagicMock()
    srv.id = server_id
    srv.name = f"vm-{server_id[:4]}"
    srv.status = "ACTIVE"
    srv.project_id = project_id
    srv.union_upper_volume_id = None
    srv.union_share_ids = []
    srv.union_strategy = None
    srv.metadata = {}
    return srv


# ---------------------------------------------------------------------------
# 입력 검증
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_action_invalid_action_returns_422(client):
    """화이트리스트 외 action → 422."""
    resp = await client.post(_URL, json={"action": "REBOOT_ALL", "instance_ids": ["abc"]})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_action_empty_ids_returns_422(client):
    """빈 instance_ids → 422."""
    resp = await client.post(_URL, json={"action": "start", "instance_ids": []})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_action_too_many_ids_returns_422(client):
    """51개 초과 → 422."""
    ids = [f"id-{i}" for i in range(51)]
    resp = await client.post(_URL, json={"action": "start", "instance_ids": ids})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_bulk_action_exactly_50_ids_ok(client):
    """50개 딱 맞는 경우는 유효 (422 아님)."""
    ids = [f"id-{i}" for i in range(50)]
    srv = _make_server("id-0")

    with (
        patch("app.api.compute.instances.nova.get_server", return_value=srv),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.start_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(_URL, json={"action": "start", "instance_ids": ids})

    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 정상 동작
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_start_ok(client):
    """start 일괄 처리 — 성공 시 ok=True 결과 반환."""
    srv = _make_server("inst-1")
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=srv),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.start_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(_URL, json={"action": "start", "instance_ids": ["inst-1"]})

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["ok"] is True
    assert result["id"] == "inst-1"


@pytest.mark.asyncio
async def test_bulk_stop_ok(client):
    """stop 일괄 처리 — 성공."""
    srv = _make_server("inst-2")
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=srv),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.stop_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(_URL, json={"action": "stop", "instance_ids": ["inst-2"]})

    assert resp.status_code == 200
    assert resp.json()["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_bulk_reboot_ok(client):
    """reboot 일괄 처리 — 성공."""
    srv = _make_server("inst-r")
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=srv),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.reboot_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(_URL, json={"action": "reboot", "instance_ids": ["inst-r"]})

    assert resp.status_code == 200
    assert resp.json()["results"][0]["ok"] is True


@pytest.mark.asyncio
async def test_bulk_delete_ok(client, empty_layer_consume_db):
    """delete 일괄 처리 — 성공."""
    srv = _make_server("inst-3")
    with (
        patch("app.api.compute.instances.nova.get_server", return_value=srv),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.delete_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
        patch("app.api.compute.instances.neutron.cleanup_instance_fips"),
    ):
        resp = await client.post(_URL, json={"action": "delete", "instance_ids": ["inst-3"]})

    assert resp.status_code == 200
    assert resp.json()["results"][0]["ok"] is True


# ---------------------------------------------------------------------------
# IDOR 방어
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_action_idor_rejected(client):
    """다른 프로젝트 인스턴스 포함 시 해당 항목 ok=False, 내 인스턴스는 ok=True."""
    from fastapi import HTTPException

    my_srv = _make_server("inst-mine", project_id="test-project-123")
    other_srv = _make_server("inst-other", project_id="other-project-999")

    def fake_get_server(_conn, sid):
        return my_srv if sid == "inst-mine" else other_srv

    def fake_owner_check(server, conn, token_info):
        # 실제 assert_instance_owner와 동일 동작: 타 프로젝트는 404
        if server.project_id != conn._afterglow_project_id:
            raise HTTPException(status_code=404, detail="인스턴스를 찾을 수 없습니다")

    with (
        patch("app.api.compute.instances.nova.get_server", side_effect=fake_get_server),
        patch("app.api.compute.instances.assert_instance_owner", side_effect=fake_owner_check),
        patch("app.api.compute.instances.nova.start_server"),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(
            _URL,
            json={"action": "start", "instance_ids": ["inst-mine", "inst-other"]},
        )

    assert resp.status_code == 200
    results = {r["id"]: r for r in resp.json()["results"]}
    assert results["inst-mine"]["ok"] is True
    assert results["inst-other"]["ok"] is False
    # IDOR oracle 방지: 에러 메시지는 generic (404/403 구분 없음)
    assert "처리 실패" in results["inst-other"].get("error", "")


# ---------------------------------------------------------------------------
# 부분 실패
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_action_partial_failure(client):
    """일부 Nova 오류 시 해당 id만 ok=False, 나머지는 ok=True."""
    srv_ok = _make_server("inst-ok")
    srv_fail = _make_server("inst-fail")

    def fake_get_server(_conn, sid):
        return srv_ok if sid == "inst-ok" else srv_fail

    def fake_start(_conn, sid):
        if sid == "inst-fail":
            raise RuntimeError("Nova internal error")

    with (
        patch("app.api.compute.instances.nova.get_server", side_effect=fake_get_server),
        patch("app.api.compute.instances.assert_instance_owner"),
        patch("app.api.compute.instances.nova.start_server", side_effect=fake_start),
        patch("app.api.compute.instances.invalidate", new_callable=AsyncMock),
        patch(
            "app.api.compute.instances.cache_invalidation.invalidate_mutation_count",
            new_callable=AsyncMock,
        ),
        patch("app.api.compute.instances.rec", new_callable=AsyncMock),
    ):
        resp = await client.post(
            _URL,
            json={"action": "start", "instance_ids": ["inst-ok", "inst-fail"]},
        )

    assert resp.status_code == 200
    results = {r["id"]: r for r in resp.json()["results"]}
    assert results["inst-ok"]["ok"] is True
    assert results["inst-fail"]["ok"] is False
    assert "처리 실패" in results["inst-fail"].get("error", "")
