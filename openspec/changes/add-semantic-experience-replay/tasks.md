## 1. 계약·coverage·운영 선행 조건

- [x] 1.1 기존 interaction/audit/request/operation/worker 경계와 주요 기능 계열의 coverage 목록을 작성하고 현재 미관측/비밀 영역을 명시한다.
- [x] 1.2 버전별 envelope와 per-event 필수/선택/enum/길이·크기 제한, stable action/component/stage/reason registry를 확정하고 invalid/forged/secret payload 경계 회귀를 작성한다.
- [x] 1.3 현 source의 세션당 events/bytes·API/worker fanout·저장·query 부하와 브라우저/API p95 baseline을 측정하고 수용 budget을 정한다. 측정 없는 수치를 운영 수용으로 주장하지 않는다.
  - 고정 대표 episode의 fresh OFF/ON, native SQL query/ingest/storage matrix와 실제 worker RPC/link 예산을 실행 전 고정하고 비교했다(`budget/final-453/acceptance.json`). 전송147548B≤256KiB·episode391487B≤1MiB·same native fanout/extra mutation0·SQL3SELECT·storage/ingest/query/worker 한계를 수용했다. 운영 용량과 전체 사람 session의 절대 loss는 미확인이다.
- [x] 1.4 측정에 근거해 진단 sink·schema/index·event dedup·catalog 보존을 선택하고 old/new reader/writer·복구·보존 삭제 및 운영 opt-in 설계를 확정한다. 기존 업무 감사와 high-volume diagnostics는 분리한다.

## 2. 명시적 인과관계·수집 계약

- [x] 2.1 기존 브라우저 수집기의 owner fence를 재사용해 탭별 구간/page/action sequence와 비동기 context를 구현한다. Token bytes를 식별자로 저장하지 않는다.
- [x] 2.2 API client·follow-up read·SSE에 source/owner-bound correlation을 전달하고 서로 다른 action 및 request attempt를 구분한다. Backend request와 기존 operation ID를 연결한다.
- [x] 2.3 worker claim/실행/native dispatch/readback/cancel drain에 연결 metadata를 전달한다. 형제 서비스 미지원 내부 span은 미확인으로 표시한다.
  - Source mail outbox worker의 실제 Redis role/lease·aiosmtplib verified SMTPS→GreenMail·readonly IMAPS exact-ID readback·SQL accepted2/unknown1과 동일 role의 다른 actor 다중 delivery를 수용했다. 직접 반복 취소+실제 SQL notice 지연 중 lease/dispatching을 SMTP·SQL 종료까지 유지했고 childspan당 최대4행·원 operation link1·last-delivery cleanup 오귀속0이다. Palimpsest build 성공이나 production mailbox 수용은 아니다.
- [x] 2.4 strict v2 ingest와 bounded body/batch/rate, trusted actor/scope, server-owned provenance 및 dedup을 구현하고 endpoint pytest를 추가한다. 기존 v1은 혼합 배포 기간 동안 기존 계약대로 동작한다.
- [x] 2.5 bounded queue·동일 이벤트의 제한 재전송·gap/health·collector 재귀 제외를 구현한다. 업무 요청 replay/자동 로그인 복구나 scope 재귀속이 발생하지 않음을 검증한다.

## 3. UI 관측·메시지·화면 결과

- [x] 3.1 기존 Button/Field/Form/Modal/Alert/Toast/Wizard를 검토해 source action/component ID와 semantic hook을 제공한다. DOM text/ordinal을 의미 식별자로 사용하지 않는다.
- [x] 3.2 실제 feature state owner에서 loading/ready/empty/error·modal/단계·validation 거부를 기록하고 입력값·임의 선택값은 수집하지 않는다.
- [x] 3.3 메시지 key·실제 표시 locale·catalog/build revision·허용 parameter와 redacted/복원 불가 상태를 구현한다. 현재 locale와 이미 저장된 오류 문구의 언어가 달라도 정확히 표현한다.
- [x] 3.4 결과 수신/owner 검증/적용/DOM commit/노출/폐기 사건을 분리한다. DOM commit은 사람의 인지 증거로 표시하지 않는다.

## 4. 대표 흐름·내부 처리·전체 적용

