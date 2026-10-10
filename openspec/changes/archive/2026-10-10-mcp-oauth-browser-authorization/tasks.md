## Implementation Tasks

- [x] 현재 source/discovery를 읽고 운영 pieroot 세션에서 DCR201, authorize303, consent200, PKCE code exchange200, MCP initialize/tools-list200 및 refresh rotation200을 관찰한다.
- [x] 개인 키를 유지하면서 계정 화면에 secret-free OAuth JSON·authorize endpoint·연결 방법을 네 언어로 제공한다.
- [x] 미로그인 exact consent shell과 로그인 후 프로젝트 선택에서 ticket을 보존하고 scoped approval 경계를 검증한다. Optional refresh client_id binding을 실제 MariaDB HTTP7조건으로 검증한다.
- [x] 공개 MCP 가이드의 OAuth/client 사용 예시 및 endpoint·토큰 수명·폐기를 네 언어로 갱신한다.
- [x] consumer-visible regression과 실제 local browser smoke, project test gate 및 build를 완료한다.
- [x] architecture/changelog·patch version을 갱신하고 dev exact-SHA CI 및 불변 release artifact를 검증한다.
- [x] 운영 consumer에서 발견한 SDK cold `tools/call`의 None.params를 수정하고 public pagination·validation·read/write 권한 경계와 실제 TCP consumer를 검증한다.
- [x] corrective patch1.30.8와 후속 real-provider session repair1.30.9의 전체 gate·architecture·dev exact-SHA CI·불변 image/release qualification을 완료한다.
- [x] deployment server의 `/etc/kolla`에서 native `-i /etc/kolla/multinode --tags afterglow` canonical genconfig/pull/prechecks/reconfigure를 실행하고 운영 OAuth·API 키 및 responsive UI를 확인한다.
- [x] 검증용 OAuth grant/token을 회수하고 실제 증거·한계를 기록한 뒤 OpenSpec을 archive한다.

## Local verification

- `npx vitest run`의 hooks/account/consent-helper/consent-page4파일72조건 통과. Unauthenticated consent-shell 회귀는 수정 전302/실패, 수정 후200/no-store/no-referrer이며 adjacent route는 계속302다.
- 실제 MariaDB HTTP refresh7조건 통과. Wrong/empty client, omitted client, code expiry/ticket cleanup, missing/ambiguous binding과 correct-client replay를 포함한다.
- `npm run test:gate` 통과: backend unit4,188, frontend332files/2,510 + runner9, contract154, disposable DB functional35, Ruff check와 format554files. Source digest `b6d0a8c48f6a905836c9c44743782c4802310281fa698fb514a8b9e7a9f45f90`.
- Version1.30.7 동기화, Svelte check2,338files/0errors·기존 DocCodeBlock tabindex경고1, i18n0errors/0warnings·9,377messages·hardcoded Korean0, production build 통과.
- 실제 built frontend Chromium: 미로그인 ticket 보존→로그인→프로젝트 선택(선택 전 consent GET0)→scoped approval/deny·ticket 정리. Secret-free clipboard JSON과 기존 개인-key consumer 회귀를 유지한다.
- 계정4언어 × light/dark ×390/767/768/1023/1024/1440px48조건에서 actual theme/viewport·credential-free JSON·가로 넘침0을 확인했다. 공개 가이드4언어 ×390/1440px8조건에서 OAuth endpoint/client metadata/refresh 설명과 가로 넘침0을 확인했다.
- UI identity/API는 합성이다. 이 결과는 운영 로그인·Keystone/provider·클라이언트 제품 전체 호환성의 증거가 아니다. Receipt: `/private/tmp/afterglow-mcp-release-ctnj_jie/oauth-ui-1307-receipt.json`.

## Release qualification and inventory policy

