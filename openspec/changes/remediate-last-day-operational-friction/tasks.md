## 1. 기능 복구

- [x] 1.1 MCP 목록/OAuth schema 복구 후 실제 인증 읽기·배포 bootstrap 검증을 완료한다.
- [ ] 1.2 MCP K3s/Waygate native 인증·권한 실패를 조치한다.
- [ ] 1.3 Lumen/Drover/Palimpsest/K3s403을 정상거부·배포차이·소스결함으로 분리하고 조치한다.
- [x] 1.4 Mail payload 실패의 DB/key/소비자 혼선을 해소하고 unknown/실패 재전송과 키 rotation을 하지 않는다.
- [x] 1.5 Redis Sentinel/worker 조정 장애와 작업 상태를 확인하고 원인을 조치한다.

## 2. 지연·운영 비효율

- [x] 2.1 관리자 topology·policy catalog·usage schedule·auth 병목과 중복 I/O를 조치한다.
- [ ] 2.2 probe/health/readiness·telemetry 양 및 controller1 편중503을 조치한다.
- [x] 2.3 instance health report401과 report-token lifecycle을 조치한다.
- [ ] 2.4 Flavor 반복 경고·Palimpsest claim405/readiness503을 조치한다.
- [x] 2.5 console500/owner502/overview503/OAuth 안전한 오류 분류를 조치한다.
- [x] 2.6 로컬 테스트/개발/운영 로그를 구분하고 반복 DEBUG 증폭을 조치한다.
- [x] 2.7 Standalone worker에도 같은 secret-safe JSON 로깅을 적용하고 실제 worker-only image를 검증한다.

## 3. 경험 관측·검증

- [ ] 3.1 `add-semantic-experience-replay` 계약에 따라 실제 저장/인과연결/표시 결과/한국어 안전조회·누락표시를 구현·검증한다.
- [x] 3.2 실제 source smoke·behavior regressions·관련 gate·architecture/docs/changelog를 완료하고 운영 수용과 block을 분리 보고한다.
- [x] 3.3 재검증 중 발견한 정책 합성 조회의 서비스별 실패를 분리하고 실제 source JWT/owner/write guard·보호된 갱신 세션으로 다시 수용한다.

## 현재 운영 경계

