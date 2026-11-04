## Context

이 문서는 승인된 설계이며 구현 완료 기록이 아니다. 현재 소스 확인:

- `frontend/src/lib/utils/interactionAudit.ts:3-10`: click/submit/navigation/client_error/request_failed와 role/ordinal/route만 관측한다. `82-88`의 조작 문맥은 다음 timer turn에서 종료되어 비동기 후속 호출의 인과관계를 보장하지 않는다. `116-140`은 bounded best-effort 전송이다.
- `backend/app/api/common/interactions.py`: strict 필드·body/batch/rate 제한, 검증된 actor/scope와 익명 페이지 경계가 있다.
- `backend/app/main.py`의 `activity_audit_middleware`: server request ID·인증 단계·업무 terminal과 SSE200 구분을 이미 소유한다.
- `backend/app/services/activity.py:73-145`: 일반 감사 기록 일부는 DB 장애/기록 실패 때 best-effort다. 새로운 기능의 lossless 보장 근거로 사용할 수 없다.
- `backend/app/utils/auth_diagnostics.py`: source literal 단계·소요 시간·안전한 오류 종류를 이미 지원한다.
- `docs/security.md:304-312`: 원문 입력/DOM/URL/query/hash/body/credential 비수집, browser observed와 server proof 분리, scope/ABA fence가 정본이다.
- `openspec/changes/admin-openstack-event-viewer/tasks.md`: 기존 관리자 event 검색/상세/통계가 있으므로 이를 대체하는 두 번째 감사 viewer를 만들지 않는다. 새로운 경험 단위 projection을 연결한다.

## Goals / Non-Goals

**Goals:**
- 사용자 경험·서버 처리·화면 결과를 같은 인과관계로 조회한다.
- 한국어 운영 해설과 당시 사용자 표시 언어를 분리하고, 실패/불명/누락을 숨기지 않는다.
- 원래 인증·권한·비밀·일회용 요청·업무 원장·취소 drain 계약을 보존한다.
- 인증/복구, MCP 동의, VM/볼륨 생성의 실제 경로로 먼저 검증하고 모든 주요 기능 계열의 적용 목록을 완료한다.

**Non-Goals:**
- DOM snapshot, 화면/동영상 녹화, 입력값/채팅/터미널 원문 수집, 픽셀 동일 재생.
- replay에서 운영 HTTP 호출·메일·native mutation 재실행.
- 기존 로그에 없는 과거 사실 생성, 브라우저 신고로 서버 성공/신원/권한 증명.
- 이 계획 승인만으로 운영 수집/보존 삭제/배포/스키마 적용 활성화.

## Decisions

### 1. 의미 기반 사건 계약

기존 수집기의 정책·owner fence를 재사용한다. v1 payload에 임의 필드를 섞지 않고 별도 v2 schema/수집 경로로 전환하며 old API와 공존 중 unsupported 서버에 downgrade한 의미를 성공처럼 보여주지 않는다. 후보 경로는 `POST /api/v1/activity/experience-events`다. 실제 endpoint/설정 소유권은 구현 전 기존 router와 확정한다.

공통 envelope:
- `schema_version`, `event_id`, `event_type`, `source`.
- `experience_segment_id`, `page_view_id`, `action_id`, `caused_by_event_id`.
- `request_id`, `trace_id`, `span_id`, `parent_span_id`, `operation_id`, `attempt`(해당 사건에만).
- `client_seq`, `client_monotonic_ms`, client 발생 시각과 server 수신 시각을 별도 저장.
- frontend build, backend/service revision, catalog revision, redaction policy version.
- allowlisted route/action/component·stage/status/reason·duration·비민감 typed payload.

필수/선택 필드·크기·enum·per-event payload는 구현1단계에서 단일 registry로 확정하고 schema fixture에서 검증한다. Token/raw URL/user-supplied actor는 envelope가 아니다. Client ID는 인과 탐색용 비신뢰 값이며 서버 origin·actor·scope를 대신하지 않는다. Server/worker 사건은 서버 소유 IDs와 신뢰 provenance로 기록한다.

이벤트 계열:
- UI: `view.entered`, `view.state_changed`, `action.started`, `validation.rejected`, `message.presented`, `result.applied`, `result.discarded`, `view.exposure_changed`.
- 실행: operation accepted/running/terminal, source-owned stage 시작/종료, dispatch/readback, queue claim, lease lost, retry attempt, cancel requested/drained.
- 수집 상태: `telemetry.gap`, dropped/truncated/sampled 구간, 수집 종료 원인.

### 2. 명시적 인과관계와 owner 수명

