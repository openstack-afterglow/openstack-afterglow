"""Informational route-catalog smoke; authentication is tested through HTTP behavior."""

from fastapi.routing import APIRoute

from app.main import app

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _iter_api_routes():
    """app.routes 에서 /api/ 경로 APIRoute만 순회."""
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/"):
            yield route


def test_minimum_route_count():
    """전체 /api/ 라우트 수가 기준값(200) 이상이어야 한다.

    대규모 라우터 삭제/미등록을 감지하기 위한 간단한 경보. 조건부 서비스 일부가 꺼진
    환경에서도 200개 미만이 되면 구조적 문제가 있는 것으로 판단한다.
    """
    count = sum(len(route.methods or []) for route in _iter_api_routes())
    assert count >= 200, (
        f"전체 API 엔드포인트(HTTP method × path) 수가 {count}개로 기준값(200)에 미치지 못합니다. "
        "라우터 미등록 또는 대규모 삭제 여부를 확인하세요."
    )


def test_admin_routes_summary(capsys):
    """현재 등록된 /api/admin/ 라우트를 열거 (정보성)."""
    routes = sorted(
        (m, r.path) for r in _iter_api_routes() if r.path.startswith("/api/v1/admin/") for m in (r.methods or [])
    )
    print(f"\n[admin routes total: {len(routes)}]")
    for method, path in routes:
        print(f"  {method:6} {path}")
    # 정보성 테스트 — 항상 통과
    assert len(routes) >= 50, (
        f"admin 라우트가 {len(routes)}개로 예상보다 적습니다. admin 라우터 등록 여부를 확인하세요."
    )
