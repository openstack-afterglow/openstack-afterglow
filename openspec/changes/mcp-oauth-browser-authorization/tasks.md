## Implementation Tasks

- [x] 현재 source/discovery를 읽고 운영 pieroot 세션에서 DCR201, authorize303, consent200, PKCE code exchange200, MCP initialize/tools-list200 및 refresh rotation200을 관찰한다.
- [x] 개인 키를 유지하면서 계정 화면에 secret-free OAuth JSON·authorize endpoint·연결 방법을 네 언어로 제공한다.
- [x] 미로그인 exact consent shell과 로그인 후 프로젝트 선택에서 ticket을 보존하고 scoped approval 경계를 검증한다. Optional refresh client_id binding을 실제 MariaDB HTTP7조건으로 검증한다.
- [x] 공개 MCP 가이드의 OAuth/client 사용 예시 및 endpoint·토큰 수명·폐기를 네 언어로 갱신한다.
- [x] consumer-visible regression과 실제 local browser smoke, project test gate 및 build를 완료한다.
- [ ] architecture/changelog·patch version을 갱신하고 dev exact-SHA CI 및 불변 release artifact를 검증한다.
- [ ] deployment server에서만 canonical Kolla genconfig/pull/prechecks/reconfigure를 실행하고 운영 OAuth·API 키 및 responsive UI를 확인한다.
- [ ] 검증용 OAuth grant/token을 회수하고 실제 증거·한계를 기록한 뒤 OpenSpec을 archive한다.

## Local verification

- `npx vitest run`의 hooks/account/consent-helper/consent-page4파일72조건 통과. Unauthenticated consent-shell 회귀는 수정 전302/실패, 수정 후200/no-store/no-referrer이며 adjacent route는 계속302다.
- 실제 MariaDB HTTP refresh7조건 통과. Wrong/empty client, omitted client, code expiry/ticket cleanup, missing/ambiguous binding과 correct-client replay를 포함한다.
- `npm run test:gate` 통과: backend unit4,188, frontend332files/2,510 + runner9, contract154, disposable DB functional35, Ruff check와 format554files. Source digest `b6d0a8c48f6a905836c9c44743782c4802310281fa698fb514a8b9e7a9f45f90`.
- Version1.30.7 동기화, Svelte check2,338files/0errors·기존 DocCodeBlock tabindex경고1, i18n0errors/0warnings·9,377messages·hardcoded Korean0, production build 통과.
- 실제 built frontend Chromium: 미로그인 ticket 보존→로그인→프로젝트 선택(선택 전 consent GET0)→scoped approval/deny·ticket 정리. Secret-free clipboard JSON과 기존 개인-key consumer 회귀를 유지한다.
- 계정4언어 × light/dark ×390/767/768/1023/1024/1440px48조건에서 actual theme/viewport·credential-free JSON·가로 넘침0을 확인했다. 공개 가이드4언어 ×390/1440px8조건에서 OAuth endpoint/client metadata/refresh 설명과 가로 넘침0을 확인했다.
- UI identity/API는 합성이다. 이 결과는 운영 로그인·Keystone/provider·클라이언트 제품 전체 호환성의 증거가 아니다. Receipt: `/private/tmp/afterglow-mcp-release-ctnj_jie/oauth-ui-1307-receipt.json`.
