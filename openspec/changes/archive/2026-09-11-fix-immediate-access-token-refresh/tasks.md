## Implementation Tasks

- [x] JSON/직접 fetch/자동 갱신 및 backend 실패 경계를 조사하고 범위를 확정한다.
- [x] timer 이전 만료 요청과 직접 인증 요청의 복구 누락을 회귀로 재현하고 공통 client를 수정한다.
- [x] 탭 mount/focus/visible 재개 시 기존 shared refresh를 즉시 실행하고 lifecycle 회귀를 추가한다.
- [x] first-party raw fetch 소비자를 공통 인증 복구 경로로 전환한다.
- [x] targeted/auth/lumen 검증 및 브라우저 HTTP 복구 smoke를 수행한다.
- [x] 보안/아키텍처/changelog를 갱신하고 gate 및 임시 index staged check 후 archive한다.

## Verification evidence

- 수정 전 재현: 만료된 대시보드 동시 요청 2개가 refresh보다 먼저 전송됨; 다운로드 첫 401이 caller 오류로 반환됨.
- 집중 회귀 8파일 103 passed; 이후 채팅 refresh HTTP 오류 분류 회귀를 추가하여 해당 파일 11 passed.
- auth domain: backend 154 / frontend 59 passed. Lumen BFF domain: backend 29 / frontend 100 passed.
- 실제 Chrome에서 Vite-served client/lifecycle/chat consumer와 합성 HTTP 응답으로 확인: dashboard 2요청은 refresh 1회 후 바로 200, SSE와 XHR는 각각 401 → refresh 200 → 재시도 200, focus 복귀는 timer를 기다리지 않고 refresh. 실제 사용자 자격/운영 API는 사용하지 않음.
- `npm run check`는 이번 변경 파일의 오류 없이 별도 기존 `ChatSettingsOverlay.test.ts:39`의 ChatUsage fixture 누락(found/누적 사용량 4필드) 1건으로 실패. 해당 채팅 사용량 작업은 수정하지 않음.
- 첫 gate는 검토 이후 Kolla defaults의 동시 변경으로 architecture snapshot이 stale해 중단됨. 복원된 defaults를 확인한 뒤 다시 stamp하고 gate 재실행.
- 최종 `npm run test:gate` 통과(Unit/Contract/Functional, backend lint/format). 동일 source `9043b3ed68bc6cc8324c94e0782a88ee651da81044990e880ac7755c2de2a6f4` / 2000 files의 isolated `GIT_INDEX_FILE` staged architecture check 통과. 검사 전후 실제 index bytes 불변; commit/push/deploy하지 않음.