- [x] 4.1 인증/계정 복구/provider 확인에 단계·정책 거부·일회용 처리·결과/문구를 연결한다. 언어/테마 변경 때문에 inspect나 callback을 반복하지 않는 실제 root-layout 회귀를 유지한다.
- [x] 4.2 MCP client review·scope/project 선택·preview·approve/deny·만료·권한 거부·unknown을 연결하고 token/code/ticket 및 원문 URL을 배제한다.
- [x] 4.3 VM 생성의 접수→operation→native→readback→UI 반영/폐기와 취소 요청/실제 drain을 연결한다. HTTP/SSE 성공과 실제 readiness 조건을 구분한다.
  - 원 action의 실제 SDK cancel→drain과 consumer create/SG/rollback/admin 약2초 종료·lease/connection 유지·추가 native replay0을 수용했다. SDK 종료는 provider 취소/guest 준비가 아니다. 최신 compiled source422에서 create-linked validation event가 wire/ACK/SQL/export·원 root·request/action과 일치했고 Nova CREATE0이다. 과거 disabled-Next UI gate를 소급 합격 처리하지 않는다.
- [x] 4.4 볼륨 생성의 접수→provider 상태 확인→terminal→목록/상세 반영을 연결하고 out-of-order polling과 unknown의 자동 재실행을 차단한다.
- [x] 4.5 1.1의 나머지 기능 계열을 같은 registry/공통 경계로 적용한다. 감사 필요·진단 적용·의도적 비수집·원격 미지원 범위를 구분하며 대표4흐름만으로 전체 완료 처리하지 않는다.
  - Source/local 완료: `operational-remediation-20261105/consolidated-current-acceptance.json`은 core4계열26조건·나머지7계열18 source-owned/2 generic docs 조건의11계열 분류를 연결한다. Standalone container/file의 최초 source-owned state와 guarded DOM·파일 독립 규칙 실패/실제[]·manual/passive 경계를 실제 compiled 경로로 수용했다. DB/Drover applied-only·monitoring overview/docs generic-only·raw content 비수집·remote-unsupported를 그대로 표시하며 모든 native 정상 CRUD·현재 사람 권위를 주장하지 않는다.

## 5. 저장·조회·한국어 재생

- [x] 5.1 1.4에서 선택한 실제 진단 sink와 제한된 experience index/projection을 구현한다. 실제 저장이 없을 때 mock/no-op/fake fallback으로 완료 처리하지 않는다.
- [x] 5.2 기존 관리자 event 탐색에 지원 코드/segment/action별 조회를 연결하고 모든 child/operation에 fresh scope 및 cross-project redaction을 적용한다. 익명 구간의 별도 열람 경계도 검증한다.
- [x] 5.3 한국어 경험 타임라인에 browser observed/server proof/업무 terminal/화면 결과·gap/partial coverage를 구분하고 상충·미확인 상태를 설명한다.
- [x] 5.4 비실행 replay renderer와 안전한 export, 열람/export 감사를 구현한다. 사건 데이터의 script/HTML/URL·operation 참조가 운영 요청을 발생시키지 않도록 검증한다.
- [x] 5.5 승인된 보존 정책에 맞는 진단/index/export/catalog 만료와 backup/hold/삭제 절차를 구현·검증한다. 운영 삭제 job은 별도 승인 전 활성화하지 않는다.

## 6. 수용·문서·안전한 전환

- [x] 6.1 permanent behavioral regressions로 async fanout·재전송 dedup·역순 수신·시계 오차·scope/ABA·익명 전환·취소 drain·서버/UI 결과 불일치를 검증한다. Wiring/source-text pin은 추가하지 않는다.
- [x] 6.2 실제 compiled browser와 source API/worker·전용 datastore를 연결해 네 대표 flow 및 1.1 coverage 경로를 실행하고 신뢰 경계·조회 결과·미확인 영역을 증거로 남긴다.
  - Source/local 완료: 현재 source0eab16fb의 core375 captured IDs/SQL3980행 snapshot missing0, native/workspace SQL828/1219행 및 현재 f51a/f51b 네 대표 episode를 연결했다. 별도 fresh worker-f05e에서 실제 Redis role/lease→encrypted outbox→verified SMTPS→독립 readonly IMAPS→SQL accepted/unknown 각1건·원 DATA2회·진단 각9행/link 각2개를 수용했다. Packaged public recovery는 실제201/ACK9/SQL9다. VM422/validation.rejected는 guest 성공이 아니며 synthetic identity/native peer와 현재 사람/native IAM 수용을 구분한다.
