"""튜토리얼 진행 이력 API — 계약/검증 테스트 (실 DB 없이 client fixture).

- GET 은 DB 미가용 시에도 빈 맵으로 graceful degrade(200).
- 잘못된 status / 미지원 tour_id 는 DB 접근 전에 422 로 거부(화이트리스트).
- 유효한 기록 요청은 DB 가용 시 204, 미가용 시 503(fail-closed) — 둘 중 하나.
"""

from __future__ import annotations

import pytest

from app.services import tutorial_status as tutorial_status_service

pytestmark = pytest.mark.asyncio


async def test_get_statuses_returns_map_even_without_db(client):
    resp = await client.get("/api/v1/tutorials/status")
    assert resp.status_code == 200
    body = resp.json()
    assert "statuses" in body
    assert isinstance(body["statuses"], dict)


async def test_post_rejects_invalid_status(client):
    resp = await client.post("/api/v1/tutorials/vm-create/status", json={"status": "bogus"})
    assert resp.status_code == 422


async def test_post_rejects_unknown_tour(client):
    resp = await client.post("/api/v1/tutorials/not-a-tour/status", json={"status": "completed"})
    assert resp.status_code == 422


async def test_all_administrator_tour_ids_are_whitelisted():
    administrator_tour_ids = (
        "admin-compute",
        "admin-storage",
        "admin-library",
        "admin-waygate",
        "admin-network",
        "admin-containers",
        "admin-key-manager",
        "admin-monitoring",
        "admin-system",
        "admin-identity",
    )

    assert (
        tuple(tutorial_status_service.validate_tour_id(tour_id) for tour_id in administrator_tour_ids)
        == administrator_tour_ids
    )

    assert tutorial_status_service.validate_tour_id("waygate") == "waygate"


@pytest.mark.parametrize("status", ["completed", "dismissed"])
async def test_post_valid_status_persists_or_reports_unavailable(client, status):
    resp = await client.post("/api/v1/tutorials/volume/status", json={"status": status})
    # DB 가용: 204, DB 미가용: 503 (fail-closed, 조용히 통과하지 않음)
    assert resp.status_code in (204, 503)
