## Contract
- [x] 현재 가격/등록 경로와 소유권 보호를 확인하고 additive JSON 계약을 고정한다.

## Implementation
- [x] 이미지 종류 discovery/등록/목록 관리와 별도 가격 편집 화면.
- [x] 텍스트·이미지·오디오별 입력·캐시 입력·출력 가격 저장과 기존 값 보존.
- [x] 초·분·시간 단위와 과금 기준/예약 비용 편집.
- [x] Lumen frozen 가격·실제 사용량 계산 연결.

## Verification
- [x] 소비자 행동 회귀 테스트·typecheck/build와 실제 브라우저 등록/가격 편집 smoke.
- [x] architecture/API 문서의 영향 범위와 검증 제한을 간결하게 갱신한다.
- [x] 다른 작업의 dirty source 검토와 전체 gate가 완료된 뒤 architecture guard를 갱신하고 archive한다.

Actual mounted component→synthetic-admin Lumen HTTP→SQLite에서 이미지 등록/종류 필터/활성 전환/가격 save·reopen·no-op과 음성 second/minute/hour/session 문자열을 확인했다. Minute 변경은 기존 second alias를 보존했고 같은 시간 가격으로 검증됐다. 390px editor는 scrollWidth 380px였고 양수/explicit-zero/미설정 가격을 구분했다. 운영 auth/BFF·MariaDB worker·paid provider 검증으로 승격하지 않는다.

Focused Vitest editor/selection/client/usage 4개 파일 84건 통과. `npm run test:all`은 backend 3307·frontend 1714·runner 9·contract 136·DB functional 28건 통과했고 `npm run check`는 2118개 파일 0 errors/0 warnings, production build도 통과했다. 실제 브라우저는 390px editor와 desktop 저장·재열기·no-op·프로젝트 전환을 관측했다. Delayed PATCH 응답 중 프로젝트 전환은 브라우저 interceptor timeout으로 시나리오를 끝내지 못했으며 permanent consumer 회귀가 fence를 검증한다.

전체 `npm run test:gate`는 stale architecture snapshot에서 중단했다. Backend Ruff check는 통과했으나 format check는 작업 외 `app/main.py`, `app/services/layer_build.py`, `tests/test_logging_contract.py`에서 실패했다. 이 파일을 재포맷하거나 source review marker를 덮어쓰지 않았다. 검토 범위는 ChatConfiguration, ModelMediaPricingEditor, 가격/selection helper, chat API·usage type과 해당 행동 회귀다.

2026-10-01 working-tree architecture guard는 stale이다. 관련 본문/API guide/changelog는 갱신했지만 다른 작업의 dirty source를 함께 stamp하지 않았다. 전체 게이트/검토가 완료될 때까지 archive하지 않는다.

2026-10-02 release integration: 전체 현재 source의 backend/frontend/package 경계를 review하고 발견한 blocker를 수정했다. 최종 `npm run test:gate`는 architecture guard·backend 3523·frontend 1896·contract 141·DB functional 28·backend Ruff/format을 모두 통과했다. `npm run check`는 2130 files/0 errors/0 warnings, production build도 통과했다. Working digest `f44758f90d282a4de681e4861573ea7976b181bf94090a78ac8437ad16027c24`. 이 결과는 위 과거 gate 실패를 숨기지 않으며 운영 auth/provider/deploy나 미완료 delayed PATCH 브라우저 시나리오의 증거로 승격하지 않는다.