- Release source `59cd235aaa73e5c64091af1ca20c66990ac99e45`, 불변 tag `v1.30.7`. Exact dev CI37929667042와 tag Docker CI37930426730은 required tests/build/manifest 모두 성공; live OpenStack CI는 credential gate에 따라 skipped이며 운영 proof로 대체하지 않는다. Helm Chart Release37930426181도 성공이다.
- 네 version image의 실제 registry index가 `latest`와 같고 모든 declared architecture에서 해당 revision·version1.30.7·non-root 실행을 확인했다. API/frontend/worker는 amd64, Cloud Shell은 amd64/arm64. Receipt `/private/tmp/afterglow-mcp-release-ctnj_jie/oauth-1307-image-execution.json`.
- 운영 변경은 Afterglow backend/frontend/worker immutable pin과 source role/site 링크뿐이다. 기존 operator lock·형제 package/image/config·Cloud Shell 운영 설정·datastore/schema·키를 변경하지 않는다. Private recovery root `/home/pieroot/.cache/mcp-oauth-1307`.
- 2026-10-09 사용자 지시로 정식 inventory `/etc/kolla/multinode`를 직접 사용한다. 기존 inventory bytes/대상과 과거 `multimode` 실행 기록은 보존하되 alias를 생성·복구하지 않는다. 현재 경로 parse 및 실제 control/afterglow3대 dispatch를 새 receipt로 확인한다.
- 정규 실행 전 guard가 `passwords.yml`에 추가된 `palimpsest_database_password`를 감지해 CLI 실행 전에 중단했다. 값 노출 없이 기존 credential 전부 동일·추가 값이 이미 존재한 canonical plugin secret과 동일함을 검증하고 별도 private baseline `operator-before-1307-multinode.tar.gz`를 보존했다. 기존 복구본과 receipt를 덮어쓰거나 자격 증명을 회전하지 않았다.

## Production consumer blocker and corrective patch

- v1.30.7 canonical `/etc/kolla/multinode`의 genconfig/pull/prechecks/reconfigure 네 단계가 모두 rc0이며 실제 세 controller가 exact image revision을 사용한다. Public consent shell은 세 frontend에서200/no-store/no-referrer다. Receipt `wireguard-dmslab:/home/pieroot/.cache/mcp-oauth-1307/kolla-afterglow-1307-multinode.json`, `runtime-after.json`, `http-smoke-1307.json`.
- 실제 browser 승인→loopback PKCE code 교환200, read tools/list28개를 관찰했으나 capabilities `tools/call`은 HTTP200/`isError=true`/None.params였다. 이는 완료가 아니라 blocker다. Wrong-client refresh400 invalid_grant 뒤 correct-client rotation200·new bearer tools/list200, revoke200·revoked bearer401을 확인하고 임시 grant를 폐기했다.
- Installed SDK1.28.1은 cold `_get_cached_tool_definition`에서 ListToolsRequest handler를 None으로 호출한다. 수정 전 실제 SDK HTTP regression은 cold/beyond-first-page 두 조건 모두 같은 오류로 실패했다. 정확한 callback annotation과 SDK validation을 유지하며 내부 schema refresh를 현재 principal 전체 snapshot으로 분리하는 patch1.30.8로 해결한다.
- Corrected SDK regression3조건(수정 전 cold/beyond-page2실패)이 모두 통과한다. Mutation probe는 real schema에 valid함을 먼저 검증하고 cached manage schema 뒤 read grant가 ledger에 도달하지 못함을 확인한다. 실제 Uvicorn TCP/installed SDK/real registry에서 capabilities typed 결과·isError=false, public page1/1·distinct cursor와 read mutation 거부를 관찰했다. Identity/Redis/audit만 합성이며 provider acceptance가 아니다. Receipt `/private/tmp/afterglow-mcp-release-ctnj_jie/mcp-cold-cache-tcp-receipt.json`.
- macOS traced installer regression의 큰 stdin pipe write와 PTY output backpressure 교착은 concurrent select feed/drain으로 수정했다. 기존11종 auth/outage/unsafe-metadata/TLS 실패 분기·secret/기존 설치 보존·echo 복구 assertions가 통과한다. Deadline·trace·운영 installer는 변경하지 않는다.
- Patch1.30.8의 최종 `npm run test:gate`가 source digest `10953dda98bfcf1d34513771f9437cf7362549e9676ed11f2b76dd35a724f1e8`에서 통과했다: backend4,191, frontend332files/2,510+runner9, contract154, 실제 DB functional35, Ruff555files. JS orchestration106·Kolla26·installer19 통과이며 이 실행의 installer native-client 조건36개는 skipped다. Existing deprecation warnings는 유지한다. 최종 output `artifact://1232`와 actual TCP receipt는 live OAuth/provider proof와 구분한다.

