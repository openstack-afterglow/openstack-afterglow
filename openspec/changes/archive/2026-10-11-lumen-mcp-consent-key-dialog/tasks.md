## Implementation Tasks

- [x] 1. 기본 Afterglow MCP를 비활성으로 노출하고 명시적 읽기/관리 승인·비활성화 API와 실제 실행 fence를 구현한다.
- [x] 2. 관리자 승인 remote MCP의 사용자별 활성화를 구현하고 직접 MCP 추가 및 OAuth 연결을 보존한다.
- [x] 3. 폐기된 API 키 기본 숨김과 전체 보기 전환을 구현한다.
- [x] 4. API 키 발급 모달에서 프로젝트·이름·만료·권한·월 한도를 함께 선택하고 native 저장·만료 인증을 구현한다.
- [x] 5. 관련 소비자 경계 회귀, native HTTP/datastore smoke와 실제 Chromium의 승인·발급·목록·반응형 동작을 검증한다.
- [x] 6. 검증된 범위의 architecture/API/design/changelog와 DB 양방향 호환성 한계를 기록하고 scoped architecture guard를 실행한다.

## Original-session verification receipt

- Local-only 증거: `/Users/pieroot/.local/share/afterglow-proofs/lumen-settings-consent-20261011/`; 실제/합성·image/current-source·owned/concurrent-snapshot 범위는 `docs/testing.md`에 분리했다.
- Canonical cloud arm64/amd6442checks·80sourceHTTP·74fakeIAM HTTP, native API/worker×두 architecture268assertions·228HTTP·104migration applications와 별도 실제 lifespan/worker readiness를 확인했다. 최신 공유 model/authority는 별도 host source21checks·40HTTP·37SDK HTTP와 최종 consent3files82개로 검증했다.
- Compiled Chromium10시나리오·theme/viewport/locale32조건, frontend2909+runner9·contracts156·native integration288·i18n0문제, scoped Ruff8files와 네 exact architecture working/staged scope가 통과했다.
- 독립 complete backend unit4990개·원래 functional118개/23deselected도 통과했다. Functional은 current shared migration test를 변경 없이 추가 overlay한 scope이며 initial frozen fixture2실패를 보존했다. `tests/final-functional.json`에 exact source hashes와 owned stores를 기록한다.
- 전체 `npm run test:gate`는 installer PTY timeout으로 실패했다. 별도 frozen whole lint3import·admin quota Svelte Props1error/기존 warnings2도 보존하며 full gate green 또는 commit/push로 보고하지 않는다. 구현 결합 AST cache 검사만 제거하고 소비자 행동 회귀는 유지했다.
- Live IAM/OAuth/MCP tool success·paid inference·production snapshot/원래 키·양방향 writer/schema·mixed-version·publish/deploy는 미검증이다. Private config·shared index·root review marker·기존 stores/volumes/keys를 보존했다. gbrain CLI 부재로 sync하지 않았다.


## Parent completion (2026-10-11)

The interrupted session's canonical HTTP/SQL/Redis, process-readiness and compiled Chromium receipts remain scoped to their original source and synthetic identity/provider boundaries in docs/testing.md. The parent integration additionally verified native runtime/manifest byte parity, applied real 001–026 migrations to a fresh owned local MariaDB schema, and passed both current-source owner-activation and native-key integration files (exit0; lumen_dev_integration_20261011170327_c864b3ba2e.receipt.json). The final merged Afterglow source passed the unmodified full test:gate and current-source API/compiled-browser smoke; these are separate from the earlier session's failed whole gates. Production 085/086/native026 cutover, restored current snapshot/original keys, two-way writer/schema compatibility, mixed-version queue and rollback remain unqualified; no production migration, sibling source publish or deployment was performed.

