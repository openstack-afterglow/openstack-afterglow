## Implementation Tasks

- [x] Lumen additive discovery 계약과 Afterglow BFF 전달을 연결한다.
- [x] source·정상 빈 결과·safe 실패·미지원 및 retry를 표시하고 live fallback/부분 목록을 거부한다.
- [x] 후보 검토 후 기존 POST 등록·활성화 또는 비활성 저장, 수동 입력과 가격/capability 관리 경로를 유지한다.
- [x] discovery generation/provider/token/project/destroy fence를 적용한다.
- [x] bulk 등록 provider snapshot, scope 취소와 부분 실패 상태를 구현한다.
- [x] model mutation invalidation 및 명시적 refresh/focus/visible 목록 갱신 시 유효한 선택을 유지한다.

## Verification Tasks

- [x] deferred 응답 A→B/닫기/재조회와 bulk provider 혼합 회귀를 검증한다.
- [x] BFF safe schema 전달과 열린 ChatPanel 선택 보존을 검증한다.
- [x] 실제 브라우저 검색·검토·등록·재시도·provider 전환을 검증한다.
- [x] mobile/tablet/desktop, 767/768·1023/1024, light/dark 배치를 검증한다.
- [x] 영향받는 이미지의 지원 아키텍처 빌드·실행을 검증한다.
- [x] canonical local services 배포·readiness·인증 조회를 검증한다.
- [ ] 실제 Anthropic/OpenAI live discovery와 승인된 최소 text inference/compat/usage 증거를 기록한다.
- [x] architecture·API 문서·검증 증거를 갱신하고 canonical guard와 gates를 실행한다.

## Verification evidence — 2026-09-23

- Focused frontend onboarding/picker suites: 63 passed; BFF contract: 37 passed. `npm run check`: 0 errors / 0 warnings. `npm run test:gate` passed after formatting the changed BFF regression test.
- Real Chromium source-component smoke exercised filtering, reviewed inactive/explicit-price activation, retry, provider switching and explicit capability editing. Registration and capability dialogs passed dark/light widths 390, 767, 768, 1023, 1024, 1280 and 1440; registration actions remained accessible at 720×500. The temporary fixture was removed before image build.
- Frontend, Lumen API and worker images built and executed on linux/amd64 and linux/arm64. Canonical `docker-compose.dev.yml` build, migration and targeted `up --no-deps --no-build --wait` preserved the existing project and volumes. Frontend/API health checks passed; the worker has no declared Docker health check, so readiness was verified by observing its actual Redis BRPOP consumer.
- Authenticated deployed BFF smoke: missing-provider-key discovery returned HTTP 200 + no-store + safe error and no candidates. An unknown model remained unpriced/inactive, then appeared immediately in user models after explicit price activation. Only temporary smoke provider/model rows were created and deleted; final inventory returned to empty. Deployed admin discovery/navigation also passed all 14 dark/light responsive states.
- Architecture working checks and `--staged` checks passed. Staged verification used isolated temporary indexes; the user's real indexes were hash-verified unchanged. No commit, push or production deployment.
- **Blocked:** local provider inventory is empty and no real Anthropic/OpenAI API key is configured. No paid upstream discovery/inference or real-provider billing claim is made. Real MariaDB/Redis and synthetic provider process-stack tests are separate evidence. This change remains open, not archived, until live acceptance can be exercised.