- 1.4: 사용자가 공유 DB 유지·로컬 backend 중지를 선택했다. 잘못된 암호화 키와 별도 Redis 조정을 사용하던 local backend만 중지하고 원래 image/env/mount/restart policy를 보존했다. DB·키·메일 상태 변경과 재전송은 없다. 호환성 admission 또는 별도 DB 격리 전 재기동하지 않는다.
- 1.5: 16:23 UTC의 세 Valkey/Sentinel 동시 재시작과 조정 오류를 시간 대조했다. 이후 native PING/master+replica2, dispatcher6, 미완료 mail0·Drover0을 확인했다. 이미 회복된 작업을 reset/replay하지 않는다. 이 일시 장애를 앞뒤로 계속된 controller1 telemetry503의 원인으로 단정하지 않는다.
- 1.1: 별도 운영 receipt에서1.32.6/0334564의 Kolla SQL106 bootstrap 및2026-11-03 19:15:58UTC 실제 인증 `mcp-tokens`/`mcp-oauth/grants` HTTP200을 확인했다. 이미 끝난 복구/재시작은 반복하지 않는다. 사용자 Chrome relay 시각 수용은 별도 제한으로 남고 인증 우회·저장 자격 impersonation은 하지 않는다.
- 1.2–1.3 현재 재조회(2026-11-05): 세 controller의 Afterglow는 여전히1.32.6/0334564이고, Lumen0.6.13/9d5e217b·Drover0.4.17/8526860f·Waygate0.3.7/89cdd1b9 API cohort는 정합한 새 revision으로 바뀌었다. Controller1 Lumen/Waygate auth의 openid literal도 있다. 과거 미배포 진단을 현재403의 원인/복구 증거로 재사용하지 않는다. 실제 현재 사람 browser relay가 끊겨 권위·policy 읽기 수용은 차단이며 원 key/schema/backup·rollback continuity는 별도 protected 운영 수용 전제다. 저장 사용자 자격으로 대체하지 않았다.
- 2.4: 실제 Hub worker의 claim settlement 계약과 구 API의 POST-only 계약 불일치를 확인했다. 불확실한 claim journal 두 개를 삭제/재전송하지 않고 restart-loop worker만 일시 중지했다. 전후 journal hash·inode·mtime/volume/image/restart policy가 일치한다. 구 API가 처리했을 수 있는 claim은 새 cursor가 비어 있다는 이유로 무실행 처리하지 않으며 원장 대조/명시적 operator disposition 전 재개하지 않는다.
- 2.6(source/local): dependency DEBUG 증폭을 제한하고 pytest/PID 파일 목적지와 source/process/runtime metadata를 검증했다. 수정된 operational/logging 관련372회귀가 통과했으며, 실제 격리 Uvicorn/TCP7요청에서 metrics7·샘플 request4·불완전 probe2(WARNING)를 관측했다. 두200응답도 JSON payload는 유효하지 않았으므로 HTTP200을 사용자 성공으로 해석하지 않는다. 고정 진단 사유 보존과 query/body/오류 canary의 실제 stream/file 비노출, runtime file_scope 및 서버 종료를 확인했다. 운영 release 적용 증거는 아니다.
- 2.7(source/local): API/worker common module로 clean cutover하고 worker CLI에서만 초기화하여 module import가 API request handler/audit를 지우지 않게 했다. 최종 관련262회귀와 실제 canonical amd64 worker-only image CLI lifecycle/file+stderr JSON·entrypoint worker·driver1054·canary 비노출·API main/Uvicorn 미import 및 canonical crypto smoke가 통과했다. DB 미설정 종료는 readiness/업무 성공이 아니며 운영 배포 증거가 아니다.
- 2.1(source/local): 설치 SDK/HTTP topology before/after와 local policy batch/fresh authority를 검증했다. Network 관측의 effect 재조회 loop는 수정 전 실패/수정 후8회귀, 실제 logical renewal·role/readiness/API-base ABA·미저장 catalog draft 보존16회귀를 통과했다. 업무 지연·권위 판정을 캐시로 숨기지 않는다.
- 2.2: 1.32.6 재시작 뒤18:30–22:06UTC traffic503은 controller1/2/3에서137/1/3이었다. HAProxy의3backend/2초 health 주기를 확인했고 interval/deadline을 무작정 늘리지 않았다. Fresh subprocess Redis가 빨라도 실제 API pool/event-loop의 원인 증거는 아니다. 실제 Redis Lua commit→ACK loss에서 counter 증가1·자동 재전송0을 확인했다. Matching finite-diagnostic release와 live stage 수용 전 원인 해결/실제 loss율을 주장하지 않는다.
- 2.3(source/local): 실제 Redis-driver socket GET/SETEX 장애에서204→503→503→같은 credential204, unknown401·instance mismatch403 및 원 절대 TTL의 단조 감소를 확인했다. Store 장애를 credential 거부나 거짓204로 가장하지 않고 기존 credential을 재발급/폐기/갱신하지 않았다.
- 2.5(source/local): traceback 본문·locals/임의 예외 문자열 대신 구조화 type/frame·HTTP status·known numeric DB code·유한 OAuth private reason을 보존한다. Public OAuth 오류는 credential 존재/resource 차이를 드러내지 않는 동일 payload로 유지한다. Console403/404/409·owner 불완전502·overview upstream503을 정상 빈 응답이나 성공으로 억제하지 않으며 과거500의 미관측 stack을 소급 원인 확정하지 않는다.
- 3.3(source/local 완료): 명시 envelope의 Waygate/Drover503은 정상 local11행·Builder catalog/다른 service 값을 보존하고 원문 오류를 제외한다. 실제 compiled UI의 서비스별 조회 불가·실패 행 저장 차단·Notion null/false/unknown·target200/runtime nativeSQL1054→503의 독립 표시·logical renewal draft 보존·base/owner late response fence를 확인했다. Original source JWT/get_os_conn/write/admin guards override0 cohort에서 member/reader/foreign scope와 보호된 갱신 세션을 별도 실행했다. Notion fixture logout503은 native client tokens-manager 미구현이며 local owner 폐기만 수용하고 server revocation은 UNKNOWN이다. 최종 전체 gate와 운영 native 수용은3.2 및 별도 block으로 유지한다.
- 성능: 첫 OFF/ON pair는 signup-options429가 포함돼 합격을 폐기했다. 같은200상태의 paced20+20·동일 budget 규칙으로 재측정하며 rate limit 완화나 미확인 수집률 주장을 하지 않는다. 운영 auth/Hub/traffic 차단을 source-local green으로 덮지 않는다.
- 3.2(source/local 완료, 2026-11-05 supersession): source0eab16fb/4141files의 Python3.12.13 전체 gate14382backend/7351frontend/261contracts/263DB/Ruff876와 private architecture를 통과했다. Matching amd643이미지·정본 소유 Compose·public recovery201/ACK9/SQL9, current worker CLI/crypto 및 fresh source Redis/verified SMTPS/IMAPS/SQL accepted/unknown 각1건을 수용했다. 공유 index·운영 release/schema/IAM/key/unknown 원장은 변경하지 않았다.
- 3.1 source/local 수용 완료: 현재11계열은 core26조건·나머지7계열18 source-owned/2 generic docs와 current4flow budget·worker proof로 분류했고 legacy standalone 초기 guarded DOM 공백도 해소했다. 세부 capability의 generic-only/applied-only·원격 미지원과 synthetic 권위는 명시한다. `add-semantic-experience-replay`4.5/6.2는 source/local 증거로 닫지만6.7 및 이 운영 change의 native/auth/Hub/traffic acceptance는 여전히 열려 있으며 archive하지 않는다.
- 운영 재조회(2026-11-05): 원 Hub worker는 exited/restart2408·같은 ID/image이고 두 원 journal SHA가 최초 격리 receipt와 일치한다. 현재 설치 Hub API는 여전히 POST-only claim route이며 recover handler가 없다. Recovery GET 자체가 settlement commit이므로 조회처럼 호출하지 않았고 unknown replay·cursor 초기화·worker 재시작도 하지 않았다. 원 claim/build 원장 대조와 identity 없는 legacy claim의 명시적 operator 판정이 필요하다.
- Controller1 편중은 최근 약10분200/503=2436/15, 다른 controller2442/0·2444/0으로 남아 있다(서로 약간 다른 관측 window). Redis latest128 slowlog EVAL의 선택 표본10–16.650ms와 cgroup throttling0은 live API pool/event-loop/Sentinel 지연 원인 증거가 아니다. 배포된0334564에는 세부 stage 진단도 없다. 기존 API process의 bounded 관측 또는 정합·복구 조건을 갖춘 별도 diagnostic rollout 승인 없이 timeout 확대·임의 restart로 가리지 않는다. Secret·key·SQL·서비스·보존 상태 변경은 없었다.
- 승인된 operational readonly 관측(2026-11-05): 세 기존 API의50초 외부 stack 관측 뒤 sampler와 임시 binary를 회수하고 원 PID/start/restart·TracerPid0을 확인했다. 구간 내503=0이므로 원인은 UNKNOWN이다. Ctrl2/3의 main-loop 동기 Nova socket wait는 실제 SDK/HTTP failing-before3사례로 분리했고 source의 detail·조건부 flavor 읽기를 completion-drained thread로 전환했다. 관련138회귀와 httpcore missing-sniffio 탐색 local15000→0을 확인했지만 운영 배포·503 복구 판정은 하지 않았다.
- 승인된 Hub 원장 대조(2026-11-05): fresh readonly connection2회에서 cursor58846·decoded result null이 동일했다. Journal58848은 exact receipt/build/lease가 없어 권위 있는 join이 불가능하며 legacy POST는 sequence-unaware다. 좁은 시간 창 후보0도 미실행 증거가 아니다. 원 journal/hash·worker exited hold를 유지했고 replay·reset·settlement·재시작은 하지 않았다. 추가 역사 원장/backup 또는 명시적 비재실행 disposition은 별도 operator 선택이 필요하다.
- 최종 현재 사용자 MCP 안전 읽기(2026-11-05): mounted VM/K3s/Waygate를 각limit1로 실행했으나 모두 unavailable이고 Relay target discovery도 연결되지 않았다. Native 전용403인지 공통 connection/credential 단계인지 확정하지 않는다. 저장 사용자 credential을 추출·대신 사용하지 않았고 추가 protected grant integrity/expiry·역사 Hub 원장 및 traffic 관측은 별도 operator 범위로 남긴다.
- 추가 승인된 readonly 범위 완료(2026-11-05): Controller1 기존 process 하나를 configured10Hz·실제299.214초 관측하여 자연503 6건 모두 `record_event=False` 뒤 `ingest_traffic:65`의 비연쇄 HTTP503임을 확인했다. 성공606건 및 duration-matched 성공20/20에도 import 탐색이 있어 실패 고유 원인으로 단정하지 않는다. 배포0334564d에는 stage logger가 없어 내부 False 이유는 복원 불가다. Sampler 회수·원 PID/start/image/restart0·TracerPid0을 확인했고 재시작·timeout 변경·배포는 없다. 최종 clarification과 `controller-approved-observation-final.json`을 사용하며 초기 미확정 receipt는 원인 판정에 사용하지 않는다.
- Hub 역사 metadata 대조 완료(2026-11-05): 원 worker의 UUID7개는 모두 channel이며 exact build/lease 필드는 없었다. 10월30일 backup은 sequence58848보다 오래되고, 세 actual Hub API retained log는 관련11월2일 window 초반을 포함하지 않는다. Claim route literal5개는 status/outcome UNKNOWN이며 권위 있는 claim→build/lease/outcome join을 만들지 못했다. `hub-historical-read-summary.json`에 approved metadata investigation complete를 기록했다. 복호화·restore·settlement GET·replay/reset·재시작 없이 원 journal/hash와 exited hold를 유지한다.
- 남은 승인 경계: traffic은0334564d 기반 최소 finite-stage 진단 후보·격리 검증·rollback이 필요하며 공유 dev/SQL107·108 전체 rollout은 금지한다. Hub unknown은 추정 성공/실패로 닫지 않고 원본 보존·비재실행 disposition 및 호환 cohort 전환 조건을 별도로 승인받는다. MCP는 현재 로그인 Chrome Relay 연결을 기다리며 사용자가 선택하지 않은 protected grant SQL/저장 human credential 대체 경로는 실행하지 않는다. 이 세 운영 항목과 semantic6.7은 계속 미완료이며 archive하지 않는다.