- [x] 6.3 offline/crash/collector/SQL/sink 장애·queue overflow·전송 응답 유실에서 본 업무 보존·누락/미확인 표시·원래 API 무재실행을 검증한다.
- [x] 6.4 입력/credential/query/body/DOM/채팅/terminal canary의 수집/일반로그/저장/export 비노출, 타 scope 조회/지원 코드/악성 replay event를 검증한다.
- [x] 6.5 계측 전후 성능·전송량·저장량·유실률·인과 연결률을 측정해 1.3 budget과 비교하고 실제 불합격을 해결한다.
  - 원시 cause38/40, 정확히 증명한 익명→로그인 cross-owner2를 별도 표시한 eligible38/38, client-ACK IDs132중 missing0을 수용했다. Source request/header/profile owner booleans로만 예외를 증명하며 원문 token을 저장하지 않았다. ACK 미관측7개는 SQL 존재·owner-fence drop4·document-end queue snapshot10의 fate는 UNKNOWN으로 남긴다. 이전36/38 거부는 historical로 보존했다.
  - 후속 현재 source/catalog의 fresh f51a/f51b: OFF/ON 전체 wire22606/190878B, episode25898/451072B로 원262144B/1MiB 한계 통과. 추가 native mutation0, ACK131/131 SQL missing0·미관측7개도 SQL 존재, raw40−정확한 cross-owner2=eligible38/38이다. ACK p9572.7ms/11관측batch와 stored JSON p95924B는 운영 request p95/사람 세션 비용이 아니며 절대 crash loss는 UNKNOWN이다.
- [x] 6.6 source smoke 후 ARCHITECTURE.md·DESIGN.md·API/security/testing/deployment 문서·설정 예시/K8s 생성 경로·changelog를 실제 구현과 함께 갱신한다. Named target→전체 test:gate·architecture 검증과 mixed-version/schema-before-writer·rollback 복구를 완료한다.
- [ ] 6.7 운영 opt-in·보존·배포는 기존 별도 승인과 선행 조건을 충족한 경우에만 수행한다. Source/local/운영 증거를 분리하고 이 change의 모든 수용 기준을 충족한 뒤 archive한다.
  - Source/local 수용은 끝났지만 운영 수집·보존 삭제·릴리스/배포·실제 권위는 승인하지 않았다. 현재 Relay 연결 불가와 mounted VM/K3s/Waygate 읽기 unavailable, Hub legacy outcome unknown, controller1 failure stage 미관측을 source green으로 닫지 않는다. 원 key/DB/hold와 unknown 원장을 유지하며 별도 운영 판단 전 archive하지 않는다.

## 진행 증거와 미완료 경계

