"""공개 엔드포인트 카탈로그 회귀 방지 테스트.

FastAPI route 목록에서 예상 밖 공개 API와 대규모 route 삭제를 확인한다.
관리자 권한은 dependency 함수의 배치가 아니라 실제 HTTP 거부 결과로
test_enrollment_policy.py 및 각 관리자 endpoint의 보안 테스트에서 검증한다.
"""

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


def _has_any_auth_dep(route: APIRoute) -> bool:
    """route 에 어떤 형태로든 의존성이 있으면 True (= public 이 아님).

    두 가지 경로를 확인:
    1. decorator 레벨 dependencies=[Depends(...)]: route.dependencies 가 비어 있지 않음
    2. 핸들러 함수 파라미터에 Depends 기본값이 하나라도 존재

    이 휴리스틱으로 requirements=[Depends(require_admin)], Depends(get_os_conn),
    Depends(_require_admin) 등 모든 패턴을 감지한다.
    """
    # 1) decorator 레벨 dependencies
    if route.dependencies:
        return True

    # 2) 핸들러 파라미터 Depends
    import inspect

    from fastapi.params import Depends as _DependsClass

    if route.endpoint:
        try:
            sig = inspect.signature(route.endpoint)
            for param in sig.parameters.values():
                if isinstance(param.default, _DependsClass):
                    return True
        except (ValueError, TypeError):
            pass

    return False


# ---------------------------------------------------------------------------
# 공개 엔드포인트 스냅샷
# 이 목록 이외의 인증 없는 엔드포인트가 생기면 테스트가 실패한다.
# 조건부 서비스(k3s)의 라우트는 app에 없을 수 있으므로 optional 처리.
# ---------------------------------------------------------------------------

EXPECTED_PUBLIC = frozenset(
    {
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/health/detail"),  # 모니터링 대시보드용 Redis 상태 포함 헬스체크
        ("GET", "/api/v1/dashboard/config"),  # 새로고침 간격 등 UI 설정만 반환, 인증 불필요
        ("GET", "/api/v1/site-config"),  # 사이트명·서비스 플래그 — 로그인 전 UI 초기화에 필요
        ("GET", "/api/v1/site-config/assets/{slot}"),  # 로그인 전 브랜딩 이미지 제공용 public asset
        # Global provider options plus exact signup/provider context resolution.
        ("GET", "/api/v1/auth/login-options"),
        ("GET", "/api/v1/auth/domains/resolve"),
        ("POST", "/api/v1/auth/domains/{domain_id}/providers/{provider_id}/authorize"),
        ("POST", "/api/v1/auth/providers/callback"),
        ("POST", "/api/v1/auth/providers/entry"),  # One-use browser-bound verified OIDC proof; no anonymous creation.
        ("POST", "/api/v1/auth/providers/link"),  # Browser-bound link ticket plus original account proof.
        ("GET", "/api/v1/auth/signup/options"),  # Public signup availability; no account lookup.
        # Email-delivered one-use enrollment tokens authorize these onboarding requests.
        ("GET", "/api/v1/auth/invitations/{token}"),
        ("POST", "/api/v1/auth/invitations/accept"),
        ("POST", "/api/v1/auth/domains/{domain_id}/registrations"),
        ("POST", "/api/v1/auth/registrations/accept"),
        ("POST", "/api/v1/auth/login"),
        (
            "POST",
            "/api/v1/auth/personal-project/recovery",
        ),  # Fresh native password proof, same login guard/publication.
        # k3s 활성 시에만 등록되는 라우트
        ("POST", "/api/v1/k3s/callback"),
        # VM 내부 헬스 리포트 — Bearer report_token으로 자체 인증 (Keystone X-Auth-Token 불가)
        ("POST", "/api/v1/instances/{instance_id}/health/report"),
        # VM 내부 CephX 키 회전 — Bearer report_token으로 자체 인증
        ("POST", "/api/v1/instances/{instance_id}/credentials/rotate-cephx"),
        # 단발 다운로드 토큰(?token=) 또는 X-Auth-Token 헤더 중 하나 수용 — 내부 분기로 인증
        ("GET", "/api/v1/object-storage/{container_name}/objects/{object_name:path}/download"),
        # Palimpsest export download — one-use Redis dl_token으로 자체 인증
        ("GET", "/api/v1/palimpsest/hub/image-exports/{export_id}/download"),
        # Prometheus SD — Bearer monitoring_sd_token으로 자체 인증 (Keystone X-Auth-Token 불가)
        ("GET", "/api/v1/sd/prometheus/targets"),
        ("GET", "/api/v1/sd/prometheus/libvirt-targets"),
        # refresh 토큰으로 자체 인증 (만료된 access token 갱신용)
        ("POST", "/api/v1/auth/refresh"),
        # Waygate 에이전트(VM 내부) — Bearer report_token(waygate_agent_auth)으로 자체 인증
        # (Keystone X-Auth-Token 불가). instance_health.report 패턴과 동일하게
        # FastAPI Depends()가 아닌 핸들러 내부 _verify_and_bind()로 fail-closed 검증.
        ("POST", "/api/v1/waygate/servers/{server_id}/agent/register"),
        ("GET", "/api/v1/waygate/servers/{server_id}/agent/desired-state"),
        ("POST", "/api/v1/waygate/servers/{server_id}/agent/status"),
        # MCP OAuth client redirect — validates signed state plus initiating-browser nonce cookie.
        ("GET", "/api/v1/chat/mcp-oauth/callback"),
        # MCP OAuth public-client endpoints validate their own signed/browser-bound requests.
        ("POST", "/api/v1/mcp/oauth/register"),
        ("GET", "/api/v1/mcp/oauth/authorize"),
        ("POST", "/api/v1/mcp/oauth/token"),
        ("POST", "/api/v1/mcp/oauth/revoke"),
        ("OPTIONS", "/api/v1/mcp/oauth/{path:path}"),
    }
)


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


def test_no_unexpected_public_routes():
    """인증 없이 접근 가능한 엔드포인트가 EXPECTED_PUBLIC 스냅샷을 벗어나지 않아야 한다."""
    unexpected = []
    for route in _iter_api_routes():
        if _has_any_auth_dep(route):
            continue
        for method in route.methods or []:
            key = (method, route.path)
            if key not in EXPECTED_PUBLIC:
                unexpected.append(f"  {method} {route.path}")

    assert not unexpected, (
        "인증 없이 접근 가능한 예상 외 엔드포인트가 감지되었습니다:\n"
        + "\n".join(unexpected)
        + "\n\n의도적으로 public으로 만든 경우 EXPECTED_PUBLIC 에 추가하세요."
    )


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