동시 task에도 공유 전역 last-click 변수에 의존하지 않는다. Action context를 API 호출·follow-up GET·SSE·worker operation에 명시 전달한다. 장기 native 작업의 원장에 연결키를 보존하되 자격이나 business payload를 복사하지 않는다. Existing operation ID를 재사용하며 diagnostic ID를 idempotency key로 쓰지 않는다.

탭별 구간을 사용하고 logout/user/home/project 전환 때 새 구간을 연다. Same-owner bearer rotation은 구간을 유지한다. 익명→로그인도 구간을 분리하며 명시 전환 관계만 연결하고 익명 행을 확인된 계정으로 소급 변경하지 않는다. 다른 scope의 폐기 사건은 이전 owner 식별자를 새 계정으로 보내지 않으며 기존 정제 규칙 아래 원래 구간의 허용된 사건만 보존한다.

Client sequence+monotonic time은 같은 구간의 순서, causal edge는 요청/worker 간 관계를 나타낸다. 시계 오차·역순 수신·동시성을 보존하고 DB ID나 wall time만으로 확정 total order를 만들지 않는다.

### 3. 업무 결과와 화면 결과 분리

서버 결과: `accepted`, `running`, `succeeded`, `failed`, `cancel_requested`, `cancelled`, `outcome_unknown`. 성공 조건은 기능별 기존 authoritative readback/원장 계약으로 정의한다. HTTP202/SSE200/timeout을 terminal로 합성하지 않는다. 취소 요청과 실제 native 종료·정리 완료는 별개다.

브라우저 결과: 수신→현재 owner에 적용→DOM commit→viewport/활성 탭 노출 관측. DOM 반영은 화면 state owner에서 기록하고 공통 Button click만으로 추정하지 않는다. 사람이 읽거나 이해했다는 증거로 표시하지 않는다. 클라이언트 종료 뒤 최종 사건이 없으면 화면 반영 미확인이지 failure가 아니다. `result.discarded`는 stale/abort/scope_changed 등 고정 이유를 기록한다.

### 4. 메시지·언어와 프라이버시

`message_key`, 실제 메시지 생성/표시 locale, 당시 catalog/build revision, tone과 허용된 typed parameter만 기록한다. 현재 locale만으로 과거 메시지 언어를 추정하지 않는다. 보존된 정적 catalog로 복원하고 비민감하지 않은 parameter는 마스킹한다. 원본 catalog가 없으면 복원 불가로 표시한다.

금지 데이터: 비밀번호·token/code/ticket/cookie/header 원문·query/hash·request/response body·free-text DOM·채팅/프롬프트/도구 인수결과·terminal·kubeconfig/key/cloud-init·임의 파일/자원 이름. 모든 입력의 값은 기본 금지다. 의미적으로 필요한 source enum(예: 승인 접근 read/manage)은 field별 검토된 typed allowlist에서만 허용하며 원 form value를 수집하지 않는다.

Client 생성 allowlist→strict server schema→storage/query/export 재정제, 3중 방어를 적용한다. Client canary leak와 ingress/외부 agent 로그 범위도 검증한다. Client error는 고정 fingerprint와 배포 revision을 우선 사용하고 message/stack/locals를 무조건 수집하지 않는다.

### 5. 전송·감사·저장 분리

진단은 best-effort, 중요한 업무 감사는 기존 도메인의 내구성 정책을 따른다. Native 효과와 SQL write의 원자성을 주장하지 않는다. Audit 원장이 이미 있으면 참조하며 diagnostics 때문에 native 요청을 retry/rollback하거나 성공 판정을 변경하지 않는다.

v2 ingest는 `(server-verified scope, source stream, event_id)` dedup을 제공한다. 크기·횟수·deadline이 제한된 동일 이벤트 재전송만 허용하며 original API의 재실행과 분리한다. 큐는 bounded memory 기본이고 raw payload·credential을 브라우저 영구 저장하지 않는다. 기한/owner fence 초과는 폐기하고 누락을 남긴다. Crash로 누락 통지조차 없을 때는 viewer가 구간의 마지막 관측 이후를 미확인으로 표시한다. Collector 자체 이벤트의 재귀 수집은 금지한다.

모든 고빈도 이벤트를 `ActivityLog` row로 추가하지 않는다. 기존 업무 감사와 별도 MariaDB6-table 진단 영역을 사용하고 projection에서 참조 연결한다. 초기858개 legacy sanitized row의 p50/p95/max354/392/425byte는 wire/세션/SQL 물리 크기가 아니며 기존 SQL 기반 저용량 선택의 출발 자료일 뿐이다. 실제 v2 native QA snapshot은 browser3700행의 JSON p50/p95/max863/927/1053byte, API2828행846/868/938byte, worker3행829/832/832byte를 측정했다(nearest-rank, 별도 column/index/binlog/replica 제외). 반복 benchmark가 포함된 bounded segment를 전체 사람 세션으로 환산하지 않는다. `owned-storage-measurement.json`과 실제 paired browser/API 수용으로 현 구현 비용을 추적하며 운영 동시 사용자·수집률·Galera 용량은 승인된 opt-in 전 별도 검증한다.

