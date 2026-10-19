## Why

관리자 화면을 새로고침하면 root와 admin layout이 각각 `/api/v1/auth/me?refresh=true`를 발행한다. Admin layout은 별도 `verifiedIdentity`를 관리하므로 서버가 검증한 정상 refresh/rescope에서도 자식을 해제하고 전체 관리자 권한 확인 화면으로 돌아간다. 중복 native 인증 비용과 불필요한 화면·입력 재생성이 발생한다.

## What Changes

- Root `createAuthVerificationController`를 브라우저 인증 검증의 단일 소유자로 유지하고 admin layout의 별도 요청·retry·identity 상태를 제거한다.
- Admin layout은 기존 `authReady`와 현재 `isAdmin`을 함께 소비한다. 저장된 flag만으로 열지 않으며 새 document의 복원은 root `/me` 한 번이 성공해야 한다.
- 이미 준비된 exact-owner native token refresh는 기존 readiness 계약에 따라 화면과 초안을 유지한다. 명시적인 scope 전환은 `projectSwitching`부터 이전 workspace를 숨긴다. Root는 새 token을 background `/me`로 재검증하고, 확인된 관리자 철회·401·장애는 기존 fail-closed 경계를 따른다.
- Fresh mapped login은 기존 일회성 메모리 proof를 재사용한다. 일반 data refresh·관리자 내부 탐색 때문에 별도 `/me`를 추가하지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- 관리자 진입·refresh 시 root와 동일한 인증 readiness를 소비하는 화면 생명주기.

## Impact

Frontend admin layout과 그 권한 전이 회귀만 변경한다. API·native grants·JWT/Redis 수명·권한 cache/TTL·schema·config·의존성·service ownership·배포 topology는 변경하지 않는다. 관리자 endpoint의 `require_admin` live native 검증은 유지한다. 공유 checkout/index와 실행 중인 사용자 서비스를 보존하며 운영 배포는 수행하지 않는다.

완료 기준: restored/unverified admin의 첫 `/me`가 하나이고 성공 전 private child가 없으며, 정상 token refresh 중 같은 DOM/초안이 유지되고, revocation·401·outage·다른 login·scope/ABA의 늦은 응답이 관리자 화면을 열 수 없다. 실제 Chromium 새로고침·탐색·refresh와 합성 API 경계를 명시적으로 검증한다.
