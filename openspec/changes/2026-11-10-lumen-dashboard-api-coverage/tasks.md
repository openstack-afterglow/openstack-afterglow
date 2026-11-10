# Tasks

## 0. Gap map 기준 고정

- [ ] 0.1 Lumen `docs/api/*/reference.md` 9개 그룹 210개 연산을 기준 목록으로 고정한다. 생성 기준은 `docs/api/README.md` 생성 명령과 같은 라이브 OpenAPI다.
- [ ] 0.2 배포된 Lumen `/openapi.json`을 받아 기준 목록과 diff한다. 불일치하면 구현 전에 이 change의 목록을 갱신한다.
- [x] 0.3 gap map 1차: 프론트엔드 `api.*`·`fetchWithAuth` 호출과 동적 베이스 경로(`${base}`, `credentialPath`)를 확인해 격차를 정정했다. 확정 격차는 아래 1~5절과 같다.

## 1. 브리지 계약 (다중 권한, Afterglow 선행 작업)

- [x] 1.1 마이그레이션 110(`backend/migrations/110_mcp_lumen_multigrant.sql`): 기본키를 `(owner_user_id, owner_project_id, grant_id)`로 바꾸고 manifest를 등록했다. 기존 행은 그대로 유지된다. 롤백 SQL은 포함하지 않았다(ledger 기록 후 비멱등).
- [x] 1.2 `/api/v1/mcp/lumen/snapshot`이 `snapshots` 목록을 반환하고, 실패한 grant만 제외한다. 최상위 `snapshot`·`entries`·`service_fingerprint`는 첫 번째 grant와 같다.
- [x] 1.3 `DELETE /api/v1/auth/mcp-tokens/{token_id}/lumen-default` 추가. `PUT`은 추가로 켜고, 모든 변경은 소유자 generation을 올린다.
- [x] 1.4 `defaults`: 내부 기본 흐름은 퇴역한 내부 grant의 선택 행만 지우고 사용자가 켠 개인 토큰 선택은 유지한다. 해제(`disable_lumen_grant`)도 내부 선택만 지운다.
- [x] 1.5 프론트엔드 해제 버튼을 권한별 `DELETE`로 바꿨고, 목업 상태를 권한별 목록으로 바꿨다.
- [x] 1.6 테스트: DB 기능 레인(`test_mcp_lumen_defaults_db.py`의 독립 선택·권한별 해제·폐기 grant 제외), 계약 테스트(다중 grant 목록·부분 제외·빈 목록), 경계 테스트(`DELETE .../lumen-default`의 외부 workspace 거부), vitest·svelte-check.
- [ ] 1.7 Lumen 저장소의 `docs/api/integrations/afterglow-bridge.md`는 이 저장소 밖에 있으므로 건드리지 않았다. Afterglow 쪽 문서(ARCHITECTURE.md, docs/api/auth.md)는 갱신했다. Lumen 소유자가 "Afterglow에 남은 작업" 항목을 해소 표시해야 한다.
- [ ] 1.8 알려진 한계: `GET /api/v1/chat/cloud-tools`는 첫 번째 유효 선택 하나만 요약한다. 여러 선택의 도구 목록 합산 표시는 아직 구현하지 않았다.

## 2. 사용자 기능 격차 (대시보드, 사용자 권한)

- [ ] 2.1 플러그인 바인딩 사용자 화면: `GET/POST/PATCH/DELETE /v1/plugin-bindings` (scope `native:extensions:read|write|delete`). 비공개 설정은 편집 권한이 있을 때만 `include_private=true`로 읽는다.
- [ ] 2.2 코드 워크스페이스: `GET/POST /v1/code-workspaces`, `GET/DELETE /v1/code-workspaces/{id}`, `PUT /v1/conversations/{id}/code-workspace`. 생성·삭제는 202 비동기 결과를 상태 폴링한다.
- [ ] 2.3 Git 자격증명: `GET/POST /v1/git-credentials`, `PUT/DELETE /v1/git-credentials/{id}`. 토큰 입력은 readback하지 않는다.
- [ ] 2.4 run 하위 항목: `GET /v1/runs/{id}/children`(부모 소유자 검사, `native:runs:read`).
- [ ] 2.5 상호작용 응답: `POST /v1/runs/{id}/interactions/{iid}`(`native:runs:write`). `interaction.resolved` SSE 이벤트와 연결하고, 응답 버튼을 실제로 렌더링하는지 확인한다.
- [ ] 2.6 사용량 상세: `GET /v1/usage/records`(`usage:read`)를 사용량 화면의 원장 표에 연결한다.

## 3. 관리자 기능 격차 (시스템 관리자, require_admin)

