---
title: 국소 기능테스트 가이드
lang: ko
nav_order: 8
---

# 국소 기능테스트 가이드

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
