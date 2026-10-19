## Implementation Tasks

- [x] Root/admin 중복 `/me`와 정상 continuation의 화면 해제 원인을 추적하고 서버 live 권한 경계를 확인한다.
- [x] Root/admin 중복 요청의 failing-before와 정상 refresh 중 초안 보존 회귀를 기록한다.
- [x] Admin layout을 root readiness의 소비자로 단순화하고 기존 보안 실패·mockup 경계를 유지한다.
- [x] 권한 철회·401·장애·다른 login/scope·ABA와 정상 refresh의 관련 회귀 및 named auth/access target을 검증한다.
- [x] 실제 격리 Chromium에서 첫 새로고침·내부 탐색·token refresh·철회·장애·responsive 화면을 확인하고 합성/운영 증거를 구분한다.
- [x] 문서/architecture/changelog에 확인한 계약과 검증 경계를 기록하고 change를 archive한다.