- [ ] 3.1 MCP 연결: `GET/POST /v1/admin/mcp-connections`, `PATCH/DELETE /v1/admin/mcp-connections/{id}`, `POST .../catalog/refresh`. 실패한 탐색은 마지막 정상 카탈로그를 유지하며 오류 종류만 표시한다.
- [ ] 3.2 MCP 레지스트리·번들: `GET /v1/admin/mcp-registry`, `POST .../install-all`, `POST .../{entry_id}/install`, `GET /v1/admin/mcp-bundles`, `POST .../{slug}/install`. 설치는 idempotent이며 재설치가 기존 연결을 덮어쓰지 않음을 화면에 명시한다.
- [ ] 3.3 플러그인: `GET /v1/admin/plugins`, `GET/POST/PATCH/DELETE /v1/admin/plugin-bindings`.
- [ ] 3.4 런타임: `GET /v1/admin/runtime-pools`, `GET /v1/admin/runtime-resources`(읽기 전용).
- [ ] 3.5 에이전트 프로젝트 쿼터: `GET/PUT /v1/admin/agent-project-quotas/{project_id}`.
- [ ] 3.6 메모리 모델: `PUT /v1/admin/memory-model`(204). 기존 title-model 화면 패턴을 따른다.
- [ ] 3.7 모델 가격 가져오기: `GET /v1/admin/models/pricing/models-dev/providers`, `GET .../{models_dev_provider_id}`, `POST .../import`. 가격은 관리자 검토 후에만 등록한다.
- [ ] 3.8 API 키 관리(관리자): `GET /v1/admin/api-keys`, `PATCH /v1/admin/api-keys/{key_id}/limits`.
- [ ] 3.9 프로바이더 수준 인증: `PUT /v1/admin/providers/{id}/auth/token`, `DELETE .../auth`, `POST .../auth/device`, `POST .../auth/device/{attempt}/poll`, `DELETE .../auth/device/{attempt}`. 기존 계정·자격증명 수준 패널의 흐름을 재사용한다.

## 4. API 클라이언트 표면 (API 콘솔)

- [ ] 4.1 Chat Batch: `GET/POST /v1/chat/batches`, `GET /v1/chat/batches/{id}`, `GET .../items`, `POST .../cancel` (native, `native:batches:*`). 한 batch는 여러 operation을 섞을 수 있으므로 item 상태를 함께 보여 준다.
- [ ] 4.2 Compat Batch·Files: `GET/POST /v1/batches`, `GET/POST /v1/batches/{id}/cancel`, `GET /v1/files`, `POST /v1/files`, `GET/DELETE /v1/files/{id}`, `GET /v1/files/{id}/content`. 파일 업로드는 `purpose=batch`만 받는다.
- [ ] 4.3 Compat 미디어: `POST /v1/audio/speech`, `/v1/audio/transcriptions`, `/v1/images/generations`, `/v1/images/edits`(API 키, compat scope).
- [ ] 4.4 SDK 프로토콜 콘솔: `POST /v1/chat/completions`, `/v1/responses`, `/v1/messages`, `/v1/messages/count_tokens`, `GET /v1/models`, `/v1/cli/models`. 키는 화면에서 한 번만 보여 주고 저장하지 않는다.
- [ ] 4.5 Claude Gateway: device 승인 셸은 기존 `POST /api/v1/chat/claude-gateway/authorize`로 이미 호출된다. 나머지 게이트웨이 프로토콜 엔드포인트는 Claude Code 클라이언트 전용이므로 콘솔에 노출하지 않고 문서로 안내한다.

## 5. 검증과 문서

- [ ] 5.1 백엔드: 새 BFF 경로마다 pytest(권한 거부, 소유자 불일치, 관리자 전용 경계, 비밀 응답 미노출). 기존 catch-all 테스트에 회귀가 없는지 확인한다.
- [ ] 5.2 프론트엔드: 화면별 vitest와 `svelte-check`. 비밀 입력 화면은 readback 금지를 검증한다.
- [ ] 5.3 게이트: `npm run test:gate`(docs:check 포함). 운영 Compose·볼륨·인증정보는 건드리지 않는다.
- [ ] 5.4 문서: ARCHITECTURE.md, docs/api/chat.md(또는 해당 문서), docs/security.md, docs/testing.md를 갱신한다.
- [ ] 5.5 실제 증거: 로컬 Lumen 또는 격리 환경 HTTP 호출. 운영 Lumen·Keystone 검증은 이 change 범위 밖이며 명시한다.

## 격차 집계 (검증 기준)

| 영역 | 연산 수 | 상태 |
| --- | --- | --- |
| 브리지 계약(다중 권한) | 2 (PUT 기존, DELETE 권한별 신규) + snapshot 응답 | 미구현 |
| 사용자 기능 | 16 | 미구현 |
| 관리자 기능 | 30 | 미구현 |
| API 클라이언트 표면 | 23 (Batch·Files 14, 미디어 4, SDK 프로토콜 5) | 미구현 |
| 이미 대시보드 제공 | 관리자 mcp-servers·custom-tools·skills 12, 프로바이더 계정·자격증명 등 수 | 유지 |
| 제외 (프로토콜·헬스) | 15 (`/`, `/v1/`, health, ready, compat discovery, policy, claude-gateway 프로토콜 7, mcp-oauth callback) | 해당 없음 |

집계는 `reference.md` 표와 프론트엔드 호출 확인에 기반한 수동 검증치다. 최종 수치는 0.2 diff 이후 확정한다.