## 4. 승인된 후속 준비 (2026-11-05)

- [x] 4.1 배포0334564d 기준의 최소 finite-stage 진단 후보만 선별해 격리 behavior·실제 API/Redis·이미지 경로를 검증하고 정확한 변경·배포·rollback 조건을 제시한다. 실제 발행·운영 배포는 하지 않는다.
- [x] 4.2 원 Hub unknown·journal·중지 worker를 보존하면서 현재 build/lease metadata를 제한 읽기로 대조하고 호환 API/worker/schema 및 비재실행 전환 조건을 검증한다. 원장 판정·settlement·replay/reset·복호화·restore·재시작·실제 전환은 하지 않는다.

진단 후보도 정식 release나 운영 수용이 아니다. DMSLab의 실제 배포는 상세 개발 가이드의 전체 compute/control 실행 단위를 따라야 하며 controller1-only canary·수동 controller loop를 대안으로 실행하지 않는다. 공유 dev의 무관한 변경·SQL107/108·의존성·timeout 변경을 최소 후보에 포함하지 않는다.

4.2 수용:12:00:36UTC의 단일 native readonly census에서 builds6개(complete5/error1)·image_jobs8개(complete2/error6), 두 표의 nonterminal·future lease0을 관측했다. 이는 point-in-time SQL이며 writer fence·외부 실행 부재·과거 unknown 판정이 아니다. 원 worker exited/restart2408·동일 scratch 실행0·두 journal hash의 전후 일치를 확인했다. 현재 API57ab180/held worker7c4bb06은 정합 cohort가 아니지만 공개0.3.12의 API/export/build-worker3이미지 OCI index·amd64 manifest·config digest와 선언된 version/revision4905228의 tag 일치를 추가 확인했다. Source checkout HEAD는c4dcee6이므로 검토한5개 contract 파일만 release4905228과 working-byte diff0을 확인했으며 전체 checkout/source 또는 image binary 동일성으로 승격하지 않는다. `hub-current-cutover-qualification.json`과 `hub-public-cohort-metadata.json`에 bootstrap의 creator/PK/visibility·paired SQL/CAS 복구·원 unknown 보존·정본 전체-group 배포 조건을 보존했다. Layer pull/run·schema/restore 수용·운영 전환은 수행하지 않아2.4는 계속 미완료다.

