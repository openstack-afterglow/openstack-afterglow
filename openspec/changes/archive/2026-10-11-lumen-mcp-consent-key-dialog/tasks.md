## Implementation Tasks

- [x] 1. 기본 Afterglow MCP를 비활성으로 노출하고 명시적 읽기/관리 승인·비활성화 API와 실제 실행 fence를 구현한다.
- [x] 2. 관리자 승인 remote MCP의 사용자별 활성화를 구현하고 직접 MCP 추가 및 OAuth 연결을 보존한다.
- [x] 3. 폐기된 API 키 기본 숨김과 전체 보기 전환을 구현한다.
- [x] 4. API 키 발급 모달에서 프로젝트·이름·만료·권한·월 한도를 함께 선택하고 native 저장·만료 인증을 구현한다.
- [x] 5. 관련 소비자 경계 회귀, native HTTP/datastore smoke와 실제 Chromium의 승인·발급·목록·반응형 동작을 검증한다.
- [x] 6. 검증된 범위의 architecture/API/design/changelog와 DB 양방향 호환성 한계를 기록하고 scoped architecture guard를 실행한다.

## Parent completion (2026-10-11)

The interrupted session's canonical HTTP/SQL/Redis, process-readiness and compiled Chromium receipts remain scoped to their original source and synthetic identity/provider boundaries in docs/testing.md. The parent integration additionally verified native runtime/manifest byte parity, applied real 001–026 migrations to a fresh owned local MariaDB schema, and passed both current-source owner-activation and native-key integration files (exit0; lumen_dev_integration_20261011170327_c864b3ba2e.receipt.json). The final merged Afterglow source passed the unmodified full test:gate and current-source API/compiled-browser smoke; these are separate from the earlier session's failed whole gates. Production 085/086/native026 cutover, restored current snapshot/original keys, two-way writer/schema compatibility, mixed-version queue and rollback remain unqualified; no production migration, sibling source publish or deployment was performed.

