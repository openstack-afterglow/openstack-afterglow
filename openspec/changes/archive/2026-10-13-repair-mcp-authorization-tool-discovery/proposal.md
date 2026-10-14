## Why

사용자 보고에서 외부 MCP OAuth 동의는 읽기/관리 및 일부/전체 프로젝트 모두 인증 생성에 실패한다. Lumen의 Afterglow MCP 승인은 활성 상태인데 채팅 도구 검색은 `loaded_tools=[]`, `tools=[]`를 반환한다. 화면의 승인 표시가 아닌 실제 연결과 도구 실행을 복구한다.

## What Changes

- 외부 OAuth 동의→프로젝트별 restricted application credential→code/token→MCP 초기화 경로의 실제 실패 원인을 추적하고 최소 수정한다.
- Afterglow 선택 snapshot→Lumen durable admission/worker→MCP discovery/search/load/call 연결을 추적하고 실제 도구를 제공한다.
- 실제 fake-provider native worker 검증에서 발견된 queued tool-result 턴 소유권 경합을 발행 시점 originating ordinal로 수정하고 persisted assistant 메시지별 완료를 검증한다. 공개 protocol/journal schema는 바꾸지 않는다.
- 현재 caller/user/project, 승인된 target, read/manage, PKCE/resource/state/expiry/revocation 경계를 유지한다.
- 실제 HTTP/SQL/Redis/MCP SDK 및 compiled 브라우저로 연결과 실행을 검증하고 합성 identity/provider/cloud와 운영 수용 증거를 분리한다.

## Capabilities

### New Capabilities

없음. 기존 MCP 인증 및 도구 연결의 결함 복구다.

### Modified Capabilities

- 외부 MCP OAuth 승인 및 restricted credential 준비.
- Lumen 내장 Afterglow MCP discovery와 실제 도구 호출.

## Impact

영향 범위는 Afterglow MCP authority/BFF 및 원인이 있는 native Lumen MCP discovery/runtime이다. 새 인증 우회, privileged credential fallback, 자동 동의, 유료 provider 호출, 실제 cloud mutation, 운영 schema/deployment, 커밋·푸시는 포함하지 않는다. 공유 checkout/index/Compose/DB와 사용자 동시 변경을 보존한다.