4.1 수용: immutable packaging snapshot a7a26c86/6778entries·patch12708860은0334564d 위 `traffic_analytics.py`/`utils/log.py` 두 product 파일만 변경한다. 원200/503·250ms·Lua/EVAL·drop bookkeeping·취소·무재시도를 보존하고 원 Lua 용량 거절도 finite aggregate/capacity로 관측한다. 기존155회귀와 실제 before/after TCP·설치driver·Redis/Lua, canonical Compose SQL106 bootstrap→API의200/503/복구 및 stream/file timeout·connection 진단을 수용했다. API d4a49e65·transitive worker b5c0c8f7의 amd64 빌드/실행·두 source hash 일치를 확인했고 worker는 filter/import 및 원 no-DB 종료만 검증하여 readiness로 주장하지 않는다. 별도 dev gate 사본은 원6778entries 중 ARCHITECTURE 설명/stamp만 다르고 전체 gate13511backend/6782frontend/258contracts/233DB/Ruff846 및 b6f98672/4067files working/staged architecture를 통과했다. Qualification-only Redis5 close API·잘못 주입한 LOG_DIRECTORY를 고쳤으며 product/test를 바꾸거나 실패를 삭제하지 않았다. 소유 SQL/PostgreSQL/Redis를 백업하고 새 fixture만 중지했다. 원 f4551cd0는 registry digest가 아닌 Docker config ID이므로 실제 대응 registry manifest01245ce9도 별도 metadata로 확인했다. `traffic-minimal-candidate/qualification/acceptance.json`과 manifest에 정확한 실행·제한·rollback을 기록했고 shared source/index·발행·운영 배포는 변경하지 않아2.2는 계속 미완료다.

