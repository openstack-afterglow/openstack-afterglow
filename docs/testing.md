---
title: 국소 기능테스트 가이드
lang: ko
nav_order: 8
---

# 국소 기능테스트 가이드

## 완료 세션 dev 통합 검증 (2026-10-11, local-only)

`integrate-completed-sessions-dev-ci`는 완료 세션들의 source·tests·docs·공개 screenshot을 private 입력 없이 `/private/tmp/afterglow-dev-integration-20261011.bkJlix/repo`의 local `dev`에 통합했다. Local checkpoint `7f2572197747bb80e09255879836b415b0d96edd`와 upstream `97209ed4a412feacb03fb7b0d64508721817d51a`의 ancestry를 모두 보존한다. 아래 과거 작업별 실패/성공 기록은 당시 범위로 유지하며 현재 통합 성공으로 소급 변경하지 않는다.

1. **최종 전체 gate**: PTY EOF 수정 뒤 원래 `npm run test:gate`가 exit0이었다. Orchestration175, Kolla Node27/Python11, Unix installer20, backend unit5,003, frontend342files/2,914 및 runner9, consumer contract174, 실제 MariaDB/PostgreSQL/Redis functional118/23deselected, Ruff check·format574files가 통과했다. PowerShell36개는 `pwsh` 부재로 skip이며 Windows 실행 proof가 아니다. 별도 소유 `afterglow-dev-integration-gate-bkjlix`의 세 datastore와 기존 runner override만 사용했고 suite/check를 축소하지 않았다. 최종 full gate output은 session `artifact://468`에 보존하며 앞선 `artifact://365`와 중간 실패 `artifact://447`을 덮어쓰지 않는다. 최종 source fingerprint는 `936a2135eb61d0b4f93f7dbb1b03ba4e482d29e5d1258ceb6206f009b2592b34`/2,601files다.
2. **검토와 수정**: MCP target catalogue가 선택 PAT의 실제 project target을 유지하고 Lumen read/preview/mutation이 공용 Redis budget·concurrency admission을 사용하도록 바로잡았다. SDK work는 timeout 후에도 drain 전 slot을 반환하지 않는다. Catalogue 승인/OAuth/비활성화 요청은 actor/project와 abort signal에 묶여 identity 전환·unmount 뒤401 recovery replay/redirect를 막는다. 네 locale의 기본 위임 설명은 실제 access chip과 모순되지 않게 수정했다. 문구/API mock signature만 고정하던 obsolete assertion은 삭제하고 소비자 행동 회귀는 유지했다. 최종 세 독립 source review는 remaining defect를 보고하지 않았으며 이는 runtime/운영 acceptance의 대체물이 아니다.
   Unix installer 재검증에서는 `artifact://447`의 `python3 ETIMEDOUT`이 발생했다. 세션 종료 후 macOS PTY의 EOF가 계속 readable인 마지막 drain을 실제 재현했고, EOF 종료와 종료한 keeper의 release 생략을 `scripts/lumen-sh.test.js`에 적용했다. 유지한 terminal-revocation/invalid-arity 회귀는 이전 drain에서20초 ETIMEDOUT으로 실패하고 수정 뒤 status1·입력0·echo 복원·파일 보존을 확인했다. 같은 실제 PTY/installer 경계를 Linux ARM64 image에서도 확인했다. 제품 installer/API/frontend/native source와 timeout·suite는 그대로이며 앞선 image·HTTP·화면 smoke의 application bytes는 변하지 않았다. GBrain sync는 CLI가 없어 실행하지 않았고 검색 guidance도 변경하지 않았다.
3. **현재 통합 API smoke**: 실제 Uvicorn·MariaDB·Redis와 source registry/run_sdk를 실행하여78checks/실제 TCP22요청을 통과했다. Project-B PAT catalogue 유지, 반복 조회 mint0, caller·grant rate429, coordination transport503, deny-before-provider/ledger 및 worker hold→timeout→drain 후 slot 회수를 관측했다. Identity·VM read/preview provider는 named synthetic seams이며 실제 provisioning·성공 mutation·분산 replica/운영 인증 proof가 아니다. `runtime/20261011T155731_5f24eea128ac4f849f94d702dce0fbbe.receipt.json`은 실제 경계·assertion·자기 namespace cleanup과 보존 SQL schema를 기록한다.
4. **빌드·실제 화면**: canonical Dockerfile backend/frontend/worker 세 target의 ARM64와 AMD64 빌드6개가 성공했다(`runtime/final-*-build-{arm64,amd64}.json`). 두 backend image의 실제 app lifespan·TCP health200/protected401, UID1000·Python3.12.15·SDK3.3.0·OpenTofu1.8.3의 정확한 linux_arm64/linux_amd64 실행을 확인했다. 이는 network-none/no-DB·unreachable synthetic Keystone의 packaged startup proof이며 DB/Redis readiness·운영 인증이 아니다. 두 worker의 실제 crypto encrypt/decrypt image smoke도 통과했지만 Notion sync는 실행하지 않았다. Compiled Node frontend는 canonical dev Compose의 별도 소유 project에서 두 architecture를 각각 기동하고 실제 Chromium에서 조회/열기/취소 mutation0, manage 승인 POST, 비활성화 DELETE, exact config_version4의 remote activation PATCH, 가로 overflow0·JS error0을 확인했다. AMD64는 실제 x64 Node20.20.2/UID1001이며 Docker Desktop emulation이다. API/권한/identity는 합성이며 실제 MCP OAuth/remote provider 변경은 없다. `runtime/final-consent-{arm64,amd64}.{json,png}`는 이 최종 화면 proof다. Svelte check2,354files/0errors/기존 tabindex warning2, i18n37namespaces/9,596messages·scan989files/0문제도 확인했다. 전체 responsive coverage는 아래 원래 개별 세션 receipt와 구분한다.
5. **중단된 native 검증 완료**: 현재 sibling source의 consent/key runtime11개와 manifest/SQL이 원래 canonical native receipt와 byte-identical임을 확인했다. 별도 소유 MariaDB schema에 실제 Lumen manifest001–026을 적용하고 `tests/integration/test_mcp_owner_activation.py`, `test_native_api_key_flow.py`가 exit0이었다. 첫 scratch guard가 테스트가 소유한 loopback HTTP listener까지 차단한 오류는 제품/network guard를 약화하지 않고 scratch allow-loopback 경계를 바로잡았다. 최종 `runtime/lumen_dev_integration_20261011170327_c864b3ba2e.receipt.json`은 source hash·selector·실제 적용 목록을 보존한다. Identity/provider·autouse Redis는 합성이며 sibling source commit/publish/deploy는 하지 않았다.
6. **사용자 보고 Compose 실패와 복구**: 첨부 실행은128/128 image build 성공 뒤 네 migration/bootstrap에서 DB connect timeout으로 exit1이었다. 기존 container/log를 재실행 전에 보존했다. 당시 container target은 controller `.11`(Lumen의 short IPv4 `172.30.11` 포함)이었고, 조사 시 현재 shell-rendered target은 VIP `.253`이었다; 같은 입력이라고 취급하지 않는다. `afterglow-lumen-settings-qa_default`의 `172.30.0.0/16` bridge가 외부 DB 대역과 겹쳤다. 사용자 승인 아래 이 bridge만 `192.168.240.0/24`로 옮기고 기존 세 datastore의 ID·PID·StartedAt·port·mount·aliases를 보존했다. 실제 dev container에서 `.11`/`.253`:3306 연결과 다섯 선택 DB의 인증된 SELECT-only를 확인했다. `runtime/reported-compose-failure-sanitized.json`, `qa-network-relocation.json`, `qa-network-restored-tcp.json`, `private-db-select-only.json`에 비밀 없는 evidence를 보존한다. 기존 failed migration/bootstrap을 운영 DB에 재실행하거나 운영 schema/IAM을 변경하지 않았다.
7. **운영 cutover 준비·차단 경계**: 승인된 read-only cutover preflight에서 세 controller의 Afterglow `9cbfecad`/1.30.12, Lumen `bc2fefd8`/0.6.7, Drover `84cea3cc`/0.4.8, Waygate `fd2d1b36`/0.3.3와 controller1의 Palimpsest `1f120392`/0.3.2 image pins·revision을 기록했다(`runtime/production-service-revisions-readonly.json`). MariaDB10.11.19의 Afterglow grant expiry는 NOT NULL·consented_at 부재이며 Lumen ledger는001–025다; 새 writer 전에 Afterglow085/086 및 native026 평가가 필요하다. 확인된 ecosystem snapshot은 `/var/backups/afterglow-ecosystem/latest-main-20261005T012922Z`이며 현재 deployment/ledger보다 오래되어 현재 snapshot으로 승격하지 않는다. 일관된 현재 snapshot·원래 key/rotation·Redis/PostgreSQL/checkpointer/CAS state, 실제 복원과 양방향 old/new writer·mixed-version API/worker/queue·rollback proof는 미제공/미검증이다. 운영 writer 중지·새 backup·migration/write·배포는 이번 commit/CI 권한에 포함하지 않는다.

이 통합은 기존1.30.12를 유지한다. 공유 checkout/index·private env/config/key와 다른 프로젝트의 기존 container/volume은 보존하며, host-only QA network 이동은 Git의 source 변경이 아니다. Commit/push/정확한 SHA Actions 상태는 OpenSpec 완료 기록에서 별도로 기록한다.

## 계정·전체 리소스·공통 콘텐츠 폭 검증 (2026-10-11, local-only)

`streamline-account-resource-surfaces`는 계정 MCP 선택·만료·복사·활동 paging,25종 inventory, 일반 VM의 unsupported library/HA cutover와 모든 page의 공통80rem shell을 포함한다. 현재 공유 source를 private config·DB data·다른 worktree·dependency cache 없이 격리한 snapshot에서 검증했으며 실제 공유 index/review marker와 운영 설정은 보존했다. 증거는 `/Users/pieroot/.local/share/afterglow-proofs/account-resources-20261011/`의 JSON·화면·로그다.

1. **실제 화면**: source Chromium에서8개 만료 preset 각각 발급→실제 전체 JSON clipboard 복사→닫은 뒤 secret 제거, OAuth/API method 전환,10/15/20개 활동의 서로 다른 다음 페이지·이전 복원·filter 초기화를 확인했다. 계정·리소스 각각390/767/768/1023/1024/1280/1440/1920px에서 overflow0이었다. 리소스25개 category,5→8개 펼치기/접기, named 표의 실제 키보드 가로 스크롤을 확인했다. Theme transition 중간 frame은 최종 시각 증거로 쓰지 않고 animation 완료 후 캡처했다.
2. **Compiled production preview**: 실제 `npm run build` 산출물에서 계정/리소스×4locale×light/dark×390/1440px32조건과 사용자/관리자27route×390/1024/1920px81조건을 확인했다. 외부 shell은1280px 상한·parent 기준center 오차0·mobile16px/desktop24px padding이며 document overflow0이다. 실제25종 native 응답 fixture를 별도 HTTP로 반환해 다른 project item 링크 차단, DB 실패/Drover 거부/Waygate 비활성의 `partial`·unknown,503 뒤 이전 snapshot 제거와 정상 재조회 복구도 확인했다. Identity/API는 합성이다. 첫 별도 fixture는 Chromium의 금지 port1 때문에 인증 복구 gate가 열렸으며, 안전한 same-origin15453으로 검증 환경만 수정했다.
3. **MCP 실제 HTTP/SQL**: Uvicorn→설치된 OpenStack/Keystone SDK→loopback Keystone24요청 및 실제 MariaDB에서 무기한/6개월/1년의 생성201·목록의 동일 UTC microsecond·conflict422·폐기204·폐기 후 인증 거부를 확인했다. 무기한은 upstream 만료 field를 생략하고SQL NULL이며 미래 시각 조회에서도 만료되지 않았다. SQL focused103개 통과. 처음 관측한 ORM 초 이하 정밀도 손실과 naive 목록 시각은 DATETIME(6) variant·UTC projection으로 수정했다. Migration CHECK 오류4025는 이 MariaDB driver에서 OperationalError임을 반영했다. Keystone/브라우저 identity는 합성이고 실제 IAM 쓰기는0이다.
4. **Inventory native 및 Drover**: 설치된 SDK/native adapter와 두 실제 Uvicorn 사이1449개 provider HTTP에서 모든25종·두 scoped project·pagination·keypair dedup·metadata 제한·package capability revocation/context 장애/namespace 교체·cycle/403/실패의 null count를 확인했다. 응답/Keystone/role graph/fakeredis는 합성이며 provider mutation0이다. 형제 Drover는 실제 격리 MariaDB11.4/Redis7과16HTTP로 SQL stop→실제15초 breaker→재시도503→SQL restart/cooldown→정확한 목록200을 확인했고 SQL outage 중 Redis fallback0이다. Native pytest93개·changed Ruff 통과. Legacy DB 미설정은 startup 이후 전환한 제한적 proof이고 기존 Redis SET/cache key 충돌을 피하는 `no_cache=true`만 확인했다; 전체 native migration/readiness·운영 IAM은 미검증이다.
5. **VM cutover**: 일반 image/flavor/settings/review4단계를 실제 source Chromium에서 이동하고 mobile review까지 확인한 뒤 취소했다. UI에 library/squashfs/HA 단계가 없으며 실제 VM은 만들지 않았다. 실제 BFF TCP에서 제거된 public list/consume404와 보존된 library/ordinary-create/admin-consume의 auth401을 확인했다.401은 인증 경계가 살아 있다는 증거이지 provisioning 성공이 아니다. 최종 관련 backend87개가 통과했다. 내부 router/column 존재만 확인하던 incidental test는 제거하고 실제HTTP404 회귀로 바꿨다.
6. **전체 gate와 후속 검사**: `npm run test:gate`는 architecture·orchestration175·Kolla Node27/Python11·shell installer19(기존 PowerShell36skip) 뒤 backend4993passed/1failed로 중단됐다. 실패는 동시 Lumen 변경의 `test_mutation_invalidate_coverage.py::test_mutation_handlers_have_invalidation`이 `proxy.py:approve_cloud_tools`, `disable_cloud_tools`를 지목한 것으로 보존했으며 이 작업에서 예외·검사를 우회하지 않았다. 별도 원래 suite 명령으로 frontend341files/2909+runner9, contracts156, 실제 MariaDB/PostgreSQL/Redis functional118(23deselected), Ruff check/format573files가 통과했다. 최종 HTTP 회귀 교체는 gate 이후 exact87개로 검증했으며 전체 gate 재통과로 표현하지 않는다. Svelte check2353files/0errors/2warnings(DocCodeBlock, keyboard-scroll ProjectUsageTable tabindex), i18n check/scan0문제, production build 통과다.
7. **배포·호환성 경계**: Migration085를 적용하기 전 무기한 writer를 활성화하지 않는다. 실제 production revision/schema·복원 snapshot·원래 암호화 키·양방향 writer/schema·mixed-version API/worker·rolling upgrade와 rollback은 검증하지 않았다. 신규SQL의 성공을 운영 호환성으로 승격하지 않으며 nullable lifetime을 읽는 모든 API/worker의 호환 cutover를 별도로 검증해야 한다. Companion Drover도 별도 release/deploy가 필요하다. 실제 cloud/provider provisioning·운영 DB/IAM 변경·publish/deploy·commit/push는 수행하지 않았다. Optional gbrain은 CLI 부재로 sync하지 않았다.
8. **Architecture**: 최종 docs와 HTTP 회귀 교체를 반영한 frozen snapshot의 working stamp/check·staged check가 `d3768d2de0ad659d9c97a0afa77df6cdc1353339978c6ac9faa3e2b407bda4ed`/2601source files로 통과했다. `architecture-receipt.json`은 command·scope·exit를 보존한다. 첫 gate source digest는 `d6edfbdb8b47828f08d28b29250d16bbb407f3c7406013ba7e8877b64b2d9249`이며 이후 DESIGN 설명/HTTP regression만 달라졌다. Docs/ARCHITECTURE/OpenSpec은 digest의 source 제외 경계다. 이 snapshot은 공유 source 정지 시점의 동시 변경도 포함하므로 기능 단독 또는 현재 전체 공유 tree의 gate 성공을 주장하지 않는다.

