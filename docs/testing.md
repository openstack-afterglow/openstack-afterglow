---
title: 국소 기능테스트 가이드
lang: ko
nav_order: 8
---

# 국소 기능테스트 가이드

## 1.30.27 release 검증 진행 (2026-10-26)

- 요청 시점 완료 source와 승인한 실제 release blocker 수정만 격리한다. 이후 동시 작업의 project-cleanup/navigation 미완료 변경과 private 설정은 release에 섞거나 덮어쓰지 않는다.
- Forecast raw native collection completeness는 focused46passed 및 실제 Uvicorn HTTP/설치 SDK→loopback Keystone으로 complete ready와 truncated unavailable/null·usage 조회0을 확인했다. Original directory 경계와 유효 display metadata를 재구성하면 subset 사용을 시도해 regression이 실패한다. Native 운영 LIST metadata도 읽기만으로 확인했다. Principal/Nova/quota는 합성이며 live forecast 정확도 증거가 아니다.
- 최초 source25b2a51b/3512files gate는 backend99%에서 도구900초 제한으로 중단됐고 scanner selector 한 건만 결과가 없었다. 별도 real asyncio/fakeredis 재현은 내부 `asyncio.timeout(0)`의 일시적 cancellation count 때문에 shutdown이 자기 취소를 생략하는 hang과 cleanup 진입 전 pending 취소 유실을 증명했다. Scanner에 독립 취소를 요청하고 실제 HTTP/SDK·exact target/output/claim drain을 보존하는 수정 뒤 재현은 종료했다. 원래 gate의 stack은 확보하지 못했으므로 동일 원인으로 단정하지 않는다.
- Source-only independent native review는 Palimpsest optional blob identity와 descendant base completeness 두 실제 결함을 발견했고 담당 qualification에서 수정/회귀를 검증한다. Lumen 새028은 immutable 두027 receipt를 보존하고 exact schema/material/policy/ledger drift를 DDL 전 거부하도록 별도 검토했다. 운영 전환은 user의 명시 확장 승인 아래 cold backup/restore·정식 release가 선행한다.
- 운영은 현재 Afterglow1.30.26/Lumen0.6.9/Palimpsest0.3.7을 유지했다. SQL/config/census의 보호된 hot capture와 network-none/tmpfs MariaDB10.11.19 복원은 Afterglow103tables/5130rows·Lumen66/6602·Palimpsest15/15로 성공했으나 cold 상태/운영 migration proof가 아니다. Exact native OIDC tuple을 read-only로 확인했고 source opt-in 후보는 나머지 설정 및 명시3600초 timeout을 보존한다. Active config/overlay·native mapping/IAM은 아직 바꾸지 않았다.
- **최종 Afterglow source gate:** `b8f3e1df5140c7af713b2861ec1aad0283e124e05e3f7d25a287ae6ef3e7422a`/3512files의 `UV_NO_SYNC=1 npm run test:gate` 전체가 성공했다: backend9959passed/95skip, frontend454files/5367passed, contracts183, disposable DB167passed/33deselected, Ruff746files. Worker/dispatcher focused77passed이며 frontend check0errors/16warnings다. 이후 추가 WIP는 이 검증에 포함하지 않는다. CI/tag/운영 결과는 아직 별도 대기다.

## Domain manager workspace (2026-10-26, source only)

- **요청/구현:** 현재 도메인에서만 멤버 내보내기(계정 삭제 아님), manager 직접 프로젝트 생성, 이메일 후 다중 project/role 선택·일괄 초대, 도메인 monitoring/forecast/allocation 통합을 구현했다. 기존 user/index/private config·운영 datastore·실제 cloud IAM은 변경하지 않았다. 새 source는 구형 invitation reader cohort와 coordinated cutover가 필요하며 운영 snapshot의 mixed-writer qualification은 수행하지 않았다.
- **발견·수정:** 생성 backend는 이미 manager를 creator 없이 허용했으며 UI 진입점이 없었다. Monitoring은 context revalidation 중 첫 mount에서 blocked 조회가 빠지면 계속 loading이었다. 통합 뒤 세 요청을 독립적으로 시작한다. Review에서 Keystone null subtree leaf·project LIST truncation·eviction authority403 teardown을 발견해 수정했다. Eviction은 complete metadata의 user/group-scoped source와 exact project read로 비활성/목록 누락 grant까지 검사한다. 기존 fresh manager authority의 전체 graph 검증은 완화하지 않았다.
- **실제 HTTP/native SDK:** 설치 keystoneclient/openstacksdk → 합성 loopback Keystone/Nova → 실제 Uvicorn의21 HTTP 시나리오와8 forecast adapter 경계를 실행했다. 계정/foreign grant/resource sentinel 보존, self/home/owner/protected/revoked manager/shared group 차단, partial/미확정 readback503, null inherited leaf·disabled local grant 회수, native list truncation의 쓰기0을 확인했다. 생성은 실제 disabled staging·unique owner readback·SQLite completed journal을 확인했고 quota apply는 합성 callback이었다. Forecast는 실제 wire의 compute2.39·exact start/end와 empty/거부/잘못된 project/window/row를 검증했다. Graph lease transport는 fakeredis, authenticated principal/native cloud는 합성이며 운영 acceptance가 아니다. 별도 실제 Uvicorn/SQLite invitation7시나리오에서는 단일 이메일·2UUID+Default 확정 grant, legacy row 수락, foreign/disabled/revoked role/issuer 쓰기0, 두 번째 grant 응답 유실 뒤 recovery_required/unknown·재수락410·자동 보상/재전송0을 확인했다. 이 invitation proof의 SMTP/native adapter는 합성이며 SDK proof와 구분한다.
- **실제 UI:** 현재 Vite-compiled Svelte console/controller/client/primitives에서 foreign account eviction confirmation→DELETE1, creator preset 없는 manager create→POST1→목록 재선택, 이메일 뒤2project/각 role 선택→단일 invitation POST1을 실행했다. 계정/API는 외부 fixture이며 실제 메일/운영 IAM은 호출하지 않았다. Users·create modal·invite modal·monitoring 각각9locale×2theme×6viewport(390/767/768/1023/1024/1440),432조건 및 최종 재가입 안내 confirmation108조건(총540)에서 페이지 가로 overflow0과 모달/최종 action 경계를 확인했다. Creation은 CSS zoom200%에서도 overflow0이었다. Monitoring inventory disclosure·30일 forecast/budget을 확인했고 budget503 중 resource/forecast/current manager 화면 유지도 실제 실행했다.
- **국소 회귀:** eviction/monitoring/quota/shared forecast backend98passed·frontend3files20passed, invitation/current lifecycle backend121passed·frontend3files37passed, project creation backend11cases와 인접 frontend4files75passed, 후속 eviction authority/replay를 포함한 DomainIam32passed를 확인했다. 초기 history foreign-domain 누락 및 forecast malformed fixture2건은 실패 기록을 보존하고 실제 contract 수정 뒤 통과했다. 신규 owned Python15files Ruff check/format, i18n0errors·37 unrelated key-order warnings, hard-coded Korean scan0, Impeccable detector[]였다. 더 넓은 frozen-source gate는 최종 receipt와 구분한다.
- **증거:** `~/.local/share/afterglow-proofs/domain-manager-workspace-20261026/`의 native HTTP results/requests/recipe, browser-actions·responsive JSON·screenshots 및 frozen public snapshot/check logs. Snapshot의 임시 index만 architecture stamp/staged guard에 사용하며 실제 공유 index·원래 review marker는 보존한다. 이 기록은 source 로컬 검증이며 배포·실제 cloud 삭제/초대/SMTP·운영 리소스 예측 정확도 증거가 아니다.
- **사용자 확인:** 내보내기는 잘못 연결된 외부-home 계정의 현재 권한 정리만 수행한다. SSO auto-join 규칙과 pending invitation은 유지하고 재로그인/기존 초대 수락으로 재가입할 수 있음을 확인창·도움말·API/user guide에 명시했다. Durable ban·초대 일괄 취소·계정 relink/merge는 사용자 선택상 범위 밖이다.
- **검증 중 복구:** 첫 격리 snapshot은 backend Access1694/전체9935passed였으나 frontend generated SvelteKit tsconfig 선행 생성이 없어 dependency optimizer가 실패했다. Harness에 정식 frontend prepare를 추가했고, 발견된 신규 Forecast snippet nullable narrowing 및 test ByRoleOptions 타입 오류2개도 source에서 수정했다. 두 번째 snapshot의 정본 gate·Access·frontend check·임시 staged guard가 모두 통과했다. 이후 사용자 readmission 안내를 추가한 최종 snapshot 검증은 별도 receipt에 기록한다. 실패를 기존 성공으로 덮어쓰지 않았다.
- **최종 frozen gate:** `verification-1793012529833142000/`의 prepared public snapshot `552b83f84b4fae733fa769c9e574de8c6daa8df274c1f41ac3d93bf4aae2b700`/3507source files에서 Access backend1694·frontend27files374passed, 정본 `npm run test:gate` backend9935passed/95skip·frontend454files5367passed·contracts183·disposable DB functional167passed/33deselected·Ruff746files가 통과했다. Frontend check는0errors/16 기존 warnings, 임시 staged architecture guard도 같은 digest로 통과했다. 마지막 parity에서 application source는 모두 동일하고 동시 세션의 `CLAUDE.md`만 capture 이후 바뀌어 보존했다. 따라서 해당 frozen source 검증이지 동시 context 변경을 포함한 새 shared digest의 검증으로 주장하지 않는다. 실제 공유 index·private config·running services는 보존했으며 owned browser/Vite runtime을 종료했다.
- **후속 접근성/target 보완:** 다중 초대의 각 role fieldset legend에 project 이름·전체 ID를 추가해 같은 project_reader 선택을 스크린리더가 프로젝트별로 구분한다. 실제 Chromium의390/768/1440px에서 두 named group·overflow0·단일2project POST를 다시 실행했다. IamProjects/IamInvitationProjects 두 파일을 Access target에도 등록했고 exact12cases와 target registry 검증을 통과했다. 이 두 source 변경은 위552b83f8 receipt 이후이므로 후속 frozen gate receipt를 별도로 유지한다.
- **후속 최종 gate:** `verification-1793012999271543000/`의 source `67f0c499046b79c34e8032b59f110e5964b36c80e46b2de5e3b135dc8cb7efc5`/3507files에서 Access1694backend·29frontendfiles386cases, 정본 gate9935backend/95skip·454frontendfiles5367cases·183contracts·167DB/33deselect·746Ruff와 frontend check0errors/16warnings·임시 staged guard가 모두 통과했다. 마지막 application source parity는 동일하며 concurrent CLAUDE.md만 snapshot 이후 변경되어 그대로 보존했다. 모든 이전 digest receipt는 해당 snapshot에만 한정한다.
- **Release review 후속 회귀(실행 전):** `test_domain_quota_monitoring.py`에 설치 openstacksdk→loopback Keystone TCP→실제 forecast API aggregate 회귀를 추가했다. HTTP200 `truncated:true`를 SDK iterator가 누락하는 subset과 complete/disabled-project 집합을 비교하고, 원본 collection의 missing/malformed links·continuation·truncated/limited·중복/foreign ID·native403에서 전체 합계/추세가 차단되는지 정의한다. Nova history/quota와 manager principal은 기존 합성 fixture다. 이 추가분의 failing-before/수정 후·Access/정본 gate 결과는 Main의 후속 실행 증거가 필요하며 기존 frozen receipt에 포함됐다고 주장하지 않는다.

## 현재 공개 변경사항 로컬 커밋 검증 (2026-10-26)

- **범위:** 사용자가 현재까지의 변경사항 커밋을 승인했다. 기존 native OIDC/IAM·관리자 상세/그룹/스토리지/볼륨 이전·Palimpsest·Lumen UI·dashboard/session·HTTP transport와 관련 문서/테스트를 현재 local `dev` checkpoint로 보존한다. 새 기능·버전 변경·push·release·운영 배포 승인이 아니며 미완료 `connect-palimpsest-asset-dashboard` checklist는 완료 처리하지 않는다.
- **정본 gate:** private 설정 없는 격리 snapshot에서 `UV_NO_SYNC=1 npm run test:gate` 단일 명령이 성공했다. Backend9882passed/95skip, frontend450files/5334passed, contracts183passed, disposable MariaDB/PostgreSQL/Redis functional167passed/33deselected, Ruff742files check/format 통과다. Disposable test services는 정리했고 운영 datastore에는 접근하지 않았다.
- **source binding:** 실제 checkout과 격리 snapshot의 source digest는 `63dd84fc9ec933ff3f84d52e4cd21e5bd3b6f5c4f9978deab5e4bcedfd324673`/3503files로 일치한다. 최초 snapshot의3504번째 항목은 clone에만 추가한 root `node_modules` dependency symlink였으며 clone-local exclude에만 추가하고 같은 application source로 정본 gate를 다시 통과했다. Shared architecture review도 현재 source로 stamp하며 commit 전 staged guard로 확인한다.
- **리뷰/비밀:** backend와 frontend/deploy의 독립 read-only review에서 commit blocker를 찾지 않았다. Gitleaks는 pending diff/new public files2.32MB에서 credential-management 일반 문장 한 건만 탐지했고 실제 credential 값이 아닌 false positive임을 원문으로 확인했다. 기존 private/ignored 파일과 runtime·IAM·키는 커밋 범위에 넣지 않는다.
- **증거/한계:** 마지막 gate output은 `artifact://105`, scratch proof는 `/var/folders/1m/xfc726k14szbjnrlq5t68zjw0000gn/T/afterglow-commit-goimuvu0/`다. 이 검증은 현재 source integration이며 기존 기능별 실제/synthetic acceptance 경계·운영 호환성/성능 미검증을 대체하지 않는다. 기존 두 test 파일의 EOF 추가 blank-line 경고는 이 checkpoint에서 변경하지 않았다.

## Accounts 그룹 후보 N+1 제거 (2026-10-26, source 한정)

- **원인/변경:** 명시 source-home 후보가 LIST 뒤 모든 사용자에 exact GET을 순차 수행했다. 이제 exact enabled group/두 domain proof 뒤 native LIST의 unique ID·정확한 home·엄격한 enabled boolean·name/email 형식을 검증해 활성 후보를 직접 구성한다. 기본 home/joined directory, source no-store/ABA와 graph-locked fresh system-admin/user/home admission은 바꾸지 않는다. LIST/provider/metadata 오류는 빈 목록·부분 성공으로 바꾸지 않는다.
- **실제 before/after:** 설치 keystoneclient/openstacksdk·Uvicorn·native loopback TCP의 Accounts500명에서 전체 native GET507→7, 후보 user GET500→0, LIST1→1, 응답1828.42→14.68ms였다. 합성 upstream의 user GET마다2ms 지연을 준 단일 순차 비교이며 운영 cloud latency 수치가 아니다. 응답500개 전체 UUID/정렬/no-store는 같고 조회의 native 쓰기는0이다.
- **fresh admission/오류:** 조회 후 삭제404·비활성403·home 변경403·provider403/503·ID 대체503, 다른 domain grant403·비관리자403을 실제 HTTP로 검증했다. LIST403/503·다른 home/중복 ID/불명 enabled/email503은 전체 요청 실패다. 정상 명시 admission204는 합성 native PUT1회만 실행했고 실제 cloud/IAM mutation은0이다.
- **회귀/증거:** 501명 후보의 GET N+1 regression은 수정 전501번 재조회로 실패하고 수정 후 통과했다. 현재 source의 관련 backend3files176passed·owned Python Ruff check/format 통과이며 `~/.local/share/afterglow-proofs/group-candidate-scale-20261026/`에 before/after와 재현 recipe를 보존한다. Frontend/API response/schema/config/dependency/runtime/운영 배포 변경은 없다. 넓은 Access·정본 gate 결과는 완료 receipt에 별도로 기록한다.
- **최종 격리 검증:** 기존 검증 source `e416c676…`와 이 follow-up의 route/test만 통합한 `ded94deb0490a35a6236bc0c3d561b01bedc92d43806d251c96d538c095db11c`/3500files에서 Access backend1641·frontend24files349passed, 정본 `npm run test:gate` backend9854passed/95skip·frontend450files5334passed·contracts183·실제 DB functional167passed/33deselected·Ruff739files가 통과했다. 변경한 두 source/test는 공유 checkout과 byte-identical이다. 다른 세션의 후속 source를 덮어쓰거나 이 snapshot으로 전체 공유 checkout을 검증했다고 주장하지 않는다.
- **공유 실행 한계:** 공유 checkout Access는 assertion1641passed 뒤 RBAC6case teardown에서 non-loopback Keystone DNS를 network guard가 차단해 전체 명령은 실패했다. 외부 service 호출을 막는 guard/테스트를 완화하거나 private 설정을 변경하지 않았다. 원인은 이 작업에서 확정하지 않았으며 격리 Access/gate 성공으로 소급 성공 처리하지 않는다. 두 실행의 전체 로그를 보존한다.

## Native HTTP socket pool 재사용 (2026-10-26, source 한정)

- **소유권:** native Keystone·SDK·MCP·background inventory의 HTTP adapter/socket pool만 process-local로 재사용한다. Session/auth plugin·cookie/header·catalog/discovery와 native 권위 proof는 작업별로 분리한다. 기존 Requests TLS/CA/client-certificate/proxy pool key·Keystoneauth keepalive·timeout/retry를 보존한다.
- **실행 전후:** 설치 Keystoneauth5.13.1의 합성 loopback HTTP에서 서로 다른 Session/auth plugin을 두 번 만들고 각각 닫은 뒤 비교했다. 기존 authPOST2/resourceGET2/TCP2 → 새 authPOST2/resourceGET2/TCP1이다. 별도 실제 SDK factory→Drover proxy smoke도 Alice/project-a와 Bob/project-b의 정확한 서로 다른 token·cookie 미공유·authPOST2/TCP1과 shutdown socket EOF를 확인했다. 인증/권한 검사를 줄인 결과나 운영 latency 측정은 아니다.
- **실제 수명:** native TCP socket을 연 채 독립 Notion worker main을 취소했을 때 child drain 전 socket 유지와 cleanup 뒤 EOF를 관측했다. 실제 AnyIO MCP manager start→API shutdown을 같은 task에서 두 번 수행해 task-scope 정상 종료를 확인했다. DB/외부 owner cleanup과 provider 내용은 합성이다.
- **cleanup 세부:** 설치 urllib3의 `PoolManager.clear()`는 retained consumed Response가 가진 pool reference까지 즉시 닫지 않는다. Drain 뒤 각 idle pool을 명시 close하며 retained Response·API shutdown 회귀로 EOF를 검증한다. Library 기본 pool 제한을 유지하고 mutation replay를 추가하지 않는다.
- **Architecture/style:** public source3504files·`8dcf9faf93b9551124605702a7f7052577806e7a5374a5c4305d9b4ad3fcb096`의 격리 snapshot에서 working stamp/staged guard, task-owned Python14files Ruff check/format을 통과했다. Task-owned source15files는 이 snapshot과 byte-identical이다. Shared index/global review marker·기존 WIP·private 설정·운영 DB/IAM/서비스는 보존했다. 검토 범위는 transport 소유권이며 captured unrelated WIP를 개별 검토했다고 주장하지 않는다.
- **회귀:** transport/auth/SDK/MCP exact202passed와 inventory/Notion/worker exact50passed다. 새13조건은 실제 HTTP/TLS·쿠키/토큰/프로젝트 격리·동시 요청·fresh 권위 회수·오류401/403/503·응답 유실 POST1회·retained Response pool 종료를 검증한다. 최초 gate의9871pass/95skip/4fail은 기존 inventory/worker mock이 raw SDK factory를 patch하던 경계였으며 새 native factory seam으로 이관하고 의미 assertion은 유지했다. Shared-checkout exact 실행은 worker coordination test 도중 도구의300초 wall-clock deadline으로 종료된 미완료 실행이다. 그 전까지 test failure는 관측하지 않았으며 worker 결함·private 설정·실행 지연 원인은 입증하지 않았다. 이후 격리 qualification 성공과 구분하며 상세 결과는 해당 OpenSpec `verification.json`에 기록한다.
- **넓은 검증:** named backend auth1145·access1638·workers140·MCP532passed/125DB deselected다. 초기 frontend startup의 missing generated tsconfig는 snapshot에서 기존 `svelte-kit sync`로 준비했다. 이후 **동일 frozen source의 정본 `UV_NO_SYNC=1 npm run test:gate` 전체가 성공**했다: backend9875passed/95skip, frontend450files/5334Vitest·Node log runner9passed, contracts183, canonical disposable MariaDB/PostgreSQL/Redis functional167passed/33deselected와 전체 backend Ruff742files. 이전 startup 실패·별도 lane 결과와 마지막 단일 명령 성공은 `verification.json`에서 구분한다.
- **미실행:** 실제 cloud p50/p95·운영 인증/권한 수용·배포·commit/push는 수행하지 않았다. gbrain detect 실행 파일 부재로 code index sync와 agent guidance 수정도 수행하지 않았다.
- **남은 검증 경계:** library 기본10endpoint pool/각 pool10idle connection의 재사용률은 전체 운영 service catalog·실제 동시성에서 측정하지 않았다. 초과 동시 연결은 차단하지 않지만 재사용률이 낮아질 수 있다. Architecture stamp/gate는 격리 snapshot에 한정되며 보존한 공유 checkout global review block의 freshness나 그 checkout의 `docs:check` 성공을 주장하지 않는다.

## 관리자 볼륨 목적지 인증·401 재전송 차단 (2026-10-26, source 한정)

- **운영 원인 확인:** SSH read-only로 `/etc/kolla/plugins/openstack-afterglow-v1.30.26/backend/app/api/identity/admin.py:2572-2612`를 읽었다. 고정 service-project session의 같은 endpoint/token으로 create/accept를 호출하고 target은 `X-Project-Id`에만 넣으며 실제 이전 후 owner를 확인하지 않는 기존 코드다. 보고된 볼륨은 재현·복구 목적으로 변경하지 않았다. Current dev의 미배포 `admin_destination`은 verified unscoped `session_token`에서 exact human/home/target-project/domain 자격을 자동 발급하고, `accept_on_connection`은 실제 Cinder owner/status/attachments를 확인하므로 이 source와 운영 코드는 다르다.
- **추가 결함·수정:** 실제 installed SDK→loopback Keystone/Cinder의 create401·accept401에서 각각 native POST2회를 관측했다(수정 전 9pass/2fail). `connect_retries=0/status_code_retries=0`과 별개인 Keystoneauth `allow_reauth=False`를 두 transfer wrapper에 적용하여 재인증·POST replay를 차단했다. 프로젝트 역할 자동 부여·서비스 credential fallback·암묵적인 재수락은 없다.
- **회귀:** `test_admin_volume_transfer_native_http.py`, `test_admin_volume_transfer.py`, `test_volume_transfer.py` exact104passed. 실제 SDK/native HTTP11조건은 cross-domain target token, scoped-root 혼동 방지, 잘못 발급된 user/home/project/domain, native401/403/quota413와 service-project owner로 완료된 응답의502를 검증한다. Storage target에 관리자 회귀 두 파일을 등록했으며 backend959/frontend177passed, task-owned Ruff check/format이 통과했다.
- **공유 checkout access target:** backend assertion1638개는 통과했으나 기존 RBAC6개가 private config의 실제 Keystone hostname을 조회하려 하여 non-loopback network guard teardown error로 중단됐다. 이 target 전체를 성공으로 보고하지 않으며 cloud 접근을 허용하거나 private 설정·다른 RBAC source를 바꾸지 않았다. Private 설정이 없는 격리 public snapshot의 전체 gate 결과는 별도로 기록한다.
- **실행 smoke:** 별도 Uvicorn TCP→installed SDK→loopback native provider에서 create201, scope403, Cinder403, accept200, validation422, ambiguous502, exact-volume recovery200과 POST no-replay를 확인했다. Human authority/SQL ledger/native provider 내용은 합성이고 실제 cloud mutation은0이다. Source/API 계약만 검증하며 운영 로그인·실제 target role coverage·실볼륨 이전/복구·배포 acceptance가 아니다.
- **격리 architecture/full gate:** private 설정을 제외한 public snapshot3503source files의 공식 working stamp/staged guard가 `6fedd4444ac96210c4828704110890901f8aa653a9433534e33bac94003e71bb`로 통과했다. `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate`는 backend9871passed/95skip/4fail에서 중단됐다. 세 failure는 변경하지 않은 native inventory/Notion test connection의 누락 `config`, 한 failure는 Notion worker inventory-thread timeout이다. Transfer exact104개는 이 전체 backend run에서도 통과했다. 전체 gate 성공으로 재분류하지 않으며 commit/push·배포를 하지 않았다. Snapshot은 동시 public WIP를 포함하지만 이번 review 범위는 transfer뿐이고 공유 index/global review marker는 보존했다.
- **중단 뒤 나머지 계층:** 같은 frozen source에서 frontend450files/5334tests와 log-runner9개, contracts183개, 실제 disposable MariaDB/PostgreSQL/Redis functional167passed/33deselected, backend Ruff742files가 각각 통과했다. 관리자 transfer modal/client exact20개와 target orchestrator10개도 통과했다. 이 별도 계층 성공은 위 backend4fail 또는 전체 gate 실패를 상쇄하지 않는다. Functional runner가 task-owned container3개와 network를 정상 제거했다.
- **경계:** UI/API shape·DB schema·설정·IAM·기존 Compose/운영 container 및 보고된 실제 volume owner는 변경하지 않았다. Source 증거는 `openspec/changes/archive/2026-10-26-enforce-volume-transfer-authentication/`와 `~/.local/share/afterglow-proofs/transfer-auth-20261026/`에 기록한다. Local gbrain CLI는 없어 code-index sync는 실행하지 못했다.
- **후속 redirect 보정:** 위401 검증은307/308 redirect 경로를 증명하지 않았다. Installed Keystoneauth가 동일 POST/body/header를 별도 origin의 `Location`으로 보내는 것을 native SDK의 create/accept×307/308 네 조건에서 각각 sink POST1(accept auth key·native token 포함)로 재현했다. 두 wrapper에 `redirect=False`를 추가한 뒤 exact108passed와 sink POST0, 응답502, 원래 owner/pending 보존을 확인했다. 앞서 전체 gate 실패를 소급 성공으로 바꾸지 않으며 후속 최종 source 검증은 별도 `prevent-volume-transfer-redirect-replay` evidence를 따른다.
- **후속 최종 검증:** create/accept×307/308을 실제 Uvicorn TCP→installed SDK→별도 loopback origin sink로 실행하여 원래POST1·sinkPOST0·native token/key 전달0·source/pending 보존과 정상 accept200을 확인했다. 최신 captured public snapshot3503source files(`3d1151ea9e0443720d9eeed6e6235116c3b509de8cdc1947f459023598d9d628`)의 working stamp/staged guard 및 **단일 `UV_NO_SYNC=1 VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate`가 성공**했다: backend9879passed/95skip, frontend450files/5334tests·log-runner9, contracts183, disposable real-datastore functional167passed/33deselected, Ruff742files. Named storage963backend/177frontend와 exact108도 통과했다. 이전 snapshot의 실패 기록은 유지하며 동시 inventory/Notion 수정은 이 transfer 작업에서 작성하지 않았다. 최종 증거는 `openspec/changes/archive/2026-10-26-prevent-volume-transfer-redirect-replay/verification.json`이며 shared index/review marker·운영 runtime/IAM·실제 volume은 그대로다.

## Lumen 프로바이더·다중 키 pool·모델 등록 창 (2026-10-26, source 한정)

- **현재 runtime 원인:** 실행 중인 local Lumen0.6.9 모듈을 read-only로 확인했으며 provider DTO에 selection_policy가 없고 account/probe route도 없었다. 새 UI는 이를 single-key 교체로 숨기지 않고 pool 미지원과 blocked write를 표시한다. Unpublished native account027은 non-additive이며 published Kubernetes027과 충돌하고 repaired shared schema도 별도 reconciliation이 필요하다. 이 작업은 SQL/checksum·private config·공유 image·DB·운영 migration을 변경하지 않았다.
- **UI 기능:** `/admin/chat` 기본 entry/header/navigation은 프로바이더 설정이다. 실제 source-compiled page/controller/client에서 기존 Key A를 보존하며 Key B POST1회, explicit policy/key 지정, 정확한 key 연결 검사, 현재 endpoint와 기록된 과거 endpoint 분리·older page·unknown 과거 receipt를 확인했다. 미지원 native에서는 정책 저장·계정 추가가 비활성이다. 모델 기본 화면에는 생성 form이 없고 명시 추가 후 한 dialog에서 provider·discovery/manual 선택과 선택 항목별 이름/종류/가격을 등록한다. Manual provider1/name·input1.25/output5/cache0과 discovered provider2/선택1개·수정 ID/input2/output8/active를 실제 client 요청과 UI 결과로 확인했으며 미선택 후보는 등록되지 않았다. 결과 불명인 쓰기의 close/reopen은 POST1회만 유지하고 재제출을 막았다.
- **실제 native/새 Go:** canonical native Dockerfile의 API/worker/test와 pinned converter를 linux/arm64·amd64로 빌드·실행했다. 별도 canonical Compose one-off/network none 안의 Uvicorn·SQLite·새 Go child→실제 loopback upstream→Python settlement/allocation→native history는 양 architecture에서 정확한 두 키로 send2회·history200·과거 endpoint 보존·spoofed header 무시·old receipt null·cursor·member403·ownership404·stale probe409/no extra send를 통과했다. Identity/upstream 내용은 합성이며 실제 cloud/vendor 수용이나 운영 배포가 아니다. API/worker 자체의 platform/version 명령도 실행했고 full worker/cloud lifecycle은 이 smoke가 증명하지 않는다.
- **회귀:** native pool/probe/relay/direct/audio/image/search/realtime9files233passed, completion/title/memory/compaction/run7files322passed, actual Go `go test ./...` 통과. Direct media serializer/handshake의 일부 경계는 MockTransport/FakeWebSocket이며 실제 Go/TCP 증거와 구분한다. Frontend model/cache/media/catalog/pool/nav7files157passed, BFF58contracts와 named Lumen target이 통과했다. Scope/generation/secret/device/price 불변식을 유지했고 mock 구현 잔존·미전환 dialog opener와 typed select/busy 선언 오류를 수정했다.
- **반응형/locale:** manual creation·discovered-item review·pool/history 세 상태×nine locale×dark/light×390/767/768/820/1023/1024/1440의378조건에서 overflow0·single modal·frame/footer/body bounds와 current/recorded endpoint 구분을 확인했다. Swahili long badge nowrap와 global10px scrollbar가 드러낸 overflow를 실제 렌더에서 수정했다. 최신locale0errors/37기존 ordering warnings·scan0/1216files, Svelte0errors/16기존 warnings, Impeccable detector[]다. 200% zoom·production surface의 실제 human/native acceptance는 별도이며 image health는 UI 시나리오 증거가 아니다.
- **증거:** `~/.local/share/afterglow-proofs/lumen-provider-model-workflows-20261026/`에 native actual-binary recipe/양 architecture receipt, compiled pool/model behavior·378조건·desktop/mobile 화면·현재 runtime capability와 canonical Compose override를 보존한다. 새 native source는 `/Users/pieroot/code/lumen-admin-fixes`의 local dev이며 원래 `/Users/pieroot/code/lumen` checkout은 그대로다. Commit/push/release/shared-service replacement·유료 요청·계정/키/운영 데이터 변경은 없다.
- **Image/runtime·gate 경계:** Afterglow frontend도 정본 Dockerfile target을 양 architecture로 실제 빌드하고 private mount 없는 별도 정본 Compose에서 healthy, `/health`200·`/login`200과 Node arm64/x64 실행을 확인했다. 이는 source-compiled authenticated UI fixture와 별개인 built-server smoke다. Groups의 current backend image도 양 architecture에서 실제 SDK/TCP의 후보200·명시 추가204·오류/권위 경계를 실행했고 native cloud mutation0이다. 최초 통합 gate는 source353191b/3500files에서 backend9850passed/95skip·기존 native supervisor SIGINT timeout1건으로 중단됐으며 해당 supervisor는 변경하지 않았다. 이후 exact selector2passed는 확인했지만 그 간헐 실패를 수정했다고 주장하지 않는다. 별도 native full contract는4024passed/384deselected·4failed/12errors로 중단됐고 Git/uv/example-file 컨테이너 tooling 미비와 기존 expired-approval graph failure를 기록했다. Task native233+322/Go/실제 양 architecture smoke를 native 전체 gate 성공으로 바꾸어 보고하지 않는다.
- **최종 정본 통합 gate:** native supervisor/production code를 바꾸거나 해당 회귀를 제외하지 않은 clean 실행은 source `e416c676c9dfa65190da0474841a1f2d96b73828d6963ad2b5f52b3b4ae19bd6`/3500files에서 backend9851passed/95skip, frontend450files5334passed, contracts183, real MariaDB/PostgreSQL/Redis functional167passed/33deselected, Ruff739files로 통과했다. Native SDK143passed·SDK Ruff도 별도로 통과했다. Working/staged architecture guard는 격리 snapshot에서만 수행하고 공유 marker/index를 보존한다. 이 Afterglow gate는 native full-contract 실패나 migration/release 선행 조건을 해소한 증거가 아니다.
- **동시 변경 보존:** 위 결과는 격리한 `e416c676…` snapshot에 한정한다. 최종 비교에서 Lumen·cross-home Groups 구현은 일치했으며, freeze 뒤 추가된 다른 세션의 OpenStack/auth/Notion/test-target 변경은 덮어쓰거나 이 gate로 검증했다고 주장하지 않는다. 공유 checkout의 global review marker freshness와 `docs:check` 성공도 주장하지 않는다.

## 별도 GitLab OIDC 그룹 진단 (2026-10-26, local/synthetic)

- **범위:** `scripts/oidc_group_probe.py`의 독립 loopback 콜백이며 Afterglow/Keystone 로그인·설정·schema·native IAM 변경이 아니다. 새 진단 client의 등록/실제 사용자 로그인은 아직 수행하지 않았다. [실행 절차](oidc-group-diagnostics.md)에 등록 URI·scope·출처별 claim과 offline mapping 후보 경계를 기록했다.
- **회귀:** `npm run test:target -- backend:tests/test_oidc_group_probe.py` 140passed. 실제 RSA 검증·aud/issuer/nonce/azp/at_hash·UserInfo subject·state/browser/replay·discovery origin/redirect/size·missing/empty/malformed groups·private exclusive 출력과 callback Host/duplicate-query를 검증했다. Task-owned Python2files Ruff check/format 통과다.
- **인접 auth target:** backend1119passed. Frontend634passed/2failed이며 두 실패는 수정하지 않은 `AdminSidebar.test.ts`의 `Lumen` 링크 기대다. 해당 navigation의 동시 변경은 이 독립 도구의 범위 밖이므로 덮어쓰거나 assertion을 바꾸지 않았다. Named target 전체 성공으로 보고하지 않는다.
- **실행:** 실제 `main()`·`HTTPServer`·httpx TLS를 scratch CA의 loopback HTTPS provider에 연결하고 별도 Chromium에서 start→합성 consent→callback200의 성공 문구를 관측했다. TLS 검증은 probe에서 유지했고 browser만 scratch certificate를 허용한 뒤 복원했다. Provider가 PKCE verifier를 확인했고 실제 token→JWKS→UserInfo 순서, source별 원문 그룹과 정확한 집합 차이, report0600·secret/access-token 비포함을 확인했다. 이 IdP는 합성이며 실제 GitLab 사용자 claim이나 Keystone WSGI 관측 증거가 아니다. 테스트 listener·CA/key·secret·출력은 종료/제거했다. CLI `--help`도 실제 실행했다.
- **외부 근거:** 실제 공개 GitLab discovery의 code/S256/RS256·group claim 광고와 SSH read-only operator guide/schema2.0 JSON의 `OIDC-groups_direct`를 확인했다. 운영 callback/native federation·계정/그룹/role/project 쓰기·secret 갱신·배포는0이다.
- **Architecture:** HEAD+task-owned source2files와 관련 문서의 격리 snapshot에서 공식 working stamp/staged guard를 통과했다(`19db252433d88ac30a4bc6504c9ed39911374021547b8f933fe8697fd7c4f6b3`,3436source files). Shared index/global review marker와 동시 WIP는 보존했다. 전체 `test:gate`·운영 native/live acceptance·릴리스는 이 도구의 검증으로 주장하지 않는다.


## 관리자 내부 manager projection 그룹 노출 (2026-10-26, source 한정)

- **원인:** 내부 `afterglow-default-managers-*`/`afterglow:default-manager-reader:v1:*` 그룹을 관리자 일반 그룹 목록에 포함하여 UI가 수정·멤버 변경·삭제를 제안했다. 직접 삭제의 `403 domain_manager_projection_is_private`는 권한 동기화 원장을 지키는 의도된 보호이며 해제하지 않는다.
- **수정:** 기존 canonical predicate를 cached inventory 반환 뒤 생성 이력 보강 전에 적용한다. Fresh·warm·수정 전 legacy warm cache에서 name-only/description-marker-only projection을 모두 제외하고 일반 그룹·domain scope·정렬·mutation guard를 보존한다. Frontend/API schema·설정·DB/schema·native IAM은 변경하지 않는다.
- **전후 회귀:** 새 endpoint 회귀는 수정 전 목록 누출2failed/직접 삭제 보호1passed, 수정 뒤 inventory/default-domain/domain-project3files186passed. 최종 named access는 backend1638passed, frontend24files349passed. 변경 Python2files Ruff/lint/format 통과다.
- **실제 HTTP·브라우저:** Uvicorn·설치된 Keystone/OpenStack SDK·fakeredis cache/graph lease·loopback native를 실행했다. Legacy cache를 그대로 채운 뒤 GET200의 일반 그룹1개만 표시, private 직접 DELETE403/native write0, compiled 관리자 화면에서 일반 그룹 삭제 확인→실제 DELETE204→목록0개와 native 그룹 부재를 확인했다. Native 삭제는 합성 `ordinary`1회뿐이며 두 private 그룹은 그대로 남고 unexpected native 요청0이다. QA 문서의 별도 same-origin proxy로만 CSP를 분리했으며 운영 CSP/인증/그룹은 바꾸지 않았다. Identity/admin authority와 provider 데이터는 합성이며 운영 삭제 수용의 증거가 아니다.
- **증거:** `~/.local/share/afterglow-proofs/private-manager-group-inventory-20261026/`의 `before.log`, `after-exact.log`, `access-target.log`, `http-before-browser.json`, `http-browser-final-state.json`, `filtered-admin-groups.png`, `ordinary-group-deleted.png`. Frozen source `90497ed0c269a0f370aee3396a2608e51a313ff94c9ee133c787d4480e99901e`/3497files의 architecture working/staged guard만 격리 index에서 확인했다. Shared review marker/index는 보존하며 이 작업과 무관한 WIP 전체를 검토했다는 주장은 하지 않는다.
- **최종 전체 gate:** 위 frozen source에서 `npm run test:gate`를 실제 실행했다. Backend9711passed/95skipped, frontend447files5327passed/3files6failed이며 전체 gate는 실패다. 실패는 `chat-gated-surfaces.test.ts`의 Lumen option1건, `AdminSidebar.test.ts`의 Lumen link2건, `admin/chat/__tests__/page.test.ts`의 모델 불러오기 button3건이다. 상세 ID/오류는 `test-gate.log`에 있으며 이번 그룹 수정의 통과를 전체 gate 성공으로 확대하지 않는다. Gate가 frontend에서 종료되어 뒤 contract/functional/global lint lane은 이번 gate에서 실행되지 않았다. Commit/push/deploy는 수행하지 않았다.


## 관리자 그룹의 명시적 타 identity-domain 사용자 (2026-10-26, source 한정)

- **기본/명시 scope:** 기본 `/domains/{id}/members` home/joined 조회는 유지한다. Group 소유 domain과 별개로 Accounts 등 활성 계정 home을 하나 골라 `/groups/{group}/candidates?domain_id=...&user_domain_id=...`에서만 조회하고 전체-domain 선택은 없다. 명시 추가는 기존 graph lease 안에서 system-admin과 exact enabled user/home/group/target을 다시 검증한다. 자신의 group domain만 사전 가입 예외이며 다른 domain grant·owner/projection·마지막 manager/system-admin·native policy 보호는 유지한다. 계정 이동·추가 role grant는 없다.
- **실제 HTTP:** Uvicorn·설치된 keystoneclient/openstacksdk·실제 graph lease와 loopback native/fakeredis를 실행했다. 기본200·미가입 기본 PUT403·Accounts 후보200·명시 추가204·이후 멤버200, source/group mismatch403·user403/503·home404·metadata503·third-domain grant403·비관리자403을 확인했다. 합성 native에는 정확한 UUID PUT1회, 별도 role write0·live cloud mutation0이다. 운영 인증/그룹 변경 수용은 아니다.
- **실제 compiled UI:** Default 유지→Accounts 선택→이메일/전체 UUID 검색→정확한 UUID 추가1회를 확인하고 다른 home의 동명 계정과 source 전환 시 기존 멤버 유지·loading/error≠empty·독립 domain-catalog 실패/재조회·explicit retry를 확인했다. Source ABA는 최초 구현에서 real-client force flight를 재사용하여 현재 lookup이 과거 pending 결과를 기다리던 결함을 재현했다. 전용 no-store 요청으로 분리한 뒤 실제 client를 사용하는 영구 회귀가 failing-before/passing-after이고 브라우저에서도 이전 응답이 새 실패를 되살리지 않는다.
- **반응형/회귀:** nine locale×dark/light×390/767/768/820/1023/1024/1440의126조건에서 picker popover·source/action containment·전체 UUID/email·overflow0이다. Backend3files207passed, final frontend3files28passed; 초기 관련 Access backend1635·frontend21files321passed. i18n0errors/37기존 ordering warnings·scan0, Svelte0errors/16기존 warnings, group detector[]다. 테스트가 사용하는 SDK/HTTP/UI는 실제이며 authority/provider 데이터는 합성이다.
- **보존/증거:** `~/.local/share/afterglow-proofs/cross-domain-admin-groups-20261026/`에 HTTP recipe·receipt, real-client 전후 회귀, compiled behavior·126조건·desktop/mobile 화면을 보존한다. Shared index/review marker·private config·service/database/native IAM은 수정하지 않았다. 이 작업은 그룹 전용이며 일반 IAM/프로젝트 후보 목록의 범위를 확대하거나 다른 strict directory404를 복구한 증거가 아니다.
- **최종 frozen group gate:** Lumen 후속 변경을 섞기 전 source `9baddc551f712e253c4d91ff8aa5ff04fefe50292afb5ac32f127808710610dc`/3500files의 격리 `npm run test:gate`는 backend9708passed/95skip, frontend451files5326passed, contracts182, real datastores167passed/33deselected, Ruff738files로 통과했다. 이후 Lumen source의 통합 gate와 구분한다. 모든 functional-owned container/network는 runner가 제거했고 공유 서비스 replacement는 수행하지 않았다.

## 관리자 그룹 사용자 조회·UUID 구분 (2026-10-26, source 한정)

- **원인/실제 native:** configured local backend의 read-only directory 실행은 dangling role-assignment user GET404로 전체404였다. 새 함수만 별도 process memory에 적재하고 candidate opt-in을 적용하면69users/67enabled를 반환했다. 사용자 정보·UUID는 receipt에 저장하지 않았고 runtime 파일/config/IAM은 변경하지 않았다. 9.40초/8.80초 단일 관측은 성능 개선 주장이 아니며 실제 중복 이름 사례는 이 목록에 없었다.
- **좁은 수정:** administrator `/domains/{id}/members`만 exact user404를 생략한다. 기본 directory·manager/group mutation은 strict이며 user403/503·home-domain404·ID 대체·malformed graph 오류는 유지한다. 다른 directory 소비자까지 복구했다고 주장하지 않는다. Saved-before 회귀는404로 실패했고 수정 뒤 관련 backend2files117passed, group UI2files16passed다.
- **Actual HTTP:** 실제 Uvicorn·설치 keystoneclient/openstacksdk와 loopback native fixture에서 후보/그룹 멤버200, user403/503, home404, mismatch503, strict directory404를 확인했다. 같은 이름의 두 UUID·이메일·native home과 foreign read-only metadata를 보존했다. Guard/Keystone 데이터는 합성이고 native mutation0이다.
- **Actual compiled browser:** 실제 Svelte group page/controller/client를 별도 origin/profile에 mount했다. Before는 email/UUID 검색 실패·후보404와 거짓 no-match 동시 표시·멤버 UUID 누락을 재현했다. After는 동명·다른 home 후보2개, email/전체 UUID 검색, 정확히 선택 UUID의 PUT1회, 기존 멤버 UUID만 제외, 성공한 멤버 유지, pending/error≠empty, 명시 retry 복구와8개 초과 후보 접근을 확인했다. 아홉 locale×두 theme×390/820/1440의54조건에서 overflow0·전체 ID/이메일 및 action containment를 확인했다. 합성 identity/API이며 실제 로그인·native group 편집 수용은 아니다.
- **Locale/type:** 최신 i18n0errors/37기존 ordering warnings·scan0, Svelte0errors/16기존 warnings. Browser recipe·native read-only receipt·HTTP/전후/54조건 증거는 `~/.local/share/afterglow-proofs/admin-group-user-lookup-20261026/`에 보존한다. Shared index/review marker·private 설정·기존 서비스·DB/schema·IAM·그룹은 보존하며 commit/push/배포는 별도다.
- **최종 격리 gate:** source `6cb20eedcc504ba9600bea058b5a9c1230fc95bb4cf7831526db1111e273f4bf`/3498files에서 `npm run test:gate`가 backend9652passed/95skip, frontend450files/5313passed, contracts182, real MariaDB/PostgreSQL/Redis functional167passed/33deselected, Ruff737files로 통과했다. Related access target은 backend1579·frontend21files/321passed다. Working/staged architecture guard는 격리 snapshot에서만 수행하고 공유 marker/index를 stamp/stage하지 않았다. Code indexing은 local gbrain CLI 부재로 미실행이며 production/공유 서비스 반영은 없다.

## 응답 지연·세션 갱신·목록 cache·관리자 볼륨 이전 (2026-10-26, source 한정)

- **실제 기존 runtime 기준:** local container의 구조화된 route 로그60분을 값/ID 없는 집계로 보존했다. Dashboard summary16건 p50/p95는3789/5478ms, quota16건4047/7602ms였고 관리자 overview20.24초·SSO callback14.03초는 각각1건이다. Frontend login HTML의 브라우저 TTFB21ms와 login-options664–806ms, canonical-origin authorize774ms·GitLab302162ms·signin180ms를 별도로 관찰했다. Human callback을 새로 완료하거나 이 역사적 표본과 합성 smoke를 속도비로 비교하지 않는다.
- **실제 native 전후:** 설치된 SDK와 같은 고정 credential로 읽기/인증 교환만 실행했다. Fresh 관리자 guard는3724.53→1260.92ms, native HTTP46→21·token exchange6→2였고 다음 guard의 fresh 권위 경계는 그대로다. 요청-local 검증 AccessInfo 재사용은 동일 Nova2rows에서514.16→363.48ms·HTTP4→2·추가 token exchange1→0이었다. 각각 순차 단일 표본이며 전체 운영 p95/SLA가 아니다. Service policy/IAM·cloud resource·운영 설정은 변경하지 않았다.
- **Cache/응답:**50ms 합성 origin에 동시에8force 요청을 보내408.85ms/8origin에서52.70ms/1origin으로 줄어드는 것을 실행했다. 실제 Uvicorn·SDK·loopback Nova/Cinder/Neutron의 compact snapshot은548bytes, cold6provider requests·warm0requests, 한 native-proof dependency를 사용했다. Force는6requests, quota 실패는null/error만 반환하고 summary를 유지했다. 권위/provider 데이터·memory cache는 합성이며 `Server-Timing`은 backend 헤더 생성 전 숫자 시간이다.
- **로그인/하루 세션:** 실제 설정은 absolute3600초·access900초·native root86400초였고 token exchange는 native 만료를 늘리지 않았다. Source default86400초와 native/original deadline JWT·Redis TTL bound를 적용하되 기존 private 설정은 보존했다. 실제 Uvicorn auth routes·서명 JWT·SQLite·fakeredis Lua 및 synthetic native v3 transport에서 password/provider 각각23시간 된 family refresh200, 원래 started_at/family 보존, old JTI401·24시간deadline401·5분 native bound·native revoke401을 확인했다. 실제 Vite client/auth store의90초 terminal deadline에서6read/1refresh로 반복 preflight 회전을 막았고 명시/실제401 갱신은 계속 검증한다.
- **Login read control:** 같은 현재 Uvicorn/서명/SQL/native-v3 합성 경계에서 이전 Personal 조회 알고리즘만 process-local로 복원한 control과 비교했다. Password directory read37→33, provider41→37이며 login token exchange3·refresh2는 동일하다. 두 process를 gate와 병행했으므로130ms/40ms 계열 timing은 속도 개선 비율로 쓰지 않는다. Native membership/provenance·회수·원래 deadline 검증은 두 mode 모두 유지했다.
- **남은 지연/범위:** matched control은 password130.6→130.9ms·provider41.2→40.5ms로 로그인 지연 개선을 입증하지 못했다. 실제14.03초 GitLab callback의 내부 stage별 비용과 수정 후 human callback은 미확인이므로 그 지연은 미해결이다. 기존15–20초 관리자 route 전체의 전후도 측정하지 않았고 guard/SDK 단위 개선만 확인했다. Controller-local SWR은 unmount 뒤 표시 snapshot을 유지하지 않으므로 화면 재방문 속도 개선도 주장하지 않는다. Native compute discovery도 요청-local connection마다 남는다.
- **모든 목록 조사:** source coverage는130dashboard/admin routes·90공통 auto-refresh callsites·127timer/helper files와 수동 버튼/예외를 기록한다. Actual compiled helper는180ms slow round에서50ms timer3회 중복0, 완료 뒤 지연·간격 변경 initial replay0·한 manual 후행·unmount/offline/hidden stop·online resume를 통과했다. 권한 observation이 새 native GET을 시작하지 않는 readiness, draft/terminal 보존, ABA·취소 waiter·mutation invalidation과 강제 freshness/새 token·project routing assertion을 유지했다. 이 source inventory는130개 화면 모두의 live-cloud 실행 수용이 아니다.
- **관리자 이전:** 실제 router/Uvicorn/설치 SDK와 loopback Keystone/Cinder에서 생성201·정확한 all_tenants recovery200·target scope403·native accept403·성공200·비밀 없는 validation422·응답 유실502, 정확히 create1/accept3/Keystone4를 확인했다. Human 권위와 SQL ledger는 합성이며 live volume mutation은0이다. Production build/Node의 실제 admin volume 목록→발급→native-domain metadata 선택→수신은 synthetic tutorial/HTTP로create1/accept1을 통과했다. 별도 compiled supplied-key 진입은create0/accept1로 다른 선택 프로젝트 수신을 완료했다. Actual source component의403 key retention과54locale/theme/width 조건(9×2×3), bounded footer·overflow0·동일-session key 유지도 확인했다.
- **SSE mutation:** `client.upload.test.ts`는 실제 `ReadableStream`을 완료/실패로 각각 끝내기 전후에 inventory revision을 바꾸고 pre-stream·in-stream warm cache가 모두 폐기됨을 확인한다. 고정 sleep 대신 consumer-visible 재조회 결과를 기다리며31개 upload/SSE 회귀가 통과했다. 공통 cache 재작성 중 제거했던 의미 계약을 복구했으며 bearer/scope·force 관련 assertion도 유지했다.
- **초기 통합 gate(c92bd5):** private 입력을 제외한 격리 `dev` snapshot의 `npm run test:gate`가 backend9628passed/95skipped, frontend450files/5303passed 및 Node runner9, consumer contracts182, 실제 MariaDB/PostgreSQL/Redis functional167passed/33deselected, Ruff737files로 통과했다. Orchestration170·Kolla18·installer20도 통과했고 PowerShell 미설치36skip은 미검증이다. 별도 Svelte check는0errors/16warnings, i18n0errors/37ordering warnings·hard-coded Korean0이며 production build를 실제 실행했다. 해당 source hash는 `c92bd5f4bc30c0ac705348f226a6afae7acf00b475c5c763d7d902f34621b81d`/3498files; working/staged architecture guard는 격리 snapshot에서만 확인했다. QA HTTP/source/compiled 서버와 managed tab을 해제하고 test-owned datastore3개·network·잔여 volume0을 확인했다.
- **배포 기본값 보정:** backend/example/generate_k8s 외에 남아 있던 Helm·개발 values·bundled Kolla template의3600초도86400초로 통일했다. 실제 backend consumer가 없는 `absolute_timeout`/`absoluteTimeout`은 mapper/template/value에서 제거했으며 별도4시간 runtime cap은 아니었다. 실제 Helm render를 backend의 세션 deadline 함수로 소비해 기본 하루와 명시600초 각각 만료1초 전 허용·정확한 deadline401/세션 삭제를 확인했다. 현재 private 설정은 별도 `[session] timeout_seconds = 86400`, Helm은 `session.timeoutSeconds: 86400` 및 승인된 반영/새 로그인이 필요하며 이 실행에서는 변경하지 않았다.
- **수신 root 보정:** administrator destination exchange가 scoped `token`을 쓰던 결함을 strict scoped-rescope-disabled fixture에서403으로 재현하고, verified unscoped `session_token`으로 바꾸어200을 확인했다. Missing root는 scoped/executor fallback 없이403이다. Focused179passed, Helm lint1chart/0fail, 최종locale check0errors/37warnings·scan0을 재확인했다. 실제 canonical `Dockerfile --target backend`를 arm64/amd64 모두 빌드하고 `aarch64`/`x86_64` 실행을 확인했다. Canonical Compose backend의 별도 one-off 실행은 private env/volume 없이 network none의 합성 native TCP에서 두 architecture 모두 create201·scope/native403·accept200·validation422·ambiguous502·recovery200을 통과했으며 종료 뒤 해당 project container/network/volume은0이다. Shared local/운영 교체나 Kubernetes rollout은 아니다.
- **보정 후 최종 gate:** source `42ae393e1669a85c4c7c33ee01c07dc5383c1ba4853b589bf1a6b753259cd3f0`/3498files의 격리 canonical gate가 backend9632passed/95skip, frontend450files/5303passed, contracts182, real-datastore functional167passed/33deselected, Ruff737files로 통과했다. c92bd5는 이전 통합 결과이며 현재 source의 증거는 `2026-10-26-correct-session-distribution-and-transfer-root/verification.json`이 정본이다. 최신locale0errors/37warnings·scan0도 재실행했고 실제 target-project 역할 보유 범위와 human SSO callback 수용은 여전히 미검증이다.
- **보존/미검증:** 공유 index/review marker·private TOML·서명/암호화 키·운영 DB/schema·IAM·RGW·기존 Compose 서비스는 보존했다. 새 human GitLab callback·real target-project Cinder mutation·실행 중private3600초 변경·배포/commit/push는 하지 않았다. 증거와 재현 recipe는 `~/.local/share/afterglow-proofs/dashboard-latency-session-transfer-20261026/`와 해당 OpenSpec verification에 분리하며 code indexing은 local gbrain CLI 부재로 실행하지 않았다.

## 관리자 Swift·도메인 토폴로지·Lumen 키/모델 종류 (2026-10-25, source 한정)

- **구현:** 관리자 Swift 목록을 `/api/v1/admin/object-storage`의 fixed-executor account 조회로 분리하고 consumer inventory 조건을 제거했다. 동명 bucket은 `(project_id,name)`으로 구분하고 foreign-project 삭제를 비활성화한다. 관리자 topology는 native 소유 domain UUID별 부모 box/레인을 추가하며 실제 연결을 합성하지 않는다. Lumen account에 여러 키를 유지하면서 키별 명시적 JSON/plain ping 검사와 transient 관측 상태를 추가했다. 등록 모델 종류 수정은 같은 ID·공유 token 가격을 유지하고 비활성 저장하며 종류 전용 단가 제거를 안내한다.
- **Focused/named:** 최종 모델·키·canvas·Swift frontend는 부분 inventory와 cache-only 생성/reopen/reset 의미 회귀를 포함해 **17files/320passed**다. Storage named는 최종 backend916·frontend177을 통과했다. Lumen named의 backend61·frontend191은 이전 wire-echo4cases 제거 전 결과이며 전체 consumer contract는182passed다. Native Lumen 최종 probe/account/transport/model 회귀197passed, SDK143와 전체 Ruff가 통과했다. 요청 필드 복사만 확인하는 회귀 대신 실제 상태/인가·생성 후 재열기·HTTP evidence를 유지했다.
- **Swift 후속 실환경 검증/수정:** 첫 report의 strict-failure 수용은 아래 부분 응답으로 대체한다. Read-only Kolla flag는 `ceph_rgw_swift_account_in_url=yes`, 실제 executor catalog도 `/swift/v1/AUTH_<executor>`였다. 고정 토큰으로57enabled 계정 HEAD를 실행해 executor204·foreign29개204·27개403을 확인했다. 현재 source의 정확한 admin flags를 process-local 진단에 로드해 실제 RGW GET을 실행한 결과 **readable30·unavailable27·버킷8개**, scope 보존을 확인했다. Native 정책/role/config를 변경하지 않았다. Ceph effective admin-role 설정은 storage-hop host-key 차단으로 확인하지 못했고 검증을 끄지 않았다. 원 screenshot500 traceback은 여전히 확정하지 않는다.
- **부분 inventory 계약/smoke:** API는 `{items, project_count, partial, unavailable_projects}`로 readable row와 denied/failed 계정을 분리한다. Directory/endpoint 오류는 전체 오류다. Uvicorn/실제 SDK/loopback5scope200 및 provider401/403/500/503의 per-project unavailable metadata·raw error 비공개를 확인했다. Backend focused158passed·관련 frontend52passed, i18n0errors/37기존warnings다. 최종 compiled UI에서 readable bucket 유지·미조회 UUID/사유 disclosure·전체 합계 숨김·전부 unavailable일 때 미확인 empty 상태를 확인했고6width overflow0이었다. 합성 UI/native-loopback proof와 실제 RGW read-only 결과는 분리해 보존한다.
- **Native provider:** 실제 native Uvicorn/SQLite/`provider_client`에서 structured-A/plain-B/auth-rejected-A **정확히3sends**와 stale-generation409/추가send0, synthetic authority6checks를 확인했다. 최종 요청은 `{"request":"ping"}` 또는 `ping`이며 structured 결과는 canonical `{"response":"pong"}`이다. Plain의 비어 있지 않은 정상 length-terminal도 연결 관측으로 인정한다. Identity와 private converter/provider는 합성이고 Go converter·paid upstream 검증은 아니다.
- **실제 Chromium:** production SvelteKit build/Node adapter를 실행했다. Native HTTP/SQLite로 모델5종을 수동 등록해 각각의 종류를 저장하고 기존 text→image 종류 수정/동일ID·비활성·공유 token 단가 보존·종류 필터를 확인했다. 키2개 실제 CRUD, 합성 probe 응답의 서로 다른 키별 성공/실패 표시와390/767/768/1023/1024/1440px overflow0을 확인했다. Topology는4domain parents/7zones 포함·비중첩, duplicate-label UUID·shared/external단일표시·검색·레인4그룹·consumer box0, 두 theme×6width에서 parent4/zone7/overflow0이다. Swift 동명2bucket의 owner 상세URL·foreign delete비활성 및390/768/1024/1440px overflow0도 확인했다. 아홉 locale의 모델 수정 button과 실제 document lang을 확인했다. Identity/cloud/topology/probe 응답은 명시한 부분에서 합성이다.
- **전체 검증 한계:** 격리 snapshot의 `npm run test:gate`는 backend9537passed/95skip 후 별도 Palimpsest 작업8fail/8error로 중단했다. 초기 전체 frontend에서 이번 변경의 요청-copy/문구2개 회귀를 정리한 뒤 영향 영역315passed이며 최종 전체 frontend의 남은 실패는 별도 Palimpsest/library 영역이다. `npm run check`는 범위 밖 AdminFileStorageDetailPanel nullability2errors/기존17warnings다. 실제 MariaDB/PostgreSQL/Redis functional **167passed/33deselected**, owned test stack teardown 완료. i18n check0errors/37기존key-order warnings·scan0, changed-UI detector[]다. 전체 gate 성공이나 commit 가능 상태로 보고하지 않는다.
- **Native 전체/배포 경계:** native contract는 pre-final-ping source에서4013passed/7fail/384deselected였다. 기존 expired approval1개, matching Bifrost binary 부재5개, Python3.13 guest TLS fixture1개다. 원래 native release checkout은 유지하고 별도 `/Users/pieroot/code/lumen-admin-fixes`의 local dev에 변경을 보존했다. 기존 native branch의027 migration 번호/0.6.9 상호호환 cutover blocker는 해결·배포하지 않았다. 새 schema·설정·키·IAM·운영/로컬 Compose 서비스는 변경하지 않았으며 commit/push/release/deploy는 없다.
- **보존:** 원래 공유 index와 architecture-review marker를 유지하고 isolated snapshot에서만 stamp/`--staged` guard를 실행했다. 증거·실행 recipe·browser JSON은 `~/.local/share/afterglow-proofs/admin-storage-topology-lumen-20261025/`에 보존한다. gbrain sync helper가 없어 indexing은 실행하지 않았다.

## Impeccable 제품 맥락 초기화·개발 CSP (2026-10-25, source 한정)

- 사용자 확인으로 primary audience를 범용 클라우드 소비자, 핵심 가치를 클라우드·AI 통합 작업 공간으로 기록했다. `PRODUCT.md`는 durable product truth만 소유하며 `DESIGN.md`·기존 UI를 변경하지 않았다. 랜딩·쇼케이스 제작 기본값 `buildPath=comp`는 `.impeccable/config.json`에만 저장했고 앱·문서의 code-first 원칙과 분리했다.
- 별도 승인한 Live CSP는 정확히 `http://localhost:8400` script/connect 개발 예외다. SvelteKit config의 `NODE_ENV=development`와 effective response hook의 `$app/environment.dev` 경계로 production에서 제외한다. Hooks가 runtime connect origins를 최종 합성하므로 config의 script-src만 변경하는 것으로는 동작하지 않는다. 기존 API/WebSocket origins·nonce/hash·다른 resource directives는 보존한다.
- `npx vitest run src/hooks.server.test.ts`: **80passed**, production/dev picker origin 경계·기존 runtime 연결 허용·nonce/hash 보존 회귀 포함. 실제 `NODE_ENV=production`의 SvelteKit config import에서 script source가 기존 `['self']`임을 확인했다.
- 독립 Vite `127.0.0.1:51487/login` 실제 HTTP200에서 helper script/connect 허용, generated nonce 보존과 unsafe-inline script 미허용을 확인했다. Header smoke 후 owned Vite를 종료했다. Live helper/injection·실제 picker 상호작용은 시작하지 않았으며 화면 변경이 없어 visual QA/이미지 생성은 실행하지 않았다. 전체 test:gate·production build·배포 수용을 이 국소 검증으로 주장하지 않는다.


## 배포 정본 native OIDC 소스 통합 (2026-10-25, 로컬 backend 반영·운영 미배포)

- **실제 원인/정본:** Kolla의 schema2.0 ephemeral Accounts·Personal `{0}-project/member`·dmslab Default/reader·groups_direct mapping은 의도된 최신 계약이다. 정본 JSON과 live `sso_oidc_mapping`이 같고 실제 세 controller는 `dmslab_oidc_transport`를 사용한다. 이전 accounts-auth 파일은 남아 있어도 비활성이다. 세 controller의 version-bound native adapter와 native guard는 이미 정상이며 로컬은 base3modules와 누락된 adapter 때문에 `native_mapping_unsafe`503을 재현했다. Mapping을 되돌리거나 native 정책을 재설계하지 않았다.
- **소스:** 기존 배포 adapter delta를 `native_oidc.py`와 auth/account helpers로 이식하고 provider별 `native_mapping` model/digest/domain pins로 일반화했다. 설정·K8s/example에 같은 nested contract를 보존하며 operational ID/issuer/client는 application source 상수가 아니다. Native mapping 전체 drift·issuer/protocol proof·stable subject·외부 Personal/shared/admin/group authority·entry/link mode 전환·삭제 불명 receipt를 거부한다. Alternate native protocol shadow는 같은 pinned mapping/issuer의 complete LIST proof로만 인정한다. Conditional remote가 placeholder numbering을 바꾸는 mapping은 거부한다. Legacy pin 미설정 provider revision은 불필요하게 변경하지 않는다.
- **회귀/실행:** focused655passed/1skip. 실제 Uvicorn TCP callback에 signed OIDC wire·PKCE/nonce·합성 native directory/auth를 연결해 정상200와 digest drift503(교환0)을 검증했고 owned server2개를 종료했다. 이는 실제 사용자 GitLab code나 운영 native provisioning 수용이 아니다. Scope regression 및 전체 gate에 이전 관리자 상세/역할 제한 변경도 포함했다.
- **최종 gate:** source `632a74a074357f979198871593f71d58ae39f706b8821d0d26b0a3b26823b392`/3444files, 격리 public snapshot에서 `npm run test:gate` exit0: backend9480/95skip, frontend439files/5124tests, contract181, disposable DB166, Ruff728formatted. DB/cloud env는 비웠고 완료 후 canonical backend/.venv의 dev extras 및 crypto canonical origin/import를 복구했다.
- **승인된 로컬 반영:** 사용자 승인 후 정본 Dockerfile/Compose backend를 arm64·amd64로 build하고 양 architecture 실행/module smoke를 확인했다. Backend만 `--no-deps --no-build --wait`로 교체했다. 실행 중 DATABASE_URL과 render 기본값 불일치는 적용 전에 정확한 기존 env override로 해결했고 사후 환경 전체·mount·config bytes·13개 다른 container IDs를 보존했다. Docker Desktop의 `/host_mnt/Users` 표기는 같은 host mount의 VM 경로이며 logical source 및 실제 config bytes를 대조했다. SQL model28개 중 변경은 non-SQL auth_settings뿐이며 새 schema/migration은 없다. Private 설정은 dmslab provider의 exact existing mapping pin 추가·지원하지 않는 Default provider 비활성·Default allowlist 비움 세 경로만 변경했다. Root config/secret/기존 DB·키는 보존했다.
- **로컬 수용 한계:** 실제 :8000 backend healthy, real native guard가 현재 운영 mapping을 수용한다. `/auth/login-options`는 지원하는 dmslab provider 하나만 반환하고 실제 Chromium에서 Default 제거·GitLab 로그인 화면 handoff를 확인했다. 사용자 암호/IdP session/code를 사용하지 않았으므로 fresh human callback/로그인 완료는 사용자 재시도가 필요하다. 운영 Kolla/Keystone mapping·이미지·계정/grant 변경이나 commit/push/tag는 하지 않았다. 증거: `~/.local/share/afterglow-proofs/integrate-deployed-native-oidc-20261025/`.

## Native admin 프로젝트 할당 제한 (2026-10-25, source 검증·미배포)

- **계약:** 사용자/project·도메인 IAM replacement와 관리자 user/group project grant에서 literal native `admin` 신규 추가를 막고 기존 direct admin은 회수할 수 있다. `project_admin`·서비스 `*_admin`과 dedicated system:all admin grant/revoke 및 마지막 유효 관리자/Default manager 보호는 유지한다. 기존 운영 grant·role/DAG를 자동 변경하지 않았다.
- **보안 경계:** removal-only catalog admin을 초대 grant allowlist에서는 제외한다. Unrelated direct 및 group/상속 grant는 immutable/provenance 계약을 유지한다. 도메인 IAM의 privileged-account 예외는 잠긴 실제 snapshot의 delta가 해당 project admin 회수만이고 추가/다른 회수가 전혀 없을 때에만 허용한다. General protected-user/credential·system/domain/다른 project admin/service/operator 보호 회귀는 계속 통과한다.
- **회귀:** 이전 UI source에 신규 테스트를 적용하면10failed/26passed, 수정 후36passed다. Backend role/membership/domain-IAM/system suite323passed, 확장 access target1555backend/321frontend가 통과했다. 실제 Uvicorn TCP에서 관리자 user/group 새admin422·기존admin해제200, 사용자 mixed admin추가422·직접admin만해제200(기존 project_member 보존), system admin grant/revoke 각각200과 정확한 native system calls를 확인했다. 인증/native directory는 stateful 합성이며 main 앱 startup/운영 Keystone 수용이 아니다(`http-smoke.log`).
- **화면:** 실제 shared 사용자 역할 modal과 관리자 project access modal을 disposable Vite harness에서 Chromium으로 열어 미할당 admin 비활성, 기존 admin 해제 뒤 재선택 불가, 관리자 DELETE 한 건·POST0을 확인했다. 390px light의 admin 행 비활성 및 document overflow0을 확인했다. Group/inherited overlap의 direct 해제 후 effective 체크 유지도 UI 회귀에 포함된다. 브라우저 fixture는 합성 mutable API이며 실제 운영 로그인/권한 회수가 아니다.
- **최종 canonical gate:** source `af84391ba3aaa556cd05cb68564c13fc1b3792ff202512d47c52cbde380a71be`/3442files, `npm run test:gate` exit0: backend9350/95skip, frontend439files/5124tests, contract181, disposable DB166, Ruff726formatted. 운영 DB/cloud env를 비운 격리 public snapshot에서 실행했고 이전 미커밋 관리자 상세 복구도 포함한다. 검사 후 canonical backend/.venv의 dev extra와 afterglow-crypto canonical origin/import를 복구·확인했다. QA browser/server/harness 제거, commit/push/tag/deploy·native IAM/schema/config 변경 없음. 증거: `~/.local/share/afterglow-proofs/restrict-native-admin-role-grants-20261025/`.

## 관리자 상세 transport 복구 (2026-10-25, source 검증·미배포)

- **범위:** Identity의 `_selected_objects`와 관리자 목록/상세/관리 작업을 fixed `get_admin_os_conn`으로 통일하고, 인스턴스·이미지·Manila·Octavia·Trove의 관리자 상세/관련 reads를 명시적인 admin 경로에 연결했다. Browser mode는 nullable project hint와 독립적이며 native 부모 UUID/owner 및 child 연결을 확인한다. 사용자 domain/project guard·Personal 역할·K3s/Palimpsest caller credential을 완화하지 않았다. Trove 관리자 목록은 `/api/v1/admin/database-instances`로 이전했다.
- **Fail-before:** 이전 source에 신규 Identity executor 회귀만 적용하면12조건 중11개가 실패하고 기존 올바른 directory path1개만 통과했다. 수정 뒤 관련 endpoint/권위 회수/owner mismatch 회귀가 통과했다. Source-focused849backend/1skip, frontend18files/312tests, access1521backend/285frontend, instances1441backend/613frontend, storage892backend/167frontend를 실행했다.
- **실행 smoke:** 변경된 실제 router를 격리 FastAPI 앱에 mount한 Uvicorn HTTP와 설치된 openstacksdk, 별도 loopback native fixture에서16개 관리자 parent/child read200,16개 member 관리자 요청403과 native send0, 기존 consumer foreign-private image404를 확인했다. 이는 main 앱의 전체 startup/middleware 수용이 아니다. 실제 main 앱의 health-route precedence와 감사/비밀번호 redaction은 회귀 suite로 별도 검증했다. Human/Keystone authority와 native cloud는 합성이며 production credential·DB를 사용하지 않았다. Compiled frontend의 실제 Chromium에서 사용자/프로젝트 목록, private image·foreign-domain VM·share·LB·DB 상세를 열었다. 390px light 이미지 상세의 document overflow0을 확인했다. Gnocchi 실제 수치·notification/profile shell API는 fixture 범위 밖이며 실제 운영 로그인/자원 작업/배포는 수용하지 않았다.
- **검증에서 잡은 추가 결함:** actual compiled VM click의 순환 초기화 TDZ를 독립 owner state로 수정하고 real-controller panel mount 회귀를 추가했다. Metrics no-store route class를 관리자 router 전체에 씌우면 기존 password-redacting validation을 우회하므로 metrics 전용 subrouter로 제한했다. 기존 비밀번호 비노출 및 metrics 경계293개가 함께 통과했다. Monitoring SG 생성의 target project 누락, 관리자 이미지 삭제 cache 누락, SDK Resource dict snapshot/current attribute 차이와 Trove name@host pagination을 수정·검증했다.
- **최종 gate:** 추가 CephX 응답 hardening을 포함한 격리 public source `b36154a006fe08391f82fec0e49f513d9aa51e729e76c83415d0d85d23225ae6`/3442files에서 `npm run test:gate` exit0: backend9316/95skip, frontend439files/5111tests, contract181, disposable DB166, Ruff726formatted. 운영 DB URL·cloud credential은 비웠고 private `.env/afterglow.conf`는 snapshot에 없다. 초회 gate의 소유권 fixture 및 validation/선택 regression은 해결했고 최종 로그는 `~/.local/share/afterglow-proofs/repair-admin-detail-transport-20261025/test-gate-credential-final.log`다.
- **의도한 제한/보존:** fixed executor로 target 소유를 보장할 수 없는 VM 새 볼륨 생성은 admin 상세에서 숨기고 caller-bound block-ledger 삭제는 native mutation 전에409다. Foreign-private Palimpsest export는 숨기고 기존 caller trust를 유지한다. LB/DB/Manila mutation은 확인된 caller-project 소유에서만 노출한다. Commit/push/tag/release·운영/로컬 Compose 교체·native IAM/schema/config 변경 없음. Optional gbrain CLI가 없어 index sync는 실행하지 않았다. 증거는 같은 private proof root의 `http-smoke.json`, `browser-smoke.json`, screenshots 및 selector/target/build logs다.
- **추가 자격 경계:** 관리자 VM storage 접근 허용/connection-info와 share access-rule 목록에서 `secret/access_key`를 제거했다. 실제 공용 storage 로직과 stateful native-rule fixture를 거치는 회귀 및 실제 TCP3개 응답200에서 provider key는 보존되고 브라우저 응답에는 key가 없음을 확인했다(`storage-credential-{qualified,tcp}.log`). 소비자 명시 key 조회는 유지한다. 검증 후 canonical `backend/.venv`를 `uv sync --frozen --extra dev`로 복구하고 afterglow-crypto의 direct_url이 canonical `services/afterglow-crypto`이며 import/dev 도구가 정상임을 확인했다.

## 1.30.26 운영 배포 (2026-10-24, 관리자 사용자 삭제 + Accounts 이메일 매핑)

- **경위:** `v1.30.25`(`6d57ab65`)를 CI(run40011414906 attempt2; attempt1은 변경과 무관한 backend test hang으로 취소)·tag 발행(Docker40020654946/Helm40020654923)까지 마쳤다. 배포 중 다른 작업이 운영1.30.24에 Accounts `type: local` 이메일 native mapping 검사를 operator overlay(`globals.d/94-afterglow-email-mapping.yml`, 20:01Z 재기동)로 적용했고, 1.30.25에는 없어서 Kolla pull guard가 의도대로 막았다. 컨테이너 변경0으로 pin·role/site link를1.30.24로 되돌렸다. 사용자가 이메일 기반 매핑이 원래 의도이고 stable-sub 전용 가정이 잘못이었다고 확인했다.
- **Source:** 준비된 port를 1.30.25 위에 통합하고 email 매핑 분기를 운영자 registry(`cfg:`) OIDC로 제한했다. Tenant SQL OIDC의 email 매핑이 503 `native_mapping_unsafe`인 회귀는 제한 전 실패/후 통과를 확인했다. 최종 source `9749323a…`/3434 gate: backend9136/95skip, frontend434/5075, contract181, DB166, Ruff723. 앞선 1.30.25 gate의 두 차례 실패는 변경과 무관한 timing test(host observer·lumen-sh PTY) timeout이었다.
- **Release:** `25b9864c` dev CI40043006794, `v1.30.26` Docker40043597187·Helm40043597092 성공. API `c6254076…`, frontend `c80a15f9…`, worker `92eb77ac…`이며 latest가 같은 revision이고 Helm1.30.26이다. CI 발행 platform은 amd64이고 로컬 arm64는 같은 commit에서 canonical Dockerfile로 빌드했다.
- **Schema:** 운영 DB에는 `account_identity_transfers`가 이미 있었다. 2026-10-23 12:43:39Z에 공유 local Compose를 미발행 source로 재생성한 backend가 운영 DB에서 ORM `create_all`로 만들었고(DATETIME(0), row0), 이 세션에서 만든 것이 아니다. SQL102는 `IF NOT EXISTS`라 no-op이므로 DDL을 실행하지 않았다. 새 암호화 SQL/Redis/config 복구 지점을 격리(network-none/tmpfs) 복원해103tables/4879rows와 Redis2197keys를 확인했다. Redis에 stream key가 있어 logical digest에 stream 비교를 추가했다. 복원본에서 1.30.26 ORM50tables와 journal insert/readback/delete, 1.30.24 ORM49tables가 통과하고 row 수는 변하지 않았다.
- **Fleet:** 배포서버 `/etc/kolla`에서 overlay 파일을 보호 backup 후 제거하고(module 디렉터리 보존) pin만 바꿨다. `/etc/kolla/multinode` 전체 대상에 `genconfig→pull→prechecks→reconfigure --tags afterglow --skip-tags haproxy`를 `--limit` 없이 실행해 모두 failed0/unreachable0(reconfigure c1 ok124/changed5, c2·c3 ok68/changed2)이었다. API/frontend6 healthy·worker3 running이 모두 `25b9864c`이고 비대상 container710개는 변경0이며 native/provider fingerprint가 일치한다. 세 controller의 배포 image가 실제 운영 Keystone mapping(protocol `openid`)을 쓰기 없이 accepted로 판정했고 overlay mount는 없다. 재기동 이후 stdout/stderr traceback0, public `/`·`/api/v1/health`·login-options200이다.
- **Local:** 같은 실행기·환경으로 canonical targeted Compose를 적용했다. Definition hash와 12개 effective field가 같고 backend/frontend만 교체했으며 16개 비대상 container를 보존했다. 이 교체로 운영 DB에 붙어 있던 미발행 local writer도 정리되었다.
- **미검증:** 실제 사용자 GitLab 로그인·그룹 반영과 관리자 인증 후 사용자 삭제 화면은 사람 계정으로 확인하지 않았다. 운영 계정·native grant·resource는 삭제하거나 변경하지 않았다. Native protocol 통합(Keystone)은 별도 승인 사항이다. 증거: `~/.local/share/afterglow-proofs/deploy-admin-user-deletion-20261024/`, `/etc/kolla/.afterglow-rollout-backups/1.30.26/email-mapping-20261024/`.


## 관리자 사용자 삭제 (2026-10-23, source 검증·운영 미배포)

- 사용자 목록 table/card에 삭제를 추가하고 native home·전체 user ID·이름 확인과 정확한 full-ID 입력을 요구한다. Cancel/짧은 ID/자기 계정/actor-home-session-project-domain ABA/late-response와 불확실한 응답의 no-replay를 검증했다. Name이 알 수 없거나 federated라는 이유만으로 자동 삭제하지 않으며 프로젝트 멤버십 제거와 구분한다.
- 안전성: existing admin-project executor·fresh system-admin·공유 graph lease, dispatch 직전 actor 재검증, exact native domain/user, Personal primary/추가 프로젝트 소유·active enrollment/provisioning·ownership/identity-transfer journal 보호, last-admin/domain-manager·native admin/service/system 보호. 운영 read-only inventory에서 `service` role 없이 service-project `admin`만 가진 aodh/barbican/ceilometer/ceph_rgw/gnocchi/manila/masakari/trove 등도 확인해 native admin DAG를 보호한다. Native 서비스 계정/역할은 변경하지 않았다. Configured username이 같은 다른 home도 보수적으로 보호하며 기존 다른 `protected_user` 호출자의 read set은 deletion opt-in flag로 유지한다.
- Source `e6b03e2a5a5c36d3543ace8ce7791e5ecf1801d7af08065945bd4e90f5d2c8fc`/3434files: focused backend75, frontend46; access target backend1404/frontend285; 최종 `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate` exit0, backend9127pass/95skip, frontend434files/5075tests, contract181, disposable DB166, Ruff723. `npm run check`0errors/16기존 warnings, i18n0errors/37기존 key-order warnings. 초기 frontend teardown null prop 문제와 fixture 이메일/Testing Library 타입 오류를 수정했으며 source gate를 재실행했다.
- 실제 실행: isolated Uvicorn TCP→실제 SDK Connection/Identity Proxy→loopback native DELETE에서 wrong-domain403, service-project admin-only409, 정확한 user delete204, 삭제 후404·native DELETE1회, 프로젝트 보존과 target session 폐기/actor session 보존을 확인했다. SQL은 임시 SQLite, Redis와 native directory/authority는 synthetic이다. 이것은 운영 사용자 삭제 증거가 아니다.
- Image: canonical Dockerfile backend/frontend/worker6개를 arm64 native·amd64 emulation으로 build/run했다. API image에서 actual self-delete guard409, worker shared guard import, frontend 양 architecture의 실제 login HTTP200을 확인했다. Arm64 compiled frontend를 Chromium으로 열어 합성 API에서 삭제1회·목록 갱신을 실행했다. Shared local backend를 새 image로 재기동하거나 운영 DB에 create_all/migration을 수행하지 않았다.
- UI: actual Chromium의390/767/768/1023/1024/1440px에서 가로 overflow0, 아홉 locale의 raw key 노출0, compiled390px/1440px의 안정된 panel bounds와 dark/light confirmation을 확인했다. 최초 캡처의 transition frame은 animation 종료 후 다시 찍었다. Browser named-tab aliasing과 QA fixture reload 문제는 제품 source가 아니라 격리 harness에서 해결했고 원래 인증 guard를 완화하지 않았다.
- 남은 운영 경계: 새 account-transfer/Personal/enrollment/ownership guard는 source가 요구하는 기존 SQL manifest(102포함)를 필요로 한다. 별도 schema/readiness·승인된 rollout·실제 로그인한 운영 사용자 삭제 수용은 수행하지 않았다. 이미 native 사용자가 없는 orphan grant 정리와 앞서 확인한 역할 모달 후보404는 이 기능으로 자동 해결하지 않는다. 삭제는 외부 IdP 계정의 정지/삭제도 아니다.

Evidence: `~/.local/share/afterglow-proofs/admin-user-deletion-20261023/`의 `backend-final.log`, `frontend-focused-final.log`, `access.log`, `test-gate-final.log`, `frontend-check-final.log`, `i18n-check.log`, `http-smoke.json`, `images.json`, `browser-smoke.json`, `compiled-browser.json`, `browser-locales.json`, `final-panel-bounds.json`, `users-confirm-{built-desktop,mobile-final,mobile-light}.png`.


## Keystone 마지막 federation 연결 해제 의미 정정 (2026-10-23, 미배포)

- **이전 증거의 한계:** 아래 Accounts-entry의 합성 HTTP last-tuple 이전 성공은 실제 Keystone 호환 증거가 아니다. 설치된 `Manager._update_user_with_federated_objects`는 `if not user.get('federated')`에서 기존 native 연결을 보존한다. 반면 custom extra인 stable metadata 변경은 별도로 적용되어 `federated:[]`와 stable 목록 제거를 같이 보내면 부분 적용될 수 있다. 실제 API schema는 nonempty IdP의 protocols `minItems=1`이므로 빈 protocols로도 우회하지 못한다.
- **직접 실행 증거:** 운영 container의 설치된 메서드를 읽기 전용 inspect한 뒤, 동일 메서드를 in-memory driver/shadow stubs로 실행했다. Native DB/network effect0에서 `[]` PATCH의 연결 보존과 extra 변경의 독립 적용을 확인했다. 실제 운영 user PATCH·schema·mapping·grant 변경은 하지 않았다. Evidence: `installed-keystone-empty-federated-smoke.json`.
- **수정:** native test double이 falsy federation의 기존 목록을 보존하도록 수정했다. 마지막 source tuple의 connect/create는 admission·journal·native 쓰기 전에409 `native_binding_conflict`로 중단한다. 보상도 native 연결이 남아 있는데 빈 목록 복구가 필요하면 metadata를 먼저 지우지 않고 fence한다. 다른 실제 유효 federation 연결이 남는 nonempty source replacement와 정상 Accounts attach/create는 유지한다. Dummy 연결 추가·user 삭제·직접 SQL 수정은 하지 않는다. 해당 마지막 연결의 운영 해제는 별도 지원·검증된 operator-native 절차가 선행돼야 한다.
- **검증:** 새 single-tuple 회귀는 수정 전 native readback 실패/`identity_transfer_recovery_required`로 실패했고 수정 후 connect/create 모두 원래 두 계정·journal 무변경, federation 호출0으로 통과했다. Focused3files280pass; named auth 중간 guard1037backend/630frontendpass. 최종 source `3053ffad6f9af8c9ec99ca9df6c5caf9d9c978d0f361dd77107c5220c4f30c7f`/3430files에서 `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate` exit0: backend9052pass/95skip, frontend432files/5029tests, contract181, disposable DB166, Ruff722. API/worker arm64 native·amd64 emulation을 정본 Dockerfile로 다시 build/run하고 network-none API image에서 store/native client 없는 조건으로 preflight409를 직접 실행했다. Frontend 코드는 변경하지 않았다.
- **운영 상태:** 기존1.30.24, DB·키·native 계정·연결·설정은 그대로다. 이 guard는 unsupported transfer를 안전하게 막는 수정이지 운영 legacy 연결 이전을 완료한 것이 아니다. 기존 SQL102 hard prerequisite와 별도 rollout 승인도 유지한다.
- **후속 live read-only 구분:** 실제 같은 이메일 Accounts/Default 쌍의 Default source는 마지막 연결 하나만 가진 상태가 아니었다. Native association2개는 `gitlab/openid`와 `gitlab/mapped`이고 둘 다 protocol이 존재한다. Mapped 하나를 제거해도 openid1개가 남으므로 이 특정 source는 `[]` 미지원에 해당하지 않으며 nonempty PATCH 경로의 후보이다. 실제 이전은 실행하지 않았다. Evidence: `live-last-tuple-count.json`, `live-last-tuple-protocols.json`. 일반적인 last-tuple 제한을 이 source의 필수 direct-SQL/operator-unlink 요구로 확대하지 않는다.

Evidence root: `~/.local/share/afterglow-proofs/gitlab-accounts-entry-20261023/`의 `last-unlink-{before,final-regression,final-test-gate}.log`, `last-unlink-final-images.json`과 installed-method smoke receipt.


## GitLab 최초 로그인 Accounts 연결/생성 확인 (2026-10-23, 미배포 source)

- **운영 read-only 원인:** controller3대의 cfg provider revision은 모두 `16895922974498`이며 discovery binding 조회도 성공했다. 운영 callback409 두 번을 확인했고, 같은 정규화 이메일의 Accounts/Default 사용자 한 쌍에서 Default가 stable GitLab issuer/sub와 native `gitlab/mapped`를 보유했다. 해당 저장 tuple을 사용한 mutation 없는 `directory` 조회가 `account_email_conflict`를 재현했다. 사용자 callback의 error code 자체는 로그에 남지 않아 동일 요청의 code라고 단정하지 않는다. UI가 모든409를 providerChanged로 표시한 것은 source로 확인했다.
- **Keystone 설정:** 활성 IdP `gitlab`, remote_ids의 정확한 issuer, protocol `mapped`와 `afterglow_gitlab_stable_sub` mapping을 조회했다. Mapping은 user-only ephemeral `user.id={0}`/`OIDC-sub`, 세 controller의 auth methods는 password/token/mapped/openid/application_credential이다. IdP의 domain metadata가 Default라는 사실은 기존 exact native federation tuple의 canonical home을 정하는 입력이 아니다. Email/name mapping으로 바꾸지 않았고 native config/user/grant/resource/운영 SQL은 수정하지 않았다.
- **Source behavior:** operator cfg OIDC의 Accounts 이메일 match는 연결 확인, 부재는 생성 확인이며 local password 입력이 없다. 정확한 same-email Default stable/native 연결은 명시 안내/확인 뒤 association만 옮긴다. SQL102 journal은 bearer 없는 암호화 snapshot을 effect 전에 commit한다. Native timeout/process death·미확정 writes는 fresh OAuth로 replay하지 않고 operator settlement가 필요하다. SQL tenant provider의 explicit account proof와 기존 초대/이메일 수정의 global 중복 fence는 유지한다.
- **Actual runtime:** 실제 Uvicorn API·SQLite journal/enrollment·서명 IdP·설치된 KeystoneClient의 loopback TCP GET/PATCH·native token transport·JWT/session과 compiled frontend를 실행했다. Native users/grants/provider는 합성이며 이 HTTP smoke의 Redis는 fakeredis다. 운영 native write proof가 아니다. Callback409→연결 버튼→entry200→`/dashboard`, Accounts canonical UUID/home와 Personal/member landing을 확인했다. Source Default user의 password/선호/home/다른 fields를 보존하고 journal committed와 exact tuple 이전을 확인했다. Accounts가 없고 legacy 동일 email만 있는 create도200/Accounts+Personal이며 기존 legacy를 선택/변경하지 않았다. Ticket replay401, desktop/mobile390px 비밀번호 입력0·ticket DOM/storage/history 비노출·overflow0·cancel 복귀와 compiled create/503의 no-replay도 확인했다.
- **Checks:** focused backend277pass, callback88/API28pass, named auth backend1035/frontend630pass. 잘못된 hostless cookie fixture는 actual API-host cookie로 수정했고 passwordless synthetic native create adapter의 누락 password 인자를 고쳤다. 최초 full gate는 새 공개 endpoint가 기존 allowlist에 없어서 실패했다. 보안 route inventory guard는 유지하고 browser-bound 자체 proof의 `/providers/entry`를 명시 등록했다. 최종 source `06810dba9d7abe35228baee36feefeff0c4d0c758e0f4debb98604a0c1049bf0`/3430files의 `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate`는 exit0: backend9049pass/95skip, frontend432files/5029tests, contracts181, disposable DB166, Ruff722이다. 공유 operator checkout에서는 full gate를 실행하지 않았다.
- **Artifacts/schema:** canonical Dockerfile의 API/frontend/worker를 arm64와 amd64로 실제 build/run했다. Arm64는 native, amd64는 Docker Desktop emulation이다. API entry/model과 worker journal import, arm64 compiled browser와 amd64 frontend main-server callback SSR200을 확인했다. SQL102는 별도 network-none/tmpfs MariaDB10.11.19에서 apply/reapply와 row roundtrip을 통과했다. 운영 schema apply·native 연결 이전·Kolla rollout/실제 사용자 최종 GitLab login은 수행하지 않았다. Npm image audit는 기존 lock graph에서4건(critical1 포함)을 보고했으며 이번 기능 수정에 dependency 갱신을 섞지 않았다.

- **추가 경계 확인:** 동일 이메일의 Default 사용자를 둔 실제 password-login handler는 이메일 alias로 Accounts 신원만 발급했고 Default-only 사용자명은401이었다. 같은 이메일의 Accounts/Default 사용자에 대한 username/password 복구는 각각202·메일/proof0이며 의도된 global-uniqueness 제한을 확인했다(별도 throwaway3pass, `artifact://2008`). 설치된 Keystone `mapped`/`Manager.shadow_federated_user` source도 읽기 전용 확인했다. Exact native tuple 부재 시 IdP domain의 shadow-user 생성 경로가 있으므로 Afterglow 밖의 직접 Keystone federation을 Accounts 자동 연결로 보장하지 않는다. IdP domain 변경은 수행하지 않았다.
Evidence: `~/.local/share/afterglow-proofs/gitlab-accounts-entry-20261023/{live-readonly.json,http-connect.json,http-create.json,http-browser-native-final.json,migration102-mariadb.json,image-build-runtime.json,test-gate-final.log}`. 기존 운영1.30.24와 private 설정/DB·키·native 계정은 그대로이며 이 source를 운영에 반영하려면 SQL102·backend/frontend release와 별도 승인된 표준 배포가 필요하다.


## 1.30.24 final account-entry and worker release receipt (2026-10-23)

- **Exact release:** `15d54c9b906f633142b63a82b5f66a146bce465f`, source digest `8aa0f09e7776e70a0d2ffcbeaad426dc42157bc08e7e8e0b39fd4ddf1a8b8b60`/3429files. Dev39841587452·tag images39842479613·Helm39842479478은 같은 SHA로 success이고 세 version/latest image digest가 같다. Helm version/appVersion1.30.24·digest `53af6b8a0f1c8328fc9077dceec3131ae9d58df0025e5e2bb3205d4269e0f22a`를 직접 조회했다. Exact arm64 API/worker/frontend binary/version과 published amd64 worker의 actual scheduler idle tick을 실행했다.
- **Full native command:** 배포서버172.30.0.50 `/etc/kolla`에서 전체 `/etc/kolla/multinode`, afterglow tag/skip haproxy로 표준 pull→prechecks→reconfigure를 수행했다. --limit·controller deployment wrapper는 없으며 최종 원문은 `artifact://1836`이다. 마지막 recap은 c1 ok124/changed5, c2/c3 ok68/changed2, 전체 failed0/unreachable0이다. 버전0.23과0.24는 같은 schema/policy code이므로 추가 DDL·별도 cold drain 없이 기존 cold0.23 recovery point를 유지하고 새 single-transaction SQL/per-key atomic Redis restore를 검증한 뒤 적용했다. 이 hot capture를 전역 동시시점의 cold snapshot이라고 부르지 않는다.
- **Fleet/data preservation:** Nine apps의 immutable refs/revision은 publication과 일치하고 API/frontend6 healthy·worker3 running/restart0이다. 비대상262/259/176=697개 ID/image/start/restart 무변경, native8개+provider client2개 effective fingerprint 일치다. Operator packages는 Kolla21.3.1.dev4/Lumen0.6.9/Drover0.4.15/Waygate0.3.5/palimpsest-client0.3.7 그대로다. 추가 native IAM/resource/quota write·key rotation·027 replay는 수행하지 않았다.
- **Actual runtime:** deployed optional-marker guard→real Nova all-tenants200·Keystone SDK domain first-page read가 성공한다. Direct dependency smoke는 caller authentication을 대신하지 않는다. 모든 controller는 issuer를117.16.137.210(public)으로 해석하고 real TLS discovery200을 반환한다. Source0.23에서 발생한 worker별 fastapi traceback68회는0.24 startup 이후 stdout/stderr를 합친 관측 창에서0이며 API traceback/legacy scope error/SQL1045·1054도0이다. Long-running error-free 또는 실제 Trove backup 생성·복원 증거로 확장하지 않는다.
- **Public/GUI:** current production health/signup-options/login-options200, signup/button/smtp/recovery=true, DMSLab organization provider1개, unauthenticated admin overview401이다. Actual current SSO buttons reach external GitLab sign-in; credentials are not entered. Browser response-listener worker reset으로 최종0.24 authorize response log가 사라졌음을 숨기지 않는다; exact authorize200/production callback/state/S256 metadata는 변경 없는 auth code/config의0.23 receipt에 있고0.24는 실제 settled provider page를 캡처했다. Synthetic compiled visibility save/direct-signup/390px checks는 별도이다.
- **Canonical gates:** worker-only real Redis/registered WorkDispatcher idle tick 후와 local/native runtime 후 각각 `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate` exit0. Backend9008passed/95skip, frontend432files/4978tests, contracts181, functional166passed/33deselected, Ruff722. Missing FastAPI를 검사하는 source-text/의존성 wiring test는 만들지 않고 actual minimal worker image path를 실행했다.
- **Local:** 같은 source의 backend/frontend 두 개만 canonical Compose --no-deps/--no-build로 교체했다. 실제 기존 DB값을 process override로 명시해 complete backend/frontend definition hash를 재현하고 old/new read-only/network-none image의12개 native/provider field를 비교했다. Private env/config file·기존 actual target·16개 local peers·Lumen legacy pin을 유지했다. Local public signup=false는 기존 source config를 보존한 값이며 production=true와 혼동하지 않는다.
- **Limits:** fresh real-user app administrator session, final OIDC callback/native canonical identity exchange, actual mail delivery/receipt/redeem, real Cloud Shell terminal은 이번 acceptance에서 실행하지 않았다. Mail SMTP TLS/auth만 확인했고 비밀번호/코드/토큰을 읽거나 replay하지 않았다. gbrain CLI 부재로 index sync/검색 guidance 성공도 주장하지 않는다.

Evidence: `~/.local/share/afterglow-proofs/ship-compat-20261022T135044Z/{final-release-13024-verification.json,native-fleet-13024-acceptance.json,local-13024-exact-target-cutover.json,worker-13024-real-idle-tick.json,worker-13024-amd64-real-idle-tick.json,post-13024-sanitized-log-summary.json,production-13024-public-and-sso.json,test-gate-13024-post-runtime.log}` and the archived OpenSpec verification receipt. Source0.23 qualification below remains its own historical scope.


## Account-entry regressions and independent signup visibility (1.30.23, 2026-10-23)

- 관리자 overview/domains/notifications503의 실제 stack은 `get_admin_os_conn:726`이었다. 실제 configured afterglow-service token은 project-scoped/admin role이 있지만 raw is_admin_project를 생략하며 operator admin project token도 같은 dialect였다. 기존 guard는503을 반환하지만 같은 native token의 Nova all-tenants list는200이었다. 수정된 exact function을 실제 runtime의 새 ephemeral namespace에서 실행해 guard 통과·native Nova200을 확인했으며 caller authorization은 이 smoke에서 대체하지 않고 별도 real-SDK authenticated regressions로 검증했다. False/null/string/number·wrong scope·revocation·logical workspace/transport 분리는 유지한다.
- 실제 SMTP STARTTLS와 AUTH는 성공했고 메일은 보내지 않았다. Signup options는 smtp_configured/recovery_enabled=true지만 public_signup_enabled=false/revision0/source default였으므로 UI가 발송 전에 막혔다. 사용자가 공개 이메일 가입 활성화와 별도 signup-button visibility를 승인했다. 메일 수신/one-use verification은 실제 mailbox 증거 없이 성공으로 주장하지 않는다.
- local에서 `dmslab_gitlab_domain` registry와 exact DMSLab domain policy(gmail.com/konkuk.ac.kr 자동 참여)만 protected operator source에 옮겼다. Default/GitLab.com registry나 다른 설정은 복사하지 않았다. 배포서버 전체 inventory에 표준 reconfigure를 실행했고 public login-options가 DMSLab provider1개, signup-options가 signup/smtp/recovery=true를 반환했다. Native gitlab/mapped→afterglow_gitlab_stable_sub user-only mapping과 enabled dmslab domain을 조회 확인했다.
- 최초 실제 authorize는 DNS가 사설172.30.102.117로 해석되어 unsafe_url422였다. 사용자가 DNS를 외부 경로로 변경한 뒤 같은 운영 authorize가200, production `/auth/callback`, S256 PKCE/state를 반환했다. 추가 hostname pinning·사설 CIDR 허용·SSRF/TLS 완화는 적용하지 않았다. 실제 GitLab sign-in 화면으로 handoff했으나 비밀번호를 입력하거나 user code/token을 출력하지 않았으므로 완전한 사용자 로그인 수용은 별도다.
- 새 visibility는 enrollment-policy DB 우선/row 부재 config fallback, global system-admin 수정 권한, public link projection과 direct signup/email/OIDC 독립성을 검증한다. 신규 조직 autojoin은 operator file proof와 저장된 manager signup policy를 교차하고 기존 membership early return을 유지한다. 현재 DMSLab SQL policy row는 부재/revision0이므로 승인한 file baseline을 임의로 막거나 새 manager policy를 만들지 않는다.
- Focused backend 첫 실행549pass/1skip에서 새 allowed-path fixture에 smtp_from_address가 없어2fail을 관측했고 fixture에 실제 설정 필드를 추가했다. 이후 canonical federation/admin transport222pass, actual Vitest 네 파일154tests가 통과했다. 처음 npm test에 selector를 추가한 호출은 별도 Node runner에 selector가 전달되어 실패했으며 actual Vitest 직접 실행으로 검증했다. 이후 같은 source의 정본 gate와 native full-fleet receipt는 아래에 구분한다.

### 1.30.23 actual release and worker runtime follow-through

- **Source/gate:** 불변 `v1.30.23` source `e009576418c1ab35b4a17a06aed6d49b493874eb`, source digest `37f6bddad77087e31fde4767ab0a3d16005d52fe83d797ed68e1f429fac6c8c1`/3429files. 사전과 compiled/native runtime 후 정본 gate가 모두 exit0였다: backend9008/95skip, frontend432files/4978tests, contracts181, isolated functional166/33deselected, Ruff722. Dev39832590773·tag images39833656959·Helm39833656781이 성공했고 version/latest digest parity, actual arm64 API/worker/frontend와 published amd64 API 실행을 확인했다.
- **Schema/data:** Old native API/worker6개는 native whole-group Ansible command로 함께 drain했고 원래 local writer도 중지했다. MariaDB10.11.19 network-none/tmpfs의 hot/cold restore에서102tables/4776rows, policyrow0, old/candidate ORM49개를 검증했다. Manifest101 checksum `a3a87b7b49994da90ee851120bb3210a1308c7dcfa0d33f7b91f74f69830392c`의 단일 ADD COLUMN만 운영에 적용했다. Shape는 tinyint(1)/NOT NULL/default1, 기존 policy projection·모든 table counts와 row 부재 fallback이 보존됐다. Redis1875keys를 암호화 capture했고 already-expired2개를 제외한 surviving1873keys의 격리 restore가 통과했다. 사전 manifest record 파싱 assertion은 DDL 전에 멈췄으며 실제 format을 적용한 뒤 한 statement만 실행했다.
- **Native fleet:** 배포서버172.30.0.50 cwd `/etc/kolla`, 전체 `/etc/kolla/multinode`에서 표준 `kolla-ansible reconfigure --tags afterglow --skip-tags haproxy`를 **--limit 없이 한 번** 실행했다(`artifact://1793`; c1 ok124/changed5, c2/c3 ok68/changed2, all failed0/unreachable0). API/frontend6개 healthy·worker3개 running/restart0, source/references 일치, 비대상262/259/176=697개 ID/image/start/restart 무변경과 native8개+provider client2개 fingerprint 일치를 확인했다. SQL101은 native IAM/resource/key 변경을 하지 않았다.
- **Actual boundaries:** 배포된 generator가 omitted-marker token을 받아 실제 Nova all-tenants200과 Keystone SDK domain first-page read를 수행했다. 이 직접 dependency smoke의 caller authorization은 false이며 fresh caller authority는 별도 real-SDK regressions에서 검증했다. Smoke-only identity.get_endpoint overload 및 raw catalog root404를 서비스 실패로 숨기지 않고 올바른 SDK list/discovery로 수정했다. Production public options는 signup/button/smtp/recovery=true, 실제 SSO 버튼은 authorize200·production callback·S256/state로 GitLab sign-in까지 연결됐다. Waiter30초가 먼저 끝났지만 최종 page와 retained response에서 handoff를 확인했으며 password/code를 입력하거나 출력하지 않았다.
- **Compiled visibility:** Exact arm64 frontend에서 synthetic administrator/API fixture로 public signup true를 유지한 visibility false 저장/revision11, quota unchanged, login link hidden, SSO/recovery retained, hidden 상태의 direct `/signup` enabled 및390px overflow0을 확인했다. 실제 production administrator save나 mail delivery proof로 세지 않는다.
- **Worker regression:** Docker stderr까지 합친 후 실제 각 worker에서 `db_auto_backup._execute_tick`→Keystone factory→missing fastapi traceback68회를 관측했다. stdout-only 조회의0은 건강 증거가 아니므로 폐기했다. 1.30.24 source는 worker group에 기존 API와 같은 FastAPI0.136.3을 직접 선언한다. Worker-only arm64 image와 isolated real Redis에서 registered WorkDispatcher의 실제 idle tick을 완료했다; 최초 fixture의 membership 미등록·Redis5.0 close API 오용은 harness에서만 수정했고 scheduler/authority guard는 바꾸지 않았다. 이 source의 전체 gate도 위와 같은9008/4978/181/166으로 exit0이며 final immutable publication/fleet receipt는 별도로 붙인다.
- **Local preservation/cutover:** 원래 local API는 먼저 같은 ID/image로 복구했다. 이후 기존 actual DATABASE_URL을 `AFTERGLOW_DATABASE_URL` process override로 보존하여 backend 전체 service hash를 정확히 재현했고 frontend hash도 같음을 확인했다. Network-none/read-only old/new image에서 native/provider12개 effective field가 일치한 뒤, 같은 executor/env로 canonical `up --no-deps --no-build --wait backend frontend`만 수행했다. 두 app은1.30.24/15d54c9b이며 healthy이고 private env/config 파일은 변경하지 않았다. 다른 local16개 container의 ID/image/start와 Lumen0.6.9 pin은 그대로다. 승인된 actual override 없이 다른 연결문자열을 해석하는 plain recreate를 하지 않는다.


Evidence: `~/.local/share/afterglow-proofs/ship-compat-20261022T135044Z/{admin-overview-investigation.json,admin-overview-real-executor-scope.json,actual-new-native-admin-guard-smoke.json,smtp-real-auth-without-send.json,email-signup-policy-cause.json,dmslab-native-federation-prerequisites.json,dmslab-manager-admission-before-rollout.json}`. 이 조사는 이전의 public health/login-page qualification을 authenticated admin/SSO/signup 수용으로 확장해서 해석하면 안 된다는 실제 회귀 기록이다.


## 1.30.22 native fleet reconfigure — actual production receipt (2026-10-23)

- **최종 source/release:** `222469e8409e352e9b92cd59ad15782f70daab54`, architecture source digest `231c2b2e95d5702be0eef2e72012d1385dd3d2a0a1cf967eca50f0733644df58`/3428files. Dev CI39814014218·tag images39816007942·Helm39816007832가 성공했고 API/frontend/worker의 version/latest digest와 revision을 검증했다. Helm1.30.22 digest는 `9eb235c3dc9e1e1b13ce3c06cc99b3679e3d7c8f7fb8694a040f06bbb1c93fb4`다. 실제 arm64 세 image를 별도로 build/run했고 표준 발행과 controller runtime은 현재 workflow의 amd64다.
- **정식 실행:** 사용자의 재확인에 따라 controller3 loop driver를 다음 mutation 전에 중지하고 진행 중 native precheck가 끝난 뒤, 실제 배포서버172.30.0.50에서 `/etc/kolla`를 cwd로 `kolla-ansible reconfigure -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy`를 **--limit 없이 한 번** 실행했다. 원문 `artifact://1672`의 controller recap은 c1 ok124/changed4, c2 ok68/changed1, c3 ok68/changed3이며 모두 failed0/unreachable0다. 앞선 per-host 기록은 진단/이전 시도이지 최종 전체 배포 완료 증거가 아니다.
- **Fleet:** API/frontend6개 healthy·Notion worker3개 running, 모두 release revision/digest와 restart0을 확인했다. Non-target container262/259/176개에서 변경·추가0이며 Lumen0.6.9와 다른 native service images/packages/datastores는 유지했다. 로컬 backend도 같은 원래 container ID/image로 복구해 healthy다.
- **정본 gate:** `VITEST_MAX_WORKERS=3 TZ=UTC npm run test:gate` exit0, backend8972passed/95skipped, frontend432files/4958tests, contracts181, functional166passed/33deselected, Ruff722files. Native-Zun precheck의 세 경계 회귀도 Kolla target에서 통과했다. 사전 실패와 환경 한계는 아래 기록을 지우지 않는다.
- **보존과 복구:** old API/worker6개 및 공유 DB의 local API를 drain하고 cold SQL102tables/4767rows exact-count restore와 cold Redis1861 surviving-key restore를 통과했다. MariaDB의 idle socket2개가 남아 첫 capture를 중단했으나, 각 socket이 ProxySQL backend pool 소유임을 확인했고 non-probe active query는 없었다. ProxySQL을 죽이거나 DB 연결을 강제 종료하지 않았다. Hot Redis의 논리 읽기/DUMP 경합은 read-only WATCH/EXEC 일관성 검증과 clone-side 원래 expiry 복원으로 해결했고 원본 실패 capture는 보존했다.
- **설정 이관 실패와 수정:** 첫 reconfigure의 bootstrap은 SQL1045로 실패했고 새 API/worker는 시작되지 않았다. Untouched c2/c3와 c1의 protected generated config를 복원해 기존 서비스 가용성을 회복한 뒤 조사했다. 기존1.30.19는 마지막 native zz layer가 operator source의 오래된 native-owned 값을 가리고 있었다. 새 single-effective-config 경로에서 그 값이 드러난 것이 원인이다. 비-native operator 값에는 차이0임을 먼저 확인하고 이전 native layer 소유 중복값만 source에서 제거했다. 실제 serving process 기준 DB URL·SECRET_KEY·Keystone password/user/project·Redis URL·backend port 여덟 fingerprint가 최종 세 controller 모두 원래 값과 일치한다. 같은 native Keystone origin의 root는300, 명시/v3는200이므로 `/v3`만 명시했다. 실패한 stopped-writer 시도 중 일시적 API 중단이 있었으며 이를 무중단 배포로 주장하지 않는다.
- **실제 HTTP/browser:** public health/site-config/login200, admin/users·chat/admin/providers·cloud-shell/workspace 미인증401, public capability chat/cloud_shell=true. 새 사용자 이름/이메일 로그인 화면을1440px·390px 실제 Chromium에서 확인했고 overflow0/JSerror0이었다. 실제 새 backend가 설정 그대로 전용 service user/project에 인증해 native Zun list200·Cinder read를 통과했다. 기존 Lumen provider key5건은 실제 legacy API container에서 decrypt5success/0failure이며 plaintext 출력과 provider 호출은 없었다.
- **범위·남은 수용:** 승인한 Cloud Shell 전용 프로젝트 재사용과 기존 서비스 계정의 admin 역할1건 외 native grant·resource 생성/이전은 없다. 새 프로젝트/network/volume/terminal container·registry secret 생성이나 quota 변경은 없다. 실제 사람의 password/OIDC/SMTP·로그인 후 관리자 흐름·live terminal/home 생성/reset·유료 provider 호출은 시험하지 않았다. 진단 중 ConfigParser section 열거가 DEFAULT credential-bearing 값을 상속해 도구 출력에 포함한 사고가 있었으며 값은 재출력/커밋하지 않았고 인프라 credential의 임의 회전은 하지 않았다.

Proof root: `~/.local/share/afterglow-proofs/ship-compat-20261022T135044Z/verification.json`, `native-fleet-reconfigure.json`, `fleet-after-native-reconfigure.json`, `fleet-effective-credential-preservation.json`, `cold-recovery-preserved-v3.json`, `actual-new-runtime-cloud-shell-native-proof.json`, `post-deploy-legacy-provider-decrypt-proof.json`, desktop/mobile PNG. Operator protected recovery: `/etc/kolla/.afterglow-rollout-backups/1.30.22/cloud-shell-enabled-20261023/` and its native-authority retry subdirectories.


## Cloud Shell Ansible exec correction (1.30.22, 2026-10-23)

The1.30.21 canonical precheck still failed its Zun/Cinder readiness assertion although direct execution of each native query passed. Installed `ansible-doc community.docker.docker_container_exec --json` confirmed that `command` is a string and `argv` is its list-of-strings alternative. The role's Python argument array now uses `argv`. A read-only actual Ansible play executed this exact helper through the installed module in the real controller1 toolbox and required the returned project ID and native readiness; both tasks passed with changed0/failed0. No stock toolbox package/image was changed. Earlier1.30.20/1.30.21 artifacts remain immutable; rollout targets the newly qualified patch, not a locally patched released role.


## Cloud Shell native precheck correction and approved preparation (2026-10-23)

The user chose to prepare Cloud Shell enablement and reuse the existing dedicated project. Current Keystone confirms the exact enabled `cloud_shell` project, its own Default network/subnet/router and default security group. A single approved direct admin assignment for the existing Afterglow service user was added to that project; no human grant, existing security-group rule, quota, project/network/volume/container or registry secret was changed. Protected operator input backups precede the explicit image/network/security-group/HTTPS/WSS configuration. All three controllers verified Keystone HTTPS200 and the Zun WSS origin's TLS certificate (ordinary HTTPS GET405; this is not a real exec WebSocket proof).

The actual stock `kolla_toolbox` returned exit2: `appcontainer list -f json` is not an OpenStack command. The role now authenticates and lists native Zun with its existing SDK/Keystone libraries, not an optional CLI plugin. Executing the exact helper in that real toolbox returned exit0 and `native_zun_list=ready` for the dedicated project. Three offline boundary regressions reject token project substitution before any Zun request, native403/503 or invalid list bodies, and credential-bearing exception publication. Runtime application behavior and schema are unchanged;1.30.21 contains the deployment-only correction and version metadata.

The selected public `openstack-client:slim` resolves to manifest `sha256:e98b344bad37f41bc381f5817248702062a0181a61bb0faf80a47a432b48d7df`, containing amd64 and arm64. Both exact-digest images executed `openstack-client-check`:13 commands passed, UID1000, Python3.12.15, OpenSSL3.5.7/TLS1.3. This is image/tooling proof, not a live user's terminal or provider invocation. The original moving-reference Ansible task failure remains preserved; direct execution of the same registry resolver on controller1 succeeded, so its censored root exception is not claimed as diagnosed. Explicit digest selection is the normal immutable production path, not a disabled precheck.


## 1.30.20 release CI timezone correction (2026-10-22)

Initial exact-SHA `e80824d6` CI run `39791276212` passed backend, contracts, functional and frontend shard1, but shard2 failed `HubArtifactsPanel.svelte.test.ts` because a test changed `process.env.TZ` after its Vitest worker thread started. The rendered worker-local UTC times were compared with explicitly Seoul-formatted expectations. The correction removes the ineffective late timezone override and compares the same UTC instants in the worker's actual local timezone; production formatting remains unchanged. The exact component tests pass when the process starts under both `TZ=UTC` and `TZ=Asia/Seoul`. The original CI failure is preserved; no check is bypassed or reclassified as success. Release publication and rollout remain gated on a successful final-SHA CI.

The follow-up strengthens that regression rather than relying on the worker's timezone: `vitest.config.ts` fixes `TZ=Asia/Seoul` before workers start and the assertion keeps an explicit Seoul formatter. From both UTC and America/Los_Angeles parent processes the two component tests pass; removing the production UTC suffix causes the native-timestamp test to fail from a UTC parent, then the source is restored byte-identical. A local unrestricted frontend run terminated with SIGBUS; the full frontend suite passes with the supported `--maxWorkers=3` override. Local loopback backend fixtures also observed an unrelated `/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary` POST; no backend assertions were weakened, and the affected thirteen selectors pass on their own. An attempted clean Linux gate on the operator host did not complete; its owned process tree and qualification directory were removed, no qualification datastore remained, and its result is not a pass. Exact-SHA GitHub CI is the Linux qualification boundary.


## Lumen 공유 DB 하위호환 단계 (2026-10-22, local deployment)

Proof는 `~/.local/share/afterglow-proofs/lumen-bounded-recovery-20261022T080822Z/`다. `diagnosis.json`, `kolla-baseline-before-drain.json`, `drained-backup.json`, `live-apply-result.json`, `kolla-restart-verification.json`, `connection-decrypt-preservation.json`가 핵심 receipt이고 harness·원본 실패 log는 모두 보존한다.

- **원인:** `lumen-api`의 반복 재시작은 PID 1에서 private child가 ready 안내 뒤 종료해 인증 readiness가 거부되는 문제였다(실제 binary를 격리 PID1로 실행해 재현하고 `--init`/PID7에서는 200). 수정된 source로 API/worker arm64·amd64 네 이미지를 정본 Dockerfile로 빌드해 모두 PID 1에서 인증 readiness 200을 확인했다.
- **호환성 증거:** 운영 Kolla `0.6.9`는 provider 행 credential 컬럼을 읽는다(운영 container의 model/repository를 직접 확인). 공유 DB에서 027이 이를 비워 6 provider 중 legacy API key 0건, 새 credential 표 5건만 남아 있었다. 운영 chat run은 2026-10-14 이후 0건이어서 사용자 요청 실패는 관찰되지 않았다.
- **복구 방식:** 일치하는 MariaDB `10.11.19` network-none 복원본에서 먼저 전체 repair를 리허설했다. 정확한 `0.6.9` 이미지의 ORM 읽기(6 provider, 5 ciphertext)와 legacy 형태 auth-attempt INSERT 수용, 동일 provider 두 번째 attempt의 `PRIMARY KEY(provider_id)` 거절을 확인한 뒤 운영 writer 6개와 로컬 2개를 정지하고 drain 이후 backup(5.9MB, 0600)을 새 MariaDB에 복원해 provider6/credential6/ledger28/run70이 일치함을 확인하고 실제 apply했다. Statement 3개 모두 앞뒤 stage guard를 통과했고 재실행은 `already_compatible`·0 statement였다.
- **보존:** 운영 Kolla 6개는 동일 container ID/image로 재시작해 모두 `healthy`다. 기존 provider API key 5건이 로컬 새 배포와 운영 container 양쪽에서 같은 키로 복호화된다(0 실패, plaintext는 출력하지 않음). 새 account/credential 표와 migration ledger 28행은 그대로다.
- **실제 로컬 배포:** 정확한 `0.6.9` source를 `LUMEN_BUILD_CONTEXT`로 빌드한 Lumen API/worker와 Afterglow backend/frontend를 `--no-deps`로 시작했고 migration job은 실행하지 않았다. 열네 개 로컬 service가 모두 up이며 backend의 ERROR/traceback/SQL1054은 0이다.
- **UI/설정 회귀:** `LegacyProviderAuth.test.ts` 13건이 provider 단위 route만 호출·account route 미호출·key 폐기·identity 변경 후 늦은 code 비게시·공유 경고를 검증하고, 의도적 mutation(account route로 우회)은 해당 test만 실패시켜 복원했다. 설정 test 4건은 보존 키·범위 누출 없음·생성 키 0600/미회전·pinned source·없는 source 즉시 중단을 검증하며 키를 공용 환경에 되돌리는 mutation은 해당 test만 실패시켰다. 기존 `page.test.ts`의 account-native fixture 8건은 실제 DTO의 `selection_policy`가 없어 새 분기에서 실패했으므로 fixture에 실제 필드를 추가했다.
- **정직한 정정:** 에이전트 작업 중 `LegacyProviderUI`와 `LegacySchemaRepairPlan`이 rate limit으로 중단됐으나 남긴 산출물은 모두 검토·검증했다. Harness는 SQL collation 순서와 Python 정렬이 달라 정상 상태를 불일치로 오판하는 결함이 있어(첫 리허설이 stage 0에서 중단, 어떤 statement도 실행되지 않음) 순서 무관 비교로 고쳤으며 원본 결과는 `rehearsal-result.json`에 보존했다. 컴포넌트의 만료된 message key `configuration.experimentalSharedByAllUsers`는 mock된 `t` 때문에 단위 test가 놓치고 `svelte-check`가 찾아냈다.
- **미검증:** 실제 provider 호출·OAuth·구독 인증·로그인한 관리자 화면(실제 비밀번호를 사용하지 않음)과 account 런타임으로의 승격·재조정. 이 단계는 운영 Kolla 이미지/설정을 바꾸지 않았다.

## Lumen private converter account UI (2026-10-22, local-only)

Unpublished local source: Lumen replaces runtime LiteLLM with owned Python request/metadata/child lifecycle and pinned Bifrost converters plus one-send HTTP; Afterglow supplies the authenticated BFF and administrator account panel. The earlier BFF selection passed **56 tests** and account component **11 tests**. A later final-source run across both admin-chat directories passed **140 tests / 9 files**, Svelte check **0 errors/16 warnings**, and i18n **0 errors/37 warnings**. The concurrent legacy credential fallback was inspected, not rewritten: native recognized `selection_policy` selects account management; absent capability selects provider-level authentication. Neither grants authorization.

The panel and `providerAccounts.ts` cover endpoint account/credential policies, explicit/priority/weighted admission, model-ID and operation restrictions, blank=null unrestricted versus `-`=[] deny-all, lifecycle secret clearing/stale-response fences, expiry/cooldown, local allocation usage and credential-specific token/device auth. BFF/native Lumen remains final authority; no browser selection can bypass generation/operation checks. Locale files are en/ko/ja/zh-CN/bn/ms/nb/sw/vi. Provider routes are no-store on success/handled errors and omit private URL/exception content in transport-failure logs. Metadata must never return stored key/token/ciphertext.

Final runtime qualification rebuilt root `Dockerfile` **backend and frontend for arm64 and amd64**, then deployed each pair through canonical production Compose with task-owned pinned-image overrides and isolated synthetic IAM/MariaDB/Redis/native Lumen. Both pairs passed **54 authenticated browser states each** (9 locales × light/dark × 390/768/1440), with native account data, explicit credential selection, masked keys and no measured horizontal overflow. **amd64 execution was emulated on the arm64 host; native amd64 hardware was not exercised.** Frontend IDs: arm64 `f4fe6b88…`, amd64 `46ed7afa…`; backend: arm64 `367866f9…`, amd64 `c8278728…`. Receipts: `/tmp/afterglow-images-20261022-final/results.txt`, `/tmp/afterglow-bifrost-{final,amd64}-matrix-receipt.json`. A fresh fixture lacked migrations, corrected by applying canonical migrations. Separately, intermittent host-loopback IAM503 after approximately 15 seconds has **unattributed cause**. Moving IAM to the container network preceded the successful runs but does not prove a fixture defect or rule out a rebuilt-backend regression; the new image includes concurrent dirty-tree backend edits, and no controlled comparison with old backend `8e019c85…` was performed. Successful matrices qualify only the container-network topology, not the failing host-loopback path. Earlier CRUD/device/inference receipts were not all repeated on these final images. No real provider/OAuth, legacy-server browser, project-switch race or production rollout acceptance is claimed. Lumen final gates: root3994pass/1known unrelated failure, SDK143pass, integration353pass, system31pass, Go test/vet clean; see Lumen `docs/testing.md` for exact boundaries.

**Host-loopback follow-up (supersedes the no-comparison statement above).** Old backend `8e019c85…` and new `367866f9…` each passed 100 TCP connections and 100 installed-SDK authority lookups (50 sequential + 50 at concurrency10 for each type) against identical synthetic IAM. Both images nevertheless reproduced browser-load HTTP503 after about15s with the same compiled frontend and configuration. Socket diagnostics observed `connect(192.168.65.254:18182)` timeout before HTTP authority response. A queue512 listener reduced the 500-connect stress maximum7.179s→0.035s but did not fix browser load; binding all host interfaces also did not fix it. Packet capture was denied by host BPF permissions. Root cause remains unconfirmed, not a demonstrated rebuilt-backend regression or a proven setup-only defect. No product changes were justified. Final host-loopback acceptance remains blocked. Evidence: `/Users/pieroot/bifrost-receipts/iam-final-comparison/` (`old.json`, `new.json`, `socket-diagnostics.log`, `conclusion.json`).


- [x] Parent final integrated source/SDK/Go and isolated MariaDB migration027/backfill/rerun/one-debit-allocation proof (counts and known failure above).
- [x] Matching Linux arm64/amd64 image build **and execution**, child lifecycle and canonical process-system acceptance (Lumen and Afterglow receipts remain distinct).
- [x] Compiled account UI → authenticated BFF → native Lumen, earlier CRUD/policy/usage/auth/privacy proof plus final-image nine-locale/theme/width matrices. These overlapping receipts are not a claim that every earlier action was repeated on final images.
- [ ] Separate authorized real-provider/OAuth and provider subscription-pooling permission, vendor invoice, cloud and production rollout gates.

Architecture freshness is recorded only in task-owned HEAD-plus-reviewed-path clones; the shared index and architecture markers remain untouched because unrelated concurrent work exists. This scope does not qualify all public WIP or a production release.


## 사용자 작업공간·관리자 chrome 분리와 Personal 표시 이름 (2026-10-22, local source)

Proof는 `~/.local/share/afterglow-proofs/console-workspaces-labels-20261022T060824Z/`다. 기존 사용자 선택기에 system-admin의 전체 native domain/project 관측이 섞이던 경로를 실제 membership directory·scope commit·remembered landing으로 분리했다. 새 회귀를 prior source에 실행한 `membership-before.log`는4fail/2pass였고, owner/native/projection·workspace·login6파일의 통합 focused 결과는253pass, 최종 native project role-only public capability·Rbac focus는225pass였다. Fresh current/remembered selector는 system-admin 관측 권한을 membership으로 삼지 않으며 관리용 provider/서비스 원본 transport 경계는 별도로 유지한다.

`workspace_http.py`·`workspace_smoke.py`는 production auth/project router·SQL/JWT·fake Redis, 설치 Keystone/OpenStack token SDK와 raw project PATCH의 실제 loopback HTTP를 사용한다. Synthetic alice(system-admin)와 bob(ordinary)이 각자 Personal/member로 로그인했고 alice directory에는 본인 domain/project만, 다른 Personal 선택과 비소속 domain 조회는403이었다. Label PUT는 `afterglow_display_name` 하나만 native PATCH하고 name/UUID/전체 기존 metadata·grant/quota write를 보존했다. GET·workspace·`/me`·fresh login에 같은 label이 나타났고 foreign-owner403·invalid422를 확인했다. Native directory/users/roles/quota는 합성이며 운영 Keystone writer permission/persistence 수용은 아니다.

관련 frontend6파일126behavior tests·i18n/build를 통과했다. 초기 Svelte check의 parent test 누락 token type을 고쳤고 동시 작업 ProviderAccountsPanel/catalog 상태의 일시 오류는 보존한 뒤 최종 check0errors/16기존warnings를 확인했다. 실제 브라우저 matrix는 backend public `is_manager`가 system-admin을 포함해 사용자 관리 picker를 노출하는 추가 결함도 잡았다. 실제 project manager/reader/member public capability로 수정했으며 별도 native system-admin guard·privileged API 권위는 유지한다.

정본 Dockerfile의 backend/frontend 양 architecture(arm64·amd64)를 실제 build·binary/helper 실행했다. 별도 QA project에서 `docker-compose.prod.yml run --no-deps --pull never frontend`로 만든 새 image를 실행하고 actual image ID·service·loopback8952·healthy를 확인했다. Production UI와 위 실제 API/native TCP fixture의9locale×실제2theme×6width(390/767/768/1023/1024/1440)108조건에서 user chooser의 home 비노출·본인1domain/1project·project-manager control 없음, admin header/drawer selector0·모드 복귀·overflow0을 검증했다. 실제 settings form으로 label 저장→header/chooser 반영→reload persistence와 ID/home/member 보존을 확인했다. 관리자 개요의 resource data는 이 fixture에서 미구현이라 클라우드 inventory 수용으로 세지 않는다.

기존 private config/공유 운영 DB·IAM·quota·실행 이미지는 건드리지 않았다. Source qualification의 canonical gate·matching architecture/staged guard·image IDs와 최종 정리는 같은 proof의 `verification.json`에 기록하며, synthetic native proof를 운영 rollout·실사용자 인증/영구 metadata write 수용으로 승격하지 않는다.

최종 source `f1f196a10d19d7866e0672628f3163badbb7f331c4cfcba0c1e905643b886e39`/3424files의 변경하지 않은 `npm run test:gate`는 exit0이었다: backend8972pass/95skip·frontend4945pass/431files·contracts181pass·실제 disposable DB166pass/33deselected·Ruff check/722files format. `auth access storage` named targets도 exit0이다. 없는 `network` target을 지정했던 첫 named invocation과 architecture copy/stamp race·동시 provider 작업 중 frozen snapshot 차이는 원래 log로 남기고 실제 source parity를 회복한 뒤 검증했다.

첫 substantive gate는 이전 system-admin UI write 기대2개와 native project-domain mismatch의503/403 분류1개를 잡았다. 사용자 public capability는 실제 project role을 따르도록 테스트를 이관하고 native proof mismatch는 기존403으로 유지했다. Full frontend gate의 이전 identity 기반 command-palette fixture는 실제 route surface를 명시하도록 바꿨고, 동시 ProviderAccountsPanel의 최신 localized mock 수정은 그대로 보존했다. 기존 provider-catalog retry test는 public draft 보존과 별개로 이미 구현된 one-use API key 폐기를 존중해 fresh key 재입력을 검증하도록 이관했으며 provider 구현을 되돌리지 않았다. 마지막 format gate가 지적한 existing Lumen contract 두 줄의 folding만 정리했고 assertions·network guards·test hooks·정본 gate를 완화하거나 skip하지 않았다. 모든 원래 실패·harness와 최종 receipt를 proof에 보존한다.


## 로그인 enrollment 스키마 복구 (2026-10-22, shared operational DB)

사용자가 보고한 password/native subject 성공 후 로그인500은 `domain_enrollments.personal_domain_name` 누락 SQL1054였다. 실제 local backend는 `172.30.0.11:3306/afterglow_kolla`, 운영3controller는 같은 Galera의 internalVIP `.253`을 사용했고 read-only 비교에서093의7컬럼·098의quota1컬럼·099의2컬럼과096 `domain_id NULL` 선행 조건이 없었다. 정책/intent table 존재와 health200은 기존 테이블 upgrade의 증거가 아니었다.

사용자 승인 뒤 `~/.local/share/afterglow-proofs/login-schema-recovery-20261022T050104Z/`에0700 proof directory·0600 SQL backup/config 복구본을 보존했다. Original image ID·effective env·DB/key/config를 capture하고 같은 MariaDB10.11.19·utf8mb3/collation/sql_mode의 network-none/tmpfs fixture에 consistent snapshot을 restore했다. Manifest093/096와 누락098/099 ALTER만 선별한7statement rehearsal 뒤102table row/count fingerprint 변화0·exact29column login ORM query 및 policy/intent6model query를 통과했다.

2026-10-22 **05:08:03–05:09:58 UTC**에 local API1개와 운영3controller의 API/Notion worker6개만 drain했다. Final protected recovery-point backup을 다시 만들고 그 backup의 격리 restore가 실제102tables/4697rows와 완전 일치함을 확인한 뒤, bounded10s metadata lock 아래 동일 DB/image/config executor로7statement를 적용했다. 새10컬럼·nullable domain·093/096 data UPDATE affected0을 확인했고 live102table data fingerprint 변화0이었다. 기존 journal·native user/home/password/federation/grant/resources·Redis/keys·sibling 서비스/datastore는 변경하지 않았고 migration ledger를 임의 생성/채우지 않았다.

같은 원래7container ID/image/env/key/config로 복구했다. 운영 API/frontend6개 healthy, worker3개 running(healthcheck 없음), local API healthy; 모든 mount는 destination-keyed 비교로 같았다(Docker mount array ordering만 달라진 diagnostic은 retained). Native 대상 user metadata/direct/effective grant fingerprint와 Personal binding도 완전 동일했다. Local 실제 backend의 enrollment29컬럼·추가5model ORM SELECT/ROLLBACK, 운영3controller의 VIP readback29컬럼·nullable, native Accounts/Personal resolution·member implication 안전성·정책2vCPU/4096MiB/1024GiB read를 확인했다.

같은 image의 canonical `app.bootstrap.main()`을 **복원·수리된 격리 snapshot에만** 실행해 exit0·기존 row 변화0·new table0을 확인했다. `http://localhost:3080/login` 실제 Chromium에서 username/password·provider catalog200·오류 alert 없음·가로 overflow0을 확인했고 local/deployed login GET200이었다. **Fresh 사용자 password는 읽거나 추측·재전송하지 않았고 실제 password POST200/Personal project 생성은 아직 검증하지 않았다.** 먼저 연 QA tab의127.0.0.1-only host fence가 configured localhost API OPTIONS를 막은 오류는 backend 요청0인 harness 진단으로 분리하고 올바른 origin으로 새 tab을 열었다. 초기 relay 미연결/fixture missing import, 실행 harness/원래 실패·백업·SQL·schema/row·runtime/native receipt는 삭제하지 않았다.

배포 후보 backend의 실제 model module 전체를 import해 SQL reader의49tables/586columns와 live schema를 읽기 전용으로 대조했다. Missing table/column0·model이 nullable인데 DB가 거부하는 column0이었다. 이는 후보의 명시적 ORM model 저장소 선행 조건 검증이며 독립 native 서비스 schema·실제 새 사용자 인증/프로젝트 생성·모든 외부 API policy 수용을 포괄하지 않는다.

이번 작업은 **현재 공유 Afterglow DB의 schema-before-writer 선행 조건 복구**이지 신규 image release/push·전체 생태계 배포 또는 old/new auth semantics의 rolling compatibility 수용이 아니다. Source/설정·버전·image contents는 바꾸지 않았으며 기존 qualified source gate를 이번 운영 로그인 성공으로 재사용하지 않는다. DDL implicit commit 뒤 image만 내리는 rollback은 보장하지 않고 보호된 recovery point·writer drain·unresolved journal/새 nullable-row 검토가 필요하다.


## 검증된 가입·OIDC Accounts 자동 연결 (2026-10-22, local source)

Proof는 `~/.local/share/afterglow-proofs/verified-account-entry-20261022/`에 보존한다. 기존 token/graph-lease 경로를 재사용하고 email형 username의 case/IDNA/trailing-dot cross-alias 및 unresolved 생성의 이름 충돌을 보완했다. 신규 회귀를 old source에 실행해 signup6fail/2pass, OIDC8fail/6pass를 확인했고 수정 source의 signup/federation/provider/organization·K8s/Helm generation389개와 정확한 frontend4파일115개를 통과했다. 최초 frontend 명령은 npm compound script에 selector를 전달해 Vitest4888개는 통과했지만 뒤 Node test가 TS selector를 받아 실패했다. 정확한 `npx vitest run`과 최종 정본 gate는 이 harness 오류와 별개로 기록한다.

`entry_http.py`·`entry_smoke.py`는 production router/SQL/JWT·fake Redis, 실제 SMTP TCP, signed OIDC discovery/token/JWKS TCP, 설치된 Keystone user client와 OpenStack native-token SDK TCP를 실행한다. Proof 없는422/404·검증 전 create0·이름중복409→동일 delivered token으로 unique 가입200·token 재조회410·이메일중복409를 확인했다. OIDC unverified403→동일 Accounts 계정 자동 연결200→재로그인200, native attachment PATCH1·canonical UUID/home/personal/member 보존을 확인했다. Native domain/grant/quota·발신 mailbox·IdP 데이터는 합성이고 실제 운영 SMTP/Keystone/provider 수용이 아니다.

Compiled adapter-node Chromium에서 실제 SSO 버튼→합성 IdP browser authorization→signed callback·native SDK→기존 alice의 Personal/member dashboard를 확인했다. 실제 SMTP 링크로 가입 페이지를 열어 중복 이름 안내·password/confirm 공란→다른 이름과 fresh password로 계정 생성, 신규 user native readback과 anonymous terminal state를 확인했다. 첫 QA wait의 잘못된 완료 문구/대기 timeout은 실제 관측한 terminal DOM·tab-local session과 분리해 receipt에 기록했다. Login은9locale×실제2theme×390/768/1440px의54조건에서 내부 Accounts 안내 없음·credential control 유지·overflow0이다. Build/i18n check exit0. 초기 fixture의 구 FastAPI event API·누락 SQL provider table/readiness·native POST dispatch·default origin 오류는 소유 harness에서만 수정했고 raw log를 보존했다. 운영 image/schema/IAM/credential/quota/resource는 변경하지 않았다.

Tenant manager가 자기 issuer에서 기존 조직 멤버의 Accounts 이메일을 verified로 주장하는 공격 회귀는 trust 제한 전1fail(DID NOT RAISE), 운영자 registry만 자동 연결하도록 제한한 뒤 통과했다. 최종 signup/federation/provider/organization/recovery·K8s/Helm focus424pass를 확인했다. 조직 관리권·SQL provider allowlist만으로 native association이나 로그인 권위를 얻지 못하며 실제 운영자 file-provider HTTP 수용과 별개로 검증한다.

아홉 locale에서 같은 username retry 경로를 반복하던 permanent test는 한 behavioral regression으로 합쳤다. Locale/theme/viewport 검증은 위 실제 Chromium54조건에 남기고 최종 gate의 frontend 개수는 이 중복 제거 후 source를 따른다.

최종 source `0251226e20520a0c39a84100611551b8f67927360402c3306a57bc7713869ec2`·3416files의 변경하지 않은 `npm run test:gate` exit0: backend8918pass/95skip·frontend4880pass/428files·contracts159pass·DB functional166pass/33deselected·Ruff check/720files format. 최종 exact frontend107pass·Svelte check0errors, working/격리 staged source 일치·테스트 snapshot mismatch0·실제 shared index 불변을 확인했다. 중복 locale-unit row 제거 전 `369fb5...`의 별도 gate도 통과했지만 현재 source receipt와 구분한다.

최종 canonical gate·working/격리 staged source parity·archive receipt는 같은 proof의 `verification.json`에 기록한다. 기존 과거 gate 결과를 이번 source의 수용으로 재사용하지 않는다.


## 도메인 리소스·Flavor·개인 로그인 변경 검증 (2026-10-22, local source)

작업 proof는 `~/.local/share/afterglow-proofs/domain-resources-flavors-personal-login-20261022/`에 보존한다. 기존 source와 실행 frontend 이미지에서 직접 타이핑한 Enter는 합성 로그인 POST를 보냈으므로 사용자 화면의 실패 원인을 그 관측만으로 확정하지 않는다. Input event 없이 DOM credential만 채운 경계는 disabled submit·POST0으로 재현했고, submit 시 현재 control 값을 읽도록 수정한 뒤 같은 Chromium Enter에서 POST1·합성401 표시를 확인했다. 실제 OS 비밀번호 관리자의 동작이나 운영 사용자 비밀번호 수용은 검증하지 않았다. 새 regression은 수정 전1fail, 수정 후 LoginPage64pass이며 기존 pending·IME·owner/ABA·fresh-password recovery를 포함한다.

이전 source `fe482cd318aeef43c05a048bf39e75e9eb9e0622935b3be6758c3ee22e05e1b9`·3416files는 정본 gate에서 backend8854/95skip·frontend4875/428files·contracts159·DB166/33deselected·Ruff check/720files format을 통과했다(`test-gate-isolated-final.log`). 그러나 이 단계는 downstream Nova scope 정책을 집행하지 않았으므로 provider 권한 수용 증거가 아니다. 아래 native project-scope 정정 receipt가 최종 source와 downstream 수용을 대체한다. 이전 로그·실패와 실제 공유 index 보존 증거는 유지한다.

- 실제 Uvicorn resource router→설치 OpenStack SDK/Keystone client→합성 native TCP에서 domain A의2VM/6vCPU/12288MiB·2vol/192GiB, B 분리, zero-domain, marker2페이지·domain/project 교집합·volume type/size·422range·native404·hypervisor ownership을 확인했다(`resource-http-smoke.json`). Directory404→503 문제를 실제 SDK 예외로 고쳤고 reviewed public503 code가 중앙 sanitizer를 통과하도록 했다.
- 실제 flavor HTTP/router·설치 SDK·기존 same-host Placement evaluator·SQLite GPU quota에서 Public/Private parity, private native ACL 회수, quota0의 양쪽 GPU 거부·ACL 불변, max_unit와 down-host 차단을 확인했다(`flavor-http-smoke.json`). ID-only 실제 SDK Flavor의 선언 key를 wire metadata 존재로 오판하던 GPU usage는 실패2개→17pass로 수정하고 native extra-spec 조회 실패를 unknown으로 유지했다.
- Production auth/JWT/Redis/SQL·Keystone SDK TCP에서 ordinary personal, opt-in 저장→새 로그인 remembered, markerless Accounts admin의 직접 member personal을 확인했다. `personal-admin-native-system-http.json`은 logical personal 유지와 Keystone system exchange만 증명한다. Stock Nova2025.2는 이 system token을 거부했으며 현재 provider inventory는 아래의 명시적 configured admin-project executor로 정정했다. Consumer/credential·native sibling-service caller token은 승격하지 않는다.
- 실제 quota HTTP/production preview/apply·SQLite journal에서2/4096/1024 한도 적용·native readback·updated journal 및 usage 초과409를 확인했다(`personal-quota-http-smoke.json`). Native quota/directory는 합성이다. Frozen intent·기존 grant/리소스는 변경하지 않고 실제 운영 프로젝트에는 적용하지 않았다.
- Chromium에서 domain drill-down/selector A→B와 header personal project 불변, 전체 volume2/192와 상세 필터1/128 분리, hypervisor domain/project/flavor, private domain→정확한 project 선택/명시 grant, profile preference 저장/reload, source-default draft/save와 existing quota preview/확인/apply를 조작했다. Vite surface의9locale×light/dark×6width×3resource routes324조건과9locale×2theme×3width×3settings routes162조건에서 overflow0을 기록했다. Production adapter-node build 후5개 actual route와 Enter POST1→admin personal `/dashboard`도 확인했다. `compiled-mobile-policy-viewport.json`은 실제390×1000·overflow0이다. UI-only write fixture, SDK-backed resource fixture와 native auth/quota proof는 구분한다.
- `svelte-check`0errors/16warnings, i18n0errors/37key-order warnings·48namespaces/11187messages, Korean scan1199files/0lines, production frontend build와 target catalog validation을 통과했다. 번역은 원어민 검수 전이다. Initial source/fixture failures·PUBLIC_API_BASE 검증 환경 누출과 격리 venv의 관측된 package 파일 소실/복구 기록은 삭제하지 않았다. 한 authority gate에는 layer-build 임시 HTTP server로 외부 `exa.language_server ... RetrieveUserQuotaSummary` POST가 들어와 실패했으며 assertion/network guard를 바꾸지 않고 병행 도구 호출 없는 최종 동일 gate가 통과했다. 그 요청의 발신 원인은 확인하지 않았다.

운영 container/config/DB/schema/native 권한·quota·실제 사용자 credential과 형제 저장소는 변경하지 않았다. 새 source의 실제 운영 login/SSO·scheduler acceptance, 기존093/098–100 schema 호환성·배포, 저장된 관리자 정책/기존 개인 프로젝트에 제공 quota를 적용하는 명시 운영 절차는 별도다. Backend 코드 변경만으로 운영 누락 column을 우회하거나 기존 quota를 덮어쓰지 않는다.

### Native admin-project transport 정정

이전 완료 보고의 Keystone system exchange는 Nova 인가 증거가 아니었다. `provider-scope/`의 동일 login/JWT/SDK/TCP harness에서 upstream Nova2025.2 `servers:detail:get_all_tenants`·hypervisor·flavor-access 원문 rule을 실제 oslo.policy로 집행하자 personal login200 뒤 native system token은 각각 `InvalidScope`403이고 BFF inventory500·hypervisors500·ACL503이었다(`provider-scope-before.json`). 원본 정책 파일·URL·SHA는 `upstream-policy-manifest.json`에 보존한다. 설치 oslo.policy6는 scope enforcement가 unconditional이며 scope check를 끄거나 native policy를 수정하지 않았다.

정정 source의 명시적 fresh-admin-guarded configured project executor로 같은 actual HTTP 경로가 통과했다(`provider-scope-after.json`): 글로벌 VM2개·personal domain 한정1개, domain/project picker, hypervisor의 두 도메인 소유 VM, private ACL list200→add200→readback→remove204→빈 readback. 실제 native policy 통과 요청13회는 모두 configured provider-admin-project이고 사람의 native personal token은 전후 member·같은 user/home/project였다. System grant 회수 후 동일 JWT의 inventory403·추가 executor 인증0을 확인했다. 이것은 실제 route/dependency/SDK/Redis/SQL/HTTP·upstream rule 집행과 합성 Keystone/Nova directory/data의 경계이며 운영 Nova 서버 실행이나 실제 운영 계정 수용이 아니다.

Permanent installed-SDK scope regression은 이전 source에서1fail이며 이후 native executor validity·ordinary/revoked caller·auth/operation failure·exactly-once close를 포함한 focused338pass를 통과했다. Auth/access/instances/storage named targets도 backend869/1280/1369/887 및 frontend478/181/609/166pass다. Selector와 mixed monitoring의 native Drover/telemetry는 configured execution credential을 넘기지 않고 original caller transport를 유지한다. 최종 source/gate/staged receipt는 `provider-scope/verification.json`과 이 change archive에 기록한다. 운영 config·native IAM·database/schema·quota·runtime 변경과 commit/push/deploy는 없다.

정정 최종 source `87a7c491fb776c4b0b14a863f93be51a2568b0950988b1bd7db36a49518d5a5a`·3416files의 **변경 없는 정본 `npm run test:gate` exit0**: backend8869pass/95skip, frontend4875pass/428files, contracts159pass, DB functional166pass/33deselected, Ruff720files check/format. `provider-scope/test-gate-final.log`와 matching working/격리 staged guard·actual index 불변·tested source mismatch0 receipt를 보존한다. 최종 selector/caller-bound monitoring focus도332pass이며 runtime/SQL fixture 상태만 정리하고 실행 harness·upstream source·원 로그는 보존한다.

### Manila execution-project URL 정정

Nova scope 정정은 Manila 수동 client의 URI project 선택까지 검증하지 못했다. `_afterglow_token`은 executor인데 URL project가 logical Personal이면 실제 `/v2/{executor}/{personal}/shares/detail`404가 발생했다. `get_client`를 mock하지 않고 real installed SDK catalog→loopback HTTP를 쓰는5개 회귀는 수정 전 모두 실패했고 수정 후 Manila/file-storage 관련108tests가 통과했다(`manila-scope/http-regression-{before,after}.log`). Scoped `/v2/{executor}`·version-root `/v2`·metadata 없는 SDK current project를 검증하며, missing/empty native scope는 요청0으로 거부한다. 별도 quota target은 `/v2/{executor}/quota-sets/{personal}/detail`로 유지한다.

Production login/JWT/Redis/SQL/dependency/router·SDK catalog·실제 Manila HTTP client를 실행해 Personal/member 로그인200→`GET /api/v1/admin/file-storage`200과 native `/v2/provider-admin-project/shares/detail` 한 번을 확인했다(`manila-scope/manila-http-smoke.json`). Caller native project/home/member는 전후 동일하다. Native directory·share는 합성이며 운영 Manila 정책/파일 시스템 수용이나 모든 프로젝트 share inventory의 의미를 확장한 검증은 아니다. 소유 fixture/runtime만 종료하고 원본 harness·raw failure·receipt는 보존한다. 최종 source·canonical gate·matching staged guard는 `manila-scope/verification.json`을 따른다.

최종 source `10a663403843527e1385c99b293441ea933a4277d533a31be47eb0207ede1b4b`·3416files의 정본 `npm run test:gate` exit0: backend8874pass/95skip·frontend4875pass/428files·contracts159pass·DB functional166pass/33deselected·Ruff check/720files format. Storage target892backend/166frontend와 working·격리 staged architecture/source mismatch0·공유 index 불변도 확인했다. 첫 gate의 missing-Manila-endpoint 회귀1실패는 scope 없는 MagicMock fixture가 새 native scope guard에 먼저 걸린 것으로, explicit authenticated admin project만 제공해 원래 discovery-error assertion을 유지했고 원본 실패 log를 보존했다.


## 프로젝트 없는 관리자 로그인 응답 정정 (2026-10-22, local source)

최신 로컬 backend 로그의 2026-10-21 22:36:50·22:37:04·23:39:26 KST password login은 native exchange부터 session publication까지 성공한 HTTP200이며 바로 logout200이 뒤따랐다. 화면의 `login.sessionMismatch`는 frontend가 Accounts identity와 visible legacy 작업 domain·빈 project를 가진 관리자 응답을 거부한 경로다. 과거 native password401과 구분한다. `loginAuthState`는 서버가 보고한 system administrator·projectless·visible exact working domain인 경우만 수용하도록 수정했다. 일반 사용자 foreign organization landing과 관리자 invisible/project-scoped foreign landing은 계속 거부한다.

수정 전 authSession 회귀 2fail/23pass → 수정 후 authSession/authFlow/authVerification/LoginPage 135pass. 실제 Chromium에서 합성 login200 응답으로 동일 오류를 재현한 뒤 수정 후 `/select-domain`·Accounts identity 보존·project null을 확인했다. Chooser inventory API는 fixture 미제공으로 경고 상태이며 실제 프로젝트 선택 수용을 주장하지 않는다. 운영 비밀번호·native grant·schema·config 변경 및 container rebuild/restart/deploy는 하지 않았다. 실행 중 frontend 이미지는 이 수정 전이므로 실제 사용자 재로그인 수용은 아직 미검증이다. Proof: `~/.local/share/afterglow-proofs/projectless-admin-login-20261022/`.

같은 read-only 조회에서 Accounts 사용자의 effective assignment는 이전0에서2로 바뀌었고 personal project는 없었다. 운영 `domain_enrollments`의 누락 column은 그대로이며 일반 사용자 provisioning에는 별도 schema blocker다. OIDC callback409도 지속한다. 이번 source 수정은 이 두 문제를 우회하지 않는다. 로컬 backend의 시계열 수집은 Redis 기록, trash loop는 운영 Swift 영구 삭제가 가능한 writer이며 조회된 추가 로그에서 성공 purge/delete 기록은 없었다. 이 부재는 과거 삭제가 전혀 없었다는 증거가 아니다.

커밋 준비의 격리 전체 gate에서 backend unit8740pass/95skip·frontend4822pass 후 contract145pass/14fail을 관측했다. 공용 합성 directory가 Accounts home으로 이관됐지만 legacy Default transport fixture의 token/home는 Default인 불일치였다. 두 contract fixture만 legacy native home과 token home을 일치시켜 실제 identity/admin guard를 유지했고 exact 두 파일49pass를 확인했다. 제품 인증/인가나 assertion을 완화하지 않았다. 전체 gate 최종 결과는 `~/.local/share/afterglow-proofs/commit-current-20261022/`에 보존한다.


## 첫 로그인 personal 재개·member-only native policy·프로필 사진 (2026-10-21, local source)

Proof root: `~/.local/share/afterglow-proofs/personal-first-login-profile-20261021/`. 이 절은 아래 즉시 관리자 personal 생성에 대한 과거 receipt를 대체하는 후속 구현의 증거다. 기존 사용자·비밀번호·home/grant·운영 DB/schema/config·native IAM policy·배포는 변경하지 않았다. Commit/push/release도 실행하지 않았다.

- 실제 API/router·SQL journal·JWT/Redis·설치 Keystone SDK의 TCP 경로에서 admin create201은 `personal_project_deferred:true`/project null과 user만 저장했다. 잘못된 password401에는 project가 없었다. 첫 native project read에 안전한 pre-dispatch 중단을 주입해503 `personal_project_retry_available`을 얻고 fresh password recovery200으로 정확히 하나의 personal project·direct member만 만들었다. 반복 login200은 같은 project였다. Native directory·admin proof·SMTP·quota endpoint는 합성이다. `account-profile-http.json`.
- Compiled adapter-node frontend + 실제 위 API의 브라우저390px에서 첫 login503→password 공란·retry disabled→새 password 입력→`POST /auth/personal-project/recovery`200→Accounts identity/Personal active workspace chooser 및 project1개를 확인했다. `compiled-browser.json`, `personal-recovery-ko-390.webp`. `waitForUrl` glob helper는 올바른 chooser URL에도 timeout을 보고해 다음 observe와 network503/200으로 실제 결과를 확인하고 tool issue로 기록했다. 이를 제품 로그인 실패로 처리하지 않았다.
- 같은 compiled `/dashboard/account`에서 Gravatar 선택·생성·실제 file upload200, header와 card의 같은 loaded128px PNG, reload 및 fresh login 뒤 native image persistence를 확인했다. Active SVG upload422는 이전 이미지를 보존했다. Gravatar 외부 응답은404로 고정해 fallback을 검증했으며 실제 Gravatar 서비스 가용성은 검증하지 않았다. Native exact-self read 뒤 bounded service writer의 image-key-only PATCH를 썼다. `account-profile-http.json`, `compiled-browser.json`.
- 실제 지원 locale `ko/en/ja/zh-CN/sw/nb/ms/vi/bn`×light/dark×390/767/768/1023/1024/1440의108조건에서 실제 document locale, header/card 동기화·이미지 load·controls containment·가로 넘침0을 확인했다. `profile-responsive-matrix.json`, `profile-{ko-dark-1440,bn-dark-390,en-light-768}.webp`. 초기 unsupported-locale 시도는 별도 receipt로 보존하고 검증 count에 쓰지 않는다. 번역은 원어민 검수 전이다. 합성 harness가 제공하지 않는 기존 activity/sessions/keypair 섹션은 오류 상태였으며 그 기능 수용을 주장하지 않는다.
- Native Lumen·Drover·Waygate의 실제 Uvicorn capability HTTP + 설치 Keystone SDK loopback으로 personal member의 프로젝트 작업 허용·ordinary member 제외·operator `!`·system ceiling·reduced credential 거부를 실행했다. `*-personal-http.stdout.log`. Palimpsest native HTTP+SQLite+CAS는 package2개 publish/download 뒤 personal human의 own metadata DELETE204→그 package404, 다른 package shared blob download200·CAS bytes 불변을 확인했다. Key DELETE403/삭제권 위임422, global build/shared-layer DELETE403도 유지했다. Directory만 합성이며 모든 서비스 lifespan off, 실제 provider VM/VPN/inference는 실행하지 않았다. `hub-personal-http.stdout.log`.
- 최종 backend unit **8741passed/94skipped**, frontend 전체 **4818passed/420files**; 등록된 auth/access selector의 중복 제거 합집합 **1987backend/637frontend passed**. Backend는 private config를 읽지 않는 외부 cwd·public test env에서 같은 실제 source를 실행했다. Native affected Lumen757passed와 최종 personal26passed, Drover438passed와 최종 personal34passed, Waygate1230passed/2skipped와 최종 personal33passed, Hub412passed. Broad native 수치는 마지막 absent/null predicate 경계 추가 전이고 뒤 exact matrix가 그 변경을 재검증했다. `commands.json`, `*-affected*.stdout.log`, `*-personal-final.stdout.log`, `lumen-personal-postlint.stdout.log`, `backend-unit-current.*`, `frontend-unit-final.*`, `auth-access-*.stdout.log`.
- 복구 UI/status fixture와 public endpoint inventory의 새 password-proved recovery allowlist를 이관했다. Profile deferred response의 test type을 실제 union으로 바꿨다. 초기 실패 로그는 보존했으며 source 문구·빈 token 표현·copy를 고정하는 assertion으로 성공을 만들지 않았다. 일반 role API의 personal 승격/필수 member 회수/legacy 관리자를 다루는 regression은 guard 제거한 reconstructed-before에서6fail, 최종8pass로 확인했다. `member-guards-baseline-valid-adapter.*`, `member-guards-final.*`.
- Production frontend build·Svelte check0errors/기존16warnings·i18n0errors/기존37key-order warnings·scan1196files/하드코딩 Korean0, backend Ruff check/716files format, 네 native changed-slice Ruff 및 target registry validation 통과. 무관 경고·기존 native 전체 lint baseline은 숨기거나 재서식하지 않았다. 이번 변경의 full `test:gate`, DB functional, live password/OIDC/mail/네 서비스 deployment 수용은 미실행이다. Gbrain CLI/config가 없어 sync하지 않았다.
- 증거 보존 정정: 초기 cleanup은 harness 원본까지 지웠다. Append-only 실행 기록에서6개 원본과 account harness의 두 후속 patch를 복원해 `harness/executed/`에 보존하고 SHA-256·기록 위치를 `harness-manifest.json`에 남겼다. `harness/`의 재실행본은 account의 base import와 launcher의 durable cwd 인식 두 경로 가정만 바꿨고 `topology_http.py` 의존성도 함께 보존했다. `commands.json`의 실제 실행 command/cwd는 변경하지 않고 `replay_command`/`replay_cwd`·manifest/source 경로를 연결했다. 보존 경로에서 네 서비스 native HTTP와 새 account 재현 driver를 실제로 다시 실행해 모두 통과했다(`*-preserved-http-replay.*`, `account-profile-preserved-replay.*`). Reconstructed-before의6fail은 당시 source에 대한 과거 증거이며 text-sensitive 원본 plugin을 미래 source에 그대로 적용해 같은 수가 나옴을 보장하지 않는다. 이후 cleanup은 source를 지우지 않는다.

**Personal kind 운영 호환성 미검증:** 현재 Afterglow `account_spaces._shared_domain`은 optional kind의 키 부재와 명시적 null을 모두 수용하지만 네 native 서비스는 키 부재 또는 정확한 `personal`만 수용하고 명시적 null은 거부한다. 실제 Afterglow 함수를 호출한 `harness/personal_kind_probe.py`/`personal-kind-admission-audit.stdout.log`가 두 경우의 수용을 확인했다. `native-accounts-readonly.json`의 null은 진단 projection의 기본값이므로 운영 native JSON에 키가 없는지, 실제 null이 저장됐는지 구분하지 못한다. 따라서 운영 Personal이 네 서비스와 호환된다고 주장하지 않는다. 배포 수용 전 raw exact domain 응답의 key presence/type/value와 실제 personal-owner 권한을 별도 검증해야 하며, 이번 증거 보완에서는 native metadata나 운영 계정을 수정하지 않았다.

### 보고된 Accounts password401 진단 한계

기존 오류의 정확한 단계는 native password exchange 거절이다. Read-only 운영 조회에서 exact Accounts의 해당 native user enabled, password row/hash 존재·expiry 없음, failed count0·lockout policy 미설정을 확인했다. Password hash/값은 읽거나 출력하지 않았다. 설치 Keystone `authenticate`는 password 검사 전에 user/lock, 뒤에 enabled/expiry를 판단하지만 당시 제출된 비밀번호 및 exact upstream 내부 사유는 로그에 없다. 현재 metadata는 과거 실패 순간의 password 일치를 증명하지 않는다. 설치 SDK의 합성 wire smoke는 정확한 Accounts UUID/username/password body와 outside-domain fallback 없음만 증명한다. `native-{accounts-readonly,password-metadata-readonly,login-failure-window}.json`, `accounts-password-wire-smoke.log`. 비밀번호 추측·로그인 재시도·reset/unlock·다른 home fallback을 하지 않았으며 운영 로그인 복구 성공은 미확정이다.

## 운영자 native Accounts·Personal 및 Accounts 로그인 (2026-10-21, local source)

이전 작업의 lowercase 자동 shared-domain 생성·관리 marker 요구는 이 후속 cutover에서 대체했다. 운영자가 CLI로 만든 실제 `Accounts`/`Personal`을 사용하고 domain 자체는 생성/수정하지 않는다. 신규 identity와 개인 member project는 exact 조회 UUID를 사용하며 웹 조직의 opaque native/display 이름 분리는 유지한다. 비밀번호 로그인은 Accounts 안의 username/email만 선택하고 다른 home으로 fallback하지 않는다. 기존 계정/password/grant·과거 journal은 자동 이동하거나 재바인딩하지 않는다. 운영 DB/schema/config·Keystone mapping·배포 변경은 실행하지 않았다.

Proof root: `~/.local/share/afterglow-proofs/operator-domains-20261021/`.
- `native-sdk-smoke.log`, `accounts-login-sdk-smoke.log`: 설치된 Keystone SDK → 실제 loopback HTTP → 실제 `ensure_shared_domains`/`password_account`를 실행했다. Operator 제공 UUID 두 개와 native Accounts user inventory query를 확인했고 domain POST/PUT 없이 동작했다. 표시 이름만 Accounts인 opaque domain과 다른 domain의 동명 user를 후보로 선택하지 않으며 outside-only alias는 credential 호출 전에 거부했다. Native cloud 데이터는 합성이며 운영 도메인/인증 성공 증거가 아니다.
- 실제 Vite 로그인 화면 Chromium390/1024px: Accounts 안내·기존 username/password·SSO/가입/복구 동선과 domain 입력 없음, document 가로 넘침0을 확인했다. `login-ko-{390,1024}.webp`. Frontend API 목적지는 격리 loopback의 닫힌 포트로 고정했고 실제 운영 로그인은 하지 않았다. 브라우저와 임시 frontend는 종료했다.
- LoginPage60tests와 frontend 전체4801tests/418files가 통과했다. i18n check0errors/37key-order warnings, scan1194files/하드코딩 한국어0. 변경된9locale 안내는 원어민 검수 전 초안이다. 문구 자체를 고정하는 테스트 assertion은 제거하고 form/요청/수명 동작 검증만 유지한다.
- 첫 affected backend run은634passed/11failed였다. Personal inherited grant fixture가 effective 조직 조회에도 raw domain grant를 주입한1건은 raw-only로 수정하고 exact regression1passed를 확인했다. 나머지는 Accounts 변경 전 home·native project-bound admin fixture 전제10건이며 최초 로그는 `affected-backend.log`에 보존한다.
- 최종 affected backend645passed. Scope-bound admin의 프로젝트 native source는 실제 exchange/publication fixture로 준비하고 unscoped proof CAS 뒤에는 현재 session과 비교한다. Role-visibility/token-binding의 immutable home fixture와 live integration consumer 응답도 Accounts identity/Personal workspace 분리에 맞췄으며 기존 권한/원본 token/회수 assertions는 유지한다.
- 최종 **backend unit8697passed/94skipped**, frontend4801passed, Ruff check 통과/714files formatted, production frontend build 통과, Svelte check0errors/16warnings5files. `backend-unit-isolated-corrected.log`, `frontend-tests.log`, `frontend-build-check.log`, `frontend-check.log` 참조. Backend는 repo의 private afterglow.conf를 로드하지 않는 외부 임시 cwd에서 같은 실제 source·전체 unit selector를 실행했다.
- 최초 repo cwd broad unit은300초 제한에 도달했고 정본 auth/access target은 private 설정을 로드하여 service_proxy._get_internal_endpoint가 외부 Keystone DNS를 시도해 network guard로 차단됐다. Socket stack 진단 `role-network-diagnostic.log`로 원인을 확인했고 network guard를 끄거나 허용 목록을 늘리지 않았다. 격리 cwd의 metadata67tests 통과 후 전체 unit에서 live integration fixture의 새 필수 identity 이름 누락16건을 수정했으며 최종 전체가 통과했다. 실패/timeout 로그는 보존한다. 이번 후속 작업에서 full test:gate·DB functional·live OpenStack은 실행하지 않았고 green 전체 gate/운영 수용을 주장하지 않는다.
- 새 schema/config/dependency 없이 native-domain 선택 및 공개 password-login 범위만 바꾼다. 필요한 운영 administrator도 Accounts에 있어야 하므로 production cutover 전 Accounts 계정/native system 권한과 실제 회원가입·OIDC·메일·비밀번호 로그인을 별도 수용해야 한다. Gbrain CLI는 설치되어 있지 않아 sync하지 않았다.

## Accounts identity-only·personal member 신규 생성 (2026-10-21, local source)

Proof root는 `~/.local/share/afterglow-proofs/accounts-personal-member-20261021-2qwxgyzv/`이다. 새 human은 native `accounts` identity-only와 `personal`의 본인 직접 `member` 프로젝트를 사용하며 관리자 관측 domain은 자동 조직 admission이 아니다. 기존 계정/home/password/federation tuple·조직 grant·과거 owner 기반 personal·singular account receipt는 자동 변경하지 않는다. 새 관리 marker 없는 기존 accounts domain은 자동 채택하지 않고 명시적 provenance 검토가 필요하다.

- 실제 TCP HTTP로 공개 등록202→수락200, 조직을 관측한 관리자 생성201, accounts를 관측한 관리자 생성201을 실행했다. 각 native directory에서 identity home=accounts, personal project 이름=username+하이픈+임의 소문자8자+숫자8자리, 직접 grant=member 하나, 선택 domain/identity Default grant 없음과 disabled staging 뒤 quota/readback·활성화를 확인했다. 세 계정 모두 설치된 native SDK의 loopback token HTTP를 거쳐 재로그인200·같은 personal 프로젝트·roles={member}·`/auth/me` can_write=true를 확인했다. `api-smoke.json`.
- 새 source의 compiled SvelteKit 관리자 `/admin/users`에서 실제 생성 버튼을 눌러 실제 loopback POST201을 얻었다. 결과에는 accounts identity와 실제 개인 프로젝트만 표시하고 관측 조직 admission을 표시하지 않았다. Native 상태도 해당 사용자 personal member 한 grant뿐이었다. `browser-verification.json`, `browser-created-native-state.json`, `browser-create-requests.json`, `admin-{create,created}-ko-light-1440.png`.
- 실제 modal의9locale×2theme×6width(390/767/768/1023/1024/1440px)108조건에서 document/frame 가로 넘침0·계정/개인/member 안내·footer 접근을 확인했다. 정확한 tutorial `statuses` fixture로 이미 dismissed인 사용자를 모델링해 Bengali dark390·English light768·Korean light1440의 가리지 않은 modal도 확인했다. `admin-create-responsive-matrix.json`, `admin-create-clean-samples.json`, 해당 PNG. 새 번역은 원어민 검수 전 초안이다.
- 지정 enrollment/member/foreign-authority/uncertain-write·OIDC 신규 생성·admin modal selector와 password 변경·unsafe member DAG·reserved accounts organization 설정 회귀를 실행했다. 최초 consumer fixture의 owner/reader 기대값과 native adapter의 필수 description 가정을 member/실제 optional native 계약으로 이관했고, unsafe-member 회귀는 앞선 invitation role 검증이 아닌 실제 personal guard를 통과하도록 분리하고 원인 예외도 검증했다. Wording/source-text assertion으로 변경을 검증하지 않는다.
- Frontend build와 `check`는 성공했다(`svelte-check`:0errors/16warnings, 기존5files). `i18n:check`는0errors/37key-order warnings, `i18n:scan`은1194files/하드코딩 Korean0이다. 무관한 경고를 감추기 위해 전체 catalog/기존 UI를 재서식하지 않았다.
- 최종 frozen source는 `aad0734700a3668fdf13a60471532b4f52ad922c0e30a0ba495c30e7650a6079`/3394files이며 working·소유 checkout의 staged architecture guard가 일치했다. Auth771backend/440frontend와 access1143/181은 통과했다. Formatting-only 마지막 정리 뒤 전체 `test:gate`는 backend8625passed/95skipped/1failed로 중단됐다. 실패는 `test_layer_build_ownership.py::test_native_create_response_loss_is_observed_without_second_post[port]`의 임시 TCP 서버에 `/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary` POST가 도착해 `unexpected` 검증이 실패한 것이다. 요청 생성 주체는 미확정이며 계정 계약 실패로 치환하거나 path를 무시하는 예외를 추가하지 않았다. 앞선 formatting 정리 전 backend8626passed 실행도 별도 보존하며 최종 full gate 성공으로 합산하지 않는다. `final-gate-{1,2}.log`, `gate-before-format-correction.log`.
- Full gate에서 도달하지 못한 같은 최종 source의 frontend4801(418files)·contract159·실제 일회용 MariaDB/PostgreSQL/Redis functional166(33deselected)·Ruff check/714files format은 각각 실행해 모두 통과했다. `final-remaining-lanes.json`. Svelte/i18n 경고와 전역 gate의 위1실패는 남아 있으며 skip/selector narrowing/경고 suppression으로 green을 만들지 않았다.
- `rapid` change의 planning status는 complete이고 `personal-domain-enrollment` main spec의 strict validation은 통과했다. Legacy `openspec validate --type change --strict`는 rapid change에도 delta-spec 파일을 요구해 거부하므로 이 명령의 성공을 주장하지 않는다. Main spec은 새 shared identity/personal member·관리자 관측·미래 project quota 계약으로 직접 동기화했다. Optional gbrain CLI와 detector가 설치되어 있지 않아 code index sync는 수행하지 않았다.

API/router·SQLite journals·JWT/Redis 로직·native SDK token transport와 compiled browser는 실제이며, Keystone directory/issuer/provider·SMTP·quota native endpoint 및 브라우저 관리자 identity/shell metadata는 합성이다. 사용자 실행 stack·운영 DB/Keystone/IdP·기존 credentials/grants·메일함·live GitLab code exchange를 변경하거나 검증하지 않았고 commit/push/release/deploy도 하지 않았다. 사용자 index/private 설정을 건드리지 않고 별도 public-source snapshot/개발 venv·loopback tmpfs datastore에서 검증했으며 전체 gate는 위에 기록한1실패로 non-green이다.

## Account·personal·organization와 서비스별 policy 검증 (2026-10-21, local source)

Afterglow proof root는 `~/.local/share/afterglow-proofs/account-topology-20261020-019qotth/`이며, 네 native 서비스의 독립 receipt는 `~/.local/share/afterglow-proofs/service-policy-20261020-{lumen,drover,waygate,palimpsest}-019qotth/verification.json`이다. 실제 source/API/SQL/SDK/이미지 실행과 합성 identity/provider 경계를 구분한다. 운영 IAM·계정·schema·배포나 실제 Nova/guest 수용을 뜻하지 않는다.

- 실제 Afterglow BFF가 loopback TLS native endpoint를 원래 credential로20회 읽었다. 현재 role을 바꾸지 않은 native capability 변경을 반영하고, 정상 빈 capability·한 서비스503·알 수 없는 capability를 구분하며 다른 서비스/core 권한을 유지했다. CA 검증을 켰고 identity와 upstream 정책 응답만 합성이다. `policy-bff-http.json`.
- 정본 standalone Compose에서 빌드한 arm64 frontend를 UID1001·healthy 상태로 실행했다. 실제 관리자 역할 화면의 미리보기와 별도 확인 전에는 변경이 없고, 확인 뒤 실제 역할 API가 legacy 서비스 edge67개만 제거했다. Role ID·직접 grant·project/custom edge·fixture 로그인 증명은 보존했다. `policy-compose-frontend.json`, `policy-compiled-browser.json`, `policy-after-explicit-apply.png`.
- 같은 compiled modal의9locale×2theme×6width(390/767/768/1023/1024/1440px)108조건에서 document/frame 가로 넘침0·viewport 안의 frame/적용 버튼·policy.yaml 안내를 확인했다. `policy-modal-responsive.json`, ko/light1440·bn/dark390 PNG. 새 번역의 원어민 승인을 주장하지 않는다.
- 최종 source를 별도 TCP API로 재기동해 실제 router·SQLite journal·native token SDK를 실행했다. 새 계정은 account home을 유지한 personal primary에 로그인했고, domain manager의 명시적 초대201→기존 계정 수락200→조직 scope200 뒤 `member`, `reader`, `project_member`, `project_reader`, `drover_admin`만 받았다. Drover leaf는 합성하지 않았고 identity home은 그대로였다. Manager 자신의 grant 없는 resource scope403도 유지했다. Mail·Keystone·quota 공급자는 합성이다. `integrated-account-policy-http.json`.

### Native 서비스별 독립 결과

아래 full/focused/SQL/system/SDK selector는 겹칠 수 있으므로 합산하지 않는다. 모든 서비스가 실제 oslo.policy6.0.1과 표준 generator를 실행했으며 API·worker canonical image를 arm64/amd64로 빌드하고 실제 nonroot 정책 읽기를 검증했다.

| 서비스 | 관측 결과 | 남은 경계 |
|---|---|---|
| Lumen | focused1036, root contract3815passed/1failed, SQL340, system31, SDK128, root/SDK Ruff 통과 | 기존 `test_v2_graph_interrupts_before_external_mutation_dispatch[expired]`는 `_v2_resume`가 denial 대신 `None`을 반환해 full contract가 non-green이다. 별도 graph 구현은 바꾸지 않았다. Nova guest 정책 파일 배포는 운영자 선행 조건이다. |
| Drover | focused595, full1595passed/3skipped, real Uvicorn/native policy·표준 generator·4image 정책 실행 통과 | Canonical lint의 기존 `configmaps.py:37 SIM102`, `cloud_shell.py:47 UP017`을 보존했다. 실제 cloud VM 생성은 하지 않았다. |
| Waygate | full1746passed/3skipped, parser/type/identity19, policy HTTP32, native MariaDB/Redis2,4image와 Compose API/worker 정책 실행 통과 | 기존 `tests/admin_executor_smoke.py:24,225 I001` 때문에 전체 Ruff는 non-green이다. 실제 WireGuard/cloud dataplane 수용은 아니다. |
| Palimpsest | Hub650passed/2skipped, native MariaDB process2, Kolla41, human-system HTTP49, Docker HTTP185checks/architecture,4nonroot permission probe·lint 통과 | Docker HTTP는 명시한 SQLite/lifespan-off adapter다. 별도 실제 MariaDB process 증거와 구분하며 full production Hub lifespan·KVM/Glance build·Kolla rollout은 아니다. |

Malformed native clause의 `not`/`or` 조합과 policy.d, YAML typed-value·casefold ID 충돌을 실제 engine으로 검사했다. 잘못된 파일은 반복 요청에서도503이며 수정 뒤 회복한다. Waygate의 before proof는 malformed negation6건의 잘못된200을 재현했고 after proof는503을 확인했다. Quoted empty/`@`/`!`의 표준 의미는 유지한다. Native6.x에서 제거된 `enforce_scope` override는 사용하지 않는다. Palimpsest는 root0640 비밀 TOML을 보존하고 실제 UID:GID1000:1000이 읽을 수 없는 상태에서 별도 root0644 정책 전용 TOML/YAML을 실행했다.

### User-data 관측 범위

Drover 실제 template의6plugin 활성화와1,004개 held role fixture에서 provider 위임은 `member`·`load-balancer_member` 두 개였고 서비스 role 문자열은 렌더링하지 않았다. 다음 값은 합성 callback/credential을 사용한 해당 fixture의 측정치이며 운영 payload나 Nova 제한 통과로 확대하지 않는다.

| Payload | 렌더링 문서 bytes | Nova decode 후 bytes | Base64 bytes |
|---|---:|---:|---:|
| Ubuntu server/6plugins | 78293 | 16480 gzip | 21976 |
| Ubuntu agent | 15227 | 4536 gzip | 6048 |
| FCOS server/6plugins | 30150 | 30150 | 40200 |
| FCOS agent | 8653 | 8653 | 11540 |

Drover callback은 role JWT가 아닌 고정 입력 길이의 난수 token이며, 일반 Nova adapter는 전달받은 userdata를 그대로 보낸다. 사용자 보고의 실제 실패 payload·설정 제한을 확보하지 못했으므로 원인·운영 해결을 확정하지 않는다. 새 압축 우회나 과도한 provider 위임을 추가하지 않았다. 기존 운영 service edge는 native policy 지원 배포/수용 뒤 명시적 관리자 preset으로 전환하며 이 검증에서 운영 IAM을 변경하지 않았다.


### Afterglow immutable image 실행

`policy-final-image-builds.json`의 frontend·backend·worker6개 arm64/amd64 image는 `febe1d1f43bc38c37c7390cd99faf27e1614219638c8d937118836cf27d34569`/3393files에서 빌드했다. 이후 consumer fixture 이관 snapshot `2af2c9b9…`와 API/worker 각 image의 실제 Python app323files를 byte hash로 비교해 차이0을 확인했다(`policy-final-runtime-source-parity.json`). 이미지를 final test-only source hash에서 다시 빌드했다고 표현하지 않는다.

`policy-final-image-runtime.json`은 실제 UID1000의 ASGI422/제거한 `personal_domain_name` 입력 거부와 worker의3개 topology model loading·crypto round-trip을 양 architecture에서 확인했다. ASGI는 lifespan-off·SQL sentinel 검증이며 실제 DB/native startup 수용은 아니다. `policy-final-frontend-image-runtime.json`은 stock UID1001 entrypoint에서9locale personal guide와 login SSR200을 양 architecture에서 확인했다. Compiled 관리자 modal의 이전 실제 browser proof는 앞의 별도 image/receipt 범위를 따른다.

### 필수 gate와 관련 target

최종 `npm run test:gate`는 source `2a563789902e6f79d136d063ad971b7dcc8840ede58f7cc268b101b5495262e1`/3393files에서 exit0이다. 기존 사용자 index·private 설정·실행 stack을 바꾸지 않고 별도 checkout/index와 lock 기반 dev venv, loopback/tmpfs MariaDB·PostgreSQL·Redis를 사용했다. Receipt는 `gate-1792526251428959000-results.json`, 원문은 `verification-gate-1792526251428959000-1.log`다.

| 검증 | 관측 결과 |
|---|---|
| Backend unit | 8618passed,95skipped |
| Frontend Vitest | 418files/4801passed; logger9tests도 통과 |
| Contract | 159passed |
| DB functional | 166passed,33deselected |
| Backend Ruff | check 통과,713files format 통과 |
| 관련 auth target | backend770/frontend440passed |
| 관련 access target | backend1137/frontend181passed |
| 관련 config target | backend507passed/1skipped,frontend12passed |
| Native-policy consumer selector | default-domain/Lumen-cloud-tools/Palimpsest-packages258passed |

Selector/target은 겹치므로 합산하지 않는다. 관련 target은 consumer fixture 이관 snapshot `2af2c9b9…`에서 실행했고, 이후 Lumen test file의 format-only 변경을 포함한 위 최종 gate가 전체 단계를 다시 통과했다. Node orchestration·Kolla·shell CLI 단계도 gate에 포함되며 PowerShell runtime 미설치36skip은 Windows 수용이 아니다. Native 네 서비스의 별도 full gate/lint 잔여 실패는 위 표와 독립이며 Afterglow exit0으로 덮지 않는다.

초기 검증 harness의 test/application schema 충돌·누락한 dev extra와 과거 BFF leaf fixture 기대는 실패 log에 남겼다. 실제 DB 분리 guard·native 정책을 약화하거나 오류를 숨겨 통과시키지 않았다. 선택적 gbrain detector는 `no-cli`/config 없음이므로 sync·CLAUDE guidance 변경·upload를 하지 않았다. 운영 migration·SMTP/OIDC/Keystone·Nova/guest 수용과 기존 서비스/IAM cutover는 별도 승인·사전조건이다.

두 rapid change는 일반 `openspec archive <change> --yes`로 `openspec/changes/archive/2026-10-20-separate-account-personal-organization`와 `2026-10-20-enforce-service-local-policy`에 archive했다. 두 명령 모두 task complete/exit0이며 delta spec 부재는 non-blocking warning으로 남았다. Main spec 동기화나 delta scenario 검증 통과를 주장하지 않는다. 전용 tmpfs DB3개는 정확한 project·service label과 무영속 mount를 확인한 뒤 force/volume 삭제 없이 stop/rm했으며 검증 원문·이미지는 보존했다.

## 태블릿·모바일 compact resource cards (2026-10-21, local source)

사용자·관리자 authored native table114files/146nodes를 Svelte AST로 대조해 `ResponsiveTable` 밖의 table0을 확인했다. 별도 div-grid 목록·wizard·modal/detail·chart 원본도 전환했다. 사용자가 작성한 Markdown의 임의 표는 애플리케이션 resource view가 아니므로 변환하지 않는다. viewport1024px 미만은 카드만, 이상은 table만 mount한다. 좁은 desktop panel 자체의 폭은 전환 조건이 아니다.

- 실제 source component와 원본 CSS를 격리 Vite/Chromium에서 실행했다. 인스턴스(사용자/관리자), 백업, DB, 키페어, 쿼터, chart 원본, loading을 구성했으며 data/controller callback만 합성이다. 320/390/767/768/1023/1024/1280/1440px × light/dark16조건에서 single branch·document/card 가로 넘침0을 확인했다. Viewport 변경 직후가 아닌 두 animation frame 뒤 geometry를 측정했다.
- 선택 상태와 quota draft23은 breakpoint 왕복 뒤 유지됐다. Native 상세 disclosure의 keyboard Enter, 인스턴스 start callback, 백업 삭제 후 해당 카드 제거, DB restart callback, quota compute `{cores:23}` submit을 확인했다. 1280px viewport의420px panel은 table을 유지했다. 긴 관리자 이름은 두 줄 clamp와 전체 accessible name/title을 유지한다. ko/en 화면을 확인했으며 locale 전체의 원어민 검수로 확대하지 않는다.
- 전체 frontend418files/4801Vitest 및 logger9tests passed. Focused responsive/volume/topology/admin-image4files111passed는 전체와 중복이다. Svelte2722files0errors/16기존warnings. i18n48namespaces11127messages0errors/37기존 key-order warnings;1194files hardcoded Korean0. Production build 통과. jsdom navigation-not-implemented 진단은 suite 실패가 아니며 숨기지 않았다.
- 증거 root: `~/.local/share/afterglow-proofs/tablet-resource-cards-20261021/`의 `source-table-audit.json`, `gallery-matrix.json`, `gallery-behavior.json`, `gallery-mobile-final.png`, `gallery-tablet-en-light.png`, `gallery-desktop-narrow-panel.png`. AST coverage는 모든 화면을 실제 cloud 데이터로 수용했다는 뜻이 아니며 browser smoke는 위 대표 component의 합성 상태다. Backend 변경·full `test:gate`·운영 배포·실제 provider mutation은 수행하지 않았다. 선택적 gbrain은 detect 결과 no-cli/missing-config로 sync할 수 없었다.
- 최종 production bundle도 별도 Node runtime에서 실행했다. Runtime `PUBLIC_API_BASE`를 합성 origin으로 지정하고 root→실제 console link→`/dashboard/compute/instances` SPA 경로로 진입했다. 1280px table→768px card 전환, `Compiled-user-worker`와 overflow0을 확인했다(`compiled-browser.json`, `compiled-user-instances-tablet.png`). 초기 runtime env 누락과 잘못 추정한 `/dashboard/instances` deep link의 asset 실패는 harness 오류였으며 성공 근거로 세지 않는다.
- Architecture working stamp는 `febe1d1f43bc38c37c7390cd99faf27e1614219638c8d937118836cf27d34569`/3393files다. `--staged`는 변경을 stage하지 않은 기존 index `3594c25d…`/3358files만 통과했으며 이번 변경의 staged qualification은 아니다. Rapid change는 [완료 archive](../openspec/changes/archive/2026-10-20-compact-tablet-resource-cards/tasks.md)로 이동했다. UTC 날짜를 사용하며 delta 없는 rapid schema 경고를 spec validation 통과로 세지 않는다. Commit/push/deploy는 수행하지 않았다.
- Compiled 카드에서 한 행을 선택한 뒤1280px table로 전환해 checked row1개를 확인했다. Tutorial 초대 overlay는 실제 ‘나중에’ 버튼으로 닫고 작업했으며 카드 선택 guard를 우회하지 않았다. Task-owned gallery/compiled service와 browser를 종료하고 throwaway source를 제거했다. 최종 receipt는 같은 proof root의 `verification.json`이다.

## 리사이즈 가로 스크롤·현재 플레이버 확인 수정 (2026-10-21, local source)

실제 `ResizeModal.svelte`와 공용 `Modal`·원본 CSS utility를 격리 Vite/Chromium으로 실행했다. Controller/provider 데이터만 합성이며 운영 source 배포나 실제 VM 변경은 아니다. 기존 panel은 `w-full`에 `mx-4`를 더해 내부 scroller452px/client 대비480px/scroll을 만들었다. Caller 중복 margin을 제거하고 FormModal과 같은 viewport-bounded28rem·select 폭 제약으로 수정했으며 overflow 숨김은 쓰지 않는다.

- 오류/빈 목록과 긴 flavor 선택지를9개 폭(320/390/613/677/767/768/1023/1024/1440)×2theme36조건에서 확인했다. 별도9locale×7width×2theme126조건에서 실제 선택 및 활성 submit과 가로 넘침0을 확인했다. Native option menu의 OS 표현은 브라우저 소유다.
- 기존 ResizeModal/InstanceHeader40tests passed. UI의 SHUTOFF 진입 제한·quota·confirm/revert 동작을 변경하지 않았다. CSS layout은 jsdom으로 검증할 수 없어 permanent class/source assertion 대신 실제 browser geometry를 보존했다.
- 증거: `~/.local/share/afterglow-proofs/resize-modal-20261021/{before.png,before.json,after.png,responsive.json,locales.json}`. Synthetic frontend fixture는 backend flavor 수정의 증거로 계산하지 않는다.
- 현재 flavor 오류는 SDK의 `original_name`→가상ID를 실제 native ID로 오인해 catalog lookup이 실패한 것이었다. Nova embedded allocation을 내부 PrivateAttr로 유지하고 CPU/RAM/disk/extra_specs를 resize 증분 기준으로 사용한다. Legacy resolver와 same-flavor·disk/quota 차단은 유지한다. Focused backend4selectors69passed. 실제 SDK microversion2.61→합성 Nova TCP에서 사용자/관리자 각 정상·catalog부재 listing200/POST200과 project-path same/disk/quota409·action미전송을 확인했다. Admin authority는 합성이며 native admin POST는 원래 계약 그대로다.
- `svelte-check`2714files0errors/16기존warnings. Backend Ruff check 통과; full `test:gate`·운영배포·실제 cloud credential/VM resize는 수행하지 않았다. 증거 root의 `verification.json`에 source/browser/SDK 경계를 구분한다.
- 최종 `npm run test:target -- instances`: backend1288passed, frontend38files/601passed(앞선 focused와 중복, 합산하지 않음). 변경 backend4files Ruff check/format도 통과했다. Architecture working/staged(private index) snapshot은 `93c438ba8df3341fa45bbe4e726981d37da62ea796a1d1f36b8cf3419f0c53ef`/3385files이며 실제 Git index는 보존했다. Task 외 동시 WIP까지 새로 검증했다는 뜻은 아니다. Browser·격리 runtime은 종료했고 throwaway source는 제거했다.
- 완료 tracker: [리사이즈 수정 rapid archive](../openspec/changes/archive/2026-10-20-fix-instance-resize-modal-overflow/tasks.md). Archive는 UTC 날짜를 사용한다. Commit/push/deploy는 수행하지 않았다.
- 추가 classic-scrollbar 검증: 좁은 viewport에서100vw 기반 폭은 실제 scrollbar gutter를 반영하지 않아333px scroller에343px panel이 넘칠 수 있었다. 최종 panel은 `width:28rem; max-width:100%`로 Modal의 실제 content box에 제한했다. Chromium의 forced scroll/gutter에서320/375/390/449/613/677/767/768/1023/1024/1440px11조건 모두 가로 넘침0(`classic-before.json`, `classic-after.json`). 위126locale는 직전 width식의 검증이며 최종 scrollbar-safe 폭의 추가 검증과 구분한다.
- 최종 scrollbar-safe CSS 변경 후 focused frontend40tests를 다시 통과했다. 최종 architecture working/private-staged snapshot: `a6c2d18ff8715e947055dc881fd0697db93fca3c0fc9bbde635d31118c2b0645`/3385files(`architecture-final.json`). 실제 index를 변경하지 않았다. 앞선1288/601 target·SDK 증거는 backend 및 직전 CSS 상태의 검증으로 보존한다.

## 인스턴스 이름·관리자 도메인 조건·빠른 chooser 검증 (2026-10-21, local source)

현재 `dev` source와 production frontend bundle을 task-owned loopback4179/4181에서 실제 Chromium으로 실행했다. 실제 Afterglow router→openstacksdk→합성 Nova/Keystone TCP를48181에 연결하고 별도 native Lumen dev worktree의 MariaDB/Redis SQL도 검증했다. Identity/admin 주장과 provider data는 합성이며 운영 인증·cloud mutation·release/deploy 수용은 아니다. 근거 root: `~/.local/share/afterglow-proofs/instance-admin-scope-20261021/`.

| 검증 | 실제 관측·경계 |
|---|---|
| 공용 이름 변경 | 일반 사용자 source UI와 관리자 source/compiled UI에서 저장 뒤 실제 native name-only PUT 및 새 header/list를 확인했다. 관리자 대상은 active project와 다른 프로젝트이며 global workspace는 바뀌지 않았다. Provider400 뒤 modal/draft/기존 이름 유지. `final-sdk-http.json`의13checks는 scoped native paging·foreign marker400·동일 domain/project 교집합, 사용자200/관리자200/foreign-user404/reader403/non-admin403/invalid422를 포함한다. |
| 기존 리사이즈 | ACTIVE에서 UI 미노출, SHUTOFF에서 사용자·관리자 양쪽 버튼 노출을 확인하고 기존 구현을 변경하지 않았다. 실제 resize/confirm/revert나 VM 전원 변경은 실행하지 않았다. |
| 독립 필터 | 관리자 Teaching/Beta 선택은 목록 요청에 `domain_id=domain-b&project_id=project-b`를 전달하고 Research/Alpha active scope를 유지했다. 다른 domain 선택은 불일치 project를 지웠다. 실제 quota page에서도 해당 domain의 project만 선택되고 domain 변경 즉시 이전 quota 값/선택을 지웠다. Native quota 값은 fixture이며 quota write는 하지 않았다. |
| Chooser cache | Source와 compiled 모두 첫 목록2reads, 즉시 다시 열기0, 이미 본 domain 재방문0, 명시 refresh2를 확인했다. Global active scope는 유지됐다. `workspace-browser.json`, `compiled-workspace-cache.json`. TTL·auth/authority ABA·closed cache invalidation과 uncertain-create 해제 금지는 controller/component51회귀에 포함한다. |
| 반응형·locale | 공용 rename modal의9locale×light/dark×390/767/768/1023/1024/1440px108조건에서 가로 overflow0, input/dialog viewport 내부 및 Field 도움말 접근성 연결을 확인했다. `rename-responsive-locales.json`과 ko390dark/en1440light PNG. 새 번역은 원어민 승인으로 승격하지 않는다. |
| Frontend | 전체413files/4769Vitest passed. Core scope/rename4files39passed, network/chat/flavor4files51passed는 전체 suite와 중복이므로 합산하지 않는다. Svelte2714files0errors/16warnings, i18n48namespaces11125messages0errors/37기존 key-order warnings, scan1192files0hardcoded Korean. `PUBLIC_API_BASE`를 합성 TCP origin으로 지정한 production build와 compiled rename/filter/cache smoke 통과. |
| 관련 backend target | `instances`1271passed, `storage`887passed, DB/containers/secrets/events/IAM/scope custom131passed. 이 selector들은 중복될 수 있어 합산하지 않는다. 마지막 custom에는 stale administrator claim의 Trove/Swift all-project 거부2경계를 포함한다. Exact rename/scope 초기6selector118passed도 별도 이전 관측이며 최종 source의 전체 gate 통과로 확대하지 않는다. |
| Native Lumen | 두 stats unit selector32passed, canonical disposable MariaDB/Redis의 stats-domain integration1passed. 별도 실제 native `/v1` Uvicorn TCP는35tokens/2distinct users/1conversation, exact project20tokens, foreign intersection0, offset/cursor와 non-admin403을 검증했다. `native-lumen-tcp.json`. Subject/admin 주장은 합성이며 canonical release checkout은 변경하지 않았다. |

검증 준비 중 새 Testing Library role query의 미지원 `exact` option·화살표 버튼 이름과 metadata 오류 copy 가정, auth remount 전 old DOM을 먼저 찾는 fixture race를 교정했다. 제품의 scope/auth fence를 낮추지 않았다. Fresh conditional administrator 확인으로 기존 Trove test가 외부 native를 호출하려던 시도는 network guard가 차단했고 정확한 boundary fixture와 stale-admin denial 회귀로 격리했다. Swift의 한 프로젝트401을 성공 부분 목록으로 허용하던 기대는 complete inventory의503/no-partial 계약으로 갱신했다. 초기 raw interception/입력 선택·quota URL의 cache query 누락과 native TCP smoke discovery 실패는 harness에서 교정했다.

Backend 변경21files와 추가 fixture3files의 Ruff check/format check는 통과했다. Native 변경5files Ruff check 및 직접 바꾼4files format check가 통과했으며 `lumen/services/stats.py`의 범위와 무관한 기존 uncached-token 산술식 formatting1hunk는 보존했다. 전체 `test:gate`·multi-arch image build·사용자 실행 서비스 교체·운영 DB/schema/native 자원/설정 변경은 이 작업에서 수행하지 않았다. Architecture working snapshot과 기존 index 검증은 구분하며 미커밋 사용자 변경은 stage/reset하지 않는다.

최종 working architecture는 Afterglow `99f41e08f0b2428553f1836ea7d2eebc321430dd903825aaba7e4fa8c4c72772`/3388files, native dev `034728a7cff47d22150691993fe875111b566faafd0cf2fef89105f7dca00acc`/424files다. Task-owned temporary index의 `--staged`도 각 working digest와 일치했고 실제 두 Git index SHA는 전후 동일했다(`architecture-review.json`). 실제 Afterglow index의 기존 `3594c25d…` 통과는 별도 baseline이며 이번 변경을 stage/commit했다는 뜻이 아니다. 선택적 gbrain CLI가 없어 sync는 수행하지 않았다.

Afterglow tracker는 delta 없는 저장소의 `rapid` schema다. `openspec status`의 두 planning artifact는 complete였으나 일반 strict validator는 delta 부재로 실패했다. 이 검사를 spec 검증 통과로 세지 않으며 rapid archive에는 저장소 절차의 `--skip-specs --yes`를 사용한다. Native change는 해당 delta와 sync한 main capability 모두 strict validate를 통과했다.

완료 tracker는 [Afterglow rapid archive](../openspec/changes/archive/2026-10-20-improve-instance-and-admin-scope-controls/tasks.md)와 native dev의 `openspec/changes/archive/2026-10-20-scope-admin-stats-by-domain`이다. Native main capability는 archive 전에 sync했다. Task-owned source/compiled/SDK HTTP service3개·fixture와 browser를 종료하고 throwaway runtime harness를 제거했다. 최종 요약은 proof root의 `verification.json`에 보존하며 commit/push/deploy는 하지 않았다.

## 상단 바 반응형 검증 (2026-10-20, local source)

현재 working source를 별도 Vite `127.0.0.1:4188`에서 실행하고 실제 Chromium으로 검증했다. Identity·auth/me·site-config·볼륨 API는 합성 fixture이며 Cloud Shell과 시스템 관리자 모드 버튼을 함께 표시했다. 운영 인증·Cloud Shell 접속·서비스 배포 수용 증거가 아니다.

- 320/375/390/639/640/767/768/1023/1024/1279/1280/1287/1373/1440/1920px의15너비에서 visible header controls의 pairwise 겹침·viewport/48px header 이탈0.
- ko/en/ja/zh-CN/sw/nb/ms/vi/bn × light/dark × 320/390/768/1024/1280/1373/1920px의126조건에서 같은 판정 통과. 1279/1280px 검색 trigger는 정확히1개다. 모바일 검색은 drawer에서 제공한다.
- 390px에서 drawer의 프로젝트 선택이 실제 workspace modal을 열고 drawer 검색이 command palette를 여는 것을 확인했다. Drawer Docs 링크 노출과1373px expanded search의 command palette 열림도 확인했다.
- 근거: `~/.local/share/afterglow-proofs/responsive-header-20261020/geometry.json`, 같은 디렉터리의320/390/768/1280/1373/1920px PNG. 사용자 실행 서비스·private config·DB는 변경하지 않았다. 전체 test:gate·운영 배포는 실행하지 않았다.
- `npm run check`를 실행했으나 도구가 반환한 background job의 완료 출력/상태가 회수되지 않아 성공 여부는 미확인이다. Architecture working stamp는 동시 locale 변경을 포함한3358source files의 `cd97ba983bc36dacf3f8c083a67c44b974460e076023a535bfdd658a73e39043`; `--staged`는 변경을 stage하지 않은 기존 index digest `3594c25d…`만 통과했으므로 이번 수정의 staged qualification으로 세지 않는다. 선택적 gbrain CLI는 없어 sync하지 않았다. Task-owned QA server/browser는 종료했다.

## 남은 실제 local dev source 통합 (2026-10-19)

게시된 `c893591dc0904e46b78be84685e3b2ace6f4dbfe`와 실제 공유 `dev` HEAD `3c9af255f7047c25d5ea8bcbf3d37d357634a134`의 잔여 작업을 대조했다. 외부 proof root는 `~/.local/share/afterglow-proofs/remaining-source-20261019-8kflhybg/`다. `capture-manifest.json`·public tar·원래 index와 private 입력의 hash/mode를 보존하고 최초 capture·현재 source·게시본의 각 대안을 분류했다. 게시본의 home-first/projectless·auth owner/ABA·원래 socket peer·명시 launcher trust는 유지하며, 이전 local-sync 절의 TOML trust 대안과 오래된 domain-first 문구를 현재 계약으로 되돌리지 않는다.

| 실행한 검증 | 관측 결과·경계 |
|---|---|
| 최종 필수 gate | `npm run test:gate` exit0. Reviewed source `3594c25d6d1ae9618311a154ac10a9802a7a01dfe81b6233fb50599553503bdc`/3358files에서 backend **8721passed/95skipped**, frontend **406files/4652passed**, API contract **163passed**, disposable DB functional **166passed/33deselected**, backend Ruff check·707file format check 통과. JS orchestration/Kolla/installer lane을 포함한 raw 근거는 `gate-receipts.json`·`test-gate.log`를 따른다. 중첩 selector는 합산하지 않는다. |
| Focused·static | Backend config/observer/traffic/proxy **362passed/1skipped**, frontend14files **451passed**. Svelte **0errors/16warnings**, i18n48namespaces/11112messages **0errors/37key-order warnings**. 기존 root standalone import-order2건은 backend-only canonical lint 범위 밖이며 숨기거나 일괄 restyle하지 않았다. `focused-receipts.json`과 해당 log를 따른다. |
| 정본9image build·실행 | backend/worker/frontend/native-vm의 arm64·amd64, native-cloud-vm의 지원 amd64를 build/load하고 실제 비특권 Python/Node ABI를 확인했다. Backend source parity와 worker 양 ABI crypto smoke를 통과했다. `image-build-metadata.json`·`image-runtime.json`; amd64는 Docker emulation이며 worker job·VM/KVM boot·운영 image 발행 수용은 아니다. |
| 실제 HTTP trust 경계 | Task-owned canonical dev Compose 두 arm64 service가 healthy. Native/SQL/background writer를 끄고 readonly 합성 TOML1개·logs tmpfs만 mount했다. 실제 API health200·retired domain login422·unauthenticated admin401, untrusted bridge peer의 spoofed HTTPS는 HTTP307, 실제 trusted loopback socket의 HTTPS는 HTTPS307이며 query를 보존했다. `runtime/{render-preflight,post-apply,http-smoke}.json`. |
| 실제 compiled metric·locale | 정상 root `/me` 검증과 완전한 scoped 합성 DTO를 사용하는 compiled MetricsPanel에서 서로 다른 날짜·동일 시각 두 점의 실제 차트/접근성 표가 full Korean date-time으로 구별되고 overflow0이었다. 같은 image의9locale Nova article200·34paragraphs·HTML lang과 login의 cookie/lang·domain field0·desktop overflow0, Bengali390px article overflow0을 확인했다. `runtime/browser-{metrics,locales}.json`과 screenshot; 번역은 machine draft이며 native 인증·실제 cloud 데이터 수용은 아니다. |

Synthetic UI 준비 중 builtin tutorial의 instance에 project ID가 없어 올바른 scoped metrics guard가 panel을 숨겼고, broad interception의 wildcard/우선순위·preflight 처리도 부정확했다. 제품의 권한 guard를 낮추거나 tutorial source를 바꾸지 않고 정확한 pathname·완전한 DTO·OPTIONS204를 사용하는 test-owned fixture로 교정한 뒤 위 실제 화면을 관측했다. 현재 사용자 credential·GitLab code·운영 token은 사용하지 않았다. 선택적 gbrain CLI는 없어 index/guidance sync하지 않았다.

Public source **136files**를 `88f84e56172e3c7933e70d26cd1dada2365f9fc2`로 커밋해 `origin/dev`에 정상 push했다. Actual checkout의 captured public tree에 exact134path patch를 적용하고 index가 target tree와 같은지 확인한 뒤 `3c9af255→88f84e56`을 reset/stash 없이 정상 fast-forward했다. 그 시점의 public worktree/index는 clean이고 private7inputs의 hash/mode, 기존18service의 ID/image/start/env/mount가 전후 같았다. `actual-source-delivery.json`·`actual-preservation.json`이 근거다. Staged Gitleaks는0findings이며 이는 pattern scan의 범위이지 비밀 부재의 수학적 증명은 아니다.

[완료 OpenSpec](../openspec/changes/archive/2026-10-19-reconcile-remaining-local-source/tasks.md)는 저장소 rapid 절차의 `--skip-specs --yes`로 archive했다. Delta 부재 경고와 archive 작업 자신의 미완료1항목 경고는 비차단이었고 실제 archive 직후 해당 checkbox를 완료했다. 후속 마감은 문서 전용이며 새 source/runtime qualification으로 세지 않는다. 기존 local 서비스·private/ignored 입력·다른 worktree를 교체하지 않았고 버전 bump·tag·main PR/merge·release·migration·운영 배포도 하지 않았다. 기본 브랜치 Dependabot high1 push 알림의 도입 여부·영향과 remote GitHub CI 통과는 이번 근거로 평가하지 않았다. 아래 과거 feature/release 수용 기록은 해당 시점의 증거로 유지한다.


## 실제 로컬 dev 아홉 언어 통합 (2026-10-19)

사용자가 승인한 full local sync는 원격에 이미 병합된 언어 지원과 실제 `/Users/pieroot/code/afterglow`·localhost3080의 차이를 해결한다. Base `aac6b9c5dc3e53fc3e430ca9ed96c30cacdbdb1e`, fetched target `3c9af255f7047c25d5ea8bcbf3d37d357634a134`; 공개 WIP snapshot `5035f4afbe132fd0d0d6797b93e668a1659b7d01`과 original index/manifest/tar는 외부 proof root `~/.local/share/afterglow-proofs/afterglow-local-dev-reconcile-wb61pysx/`에 보존한다. 격리 clone `/tmp/afterglow-full-dev-sync-0v3944hu`에서124conflict paths를 해결했다. Local domain credential/telemetry·background/storage·effective-config/cache 작업과 remote role/flow/fabric/MMDB·nine-locale 동선을 결합했으며 미커밋 작업을 remote에 게시하지 않는다.

검증 중 찾은 통합 오류와 교정:
- 초기 image의 새 다섯 언어 docs는 strict dictionary 누락으로500이었다. 기존 source에 추가된 gettingStarted7·coreGuides4문구를 언어별로 번역하고, UI의1011missing entries·63obsolete keys와 별도118entry domain-admin namespace를 동기화했다. 최종 키 비교는48namespaces에서 기존8translation locales 모두 missing/extra0이다. 새 번역은 원어민 검수 전 초안이다.
- Kolla는 local effective TOML을 읽고 backend env를 제거했지만 remote socket factory가 env-only proxy trust를 기대했다. Native `[app] trusted_proxies` 렌더링·Settings flatten·factory TOML fallback으로 결합했다. 명시 환경변수 우선과 빈 trust override를 보존하고 analytics CIDR로 인증 권위를 대체하지 않는다. Consumer181passed/1skip 및 실제 Uvicorn TCP에서 default/empty TOML HTTP307과 trusted TOML HTTPS307, query 보존을 확인했다.
- Chart fixture의 broad `.pointer-events-none` selector가 독립 SVG overlay를 잡아 실패했다. CSS class 존재에 의존하는 incidental test를 삭제하고 실제 data/lifecycle/decimation 회귀는 유지한다. Production chart 코드를 이 fixture에 맞춰 바꾸지 않았다.
- 일부 delegated worker가 상대 경로로 original checkout의 chart9·새 catalog46개를 실수로 쓰거나 stage했다. 소유 경로를 확인하고 중지했으며 별도 tar/index로 보존했다. 이를 사용자 변경으로 오인해 revert하지 않고 final semantic publication에 포함한다. Original baseline index는 clean이었으며 사용자 미커밋 WIP·private inputs는 보존한다.

격리 qualification: backend unit8694passed/95skipped, telemetry/config545passed/11skipped, disposable functional166passed/33deselected, orchestration166·Kolla18+Python13이 통과했다(서로 포함된 selector는 합산하지 않는다). Native config/import smoke는 version1.30.19와 중복 없는569API method/path를 확인했다. Final canonical Docker frontend arm64/amd64 build와 각각 실제 Node arch arm64/x64·app1.30.19를 확인했다. 두 runtime에서 모든9locale docs200·SSR lang·9choices·locale cookie를 확인했고 실제 Chromium에서 docs→login9locale 유지 및515×402 메뉴9choices·내부 스크롤·수평 overflow0을 확인했다. 실제 로그인·Keystone·BPF/SNMP·운영 rollout 수용이 아니며 backend는 이 작업에서 갱신하지 않는다.

최종 gate·실제 local cutover 결과는 이 절의 후속 receipt와 proof root의 JSON/log/screenshot을 따른다. 초기 실패·기존 jsdom navigation stderr, Svelte16warnings, i18n key-order51warnings 및 PowerShell 미설치 skip은 숨기지 않는다. 선택적 gbrain CLI는 PATH에 없어 sync하지 않았다.

Final `npm run test:gate` exit0: architecture `411604751ffd8910ae62a414e905d6be5a773f4891b8940980ad3f5080c0112f`/3359source files, orchestration166, Kolla18+Python13, CLI20passed/36PowerShell skipped, backend8694passed/95skipped, frontend406files/4615passed+9runner, contract163, disposable functional166passed/33deselected, Ruff check/format707files. Svelte check0errors/16warnings, i18n0errors/51key-order warnings·48namespaces/11110source messages, scan1181files/0hardcoded Korean. Working/staged architecture와 version1.30.19동기화도 통과했다. Gate raw receipt는 `artifact://230`, builds는 `artifact://221`, final multiarch/runtime/cookie/menu evidence는 proof root에 보존한다.

Actual local receipt: `dev` HEAD와 `origin/dev`는 모두 `3c9af255f7047c25d5ea8bcbf3d37d357634a134`이고 index는 그 remote baseline이다. 기존/통합 WIP는 uncommitted working source로 남겼다. 최초 binary apply는 검증용 root `node_modules` symlink를 기존 실제 directory 위에 쓰려다 중단했고 일부 replace-target5개를 제거한 상태였다. 새 dependency directory·private input은 건드리지 않았으며 exact partial manifest를 기록하고, 오직 격리 symlink를 source/index에서 제외한 잔여 patch로 복구·완료했다. 최종 source guard는 `a8d7e07589e5ab910b9687910763c5ae36e7ef0d46684906723f65bb4f114735`/3358files다. 이는 위3359file gate에서 source가 아닌 검증 symlink 하나를 제외한 정정이다.

정본 `.local-services/compose.env`·`docker-compose.dev.yml`·project `afterglow-local-services`를 같은 Python executor/environment에서 render/apply했다. Empty ingest key를 유지해 reporter는 비활성이고, obsolete trust-client=false 대신 direct Node listener의 peer-is-socket=true만 의도적으로 전환했다. `up --no-deps --no-build --wait frontend` exit0·healthy; 실제 frontend `c4bbd98a26034226577478749223fd559f9570bc8b10021c1318947aab585f7a`, final OCI index `sha256:c97f3317abdca9a37ea47245d86b9f2910e6e3b4acede5b0f15100dd79c93181`. Env·mount·port·group은 승인 render와 일치하며 private5files SHA와 비대상35containers의 ID/image/start/env/mount/port는 전후 동일하다. Backend ID `1774f385c6c108c0df7c706367e0478843910199c9a0f5375b88d396bfc91e88`·start `2026-10-19T07:52:40.974825006Z`를 유지했다. 기존 image object는 이미 없어 running frontend filesystem을 `afterglow-local-reconcile:frontend-rollback`으로 보존하고 native Node 실행을 검증했다. DB migration·backend/worker 재시작·운영 배포는 하지 않았다. 동시 사용자 activity나 기존 writer의 정상 DB 쓰기까지 없었다고 주장하지 않는다.

Actual Chromium localhost3080에서9locale의 docs→getting-started article→login→reload 언어 유지, main의 실제 Swahili button 클릭·닫힘·focus 복원·shared docs 선호를 확인했다. 실제 main 메뉴9choices,515×402 overflow0·내부 scroll104px 뒤 Bengali 접근,900×700 docs 메뉴 전체9언어 screenshot을 보존했다. 실제 public-flow browser errors0. `actual-nine-language-navigation.json`, `actual-main-language-click.json`, `actual-menu-after.json`, `actual-preservation.json`, `actual-docs-all-nine-languages.png`, `actual-main-menu-{after,last-language}.png`가 최종 runtime evidence다. 임시 arm64/amd64 frontend4개와 lifespan-off backend smoke만 종료했으며 사용자 canonical frontend는 healthy로 유지했다.

Post-rollout final gate도 exit0(`artifact://254`): scaffold를 제외한 `a8d7e07589e5ab910b9687910763c5ae36e7ef0d46684906723f65bb4f114735`/3358files에서 backend8694/95skip, frontend406files/4615+9runner, contract163, disposable functional166/33deselected, Ruff707files 통과. Actual root의 working guard·version1.30.19와 `/health`200/`status=ok`도 archive 뒤 다시 확인했다. OpenSpec는 `openspec/changes/archive/2026-10-19-sync-local-dev-nine-languages`로 완료 archive했다.


## 전체 공개 source dev 통합 (2026-10-19, local qualification)

`integrate-all-source-dev`는 요청 시점의 public snapshot과 최신 fetched `origin/dev` `3c9af255f7047c25d5ea8bcbf3d37d357634a134`를 격리 local `dev`에서 통합한다. 증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/commit-all-20261019-0meyzotw/`다. 아래는 **최종 통합 source의 새 검증**이며 이후 역사적 feature/release 기록의 실패·미수용 경계를 소급 변경하지 않는다. 공유 checkout은 작업 중 upstream과 동시 source가 갱신되었으므로 처음 index/source와 byte-identical하다고 주장하지 않는다. 초기 snapshot·변경 분류는 `original-source-manifest.json`·`shared-source-preservation.json`에 보존하며 현재 공유 source/index를 reset/stash하지 않는다.

| 실행한 검증 | 실제 관측·경계 |
|---|---|
| 필수 전체 gate | `npm run test:gate` exit0. Backend unit **8,709passed/95skipped**, frontend **406files/4,635Vitest +9Node passed**, API contract **163passed**, task-owned MariaDB/PostgreSQL/Redis functional **166passed/33deselected**. Ruff check·707file format check 통과. JS orchestration·Kolla·shell installer lanes도 통과했으며 PowerShell 부재로 그 installer36건은 skip 상태다. `test-gate-final.log`·`final-gate-receipt.json`을 따른다. |
| Frontend static·문서 | Svelte **0errors/16warnings**, i18n **48namespaces/11,112source messages/0errors/37key-order warnings**. Fail-closed docs/catalog·route·topology의 최종 focused4files/143passed. 기존 topology fixture는 raw token/scope 변경 후 root의 fresh authority 수용을 모델링하도록 고쳤고 private graph·late response 차단은 유지했다. 번역 review 승인은 올리지 않았다. |
| 실패 전후 회귀 | 이전 authSession source에서 명시적 project 제거 관련 **12failed/64passed**, 최종 focused **76passed**. Backend의 다른 working domain projectless 두 번째 refresh는 수정 전403이었고 수정 후 신규19개 경계 사례를 포함한 focused auth/K8s/proxy **126passed**. Nova guide 새5locale의4개 누락씩20개는 실제 fail-closed docs suite25fail을 만든 뒤 번역 보완으로 해결했다. |
| 실제 TCP 인증 경계 | `projectless-http-evidence.json`: 실제 Uvicorn factory/FastAPI/JWT·SQLite/fakeredis와 합성 native HTTP에서 legacy domain422, home 최초 로그인200, 조직 선택200, 프로젝트 권한 회수 뒤 반복 projectless refresh·`/me`·workspace200, working membership 회수403, 허용 workspace 재선택200, 원 native proof 회수 후 `/me`·refresh401을 확인했다. 권한 복원 write0·OAuth replay0. Native directory/IdP/cloud는 합성이며 lifespan을 꺼 startup writer는 없다. |
| 정본9image build·실행 | Root Dockerfile의 backend/worker/frontend·native-vm은 arm64/amd64, native-cloud-vm은 지원하는 amd64를 build/load했다. `image-build-metadata-qualified.json`과 `qualified-image-runtime.json`:9개 모두 요청 ABI의 비특권 Python/Node 실행, backend/worker/native7개에서 최종 변경 source hash 일치, worker 양 architecture crypto round-trip 성공. amd64는 Docker Desktop emulation이며 worker job·VM/KVM boot나 운영 image 발행의 수용 증거가 아니다. |
| 최종 image HTTP·화면 | Canonical `docker-compose.dev.yml` +task-only override의 두 arm64 container가 healthy. Native/SQL/background writer를 끄고 readonly 합성 TOML1개·logs tmpfs만 mount했다. 실제 API health200·legacy login422·unauthenticated admin401, compiled Chromium에서 domain input0·메인 provider0·단일 SSO 진입·같은 이름의 Default/dmslab2choices·복귀 시 password 삭제와 username focus·desktop overflow0을 확인했다. Public provider metadata는 합성이고 사용자 credential·positive GitLab/Keystone 교환은 실행하지 않았다. `runtime/`의 HTTP·browser·post-apply receipt를 따른다. |

통합 리뷰에서 K8s의 중복 `[traffic_analytics]` TOML table과 effective-config cutover 중 누락된 Kolla launcher `FORWARDED_ALLOW_IPS`를 수정했다. Projectless 경로는 native subject/home 검증 **뒤** fresh selected-domain overlay를 사용하며 scoped-native 불일치·계정/home·membership/native proof 회수는 계속 차단한다. Frontend는 명시 null/빈 project를 제거하고 생략은 보존하며 old-owner/ABA를 수용하지 않는다. Getting Started9locale는 domain-free password·별도 SSO·home-first 선택과 과거 screenshot 표시를 맞췄다. Local scratch script/credentials·QA runtime은 public source에 넣지 않는다.

첫 통합 gate는 frontend의 docs 누락과 fresh-readiness 미설정 fixture에서 중단했고, Ruff import/format도 교정했다. 위 최종 gate와 image source 검증은 그 수정 뒤의 결과다. Browser fixture의 구형 `/login/options` 가정은 실제 `/login-options`로 바로잡았고 오래된 user relay는 재시작하지 않고 전용 Chromium을 사용했다. 운영·native 권한/계정/볼륨을 수정하거나 SQL090–098을 적용하지 않았다. Schema-before-writer·old cohort drain·실제 native federation/SMTP·migration 복구·운영 배포 수용은 별도 승인/검증이 필요하다. 이번 범위는 public source commit/push이며 version bump·tag·main PR/merge·release·서비스 배포는 하지 않는다. 선택적 GBrain CLI 부재로 sync/guidance 변경은 수행하지 않았다.

Public source commit `ceba25a29695cf6debfa0b2cc8acb48ad60d7e0f`를 `origin/dev`에 정상 push하고 rapid change를 [2026-10-19-integrate-all-source-dev](../openspec/changes/archive/2026-10-19-integrate-all-source-dev/tasks.md)로 archive했다. CLI의 delta 부재 경고는 비차단이고 저장소 rapid 절차대로 spec 갱신을 생략했다. Exact staged diff의 scanner19건은 synthetic fixture6·제거된 fixture2·boolean identifier1·과거 source digest10으로 확인했으며 실제 추가 credential은 발견하지 않았다. Pattern scan과 제한된 수동 검토이지 비밀 부재의 수학적 증명은 아니며 allowlist는 추가하지 않았다. 전용 Chromium/fixture와 exact ID/image/mount를 확인한 QA container2개만 종료하고 volume/network는 제거하지 않았다(`runtime/cleanup.json`). Push의 기본 브랜치 Dependabot high1알림은 이 변경의 도입 여부/영향을 평가한 것이 아니다. 원격 CI 통과·live 로그인·운영 적용은 이 게시 완료에 포함하지 않는다.

## 조직 SSO 로그인 진입 분리 (2026-10-19, local source)

`separate-organization-sso-login`은 기존 LoginPage의 비밀번호 form과 조직 SSO 선택 view만 분리한다. 메인에서는 SSO 버튼 하나만 보이고 명시 진입 뒤 기존 public catalog의 등록을 표시한다. 새 route/API·native identity·schema·개인-domain 가입/승인/quota 정책은 바꾸지 않았다. 증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/sso-entry-20261019-1cAJ25/`이며 아래 중첩 suite는 합산하지 않는다.

| 실행한 검증 | 관측 결과·경계 |
|---|---|
| Exact LoginPage 회귀 | **59passed**. 명시 SSO 진입 전 제공자 숨김, password 삭제/focus 복귀·continuation 보존, loading/empty/unavailable, 중복 이름의 exact origin, credential/authorize pending lock과 기존 owner/ABA·unmount 경계를 확인했다. |
| Named auth | Backend **714passed**, frontend **21files/403passed**. Native/IdP는 suite fixture이며 실제 사용자 GitLab 로그인 수용이 아니다. |
| 전체 frontend | **403files/4,450 Vitest passed +9 Node runner passed**. 기존 jsdom navigation-not-implemented stderr를 숨기지 않았다. |
| i18n | **48namespaces/10,986messages**, check0errors/0warnings, scan1,147files/0hardcoded Korean. en/ja/zh-CN 새 문구는 사람 검수 전 초안이다. |
| Production build | `npm --prefix frontend run build` 성공. 별도4187 preview로 실제 compiled UI를 실행했다. Docker image build·공유 서비스 갱신·운영 배포는 하지 않았다. |
| Source Chromium | ko/en/ja/zh-CN×light/dark×390/767/768/1023/1024/1440px **48조건/96surfaces**, overflow0·메인 제공자0·SSO2choices·최소44px·heading focus·password field 제거·실제 locale/theme·raw key 부재를 확인했다. |
| Compiled Chromium | 같은4locale/2theme×390/768/1440px **24조건/48surfaces**에서 위 경계와 back action44px를 확인했다. API는 합성이며 선택한 Default 공급자의 intercepted HTTPS 목적지와 돌아온 원 origin의 정확한 pending domain/provider를 확인했다. |
| 실제 browser action | dmslab의 exact encoded provider authorize POST503 뒤 안전한 오류·password 복귀, native Enter의 username/password-only 단일 POST401을 관측했다. Source의 password 삭제·focus 복귀도 확인했다. 응답은 격리 fixture이며 실제 Keystone·SSO cookie/code 교환·callback 성공은 이 UI 변경의 새 증거가 아니다. |
| 정적 검사 한계 | Svelte check는 기존 `dashboard/database/instances/+page.svelte:42`의 `PageState.instanceId` **1error/16warnings**로 실패했다. LoginPage 변경 파일에는 진단이 없었다. 전체 `test:gate`는 이번 UI-only 요청에서 재실행하지 않았고 이전 home-first 작업의 전체 gate 실패를 새 통과로 바꾸어 주장하지 않는다. |
| Architecture/index | Working·task-owned staged guard가 `source_sha256=311297c9c77ac93487a7143f942b424dbd1c5c73804300554e0169f99cca8369`/3,059files로 일치했다. 실제 사용자 index SHA는 전후 `55c07c33bcf2be1d17721de3cae672fda08d9c28774df972a2c8219846a77591`로 동일했다. 동시 WIP 전체를 새로 수용했다는 뜻은 아니다. |

`responsive-locale-matrix.json`, `compiled-locale-matrix.json`, `source-action-evidence.json`, `compiled-provider-redirect.json`과 screenshot을 보존했다. 초기 QA에서 로그인에도 docs-only `?lang=`이 적용된다고 가정한 부분은 실제 locale cookie로 수정했다. Native aria text handle·Enter helper 호출·navigation을 가로지른 page wait timeout은 harness 문제였고, 마지막 것은 실제 목적지 URL과 원 origin sessionStorage로 완료를 확인했다. 앱 인증 정책을 우회하거나 OAuth를 재전송하지 않았다. 자동 완료 알림 누락은 보존된 command artifact로 확인했다. 선택적 gbrain CLI는 PATH에 없어 sync하지 않았으며 기존 guidance는 변경하지 않았다.

## 도메인 입력 없는 원 도메인 로그인 (2026-10-19, local source)

`home-first-domain-free-login`은 password body를 `{username,password}`로 제한하고 canonical native home에서 최초 세션을 발급한다. 모든 fresh password/provider 로그인 뒤 공유 workspace chooser를 열며 조직 탐색과 명시적 scope commit을 분리한다. 기존 identity/home·credentials를 이동하거나 실행 중 사용자 서비스를 교체하지 않았다. 증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/home-first-login-20261019-oq6Kwj/`이며 아래 중첩 suite 수는 합산하지 않는다.

| 실행한 검증 | 관측 결과·경계 |
|---|---|
| Backend exact auth/native/diagnostics 소비자 | **402passed**. Global unique account·disabled/ambiguous subject·home 정책·한 번의 password proof·provider origin·실제 error cause/secret redaction과 legacy selector422를 포함한다. |
| Canonical auth/access targets | Backend **714/1,093passed**, access frontend **172passed**. Auth frontend의 초기401passed에는 뒤에 삭제한 unmount-only 관측 불가2건이 포함되므로 최종 전체 frontend 결과와 구분한다. |
| 최종 전체 frontend | **403files/4,446Vitest +9Node passed**. Credentials/authorize의 owner·ABA·no-replay·fresh chooser·root readiness·onboarding/invitation/MCP와 공개 catalog의 mounted lifetime/transition lock 회귀를 포함한다. 기존 jsdom navigation stderr와 Svelte warnings를 숨기지 않았다. |
| 별도 API contract | **163passed**. 전체 gate의 downstream 실행으로 세지 않는다. |
| 실제 datastore functional | 고유 Compose project의 MariaDB/PostgreSQL/Redis에서 **163passed/31deselected**. 기존 개발 datastore나 운영 credential은 사용하지 않았다. |
| i18n | **48namespaces/10,980messages**, errors/warnings0; scan **1,147files/hard-coded Korean0**. |
| 실제 TCP application/JWT/Redis | `http-evidence.json`: legacy domain422, password 최초 home, 조직 directory 탐색 시 session 불변, 명시 조직/project commit, 원래 deadline 보존, retired refresh401, 새 로그인 home 복귀, 모호한 계정409/native password 시도0, provider origin 보존과 기존 native identity 필드 불변을 확인했다. Native directory/password/token·IdP·graph lease는 합성이고 ownership은 SQLite다. |
| 실제 compiled Chromium 흐름 | `final-browser-evidence.json`: native Enter 로그인→home chooser, 탐색만으로 scope 불변→명시 조직/project 전환, 이전 조직에서 logout→새 로그인 home 복귀. 별도 provider 버튼→합성 IdP→실제 callback/TCP API는 home과 provider origin의 분리를 확인했다. 명시 home continue 뒤 document restore는 dashboard에 남았다. |
| 실제 responsive·theme·locale | ko/en/ja/zh-CN ×light/dark ×390/767/768/1023/1024/1440의 **48조건/96surfaces**. 문서/controls horizontal overflow0, locale별 실제 html language·theme 확인, 미번역 key0, 중복 provider의 origin label·최소44px action을 확인했다. `responsive-locale-matrix.json`의 public catalog/도메인/workspace snapshot은 별도 합성 visual fixture이며 운영 권한 수용이 아니다. |
| 정본9image build·binary runtime | Backend/worker/frontend 양 architecture와 native-vm 양 architecture, native-cloud-vm amd64를 build/load했다. 각 요청 CPU ABI·non-root Python/Node를 실행하고 backend/worker/native7개 image의 변경 Python5파일 hash를 source와 대조했다. Worker crypto round-trip·native supervisor CLI help, 격리 arm64 API/frontend health와 실제 legacy login422도 확인했다. AMD64는 Docker Desktop emulation이며 worker job·VM disk/KVM boot·운영 rollout 증거가 아니다. |

브라우저에서 **SPA logout 직후 provider 버튼이 사라지고 document reload 후에만 복구되는** 회귀를 발견했다. Server catalog는200/provider1인데 credential/authorize generation이 늦은 공개 metadata 응답까지 폐기했다. 공개 catalog는 mounted login page 수명으로 분리하고 credential/authorize 세대·scope/logout action lock·unmount guard는 유지했다. 같은 compiled 흐름에서 새로고침 없이 활성 GitLab 버튼1개가 복구됐다(`logout-catalog-before.json`, `logout-catalog-after.json`). Public metadata GET 자체를 credential 교환처럼 lock에 묶는 추가 queued rediscovery는 채택하지 않았다. 검증 후 잘못 들어온 그 중간 refinement는 정확한 qualified source로 복원했고 최종4,446건을 다시 통과했다. DOM이 이미 없는 unmount-only assertion2건은 보안 회귀로 세지 않고 삭제했다.

초기 catalog HTTP503의 missing `_field` import와 변경된 password exception 구조·scoped exchange 경계를 구분하지 못한 diagnostic fixture2건은 교정 후 exact402건을 통과했다. 첫 buildx 호출의 context 오류는 명시 `docker --context=default buildx`로 수정했고 Docker engine/사용자 context를 재시작·초기화하지 않았다. Visual harness의 chooser reload/login-selector 혼동은 harness만 수정한 뒤 남은 matrix를 완료했다.

필수 `npm run test:gate`는 architecture·JS lanes 뒤 backend **12failed/8,472passed/91skipped**로 종료했다. 이 중 `tests/test_instance_storage_delete.py`11건은 이전에도 기록된 block-consumer DB/managed-grant 경계이며, 추가1건은 `tests/test_layer_build_ownership.py::test_native_create_response_loss_is_observed_without_second_post[rule]`의 예상 외 `/exa.language_server_pb.LanguageServerService/RetrieveUserQuotaSummary` POST 포착이다. 이 추가 실패의 선행 baseline/원인은 확정하지 않았으며 범위 밖 source를 수정·skip/xfail하거나 확인용 재시도로 지우지 않았다. Gate 뒤 단계는 실행된 것으로 표시하지 않고 위 frontend/contracts/functional의 별도 실행과 구분한다. 마지막 test-only 관측 불가 assertion 삭제는 backend 동작을 바꾸지 않는다.

Global Ruff check는 통과했지만 전체 format check는 변경 범위 밖12파일로 실패했다. Svelte check도 기존 `dashboard/database/instances/+page.svelte:42`의 `PageState.instanceId`1error/16warnings로 실패했다. 전체 gate green·commit/push/deploy·실제 GitLab/Keystone/운영 계정·기존 Default 사용자 이관/삭제 수용은 주장하지 않는다. 새 schema/config key는 없으며 앞선 개인 도메인 가입098 등 prerequisite와 backend/frontend 동시 cutover가 필요하다. GBrain CLI는 PATH에 없어 sync/guidance를 바꾸지 않았다.

최종 source guard는 `source_sha256=6fb9ed672b0c387b69566c8402f78e16db0d9c35c00b9e5d962ab8829654df46`/3,059files다. 실제 사용자 index는 처음 byte hash 그대로이고 task-owned index/object store에서 staged snapshot을 별도로 확인한다. 이 digest는 동시 WIP 전체의 acceptance를 뜻하지 않는다. `cleanup-evidence.json`은 기존19개 container의 ID/image/env·mount hash/running 불변과 QA5개 container 정지·소유 API/browser 종료를 기록한다. 기존 volumes와 QA image/cache·검증 receipts는 보존하고 throwaway HTTP scripts2개만 제거했다.

최종 working·task-owned staged guard는 위 동일 digest/3,059files로 통과했고 실제 index SHA는 처음 값과 같았다(`architecture-evidence.json`). Rapid change는 [`2026-10-19-home-first-domain-free-login`](../openspec/changes/archive/2026-10-19-home-first-domain-free-login/tasks.md)으로 archive했다. CLI의 delta 부재 경고는 비차단이며 저장소 rapid 절차대로 `--skip-specs --yes`를 사용했다. Delta strict 검증이나 운영 수용을 통과했다는 뜻은 아니다.

## 개인 도메인 가입·승인·기본 quota (2026-10-19, local source)

`personal-domain-enrollment-policy`의 증거는 `/Users/pieroot/.local/share/afterglow-proofs/personal-enrollment-20261019-XCvLvQ/`에 보존한다. 새 human의 개인 home과 조직 reader admission을 분리하고 기존 계정 ID/home·credentials를 이동하지 않는다. 아래 중첩 suite 수는 합산하지 않으며 실제 GitLab/Keystone/cloud·메일함·운영 배포 수용과 구분한다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| 최종 backend 회귀 | 가입 정책·public signup·canonical federation·domain auth/IAM·개인 도메인·quota·endpoint inventory의 **346passed**. 승인 전 native/session 부재, OIDC/GitHub의 exact personal home·reader-only 조직 참여, case/IDNA 우회 거부, rejected/consumed 재사용 거부, quota 미확정·activation 후 finalization 실패의 fresh callback 우회 차단, 기존 identity/home 유지와 권한 철회·ABA를 검사했다. Native directory/IdP/SMTP 경계는 합성이다. |
| Frontend·contract | 전체 frontend **403files/4,390Vitest +9Node passed**, 별도 API contract **163passed**. 가입 admin panel·public/provider pending/rejected·초대 재조회·late response/ABA·복원 세션 callback one-use readiness의 상태 회귀를 포함한다. i18n check **48namespaces/10,988messages**, errors/warnings0. |
| 실제 DB 기능테스트 | Canonical test profile의 task-owned MariaDB/PostgreSQL/Redis에서 **163passed/31deselected**. 기존 개발 datastore는 사용하지 않았다. Native/SMTP I/O는 이 suite에서 합성이다. |
| 실제 MariaDB migration·정책 | MariaDB **11.4.13/utf8mb4**의 task-owned 새 schema에091→092→093→096→098을 적용하고098을 다시 적용했다. 기존 invitation의 domain/status 보존·nullable snapshot·정책 row 미생성, SQL revision 충돌409, pending commit의 caller rollback 뒤 보존, 새 proof 승인/소비와 quota JSON readback을 확인했다(`migration-evidence.json`). Graph lease·identity/audit는 합성이며 운영 snapshot·mixed-version·backup/restore 증거가 아니다. |
| 실제 HTTP·quota transport | 실제 FastAPI·SQLite·설치된 keystoneauth Session→loopback compute/volume/network HTTP에서 pending403·native 생성0 → 승인 → 새 email proof → 개인 domain/Default/user 및 consumed journal을 확인했다. Quota PUT3개 모두 사용자/Default disabled 상태였고 native readback 뒤 활성화됐다. Blank 생략/0/-1·정책 변경 뒤 기존 quota 불변도 확인했다(`http-evidence.json`, `final-container-http-evidence.json`). Identity directory·SMTP·graph lease는 합성이므로 실제 cloud quota 지원이나 배달 영수증이 아니다. |
| 최종 compiled Chromium | 최종 arm64 frontend image의 관리자 저장·대기열 승인/거절·fresh email 가입 완료를 실제 위 HTTP API에 연결했다. ko/en/ja/zh-CN ×light/dark ×390/767/768/1023/1024/1440의 **48조건/96surfaces**에서 문서 overflow0·control containment·미번역 key 부재·거절 화면 credential input0을 확인했다(`responsive-locale-matrix.json`). 별도 provider pending/rejected403 fixture는 한 번의 POST·URL code 제거·session 미발급을 확인했으며 실제 IdP 인증 증거가 아니다. Screenshot은 finite motion 종료 후 검토한다. |
| Canonical 이미지·실행 | Root Dockerfile의 backend/worker/frontend **3targets×arm64/amd64**를 실제 빌드하고 canonical dev Compose +task-only override의 격리 project에서 각 architecture의 app main·Node·Notion worker와 실제 MariaDB/Redis를 실행했다. API/frontend health·signup options200, non-root UID, Python/Node architecture, OpenTofu1.8.3의 실제 architecture와 backend/worker의 최종 source8파일 SHA 일치를 확인했다(`image-evidence.json`). Worker job·운영 native/SMTP 수용은 아니다. |

최초 `npm run test:gate`는 architecture·JS 단계 뒤 backend **35failed/8,377passed/91skipped**로 중단했다. 이 중 새 SMTP readiness fixture22건을 실제 sender 필드로 보완하고, dependency 배치만 검사하던 admin wiring 단언은 삭제해 새5개 endpoint의 ordinary/revoked-admin HTTP403·정책/queue 무변경으로 대체했다. 그 교정 뒤 최종 scoped346건은 통과했다. 당시 나머지는 범위 밖 storage-delete11건의 block consumer DB/managed-grant 처리와 host-observer timeout1건이며 skip/xfail하거나 무관 source를 수정하지 않았다. 전체 gate를 다시 green으로 보고하지 않으며 downstream frontend/contract/functional은 위 별도 실행 근거다.

Global Ruff check는 통과했다. 전체 format check의20파일 중 이번 변경8파일을 scoped format했고 나머지12개 범위 밖 formatting은 보존했다. Svelte check는 기존 `dashboard/database/instances/+page.svelte:42`의 `PageState.instanceId`1error/16warnings로 실패했다. GBrain CLI가 없어 sync는 수행하지 않았다. Migration098 schema-before-writer·old signup writer drain이 필요하고, 기존 Default 사용자 삭제/이관·공유 mapper/권한·실행 중 사용자 서비스/볼륨 변경이나 운영 rollout은 하지 않았다.

Working과 task-owned disposable index의 staged architecture guard는 동일 `source_sha256=efea5272ac61dcf1b188baa353dec7391f1a0c0b2298ee2e1398502d444bc7fd`/3,059files로 통과했고 원래 사용자 index는 byte hash가 그대로다(`architecture-evidence.json`). 격리 앱/datastore6개·QA image tag3개·browser profile·throwaway scripts/SQLite/index만 제거했으며 기존 사용자 서비스14개의 ID·image·환경/mount hash·running 상태가 같았다(`cleanup-evidence.json`). Rapid change에 delta 계약6개를 보완·strict 검증하고 main spec에 동기화한 뒤 `openspec/changes/archive/2026-10-19-personal-domain-enrollment-policy/`로 archive했다. 상세 결과는 그 `verification.json`과 위 proof root를 따른다. 이 source digest는 동시 WIP 전체의 acceptance를 뜻하지 않는다.

## 관리자 권한 확인 단일화 (2026-10-19, local source)

증거는 `/Users/pieroot/.local/share/afterglow-proofs/admin-verification-2026-10-18T183725248Z/`에 보존한다. 현재 frontend source의 격리 Vite와 실제 Chromium을 실행했으며 identity·API 응답은 loopback 합성 fixture다. 실제 GitLab/Keystone 인증·운영 API 성능이나 배포 수용 증거가 아니다.

- 수정 전 root/admin을 함께 실행하는 `AdminReadiness.test.ts`에서 `/me`가1회여야 하는 회귀가 실제2회로 실패했다(`artifact://1071`). 같은 실제 브라우저의 전체 새로고침도2회를 기록했다(`before.json`). 수정 후 새 document의1회 검증 중 private child 부재, normal refresh의1회 background 검증 중 같은 검색 input DOM·입력값 보존, 목록 새로고침·관리자 내부 탐색의 추가 `/me`0회를 확인했다(`after.json`). 지연은 인위적인 fixture 조건이므로 이 수치로 운영 latency 절감률을 계산하지 않는다.
- Fresh proof 재사용·불완전 flag 거부·다른 login의 늦은200/401 폐기·정상 refresh 입력 보존·권한 철회·scope 전환 시작 차단·401·503·same-tick scope ABA의10개 admin 회귀가 통과했다. Root만 `/me`·retry를 소유하며 서버 `require_admin`·native 검증·권한 cache/TTL·세션 수명은 변경하지 않았다.
- 실제390px 브라우저의 관리자 철회200은 private 화면·admin API 요청0과404 UI,401은 자격 제거·login 이동,503은 private 화면·admin API 요청0과 전역 비해제 recovery modal을 확인했다(`security.json`). `ko/en/ja/zh-CN` × light/dark ×390/767/768/1023/1024/1440의48조건 모두 문서 overflow0·private 목록 정상·새 document `/me`1회였다(`matrix.json`).
- Named auth는 backend614/frontend277, access는 backend1,094/frontend172 통과했다(`artifact://1079`). 전체 frontend는402files/4,320Vitest와9Node tests 통과했다(`artifact://1086`). i18n check는48namespaces/10,914source messages에 errors/warnings0, scan은1,145files의 hard-coded Korean0이었다. 중첩 target 수를 전체 테스트 수에 더하지 않는다.
- Svelte check는 변경 영역 밖 `dashboard/database/instances/+page.svelte:42`의 기존 `PageState.instanceId` 오류1개와 기존 warning16개로 실패했다(`artifact://1081`). 전체 `test:gate`·Docker 이미지 build·실행 중인 사용자 서비스 교체·운영 rollout은 실행하지 않았다. GBrain CLI가 없어 sync/agent guidance 변경도 하지 않았다.
- HEAD+이 작업의 frontend6source/catalog 파일과 현재 문서만 사용하는 task-owned snapshot에서 architecture working stamp·staged guard가 동일 `source_sha256=97b991bbe386bffb0df2de61a1b953f39f73470489a108ea10f0a38d264a165b`/2,620files로 통과했다(`architecture.json`). 공유 index/global review marker·private 설정·native 계정·기존 서비스는 보존했으며 snapshot이 동시 WIP 전체 또는 현재 운영 소스를 승인하는 것은 아니다.

## GitLab shared mapped 재발 방지와 callback 대기 (2026-10-18, native·local frontend)

증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/gitlab-login-outage-2026-10-18T102924454Z/`다. 사용자 보고의 callback503·첫 연결 timeout·password 로그인 성공을 재실행으로 확인하지 않았다. 실제 native `gitlab/mapped`가 다시 `sso_oidc_dmslab_mapping`을 가리켰으며, authoritative `/etc/kolla/globals.yml`·mapping JSON은 그 계약을 계속 선언하고 세 관리 scripts도 도메인 접두사·email·groups 규칙을 덮어쓸 수 있었다. 설치 Kolla의 mapping/protocol update tasks도 그 선언을 소비한다. 실제 마지막 reset actor·시각은 확인하지 못했다. OPTIONS403·Swift401을 이 callback의 원인으로 단정하지 않는다.

- Operator globals·전용 `git.dmslab.re.kr.stable_sub_identity_mapping.json`·sole reconciler를 정확한 `afterglow_gitlab_stable_sub`/schema1.0/user-only `OIDC-sub`로 통일했다. 옛 bootstrap·web forwarder는 fail-closed, group migration은 mapping write를 제거하고 별도 `--migrate-groups`를 요구한다. 기존 grants migration은 실행하지 않았다. Bounded source/cron/systemd scan에서 다른 해당 writer/caller는 발견하지 못했으며 모든 다른 infrastructure repository까지 검사했다고 주장하지 않는다.
- Native apply는18requests로 binding을 복구하고 IdP·legacy openid의 rules/null attribute·retired mapping·다른 protocol을 readback했다. 두 번째 apply는6requests·`changed=false`·writes0이었다. 정본 `genconfig -i /etc/kolla/multinode --tags keystone`는 operator venv PATH 보정 후 성공했다. 세 controller 각각 changed6/failed0이며 generated map 두 위치만 old→stable source로 교체되었다. 다른 기존 파일과 auth/Apache runtime bytes·metadata는 전후 동일했다(`native-generated-convergence.json`). Keystone uWSGI·HTTP proxy image를 교체하거나 재시작하지 않았다.
- 세 controller에서 실제 `core.load_auth_methods()`가 원래5methods와 `keystone.auth.plugins.mapped.Mapped`를 로드했다. Horizon 후보·runtime Django Client는 두 domain의 **전체 mapped WebSSO Location**, unknown-domain400, 각 missing-CSRF 거부와 blank-required credentials-form POST 보존을 확인했다. Human password 인증은 시도하지 않았다. Horizon만 private backup 후 순차 graceful 반영했다(`horizon-apply.log`). Public browser에서 Default/dmslab 각각 실제 GitLab 로그인 화면에 도달했지만 사람의 자격증명·positive native token은 사용하지 않았다(`horizon-live-provider-landings.json`).
- 재생성 duplicate는 이전 삭제 ID와 다른 `1170eb18f7cfa0f3dfaf93b2b17b617a63777283e168c9c00c960263e7bde416`였다. Canonical stable subject에 `dmslab:`을 붙여 URL-quote한 tuple임을 확인했고 direct roles/groups/credentials/application credentials/trustor/trustee는 모두0이었다. 사용자의 **별도 삭제 선택** 후 graph lease 아래 exact state·subject·canonical/email 유일성·unresolved journal을 다시 검사하고 strict session 회수0·단일 DELETE·NotFound를 확인했다. Canonical fields/auth objects/grants/groups는 전후 일치하고 resource/password mutation은0이다(`duplicate-native-ledger/state.json`). 과거 resource attribution 부재까지 증명하거나 다른 계정을 삭제한 것은 아니다.
- 실제 현재 backend의 두 configured native guard accepted, mapped/openid invalid bearer401, forged claim headers401와 direct-auth header bypass401·subject-token0, canonical 동일 이메일1개와 saved project 보존을 확인했다(`native-recovery-smoke.log`). 이는 사용자의 positive federation token 수용이 아니다.

| 실행 | 실제 관측 | 경계 |
| --- | --- | --- |
| Exact login-operation/canonical/domain auth selectors |233passed | 새 정책 I/O 뒤 user/domain disable 거부 포함 |
| `node scripts/test-target.js auth` |backend614·frontend277passed | 중첩 suite는 합산하지 않음 |
| 전체 frontend unit |402files·4,314Vitest +9Node tests passed | 기존 Svelte warnings는 별도이며 해당 timeout source를 포함 |
| Canonical contracts |163passed | 전체 gate short-circuit 뒤 별도 실행 |
| DB functional |163passed·31deselected | 실제 MariaDB11.4·PostgreSQL16·Redis7; private env 제외·고유 project·ephemeral loopback ports·tmpfs, teardown0 |
| Canonical9image build/load와 실행 |backend/worker/frontend/native-vm 양 architecture + native-cloud-vm amd64 exit0; Python/Node·non-root·해당 module import | AMD64는 Docker Desktop emulation, VM disk boot/운영 rollout 아님 |
| Real HTTP + compiled browser slow callback |35.02초 뒤 callback200·federation1·session1·user write0; 같은 user/home/working/saved project로 dashboard 진입 | SQL/JWT/application path 실제, native/IdP/fakeredis는 격리 fixture |
| 기존 local frontend만 canonical Compose 교체 |healthy; 모든 env/mount/port/group 일치, backend ID/image 그대로 | 사용자 선택에 따라 다른 role/session 변경6파일·backend 개선은 미반영 |

Callback client만120초로 대기하며 일반 API30초·OAuth non-replay·no-store·late-owner fence는 유지한다. Backend source는 request-owned connection을 공유하되 정책 I/O 뒤와 publication 전에 authority 관측을 버린다. 로컬 backend와 source의 추가 차이를 발견하고 사용자에게 범위를 제시했으며 **이번 장애 복구만 반영**하는 선택을 따랐다. 따라서 격리 source proof를 현재 backend 성능·role/session 동작으로 표시하지 않는다. Root/local TOML·private compose.env·기존 keys/volumes를 보존했고 공유/운영 DB migration이나 기존 local backend의 startup/schema writer를 실행하지 않았다.

실제 GitLab 인증 후 기존 canonical user/home·두 도메인 saved-project 최종 진입은 사람의 새 로그인이 필요하다. 기존 code/state 재사용이나 service-account 대체로 수용하지 않았다. 기존 non-green 전체 gate를 위 focused/build/native/browser 결과로 green 처리하지 않으며 광역 OpenSpec은 해당 real-user·운영 수용 항목을 active로 유지한다.

최종 공개 working copy5,032files에서 task-owned working/staged architecture guard는 같은 `source_sha256=96bb7833b1d70155d03cf3014e1a37e89d33e9fd3de165a6f0ed97e359942ad5`/3,051sourcefiles를 확인했다. 공유 review marker·index와 보호 설정5개 SHA는 유지했다. Snapshot에는 당시 동시 WIP의 whole-file도 포함되며 그 전체 업무나 native operator source를 이 digest 하나로 승인하지 않는다. OpenSpec strict 검증은 통과했으며 gbrain CLI는 없어 sync·agent guidance 변경은 하지 않았다.

전체 `npm run test:gate`는 JS lanes·working architecture 이후 backend unit의 storage-delete11건에서 종료했다(8,357passed·91skipped). 실패 파일은 `tests/test_instance_storage_delete.py`이며 기존 별도 작업 기록의 차단 범위와 같다. 별도 `lint:backend`의 Ruff check는 통과했지만 format check는 이번 callback 수정 파일 밖12개를 보고했다(`final-lint.log`). 이 파일들을 광역 format하거나 실패를 skip하지 않았고, green gate·commit·push를 주장하지 않는다. 별도 실행한 frontend/contracts와 scoped runtime 결과가 이 실패를 지우지는 않는다.

별도 functional lane은 canonical `scripts/test-db.js --no-start`에 task-owned3services의 실제 임시 URL만 전달했다(`functional-services.json`). 기존 고정3307/5434/6380이나 운영 DB를 재사용하지 않았고 종료 후 컨테이너3개와 해당 network를 제거했다. 브라우저4tabs·소유 Chrome/API·compiled frontend fixture도 종료했으며 공유 SDK browser/사용자 서비스는 유지했다. Tests가 공유 venv의 editable `afterglow-crypto`를 소유 snapshot에 연결한 부분만 같은0.1.1의 정상 repository source로 복원했다. 현재 backend OpenAPI도 `/auth/providers/link`의200을 `ProviderLinkResponse`로 선언하여 frontend-only cutover의 연결 완료 계약과 일치한다(`runtime-link-contract.json`).


## 본인 프로젝트 역할 변경과 로그인 유지 (2026-10-18, local source)

`preserve-login-on-project-role-changes`는 본인 프로젝트 role 편집 때의 로그인 family 일괄 회수와 native project token/로그인 증명 결합을 분리했다. 사용자가 선택한 계약은 **로그인은 유지하되 새 요청에는 현재 권한을 적용**하는 것이다. 다음 로그인까지 철회된 권한을 남기거나 provider의 진짜 로그인 회수를 우회하지 않는다. 증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/project-role-session-20261018-dudgqty1/`다.

- `baseline-reproduction.json`은 변경 전 real role completion·session-store Lua를 실행해 기존 family가 삭제되고 native revoke가 발생함을 재현했다. 같은 경로의 `role-completion-smoke.json`은 변경 후 family 유지·native 로그인 증명 회수0을 확인했다. 관리자 논리 workspace의 원래 connection project를 잃는 추가 회귀도 변경 전403, 변경 후 인증 문맥200·refresh200으로 확인했다(`admin-project-loss-before.log`, `admin-project-loss-after.log`).
- `http-smoke-final.json`은 실제 TCP Uvicorn/FastAPI와 제품 JWT·session·role 서비스를 실행했다. 로그인200 → 본인 admin/member를 reader로 축소200 → 같은 family의 `/auth/me`200·현재 reader·`can_write=false` → refresh200·원래 절대 deadline 유지 → logout200·후속401을 확인했다. 이전 파생 project credential은 폐기된 상태였고 진짜 native 로그인 회수는 access/refresh 모두401이었다. Native directory/token transport·quota/audit·graph lease는 disposable fixture, Redis는 fakeredis, ownership journal은 격리 SQLite다. 운영 Keystone·사용자 브라우저·공유 세션의 수용 증거가 아니다.
- Password/provider root 보존, 현재 권한·동시 proof CAS·원래 lifetime, project-only403과 실제 root401, stale projection을 조회/refresh가 임의 수정하지 않는 경계를 회귀로 확인했다. 관리자 원본 project 상실 뒤에도 현재 system authority·선택 target 검증과 core403을 유지했다. 명시 domain/workspace onboarding은 보존하고 refresh·인증 조회·직접 project 복구만 grant를 생성하지 않는다. 기존 role-driven family 삭제·60초 cache·정확한 교환 순서·verbatim native token 전달을 고정하던 incidental assertion은 제거했다.

| 실행 | 관측 결과 | 증거 |
| --- | --- | --- |
| `node scripts/test-target.js auth` | backend612·frontend277 passed | `target-auth-final.log` |
| `node scripts/test-target.js access` | backend1094·frontend166 passed | `target-access-final.log` |
| Native login-proof regression | 13 passed | `auth-proof-final.log`; 이후 auth/full backend에도 포함 |
| Package JWT/native-boundary migration | 146 passed | `package-proof-migration.log` |
| `node scripts/test-target.js contracts` | 163 passed | `contracts.log` |
| 변경 Python source/tests Ruff | check 통과 | `owned-ruff-pass.log`, `package-fixture-ruff.log` |

중첩 suite는 합산하지 않는다. Package fixture는 unscoped root와 파생 project credential을 구분하고 실제 production session validator를 실행하며, 기존 no-exchange·native token 문자열 pin으로 새 계약을 막지 않는다.

최종 frozen-source `npm run test:gate`는 architecture·JS orchestration/Kolla/installer lane 뒤 backend **8355passed·91skipped·11failed**로 중단했다(`full-project-gate-final.log`). 실패는 변경 범위 밖 기존 `tests/test_instance_storage_delete.py`의 block-consumer tracking/managed-grant cleanup이다. 이를 skip/xfail하거나 무관 source를 수정하지 않았다. Gate 후속 full frontend·contract·functional·lint를 실행한 것으로 표시하지 않으며 위 named frontend·별도 contracts/Ruff 결과와 구분한다.

사전 구조 검토는 role completion의 family 삭제·native credential 결합과 auth/권위 경계를 확인했고 사후에는 identity/provider/lifetime·원자적 family 회수·native source/논리 target·lease와 취소 drain을 검토했다. 새 schema/config/dependency/router·service ownership·배포 topology는 없다. Task-owned 공개 snapshot만 `source_sha256=407cf6ba67c4154770298abca2dc0814b9dfbde5b99efcace21cd1387b613d7c`/3050files로 stamp해 working guard를 통과했다. 공유 staged guard는 기존 `01a2c45cd44b880988f142d0fc109b579a1d9591b9958dc0e19da0e50931e932`/2615files로 통과했고 공유 global marker/index를 갱신하지 않았다. 동시 WIP 전체의 semantic 승인이나 운영 rollout을 뜻하지 않는다.

`preservation-final.json`에서 시작 전후 index·root/local TOML·compose.env·secrets.json의 SHA가 동일했다. Production/기존 로컬 stack의 재시작·교체·IAM mutation·version bump·commit/push는 수행하지 않았다. Python LSP는 미설정이고 GBrain CLI는 없어 index/agent guidance를 바꾸지 않았다. Keystone 자체가 group membership 변경으로 사용자의 unscoped token까지 회수하는 경계에서는 재로그인이 필요하며 이를 role-only403으로 숨기지 않는다.

OpenSpec은 저장소의 `rapid` schema(proposal/tasks)를 완료하고 [`2026-10-18-preserve-login-on-project-role-changes`](../openspec/changes/archive/2026-10-18-preserve-login-on-project-role-changes/tasks.md)로 archive했다. CLI는 delta spec 부재를 비차단 경고로 표시했고 `--skip-specs --yes`로 spec 변경 없이 완료했다(`openspec-archive.log`, exit0). Generic strict delta validation을 통과했다고 주장하지 않는다.

## 기존 계정 연결 완료·별도 재로그인 (2026-10-18, local source/runtime)

사용자는 최초 기존 계정 연결이 timeout으로 보인 뒤 새 로그인이 성공한다고 보고했다. 실패한 real-user OAuth code/password 요청을 재실행하지 않았다. 연결 요청이 native attachment 이후 federation·세션 발급까지 이어가던 경계를 분리했다. 두 link API는 저장/readback을 확인한 `ProviderLinkResponse`만 반환하며 새 login token·session을 만들지 않는다. 증거 루트는 `/Users/pieroot/.local/share/afterglow-proofs/link-first-login-20261018T044142773Z/`다.

- `test_link_confirms_attachment_without_login_then_fresh_callback_issues_session`은 변경 전 실패(`failing-before.log`)했고 변경 후 canonical federation44개와 UI focused41개가 통과했다. `npm run test:target -- auth`는 backend599개·frontend277개 통과이며 `auth-target.log`에 기록했다. 네 언어 번역 검사도 errors0/warnings0이다.
- `http-proof.json`은 실제 TCP Uvicorn/FastAPI route·SQL·signature/JWT 경로에서 연결200 → native attachment 존재·federation0·session0, **별도 authorize/callback**200 → 같은 canonical user/home·federation1·session1을 확인한다. Native directory/password/provider와 Redis는 격리 fixture다. 원래 home과 saved-project sentinel은 유지했다. 이 fixture는 accessible saved project 선택이나 실제 GitLab token의 수용 증거가 아니다.
- Compiled frontend의 실제 browser에서 password proof 제출 → 연결 완료 → 선택 도메인의 명시적 재로그인 → configured provider 버튼 → 새 callback/dashboard를 실행했다. 연결 직후 browser auth가 없고 fresh callback에서만 생기며 API counter도0→1이다(`browser-fresh-login.json`). Native 저장이 반영되지 않는 fixture는 성공 안내·session 없이 오류를 표시한다(`browser-unconfirmed.json`). Timeout을 성공으로 바꾸거나 소비된 proof를 자동 재전송하지 않는다.
- `ko/en/ja/zh-CN` × light/dark × width390/767/768/1023/1024/1440의48개 actual surface에서 overflow·password form 잔존·자동 auth 발급이 없고 같은 선택 도메인의 재로그인 CTA를 확인했다(`browser-matrix.json`). 각 locale/theme의390px screenshot과 Korean desktop/failure screenshot을 보존했다.
- Canonical root Dockerfile의 backend/worker/frontend/native-vm은 arm64·amd64, amd64-only native-cloud-vm은 amd64로 총9개 이미지를 실제 build/load했다(`bake.json`, `images.json`). 모두 container command를 실행해 architecture·non-root runtime·변경된 API model을 확인했다(`image-runtime.json`). Canonical dev Compose의 격리 backend/frontend도 양 architecture에서 healthy 및 API health200·browser-binding 없는 link401을 확인했고 amd64 compiled browser의 연결 완료도 실행했다(`canonical-image-http.json`). Image command/HTTP는 VM disk boot나 운영 rollout 증거가 아니다.
- Svelte check는 변경 영역 밖 `dashboard/database/instances/+page.svelte:42`의 기존 `PageState.instanceId` 오류1개와 warning16개로 실패했다. 이를 숨기거나 무관한 화면을 수정하지 않았다. GBrain CLI는 설치되지 않아 sync를 수행하지 않았고 agent guidance/index를 임의 변경하지 않았다. 실제 GitLab/native positive 수용은 사용자 보고와 격리 proof를 구분하며 광역 change의 미확인 운영·mailbox·두 도메인 saved-project acceptance를 새 테스트 결과로 대체하지 않는다.
- 최종 frozen-source `npm run test:gate`는 architecture working check 뒤 backend8319 passed·91 skipped·기존 storage-delete11 failed로 중단했다(`final-gate.log`, `tests/test_instance_storage_delete.py`); 뒤의 frontend/contract/functional/lint를 실행한 것으로 표시하지 않는다. 별도 실행한 full frontend는4314개 및 file-log runner9개, contracts는163개가 통과했다. Ruff check는 통과했지만 이번 변경 파일 밖12개 formatting으로 `lint:backend`는 실패했다. Functional lane은 실행하지 않았다.
- 공유 index·보호된 root/local TOML·compose.env·secrets.json의 SHA는 시작과 동일하다(`preservation-final.json`). 공유 staged architecture review도 통과했다(source `01a2c45c…`,2615파일). 검증 snapshot만 새 계약으로 stamp하여 working check를 통과했다(source `6e937b5c…`,3050파일); 공유 global marker/index를 임의 stamp/stage하거나 commit·push하지 않았다. 광역 OpenSpec은 real-provider/운영 수용 미확인 항목 때문에 active로 유지하며 현재 link-first checklist와 strict validation은 완료했다.

### 로컬 반영과 실행 환경 보정

검증한 arm64 backend/frontend를 기존 `afterglow-local-services`의 두 image alias에 반영하고 canonical dev Compose로 갱신했다. 두 서비스의 최종 image·healthy·기존 explicit env 전체·그룹·mount·port 일치를 확인했으며 다른16개 서비스의 ID/image/state는 그대로다(`local-image-cutover.json`, `local-cutover-after.json`). 실제 localhost8000 health200·binding 없는 link401과 localhost3080의 Default/dmslab 재로그인 화면·configured provider 표시·오류/overflow/auth 자동 발급 없음도 확인했다(`local-browser.json`). 사람의 password나 실제 provider authorization은 시작하지 않았다.

반영 과정에서 **Bun preflight와 persistent shell의 서로 다른 `AFTERGLOW_DATABASE_URL` 환경** 때문에 첫 backend가 원래 대상이 아닌 Compose local 기본 DB를 선택했다. Post-cutover env 비교에서 발견해 API를 중지하고, 기존 값을 명시한 동일 실행 환경에서 canonical Compose를 다시 render·apply한 뒤 전체 env 일치를 확인했다. 보호된 설정 파일 자체는 바꾸지 않았다. `database_auto_create_tables=true`인 기존 설정으로, 조사 범위05:15:53–05:21:43 UTC에 table 생성/확인 로그가 있으며 local 기본 DB에 `account_recoveries`가 생성되었다. Read-only metadata 및 row count로 새 table이 비어 있음(0행)을 확인했다. 같은 시간의 사용자 `role_assign` 요청200·local `activity_logs`의 audit1행은 보존했으며 native 역할 요청을 재실행/회수하거나 audit를 임의 복사·삭제하지 않았다. 해당 route는 기존 native assignment 경로다. Pre-window schema/data snapshot이 없어 다른 column/row 영향이 전혀 없다고 증명할 수는 없으며, 안전하지 않은 DROP·자동 DB merge로 덮지 않는다. 상세 근거는 `local-environment-correction.json`, `local-correction-log-assessment.json`, `local-correction-database-assessment.json`, `local-correction-recovery-table.json`, `local-correction-audit-preservation.json`에 있다.

## GitLab 콜백503 native 이관 (2026-10-18, 실제 native·로컬 API)

사용자 보고의 비밀번호 로그인200·provider callback503을 재시도 확인으로 소비하지 않고, 현재 backend와 native directory를 읽어 원인을 분리했다. 두 기존 공급자의 `preferred_username`·email·group mapping을 새 canonical 보호 검사가 `native_mapping_unsafe`로 거부했다. 해당 callback 응답은 CORS 허용 헤더가 있었으며 허용된 local-origin preflight도200이다. 반복되는 다른 OPTIONS403이나 Swift401을 이번 callback의 원인으로 단정하지 않는다. 증거는 `/Users/pieroot/.local/share/afterglow-proofs/secure-accounts-20261017T163940/gitlab-callback-20261018/`다.

- 사용자는 두 계정 모두 본인 소유이고 `jung-geun`으로 작업하지 않았다고 확인하고 그 계정 폐기를 명시 승인했다. Exact duplicate ID만 삭제하고 NotFound를 확인했다. Canonical `pieroot` ID/home/name/email/password-capability/federation/default-project와 authentication objects는 보존했다. dmslab Default의 확인된 직접 owner/reader 두 권한을 canonical에 먼저 추가·조회한 뒤 duplicate에서 회수했다. 기존 SQL ownership journal `2d520438-adb6-4b85-b1a6-038234fd54f1`은 completed/verified이며 final unique owner도 canonical이다. Strict duplicate session 회수는 active family0개였다. 리소스 조회·삭제나 manager 자동 동기화는 하지 않았다. 원본 native 자료와 safe receipt는 private `~/afterglow-account81ea72d-cutover-mq9nmmot/`에 남겼다.
- 실제 설치 Keystone은 새 auth-method namespace에 클래스 경로만 지정하는 방식을 stevedore `NoMatches`로 거부했다. **Activation 전에** 잡았으며 패키지 설치·runtime source patch·unsupported alias 활성화를 하지 않았다. 시도한 alias 설정은 operator·세 controller의 generated/live7파일에서 원본 bytes로 복구했고 unused protocol을 삭제했다. 원래 `gitlab/openid`와 그 mapping은 그대로다. 이번 dmslab 연결 소유의 `gitlab/mapped`만 dedicated `afterglow_gitlab_stable_sub` user-only/`OIDC-sub` mapping으로 이관했다.
- 세 controller의 실제 `core.load_auth_methods()`가 원래5methods와 builtin `Mapped`를 로드했고 Keystone config SHA가 원본과 같았다. Apache3개 모두 Syntax OK 후 **별도 `keystone_httpd`만** 순서대로 graceful reload하여 각 `/v3` HTTP200을 확인했다. Keystone uWSGI는 재시작하지 않았다. Exact mapped/auth route는 기존 JWKS/AuthType을 보존하고 valid-user AND exact issuer AND 기존 application audience를 요구한다. 다른 Apache bytes는 보존하며 root-private before/intermediate/final 자료는 operator·controllers의 `/etc/kolla/.afterglow-oidc-backups/afterglow-oidc-stage-20261017T195911Z/`에 있다. 최종 `stage-manifest-mapped.json` SHA256은 `bbe3fe56e71d64b28bab6eebbf369cc1566b6b477c2f1aeeb52975045742fa06`이다.
- Root/local protected TOML의 기존 두 provider key만 같은 supported `mapped` 경로로 선택하고 dmslab exact-domain의 해당 provider에 gmail.com/konkuk.ac.kr auto-admission을 설정했다. Credential·callback·키·그 외 설정은 보존한다. 정본 dev Compose에서 local backend만 restart했다. 새 source/image/schema/migration이나 Afterglow 운영 image 배포는 없다.
- 실제 native smoke: 두 configured mapping guard accepted, mapped/openid의 invalid bearer401, forged claim header401, direct `/auth/tokens` header bypass401, subject token 발급0, canonical 동일 이메일 계정1개와 saved project 보존, configured dmslab 두 host 허용·다른 host와 Default autojoin 거부를 확인했다. Focused `test_domain_auth.py`는89passed다. 기존 전체 gate의 비수용 상태는 별도이며 이번 config/native 수정으로 green을 주장하지 않는다.
- 실제 compiled local UI에서 두 domain의 provider 선택을 확인했고 live GitLab 인증을 거친 callback은503 대신409 `account_link_required` 및 기존 계정 본인 확인 화면까지 진행했다. IdP/native를 mock하지 않았지만 **아직 기존 계정 proof 이후의 positive native token exchange·두 도메인의 최종 로그인/기본 프로젝트 진입은 미수용**이다. Assistant는 사용자 password를 입력하거나 service account로 로그인하지 않았다. Native raw headers/비밀은 증거 요약에 기록하지 않는다. Browser helper의 fill/click 문제는 공개 domain/provider form의 실제 DOM event handler로 우회했고, screenshot은 `page.screenshot`으로 기록했다.
- 기존 auth 구현을 고정한 task-owned 공개 snapshot에서 architecture working/임시-index staged가 같은 `3f2a0d65d904681e1e254764da07b0049a9f4826bec13b8f46451db656b2144d`(3,050files)로 통과했다. 이번 수정은 기존 설정 선택·native mapping/verifier만 이관하므로 application router/schema/service ownership의 구조 변경이 없다. 공유 architecture review marker와 실제 index는 보존했고 이 검증은 동시 source 전체 승인이 아니다. Root/local TOML은 승인된 protocol 선택·email-domain policy 변경만 다르고 private env·secrets, 기존 backend/frontend container ID/image/config-hash는 보존됐다. OpenSpec strict validation도 통과했으며 최종 safe receipt는 incident root의 `verification.json`이다.

## Docker 빌드 레이어 캐시 최적화 (2026-10-18)

`optimize-docker-layer-caching`은 현재 공개 source snapshot 5,027files를 고정하고 Dockerfile·`.dockerignore`만 덮어써 비교했다. 원본 manifest SHA256은 `f59db6d5a8dc61b8515f1913b97bbc14039ba7457b08a1c4d2b6a986f364ca61`, 최종 Dockerfile은 `8f9d47dfef7d5e6a112256ad5dac3e01ad1c495a38fc4d216119c4a60e381756`이다. 실행 로그·단계별 JSON·이미지 metadata·원본/최종 Dockerfile은 `/Users/pieroot/.local/share/afterglow-proofs/docker-layer-cache-20261018-uhnozzcy/`에 보존한다. 범위 밖 공유 source와 index·private 설정·실행 중 개발 stack은 보존했다.

### Source-only 재빌드 실측

Docker Desktop의 native linux/arm64에서 `docker buildx build --platform linux/arm64 --target TARGET --progress=plain --load`로 측정했다. 의존성 레이어를 준비한 뒤 앱 Python 파일 또는 동일 길이의 새 static 파일을 변경했고 cache prune/`--no-cache`는 사용하지 않았다. 단일 실행의 로컬 wall time이며 CI/cold build의 보편적 속도 보장이 아니다.

| Target | 변경 전 | 변경 후 | 감소 | 설치 단계 관측 |
| --- | ---: | ---: | ---: | --- |
| backend | 48.964초 | 3.519초 | 92.8% | 전: apt23.1초·재귀 chown5.7초. 후: OS/uv/OpenTofu 캐시, 앱 복사·bytecode만 재실행 |
| frontend | 39.124초 | 29.670초 | 24.2% | 양쪽 Bun 컴파일 실제 실행23.4/25.6초. 전: npm+chown5.6초. 후: npm `CACHED` |

첫 frontend probe는 기존/새 Dockerfile의 동일 Bun stage가 이미 생성한 compile cache를 공유했으므로 4.761초를 전후 성능 비교에서 제외했다. 위 최종 수치는 서로 다른 새 static 내용을 사용하여 양쪽 `bun run build`가 다시 실행된 결과다. Backend/worker·개발 backend의 source-only build도 uv/소유권 설정 캐시를 유지했다. Native source 변경 뒤 MariaDB/Redis와 amd64 kernel/initramfs 설치는 `CACHED`였으며 kernel 단계의 최초 실측은134.1초였다. Native cloud14.147초 재빌드는 이미 준비된 frontend artifact도 재사용하므로 전체 cold VM build와 비교하지 않는다.

### 실제 이미지·런타임 경계

| 실행 | 관측 결과·한계 |
| --- | --- |
| 정본 build | Backend/worker/frontend/native-vm/backend-dev/frontend-dev ×arm64/amd64 및 amd64-only native-cloud-vm, 총13조건 build/load exit0. 변경 source 경로가 실제 실행됐고 지원하지 않는 architecture에 대한 기존 OpenTofu/native cloud 거부 조건은 유지한다. |
| 실제 바이너리 |13개 image의 Python 또는 Node/Bun 실행·architecture를 확인했다. Python image UID1000·crypto0.1.1의 site-packages 설치, frontend UID1001 및 기존 frontend-dev UID0을 확인했다. 해당 image의 OpenTofu1.8.3은 정확한 linux_arm64/linux_amd64이고 rbd/rados는 Ceph18.2.7이다. AMD64 실행은 Docker Desktop emulation이다. |
| Crypto freshness | 임시 crypto source module만 추가한 worker build에서 외부 의존성 단계가 `CACHED`인 채 local wheel1개를 다시 만들었고 최종 image에서 새 module을 import했다. 양 architecture의 정본 worker-image-smoke도 실제 encrypt/decrypt를 통과했다. Probe는 제품 source에 추가하지 않았다. |
| 정본 Compose | `docker-compose.dev.yml` + task-only override의 독립 `afterglow-docker-opt-{arm64,amd64}`에서 실제 MariaDB/Redis·backend·compiled frontend·Notion worker를 실행했다. API/frontend health200·login document200, backend/worker UID1000·source hash 일치, Redis TIME보다 미래인 worker membership 및 graceful exit0을 확인했다. Worker의 실제 Notion/cloud job 수용은 아니다. |
| Native supervisor | native-vm 양 architecture와 native-cloud-vm amd64의3조건에서 network none·read-only root·cap-drop ALL·tmpfs state로 실제 API/frontend health200·login200과 종료0을 확인했다. systemd/KVM boot·guest kernel·운영 인증 수용은 아니다. |
| 구조 검토 | 격리 dev snapshot의 working stamp와 staged guard가 동일 source SHA256 `b07096a3aea581d8304d0d6aa281352713a222cb8f871a5ba3a7eed13a2ef380`/3,049files로 통과했다. Source에는 보존한 동시 WIP가 포함되며 해당 변경 전체의 semantic 승인이 아니다. 공유 index와 global review marker는 보존했다. |
| 전체 프로젝트 gate | 위 frozen source에서 `npm run test:gate`1회,131.2초·exit1. Architecture·JS orchestration/Kolla/installer lane 뒤 backend unit **8,317passed/12failed/91skipped**로 중단했다. 실패는 범위 밖 storage-delete11건(block consumer tracking/managed grant cleanup)과 host-observer의 실제 local process timeout partial-output1건(`b''` 대 기대 `b'1 *\n'`)이다. 재시도·skip/xfail·시간 제한 완화나 무관 source 수정은 하지 않았다. Gate의 후속 frontend/contract/functional/lint는 미실행이며 별도 Docker smoke와 합쳐 전체 gate 성공으로 보고하지 않는다. Host uv 환경은 Python3.13이고 container는 Python3.12다. |
| OpenSpec | 저장소 정본 rapid schema는 proposal/tasks와 기존 docs를 사용한다. Generic `openspec validate optimize-docker-layer-caching --strict`는 delta spec 부재로 exit1이며 통과로 보고하지 않는다. 새 specs 관례를 추가하지 않고 정본 `openspec archive optimize-docker-layer-caching --skip-specs --yes`로 tasks complete·archive exit0을 확인했다. CLI가 생성한 실제 경로는 `openspec/changes/archive/2026-10-17-optimize-docker-layer-caching/`이며 비차단 경고를 보존했다. |

Production/기존 로컬 stack의 교체·version bump·commit/push·schema/migration·운영 DB/IAM 변경은 수행하지 않았다. 격리 runtime의 cloud URL은 의도적으로 닫힌 loopback9이고 upstream 경고를 readiness/인증 성공으로 숨기지 않는다. Optional gbrain refresh는 CLI 부재로 실행하지 않았고 agent search guidance도 변경하지 않았다.

## 초대·전역 계정·이메일 복구 (2026-10-17, local source)

`secure-global-account-enrollment`은 조직 참여와 공개 개인 가입을 분리하고 native 계정의 immutable home·선택 workspace·provider origin을 별도로 검증한다. 전역 정규화 이메일 ownership은 complete native envelope와 모든 exact user GET을 사용하며 기존 중복은 자동 병합하지 않는다. 증거 root는 `/Users/pieroot/.local/share/afterglow-proofs/secure-accounts-20261017T163940/`다. 아래 중첩 suite는 합산하지 않는다.

| 실행 경계 | 관측 결과·한계 |
| --- | --- |
| 신규 account 소비자 | 최종 backend security10파일 **359passed**. 이메일 인증 전 native write 없음, 조직 self-registration403, 초대·configured exact email-host admission, 기존 계정 연결·local password 보존, hidden collection email·truncated/limited/next의 fail-closed, username/reset/email-change proof와 cancellation·unknown outcome·session revoke를 포함한다. Link/recovery 경합3건은 수정 전 DID NOT RAISE, 수정 후 차단하며 password-origin legacy link의 recovery marker도 보존한다. |
| 관련 named target | 최종 `npm run test:auth`: backend **598passed**, frontend **20files/268passed**. `test:config`: backend **478passed**, frontend **12passed**. 앞선 diagnostic/native directory·system authority synthetic fixture와 proxy email/operation fixture 실패는 원인을 보정했으며 native 권위/정책을 bypass하지 않았다. Proxy exact 독립15passed에는 generated-K8s direct import의 root path 격리를 포함한다. |
| Frontend | `test:unit:frontend` **402files/4305passed**. 정본 host build 성공. `i18n:check`0errors/0warnings, `i18n:scan`hard-coded Korean0. 별도 type check는 이 범위 밖 database instances page의 `PageState.instanceId`1error/16warnings로 실패했다. |
| 실제 SQL·Redis | 정본 test-profile Compose를 task-owned `afterglow-secure-accounts-20261017`에서 기동해 **163passed/31deselected**. Recovery MariaDB row locks·one native dispatch·cancel drain·SQL finalization failure와 nullable enrollment migration을 포함한다. 전용 tmpfs datastore만 종료하며 기존 개발 DB/cache/volume은 보존했다. Native/SMTP consumer I/O는 이 suite에서 합성이다. |
| 실제 HTTP·SMTP·compiled Chromium | 실제 FastAPI·SQLite·Fakeredis·aiosmtplib→loopback ESMTP와 compiled Svelte UI에서 이메일 가입 전0accounts/0domains → 인증 후1account/1personal domain/1Default 및 manager+owner+reader를 관측했다. 기존 이메일에는 credential 생성 폼이 없고 원래 home 로그인/복구만 노출했다. Username proof 재조회410, reset 뒤 실제 저장 password 변경·원래 refresh session 제거·captured native revoke1회·replay410을 확인했다. Signed RSA OIDC HTTP fixture→collision409→원래 password proof→canonical `foreign`/home `other` 유지→작업 `domain` Default dashboard 및 reader만 부여, 신규 계정0·password 변경false를 확인했다. Native directory/SDK/IdP·cloud quota는 합성 경계다. |
| 실제 공개 화면 | Signup/recover ×ko/en/ja/zh-CN ×light/dark ×390/834/1440px **48조건**에서 공개 route 유지·form·가로 overflow0을 확인하고 mobile dark screenshot을 검토했다. 최초 browser smoke는 root client publicRoutes 누락으로 login으로 되돌아가 수정했다. SMTP 주소 cooldown 때문에 즉시 다른 recovery kind 요청은 메일이 추가되지 않았고 정상 제한 뒤 reset을 확인했다. Dashboard cloud resource fixture 미제공 오류는 로그인 성공과 분리한다. |
| 실제 native capability | Marker-owned disposable native domain/user만 생성해 password 인증 전후 전체 federated tuple PATCH와 original password 유지, 정확한 marker readback·사용자/domain 제거를 확인했다. 별도 password 변경 뒤 기존 token은 이미 native invalid404였으며 정확한 Fernet invalid message를 확인해 제한적 idempotent revoke 계약에 반영했다. Generic/proxy404·401/403은 실패로 남는다. 이 probe는 실제 GitLab 사용자 code exchange·canonical 기존 계정 migration 수용이 아니다. |
| 정본 image·격리 Compose | Canonical Dockerfile의 backend/worker/frontend **3targets×arm64/amd64**를 실제 build했다. `docker-compose.dev.yml`+task-owned override의 `afterglow-secure-accounts-runtime`에서 두 architecture 각각 API·compiled frontend·`python -m app.notion_worker` main과 MariaDB/Redis를 실행했다. API/frontend health200, backend/worker uid1000·frontend uid1001, architecture와 account source3파일 SHA 일치를 확인했다. Worker job·실제 native 로그인·메일 발송은 이 runtime에서 실행하지 않았다. |
| 정본 공개 화면·실패 경계 | 두 architecture의 실제 `/auth/signup/options`200과 compiled `/signup`에서 SMTP off일 때 signup/recovery 비활성·credential form0·390px overflow0을 관측했다. Native URL은 의도적으로 loopback9여서 proof 조회는503과 no-store/no-referrer이며, cloud sampler 연결 경고를 보존했다. 첫 arm64 startup의 background table-read 경고도 보존했고 ORM table 생성 완료와 분리했다. 이는 native readiness·운영 SMTP 수용을 뜻하지 않는다. |
| 최초 전체 gate | Frozen public source의 `npm run test:gate`는 architecture·JS 단계 뒤 backend **67failed/8256passed/91skipped**로 중단했다. Package browser/home-password policy fixture, public-route inventory, obsolete mocked URL forwarding test 및 identity/dashboard/Waygate authority consumer 계약과 별도 storage-delete11건이 실패했다. 해당 gate의 downstream frontend/contract/functional/lint는 미실행이며 별도 실행 근거와 합치지 않는다. URL mock 전달 검사2건은 삭제하고 기존 설정 정규화·실제 SDK HTTP revocation/federation 소비자 검증을 유지한다. 전체 gate를 green으로 주장하지 않는다. |
| Consumer 계약 이관·실제 dashboard | 기존 package fixture를 exact native email/home와 실제 SQLite `DomainLoginPolicy`로 이관하고 정책 회수 뒤 package/legacy Hub403·추가 upstream0을 검사한다. Identity·Waygate·dashboard는 현재 user/group/raw/effective grants/role-ID graph를 모델링하며 claim-only 승격을 제거했다. 이 과정에서 실제 `user_inventory` child의 home 누락을 발견했다: 의미 있는 packages-ready 회귀는 수정 전 failed, 수정 후 통과했다. 실제 Uvicorn cross-home(default→tenant-a) HTTP에서도 member package ready·nonmember/현재 membership 회수 denied·administrative cloud connection/mutation0을 확인했다. |
| 공급자·기본 프로젝트 최신 소비자 | `test_domain_auth.py`·`test_login_native_operation.py`·`test_domain_projects.py` **256passed**. 설정 기반 provider 선택·allowlist와 저장된 선호 우선, native scope/JWT/session·새 도메인 manager/owner/reader 및 후속 reader 경계를 유지한다. 실제 외부 GitLab 사용자 인증 수용은 별개다. |
| 최종 consumer·contract·style | Account consumer7파일 **356passed**, 별도 전체 API contract **163passed**. 기존 catalog private-helper mock 전달 검사6건을 삭제하고 HTTP endpoint 선택·scope/header·실패 계약은 유지했다. Lumen admin fixture는 original project native membership·exact home/user/token·실제 system grant로 이관하며 action guard를 우회하지 않는다. Backend 전체 Ruff check 통과, 이 작업 소유23파일 format 통과. 전체 format은 보존한 다른 동시 변경12파일 때문에 실패하며 일괄 restyle하지 않았다. |
| 최종 frozen auth target | Backend **598passed**. Frontend 최초 실행은 snapshot의 생성된 `.svelte-kit` tsconfig 부재로 dependency optimization 전에 실패했다. 정본 `svelte-kit sync` 뒤 동일20개 frontend selector **268passed**를 별도로 확인했으며 앱 코드·의존성·config 우회는 없다. 앞선 동일 source frontend 전체4305건·HTTP/browser 증거와 중첩하므로 합산하지 않는다. |
| 최종 전체 gate | 최종 frozen public source `3f2a0d65d904681e1e254764da07b0049a9f4826bec13b8f46451db656b2144d`/3050files에서 architecture·JS 단계 뒤 backend **8318passed/11failed/91skipped**로 종료1이었다. 남은11건은 기존 `test_instance_storage_delete.py`의 block consumer tracking DB/managed grant cleanup이며 skip/xfail하거나 무관 source를 수정하지 않았다. Gate의 downstream은 미실행이고 위 별도 frontend·contract·실제 SQL와 Ruff check 근거만 주장한다. Working와 소유 snapshot index의 staged architecture guard는 같은 digest를 검증했으며 실제 user index는 변경하지 않았다. |
| 최종 revision·artifact 검증 | 위 final source의 API/worker4개 image를 다시 build하고 arm64/amd64 각각 정본 dev Compose main·health/공개 signup HTTP를 실행해 account4파일(새 inventory home 전파 포함)의 SHA를 host와 대조했다. Frontend는 동일하게 검증된 compiled image를 재사용했다. Worker job/native/SMTP 수용은 아니다. 마지막으로 task-owned 앱/datastore만 중지했고 사용자 기존 backend/frontend의 container ID·image·config hash와 private 입력/index가 원래 fingerprint와 일치했다. Rapid change에 빠진 delta 계약을 추가한 뒤 `openspec validate secure-global-account-enrollment --strict`도 통과했다. |

새 API는096/097 schema와 old signup/profile-email writer drain을 요구한다. 현재 공유 runtime/private 입력과 index fingerprint는 보존했다. 실제 native 두 GitLab mapper는 mutable preferred_username·project/group grants를 포함해 새 user-only stable-sub guard를 만족하지 않는다. 기존 공유 mapper를 덮어쓰지 않으며 별도 native protocol/verifier와 소유권 검토 후에만 cutover한다. 기존 dmslab Default에는 network/subnet/router/ports가 있고 Swift·Barbican/Trove 소유권 검사는 일부 미확정이다. 따라서 실제 중복 계정 통합·운영 SMTP mailbox·실제 GitLab 완료 로그인·운영 rollout은 미수용이며 active OpenSpec을 완료 archive로 표시하지 않는다. 선택적 gbrain CLI는 부재해 index sync를 실행하지 않았다.

기존 duplicate의 추가 read-only native 검사에서는 raw grant가 dmslab Default의 **project_owner/project_reader2건**이고 group0이었다. Native credential/application credential/trustor trust의 별도 SDK 목록도 각각0건을 관측했다(`native-duplicate-raw-grants-readonly.log`, `native-duplicate-credentials-readonly.log`). 이는 Swift/Barbican의 검증되지 않은 project scope나 Trove resource 확인 실패를 해결한 증거가 아니며, 개인 ACL·소유권을 추정해 이전/비활성화하지 않는다. 현재 owned browser는 익명이며 실제 사용자 GitLab의 immutable subject/account proof도 수신하지 않았다.


## 로그인 기본 프로젝트 우선순위 복구 (2026-10-17, local only)

`honor-login-default-project`는 프로필의 Keystone 사용자 `default_project_id`를 읽고도 도메인의 `Default`로 덮어쓰던 `_prepare_domain_session` 회귀를 수정한다. 명시한 프로젝트 → 현재 선택 도메인의 활성·접근 가능한 사용자 선호 → 도메인 `Default` → 다른 접근 가능한 프로젝트 순서다. Default 생성·owner/reader/manager baseline과 최종 native scope 확인은 별개로 유지하고, 접근 불가 선호를 권한으로 사용하거나 저장값을 변경하지 않는다. 새 schema/config/dependency/router/service ownership/deployment topology는 없다.

증거: `/Users/pieroot/.local/share/afterglow-proofs/login-preferred-project-wsfsq_rd/`. 아래 suite는 서로 겹치므로 합산하지 않는다.

| 실행 경계 | 관측 결과·한계 |
| --- | --- |
| 회귀·소비자 | 수정 전 saved-default exact selector의 password/provider **2failed**(`Default` 반환), 수정 후 native login 파일 **34passed**. 명시 선택·Default 생성과 선호 보존·미설정/다른 도메인/비활성/권한 회수/삭제/없는 UUID·실제 JWT/session scope를 확인했다. Auth/domain/provider/workspace/profile5파일 **203passed**. 변경2Python파일 Ruff lint/format 통과. 이전의 incidental directory 호출 개수 단언은 제거했다. |
| 실제 HTTP | Loopback Uvicorn에서 최초 Default 로그인200 → 실제 profile PATCH로 `work-a` 저장200 → password/provider callback 각각200·`project_id=default_project_id=work-a`, Redis 세션 project도 `work-a`를 확인했다. 명시적 `Default`는 선호보다 우선하고 타 도메인 선호는 Default로 대체하되 저장값은 보존했다. Auth/profile/JWT/session과 SQLite ownership journal은 실제 구현이며 native directory/SDK transport·IdP·Redis·quota I/O는 합성이다. |
| 실제 Chromium | 현재 frontend Vite3086을 위 API18753에 직접 연결해 도메인→비밀번호 로그인200 뒤 `/dashboard`로 진입했다. Header의 `Work · tenant-a`, sessionStorage의 `projectId=work-a`,1440px overflow0을 확인하고 `preferred-project-desktop.webp`를 시각 검토했다. Dashboard summary/quota의 미제공 fixture 오류는 보존했으며 실제 cloud resource 로딩 증거가 아니다. Browser exact-name selector·glob URL wait 실패 뒤 실제 URL/새 observe로 확인했으며 제품 로그인 우회는 없다. |
| 정본 image·로컬 반영 | Canonical Dockerfile backend/worker ×amd64/arm64 실제 build와 uid1000 Python 실행·변경 auth source SHA256 대조를 통과했다. Worker main/job은 실행하지 않았다. 기존 실행 backend의 DB URL shell override를 보존해 Compose config hash `263ec3966e183130982f30ef5f61f34c3e52f0b958404278985d83de032fae8b`가 일치함을 확인한 뒤 `up --no-deps --no-build --wait backend`로 backend만 갱신했다. Healthy·`/api/v1/health`200·runtime source parity를 확인했다. Frontend·다른 서비스·user volume·private config는 변경하지 않았다. |
| 별도 auth target | Backend **472passed/4failed/4errors**. 기존 role visibility4건에서 native fixture가 non-loopback Keystone DNS를 시도해 network guard가 차단했고503/teardown 오류가 남는다. 해당 target은 실패 후 frontend를 실행하지 않았다. |
| 전체 gate | Task-owned frozen public source에서 `npm run test:gate`는 architecture·JS orchestration/Kolla/CLI 이후 backend **8,181passed/18failed/91skipped**로 중단했다. Role visibility4·identity roles1·user dashboard1·Waygate authority1·instance storage delete11건이며 수정/skip/xfail하지 않았다. Downstream frontend/contract/functional/lint stage는 이 gate에서 미실행이다. 전체 release qualification은 green이 아니다. |

공유 index/global architecture review marker와 private 입력은 보존하고 별도 public snapshot에서만 working/staged architecture guard를 실행한다. 실제 사용자 GitLab code exchange·native IAM write·운영 배포는 수행하지 않았다. 선택적 gbrain CLI가 없어 sync는 미실행이다. Commit/push/tag는 하지 않았다.


## 도메인 로그인 자동 진입·Default 소유권 (2026-10-17, local only)

`auto-enter-domain-default-project`는 선택한 로그인 도메인에서 실제 native project scope를 확정한 뒤 바로 dashboard로 진입한다. Default가 없는 도메인의 첫 인증 사용자는 새 Default의 `project_owner`, 이후 참여자는 직접 `project_reader`를 받는다. 실제 새 도메인 생성자만 별도로 `manager`를 받으며 기존 도메인의 첫 로그인만으로 manager나 기존 프로젝트 소유권을 가져오지 않는다. 공급자 선택은 기존 설정 registry/allowlist를 재사용하고 새 schema·migration·dependency·전역 역할 seeding은 추가하지 않았다.

증거: `/Users/pieroot/.local/share/afterglow-proofs/domain-default-onboarding-20261017T105822Z/`. 아래 결과는 서로 겹치는 suite를 합산하지 않는다.

| 실행 경계 | 관측 결과·한계 |
| --- | --- |
| 변경 backend 소비자 | auth·native operation·Default lifecycle·enrollment·소유권 회귀 **418passed/5skipped**. Skip5개는 별도 DB lane에서 실행하는 조건부 테스트다. 전체 gate에서 발견한 personal-domain API의 `added_grants` 개수 단언은 삭제하고 실제 새 Default의 활성 상태·정확한 owner/manager/reader 권한으로 검증했다. 해당 exact selector1passed 뒤 파일 전체 **15passed**. |
| 실제 SQL 기능테스트 | 정본 test-profile Compose의 task-owned MariaDB/PostgreSQL/Redis에서 **159passed/31deselected**. 새 개인 도메인 소유권과 동시 초대 수락의 단일 사용자·owner·확정 journal, scope 격리를 포함한다. 전용 loopback datastore만 기동·종료했으며 기존 개발 DB/cache/volume은 보존했다. |
| Frontend 소비자 | auth/callback/domain selection·owner 역할 모달·Domain IAM·4개 locale docs의 focused **11files/183passed**. 전체 frontend **401files/4,277passed**. `i18n:check`0errors/0warnings, `i18n:scan`hard-coded Korean0. 변경 backend16파일 Ruff lint/format 통과. |
| 실제 HTTP | Loopback Uvicorn의 실제 auth/JWT/session·ownership SQLite·멤버 API에서 첫 사용자/참여자 로그인200, owner 역할 위임200, reader/foreign403, owner 제거409, 도메인 생성201·scope 전환200을 확인했다. 동시 최초 로그인2개는 모두200이며 새 Default1개·owner1명이다. Native directory·IdP·Redis·quota I/O는 합성이며 실제 Keystone write나 GitLab code exchange 증거가 아니다. |
| 실제 compiled Chromium | 정본 Compose frontend를 task-owned3085에서 loopback 합성 API18752로 직접 연결했다. 비밀번호 최초 로그인과 설정 기반 공급자의 실제 authorize/callback200 뒤 선택 도메인의 Default dashboard로 진입했다. Owner의 admin checkbox 활성·역할 PUT200·reader로 환원, reader의 편집 UI 차단을 확인했다. 1440px desktop/390px mobile의 가로 overflow0, settled mobile modal·새 한국어 guide 문단을 screenshot으로 확인했다. Native/IdP는 위 합성 경계이며 dashboard cloud summary/quota와 profile은 fixture 미제공 오류를 보존한다. |
| Browser fixture 정정 | 최초 request interception은 공급자의 full-document 이동 이후 지속되지 않았다. 정본 frontend의 `PUBLIC_API_BASE` 환경 override로 API를 직접 연결해 다시 검증했으며 product auth를 우회하거나 실패 응답을 성공으로 바꾸지 않았다. Cross-navigation custom wait와 modal animation 중간 캡처는 tool/fixture 경계로 구분하고 최종 화면은 새 관측과 animation 종료 뒤 저장했다. |
| 정본 image·로컬 runtime | Canonical Dockerfile의 backend/worker/frontend3target ×amd64/arm64 build 성공. Backend/worker 양 architecture의 uid1000 실제 Python에서 변경3file의 host source hash를 대조하고 두 service module을 import했다. Worker main/job 실행의 증거는 아니다. 최종 frontend는 두 architecture에서 실제 Node server의 health200/login200과 compiled domain form을 확인했다. 정본 개발 backend/frontend를 갱신했으며 prod/Kolla 배포는 하지 않았다. Image tag 대신 존재하지 않는 config digest를 지정한 arm64 smoke1회는 reference 오류로 남기고 실제 Compose tag로 실행했다. |
| 관련 auth/access target | `auth` backend **458passed/4failed/4errors**, 별도 `access` backend **1,063passed/5failed/4errors**. Role visibility4건과 identity-role native authority1건에서503 및 차단된 non-loopback fixture 접근이 남는다. 실패 뒤 각 target의 frontend는 실행되지 않았으며 위 별도 전체 frontend 결과와 구분한다. |
| 별도 API contract | **151passed/13failed/5errors**. Lumen admin authority11건과 proxy의 기존 세션 `/auth/me` 검증2건이 실패했고 generated-k8s fixture5개는 `generation_config` import 오류다. 새 Default preparation에 도달하기 전의 실패를 로그인 성공으로 숨기거나 무관 source를 수정하지 않았다. |
| 전체 gate·type check | Frozen public current-source의 `npm run test:gate`1회는 architecture·JS orchestration/Kolla/CLI 뒤 backend **8,166passed/19failed/91skipped**에서 중단했다. 이 중 위 personal-domain consumer1건을 보정·통과했고 남은 권한/identity/user-dashboard/Waygate7건·storage delete11건은 수정/skip/xfail하지 않았다. 전체 gate를 green으로 보고하지 않으며 보정 후 gate 전체는 재실행하지 않았다. Frontend check도 별도 database instances page의 기존 `PageState.instanceId` **1error/16warnings** 때문에 실패했다. |

Native read-only preflight에서는 필요한 canonical 역할·안전한 계층과 Default 도메인의 기존 Default를 확인했고 dmslab에는 Default가 없었다. 이 관측은 이후의 실제 사용자 로그인·자원 생성·운영 수용을 증명하지 않는다. SQL journal/lease·Redis·현재 native 역할 graph와 quota policy는 정상 준비되어야 하며 불명확한 write를 재생하거나 임시 projectless session으로 성공시키지 않는다. Task-owned browser/API/frontend 및 기능테스트 datastore는 종료했고 오해를 부르는 초기 캡처·throwaway runtime script도 제거했다. 선택적 gbrain CLI 부재로 search index sync는 미실행이다. Commit/push/tag/운영 배포는 수행하지 않았다.

## Flavor 우선 VM·부팅 볼륨 자동 보호 (2026-10-17, local only)

`flavor-first-vm-volume-protection`은 공통 사용자·관리자 wizard 순서와 명시적 GPU driver image 추천, 신규 부팅 볼륨의 snapshot/backup opt-in을 연결한다. SQL schema·dependency·operator 설정·기존 stack/volume·공유 index는 변경하지 않았다. 증거는 `/Users/pieroot/.local/share/afterglow-proofs/flavor-first-vm-20261017/`에 둔다.

| 실행 경계 | 관측 결과·한계 |
| --- | --- |
| 최종 backend focused | 생성 보호·GPU metadata·native Glance JSON Patch·snapshot/backup calendar·분산 claim·실제 SDK/HTTP 회귀8파일 **242passed**. 동의 없는 요청/재사용 볼륨은 생성 전 거부, 실제 생성 UUID의 정책 등록 후 성공, lost ACK 보상·명시적 정책 편집 보존·두 lane 경합·불명확한 접수의 no-replay와 수동 사본 보존을 확인했다. |
| Admin image 보정 | 전체 gate에서 optional `properties`가 없는 이미지의 신규 GPU projection이500이 되는 오류를 발견해, 기존 optional metadata 읽기와 같은 `getattr` 경계로 수정했다. 기존 search·pagination·protected/duplicate consumer 회귀를 보존하고 call-argument/forwarding 및 bare-not403 검사5개를 제거했다. 정확한 실패 selector 통과 후 admin/image/native-Glance3파일 **53passed**(위242와 일부 중복), 해당 파일 lint/format 통과. 실제 Uvicorn HTTP에서 properties 부재/null/명시적 driver3행은200과 각각 null/null/nvidia로 반환했다. |
| Frontend | 새 순서·선택 UUID 유지·unknown/mixed vendor·current incarnation·RAM·별도 boot volume 최소 용량·동의·재사용/프로젝트 reset 관련 focused **198passed**. 전체 frontend **401files/4265tests**, 기존 file-log runner **9passed**. |
| 관련 target | `storage`는 backend **885passed**와 frontend **165passed**. `instances` backend는 **1261passed/11failed**이며 실패는 `test_instance_storage_delete.py`의 block consumer tracking DB/정확한 grant 제거 경로다. 해당 target은 실패 뒤 frontend를 실행하지 않았으므로 별도 전체 frontend 결과와 구분한다. |
| 실제 HTTP·SDK·Redis | Host와 canonical backend image에서 실제 Uvicorn·설치된 openstacksdk·loopback Nova/Cinder HTTP·task-owned Redis keys를 사용했다. Tenant sync/SSE·admin SSE에서 실행 동의를 native write 전에 검사하고 정책을 실제 생성 볼륨/대상 project로 등록했다. ACK 유실 뒤 failed/신규 자원 제거·orphan policy0, snapshot reply loss 뒤 POST1회·완료 reconcile·old automatic만 prune·manual/backup 보존을 관측했다. Authority·flavor admission·network/cloud-init·audit는 합성 경계이며 live cloud/guest restore 증거가 아니다. |
| 실제 화면·compiled image | Source와 canonical frontend image의 실제 Chromium에서 Flavor 우선, CPU 일반 후보/GPU 이미지 경고, GPU driver 후보·수동 UUID 유지, 기본 off·독립 opt-in/동의·검토, 기존 볼륨의 비활성화/해제, 40GB nominal Flavor에서 80GB image의 추천/부팅 볼륨 확장을 확인했다. 390/834/1440px·light/dark 및 ko/en/ja/zh-CN 화면을 확인했으며 API 응답은 합성 fixture다. 실제 frontend POST/SSE200은 관측했지만 browser API fixture는 실제 cloud 생성 성공의 증거가 아니다. |
| Build·검사 한계 | 정본 Dockerfile의 backend/frontend `linux/amd64` target을 task-only tag로 build·실행했다. arm64/운영 Compose·Kolla 배포 및 live GPU/backup restore는 수행하지 않았다. `i18n:check`는0errors/0warnings, `i18n:scan`은hard-coded Korean0. Frontend check는 별도 `dashboard/database/instances/+page.svelte`의 `PageState.instanceId`1error/16warnings 때문에 실패했다. |
| 전체 gate·최종 통합 | 최초 `npm run test:gate`는 architecture·JS orchestration/Kolla/CLI 단계 뒤 backend에서26failed/4errors로 중단했다. 이 중 신규 admin image의 optional metadata 오류는 위 보정으로 해결했다. 보정 후 전체 backend 재실행은 **8129passed/18failed/4errors/91skipped**다. 남은 실패는 role visibility·identity/user dashboard·Waygate authority7건과 storage delete11건이며4errors는 차단된 non-loopback Keystone 접근이다. 남은 권한·스토리지 실패를 skip/xfail로 숨기지 않았고 downstream contract/functional 및 그 gate의 frontend/lint는 완료로 주장하지 않는다. |
| Style·구조 검토 | Affected 파일의 Ruff lint와 수정한10파일 format, admin image2파일 lint/format은 통과했다. 전체 format 검사에는 다른 동시 WIP의 차이가 남아 무관 구간을 일괄 restyle하지 않았다. 공유 index의 staged architecture check는 통과했으며 작업 tree 검토와 별개인 preserved-index snapshot이다. gbrain CLI가 없어 검색 인덱스 동기화는 실행하지 않았다. |

정책·slot/journal은 공유 Redis 내구성을 전제로 한다. 요청·Redis·Cinder/Nova의 다중 시스템 원자성은 제공하지 않는다. 정상 관측 가능한 실패는 요청 소유 정책만 보상하지만 **등록 ACK 유실과 Redis 정리 불가/process crash가 겹친 경우의 durable deferred cleanup은 보장하지 않는다**. 스냅샷은 같은 source storage의 crash-consistent 시점 사본이며 독립 백업·파일시스템/앱 일관성·실제 복구 성공을 대신하지 않는다. GPU 검증은 이미지 incarnation/digest 승인이지 가변 driver metadata의 실제 설치·모델/버전/호스트/vGPU·라이선스 인증이 아니다.

## System 관리자의 서비스 작업 검증 (2026-10-17, local only)

`system-admin-service-operations`는 기존 project service capability 또는 현재 human `system:all` admin으로 Lumen·Drover·Waygate·Palimpsest의 명시 target 작업을 인가한다. Target membership·세부 leaf가 없는 관리자를 검증하되 원본 native source와 선택 target, provider executor·resource owner·machine credential ceiling을 합치지 않는다. 현재 공유 checkout의 다른 변경과 index·private config·기존 stack은 보존한다.

| 실행 경계 | 관측 결과·한계 |
|---|---|
| Afterglow BFF 회귀 | Native scope·service authority·domain/refresh 경계의 focused **374passed**. 명시한 빈 target을 fallback하지 않고 projectless 관리자 workspace를 다시 검증하며 타인 session DELETE는404를 유지한다. |
| 실제 main-app HTTP | Uvicorn의 실제 JWT/session/workspace handler와 fakeredis Lua rotation에서 source project `""`, target membership `[]`인 관리자의 네 service permissions를 허용했다. Core native scope403·foreign session DELETE404·권한 회수 후 요청/refresh403을 확인했다. Keystone I/O·Redis storage는 합성이며 lifespan은 꺼 두어 SQL/background worker를 시작하지 않았다. |
| Frontend 소비자 | Permissions/ProjectSelector·Drover controller/grade·Waygate workspace·Palimpsest controllers/page·Lumen key manager **10files/282passed**, production frontend build 성공. 전체 Svelte check는 이 작업에서 편집하지 않은 `charts/runtime-map.test.ts`의 `@testing-library/dom` 누락과 database instance page의 `PageState.instanceId` 오류 **2건**으로 실패했다. 빌드 성공을 type-check 전체 통과로 바꾸어 보고하지 않는다. |
| 실제 compiled Chromium | `roles=[]`, `isSystemAdmin=true`인 합성 서버 세션에서 Drover cross-project 상세·grade별 실제 Blob 다운로드와 권한 회수 뒤 늦은 파일 공개 차단을 확인했다. Lumen provider 관리, Waygate 생성 form, Palimpsest의 exact-package/action-bounded own-key form에 진입했다. Browser에서는 provider 변경·키 발급·paid call을 실행하지 않았다. |
| 반응형·locale/theme | Palimpsest own-key form을 ko/en/ja/zh-CN ×light/dark×390/767/768/1023/1024/1440px의 **48조건**에서 열어 source-derived 권한, 실제 theme preference, 가로 overflow 없음과 입력·footer 접근을 확인했다. 초기 harness의 `.dark` class 가정을 실제 기본-dark/`.light` 계약으로 정정했으며 product theme code는 바꾸지 않았다. |
| Lumen native authority·consumers | 최종15파일 **1,216passed**, installed Keystone deprecation warnings8,001건 보존. Original issued-ID ceiling·raw direct/group/inferred authority·source/target/domain·key/durable/media/Batch/MCP·cloud/memory 소비자 경계를 포함한다. Shared run fixture를 실제 `capability_snapshot` 계약으로 이관하고 전달 인자/mock echo만 검사하던 두 테스트는 삭제했다. |
| Lumen 실제 main/API·SQL | 정본 test Compose의 별도 MariaDB·Redis와 installed SDK를 사용한 실제 `lumen.main` lifespan/readiness 및 **29HTTP checks** 통과. Projectless system token/direct grant와 unscoped token/group-inferred grant에서 target roles=[]로 provider 생성·목록·변경·삭제, ordinary key 발급·목록·이름 변경·폐기를 실행했다. SQL로 실제 owner/target·SHA-256 저장·월50/주10 한도·expiry·폐기 상태를 독립 대조하고 목록의 평문/해시 비노출을 확인했다. Machine key의 admin 상속은401, 현재 grant revoke의 read/create/delete는403, metadata outage는503이다. Provider inference·worker 실행·live IAM은 없다. |
| Lumen durable SQL | Current source의 Batch coordinator·child 두 파일 **96passed**. 실제 SQL snapshot ON/OFF에서 reduced original ceiling의 저장·idempotence·child 상속과 validation/materialization/provider-start 경계를 검사했다. Provider와 directory 권위는 합성이며 paid call·VM/sandbox guest 실행 증거가 아니다. |
| Drover native authority/executor | 최종13파일 **460passed**와 실제 HTTP/SDK/executor smoke 통과. Raw admin4variants·불완전/장애 경계32개, cached-send 회수5종, provider I/O12회와 retired executor credentials2개를 확인했다. Requester target roles=[]·requester role grant0이며 `iam_writes=0` 필드는 role-grant writes만 뜻한다. SQLite facade이며 native worker lease·MariaDB locking·VM/K3s readiness를 증명하지 않는다. |
| Waygate native authority/executor | 최종9파일 **1,371passed/2skipped**, 수집1,373개와 결과1,373개의 누락·중복0. 삭제된 executor를 terminal denial로 분류하는 두 회귀를 포함한다. 실제 Uvicorn/public SDK/SQLite/worker에서 provision/delete completed·server DELETED, target assignments=[]·Trust 생성0·provider requests30·회수 뒤 새 read/create/delete403·queued job failed·추가 provider sends0을 확인했다. Redis timeout traceback3건을 보존하며 Redis·agent/guest health 성공으로 보고하지 않는다. |
| Palimpsest native HTTP | 최종5파일 **485passed/2skipped**와 standalone **49/49HTTP checks** 통과. Human token/password+token 호환, 원본 reduction marker veto·strict raw completeness, OCI/package·layer/image·bounded key·build admission/readback·회수 뒤 I/O 거부를 검사했다. 기존 >8GiB sparse PAX 회귀를 그대로 실행했다: logical cap9GiB,10ms allocated-byte monitor의 관측 peak87,670,784bytes로256MiB threshold 미도달(하드 filesystem quota는 아님). Build worker는 실행하지 않았다. |
| Native schema | 소유 MariaDB11.4.13에서 historical SQL→Drover005/Waygate007 실제 migration, 기존 행·감사 필드 보존과 두 번째 apply의 pending0을 확인했다. Legacy authority를 admin으로 승격하지 않으며 Drover의 cluster 생성 전 uncertain attempt retry도 검사했다. Palimpsest offline bootstrap을 두 번 실행해 nullable issuer provenance/key-audit 확장과 기존 행 보존을 확인했다. Cached canonical dependencies+read-only current source의 증거이며 새 image·production snapshot·mixed-version/writer/rollback qualification은 아니다. |
| Architecture·메타데이터 | Afterglow와 네 native 서비스의 별도 `dev` clone에서 HEAD+명시한 현재 통합 경로로 정본 architecture stamp/staged check를 통과했다. 최종 Lumen import 정리도 재반영했다. 원본 index·공유 architecture bytes는 각 검사 전후 동일했다. `architecture-*.json`에 base SHA·경로·source digest를 보존하며 전체 dirty checkout·full gate·release 수용으로 확대하지 않는다. |
| 최종 Lumen lint | 테스트 import 순서·module spacing만 정리한 뒤 `ruff check lumen tests sdk/lumen_sdk sdk/tests` 통과. 해당 native SDK/HTTP authority 파일을 다시 실행해 **343passed**를 확인했다(위1,216개의 부분집합이며 합산하지 않음). 설치 SDK의8,001 deprecation warnings는 숨기지 않았다. |

전체 gate와 이미지 qualification은 별도다. Lumen full contract의 실행 기록은4failed/3,761passed/12errors이며, 별도 approval-checkpoint resume 실패와 Git/SDK editable path/offline wheel-cache의 실행기 제한을 구분해 보존했다. 실행기 보완 뒤의 개별 결과를 full contract green으로 합치지 않는다. 현재 전체 `npm run test:gate`, live OpenStack/Nova·VM/K3s readiness, 운영 directory RBAC·provider policy·DB/mixed-writer·Kolla 배포는 이 표로 증명하지 않는다. Native arm64/amd64 canonical build는 `RUN --network=none`에서 Debian APT cache가 없어 DNS/package acquisition 단계에서 실패했고 공유 runtime에 의존하는 worker/controller도 qualification 차단 상태다. 네트워크·서명 검증을 풀거나 과거 image/source smoke로 대체하지 않았다.

Afterglow 정본 target/platform9개도 `RUN --network=none --no-cache`에서 uncached APT/Bun 입력을 얻지 못해 실패했다. 초기 RUN network 제한 없는 시도는 정책 미준수 관측으로 별도 보존하며 image 수용 증거에서 제외한다. Offline 최종 결과는 `afterglow-canonical-images-7mk4k0uz/offline/acceptance-results.json`이다.

소유 scratch receipt: `/var/folders/1m/xfc726k14szbjnrlq5t68zjw0000gn/T/afterglow-system-admin-f6gnvztx/`의 `bff-admin-target-passed.*`, `bff-real-http-clean.*`, `frontend-admin-focused.*`, `frontend-admin-build.*`, `frontend-types.*`, `browser-ui-proof.json`과 service/mobile screenshots. 임시 fixture/프로세스와 최종 native receipts의 보존·정리는 최종 통합 기록으로 구분한다.

최종 정리: task-only UI/합성 API service2개를 중지하고 정확한 owned profile을 확인한 Chromium PID에 TERM을 보냈다. Task-only Compose MariaDB/Redis2개와 schema DB1개를 graceful stop했으며 tmpfs 데이터는 지속 보존으로 주장하지 않는다. 증거·scratch 파일은 보존했고 기존 사용자 stack·volume의 prune/down은 실행하지 않았다. OpenSpec strict validation은 통과했지만 full-gate/image 선행 조건 때문에 change는 open 상태다. Optional gbrain CLI가 없어 검색 인덱스 sync는 실행하지 않았다.


## 도메인별 로그인 공급자 allowlist 검증 (2026-10-17, local-only)

`configure-domain-provider-allowlists`의 현재 계약은 exact-domain `allow_providers`가 default를 대체하고, 생략하면 상속하며, 둘 다 생략하면 활성 파일·도메인 소유 SQL 공급자를 허용하는 것이다. `[]`는 외부 공급자0개이고 명시 목록에 공통·SQL 공급자를 추가하지 않는다. 같은 kind도 독립 ID를 유지한다. 공개 목록·authorize·callback·refresh·verification의 서버 집행과 기존 password/email/signup 정책·native federation 경계는 UI 표시와 별개다.

**완료 상태 정정:** image의 Settings/선택 module 실행은 정본 배포 증거가 아니었다. 이후 정본 로컬 Compose에서 실제 앱을 검증했지만 필수 gate가 실패했으므로 배포 qualification은 **BLOCKED**다. 앞선 archive를 되돌려 `openspec/changes/configure-domain-provider-allowlists`의 최종 문서/archive·배포 acceptance checklist를 미완료로 유지한다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| 실제 HTTP | 실제 Uvicorn public router·Settings·SQLite에서 `all`/`default_com` 두 mode × `all`/`dmslab`/`none`/`inherit` 네 도메인을 조회했다. 제한 없는 `all` mode는 GitLab.com·DMSLab GitLab2개, restricted는 DMSLab1개, empty는0개, inherited는2개였다. `default_com`에서는 default 상속 도메인이 GitLab.com1개이고 restricted는 여전히 DMSLab1개, empty는0개다. 허용 authorize200, restricted의 제외 공급자·빈 목록·disabled 공급자 직접 authorize404, 목록 제거 뒤 pending callback403을 확인했다. Native directory·discovery/DNS·fakeredis는 합성이다. |
| Source Chromium |2default modes ×390/767/768/1023/1024/1440px ×light/dark ×4domains의 **96조건**에서 선택 목록·기존 password form·가로 overflow0, 공급자가 있는 경우 button 최소44px를 확인했다. `desktop-unrestricted.png`는 비밀번호 form과 독립 공급자2개, `mobile-restricted.png`는 비밀번호 form과 제한된1개를 보여준다. Compiled image runtime 증거는 아니다. |
| 실제 허용 클릭 |허용 공급자 버튼의 실제 클릭이 `git.dmslab.re.kr` authorization host로 향했고 외부 목적지는 intercept했다. Browser error entries는 빈 배열, dropped0이다. Live IdP 요청이나 로그인 완료 증거가 아니다. |
| 정본 backend·worker image |Frozen public snapshot `source-review-7v5yes3j`의 canonical `Dockerfile`로 backend와 worker 각각 `linux/amd64`·`linux/arm64` build를 완료했다. 변경 runtime source 6개는 현재 checkout과 byte 일치한다. 각 platform에서 network none·read-only·cap-drop ALL·uid1000으로 실행해 backend는 선택 결과(제한 없음2·restricted1·empty0·inherited2)를, API-only JWT 의존성이 없는 worker는 TOML/nested Secret Settings 로드와 allowlist 값을 확인했다(**4/4**). 정본 Compose/Kolla/cluster rollout은 아니다. |
| Focused regression·소비자 |`test_domain_auth.py`·`test_afterglow_conf_config.py`·`test_generate_k8s.py`·`test_config2helm.py` **303passed**. 첫 실행의 2실패는 명시 목록에 SQL fallback UUID를 넣지 않은 test fixture 문제였고 exact2passed 뒤 전체 재실행했다. Frontend auth/login 소비자 **5files/27passed**, 변경 backend/test Ruff 통과, OpenSpec strict valid. `generate_k8s.py`의 미사용 `load_config` import F401은 이 변경 이전 snapshot에도 있던 기존 lint 부채로 남는다. |
| 실제 Kustomize·Helm |제한 없음·default `[]`·default `gitlab_com` 3 mode에서 생성 tree `kubectl kustomize`와 실제 chart `helm template`의 backend·Notion worker env→Settings를 왕복했다(**12조건**). 생략은 생략으로, `[]`는 `[]`로 남고 domain override·empty와 Secret 분리를 유지했다. Helm Secret 렌더링 필수값은 합성 placeholder이며 클러스터 apply는 하지 않았다. |
| 정본 로컬 Compose 실제 runtime |동일 frozen source의 built backend·worker를 정본 `docker-compose.dev.yml`과 일회성 격리 override로 별도 `afterglow-allowlist-qa-20261017` project에 배포했다(arm64). 실제 MariaDB/Redis, `uvicorn app.main:app --reload`, `python -m app.notion_worker`를 기동하고 backend health200·worker main의 살아 있는 Redis membership을 확인했다. 실제 installed Keystone SDK→합성 native HTTP directory를 거쳐 2default mode×4domain 목록과 직접 거부·unknown404·disabled403 총20 HTTP조건이 통과했고, 파일 변경 뒤 API/worker를 모두 recreate하여 default 대체·상속·empty를 확인했다. 첫 시작의 disabled fixture 필수 metadata 누락은 fixture를 완성해 해결했다. IdP에는 요청하지 않았고 live federation·mixed-version/운영 rollout은 미검증이다. |
| 필수 gate — BLOCKED |격리 final public snapshot에서 `npm run test:gate`를1회 실제 실행했고 exit1이다. Docs guard·orchestration166·Kolla18/image-reference13·CLI20passed/36skip 뒤 backend **8,129passed/18failed/91skip**에서 중단했다. 실패는 role visibility4, dashboard package-state1, identity/domain metadata1, Waygate authorization1, instance-storage tracking11이다. Downstream frontend unit·contract·functional·backend lint는 `&&`로 실행되지 않았으며 assertion 변경·실패 재확인 rerun·범위 밖 수정은 하지 않았다. 이 gate는 host arm64이며 backend/worker 양 architecture module smoke를 전체 gate로 대체하지 않는다. |

Evidence: `~/.local/share/afterglow-proofs/domain-provider-allowlists-20261017/`의 `focused-tests-final.log`, `exact-fallback-tests.log`, `http-runtime.json`, `renderer-runtime.json`, `image-runtime.json`, `browser-matrix.json`, `browser-click.json`, `desktop-unrestricted.png`, `mobile-restricted.png`, `backend-build.json`·`backend-build.log`, `worker-build.json`·`worker-build.log`.

추가 evidence: `canonical-compose-start.log`·`canonical-compose-restart.log`·`canonical-compose-default-restart.log`, `canonical-deployment.json`, `canonical-http-runtime.json`, `canonical-native-requests.json`, `canonical-required-gate.log`·`canonical-required-gate-receipt.json`·`canonical-required-gate-preflight.json`. Gate에서 필요한 root `node_modules` symlink가 architecture 입력1개를 추가해 snapshot 안에서만 재-stamp했다(`bbb11bf39db4c537119b2b6e271cdc503cf40e83bfa346bb19912ba8320c5333`/3,033 inputs). 아래3,032-file 원래 검토와의 차이를 설명하며 공유 stamp/index는 그대로다.

Architecture: private 설정을 제외한 public source4,993 paths의 격리 snapshot `source-review-final-ewgvse8d`에서 stamp 뒤 working/staged guard가 같은 `source_sha256=a0619f41cc0c182b7a0196bc488239009188db9a34ac7de04f0e17994c8e25f5`/3,032 source files로 통과했다(`architecture.json`). 공유 index와 global review marker는 바꾸지 않았고 동시 WIP 전체의 gate·배포 승인이 아니다.

이는 local-only HTTP·source browser·renderer·image 관측이다. Live GitLab/Keystone federation·운영 배포·전체 gate 수용이나 Redis discovery-pin 내구성을 주장하지 않는다. Cache pin 유실 뒤 재관측 위험은 남으며 pinning 재설계는 이 변경 범위가 아니다. 아래 `configure-domain-login-methods`의 named auth/config 실패와 검증 수치는 당시 source의 역사적 기록이며 현재 변경의 성공/실패로 재사용하지 않는다.

정리: 소유 Uvicorn·Vite service와 로그인 QA tab을 닫고 exact owned profile의 Chromium process에 TERM을 보냈다. 이 작업의 QA image tag2개와 임시 fixture/frontend/script tree만 제거했으며 증거 snapshot·receipt는 보존했다(`checks.json`, `cleanup.json`, `verification.json`). 기존 stack·volume·private 설정·공유 index/global stamp는 건드리지 않았다. Optional `gbrain` CLI는 없어 검색 sync를 실행하지 않았고 사용할 수 없는 검색 guidance도 추가하지 않았다.

Canonical 추가 정리: 별도 project의 worker→API→datastore를 graceful stop하고 이 project의 stopped container4개·network1개·QA image tag2개만 제거했다. 합성 native HTTP service와 throwaway script2개도 제거했고 배포 설정·전체 lifecycle/gate logs와 receipts는 증거로 보존했다(`canonical-application-lifecycle.log`, `canonical-cleanup.json`). tmpfs datastore의 지속 보존은 주장하지 않으며 사용자 stack·volume·운영 설정은 변경하지 않았다.

### 현재 실행 중인 로컬 GitLab 설정 이관 (2026-10-17, 두 도메인 설정 적용·사용자 인증 미검증)

사용자는 Default와 dmslab에서 `git.dmslab.re.kr` 로그인을 요청했고, 후속 질문에서 공유 Keystone/GitLab 변경을 승인했다. 초기 두 도메인의 resolve는 모두200/provider0개였으며 private 설정에는 현재 코드가 읽지 않는 `[gitlab_oidc]`만 있었다. 초기 native 조회는 `gitlab/openid`만 반환했지만, 최종 적용 직전에는 `gitlab/mapped → sso_oidc_dmslab_mapping`도 이미 존재했다. 이 작업이 native protocol을 생성했다고 주장하지 않으며 현재 유효한 연결을 재사용했다. 이전 Default-only 부분 적용 상태는 `verification-before-approval.json`에 보존했다.

- Root/local private 설정을 기존 자격증명을 유지한 두 registry 인스턴스로 이관했다. Default는 `dmslab_gitlab`의 `gitlab/openid`, dmslab은 `dmslab_gitlab_domain`의 `gitlab/mapped`를 exact-domain allowlist로 선택한다. 두 인스턴스는 같은 기존 GitLab application을 사용하며 native protocol/mapping만 다르다. 명시 default `[]`로 다른 도메인에는 노출하지 않고 구형 frontend 플래그는 제거했다. 새 application source/image·schema·의존성 변경은 없다.
- Native의 기존 dmslab mapping은 대상 user domain과 해당 도메인의 `project_reader` 그룹을 반환한다. Installed Keystone28.0.3.dev6의 실제 `validate_and_prepare_federated_user` 실행으로 명시 user domain이 IdP의 Default fallback을 대체함을 확인했다. Controller3개의 실제 Apache 설정에 `mapped` route·bearer 검증·GitLab JWKS가 존재하고, live `openid`/`mapped` 양쪽은 잘못된 bearer를401로 거부했다. 이는 유효한 사용자 토큰 교환 증거는 아니다. 기존 IdP·Default/dmslab mapping·그룹·grant·계정은 변경하지 않았다.
- 승인된 GitLab application25에 **`http://localhost:3080/auth/callback`만 추가**했다. 실제 Rails row lock 안에서 기존 callback4개를 보존하고 client ID/secret 불변을 확인했다. 기존 운영·test·chat callback을 삭제하거나 운영 Afterglow를 배포하지 않았다. 적용 전 native/GitLab 복구 사본을 확보했다.
- 정본 `docker-compose.dev.yml`에서 기존 backend만 `restart --no-deps backend`했고 health200/healthy를 확인했다. Container/image/env/mount/network와 다른 서비스·DB·volume은 동일하다. 두 도메인의 비밀번호 로그인과 기존 회원가입 정책도 유지했다.
- 최종 실제 resolve에서 `Default`/`default`는 `cfg:dmslab_gitlab`1개, `dmslab`은 `cfg:dmslab_gitlab_domain`1개다. 각각 authorize200으로 실제 GitLab authorization URL·등록된 generic callback·S256·browser cookie를 반환하며 반대 도메인의 provider ID 직접 요청은404다.
- 최종 실제 로컬 Chromium에서 Default1440px와 dmslab390px의 provider 버튼을 각각 클릭해 live `Sign in · GitLab` 화면에 도달했다. 두 화면의 password form과 overflow0을 확인했고 browser error entries는0개였다. 사용자 자격증명을 입력하거나 기존 브라우저 세션을 가져오지 않았다.
- **미검증:** 실제 사용자 GitLab 인증·consent/code exchange·callback·Keystone session 발급은 실행하지 않았다. 전체 gate18실패도 재실행하거나 해결된 것으로 처리하지 않는다. 설정 적용·upstream 로그인 화면 도달을 전체 federation 성공이나 운영 Afterglow 배포 수용으로 확대하지 않는다.

Evidence: `~/.local/share/afterglow-proofs/domain-gitlab-current-20261017T073458Z/`의 `verification.json`, `both-domain-http.json`, `both-domain-browser.json`, `effective-auth-metadata.json`, `gitlab-callback-update.json`, `native-final-readonly.json`, `native-domain-semantics.txt`, `native-controller-protection.json`, `both-default-desktop.webp`, `both-dmslab-mobile.webp`, `both-gitlab-sign-in.webp`. `private-backup/`은 실제 비밀을 포함하는0600 복구 사본이며 공개·커밋하지 않는다. 소유 브라우저 tab과 Chromium만 종료했으며 로컬 backend 설정은 적용된 채 유지한다.

## 설정 기반 로그인 연결 확장 검증 (2026-10-17, local-only)

현재 auth runtime은 도메인 이름/알려진 ID/GitLab host 분기 없이 registry의 issuer/client/native IdP·protocol과 exact-domain allowlist를 사용한다. 기존 일반화 구조를 재사용하며 새 registry/schema/alias, 앱 source·image 변경 또는 실제 private 연결·공유 인증 인프라 변경을 추가하지 않았다. 설정 예시와 운영 절차는 [설정만으로 로그인 연결 추가](api/auth.md#설정만으로-로그인-연결-추가)를 따른다.

- 실제 `get_settings()`가 별도 `afterglow.conf`와 nested Secret env를 읽는 Uvicorn에서 public resolve·authorize를 호출했다. 임의의 `dom-a`/`dom-b`가 같은 issuer/application의 `home_sso`/`team_sso`를 선택하고 각각 `openid`/`team_oidc` native 경로로 처리됐다. 같은 표시 이름/kind/issuer가 별도 인스턴스를 합치지 않았다.
- 실행 script를 그대로 두고 TOML과 해당 Secret만 추가한 뒤 process를 재시작했다. `code_host` GitHub 옵션이 `dom-b`에 추가되고 기존 두 옵션도 유지됐다. 세 옵션 모두 실제 서비스의 code exchange·서명된 OIDC JWT 또는 verified GitHub email·native federation 결과·`require_provider` 검사를 통과했고 기존 두 provider revision은 유지됐다. 타 도메인의 새 옵션 직접 요청은404였다.
- 실제 public callback에서 native domain·IdP·protocol 불일치3조건은403 `foreign_domain`, 같은 state 재사용은401이며 browser cookie를 지웠다. 회귀는 같은 issuer의 독립 native binding, 잘못된 native 결과 거부, 새 옵션 추가 중 기존 pending login/provider-bound session 보존을 다룬다.
- 현재 실행 중인 compiled frontend의 소유 Chromium tab에서 browser-only forwarding으로 위 실제 HTTP API를 연결했다. Desktop1440px·mobile390px에서 설정된 SSO/GitHub 버튼2개, 기존 password form, overflow0을 확인했다. 최초 QA proxy의 OPTIONS 헤더 누락2실패는 실제 CORS preflight 헤더를 전달하도록 고쳤으며 앱 source/보안 정책은 바꾸지 않았다. 이후 새 error entry는0개다.
- 동일3개 registry key·개별 native protocol·도메인 allowlist와 Secret env를 shared K8s/Helm renderer로 왕복했다. 공개 auth TOML에는 secret이 없고 Helm의 auth TOML/Secret key 집합이 일치한다. 이번 추가 검증에서 cluster apply나 새로운 image build는 수행하지 않았다.
- **경계:** 실제인 것은 TOML Settings·FastAPI HTTP·SQLAlchemy SQLite·PKCE/state/revision·서명 검증·compiled UI다. Upstream IdP/자격·native directory/federation은 합성, Redis는 fakeredis다. 성공 경계는 `complete_authorization`/`require_provider`이며 실제 사용자 consent·유효한 cloud federation token·브라우저/Keystone session 발급 성공이 아니다. 기존 전체 gate18실패와 실제 사용자 acceptance는 그대로 미완료다.

- 최종 consumer selector는 `test_domain_auth.py`·`test_afterglow_conf_config.py`·`test_generate_k8s.py`·`test_config2helm.py` **308passed/5warnings**다. 추가5조건을 포함하며 변경 test의 Ruff check/format check와 OpenSpec strict 검증도 통과했다. 비동기 tool 출력이 전달되지 않은 이전 실행은 증거로 집계하지 않고 foreground subprocess의 durable `focused-tests.log`·`focused-tests.json`을 정본으로 보존했다. 기존 전체 gate는 실패 원인 수정 없이 재실행하지 않았다.

Evidence: `~/.local/share/afterglow-proofs/configurable-login-20261017T091014Z/`의 `http-before.json`, `http-after.json`, `renderer.json`, `browser.json`, `boundaries.json`, `desktop.webp`, `mobile.webp`. 초기 fixture의 미등록 provider Secret·SQLite/MySQL bootstrap·callback 등록 불일치와 수정 경계를 `boundaries.json`에 보존했다. 기존 private 설정3개는 fingerprint 불변으로 확인했다.

## 공통·도메인별 로그인 설정 검증 (2026-10-17, historical local-only)

아래는 이전 `configure-domain-login-methods`의 additive 공통/정확한 Keystone domain-ID 선택을 domain-first API·화면에 연결했을 당시의 역사적 증거다. 현재 선택 계약은 위 `configure-domain-provider-allowlists` 절을 따른다. 당시 운영 `afterglow.conf`·Keystone·DB·기존 stack·공유 index는 변경하지 않았고 비밀번호·이메일·회원가입 SQL 정책을 유지했으며 새 migration은 없었다.

| 검증 경계 | 실제 결과·제한 |
|---|---|
| Focused backend/config | `test_domain_auth.py`, `test_afterglow_conf_config.py`, `test_generate_k8s.py`, `test_config2helm.py` **281passed**. SQL 공급자와의 합성, exact-domain 격리, state/secret/revision 변경, discovery drift와 SQL last-method guard, signed OIDC/native-session 경계 및 실제 session-store Lua rotation을 포함한다. Native/IdP와 Redis는 합성 fixture이며 운영 로그인 증거가 아니다. |
| Frontend 소비자 | LoginPage·ProviderCallback·authSession·public site/runtime config **5files/44passed**. 새 문구·locale 키는 추가하지 않았다. |
| 실제 HTTP | 별도 Uvicorn의 실제 public router·TOML Settings·SQLite policy/provider 조회로 dmslab 공통+전용2개, 타 도메인 공통1개, unknown404·disabled403, foreign/unselected provider404와 PKCE S256/nonce/state cookie 발급200을 확인했다. Storage unavailable flag 주입은503/no-store를 유지한다. Native directory·IdP transport·fakeredis는 합성이며 실제 DB 단절이나 외부 로그인 완료를 주장하지 않는다. |
| Source Chromium |390/767/768/1023/1024/1440px×light/dark×2도메인 **24조건**에서 선택 목록·공통 우선 순서·기존 비밀번호 form·overflow0을 확인했다. 최초 provider action 약38.8px를 관측해 기존 `Button`의 최소44px를 적용한 뒤 검증했다. 실제 클릭은 API authorize와 tab-local domain/provider continuation을 거쳐 합성 GitLab authorization 목적지로 이동했고, 외부 요청은 intercept하여 live IdP에 보내지 않았다. |
| Compiled Chromium |정본 Dockerfile frontend image를 실행해4locale×390/768/1440px×2도메인 **24조건**, overflow0·최소44px·JSerror0을 확인했다. API는 위 격리 Uvicorn이고 cloud/IdP acceptance가 아니다. |
| 실제 Kustomize·Helm |생성 tree의 `kubectl kustomize`와 실제 chart의 `helm template`를 통해 API/Notion worker 각각의 Secret refs→실제 Settings 로드를 확인했다. ConfigMap에 credential0, 공급자 metadata·선택·secret2개 보존. 최초 namespace 없는 strategic patch의 target 불일치를 재현했고 explicit Deployment target으로 수정한 뒤 통과했다. 클러스터 apply/rollout은 하지 않았다. |
| Images·실행 |정본 Dockerfile backend/worker/frontend를 각각 `linux/amd64,linux/arm64`로 build했다. Retained BuildKit history와 logs에서 backend46/worker39step 완료·양 platform build를 복구했고 frontend build도 exit0이다. 세 image의 양 architecture에서 비특권 process를 실행했다: backend/worker는 실제 auth Settings·Secret 로딩, frontend는 Node arch/UID와 위 compiled surface를 확인했다. Backend/worker는 formatter/import 정리 이전 build이므로 최종 전체 source parity·전체 API/worker bootstrap 또는 정본 Compose/Kolla 배포 proof로 확대하지 않는다. |
| Scope quality |변경 backend/config model·service·회귀7files Ruff check와 format check 통과. 전체 `test:gate`·운영/mixed-version DB 및 native federation·cluster/Compose/Kolla 배포는 검증하지 않았다. |
| Named target 한계 |`auth` backend는 **445passed/4failed/4errors**에서 중단: `test_role_visibility`의 system-admin permissions fixture가 native 검증을 mock하지 않아 non-loopback DNS guard에 걸리고503을 반환했다. 별도 `config` backend는 **460passed/3failed**: `test_proxy_scheme`의 `_is_system_admin` lambda가 기존 keyword-only `operation`을 받지 못해503이다. 두 실패 경로는 이 변경에서 편집하지 않은 기존 fixture/API 경계이며 성공으로 숨기거나 assertion을 약화하지 않았다. Serial runner가 중단한 frontend는 위 exact5files를 별도로 검증했다. |

Evidence: `~/.local/share/afterglow-proofs/domain-login-config-20261017/`의 `focused-tests.log`, `frontend-tests.log`, `named-targets.log`, `config-ui-tests.log`, `http-runtime.json`, `renderer-runtime.json`, `matrix.json`, `compiled-browser.json`, image build/platform receipts와 desktop/mobile screenshot. 초기 background receipt가 자동 전달되지 않아 test output은 durable subprocess capture로 재취득했고 image build는 기존 BuildKit 기록으로 복구했다. Optional gbrain CLI가 없어 sync하지 않았으며 commit/push·운영 변경은 수행하지 않았다.

최종 frozen public snapshot `source-review-1792173340960619000`의 working/staged architecture guard는 같은 `source_sha256=8b693cc8db16c5aa8eb9c94f3c19f2ac59c1733161271043663ccbe314b47dad`/3,025source files로 통과했다(`architecture.json`). 이는 이 인증 설정 경계의 source 검토이며 동시 WIP 전체의 gate·배포 승인으로 확대하지 않는다. 공유 index/global review marker는 보존했다. 소유 Vite/Uvicorn·compiled frontend container·Chromium을 종료했고 임시 smoke script/DB/profile과 QA image tag3개만 제거했다. Evidence와 public-source snapshot은 위 proof root에 보존한다.

## 관리자 Aodh·Gnocchi 검증 (2026-10-16, local only)

`admin-aodh-gnocchi`는 `/api/v1/admin/telemetry`의 caller-scoped Aodh 경보 관리와 독립 Gnocchi 읽기 점검, 관리자 monitoring navigation·세 화면·네 locale를 추가한다. 격리 public-source snapshot과 receipts는 `/Users/pieroot/.local/share/afterglow-proofs/admin-aodh-gnocchi-rweceb7q/`다. 공유 index·private operator 설정·기존 stack/volume·운영 cloud/IAM/daemon은 변경하지 않았다. Commit/push/release/배포나 실제 경보 발송은 수행하지 않았다.

| 검증 경계 | 실제 결과 |
|---|---|
| 관리자 endpoint | 처음 exact `tests/test_admin_telemetry.py`252passed. 이후 numeric overflow3회귀를 추가한 최종 source는 아래 monitoring target에서 함께 통과했다. Fake native I/O 외 actual router/service·fresh `require_admin`·synthetic Keystone directory/DAG를 유지하며 권한·no-store·일곱 rule·세 상태 action·trust scrub·paging·bounded malformed/oversize/raw zero·불확실한 mutation을 확인한다. |
| 정본 monitoring target | `node scripts/test-target.js monitoring`: backend734passed/5deprecation warnings, frontend28files/569passed. 기존 native resource monitoring·fallback·host/traffic/login 회귀도 포함한다. |
| 최종 UI 국소 회귀 | 브라우저에서 발견한 policy cell/retention label·settings table focus 수정 뒤 관련8files/181passed. JSON rule/time constraints는 whitespace가 아닌 값으로 확인하고, guided threshold0·300초·3period를 명시 입력한다. |
| 실제 HTTP/SDK | 현재 router/service를 Uvicorn으로 실행하고 installed OpenStack SDK/Keystone session이 loopback Keystone→Aodh/Gnocchi와 실제 HTTP로 통신했다.15scenario가 생성→재조회→수정→삭제, trust userinfo 제거, 세 상태 액션 보존, 페이지, private 원문 차단, denied/absent/offline/partial/empty/zero를 통과했다. API identity/admin guard와 native 서비스는 합성이며 fresh authority 자체는 endpoint suite에서 별도로 검증했다. |
| Compiled Chromium | 실제 production frontend + 위 실제 BFF/SDK/HTTP를 연결했다. 사용자 동작으로 trust 확인→생성·재조회·비활성/반복/critical 수정→삭제를 수행하고 native resulting state를 확인했다. Gnocchi raw ns·actual300초·실측0과 partial processing403 중 정책 보존, catalog 없는 Aodh 안내도 확인했다. 실제 native notifier는 실행하지 않았다. |
| Responsive/locales | ko/en/ja/zh-CN × light/dark ×390/767/768/1023/1024/1440px ×세 화면144조건에서 locale 제목·document/main horizontal overflow0을 확인했다. 별도48설정 modal 조건에서 bounded form을 스크롤한 후 Save 도달을 확인했고 모바일 경보 표 ArrowRight는 scrollLeft0→6으로 실제 이동했다. Footer 고정이나 모든 버튼44px를 주장하지 않는다(기존 Button md 약31.6px). |
| Build/i18n | 최종 `npm run build` 통과. `i18n:check`0errors/0warnings·48namespaces·10,869messages, `i18n:scan`1,137files/0hard-coded Korean lines. |
| 타입·경고 | `npm run check`는 변경 밖 database instances `PageState.instanceId`1error로 실패했다. 이 변경의 required breadcrumb 누락과 role query의 지원하지 않는 `exact` 옵션20개는 수정했다. 최종 측정 시 warnings16개: 새 native readonly scroll regions/table의 tabindex·keydown 관련13개와 기존3개. 경고를 suppress하거나 전체 zero-diagnostics로 포장하지 않았다. |
| Backend/runner 품질 | 변경 backend3파일+main의 Ruff check·format check 통과. `node --test scripts/test-target.test.js`10passed. |
| 전체 gate·운영 한계 | 이번 추가 작업에서 전체 `test:gate`는 실행하지 않았다. 이전 native-monitoring snapshot의 storage11/domain-auth3 실패는 아래 해당 작업의 역사적 결과이며 새 source의 현재 실패/성공으로 재사용하지 않는다. Live Aodh plugin/policy/quota, evaluator/notifier→receiver 전달, Zaqar 메일, Heat 자동 복구, 실제 Gnocchi metricd/수집·고부하·운영 배포는 미검증이다. |

Fixture 수정도 증거에 구분한다. 첫 HTTP receipt는 비인증 공개 `/v3` version discovery까지 인증을 요구한 잘못된 assertion이어서 Aodh/Gnocchi native 요청만 검사하도록 정정했다. 초기 settings label selector는 required 표시를 포함한 label text 때문에 실패해 접근 가능한 role/name으로 수정했다. 첫 matrix의 footer probe는 긴 폼을 스크롤하지 않고 offscreen 버튼을 검사했으며, 최종48조건은 실제 스크롤 후 도달성을 검증한다. Modal transition 중 캡처와 settled screenshot을 분리 보존한다. 외부 Google font 차단과 navigation 시 종료된 합성 DELETE request의 browser network abort는 숨기지 않으며 실제 provider 삭제·UI 성공·resulting absence와 구분한다.

Named target의 `uv run`이 공유 `.venv`의 동일 `afterglow-crypto0.1.1` 설치 origin을 snapshot source로 옮긴 것을 확인한 뒤, `uv pip install --no-deps --reinstall ./services/afterglow-crypto`로 원래 repository origin에 복구했다. 다른 dependency나 private 설정을 동기화하지 않았다. 이후 shared-venv snapshot 검증은 `UV_NO_SYNC=1` 또는 독립 venv를 사용한다. Optional gbrain CLI는 없어 sync/context 파일을 변경하지 않았다. Architecture scoped stamp·staged guard, OpenSpec 검증/archive 결과는 해당 change의 `verification.json`에 기록한다.

## 작업 영역 지연·조기 로그아웃 조사 (2026-10-16, frozen local qualification; 일부 수용 차단)

`accelerate-workspace-directory`는 요청 안의 native 연결/관측 재사용, chooser 병행 조회와 scope/refresh 소유권을 수정한다. **새 고정 소스의 정본 image·격리 native/application 실행은 확인했지만, native-cloud VM boot·실사용자 브라우저 timing·전체 gate와 후속 동시 WIP 통합은 미수용이므로 OpenSpec은 열린 상태다.** 이 변경은 새 schema·설정·dependency·권위 cache TTL을 추가하거나 절대 세션 수명을 늘리지 않았다.

| 검증 경계 | 관찰 결과·제한 |
|---|---|
| 기존 debug 로그 | 보존 로그의 `/auth/workspaces`200 **10,241.31ms**, `/auth/token/workspace`200 **19,068.95ms**, 이후 `/auth/me`200 **6,099.31/6,707.92ms**. Stage는 중첩되므로 합산하지 않는다. 서로 다른 요청이 같은 caller/session이라는 증거는 없고 client timeout 실측도 아니다. |
| 기존 수명·로그아웃 기록 | 기존2026-10-16 13:01:42UTC snapshot의 effective 값은 access900초·refresh604800초·absolute session3600초. Session8개 중 started/age가 알려진4개 모두 절대 만료 뒤였고 나머지4개는 age 불명이다. Redis TTL/refresh remaining 양수는 절대 세션 유효성의 증거가 아니다. 보존 refresh401의 구조화 stack은 `_check_session_timeout`에서 끝나며 session lookup2.211ms, 전체2,484.71ms였다. 당시 JWT 자체의 `exp−iat`·native 만료·현재 runtime effective 값·자연 rotation은 미관측이었다. 해당 bounded log의 HTTP503 row는0이며 source의503 분기는 발생 증거가 아니다. 새 관측은 아래 별도 행을 따른다. |
| 수정·회귀 | 동일 scope 교체 토큰을 늦은 non-replay401이 지우던 경합과 refresh 후 재시도401이 pending scope를 기다리지 않던 경합을 failing-before/passing-after로 확인했다. 최종 관련8files **142passed**, canonical `auth` target **420backend/238frontend**, `access` **1,036backend/166frontend** 통과. Native callback fixture의 새 keyword-only `operation` 계약을 이관했고 기대하는200/403/409 결과는 약화하지 않았다. 영향 backend7files Ruff check/format 통과. |
| Compiled host UI | 최종 public snapshot을 `npm run build` 뒤 preview로 실행하고 실제 Chromium에서6시나리오를 확인했다. 알려진 domain의 directory/workspace 동시 pending1쌍, foreign→home 탐색의 workspace2회·directory0회와 세션 불변, 단일 선택→실제 `/dashboard` 및 owner 유지, foreground refresh1회, scope 응답 전 near-expiry focus 대기·stale refresh0회,390px chooser overflow0. API/identity/token은 **전부 합성**이며 native SDK·정본 image·실사용자 latency 개선 증거가 아니다. 초기 과도한 latch hold의 빈 응답, URL observer 오용 timeout과 isolated-world clock 미발생도 실패 기록으로 보존했다. 실제 main-world clock/focus는 CDP로 관찰했다. |
| 전체 frontend | 고정한 최종 소스에서 **394files/4,092passed**, Node log runner **9passed**. 기존3종 Svelte 경고는 유지됐다. 전체 `test:gate` 성공과 같지 않다. |
| 이전 native 전후 시도 | Baseline directory22operations/600assertions와 별도 lifecycle38/1,019는 보존했다. Build10의9images와 binary/source parity는 **이전 source** 증거다. 그 뒤 arm64 directory는 초기 `/me` 상태 검증에서0operations, lifecycle은 첫 login503·41,772.64ms/0nativeHTTP로 실패했고 amd64는 Compose readiness에서 막혔다. 이 결과로 성능 개선을 주장하지 않는다. |
| 이전 build11·daemon 장애 | 당시 source의 build11 backend arm64/amd64는 exit0, frontend arm64는 Vite compile 후 Docker RPC `Unavailable/EOF`로 exit1이며 나머지는 미실행이다. 같은 `desktop-linux` socket의 이후 inventory는 container/image/volume0, Desktop은 running이었다. API proxy log에15:02:26–39UTC 다수 container stop/delete와15:06:46UTC image delete usage가 있으나 호출자·원인·host 영구 데이터 상태는 미확인이다. 복구 뒤 새 proof가 이 실패를 취소하지 않으며 재시작·reset·prune·공유 stack 재생성으로 성공을 만들지 않았다. |
| Host native 대안 | Docker 없이 보존 Redis7.4.2·native HTTP fixture와 실제 `app.main`을 loopback에 실행했다. SQLite DB 초기화가 aiosqlite 경계의TypeError로 실패했고 native MariaDB/MySQL server도 없었다. API startup 표시는 DB readiness로 인정하지 않았으며 로그인·native driver를 실행하지 않고 소유3process를 종료했다. DB/SDK monkeypatch로 성공을 만들지 않았다. `native-host/result.json`에 보존한다. |
| 전체 gate·contract | 이전 고정 snapshot의 `npm run test:gate`는 backend7,582passed/91skipped/22failed에서 중단됐다. Auth fixture3개는 위 target에서 수정·검증했으나 storage11·backup1 실패의 수용은 별도다. Setup/config7건은 public chart GPU 파일을 private filename 규칙으로 제외한 capture 오류였으며 tracked HEAD와 bytes가 같은 파일만 새 validation snapshot에 보존했다. Canonical `test:contract`는167passed/5errors: `test_proxy_scheme`의 generated-K8s fixture가 `generate_k8s.py`를 직접 로드하면서 인접 `generation_config`를 찾지 못했다(파일은 snapshot에 존재). 범위 밖 계약을 수정하거나 전체 gate·contract·full lint 성공으로 보고하지 않는다. 새 functional 결과는 별도 행을 따른다. |
| 새 공유 debug 로그 | Backend/frontend healthy를 읽기 전용 확인했다. 16:32–16:52UTC window의 login200은4,428.22ms, workspace200은5,230.49ms, domains200은6,991.33ms. 후속17:04–17:05UTC refresh200은4,320.25ms, workspace commit200은8,629.84ms, `/me`200은5,358.79/5,750.96ms였다. 이 로그 window의 auth401/503은0이고 OPTIONS403은 별도 noise다. 서로 다른 요청의 동일 caller/session이나 사용자 click→화면 timing은 추정하지 않는다. 지연이 사라졌다는 수용이나 historical19.07초와 controlled 비교가 아니다. |
| 새 실제 세션·native 수명 | 17:00:23UTC bounded read-only Redis SCAN2/GET1/TTL1은 세션1개, age951.27초·refresh/TTL603,849초·absolute remaining2,648.73초를 관측했다. 새 probe 설정은900/604800/3600초이며 실행 process의 cached singleton attestation과 구분한다. 같은 최초 started_at의 기존 사용자 native token으로 **GET `/auth/tokens` 한 번만** 수행해17:07:35UTC에200·stored user 일치, issued17:06:47UTC·expires다음날16:44:28UTC를 확인했다. 해당 로그인의 absolute deadline은17:44:32UTC다. Native token/refresh가 남아 있어도 절대 제한은 연장되지 않는다. 실제 브라우저 JWT 값 자체는 relay 구버전으로 미관측이며 raw token·JTI·user/project ID·로그는 보존하지 않았다. |
| 새 정본 build·Compose | Manifest `2fab44fd4de23143552e3d1207bf706d8d69c12ed1b4df69ded972b214cd4d41`의 public4938files를 고정했다. Root Dockerfile의 backend/frontend/worker/native-vm 각각 arm64·amd64와 native-cloud-vm amd64 **9개 build 조건 모두 exit0**. Binary smoke9images·Python7images/304app files parity와 실제 architecture·Python/Node/OpenTofu/Ceph 명령을 확인했다. Canonical dev Compose+외부 격리 overlay의 fresh SQL/Redis tmpfs·loopback random ports로 양 architecture API/frontend health·login document200과 worker live member/leader를 확인했다. Application source mount·실제 cloud/provider credential은 없다. |
| 새 directory 전후 SDK/HTTP | 각 architecture에서22operations가 성공했고 baseline과 동일 seed·25ms/native HTTP delay·응답·권한 의미가 일치했다. Manager workspace는 SDK HTTP85→42/service auth19→3, member는130→52/22→3이었다. Domains는36/42HTTP로 baseline과 같아 추가 감소를 주장하지 않는다. Derived projection의 권한 승격 거부·creator 범위·live revoke/disable·탐색 전후 session 불변·native write0을 확인했다. 수치는 합성 native 조건의 호출 수이며 production latency가 아니다. |
| 새 scope/refresh·503 경계 | arm64/amd64 각각38operations,1,059/979assertions가 성공했다. Workspace/domain/project/refresh 회전에서 원래 home·started_at을 보존하고 이전 access/refresh는401·nativeHTTP0이었다. Revoked Default refresh403, disabled identity401을 확인했다. 별도 실제 SDK HTTP의 roles503 주입3경로(domains/workspaces/refresh)는503·자격 미발급·원래 access/session 유지 후 정상 refresh200을 확인했다. 공유 세션이나 정책을 수정하지 않았다. |
| 새 정본 compiled Chromium | 실제 arm64 frontend/backend/SDK/SQL/Redis와 합성 native provider에서 login→chooser4,122.30ms, 프로젝트 click→해당 개요 heading2,438.60ms, workspace POST2,405.90ms였다. 초기 domain/workspace는0.20ms 차이로 시작했고 foreign/home 탐색은 workspace만 추가하며 자격·scope가 불변이었다. 연속 focus2개는 refresh1개로 합쳐졌고 pending Beta commit 완료 뒤 refresh가 실행되어 Beta를 유지했다. Near-expiry는 browser main-world `Date.now`만+840초 후 복구했으며 서버 시계·JWT·정책은 바꾸지 않았다. 390px ready chooser의 document overflow0, dialog0–390px, JS exception0 및 desktop/mobile screenshot을 보존했다. 합성 timing이지 현재 사용자 browser의 결과가 아니다. |
| 새 서명 JWT·절대 만료 | 새 합성 로그인에서 실제 서명 JWT `exp−iat`는900/604800초, native fixture는3600초였다. 회전 뒤 원래 started_at은 같았다. **이 합성 세션 하나만** started_at을 deadline 뒤로 이동시킨 HTTP/Redis smoke에서 두 JWT와 TTL이 남아 있어도 access/refresh/retry401·record 삭제를 확인했다. 실제1시간 자연 경과나 공유 세션 변경은 아니다. |
| Native VM의 제한 | native-vm 양 architecture의 non-root/read-only/cap-drop-all supervisor를 순차 실행해 schema43tables, container-loopback API/frontend/login200, worker live lease·leader와 exit0 shutdown을 확인했다. Internal-network guard 아래 host published ingress는 connection refused였으므로 host/browser ingress 수용이 아니다. native-cloud-vm amd64는 build/binary·boot asset만 확인했으며 승인된 amd64 KVM/boot host가 없어 **VM boot는 차단**이다. CLI help를 boot 성공으로 대체하지 않는다. |
| 새 functional | 변경 없는 frozen runner로 unique canonical test project의 MariaDB/PostgreSQL/Redis readiness 뒤 `npm run test:functional`을 한 번 실행해 **159passed/31deselected/0failed/0errors/0skipped**,5deprecation warnings·exit0을 확인했다. Docker/SDK mock을 추가하지 않았다. PostgreSQL health는 전체 checkpointer 수용이 아니다. 소유3containers/network만 정리했다. 그 functional inputs는 canonical frozen backend794/frontend1919/scripts49files·package/Compose와 byte parity였지만 이후 공유 checkout 전체에 대한 수용은 아니다. |

이전 proof는 `~/.local/share/afterglow-proofs/workspace-directory-20261016-2czs9_ph/`와 `resume-final-20261016T150325Z/verification.json`에 그대로 보존한다. 재개 proof root는 **`~/.local/share/afterglow-proofs/canonical-final-20261017-elkqva73/`**이며 `verification.json`이 build·각 architecture native/comparison·compiled browser·JWT/absolute·현재 read-only 로그/세션·native 만료·소유 자원 disposition을 연결한다. Functional 원본과 parity는 이전 root의 `resume-final-20261016T150325Z/functional-20261016T164002Z-z8o3sxe6/`에 있다. 공유 index·설정·세션·TTL·권한과 기존 stack은 변경하지 않았고 commit/push/운영 배포는 하지 않았다.

이전 validation snapshot의 working/staged architecture guard는 `source_sha256=747bfd14b80808a195b1eb5817e7f8e31081b0b6695d04f53652b775d03c4b54`/3,000files였다. 새 정본 실행 뒤17:10UTC read-only parity는 이 수정의 source/test14files가 frozen bytes와 같음을 확인했지만, config/domain-auth provider/bootstrap/login UI/nav/test runner/generator 등 기존24inputs의 동시 변경도 확인했다. 이들을 덮어쓰거나 이전 이미지를 최신 전체 checkout 수용으로 승격하지 않는다. `scope-current-parity.json`, `current-runtime-source-parity.json`과 `concurrent-auth-inputs.diff`에 범위를 남긴다. 실사용자 브라우저 relay 갱신, 승인된 VM boot target, 전체 gate 및 동시 WIP 통합의 별도 qualification 전에는 archive·전체 완료를 주장하지 않는다.

새 문서 검증은 별도 current public4975files snapshot에서만 stamp/stage한 뒤 `npm run docs:check`와 `python3 scripts/check_architecture.py --staged`를 통과했다. Working/staged digest는 `06c05be9c3c74406750e6fab9aea7f5e6910341f22897b94eda1c93f80eaa402`/3,024source files이며 공유 index·review marker의 hash는 그대로였다. 이는 정본 이미지를 빌드했던 더 이른 frozen source와 구분하며 현재 tree의 runtime 수용은 아니다. 결과는 새 proof의 `docs-current-validation-1792172075387/checks.json`에 있다. `openspec validate accelerate-workspace-directory --strict`는 기존 rapid change에 `specs/` delta가 없어 exit1이므로 성공으로 보고하지 않는다. Optional gbrain CLI는 여전히 PATH에 없다.

마지막17:44:47UTC의 수동 read-only 관측에서는 같은 실제 로그인 세션의 age가3,615.26초, absolute remaining이−15.26초인데도 refresh remaining603,216.74초·Redis TTL603,218초·blacklisted=false였다(`current-absolute-deadline-readonly.json`). 실제 시계가1시간 상한을 지난 사실이지, 사용자 대신 refresh/API를 호출해 세션을 삭제하거나 자연 HTTP401을 관찰했다는 뜻은 아니다. 직전 bounded current 로그에서는17:18:24UTC refresh200·4,561.70ms와 `/me`200만 확인했다. 공유 backend/frontend의 ID·image·시작 시각·healthy 상태는 그대로였다(`current-final-readonly.json`).

## Ceilometer·Gnocchi native monitoring 검증 (2026-10-16, local only)

`openstack-native-telemetry`는 current caller catalog/session으로 native 실측을 읽고 독립 exporter fallback을 유지한다. 격리 snapshot은 `/Users/pieroot/.local/share/afterglow-proofs/native-telemetry-s53kdwnd/source`이며 private operator 설정·기존 datastore·volume을 사용하지 않았다. 실제 OpenStack 수집 서비스 활성화·운영 배포·release·Afterglow commit/push는 수행하지 않았다.

| 검증 경계 | 관찰 결과·제한 |
|---|---|
| Collector/API 회귀 | 초기 통합에서 중앙 5xx sanitizer가 route no-store를 버리던 실패를 수정했다. 정상·403·422·sanitized502, 실제 인증 프로젝트 경계, native 소유권·단위·reset/gap·historical 분모·archive·partial recommendation을 검증한다. 최종 selector/결과는 OpenSpec verification receipt에 보존한다. |
| 실제 SDK/HTTP | 실제 수정 router·collector·설치된 OpenStack SDK/Keystone session과 Prometheus HTTP를 Uvicorn으로 실행했다. Loopback Keystone/Gnocchi/Prometheus·Nova/identity/inventory는 합성이다. Healthy CPU ns/vCPU·byte/IOPS rate·zero/RAM MiB, 독립 memory fallback,403·catalog 부재·미수집·외국 owner·양 provider 실패·인가 경계와 default14d/300s archive→21600s provider mean resample을 통과했다. Native 정책·성능·archive retention의 live acceptance가 아니다. |
| 실제 privacy HTTP | 실제 `app.main.sanitized_http_exception_handler` 아래502가 masked detail와 no-store를 반환하고 arbitrary upstream secret header를 공개하지 않음을 확인했다. |
| Browser | 실제 Vite admin monitoring·instance detail/추가 native meter·기록 이력·usage 화면을 Chromium으로 실행했다. Native 실측0·기록 시각/단위, catalog 부재 시 exporter fallback과 usage provenance를 확인했다. 네 locale 각각 light390/dark1440px8조건에서 horizontal overflow0·native zero를 확인했다. Tutorial 상태 POST fixture 미구현과 외부 Google font 차단은 별도 network 오류이며 JS exception 성공으로 숨기지 않았다. |
| Frontend typing | 이 변경의 usage snippet이 PageShell prop으로 추론되던 오류를 top-level snippet으로 옮겨 수정했다. 최종 `npm run check`는 변경 밖 database instances `pushState(...,{instanceId})` 대 App.PageState 불일치1error와 기존3warnings로 여전히 실패한다. |
| 전체 gate | `npm run test:gate`를 격리 current public snapshot에서 실제 실행했다. Architecture·JS orchestration 단계를 통과한 뒤 backend unit7,582passed/91skipped/14failed에서 중단했다. 실패는 `test_instance_storage_delete.py`11개(block consumer tracking unavailable/상태 불일치)와 `test_domain_auth.py`3개(native issuance503 대 기대200/403/409)다. 이 native monitoring 변경의 관련 selector 실패는 없으나 전체 gate 통과·후속 frontend/contract/functional/full lint 실행으로 보고하지 않는다. |
| 환경·보존 | 사용자 index·private 설정·기존 stack·cloud 자격과 데이터를 변경하지 않았다. Optional gbrain CLI는 PATH에 없어 sync하지 않았다. |

HTTP/privacy receipts·browser matrix/스크린샷은 위 proof root에 보존하며 canonical monitoring target 및 최종 scope Ruff check/format 결과는 OpenSpec verification에 기록한다. 최초 UI 회귀는 닫힌 chart data disclosure와 중복 current-value/table text, renderer mock call 가정 때문에 실패했다. 실제 disclosure·접근 가능한 table cell을 검증하도록 수정했으며 production chart 동작을 우회하지 않았다.

최종 native collector/API7files **173passed**, canonical `monitoring` target **479backend/388frontend**(artifact://333), frontend native consumers10files130passed와 usage/snippet/chart semantic3files41passed, scope backend12files Ruff check/format을 통과했다. Frontend build와 i18n check(0errors/0warnings,47namespaces)도 통과했다. Malformed sample 진단이 이미 알려진 reset을 가려 coarse archive로 바꾸던 회귀를 failing-before/passing-after로 고쳤고 continuity flag를 diagnostic과 분리했다. Frozen public snapshot의 working/staged architecture guard는 `source_sha256=09d4039f3ce02b4a7980dd0149ff9456f2bf39c7b2d14e228c0a429493b95224`/3,024files로 통과했다. 공유 index/global review marker는 보존했으며 이 stamp는 동시 WIP 전체 gate 승인이나 운영 수용이 아니다. 완료 기록은 `openspec/changes/archive/2026-10-16-openstack-native-telemetry/verification.json`이다. Rapid schema의 generic strict validation은 delta 부재 오류였고 canonical archive는 이를 non-blocking 경고로 표시하며 `--skip-specs --yes`로 tasks complete를 archive했다. Strict validation 통과로 보고하지 않는다.

## 독립 Cloud Shell image와 pull 설정 검증 (2026-10-16)

`configure-gitlab-cloud-shell-image`는 독립 [openstack-afterglow/openstack-client](https://github.com/openstack-afterglow/openstack-client)의 source `4ea9cbd4e6ee6b25815417e02646e7179ab1b9a3`를 올리고 Afterglow의 image/CLI build 정본을 그곳으로 옮겼다. GitLab parent `434529e3045226620aeaea736e2af15c37b7e49f`와 원본 이력을 유지하고 source 저장소는 private으로 만들었다. 원본의 명시적 LICENSE 부재와 과거 README의 literal credential 예제(실제 자격이었는지는 미확인)는 독립 README에 기록했으며 공개 전환이나 history rewrite는 하지 않았다.

| 검증 경계 | 실제 결과·한계 |
|---|---|
| 독립 source/로컬 image | stdlib bootstrap7passed, Actions `actionlint` 통과. Debian/Alpine 각각 amd64/arm64 네 image를 실제 build하고 non-root CLI·setuid/echo-off PTY·UID/GID1000·capability0/NoNewPrivs·tmpfs0600·installed SDK scoped-cloud/token 로딩·컨테이너 교체 후 home 보존을 통과했다. 로컬 amd64는 ARM 호스트의 교차 실행이며 native CI 증거와 구분한다. |
| Exact-source GitHub CI | [38882078745](https://github.com/openstack-afterglow/openstack-client/actions/runs/38882078745)는 위 SHA의 native amd64/arm64×Debian/Alpine 네 build/runtime gate와 발행 잡 모두 success다. 발행은 검증된 네 archive를 그대로 로드하고 재빌드하지 않는다. Publish 로그에서 아래 두 index digest의 revision manifest 및 `slim`/`latest`/`alpine` promotion을 확인했다. Artifact action의 Node20 deprecation warning은 있었으며 job 실패는 아니다. |
| Backend 실제 runtime | 정본 root Dockerfile backend의 양쪽 architecture build와 정본 dev Compose+owned override를 실행했다. 실제 keystoneauth/Zun adapter→합성 loopback HTTP에서 default/member, explicit policy3개, 미게시 image와 명시 policy403까지6조건씩 create/exec/exact cleanup·home 보존을 통과했다. Provider/network/home은 합성이며 live OpenStack/Redis mutation은 없다. |
| 설정 생성·실제 CLI | K8s renderer·Helm·Kolla 두 Cloud Shell Jinja section과 TOML/env 우선순위를 확인했다. 추가로 실제 `config2helm.py` CLI→`helm template`→ConfigMap TOML에서 `services.cloud_shell`이 꺼지는 누락을 재현한 뒤 full Cloud Shell mapping을 추가했다. Default/always/ifnotpresent/never4조건에서 선택한 alternate registry image·UUID·network/resource/timeout이 보존된다. Cluster에 적용하지 않았다. |
| 관련 회귀 | Afterglow `test:cloud-shell` backend30/frontend29, `test:orchestration`166, Kolla Node24/Python11, focused CI decision52, version sync1.30.12 통과. Helm converter를 포함한 configuration consumer4files161passed. 초기 focused Cloud Shell/safety/K8s84도 통과했으며 중복 실행한 suite를 합산하지 않는다. 소유 backend5files Ruff check/format과 root converter의 syntax/fatal checks 통과. |
| Architecture | Frozen current public source(동시 WIP 포함)의 독립 clone에서 working와 staged guard가 같은 `0a12d3631aaf68fdf966e6a051b87265fff1a196f094b8d7735227011924e840`/2,994files로 통과했다. 공유 index/review marker와 private config의 image 외 credential, 기존 stack/volume은 보존했다. 전체 동시 변경의 integration 승인이나 새로운 full-gate 성공이 아니다. |
| Pull 인증·미검증 | 현재 `gh` credential의 package/versions API는 `read:packages` 부족403, 기존 Docker credential의 digest inspect도 scope 불일치403이다. 빈 임시 Docker config의 anonymous inspect는 `manifest unknown`이었다. Package ACL 상세·로컬 authenticated pull·실제 Zun registry/pull/attach/CLI·운영 배포는 미검증이다. 공개 전환·권한 우회·native registry credential 생성은 하지 않았다. 전체 `npm run test:gate`는 이번 작업에서 실행하지 않았고 Afterglow commit/push/tag/배포도 하지 않았다. Optional gbrain은 CLI/detect가 없어 sync하지 않았다. |

게시 registry는 `ghcr.io/openstack-afterglow/openstack-client`다. 아래는 성공한 발행 job에서 확인한 manifest이며 **로컬 authenticated pull 증거와는 별개**다.

| Channel | Multiarchitecture manifest digest |
|---|---|
| `slim`, `latest` | `sha256:239c7d3972de6e2df7387904ae8fa7a637f0c021d56d4254bba91880a34827a2` |
| `alpine` | `sha256:2bb98716d81bd04894438e2e4fcb32943987abe8201c9a0cd7280d8720cfe2d9` |

Bootstrap 이전 중 SDK가 public file의 top-level `clouds` mapping과 명시적 `OS_CLIENT_SECURE_FILE`을 요구함을 확인해 image helper에서 수정했다. Alpine의 `/bin/setpriv` 패키지 경로, Bash bracketed-paste 출력과 Debian console-only logout hook은 실제 image에서 확인하고 smoke를 교정했다. Errexit는 assertion subshell에 유지하므로 검증 실패를 무시하지 않는다. Source bootstrap marker/wire shape와 BFF API/UI·lease·Cinder ownership은 바꾸지 않는다. 별도 registry UUID를 운영자가 설정하기 전 private pull을 성공으로 표시하지 않는다.


## 로그인 중복 인증·조회 제거 검증 (2026-10-16, local-only)

`reduce-login-authority-roundtrips`는 요청 수명에만 묶인 native client/read 재사용과 최종 project 단일 교환으로 로그인 왕복을 줄인다. 준비된 Default reader·전체 manager projection은 native 무쓰기 증명 후 유지하고, 보정이 필요하면 기존 lease·fresh guard·변경 후 재검증을 수행한다. Fresh login의 일회성 응답 매핑만 frontend readiness를 확정하며, 저장 세션 복원은 여전히 `/auth/me`를 통과해야 한다. 권한 cache TTL·세션 수명·철회 규칙을 완화하지 않았다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| Native 반복 로그인 전후 | 동일 seed와 native HTTP당 합성25ms 지연, 실제 SDK·app HTTP·MariaDB·Redis. Reader/manager 각2회 반복 구간4개 중앙값은 **4,908.07→592.74ms**(최종 arm64), identity HTTP **168–170→20–21**, service password exchange **36–37→1**. amd64 중앙값은 **632.35ms**. Capture에는 response 뒤 prewarm 및 겹친 worker 요청이 포함될 수 있어 login-exclusive 호출 수로 주장하지 않는다. |
| Native 실패·권한 경계 | 수정 전29operations/947assertions, 최종 arm64 **29/1,016**, amd64 **29/1,005** 모두 통과. Reader/manager 무쓰기, 최초 reader 보정, legacy/projectless, 명시 scope·home identity, 잘못된 password·disabled 계정/domain, 외부 manager 철회 후 stale projection 정리, fresh disabled refresh, committed grant503의 재전송 없음, refresh rotation/replay·logout 거부를 실제 HTTP로 확인했다. Unknown native endpoint0. |
| Compiled fresh login | 기존 compiled frontend+수정 전 backend와 최종 arm64 images의 Chromium 단일 표본. 로그인 click→작업 영역 chooser 활성화 **7,228→779.4ms**, login API **4,901.6→691.6ms**. 기존 즉시 `/auth/me` **2,296.4ms**가 최종 fresh login에서는 요청되지 않는다. 전체 dashboard resource load 완료 시간이나 사용자가 제시한 운영22.66초와의 전후 비교가 아니다. |
| Compiled session 경계 | Reload의 실제 `/me`200을 보류하면 chooser disabled, 응답 뒤 enabled. 실제 server logout 후 복원 및 손상된 tab token 복원은 `/me`401→로그인 복귀·저장 snapshot 제거. 이전 `/me`200을 지연한 상태에서 UI logout→새 login 뒤 이전 응답을 해제해도 old request는 abort되고 새 session/chooser를 유지했다. Same-token ABA/non-cooperative callback은 영구 회귀에서 별도 확인했다. |
| Refresh consumer 연속성 | 첫 dashboard summary만 합성401을 주입해 실제 refresh rotation과 새 `/me`를 실행했다. 새 token 검증 응답 보류 중 기존 chooser node가 유지되고 disabled 전이0, 최종 dashboard 상태 유지. 자연 만료 시간 측정은 아니다. 최초 cooperative-priority 응답 해제 harness의 timeout 및 browser clock trigger 미발생은 수용 증거에서 제외했다. |
| 화면 | 실제1440×1000·390×844의 login/dashboard를 시각 확인했다. Mobile document overflow0·chooser readiness를 확인했고 외부 font는 차단했다. UI markup/style/번역 변경은 없으며 전 locale/theme matrix를 새로 통과했다고 주장하지 않는다. |
| 회귀 | Exact backend **220passed**, 최종 `auth` backend **414**/frontend **208**, `access` backend **1,036**/frontend **166**. 전체 frontend **392files/4,014passed**, Node log runner **9passed**. Target runner12·selector validation 및 변경 Python11files Ruff check/format 통과. 초기 access fake SDK session fixture는 실제 Session cleanup 계약으로 고쳤고 인증 결과 assertion은 유지했다. |
| 전체 gate | Frozen source의 `npm run test:gate`는 docs guard와 JS/Kolla/installer lane 뒤 backend **7,375passed/11failed/91skipped**에서 중단했다. 실패는 범위 밖 기존 `test_instance_storage_delete.py` block-consumer DB/managed grant 정리11건이다. 뒤의 frontend/contract/functional/lint가 gate에서 실행됐다고 합산하지 않는다. 최초 owned snapshot의 root node_modules symlink로 발생한 stale guard는 그 symlink만 제거한 뒤 교정했다. |
| Canonical image·배포 | Root Dockerfile backend/frontend/worker/native-vm의 arm64+amd64 및 amd64-only native-cloud-vm **9build** 통과. Python/Node와 해당 image의 OpenTofu1.8.3·Ceph18.2.7을 실행하고 Python image7개의 backend303files hash parity를 확인했다. 정본 dev Compose+task override 양쪽 architecture의 API/frontend/DB/fixture health 및 실제 worker Redis 미래 lease·leader, 종료0·membership 제거 통과. Native supervisor3조건은 fresh tmpfs DB/Redis의 login→domain 생성→Default 선택→IAM·종료0이며 실제 VM boot는 아니다. |
| Source·architecture | Frozen `source-1792140968268021000`의 별도 dev/index에서 working/staged guard **1ad840382a0bbc5a982c8c6f76e97f0f876f55963e369a28ebe6693ff2383417 /3,000files**. 로그인 소유 code/tests37files는 최종 build 입력과 일치한다. Freeze 뒤 동시 수정된 `Dockerfile`, `backend/app/config.py`, `backend/app/services/cloud_shell.py`, `backend/app/services/zun.py`는 보존했으며 이 결과가 최신 checkout 전체 image/다른 작업의 acceptance는 아니다. 공유 index/review marker는 수정하지 않았다. |

Proof: `~/.local/share/afterglow-proofs/login-authority-20261016-do6d41qc/`의 `comparison-{arm64,amd64}/comparison.json`, `native-{arm64,amd64}/receipt.json`, `browser-qualification.json`, `browser-*.webp`, `builds.json`, `binaries.json`, `native-supervisors.json`, `worker-readiness-shutdown.json`, `regression-results.json`, `full-gate.log`, `architecture-final.json`, `final-source-parity.json`, `cleanup.json`, `shared-after.json`. 소유 container26개/network5개·QA image tag9개와 browser/profile을 정리했고 기존 local stack19개의 ID/image/mount는 그대로다(running15/healthy9). Named volume 삭제·prune·commit/stage/push·기존 stack 교체·운영 배포는 하지 않았다.

실제인 경계는 compiled application·SDK transport·SQL·Redis·browser이고 native identity/policy/cloud는 synthetic이다. 운영 Keystone policy·SSO/외부 IdP·사용자 실제 로그인 개선 시간·mixed-version/운영 rollout은 미검증이다. 새 schema/config/dependency는 없으며 선택적 gbrain CLI 부재로 검색 index sync는 미실행이다.

## 도메인·프로젝트 통합 작업 영역 검증 (2026-10-16, local-only)

`manage-domain-project-workspaces`는 좌상단의 도메인→프로젝트 선택, 계정별 표시 선호, exact-domain `project_creator`, 단일 owner와 명시적 이전, 신규 human 개인 identity domain, 즉시 Default reader 가입, domain allocation budget 및 IAM 사용량·리소스 관측을 구현한다. 기존 계정·서비스 identity를 이동하지 않고 운영 role/grant·데이터·키·private 설정·공유 index를 보존했다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| Named target·회귀 | `auth` backend **378**/frontend **171**, `access` backend **951**/frontend **162**, design **128** 통과. 최종 optional-resource project deletion **49** 통과. 실제 브라우저에서 발견한 최초 sparse quota 입력의 저장 누락을 교정하고 `QuotaEditor`의 첫 값·0·무제한·명시적 제거 **2**회귀가 통과했다. |
| 전체 frontend·contract·functional | Frozen source의 frontend **390files/3,969passed**, Node log-runner **9passed**. Contract **177passed**. 정본 Compose의 실제 MariaDB/PostgreSQL/Redis functional **159passed/31deselected**이며 PostgreSQL readiness·SELECT가 모든 checkpointer 동작의 증거는 아니다. |
| 전체 gate의 잔여 실패 | `npm run test:gate`는 backend **7,303passed/11failed/91skipped**에서 중단했다. 실패는 기존 `test_instance_storage_delete.py`의 managed grant/rule cleanup11건이다. 별도 Ruff check는 통과했지만 format은 `app/api/compute/instances.py`, `app/services/mcp_control_plane/connection.py`, `tests/test_admin_flavor_reconcile.py`, `tests/test_mcp_consumer_auth.py`, `tests/test_palimpsest_dockerfile.py`, `tests/test_resource_policies.py` **6files**가 남는다. 전체 gate 성공·commit 가능 상태로 보고하지 않는다. |
| 언어·type check | i18n **47namespaces/10,623messages,0errors/0warnings**, scan **1,126files,hard-coded Korean0**. Svelte는 범위 밖 `dashboard/database/instances/+page.svelte:42`의 `PageState.instanceId` **1error**와 기존 DocCodeBlock/WizardStep5Config/ProjectUsageTable **3warnings**가 남는다. |
| Native deployed behavior | 최종 arm64/amd64 격리 Compose 각각 **477 assertions/7scenarios, 실패0**, native mutation109회와 unsupported endpoint0을 확인했다. 실제 application auth/rotation·명시 소속·동일 표시 이름·새 human 개인 domain·SMTP capture 뒤 signup/초대 수락·creator/sole owner 이전·unknown reply settlement·finite budget/default·partial/timeout·empty/unknown/nonempty project deletion 경계를 포함한다. Backend/frontend/DB/fixture health와 Redis Notion membership/leader를 확인했고 native supervisor3조건도 auth→domain 생성→Default 선택→IAM 및 graceful exit0을 통과했다. 실제 VM boot는 아니다. |
| 실제 SQL migration | 격리 MariaDB **11.4.13/utf8mb4**의 별도 schema에서091 old enrollment row를 준비하고092→093→094를 실행했다. 기존 row/identity 보존·`added_grants=[]` backfill, old-column INSERT의 NULL 허용, quota policy·unknown quota/ownership journal의 저장/readback을 확인했다. SQL additive compatibility이지 구형 writer의 새 budget/fence 의미나 운영 snapshot·mixed-version·backup/restore 증거는 아니다. |
| 최종 compiled Chromium | 실제 최종 image와 application API를 연결해 로그인→chooser domain 생성→Default 선택→새 Analytics project→단일 owner 표시, pin/hide/recover/order와 reload 유지, sparse quota 첫 값2 저장과 explicit fresh readback 후 편집 재개를 확인했다.4locale×2theme×390/767/768/1023/1024/1440px **48조건/192surfaces**, screenshot64개에서 selector·display settings·quota·domain resources의 document overflow0 및 dialog/footer 경계·page error0을 확인했다. Guidance는 실제 오류가 아닌 info tone이다. |
| Architecture·source parity | Frozen public source의 별도 dev/index에서 working stamp와 staged guard가 같은 `dfdd4b5313866f70c18dcad49d29791d299c9563bf3224827a707fbed5ee10a9`/2,993files로 통과했다. 현재 runtime/migration/frontend source2,299files가 최종 build source 및 gate snapshot과 일치하고 Python image7개의 backend302files도 일치했다. 동시 WIP가 포함된 snapshot이므로 범위 밖 변경 전체 acceptance는 아니다. 공유 index/review marker는 보존했다. |
| Canonical build·실행 binary | Root Dockerfile backend/frontend/worker/native-vm의 arm64+amd64와 amd64-only native-cloud-vm **9build** 통과. 각 image의 architecture·Python/Node와 해당 target의 OpenTofu/Ceph binary를 실제 실행하고 backend source parity를 확인했다. 마지막 informational guidance tone까지 포함한 frozen source는 `source-1792099873866087000`, manifest SHA256 `6e16e53f36ad0de503bb335f441743b78cc7f1864d8149ad9ca190508c3657f9`/4,913files다. |
| Docker Desktop 복구 | Engine `/_ping`·API가 응답하지 않는 상태에서 사용자 승인으로 Desktop만 재시작했다. 기존 local MariaDB/PostgreSQL container를 같은 ID로 다시 시작하고 API6개·datastore3개의 health를 확인했다. Volume·키·설정을 지우거나 바꾸지 않았고, 중지로 tmpfs가 사라진 feature fixture는 새 격리 project로 대체했다. |

Domain quota는 Afterglow가 쓰는 native 프로젝트 limit의 합계 budget이며 cloud-wide 실사용 hard cap이 아니다. Disabled project를 포함하고 missing/unknown/unsupported/0/-1을 구분한다. 사용자별 수치는 native `user_id`로 귀속 가능한 사용량이며 별도 user quota를 만들어내지 않는다. Enrollment·quota·ownership의 불명확한 native effect는 journal/readback/명시적 settlement로 처리하며 자동 재전송·추측 rollback은 하지 않는다.

Durable proof: `~/.local/share/afterglow-proofs/domain-workspaces-native-20261016-gFHvgyek/`. 실패한 초기 harness/fixture·gate 결과도 보존했다. 실제 경계는 built `app.main`, installed SDK, HTTP, SQL, Redis와 compiled UI이고 Keystone·cloud resource·SMTP는 격리 synthetic boundary다. 운영 정책/외부 IdP·실제 이메일 delivery·실제 VM boot·production migration·mixed-version·backup/restore·운영 배포 수용의 증거가 아니다. Schema092–094는 기존 schema 업그레이드와 writer drain이 필요하며 세부 복구 제한은 [배포 가이드](deployment.md)를 따른다. 선택적 gbrain CLI 부재로 검색 sync는 미실행이다.

최종 receipt는 `native-arm64/receipt.json`, `native-amd64/receipt.json`, `builds.json`, `binaries.json`, `native-supervisors.json`, `migration-native.json`, `architecture-final.json`, `final-source-parity.json`, `postrestart/browser/matrix.json`, `browser-final-flow.json`에 분리했다. 장시간 열려 있던 이전 QA 세션은 실제401 `세션이 만료되었습니다` 뒤 정상 폼으로 재인증했으며 만료·회수 규칙을 완화하지 않았다. 초기 quota readback 대기는 자동 재편집을 기대한 harness 오류였고 실제 계약인 명시적 관측 새로고침으로 확인했다.

마지막 실제 system-scope 관리자 로그인으로 exact-domain 관측과 ceiling editor의 info guidance도 확인했다(`postrestart/admin-budget.webp`). QA 소유 container36개·network6개와 browser3개/profile3개만 정리했고 named volume 삭제·global prune은 없었다. 기존 local stack19container의 ID·image·mount가 복구 직후 기록과 같고 running15개/healthy9개를 유지한다. 이 기능의 image를 기존 개발 stack이나 운영에 덮어쓰지 않았다.


## 공통 언어 쿠키 통일 검증 (2026-10-16, local-only)

`unify-browser-language-cookie`는 문서 URL 전용 언어와 앱 쿠키의 분리를 제거한다. `/docs`·메인·로그인·인증 후 화면은 같은 root-path `afterglow_locale` 선호를 사용하고, 문서의 명시적 `lang=ko|en|ja|zh-CN`도 그 선호에 반영한다. 기존 backend·인증/인가·schema·운영 배포와 공유 index는 변경하지 않았다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| 수정 전 실제 Chromium | 로그인 영어 선택은 cookie `en`인데 `/docs`의 HTML·본문은 `ko`였다. 문서 일본어 선택 뒤 cookie는 여전히 `en`이고 로그인 복귀도 영어였다. 초기 수정 뒤에도 미리 읽힌 문서 링크가 변경 전 언어를 되살리는 것을 확인해 `afterglow:locale` invalidation을 추가했다. |
| 최종 frontend 회귀 | Node24.14.1에서 `npm --prefix frontend test`: Vitest **383files/3,910passed**, Node log-runner **9passed**. 최초 focused6files/108passed도 확인했다. PTY가 다른 PATH의 Homebrew Node26.9.0을 사용한 실행은 experimental Web Storage/jsdom 충돌로47files/470tests와5unhandled errors가 실패했다. 기존 프로젝트 지침대로 Node24 runtime으로 재실행해 전체 통과했고 source·테스트·오류 처리를 우회하지 않았다. |
| i18n·Svelte | `i18n:check`: **45namespaces/10,381messages,0errors/0warnings**. `i18n:scan`: **1,108files,hard-coded Korean0**. 최종 `check`는 변경한 docs 오류 없이 범위 밖 `dashboard/database/instances/+page.svelte:42`의 `PageState.instanceId` **1error**와 DocCodeBlock/WizardStep5Config/ProjectUsageTable **3warnings**가 남았다. 전체 type check 성공은 아니다. |
| 실제 SSR HTTP | 현재 source Vite4176에서4locale×메인·로그인·docs home·Nova·missing docs·dashboard **24응답**의 HTML `lang`이 쿠키와 일치했다. Missing docs는404를 유지하며 explicit Korean 응답은 `afterglow_locale=ko; Max-Age=31536000; Path=/; SameSite=Lax`를 기록했다. HTTPS Secure는 hook 회귀에서 확인했다. |
| 실제 Chromium 내비게이션 |4locale의 앱 선택→언어 query 없는 docs→콘솔→reload에서 cookie·HTML·docs 본문·header choice 일치. 실제 domain/username/password 폼을 합성 API로 제출하여 중국어 로그인 후 dashboard를 확인했고, logout은 auth/session marker만 지우며 언어는 유지했다. 새 auth 우회나 실제 Keystone 계정 사용은 없다. |
| Preload·기사·오류·no-JS | 실제 docs `__data.json?lang=en` hover preload는200·Set-Cookie 없음·현재 한국어 유지, click 뒤 영어로 commit됐다. Nova에서 언어 전환은 `reader=shared#connect-verify`를 보존했다. 저장된 중국어의 docs404 문구와 복구 동작을 확인했다. JS를 꺼서 query 없는 Nova가 일본어를 상속하고 native Korean 링크가 cookie·본문을 한국어로 바꾼 뒤 로그인 SSR도 한국어인 것을 확인했다. |
| Responsive/theme |4locale×light/dark×390/800/1440px **24조건/48docs·console surfaces**에서 언어/선택 상태 일치, document overflow0, 펼친 문서 언어 메뉴 viewport 내 배치를 확인했다. 기존 디자인·번역 문구·권한 동작은 변경하지 않았다. |
| Architecture | Frozen public working-source의 별도 임시 dev/index에서 stamp·working·staged guard가 모두 `a166d8c1b3693e1653e3fe4e11cc341349c5b0208958a916db9c4f522ca27e40`/2,945files로 통과했다. Digest에는 동시 WIP가 포함되므로 전체 변경의 검토/acceptance가 아니다. 공유 index·active review marker는 보존했다. |

Proof: `~/.local/share/afterglow-proofs/locale-cookie-20261016/`의 `browser-receipt.json`, `architecture.json`, `verification.json`, `docs-en-desktop.png`, `login-en-mobile.png`. Browser와4176서버·QA profile·임시 architecture snapshot은 정리했다. 인증·API 응답은 합성이며 dashboard의 범위 밖 data API는 격리503으로 막았으므로 실제 인증/클라우드·운영 화면·전체 backend/functional `test:gate`·production build/배포 증거가 아니다. 외부 font는 차단했으며 선택적 gbrain CLI 부재로 search sync는 미실행이다.

## 로컬 로그인 지연·인증 debug 진단 검증 (2026-10-15)

`repair-local-login-debug-diagnostics`는 설정된 Keystone interface/region을 무시하던 native client와 중복 권위 조회, 실제 mount에서 꺼져 있던 debug 및 처리된 인증 예외의 로그 누락을 수정한다. Native 역할·상속·project/domain/system 경계는 유지하고 동일 호출 내 읽기만 재사용한다. 호출 사이 권한 cache는 추가하지 않는다. 새 schema·endpoint·dependency·배포 topology는 없으며 기존 prepared env·키·볼륨·공유 index를 보존한다.

| 검증 경계 | 관측 결과·한계 |
|---|---|
| 실제 native 읽기 전후 | 같은 설정 계정의 installed SDK 인증·권위 확인: 총 HTTP **674→50**, `login_authority` **31.760→5.311초**. 기존 client의 public endpoint 선택을 설정된 internal로 교정했고 수정 뒤 요청은 모두 internal이었다. 이 수치는 전체 브라우저 로그인 시간이 아니다. |
| 정확한 회귀·named target | 진단/logging/rotation **89passed**, endpoint 선택 **3passed**. 최종 `auth` backend **371**/frontend **134**, `access` backend **637**/frontend **135** 통과. 초기 stale fixture의 interface/region 누락과 home membership에서 unrelated foreign inventory를 요구하던 옛 기대값을 교정했다. Scoped Ruff check/format 통과; 이번 변경에서 전체 `test:gate`는 실행하지 않았다. |
| Native 실패 진단 | 실제 설치된 Keystone SDK를 loopback의 닫힌 TCP port에 연결했다. Backend 양쪽 architecture와 native image3종 모두 API503 및 stream/file 양쪽의 `domain_resolution`·`request`, 동일 correlation, 함수/줄 번호, `ConnectionRefusedError`/errno111을 확인했다. Host는 errno61. Exception message·source·locals·wire DEBUG·credential은 출력하지 않는다. |
| Canonical build/runtime | Root Dockerfile backend/worker/native-vm의 arm64+amd64와 native-cloud-vm amd64 **7build 통과**. Python·해당 image의 OpenTofu1.8.3/architecture·Ceph18.2.7을 실제 실행하고 모든 image의 `backend/app` **302files**가 frozen source 및 현재 runtime source와 일치함을 확인했다. Native supervisor3조건은 API/frontend health·login document200, 종료0이며 실제 VM boot/systemd 증거는 아니다. |
| 격리 amd64 Compose | 정본 `docker-compose.dev.yml` + task-only override의 실제 MariaDB/Redis·installed SDK·합성 Keystone으로 domain resolve/login/me/domains/refresh/logout **6개 HTTP200·no-store**. Backend/DB healthy, Notion membership1과 project/home identity·system admin을 확인했다. 자체 tmpfs container/network만 정리했으며 운영 Keystone 성공으로 승격하지 않는다. |
| 기존 로컬 Compose | 검증된 arm64 backend·notion-worker만 `--no-deps --no-build --pull never --force-recreate --wait`로 교체했다. Backend healthy, worker는 Docker healthcheck가 없으므로 Redis TIME보다 미래인 자기 membership lease1개로 readiness를 확인했다. 기존 image rollback tag와 mount를 보존하고 나머지 **17containers**는 ID가 그대로다. |
| 실제 로그인·브라우저 | 배포 뒤 서버 로그에서 domain resolve200/**0.565초**, 실제 password login200/**21.971초**, projects/me200을 관측했다. 기존 실제 브라우저 세션의 `/auth/me`200/**12.954초**·no-store, system admin/domain manager·동일 home/working domain과 project scope, 대시보드·도메인 IAM 메뉴를 확인했다. 서비스 계정으로 scripted full login을 실행한 증거와 구분한다. 지연이 제거됐거나 모든 native/SSO 흐름이 통과했다는 뜻은 아니다. |
| 실제 debug 안전성 | 새 backend의 startup event는 application DEBUG/root INFO다. 실제 login의 `authenticate`, `domain_preparation`, `session_publication`과 native 하위 단계 완료 duration이 한 correlation으로 남는다. 배포 로그에 설정 계정 비밀번호와 보호된 SDK wire DEBUG가 없음을 확인했다. |

실계정 안전 preflight는 GET/HEAD와 token 발급 POST만 허용했다. 서비스 계정의 Default reader grant가 없고 network no-op 증명도 실패했으므로 **agent는 해당 계정의 full login을 실행하지 않았다**. 일반 login은 기존 계약에 따라 native baseline/projection·기본 네트워크를 변경할 수 있으므로 read-only 진단으로 취급하지 않는다. 위 실제 로그인 성공은 별도로 관측된 로컬 서버/브라우저 증거다. 운영 배포·수동 IAM 수정·실제 VM boot·SSO/provider callback·mixed-version/복구는 이 변경의 검증 범위가 아니다.

Durable proof: `~/.local/share/afterglow-proofs/login-debug-20261015T055711Z/`의 `native-before.json`, `native-after-source.json`, `builds.json`, `image-runtime.json`, `compose-amd64.json`, `source-parity.json`, `local-deployed.json`, `deployed-auth-events.json`, `browser-existing-session.json`, `existing-session-iam.webp`. Private 설정 snapshot/env는 이 외부 디렉터리에만 보존하며 공개 receipt에 복사하지 않는다. 초기 worker readiness harness의 Redis `aclose()` cleanup은 설치된 client의 `close()`로 교정한 뒤 exit0을 확인했다. 테스트·빌드에 포함된 동시 WIP 전체의 acceptance나 전체 gate 성공을 주장하지 않는다.

Architecture working stamp와 격리 index staged guard는 frozen public source + 최종 test-only 교정2개의 동일 `7a12ec7f4dc62b9b3a68a9ec203c8929a88fc557a1b0c711edc0947c191797fd`/2,943files로 통과했다(`architecture.json`). 공유 index/review marker는 수정하지 않았다. Docker Desktop의 `/host_mnt/Users/`와 `/Users/` host alias를 정규화해 기존19container의 mount/volume identity도 일치함을 확인했다. 선택적 gbrain CLI 부재로 검색 index sync는 미실행이며 설치·설정 변경은 하지 않았다.

## Default 공통 manager·작업 도메인 검증 (2026-10-15, local-only)

`default-project-domain-authority`는 기존 identity 도메인을 이동하지 않고 canonical Default manager, verified-login reader baseline, 작업 도메인 선택·생성과 exact system admin을 구현한다. 공유 `dev`와 private 설정·기존 볼륨·index는 보존하며 운영 grant·프로젝트·계정을 변경하지 않는다. Public frozen source는 `/var/folders/1m/xfc726k14szbjnrlq5t68zjw0000gn/T/afterglow-default-domain-source-2jt__cga`, 통합 proof는 `~/.local/share/afterglow-proofs/default-domain-authority-20261015-9ca2/`다. 동시 WIP도 포함한 snapshot이므로 이 작업의 acceptance와 전체 통합 gate를 구분한다.

| 실행 경계 | 관측 결과·한계 |
|---|---|
| Feature-focused regression | Backend **853passed /18deselected**. `test_default_domain_policy`의 committed manager revoke·HOME domain disable2조건은 수정 전 실패했고 수정 후 인접3files102passed. 최종 named auth는 backend354/frontend134, access는 backend616/frontend135가 통과했다. |
| Installed SDK·API·Redis | 실제 python-keystoneclient/openstacksdk/keystoneauth1 → loopback Keystone HTTP, 실제 Uvicorn affected routers, Redis7.4.11 Lua 및 SQLite 정책으로 **127PASS /0FAIL**. External creator·원래 세션 보존·Default baseline·native ordinary-project reader·IAM/시스템 권한 분리·group/inference last-manager·scope/lifetime/provider/race·ACL fail-closed를 검증했다. |
| 불명확한 native 응답 | 정상 DELETE204와 commit뒤503을 구분했다. 실제 installed requests15초 timeout에 committed reply를16초 지연시켜 **ReadTimeout15.000653초**, API503, DELETE1회, manager/projection/access/session 정리를 확인했다. HOME domain disable의 committed503도 정리됐다. |
| Native hierarchy | enabled child가 있는 일반 parent disable403, child 먼저 disable, disabled parent 아래 create400/enable403, disabled domain 아래 create400와 disabled project rescope403. 초기107조건의 불가능한 disabled-ancestor fixture는 철회했고 corrected127만 최종 증거다. |
| Compiled browser | 실제 host adapter-node production UI + 합성 API에서 **795 qualified assertions /0fail**(기존695+최종 copy/trusted-IME100), 4locale×2theme×390/1440의192view조건과16modal조건,297screenshots. Native Enter·pending1회·선택/생성/uncertainty·의도 continuation·late/foreign response·project-independent IAM와 관리자 모드를 확인했다. 외부 Google Geist 요청은 차단했고 local Pretendard/system CJK로 관측했으므로 production Geist 폭의 증거는 아니다. |
| Browser 발견사항·IME | 네 locale IAM help의 재로그인 지시를 working domain·계정 소속 유지 안내로 수정했다. 새 production chunk `D-uTAgyn.js`의 SHA256 `6e38d2b7bb740b9c66d96fe1bd6b99cc657ab5fd8cb705526523d73486c1adbf`와 새4문구 존재·옛4문구 부재를 먼저 확인한 뒤16IAM조건/32screenshots를 재검증했다. Trusted CDP composition은 domain/username/password에서 `isTrusted=true,isComposing=true,keyCode=229,defaultPrevented=true`, 조기 요청0회와 commit뒤 Enter1회를 확인했다. OS-native candidate window나 실인증 증거는 아니다. |
| Canonical 이미지·배포 | Root Dockerfile backend/frontend/worker/native-vm의 arm64+amd64와 amd64-only native-cloud-vm **9build 모두 통과**. 각 architecture의 Python/Node/OpenTofu를 실행하고 Python image7개의 backend/app294파일 hash를 확인했다. 격리 `docker-compose.dev.yml` 배포2조건에서 backend/frontend/MariaDB healthy, 실제 Redis Notion membership/leader와 graceful exit0을 확인했다. Native supervisor3조건은 API/frontend/login HTTP 및 exit0이며 실제 VM 부팅은 아니다. |
| Built main app 인증 경계 | 양쪽 architecture의 변경 없는 `app.main`·installed SDK·실제 MariaDB/Redis·합성 Keystone HTTP로 도메인 생성/Default·원래 session의 도메인 조회/전환·동일 native user/home identity·이전 access/refresh401·IAM·cross-domain project403을 확인했다. API로 직접 만든 프로젝트의 명시적 project_owner 쓰기와 별도 native 프로젝트에서 manager-only reader/no-write를 분리했다. |
| 전체 gate와 후속 교정 | 실제 `npm run test:gate` **1회는 실패**: backend6,966passed/89failed/91skipped에서 중단. 새 identity/native membership 계약을 누락한 Palimpsest51·volume transfer27·별도 contract4실패의 fixture를 보완했다. 최종 package132passed, 관련7files342passed, 전체 contract177passed. Native 권위 guard를 우회하지 않았고 기존11개 instance-storage delete 실패는 범위 밖으로 보존했다. Gate 전체를 다시 통과했다고 합산하지 않는다. |
| 나머지 canonical 검증 | Gate 중단 뒤 별도 전체 frontend **383files/3,899passed+Node9passed**, 실제 MariaDB/Redis functional **159passed/31deselected/0skipped**(domain enrollment5포함). PostgreSQL은 readiness와 SELECT만 확인했으며 checkpointer application proof가 아니다. Backend Ruff check와 수정11files format 통과; 범위 밖 format6files와 알려진 Svelte `PageState.instanceId` 오류는 미해결이다. i18n45namespace/10,381message는0errors/0warnings, scan1,108files는 hard-coded Korean0. |
| Infra·source 경계 | 사용자 승인 후 Docker Desktop을 재시작하고 기존 local DB/volume을 복구했다. 원래 `afterglow-local-services` 네트워크는 `10.201.0.0/24`, 앱6개·DB3개 healthy와 migration/bootstrap4개 exit0을 확인했다. 기능 image qualification은 별도 격리 project만 대상으로 했으며 동시 변경된 `HubArtifactsPanel.svelte`는 frozen image에 포함되지 않았다. 해당 images를 기존 개발 stack에 덮어쓰거나 운영에 배포하지 않았다. |

Corrected native archive는 `~/.local/share/afterglow-proofs/default-domain-native-20261015-PZfCIHpL/native-proof.tar.gz`(SHA256 `97f701a9f97cd60c35e43f4b201a79ef3dd50365a49562ccf0fe2f18c18edcf9`)이며 HTTP/state/sourcehash/transportexception/정확한 실행 command와 cleanup을 포함한다. Browser receipt는 `~/.local/share/afterglow-proofs/default-domain-authority-browser-1792009012472/receipt.json`; superseded harness attempts17개도 보존한다. Browser/fixture/profile과 부모 소유 production UI server는 종료했다.

Image receipt는 통합 proof의 `final-receipt.json`, 최초 전체 gate 원본은 `gate-proof/RECEIPT.md`, fixture 최종 교정은 `post-gate-final.json`이다. 최초 실패·중간 fixture 실패를 보존했다. Full gate의 JS orchestration175·Kolla Node24/Python11·installer20은 통과했고 PowerShell 부재36개는 skip이다. 미해결 format 대상은 `app/api/compute/instances.py`, `app/api/identity/admin.py`, `app/services/mcp_control_plane/connection.py`, `tests/test_mcp_consumer_auth.py`, `tests/test_palimpsest_dockerfile.py`, `tests/test_resource_policies.py`다. 원래 개발 stack의 worker Running은 readiness 증거로 세지 않으며, feature-owned fixture/container/network/profile/server만 종료했다.

Native Keystone/state·provider metadata는 합성이며 SQLite는 운영 MySQL이 아니다. 실제 enrollment SMTP·외부 OIDC callback·운영 Keystone policy·mixed-version/backup/restore는 이127조건의 증거가 아니다. 측정된40,564nativeHTTP/2,388service-admin password exchange는87API case와 setup/state를 포함하며 fresh `_get_admin_ks_client`와 반복 권위 조회의 부하 위험을 드러낸다. **[INFERENCE] 원격 Keystone 지연에서는 응답 시간이 커질 수 있다.** 이는 production latency benchmark가 아니며 권한 cache를 느슨하게 하거나 service-account impersonation으로 우회하지 않았다.

이 변경에는 새 SQL schema가 없지만 기존090/091·암호화 키가 필요하다. Session identity/working-domain 및 Default 관리 모델은 구형 writer와 동일 의미가 아니므로 mixed-version을 자동 호환으로 가정하지 않는다. 기존 도메인 creator는 운영자가 명시적으로 확인해 bootstrap하고 전체 API/UI cutover와 session 재인증을 계획해야 한다. 이미 발급된 native token·외부 Keystone mutation은 Afterglow graph lease 밖에 있다.

## 도메인 격리·IAM 검증 (2026-10-15, local-only)

`domain-isolation-iam`은 shared `dev`의 현재 source에 system:all 관리자 경계, explicit tenant domain, 관리 모니터링·사용자 IAM·domain-first password/federation·verified-email enrollment를 구현한다. 기존 Default identity/data/grant·private 설정·공유 index·운영 IAM은 보존했다. 실제 서비스와 합성 adapter의 근거는 분리하며 외부 IdP·SMTP·운영 Keystone/policy 수용을 주장하지 않는다.

| 검증 경계 | 관측 결과 |
|---|---|
| Backend 초기 integration | 첫 전체 unit은298failed/6580passed/91skipped였다. Explicit synthetic admin fixture와 native-domain metadata/interface·email normalization·no-store/error mapping을 수정한 두 번째 실행은23failed/6855passed/91skipped였다. 이 수치는 최종 통과가 아니라 수정 전 증거다. |
| Credential actual HTTP | 실제 Uvicorn main app → installed OpenStack SDK → loopback Keystone6조건 통과. Domain 누락/빈 값·빈 owner query는422이며 native lookup0, same-domain inventory200·secret 제외, foreign owner403, native issuance 검증 실패+cleanup503은502 `credential_rollback_failed`·no-store·secret 비공개다. Admin identity와 Keystone issuer만 합성이다. |
| MCP native domain boundary | 설치된 Keystone SDK와 loopback HTTP4조건에서 same-domain saved credential만 허용하고 foreign project domain·missing user/project domain은 거부했다. 실제 cloud가 아니다. |
| Frontend diagnostics | i18n43namespaces/10223messages는0errors/0warnings. Svelte check의 owned diagnostics를 수정했고 남은1error(database instances PageState의 `instanceId`)·3warnings(DocCodeBlock, WizardStep5Config, ProjectUsageTable)은 범위 밖 기존 source다. 전체 type check 성공이 아니다. |
| 최종 frozen canonical gate | `npm run test:gate`의 architecture·JS orchestration/Kolla/install lane 통과 후 backend unit은**6,868passed /91skipped /11failed**(67.85s)다. 실패는 모두 기존 `test_instance_storage_delete.py` block-consumer tracking/DB 계약이다. Gate는 여기서 중단했으며 전체 통과·뒤의 frontend/contract/functional/lint 실행을 주장하지 않는다. |
| 별도 canonical contract·functional | 격리 설정 cwd에서 `test-target.js contracts` **174passed**, 실제 MariaDB/PostgreSQL/Redis를 사용하는 `test-db.js --no-start --keep` **159passed /30deselected**. Domain IAM DB5, auth/IAM+fake Redis117, real Redis session race7도 통과했다. PostgreSQL16.14 savepoint/write/rollback 후 잔여 row0. |
| 실제 SQL·Redis + TCP HTTP | MariaDB11.4.13·Redis7.4.11, manifest93개 checksum, migration090/091 각각2회 적용 및 ORM9/23/19개 column·nullability·PK/index parity 통과. Policy/provider revision·duplicate·last-method rollback, domain-bound secret, 동시 수락200/410, 가입 시 project 자동 가입 없음, SMTP 실패 `delivery_failed`, `recovery_required→revoked`, 최종 commit 실패 보상 `failed`, stale-JTI family revoke를 확인했다. Native Keystone·federation·SMTP만 합성이며 pytest fixture를 import하지 않는 standalone runtime이다. |
| 최종 frontend | **378files /3,751tests 전체 통과**, skip0. Domain edit 시 username/password/method를 모두 비우며, 실제 delayed Slow→Other 응답은 새 domain을 덮지 않는다. Announcement complete pagination·foreign-domain recipient 회귀도 포함한다. |
| 현재 source Chromium | ko/en/ja/zh-CN ×390/767/768/1023/1024/1440의144dark조건, English12light조건, 사용자 생성 modal3조건. Domain-first password POST, provider 시작/continuation, selected-domain 사용자 생성, 명시 domain 변경·old row 제거, 실제 OPTIONS204→credential GET403 후 system-admin 유지, IAM·monitoring의 unavailable/partial/0 표현을 확인했다. API·native identity/provider/cloud는 합성이며 real callback/email·browser provider/recovery writes·전체 admin application/group/project inventory·Firefox/Safari 검증이 아니다. |
| Canonical container build/run | Root Dockerfile `backend`·`worker`·`frontend`·`native-vm`은 linux/arm64+linux/amd64, amd64-only `native-cloud-vm`은 linux/amd64 build와 실행을 통과했다. 양쪽 backend image에서 실제 TCP/SQL/Redis enrollment smoke, OpenTofu1.8.3의 정확한 architecture·Ceph18.2.7 실행, worker image의 installed `afterglow-crypto`0.1.1 encrypt/decrypt를 확인했다. Native image3조건은 UID1000·network none·cap-drop ALL에서 API/frontend200·domain tables3·live Notion membership을 확인했으며 실제 VM 부팅 증거는 아니다. |
| Canonical 개발 배포 | Public-source snapshot의 `docker-compose.dev.yml`에 task-only image/loopback/QA datastore override를 적용해 `afterglow-domain-runtime`의 backend·frontend·notion-worker를 배포했다. Backend/frontend는 Docker healthy, healthcheck가 없는 worker는 실제 Redis TIME보다 미래인 자기 membership lease로 readiness를 확인했다. API/frontend health200, empty domain·domain 없는 password login422, unauthenticated IAM401·no-store 통과. 원래18000 port 충돌은 기존 process를 건드리지 않고59106(API)/59107(UI)로 회피했다. |
| 배포된 compiled UI | Arm64 frontend image의 실제 Chromium1440/390px에서 domain-first login과 credential 미노출을 확인했다. 실제 backend domain resolve는 cloud 미설정으로503이고 UI는 도메인 확인 불가를 표시하며 계속할 수 있는 password/SSO를 만들지 않는다. Mobile horizontal overflow0. 외부 font는 의도적으로 차단했다. 별도 amd64 image의 frontend health/login document200도 통과했다. |

Query validation 오류는 `Identifier = Query(...)`가 Pydantic `Annotated`의 ID 제약을 잃어 빈 domain을 native lookup에 보낸 것이 원인이다. `Annotated[Identifier, Query()]`와 optional counterpart로 수정했고 missing/empty selected-domain 및 empty-owner regression을 유지한다. Rollback 실패 회귀는 isolated router뿐 아니라 실제 main app middleware를 통과한다. 중앙5xx sanitizer에는 검토한 고정 code만 `public_service_error`로 공개하며 arbitrary exception detail은 계속 마스킹한다.

Private root TOML의 기존 `Invalid value (line10,column9)` 때문에 backend는 `/tmp/afterglow-domain-qa/cwd`에서 같은 source·venv와 명시적 `--rootdir`로 실행했다. Private 파일을 수정·출력하지 않았다. 범위 밖 storage deletion11실패는 기존 block-consumer WIP의 `lookup_for_server`가 없는 DB를 요구하는 경계이며, 위 공유 background-process 및 calendar 기록과 동일하다. Production guard나 삭제 safety를 낮춰 통과시키지 않는다.

Migration090/091은 policy/provider/enrollment의 additive 테이블이며 기존 identity·grant를 이동하지 않는다. 새 writer에는 schema-before-writer가 필요하고 old writer/new schema가 새 login policy를 집행한다는 보장은 없다. Domain metadata 없는 기존 session과 old invitation link는 재사용되지 않는다. 실제 운영 revision/ledger·복원 snapshot·원래 encryption key·혼합 버전·backup/restore 증거가 없어 운영 양방향 호환성은 미검증이다. API/UI/worker는 검증된 schema와 함께 일괄 cutover해야 하며 이미지 downgrade만으로 인증 정책 rollback을 보장하지 않는다.

검증 source는 private 설정을 제외한 public snapshot과 file mode/bytes가 동일한2,918files이며 final gate와 working/disposable-index staged architecture digest는 모두 `43c6754e611e21b012a822320c2de4145919ff1663405b98779b90917d068bb0`다. 공유 동시 WIP도 포함하므로 이 digest가 모든 기능의 acceptance를 뜻하지 않는다. 원래 Git index는 stage하지 않았고 임시 index만 사용·제거했다. Global gbrain CLI가 없어 search-index sync는 수행하지 않았으며 이 작업을 위해 별도 설치·설정 변경하지 않았다.

통합 receipt는 [`domain-isolation-iam/verification.json`](../openspec/changes/archive/2026-10-14-domain-isolation-iam/verification.json), durable 원본은 `~/.local/share/afterglow-proofs/domain-isolation-20261015/`다. Frontend receipt·matrix·network·race·screenshots와 통합 verification receipt에서 정확한 경계를 구분한다. 초기 unit 실패와 native HTTP/SQL/Redis 원본은 `/tmp/afterglow-domain-qa/`에 생성한 뒤 durable proof로 보존했다. 폐기된 GitLab/설정 구현 문자열을 고정하던 Kolla source-text test3개(184줄)를 삭제했으며 새로운 문자열 snapshot으로 재고정하지 않았다. 실제 TOML renderer의 layer precedence·public allowlist·secret 비공개·type rejection 테스트는 유지한다. Mockup native payload data는 기존 data-only localization exclusion 방식을 사용하고 UI catalog/scanner 검사는 유지한다.

## 추가 다섯 언어 dev 통합 검증 (2026-10-19; local-only)

`origin/i18n`의 기존 네 언어 커밋 `88113fb8`은 이미 `origin/dev`의 조상이다. 미반영된 변경은 별도 `afterglow-i18n` worktree의 미커밋 30개 tracked 파일과 243개 신규 파일이었다. 최신 fetched dev `08e272422cd855b30d39929c24993047ec0cd6ad`를 기준으로 격리 clone에 이 273개 파일만 byte-identical하게 옮겼다. 원래 worktree의 source/index와 공유 dirty dev checkout, private 설정은 수정하지 않았다. 기존 OpenSpec 두 archive의 과거 검증은 아래 새 실행과 구분해 보존한다.

| 검증 경계 | 실제 관측 |
|---|---|
| 번역 검사 | `i18n:check` 0 errors/0 warnings, 40 namespaces/10,022 source messages; `i18n:scan` 1,103 files/하드코딩 한국어 0. |
| 관련 회귀·컴파일 | canonical frontend cwd의 10 files/207 tests 통과. Svelte check 2,554 files/0 errors/기존 3 warnings, production build·adapter-node 완료. |
| 전체 프로젝트 gate | 최종 `npm run test:gate` 성공. Orchestration 175, Kolla 27 + Python resolver 11, shell CLI 20 passed/PowerShell 36 skipped, backend unit 6,781 passed/95 skipped, frontend 370 files/3,704 tests + Node runner 9, consumer contracts 174, disposable MariaDB/PostgreSQL/Redis functional 157 passed/29 deselected, Ruff check/format 639 files 통과. 관련 207 tests는 전체 frontend 결과와 중복 합산하지 않는다. |
| Architecture | 동일 source digest `8ba5b3fcb181cc5a201f6775b8c0c324065e641c24cbaf82b7d0c03a7ee09f50`/3,104 files의 working guard 통과. Frontend 현지화 경계만 확장하며 backend/API·인가·schema·dependency·배포 topology에는 구조 영향이 없다. |
| 실제 compiled 화면 | Node adapter를 loopback 4199에서 실행하고 Chromium 150에서 9 locales × 2 themes × 390/768/1440px × 메인/로그인/docs/tutorial console의 216조건을 확인했다. 각 조건의 실제 pathname, 9개 언어 항목, 최소 44px 행과 viewport 내 메뉴를 검증했으며 document 가로 overflow는 0이었다. |
| 선택·유지 동선 | 추가 5개 언어를 실제 로그인 메뉴에서 선택 → 언어 없는 docs → Manila 가이드에서 다음 언어 선택 → 로그인 복귀·reload를 검증했다. 번역된 로그인 버튼·문서 제목, 공용 쿠키·HTML lang과 hydrated reader query/fragment를 확인했다. |
| SSR·native·keyboard | 9 locales × 로그인/docs/Manila 27개 HTTP 응답의 초기 lang을 확인했다. 명시적 docs 선택의 1년/Path=/SameSite=Lax 쿠키와 data preload의 선호 미변경을 검증했다. JS 없는 docs 선택은 article·reader query와 다음 로그인 언어를 유지했다. Fragment는 서버에 전달되지 않아 no-JS 링크에서는 소실되며 hydrated 동선의 보존과 구분한다. End/Enter의 마지막 Bengali 선택과 trigger focus 복귀를 확인했다. |

실제 UI·HTTP·Node runtime의 증거이며 console은 내장 tutorial의 **합성 identity/data**다. 나머지 API는 외부 호출을 막고 unavailable 응답을 사용했다. 실제 Keystone 로그인, backend 데이터·provider, 원어민 번역 승인 또는 운영 배포의 수용 증거가 아니다. 번역은 기존 draft 상태를 유지한다. API·인가·schema·dependency·배포 topology 변경은 없으며 이번 승인 범위는 dev 통합·push이고 main merge·버전/tag·운영 배포는 포함하지 않는다.

초기 잘못된 root cwd의 Vitest 실행은 frontend alias/Svelte 설정을 읽지 못했으므로 제외했다. 최초 전체 gate는 새 clone의 pytest 미설치에서 중단되어 frozen `dev` extra를 설치했다. 초기 browser matrix는 tutorial session이 로그인 redirect를 유발할 수 있어 제외하고, 조건마다 소유 storage/cookie를 초기화하고 실제 pathname을 검사하는 위 216조건으로 대체했다. No-JS fragment 보존을 요구한 throwaway assertion은 실패했으며 위의 정확한 관측 경계로 정정했다. 소스 결함을 숨기거나 이 실패들을 성공으로 집계하지 않는다.

정제된 JSON·실제 PNG: `~/.local/share/afterglow-proofs/i18n-dev-merge-20261019/`의 `compiled-responsive.json`, `language-persistence.json`, `ssr.json`, `native-keyboard.json`. 선택적 gbrain CLI는 PATH에 없어 indexing/시작 지침 변경을 하지 않았다.

### CI frontend runtime 설치 후속 수정

병합 커밋 `cd3062158575034e24774d0b126bd1f1faedcd19`의 [Actions 39252951448](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/39252951448)는 모든 테스트 lane과 Bun frontend compile을 통과했지만 Node20-Alpine runtime의 lock 없는 `npm install --omit=dev --ignore-scripts`에서 npm10.8.2 Arborist `Cannot read properties of null (reading 'edgesOut')`로 실패했다. 이 실패를 번역·compile 실패나 성공한 이미지 발행으로 보고하지 않는다.

최소 수정은 기존 `package-lock.json`을 runtime에 함께 복사하고 `npm ci --omit=dev --ignore-scripts`를 사용하는 것이다. 두 root version metadata만 현재 manifest의1.30.19로 맞췄고 JSON 대조로 의존성 graph 불변을 확인했다. Bun lock/build·Node20 base·nonroot user·entrypoint·API·인가·schema·배포 topology는 유지한다.

- 실제 canonical `Dockerfile --target frontend`의 `linux/amd64`·`linux/arm64` 빌드가 모두 성공했다. 변경된 runtime 설치 단계가 각각241packages를 설치했으며 fake/no-op/cache-only 성공이 아니다.
- 두 최종 이미지를 소유 loopback container로 실행해 Node20.20.2의 실제 `x64`/`arm64`, nonroot UID1001, 설치된 `smol-toml`의 TOML parse와 Bengali `১,২৩৪.৫` 서식을 확인했다. 각 이미지에서9locales×로그인/docs/Manila의27HTTP응답, 총54개에서200과 초기 HTML lang을 확인했다. 기존 서비스·DB·볼륨·설정은 연결하거나 교체하지 않았다.
- 수정 source digest `1c7ff2f7792c112130d539cda0e016c0939f971ee2ff4b4efcad48de79b46180`/3,104files에서 전체 `test:gate`가 다시 exit0이었다. Source-only216조건 browser proof와 이번 실제 image/HTTP proof는 구분한다. 운영 배포·실제 인증/provider·원어민 검수는 여전히 미실행이다.
- 근거: 같은 외부 proof directory의 `frontend-amd64-build.log`, `frontend-arm64-build.log`, `frozen-install-gate.log`, `runtime-image-smoke.json`. 기존 lock의 npm audit 결과2low/1moderate는 보존했고 광역 dependency update나 audit-fix는 하지 않았다.



## 벵골어 추가 검증 (2026-10-16; local-only)

`add-bn-locale`는 별도 `/Users/pieroot/code/afterglow-i18n`의 `i18n`에서 기존 여덟 언어 구현에 벵골어(방글라데시)를 추가했다. 시작·최종 fetch의 `origin/dev`는 모두 `08e272422cd855b30d39929c24993047ec0cd6ad`이고 최종 merge는 `Already up to date`, ancestry check는 exit0이었다. Locale `bn`, 원어 메뉴 `বাংলা`, Intl `bn-BD`이며 기존 공용 쿠키·SSR·namespace ICU·typed guide·검색·CSV 경로를 재사용한다.

40개 UI namespace의10,022문구,15개 가이드의5개 dictionary·1,152항목과118개 용어를 제공한다. `i18n:report -- --locale bn`은10,022draft·0reviewed·0outdated·0missing이었다. 모든 번역은 기계 작성 초안이며 자동 구조·의미 대조는 원어민 검수 승인이 아니다.

| 검증 경계 | 실제 관측 |
|---|---|
| 번역·source guard | `i18n:check`0errors/0warnings·40namespaces/10,022source messages; `i18n:scan`1,103files/hard-coded Korean0. Guide dictionary1,152항목의 source key 순서·누락·빈 값·한글 잔존0. |
| Frontend 회귀 | exact docs search1file/29tests → 관련8files/189tests → 전체370Vitest files/3,704tests와 Node file-log runner9tests 통과. 포함된 selector를 별도 합산하지 않는다. |
| Compiler·build | Node24.14.1에서 `npm run check`0errors/기존3warnings(`DocCodeBlock`, `WizardStep5Config`, `ProjectUsageTable`), production build·adapter-node 완료. 실제 `node build`를 loopback4188에서 실행했다. |
| 실제 사용자 동선 | Bengali 로그인 선택→언어 없는 docs→`Cinder স্ন্যাপশট` 검색·가이드→합성 로그인→콘솔 reload→docs 복귀·콘솔 복귀→실제 logout confirmation에서 `html.lang`/공용 쿠키 유지. Hydrated Manila 언어 왕복은 path/query/fragment를 보존했다. |
| Compiled 반응형 | 9locales·2themes·landing/login/docs/console의248조건: 기존8언어는320/768/1024px, Bengali는320/390/767/768/1023/1024/1440px. 가로 document overflow0,9언어 항목·최소44px·viewport-bounded menu. 콘솔 geometry는 disposable synthetic session을 주입했으며 실제 fixture 로그인은 별도 동선으로 검증했다. |
| Native·keyboard | JavaScript를 끈 실제 docs 언어 링크가 Bengali 쿠키와 reader query를 갱신하고 다음 login SSR도 Bengali였다.320×450px에서 End/Enter로 마지막 বাংলা 선택·세로 스크롤 접근, Escape refocus·outside dismissal을 확인했다. |
| HTTP·Intl | 15guides×9locales를 포함한180개 SSR 응답에서 HTML lang·정상200/문서404 확인. 명시적 `lang=bn`은1년 Max-Age·Path=/·SameSite=Lax 쿠키를 설정했다. 실제 Node/Chromium의 `bn-BD` 숫자·날짜는 벵골 문자로 표시됐다. |
| Architecture·index | Working stamp와 temporary-index staged guard 모두 `8ba5b3fcb181cc5a201f6775b8c0c324065e641c24cbaf82b7d0c03a7ee09f50`/3,104source files로 통과. 실제 index 전후 SHA-256 동일, temporary index 제거. |

Browser는 실제 Chromium150의 compiled UI이며 로그인/me/logout만 합성 응답이다. Backend 데이터는 의도적으로503/unavailable이므로 실제 데이터·차트·Keystone/provider·운영 인증 수용이나 console-error-free를 주장하지 않는다. 관측한 최종 bounded error 기록에는 pageerror가 없지만 network 실패가 존재한다. 초기 단일 대형 matrix run은 timeout으로 결과가 반환되지 않고 persistent fixture routes도 소실되어 후속 identity 읽기가 실패했다. 이 실행을 통과로 세지 않고 fixture를 복구해 locale별 bounded run과 매 조건별 JSON receipt로 최종248조건을 완료했다. Bun의 Intl 숫자는 Latin 자릿수를 기본으로 써 초기 throwaway assertion이 실패했으나 실제 서비스 Node와 Chromium은 `bn-BD` Bengali 자릿수·월명으로 확인했다. 지역 서식 결과를 특정 엔진 전체의 동일 bytes로 강제하지 않는다.

전체 `npm run test:gate`·실제 backend/provider·운영 배포는 수행하지 않았다. 커밋·push·실제 index staging 없이 현지화 worktree의 기존 변경을 보존했다. 소유 frontend service·Chromium·scratch profile을 정리했고 proof만 유지한다. 선택적인 gbrain sync는 CLI가 `ENOENT`여서 실행하지 않았으며 시작 지침 파일을 바꾸지 않았다.

증거: `~/.local/share/afterglow-proofs/add-bn-locale-20261016/`의 `browser-verification.json`, `compiled-responsive-final.json`, `intl-smoke.json`, `guide-data-integrity.json`, `architecture-guard.json`, test/check/build 로그와 실제 PNG. OpenSpec 검증 기록은 [archived verification](../openspec/changes/archive/2026-10-16-add-bn-locale/verification.json)에 보존한다.


## 스와힐리어·노르웨이어·말레이어·베트남어 추가 검증 (2026-10-16; local-only)

`add-sw-nb-ms-vi-locales`는 별도 `/Users/pieroot/code/afterglow-i18n`의 `i18n`에서 진행했다. 시작·최종 fetch의 최신 dev는 모두 `08e272422cd855b30d39929c24993047ec0cd6ad`이며 최종 merge는 `Already up to date`, ancestry check는 exit0이었다. 추가 언어는 탄자니아용 Kiswahili `sw`/`sw-TZ`, Norsk bokmål `nb`/`nb-NO`, 말레이시아용 Bahasa Melayu `ms`/`ms-MY`, Tiếng Việt `vi`/`vi-VN`이다. 기존 네 언어와 같은 namespace·ICU·typed guide·CSV 경로를 사용한다.

새 언어마다40 UI namespace의10,022문구와15개 가이드에 필요한5개 dictionary·1,152항목을 제공한다. `i18n:report -- --locale sw,nb,ms,vi`는 각10,022 draft·0reviewed·0outdated·0missing이었다. 이는 기계 작성 초안이며 원어민 의미·용어·문체 검수가 완료됐다는 뜻이 아니다.

| 검증 경계 | 실제 관측 |
|---|---|
| 번역·source guard | `i18n:check`0errors/0warnings·40namespaces/10,022source messages, `i18n:scan`1,097files/hard-coded Korean0. |
| Frontend 회귀 | 관련8files/164tests, 전체370Vitest files/3,679tests와 Node file-log runner9tests 통과. 관련 회귀는 전체 suite와 중복 집계하지 않는다. |
| Compiler·build | Node24.14.1에서 최종 `npm run check` exit0·0errors/기존3warnings(`DocCodeBlock`, `WizardStep5Config`, `ProjectUsageTable`). Vite8.2.2 production build와 adapter-node 완료(`artifact://222`), 실제 `node build`를 loopback4187에서 실행했다. |
| 실제 사용자 동선 | 새 네 언어의 로그인 선택→언어 없는 docs→본문 검색·Cinder 가이드→합성 로그인→콘솔 reload→docs 복귀·logout에서 `html.lang`/공용 쿠키 유지. Native no-JS docs 선택4건,8항목 End/ArrowUp/Enter·Escape refocus·밖 클릭,320×450px의 마지막 항목 스크롤 접근 확인. |
| Source 반응형 | 새4locales×2themes×320/390/767/768/1023/1024/1440px×landing/login/docs/console의224조건. Document 가로 overflow0,8항목·44px 최소 행 높이와 viewport-bounded menu 확인. |
| Compiled 반응형 | 전체8locales×2themes×320/768/1024px×같은4surfaces의192조건. 가로 overflow0, 메뉴 경계·8항목·44px 행 높이와 관측한 unhandled runtime event0. Identity는 합성이며 정상 backend data/실서비스 chart rendering 검증으로 확대하지 않는다. |
| 실제 SSR·공유 URL | Source56개 응답, compiled160개 응답에서 cookie locale과 초기 HTML language·정상200/문서404를 확인했다. Compiled에는15guides×8locales가 포함된다. 명시적 docs 선택의1년/Path=/SameSite=Lax 응답과 no-JS 쿠키 갱신, hydrated Manila 문서의 path/query/fragment 유지·한국어 명시 선택→콘솔 복귀를 확인했다. |
| Architecture·index | Working stamp와 격리 temporary-index staged guard가 같은 `f20bc41cf8e1208a35a184b3e838da48e9528b87573785be4ee117b5b00a4d06`/3,057source files로 통과했다. 실제 worktree index의 전후 SHA-256이 같고 temporary index를 제거했다. |

초기 isolated `node_modules`가 frozen npm lock과 달라 React import suite2개와 missing-module type diagnostics가 실패했다. 소유 dev server를 중지한 뒤 `npm ci --no-audit --no-fund`로437packages를 설치하여 최종 suite/check를 통과했다. `package.json`·`package-lock.json`·`bun.lock` SHA는 전후 같았다. 실패 로그도 보존하며 dependency source/manifest를 고쳐 숨긴 결과가 아니다.

브라우저는 실제 Chromium150의 source/compiled UI이며 identity/login/me/logout은 합성 응답이다. 나머지 API data는 의도적으로 unavailable이므로 network/CORS 실패와 번역된 오류 상태가 존재한다. Console-error-free·실제 Keystone/provider·운영 로그인/배포·전체 `npm run test:gate` 통과를 주장하지 않는다. 커밋·push·배포는 하지 않았다. 선택은 공용 `afterglow_locale` 쿠키이며 계정 설정·인가·schema·운영 상태를 변경하지 않는다.

초기 번역 worker의 잘못된 shared-root 사본과 당시 snapshot/hash 확인·외부 tar backup·정리 내역은 `shared-copy-reconciliation.json`에 별도 기록했다. 최종 검증 중에는 shared checkout을 추가 정리하지 않았다. 이 기록을 모든 동시 변경이나 관측하지 못한 과거 내용의 보존 보장으로 확대하지 않는다. 선택적인 gbrain sync는 CLI가 `ENOENT`여서 수행하지 않았고 agent 시작 파일을 바꾸지 않았다.

상세 정제 기록은 [archived verification](../openspec/changes/archive/2026-10-15-add-sw-nb-ms-vi-locales/verification.json), 외부 증거는 `~/.local/share/afterglow-proofs/add-sw-nb-ms-vi-20261016/`의 `browser-verification.json`, `architecture-guard.json`, `frontend-tests-final.log`, `frontend-check-final.log`, 초기 실패/설치 로그와 실제 screenshots다.


## 국가·요청 origin·radial mesh 관측 검증 (2026-10-15; local/disposable·production 분리)

`observe-country-request-origin-and-network-mesh`의 qualification은 **source/unit, 실제 native BPF/socket·Redis·MMDB, built-image adapter/API runtime, 합성 API Chromium**으로 나뉜다. 최초 격리 기준은 `cbd75d6d506e3609c07202183181004f950a4c51`이며 최신 `origin/dev` `a7830307`의 별도 OAuth/chat 수정까지 보존해 통합했다. 아래 최초 gate/image/browser 결과는 통합 전 bytes의 증거이고 통합 후 결과와 구분한다. 과거 배포1.30.x 또는 이전 collector 활성화를 이 변경의 운영 수용으로 승격하지 않는다.

### Source/unit·renderer 경계

Typed config/secret 분리·factory original-peer 보존·origin/legacy bucket·flow uint64/reset/freshness·physical qualification과 renderer consumer 회귀를 작성하고 선택 lane을 실행했다. 초기 선택 회귀의 **실패2건**은 short secret literal이 Pydantic `too_short`에 걸린 test fixture와 corrupt-state diagnostic의 잘못된 exact expectation이었다. 실제 secret leak 또는 재현된 exploit으로 기록하지 않는다. Renderer 초기4실패는 required app/Helm secret을 빠뜨린 fixture와 obsolete whole-template source assertion이었다. Brittle 구현 문자열 검사를 제거하고 실제 렌더된 ephemeral log volume과 optional read-only country PVC를 각각 확인한 repaired3 selectors가 통과했다. Graph27회귀는 physical false/null/missing/wrong-device가 cable rate로 승격되지 않는 user-visible 경계를 포함한다. 이 선택 결과를 전체 backend/frontend/contract/functional gate 성공으로 합산하지 않는다.

Observer ancestry/single-link/exact0640, installer의 root import 이전 source validation, MAC/ifindex fencing, SNMP wrap 뒤 discontinuity 보존은 **static review에서 발견해 보강한 경계**다. 재현된 운영 공격·failed-before exploit으로 쓰지 않는다. Fabric/SNMP의 deterministic unit transport/MIB/Redis fence 검증은 실제 인증된 물리 switch/port counters의 수용 증거가 아니다.

추가 static review의 **unresolved/logical switch endpoint cable attribution**과 **sysUpTime wrap/closing boot continuity**는 별도 failed-before로 재현했다. 양쪽 switch endpoint 회귀2건은 미해결 끝에도2방향 rate를 붙여 실패했고 수정 후 graph30회귀가 통과했다. Unit/실제 loopback SNMPv3 authPriv UDP의 정상 wrap2건은 reset으로 거부돼 실패했지만 ordinary reboot 거부는 이미 통과했다. Closing uptime 누락/잘못된 type·engine boots 누락·quick reboot4건은 모두 잘못된 baseline을 반환하여 실패했다. Typed opening/closing GET·같은 engine boots·monotonic 및 modulo32-bit elapsed bound를 적용한 뒤 fabric45회귀가 통과했다. Current-source Chromium의 unresolved trunk는 LLDP 선1개/rate unknown/arrow 없음이었다(`integrated-browser/physical-trunk-after.json`). 이 결과는 실제 물리 switch credential/view·port 수용이 아니다.

통합 전 전체 `npm run test:gate`는 exit0이었다. Working-source digest `3ebb6c28af72996bce8060c73ff4ba0a10a85144f7f65b8e27cc49270a8106a9`/2,869files이며 commit SHA가 아니다. 원문 `artifact://406`/`artifact://417`.

| 통합 전 gate lane | 관측된 결과 |
|---|---|
| Architecture freshness | passed |
| JS orchestration / Kolla contract | 175 / 27 passed |
| CLI install | 20 passed / 36 skipped (PowerShell unavailable) |
| Backend unit | 6,772 passed / 95 skipped |
| Frontend unit / file-log runner | 370files / 3,628tests passed; runner9passed |
| Consumer contract | 174 passed |
| Disposable MariaDB/PostgreSQL/Redis functional | 154 passed / 27 deselected |
| Ruff | check passed;639files formatted |

초기 full gate의 proxy12실패는 새 launcher가 `--no-proxy-headers`인데 fixture가 여전히 `app.main:app`를 직접 구성해 factory를 누락한 것이었다. 실제 rendered app/factory/env로 fixture를 이관해 기존 HTTPS redirect·직접 HTTP·untrusted spoof와 IP-binding 재인증을 검증했고 해당20건과 위 전체 gate가 통과했다. 인증/rate-limit 정책을 완화하지 않았다. Typed origin fixture의 null 계약 및 scoped definition-list 검사를 이관했다. Svelte/i18n 검사는0errors/기존3warnings,40namespaces/10,022messages,1,073files에서 hard-coded Korean0이었다.

최신 `origin/dev` `a7830307` 통합 및 dense graph 회귀 추가 후 `npm run test:gate`도 exit0이었다. Working-source digest `1f015c579d86a859f43f8d187f8945931bdd9933816c5a358ce694b670dbe0da`/2,869files,backend **6,774passed/95skipped**,frontend **370files/3,629tests**,contract **174passed**,실제 disposable functional **157passed/29deselected**,Ruff check/format **639files**가 통과했다(`artifact://443`/`artifact://455`). 선택 frontend38회귀·Svelte0errors/기존3warnings·i18n0errors/0warnings 및 hard-coded Korean0도 통과했다. 이 gate는 물리 switch/운영 수용을 증명하지 않는다.

Final continuity fixes 뒤 frozen source `808f18a1802cdbe5d43940eadae2c39cf5eb89f1566a814e5068135f3d00dd03`/2,869files의 `npm run test:gate`는 isolated Docker engine의 canonical functional datastores를 사용해 exit0이었다. Backend **6,781passed/95skipped**,frontend **370files/3,631tests**,contract **174passed**,functional **157passed/29deselected**,Ruff check/format **639files**가 통과했다(`artifact://533`/`artifact://535`). 이는 source·DB contract qualification이며 runtime images와 실제 운영/물리 switch acceptance는 별도다.

### 실제 native runtime: BPF/socket·Redis·MMDB

| 경계 | 보존된 실제 결과와 제한 |
|---|---|
| Linux BPF 실행 | Disposable aarch64 VM/kernel6.8.0-134의 BCC `BPF_PROG_TEST_RUN`에서 collector56passed/21warnings. IPv4/IPv6/VLAN·nonlocal exclusion·uint64/map capacity/invalid-L3 경계를 실제 filter로 exercise했다. Final receipt는 unchanged collector/filter/security/test4파일 hash를 명시해 이 결과를 보존한다. Warning은 배포판 BCC bytes deprecation이며 전체 Python suite 수치가 아니다. |
| 실제 AF_PACKET socket | Guest virtio `eth0`와 등록 local gateway fixture의 egress137→194packets, ingress140→198packets 및 byte 증가를 관측했다. Quiet period의 delta0, collector restart의 새 identity, stop 뒤 stale rejection을 확인했다. Header-only return-zero filter이며 guest NIC의 **Linux skb** 계수다. DMS physical NIC/wire/switch, offload 정확성 또는 full mesh를 검증한 것이 아니다. |
| 최소권한 handoff | Collector CapEff/CapBnd/CapAmb `0000008000002000`(CAP_BPF+CAP_NET_RAW), NoNewPrivs1/Seccomp2. Nonroot observer가2rows를 읽었고 CapEff0/NoNewPrivs1/Seccomp2를 유지했다. Installer unprotected source 및 writable destination 거부도 확인했다. |
| 실제 complete MMDB | 공식 DB-IP2026-10 압축 해제 database8,348,509bytes, SHA-256 `dbd70ccfa2a13627eaf4913d19920a1a229f1b3c5439ac01c509995b6364202a`; provider MD5/SHA1 일치와 metadata DBIP-Country-Lite/ip_version6/build version2026-10-01을 확인했다. Native lookup은 IPv4 US·IPv6 CA·service endpoint KR, private→XX/non_global·missing→XX/address_unavailable였다. 실제 운영 client 국가 정확성이나 모든 address의 ground truth 검증은 아니다. |
| Factory/API·실제 TCP Redis | 실제 Uvicorn TCP/factory/API·Redis Lua/HLL·complete MMDB로 external3/internal2/unknown4와 legacy-unclassified2를 분리했다. 기존 auth client rewrite 유지·analytics trust 독립, raw-IP durable 저장 없음, dedupe/TTL, writer401·ordinary admin403을 확인했다. `app.main` binding·admin identity·SvelteKit adapter event는 합성으로 실제 Keystone/main lifespan/배포 인증을 주장하지 않는다. |
| Reporter 실제 HTTP | Raw escaped oversized body는 실제 HTTP413이었다. Reporter의 invalid-evidence sentinel 적용 뒤 실제 HTTP200,299-byte wire payload를 확인했다. Listener/cleanup harness 수정까지 포함한 최종 command exit0(8.88s)/receipt passed:true다. Synthetic adapter peer이며 native SvelteKit deployment/production provenance 수용을 뜻하지 않는다. |
| SNMP 실제 UDP·Redis runtime | Current source/pysnmp7.1.22/cryptography50.0.0에서 loopback authPriv UDP→실제 isolated TCP Redis Lua fence→fabric snapshot을 실행했다. 실제6.230250초 interval에서 sysUpTime4294966996→324 wrap 및 packet delta300/byte delta100의 정확한 rate를 확인했다. Closing uptime 누락/잘못된 type·boots 누락은 `snmp_invalid_response`,quick reboot는 `snmp_stale_sample`이며 key·username은 durable state에 없었다. Native MIB/identity는 합성이며 실제 switch/view/physical-port 수용은 아니다. 원문 `native-fabric-final.json`. |

**Failed-before와 수정 원인:** 첫 native BPF/filter 회귀는 통과했지만 systemd collector는 `no_fresh_snapshot`으로 실패했다. `ProtectKernelModules=yes`가 `/lib/modules/<kernel>/build` symlink 접근을 가려 BCC가 `chdir(...): Permission denied`, missing kheaders/module 메시지를 냈다. Unit에 `BCC_KERNEL_SOURCE=/usr/src/linux-headers-%v`를 명시해 이미 provision한 matching distro headers를 사용한 뒤 위 실제 socket/handoff 결과를 얻었다. Module protection·MemoryDenyWriteExecute·capability/seccomp 경계를 낮추지 않았다. Before의 overall passed:false와 after passed:true를 함께 보존하며 이것은 별도 Ubuntu storage Python executable-stack repair의 역사적 receipt와 혼동하지 않는다.

Durable native receipts: `~/.local/share/afterglow-proofs/network-observation-20261015/native-collector-before.json`, `native-collector.json`, `native-http.json`. Provider/native lookup 원본은 parent의 `country-mmdb-provider-receipt.json`과 `country-mmdb-native-qualification.json`이다. Source pin·실제 데이터·합성 identity 경계를 분리해 읽는다.

### Built-image runtime (통합 전 source)

Canonical root `Dockerfile`의 backend/frontend/worker/native-vm을 **linux/amd64+linux/arm64**, declared native-cloud-vm은 **linux/amd64**로 실제 build했다. OpenTofu1.8.3의 linux_arm64/linux_amd64와 Ceph18.2.7,Python3.12.15/pysnmp7.1.22·factory 및 worker crypto0.1.1,frontend Node20.20.2/x64·arm64를 built images 안에서 실행했다. `*-build.json`은 durable proof root에 보존한다.

Canonical `docker-compose.dev.yml`와 task-owned port/image/tmpfs overlay의 `afterglow-observation-runtime-20261015`에서 backend/frontend·Redis·MariaDB health와 running Notion worker를 확인했다. 최초 기동은 throwaway TOML에 존재하지 않는 fabric `enabled`를 넣어 strict config가 거부했고 그 fixture key만 제거했다. 실제 adapter-node→factory/API→Redis Lua/HLL에서 login/health200·response-byte observations·external0/legacy0와 private/noncluster unknown,위조 XFF 원문 nondurability 및 empty fabric generation registration을 확인했다. 실제 mounted full MMDB SHA와 US/CA/KR도 일치했다. 개발 IAM 값은 synthetic loopback이며 Keystone 로그인/권한 또는 switch SNMP 수용이 아니다. 원문 `container-pipeline.json`.

`native-vm` canonical nonroot OCI entrypoint는 network-none/tmpfs에서 **arm64/amd64** 모두 MariaDB/Redis/schema·API/frontend ready,UID1000·complete MMDB lookup과 exit0 graceful shutdown을 확인했다. `native-cloud-vm` image build는 성공했으나 별도 OCI lifecycle command는 Docker stop timeout으로 전체 성공이 아니었다. Nova/KVM guest boot는 어느 결과도 주장하지 않는다. 동시에 Docker inspect/stats·HTTP timeout과 Docker VM OOM events를 관측했고 공유 engine restart/prune·다른 프로젝트 변경은 하지 않았다; 당시 task Compose containers는 OOM=false/restart0이었다. 원문 `native-entrypoint.json`과 retained failed command output.

최종 source의 desktop backend/frontend/worker amd64+arm64 build는 성공했지만 이어지는 native target은 BuildKit `no active session`으로 중단됐고 Compose recreate는360초 timeout이었다. 호스트 Redis port와 container API도 timeout이어서 그 결과를 ready로 쓰지 않았다. Shared engine39running containers는 restart/prune하지 않고 별도 task-owned Lima/Docker29.1.3/API1.52·containerd/6CPU/8GiB로 격리했다. Initial SSH 세션의 stale docker-group membership은 해당 VM 연결만 갱신하고 root:docker0660 socket을 유지한 채 private Unix tunnel로 해결했다. Ubuntu QEMU8.2.2의 amd64 `sqv` SIGSEGV가 APT signature failure로 드러났으며 **task VM의 qemu-x86_64만** Docker 권고 pinned binfmt image `sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0`로 교체한 뒤 sqv1.3.0 실행을 확인했다. Signature verification을 끄지 않았다. Root runbook/architecture/source를 바꾸는 문제 회피가 아니라 QA runtime repair이며 `runtime-environment.json`에 성공/실패 경계를 보존했다. 최종 isolated build/ready/image-runtime 결과는 별도 receipt를 따른다.

해당 QEMU 교체 뒤 APT/sqv는 정상이었지만 OpenTofu1.8.3의 Go `lfstack.push` pointer packing은 실패했다. Task VM만 기존 host Rosetta로 재부팅했고 docker-container BuildKit0.33.1은 amd64 chroot probe에서 `/proc/self/exe` 경계를 만나 여전히 내부 QEMU를 선택했다([upstream7110](https://github.com/moby/buildkit/issues/7110),[7052](https://github.com/moby/buildkit/issues/7052)). 동일 owned engine의 canonical Docker driver/BuildKit0.26.2로 unchanged `tofu-installer`를 build하여 pinned amd64 checksum과 build·container runtime의 **OpenTofu1.8.3/linux_amd64**를 exit0으로 검증했다(`artifact://551`). Project Dockerfile·APT trust·버전 검사는 우회하지 않았다. 전체 target의 final image/runtime 결과는 별도 receipt로 판단한다.

### 최종 source built-image runtime (task-owned isolated VM)

Frozen source `808f18a1…`의 canonical Dockerfile target을 owned Docker driver로 모두 build했다. backend/frontend/worker/native-vm/cloud-shell은 **linux/amd64+linux/arm64**, native-cloud-vm은 **linux/amd64**이며 808.70초가 걸렸다(`final-image-builds.json`, `artifact://552`). Built image 안에서 두 architecture 모두 Python3.12.15/pysnmp7.1.22/factory, OpenTofu1.8.3 `linux_arm64`/`linux_amd64`, Ceph18.2.7, Node20.20.2 arm64/x64와 worker/cloud-shell module을 실행했다(`final-image-runtime.json`).

Canonical `docker-compose.dev.yml` project의 첫 backend 기동은 `IsADirectoryError`로 실패했다. VM 재부팅 뒤 nonsecret QA fixture가 없어 short bind가 빈 디렉터리를 만든 것이다. 정확한 config/MMDB fixture를 SHA로 복원했고 QA overlay는 `create_host_path=false` read-only bind로 바꿨다(`mount-fixture-repair.json`). 그 뒤 Redis/MariaDB/backend/frontend는 healthy, worker는 running이었다. 실제 adapter-node→factory/API→Redis에서 backend internal4, frontend internal3/unknown2, external0/legacy0을 확인했다. MMDB `2026-10-01` SHA와 US/CA/KR, 위조 XFF 원문 비저장과 fabric generation registration도 일치했다(`container-pipeline-final.json`).

`native-vm` arm64/amd64는 network-none에서 supervisor ready, UID1000, `offline_mmdb`, exit0 graceful shutdown이었다. `native-cloud-vm`도 supervisor/API/frontend health와 UID1000은 통과했다. 다만 root:root0700 `/etc/afterglow` 아래 mount한 MMDB는 appuser가 읽지 못해 `database_unavailable`이었다. Root-owned read-only `/usr/local/share/afterglow/geoip/country.mmdb`와 env 경로로는 `offline_mmdb`/US·CA·KR과 exit0을 확인했다(`native-final-entrypoint.json`). 이 경계는 deployment 문서에 기록했으며 Nova/KVM guest boot는 주장하지 않는다.

Host `127.0.0.1:58642`로 실행한 첫 browser pass는 무효다. 그 listener는 Docker Desktop의 이전 frontend였고 API 요청이 `58641`로 갔다. 그 image는 unresolved trunk를 rx/tx measured edge로 표시했다. 결과는 폐기했다(`final-compiled-browser-invalidated.json`). `limactl` forward `58742`의 final frontend `sha256:08007d29…`(API `58741`)에서 **96/96조건·50/50조작**, 38node Fit overlap0·navigator38/44px·overflow0을 확인했다. Unresolved LAG/trunk endpoint는 rate unknown·marker 없는 단일 LLDP edge였다. Application exception은0이고 차단한 fonts와 unmatched GitLab fixture 등 request failure103건이 있다(`final-compiled-browser/summary.json`). Dense 합성 overview에서는 edge/port가 core label 위를 지나간다. Identity/API는 합성이며 인증·provider·switch·운영 수용이 아니다.

### Synthetic Chromium 경계

실제 current-source Vite/Chromium input/rendering에서 topology/traffic의 **96/96 route×locale×theme×width 조건,50/50 interaction**을 확인했다. Directional zero/reset/stale/error·physical-port qualification·pps/B/s·node/edge/list selection·stable refresh·keyboard/mouse·native touch pan/pinch·mobile inspector와30source/range/origin 조합을 포함한다. Overflow/uncontained control/reduced-motion running animation/page error는0이었다. `physical=true`·matching device가 없는 join을 unmeasured LLDP edge로 유지하도록 수정했고 inspector grid/wrapping과 mobile min-content width oscillation/fit을 수정했다.

Identity·모든 API/inventory/switch/flow/MMDB analytics payload는 **합성**이다. Real authentication/provider/production proof가 아니며 source와 built-container UI는 아래에서 구분한다. 이전 **잘못된 checkout의 legacy browser evidence는 명시적으로 무효화**했다. 이 최초 source 화면의 high-density Fit에는 fixed-size node targets가 겹쳤으나 zoom·complete evidence-list selection은 가능했다; 이후 camera-scaled glyph/cluster spacing 수정과 현재 overlap0 증거를 아래에 분리했다. Reused profile의 native-touch flakiness와 fresh-profile 최종 pan/pinch transform 성공을 구분한다. Durable proof: `~/.local/share/afterglow-proofs/topology-traffic-assigned-20261015T1500/`의 summary/matrix/interactions·screenshots·before/after defects·재사용 scripts.

Built adapter-node frontend에서도 동일 synthetic96조건/50조작이 통과했다. `compiled-browser/summary.json`의 application exceptions는0이나 network errors는0이 아니다: 의도적으로 차단한 외부 fonts 및 unmatched login GitLab-enabled fixture 요청이 기록됐다. Actual adapter reporting/Redis proof는 위 runtime 절과 별개다. 이후 screenshot에서 확인한 dense overview의 fixed44px box overlap은 camera-scaled glyph 및 controller core/host sector 밖의 switch-port cluster spacing으로 수정했으며 integrated source/image의 후속 화면 증거와 구분한다.

통합 후 current-source Vite/Chromium에서도 **96/96조건·50/50조작**이 통과했다.18hosts+2switches+18ports/38node의 Fit에서 node target pair overlap0,동등 navigator38개/min-height44px,document overflow0이었다. Overview glyph camera scale과 core 밖 port-cluster spacing의 screenshot·geometry를 `integrated-browser/dense-fit.json`·`dense-fit-after.png` 및 summary/matrix/interactions에 보존한다. 합성 API/native input이고 built-image 또는 physical switch acceptance가 아니다. Network error는0이 아니며 block한 external fonts 및 unmatched login/dashboard fixture가 실패한 기록을 application exception0과 구분한다.

### 위 local/disposable 검증이 증명하지 않는 경계

이 절의 근거는 **physical-switch SNMPv3/실제 port mapping, Nova/KVM guest boot, 운영 mixed-version/backup-restore/production rollout 수용**을 포함하지 않는다. 실제 운영은 authorized management endpoint 또는 jump 경로·read-only SNMPv3 authPriv view와 operator0600 credential-file 위치가 먼저 필요하다. LLDP 광고 `192.168.0.2/.3`의 HTTP/HTTPS timeout과 representative kernel/BTF preflight는 switch counter 수용이나 all-node collector qualification이 아니다. NIC totals/guest skb/TCP reachability/합성 ports로 physical-switch gap을 대신 채우지 않는다. 기존 deployed1.30.x 수치/장애/partial coverage는 아래 역사적 기록을 그대로 따른다.

후속 read-only operator preflight는 native `/etc/kolla/multinode` parse exit0과 Afterglow/control 대상3controllers, 기존 보호 backend/global/secret 파일·18observer 및 기존 HMAC/writer key 존재를 확인했다. 기존 operator inputs에는 fabric/SNMP credential 변수가 없었다(`operator-readonly-preflight.json`). 정확한 등록18hosts의 kernel/NIC/package/security metadata도 읽었으며 matching header directory18/18,Ubuntu BCC0.29.1가 compute/controller15대에 존재하고 storage3대에는 `python3-bpfcc`가 없었다. Standalone `clang`/`llvm` package는18대 모두 없었다. 실행 중 observer18대는 nonroot·CapEff/CapBnd/CapAmb0·NoNewPrivs1·Seccomp2였다(`all-hosts-readonly-preflight.json`). 이는 **metadata preflight**이며 BPF compile/load/capture·collector 배포·switch 접근·운영 acceptance 성공은 아니다.

### 운영 반영 1.30.18 (2026-10-15, DMS Lab Kolla)

**범위:** 사용자가 승인한 Afterglow·관측 수집기만 바꿨다. Lumen/Drover/Waygate/Palimpsest와 stock 서비스, inventory, network는 변경하지 않았다. `v1.30.18`(`365cad3a`)은 exact-SHA dev CI와 tag publish를 모두 통과했다. `latest`는 api `d28335ce…`, frontend `1226faa5…`, worker `e890f04b…`, cloud-shell `9a43256b…`과 일치했다.

- **복구 지점:** operator overrides와 controller별 generated config를 암호화해 보존했다. SQL dump는 isolated restore에서 93 tables/2,628 rows로 검증했다. Redis capture 221 keys는 isolated restore에서 217 keys를 복원했다(만료 4개 제외). 첫 Redis restore qualification은 TTL 만료와 DBSIZE 비교가 겹쳐 실패했다. 같은 capture를 값 없이 다시 재생했을 때 178/178 keys가 일치했고, 새 capture로 다시 검증했다.
- **설정:** obsolete `geoip_csv`를 제거했다. 사용자가 고른 대로 `cluster_cidrs`는 노드 주소·VIP·loopback 31개다. 분석용 proxy trust는 기존 `FORWARDED_ALLOW_IPS`와 같은 5개다. Observer `addresses`는 27개다. Globals에는 이미지 4개 key와 MMDB source/SHA pin을 추가했다. Controller마다 genconfig→target image로 rendered config 검증(`get_settings`, MMDB `offline_mmdb` 2026-10-01)→prechecks→reconfigure→verify를 진행했다. 3대 모두 healthy·restart0이었고 비대상 container(242/237/150)는 변하지 않았다. Backend launcher는 original-peer factory였다.
- **트래픽:** DB-IP `2026-10-01`과 CC BY 4.0 attribution이 표시된다. 반영 직후 실제 외부 요청은 국가별로 분류됐다(KR/AU/US/SG 등). 미확인은 세 경우에서 나온다. ① LB·컨테이너 health check가 XFF 없이 trusted proxy에서 온 경우(`forwarded_missing`). ② controller가 직접 보낸 요청이 trusted chain만 남긴 경우(`forwarded_all_trusted`). ③ 클러스터 gateway hairpin NAT 주소가 노드 목록 밖이라 `non_global_noncluster`가 된 경우. HAProxy log에서는 observer report 대부분이 gateway NAT를 거쳤다. 이는 사용자가 고른 노드 주소 정책을 그대로 따른 결과다.
- **관측기·수집기:** observer 18대를 1.30.18 source로 교체했다. 모두 nonroot·CapEff0·NoNewPrivs1·Seccomp2를 유지했다. Collector는 compute 12대·controller 3대에 설치했다. CapEff는 정확히 CAP_BPF+CAP_NET_RAW이고 snapshot은 root:afterglow-flow-read 0640이다. Storage는 사용자 선택으로 제외했다. 실측 방향 edge는 123개이며 모두 fresh다. Bridge member NIC로 들어오는 unicast는 bridge MAC으로 향하므로 `PACKET_OTHERHOST`가 되어 promiscuous 방지 규칙에 따라 세지 않는다. 따라서 현재는 송신 측 egress만 계측하고, storage→X 방향은 미계측이다.
- **사용자 화면:** 운영 `/admin/infrastructure-topology`는 렌더링되지 않았다. Observer가 여러 kernel table에서 같은 interface/destination/gateway/metric route를 보고하자 keyed list에 같은 ID가 생겨 Svelte `each_key_duplicate`가 발생했다. 운영 snapshot을 익명화해 재현했다(edge 2,199개 중 중복 route ID 939개). 1.30.19에서 동일 route evidence를 host마다 하나로 합쳤다. 수정 전 실패·수정 후 통과 회귀와 production-shape 렌더링(18 hosts/123 flows, route layer 1,103개 unique, mobile modal, overflow0)을 확인했다. 운영 화면 재확인은 1.30.19 반영 뒤 별도로 기록한다.

### 중복 route 수정과 운영 반영 1.30.19 (2026-10-15)

- **정확한 release:** `9f3be6c1a9703bdb10672f9a064a990ccb7dd637`, architecture digest `f56fed1789b0f85eaead786becb63c93c8bbe1b5d4093546962c942623cb47b0`/2,869 files. Dev CI `38675079723`, tag images `38675665542`, Helm `38675665539`는 success다. API/frontend/worker의 tag·latest digest와 실행 revision label이 일치했다. 표준 image 발행은 현 workflow의 선언대로 amd64이며, Cloud Shell은 amd64/arm64 모두 빌드하고 실제 image에서 1.30.19 metadata를 실행 확인했다. Arm64 표준 image를 새 release가 발행한다고 주장하지 않는다.
- **회귀·compiled 화면:** 동일 route 반복 회귀는 수정 전 `each_key_duplicate`로 실패하고 수정 후 통과했다. 관련 114 tests, 전체 frontend 370 files/3,632 tests가 통과했고 Svelte check는 errors0/warnings3, i18n은0/0이었다. 게시된 frontend `784102ce…`/API `2ae1e371…`/worker `ff8eceaa…`를 task-owned Compose에 재배포해 healthy를 확인했다. API host `127.0.0.1:58741`을 증명한 Chromium에서 운영 익명 snapshot의18 hosts/123 flows,1,103 unique route edges,390px modal inspector와 overflow0을 확인했다. 첫 fixture override는 외부 HTTP 차단 rule 뒤에 들어가 실패했으며 rule 순서를 고쳤다. 누적 requestfailed11을 application exception0과 구분한다. 이는 합성 identity·익명 운영 데이터이지 운영 사용자 인증 수용이 아니다.
- **복구·반영:** operator의 `/etc/kolla/.afterglow-rollout-backups/1.30.19/network-observation-20261015/`에 암호화한 설정·SQL·Redis 복구 지점을 유지한다. Network-none/tmpfs SQL restore는93 tables/2,672 rows, Redis는245 keys 중241 surviving keys를 복원했다(4 expired). Image4keys와 role/site link만 바꿨고 TOML·키·datastore·collector는 변경하지 않았다. Controller1→2→3 각각 `--tags afterglow --skip-tags haproxy --limit <one-controller>`로 genconfig→pull→target-image config-check→prechecks→terminal-work gate→reconfigure→verify-host, 마지막 전체 verify를 완료했다. 첫 controller SSH 결과 수집 timeout 뒤에도 보호된 단계별 receipt가 성공을 증명했으므로 mutation을 재실행하지 않았다. 세 API/frontend는 healthy, worker는 running, 전부 restart0이다. 비대상 container246/239/154개에서 변경·추가0, public health200·미인증 topology/traffic API401을 확인했다.
- **실제 관측:** 06:15 UTC native snapshot에는 fresh·nonzero egress flow123개와 collector measured15/unsupported3개가 있었다. 같은 snapshot의 host freshness는16 fresh/2 stale, TCP33 up/1 unknown이었으며 원본을 보존했다. 뒤이은 host별 진단에서는18개 모두 fresh(표본 age0.42–9.99s)이고 모든 TCP probe가 up이었다. Observer18개는 nonroot·CapEff0, collector15개는 정확히 CAP_BPF+CAP_NET_RAW·NoNewPrivs1·Seccomp2이고 handoff는 root:afterglow-flow-read0640/nlink1이었다. Storage collector 제외와 bridge-member egress-only 경계를 유지한다.
- **부분 관측은 남음:** 실제 DB-IP source는 `offline_mmdb`/`2026-10-01`이며 국가별 KR/AU/SG/US/DE 관측을 확인했다. 24h에는 기존 미분류와 XFF 누락·all-trusted·gateway NAT의 origin unknown이 남는다. Backend dropped474, frontend dropped323/reporter-dropped580이었던 06:15 UTC aggregate를 보존했다. 06:14 이후 controller2의 실제 frontend ingestion503도 file log에서 관측했다. `record_event`의250ms best-effort budget·실패 시 drop coverage 계약을 넓히거나 예외를 숨기지 않았다. 기록된 실패 요청 duration은0.78–1.64s였고 삼켜진 예외의 정확한 종류는 알 수 없다. 따라서 무손실·모든 요청 수집 성공으로 보고하지 않는다.
- **남은 수용:** 기존 사용자의 운영 브라우저 세션이 만료되어 `/login`으로 돌아갔고 tab auth marker도 없었다. 서비스 관리자 자격을 대신 사용하거나 토큰을 추출하지 않았다. 운영 topology/traffic 사용자 화면 최종 수용은 사용자의 재로그인 뒤 진행한다. 물리 switch/port 수용은 승인된 management endpoint/jump와 operator-side0600 SNMPv3 authPriv credential-file 경로가 없어 여전히 차단된다. `fabric.state=unconfigured`를 host traffic으로 대체하지 않으며 OpenSpec을 archive하지 않는다.

위 분리된 증거는 `~/.local/share/afterglow-proofs/network-observation-20261015/{release-1.30.19-publication.json,release-13019-browser/summary.json,release-13019-cloud-shell-runtime.json,production-runtime-13019.json,production-host-freshness-diagnostic.json,production-observer-security-13019.json,production-traffic-filelog-13019.json,production-ingestion-unavailable-timings.json}`과 operator 보호 receipt에 있다.

게시 image runtime 검증 뒤 isolated `dev`에서 `DOCKER_HOST=unix:///tmp/afterglow-observation-client-20261015.sock npm run test:gate`를 실행해 exit0을 확인했다. Backend6,781 passed/95 skipped, frontend370 files/3,632 tests, service contracts174, functional157 passed/29 deselected, Ruff639 files가 통과했다. Orchestration175·Kolla27·CLI20 passed/36 skipped도 포함한다. Disposable functional datastore만 기동·정리했으며 shared Docker Desktop과 운영 datastore는 변경하지 않았다. Gate 원문은 `artifact://782`에 보존한다.

## Chat project footer and MCP acceptance (2026-10-15)

The isolated clone starts at `cbd75d6d506e3609c07202183181004f950a4c51` (latest fetched `dev`). The UI slice changes only the light-theme new-chat project footer: existing sunken surface at90% plus primary ink produces a stronger neutral-gray strip; dark remains `rgb(36, 37, 41)`. That presentation change does not itself alter schema, API, shared tokens or authority. The separately approved OAuth authority repair has its own evidence below.

Source Vite + real Chromium, tutorial identity/API: light/dark at 390/767/768/1023/1024/1568 px passed 12 geometry checks (zero horizontal overflow; footer and enabled project button inside the viewport/strip). The project list opened. The tutorial backend does not implement chat workspace/model data, so this is presentation proof, not authenticated service or project-creation acceptance. Matrix and image: `~/.local/share/afterglow-proofs/chat-mcp-20261015/footer-source-matrix.json` and `footer-source-light.png`.

Production read-only preflight used real first-party login in the admin project. Both `/api/v1/chat/admin/mcp-servers` and `/api/v1/chat/mcp-servers` returned `200 []`; the built-in `/cloud-tools` was available but owner-disabled. Actual `/capabilities?model_id=94` reports checkpointer/MCP ready while protocol v2 is unavailable; static model capability metadata is not the runtime diagnostic. Release, rollout and real tool-call acceptance are recorded separately after execution.

The existing admin account explicitly approved **read-only / current admin project** through the real MCP consent modal. No role, global opt-in or cloud resource was changed. A real `gpt-6.1-sol` UI chat created conversation `a663ca92-de27-4eb5-9a4e-ca8ed3d69582` (201), admitted run `af0742f4-76e7-4f39-92c5-24445c2edb1b` (202), and followed native SSE (200). The replayable 44-event journal records two successful `list_available_tools` calls, successful `afterglow_projects_list` and `afterglow_vm_list`, then `run.completed`; each tool has `error_code=null`. The UI reported admin and three VMs. This is real production identity/provider/worker/Afterglow cloud-query proof before the patch rollout, not Playwright acceptance. Private receipts: `afterglow-chat-observed.json`, `afterglow-live-journal.json`, `afterglow-live-chat.png` in the proof directory above.

The user's separate external OAuth failure is real: controller1 logs at 2026-10-14 16:35 UTC show native Keystone `BadRequestException` 400 (`Could not find role assignment with role`) escaping `/auth/mcp-oauth/consents/{ticket}/approve` as500. Read-only grant metadata records the selected project token's stale `admin/member/reader`; the existing current-assignment API and a new source/native Keystone read both return only `member/reader` for that target. No IAM assignment, provider credential or existing user grant was changed during diagnosis. The repair preserves the full snapshot and omitted-role creation whenever all token roles remain currently valid; new current-graph descendants alone must not remove `member` or refuse manage. Only stale token roles require a current effective-role/token intersection with closed descendant IDs and explicit narrowed IDs. New real installed-SDK/SQL stale-role regression failed twice before issuance repair and then passed both read/manage cases alongside ten existing scope cases (12 passed). The production role metadata probe was read-only; real repaired OAuth/MCP acceptance remains a separate deployment step.

Initial full gate reached backend6610, frontend3621/368files and contract174, then could not bind the canonical functional ports already owned by concurrent `afterglow-domain-qa`. That project was preserved; this task uses the same canonical test-profile services with a temporary port-only overlay on13317/15444/16390. A later loaded-host gate exposed observer child-startup timing assertions. The partial-output test now waits for the real child's pipe to become readable before exercising the unchanged300ms reader deadline, and still proves timeout output and actual child termination; production observer code/timeouts are unchanged. The final CPython3.12 `npm run test:gate` passed: backend **6612 passed /91 skipped**, frontend **368 files /3621 tests**, contract **174 passed**, real-datastore functional **157 passed /29 deselected**, backend Ruff check and format **632 files**. Earlier failed runs remain separate from this successful candidate qualification.

Final OAuth/project/membership targets: **186 passed** with real MariaDB and the installed SDK. This includes retained `member`/manage authority with no stale token roles despite new graph descendants, explicit stale-role narrowing for read/manage, and a real public approval request proving safe400 plus partial credential rollback when Keystone revokes a role during creation. Built backend and worker for linux/amd64+arm64 and frontend for both architectures, then deployed the built images through canonical `docker-compose.dev.yml` in the isolated `afterglow-chat-runtime-20261015` project. Both architecture cohorts reached backend/frontend health and a running worker. Real-image CPython3.12.15 native-IAM smoke preserved a valid authenticated snapshot and narrowed a synthetic reproduction of the reported stale snapshot to live `member/reader`; both images' `projects.py` SHA-256 matched the working source (`048846078d0630d8c5c433e471b8b06e7b9cb2e673d90d1f537aa0bb950a5dbf`). No application credential was created by that read-only probe. Docker Desktop lacked the private VPN route, so only private auth HTTP used a temporary loopback read-only relay; public Keystone metadata retained direct verified HTTPS. The relay/probe scripts were removed. OpenTofu1.8.3 reported the correct linux_arm64/linux_amd64, worker Python reported aarch64/x86_64, and frontend Node20.20.2 reported arm64/x64. Receipts: `oauth-{arm64,amd64}-image-native.json`, `image-executables.json` in the private proof directory. This is local image/native metadata qualification, not repaired production OAuth or Playwright acceptance.

## 1.30.16 release qualification (2026-10-14)

**Local/disposable evidence below; production evidence is separate.** 최신 fetched `origin/dev` `c2712e690ae24a20870f985caf709d3766a7df4e` 위에 보존된 public WIP 전체를 통합한 격리 release clone에서 검증했다. Re-fetch 당시 더 최신 dev는 없었다. 아래 local commands/chart smoke/sibling qualification은 parent의 fresh qualification receipts이며 과거 slice의 실패/skip/제외 범위를 소급 수정하지 않는다. 이 local 결과 자체는 exact-SHA CI·tag·package/image publication·operator 변경·운영 배포 증거가 아니다. 이후 관측된 발행·배포 결과는 [Production rollout 2026-10-14](#production-rollout-2026-10-14)에 별도로 기록한다. Local 원문은 private proof root **`release-all-20261014T073153Z-c2ba90`**에 보존하며 private 입력은 공개 문서에 복사하지 않는다.

### Afterglow commands and totals

Final gate의 stamped working source는 **`fa5e23933e370e34c41bb9d003c514258c85b473fc264472f02e45ebfaf9d3d8`**, **2,849 source files**다. 이는 working-source digest이지 release commit SHA가 아니다.

```bash
env -u AFTERGLOW_TEST_REAL_REDIS -u AFTERGLOW_TEST_DATABASE_URL -u AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL AFTERGLOW_TEST_PROJECT_NAME=afterglow-release-all-c2ba90-final2 npm run test:gate
```

명령은 exit **0**이었다. Functional datastore는 disposable MariaDB/PostgreSQL/Redis이며 실행 뒤 teardown했다.

| Gate lane | Result |
|---|---|
| `docs:check` | Architecture freshness passed |
| JS orchestration | 175 passed |
| Kolla contract | 27 passed |
| CLI install | 20 passed / 36 skipped (56 total; PowerShell 실행은 미검증) |
| Backend unit | **6,610 passed / 91 skipped** |
| Frontend unit | **368 files / 3,621 tests passed** |
| File-log runner | 9 passed |
| Consumer contract | **174 passed** |
| Functional | **154 passed / 27 deselected** |
| `lint:backend` | Ruff check passed; 632 files formatted |

동일 통합 source의 formatting-only backend 변경 **이전**에 다음 명령도 실행했다. 이를 final gate의 exact stamped bytes에서 재실행한 결과로 표기하지 않는다.

```bash
npm run check
npm run build
npm run i18n:check
npm run i18n:scan
```

- `check`: 2,513 files, **0 errors / 3 existing warnings**.
- `build`: production build passed.
- `i18n:check`: **0 errors / 0 warnings**, 40 namespaces / **9,920 messages**.
- `i18n:scan`: **0 hard-coded Korean lines** in **1,072 files**.

Parent repairs는 ordinary Manila-grant deletion fixture의 block-consumer lookup mock, database instances의 빈 shallow-history state, `main.py` import order와 backend 4files formatting, vendored Bklit tooltip/touch/scroll/LTTB 및 상세 timestamp 수정, crypto native lock 재생성, 1.30.16 metadata/native lock 동기화다. Production 삭제의 authoritative lookup·revoke-before-delete·fail-closed 계약은 유지했다. 구체적인 수정 항목은 `CHANGELOG.md` 1.30.16 **Fixed**에 기록한다.

### Compiled native chart smoke

현재 source의 실제 `runtime.tsx`/vendored Bklit와 application CSS를 Vite production bundle로 컴파일해 managed Chromium에서 실행했다. Data는 synthetic local fixture이며 authenticated dashboard나 production proof가 아니다.

- Bar polling: hover 값 **2**, refresh **2→9** 뒤 cached tooltip dismissal, re-hover 값 **9**.
- Time series: held pointer가 refresh **2→9** 뒤 새 값에 re-anchor했다. 상세 title은 **`Oct 13, 09:34:56 PM`**으로 날짜·초를 포함했다.
- **390px touch**: scrub tooltip 표시 후 touch end→refresh에서 tooltip/crosshair가 되살아나지 않았다.
- Decorative line/area/bar 및 zoom-disabled map 위 vertical swipe가 page를 각각 **180/121/117/117px** scroll했다. Map은 `touch-action: pan-y`, grab cursor 없음.
- Map: keyboard focus+Enter로 Korea 선택(`aria-pressed=true`), interior touch tap으로 China 선택.
- Application exceptions **0**.

### Paired sibling qualification summary

각 sibling도 격리 integration clone의 local/disposable 검증이다. SDK/service/선택 SQL smoke는 서로 중복할 수 있으므로 합산하지 않는다. Native HTTP/SQL/process/image 실행과 synthetic provider·IAM 경계를 구분한다.

| Pair | Commands / totals | Runtime scope and limits |
|---|---|---|
| **Lumen 0.6.8** | `env -u LUMEN_TEST_DATABASE_URL -u LUMEN_TEST_REDIS_URL uv run --no-sync lumen-test contract -q`: service **3,179 passed / 344 deselected**, SDK **128 passed**, Ruff passed (CPython 3.12.13). `lumen-test integration -q`: **313 passed / 3,210 deselected**. `lumen-test system -q`: **31 passed**. | Disposable MariaDB/Redis and locally built native **arm64** api/worker/batch-worker/migrate images, fake Keystone/provider, MinIO/ClamAV/Postgres. **amd64 image execution**, real IAM/provider and production not qualified. |
| **Drover 0.4.15** | `uv sync --python 3.12 --frozen --extra service --extra dev`; `uv run pytest tests -q`: **1,560 passed / 3 skipped**; `ruff check .` passed. Frozen all-extras SDK: **114 passed**, Ruff passed. `uv build --wheel`: `drover-0.4.15-py3-none-any.whl` includes `tasks/source_build.yml`. | Canonical api/worker **amd64+arm64** images executed with version/machine/import checks. `scripts/worker_ownership_smoke.py` inside arm64 worker with qualification-only Redis overlay and empty disposable MariaDB: exit **0**, initial owners **[11,11,11]**, **9 SQL jobs**, lost-reply/killed-after-accept no replay, drain/crash takeover and Redis fail-closed, **0 duplicate healthy polls**. Provider synthetic; not Keystone/guest/production. |
| **Waygate 0.3.4** | `uv sync --python 3.12 --frozen --extra service --extra dev`; `uv run pytest tests -q -n 4 --dist worksteal`: **729 passed / 3 skipped**; `ruff check .` passed. Frozen all-extras SDK: **44 passed**, Ruff passed. Disposable `WAYGATE_DELEGATION_MARIADB_URL`, `tests/test_execution_delegation.py`: **61 passed**. | Canonical api/worker **arm64+amd64** images. `WAYGATE_NATIVE_CONTAINER_SMOKE=1 uv run pytest tests/test_native_service_grades.py -k native_built_images_and_mariadb_upgrade -q -s`: **2 passed**. MariaDB 11.4.13 preserves 001–004 ledger/records/ciphertext through packaged 005–006, NULL owner reopen and competing assign-once; native HTTP/SDK/ownership/downgrade/export/machine callbacks. Not production proof. |
| **Palimpsest 0.3.5** | `uv sync --python 3.12 --frozen --extra dev`; `scripts/test_lanes.py list --check` valid; `scripts/test_lanes.py run full`: **7,064 passed / 264 skipped**. Ruff check/format, OCI fixture and CLI-reference checks passed. Client wheel+sdist built/smoke-installed; `uv run --python 3.11 --no-dev palimpsest --version` → **0.3.5**. Hub `pytest tests -q`: **559 passed / 2 skipped**, Ruff passed; `uv build` built Hub wheel+sdist. | Disposable `PALIMPSEST_OWNERSHIP_SQL_URL`, `test_shared_sql_process_ownership_smoke`: **2 passed**, 2/3 real SQL/process workers with independent flocks, synthetic remote provider. Canonical Hub api/worker/build-worker **amd64** images executed under local emulation; version/import checks and build-worker client/tools present. Opt-in **native/KVM/BuildKit skipped**, not qualified; no native cloud/production proof. |

### Production rollout 2026-10-14

The observed DMS Lab production window was approximately **09:43–11:15 UTC**. Canonical Kolla ran from the operator host with **`--skip-tags haproxy` on every pull/prechecks/genconfig/reconfigure/deploy action**; the known controller3 HAProxy/ProxySQL/Keepalived image drift was intentionally untouched. Service order was **Drover → Lumen → Waygate → Palimpsest (controller1 Hub, then remote build worker VM) → Afterglow**. Each service used a terminal work gate, stopped every API, gated again, then stopped every worker: no mixed old/new writer cohort. Cold MariaDB dumps were restored in isolated **network-none/tmpfs** instances with exact per-table counts before genconfig/reconfigure. Verification checked pinned digests, OCI revision labels, health/restarts on every replica and unchanged non-target containers. Against the first pre-Drover census, non-target containers stayed unchanged at **234 / 231 / 144** on controllers **1 / 2 / 3**, with none added.

**Publication and operator promotion.** Afterglow commit **`eaa5772a6ebcab75dc3748add134b92d9f33f4e3`** passed exact-SHA CI; tag **`v1.30.16`** Helm Chart Release and Docker workflows succeeded. Published digests (OCI revision `eaa5772a`) were:

| Image | Digest | Scope |
|---|---|---|
| `afterglow-api` | `sha256:70cceb9edfc1b2935aaf2c40fcc9afa3e2ed31a715ec65dda1a80d91cb90b027` | Production |
| `afterglow` (frontend) | `sha256:f6d393ba16527fdba4aa689a2913371fea0f82a13227ca596b114ebda2ec94c8` | Production |
| `afterglow-worker` | `sha256:2506440c9cfccdbc9c2d33db58172b55d37a92d2525575013681568d67ac6982` | amd64; production |
| `afterglow-cloud-shell` | `sha256:a4ffd68e48bb031a69095b26e772971f6b4b2e019c8cd3449328a4cfd4f38e9d` | amd64+arm64; published only, no production image configured |

Operator `/etc/kolla` packages were promoted to Drover **0.4.15**, Lumen **0.6.8**, Waygate **0.3.4** and `palimpsest-client` **0.3.5**. `uv lock --upgrade-package` changed only those packages plus the virtual `kolla` project; installed role files matched the tags byte-for-byte (**20 / 23 / 22 / 27** files respectively). The Afterglow plugin was a shallow tag checkout at `/etc/kolla/plugins/openstack-afterglow-v1.30.16`; its `deploy/kolla` tree **`ad8ee874`** matched the tag, and role/site links switched only before the Afterglow phase.

- **Quiesce and cold restore:** an encrypted `preafterglow` snapshot included every controller's `/etc/kolla/config/afterglow` backend/frontend bind-mount source and the operator backend/frontend config. **3 backends + 3 Notion workers exited 0**, with the work gate terminal. MariaDB restored **90 tables / 2,485 rows**, exact. Redis **db5: 95 keys / 0 active auto-backup journals**; all **95** keys restored in isolated Valkey.
- **088→089 migration, writers stopped:** `088_layer_block_sources.sql` (SHA-256 prefix **`5c43bf8f`**, **114 ms**) then `089_layer_block_consumes.sql` (prefix **`8a46fc70`**, **109 ms**). Required columns went **0→5**: `layer_artifacts.block_source` and `layer_consumes.transport/run_id/resources/cleanup_state`. Row counts were unchanged; table count stayed **90** after Kolla bootstrap. Follow the [schema upgrade guidance](deployment.md#13016-업그레이드-sql-088089와-writer-cohort), not a blind migration replay.
- **Reconfigure:** genconfig left generated files unchanged; new traffic-analytics settings are frontend environment variables and the empty ingest key keeps ingestion off. Reconfigure ran **controller1 → health gate → controller2 → health gate → controller3**.
- **Verify:** **9 containers** on pinned digests/revision, **healthy / 0 restarts**. `/api/v1/health` and frontend `/health` returned **200** on all three listeners and publicly. Backend logs since cutover had **0 WARNING-or-higher lines**, only DEBUG `client_error` request diagnostics.
- **Authenticated browser and Bklit:** real Chrome used first-party Keystone login as the backend's configured service account, credentials in memory only, **GET-only**. `/api/v1/auth/me` returned **200**; `/api/v1/instances` **200 (0)**; `/api/v1/auth/mcp-tokens` **200 no-store (0)**; `/api/v1/auth/mcp-oauth/grants` **200 no-store (0)**; `/api/v1/auth/mcp-projects` **200 no-store (1)**. At **1440 px and 390 px**, `/dashboard` rendered **5/5 gauge charts**, **0 failed**, **0 px horizontal overflow**; `/dashboard/activity` rendered **1/1 bar chart**. Page errors: **0**.
- **Not covered/performed:** admin-only chart pages (the account is not a system admin), all locales/themes, an ordinary test tenant, pruning, policy/IAM changes, LB/route changes, paid inference or Cloud Shell enablement. Cloud Shell publication is not production execution evidence.
- **Residual observations:** activity `hour_distribution` uses UTC-hour buckets without a timezone label; the dashboard Drover tile shows **"unavailable"** for this service account, as in the 1.30.15 post-deploy screenshot. Both pre-existed and were unchanged. The repo's `deploy/kolla/operator/pyproject.toml` still pins older role tags (Palimpsest **0.3.3**, Lumen **v0.3.1**, Waygate **v0.2.0**, Drover **v0.2.25**); it was not changed during rollout and is not the promoted operator package state.
- **Recovery boundary:** SQL **088/089 are applied and 1.30.16 writers are live**; **image-only rollback is not allowed**. Recovery requires the cold DB/Redis backups, previous images and `preafterglow` config snapshot in the protected `/etc/kolla/.afterglow-rollout-backups/1.30.16/` directory.

**Cross-service outcome and residual risks.** All four sibling releases were deployed: Drover **v0.4.15** exact-SHA CI and Release/Docker workflows succeeded; all **6** writers exited **0**, cold restore was **16 tables / 75,225 rows**, ledger stayed **4/4**, genconfig unchanged, all **6** pinned replicas had healthy APIs/**0 restarts**, readiness **200 ×3 + public**, and **0** error log lines. Lumen **0.6.8** exact-SHA CI and Package Release/Docker succeeded; terminal gate, cold MariaDB restore **63 tables / 5,540 rows**, cold checkpointer Postgres dump **4 tables**, ledger **26** unchanged, `llm_providers` **6 rows** unchanged (last update **2026-10-10**), plus **3** new worker registrations; all **6** pinned replicas had healthy APIs/**0 restarts**, readiness **200 ×3 + public**, and **0** error log lines. Five old Lumen writers exited **0**, but the old **0.6.7 controller3 worker was SIGKILLed (137) after the 300 s drain**: registration `auxiliary_active=1` with all runs/jobs/memory-outbox/batch-queue live leases zero prevented `acknowledge_drain`; five older **2026-10-05/06** registrations showed the same pre-existing defect, needing follow-up. Waygate **0.3.4** exact-SHA CI/Docker succeeded; **6** writers exited **0**, cold restore **7 tables / 54 rows**, ledger **6/6** and genconfig unchanged, replicas healthy/**0 restarts**, health **200 ×3 + public**. Its unchanged plain Redis URL targets a **read-only Valkey replica**, producing handled `ReadOnlyError` WARNINGs in `agent_auth.store_status_result` (POST still **204**, status not cached); Drover/Lumen/Palimpsest use plain URLs to the same node too, while only Afterglow is Sentinel-aware. Sentinel/master-routed wiring is a separate needed change. Palimpsest **v0.3.5** merged PR **#24** at **`04d51ad6e1bf00c4b6e5bf82050383d0bb0a10cf`** after six required checks on `1ff87efe`; dev CI, Release (verify/PyPI/GitHub) and Hub image workflows succeeded, with native KVM proof skipped by repository policy. Controller1 Hub API/worker exited **0**; cold restore **15 tables / 10 rows**, encrypted blob tar **884,766,720 bytes**, genconfig unchanged, controller1-only reconfigure, health **200 direct + public**, unauthenticated `/v1/me` **401**. The remote build worker halted on the old **0.3.4** journal's **`claim_pending`** at **10:47:06Z**, **5 s** after Hub API quiesce began. Server proof showed **4 terminal builds**, every `lease_expires_at` **NULL**, last change **2026-10-13 21:19:30Z**, nothing claimable: the journal was preserved in operator backup and on the VM, `worker.json` cleared, `worker.lock` retained. The worker then had **0 restarts**, and Hub logged **16** claim requests → **204** in **2 minutes**. Future rollouts must stop/drain the remote build worker **before** the Hub API.

Sanitized archive evidence: [`production-verification.json`](../openspec/changes/archive/2026-10-14-release-complete-public-changes/evidence/production-verification.json).

## Bklit 대시보드 수치 시각화 전환 검증 (2026-10-14, local-only)

`standardize-bklit-visualizations`는 실제 MIT Bklit UI registry commit `f7b3bd2999a5c993863f9cc5523c9cf60b9f3bc2`를 Svelte의 client-only React 경계에서 실행한다. 사용자/관리자·서비스별 자체 선/영역·bar/stack·usage/quota/capacity gauge/ring·country choropleth를 전환했고 전체 surface/향후 개발/upstream 갱신 기준은 `frontend/README.md`에 둔다. 편집 토폴로지·외부 Grafana·진행 상태/아이콘은 별도이며 내장 수치 그래프만 이 경계를 사용한다.

Private root 설정은 읽거나 수정하지 않고 현재 public frontend를 별도 scratch로 복사해 실제 adapter-node production build를 실행했다. Identity/API payload는 loopback 합성이며 cloud/provider 호출·실제 인증·배포 증거가 아니다. 1,717개 `frontend/src/` 파일은 compiled clone과 SHA-256 byte parity가 일치한다. QA route/fixture/profile은 scratch에만 존재하며 공유 checkout/index·Compose·볼륨·운영 설정은 보존한다.

| 검증 경계 | 실제 결과 |
|---|---|
| Native boundary + login consumer exact | `runtime.test.ts`, `runtime-map.test.ts`, `loginMonitoringController.test.ts`: 3files / 39 passed. Native scales/paths/projection을 사용하며 jsdom shim은 없는 layout 정보만 제공한다. |
| 전체 frontend | 최종 `vitest run --maxWorkers=4`: 367files / 3,615 passed, 실패/skip 0. File-log runner 9 passed. Legacy SVG element/class/geometry-implementation assertion은 삭제하고 실제 값·filter·scope·unknown-budget 계약은 유지했다. |
| Named design target | `npm run test:frontend:design`: 26files / 128 passed. |
| Build·i18n | 실제 adapter-node production build 성공. i18n check 0errors/0warnings,40namespaces/9,920source messages; scan 1,072files에 hard-coded Korean 0. |
| Type check 한계 | 최종 `npm run check`: 2,520files, 범위 밖 database instances `PageState.instanceId` 오류1개(`+page.svelte:42:54`)와 기존 warning3개. Bklit/TSX 변경 진단0. 전체 type check 통과로 표기하지 않는다. |
| Compiled component matrix | 실제 consumer 39개 plot(ring5/gauge10/bar11/time-series12/choropleth1), ko/en/ja/zh-CN × light/dark × 390/768/1024/1440 = 32조건. Document overflow·invalid path·축 잘림·pairwise label overlap·reduced-motion running chart animation 모두0. |
| Compiled actual routes | `/dashboard/activity`, `/admin/chat/stats`, `/admin/monitoring/traffic` × 2themes × 4widths = 24조건. Overflow·invalid path·axis label overlap0, browser exception0. |
| Data/filter/refresh | Activity 7d→24h, admin chat model-a/90d, instance metrics 1h→6h 및 refresh, chat day→month/1y의 실제 query와 렌더링 확인. Traffic backend→frontend/24h→7d, refresh의 Japan100→101 관측을 native map label에 반영했다. |
| Numeric/lifecycle edge | 5px stack의0/70/95/120 사용량에서 정확한 used/proposed endpoint와100% clipping;18px ring;무제한;null gap3구간과 table의 미관측 표시;empty에서 painted path0;unmount0/remount39;독립 timestamps·실제0 baseline을 검증했다. |
| Map·motion·quota | SG(소국가)/XX(미위치) 선택 보존, clear/Enter/Space와 동일 native feature focus 유지, native tooltip, quota7/10=70%와 limit10 입력 보존. Live motion 정책 변경 뒤12frames 동일 geometry·running animation0. |
| Browser에서 발견/수정 | 작은 ring padding·5px stacked segment/초과 clipping·null gap/reveal;모바일 범주 축 잘림/겹침과120px metric card의 숫자 tick 겹침. Canonical ISO bucket은 scale key로 유지하고 축/tooltip 상세 formatter를 분리했다. 축의 width/height 기반 tick density와 이웃 간 간격을 실제 browser에서 확인했다. 초기 실패 matrix도 보관한다. |
| Architecture | Public frozen snapshot(동시 WIP 포함)의 working stamp와 독립 temporary-index staged guard가 동일 `891401c9ce17f0bdc88a4a79dbca7c4f22405c6e2f2784ad4160fef23b3c0145`/2,847files로 통과했다. 공유 index/review marker는 그대로이며 전체 동시 WIP의 integration 승인이 아니다. |
| 전체 gate 한계 | 동일 public frozen snapshot에서 `npm run test:gate` 실행. 첫 시도는 scratch에 pytest가 없어 중단됐고 locked `uv sync --extra dev --frozen` 뒤 같은 명령을 실행했다. Architecture·JS orchestration/Kolla/install lane 통과(비가용 PowerShell36 skip), backend unit6,569passed/91skipped/11failed. 실패11개는 모두 범위 밖 `test_instance_storage_delete.py`의 block-consumer tracking/DB 계약이며 기존 동시 WIP를 고치지 않았다. Gate는 이 지점에서 중단되어 이후 contract·functional·backend lint는 미실행이며 전체 통과로 기록하지 않는다. Frontend는 별도 최종 전체 실행으로 위와 같이 통과했다. |

Receipts: `~/.local/share/afterglow-proofs/afterglow-bklit-7mhvOI/`의 `matrix-final.json`, `route-matrix.json`, `routes.json`, `consumer-filters.json`, `interactions.json`, `quota-motion.json`, `frontend-tests-accepted.json`, `architecture.json`, `source-parity.json`, `accepted-*.png`, `route-*.png`. 실제 운영 인증·cloud/provider·deployment acceptance는 미검증이다. 선택적 gbrain CLI가 설치되지 않아 code index sync는 실행하지 않았다.

## 공유 background process 역할·대상 분배 검증 (2026-10-14, local-only)

`distribute-background-processes`와 Drover·Waygate·Lumen·Palimpsest native change를 각 저장소 current working tree를 byte 단위로 복사한 frozen public clone(동시 WIP 포함)에서 실행했다. 소유한 Docker MariaDB 11.4(tmpfs)·Redis 7 loopback fixture와 합성 provider만 사용했고 private 설정·운영 Redis/IAM·배포·commit·stage·push는 하지 않았다. Receipts: `~/.local/share/afterglow-proofs/afterglow-process-ownership-n7xrnua4/`.

| 검증 경계 | 실행 결과 |
|---|---|
| Afterglow 선택 lane(최종 source) | core 19files 675 passed; build 8files 143 passed; Notion/Trove 7files 92 passed; 인접 consumer 22files 403 passed/95 skipped. Skip 91건은 Linux GNU coreutils guest helper, 4건은 MariaDB 전용이며 owned MariaDB의 `AFTERGLOW_TEST_DATABASE_URL`로 4 passed. |
| Afterglow 전체 backend unit | `pytest tests/ -m "not db and not contract" -n 4` 6569 passed, 91 skipped, 11 failed. 실패는 모두 `test_instance_storage_delete.py`의 `block consumer tracking database unavailable`로, untracked block-consumer WIP와 수정된 `instances.py`에서 발생하며 2026-10-12 기록과 같은 범위 밖 실패다. |
| Failed-before/passed-after | ① Leader crash 중 assignment hash TTL이 membership(45초)과 같아 후계 선출(약 60초) 전에 만료되어 정상 실행자 lease를 철회했다(`DispatcherUnavailable: Background work lease was revoked`). 2× TTL 뒤 `test_work_dispatcher.py` 39 passed, 실제 Redis 운영 상수(45/10/90)에서 lease 85.1초 유지·후계 60.04초 선출·철회 없음. ② Manila 2.45+ `access_list` 오독(native HTTP `ValueError: Manila access-rule list is incomplete`) 수정 후 통과. ③ 선택 consumer 정리 실패에도 import를 `complete`로 닫음(`'complete' == 'running'`) 수정 후 통과. ④ Library 취소의 즉시 terminal·요청 내 provider 연결(`completed_at` 설정, keystoneauth `MissingRequiredOptions`)을 pending cleanup 계약으로 바꾼 뒤 2 passed. 이 함수는 `110058dd` 이후 API route가 없다. ⑤ Ownership 재작성으로 사라진 layer build `execution` INFO/DEBUG 이벤트(`[] == [started, completed]`)를 복원했고 `test_logging_contract.py` 43 passed. |
| 실제 API process | 실제 `uvicorn app.main:app` 3개, Redis DB8, MariaDB에서 api-roles/builds/volume-backups 각 3 member, 역할 1/1/1. SIGTERM 0.23초 graceful shutdown 뒤 member 2와 역할 재배정, 전체 종료 뒤 member 0·leader null·traceback 0이고 3/3이 `Application shutdown complete`를 기록했다. Exit `-15`는 Uvicorn 0.39가 graceful lifespan 종료 뒤 SIGTERM을 재발생시킨 결과다. |
| 실제 공유 role process | Interpreter 3개, 실제 Redis, native `run_roles`/`_background_sdk`. 초기 2/2/2, SIGTERM drain 뒤 생존자 재배정, crash 인계 46.73초·실제 작업 89.69초(90초 lease), overlapping role effect 0, 종료 뒤 member 0·leader null. Leader-gap 수정 전 실행(49.95초/90.07초)은 별도 보관했다. |
| Notion lane 안정성 | 4 lane 동시 실행 중 1회가 300초 제한을 넘었다(출력 없음, 원인 미확정). 같은 source 단독 1회와 동시 부하 8회(faulthandler 45초) 모두 92 passed로 재현되지 않았고 잔여 process도 없었다. |
| Afterglow style·architecture | 소유 backend 45 files `ruff check`·`ruff format --check` 통과. `main.py`는 소유 줄만 정리하고 동시 import block은 건드리지 않았다. Frozen public snapshot(동시 WIP 포함)의 working stamp와 격리 temporary-index staged guard가 동일 `98e79ca0151c428ae659c294c5950209a5784b67dcc269f03d045703531f6a34`/2847files로 통과했다. 공유 index/review marker는 보존했다. |
| Drover | Focused 374 passed; 전체 service 1323 passed/1 skipped. Three-replica smoke(owned Docker Redis pause/unpause, 빈 MariaDB, 합성 provider)는 exit 0, [11,11,11], 모든 safety flag true. 이전 시도 1·2는 harness 실패(listen backlog, InnoDB 1213 deadlock)였고 3·4와 최종 run은 통과했다. Ruff는 기존 scoped-access 2건만 남았다. Guard `f7e9f7f0…`/230files. |
| Waygate | Focused 115; MariaDB 49(0 skip, 실제 worker SIGTERM/SIGINT drain·accepted response 유실 무재발행 포함); 전체 671 passed/3 skipped(opt-in image 2, live 1); Ruff clean. Guard `b3f9def4…`/120files. |
| Lumen | Focused 110; integration 110 passed/3393 deselected(실제 Redis/SQL 다중 process smoke·late join·crash·lock 내 배정 상실, ON/OFF); contract service 3159/344 deselected·SDK 128·Ruff 통과. Ruff는 HEAD 기존 1건만 남았다. Guard `41a373a1…`/501files. |
| Palimpsest Hub | Focused 93 passed/2 skipped; MariaDB 다중 process smoke 2 passed; 전체 hub 378 passed/2 skipped. Hub format gate는 다른 change(`isolate-service-execution-credentials`)의 7 files와 `tests/test_auth.py` I001 때문에 실패 상태로 남는다. Guard `d4300659…`/468files. |
| 미검증 | 운영 Redis/Sentinel failover와 비동기 복제의 lease/journal 유실·TIME skew, 혼합 버전 rolling upgrade, 실제 OpenStack/Keystone/K3s/KVM/유료 추론, 배포. 전체 `npm run test:gate`는 동시 WIP 실패 때문에 통과로 기록하지 않는다. |

## 관리자 자격 증명·호스트·접속 모니터링 검증 (2026-10-14, local-only)

`add-admin-credentials-host-telemetry`는 Identity 자격 증명, Hypervisors host health, 인프라 topology, traffic/world map 및 login/session 화면을 연결한다. Private root TOML의 기존 line10,column9 파싱 장애를 변경하지 않고 current public source를 격리 clone으로 복사했다. 동시 public WIP가 포함된 snapshot이며 공유 index/review marker·운영 설정·배포를 수정하지 않았다.

| 검증 경계 | 실행 결과 |
|---|---|
| 선택 회귀 | Monitoring target backend304/frontend263(11files), access backend326/frontend38(4files), config backend256/frontend12(2files) 통과. 공유 selector의 중복은 합산하지 않는다. 후속 미응답 hop 압축 회귀는 topology2files81passed로 확인했다. |
| 빌드·품질 | Adapter-node production build 성공. i18n0errors/0warnings,40namespaces/9911source messages. 변경 backend25files Ruff check/format 통과. Svelte check는 범위 밖 database instances `PageState.instanceId` 오류1개와 기존 warning3개로 실패하며 변경 파일 진단은0이다. |
| Native credential | 실제 FastAPI→installed openstacksdk3.3.0→loopback Keystone HTTP로 reader 역할 application201·1회 secret·닫기 후 폐기·확인 삭제204, cert 원문 blob 생성/명시적 상세/수정/삭제204를 실행했다. 목록 blob 비공개·no-store, nonadmin403, native403 정제와 UI 거부·복구를 확인했다. Identity와 Keystone records는 합성이다. |
| 10초 host health | 실제 lifecycle/Redis lease와 native Nova HTTP inventory, bounded HTTP exporter fixture에서3hosts의 CPU25%·memory50%·filesystem75%·RX10KiB/s·TX20KiB/s 및 연속 history를 확인했다. Exporter503은 UI의 연결 실패·측정 없음이고 Nova heartbeat와 구분된다.200복구 뒤 새 연속 표본의 rates가 복원됐다. |
| Linux observer/network | 전용 nonroot/read-only/cap-drop-all Linux container의 실제 iproute2·`/proc/net/dev`·HTTPS observer가10초마다 보고했다. 실제 TCP9100open/9101closed를 방향별 표시하고, unprivileged traceroute가 direct1hop와 소유 dual-NIC router를 지나는2hop 성공, router 이후15미응답 hop의 reached=false를 보고했다. 연속 미응답은 지도에서 범위로 압축되며 원본 hop은 유지한다. Disallowed destination422·nonadmin403·60초 trace rate limit을 확인했다. LLDP 미설치는 unsupported로 표시했고 물리 케이블 연결을 검증했다고 주장하지 않는다. |
| 실제 장애 표시 | 소유 observer를 중단하자 host·NIC·peer·trace 근거가 오래된 관측/확인 불가로 바뀌었고 다시 시작했다. Exporter HTTP503과 Keystone403도 실제 응답으로 주입해 정상0 대신 오류·미측정을 표시하고 복구를 확인했다. |
| Traffic/login 실제 저장 | 실제 Redis Lua/HLL에 한국·미국·호주 합성 country fixture의200/401/404 요청을 수집하고 세계지도2개 country→KR 논리 arc와 미위치 분리를 확인했다. 실제 SvelteKit server reporter가 frontend source의 HTML pageview/response bytes/unique estimate를 별도 수집했다. SQLite ActivityLog4개와 Redis 유효 세션1개를 표시하고 절대수명 초과 세션을 제외했다. 응답에 token/JTI/IP/fingerprint가 없으며24h/7d/30d 조회200을 확인했다. |
| Compiled Chromium | 실제 adapter-node UI의6screens×ko/en/ja/zh-CN×dark/light×320/390/768/1024/1440px 총240조건에서 document overflow0·heading/locale/theme 표시를 확인했다. Credential CRUD, host graphs, NIC counters, shared router/gap map, country map, login history를 시각 검토했다. Native cloud/auth/exporter/country는 합성이며 실제 운영 로그인/provider acceptance가 아니다. |
| Native Redis 회귀 | 별도 disposable Redis DB6에서 Lua concurrency/dedupe/HLL/privacy·24h/7d/30d/retention·capacity·route/country 경계4passed. 처음에는 test의 binary DUMP를 text/hiredis client로 읽어 UnicodeDecodeError와 다음 pipeline 오염을 일으켰다. 별도 decode_responses=false pool로 fixture만 수정해4개 모두 통과했으며 서비스의 실제 empty/unavailable 구분을 약화하지 않았다. |
| 전체 gate | `npm run test:gate`는 docs guard를 통과했으나 orchestration174passed/1failed에서 중단됐다. Frozen 동시 WIP의 storage selector가 없는 `tests/test_backup_dispatcher.py`를 가리킨다. 무관한 selector/source를 변경하지 않았고 이후 전체 unit/contract/functional/lint 통과를 주장하지 않는다. stdout은 `full-gate.log`에 보존했다. |
| Architecture | Binary-reader fixture 최종 수정 뒤 frozen public snapshot(동시 WIP 포함)의 working stamp와 격리 temporary-index staged guard가 동일 `1d4708475cb3a1c857d6e4c684485d1b285a1099ffa26d0f456a580bf46cc75d`/2735files로 통과했다. 공유 index/review marker는 보존했고 전체 동시 변경의 integration 승인을 뜻하지 않는다. |

증거는 `~/.local/share/afterglow-proofs/afterglow-admin-monitoring-fvp32smm/`의 `verification.json`, `browser-matrix.json`, 화면별24개WebP와 `world-map-light.webp`, `exporter-outage.webp`, `observer-stale.webp`다. 첫 native directory fixture의 marker 미처리로 SDK endless pagination503이 발생했으며 marker page를 구현해200복구했다. 외부 font 차단·명시적 fixture 재시작/페이지 이탈의 request abort는 JS 오류와 구분한다. 실제 운영 exporter/LLDP·허용된 외부 인터넷 경로·GeoIP DB·IAM, multi-arch image/운영 배포는 검증하지 않았다. Gbrain CLI는 PATH에 없어 sync/CLAUDE 변경을 하지 않았다.

검증 종료 후 소유 API/frontend/Chromium, disposable container7개·network2개·observer image를 종료·제거했다. 임시 clone/profile·fixture scripts·합성 TLS/SQL/GeoIP 입력을 제거하고 JSON/WebP/full-gate log만 보존했다. 기존 개발 서비스·volume·private 설정과 사용자 index는 건드리지 않았다. OpenSpec rapid change는 delta spec 없는 task-based 변경으로 `openspec/changes/archive/2026-10-13-add-admin-credentials-host-telemetry/`에 archive했다.


## 보안 그룹 규칙 저장·인라인 편집 검증 (2026-10-14, local-only)

`fix-security-group-rule-editor`는 사용자 첨부 화면의 수동 제거/추가 편집, 표 맨 아래 편집 폼, 추가 폼의 중복 진입 버튼을 수정한다. 변경 source는 route·rules panel·shared form·page 회귀·네 `network-pages` catalog 8개다. Backend endpoint·schema·권한·설정·운영 상태는 변경하지 않았고 공유 index·review marker·동시 WIP·private 설정을 보존했다.

| 검증 경계 | 실제 관측 |
|---|---|
| Exact page 회귀 | `npm run test:target -- frontend:src/routes/dashboard/network/security-groups/__tests__/page.test.ts` 21 passed. 인라인 위치·취소/무변경 무요청, 생성 우선 교체, 쿼터 가득 참의 제거 우선·복원, 복원 실패 뒤 재저장의 중복 DELETE 없음, 기존 규칙 제거 실패, 잘못된 CIDR/IP 버전/포트/원격 대상의 쓰기 전 거부, 외부 삭제 뒤 저장을 포함한다. |
| Design·i18n·type | `npm run test:frontend:design` 27 files/138 passed. `i18n:check` 0 errors/0 warnings, `i18n:scan` hard-coded Korean 0. `npm run check`는 변경 파일 진단 0이지만 범위 밖 `CredentialManagement.svelte`의 `$props.id()` 위치와 database instances `PageState` 오류2개로 exit1이다. |
| 전체 frontend unit | `npm run test:unit:frontend`는 363 files/3,517 tests passed지만, 범위 밖 untracked `CredentialManagement.svelte`의 같은 `$props.id()` compile 오류로 `adminCredentialsController.test.ts` suite 1개가 실패해 exit1이다. 이 변경의 회귀는 모두 통과했다. |
| 실제 Chromium 흐름 | 현재 작업 트리 Vite dev(`127.0.0.1:4417`)의 실제 route를 합성 sessionStorage identity와 in-memory HTTP fixture로 실행했다. 선택 행 bottom과 form top(532px), form bottom과 다음 행 top(777px)이 같았고 동작은 `저장`/`취소`였다. 취소·무변경 저장은 요청이 없었고 교체는 POST→DELETE였다. 추가 시 상단 trigger0·단일 `추가`였으며 생성 실패는 POST만 보내 원래 규칙/초안을 유지했다. 쿼터 가득 참에서는 잘못된 CIDR·IP 버전이 요청 없이 거부되고 DELETE→실패 POST→복원 POST가 원래 정책과 초안을 남겼다. 복원 실패 보고 뒤 재저장의 DELETE는 1회였고 기존 규칙 제거 실패는 두 정책과 부분 적용 오류를 표시했다. |
| 반응형·locale·theme | ko/en/ja/zh-CN × dark/light × 390/767/768/1023/1024/1440px 48조건에서 document overflow0, 편집 폼의 선택 행 직후 배치, 표 scroll container 안 입력/버튼 수용과 최대 가로 스크롤 뒤 sticky 수용, 쿼터 가득 참 경고와 두 동작, 최소 글자12px를 통과했다. 증거: `~/.local/share/afterglow-proofs/security-group-rule-editor-20261014/`의 matrix.json과 대표 screenshot8개. |
| Architecture | HEAD `aac6b9c5`+8개 source 격리 worktree/index에서 working stamp와 staged guard가 `source_sha256=cedb9087f07570fac6d5a2d37f1cb131f0ed44c037a5df0d21a0ce7d24f40b3a`/2,615 files로 통과했다. 실제 공유 index·review marker는 수정하지 않았다. |

미검증: 실제 Keystone 로그인·Neutron 규칙 생성/삭제·다중 worker cache 최신성·전체 `npm run test:gate`·배포. 합성 fixture는 backend Pydantic·Neutron 검증을 대체하지 않는다.

## MCP OAuth 역할·Lumen discovery/worker 복구 검증 (2026-10-13, local-only)

`repair-mcp-authorization-tool-discovery`는 외부 OAuth credential 발급과 명시적으로 선택된 Afterglow MCP의 legacy chat 검색·적재·실제 조회를 복구한다. 운영 기존 로그를 읽어 Keystone400 `Cannot create an application credential with unassigned role`를 확인했으며 운영 승인 요청을 replay하지 않았다. 로컬 실패-before와 수정-after를 별도로 보존한다.

| 검증 경계 | 실제 관측 |
|---|---|
| OAuth/MCP TCP·installed SDK·SQL/Redis | Read/manage × current/selected/all 6조합에서 approve200→token200→MCP initialize/list→VM `isError=false`를 확인했다. Read19/manage29 schema, 실제 조회와 명시적 revoke204·stale snapshot403 포함35checks. IAM/identity/catalog/VM inventory는 합성이다. |
| Afterglow 관련 회귀 | 비DB credential/프로젝트 권위 선택164passed·Ruff 통과. DB/authority 선택306passed로 actual SDK 요청·반환 project/role ID mismatch cleanup·selected/all anchor 제외·read/manage ceiling·expiry/revocation을 검증했다. 두 선택은 중복 가능하므로 합산하지 않는다. |
| Native discovery 경계 | 실제 native bindings·installed plugin의 TCP bridge/SQL/Redis/VM SDK10checks: 최초3schema, 한국어 cloud/VM 검색 적재, 후속 요청 schema, 실제 조회, legacy manage mutation 비노출, foreign/disabled snapshot 거부. 이 직접 경로만으로 provider/worker 완료를 주장하지 않는다. |
| Canonical native system | 기존 Lumen `docker-compose.system.yml`에 소유한 fake IAM/provider/Afterglow bridge overlay를 적용했다. Packaged API/worker·migration/bootstrap·MariaDB/Redis/SSE에서13checks 통과. Provider3rounds가 initial3schemas→한국어 discovery·VM schema 추가→SDK VM 결과·최종 응답을 확인했고 소유 grant를204철회했다. |
| Native durable 경합 회귀 | 실제 system 실행에서 성공한 tool result가 후속 producer turn에 잘못 붙어 run이 실패하는 경합을 발견했다. 발행 시점의 private originating ordinal로 고정했다. Native SQL 회귀5passed는 첫 model-response 소비를 다음 provider round 이후까지 지연하여 tool 결과·assistant 메시지·완료 턴의 소유권을 검증한다. |
| 실제 compiled 채팅 | 사용자 새 채팅 버튼→한국어 입력→conversation201→completion202→native SSE200→run `completed`. 실제 native event journal의 `list_available_tools`와 `afterglow_vm_list` 모두completed이며 합성 VM 응답이 화면에 표시됐다. Browser session/permissions와 BFF→native mapping만 소유 QA fixture이며 운영 BFF/auth 검증으로 대체하지 않는다. |
| Context inspector | Light/dark ×390/768/1440px 총6조건에서 panel viewport 안·가로 overflow0·최초3schemas를 확인했다. Preview와 실제 initial provider schema 집합이 같고 discovery-loaded schema는 후속 요청에만 추가된다. 최초3개만 표시되는 상태는 lazy-load 정책이며 전체 MCP 미연결의 증거가 아니다. |
| 이미지·architecture | Canonical Dockerfile의 Afterglow backend 및 Lumen API/worker3targets를 linux/arm64·linux/amd64로 빌드했다. 각6개 packaged 실행이 aarch64/x86_64·exit0과 host/image source SHA parity를 확인했다. Native system workload는 arm64이며 amd64는 Docker Desktop emulation의 실행/parity 검증이다. |
| Lumen gate | Service contract3125passed/320deselected/21dependency warnings, SDK128passed, root/SDK Ruff 통과. 초기 cache-billing fixture3failure는 current event-bound ordinal 계약에 맞춰 이관한 뒤 통과했으며 실패 receipt를 보존했다. |
| 최종 Afterglow full gate | 격리 snapshot의 `npm run test:gate`가 docs guard→orchestration/installer→unit→contract→functional→Ruff check/format까지 통과했다. Backend5769passed, frontend350files/3300passed+runner9, contract174passed, MariaDB/PostgreSQL/Redis functional150passed/27deselected, Ruff586files. PowerShell36skip과 기존 범위 밖 Svelte warning3개를 유지한다. |

Scope는 Afterglow base `aac6b9c5dc3e53fc3e430ca9ed96c30cacdbdb1e`+owned source/tests6개 및 Lumen base `24e6ae46e7673772b7ef4b2f176b1802258c4235`+owned source/tests10개다. 최종 격리 architecture working/staged guard는 Afterglow `41ee11098dcdfe9a68f0f1fd061754317eed50ffdb739da85622ed002e3a1b9d`/2615files와 Lumen `0dfe7c4a5c333f97d4ea839052c561029f9dcd62b0a1d1ef6943019ec899fd3d`/422files로 통과했다. Gate 당시 working digest `0766c7e047e2fe77465433fb1b1e695649a7b9eb9b4be835429a00ec9214b23a`/2616files에는 clone-only root `node_modules` runtime symlink1개가 포함돼 있었고 staged guard에서 그 차이를 드러냈다. Clone `.git/info/exclude`에 이 alias만 분리해 재stamp했으며 product source·suite·dependencies는 변경하지 않았다. 공유 index/review marker·private 설정과 무관한 동시 변경을 보존했고 shared 전체 WIP의 integration 승인이 아니다.

Raw evidence는 `/Users/pieroot/.local/share/afterglow-proofs/afterglow-mcp-repair-xgt8rj01/`의 `verification.json`, `cloud-runtime.json`, `native-runtime.json`, `system-arm64/system-native.json`, `browser-native-events.json`, `browser-context-matrix.json`과 WebP다. 초기 clone editable-venv/REAL_REDIS 환경 혼입의47failed/5722passed, dev-extra 누락, generated SvelteKit tsconfig 누락의 frontend startup 실패는 setup 실패로 분리해 보존한다. Private TOML·suite·제품 권한 계약을 바꿔 성공으로 만들지 않았다. Gbrain CLI가 PATH에 없어 sync/CLAUDE 변경은 하지 않았다. 운영 배포·production schema/원래 key·mixed-version/writer 호환성·live IAM/cloud 쓰기·paid inference는 수행하지 않았다.

최종 gate는 `AFTERGLOW_TEST_DATABASE_URL`·`AFTERGLOW_TEST_CHECKPOINTER_POSTGRES_URL`과 소유 Redis DB6를 명시했다. Unit에는 global `AFTERGLOW_TEST_REAL_REDIS`를 제거하고 기존 functional runner만 real-Redis flag를 설정했다. 독립 clone venv는 frozen lock의 dev extra를 설치했으며 frontend는 기존 `svelte-kit sync`로 generated tsconfig를 준비했다. Suite 범위나 consumer assertion을 줄이지 않았다. 최종 native system·UI grant204철회와 브라우저 release 뒤 소유 Compose만 `down`하며 volume 삭제/prune·기존 개발 서비스 중단은 하지 않는다.

정제된 최종 수용 증거는 [archived verification](../openspec/changes/archive/2026-10-13-repair-mcp-authorization-tool-discovery/evidence/verification.json)다. 소유 native10개·functional datastore3개 container와 임시 HTTP server는 종료·제거했고 browser를 release했으며 throwaway fixture14개를 제거했다. Gate 전체 stdout은 private proof의 `afterglow-full-gate.log`로 보존한다. 원래 공유 Compose/volume·설정·index와 운영 상태는 변경하지 않았고 stage/commit/push는 소유 clone의 architecture 검증용 index 이외에는 수행하지 않았다.


## 다중 컨트롤러 볼륨 자동 백업 분배 검증 (2026-10-14, local-only)

`distribute-volume-backup-scheduler`는 모든 backend process가 반복하던 정책 전체 스캔을 Redis leader 하나로 모으고 due/active 작업을 살아 있는 process에 분배한다. 운영 Kolla·Redis/Sentinel·Keystone·Cinder·private 설정·shared index/review marker·release/deployment는 변경하지 않았다. 검사는 current public working source(동시 public WIP 포함)를 frozen local clone에 복사해 수행했고 private `afterglow.conf`·env 입력은 복사하지 않았다.

| 실행 경계 | 관측 결과 |
|---|---|
| 독립 3 process + Redis7 | 실제 `scheduler_loop` process3개, Redis server TIME·45초 member/leader·10초 heartbeat·15초 poll·90초 volume lease를 사용했다. Idle18초 동안 scan worker1·SDK connection0. 9개 due 정책은3/3/3으로 제출·완료됐다. Leader hard kill49.97초 뒤 successor가 선출되고 남은2개 process가6개를3/3으로 처리했다. |
| 접수 후 worker crash | Provider가 POST를 접수한 뒤 응답을 막고 담당 process를 hard kill했다. Journal `unknown`·lease TTL90에서90.03초 뒤 다른 process가 기존 백업 ID를 `available`로 확인했고 그 볼륨의 POST는1개였다. 재시작한3 process는 새 identity로 참여해 3개를1/1/1로 처리했다. |
| Installed openstacksdk3.3.0 HTTP | Loopback Cinder에 대한 실제 SDK 직렬화(`incremental`/`force`)·version discovery·GET/POST/DELETE 164요청. 총 POST20, 오래된 관리 백업9개만 보존 정리하고 수동 백업은 보존했다. Private config source0. Provider·project identity·data copy는 합성이다. |
| Failed-before/passed-after | 접수 후 응답 유실은 수정 전 SDK connection retry로 POST2, 수정 후 POST1→`unknown`→`accepted-1` 확인이다. 빠른 worker의 조기 완료 후 재배정은 수정 전 native4/3/2·consumer worker-a4/worker-b2, 수정 후 native3/3/3·consumer3/3/3이다. |
| Consumer regression | 기본 fakeredis와 opt-in real Redis(DB1)에서 dispatcher·distributed·auto-backup·native HTTP105통과. 최종 storage target backend751·frontend14files/142통과. |
| Style | 소유 Python6files의 Ruff format/check가 통과했다. `app/main.py`는 최종 scoped check/format에서 제외했으며 동시 WIP traffic analytics/host-observation import·validation 줄의 차이는 수정하지 않았다. |
| Cross-cutting backend unit | 최종69file public-source refresh 이전 snapshot의 unit 전체는6271 passed/91 skipped/25 failed/22 errors였다. 최종 stamped snapshot의 전체 unit 수용 증거로 승격하지 않는다. 실패·오류는 동시 WIP인 `test_host_health.py`, `test_host_observer.py`, `test_admin_credentials.py`, `test_login_monitoring.py`와 이전 receipt에도 있던 `test_instance_storage_delete.py`11건뿐이며 백업·scheduler suite에는 없다. Refresh 이후에는 storage target과 실제 Redis consumer만 다시 검증했다. 전체 `test:gate`는 실행·주장하지 않는다. |
| Architecture | Frozen current public source(동시 public WIP 포함, private 입력 제외)의 격리 clone에서 working과 임시 index staged guard가 `source_sha256=23f479784339659cda29f83dff95d1f35a815971ba0c5c928f876d7113935da9`/2728files로 통과했다. 공유 index와 review marker는 보존했다. |

중간 storage target의 2 failures(749 passed)는 두 consumer가 고정 2 round 뒤 독립 실행 loop의 완료/인계 전이를 가정한 시험 race였다. Assertion 범위를 줄이지 않고 관측 가능한 상태 전이까지 bounded round를 반복하도록 바꾼 뒤 최종 snapshot의 storage target이 통과했다. 실제 native imbalance(4/3/2) receipt는 `native-ha-before.json`, `native-http-before.json`으로 보존했다. 응답 유실의 POST2는 수정 전 native HTTP consumer 실패로 관측했다.

Raw evidence는 `/Users/pieroot/.local/share/afterglow-proofs/afterglow-backup-ha-82g70zwq/`의 `native-ha.json`, `native-http.json`, process별 log다. 정제된 수용 증거는 [archived verification](../openspec/changes/archive/2026-10-13-distribute-volume-backup-scheduler/evidence/verification.json)다. Hard kill한 process의 SDK connection close는 주장하지 않는다. 운영 controller·Redis/Sentinel failover·Keystone 인증·live Cinder data copy/restore·혼합 버전 rolling upgrade는 실행하지 않았다.


## Calendar 볼륨 자동 백업 검증 (2026-10-13, local-only)

`enable-scheduled-volume-backups`는 기존 desktop blind toggle/즉시 첫 사이클/1시간 경과 heuristic을 보이는 policy editor와 실제 calendar dispatcher로 cutover한다. 운영 IAM·Cinder·Redis/Compose·private 설정·shared index·release/deployment는 변경하지 않았다. 검사에는 current public working source의 frozen local dev clone을 사용했으며 private `afterglow.conf`를 복사하거나 고치지 않았다.

| 실제 실행 경계 | 관측 결과 |
|---|---|
| Current backend consumer selector | auto-backup·backup API·ownership115통과, 이후 warm cached inventory 회귀를 추가해 수정 전 실패/수정 후 통과. Native reader403, source/force400·validation422·exact project owner·pause/resume/0tier·revision/lease/pending/retention·cancelled factory close 포함. |
| 최종 storage target | backend709통과, frontend14files/142통과. PolicyUI11사례에 calendar save/backend next·deep link·source별 force·manual consent 분리·pause/resume·read-only·실패 draft·ABA/late result·invalid/orphan removal을 포함한다. Registry에 backup route regressions·shared detail·mock transport를 연결했다. |
| Real Redis7 + installed openstacksdk loopback | Injected aware clock8lifecycle 사례: June1 Monday daily/weekly/monthly 충돌의8동시 replica에서1forced full POST, 접수creating에서DELETE0, available 뒤old monthly만 삭제; manual/foreign source/project/dependent/incremental/pending 보존, paused zero connection0, source/force skip, available forcefalse, pause 중 완료 관측, failed 새 백업에서lastgood 유지,503unknown2일후 재발행0, legacy 단일 정규화. |
| 실제 native FastAPI socket HTTP |7사례: authoritative source404 policy 표시·원문 불변·정책만204제거, source503/403·foreign/missing owner에서503/403/404제거 거부·설정 유지, 원래 identity가 foreign인 malformed policy404/원문 보존. 따뜻한 backup list `[] → creating → available`를 실제 SDK/Redis/HTTP로 확인. Identity/activity sink/Cinder는 합성. |
| 실제 UTC 분 경계 timer | API 저장22:23UTC와 compiled UI 저장22:53UTC 두 실행. 저장 직후provider POST0, 실제 `main._auto_backup_loop`의15초 dispatcher에서각1POST/force=true/full, 이후fixture provider available 관측과 다음 날next 확인. UI 실행은 월/주/일 충돌의monthly 단일 백업이며 데이터 복사·운영 복원 proof가 아니다. |
| 실제 main startup/shutdown | `start_background_workers`가 실제 task를 시작했다. SDK connection factory thread를 막은 채 shutdown하면 task cancel/await·lease를 유지하며, 반환된 installed SDK connection1개를1회close하고lease 해제·taskNone/cancelled·provider mutation0 확인. |
| Compiled adapter-node + Chromium | ko/en/ja/zh-CN × light/dark ×320/390/767/768/1023/1024/1440px56조건의 policy/editor112surfaces. 가로 overflow0, viewport-bounded modal과 내부 scroll 모든 입력·동의·취소/저장 접근,44px 작업·실제 theme/locale·설명 연결 확인. Mobile list와 직접 detail 메뉴/desktop 설정 링크, native save/edit/pause/resume/remove·백업 보존, reader4controls disabled/API403·다른project policy비노출·load503이empty아님·save503draft보존도 관측했다. Invalid/orphan UI projection은 별도 intercepted200fixture; 실제 absent API 증거와 구분한다. |
| Build/catalog/compiler | Current-source production build exit0. i18n37namespaces/9504messages errors0/warnings0,994files hard-coded Korean0. Svelte check는 이번 volume policy diagnostics0이며 범위 밖 database `PageState.instanceId` 오류1와 기존 warning3를 보고했다. 그 unrelated source를 변경하지 않았다. |

따뜻한 목록이 실제 백업을 즉시 나타내지 않는 결함은 consumer 회귀의 수정 전 `[]` 응답으로 재현했다. 자동 제출·완료/실패·보존 삭제에서도 기존 backup cache invalidation/mutation-count를 적용해 수정 후와 nativeHTTP가 통과했다. Source 문구/invalid label 개수만 고정하던 새 incidental assertion은 삭제하고 실제 orphan 표시·수정/재개 차단·제거/잔여 정책 보존 검사는 유지했다.

Owned proof root: `/Users/pieroot/.local/share/afterglow-proofs/afterglow-scheduled-backup-izjvbzfc/`. `native-cases.json`, `native-api-cases.json`, `startup-shutdown.json`, `calendar-library.json`, `wall-clock-completed.json`, `compiled-cycle/`, `compiled-matrix.json`, `compiled-actions.json`, `compiled-authority.json`, `compiled-save-error.json`, `compiled-remove-and-recovery.json`와 실제 mobile/desktop light/dark PNG에 보존했다. Synthetic origin57761/57762와 전용 Redis57760만 사용했다.

검증 중 scratch native API observer가 서버 loop의 Redis client를 재사용해 cross-loop 오류를 냈으며 observer 전용 client로 수정했다. 초기 frontend run은 생성 `.svelte-kit/tsconfig.json` 전의 dependency optimizer 오류였다. Policy 테스트의 label 개수 assertion, theme 변경 정착 전 측정, 숨긴 desktop 링크를 첫 matching selector로 클릭, save 완료 전 GET 및 잘못된 예상 copy는 acceptance에서 제외하고 실제 정착/visible pointer/완료/catalog 의미를 관측했다. QA를 위해 application auth/소유권/오류를 완화하지 않았다.

미검증: 실제 Keystone 인증·권한, 운영 Cinder backup service/저장소·I/O·쓰는 게스트/DB 일관성·복원, Safari/Firefox, 운영 rollout. Force와available/API성공을 복원 보장으로 승격하지 않는다. Gbrain CLI와 detection script가 없어 sync/agent 안내 변경은 수행하지 않았다. Commit/stage/push/release·운영 배포는 하지 않았다.

후속 qualification: frozen public working source의 전체 `npm run test:gate`는 orchestration175·Kolla27·native-image-ref11·CLI20pass/36skip 뒤 backend unit에서6003pass/91skip/11fail로 중단됐다. 모두 수정하지 않은 `test_instance_storage_delete.py`의 단건/bulk managed-grant 삭제 경로이며, stack의 `layer_consume_resources.lookup_for_server`가 `block consumer tracking database unavailable`로 거부하고 관련 상태 assertion도 실패했다. 동시 Palimpsest block DB tracking source/tests는 자동 백업 범위 밖이므로 수정·축소·skip하거나 실패를 재실행해 숨기지 않았다. Full gate 통과로 보고하지 않는다.

중단된 나머지 canonical 단계는 별도 완료했다: 전체 frontend351files/3317tests와 file-log9pass, BFF contracts174pass, 전용 tmpfs MariaDB/PostgreSQL/Redis functional154pass/27deselected; disposable project는 자동 teardown되었다. 전체 Ruff lint0오류이나 format check는 범위 밖7files(`compute/instances.py`, `union/layer_ops.py`, `dockerfile_import.py`, `layer_build.py`, `test_dockerfile_import.py`, `test_palimpsest_dockerfile.py`, `test_resource_policies.py`)에서 실패했다. 이번 backend source/tests7files의 Ruff check/format은 모두 통과했다. 전용 real Redis로 lease TTL을1초로 축소한1.2초 긴 제출·두 replica durable claim·blocked factory cancellation3consumer 회귀도 통과했다.

같은 frozen source에서 working stamp/check와 alternate local clone index의 `--staged`가 같은 `source_sha256=7ac9fb728c75b6a25b5682d0ed2e2785784f609f3be16d51d2ee87b4c74036b6`,source2635files를 검증했다. Feature source34files는 공유 working bytes와 SHA-256 parity가 일치하며, private 설정·shared index/review marker는 보존했다. 이 digest는 frozen concurrent public WIP까지 포함한 snapshot freshness이며 위 unit/format 실패를 통과로 바꾸지 않는다. Compiled public `/docs/cinder`4언어와 tablet SlidePanel→정책 deep link·available 원본 forcefalse/weekly-only(0 daily/monthly) 저장도 추가 관측했다. Owned browser/API/UI/Redis를 종료했고 API connection124open/124close·timer stopped를 확인했다. Scripts/profile/temporary index/source clone은 raw logs·receipts·pixels를 durable proof root에 보존한 뒤 제거했다. Rapid OpenSpec은 `openspec/changes/archive/2026-10-12-enable-scheduled-volume-backups/`에 완료 archive했다.



## Lumen 밝은 테마·작성창·사이드바 전환 수정 검증 (2026-10-13, local-only)

`repair-chat-theme-composer-navigation`은 밝은 채팅의 표면/박스 경계, 새 초안48rem→긴 초안/기존 대화80rem 작성창, obsolete 탐색 막대 제거와 같은 ChatPanel 내 shallow 프로젝트 전환을 수정한다. Backend/native API·권한·DB·운영 설정은 변경하지 않는다. 기존 palette/dark 선언과 full-bleed workspace를 보존한다.

| 실제 실행 | 관측 결과 |
|---|---|
| 최종 adapter-node build + 실제 Chromium | ko/en/ja/zh-CN × light/dark ×320/390/767/768/1023/1024/1440/2560px64조건. 각 조건에서 빈 초안·짧은 초안·긴 초안·명시적3줄·저장 기록5상태를 확인했다. 가로 overflow0, transcript/composer 중심 정렬, 빈 작성창 inner736px·확장/저장 inner1248px 상한. 최종 textarea 최소 높이26px이며3줄 복귀70px. |
| 실제 프로젝트·기록 왕복 | 포인터로4회 왕복 시 추가 대화 목록/메시지 조회0, 같은 editor/transcript/sidebar DOM과 초안 보존. 안정된 기록 viewport의 scrollTop3510을4회 모두 유지했다. 프로젝트 index/detail·Back/Forward·직접 상세URL과 compact Escape의 보이는 trigger focus 복원을 확인했다. |
| 실제 HTTP fixture의 bounded history | opaque before:121→before:81→before:41→after:120 cursor를 그대로 전달.4page에서 반대 edge만 제거하여120messages를 유지하고 다시 최신 edge로 돌아왔다. Permanent 회귀는 pending중 중복 scroll 억제·visible anchor 보존·409 한 번 복구도 검증한다. |
| 관련 컴포넌트 회귀 | `ChatPanel`, `ChatWindow`, `ChatProjectsView`, `ChatPanelDelete`, `ChatInput`, `ChatBubble`6files/91tests 통과. 디자인 target27files/138tests 통과. |
| Build·현지화 | production build exit0. i18n37namespaces/9503messages·errors0/warnings0, scan994files/hard-coded Korean0. |
| 공유 checkout의 범위 밖 검사 | 전체 frontend349files/3305tests는 통과했지만 동시 volume-backup2suites가 `$app/state` alias 미해결로 수집 실패했다. 최종 Svelte check는 chat 오류0, volume backup catalog typing3개·database `PageState.instanceId`1개의 범위 밖 오류와 기존 warning3개를 보고했다. |
| Backend/gate 한계 | named `chat design`은 private TOML line10,column9 파싱 오류로 backend conftest 전에 중단됐다. 해당 private 설정과 별도 volume/database 작업은 수정하지 않았다. 전체 `npm run test:gate`·live identity/provider·운영 배포·Safari/Firefox는 검증하지 않았다. commit/push/release도 수행하지 않는다. |

Raw browser JSON·HTTP paths·최종 light/dark 화면은 `/Users/pieroot/.local/share/afterglow-proofs/chat-repair-20261013/`의 `final-compiled-matrix.json`, `navigation.json`, `final-navigation.json`, `pagination.json`, `project-routes.json`, `composer-reveal.json`, `multiline-reveal.json`과 `final-*.png`에 보존한다. Matrix는 DOM activation이며 실제 pointer/keyboard 전환은 별도 smoke다. Runtime/API·identity 응답은 격리 loopback fixture이고 실제 provider 실행·OpenStack mutation은 없다. 첫 source QA의 소실된 browser routes/CORS, assertion의 cache query·scrollbar 가용 폭·비동기 resize 정착 전 측정은 acceptance에서 제외했다. 실제 최종 화면에서 확인한 숨김 editor0px 측정은 width/reveal observer로 수정한 뒤 위64조건을 다시 실행했다.

공유 source/index와 기존 architecture review marker를 덮어쓰지 않고 HEAD+chat scope source19files만 별도 local dev clone에 overlay하여 guard를 stamp/`--staged`로 통과했다. Digest는 `05b00ffced76778091de607567cc679cd12e690e0760192c4baa53db97b21fa6`,source2,615files다. 이 scoped guard는 동시 Palimpsest/MCP/volume/database WIP 전체의 검토·게이트 통과가 아니다.
## 1.30.15 Stampede 기본 활성화 생성 화면 운영 검증 (2026-10-13)

`default-on-stampede-client`는 Drover `v0.4.13`의 생략=활성 계약에 맞춰 클러스터·노드그룹 생성 화면의 Stampede 스위치를 기본으로 켜고, 클러스터 생성 요청에는 사용자의 선택을 항상 boolean으로 보낸다. Frontend 전용 patch이며 DB migration·backend API·설정 변경은 없다. `v1.30.14..v1.30.15`의 비문서 변경은 frontend source/test/i18n과 version manifest·lock·Helm chart version뿐이다.

- **Source/CI:** `6deffce1a81f44279dad7600ea9c6cdc032f54a3`, 불변 annotated tag `v1.30.15`. 커밋 전 `npm run test:gate`가 rc0였다(backend unit5795, frontend3305/351 files, contract174, functional128). `i18n:check`/`i18n:scan`과 svelte check는 error0이다(기존 warning3). 정확한 SHA의 [dev Docker CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38390146794)(layered tests 포함), [tag Docker CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38390970773), [Helm Chart Release](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38390970449)가 성공했다.
- **Published image:** 아래 세 digest는 amd64+attestation index다. 세 image를 `--network none`으로 실제 실행해 version `1.30.15`, `x86_64`/`x64`, OCI revision `6deffce1`을 확인했다.
  - API `sha256:154ed3006a3887adfb8b408628aaf53d0ee1fd19400f2e1d9ac259399a1c75c8`
  - frontend `sha256:920567335691bb9d88cab150eee9da48dc7d77fdd48cf9afb423f23ad01c36e4`
  - worker `sha256:defb7543749ba0574ce354f9623e5307c7e86f28db806a9f537c801dfeb3507c`
- **Kolla rollout:** 보호 backup `/etc/kolla/.afterglow-rollout-backups/1.30.15/`에 globals 원본(SHA256 `c428f5fa…`)을 보존하고 `afterglow_image_tag`와 세 image ref만 바꿨다(새 SHA256 `4157155e…`). Canonical `/etc/kolla/multinode` `--tags afterglow`의 prechecks·genconfig·pull과 controller1→2→3 reconfigure가 모두 rc0였다.
  - 세 controller의 API/frontend/worker9개가 위 digest·revision으로 재생성됐고 restart는 0이다. API/frontend6개는 healthy이며 Notion worker에는 Docker healthcheck가 없다.
  - 기존 비대상 running container241/233/150개의 ID·image·시작 시각·restart가 그대로였다.
  - 공개 `/health`·`/api/v1/health`는 200이었다. Receipt `rollout-receipt.json`의 시각은 `2026-10-13T14:49:02Z`다.
- **실제 운영 화면:** 새 profile의 headless Chrome for Testing 150에서 `test` 계정으로 실제 로그인해 확인했다.
  - 두 창 모두 열자마자 `aria-checked=true`였고 새 안내 문구가 표시됐다. 대상은 클러스터 생성 창의 `Stampede 모드`와, ACTIVE 수락 클러스터 `dc52541f-4258-41dd-b6f4-8fcfa017808c` 노드그룹 추가 창의 `Stampede 오토스케일`(min0/max5)이다.
  - 네 번의 생성 POST는 browser 안에서 본문만 기록하고 503으로 응답해 서버로 보내지 않았다. 기록한 본문은 다음과 같다.
    - 클러스터 기본값: `{"name":"qa-intercept-13015-on","agent_count":1,"os_type":"ubuntu","stampede_enabled":true}`
    - 다시 연 클러스터 창에서 스위치를 끔: `{"name":"qa-intercept-13015-off","agent_count":1,"os_type":"ubuntu","stampede_enabled":false}`
    - 노드그룹 기본값(GPU flavor 선택): `{"name":"qa-ng-13015-on","role":"agent","node_count":0,"flavor_id":"fe5a5a4c-a568-481d-982b-469967f64808","stampede_enabled":true,"min_size":0,"max_size":5}`
    - 다시 연 노드그룹 창에서 스위치를 끔: `{"name":"qa-ng-13015-off","role":"agent","node_count":0,"flavor_id":null,"stampede_enabled":false}`
  - 이후 Drover 목록에 `qa-intercept*` cluster는 없었고, 수락 클러스터의 nodegroup은 `default-server`/`default-agent`/`gpu-accel-0413`뿐이었다.
  - 화면 캡처는 `~/.local/share/afterglow-proofs/afterglow-13015-qa-3fa2_mr_/`의 `cluster-create-default-on.webp`, `nodegroup-create-default-on.webp`다.
  - 이 browser 검증은 UI 기본값과 요청 본문의 증거이며, UI로 실제 자원을 생성했다는 증거는 아니다.
- **서버 기본값과 GPU 실행:** 운영 Drover `v0.4.13`에서 다음을 확인했다.
  - `stampede_enabled`를 생략하면 cluster는 `true`, default 그룹은 `false`이고, GPU flavor nodegroup은 `true`였다.
  - `accelerator: RTX3060LHR` nodeSelector와 `nvidia.com/gpu: 1` Pod로 GPU가 0→1로 증설됐고, 자동 label·Running nvidia-smi·Operation SUCCEEDED를 확인했다.
  - 이후 cluster/VM/volume을 정리하고 임시 flavor access를 제거했다.
  - 상세 기록과 taint 없는 GPU worker의 축소 차단 경계는 Drover [live acceptance](https://github.com/openstack-afterglow/drover/blob/dev/docs/release-0.4.0.md#live-default-on-and-accelerator-acceptance)에 있다.
- **문서 정정:** GPU Pod toleration만 추가하고 GPU nodegroup에 `NoSchedule` taint를 적용하라는 앞선 권고는 철회한다. 제공되는 Cinder/Manila/NFS CSI node DaemonSet에는 해당 사용자 taint toleration이 없어 CSI 배치·mount가 막힐 수 있다. CPU/control-plane으로 시스템 workload를 배치하는 것과 CSI toleration·실제 mount 확인은 별도 전제다. 초기 agent flavor metadata-error 경로는 일반 agent로 진행할 수 있으며, 이번 live 검증은 명시적 GPU nodegroup의 Stampede 증설뿐이다. Drover standalone Pod 예제의 CUDA registry·명령을 실제 Deployment에서 사용한 값으로 맞췄으나 standalone Pod manifest 자체의 live 실행 증거는 아니다. 코드·CSI template·taint·운영 환경은 추가로 변경하지 않았다.

OpenSpec 기록은 `openspec/changes/archive/2026-10-13-default-on-stampede-client/`에 있다. 공개 증거에는 비밀·token·kubeconfig를 넣지 않는다.

## 1.30.14 운영 기준 통합 검증 (2026-10-13)

이 릴리스는 운영 backend `v1.30.13`/`25f3557f`와 승인된 Afterglow commit `aac6b9c5`를 격리 local `dev`에서 정상 merge한 `3572268ab3ccd27daea5a134b3c46ba8f1c9dc29`다. 시작 시 세 controller의 frontend/Notion worker는 `v1.30.12`/`9cbfecad`였다. 미완료 Palimpsest/block layer·SQL088/089·sibling/operator dependency 변경과 공유 private source/index는 제외·보존한다. 실제 root/operator globals가 다르므로 authoritative `/etc/kolla/globals.d/90-openstack-afterglow-globals.yml`의 실행 중 digest를 기준으로 했다.

- 네 GPU admission source 파일과 두 핵심 test 파일은 배포된 hotfix와 동일하며 resilience 회귀는 dev assertion과 explicit target 계약을 함께 보존한다. 정적 reviewer가 merge-introduced P1/P2 없음으로 판정했다.
- Canonical `uv sync --frozen --extra dev` 후 `AFTERGLOW_TEST_PROJECT_NAME=afterglow-prod-release-v13014 npm run test:gate` exit0: backend **5795**, frontend **3300**/350files, contract **174**, disposable MariaDB/PostgreSQL/Redis functional **128**(23deselected), Ruff586files. PowerShell36개는 runtime 부재로 skip이다. 초기 pytest 미설치 실패와 잘못 지정한 capacity selector 실패는 통과 결과가 아니다.
- 정확한 admission/quota/resilience/flavor eligibility/capacity/storage-delete selector6개 **105passed**. Frontend check2370files **0errors/3기존warnings**, frozen Vite8.2.2 production build exit0. 실제 compiled Node/Chromium의4locales×2themes×390/1440px **16조건**에서 HTML locale·실제 theme class·수평 overflow0·pageerror0을 확인했다.
- Working architecture source `22c8c7f1f76dc459b1a293790a71b727eac89ffd6f473cb5edd10b9ab2ab2280`/2615files. Gate의 source snapshot과 rollout/guest·paid-provider acceptance를 구분한다.
- 시작 시 운영 read-only MariaDB10.11.19 evidence는90tables·utf8mb3_general_ci·migration ledger 없음이며 MCP grant의4컬럼과 nullable expiry가 없었다. 기존 empty project-credential child table의 PK/unique/cascade FK를 유지했다. SQL084–087만 명시 적용했고 historical073–075 DROP/DELETE 또는 없는 ledger 전체 replay는 하지 않았다.
- 초기 legacy MCP invocation101개(98success/3failed)는 모두 **idempotency_key=NULL인 read**였다. Cutover 직전 API/Notion worker6개를 모두 멈춘 뒤 keyed mutation·unresolved keyed mutation·pending credential grant가 각각0임을 다시 확인했다. Old/new argument-hash 차이는 합성 keyed row에서 별도 평가했으며 기존 ledger를 재작성하지 않았다.
- 보호 hot DB backup은90table/781732SQLbytes로 gzip·GPG decrypt roundtrip을 통과했다. Quiesced cold SQL은 실제 network-none/tmpfs clone에서90table/2285rows로 복원했고, SQL084–087을 두 번 적용하여 idempotence·constraint·bounded legacy read/write·새 scope/NULL expiry/동의/관측 필드와 원래 ciphertext 호환성을 확인한 뒤 pristine restore도 통과했다. 초기 hot decryption11회에는 합성 fixture가 포함된다. Cold runtime의 별도 counter는 fixture G를 명시 제외하여 원래 ciphertext10개를 기록했다. 새 reader/old schema1054와 old resolver/NULL expiry의 `AttributeError`는 실제로 관측한 비호환 경계이며 raw `grant_public_view`의 NULL 복사와 구분한다. 외부 provider dispatch0, 운영 data를 합성 fixture로 수정하지 않았다.
- Companion Redis DB5의 cold encrypted snapshot129keys 중128surviving keys를 격리 clone에 복원하고 이미 만료된1개는 건너뛰었다. Logical values와 TTL을 보존하며 만료 key를 되살리지 않았다. 원래 key/config/inventory와 operator·controller recovery archives, 독립0700 key escrow를 유지했다.
- 정확한 SHA의 [dev CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38290158866), [tag Docker CI](https://github.com/openstack-afterglow/openstack-afterglow/actions/runs/38290930189)와 Helm 발행이 성공한 뒤 불변 [v1.30.14](https://github.com/openstack-afterglow/openstack-afterglow/releases/tag/v1.30.14)를 배포했다. API/frontend/worker의 version/latest digest가 일치했고 published amd64 image 세 개를 실제 실행하여 version/revision을 확인했다. Source/local gate와 운영 acceptance는 별개다.
- Canonical `/etc/kolla/multinode`의 Afterglow-only pull·prechecks·genconfig와 controller1→2→3 reconfigure가 모두 rc0/failed0/unreachable0이었다. 운영 SQL084–087의9개 statement 직후90tables/2285rows·legacy grant fields·모든 table row count가 보존됐고 권한/동의 backfill은 없었다. 세 controller의 API/frontend/worker9개는 위 revision과 immutable digest로 실행됐고 API/frontend6개는 healthy였다. Notion worker에는 Docker healthcheck가 없다.
- Post-rollout19:19:11–19:24:24UTC의6회 관측에서9개 컨테이너는 running/restart0, Docker stdout/stderr ERROR/CRITICAL/Traceback/ProgrammingError marker0이었다. 원래 DB/Redis 목적지·master/Notion key·session secret은 API/worker6개에서 escrow와 일치했다. 기존 비대상 container624개(241/233/150)의 ID·image ID·start/status/restarts를 보존했다. Docker 출력 확인은 application-file 전체나 장시간 traffic/error-rate 감시, Notion 외부 동기화 완료의 증거가 아니다.
- 실제 native GPU admission은 DB policy service project와 별도 target `test` UUID, 기존 private flavor의 native ACL·실측 `RTX3060LHR` quota(-1)/usage0를 사용했다. 세 controller의 실제 healthcheck listener18020과 공개 HTTPS 모두 **200/`gpu_required=true`**였다. Missing/wrong token401, 잘못된 project/flavor400, 누락/잘못된 ID type422, 기존 unshared private flavor400을 확인했고 quota/policy/flavor access·cloud resource 변경0이다. 첫 tenant rescope는 `Unauthorized`로 실패했고 독립 test-tenant 인증/usage 교차 검증은 미검증으로 남긴다. 잘못 읽은 Settings port8020의 `ConnectError` probe도 실패 기록으로 보존하며 실제 Docker healthcheck에서18020을 확정한 뒤 HTTP를 실행했다. IAM이나 application config를 바꾸지 않았다.
- 공개 health·site config·`/.well-known/oauth-protected-resource/mcp`200, 무인증 instances/MCP 관리401을 확인했다. 실제 mounted MCP capabilities와 현재-project Nova overview 조회도 성공했다. 격리 Chromium에서 모의 intercept/identity 없이 설정된 service account로 실제 first-party login→dashboard→account와 MCP personal/OAuth/project read200·no-store를 확인했다. 개인 토큰의 만료 없음은 **draft 선택만** 했고 발급/회수하지 않았다. 1440/390px의 overflow0·application pageerror0과 screenshots를 보존했다. 독립 일반 tenant/모든 locale·theme persistence·새 OAuth 발급·guest/RDP·유료 model/provider 전체 acceptance로 확대하지 않는다.
- 새 MCP consumer 재개 뒤에는 image-only downgrade하지 않는다. SQL084–087 이후 새 형태의 durable state는 이전 reader/cleanup과 호환되지 않으므로 recover-forward 또는 DB/cloud state를 포함한 별도 recovery 평가가 필요하다. 원래 비밀·volume·형제 이미지·operator dependency는 보존했고 `main` merge나 기존 tag 이동은 하지 않았다.
- Archive 뒤 동일 source SHA/2615files의 전체 `test:gate`를 다시 통과했고 disposable functional containers/network는 정리됐다. 실제 검증 로그인은 확인 dialog를 거쳐 logout했고 소유 Chromium·compiled frontend process를 종료했다. 최종 문서/receipt만 dev로 push하며 발행된 tag와 배포 source revision은 이동하지 않는다.


Release evidence는 `openspec/changes/archive/2026-10-12-release-afterglow-1-30-14/evidence/`의 `local-verification.json`(pre-publication), `cold-recovery.json`(격리 restore), `production-verification.json`(migration/Kolla/native HTTP/운영 browser·한계)로 구분한다. Archive 날짜는 CLI의 UTC 기준이다. Durable raw receipts와 screenshots는 `~/.local/share/afterglow-proofs/afterglow-prod-rollout-20261013-26tEUU/`, encrypted SQL/config/Redis backups와 operator receipts는 보호된 `/etc/kolla/.afterglow-rollout-backups/1.30.14/`, 원래 key·backup passphrase escrow는 독립0700 `/home/pieroot/.local/share/afterglow-release-keys/1.30.14/`에 보존한다. 비밀·SQL row body·bearer·원래 key를 public evidence에 넣지 않는다.

## Afterglow 부분 커밋 통합 검증 (2026-10-13, local-only)

사용자의 전체 커밋 후속 지시에 따라 Palimpsest·블록 레이어 구현은 제외하고 현재 Afterglow 부분을 별도 public-source checkout/index에서 검증했다. Block API·consume/build/import, ORM와 background/instance cleanup hooks, Glance/Cinder/Neutron block 전용 helper, migrations088/089·manifest 항목, operator Palimpsest lock과 전용 tests/docs는 작업 트리에 보존한다. 공유 private 설정·원래 index·개발 Compose/volume·운영 자원은 변경하지 않는다. 아래 결과는 과거 scope receipt의 재사용이 아니라 이번 부분 snapshot 실행이다.

| 검증 경계 | 관측 결과 |
|---|---|
| 필수 전체 `npm run test:gate` | Exit0 (`artifact://672`): orchestration175, Kolla Node27/Python11, Unix installer20, backend unit5,765, frontend350files/3,300 및 runner9, consumer contract174, 실제 격리 MariaDB/PostgreSQL/Redis functional128/23deselected, Ruff586files. PowerShell36개는 runtime 부재 skip이며 실행 증거가 아니다. |
| Focused creation/cleanup | Backend260, frontend password75 통과 (`artifact://673`). 원래 guest-password 권한 회귀와 신규 native 생성·이미지 저장·단건/bulk/detach 및 불확실한 rule403/503 경계를 포함한다. |
| 신규 삭제 회귀 | 부모 share를 먼저 요구해 삭제된 share의 exact rule 부재에도 세 API가 막히던 오류를 재현했다(`artifact://665`:3failed). Exact rule404면 cleanup을 완료하고, 남은 rule은 현재 share 관리 권한과 identity를 확인한 뒤 deny한다. Pending/error/403/503은 서버와 tracking을 보존한다. |
| 실제 생성 SDK/HTTP smoke | Current FastAPI/Uvicorn + installed SDK→loopback Glance/Cinder/Nova:7조건·45provider HTTP. User sync/SSE×image/volume의 exact native password·ConfigDrive·user-data/keypair 부재, legacy400·자동 network mutation0, 생성 이후 합성 오류의 실제 Nova forceDelete·새 boot volume 삭제와 기존 volume 보존. Identity·cloud 자원·admission/placement/security/network/audit persistence는 합성이다. |
| 실제 삭제 SDK/HTTP smoke | Current ordinary API·Manila HTTP·Nova SDK TCP:5조건·15provider HTTP. 단건/bulk는 authoritative exact-rule404 뒤 Nova 삭제, detach는 서버 보존·tracking 제거; native rule403/503이면502·서버/tracking 보존. 운영 provider/인가를 검증하지 않는다. |
| 최신 compiled frontend | Svelte2,370files/0errors/기존3warnings, i18n37namespaces/9,450messages·0errors/0warnings, scan990files/hardcoding0, production build exit0 (`artifact://585`). 실제 Chromium4locales×2themes×390/1440px의16조건에서 overflow0·메뉴 bounds·4항목·Escape focus 복원. 문서 en→ja link/HTML lang/native password 설명·앱 ko cookie 보존을 확인했다. Reduced motion·기본 공개 config이며 API와 외부 요청은 차단했다. |
| Source/credential boundary | Qualified source digest `01a2c45cd44b880988f142d0fc109b579a1d9591b9958dc0e19da0e50931e932`,2,615files. Gitleaks의14개 탐지는 직접 검토한 source SHA-256 parity 값이며 scratch-only exact fingerprint 제외 후 leak0. Repository scanner 정책을 완화하지 않았다. Gbrain CLI 부재로 sync/안내 변경은 수행하지 않았다. |

처음 whole-tree gate의 Palimpsest fixture 실패와 미완료 block 경로는 이번 Afterglow 부분의 통과로 해결됐다고 주장하지 않는다. 기존 frontend tabindex2종·cloudInitFileInput 및 backend 경고는 유지한다. 실제 Windows 최초 부팅/RDP/GPU, 운영 IAM·DB/mixed-version migration/backup·deployment, Safari/Firefox는 미검증이며 version bump/tag/main PR·merge·운영 배포는 이 커밋 요청의 범위가 아니다.


## 사용 중 볼륨의 명시적 강제 백업 검증 (local-only)

`explicit-forced-volume-backups`는 두 수동 생성창의 일관성 경고·기본 미선택 force 동의와 기존 API의 fresh owned-volume admission을 추가한다. 실제 운영 Cinder의 원래400은 `Backing up an in-use volume must use the force flag.`였으며, 이번 구현 검증은 운영 volume/backup/VM을 생성·분리·삭제·복원하지 않는 별도 loopback 환경이다. 기존 자동 백업은 force=false를 유지한다.

| 실행 범위 | 관측 결과 |
|---|---|
| Backend consumer regressions | backup/owner24 통과. Current storage target의 backend selectors와 auto_backup.py를 같은 source·격리 cwd에서 실행해628 통과. In-use 미선택의 mutation 전400, force 선택 수락, available 수락과 강제 옵션을 통한 foreign-owner 우회 거부를 포함한다. |
| Frontend consumer regressions | 신규 consent6, 기존 storage selectors와 backup project isolation까지10files/83 통과. 선택 철회, 다른 원본 선택, 닫기/재열기, available 전환에서 동의가 승계되지 않음을 확인했다. |
| Native HTTP | 실제 현재 FastAPI route·설치된 openstacksdk·loopback HTTP. In-use 미선택400은 provider POST0; 선택 시 SDK의 backup.force=true와 API201/creating, available은 force=false/201. 기존 activity.extra의 force 선택도 관측했다. Identity/Cinder/cache/audit persistence는 합성이며 실제 backup 저장소나 복원 proof가 아니다. |
| 실제 UI | 최종 경고를 정합성 보장이 아닌 쓰기 중 데이터의 불일관성 가능성으로 표현한 current-source Vite를 Chromium으로 실행했다. 두 생성창 ×4locales×2themes×320/390/767/768/1023/1024/1440px의112조건에서 consent 전 차단·선택 후 활성화·철회 후 차단, overflow0와 panel/footer bounds를 확인했다. 실제 두 화면의 제출이 native SDK force=true로 도달했고, 사용 중 원본에서 available로 바꾼 제출은 force=false였다. 최종 consent/guide3files/34와 전체37namespace/9450source messages catalog0errors/0warnings도 확인했다. |
| Short/zoom-equivalent viewport | 두 생성창의720×450 CSS/DPR2 조건에서 실제 overflow0, bounded panel 내부 스크롤과 동의/제출 접근을 확인했다.1440×900 물리 화면의200% zoom-equivalent geometry이며 OS/browser zoom control 자체를 조작한 proof는 아니다. |
| Compiler/catalog/style | Svelte2370files/0errors/기존 범위 밖 warnings6, volume catalog0errors/0warnings. Backend 변경4files Ruff check 및 format check 통과. Test target registry validation도 통과했다. |
| Public guide/registry | 변경한4locale core guide의 catalog/locales2files/28과 test-target orchestrator12 통과. 수동 백업 Svelte3files의 hard-coded Korean scan0. Current-source 별도 frontend snapshot에서 production build가 adapter-node 출력까지 완료했다. |
| Scoped architecture | HEAD와 명시한17source overlays만 별도 dev checkout에서 stamp·working/staged check 통과. 최종 경고의 SHA256 `0614351daa08e93d8a461327597bfcc727e83f2f2c27a9b74d5699b10bffa2eb`,2602files. 공유 index/review marker와 다른 동시 WIP의 승인은 변경하지 않았다. Gbrain CLI가 PATH에 없어 sync는 수행하지 않았고 CLAUDE.md는 수정하지 않았다. |

Canonical backend target runner는 기존 private TOML `Invalid value (line10,column9)` 때문에 collection 전에 종료했다. 사용자 config는 수정하지 않았고 `PYTHONPATH=<repo>/backend`와 `/tmp`의 별도 cwd에서 같은 source/선택 파일을 검증했다. 최초 volume UI fixture의 빈 quota body는 실제 storage/compute contract로 바로잡았으며 application code를 완화하지 않았다. ActionMenu의 진입/위치 frame을 paint hit-test로 기다린 뒤 실제 pointer를 사용했다. Scoped source·native JSON·matrix·대표 screenshots는 OpenSpec evidence와 `~/.local/share/afterglow-proofs/afterglow-forced-backup-qdsxonsa/`에 보존한다.

한계: 실제 Keystone authorization, 운영 Cinder backup 생성/완료/저장소 일관성·실제 guest/DB 복원, Safari/Firefox, 전체 test:gate·commit/push·배포는 수행하지 않았다. 백업 I/O 부하, 쓰기 중 백업의 일관성과 복구 가능성은 운영 서비스별 검증 사항이다. Force 자체를 crash-consistent snapshot의 보장으로 설명하지 않으며 source의 선택값 전달과 사용자 인지/거부 boundary를 운영 복원 성공으로 승격하지 않는다.

## 언어 메뉴 테마 통일 검증 (2026-10-12, local-only)

사용자 첨부 화면의 문서/메인/콘솔 언어 메뉴 차이는 문서의 themed details와 앱의 투명 native select/OS popup에서 발생했다. `unify-locale-dropdowns`는 기존 LocaleSelect를 공용 details/summary로 바꾸고 문서 layout의 중복 구현을 제거했다. 운영체제 popup을 색만 덮는 대신 실제 열린 메뉴를 앱 theme tokens로 렌더링한다. Native toggle 직후 Escape가 누락되는 신규 경계는 수정 전 실패/수정 후 통과 회귀를 남겼다. 실제320px 콘솔 popup의 왼쪽 잘림도 viewport8px 여유로 수정했다.

| 실행 범위 | 관측 결과 |
|---|---|
| 관련 consumer tests | LocaleSelect·docs locales·LandingPage·consoleTerminalLocale·designSystemRules의5files/35tests 통과. 언어/cookie/focus, 키보드 경계·즉시 dismissal 및 기존 terminal locale lifecycle을 포함한다. |
| Compiler·catalog | Svelte0errors/공유 source의 범위 밖 warnings6개, production build exit0. 기존 DocCodeBlock/ProjectUsageTable tabindex·cloudInitFileInput 및 동시 ImageWindowsSetupSection redundant role3종이다. i18n0errors/0warnings,37namespaces/9,450messages, scan990files/0hard-coded Korean. 변경된 두 Svelte 파일에는 진단이 없다. |
| 최종 compiled Chromium | loopback5275. 문서·메인·로그인·사용자/관리자 tutorial 콘솔5surfaces × ko/en/ja/zh-CN × dark/light ×320/390/767/768/1023/1024/1440px의280조건 통과. Overflow0, 모든 popup이 viewport 내부, 항목 최소44px. 동일 theme에서 panel background/ink가 모든 surface·locale·width에 동일하다. compact trigger는 mobile44px/desktop32px, labelled44px 유지. |
| 실제 키보드/선택 | Arrow/Home/End·Enter/Space, Escape focus 복원, Tab 이탈·밖 클릭을 실행했다. 앱의4surfaces에서 선택 후 같은 stable-id trigger focus·닫힘·refocus flag 폐기,1년 cookie와 reload SSR 언어를 확인했다. 문서의 path/query/hash/tutorial 보존은 네 언어에서 검증했고, zh-CN URL 선택은 앱 en cookie를 바꾸지 않는다. |
| No-JS·short viewport | JavaScript를 끈320px 문서에서4개 실제 link·완전한 popup bounds와 zh-CN→ja navigation/HTML lang을 확인했다.720×450/DPR2에서도 menu 전체가 보인다. |

Source scope는 LocaleSelect.svelte·신규 LocaleSelect.test.ts·docs/+layout.svelte3개다. HEAD`249a937ed031d33a2fa883c37eb90c4aabacd17f`+이3overlays만 격리 local dev/index에 적용한 architecture stamp/check는 `7f750f0c54907a6e1254b78458c5457fb3ed3f9d7134eec52047c8b2107c1dc8`/2,602source files로 통과했다. 공유 index/review marker와 다른 작업을 보존하고 전체 WIP 승인으로 확대하지 않는다. Raw compiler·before/after screenshots는 `~/.local/share/afterglow-proofs/unified-locale-menu-20261012-bmy0i7u_/`, 대표 화면과 실제 matrix/interaction/architecture는 해당 OpenSpec archive의 `evidence/`에 보존한다.

한계: 공개 config와 기존 tutorial의 합성 콘솔 UI 증거다. 실제 Keystone 인증/인가·운영 콘솔·Safari/Firefox·전체 test:gate·commit/push·배포는 수행하지 않았다. Backend/API/auth/schema·theme palette·일반 form select는 변경하지 않았다. Gbrain detect는 no-cli/config 없음이므로 sync하지 않고 CLAUDE.md 안내를 임의 변경하지 않았다. `rapid`의 proposal/tasks 완료를 generic delta-spec validator 통과로 표기하지 않는다.

## Windows 이미지 서비스 설정 검증 (2026-10-12–13, local-only)

`windows-image-service-preset`은 실제 게스트 준비 확인을 전제로 한 이미지 property 프리셋과 authoritative image 최소 부트 디스크 admission을 제공한다. 새 backend preset endpoint/DB/인가·production mutation·배포는 없다. `~/.local/share/afterglow-proofs/afterglow-windows-image-preset-tuarqe9o/native-http.json`은 실제 FastAPI·설치된 openstacksdk3.3.0·loopback Glance/Nova/Cinder HTTP의16케이스를 기록한다. Identity·이미지/VM/볼륨·Placement/admission/audit는 합성이고 목록 캐시는 격리 fakeredis다. 실제 Windows 게스트·운영 OpenStack·RDP acceptance 증거가 아니다.

| 실행 범위 | 관측 결과 |
|---|---|
| 실제 SDK 오류 재현/수정 | 최초 raw PATCH가 `/glance/v2/v2/images/legacy`404였지만 API200/변경 없는 상세를 반환했다. 버전 상대 경로와 `raise_exc=True`로 수정했다. 다음 실행에서 SDK 별도 필드의 `img_config_drive` 누락을 발견해 ConfigDrive·machine type·Secure Boot·QGA를 원래 Glance property 키로 재투영했다. 공급자 fixture의 경로/상태 검사는 완화하지 않았다. |
| 저장·권한·캐시 | 사용자/admin 경로의 정확한11플래그 단일 JSON-Patch·새 전체 상세 및 별도 재조회, owner/visibility/digest/minimum/unverified/production_ready=false 보존을 확인했다. 공급자409는 API400이며 이전 값 유지, nonowner/비관리자 admin endpoint403, 관리자 foreign 이미지 저장은 소유자 유지였다. Warm owner/shared 카탈로그 캐시2회귀는 수정 전2실패·수정 후2통과했다. |
| 실제 create 전송 | 사용자 sync/SSE·관리자 SSE마다79GB는 min_disk80인 엄격한 Cinder에서 거부하고 Nova를 호출하지 않았다.80/500GB는 제출 크기를 그대로 생성하고 원문 비밀번호 digest·강제 config_drive·user-data/keypair 부재·응답/이력 비노출을 확인했다. 이전 smoke처럼20GB 요청을80GB 성공으로 꾸미지 않았다. |
| 실제 compiled UI | owner/admin × ko/en/ja/zh-CN × dark/light ×320/390/767/768/1023/1024/1440px의112조건에서 page/section 가로 overflow0, 컨트롤 영역 이탈0, preview 셀의 세로 text clipping0을 확인했다. 실제 대표 pixels와 native table/row/cell 접근성도 확인했다. Compact TableShell의 고정 셀 높이가 모바일 두 줄 값을 자르던 문제는 표준 normal density의 자연 높이로 수정했다. |
| 실제 브라우저 상태 전이 | 확인 전/공백 계정 차단, preview와 단일 실제 JSON-Patch 일치, provider 오류/초안 보존/재시도, 미선택 Win11/QGA·무관한 속성 보존, 비소유자 읽기 전용과 비관리자 admin 진입 차단, 관리자 foreign-owner 저장, 이전 저장을 닫고 다른 이미지 연 뒤 늦은 응답 격리를 확인했다. 이름 기반 distro 표시가 실제 provider property 없음에도 diff를 생략하던 문제도 재현·수정하여 실제5개 기본 flag가 저장됨을 확인했다. |
| 저장 후 VM 생성 | Canonical 카탈로그 새로고침 후 상세 재진입으로 저장 계정 유지. 새로 설정한 이미지에서 실제 wizard의20→80GB/min80,79GB 입력을 강제 clamp하지 않고 Next 차단,500GB 허용, 최종80GB 제출/SSE 완료와 정확한 native 비밀번호·ConfigDrive·user-data/keypair 없음까지 확인했다. 네 언어 공개 `/docs/glance`도 인증 없이 요구값·게스트 준비·이전 이미지 경고가 번역되어 렌더됐다. |
| 관련 검사 | Backend image API/native SDK/cache72, instances target backend1,147/frontend560 통과. 관련 frontend9files/213 통과 후 실제 distro 판정 회귀를 추가한 최종 consumer59 통과. Svelte2,369files/0errors/기존 warnings3개, i18n37namespaces/9,447source messages·0errors/0warnings, scan990files/0hard-coded Korean, 최종 production build exit0. |
| 전체 `npm run test:gate` | 격리된 frozen public-source snapshot에서 exit0: architecture, orchestration175, Kolla Node27/Python11, Unix installer20, backend unit5,758, frontend349files/3,293+runner9, consumer contract174, 실제 disposable datastore functional128/23deselected, Ruff check/format586files. PowerShell36은 runtime 부재 skip이며 Windows 게스트 실행 proof가 아니다. |

격리 staged/working architecture guard는 `b116355ae29fccafd0ff11351b827932e8021e8358e567c3afec634a80146fbd`/2,614source files로 통과했다. `source-parity.json`은 이 작업의29개 source가 실제 compiled/tested snapshot과 byte/hash로 같음을 기록한다. 공유 Git index·architecture review marker·private config·원래 `.venv`·운영 Compose/volume은 stage/stamp/교체하지 않았다. 통합 snapshot의 전체 gate는 동시 WIP의 별도 semantic 승인이 아니다. Gbrain CLI는 없어 sync/시작 지침 변경을 하지 않았다.

별도 관측: 사용자 이미지의 가상 상세 URL(`/dashboard/compute/images/:id`)을 직접 새로고침하면 landing shell과 상대 asset import 오류가 있었다. 이 routing 경로는 이번 property/최소 디스크 변경에서 수정하지 않았고, direct deep-link reload 성공으로 기록하지 않는다. 저장값 persistence는 정상 카탈로그 URL 새로고침 후 같은 UUID 재진입과 실제 API/Glance 재조회로 증명했다. Actual guest/RDP·운영 identity/provider·hardware/TPM·이미지 binary/봉인·배포/commit/push는 수행하지 않았다.


## 키네틱 아트 랜딩 검증 (2026-10-12, local-only)

`kinetic-cloud-story`는 정적 hero와 opacity-only 설명을 불투명 조형의 실제 이동·회전·조립으로 바꾼다. Hero, 서버, GPU, Lumen, Kubernetes, 기관 구축6장면을 같은 재료로 연결하며 실제 cloud operation이나 live inference를 가장하지 않는다. 기존 schema/API/auth/config/배포 구조는 변경하지 않았다.

| 실행 범위 | 관측 결과 |
|---|---|
| 관련 검사 | LandingPage·sceneMotion·typographyRoles·designSystemRules·MotionPrimitives·motion6files/37tests 통과. Svelte0errors/기존3warnings, i18n0errors/0warnings·37namespaces/9,401messages, scan988files/0hard-coded Korean. 최종 좌표·간격 수정은 마지막 production build와 아래 실제 화면에 포함했다. |
| 최종 compiled UI | adapter-node build exit0, loopback5236의 실제 Chromium. ko/en/ja/zh-CN × dark/light ×320/390/767/768/1023/1024/1440/2560px의64조건에서 overflow0, 모든 SVG paint가 viewBox 내부, 라벨최소12.51px, 주요 action44px, 예시4messages. 영문 기관 라벨 잘림과 자원 판/라벨 겹침을 수정했으며 자원 caption의 최소 여유는 SVG6.03units 이상이다. |
| 조형·연결 | 초기 replay에 각 장면의 transform 변화, 마지막 static에서 transform/자동재생 종료와 keyboard focus 보존. 불투명 face alpha255. 서버4/GPU4/Kubernetes6/기관7의21접점이 실제 SVG fill/stroke에 닿는다. 실제 조립 중 route dashoffset1, 조립 종료 후에도 draw 시작 전까지1이며 이후 연결선을 그린다. |
| 정지·접근성 | 서버의23개 named motion clock이 화면 밖에서 정지. 실제 다른 탭을 앞으로 가져왔을 때 document.hidden/paused와23개 clock의 동일 시각을 확인했다. 반복 replay는 새 timeline으로 교체, reduced 전환은 완성 frame·4messages·replay 숨김. Skip link focus,720×450/DPR2,390px no-JS 및 IntersectionObserver 부재의6개 static scene/4messages/replay 없음 확인. |
| 전후 영상 | 동일1440×900/DPR1·dark/no-preference,6장면·동일 대기/keyboard replay. Before는 보존한 변경 전5개 landing source와 원래 Korean hero caption/사진을 격리 Vite에서 실행했고 after는 최종 compiled build다. ffprobe: before32.366s/971encoded frames, after31.333s/940frames; mpdecimate changed174/339. 전후 playback·중간 contact sheet를 직접 확인했다. Nominal30fps나 changed-frame 수는 성능 개선 측정이 아니다. |

영구 raw 증거는 `~/.local/share/afterglow-proofs/kinetic-cloud-story-20261012-irg4mo8n/`의 before/after영상·source·JSON이고, 이 change의 `evidence/`에는 결과와 대표 화면을 보존한다. HEAD`249a937ed031d33a2fa883c37eb90c4aabacd17f`+명시14source overlays/27obsolete deletions를 격리 local dev/index에 적용한 architecture guard가 `6ac0b6dee070e87474264ddc484d19ec70d5f1ea985d937d9506e805bdb9344f`/2,583files로 통과했다. 실제 공유 index/review marker와 동시 WIP는 수정하지 않았으며 전체 WIP 승인이 아니다.

한계: 기본 공개 config의 로컬 Chromium 증거다. 실제 기관 config/인증·provider/GPU/VM/Kubernetes·운영 배포·Safari/Firefox·전체 `npm run test:gate`·commit/push는 수행하지 않았다. 기존 DocCodeBlock/ProjectUsageTable tabindex 및 cloudInitFileInput 경고는 남는다. Gbrain은 CLI/config가 없어 sync하지 않았고 시작 지침에 임의 설정을 넣지 않았다. `rapid` schema의 proposal/tasks는 완료이며 delta spec이 없으므로 generic strict validator의 “No deltas found”를 통과로 기록하지 않는다.

## 랜딩 연결·가림·대화 시연 수정 검증 (2026-10-12, local-only)

`repair-landing-visual-continuity`는 사용자 첨부 화면의 연결선 단절/합류, 기관 클라우드 뒤쪽 면 겹침, 잘린 빈 채팅 캡처와 무의미한 다시 보기를 수정했다. 이전 overflow/bounds 통과는 이 시각 결함을 검증한 것이 아니므로 이전 완료 주장으로 대체하지 않는다. 서버·GPU·Kubernetes·기관 구축 전체를 정지·중간 frame에서 점검했고, Lumen은 공용 `ChatBubble`의 네 언어 질문2개·답변2개로 교체했다. 대화는 작성된 예시이며 비공개 사용자 기록이나 provider 실행 결과가 아니다.

| 실행 범위 | 관측 결과 |
|---|---|
| 관련 검사 | LandingPage·sceneMotion·typographyRoles·designSystemRules 4files/18tests 통과. Svelte2,360files/0errors/기존warnings3개. i18n0errors/0warnings·37namespaces/9,400messages, scan987files/0hard-coded Korean lines. 기존 DocCodeBlock/ProjectUsageTable tabindex와 cloudInitFileInput 경고는 남는다. |
| 최종 build/runtime | Vite8.2.2·adapter-node build exit0 후 별도 loopback Node runtime5222에서 실제 Chromium 실행. 검사 후 마지막 SVG 좌표/장식선 정리는 최종 build/browser에 포함했다. |
| 최종 반응형·현지화 | ko/en/ja/zh-CN × dark/light ×320/390/767/768/1023/1024/1440/2560px, DPR1의64조건 통과. Overflow0·missing key0·SVG labels최소13.89px·주요 link/button44px·전체 대화4messages 표시. 기존 compact LocaleSelect는 mobile44px/desktop32px로 별도 기록한다. |
| 접점·가림 | 서버4·GPU4·Kubernetes6·기관7의21접점을 실제 SVG `isPointInFill/isPointInStroke`로 검사했다. Branch별 접점과 모델 circle을 포함한다. 전체 graphic paint viewBox 내부, 모든 equipment face alpha255, replay 중 transform 없음과 접점 유지 확인. Composited solid/route의 finite fade는 geometry를 움직이지 않는다. |
| 실제 대화/replay | 4.54s 질문→답변chunk→후속질문→답변chunk 순서를 중간 opacity와 screenshots로 확인. 최종5장면 static/running0·focus 유지,1440×900에서 각 headline·완성 장면·replay가 함께 보인다. Chat 최종 bottom880.43px. |
| 수명·접근성 | Offscreen 및 실제 다른 Chromium tab 활성화로 hidden 상태의 animation clock 정지/재개, 재생 중 replay가 기존 phase를 취소하고 첫 질문으로 재시작, 실행 중 reduced 전환 시 전체 대화/static·replay숨김 확인. Skip link focus,720×450/DPR2 overflow0; native200%zoom 증거는 아니다. |
| 정적 fallback | 실제 JavaScript 비활성390px에서 전체4messages·모든 scene static·replay0·overflow0. 별도 owned capability fixture의 IntersectionObserver 부재에서도 전체 대화/static·replay0. |
| 실제 전후 녹화 | 둘 다1440×900 CSS/encode·DPR1·dark/no-preference, 동일5장면·keyboard replay. Before14.4s/432frames/changed192, after17.2s/516frames/changed169. 새 대화의 전체 sequence를 담으려고 after 대화 관측은 더 길다. ffprobe/mpdecimate 결과이며 nominal30fps를 성능/fps 개선으로 해석하지 않는다. |

QA probe 정정도 기록한다. 최초 matrix는 기존 desktop locale32px를44px 주요 action과 혼동해 중단됐고, 실제 controls를 분리한 기준으로64조건을 완주했다. Lifecycle의 모든 순차 assertion은 통과했으나 마지막 network assertion이 public site-config의OPTIONS를 금지해 실패했다. 실제 request trace는 해당GET/OPTIONS만 있고 preflight403(CORS)이었다. Network 분류만 정정했으며 앱에서 오류를 숨기거나 성공한 lifecycle 시나리오를 반복하지 않았다. Private chat/history/inference 요청·cloud mutation은 없었다.

Scoped architecture는 HEAD`249a937ed031d33a2fa883c37eb90c4aabacd17f`+기존 랜딩을 포함한15overlays/25inherited deletions를 별도 clone/index에 구성해 실제 guard를 통과했다: `source_sha256=021e960f30faae2729494804228990d164a554f45dda54cda93433eaa0025191`,2,584source files. 공유 index/review marker와 동시 작업을 보존하며 전체 WIP 승인이 아니다. 증거는 `~/.local/share/afterglow-proofs/landing-visual-repair-20261012-4xs6up8k/`와 해당 OpenSpec `evidence/`의 compiled matrix·motion·lifecycle·contact·architecture receipts, 전후 screenshots/video다.

한계: 기본 공개 config에서의 로컬 UI 증거다. Preview-origin public-config CORS, 실제 기관 config/인증·live inference/VM/GPU/Kubernetes·운영 배포·Safari/Firefox·전체`npm run test:gate`·commit/push는 검증하지 않았다. 기존 static `/docs` 캡처는 보존했고, 변경 없는 controller의 기존 consumer tests를 유지했다. CSS 기하/가림/타이밍은 source-text나 문구 고정 테스트 대신 실제 브라우저 증거로 검증했다.

## MCP 연결 클라이언트 관측·자격 철회 검증 (2026-10-12, local-only)

`mcp-connected-client-visibility`는 인증·SDK 검증이 성공한 initialize에서 grant별 정제 서명을 기록하고 계정의 OAuth/API 키 목록에 이름·버전·추정 product/kind/browser/OS·근거·첫/마지막 관측 시각을 표시한다. 최근10개 서로 다른 서명은 실제 단말·세션 수나 온라인 상태가 아니다. 모르는 클라이언트의 `연결 제거`는 관측 삭제나 UA 차단이 아니라 같은 자격을 공유한 모든 클라이언트와 선택된 Lumen 기본 위임의 grant/API 키 전체 철회다.

| 실행 경계 | 관측 결과 |
|---|---|
| Exact·등록 target | Focused backend93개, 실제 disposable MariaDB의 observation/migration/OAuth 회귀42개 통과. 정본 `mcp` target backend519개/100deselected와 account frontend163개 통과. Account+mock transport189개/2files; 최종 catalog guard 포함193개/3files도 통과했다. |
| Schema087 | 별도 소유 DB에 기존063/084/085/086 뒤087을 두 번 적용했다. 기존 OAuth grant의 이름·활성 상태·자격을 보존하고 관측은NULL→public[]였다. 공유/운영 DB에 migration하지 않았다. |
| 실제 MCP SDK·ASGI·TCP·MariaDB·Redis | Canonical arm64/amd64 backend에서 각각6개 initialize와 실제 목록을 실행했다. 별도의 fresh amd64 실행은18개 SDK initialize와9개 lifecycle/privacy 시나리오를 통과했다: malformed/unauthenticated 미기록, 반복 first/last 갱신, 추정 근거·bot 우선순위, unsafe label 거부·10개 retention·정확한9개 공개 field, owner/project 격리, PAT/OAuth 전체 철회와 이전 bearer401·refresh400 `invalid_grant`·감사/tombstone·cleanup 확인. |
| Canonical container 실행 | 정본 Dockerfile의 backend/frontend target를 각각 linux/arm64·linux/amd64로 build/load했다. 고유 Compose project `afterglow-mcp-client-v-tdslvh`에서 실제 backend machine `aarch64`/`x86_64`와 product source hash 일치를 확인했다. AMD64는 Docker Desktop emulation이며 image build만으로 실행 증거를 대체하지 않는다. |
| 실제 compiled Chromium | 최종 qualified frontend2architecture ×4locale ×light/dark ×OAuth/API2method ×390/767/768/1023/1024/1280/1440px =224조건. Document/card/client overflow0,3개 관측·근거·unknown·비밀 비노출을 확인했다. Mobile64조건의 credential removal은 최소44px이며 native disclosure390px spot check도44px다. Desktop action은 credential의 상단에 정렬된다. |
| 실제 오류·재시도·제거 | API 목록503이어도 OAuth는 유지하고 반대 경우도 확인했다. 실패한 method는 stale row/removal/확정0 count를 숨기며 inline retry 후 복구됐다. 두 architecture에서 OAuth/PAT의 실제 browser DELETE→목록 재조회와 native epoch2·이전 bearer401·OAuth refresh 거부·감사/cleanup을 확인했다. 네 locale의 공개 guide도 실제 rendered 위조 경고·자격 전체 제거 안내를 확인했다. |
| 최종 전체 `npm run test:gate` | Exit0: architecture, orchestration175, Kolla Node27/Python11, Unix installer20, backend unit5673, frontend347files/3177 및 runner9, consumer contract174, 실제 disposable functional128/23deselected, Ruff check/format585files. PowerShell36개는 runtime 부재로 skip이며 Windows 실행 proof가 아니다. |
| 추가 frontend 검사 | Svelte2359files/0errors/기존 warnings3개; i18n0errors/0warnings·37namespaces/9397messages, scan986files/0hard-coded Korean lines. 기존 DocCodeBlock/ProjectUsageTable tabindex와 cloudInitFileInput non-reactive 경고는 남는다. Changed Python11files Ruff check/format 통과. |

**조회 실패 원인·배포 순서:** 첨부 화면 조사에서 실제 로컬 backend 로그의SQL1054 `Unknown column 'mcp_delegated_grants.project_scope'`를 확인했다. 현재 reader와 pre084 DB의 불일치이며 목록 오류 격리는 schema 복구가 아니다. 기존084–086과 신규087을 reader/writer 전에 적용할 별도 배포 준비가 필요하다. 공유 DB·원래 credential·private `afterglow.conf`·실제 Git index/review marker·다른 Docker project는 보존했다. 첫 전체 gate의 구형 grant fixture, exact allowlist의 잘못 복사된 tool paging footer, 뒤따른 stale architecture stamp는 수정한 후 최종 전체 gate만 성공으로 집계한다. Throwaway native harness의 JSON-RPC error/배열 순서/bot 추정/브라우저 mutation header/OAuth 무인증 token request 가정도 실제 계약에 맞췄으며 제품 검증·인가를 완화하지 않았다.

**Scope·한계:** private 입력을 제외한 현재 source의 whole-file snapshot으로 검증했으며 동시 WIP가 포함된 통합 실행이다. Working와 소유 candidate index의 staged architecture guard는 같은 source digest `271bcad166abcdee6507d2c14d1e69d10429615ed5ccbfffd9b6de55fda9a5d9`/2605files였다. Feature-only patch·공유 checkout 전체의 이후 변경·운영 수용 증거가 아니다. Browser IAM/profile·membership·upstream Keystone cleanup은 합성 seam이고 MCP SDK/transport/SQL/Redis와 list/revoke는 실제다. 실제 제3자 제품 신원·continuous online/단말 수·live IAM/Keystone cleanup·분산 replica·production migration/배포·mixed-version rollout·backup/restore·Firefox/Safari·commit/push는 검증하거나 수행하지 않았다. Optional GBrain CLI가 없어 sync하지 않았다.

**보존:** [`mcp-connected-client-visibility`](../openspec/changes/archive/2026-10-12-mcp-connected-client-visibility/)의 `evidence/verification.json`, `native-http.json`, `compiled-ui.json`, `container-runtime.json`, `architecture.json`에 compact receipt를 보존한다. 최종 mobile/desktop 합성 화면·image build metadata와 원래 전체 gate log는 `~/.local/share/afterglow-proofs/mcp-connected-clients-20261012-v_tdslvh/`에 남겼다. 이전 touch 수정 전 화면은 최종 수용 증거가 아니다.

Rapid proposal/tasks 완료 뒤 `openspec archive mcp-connected-client-visibility --skip-specs --yes`로 위 날짜의 archive를 만들었다. Rapid schema의 no-delta-spec 경고는 비차단이며 다른 spec 관례를 추가하지 않았다. `evidence/cleanup.json`은 소유 host native service·dedicated Chrome 종료, 소유 Compose5container/1network 정상 제거와 scratch 삭제를 기록한다. Datastore는 소유 tmpfs였고 volume 삭제·force removal·광역 prune·`down --volumes`는 사용하지 않았다. 다른 project·이미지/cache·원래 private 설정과 영구 proof는 보존했다.


## 그림·모션 중심 랜딩 검증 (2026-10-12, local-only)

`visual-cloud-product-story`는 사용자가 직전 페이지를 심심하고 글이 많다고 평가한 데 따른 공개 frontend cutover다. 큰 제품 개념 그림과 서버·GPU 학습·Lumen 채팅·Kubernetes·기관 구축의 다섯 장면으로 바꿨다. 미지원 레이어 기록·보존·포크·재사용 홍보는 복원하지 않는다. 기존 cloud/auth/API/schema/config/운영 state는 변경하지 않았다.

| 실행 범위 | 관측 결과 |
|---|---|
| 관련 consumer·design regression | LandingPage·sceneMotion·typographyRoles·designSystemRules 4개 파일·18개 테스트 통과. Skip focus·서비스 navigation, hidden/offscreen·늦은 callback·reduced motion·finite completion/replay 경계를 포함한다. 제거된 filter/fixture/plate 테스트는 새 문구로 repin하지 않았다. |
| Svelte check | 2,359개 파일·0 errors·기존 warnings 3개. `DocCodeBlock`·`ProjectUsageTable` tabindex와 `cloudInitFileInput` non-reactive 경고는 남는다. |
| Localization·build | i18n check 0 errors/0 warnings, 37 namespaces·9,392 source messages; scan 986개 파일·hardcoded Korean 0줄. Vite 8.2.2·adapter-node production build exit 0. 네 언어 번역은 원어민 검수 인증이 아니다. |
| 실제 최종 compiled UI | ko/en/ja/zh-CN × light/dark × 320/390/767/768/1023/1024/1440/2560px, 64조건. 실제 DPR 1, overflow 0, action target 최소44px, SVG label 최소12.51px, 누락 key 없음. Text뿐 아니라 전체 SVG `getBBox()`가 각 viewBox 안에 있음을 확인했다. |
| 한눈에 보이는 구성 | 1440×900에서 네 서비스 jump link가 첫 화면 안에 있다. 실제 replay activation 후에도 다섯 feature의 headline과 완성 그림이 같은 viewport에 남는다. Lumen은 실제 한국어 캡처의 채팅 영역을 명시적으로 보여주며 응답을 만들거나 provider를 호출하지 않는다. |
| 실제 motion·keyboard | 다섯 장면 keyboard replay·focus 유지·offscreen pause/resume·finite static completion/running0. 실제 다른 Chromium tab으로 전환한 hidden/visible에서도 pause/resume, 실행 중 reduced motion 전환 뒤 모든 장면 static/running0. Skip link 본문 focus와720×450·DPR2 overflow0도 확인했다. 후자는 native200%zoom 증거가 아니다. |
| 정적 fallback·clean cutover | 최종 build에서 JavaScript를 비활성화해 headline6개·완성된 static6장면·hero image decode·overflow0·inert replay부재 확인. Observer 부재는 owned synthetic capability fixture로 별도 확인했다. 삭제된 compute/quota/console/layer artwork4개 HTTP404, Nova/Lumen/Drover guide3개 HTTP200. |
| 실제 전후 녹화 | 전4.866s·1200×750 encode·146frames/changed45, 후13.0s·1440×900 encode·390frames/changed198. 후자는 실제1440×900 CSS viewport·DPR1·light/no-preference를 영상 내 sample로 확인했다. 서로 다른 디자인·행동·encoded크기이므로 성능/동일조건 fps 비교가 아니다. Helper packet 수 대신 ffprobe/`mpdecimate`를 기록했다. |

검증 중 발견·수정한 문제: `state` local name이 Svelte `$state` rune와 충돌해 발생한 타입 오류는 `motionState`로 수정했다. 첫320px 조건의11.815px SVG label은36 SVG units로 키우고 긴 일본어 label을 간결하게 정리했다. GPU pin의 연속 lower-case relative `m`이 다음 section까지 paint하던 문제는 absolute `M`으로 고쳤다. Scroll overflow0만으로 SVG paint가 안전하다고 판단하지 않았다. GPU/채팅/기관 구축의 지나치게 긴 framing도 실제 caption·그림·replay를 같이 보이도록 조정했다. 초기 check의 MCP account 타입 오류3개와 scan의MCP guide hardcoded1건은 동시 작업 영역으로, 이 변경에서 해당 source를 수정하지 않았다; 최종 global 결과와 구분한다.

Scoped architecture는 HEAD`249a937ed031d33a2fa883c37eb90c4aabacd17f` + 명시14개 overlays + obsolete25개 deletions를 별도 Git clone/index에 구성했다. 실제 guard `--staged --stamp`/`--staged`는 `source_sha256=5842b2caf370574e1a0febe100204463b691be7a3683fb58492ffd487c90618d`, source2,583files로 통과했고 공유 index/review marker는 보존했다. 전체 동시 WIP·working-tree gate 승인으로 확대하지 않는다.

증거: `~/.local/share/afterglow-proofs/visual-cloud-story-20261012-p9nbs46_/` 및 이 OpenSpec 완료 기록의 screenshots·browser JSON·motion·architecture receipts. 이전9개 cloud사이트 조사는 기존 archive에 그대로 남고 새 Apple reference는 [Mac Studio](https://www.apple.com/mac-studio/)의 source-backed 그림/기능별 소개 구조를 사용했다. 실제 Apple hero는 이 브라우저 sample에서 blank 상태여서 Apple video/motion을 관측했다고 주장하지 않는다.

한계: local site-config preview CORS 제한으로 기본 공개 config에서 UI를 검증했다. 실제 configured public-site integration, VM/GPU 할당·유료 Lumen inference·Kubernetes 설치·기관 구축·운영 배포·Firefox/Safari·전체`npm run test:gate`·commit/push는 하지 않았다. GBrainCLI는PATH에 없어 sync하지 않았다. 생성 장비 그림은 실제 inventory 사진이 아니라 개념 이미지다.

## 지원 서비스 중심 랜딩 검증 (2026-10-12, local-only)

`research-cloud-service-landing`은 공개 소개를 서버·GPU AI 학습·Lumen 채팅·Kubernetes와 기관 내부 클라우드 구축으로 한정한다. 사용자 확인대로 미지원 레이어 기록·저장·포크·재사용 story·체험 결과·library 카드·전용 source/static artwork를 제거했다. Backend/API/schema·인증·운영 topology·설정은 변경하지 않는다.

| 실행 경계 | 관측 결과 |
|---|---|
| Exact consumer regression | 최종 5개 파일·32개 테스트 통과. 체험 시작·일시정지·재개, 시나리오 변경과 늦은 callback 격리, reduced motion, workflow filter·제품 화면·skip focus를 포함한다. |
| 기존 `design` target | 최종 27개 파일·138개 테스트 통과. 첫 실행은 DESIGN.md의 구형 request-to-reuse 문구를 고정하던 assertion 1개로 실패했다. 미지원 문구를 복원하거나 새 문구로 repin하지 않고 해당 incidental test와 unused token list를 삭제했다. |
| Svelte/localization | check 2,363개 파일·0 errors·기존 warnings 3개. `DocCodeBlock`·`ProjectUsageTable` tabindex 2종과 `cloudInitFileInput` non-reactive 1종은 남는다. i18n check 0 errors·instance namespace key-order warnings 3개, scan 989개 파일·hardcoded Korean 0줄. 번역은 원어민 검수 인증이 아니다. |
| Production build·실제 compiled preview | Vite 8.2.2·adapter-node build exit 0. 최종 재빌드 뒤 네 서비스·3개 panel·reuse stage 부재와 overflow 0을 다시 실행했다. 최종 adapter-node 자체 실행(5199)에서도 390px 구축 선택·정확한 문의 목적지·overflow 0과 삭제된 두 static artwork의 HTTP 404를 확인했다. |
| Compiled responsive UI | ko/en/ja/zh-CN × light/dark × 320/390/767/768/1023/1024/1440/2560px, 총 64조건. 두 이용/구축 선택의 설명·소유 경계·console/mailto 목적지, 선택 target 44px 이상, 누락 key 부재와 horizontal overflow 0을 확인했다. Desktop 1024/1440px의 headline은 2줄이고 primary CTA는 첫 화면 안에 있다. |
| Keyboard/reduced/short viewport | Enter로 구축 선택·trigger focus 유지, Tab 문의 action, skip 본문 focus. GPU/cluster/data 3시나리오는 명시적 start 뒤 즉시 3/3 완료·진행 animation 0. 720×450·DPR 2에서 overflow 0이며 browser-native 200% zoom 증거는 아니다. |
| 링크·기존 탐색 | Nova/Lumen/Drover 공개 guide 3개 HTTP 200. Workflow 6개·filter 4개와 product project/cluster/network 3개 전환, 실제 Lumen WebP decode·font loaded/error 0을 확인했다. |
| 실제 reference 9개 | 지정 9 URL의 1440×900·DPR 1 hero/section 캡처. Google carousel, AWS hover 400ms/250ms, NHN opacity/translate 700ms, KakaoCloud 두 사이트의 muted loop MP4 재생, DO 30s CSS marquee와 CF canvas/20s waveform을 DOM/source와 대조했다. Vendor 주장·선언된 timing·실제 관측을 구분했다. |
| 전후 motion | 실제 light/no-preference·1440×900·DPR 1. 전 9.60s/288frames·후 9.333s/280frames, `mpdecimate` changed frames 95/74. Nominal 30fps는 성능 측정이 아니다. 새 구축 선택은 별도 4.733s/142frames 녹화(changed frames 10)와 rAF opacity/translate samples로 확인했으며 removed story와의 성능 비교가 아니다. |

Source/config 경계: local `localhost:8000/api/v1/site-config`는 HTTP 200이지만 5197/5198 preview origin의 CORS allow header가 없어 browser가 거부했다. 기본 공개 config로 UI를 검증했고 CORS·서비스 gate·운영 configuration은 수정하지 않았다. 실제 OpenStack resource/GPU 예약·Lumen 유료 inference·Kubernetes 설치·기관 구축·운영 custom config/배포·Firefox/Safari는 검증하지 않았다. 전체 `npm run test:gate`와 commit/push도 실행하지 않았다. GBrain CLI는 PATH에 없어 sync하지 않았다.

Scoped architecture는 HEAD `249a937ed031d33a2fa883c37eb90c4aabacd17f` + 명시적 source overlays 12개 + obsolete deletions 4개를 별도 Git index/review root에 구성해 `--staged --stamp`와 `--staged`를 통과했다(`98c0d1977586823acda12fb131b6600a9aca18ade9223c45d9ee49a73e8ffa40`, source 2,598 files). 공유 index·architecture review marker·동시 WIP는 보존하며 전체 공유 source 승인으로 확대하지 않는다. 영구 증거는 `~/.local/share/afterglow-proofs/research-cloud-landing-20261012-qxi2e2rq/`; 출처 링크를 포함한 조사 보고서와 compact receipts는 OpenSpec 완료 기록에 보존한다.

## Windows native 생성 비밀번호 전달 수정 검증 (2026-10-12, local-only; 운영 상태 읽기 전용)

`fix-windows-native-password`는 생성 비밀번호 입력과 실제 Nova 전달 사이의 불일치를 수정했다. 변경 전 실제 로컬 planner를 실행해 native marker 이미지의400 거부와 이전 marker의 Windows `adminPass` 제거·PowerShell 생성을 확인했다. 새 source는 정확한 `nova-adminpass-configdrive` metadata만 지원하며 Nova `adminPass` + `config_drive=true`, user-data·키페어 없는 생성으로 전환한다. 아래의 이전 PowerShell receipt는 당시 구현의 역사적 검증이지 현재 경로의 acceptance가 아니다.

| 실행 경계 | 관측 결과 |
|---|---|
| exact 회귀 | Backend459개 통과. Frontend5files/106개 통과: native-only metadata, user/admin image/volume, unsupported method/account 전환, 정확한 비밀번호·입력/오류/소유권·draft 폐기 및 기존 Linux 동작. |
| 정본 `instances` target | Backend1,145개·frontend36files/546개 통과. 공유 private config가 없는 frozen current public-source snapshot에서 정본 runner를 실행했다. |
| 실제 Uvicorn/FastAPI + 설치된 SDK + loopback Nova/Glance/Cinder | 63조건·399provider HTTP요청. 세 create endpoint×image/volume×공백/따옴표·Unicode/최대128자 네 password case24개에서 exact native digest·ConfigDrive·user-data/keypair 부재·target project를 확인했다. Legacy/unknown/account·명시적 userdata/GitHub/Manila·foreign volume 거부와422, Linux/no-password 보존, provider secret echo 실패도 검증했다. Identity/provider 자원·placement/admission·network/SG·audit sink는 합성이다. |
| 실제 compiled Chromium | 사용자/관리자×image/volume×ko/en/ja/zh-CN×rendered light/dark×390/767/768/1023/1024/1280/1440px,224조건 통과. Document 가로 overflow0, masked/in-bounds input·Admin 계정·Next readiness와 Linux access controls 부재. Rendered theme class 검증이며 OS preference persistence qualification은 아니다. |
| UI→위 실제 로컬 native HTTP | 네 user/admin image/volume flow의 exact secret→Nova body·ConfigDrive·SSE completed→실제 panel closure. 불일치 confirmation 차단·secret 없는 review/storage, image/volume legacy 차단·no SSH fallback, close/reopen blank와 provider 오류 비노출·실패 뒤 두 입력 폐기를 확인했다. Runtime JS error0. |
| 네 locale 공개 문서 | 실제 compiled `/docs/nova?lang=...`4개에서 해당 HTML language와 native adminPass/config-drive 설명·구형 생성 설명 부재를 확인했다. |
| Frontend/static checks | Svelte check2,362files/0errors/기존3warnings, production build exit0(Vite8.2.2). i18n check0errors/0warnings·37namespaces/9,401messages, scan987files/한국어 hardcoding0. Changed backend Ruff check·format7files 통과. |
| 전체 `npm run test:gate` | Frozen public current-source snapshot exit0. Orchestration175·Kolla27/image-ref11·CLI20, backend unit5,754, frontend347files/3,216+runner9, consumer contract174, disposable functional128/23deselected, Ruff585files 통과. PowerShell36개 runtime 부재 skip. Working·소유 임시 index staged architecture guard는 같은 `93050be8a4f1d4ace014b50d18b2a7ae7ac49dfcdf93e7fc91e4c68acd766764`/2,608sourcefiles였다. Snapshot에는 당시 concurrent WIP whole-file source가 포함되므로 scope-only나 이후 공유 source·운영 통합 승인으로 확대하지 않는다. 해당28개 scope 파일은 최종 verified snapshot과 hash 일치를 확인했다. |

실패와 수정: 첫 exact backend8실패는 Linux multipart MIME의 base64 part를 plaintext로 가정하고 `history(None)` 호출을 금지한 신규 test의 incidental assumption이었다. MIME part decode로 consumer content를 검증하고 불필요한 call/history pin을 제거했으며 Linux 구현은 바꾸지 않았다. 첫 frontend dependency optimization은 생성된 SvelteKit tsconfig 부재였고 정본 check/sync·build 뒤 같은 suite가 통과했다. Formatter가 지적한 test2개만 정리했다. Native scratch의 api_version/microversion 충돌, admin project fixture 경로와 너무 이른 browser completion observer는 throwaway harness만 수정했으며 실패를 passing evidence로 세지 않는다. 기존 `DocCodeBlock`·`ProjectUsageTable` tabindex와 `cloudInitFileInput` non-reactive warning3개는 유지한다.

Live 근거·미적용 상태: `/etc/kolla/reports/windows11-native-password-20261012/verified-summary.json`과 operator README를 읽었고, native Windows 이미지의 실제 active/private·`production_ready=false`·native marker/계정을 Glance에서 읽기 전용 확인했다. 보고서의 기존 CLI/guest ConfigDrive 암호 일치·RDP/NLA/desktop/TPM/SecureBoot/HTTPS 성공은 운영자의 선행 검증이며 이번 코드로 새 VM을 생성한 결과가 아니다. 컨트롤러3대 running backend에는 password planner가 없고 create API가 ConfigDrive를 전달하지 않으며 frontend build에도 native marker/confirmation 입력이 없어 수정 기능은 미배포다. 비밀번호 파일은 읽지 않았다. 운영 VM·이미지 공개/속성·보안그룹·운영 source/container/DB/IAM은 변경하지 않았다.

미검증: 수정본의 운영 실행/Afterglow 생성 VM의 실제 Windows 최초 부팅·RDP, CLI image boot와 별개인 Cinder boot의 새 Windows guest, 이미 초기화된 디스크의 Cloudbase plugin 재실행, 실제 placement/GPU/Windows driver·Firefox/Safari. 이미지 marker는 게스트 내부 설정이나 plugin 재실행을 대신하지 않는다. GBrain CLI는 없어 sync/guidance 변경을 하지 않았다. 영구 compact evidence는 [`fix-windows-native-password`](../openspec/changes/archive/2026-10-12-fix-windows-native-password/)에, bounded log excerpts·source parity·read-only deployed receipts와 개인정보 없는 합성 screenshots는 `~/.local/share/afterglow-proofs/afterglow-native-password-cjyjk_ng/`에 보존했다.

## Windows 초기 비밀번호·GPU flavor 수정 검증 (2026-10-12, local-only)

`windows-instance-create-password`의 당시 PowerShell 구현은 GPU flavor를 Linux bootstrap 요청으로 잘못 간주하던 거부를 수정했다. 아래 결과는 이 이전 경로의 역사적 receipt이며 현재 native 전달 계약은 위 `fix-windows-native-password` 기록을 따른다. 당시 지원 Windows image/volume은 PowerShell user-data와 config drive만 사용하고 GPU quota·fresh capacity admission은 유지했다. 명시적 user-data·GitHub SSH·Manila data mount 충돌은 mutation 전에 거부했고 제출 시 비밀 초안 폐기 뒤 재시도에는 비밀번호 재입력이 필요했다.

| 실행 경계 | 확인한 결과 |
|---|---|
| 비밀번호 exact regression | Backend378개, frontend2files/44개 통과. Metadata/소유권·입력 경계·secret redaction·wizard 전환 및 Windows GPU 허용/기존 Linux GPU 경로를 포함한다. |
| 정본 `instances` target | Backend953개, frontend28files/288개 통과. Private 설정 없는 HEAD+명시적 Windows overlay clone에서 같은 runner/selector를 실행했다. |
| 실제 Uvicorn + 설치된 OpenStack SDK + loopback Nova/Glance/Cinder | GPU21조건 통과: user sync/SSE·scoped-admin SSE의 Windows image/volume6개, explicit conflict9개, Linux password/SSH6개. Native Nova body의 PowerShell/config drive·Linux bootstrap 부재와 admission 유지, 응답/이력 비밀 비노출을 확인했다. |
| Production compiled UI → 위 로컬 HTTP 경계 | 사용자·관리자 각각 image/volume4개 SSE완료. `gpu.1080ti_8c_32g`·image root500GB, 확인값 불일치 차단·비밀 없는 review·재열기 시 빈 초안·제출 뒤 닫힘을 확인했다. Consumer GPU 설정390/767/768/1023/1024/1440px에서 transition 완료 후 document/panel overflow0·masked password·Next활성을 확인했다. |
| 실제 portable PowerShell7.6.6 | UTF-8/인용/공백/특수문자6조건의 exact account/password·injection 부재·변수 폐기를 확인했다. `Set-LocalUser`는 무해한 인자 probe이며 Windows 계정 변경 증거가 아니다. |
| Frontend 검사·빌드 | Svelte check0errors/3warnings, production build exit0, i18n check0errors/0warnings와 scan0hardcoded Korean. 기존 tabindex2종과 `cloudInitFileInput` non-reactive warning은 별도이며 숨기지 않는다. Changed backend Ruff check/format 통과. |

인접 회귀에서 일반 SSE placement-policy503보다 flavor400이 먼저 발생하던 검증 순서를 복원했다. Capacity refresh 테스트는 실제 flavor step을 명시하고 소비자 버그를 검증하지 않는 payload forwarding2개는 삭제했다. 격리 clone의 최초 frontend 시작 오류는 생성된 SvelteKit type/config 부재였고 `svelte-kit sync` 뒤 실행했다. 최초 실패 결과를 성공으로 세지 않는다. 공유 private `afterglow.conf`(기존 TOML 파싱 오류)·실제 index·공유 architecture review marker는 수정하지 않았다. 전체 `npm run test:gate`, 운영 배포·실제 GPU 할당·Cloudbase 최초 부팅·Windows 비밀번호 적용·RDP 로그인은 이번 증거에 포함하지 않는다.

영구 증거는 [`windows-instance-create-password`](../openspec/changes/archive/2026-10-12-windows-instance-create-password/)의 `evidence/gpu-native-http.json`, `gpu-compiled-ui.json`, `powershell.json`, `verification.json`, `architecture.json`과 합성 화면이다. 상세 실행 로그·기존4locale×2theme×7width의 사용자/관리자112조건은 `~/.local/share/afterglow-proofs/windows-instance-create-password-20261011-o4jmfexx/`에 보존했다. Scoped architecture proof는 HEAD+명시적 overlay의 working/staged source만 검토하며 동시 WIP나 운영·게스트 수용으로 확대하지 않는다.

## Lumen 채팅 전체 작업 영역 복원 검증 (2026-10-12, local-only)

`restore-chat-full-viewport`는 사용자 제공 화면을 기준으로 채팅·채팅 프로젝트의 외부 `PageShell` 제한을 제거하고 내부 transcript/composer만 공통80rem에 맞춘 markup/CSS 수정이다. 앞선 공통 shell 검증은 당시 기록으로 유지하며 채팅의 현재 계약은 full-bleed 예외다. 일반 설정·Studio·API·인증·DB·서비스 소유권은 바꾸지 않는다.

| 실행본 | 실제 Chromium 조건 | 관측 결과 |
|---|---|---|
| 로컬 source Vite | 새/저장 대화 × light/dark × 390/767/768/1023/1024/1280/1440/1920/2560px 및 844×390·960×500, 총44조건 | 문서 가로 overflow0. 저장 대화의 독립 기록 scroll·하단 composer, 새 대화의 높이 부족 시 내부 scroll. |
| 최종 adapter-node production build | 새/저장 대화 ×4locale ×light/dark ×390/2560px32조건, 짧은 높이/2x device scale4조건, 프로젝트 목록/상세 ×390/768/2560px6조건, 총42조건 | 문서 가로 overflow0·workspace 경계 일치·내부80rem 상한. 넓은 저장 대화의 transcript/composer 중심 오차0. |

- 실제32개 저장 메시지에서 wheel로 기록만 이동하고 입력창·외부 page 위치는 유지됐다. 두 줄 입력과 Shift+Enter, mobile history의 Escape/outside dismissal, draft 보존·trigger focus 복원을 확인했다. 전역 서비스 navigation과 채팅 history 각각 펼침/접힘4조합도 확인했다.
- 844×390 새 대화에서 관찰한 welcome/프로젝트 선택 잘림은 safe centering과 workspace 내부 scroll로 수정했다. 960×500의 deviceScaleFactor2는 실제2x 렌더링 증거이며 browser-native200% zoom으로 표현하지 않는다.
- `npm --prefix frontend run build` exit0, Vite8.2.2·frontend1.30.12. 기존 `DocCodeBlock`·`ProjectUsageTable`의 noninteractive tabindex 경고2종은 유지됐다. 전체 type check·`npm run test:gate`는 이 수정에서 실행하지 않았고 이전 세션의 gate를 이번 수정 성공으로 소급하지 않는다.
- Identity/API는 합성 fixture다. 최종 compiled 실행의 JS exception0·미지원 API 응답0·자원 mutation0을 관측했다. 화면 전환 중 context-preview 취소와 embedded font request diagnostics는 별도로 보존하며, 최종 `document.fonts`는 loaded/error0이었다. 실제 Keystone 권한·provider/과금·운영 배포 성공 증거가 아니다.
- Architecture guard는 HEAD+현재 chat source5파일의 임시 index에서 stamp와 `--staged`를 통과했다(`437992ae2c0baa32534efe7704a982f6f9f162977ee76205181b6c306018057a`, source2601files). 실제 공유 index/review marker를 보존하고 전체 동시 WIP의 qualification으로 확대하지 않는다. GBrain은 PATH의 CLI 부재로 sync하지 않았다.

영구 증거: [`source-browser.json`](../openspec/changes/archive/2026-10-11-restore-chat-full-viewport/evidence/source-browser.json), [`compiled-browser.json`](../openspec/changes/archive/2026-10-11-restore-chat-full-viewport/evidence/compiled-browser.json), [`architecture.json`](../openspec/changes/archive/2026-10-11-restore-chat-full-viewport/evidence/architecture.json). 같은 디렉터리의 WebP는 합성 로컬 화면이며 기존 운영 가이드 캡처를 대체하지 않는다. 보관 경로는 CLI가 출력한 날짜를 사용한다.

후속 **전체 변경 커밋 qualification**은 구현 소유 세션과 별도다. 공유 checkout의 첫 `npm run test:gate`는 비공개 `afterglow.conf`의 `TOMLDecodeError`(line10,column9)로 backend collection 전에 exit4였다(`artifact://509`). 설정을 수정·복사하지 않고 현재 의도된 변경의 exact tree `4c4c050ca830ab9ee81c9c8e9217e6910a4fe16a`를 기존 격리 checkout에 설치했다. 별도 소유 `afterglow-remaining-commit-gate-bkjlix`의 loopback MariaDB/PostgreSQL/Redis만 원래 runner override로 제공한 전체 `npm run test:gate`는 exit0이었다(`artifact://515`): orchestration175, Kolla Node27/Python11, Unix installer20, backend5003, frontend342files/2914와 runner9, contract174, functional118/23deselected, Ruff check·format574files. 기존 PowerShell36skip·두 frontend tabindex 경고와 backend 경고는 숨기지 않는다. Source fingerprint는 위 scoped proof와 같은 `437992ae2c0baa32534efe7704a982f6f9f162977ee76205181b6c306018057a`/2601files이며 chat source5파일도 compiled-browser receipt와 byte-identical이다. 임시 index credential scan은 no leaks였고 private env/config/key·기존 다른 datastore/volume·운영 DB/IAM/배포는 변경하지 않았다. 이 결과는 snapshot 이후 동시 작업이나 운영 acceptance를 인증하지 않는다.

## 로컬 Compose 복구·임시 컨테이너 정리 (2026-10-12)

사용자가 기존 로컬 DB 복구를 선택한 뒤 ignored `.local-services/compose.env`의 Drover·Lumen·Waygate URL 세 값만 기존 worker 대상에 맞췄다. 사용자가 주석 처리한 `.env`와 원래 키·private 설정은 보존했다. Plain/prepared/명시 local 입력의 실제 Compose 14개 DB 소비자를 확인했으며 공개 Compose·Dockerfile·서비스 코드·schema는 변경하지 않았다. 조사 중 동시 로컬 재기동에서 네 migration/bootstrap exit0와 현재 서비스 healthy를 관측했으므로 중복 up/build는 하지 않았다.

- **승인된 삭제**: 중지 컨테이너19개·빈 network9개를 제거하고, 추가 사용자 선택으로 실행 QA19개를 정상 중지·제거한 뒤 해당 network5개를 제거했다. 총 컨테이너38개·network14개를 exact ID로 정리했다. Force removal·volume 삭제·광역 prune은 없으며 승인된 tmpfs datastore9개의 내용은 폐기됐다.
- **보존 증거**: 컨테이너59→21개(실행17개·성공한 migration/bootstrap4개), network20→6개다. 현재 개발 스택·별도 sandbox·BuildKit의 ID·PID·StartedAt·restart count·mount·host port·network를 보존했고 전체 volume25개의 이름이 불변이다. 이미지·빌드 캐시는 정리하지 않았다.
- **네트워크와 실제 실행**: `afterglow-remaining-commit-gate-bkjlix_default`의 `172.30.0.0/16` 충돌 bridge를 제거했다. 현재 개발 network `172.18.0.0/16`는 유지한다. 정리 후 Drover `/v1/health/ready`는 HTTP200 및 database/redis/migrations/keystone 모두 `ok`였다. Backend/frontend와 각 sibling의 실제 liveness도 HTTP200을 확인했다.
- **검증 한계**: 정리 후 `npm run services:smoke`는 direct readiness·Lumen API contract 이후 `AFTERGLOW_SMOKE_TOKEN` 미설정으로 exit1이다. 인증 BFF/dashboard 전체 성공이나 운영 qualification으로 표기하지 않는다. Ledger/schema 비교는 동시 재기동 후 관찰 구간의 불변 증거이며 재기동 전 상태 보존을 증명하지 않는다. 이 운영 정리는 source 변경이 아니므로 전체 unit/contract/functional gate를 새로 실행하지 않았다. 운영 DB·IAM·배포는 변경하지 않았다.

증거: [`recover-local-compose-db-targets`](../openspec/changes/archive/2026-10-12-recover-local-compose-db-targets/)의 `evidence/runtime.json`, `evidence/cleanup.json`과 rollback한 두 endpoint 이동 시험 receipt. 이 host-only 정리는 서비스 ownership·정본 Compose·schema·DB 목적지 선택 계약에 구조 영향이 없다.

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

   **독립 전체 suite 후속 결과**: Backend unit 전체4990개(`tests/backend-unit-summary.log`, 원문 artifact220)와 원래 `npm run test:functional` 전체118개/23deselected가 통과했다. Functional 첫 실행은 동시 personal-expiry migration test가 MariaDB CHECK의 실제 `OperationalError4025`를 `IntegrityError`로 기대하여116passed/2failed였다. 이미 공유 source에서 수정된 사용자 test를 그대로 frozen snapshot에 복사한 최종 suite만 통과로 집계하며, 이 작업에서 무관한 test/code/SQL을 수정하지 않았다. 세 source overlay(model/authority/기존 migration test)의 hash·실제 owned MariaDB/PostgreSQL/Redis14와 실패/성공 로그는 `tests/final-functional.json`에 남긴다. 이 독립 성공을 PTY에서 중단된 전체 gate 성공으로 합치지 않는다.
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
## GPU admission service scope (2026-10-12)

기준은 `9cbfecad419b7d6c64e3a21b06a0cd80b1f44f93`(`v1.30.12` peeled commit)이며 canonical `npm version 1.30.13 --no-git-tag-version`/`version:check`로 patch manifests를 동기화했다. Focused36+14+14, K3s backend16/frontend9와 instances backend548/frontend209가 **test-passed**다. 최종 `npm run test:gate`도 통과했다: backend unit4431, frontend2569/334 files, contract174, functional35(9 deselected), Ruff check·561 files format check. Working architecture stamp와 staged check는 source SHA256 `33260ee0e5fe8c357dd4d3fe658313680068e01318be0cee78694fbc506f0a0e`/2531 files로 통과했다. Artifact qualification·rollout·deployed HTTP acceptance는 pending이며 과거 release 기록을 재사용하지 않는다. [Checklist](../openspec/changes/gpu-admission-service-scope/tasks.md)는 실제 완료된 단계만 기록한다.

Parent가 이미 관측한 수정 전503은 재현 근거로 보존한다. 이를 확인하려고 같은 실패를 다시 실행하지 않는다. 아래 native 계획의 대상 acceptance는 **HTTP200과 `gpu_required=true`**다. 실제409는 quota fail-closed 증거일 뿐 acceptance 통과가 아니며 실측 headroom 부족을 blocker로 보고한다.

### Source와 authored coverage

- [`internal_k3s.py`](../backend/app/api/internal_k3s.py)의 `k3s_gpu_admission`·`_get_project_flavor`: DB policy service-project 인증, 요청 project의 native public/private flavor access, empty specs 명시 조회, metadata/access 실패503, token401·문자열ID400·schema422·quota409·authority503. [`test_internal_k3s_gpu_admission.py`](../backend/tests/test_internal_k3s_gpu_admission.py)는 service scope와 요청 project의 차이, shared/unshared flavor, fail-closed 응답 및 connection 정리를 정의한다.
- [`gpu_inventory.py:require_gpu_quota`](../backend/app/services/gpu_inventory.py)는 `project_id`를 keyword-only로 요구하며 인증 scope에서 대상 project를 추측하지 않는다. [`test_gpu_quota_resilience.py`](../backend/tests/test_gpu_quota_resilience.py)는 explicit project 전달·기존 alias/CPU/GPU 계약과 일반 instance admission caller를 다룬다.
- [`gpu_quota.py`](../backend/app/services/gpu_quota.py)의 `get_effective_gpu_quotas`·`_get_project_gpu_usage`·`check_gpu_quota`, [`test_gpu_quota_service.py`](../backend/tests/test_gpu_quota_service.py): DB default/project merge, 미설정/0 거부·-1 무제한, own-project listing 대 cross-project `all_projects=True, project_id=<target>` listing, iteration 중 policy 실패·소유권 불명·다른 project 제외·embedded flavor specs와 metadata fail closed. DB quota 정본이나 alias 규칙을 바꾸지 않는다.

아래 target5개와 최종 `test:gate`를 실행·통과했다:

```bash
npm run test:target -- backend:tests/test_internal_k3s_gpu_admission.py
npm run test:target -- backend:tests/test_gpu_quota_resilience.py
npm run test:target -- backend:tests/test_gpu_quota_service.py
npm run test:target -- k3s
npm run test:target -- instances
npm run test:gate
```

최종 source를 검토한 뒤 architecture working stamp·staged check와 전체 gate를 통과했다. Unit/consumer fixtures 통과만으로 실제 Keystone 정책·Nova visibility·운영 DB usage 또는 deployed source를 증명하지 않는다.

### Candidate source with native providers — not deployed HTTP

보호된 `afterglow_backend`의 별도 Python 프로세스에서 candidate API·quota 함수를 메모리로 로드하고 실제 runtime DB, canonical policy factory, Keystone와 Nova를 사용했다. 서비스 인증 UUID는 `dc73b4e609414046bf9c07014e1927a6`, 대상은 `99f2f82cb2d14788a0723af31c16dab0`이다. Exact flavor `fe5a5a4c-a568-481d-982b-469967f64808`의 alias는 `RTX-3060-LHR:1,GA106-audio:1`; 정규화 quota `RTX3060LHR=-1`, 대상 usage0이었다. In-process ASGI POST200/`gpu_required=true`, header 없음/잘못된 token401, malformed project/flavor400, 필수 필드 누락422를 확인했다. 독립 `NativeTenantExec`에서도 같은 flavor의 visibility·specs와 대상 서버0을 확인했다. Quota·membership·sharing·capacity·VM 변경0이다. 초기 probe는 DB teardown 누락 경고가 있었지만 후속 probe는 `finally: await close_db()`로 종료했고 warning 없이 exit0이었다. 이 proof는 실제 providers에 대한 candidate 실행이며 running API 교체·deployed HTTP acceptance가 아니다.


### How to run the protected native smoke after gates and rollout

**실행 순서와 보호 경계:** Parent integration gates와 승인된 artifact qualification/rollout가 끝나기 전에는 smoke하지 않는다. Native smoke는 `functions.NativeTenantExec`(native test-project connection)와 `functions.NativeHostExec`(승인 controller의 보호된 SSH)을 사용한다. 이 환경의 `NativeOperatorExec`는 controller1의 `drover_api` 안에서 standalone Python을 실행하며 `conn`을 주입하지 않으므로 기존 operator connection이 있다고 가정하지 않는다. 필요한 operator/service SDK connection은 아래처럼 Afterglow runtime의 canonical DB policy factory로 만든다. 일반 shell/curl·credential-reader·openrc 출력으로 대체하지 않는다. 토큰/password/config 전체·SDK 객체·HTTP headers/body 전체·raw exception/traceback/exception chain을 도구 인자·출력·로그에 넣지 않는다. TLS 검증을 유지하고 HTTP redirect·proxy·retry·wire debug를 끈다. 실패 출력은 고정 code·HTTP status·pass/fail만 허용한다.

Rollout도 별도 승인 작업이다. `/etc/kolla/globals.d/90-openstack-afterglow-globals.yml`의 **`afterglow_backend_image_ref`만** 승인한 GHCR immutable digest로 pin하고 다른 image refs/config/secrets/volumes를 보존한다. 실제 executable은 `/etc/kolla/.venv/bin/kolla-ansible`이다. 기존 operator SSH identity에서 `/etc/kolla`를 cwd로 `/etc/kolla/.venv/bin/kolla-ansible prechecks -i multinode --tags afterglow` 후 `/etc/kolla/.venv/bin/kolla-ansible reconfigure -i multinode --tags afterglow`를 사용한다. `NativeControlExec`는 standalone operator Python이며 `NativeOperatorExec`의 container namespace와 다르다. Parent는 실제 deployed digest/revision, backend readiness, preserved configuration과 rollback 지점을 확인한 뒤 아래 deployed smoke를 시작한다.

고정 대상은 flavor **`fe5a5a4c-a568-481d-982b-469967f64808`**와 기존 **`test` project `99f2f82cb2d14788a0723af31c16dab0`**다. Candidate service-scope visibility와 독립 tenant visibility/specs는 확인했다. 최종 deployed smoke에서도 native access와 실제 UUID를 다시 확인한다. Smoke는 읽기와 reservation 없는 admission POST만 수행하며 quota·membership·flavor sharing·capacity·VM/nodegroup/volume을 생성/변경/삭제하지 않는다.

1. **NativeHostExec — identity/access 기준선:** 보호된 `docker exec afterglow_backend` Python 프로세스에서 runtime DB를 초기화하고 `await resource_policy_store.get_service_project_connection()`으로 service SDK connection을 만든다. `conn.identity.find_project("test", ignore_missing=False)`를 조회하고 반환 UUID를 이후 모든 요청의 `project_id`로 고정한다. `conn.compute.get_flavor("fe5a5a4c-a568-481d-982b-469967f64808")`, `conn.compute.get_flavor_access(flavor_id)`를 새로 읽는다. Private flavor라면 `tenant_id` 또는 `project_id`에 test UUID가 실제 있는지 확인한다. Extra specs가 비어 있으면 `conn.compute.fetch_flavor_extra_specs(flavor)`로 명시 조회한다. UUID·public 여부·`shared_to_test` boolean·정규화 GPU alias/count만 기록한다. Administrator가 flavor를 읽었다는 것만으로 shared 확인을 통과시키지 않는다. Connection과 DB engine은 종료 시 닫는다.
2. **NativeTenantExec — 독립 tenant 확인:** 현재 authenticated project가 위 test UUID인지 확인한 뒤 `conn.compute.flavors(is_public=None)`에서 같은 flavor ID가 보이는지 확인하고 `get_flavor` 및 필요한 `fetch_flavor_extra_specs`로 실제 GPU specs를 읽는다. 인증·visibility·metadata 실패는 고정 실패 code로 중단하며 관리자 connection으로 대체하지 않는다. Flavor를 Nova 생성 가능한 것처럼 mock하지 않는다.
3. **NativeHostExec — deployed service/DB 실제 상태:** 보호된 `docker exec afterglow_backend` Python 프로세스 안에서 `app.config.get_settings()`와 `app.database.init_db(settings.database_url)`로 **현재 runtime DB**를 사용하고, `await resource_policy_store.get_service_project_connection()`으로 policy connection을 만든다. 동기 SDK `conn.session.get_project_id()`로 인증 UUID가 DB `openstack.service_project`와 같은지 확인한다. 정책이 test와 다르면 authenticated UUID가 test가 아닌 것도 확인한다. 요청 UUID를 password scope로 전달하지 않는다. `_get_project_flavor(conn, test_id, flavor_id)`와 `await gpu_quota.get_effective_gpu_quotas(conn, test_id)`, `await gpu_quota.get_project_gpu_usage(conn, test_id)`, `await gpu_quota.get_effective_gpu_quota_status(conn, test_id)`로 실제 default/project merge와 alias별 `limit/in_use/available`를 기록한다. Connection과 DB는 `finally`에서 `conn.close()`·`await close_db()`로 정리한다. SQLite/mock DB, cached dashboard quota 또는 service-project usage를 증거로 쓰지 않는다.
4. **NativeTenantExec ↔ NativeHostExec — usage 교차 확인:** Tenant에서 `conn.compute.servers(details=True)`를 완전히 소비한다. Runtime의 cross-project query는 `details=True, all_projects=True, project_id=test_id`와 각 server의 `project_id`/`tenant_id` 검사를 사용한다. 양쪽에서 counted 상태(`ACTIVE`, `BUILD`, `MIGRATING`, `PASSWORD`, `PAUSED`, `REBUILD`, `REVERT_RESIZE`, `RESIZE`, `SHUTOFF`, `SUSPENDED`, `VERIFY_RESIZE`)와 flavor GPU alias/count를 대조한다. Embedded `original_name`+`extra_specs` snapshot을 보존하며 name을 flavor UUID로 재조회하지 않는다. 공개 결과는 alias별 합계·일치 boolean만 남긴다. 알 수 없는 ownership/metadata, policy 거부, generator 후반 실패는503/fail-closed이고 usage0으로 대체하지 않는다.
5. **NativeHostExec — 실제 HTTP admission:** 위와 같은 runtime 안에서 token을 `settings.k3s_gpu_admission_token`으로 읽어 `X-Afterglow-K3s-Admission-Token` header에만 넣는다. 실제 설정된 backend upstream 또는 native catalog endpoint의 `/api/v1/internal/k3s/gpu-admission`에 `{"project_id":test_id,"flavor_id":"fe5a5a4c-a568-481d-982b-469967f64808"}`를 POST한다. URL은 승인한 실제 upstream을 보호된 조회로 확정하며 `localhost:8000`을 가정하지 않는다(backend API 주소18000과 VIP8000은 서로 다를 수 있다). `await require_gpu_quota(conn, flavor, project_id=test_id)`의 실측 decision과 비교한다. **대상 acceptance는 HTTP200/`gpu_required=true`만 통과**다. 모든 요청 alias의 실측 `limit=-1` 또는 양수 limit에서 `in_use+requested<=limit`을 확인한다. 실제 부족/미설정/0의409는 올바른 fail-closed 증거이지만 target acceptance는 **blocked: real quota headroom unavailable**로 남긴다. 200을 만들기 위해 quota·capacity·membership·sharing을 바꾸거나 다른 flavor/CPU fallback으로 대체하지 않는다. 동시 외부 mutation으로 값이 달라지면 fresh quota/usage를 다시 읽어 시각을 기록하고 비교 불가를 통과로 쓰지 않는다.
6. **NativeHostExec — 부작용 없는 negatives:** 같은 endpoint에서 (a) header 없음·의도적 잘못된 token 각각401, (b) 올바른 내부 header와 `project_id="../test"` 또는 `flavor_id="../flavor"` 각각400, (c) 필수 필드 누락 또는 ID의 잘못된 타입422를 확인한다. Operator가 **기존 private flavor 중 test access가 없는 ID**를 읽기만 해서 선택한 뒤 올바른 header/test UUID로 POST하면400이다. Negative용으로 shared flavor를 unshare하거나 membership을 제거하지 않는다. 안전한 기존 unshared fixture가 없으면 해당 live negative는 미검증으로 남기고 authored regression으로 대체 통과시키지 않는다. Visible CPU flavor도 기존 catalog에서 골라200/`gpu_required=false`를 확인할 수 있지만 GPU positive를 대신하지 않는다.
7. **판정과 보존:** 비밀 없는 receipt에는 deployed digest/revision·target UUID/flavor ID·실제 native shared/tenant-visible boolean·alias별 real limit/in_use/requested·HTTP status/`gpu_required`·negative 결과·확인 시각·보존 항목만 남긴다. Quota/membership/access 기준선을 다시 읽어 smoke가 변경하지 않았음을 확인하며 외부 변경이 있으면 구분한다. Service credential tenant rescope와 DB/Keystone/access/metadata/usage 장애는 hermetic authored tests로 다루고 live datastore/Keystone를 일부러 중단하지 않는다. 모든 probe는 예외를 내부에서 잡아 고정 실패 code만 출력한다. 원문 오류를 출력하거나503을 허용/usage0으로 바꾸지 않는다. 통합·rollout·HTTP200/`gpu_required=true`와 negatives의 실제 native proof가 모두 기록될 때까지 change를 verified archive하지 않는다.

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

## 2026-10-12 인스턴스 생명주기·스토리지 연결 검증 (local, not deployed)

`instance-lifecycle-storage-clarity`의 일곱 요청을 현재 dev source에서 구현했다. 기존 Windows 초기 비밀번호/GPU correction은 보존하며 두 변경 모두 미커밋이다. Private `afterglow.conf`는 TOML parse 오류가 있어 수정하지 않고, canonical selector를 owned scratch cwd + explicit backend project/PYTHONPATH에서 실행했다. 실제 shared index·운영 설정·VM·볼륨·키는 변경하지 않았다.

| 검증 | 관찰 결과 |
|---|---|
| Exact changed-path pytest | 361 passed |
| Canonical instances | backend1064 / frontend506 passed |
| Canonical storage | backend615 / frontend76 passed |
| Required access target | backend285 / frontend15 passed; 이번 current source의 owner/access proof이며 이전 Windows archive digest와 동일한 snapshot이라고 주장하지 않음 |
| Final focused frontend + public-guide contracts | 26 files /380 passed |
| Final design target | 27 files /138 passed |
| Expansion polling regression | 원래 실패, scalar-derived scope/state projection 수정 후43 related tests passed |
| Final Svelte check | 0 errors /3 existing warnings |
| Final i18n check / scan | 0 errors /0 warnings, 37 namespaces /9575 source messages; hard-coded Korean0 in989 files |
| Production frontend build | exit0; 최종 QA는 전체 current frontend source를 owned immutable copy에서 다시 build/serve |
| Changed Python Ruff / format | check0 /12 files already formatted |
| Native API/SDK HTTP | current-source Uvicorn + installed SDK/Manila transport, synthetic loopback providers의35 scenarios passed |
| Compiled consumer/admin UI | 4 locales ×2 themes ×7 widths ×2 modes =112 conditions; document/changed volume-storage/hashed-metadata boundaries overflow0 |

Native proof는 metadata-only Windows reader/다른 creator 접근, Windows-looking Linux 이름, exact NFS fixed IP/ambiguity/CIDR/floating/foreign/reader rejection, UUID-bound CephX, GET secret exclusion, explicit no-store secret retrieval, unmanaged protection, empty-list-versus-exact-rule pending/error404 fence, VM delete-before-revoke 차단, strict integer/shrink/live-task/fractional raw SDK power rejection과 Cinder500GB/extending actual reread를 확인했다. Native tracking PUT 전에 SDK `set_server_metadata(server, **metadata)`의 positional-dict 오류가 발견되어 수정됐다.

Compiled UI는 동일 Button 규격, stop confirmation의 conditional quota 안내, SHUTOFF action grouping, Windows keypair 숨김과 Linux keypair 유지, exact NFS/Ceph form, transient secret 조회/clear/no-persistence, reader guard, root600/data80 요청 뒤 actual500/50GB extending 표시를 확인했다. Same-context30s polling이 volume draft를 닫는 회귀를 먼저 재현했고 수정 후 실제 polling 동안600 draft가 유지됐다. 새 hashed grant metadata key가 기존 metadata table을 늘리던 문제도 key wrapping으로 수정했다. 네 locale의 공개 Nova 가이드에서20–30분 안내를 실제 렌더링했다.

이전 Windows rollback의 추가 helper-level proof는 정확한 UUID를 existing `rollback_instance` → installed SDK → loopback Nova에 전달하고 native `POST forceDelete` 및 synthetic provider 부재를 확인했다. Existing delete wrapper가 force=True이므로 DELETE-only counter의0건은 cleanup 미호출 증거가 아니다. 이 결과는 완전한 create-failure orchestration 또는 실제 guest/production rollback proof가 아니다. 비밀 오류 masking은 기존 unit coverage와 구분한다.

전체 `npm run test:gate`, 실제 IAM/auth·provider capacity/physical quota 집계, live Windows first boot/password/RDP, 실제 NFS/Ceph mount/data-plane와 Cinder 완료·guest partition/filesystem growth, production/배포는 미실행이다. 기존 모바일 performance-monitoring toolbar의 자체 overflow는 이번 일곱 요청 범위 밖으로 유지했으며 전체 page의 모든 component overflow0를 주장하지 않는다. Intermediate mutable shared frontend build가 runtime chunk를 교체해 SSR500을 냈으므로 그 실행은 성공 증거에서 제외하고 immutable copy로 다시 확인했다.

Durable raw receipts: `~/.local/share/afterglow-proofs/instance-lifecycle-storage-clarity-20261012-j8ec2ih6/`의 `canonical-targets.log`, `frontend-final-tests.log`, `frontend-final-check.log`, `frontend-isolated-build.log`, `i18n-final.log`, `python-style.log`, `native-http.json`, `compiled-ui.json`, `rollback-native.json`와 privacy-safe consumer/admin screenshots. OpenSpec evidence에는 source overlay와 scoped architecture guard 결과를 별도로 보관한다.

## 2026-10-13 KST Palimpsest block transport 검증 (local, not deployed)

Afterglow dirty `dev` HEAD `aac6b9c5dc3e53fc3e430ca9ed96c30cacdbdb1e`의 block slice다. 실제 index·MCP/operator의 다른 WIP·private `afterglow.conf`·운영 서비스는 보존했다. Proof directory의 SHA 접두사는 시도 이름이지 immutable source attestations가 아니다. Shared Palimpsest checkout은 별도 `aa397a0fd976e35302974a347748a9773e3084bf`이고 게시된 Hub0.3.3 source는 `7186abf7844454eda7ed86a215192b33b9250ff8`이다.

| 실행한 검증 | 관찰 결과 및 범위 |
|---|---|
| Layer/API/ordinary single-bulk deletion 선택 node | 326 passed; 전체 backend gate가 아님 |
| 최종 SDK runner + durable cleanup selector | 97 passed; local fixture imports로 test-module plugin/global-name 충돌 제거 |
| 실제 MariaDB source DELETE/publication 경쟁 | 4 passed; NOWAIT lock·반복 request cancellation·publisher404/원본 보존 경계. Manila mutation은 synthetic |
| Linux guest helper selector | 91 passed, ext4 fixture prerequisites 포함. 실제 kernel proof와 별도 |
| Required access backend selectors | 285 passed; 같은 canonical 파일 목록을 config-discovery 없는 scratch cwd에서 실행 |
| Additive migration088/089 actual DDL | owned legacy-schema mirror에서 기존 row·old writer의 NFS/null·새 block JSON commit/reread 확인; canonical runner/운영 rollback 증거 아님 |
| Canonical Dockerfile image build/execution | backend/worker/frontend arm64·amd64 완료. Python3.12.15/UID1000, Node20.20.2/UID1001, backend OpenTofu1.8.3·Ceph18.2.7 실행 |
| Final image source match | 두 architecture backend/worker의 selected block app16파일이 현재 source bytes와 일치. Frontend는 unchanged runtime만 확인; 전체 WIP/source 승인이 아님 |
| Canonical local app liveness | isolated Compose의 backend/frontend health200 및 실제 Redis PONG. Route harness의 auth/readiness와 혼동하지 않음 |
| TCP API→native installed SDK→실제 MariaDB | synthetic provider/auth/policy로 source2개 게시, 정상/accepted-response-loss consume2개, lost run의 Nova CREATE1회, pending의 API restart 유지·discovery/recovery·exact cleanup 통과 |
| HTTP immediate import admission | 두 import의 admin422/nonadmin403, DB/provider mutation0 및 importer URL-open attempts0 확인 |
| Actual CPU-only Linux guest | kernel6.1.0-53-amd64/TCG: first boot, lower와 upper 장치명 변경 후 persistence, writable lower 거부, serial 없는 duplicate upper FSUUID 거부4조건 통과 |
| Changed Python style | scoped Ruff check 성공; 새/관련11파일 format check 성공 |
| Scoped architecture guard | HEAD+33명시 overlay,2,628files, `19474e68e7f701a66451693c49433968f2e491a741cc2d6c39bd93d7eecd7c7e`; isolated staged guard와 real index byte 보존 |

HTTP proof는 canonical backend image에서 production routers·SQLAlchemy factory·native SDK를 Uvicorn TCP로 실행한다. 인증 principal/admin, resource snapshot, Glance member visibility 및 console health는 **synthetic**이며 full `app.main` 인증/ready·Redis·guest proof가 아니다. 원본 SquashFS 파일2개의 magic/hash/길이를 전달했고 source UUID/identity는 restart 전후 유지됐다. Provider counters는 image2/volume4/port2/server2 CREATE와 같은 exact DELETE이며 최종 server/volume/port0이다. Lost-response server는1회만 CREATE됐다. 공유 Glance source 정리는 explicit external synthetic-only helper이며 production source-retirement API나 DB source pointer 삭제의 증거가 아니다.

실제 QEMU guest는 생성된 production lower/upper helpers와 root local-bottom hook을 변경 없이 실행한다. Raw readonly virtio lower를 직접 SquashFS로 mount하고 `/` OverlayFS, child precedence·whiteout·bootstrap cloud-state bind와 ext4 upper write를 관찰했다. 두 번째 cold boot에서 upper도 `vdc→vdd`로 바뀌었지만 같은 Cinder serial/ext4 UUID로 데이터가 유지됐다. Negative 조건은 success marker 없이 실제 guard 오류를 확인했다. Minimal synthetic BusyBox root와 external first-format harness를 사용하므로 Ubuntu cloud-init/사용자·SSH·provider Cinder/RBD/physical COW·quota 또는 native KVM/보안/ownership fidelity의 증거로 확장하지 않는다.

중간 실패를 성공으로 지우지 않는다: 빈 root exports가 YAML null이 된 renderer를 quote했고, build-host의 존재하지 않는 runtime config copy와 prereqs 부작용을 제거했다. 실제 initrd/boot에서 missing squashfs module을 발견해 source hook에 squashfs/overlay/ext4를 명시했다. Proof-only Bash local-top의 sh validation, 기존 symlink, BusyBox가 대신 선택한 `mkfs.ext4` 오류는 외부 harness에서 POSIX hook·고유 실제 mke2fs 경로/정상 config로 수정했으며 production에 fake UUID/formatter를 넣지 않았다. 새 SQL race의 최초 barrier가 `_reserve` 뒤를 기다려 timeout 났으므로 먼저 잡히는 `_locked` 진입을 관찰하도록 수정한 뒤4조건을 통과했다. Missing fixture와 Ruff import/shadow warnings는 local fixture exports로 수정했다. 로컬 TOML parse 오류는 고치거나 우회된 운영 설정으로 주장하지 않고 안전한 scratch에서 같은 source/selectors를 실행했다. 마지막 DB rerun은 stopped owned service/잘못된 relative Compose 경로에서 실패한 뒤 exact owned MariaDB만 시작해4조건을 다시 통과했다.

독립 initial lifecycle review의 grant bypass·stale rejection overwrite·cancelled DELETE lock release·late FIP discovery4건은 수정/실행 회귀로 해소했다. Guest/import re-review는 pre-planner rejection과 initramfs dependency correction에 새 finding이 없었다. Lifecycle reviewer의 후속 응답은 과거 snapshot을 재서술했으므로 post-fix independent clean signoff로 세지 않는다. Astra planning/ops 역할도 제공되지 않았으며 대체 승인하지 않는다.

전체 `npm run test:gate`, frontend/UI 재검증, production schema/mixed writer/rollback, 실제 Glance membership acceptance·Cinder COW clone/readonly Nova attachment·Ubuntu cloud-init/SSH와 Hub0.3.3 cutover는 **미실행**이다. 원본 `test-openrc.sh` SDK401(`req-4c47fa98-68e1-46a2-a203-3a722bb3790f`) 뒤에는 로그인 재시도·IAM/password 변경·service/admin 대체·cloud resource 생성/원격 helper 전송·writer fencing/paired restore/운영 rollout을 하지 않았다. SDK가 원본 계정/project로 token을 메모리에서 정상 발급한 뒤 actual roles/service capability와 승인된 recovery 순서를 확인해야 live 작업을 진행한다. 수동 token 파일을 요구하지 않는다.

Receipts: `~/.local/share/palimpsest-proofs/block-transport-aac6b9c5-20261013/`의 `http-state/receipt.json`, `canonical-image-final-runtime.json`, `guest-results.json`, 네 guest serial logs, `generated-files.json`, `migration-smoke.json`, `scoped-architecture-review.json`. Shared architecture markers는 관련 없는 WIP를 덮어쓰지 않는다. Parent Palimpsest working guard는 앞선 refresh checkpoint에서 stale였으며 이번 docs-only 변경으로 broad restamp·새 parent-source 승인을 하지 않았다. 현재 PATH에 Gbrain CLI가 없어 sync/guidance 변경은 하지 않았다. 모든 throwaway/proof scripts는 repository 밖에 있다.


## 2026-10-14 KST 프로젝트·도메인 간 볼륨 이전 검증 (local, not deployed)

`add-cross-domain-volume-transfers` 변경은 공유 dirty `dev` working tree에서 구현했다. 실제 index·private `afterglow.conf`·다른 WIP·운영 Cinder/Keystone은 변경하지 않았다. Private TOML이 backend config-discovery를 막지 않도록 backend selector는 scratch cwd + 명시적 `PYTHONPATH`로 같은 source를 실행했다. Frontend는 변경 13파일을 보존한 immutable scratch copy에서 build/serve했고 source SHA-256 parity를 확인했다.

| 실행한 검증 | 관찰 결과 및 범위 |
|---|---|
| Exact transfer/owner/volume pytest | 수정 전 4 failed/97 passed, 수정 후 102 passed |
| Canonical storage target | backend 821 passed / frontend 16 files 165 passed |
| Required access target | backend 326 passed / frontend 4 files 38 passed |
| Changed Python Ruff check·format | check 성공 / 6 files already formatted |
| i18n check / scan | 0 errors·0 warnings, 40 namespaces·9,920 messages / hard-coded Korean 0 in 1,072 files |
| Production frontend build | exit 0 |
| Svelte check | transfer 파일 진단 0. 기존 범위 밖 `dashboard/database/instances/+page.svelte` PageState 오류 1·경고 3으로 exit 1 |
| Actual Uvicorn TCP → installed openstacksdk 3.3.0 → loopback Keystone/Cinder | 31 HTTP assertions, 132 native requests, operator Cinder mutation 0, operator connection 16/16 close |
| Compiled Chromium | source create·ID/key clipboard·own cancel, empty destination 외부 도메인 수신, 같은 도메인 프로젝트 수신, 4 locale×2 theme×6 width의 48 조건/96 상태 overflow 0 |

Native proof는 같은 도메인과 다른 도메인 모두 생성 → 정확한 ID 조회 → 실제 출발 project/domain readback → Cinder `InvalidAuthKey` 400의 403 매핑과 원본 소유 유지 → reader 403·출발=대상 409 → destination scope 수락 → 실제 native owner/available 확인 → 반복 조회·수락 404를 확인했다. 다른 프로젝트 취소는 403, 소유 취소는 available 복원, 연결 볼륨 생성은 409이며 자동 분리하지 않았다. 관리자 UI가 다른 프로젝트를 선택해도 home scope가 아닌 선택 project credential로 수락됐다. 수락 후 응답을 끊으면 POST 1회만 전송되고 실제 이동한 소유권과 source/destination cache 무효화가 관측됐다.

초기 integration에서 SDK 3.3.0이 microversion 3.55 이상에서 `/volume-transfers`를 사용함을 harness가 404로 드러내 fixture가 old/new native path를 모두 강제하도록 정정했다. Transfer POST retry 0은 copied Proxy 속성만으로 적용되지 않아 `Proxy.request` partial로 수정했고, 실제 연결 끊김 회귀가 create/accept 각각 POST 1회를 확인한다. 브라우저에서는 모든 native 403을 잘못된 키로 표시하던 문제를 발견해 서버의 실제 사유를 보존하도록 고쳤다. Headless Chromium의 clipboard 권한 거부는 inline manual-copy 복구 화면으로 관찰했고, 권한 부여 후 ID와 키 복사 값을 확인했다.

Identity·Keystone·Cinder 응답은 synthetic loopback이며 실제 IAM/policy, Cinder backend의 데이터 이전·스냅샷/암호화 볼륨, 운영 operator 권한, 혼합 버전, 배포는 검증하지 않았다. 전체 `npm run test:gate`는 실행하지 않았다. Receipts: `~/.local/share/afterglow-proofs/volume-transfer-20261014-c7nvejts/`의 `native-http.json`, `native-http-*.log`, `compiled-lifecycle.json`, `compiled-same-domain.json`, `compiled-matrix.json`, `source-parity.json`, `*-backend.log`, `*-frontend-final.log`, `create-to-cross-domain.mp4`, `issued-final.png`, `receive-*.png`.

## 2026-10-15 KST Palimpsest Hub workspace 검증 (local, not deployed)

공유 dirty `dev`의 관찰 HEAD는 `aac6b9c5dc3e53fc3e430ca9ed96c30cacdbdb1e`다. `/tmp/afterglow-hub-dashboard-80043ecf-1792007548026`의 frozen current-source snapshot에는 동시 WIP가 포함되며,28개 명시적 Hub/source/test/locale 파일의 현재 bytes와 snapshot SHA-256 일치를 따로 확인했다. `80043ecf`는 attempt label이지 source commit attestation이 아니다. 실제 index·공유 architecture marker·private 입력·다른 서비스/VM을 보존하고 commit/push/tag/운영 배포를 하지 않았다.

| 실행한 검증 | 결과와 증거 범위 |
|---|---|
| 변경 frontend API/controller/route/실제 mounted panel |4files/97passed. 초기 permission loading 뒤 actor header가 나타나지 않는 실제 회귀는 수정 전1failed, `$derived` bridge 수정 후 통과 |
| Canonical `test:target -- palimpsest design` | backend242passed, frontend design26files/128passed. Native KVM 실행 증거가 아니라 이 selector의 portable/fixture 검사 |
| Python 변경4파일 | Ruff check·format check 통과. 최초 format2파일 실패는 정정 후 최종4files already formatted와 구분 |
| Locale | i18n check0errors/0warnings,45namespaces/10,380messages; scan0hard-coded Korean lines in1,108files |
| Svelte check | 변경 경로 진단0. 범위 밖 authSession.test.ts2건·database instances PageState1건으로3errors/기존3warnings; 전체 성공 아님 |
| 전체 frontend `npm test` |381files 중375passed/6failed,23failed assertions와 unhandled401. Auth redirect/login·terminal locale·OAuth transport·mockup·chat stream 범위의 실패를 숨기거나 제외해 성공으로 만들지 않았다. 뒤의 Node runner는 앞 단계 실패로 미실행 |
| 최종 production frontend build/serve | `npm run build` exit0, actual Node adapter59214에서 아래 UI proof. Docker image proof의 대체 성공으로 세지 않음 |
| 실제 compiled Chromium |4locale×2theme×6width×3workspace144조건, 실제 viewport·`html.light`·computed surface 확인, page/main overflow0·JSerror0. 모든 identity/API 응답은 synthetic |
| Compiled mounted authority/runtime | 실제401 rotation3회: permission pending masking→확정 denial→grant recovery→directory failure 구별. Proactive expiry refresh1회 뒤 renewed-token Hub 재조회.50+1 pagination·server exact-name search·손상 SHA-256 save0 확인 |
| 실제 브라우저 다운로드 | 합성3byte `abc`를 native Chromium download로 저장하고 SHA-256 `ba7816bf…15ad`·길이3 일치.64MiB/native transport 실제 대용량 전송 또는 운영 artifact의 증거는 아님 |
| 원본 SDK/설치된 CLI→운영 Hub | 복사한 SDK inventory snippet은 원래 `pieroot/Default/test`로 image/layer ls를 exit0 실행. 다른 선택 project의 동일 snippet은 scope guard에서 exit1·stdout0. Token을 인자/파일/출력에 넣거나 service identity로 대체하지 않음 |
| 실제 native CLI profile collision | 별도 empty config/state에서 기존 alias를 유지하고 UI의 `registry add ... && login`을 실행: add exit1, 실제 CLI dispatch1회, login0·secret입력0. Endpoint/API base/IPv6 quote와 공개 UUID는 실제 compiled UI에서 확인 |
| 실제 SDK→local control web | 복사한 `web --allow-control` snippet을 원본 SDK child에서 실행하고 전용 empty state/config·`--no-browser --port59221`만 harness로 추가했다. Authenticated `/api/v1/remotes`와 legacy artifact read200. Local access nonce와 Keystone token은 출력/저장하지 않았고 VM/control mutation·운영 artifact 다운로드는 실행하지 않음 |
| Canonical Docker builds | backend/worker/frontend arm64·amd64와 review 수정 뒤 frontend 두 architecture 빌드는 exit0. Actor-header 최종 수정의 첫 재빌드는 `/_ping`500/timeout. 마지막 재시도는 arm64 BuildKit build/export/unpack DONE을 관찰했으나 CLI 종료가 확인되지 않아 취소됐고 amd64로 진행하지 못함; **최종 image/runtime qualification은 미완료** |
| Scoped architecture / OpenSpec | HEAD+28overlay만 포함한 격리 staged guard 통과: `d3e82b8c8cd90909b646be035f6b33f29cab80d71540fcc8392143876515be91`,2,633files. 실제 index hash 동일·공유 marker 보존. Change `--strict --no-interactive` valid |

### 실제 로그인·운영 변경 안전 경계

초기 격리 container login은503 `Keystone role operation is unavailable`이었다. Host의 실제 role catalog read는67개로 성공했으나 Docker control과 owned Redis data plane은 timeout/500이었다. 원본 Docker/VM/driver를 재시작하거나 기존 datastore를 지우지 않고 proof directory에 standalone Redis7.4.2를 빌드해 native Uvicorn을 잠시 실행했다. 이 별도 runtime은 canonical image qualification이 아니다.

Source 검토에서 login이 read-only가 아님을 확인했다. `default_network_enabled`는 기본true이고 `_prewarm_dashboard`가 network/subnet/router를 provision할 수 있다. `_prepare_domain_session`의 `ensure_login_access`도 domain Default project의 `project_reader` 및 managed group을 동기화할 수 있다. 초기 native 시도는 중단했고 이후 launcher는 `DEFAULT_NETWORK_ENABLED=false`와 read-only preflight를 요구하도록 했다. 실제 preflight는 **Default project 존재, 원본 사용자 direct project_reader 없음, managed projection 없음**을 확인했으므로 IAM 변경 없는 login 조건이 충족되지 않아 재시도하지 않았다. 권한을 부여하거나 함수를 우회하거나 synthetic JWT를 실제 backend에 주입하지 않았다.

두 번의 읽기 전용 snapshot(UTC20:48:42→20:55:32)은 수집한 network1/router2/subnet1·role assignment20·Default/projected-membership 필드에 차이가 없었다. 해당 network/router/subnet의 created_at은 모두10월10일로 이번 시도보다 이르다. 그러나 **최초503/중단 요청 이전 baseline이 없으므로 그 시도들의 전체 운영 무변경을 입증하지 못한다**. 이 비교는 수집 필드와 해당 시간 창에만 유효하고 router interface 등 모든 provider 상태·다른 actor 효과를 인증하지 않는다. 원본 자원을 삭제/rollback하지 않았다. 실제 Afterglow 로그인→BFF→운영 Hub acceptance는 미검증이며, 기존 IAM을 자동 변경하지 않는 승인된 인증 경로가 필요하다.

### 리뷰·중간 실패·잔여 조건

독립 초기 리뷰가 global-refresh의 늦은 detail reopen이 새 다운로드를 취소하는 경합1건과 guide의 alias 실패 후 login·SDK insecure 우선순위·동일 subprocess web-control·API path 추측·공개 key UUID·IPv66건을 발견했다. Parent가 수정하고 consumer regression/actual CLI/compiled runtime으로 검증했다. Source 개선을 post-fix independent clean signoff나 Astra 계획/운영 승인으로 승격하지 않는다. Astra 역할은 이 세션에서 제공되지 않았다.

초기 browser fixture는 잘못된 native inventory URL로404였고 실제 `/api/v1/palimpsest/packages`로 정정했다. 최초 theme matrix는 실제 앱의 `html.light` 대신 `dark`/data-theme를 조작했으므로 무효화하고 실제 toggle과 computed state로 다시 확인했다. 최초 compiled fixture는 production CSP와 API origin이 달라 fetch가 차단되어 same-origin synthetic fixture로 고쳤다. Production CSP/source/auth를 완화하지 않았다. 녹화는 실제 UI interaction 증거이며30fps encoding을 성능 또는 정상 motion throughput으로 해석하지 않는다.

전체 `npm run test:gate`, 최종 Docker rebuild/Compose 실행·실계정 Afterglow BFF acceptance·운영 배포·IAM/DB migration·실제 VM/guest/runtime·native package 발급/로그인/게시·혼합 버전/rollback은 성공을 주장하지 않는다. Docker recovery는 다른 작업에 영향을 주므로 별도 소유권/승인이 필요하며 unsafe login을 통과시키기 위한 IAM 변경도 승인하지 않는다. 이 차단 때문에 OpenSpec change는 active로 남긴다. Gbrain CLI는 현재 PATH에 없어 sync/guidance를 변경하지 않았다.

최종 Docker 재개/정리 기록: exact-owned3개 container stop이 한 번 성공해 control 응답 복구를 관찰했지만, 이어진 final build/runtime에서 다시 stalled했다. Backend arm64 probe는143·UID/architecture 관측 없음, owned Compose up은120초 timeout, 실제 provisioning-disable config inspect는15초 timeout이었다. 마지막 frontend arm64 log는 build/export/unpack DONE과 manifest `sha256:3597549439215fd25a86055dc679bf0af7ca1aef3dfda0feaedb7b02460abafd`를 남겼으나 CLI exit는 확인되지 않았고 owned build wrapper만 취소했다. 원본 Docker/VM을 재시작하지 않았다. 최종 source+문서는 host production build를 다시 통과했지만 canonical runtime의 대체 증거는 아니다.

Owned Node/Vite/native Uvicorn·Redis/Chrome은 정지했다. 임시 credential JSON duplicate와 unsafe login smoke entrypoint는 제거하고 in-memory 입력을 비웠다. 원본 key는 stopped container metadata에서 메모리로만 보존하여 재시작 명령에 사용했고, 대상 DB/cache host가 owned `afterglow-mariadb`/`redis`임을 확인했다. 이후 CLI exact stop20초와 direct Engine Unix-socket version/stop8초 요청도 timeout이어서 **Docker3개 container의 최종 정지는 확인되지 않았다**: `afterglow-hub-dashboard-80043ecf-{backend,redis,afterglow-mariadb}-1`. 이 resource와 volumes는 global reset/prune 없이 보존하며 engine 복구 뒤 exact-owned teardown 확인이 필요하다. Frozen source snapshot은 차단된 qualification 재개를 위해 유지한다. `owned-container-cleanup.json`과 `image-builds-final-qualified.json`이 이 한계를 기록한다.

별도 backend arm64 binary probe는 `docker run --rm`으로 요청했으나143 뒤 container ID/UID/platform을 관측하지 못했다. 해당 disposable probe의 자동 제거도 독립 확인하지 않았으며, engine 복구 시 exact image tag·명령·생성 시점으로 소유권을 확인해야 한다. 다른 image 사용자나 이름 없는 container를 일괄 삭제하지 않는다.

Durable receipts: `~/.local/share/afterglow-proofs/hub-dashboard-20261015-80043ecf/`의 `source-context.json`, `selected-source-files.json`, `source-parity.json`, `compiled-browser-smoke.json`, `compiled-browser-runtime-{reactive,proactive}.json`, `guide-original-user-positive.json`, `guide-scope-negative.json`, `native-profile-safety.json`, `guide-web-control.json`, `provider-login-safety.json`, `login-provider-{before,after}.json`, `image-builds-{final,post-review,mounted-final}.json`와 `logs/`. 실제 영상은 `compiled-hub-permissions.mp4`, `compiled-native-denial-local-guide.mp4`; screenshot·matrix·download는 같은 private proof root에 있다. Provider/로그인 secret과 private config는 문서·공유 artifact에 복사하지 않는다.

### 이어서 확인 — Docker 복구·UTC 표시 수정 (2026-10-15 KST)

위 Docker timeout·미확인 상태는 당시 실패 이력이다. 이번 재개에서는 엔진 응답 복구와 기존 proof3개 container의 `running=false / exit=0`을 관찰했다. 엔진·VM 재시작이나 global prune은 수행하지 않았다. 기존28개 source/test/locale와 Dockerfile이 원래 frozen snapshot과 일치함을 먼저 확인한 뒤, 독립 리뷰가 발견한 UTC 표시 오류만 component와 기존 mounted test에서 수정했다. 수정 source는 별도 `/tmp/afterglow-hub-dashboard-80043ecf-utc-20261015T0218`에 보존했으며28개 파일+Dockerfile+정본 Compose의 현재 bytes와 SHA-256 일치30건을 기록했다. 기존 source snapshot·실패 receipt는 덮어쓰지 않았다.

| 추가로 실행한 검증 | 관찰 결과 및 범위 |
|---|---|
| UTC consumer 회귀 | 서울 시간대에서 naive `2026-10-15T00:00:00.123456`이00:00으로 표시되는1failed/1passed를 먼저 관찰했다. Native UTC datetime만 정규화한 뒤 관련 frontend4files/**98passed**. 명시적 `Z`/`+09:00`과 숫자형 마지막 관측 epoch를 보존한다. |
| 정본 image build | backend/worker/frontend의 arm64·amd64 **6builds exit0**. UTC 수정 뒤 frontend2architecture도 각각 `bun run build`·최종 npm/user stage를 실제 실행하고 export/CLI exit0. 캐시 사용·FROM resolution을 새 stage 실행으로 주장하지 않는다. |
| 실제 interpreter/architecture | backend/worker4실행은 Python3.12.15·UID1000·요청 architecture·exit0. 초기 frontend2probe는 Node20.20.2/UID1001/정확한 architecture 출력 후 부모가 부과한 과도한 UID1000 assertion으로 exit1이었다. Dockerfile의 별도 frontend는 non-root `appuser` 계약이므로 UID를 바꾸지 않았다. UTC 수정 image의 arm64/amd64를 `--network none`·고유 이름/label·`--rm`으로 다시 실행해 실제 non-root appuser/UID1001·Node20.20.2·정확한 architecture·**exit0**을 확인했다. 최초 strict receipt의 not-qualified/exit1은 보존한다. |
| 격리 정본 Compose | 운영 자격증명 없는 fresh SQL/cache에서 API·frontend가 healthy, Redis PONG·SQL SELECT1·40개 초기 schema table을 관찰했다. `/api/v1/health`·frontend `/health`·`/login`은200, 실제 Hub BFF `/me`의 무인증·invalid bearer는401. Container backend2파일 hash가 reviewed source와 같고, 실제 frontend image ID 및 HTTP static asset hash를 image bytes와 대조했다. 기존 DB upgrade·운영 auth acceptance 증거는 아니다. |
| 실제 canonical frontend Chromium | **4locale×2theme×6width×3workspace144조건**, page/main overflow0·page error0. Native403 탭 격리, 공개 UUID·IPv6 안내, 실제 검증 download3bytes를 확인했다. 별도 mounted401 rotation3회·proactive refresh1회,50+1 pagination·서버 검색·corrupt SHA save0도 최종 container에서 재실행했다. Identity/API 응답은 모두 synthetic이다. |
| UTC 실제 화면 전후 | 같은 서울 Chromium·native 형태 fixture에서 canonical image 수정 전00:00, 새 image 수정 후09:00을 확인했다. Explicit UTC 시작10:00·offset 완료12:00은 두 경우 모두 보존, page error0. `timestamp-browser-{before,after}.json`과 `continuation-browser/timestamp-{before,after}.png`가 증거다. |
| Scoped source guard | HEAD+28overlay의 격리 index/review root에서 stamp/check 통과: `source_sha256=8df68ea7fb9a3d9d64b0767b5b5d17bce5a183ae3ad300b481cee62040377d60`,2,633files. 실제 index와 공유 global review marker는 동일하게 보존했다. 전체 동시 WIP 승인이나 post-fix independent clean signoff는 아니다. |
| 실계정 사전조건 | 원본 SDK 인증 뒤 GET-only transport guard 아래 IAM4GET. 원래 user/project 일치, Default project 존재, direct project_reader 없음·managed projection0을 다시 확인했다. 실제 Afterglow login 재시도·IAM grant·인증 우회는0회이며 원본 credential/token을 복사·출력하지 않았다. |

**네트워크 실패와 한계:** internal-only network에서는 container 내부 API/frontend HTTP200·health가 성립해도 실제 published port map이 비어 Mac loopback이 ECONNREFUSED였다. 이를 앱 실패 또는 browser 성공으로 바꾸어 기록하지 않았다. 동일 isolated project의 API/frontend에만 일반 publication bridge를 추가하고 DB/cache는 internal에 남겼으며, 기존 ephemeral keys와 volumes를 보존했다. 이후 host HTTP와 browser proof는 성공했다. 이 최종 application bridge의 **외부 egress 차단은 주장하지 않는다**. 첫 publication preflight의 omitted-default `internal`(undefined/false) assertion 실패도 수정 기록으로 보존한다. 운영 endpoint/credential을 넣거나 실제 login을 실행해 우회하지 않았다.

**정리·공유 상태:** 새 offline4개 container를 정상 정지한 뒤 그4개와 새2개 network만 제거했다. 모든 owned Chromium은 종료했다. 이전3개 proof container는 exit0 정지를 확인했고 원래 키·DB/cache volumes·두 frozen source와 새 proof volumes는 의도적으로 보존했다. 옛 probe image tag를 참조하는 별도 unnamed container 후보는0이다. 전후 read에서 별도 공유 container5개의 부재도 관찰했으나 이 작업의 삭제 명령 대상이 아니므로 원인을 귀속하거나 재생성하지 않았다. 실제 제거 ID·관찰 차이는 `continuation-owned-cleanup.json`에 있다. `offline-compose-stop.json`의 네트워크 booleans는 초기 overlay render값이며 published runtime의 egress 증거가 아니다.

**잔여 차단:** 실제 Afterglow 로그인→BFF→운영 Hub는 IAM-safe prerequisite가 없어 여전히 미검증이다. 초기503/중단 login의 pre-attempt baseline 부재도 해소되지 않았다. 앞선 전체 frontend23failures/unhandled401 및 Svelte3errors는 이번 범위에서 재실행·수정하거나 성공으로 승격하지 않았다. 운영 배포·publication·IAM 변경·VM/native proof·OpenSpec archive를 하지 않았고 change는 active로 유지한다. API wire·번역 key·design 구조는 바뀌지 않아 해당 계약은 유지했다.

추가 receipt: 같은 private proof root의 `continuation-{source-parity,utc-source-parity,login-preflight,runtime-smoke,final-browser-flows,owned-cleanup}.json`, `image-builds-continuation-20261015T020536923Z-13e0cf05.json`, 원래 strict qualification/addendum, `image-builds-utc-correction-20261015T0219.json`, `utc-image-smoke.json`, `scoped-architecture-review-utc.json`, `timestamp-regression-before.json`, `continuation-browser/compiled-browser-{smoke,runtime-reactive,runtime-proactive}.json`와 `logs/`를 참조한다.

## 2026-10-25 Palimpsest 에셋 대시보드 검증 (local source, not deployed)

공유 dirty `dev`의 working tree를 격리 public-source snapshot(`/var/folders/.../afterglow-palimpsest-dashboard-*`)에 복사해 빈 DB URL·`OS_*` 미설정으로 실행했다. 운영 `afterglow_kolla`, 운영 배포, 실제 VM/hypervisor, 실제 Keystone 인간 로그인은 사용하지 않았다. 모든 identity/policy/cloud 응답은 synthetic이며 commit/push/tag/schema/IAM 변경은 없다.

| 실행한 검증 | 결과와 증거 범위 |
|---|---|
| Native Hub 전체 | `native-hub-final.log` **710 passed / 2 skipped**. 이후 catalog 22(`native-catalog-postformat.log`), unpack 29(`native-unpack-postformat.log`), 최종 CLI 계약·reference·lane 313(`native-final-shared-cli-contracts.log`). 이 수치는 native 하위 작업이 기록한 receipt(`openspec/changes/archive/2026-10-25-add-dashboard-asset-catalog/verification.md`)를 부모가 파일명으로 확인한 것이며, Hub 전체 suite를 부모가 마지막으로 다시 실행한 것은 아니다 |
| Native core-cli lane | `native-core-cli-root-env.log` 2046 passed / 2 skipped / **27 failed**(root `.venv/bin`이 PATH에 없어 `ansible-playbook` FileNotFoundError). 같은 27개만 실제 설치된 ansible-core로 재실행한 `native-kolla-missing-27-real-ansible.log` **27 passed**는 하위 작업의 로그이며 부모가 직접 재실행하지 않았다. 실패 로그는 삭제·개명하지 않았다 |
| Afterglow backend 집중 | catalog·cleanup·packages·authorization·build_work·layer_ops·layer_consume_resources·storage delete·instances·mcp_compute·auth boundaries 등 **784 passed** |
| 실제 HTTP/SQL/Redis journal/설치된 SDK | 부모가 마지막으로 실행한 `caller-cloud-http-server-deleted.log`: Uvicorn TCP 위에서 consume #1 POST 202(`creating`, 준비 전) → 조회 `active` → `DELETE` 200 → 조회 `deleted`. Provider create 순서 port→rule→volume→server, delete는 server·port·volume이고 rule/port/volume 잔여 0, Nova server 제거 단언 포함. Identity·정책·quota·provider는 synthetic이며 live VM이 아니다 |
| 실제 MariaDB publication race | `functional-mariadb-full-db-target.log`: 전용 Compose 프로젝트 `afterglow-palimpsest-asset-final-db`의 tmpfs MariaDB11.4/PostgreSQL16/Redis7 위 canonical DB target **167 passed / 33 deselected**. `test_publication_withdrawal_wins_before_locked_consume_snapshot`가 실제 InnoDB ancestor row lock 대기 후 publication 철회를409로 관찰하고 consume row를 만들지 않음을 검증했다. 전용3개 container와 network는 runner가 제거했다 |
| API 계약 | `backend-contracts-frozen.log`: **182 passed**, synthetic/loopback 계약 범위 |
| Frontend 집중 | 9 files / 248 passed (API·controllers·admin panel·consumer panel·route permissions) |
| Locale | `i18n:check` 0 errors / 37 기존 key-order warnings, 50 namespaces / 11,465 messages |
| 실제 compiled Chromium | 소비자·관리자 dark/light × 1440/1024/768/390(375) full-page capture, document overflow 0. 관리자 검색→상세에서 기록된 GitHub 빌드 출처·부모 체인·전체 ID 확인. 소비자 단일 `POST …/environments/7/consume`, 탭 전환 뒤 pending receipt 보존. 빈 후보 페이지→다음 페이지, 한 저장소 장애 시 다른 두 저장소 유지 |
| Impeccable detector | 변경 UI 4 경로 exit 0 |
| 최종 frozen source | `a2d22e411b513e35fd21036335b862958a911aa2426f23d008e5041ba062eed3`,3,497files(`gate-final-frozen.log`). Snapshot에는 preexisting·동시 WIP가 포함된다. 이 작업의 검토는 Palimpsest에 한정하며 shared tree 전체 검토·인증으로 확대하지 않는다. Diagnostic bisect 변경은 임시 복사본에만 적용했다 |

### 최종 gate 상태 (이 기록의 한계)

`npm run test:gate`는 이 변경만으로 green을 입증하지 못했다. 마지막 실행의 관찰 사실:

- 최종 `node scripts/test-target.js palimpsest` selector에 실제 수정한 admin/libraries route 회귀도 추가했다. Backend512passed, frontend10files/260passed(`palimpsest-expanded-target-final.log`), manifest validation도 통과했다. 실제 MariaDB167passed와 API계약182passed, 변경 Python25files lint/format 성공도 별도로 관찰했다.
- 마지막 전체 gate는 **112failed/9514passed/95skipped**(`gate-final-frozen.log`): `test_admin_user_deletion.py`66, `test_admin_resource_details.py`27, `test_admin_identity_domain_scope.py`12, `test_enrollment_policy.py`6, `test_admin_volume_transfer.py`1. 모든 실패ID는 `final-external-gate-failures.json`에 있다. 이전 gate의 dashboard/keystone4건은 마지막 gate의 현재 실패 목록으로 쓰지 않는다.
- 원인을 추정하지 않고 임시 source 복사본에서 bisect했다. Palimpsest projectless 예외만 제거해도 대표 enrollment5건은 실패한다(`authority-bisect-without-palimpsest-exception.log`). 예외를 유지하고 별도로 바뀐 `require_admin`의 NativeOperation rewrite만 원래 guard로 되돌리면5passed다(`authority-bisect-original-guard-with-palimpsest.log`). 실패5개파일 전체는 그 diagnostic guard로252passed/1failed: 남은 `test_admin_volume_transfer.py::test_native_palimpsest_marker_is_conservative_blocker`는409예상에201을 반환한다. Shared deps/transfer 코드는 되돌리지 않았다.
- 전체 frontend 별도 실행은40failed/5232passed,5failed/442passedfiles와 unhandled1건(`frontend-full-frozen.log`). 실패는 client.authRecovery,WaygateWorkspacePolling,vmCreateStoreRealClient,AdminReadiness,hypervisors/removal이다. 전체 backend lint도 concurrent `tests/test_admin_volume_transfer.py`의F811에서 막힌다(`final-format-check.log`). 이 경로들을 고치거나 제외하여 gate 성공으로 만들지 않았다.
- 별도 정본 재현을 수행한 Waygate 외 frontend 실패와 남은 volume-transfer marker201vs409 실패는 **원인 미확정인 통합 실패**다. Palimpsest와 무관하다고 단정하지 않으며, 해당 경로의 source를 임의로 되돌리거나 테스트를 약화하지 않았다.
- `test_layer_build_ownership` 계열이 임시 loopback port로 들어온 무관한 로컬 프로세스(`/exa.language_server_pb…/RetrieveUserQuotaSummary`)의 요청을 `unexpected`로 기록해 실패했다. 공용 `layer_provider` handler가 fixture의 서비스 root(`/nova`, `/neutron`, `/cinder`, `/glance`, `/manila`, `/v2`, `/v3`) 아래 요청만 `unexpected`로 기록하고 외부 probe는 404만 돌려주도록 한 번에 고쳤고, catalog 테스트의 엄격한 `state["unexpected"] == []`는 그대로다. 수정 뒤 해당 fixture 사용 파일 166 passed. 이것은 테스트 환경 hardening이며 application 변경이 아니다.
- 과거 한 번 gate의 unit lane이 99%에서 멈춘 사례가 있었으나 같은 입력으로 재현되지 않았다. 원인은 규명하지 못했다.
- 새 `test_palimpsest_catalog_db.py`의 `pytest.mark.db` 및 `db` selector 포함을 확인하고 실제 disposable MariaDB target을 실행했다. `node scripts/test-db.js tests/test_palimpsest_catalog_db.py`는 raw pytest selector를 받지 않아 최초 시도는 tests0로 종료·정리됐고, 올바른 `node scripts/test-db.js` 실행이167passed였다. 운영 DB·ORM bootstrap 또는 migration은 실행하지 않았다.

### 운영 의미

- 새 모든 VM 삭제 경로(일반·bulk·관리자·MCP)는 `LayerConsume` receipt store를 읽어 catalog 소유권을 배제한다. store 미초기화/조회 실패는 503으로 fail-closed하며, marker 제거/불일치는 409, 다른 owner는 404다. **SQL receipt store를 쓸 수 없는 배포에서는 VM 삭제가 막힌다.** 롤아웃 전 확인이 필요하다. 근거 테스트: `test_removed_native_marker_cannot_bypass_known_sql_catalog_delete`, `test_catalog_lookup_foreign_owner_is_indistinguishable_from_missing_instance`, `test_mcp_removed_marker_cannot_fall_back_to_ordinary_delete`, `test_removed_marker_never_falls_back_when_sql_authority_is_unavailable`(`backend/tests/test_palimpsest_catalog_cleanup.py`).
- 새 Hub/BFF 경로는 매칭되는 native Hub·client 릴리스가 배포되어야 동작한다. 새 `palimpsest bundle unpack`은 published 0.3.5에 없고 UI가 설치 확인 체크박스로 막는다.
- 실제 로컬 guest 부팅, 실제 OpenStack consume, Docker Hub 연합 검색은 이 범위에 없다.
