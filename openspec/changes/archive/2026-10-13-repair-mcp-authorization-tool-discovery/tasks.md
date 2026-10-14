## Implementation Tasks

- [x] 외부 MCP OAuth 인증 생성 실패를 실제 동의·Keystone HTTP·권한 및 프로젝트 범위 경로로 추적하고 재현한다.
- [x] 활성 Afterglow MCP가 Lumen 도구 검색·로드·호출에서 누락되는 경로를 추적하고 재현한다.
- [x] 확인된 인증/도구 연결 원인을 최소 수정하고 consumer-visible 회귀를 추가한다.
- [x] OAuth read/manage current/selected/all, MCP SDK 초기화·검색·실제 조회 호출, disabled/foreign/stale/revoked 경계를 HTTP runtime으로 검증한다.
- [x] Fake-provider native durable worker에서 발견된 producer/consumer 턴 identity 경쟁 조건을 수정하고 이전 tool result와 후속 응답이 각 assistant 메시지에 정확히 확정되는지 검증한다.
- [x] Lumen 컨텍스트 미리보기의 도구 구성과 실제 채팅 discovery·요청 구성이 같은 승인된 MCP 레지스트리를 사용하는지 검증한다.
- [x] 관련 suite와 compiled 브라우저 실제 동선 검증 후 docs/architecture/changelog에 증거와 운영 미검증 경계를 기록한다.