## Lumen MCP 명시적 승인·ordinary API 키 검증 (2026-10-11, local-only)

현재 feature 계약은 [Chat API](api/chat.md#mcp-카탈로그와-명시적-승인), [보안 경계](security.md#lumen-mcp-opt-in과-ordinary-api-키), native `docs/api-reference.md`·`docs/operations.md`를 따른다. 아래는 `/Users/pieroot/.local/share/afterglow-proofs/lumen-settings-consent-20261011/`의 실제 canonical receipt만 집계하며 이전 실패나 과거 lazy-mint smoke를 현재 acceptance로 세지 않는다.

1. **Cloud canonical**: `cloud/qualification-summary.json`의 최종 arm64·amd64 두 실행은 각각 exit0, 21checks·40source TCP HTTP·37installed-SDK fake Keystone HTTP, 합계 **2runs/42checks/80HTTP/74SDK HTTP**다. 실제 이미지 `/app` handler·MariaDB·Redis DB10·openstacksdk3.3.0/keystoneauth5.13.1 transport를 실행했다. GET 반복은 mint0, legacy `source=lumen, consented_at=NULL`은 선택·frozen preview/execute403, 명시 read는19tools/manage는29tools였다. Manage는 synthetic caller의 admin 주장 대신 SDK token의 실제 reader/member 역할로 제한했다. Idempotent approval mint0, DELETE 뒤 frozen 호출 provider HTTP 증가0, 준비 중/credential 생성 중 DELETE가 이긴 두 경합은409와 원격 synthetic credential cleanup을 관측했다. 명시 PAT 선택은 반복 GET에도 보존했다.
2. **Native canonical**: `native/canonical_summary.json`의 API/worker 이미지×arm64/amd64 네 실행은 각각 UID1000·exit0, 67assertions·57TCP HTTP·manifest001–026 실제 checksum migration26개를 적용했다. 합계 **4runs/268assertions/228HTTP/104migration applications**이며 서로 다른 소유 schema4개다. Global 기본 off, exact owner/project/config 승인·stale revision400/no commit, disable/re-enable generation의 frozen fence, separate OAuth connected-token/encrypted SQL 경계와 직접 사용자 MCP CRUD를 실행했다. Fresh issuance-policy/current scope·keys-editor·quota 아래 이름/scopes/monthly25/aware UTC expiry를 한 POST/SQL commit으로 원자 저장했고 nullable expiry의 기존 인증을 유지했다. Naive/past422·quota409·over-scope403은 새 행/commit0이다.
3. **Expiry·queued-hook의 양성 대조군**: 실제 시계 만료 뒤 HTTP401/verifierNone과 함께 독립 SQL expiry read 및 아직 유효한 키의 HTTP200을 확인했다. Expiry 행을 조작하지 않았다. 키가 유효할 때 SQL로 queued run을 seed하고 만료 뒤 packaged `_DurableExecutionHooks._start`를 직접 실행하여 `inference_authority_revoked`, rollback 및 새 execution segment/provider-start intent commit0을 관측했다. 이는 HTTP admission·실제 worker claim/graph/checkpointer 실행 proof가 아니다.
4. **실패 이력 보존**: Native `summary.json`/`native_smoke_20261011103756_379be88fbe.json`의 SQL2013→connection refused와 당시 expiry assertion은 DB 장애에 confounded되어 expiry proof에서 제외했다. Parent가 원래 소유 MariaDB의 OOMKilled=true/exit137을 관측하고 기존 소유 project만 복구한 뒤 위 양성 대조군 실행이 통과했다. Cloud의 synthetic secret_key 누락, 미설치 asyncmy, 원래 SQL FOR UPDATE 대기 중30초 HTTP timeout(제품/lock 원인 미확정), OOM 뒤 connection refused와 pinned Redis5.0.0에 없는 scratch `aclose` 때문에 assertions21개 통과 후 exit1인 첫 arm64 실행도 receipt에 남긴다. Scratch close 수정 후 두 canonical 실행만 exit0으로 집계한다.
5. **합성·provenance 한계**: Cloud `get_token_info`는 synthetic owner/system-admin이며 일반 IAM role-graph 인증 proof가 아니다. Keystone는 private loopback fake HTTP다. Native directory 권위·MCP discovery·OAuth token origin·queued orchestration은 합성이나 실제 auth/store/encryption/frozen-hook은 실행했다. Cloud schema는 SQL smoke 준비이며 migration runner proof가 아니다. Native는 실제 runner001–026이다. Native11개 runtime source hash는 네 image와 당시 host receipt가 일치한다. `cloud/source-packaging-parity.json`은 두 architecture의 packaged6files가 원래 성공 smoke와 byte-identical이고 당시 formatted host6files가 AST-identical임을 확인한다. 이후 공유 expiry model의 DATETIME(6)·UTC 직렬화 변경을 보존했으므로 최신 source 전체가 기존 image와 AST/byte-identical하다고 주장하지 않는다. 해당 통합 source는 `current-source-cloud/20261011T113526_8b85f0e6.receipt.json`의 host Darwin arm64 실제 HTTP/SQL/Redis 실행으로 별도21checks·40sourceHTTP·37SDK fakeIAM HTTP가 통과했고 authority SHA622b5b…는 최종 architecture 입력과 일치한다. 이 실행은 canonical image 재빌드나 두 architecture 최신 byte parity proof가 아니다. Import 중 기존 private TOML의 GPU-map parser 오류가 기록됐으며 private 파일은 수정하지 않았다.
6. **실제 process readiness**: `processes/process_qualification_20261011200112_269657e7.json`은 두 architecture에서 수정하지 않은 native `lumen.main:app` lifespan과 `python -m lumen.worker`를 실행했다. Manifest001–026 적용 뒤 `/v1/health`·`/v1/ready`200(database/plugins/checkpointer=true), private PostgreSQL checkpointer 초기화와 advancing worker heartbeat/accepting=1/active=0, 무인증·타인 synthetic credential401을 관측했다. Afterglow도 실제 `app.main:app` startup·MCP transport와 health200/protected401을 확인했다. Afterglow schema37개는 실제 `init_db/create_tables` 경로이며 SQL manifest runner proof가 아니다. Mandatory snapshot startup의 loopback IAM refusal은 그대로 남겼다. amd64는 Docker Desktop emulation이며 빈 work/provider/usage 상태의 readiness이지 유료 추론 성공이 아니다.
7. **실제 compiled Chromium**: `ui/compiled-browser-qualification.json`은 canonical frontend 두 architecture의 실제 Node/UID1001 실행과 browser10시나리오를 기록한다. GET/open/cancel의 mutation0, read/manage 승인 POST·비활성화 DELETE, remote exact-config activation PATCH와 직접 등록 보존, revoked 기본 숨김·expired 미폐기 표시·전체 전환, target-project policy/ceiling을 사용하는 이름/scopes/expiry/monthly-limit의 단일 POST와 취소/Escape draft 초기화를 확인했다. Key/consent modal 각각 두 architecture×두 theme×390/768/1440px의12조건, 추가 KO/EN/JA/zh-CN×390/1440px8조건, 총32조건에서 viewport 안의 dialog와 가로 overflow0을 측정하고 screenshot을 보존했다. Identity/permission/policy/API는 named synthetic fixture다. 초기 site-config CORS 불일치와 selector/date helper 오류는 보존했으며 제품 patch나 인증 우회로 해결하지 않았다.
8. **미검증 경계**: Live IAM·OAuth code exchange·remote MCP tool success·paid inference·production snapshot/원래 키·양방향 writer/schema/mixed-version rollout·publish/deploy는 미검증이다. Shared Docker bridge는 egress-filtered network가 아니며 packet capture로 전체 outbound0을 증명하지 않았다. Afterglow086/native026은 consent backfill이 없고 ordinary expiry는 native013을 재사용한다. 이전 개인 MCP token lifetime의 문자열 직렬화 실패는 ordinary native key expiry 성공과 다른 계약이다.
9. **회귀·전체 gate 결과**: `tests/gate-summary.json`에 원래 suite와 실패 로그를 보존한다. 최종 consent3files의 endpoint/owner/generation/race/migration 회귀82개와 feature Python8files Ruff check/format이 통과했다. 초기 shared pytest는 private TOML parser로 collection 전 실패했고, sanitized snapshot의 새 owned schema는 restricted test user의1044로 실패했다. Config/code/권한을 바꾸지 않고 private 파일을 제외한 snapshot과 승인된 disposable root URL을 사용한 최종82개만 성공으로 집계한다. Native 전체 integration288(3133deselected), Afterglow consumer contracts156, frontend341files/2909+runner9, i18n37namespaces/9596messages·scan989files의0문제가 통과했다. Frontend 첫 optimizer의 node:module/missing tsconfig는 기존 `svelte-kit sync` 준비 뒤 해소됐다. **전체 `npm run test:gate` 통과는 아니다**: installer PTY의 `spawnSync python3 ETIMEDOUT`에서 중단됐고, 별도 frozen whole lint는 user_inventory·test_instance_boot_from_volume·test_mcp_credentials import3건, Svelte check는 별도 admin quota의 `creditRateSecondary` Props1error/기존 tabindex2warnings였다. 무관한 source는 수정하지 않았다. 앞선 backend unit의 source-AST invalidation checker는 DB/no-store consent handler에 OpenStack cache 호출을 요구하던 구현 결합 검사여서 제거했으며 실제 행동 회귀를 유지한다. Functional/전체 backend의 최종 full-gate green을 주장하지 않으며 commit/push하지 않았다. Optional gbrain은 CLI 부재로 sync하지 않았다.
10. **Exact-index architecture scope**: `architecture/final-qualification.json`의 fresh private working stamp/check·별도 `GIT_INDEX_FILE` staged check가 네 scope에서 통과했다. Afterglow baseline `7f2572197747bb80e09255879836b415b0d96edd`+owned28paths(구현 결합 test 삭제 포함)는 `b67205c8d628e0382509ee3d2067d52373f42e8ffef477bf6b7b840a8abf898a`/2549files이며 separately enumerated prerequisite-current29paths를 더한 scope는 `e2af3b5c83d8792eefc857cbd0be5b7de7975e39d0d07c377ffacae401c90606`/2550files다. 동시 expiry model/serialization 변경을 덮어쓰지 않고 exact input에 포함했다. Full input manifests·command/stdout·shared index/root marker 보존을 기록하며 초기 guard receipt도 유지한다. Owned-only는 비소유 의존성을 제외하므로 standalone runnable qualification이 아니고 static closure도 dynamic/config 완전성이나 전체 gate를 증명하지 않는다. `full-current-source-snapshot.json`은 동시 작업을 포함하는 별도 gate scope이며 마지막 model/authority2path overlay는 `tests/final-cloud-regressions.json`에 명시한다. 이 digest로 전체 공유 WIP나 운영 호환성을 승인하지 않는다.


## 프로젝트 멤버 권한 영역별 편집 검증 (2026-10-11, local-only)

`project-member-role-area-navigation`은 기존 modal·역할/계정 회귀2개와 account locale 신규 메시지3개×네 언어만 변경한다. 같은 저장 endpoint·직접 역할/서버 DAG·외부 상속·owner/admin·group/inherited-only·busy 정책을 보존하며 API/schema/설정/의존성/운영 IAM 변경은 없다.

1. **행동 회귀**: 정확한 역할 modal11개·계정13개와 design target27files/139개가 통과했다. 영역 이동·전체 검색 fallback/해제 복원과 hidden direct/legacy ID 보존, parent 제거 뒤 shared/external 상속 및 명시적 direct child, nonowner·indirect membership·busy 보호를 검증한다. 첫 실행의 label query가 nav와 mobile select를 함께 찾아6개 실패하여 실제 combobox 역할로 selector를 한정했고 같은 behavioral suite가 통과했다. 문구만 고정하던 assertion은 제거했다.
2. **실제 current-source Chromium**: concurrent HMR에 의한 dialog 초기화를 피하려고 private 설정을 제외한 frozen frontend를 실제 Vite로 실행했다. 네 locale×두 theme×390/767/768/1023/1024/1440px와844×390 landscape, 총56조건에서 선택 영역 역할만 표시, breakpoint별 select/two-pane, document/card/body 수평 넘침0과 viewport 안의 고정 header/footer·본문 스크롤을 확인했다. 긴 사용자/role/불투명 area 값은390/768/1440px3조건에서 넘침0·title tooltip·area field 기준 분류가 통과했다.
3. **실제 소비자 lifecycle**: desktop의 전체 검색·빈 결과·해제 복원·상속 재계산·숨은 direct/legacy ID를 포함한 정확한 PUT payload, synthetic409 뒤 draft 유지와 취소,22회 키보드 Tab의 visible dialog focus 및 닫힌 뒤 opener focus를 확인했다. Busy의 검색/영역/checkbox/취소/저장 비활성화와 Escape/backdrop 차단, mobile 선택 보존·PUT200 뒤 창 종료·취소 draft 폐기, 펼친 effective snapshot128px 제한을 검증했다. Shared parent·direct child·겹친 external leaf, nonowner owner/admin 보호와 목록 로딩이 끝난 group/inherited 멤버의 edit 버튼 부재도 확인했다.
4. **범위·환경**: Browser identity/프로젝트·역할 응답/PUT는 모두 합성이며 실제 IAM 변경이나 Keystone 인가 proof가 아니다. 초기 QA의 성공 응답 handler가 후속 목록 refresh GET까지404로 응답한 환경 오류는 별도 기록했으며 제품 성공으로 승격하지 않는다. External Google Fonts를 차단한 requestfailed는 JS runtime exception과 구분한다. Evidence와56개 screenshot/JSON은 `/Users/pieroot/.local/share/afterglow-proofs/project-role-area-20261011-d5d71a9c/`에 보존한다. 공유 check는 별도 Chat API key·quota/my-resources WIP의83errors/2warnings로 실패하여 해당 source를 변경하지 않았다. 격리 baseline+역할 전용 account 키에서는 check0errors/기존 DocCodeBlock warning1, i18n check/scan0문제였다. Whole account catalog 복사는 다른 beta cutover를 섞어6개 type error를 내므로 baseline의 무관한 beta 키를 유지한 역할 키3개 overlay로 범위를 바로잡았다.
5. **Architecture**: frozen dev `7f2572197747bb80e09255879836b415b0d96edd`와 위7개 source file의 역할 전용 overlay에서 working stamp/check와 별도 임시 index의 `--staged`가 같은 digest `89ce2937adcd8705a78432b7b2e05cb355f264c05ee8038dd2f1c8c4d2704730`/2546files로 통과했다. 공유 index/review marker·동시 source를 변경하거나 이 digest로 전체 WIP를 승인하지 않는다. Scope root의 실제 index도 보존했다. Optional gbrain은 CLI 부재로 실행하지 않았으며 agent guidance를 바꾸지 않았다.
6. **Canonical compiled 산출물**: 위 역할 전용 scope에서 기존 Dockerfile의 `frontend` target을 실제 linux/arm64·linux/amd64로 빌드하고, 기존 `docker-compose.dev.yml`에 QA image/platform/loopback port만 override하여 별도 project로 실행했다. 두 컨테이너의 healthy와 Node `linux/arm64`·`linux/x64` 실행을 확인했다. 실제 compiled Chromium에서 각 architecture의 동일56조건, 총112조건이 통과했다. 추가 desktop/mobile 소비자 흐름에서 검색 fallback/복원·숨은 direct/legacy ID 보존·busy 비활성화·키보드 focus를 확인했고, 정확한 direct-only PUT200 → 목록 GET refresh → 편집 재진입의 저장된 direct child/제거한 parent 상태까지 검증했다. 후속 GET을 올바르게 응답하도록 초기 QA handler 오류를 바로잡았으며 실제 IAM은 사용하지 않았다. QA auth는 현 source의 `sessionStorage` 계약을 따른다. Legacy `localStorage` credential이 삭제되어 login으로 돌아간 초기 fixture 오류를 auth 우회로 해결하지 않았다. Header/footer 좌표는 기존200ms entrance animation이 끝난 뒤 측정하며, 중간 scale transform을 본문 스크롤 이동으로 오판한 첫 assertion도 별도 기록했다. Compiled112개 screenshot, `compiled-runtime.json`·`compiled-responsive-matrix.json`·`compiled-save-lifecycle.json`을 위 proof directory에 보존했다. Block한 external font 외 compiled JS exception/request failure는 없었다.
7. **전체 gate**: 같은 scope/digest에서 suite 선택을 바꾸지 않은 `npm run test:gate`가 통과했다. Backend4595·frontend335files/2710·contracts154·functional73(기존 marker로22deselected), orchestration175·Kolla contracts27·shell installer19·frontend runner9와 Ruff check/format573files가 통과했다. PowerShell runtime 부재로 기존36개는 skip되었으며 실행한 것으로 간주하지 않는다. 첫 gate는 QA override의 `mysql+pymysql`이 async engine에 부적합하고 published Redis socket이 timeout하여 실패했다. Source/test를 좁히거나 변경하지 않고 runner의 기존 `mysql+aiomysql` driver와 별도 canonical test-profile project의 실제 random loopback port를 사용한 최종 gate는 real MySQL/Postgres/Redis functional 경계까지 통과했다. 초기 Redis timeout의 원인을 확정하지 않는다. Shared WIP가 아니라 baseline+7path overlay의 통과 증거이며 release/publish/production deploy 또는 운영 schema 호환성 증거는 아니다. 원래 DB·설정·키·컨테이너·볼륨·index는 보존한다.


## 비밀번호 미지원 안내의 사용자·관리자 분리 (2026-10-11, local-only)

`simplify-consumer-password-support-notice`는 `instanceDetailController.svelte.ts`·`InstanceHeader.svelte`·`PasswordModal.svelte`·`instanceDetailController.password.test.ts`·instance locale4개, 총 source8개를 변경한다. 일반 사용자 상세의 `supported=false`만 “지원되지 않는 인스턴스입니다.”로 표현하며 관리자 상세의 원본 사유, 권한·지원 판정·loading/error·비밀번호 요청은 유지한다. 새 backend/API/schema·설정·의존성·배포 구조는 없다.

1. **행동 회귀**: 관련 frontend246개가 통과했다. 전역 시스템 관리자라도 일반 사용자 상세에서는 일반 안내를 사용하고, 관리자 상세에서는 같은 프로젝트를 보더라도 상세 사유를 유지한다. 사유 누락·지원 상태 전환·사전점검 중/실패·열린 비밀번호 창의 표시와 비활성화를 구분한다.
2. **실제 compiled 화면**: canonical Dockerfile/frontend와 dev Compose로 linux/arm64·linux/amd64 이미지를 각각 빌드·실행하여 Chromium10개 시나리오를 확인했다. 사용자 안내·disabled tooltip·열린 dialog에는 일반 문구만 보이고 관리자 안내·tooltip에는 원본 QGA 사유가 보였다. 지원됨으로 갱신하면 버튼이 활성화되고, pending/error를 미지원으로 잘못 표시하지 않는다. Korean/English/Japanese/Simplified Chinese×light/dark×390/1440px의16조건에서 문구·툴팁·비활성화와 가로 overflow0을 확인했다. 별도 screenshot은 적용된 light/dark theme까지 확인했다.
3. **격리 source와 아키텍처**: baseline `7f2572197747bb80e09255879836b415b0d96edd`에 변경8개와 기존 비밀번호 기능의 미커밋 prerequisite4개(loading/operation 회귀 fixture, Instance 생성자·프로젝트 type, TextInput autocomplete)를 그대로 복사한 별도 clone으로 검증했다. Working stamp와 별도 index의 `--staged`는 source digest `7762e0fab9a7de9f60509f3a9803dc6c3028bdab1f9b101aa6ed64196e4ea869`/2547files에서 통과했다. Prerequisite4개는 이 작업이 수정한 파일이 아니다. 공유 index·root review marker·동시 작업은 보존했으며, compiled 이미지의 당시 공유 frontend context와 이 격리 gate source를 혼동하지 않는다.
4. **검증 이력과 한계**: 첫 공유 검사는 MCP/my-resources의 별도 i18n/type/compile 오류 및 private TOML startup 오류로 실패했다. 격리 환경의 첫 실행에서도 dev 의존성 누락·기존 password fixture/type 누락·상속된 service URL·잘못 선택한 disposable DB가 확인되어 검증 환경만 바로잡았다. Eval 로그 writer의 이전 tail 잔존과 subprocess 대기 중 VM 종료 때문에 해당 중간 로그/실행을 전체 gate 성공으로 집계하지 않는다. 실제 운영 설정·공유 source·suite 선택은 수정하지 않았다.
5. **운영 경계와 증거**: identity/API는 loopback 합성이며 비밀번호 제출·provider mutation은0회다. 실제 Nova/QGA/guest login·운영 credential/DB·배포·commit/push는 검증하거나 변경하지 않았다. JSON·적용된 theme screenshot·격리 architecture receipt·성공/실패 로그는 `/Users/pieroot/.local/share/afterglow-proofs/password-support-notice-20261011/`에 보존한다. Optional gbrain CLI가 설치되지 않아 refresh나 agent guidance 변경은 수행하지 않았다.
6. **최종 검사 결과**: 격리 frontend check는0errors/기존 DocCodeBlock warning1이며 i18n check/scan은0문제였다. 원래 명령·suite를 유지한 `npm run test:gate`는 architecture, orchestration175, Kolla Node27/Python11, CLI19(기존 PowerShell36skip), backend unit4595, frontend336files/2725+scripts9, contract154를 통과한 뒤 functional에서 실패했다. 새 소유 MariaDB container의 `OOMKilled=true`/exit137과 connection 실패를 확인했으므로 전체 gate 통과로 보고하지 않는다. 같은 disposable store의 독립 functional 실행은73passed/22deselected였고, gate 뒤 별도로 실행한 Ruff check/format은573files 통과했다. 최종 gate 원문은 `test-gate-final.log`, OOM 상태는 `test-store-oom.txt`, 실행 구분은 `test-gate-result.json`에 보존한다.

## MCP VM·빈 볼륨 생성·네트워크 연결 검증 (2026-10-11, local-only)

`mcp-cloud-provisioning`은 canonical registry와 compute/storage/network adapter 및 관련 pytest source9개를 변경한다. Version `1.30.11`, 공유 index·기존 review marker·private 설정·기존 컨테이너/볼륨/키는 보존했다. 새 DB schema·설정·의존성·일반 REST endpoint·UI 변경은 없으며 다른 작업의 migration084/권한 확장에 대한 운영 호환성 승인도 아니다.

1. **행동 회귀**: 6개 test file의 exact selector309개와 named MCP unit428개(실제 DB/contract55개는 별도 계층으로 deselected)가 통과했다. 생성 입력/상태·owner·가시성·quota/admission/GPU·deadline/cancel 경계, target-project grant 및 credential binding, preview 무변경·완료 replay·unknown 재전송 금지와 typed safe result를 검증했다. 변경 Python9개의 Ruff가 통과했다.
2. **설치된 SDK의 실제 소유자 결함**: openstacksdk3.3.0의 `get_keypair(name, user_id=...)`가 caller owner를 resource body에 보충하여 Nova가 owner를 생략해도 증명처럼 남는 것을 실제 loopback Nova HTTP로 재현했다. Before는 missing-owner1개 실패·foreign/exact-owner2개 통과, caller owner seed 제거 후 세 경계 모두 통과했다. Owner가 없거나 타인이면 생성하지 않고 비밀을 응답에 남기지 않는다.
3. **실제 TCP/MCP/Lumen/SQL/Redis**: MCP SDK1.28.1·protocol2025-11-25, openstacksdk3.3.0, 실제 disposable MariaDB11.4/Redis7과 loopback native HTTP를 통해14개 scenario를 실행했다. MCP와 Lumen 각각 세 작업의 접수 및 replay는 provider mutation1회씩, Lumen preview는0회였다. Unsupported extras/미승인 target6개·quota/host fact/network 인가3개·read-only 직접 호출3개는 write0이었다. Provider가 효과를 기록한 뒤500을 반환한 세 작업은 각각 같은 key2회/새 key1회 호출에도 write1회, persisted `unknown`·result null·redacted error를 유지했다. 최종 원장은 succeeded6·unknown3·provider writes9이며 모든 write는 승인된 project-b였다.
4. **합성 경계와 검증 환경**: Keystone identity/token/catalog, Nova/Cinder/Neutron/Glance provider, operator host capacity facts만 합성이다. SDK 직렬화·transport·인가·admission·원장·SQL/Redis는 실제다. 첫 QA keypair query 가정은 native SDK 사실에 맞춰 수정했고, 빠른 전체 호출의429는 기본 mutation20/minute를 완화하지 않고3.25초 pacing으로 해결했다. MCP connection만 성공한 것으로 tools/call 성공을 대체하지 않았다. 공유 private config는 변경하지 않고 sanitized frozen snapshot과 Node24.14.1·GNU tools를 사용했다.
5. **아키텍처·전체 게이트**: frozen source digest `861d0a171b23368f404cadbf31919f06f5464cb06c3d4cac7f8a74eaf287a567`/2558files의 working stamp와 별도 임시 index의 `--staged`가 통과했다. 공유 working tree/index의 동시 변경을 이 digest로 인증하거나 marker를 덮어쓰지 않는다. 최초 `test:gate`는 docs/JS/backend4885개 통과 후 frontend optimizer의 `node:module`/missing tsconfig startup에서 중단됐다. 격리 frontend에서 기존 `svelte-kit sync`로 생성 설정을 준비한 뒤 startup selector8개, 전체 frontend341files/2751개+scripts9, contract154 및 실제 MariaDB/PostgreSQL/Redis functional83개가 통과했다. 최종 `npm run test:gate`도 docs·JS·backend4885·frontend2751+scripts9·contract154·functional83·Ruff573files 전체를 통과했다(CLI36skip, functional22deselected). Source·suite를 축소하거나 optimizer를 비활성화하지 않았으며 첫 실패는 통과로 집계하지 않는다.
6. **운영 한계**: VM `BUILD`, volume `creating`, 새 port ID는 접수 증거일 뿐 ACTIVE/available·guest readiness·실제 network data plane은 미검증이다. 실제 OpenStack 생성/연결·운영 DB/IAM/credential 변경·이미지 발행·배포·commit/push는 수행하지 않았다. Default Lumen read-only 권한을 확대하지 않았다.
7. **증거 보존**: native runtime JSON, MCP target·최초 실패 gate·환경 준비 후 frontend·최종 성공 gate 로그, frozen architecture review와 변경 source9개가 검증 snapshot과 일치하는 SHA-256 receipt는 `/Users/pieroot/.local/share/afterglow-proofs/mcp-cloud-provisioning-20261011-fh5LaE/`에 보존한다. Optional gbrain refresh는 CLI와 detect binary가 없어 실행하지 않았으며 agent guidance를 변경하지 않았다.

## MCP 개인 토큰·OAuth 폐기 목록 검증 (2026-10-11, local-only)

`hide-revoked-mcp-access`는 계정의 기존 DELETE→목록 재조회 경로에서 폐기한 tombstone이 다시 반환되는 문제를 수정한다. 명시적 폐기만 숨기고 아직 폐기하지 않은 만료 항목은 유지한다. Grant/token 행·감사·pending cleanup은 보존하며 새로운 schema/migration·router/response field·설정·의존성은 없다. 공유 index·기존 컨테이너/볼륨/키와 다른 작업의 변경을 보존한다.

이미지 빌드 context는 당시 공유 worktree이며 전체 gate/architecture snapshot과 별개다. 변경 authority의 두 runtime source hash는 overlay 입력과 일치했지만 이 결과로 동시 WIP 전체를 검증했다고 주장하지 않는다. Rapid change는 `openspec/changes/archive/2026-10-11-hide-revoked-mcp-access/`에 완료 checklist와 함께 archive했다.

1. **실패 전·통과 후**: 실제 disposable MariaDB와 management HTTP에서 active 개인 토큰/OAuth DELETE204 뒤 GET에 `revoked` 항목이 남고, expired 항목은 DELETE204 뒤에도 `expired`로 남는 것을 재현했다. 기존 권한 resolver는 이미 폐기한 자격을 거부했으므로 확인된 결함은 목록 표시이며 인증 우회라고 주장하지 않는다. 이전 authority를 로드한 새 회귀에서도 retained-list assertion이 실패했다. 수정 후 exact SQL/HTTP 회귀10개, OAuth refresh·project authority 전체59개, named MCP unit216개와 frontend tutorial/account92개가 통과했다.
2. **실제 로컬 runtime·화면**: canonical Dockerfile backend/frontend를 arm64·amd64로 빌드·실행하고 canonical dev Compose의 자체 project에서 두 architecture의 실제 SQL·HTTP authority를 검증했다. 사용자/프로젝트 격리, active/expired 폐기와 반복204, 목록 제외, epoch 한 번 증가, 접근·refresh 거부와 upstream 실패 시 cleanup 보존을 확인했다. Compiled 계정 화면에서도 두 architecture 각각 개인 토큰2개·OAuth2개의 확인/DELETE204 뒤2→1→0과 빈 상태, 새로고침 후0행을 관찰했다. ARM64 폐기 취소는 DELETE0·행 유지였고 AMD64 OAuth upstream 정리 실패에서도 항목이 사라지고 persisted cleanup pending·authentication rejected를 유지했다. Compiled tutorial도 개인 토큰/OAuth 폐기 뒤 재조회에서1→0·빈 상태였다; tutorial 전체 reload는 원래 in-memory fixture를 초기화하므로 DB-backed reload acceptance와 구분한다. Identity·Keystone 및 무관한 계정 API는 합성이며 일반 MCP 목록·폐기 요청은 실제 로컬 SQL-backed HTTP로 연결했다.
3. **격리와 환경 경계**: 검증 snapshot은 frozen HEAD와 MCP source/test4개만 포함한다. 현재 named runner는 `mcp` target216개에 사용했다. 전체 gate에 그 runner를 섞자 무관한 password-selector 파일 부재로 catalog 검증이 실패하여 snapshot runner를 unmodified HEAD로 복구했다. 이어 backend4595개 통과 뒤 frontend optimizer가 missing generated tsconfig/`node:module` startup에서 중단됐다. 기존 `npm run prepare`로 `.svelte-kit/tsconfig.json`을 생성해 검증 환경을 바로잡았다. 공유 runner/source를 수정하거나 suite를 축소하지 않았다. 외부 scratch harness의 `/app` import를 위한 `PYTHONPATH`, synthetic auth JSON의 Content-Type과 허용 loopback CORS는 QA 입력에서만 바로잡았다. Browser tool의 successful204 `ERR_ABORTED` 오분류는 실제 응답204·UI·SQL 결과로 판정하고 tool issue로 보고했다.
4. **증거와 운영 한계**: HTTP·browser JSON과 empty-state screenshot은 `/Users/pieroot/.local/share/afterglow-proofs/hide-revoked-mcp-access-20261011/`에 보존한다. 이 수정은 기존 schema 필드만 사용하고 DB 목적지·ledger·키를 변경하지 않는다. 실제 배포 revision/schema·production snapshot·원본 키·mixed-version writer/schema 양방향·backup/restore·운영 Keystone cleanup은 검증하지 않았으므로 운영 데이터 호환성이나 실제 인증 acceptance로 승격하지 않는다. 운영 DB/IAM/credential 변경·이미지 발행·운영 배포·commit/push는 수행하지 않았다.
5. **최종 gate·architecture**: generated config 준비 뒤 동일 scoped snapshot의 전체 `npm run test:gate`가 exit0이었다. Orchestration175, Kolla27/image-reference11, Unix CLI19, backend unit4595, frontend335files/2709tests 및 runner9, consumer contract154, 독립 disposable functional83/22deselected, Ruff check/format573files가 통과했다. PowerShell36개는 runtime 부재로 skip이며 Windows proof가 아니다. Working와 임시 index의 staged architecture guard는 같은 `source_sha256=c439ce29330b22a793ed8f0e36d42f4c61022665f651066d5ac09fc282a21b73`/2546files였다. Shared/snapshot 실제 index와 공유 review marker를 변경하지 않았으며 다른 WIP 전체를 gate했다고 주장하지 않는다. 위 proof directory의 `gate.json`/`architecture.json`에 명령·범위·전체 출력 reference를 기록했다. 기존 backend deprecation/test-key warning은 남아 있다. Own runtime/test-store project·image tag·browser만 정리하며 사용자 서비스를 중지하거나 volume을 삭제하지 않는다. Optional gbrain은 CLI 부재로 실행하지 않았고 agent guidance는 변경하지 않았다.


## 인스턴스 생성자·시스템 관리자 비밀번호 변경 검증 (2026-10-11, local-only)

`instance-password-change`는 private 설정을 제외한 독립 source snapshot과 자체 canonical dev Compose project에서 검증했다. 기존 version `1.30.11`과 공유 index·review marker·사용자 설정·기존 컨테이너/볼륨/키를 보존했다. 이 기능은 기존 Nova API 인가 및 공용 상세 UI의 변경이며 신규 DB schema·설정·의존성·native 정책을 도입하지 않는다. 동시 작업의 migration084나 운영 DB 양방향 호환성을 이 receipt로 승인하지 않는다.

1. **행동 회귀**: password44개와 SCSI 루트/유일한 bootable/모호한 두 bootable/불일치 root의 네 경계를 포함한 instances target backend584·frontend23files/219개가 통과했다. 생성자·현재 프로젝트의 일치, 시스템 관리자, 같은 프로젝트 타인·project-admin·reader·missing identity·위조 metadata 거부, ACTIVE/QGA 요구, 비밀을 숨기는 길이/상류 실패를 검증한다. Controller의 인증·인스턴스 전환 뒤 late precheck 무효화와 write 회수도 포함하도록 focused target을 갱신했다.
2. **실제 HTTP·설치된 SDK**: canonical Dockerfile의 backend arm64/amd64를 각각 실행하고 FastAPI→openstacksdk→합성 Nova/Glance/Cinder HTTP 경계를 각12조건에서 확인했다. Windows 생성자·SCSI volume boot·Linux 생성자·다른 프로젝트 시스템 관리자204, 타인 precheck/POST403, 타 프로젝트 native404, 비활성/QGA 미지원409와 Nova 정책403을 구분했다. 응답의 비밀 echo는0이며 provider 기록에는 비밀번호 길이·digest·합성 actor만 남긴다. Root 장치가 `/dev/sda`인데 데이터 디스크가 `/dev/vda`인 실제 SDK 응답에서 올바른 `Administrator`와 QGA를 확인했다.
3. **실제 compiled Chromium**: 생성자 제출과 다른 프로젝트 시스템 관리자 제출, 타인 버튼/precheck 부재, 미지원 사유, 거부 후 열린 dialog, Windows/Linux 계정 안내, close/reopen의 입력 폐기, 제출 중 입력·취소·close/Escape 차단을 확인했다. Canonical arm64 UI→BFF 생성자 및 amd64 UI→BFF 관리자 POST는 각각 실제204였다. 네 locale×두 실제 초기화 theme×390/767/768/1023/1024/1440px의48조건에서 document/dialog overflow0·입력 bounds·password masking·계정 표시가 통과했다. Mobile light와 desktop dark screenshot을 실제로 읽었다.
4. **발견·수정·환경 경계**: 첫 SDK 실행에서 `/dev/vda` 추정이 Windows boot metadata를 놓쳤고 네 실패 회귀를 보존한 뒤 Nova root/Cinder bootable 정보로 수정했다. 최종 gate 중 발견한 obsolete `require_admin` import는 제거했다. 격리 PATH에 GNU `sha256sum`이 빠진 Linux cloud-init 회귀와 Homebrew Node26의 experimental localStorage로 인한 jsdom 실패는 필요한 GNU tools·기존 Node24.14.1 runtime을 명시해 해결했다. 기능 회귀를 skip하거나 실패를 성공으로 취급하지 않았다. 문서 문구·CLAUDE symlink만 pin하던 incidental assertion 두 개는 제거하고 기존 소비자 행동 회귀는 유지했다. 컨테이너 외부 harness의 `/app` import path, 잘못된 QA URL과 synthetic auxiliary CORS/알림 응답은 QA 환경에서만 수정했다. Browser helper의 role selector 및 successful204 `ERR_ABORTED` 오분류는 tool issue로 보고했고 실제 요청204·UI·provider action으로 판정했다.
5. **운영 및 MCP 구분**: proof는 `/Users/pieroot/.local/share/afterglow-proofs/instance-password-change-20261011/`의 HTTP·browser·provider·runtime JSON과 screenshot에 보존한다. 합성 identity/provider acceptance이며 실제 게스트 QGA 적용·RDP/SSH 로그인·운영 인증/VM 비밀번호 변경·발행/배포 증거가 아니다. 별도로 현재 mount된 MCP의 authenticated read-only capabilities9개 domain·Nova overview21/ACTIVE21 응답을 확인했다. 기존 public OAuth/개인 키 운영 수용은 기록상1.30.9이며 새 다중 프로젝트/Lumen 확장은 배포됐다고 주장하지 않는다. Optional gbrain refresh는 CLI 부재로 실행하지 못했고 agent guidance는 변경하지 않았다.
6. **최종 전체 gate·source qualification**: 최종 import 정리까지 반영한 snapshot의 `npm run test:gate`는 exit0이었다. Orchestration175, Kolla27/image-ref11, Unix CLI19, backend unit4,673, frontend341files/2,751, consumer contract154, disposable functional73/22deselected와 Ruff check·format573files가 통과했다. PowerShell36개는 runtime 부재로 skip이며 Windows 실행 증거가 아니다. 동일 source의 Svelte check0errors/기존 DocCodeBlock warning1, i18n check0errors/0warnings·37namespaces/9,534messages, i18n scan991files/0hard-coded Korean lines도 통과했다. Working 및 격리 staged architecture guard는 동일 fingerprint `3752a8bc75632ca9931b01143574f21690191861877ff612484569d889ca7716`/2,557files로 성공했다. 공유 index/review marker는 변경하지 않았다. Canonical backend/frontend/worker의 arm64·amd64 최종 이미지를 실행해 HTTP 각12조건·frontend health200 및 worker uid1000/crypto 왕복을 다시 확인했다. Gate 전체 로그·진단·source/image parity는 같은 proof directory에 보존한다. 기존 backend deprecation/test-key 및 Svelte binding/a11y 경고는 남아 있다.

Rapid change는 proposal/tasks 완료 후 `openspec archive instance-password-change --skip-specs --yes`로 `openspec/changes/archive/2026-10-11-instance-password-change/`에 archive했다. Generic validator의 delta-spec 경고는 이 repo의 rapid schema가 specs를 요구하지 않는 비차단 경고이며 별도 spec 관례를 추가하지 않았다.


## 관리자 네트워크·서브넷 IP 조사 검증 (2026-10-11, local-only)

`network-ip-visibility`는 frozen dev 기준의 네트워크 관련 42개 source/test 경로만 overlay한 독립 snapshot에서 검증했다. 공유 작업 트리의 별도 MCP·migration084 checkpoint와 검증 범위를 섞지 않으며 실제 Git index·공유 architecture review marker·기존 컨테이너/키/볼륨을 보존했다. 기존 `1.30.11`을 유지하며 운영 배포는 수행하지 않았다.

1. **최종 전체 gate**: `npm run test:gate`가 exit0이었다. Orchestration111, Kolla27 및 image-ref11, Unix CLI19, backend unit4,444, frontend339files/2,603, consumer contract154, disposable functional35/9deselected, Ruff check·format560files가 통과했다. PowerShell36개는 runtime 부재로 skip이며 Windows 실행 증거가 아니다. Working source fingerprint는 `4426f9d748dd38a7cce8e48f27f35518e744604414461a7eabe2c4a2b01ac6c1`/2,540files다. Focused backend212개와 frontend9files/54개도 통과했다.
   동일 final snapshot의 Svelte check는2,350files/0errors/기존 DocCodeBlock warning1, i18n check는0errors/0warnings·37namespaces/9,482messages, i18n scan은991files/0hard-coded Korean lines였고 production build도 exit0이었다. 전체 로그는 같은 proof directory의 `frontend-qualification.log`에 보존한다.
   동일 digest/2,540files의 임시 index에 대한 `scripts/check_architecture.py --staged`도 성공했다. 실제 공유/clone index는 변경하지 않았으며 `architecture-qualification.json`에 결과를 보존한다. Rapid change는 delta spec 없이 `openspec/changes/archive/2026-10-10-network-ip-visibility/`로 archive했다.
2. **실제 HTTP/native SDK**: canonical Dockerfile의 arm64/amd64 BFF를 실행하고 설치된 OpenStack SDK가 합성 Keystone/Neutron/Nova HTTP 공급자를 조회했다. 두 아키텍처 각각12조건을 통과했다: 전체 프로젝트와 소유자, 실제 IP 버전, overlapping pool 합집합·중복 fixed IP·정확한 subnet 귀속·gateway 예약, exact IPv6 decimal·SLAAC/RA-only의 잔여 해당 없음·off-subnet/link-local gateway, malformed pool/필수 port page 장애, 선택적 device/DHCP 이름 장애, 네이티브 관리자 문맥 부재403과 Neutron 조회0, upstream404/503·비관리자403. Provider resource mutation은0이다. Worker canonical image의 두 아키텍처 crypto 왕복도 성공했지만 실제 Notion sync 증거가 아니다.
3. **실제 Chromium 표면**: 빌드된 로컬 UI와 BFF에서 유형 AND·정규화/현지화 검색·소유 이름/전체 ID·초기/후속/부분 장애와 복구·각 서브넷의 독립 펼침·IPv6 정확한 수량을 검증했다. 28개 할당/27개 포트 fixture의20행 독립 pagination·목록 축소 시 page 보정도 확인했다. 목록/네트워크 내 조사/독립 서브넷3표면 × KO/EN/JA/ZH-CN × light/dark ×390/767/768/1023/1024/1440px의144조건에서 document/value overflow는0이었다. 긴 테이블은 내부 scroll로 원래 값을 보존한다. AMD64 frontend→AMD64 BFF의 실제 필터·IPv6 화면은 console error0이었다.
4. **중간 실패와 환경 수정**: 첫 gate의 MCP mock2개 실패는 최신 공유 mock과 이전 baseline MCP consumer를 섞은 snapshot 구성 때문이었다. 격리 snapshot의 두 mock 파일에서 무관한 MCP 부분만 baseline으로 복구하고5개 subnet IP-version fixture 변경을 보존했다; 공유 MCP 작업은 수정하지 않았다. 잘못된 frontend cwd의 alias resolution은 frontend 디렉터리에서 실행해 해결했다. 다음 gate의 functional 기동은 기존 `afterglow-mcp-scopes-test`가5434를 사용하여 실패했다. 그 DB를 중지/재사용하지 않고 자체 `afterglow-network-ip-functional` project의 loopback 임의 포트 세 저장소를 기존 `AFTERGLOW_TEST_DATABASE_URL`/`AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL`/Redis override로 제공해 전체 gate를 완료했다. Suite 축소·skip으로 실패를 숨기지 않았다.
5. **증거/운영 한계**: 로컬 proof는 `/Users/pieroot/.local/share/afterglow-proofs/network-ip-visibility-20261010/`의 `test-gate.log`, `http-arm64.json`, `http-amd64.json`, `browser-qualification.json`과 screenshot에 보존한다. 이는 합성 인증·공급자 경계의 실행 증거이며 운영 Keystone 인증·실제 cloud inventory·IAM 쓰기·DHCP lease/guest connectivity·이미지 발행/운영 배포의 acceptance가 아니다. 신규 DB schema·설정·의존성·운영 자원 변경은 없다. 기존 backend deprecation/test-key 및 DocCodeBlock 접근성 경고는 남아 있다.


## 누적 dev checkpoint 커밋 검증 (2026-10-11, local-only)

사용자의 현재 변경 커밋 요청에 따라 private 설정을 제외한 누적 source snapshot을 검증했다. 이 snapshot의 package version은 기존 `1.30.11`이며 아래 개별 수정의 `1.30.12` 기반 격리 receipt와 서로 다른 범위다. 기존 OpenSpec와 각 수정의 smoke 기록은 보존한다.

1. **최종 전체 gate**: 독립 loopback MariaDB/PostgreSQL/Redis만 제공한 `npm run test:gate`가 exit0이었다. Orchestration175, Kolla27 및 image-ref11, Unix CLI19, backend unit4,595, frontend335files/2,709 및 runner9, consumer contract154, disposable functional73/22deselected, Ruff check 및 format573files를 통과했다. PowerShell runtime이 없어36개는 skip이며 Windows 실행 증거가 아니다. 최종 source fingerprint는 `82dd2411df453e5b44a7afe9f40c65f627c930e07ee03bca02df4713860d6ee0`/2,546files다.
2. **프론트엔드 진단·빌드**: 동일 frontend source의 Svelte check2,344files/0errors/기존 DocCodeBlock tabindex warning1, i18n check0errors/0warnings·37namespaces/9,489messages, i18n scan988files/0hard-coded Korean lines 및 production build가 통과했다. Unit 실행의 binding/raw-snippet 경고와 backend deprecation/test-key 경고는 숨기거나 성공 증거로 대체하지 않는다.
3. **검증 중 실패와 수정**: 첫 환경 준비에서 optional `dev` extra가 빠져 pytest 실행이 불가능했으며 frozen dev-extra 설치로 해결했다. 제거된 private `ledger._validate_lumen_selection`만 호출하던 obsolete implementation test는 삭제했고, 현재 connection/ledger·HTTP consumer의 generation fence 회귀73개는 그대로 통과했다. DB gate의 OAuth4개 실패는 fixture가 예전 `list_projects` mock만 제공하고 실제 caller-token `/auth/projects` session 호출을 지원하지 않던 원인이었다. 기존 provider fixture 관례로 교체하고 불필요한 예전 mocks를 제거했다. 만료 clock은 helper 호출 횟수가 아니라 credential 생성 중에 전진시킨다. OAuth DB22개는 grant revocation·코드 미발급·home/child 암호문 및 credential ID 폐기·remote credential 정리와 refresh 권한 축소/프로젝트 범위 고정을 실제 MariaDB 상태로 검증한다. Gate가 거부한 included Python imports/format만 정상화했다.
4. **DB 호환성 평가 범위**: Functional gate는 migration084를 축소 legacy fixture에 두 번 적용하여 singleton `current` 범위 보존과 자식 FK/cascade를 검증했다. 실제 OAuth/Lumen/추가 프로젝트 credential persistence도 disposable DB에서 실행했다. 운영 snapshot·실제 ledger/checksum·원본 키/companion state·old writer가 new 다중 프로젝트 row를 처리하는 방향·new writer가 old schema를 처리하는 방향·mixed API/worker·backup/restore/rollback은 미검증이다. 새 writer 적용 전 migration 선행과 복원 snapshot의 양방향 검증이 필요하며, additive SQL/빈 DB 성공만으로 운영 하위·상위 호환성을 승인하지 않는다. 같은 URL 선택은 직접 공유 접근이지 자동 복제/동기화가 아니다.
5. **커밋/운영 경계**: 요청 시점에 확정한147개 경로의 snapshot을 제출한다. 검증 도중 별도로 추가된 진행 중 `network-ip-visibility` 변경은 작업 트리에 보존하며 이번 checkpoint와 gate 통과 범위에 섞지 않는다. `.env`·private TOML·`.local-services`·`.omp/mcp.json`·generated outputs/캐시는 commit에서 제외한다. 버전 bump·push·tag·배포·운영 IAM/DB 조회/쓰기·migration 및 기존 shared container/volume/key 변경은 수행하지 않았다. 임시 검증 project만 사용하며 제출 index의 architecture guard도 별도로 실행한다. Optional gbrain refresh는 CLI 부재로 실행하지 못했고 agent guidance는 변경하지 않았다.

## Custom 역할 연결 경계 수정 검증 (2026-10-11)

보고된 `project_reader → audit`은 관리자의 명시적 role inference 편집이다. 프리셋 이름 목록을 전체 허용 역할 목록으로 사용해 상위 `project_owner → audit`을 거부하던 원인과, 같은 그래프를 프로젝트 멤버 관리가 재차 거부하는 경로를 함께 수정했다. 일반 reader의 self-escalation을 허용하지 않으며 알려진 core/project/service 권한은 기존 ceiling으로 제한한다.

1. **실패 전·통과 후 회귀**: 새 endpoint 회귀 두 개는 수정 전 각각 `409 Unsafe role implication requires review: project_owner -> audit`, 승인된 연결을 가정한 후속 프로젝트 관리의 `503 Project management role graph is unsafe`로 실패했다. 수정 후 exact10개 및 역할·멤버 파일 전체110개가 통과했다. 공유 source도 `/private/tmp` config-discovery 문맥에서 격리 interpreter로 동일110개를 통과하여 사용자 private 설정을 변경하지 않았다. Canonical `access` target은 backend285/frontend2files15개 통과.
2. **실제 HTTP/native SDK smoke**: 격리 clone과 공유 source의 production router를 Uvicorn HTTP로 실행했다. 설치된 openstacksdk·python-keystoneclient가 loopback Keystone fixture에 실제209요청을 전송했다. 시스템 관리자 연결200 및 네 project ancestor의 실제 상속, custom edge를 보존하는 프리셋 재적용200, project-admin의 assignable 목록/멤버 reader 교체200와 `reader+audit`·native `member` 부재, custom 직접 위임422, 일반 reader 전역 편집403, custom alias의 core/member/managed-write 전이409, 연결 제거 후 fresh graph에서 audit 상속 제거와 프로젝트 관리 유지가 통과했다. 감사 lifecycle도 실행했다. Synthetic 인증/session·FakeRedis·identity provider를 사용한 boundary proof이며 운영 Keystone 인증·정책·역할 쓰기 acceptance가 아니다. 첫 smoke의 fixture `aclose` teardown 실패를 현재 설치된 `close`로 수정한 뒤 모든 cleanup을 포함해 exit0을 확인했다.
3. **변경/운영 경계**: 기존 `identity_roles._validate_preset_catalog`와 `project_service._managed_roles` 및 기존 endpoint 회귀를 수정했다. Router/response schema·DB/ORM/SQL/manifest·native 정책·운영 인가 설정은 변경하지 않는다. Custom 역할은 프로젝트 API의 독립 위임 목록에 들어가지 않으며 `audit`이라는 이름만으로 native policy가 읽기 전용이라고 판정하지 않는다. 운영 Keystone 조회/변경·배포·기존 shared datastore 변경은 이 fix 검증에 포함하지 않는다. 공유 WIP의 별도 migration084 및 전체 동시 변경의 compatibility는 별도 판정이다.
4. **통합 gate/architecture**: 서비스별 DB 선택과 이 역할 fix를 합친 1.30.12 기반 격리 dev snapshot에서 `npm run test:gate`가 exit0이었다. Orchestration175, Kolla27, CLI19통과/PowerShell36skip, backend4411, frontend334files/2569 및 runner9, contract174, disposable functional35/9deselected, Ruff check/format561files를 통과했다. Working와 임시 index의 staged architecture guard가 같은 `source_sha256=0bb847f540722c9904bab68466af4a42075fe05b1690db4b864a49163c330c77`/2532files를 검증했다. 두 실제 Git index와 공유 architecture review marker는 보존했다. 이 receipt는 공유 전체 WIP·migration084·운영 IAM/DB의 승인이 아니다.

## Compose 서비스별 DB 선택 검증 (2026-10-11)

`AFTERGLOW_DATABASE_URL`, `DROVER_DATABASE_URL`, `LUMEN_DATABASE_URL`, `WAYGATE_DATABASE_URL`, `PALIMPSEST_DATABASE_URL`을 각 서비스의 내부 `DATABASE_URL`로 전달한다. 기존 local-only 규칙을 명시적 목적지 선택으로 교체했으며 generic `DATABASE_URL`은 목적지를 고르지 않는다. Dev의 unset/empty는 local fallback, 최소/prod Afterglow는 nonempty prefixed 입력이 필수다.

1. **실제 Compose와 private 준비 경로**: datastore matrix 67개가 14개 소비자의 `.env`·explicit env-file·shell 우선순위, 단일 서비스 선택, unset/empty 및 prod/base 필수 입력 경계를 통과했다. Runner 2개는 credential-safe 0600 private env-file 왕복과 원본 `.env` 제거 후 목적지 유지, 재준비 시 기존 secret 보존을 확인했다. Compose JSON의 `$` 재-escape를 decode하고 dotenv용으로 다시 escape하며 실제 subprocess에는 raw resolved 값을 전달한다. JavaScript replacement-string `$$`가 한 dollar를 의미하는 함정도 수정했다. 공유 작업 트리 `test:orchestration` 175개 통과.
2. **실제 이미지/DB smoke**: canonical source Dockerfile의 backend·Notion·각 sibling API/worker 10개 image를 amd64/arm64로 빌드했다. 두 architecture × 명시적 외부-selected/empty-fallback × 14개 소비자에서 각 서비스 package의 실제 DB session factory를 초기화하고 `SELECT DATABASE()` 및 SQL write/read를 검증하여 56회 통과했다. 외부-selected는 같은 disposable network의 별도 synthetic schema이며 운영 DB가 아니다. Migration/bootstrap 소비자도 전달된 URL과 engine 동작을 확인했지만, 이 smoke가 실제 migration CLI 실행·API lifespan·운영 schema upgrade를 증명하는 것은 아니다.
3. **전체 gate의 범위**: 1.30.12 기반 격리 dev clone에 이 변경만 통합하고 독립 project의 loopback ephemeral MariaDB/PostgreSQL/Redis를 제공하여 `npm run test:gate` 통과. Orchestration 175, Kolla contract 27, CLI install 19/36 PWSH skip, backend unit 4,401, frontend 334 files/2,569 tests 및 runner 9, consumer contract 174, disposable functional 35/9 deselected, Ruff check와 format 561 files. Architecture guard source digest는 `d32e88081e4349e2bf97917d8521593e811fc78d2ed20a89d032b0c77b1e4d04`(2,532 files)다. 공유 작업 트리의 다른 미완료 변경까지 전체 gate로 qualification했다고 주장하지 않는다.
4. **실패와 수정**: 수정 전 runner의 두 credential 왕복은 실패했다. Mounted `/tmp` probe의 application import root 누락과 새 clone의 generated frontend tsconfig 누락도 확인하여 probe import 경로와 기존 `svelte-kit sync` 준비 절차를 바로잡은 뒤 위 smoke/gate가 통과했다. 이전 실패 실행은 성공 증거로 취급하지 않는다.
5. **운영 호환성 경계**: 이 URL 선택 변경은 SQL/ORM/manifest를 변경하지 않는다. 공유 작업 트리의 별도 migration `084-mcp-project-delegation`은 이 변경의 qualification에 포함하지 않는다. 실제 배포 ledger/checksum·production snapshot·원본 암호화 키·mixed API/worker와 양방향 writer/schema·backup/restore·rollback 검증은 아직 제공되지 않았으므로 운영 데이터 호환성을 미검증으로 남긴다. 같은 URL은 직접 공유 접근이며 자동 복제/동기화가 아니다. 이 DB 변경의 검증에서 운영 DB 조회/쓰기·migration·배포와 기존 공유 port/volume/key 변경은 수행하지 않았다.
## 1.30.12 HTTPS proxy scheme 검증 (2026-10-11)

Kolla controller peer의 `X-Forwarded-Proto`가 Uvicorn 기본 loopback 신뢰에서 무시되는 원인을 수정했다. 초기 세 배포 경로에서 HTTPS6개가 실패한 뒤 bounded trust 교체로12개가 통과했다. 최종 Kolla·generated Kubernetes·setup Kubernetes·Helm을 실제 ASGI app에 연결하여 redirect16개와 인증 전환4개가 통과했다. 실제 signed JWT/session store와 subnet 정책에서 전환 전 proxy-IP token200 → 전환 후401, fresh client-IP token200, 비신뢰 peer의 위조401을 검사한다. Keystone·Redis는 hermetic fixtures이며 실제 운영 인증으로 승격하지 않는다.

Canonical Dockerfile의 arm64·amd64 backend image에서 실제 Uvicorn HTTP GET을 실행했다. Trusted HTTPS307·direct HTTP307·untrusted forged header307의 scheme과 encoded query 보존을 확인했다. Lifespan을 끈 sandbox transport smoke이며 운영 readiness·인가·datastore qualification은 아니다. `setup.py` ConfigMap도 required env key와 inline trust를 같은 입력으로 생성한다.

최종 `npm run test:target -- config`와 `npm run test:gate`가 독립 clone에서 통과했다: backendunit4,401, frontend334files/2,569+runner9, 소비자 contract174, 실제 disposable MariaDB/PostgreSQL/Redis functional35, Ruff check/format561files. Proxy20개는 config와 consumer contract target에 등록되어 전체 CI에서 실행된다. Existing Pydantic/FastAPI/websockets deprecation과 DocCodeBlock tabindex warning은 남아 있다. 불변 release·운영 rollout 증거는 해당 완료 receipt에 기록하며 로컬 proof와 혼합하지 않는다. Optional gbrain sync는 CLI 부재로 실행하지 않았고 공유 checkout이나 search guidance를 변경하지 않았다.

불변 [v1.30.12 release](https://github.com/openstack-afterglow/openstack-afterglow/releases/tag/v1.30.12)는 `9cbfecad419b7d6c64e3a21b06a0cd80b1f44f93`다. 동일 SHA의 [dev CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38068195517), [Docker 발행](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38068463755), [Helm 발행](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38068463407)이 성공했다. 발행 시점 tag/latest digest·revision이 일치했다. 현재 CI 정책상 backend/frontend/worker 발행은 amd64이며 Cloud Shell만 amd64/arm64다. 위 로컬 backend dual-architecture proof와 구분한다.

운영 `kolla-ansible reconfigure -i multinode --tags afterglow`는 failed/unreachable0으로 완료됐다. 세 컨트롤러의 backend/frontend/notion worker9개가 위 revision·검증된 digest로 교체되고 backend/frontend6개가 healthy였다. 실제 backend PID1은 `--proxy-headers --forwarded-allow-ips 127.0.0.1,::1,172.30.0.11,172.30.0.12,172.30.0.13`을 사용한다. 마운트30개와 environment hash9개, 원래 비대상 container613개의 ID·immutable image ID·start/status/health/restarts가 보존됐다. 관측 창에 새로 나타난 Neutron leaf16개는 교체·삭제하지 않았다. Operator secrets/inventory bytes와 canonical globals alias/mode0640이 보존되고 globals 변경은 Afterglow tag와 image pin3개뿐이다.

실제 공개 `/api/v1/admin/version/`는307/`Location: https://cloud.dmslab.re.kr/api/v1/admin/version`이며 encoded query와 공개 forged proto 헤더에서도 HTTPS를 유지했다. 정규화 URL의 무인증401과 login POST의 HTTPS307→검증422를 확인했다. 각 컨트롤러에서 forwarded HTTPS307과 direct HTTP307을 별도로 확인했고 OAuth metadata의 resource/issuer/endpoint URL은 모두 HTTPS였다. 실제 OMP-mounted capabilities·current-project overview 조회가 성공했다. 이 조회는 새 OAuth 발급·쓰기·모든 cloud domain qualification의 증거가 아니다.

OMP browser relay extension 미연결로 `browser.open`을 사용할 수 없어 격리 headless Chromium으로 실제 공개 문서 화면을 확인했다. 화면 로딩 console error0, same-origin slash fetch의 최종 HTTPS URL/redirected=true/인증401, insecure resource0을 관측했다. 짧은 post-rollout smoke이며 장시간 traffic/error-rate 감시나 실제 dashboard 세션 재로그인 증거로 확대하지 않는다. Proxy-IP에 묶였던 기존 세션의 재로그인 필요성은 별도 실제-app 회귀와 운영 문서에 명시했다.

Rapid schema change는 `openspec/changes/archive/2026-10-10-preserve-https-proxy-scheme/`로 archive했다. CLI의 no-delta 경고는 non-blocking이며 이 schema에는 별도 delta spec/sync 대상이 없다. 배포 release tag는 이동하지 않았고 완료 receipt만 후속 dev 커밋으로 기록한다.

후속 완료 기록 커밋 전 추가 `test:gate`는 기존 다른 테스트 프로젝트의 PostgreSQL5434 점유로 functional 시작이 실패했다. 해당 프로젝트를 변경하지 않고 canonical test-profile 설정의 세 DB만 고유 project/network·Docker 할당 loopback 포트로 격리했다. 이 환경의 전체 gate 재실행은 별도 CLI installer PTY fixture(`scripts/lumen-sh.test.js:736`)의 `spawnSync python3 ETIMEDOUT`에서 중단됐다. Release 전 전체 gate와 exact-SHA hosted CI 성공 증거는 유효하지만 이 추가 실행은 통과로 기록하지 않는다. 격리 환경에서 실제 functional35개와 Ruff check/format561files는 별도로 통과했으며 installer 코드·timeout·보안 테스트를 수정하거나 건너뛰지 않았다.

## dev 푸시 통합 검증 (2026-10-10)

Checkpoint `20060ce6aab244a419a9582aa74f06517b133c36`와 fetched dev `9c55578585c2f8147ef06d57e1892cac80eb6093`를 독립 clone에서 통합하고 자격증명·외부 호출 없이 전체 qualification을 완료했다.

1. **정적 검토 및 게이트**: 독립 백엔드·프론트엔드 검토에서 차단 이슈 없음. Ruff로 감지된 4개 빈 줄 경계를 제외한 불필요 변경 0. 전체 `npm run test:gate` 통과(orchestration 111, Kolla contract 27, CLI install 19 / 36 PWSH skipped, backend unit 4,401, frontend 334 files / 2,569 tests + runner 9, contract 154, disposable functional 35, Ruff 560 files). Frontend `check` 통과(2,340 files / 0 errors / 1 existing DocCodeBlock tabIndex warning), `i18n:check` 0 errors / 0 warnings(37 namespaces / 9,440 messages), `i18n:scan` 0 lines(988 files), SvelteKit production build 통과.
2. **실제 브라우저 스모크**: 독립 loopback HTTP API/웹 서버와 headless Chromium에서 만료 세션의 `/docs/mcp` 로딩 시 공지 polling이나 로그인 redirect 없이 정상 렌더링 유지 확인, `/dashboard` 접근 시 `/login`으로 안전한 redirect 확인.
3. **경계 및 비포함**: 사용자가 확인한 MCP 정상 연결을 보존하며 추가 OAuth 수정·미지정 MCP 기능·버전 변경·태그·운영 배포는 포함하지 않는다. 과거 native/production receipt는 해당 시점의 기록으로만 유효하다.

## 1.30.10 권한 피드백·역할 검색·안전한 debug 검증 (2026-10-10)

Published1.30.9 `f48d6fe2` 기반의 격리 `dev`에서 승인된 source만 통합했다. 공유 checkout/merge conflicts·별도 IAM/migration 작업은 수정하지 않았다. 자체 frontend dependencies/backend venv의 final source digest `27a5d0e545bd8f2925694071819d2e414ab7e0ac65a7685513bebef7aecc4881`에 대해 `npm run test:gate`가 통과했다: backend unit4,284, frontend333files/2,523+runner9, consumer contract154, 실제 disposable datastore functional35, Ruff check 및 format557files. Type/locale/build는 별도 qualification이며 기존 deprecation warning을 성공 증거로 숨기지 않는다.

Exact dual-output log/config/Helm regressions는 실제 settings loader와 generated YAML/TOML·Helm consumer를 사용한다. Explicit DEBUG descendant의 SDK/HTTP/SQL/access clamp와 unrelated logger 경계, opaque keys/builtin subclasses, nested/escaped/multiline secret assignment, bounded exception frames를 실제 stream/file JSON에서 검사한다. SQLAlchemy ancestor의 incidental 기본 level에 의존하던 fixture는 unrelated logger를 명시적으로 DEBUG로 설정해 경계를 격리했다. Failed-shape cache 테스트는 cache/availability/단문 record 계약을 유지하고 credential-safe filtering과 충돌하는 upstream exception wording assertion만 삭제했다.

Canonical local Compose의 backend/frontend/Lumen API/worker만 own source로 build·`--no-deps --no-build --pull never --wait` 재적용했다. 19개 container baseline과 비교해 나머지15개 ID/image/start·모든 mounts/volumes·credential environment를 보존했고 유일한 environment 변화는 승인한 backend `DEBUG=true`다. 실제 running API의 main/config/log·Lumen auth bytes가 해당 source SHA와 같으며 versions1.30.10/0.6.7이다. 실제 image process에서 stream/file 두 경로의 source·exception 구조, sentinel secret 부재, wire WARNING-only와 `FastAPI.debug=false`를 확인했다. Private/runtime 값은 receipt에 기록하지 않는다.

실제 유지된 local Keystone browser session에서 identity·chat conversations·chat/admin providers는200이고 dashboard Drover stats는200/available=true였다. 현재 server role-ID catalog를 쓰는 실제 멤버 modal에서 Lumen admin 선택 시15 descendants checked/disabled, parent 제거 시 재계산, case-insensitive name 검색과 accessible no-results, cancel-only/no grant mutation을 확인했다. 390/767/768/1023/1024/1440px에서 modal containment·page overflow0과 light/dark screenshots를 확인했다. Fixture의 transitive/shared parents·explicit direct child·external inheritance·busy/nonowner·hidden selection/save boundaries는 exact behavioral tests로 분리한다. 이는 새 운영 rollout이나 유료 provider 실행 증거가 아니다.

Native headless Chromium은 실제 유지된 local identity와 compiled1.30.10 frontend에서 provider GET만403 합성 응답으로 바꿨다. 실제 조회실패403 feedback을 렌더링하고 같은 token·platform-admin flag·`/admin/chat`을 유지했다. 실제 Keystone/backend와 UI response fixture의 경계를 구분하며 provider mutation은 없다. Access-only 복제의 만료/refresh-cookie 부재401은 service403과 분리하고 통과 증거로 세지 않았다. 허용 localhost/127.0.0.1 origin의 OPTIONS200과 미허용 origin403/no allow-origin은 별도 CORS proof이며 allowlist를 완화하지 않았다. Native role modal은 선택한 explicit leaf를 WAYGATE 검색으로 숨긴 뒤 LUMEN 검색에 다시 선택된 상태로 복원하고 취소했다.

Native-authority security review는 실제 source에 대해 no findings로 완료했다. 두 general reviewer job은 실행 실패하여 완료 review로 세지 않으며 parent가 scoped inline review를 수행했다. Optional gbrain sync는 CLI/config 부재로 차단되어 context guidance를 변경하지 않았다.

Production1.30.9 MCP는 별도 실제 SDK1.28.1/TLS/no-redirect consumer로 personal read key와 browser OAuth 모두 cold capabilities/overview·28 tools·schema-validated Nova/Cinder list를 통과했다. Wrong-client refresh400 후 기존 bearer200, 정상 rotation200/new bearer200, consumed refresh replay400 후 old/new bearer401과 verification OAuth grant revoked를 확인했다. 기존 personal keys5개는 유지했다. Native OMP current-session mounting은 project registration만 완료했고 `/mcp reload`가 아직 필요하므로 이 SDK proof를 OMP-mounted invocation이라고 기록하지 않는다. Final1.30.10/0.6.7 immutable publication·canonical multinode production receipt는 OpenSpec release checklist에서 별도로 확정한다.


## 원칙 및 4계층 테스트 계약

Afterglow 테스트 체계는 4개의 명확한 레이어 계약으로 구성됩니다.

1. **단위 테스트 (Unit)**: `npm run test:unit:backend`, `npm run test:unit:frontend`, `npm run test:unit`. 외부 네트워크·Docker·자격 증명 없이 실행되는 기본 격리 계층이며, `test:unit`은 테스트 오케스트레이터 회귀(workflow 계약과 `scripts/ci/*` 단위 테스트 포함)도 포함합니다. 백엔드 unit은 `pytest-xdist -n 4 --dist worksteal`로 병렬 실행하고, `backend/tests/_network_guard.py`의 network guard(`conftest.py`가 autouse로 등록)가 unit/contract 계층의 non-loopback connect·UDP `sendto`와 localhost 이외 호스트 이름의 DNS 조회(`socket.getaddrinfo`)를 차단하여 실패시킵니다. 로컬 `afterglow.conf` 유무로 결과가 달라지면 결함입니다. 다만 guard는 설정 파일 로딩을 격리하지 않으므로, 네트워크 호출 없이 설정값에만 의존하는 차이는 잡지 못합니다.
2. **소비자 계약 테스트 (Contract)**: `npm run test:contract`. Afterglow BFF 경로, SDK adapter, Keystone catalog/ingress, immutable SDK source 등 추출 서비스와의 소비자 경계를 검증합니다 (`backend/tests/contracts/`).
3. **국소 기능 테스트 (Functional)**: `npm run test:functional`. `docker-compose.dev.yml`의 `test` profile을 전용 project에서 실행합니다(MariaDB 3307, PostgreSQL 5434, Redis 6380). 실제 persistence/cache 경계를 사용하고 OpenStack·추출 서비스는 fake로 유지합니다.
4. **실제 환경 테스트 (Live OpenStack)**: `npm run test:live` (`live:{auth,admin,compute,network,storage,layers}`). 실제 Keystone 인증 및 OpenStack 서비스 API 통합을 검증합니다.

### 독립 서비스 실제 로직 검증 (Service-real)

4계층 기본 게이트와 별도로 **현재 서비스 API/worker를 로컬 또는 Docker에서 실행한 HTTP 검증**을 수행합니다. `test:lumen`, `test:waygate`, `test:palimpsest`는 Afterglow 소비자/BFF 계약이며 서비스 실행 증거가 아닙니다. `test:functional`도 실제 DB/cache에 연결하지만 추출 서비스는 fake입니다. Synthetic browser는 UI 경계만 증명합니다.

```bash
# 기존 dev manifest/project/volume/key를 보존하며 선택한 source만 빌드·기동
# 선택하지 않은 Drover의 service project나 Waygate callback은 요구하지 않음
npm run services:up -- --only lumen,palimpsest

# 로컬 프로세스, Docker 또는 별도 테스트 endpoint에 직접 연결
export LUMEN_API_BASE_URL='http://127.0.0.1:8012/v1'
export LUMEN_API_KEY='<scoped-lumen-api-key>'
npm run services:verify -- lumen                 # 인증 조회만; acceptance 아님
export LUMEN_SMOKE_MODEL_ID='<active-text-model>'
npm run services:verify -- lumen --exercise      # provider 실행·비용 명시 opt-in

# Waygate/Hub는 Afterglow JWT가 아닌 실제 Keystone token 사용
export PALIMPSEST_API_BASE_URL='http://127.0.0.1:8020/v1'
export PALIMPSEST_SMOKE_TOKEN='<project-scoped-keystone-token>'
export PALIMPSEST_SMOKE_BLOB='/path/to/unique-layer.sqsh'
export PALIMPSEST_SMOKE_BUNDLE=1                 # 선택: OCI bundle도 검증
npm run services:verify -- palimpsest --exercise
```

CLI는 Docker·전체 Afterglow 설정·Drover·원격 dashboard를 사전 조건으로 삼지 않습니다. `*_API_BASE_URL`은 origin 또는 `/v1` base이며 redirect/catalog/provider fallback을 허용하지 않습니다. Secret은 환경변수로만 받고 출력·파일 저장하지 않습니다. 환경변수를 echo하거나 shell tracing으로 노출하지 않습니다. 필요 시 `<SERVICE>_SMOKE_PROJECT_ID`로 허용된 project를 명시합니다. Lumen은 `LUMEN_API_KEY` 대신 `LUMEN_SMOKE_TOKEN`을 사용할 수 있지만 둘을 함께 받지 않습니다.

| 서비스 | `--exercise`의 실제 HTTP 시나리오 | 사전 조건·미검증 경계 |
|---|---|---|
| Lumen | native temporary admission/idempotency → worker completed → 연속 journal/text → canonical history·run 귀속 token ledger 대조 | 활성 text model, completion·models·usage 읽기 권한. Journal/ledger는 서비스 retention에 남으며 실패한 비종료 run은 cancel한다. 실제 provider key 또는 서비스 소유 system stack의 fake provider를 구분하여 보고한다. Media·외부 provider 진위는 자동 증명하지 않는다. |
| Waygate | client 발급·다운로드/config/key/IP → PATCH 설정·key 보존 → passphrase-encrypted export/import → 생성 client 삭제·404·server defaults/network 보존 | `WAYGATE_SMOKE_TOKEN`, `WAYGATE_SMOKE_SERVER_ID`, `WAYGATE_SMOKE_IMPORT_SERVER_ID`. 같은 project의 **서로 다른 ACTIVE·등록된·client가 없는 전용 disposable server 두 개**가 필요하다. VM을 생성하거나 callback/auth를 우회하지 않는다. VM callback·VPN data plane은 별도다. |
| Palimpsest Hub | 실제 SquashFS byte SHA-256 → 다중 offset PATCH → finalize/단일 root 계보 → blob bytes/hash 대조 → 선택 OCI tar 참조·hash 대조 → 소유 upload/catalogue 삭제·404 | 실제 고유 `.sqsh`, 쓰기 가능한 Hub store, project-scoped Keystone token과 system-admin 삭제 권한. 기존/shared digest는 거부하며 무해한 invalid-digest DELETE로 정리 권한을 선확인한다. CAS 물리 byte는 지연 GC 대상이며 GC·다중 계보·bundle import·KVM/OpenStack build/consume는 미검증이다. |

Waygate는 현재 API/worker startup에서도 VM-reachable callback 설정을 요구합니다. Client control 시나리오가 callback을 호출하지 않는다는 사실과 callback 없이 서비스를 시작할 수 있다는 주장은 다릅니다. `--only lumen,palimpsest`와 외부의 이미 실행된 Waygate endpoint 연결은 이 전제를 분리하지만 production guard는 바꾸지 않습니다.

서비스 로직 변경은 이 경로 또는 서비스 소유 system runner로 **변경한 동작을 실제 실행**합니다. 보고에는 API/DB/cache/worker/crypto/blob와 모의 identity/provider/cloud를 따로 적습니다. 필수 자격·model·ready server·artifact가 없으면 검증 공백이며 read-only 성공으로 승격하지 않습니다. 사전 조건 충족 뒤 assertion·정리 실패는 실패로 종료합니다.

### 프로젝트 서비스 등급 검증 기록 (2026-10-07, local-only)

현재 Keystone의 실제 role-ID DAG·유효 할당과 `area_grade` 프리셋을 검증했다. 다음 증거는 서로 대체하지 않는다.

| 경계 | 실행된 결과 | 실제/합성 구분과 한계 |
|---|---|---|
| Afterglow | 실제 HTTP BFF + installed Keystone SDK/current directory 경계 24개; 최종 backend unit **4,112**, 소비자 contract **154** 통과 | Identity/provider directory는 합성 HTTP. 운영 Keystone 인증·역할/DB 변경 아님. 과거 JWT role claim과 DB manager에 기대던 fixture를 현재 catalog/유효 할당으로 바꿨고 hermetic network guard를 유지했다. |
| Chromium | naming·명시적 preset·owner-only 위임, Waygate 소유 profile 원본177bytes/editor 생성/legacy owner assign-once, Drover 명시 `user/editor`312bytes와 회수 뒤 늦은 응답 공개 차단, 별도 관리자 certificate 확인; Image Blob·실제 WAV 재생·Palimpsest secret의 동일 값 장애 복구·확정 회수 폐기 | 브라우저는 실제 Chromium·현재 UI, identity/service/credential은 합성. UI 회귀9files/252tests와 최종 영향 selector5files/71tests를 별도로 실행했다(중복 집계하지 않음). 운영 credential이나 paid model 응답 증거가 아니다. |
| Waygate | API/worker `arm64/amd64` 실행, real MariaDB11.4.12의001–004→005 ledger/record/ciphertext 보존, installed SDK→real Uvicorn current-grade/owner/export/callback 경계; opt-in smoke2통과; full serial/4worker 각각625passed/3skipped, SDK44와 root/SDK Ruff통과 | Keystone만 합성 HTTP; worker queue SELECT8/9개. Gateway VM provisioning·VPN dataplane·운영 schema apply 없음. `../waygate/openspec/changes`의 완료 archive/design과 native `ARCHITECTURE.md`/`CHANGELOG.md`에 receipt를 남겼다. SDK의 기존 service_type deprecation warning44개를 숨기지 않았다. |
| Drover | API/worker `arm64/amd64` build/import, real MariaDB/Redis/k3s1.31.4에서 **119 checks per architecture**, 실제 RBAC/TokenRequest/CEL admission/exec; native regression **1,037 passed/3 skipped** | Keystone은 합성 HTTP. Worker cloud job 실행 아님; 두 cluster row는 같은 disposable k3s를 가리킨다. Default shell image tag/PATH는 정상 qualification이 아니며 disposable override를 구분한다. 이미 발급된 bearer는 expiry까지, 과거 full certificate는 별도 trust remediation 전까지 유효할 수 있다. `../drover/README.md`의 상세 한계를 따른다. |
| Palimpsest | canonical API/worker4build/import, 등록된 native app/SDK/auth/SQL/CAS/real Redis에서 **182 checks per architecture**,11CAS파일 restart/recreate byte/hash 보존; root package regression309통과 | 합성 current Keystone. Smoke-only aiosqlite factory/lifespan-off 사용: canonical SQLite bootstrap의 `connect_timeout` 오류를 보존했다. MySQL startup/TLS/KVM/Glance/운영 배포 qualification 아님. `../palimpsest/docs/project-package-registry.md`와 `build/scoped-package-capabilities-smoke/` receipt를 따른다. |
| Lumen | service **3,005**, SDK128, canonical MariaDB/Redis integration272, Compose system30(권한16시나리오) 통과; real API/online+batch worker/TLS MinIO/ClamAV, native text/image completion·decoded media·현재 owner/key revoke·owned/idempotent cancellation; canonical API/worker4build의5source hashes 일치 | Keystone/provider HTTP는 합성, 유료/운영 provider 증거 아님. 두 worker-denial 케이스는 HTTP-frozen image SQL fixture를 복제 후 downgrade/revoke하여 release했고 두 번째 public admission이 아니다. Fixed Gateway credential에 tools scope를 추가하지 않았다. Native `docs/testing.md`/change tasks가 exact command·최종 image ID·한계를 기록한다. |

`npm run test:gate`는 **전체 통과하지 않았다**. 공유 Git index의 미해결 merge로 architecture gate가 차단됐고, 별도 전체 frontend 실행에는 기존 motion/번역/scanner 테스트 실패, JS 실행에는 Kolla globals mode0600 대0640 실패가 남았다. Backend 전체 lint의 남은 실패는 범위 밖 `tests/test_vm_github_ssh_history.py`의 I001 import 정렬이며, 최종 변경한 fixture10개는 Ruff check/format을 통과했다. 관련 scope의 smoke·unit·contract 통과를 전역 release gate 통과로 바꾸어 보고하지 않는다. 공유 index와 다른 작업의 실패 source는 변경하지 않는다. Root architecture는 HEAD와 명시한 현재 role consumer120파일만 합친 임시 index에서 stamp/check를 통과했다(`source_sha256=007ac694f6decbf6e9b45650044d762eba12552280622dbce2ea28d53c21a0c9`, indexed source2410개). 전체 working tree/실제 index 통과가 아니며, 실제 index SHA-256 `571bd4768270ff93ef4606e9b8c3d46631139097ebe79e994d510d72126bffeb`와 공유 working review block을 보존했다. Gbrain 동기화는 로컬 CLI가 없어 실행하지 못했다.


### Image Studio 권한 상태 표시 복구 (2026-10-08, local-only)

1.30.4의 grant-dependent 실제 Chromium 기록(`evidence/afterglow-grant-ui.json`)은 거부된 `lumen-images_user`가 model fetch를 막는데 composer가 영구 model/options loading으로 표시되는 결함을 확인했다. 1.30.5는 기존 `imagesAllowed`로 해당 status만 감싸며 `LumenPermissionNotice`의 권한 pending/error/required leaf 상태를 재사용한다. 모델 조회, independent asset leaf와 응답 공개·draft/media 보존/회수 동작은 변경하지 않는다.

재빌드한 SvelteKit production frontend·실제 headless Chromium·loopback HTTP fixture에서 **31조건**을 실행했다: 거부와 allowed-ready 각각 light/dark × 390/767/768/1023/1024/1440px(24조건), permission pending/error, 실제 model loading/error/empty, capability error 및 image-allowed/assets-denied(7조건). 거부 상태에는 모델 요청0·잘못된 model status0, 모든 조건의 페이지 overflow0이다. 실제 권한이 부여되면 모델·capability 조회와 ready status 및 prompt 입력 후 enabled submit을 관측했다. Submit/provider 호출은 실행하지 않았다. Error smoke 중 잘못된 HTTP 오류 문구 wait 두 건은 실제 generic model error/permission detail 렌더링으로 수정한 fixture 관측이며 source 실패를 숨기지 않는다.

Served node `/_app/immutable/nodes/72.DpAv0mZL.js`와 build SHA-256은 모두 `7f83799d6430717bf013b339acd9073955e8698270293ced986d8fe277bebf03`; exercised source SHA-256은 `bea2ded4fd648d68f754f1cef7502be6958f9451be9ce3e94cf0cc5e77a04501`이다. Runtime JS 오류/console error0, 예상한503 세 경계 외 API 실패0·mutation0이며 외부 Google Fonts 요청11건 차단을 별도로 남긴다. Receipt·31 PNG는 `/tmp/afterglow-ecosystem-release-20261007.FDut9J/evidence/image-status-1305/`에 보존했다. 합성 identity·service 응답의 UI/API-contract proof이며 실제 인증/인가·유료 provider·published image·운영 cutover acceptance로 대체하지 않는다.

동일 source의 `npm run test:gate`는 backend unit4,126·frontend331files/2,459와 runner9·consumercontract154·disposable MariaDB/PostgreSQL/Redis functional28·Ruff/check 및550files format을 통과했다. Architecture working digest `1165bf7e20771520ccd643da7df7eb3ed8b503891449ffc583315c13c1b8b03f`와 version1.30.5 일치를 확인했다. Svelte check2,333files/0errors·기존 DocCodeBlock tabindex warning1, production build 통과이며 Windows/paid provider/live cloud는 실행하지 않았다. 사후 문서/완료 checklist는 runtime source를 변경하지 않는다.

불변 `v1.30.5` source3941490d의 dev Docker37746138117·tag Docker37746747991·Helm37746747697가 성공한 뒤 **발행 frontend 자체**를 digest `sha256:58d5361d6a6caf56c8d81d6cb5b5860aa03531d57f8bfe5040358dedab8c648a`로 실행했다. 재빌드 source proof와 별도의 실제 Chromium31조건(같은 light/dark6폭·거부/ready와7상태)을 통과했다. 거부modelHTTP0·overflow0·runtimeJSerror0·mutation0이며 public served node `72.DQVyHosE.js`는SHA256 `5ca75c92a1558c308432e3283a22207567df84d321e5ed51f45b895e3121d64e`다. Receipt·31 PNG는 `/tmp/afterglow-ecosystem-release-20261007.FDut9J/evidence/image-status-1305-published/`, OCI/runtime 증거는 `evidence/afterglow-1305-publication.json`이다. Native arm64 호스트의 Docker Desktop에서 declared amd64 frontend를 실행했으며 identity/API는 합성이다; 실제 Keystone/provider/production proof가 아니다. API·worker amd64와 Cloud Shell amd64/arm64는1.30.5·uid1000으로 실행됐다. API HTTP smoke는disposable MariaDB/Redis의health200·권한/역할3경계401까지 관측했다. 기존 harness의 nonexistent internal path→404/잘못된401 기대는 initial receipt에 남기고 machine endpoint 검증으로 세지 않았다. Owned browser/frontend/API-fixture·disposable API/DB/cache와 scratch는 모두 정리했고 공유 stack·운영 상태는 바꾸지 않았다.
### 실패 소유권 (Failure Ownership)

- **단위 / 계약 / 국소 기능 테스트**: 실패 시 작성자/개발자 소유의 확정 게이트 실패(deterministic gate failure)입니다. 원인을 반드시 수정해야 합니다.
- **Service-real / 실제 환경 테스트 (Live OpenStack)**: 필수 자격 증명·엔드포인트·model·ready server·artifact가 없으면 **보고된 검증 공백(reported verification gap)**입니다. 사전조건이 충족된 뒤 발생한 assertion/resource cleanup 실패는 실제 결함으로 처리합니다.

### 검증 진행 순서

개발 루프 및 사전 검증은 다음 순서로 수행합니다:
1. **정확한 경로 (Exact selector)**: 변경한 파일/함수의 direct selector
2. **도메인 타깃 (Named target)**: 관련 도메인 named target (예: `auth`, `layers`, `live:auth`)
3. **교차 관심사 타깃 (Cross-cutting target)**: `npm run test:all` (`unit` + `contract` + `functional`)
4. **커밋/PR 확정 게이트 (Deterministic Commit Gate)**: `npm run test:gate` (`test:all` + `lint:backend`)

---

## 빠른 명령

```bash
npm run test:list
npm run test:target -- auth layers
npm run test:target -- --parallel instances
npm run test:target -- backend:tests/test_instances.py::test_delete_instance
npm run test:target -- frontend:src/lib/config/site.test.ts
npm run test:functional
npm run test:functional -- --no-start
npm run test:functional -- --keep
npm run test:live
npm run test:target -- live:auth
npm run test:gate
```

---

## 일회용 국소 기능테스트 환경 (Functional Lifecycle & Ports)

`npm run test:functional`은 `docker-compose.dev.yml`의 `mariadb`, `postgres`, `test-redis`만 기본 `afterglow-test` project에서 자동 기동합니다. 별도 test manifest는 없습니다. Cloud 자격 증명이나 형제 소스 checkout 없이 실행할 수 있으며 runner는 자동 `.env` 보간을 사용하지 않습니다. 성공·실패 모두에서 이 세 컨테이너만 종료하고 tmpfs 데이터를 폐기합니다. 개발 앱·named volume·orphan을 삭제하지 않습니다. 이 계층은 일반 단위 테스트의 fakeredis fixture를 끄고 실제 Redis 연결을 검증합니다.

- **전용 포트**:
  - MariaDB: `3307` (`mysql+aiomysql://afterglow:dev@127.0.0.1:3307/afterglow_functional`)
  - PostgreSQL: `5434` (`postgresql://afterglow:dev@127.0.0.1:5434/afterglow_checkpoints`)
  - Redis: `6380` (`redis://127.0.0.1:6380/0`)
- **생주기 제어 옵션**:
  - `--no-start`: 이미 실행 중이거나 CI가 제공한 DB/캐시 서비스를 재사용하고 소유권을 가져가지 않습니다. 다른 주소는 `AFTERGLOW_TEST_DATABASE_URL`, `AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL`, `REDIS_URL`로 지정합니다.
  - `--keep`: 자동 기동한 컨테이너를 실행 상태로 유지해 디버깅합니다. 데이터는 tmpfs이므로 컨테이너 중지 시 사라집니다. 정리는 아래의 service-scoped 명령을 사용합니다.

```bash
# 자격 증명 없이 test profile만 수동 실행 (기본 앱을 함께 시작하지 않음)
docker compose --env-file /dev/null -f docker-compose.dev.yml -p afterglow-test --profile test up -d --wait --no-deps mariadb postgres test-redis
npm run test:functional -- --no-start
docker compose --env-file /dev/null -f docker-compose.dev.yml -p afterglow-test --profile test down mariadb postgres test-redis
```

일반 개발 앱은 기존처럼 `npm run services:up`으로 private 설정·키를 검증하고 시작합니다. 테스트 profile만을 위해 비밀값을 채우거나 insecure 모드로 실행하지 않습니다. 명시적인 service 목록 없이 `--profile test up`을 사용하면 기본 앱까지 선택되므로 테스트 단독 실행에는 위 명령 또는 npm runner를 사용합니다.

---

## 타깃 선택표

| 타깃 | 설명 및 사용 시점 |
|---|---|
| `auth` | 로그인/로그아웃, 토큰, 세션, site-config 인증 경로를 건드렸을 때 |
| `access` | 관리자 전용 체크, owner check, IDOR/BOLA, audit prefix, legacy v1 계약을 바꿨을 때 |
| `config` | afterglow.conf/config, K8s 설정 생성, 캐시 설정, 프론트엔드 런타임 config를 바꿨을 때 |
| `crypto` | k3s 암호화 또는 키 파생 로직을 바꿨을 때 |
| `contracts` | 추출 서비스 BFF/SDK/catalog/ingress 소비자 계약을 독립적으로 확인할 때 (`npm run test:contract`) |
| `db` | local functional DB selector. 보통 환경·teardown까지 소유하는 `npm run test:functional`을 사용합니다. |
| `instances` | Nova 인스턴스 API, 생성용 flavor 쿼터·same-host GPU/CPU/RAM capacity/admission, wizard refresh·제출 fence, 메타데이터/메트릭/헬스, 인스턴스 UI를 바꿨을 때 |
| `storage` | Cinder/Manila/Swift 스토리지 API 또는 스토리지 UI를 바꿨을 때 |
| `layers` | admin libraries, squashfs, union layer build/consume 플로우를 바꿨을 때. Dockerfile 편집기의 FROM 해석·lint 상호작용과 후보 표시도 포함합니다. |
| `k3s` | k3s API, cloud-init, 보안, 플러그인, nodegroup 테스트를 건드렸을 때 |
| `workers` | worker runtime, notion worker 템플릿/동작을 바꿨을 때 |
| `design` | 디자인 시스템 규칙, raw visual debt guardrail을 확인할 때 (`npm run test:frontend:design`) |
| `live:{auth,admin,compute,network,storage,layers}` | 실제 OpenStack 자격 증명이 필요한 live 통합 슬라이스를 확인할 때 |

---

## 직접 pytest / Vitest 실행

### 백엔드 직접 pytest 실행

```bash
npm run test:target -- backend:tests/test_instances.py::test_delete_instance
```

백엔드와 프론트엔드 step이 함께 있는 target(`instances`, `auth`, `config` 등)은 `--parallel`을 붙이면 backend lane과 frontend lane을 동시에 실행합니다.

```bash
npm run test:target -- --parallel instances
```

직접 pytest 호출:

```bash
cd backend && AFTERGLOW_ALLOW_INSECURE=1 uv run python -m pytest tests/test_instances.py::test_delete_instance -v
```

### 프론트엔드 직접 Vitest 실행

```bash
npm run test:target -- frontend:src/routes/__tests__/logout-flow.test.ts
```

직접 Vitest 호출:

```bash
cd frontend && npm test -- src/routes/__tests__/logout-flow.test.ts
```

CI의 frontend 잡은 파일 단위 2-way shard로 실행합니다. 샤드는 래퍼가 아니라 vitest를 직접 호출해야 합니다. `npm run test:unit:frontend -- --shard=1/2`는 내부 npm이 인자를 전달하지 않아 전체 스위트를 실행합니다.

```bash
cd frontend && ./node_modules/.bin/vitest run --shard=1/2 --reporter=json --outputFile.json=/tmp/shard-1.json
node ../scripts/ci/verify-vitest-shard.js --report /tmp/shard-1.json --shard 1/2 --root .
```

---

## 에이전트 및 엔드포인트/보안 개발 가이드

1. **엔드포인트 테스트 작성 의무**: 백엔드 엔드포인트를 수정/추가하면 반드시 `backend/tests/` pytest를 함께 작성합니다. 테스트 없는 엔드포인트는 미완료로 간주됩니다.
2. **보안 가이드라인 검증**:
   - 인증/권한, owner check, IDOR guard, admin dependency(`require_admin`)를 건드린 경우 `auth` 또는 `access` 타깃을 반드시 포함합니다.
   - cloud-init 템플릿보간, shell 쿼팅, Pydantic validation 변경 시 관련 단위/기능 테스트를 함께 실행합니다.
3. **커밋 전 확정 게이트**: 커밋 또는 푸시 전 반드시 `npm run test:gate` 명령을 실행하여 `test:all`과 `lint:backend` 통과를 확인합니다.


---

## 2026-10-10 인증·MCP 보안 패치 검증

기준 dev SHA는 `c210f5018ba9928dee6b0def9ed0cd61c7813f5e`이며 최종 source SHA-256은 `1029b79c96c1effef9de9abe4760e8502a8aafbcdc7e1f48fcb9f158e6fdb7ff`이다. 원본과 digest가 같은 `/private/tmp` 격리 clone에서 private `afterglow.conf` 없이 Node 24.14.1·기존 lock/dependency로 `npm run test:gate`를 실행했고 exit 0이었다.

| 최종 gate 계층 | 결과 |
|---|---|
| Backend unit | 4,458 passed |
| Frontend Vitest | 334 files / 2,577 passed |
| Backend contracts | 154 passed |
| 실제 datastore functional | 43 passed / 9 deselected |
| Backend Ruff check / format | 성공 / 565 files already formatted |
| Frontend type check / production build | exit 0 / exit 0, 기존 접근성 warning 1건 |
| Architecture working snapshot | 원본·검증 clone digest 일치, 성공 |

기능테스트는 `docker-compose.dev.yml`의 일회용 test-profile MariaDB/PostgreSQL/Redis를 loopback 전용 포트에서 사용했다. 실제 Redis Lua 동시 회전은 한 요청만 성공하고 만료 후 반복 요청은 거부됐으며, stale owner release가 새 slot owner를 삭제하지 않음을 별도로 확인했다. 실제 MariaDB 회귀에는 OAuth refresh client binding, mutation poll/cleanup의 unknown 영속화, 새 key 중복 차단 및 동시 claim이 포함된다.

MCP SDK/HTTP 경계와 browser runtime은 실제 loopback transport/Chromium을 사용하되 identity/cloud 응답은 synthetic이었다. 브라우저 확인에는 hydration, nonce 없는 inline script 차단, sessionStorage 자격 보관, 새 탭 독립 인증 및 cross-tab logout이 포함된다. 최종 queued logout 순서와 origin 누락/invalid mode는 실제 auth 모듈 및 backend selector로 독립 재검증했고 리뷰 승인을 받았다. 실제 Keystone/cloud 작업이나 운영 배포는 이 증거에 포함되지 않는다.

중간 gate에서 test fixture·검증 설정 문제가 발견되어 수정했고, 전체 frontend 실행 중 카탈로그 scan 1건은 5초 timeout이었다. 동일 selector 4건과 최종 전체 gate는 통과했다. Documents의 검증 복사본에는 예상치 못한 중복 파일이 생겨 사용을 중단하고 새 `/private/tmp` clone의 동일 digest로 검증을 완료했다. 이전 실패 실행을 성공으로 취급하지 않는다.