- [x] 4.3 정식1.32.6 대비 backend skip12개의 exact 이름·환경 사유·traffic 관련성을 대조하고 누락 selector를 실제 실행한다.
- [x] 4.4 immutable 최소 후보를 실제 Sentinel/master 경로의 warm/cold discovery·timeout·capacity·복구에서 격리 수용한다.
- [x] 4.5 Hub0.3.12의 startup reconcile→자동 recovery GET→원 journal 변경 경로를 확인하고 모든 version의 원 unknown mount 기동을 명시적으로 금지한다.
- [x] 4.6 보존된6개503의 직전/main-thread host_health와 성공 대조·발신 timer를 검토하고 시간상 연관과 인과 미확정을 구분한다.

4.3 수용: release13523pass/94skip와 candidate13511pass/106skip의 exact set diff는 Ansible runtime 미노출에 따른12개뿐이다. Country/GeoIP startup1개는 traffic 배포 경로라 영향 없음으로 생략하지 않았고 CloudShell native static precheck11개와 함께 실제 기존 operator Ansible을 read-only PATH로 제공하여12pass/0skip를 확인했다. 원 product/test는 바꾸지 않았고 canonical full gate13511/106과 supplemental12pass를 별개 실행으로 보존한다. Selector 전개·사유·이전 release pass 확인은 `qualification/release-skip-delta.json`에 있다.