## Final corrective publication, canonical rollout and actual consumer closeout (2026-10-10)

- Immutable1.30.8 revision `dce31cadd22c849f8d62a3077ded79ab9cab20b9`: dev Docker/required CI37940149729, tag Docker37940880947 and Helm37940880350 all success. Its declared-platform/non-root/version execution receipt is `oauth-1308-image-execution.json`. Canonical native multinode four-stage rc0 receipt is `wireguard-dmslab:/home/pieroot/.cache/mcp-oauth-1308/kolla-afterglow-1308-multinode.json` (completed2026-10-09T14:12:45Z).
- Real provider consumer exposed a separate scoped session adapter defect after the cold-cache repair. Immutable1.30.9 revision `f48d6fe2e031ddbc60e19f9507cdd6f01fdd001f` corrects that caller connection without widening read permissions. Exact dev CI37961101739, tag Docker37961822854 and Helm37961822437 all success; four indexes/latest-equality and all declared-platform version/non-root execution are in `oauth-1309-image-execution.json`. API/frontend/worker declare amd64; Cloud Shell declares amd64+arm64. No tag moved or main merge occurred.
- Canonical1.30.9 native `/etc/kolla/multinode` genconfig/pull/prechecks/reconfigure all rc0 on exactly dms-controller1/2/3, inventory SHA `11854c8b5b7d0605a7aa8541c379a66da18ce449c4b821365bf7300a9069a1f0`, completed2026-10-09T17:07:43Z. Private receipt `wireguard-dmslab:/home/pieroot/.cache/mcp-oauth-1309/kolla-afterglow-1309-multinode.json`. Operator credentials/config/locks/sibling images and real resources are preserved; no fallback/alias inventory used.
- Real production browser OAuth consent→loopback PKCE exchange200, followed by installed MCP SDK1.28.1 over public HTTPS `https://cloud.dmslab.re.kr/mcp` with no redirects. Both personal read key and OAuth perform **cold calls before tools/list**, return typed capabilities/overview with `isError=false`, discover28tools/page1, and complete schema-validated Nova server and Cinder volume list (limit1 each). Real cloud overview:21 total/21 active/0 shutoff/0 error. Capabilities/overview have no declared output schema, so their typed-object evidence is not called schema validation. No resource/provider mutation. Private credential-free receipts: `mcp-1309-public-personal-final.json`, `mcp-1309-public-oauth-final.json`.
- Real refresh boundary: wrong client400/invalid_grant with original bearer still200; correct rotation200 with different refresh/new bearer200; consumed refresh replay400/invalid_grant then both old/new bearer401. Owner metadata confirms the exact new OAuth grant revoked. Existing personal baseline5keys retain IDs/revocation state; the independently registered one-hour read-only OMP verification key is preserved pending its agent-mount acceptance. Receipts `mcp-1309-refresh-family-final.json`, `mcp-1309-owner-preservation-final.json`, mode0600; no secret values recorded.
- Native OMP current-session mount remains a **separate blocked task**: project registration/private credential storage exists, live-discovery configuration approval timed out unchanged, and user `/mcp reload` is required. Never count public SDK invocation as OMP-mounted invocation or retry unanswered settings approval. Browser UI/locale/responsive evidence remains the documented actual/synthetic distinction above; no blanket client-product, paid-provider or subsequent1.30.10/0.6.7 rollout claim.

