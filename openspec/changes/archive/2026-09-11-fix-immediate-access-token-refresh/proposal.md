## Why

장시간 열린 대시보드에서 access JWT 인증 실패가 먼저 노출되고 갱신은 뒤늦게 일어난다. JSON client는 401 재시도가 있지만 요청 전 만료 확인이 없고, layout은 60초 interval에만 의존한다. raw fetch 기반 채팅/SSE/첨부/다운로드와 XHR 업로드는 같은 복구 경로를 거치지 않는다.

## What Changes

- 기존 coalesced refresh를 재사용하여 현재 세션의 만료 120초 이내 access token은 인증 요청 전 갱신하고 진행 중 갱신을 기다린다.
- JSON/fetch/XHR 인증 요청은 공통 정책으로 401 직후 갱신 또는 이미 회전한 최신 토큰을 채택하여 한 번 재시도한다. 스트림은 HTTP handshake만 재시도하며 소비 중인 스트림을 재실행하지 않는다.
- 탭 mount/focus/visible 복귀 때 만료를 즉시 확인한다. 60초 보조 주기는 유지한다.
- request body/project/abort/업로드 progress 및 prefetch mutation fence 계약을 보존한다. presigned 외부 요청은 인증 갱신 대상에서 제외한다.
- refresh 401은 terminal, 503/429/network는 세션 보존 및 기존 cooldown 유지. logout revocation fence와 늦게 도착한 401/cross-tab winner 보호를 유지한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

브라우저 인증 요청의 즉시 access-token 복구 및 foreground 재개 시 선제 갱신.

## Impact

frontend/src/lib/api/client.ts, 인증 raw fetch 소비자, layout 갱신 lifecycle 및 관련 회귀 테스트. backend JWT/Keystone 검증, 세션 수명과 배포 설정은 변경하지 않는다. docs/security.md, ARCHITECTURE.md, CHANGELOG.md를 갱신한다. dev에서만 작업하고 기존 작업 및 실제 index를 보존하며 commit/push/deploy하지 않는다.

## Acceptance

만료 임박 요청이 timer 없이 refresh 후 성공하고 동시 요청은 한 번만 갱신한다. raw stream과 업로드의 첫 401이 caller 오류로 노출되지 않고 재시도 결과가 전달된다. 취소·terminal auth·transient service failure 및 기존 회전 경합 회귀를 통과한다. exact selector → auth/lumen target → test:gate 순서로 검증하고 임시 index로 staged architecture check를 통과한다.