4.5 수용: source4905228의 `build_worker.py` working parity를 확인했다. Executor preflight 뒤 startup이 reconcile을 호출하고 channel 있는 claim_pending은 recovery GET을 자동 실행할 수 있다. 성공한 empty settlement는 Journal.clear를 통해 파일 삭제가 아니라 원 worker.json을 phase=idle/channel/sequence로 다시 쓴다. 따라서 원58848을 명시적으로 비재실행 판정하고 byte-exact protected copy를 보존하기 전에는 기존/새 worker 어느 version도 원 scratch에서 시작·reconfigure·autorestart하면 안 된다. Mount/journal 보존이나 backup만으로 hold가 유지되는 것은 아니다. 현재 live GET/worker 기동·원장 변경은 없으며 `hub-startup-settlement-guard.json`을 필수 전환 gate로 둔다.

4.6 수용: 실패6/6과 duration-matched 성공6/6 모두 host_health probe frame이 있었고, 일부 성공은 실패 완료와8ms 미만 차이다. 10초 phase의 실패0.499초 집중은 관측된 시간상 연관이지 causal/lease-owner proof가 아니다. 원 source의 reporter에는10초 flush/retry가 없고 response 소비에 따른 즉시 POST·2초 deadline·기본16 inflight만 있다. 원본 capture만 분석했으며 새 profiler/live lease query는 없다. `controller-retained-periodic-comparison.json`에 겹치는 window·posthoc band·caller/task/lease 미확정을 보존했다.

4.4 수용: immutable API d4a49e65/sourcea7a26c86을 실제 Valkey8.1.11 master1/Sentinel1/replica0·redis-py5 SentinelConnectionPool로 canonical Compose에서 실행했다. SQL106 bootstrap0, positive200·900ms WRITE pause의 timeout503→200·HLEN10000 capacity503×3→200·Sentinel 정지 시 기존 master pool200·정지 Sentinel에서 새 소유 API의 cold discovery connection503×3·Sentinel/API 복구200·해당 event의 원 master dedupe를 확인했다. 실제 frontend 진단은 aggregate timeout/capacity/connection 각1줄이며 stream/file4줄(backend connection1 포함)이 동일했다. Lazy redis_acquire는 client construction일 뿐이고 이 I/O는 aggregate이며 모든503별 로그나 connect/Lua 구분을 보장하지 않는다. Source6778entries 전후 diff0·API source continuity·backup SHA와 새 소유 container7개 중지를 확인했다. Setpriv/config mode/INFO parser/stderr capture의 private harness 실패도 보존했다. Final recovery는 기존 QA schema를 재생성/rebootstrap하지 않았고 startup ping의 pool prewarm 및 restart 전 master-IP/config 미재대조 한계를 기록했다. 운영 version/topology/HA·unknown-write/restore 수용은 아니며 `qualification/sentinel-addendum.json`과 `sentinel-f06s/attempt3/final/qualification.json`이 정본이다.