- Source inventory는 `docs/testing.md`의 직전24시간/v2 절에 full state owner·generic-only·비수집/unknown 영역을 구분했다. 모든 함수/화면을 무손실 기록한다는 주장이 아니다.
- Native MariaDB3모듈30passed/5skipped와 실제 source API201/SQL/scoped recent/query200, source worker-only image의 실제 CLI JSON/1054/canary, frontend support/recent58·복구/viewer89·ChatPanel63회귀를 확인했다. Runtime API의 synthetic identity/native loopback을 production IAM/cloud 수용과 구분한다.
- Catalog GC race·cross-schema FK 거부를 실제 native SQL로 확인했고 hold 적용→비보호 detail1삭제→새 DB backup/restore·원 catalog/hold 복원을 완료했다. Released1.32.6 ORM writer/새 schema와 새 API/구 schema의 진단503·기존 health200을 실제 실행했다. Production Galera3node의 동시성/운영 복원·용량 수용은 승인된 opt-in 전 선행 조건이다.
- Compiled `/recover`의 warning metadata, browser business request 참조, 관측용 loading이 만든 network reload loop, catalog renewal/draft·role/readiness/base ABA를 교정했다. 실제 실패 전/수정 후 행동 회귀와 최종 source check/i18n/build·canonical gate(backend13758/frontend7037/contracts261/functional259, Ruff863)가 통과했다. Shared root index/review marker를 건드리지 않고 exact source c1cb310a의 private working/staged architecture를 확인했다.
- Root-layout one-time/major4flow·durable worker 연결·실제 collector/SQL 장애·baseline/performance·전체 gate·운영 opt-in 선행 조건의 열린 체크를 완료하기 전 archive하지 않는다. 수집/운영 SQL107/보존 삭제는 기본 꺼짐·미적용이다.
- 실제 compiled collector503에서 원 recovery policy GET200·표시 warning·login link를 보존하고 business GET 추가0·동일 event 최대2시도·transport gap9을 확인했다. Source SQL commit 후 browser ACK만 abort한 실제 경로는201 accepted9→201 duplicate9였으며 원 업무 replay는 없다. Native Chromium offline+synthetic focus burst500은 실제 offline 실패1·batch최대20·queue overflow gap309·기존 recovery 화면/GET1을 보존했다. 이 경계는 읽기 flow 증거이지 업무 쓰기/프로세스 crash 전체 수용 주장이 아니다.
- Actual dedicated Chrome `Page.crash`에서 미전송 focus3개는 SQL에 나타나지 않았고 이전 browser9행/seq1–9가 남았다. SDK 재부착과 명시 reload는 새 segment/seq1로 시작했다. Application 자동 recovery/전체 tail 복구는 주장하지 않는다. Source SQL 미설정/old schema 진단503에서도 기존 health200·원 native 요청 무재전송, permanent failure/dedup/owner/queue 경계를 전체 gate에서 검증했다.
- 첫 성능 pair의429 표본은 폐기하고 동일 frozen compiled tree에서 warm3+OFF20/ON20·policy200-only·65초 cooldown/3300ms pacing을 실행했다. OFF DOM p9596.225ms 뒤 ON 전에+25ms 규칙을 고정했고 ON92.381ms로 통과했다(향상 주장 아님). ON20batch/240event/168020wire bytes·accepted/retained240, signed eligible join60/60/public excluded40, receive→state/DOM p95각1ms다. 전체 사람 session·운영 용량·절대 loss는 미확인으로 명시한다.
- 실제 VM close113ms와 native202/ERROR 응답2973ms 차이를 기록하고 client aborted/unmounted/outcome_unknown·ready0/no VM-worker claim을 유지했다. 최신 원 source resolver/get_os_conn/write/admin guards·override0인 별도 cohort에서 member201/reader403/타scope403·타resource404·갱신access보호200·두번째rotation뒤oldrefresh/access401·새access200을 관측했다. Synthetic native directory와 production IAM은 구분한다.
- ChatPanel과 CloudShell/ContainerTerminal 실제 mounted component→real collector/serialization60회귀는 nonempty state/result/apply/commit 관측과 prompt/tool/output/error·binary command/output·ticket/token/kubeconfig canary 비노출을 확인했다. 외부 peer/xterm/collector HTTP는 통제 fixture이며 실제 provider/terminal/cloud 수용이 아니다. Actual browser input/password/query/body/inert-DOM 및 SQL/log/export scan과 결합하고 expired Node log6개는 UNKNOWN·Maria general/slow OFF는N/A로 남긴다.
- 최신 CSS는768px에서 document0이어도 main 내부8px overflow가 있던 오류를1023px까지 기존 stacking으로 교정했다. 실제767/768/1023/1024×light/dark8조건의 document/main/settings/Card overflow0·action 접근을 확인했다. 고정 budget candidate와 해당 settings-only CSS 수정의 별도 compiled proof를 구분한다.
- 후속 mounted 읽기 실패 회귀: Palimpsest120·ChatPanel65·Audio/Image108이 통과했고 TTS/STT의 A→B→A 실패를 수정 전 재현했다. 최종 source3b539f55/4116의 전체 gate는 backend14130/frontend7203/contracts261/DB263/Ruff865 exit0이다. 세 amd64 packaged image·정본 소유 Compose·worker CLI/crypto·public recovery ACK9/SQL9와 추가 compiled error 경계를 수용했다. 실제7조건 nativeHTTP와 관리자 native503→source404→수정 후503을 검증했다. Schema/bootstrap/core collector는 과거 backup/restore·mixed-version receipt와 byte parity이며 운영 전제는6.7에 남긴다.
- 최종 matched-catalog d63f/d64f의 ON 전체 진단 wire 상한190855B/episode450817B로 기존262144B/1MiB 한계를 통과했다. ACK131중 SQL missing0, ACK 미관측7개는 별도 SQL 존재, eligible38/38, native 추가 mutation0이다. 정확히 HTTP-message로 귀속하지 못한 legacy 연결2418B는 전액 포함했고 해당 header/body 분해·request-ID와 절대 crash loss는 UNKNOWN이다. 이전 d61/d62 불완전 계측은 보존한다.
- 2026-11-05 최종 source/local 수용: 현재 전체 gate0eab16fb/4141files, backend14382/frontend7351/contracts261/DB263/Ruff876 및 실제 amd643이미지·worker CLI/crypto/current source SMTP·22추가 detail/quota 조건과 DB/object4조건을 완료했다. Core SQL375 capture missing0, unsent CephX/password canary SQL/legacy/collector/owned logs0이다. 원 manifest3002항목 중 runtime2973개와29개 명시 non-runtime 제외를 구분하고3175 served-asset 대조를 보존했다. SQL/Redis backup 후 본 작업 소유 fixture만 종료했으며 운영 schema/key/IAM·수집/보존·Hub 원장은 변경하지 않았다.