보존은 default detail30일/aggregate90일이고 event dedup은 exact-owner/segment/event, catalog FK는 RESTRICT다. CLI maintenance row lock/write·bounded dry-run/apply·exact-owner hold/release와 무조건 catalog GC 금지를 구현했다. 격리 native MariaDB의 실제6-table backup→새 DB restore·원 catalog/hold 복원, 구1.32.6 ORM writer/새 schema·새 API/구 schema의 진단503/기존 health200 경계를 실행했다. 이는 production Galera 동시성·운영 복원을 대체하지 않는다. 시각 자료는 수집하지 않고 audit는 기존 별도 정책을 유지한다. Export는 no-store·정적 다운로드만 제공하며 배포된 외부 사본/백업의 만료는 운영 보존 절차가 필요하다. 단순 집계를 자동으로 비식별로 선언하지 않는다.

### 6. 한국어 경험 조회와 안전한 재생

기존 admin event viewer에 경험 단위 탐색을 연결한다. 비밀이 아닌 지원 코드로 exact segment/action을 찾되 코드 지식 자체가 열람 권한은 아니다. AdminResourceScope 등 기존 fresh scope를 모든 event/operation/read/export에 적용한다. Cross-project action은 허용된 부분만 표시하고 타 범위 parent/link 내용은 숨긴다. 익명 구간은 별도 운영 권한으로만 조회한다.

사용자 행동/서버 실행/화면 결과를 구분해 한국어로 설명한다. 상충·누락·미확인·샘플링과 원격 서비스 span 부재를 명시한다. Historical event/string은 데이터로 escape하고 재생 iframe/상태 renderer는 운영 API 호출, 임의 HTML/URL/script 실행, live credential 로드가 불가능해야 한다. 조회·export 자체도 감사한다.

### 7. 구현 순서와 배포 경계

1. 계약/카탈로그/현재 coverage·비밀 분류·부하 baseline·저장/보존 선택.
2. explicit action→request→operation→worker correlation과 strict v2 ingestion.
3. 공통 UI와 실제 feature state owner의 상태·메시지·화면 반영 계측.
4. 인증·MCP·VM/볼륨 및 나머지 기능 계열의 실행 단계·결과 연결.
5. 진단 저장·누락·query/export·보존 및 한국어 재생 UI.
6. 실제 source API/UI/worker+독립 테스트 datastore 검증, 혼합 버전·장애·복구·배포 선행 조건 확인.

UI 작업 전 DESIGN.md/기존 primitives 검토, endpoint pytest, named target→gate와 실제 compiled browser smoke, 새 schema-before-writer·API/worker cohort·복구·원 key 보존은 기존 규정을 따른다. 이 계획은 구현 승인/운영 적용을 혼동하지 않는다. 미완료 change는 archive하지 않는다.

## Risks / Trade-offs

- 의미 재생은 픽셀/입력값 재생이 아니다 → redacted/미기록 영역을 명시한다.
- Browser observations는 위조/차단/유실 가능 → 서버 proof와 별도 provenance, unknown/gap 표시.
- 세밀한 모든 함수 로그는 비용/잡음·민감정보를 늘림 → 업무 경계 span과 typed source enum만 채택.
- 높은 cardinality/SQL 부하 → 기존 audit 분리, 측정 후 저장 선택. 성능 budget은 baseline 결과를 근거로 구현 전 확정한다.
- 오래된 catalog/배포 혼합 → schema/build/catalog version과 unsupported 구간 표시.
- Collector 중단 → 본 업무와 분리; 내구성 audit 요구는 기존 도메인별 정책 유지.
- 형제 서비스 span 누락 → BFF 왕복 시간만 사실로 표시하고 내부 원인을 추정하지 않음.

## Rollout / Rollback Gates

수집 default-off → 합성/local 전체 acceptance → 승인된 제한 구간 opt-in → loss/성능/유출/인가 관측 → 확대 순서다. 단순 config 렌더·container healthy를 end-to-end 수용으로 대체하지 않는다. Feature-off가 새 진단 수집과 export를 중단해도 기존 감사/operation 결과는 유지한다. Additive schema의 downgrade 제약·old/new writer/reader와 실제 backup 복구를 검증하고 blind image rollback이나 과거 데이터 삭제를 수행하지 않는다.
