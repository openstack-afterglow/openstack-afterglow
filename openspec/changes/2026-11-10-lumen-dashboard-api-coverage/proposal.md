# Lumen 전체 API를 대시보드에서 제공하고 브리지 계약을 맞춘다

## Why

- 기준 명세는 Lumen 저장소의 `docs/api/`다. 그룹별 `reference.md`가 라이브 OpenAPI(2026-11-10 생성)에서 만든 210개 HTTP 연산과 연산별 인증·scope를 담는다. `docs/api/integrations/afterglow-bridge.md`는 Afterglow 수정 작업의 기준이라고 명시한다. 이전 `docs/api-reference.md`(0.6.10 candidate, 미검증)는 보조 자료다.
- Afterglow BFF `/api/v1/chat/{path}`는 `/v1/{path}`로 캐치올 중계하고 허용 목록이 없으므로 백엔드 도달성은 거의 전부 열려 있다. 빠진 것은 대시보드 UI다.
- 프론트엔드 호출을 확인한 결과, 210개 중 대시보드가 호출하는 연산은 약 100개다. 나머지는 관리자 연결·레지스트리·플러그인·런타임, 사용자 플러그인·코드 워크스페이스·Git 자격증명, run 하위 항목과 상호작용 응답, usage records, 그리고 API 클라이언트 전용 표면(compat Batch·Files·SDK 프로토콜)이다.
- 브리지 계약의 Afterglow 쪽 작업이 아직 없다. `mcp_lumen_selections`의 기본키는 `(owner_user_id, owner_project_id)`로 사용자·프로젝트당 권한 1개다. 마이그레이션 110은 없다. `/api/v1/mcp/lumen/snapshot`은 단일 `snapshot`만 돌려주고 `snapshots` 목록이 없다. 그 결과 여러 권한을 켜도 Lumen은 첫 번째 권한만 사용한다.

## What Changes

0. 브리지 계약(다중 권한): 마이그레이션 110(`mcp_lumen_selections`를 `(owner_user_id, owner_project_id, grant_id)` 기본키로 변경), `/snapshot`의 `snapshots` 목록, 권한별 `DELETE /api/v1/auth/mcp-tokens/{token_id}/lumen-default`, 프론트엔드의 권한별 토글(현재는 단일 PUT과 전체 DELETE만 호출).
1. 사용자 기능 격차: `plugin-bindings` 4개, `code-workspaces` 5개(목록·생성·조회·삭제·대화 워크스페이스 배정), `git-credentials` 4개, `runs/{id}/children` 1개, `runs/{id}/interactions/{iid}` 1개, `usage/records` 1개.
2. 관리자 기능 격차(30개): `mcp-connections` 5, `mcp-registry` 3, `mcp-bundles` 2, `plugin-bindings` 4 + `plugins` 1, `runtime-pools` 1 + `runtime-resources` 1, `agent-project-quotas` 2, `memory-model` 1, `models-dev` 3, `api-keys` 2(목록·한도), 프로바이더 수준 인증 5(`providers/{id}/auth/*`).
3. API 클라이언트 표면: compat Batch·Files·Chat Batch(14개), compat 미디어 4개, SDK 프로토콜 6개를 API 콘솔(테스트 호출 화면)로 제공한다. 실제 호출은 같은 BFF 경로를 쓴다.
4. 이미 대시보드가 제공하는 항목은 바꾸지 않는다. 관리자 mcp-servers·custom-tools·skills는 `ChatExtensionsManager`의 `base="/api/v1/chat/admin"` 경로로, 프로바이더 계정·자격증명·relay·probe·device 인증은 `ProviderAccountsPanel`로 이미 호출된다.

## Impact

- Lumen 원본 명세는 수정하지 않는다. Afterglow 쪽 BFF 경로는 캐치올 중계를 유지하며, 비밀 입력(프로바이더 키, 구독 토큰, registry 헤더)은 기존 `no-store` 및 readback 금지 원칙을 따른다.
- 권한 경계: 관리자 연산은 `require_admin`(사람 system admin)이고, 사용자 연산은 Keystone 토큰 또는 API 키 scope다. 대시보드는 Lumen 응답의 권한 결과를 그대로 쓰고 역할 배열로 우회하지 않는다.
- 배포 순서: 브리지 계약(마이그레이션 110 → Afterglow 브리지 → Lumen)을 따른다. 이 change는 운영 배포를 포함하지 않는다.
- 명세 버전 확인: 구현 전에 배포된 Lumen의 `/openapi.json`을 `docs/api/` 생성 결과와 대조한다.
