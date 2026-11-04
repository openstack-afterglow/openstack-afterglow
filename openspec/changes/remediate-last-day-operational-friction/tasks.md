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
- 1.2–1.3: native 인증의 올바른 현재 source는 확인했으나 matching sibling release·schema·원 key/복구 조건과 실제 현재 사람 scope 수용이 별도 선행 조건이다. 최신 광범위 WIP 이미지를 무검증 교체하거나 native 권한을 확대하지 않는다.
- 2.4: 실제 Hub worker의 claim settlement 계약과 구 API의 POST-only 계약 불일치를 확인했다. 불확실한 claim journal 두 개를 삭제/재전송하지 않고 restart-loop worker만 일시 중지했다. 전후 journal hash·inode·mtime/volume/image/restart policy가 일치한다. 구 API가 처리했을 수 있는 claim은 새 cursor가 비어 있다는 이유로 무실행 처리하지 않으며 원장 대조/명시적 operator disposition 전 재개하지 않는다.
- 2.6(source/local): dependency DEBUG 증폭을 제한하고 pytest/PID 파일 목적지와 source/process/runtime metadata를 검증했다. 수정된 operational/logging 관련372회귀가 통과했으며, 실제 격리 Uvicorn/TCP7요청에서 metrics7·샘플 request4·불완전 probe2(WARNING)를 관측했다. 두200응답도 JSON payload는 유효하지 않았으므로 HTTP200을 사용자 성공으로 해석하지 않는다. 고정 진단 사유 보존과 query/body/오류 canary의 실제 stream/file 비노출, runtime file_scope 및 서버 종료를 확인했다. 운영 release 적용 증거는 아니다.
- 2.7(source/local): API/worker common module로 clean cutover하고 worker CLI에서만 초기화하여 module import가 API request handler/audit를 지우지 않게 했다. 최종 관련262회귀와 실제 canonical amd64 worker-only image CLI lifecycle/file+stderr JSON·entrypoint worker·driver1054·canary 비노출·API main/Uvicorn 미import 및 canonical crypto smoke가 통과했다. DB 미설정 종료는 readiness/업무 성공이 아니며 운영 배포 증거가 아니다.
- 2.1(source/local): 설치 SDK/HTTP topology before/after와 local policy batch/fresh authority를 검증했다. Network 관측의 effect 재조회 loop는 수정 전 실패/수정 후8회귀, 실제 logical renewal·role/readiness/API-base ABA·미저장 catalog draft 보존16회귀를 통과했다. 업무 지연·권위 판정을 캐시로 숨기지 않는다.
- 2.2: 1.32.6 재시작 뒤18:30–22:06UTC traffic503은 controller1/2/3에서137/1/3이었다. HAProxy의3backend/2초 health 주기를 확인했고 interval/deadline을 무작정 늘리지 않았다. Fresh subprocess Redis가 빨라도 실제 API pool/event-loop의 원인 증거는 아니다. 실제 Redis Lua commit→ACK loss에서 counter 증가1·자동 재전송0을 확인했다. Matching finite-diagnostic release와 live stage 수용 전 원인 해결/실제 loss율을 주장하지 않는다.
- 2.3(source/local): 실제 Redis-driver socket GET/SETEX 장애에서204→503→503→같은 credential204, unknown401·instance mismatch403 및 원 절대 TTL의 단조 감소를 확인했다. Store 장애를 credential 거부나 거짓204로 가장하지 않고 기존 credential을 재발급/폐기/갱신하지 않았다.
- 2.5(source/local): traceback 본문·locals/임의 예외 문자열 대신 구조화 type/frame·HTTP status·known numeric DB code·유한 OAuth private reason을 보존한다. Public OAuth 오류는 credential 존재/resource 차이를 드러내지 않는 동일 payload로 유지한다. Console403/404/409·owner 불완전502·overview upstream503을 정상 빈 응답이나 성공으로 억제하지 않으며 과거500의 미관측 stack을 소급 원인 확정하지 않는다.
- 3.3(source/local 완료): 명시 envelope의 Waygate/Drover503은 정상 local11행·Builder catalog/다른 service 값을 보존하고 원문 오류를 제외한다. 실제 compiled UI의 서비스별 조회 불가·실패 행 저장 차단·Notion null/false/unknown·target200/runtime nativeSQL1054→503의 독립 표시·logical renewal draft 보존·base/owner late response fence를 확인했다. Original source JWT/get_os_conn/write/admin guards override0 cohort에서 member/reader/foreign scope와 보호된 갱신 세션을 별도 실행했다. Notion fixture logout503은 native client tokens-manager 미구현이며 local owner 폐기만 수용하고 server revocation은 UNKNOWN이다. 최종 전체 gate와 운영 native 수용은3.2 및 별도 block으로 유지한다.
- 성능: 첫 OFF/ON pair는 signup-options429가 포함돼 합격을 폐기했다. 같은200상태의 paced20+20·동일 budget 규칙으로 재측정하며 rate limit 완화나 미확인 수집률 주장을 하지 않는다. 운영 auth/Hub/traffic 차단을 source-local green으로 덮지 않는다.
- 3.2(source/local 완료): 최종3b539f55/4116files의 Python3.12.13 전체 gate14130backend/7203frontend/261contracts/263DB/Ruff865와 private working/staged architecture를 통과했다. 최신 amd64 API/frontend/worker image와 정본 소유 Compose·별도 SQL/Redis, public recovery collector201/ACK9·SQL9와 worker CLI/crypto를 실행했다. Palimpsest/Lumen read-error 적용/DOM, Audio capability ABA·관리자 container503→false404 누락을 수정하고 실제 browser/source HTTP·SQL로 재수용했다. 공유 index·운영 release/schema/IAM/key/unknown 원장은 변경하지 않았다.
- 3.1: 최신11계열 matrix·동일 catalog 전체 wire/legacy 비용·추가 native mutation0·ACK/SQL·privacy 근거를 통합했으나 legacy standalone source-owned DOM과 전체 native/human 경계는 미확인이다. `add-semantic-experience-replay`4.5/6.2/6.7을 임의 완료/축소/archive하지 않는다. Native release·schema·원 key·현재 사람 권위와 Hub claim disposition은 기존 별도 승인 전제를 유지한다.
