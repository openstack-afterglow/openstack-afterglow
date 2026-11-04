---
title: 관리자 이벤트
parent: API 레퍼런스
---

# 관리자 이벤트 조회

`/api/v1/admin/events`는 `require_admin` 시스템 관리자만 사용할 수 있습니다. 사용자 개인 기록(`/api/v1/profile/activity`) 및 프로젝트별 기록(`/api/v1/admin/projects/{project_id}/activity`)과 동일한 `activity_logs` 이력을 전역으로 조회합니다. 이벤트 자체는 DB에 저장된 이력이며 과거에 기록되지 않은 사건을 소급 생성하지 않습니다. 선택 `domain_id`를 지정한 조회는 현재 Keystone 도메인·소유 프로젝트를 새로 확인합니다.

| 메서드 | 경로 | 결과 |
|---|---|---|
| `GET` | `/api/v1/admin/events` | ID 내림차순 이벤트 배열. `limit` 기본 50, 1–200. 마지막 행의 `id`를 `before_id`로 전송해 다음 페이지 조회 |
| `GET` | `/api/v1/admin/events/stats` | 현재 필터의 총/성공/실패/진행 중 및 browser 관측 건수와 서비스·프로젝트·페이지·액션별 `{key,total,failed}` 집계. 관측0이면 기존 호환 응답에 observed를 생략할 수 있음 |
| `GET` | `/api/v1/admin/events/{id}` | 단일 이벤트 상세, 없으면 404 |

목록·집계는 `domain_id`, `project_id`, `user_id`, `username`, `resource_type`, `resource_id`, `action`, `status` (`started`, `success`, `failed`, `observed`), `service`, `source` (`afterglow`, `openstack`, `browser`), `request_id`, UUID `interaction_id`, `page`, `from_at`, `to_at`을 공유합니다. 선택 domain과 project는 독립적인 AND 조건이며 교집합이 없으면 빈 목록·0집계입니다. Fresh project UUID 집합을 SQL WHERE에 넣어 cursor/limit/aggregate 전에 적용하고 단일 상세도 선택 scope 밖이면404입니다. 익명·projectless 관측은 임의 domain에 귀속하지 않아 global admin에서만 보일 수 있습니다. Directory 장애는 전역 결과나 빈 성공으로 대체하지 않습니다. 기간은 UTC 오프셋이 포함된 ISO8601 시각이며 커서는 집계에 적용되지 않습니다. 건수는 stage와 observation을 포함한 기록 행이지 고유 작업·전체 cloud 오류 수가 아닙니다.

각 이벤트는 `created_at`, `project_id`, `user_id`, `username`, `resource_type`, `resource_id`, `resource_name`, `action`, `status`, `error_message`, `extra`, `source`, `service`, `page`, `request_id`, `external_id`, `event_type`, `http_status`를 포함합니다. 기존 행의 `source=null`은 API에서 `afterglow`로 표시하고 같은 출처 필터에 포함합니다. 나머지 신규 컬럼은 기존 행에서 `null`입니다. `X-Request-Id`는 Afterglow가 처리한 변경 요청에서 생성하는 추적 ID이며 OpenStack이 발행한 `request_id`와 자동으로 동일하지 않습니다. 동일 자원 ID·프로젝트·시간을 함께 확인하세요.

## 수집 범위와 운영 경계

- 서버는 인증된 자원 변경의 명시 terminal 결과를 우선하고, 인증 요청·사용자 동작과 연결된 API·API 실패에 구조화 request/stage 관측을 추가합니다. 로그인 성공과 신원 미확인 로그인 실패, 처리 중 성공/실패 및 request-context application warning/error를 분리합니다. 검증되지 않은 username을 제출 값에서 복사하거나 원문 예외를 저장하지 않습니다. 성공한 비연결 polling/health와 ingestion 자체는 추가 click/request 이력을 재귀 생성하지 않습니다. SSE200 handshake는 최종 성공이 아니므로 생성 작업 자체의 종료 이벤트가 필요합니다.
- HTTP 202는 완료가 아닌 `started`로 기록합니다. 관리자 화면의 새로고침은 적용된 조건을 유지하면서 조회 기간의 끝을 현재 시각으로 갱신합니다. 다음 페이지는 같은 기간을 유지합니다.
- OpenStack 자체에서 발행한 알림은 별도의 **선택적** RabbitMQ AMQP 0-9-1 collector 설정과 각 서비스의 notification 발행이 있어야 도착합니다. 알림이 발행된다면 CLI/Horizon/내부 작업도 수집할 수 있지만, 해당 서비스가 발행하지 않는 이벤트·설정 이전 기록·끊긴 broker·누락된 사용자/프로젝트 정보는 추론할 수 없습니다. `source=openstack`은 Afterglow 요청 결과와 구분합니다. Keystone CADF의 명시적 outcome과 Nova/Cinder의 종료/오류 접미사는 성공·실패 상태를 정규화하며, 불확실한 알림은 `started`로 남습니다.
- native 알림의 원문 오류 메시지/metadata는 비밀값이 섞일 수 있어 저장하지 않습니다. 오류 알림은 안전한 식별자 형태의 `extra.error_type` (예: `MaxRetriesExceeded`), 숫자 `extra.error_code`/`http_status`가 있을 때만 원인을 좁혀 표시합니다. 명시된 값이 없다면 원문을 추측하거나 만들어내지 않습니다. 비정상·과대 payload는 거부하고 재시도하지 않으며, broker 복구 시 이미 ack하지 않은 메시지는 DB 외부 ID 제약으로 중복 없이 재전달합니다. Durable queue 자체는 발행자가 persistent 메시지를 보내고 broker 저장 정책이 유지되어야 재시작 후 내구성이 있습니다.
- 수집 DB가 사용 불가능한 동안 Afterglow의 best-effort 활동 기록은 요청을 중단시키지 않습니다. 관리자 조회는 DB 장애를 빈 기록으로 가장하지 않습니다. 중요한 보안/컴플라이언스 감사의 유일한 저장소로 사용하지 마세요. API는 비밀번호·토큰·요청 본문·원본 알림 payload를 저장하지 않습니다.

## 브라우저 버튼·링크 동작 수집

`POST /api/v1/activity/interactions`는 system-admin 조회 API와 별개인 수집 endpoint입니다. Content-Type은 `application/json`, body는 최대16KiB, batch는1–20개, trusted source-address 기준60요청/분입니다. 인증이 있으면 기존 token 검증으로 사용자/프로젝트를 결정하고 잘못된 bearer를 익명으로 낮추지 않습니다. 인증 없이 허용하는 것은 `/`, 로그인·가입·복구·초대·등록·문서·auth/OAuth 등 공개 route 관측뿐이며 private page는401입니다.

```json
{"events":[{"kind":"click","page":"/dashboard/compute/instances","control":"button","ordinal":3,"interaction_id":"11111111-1111-4111-8111-111111111111"}]}
```

- `kind`: `click|submit|navigation|client_error|request_failed`; `page` 필수, `control` 선택(`button|link|form|summary|combobox|checkbox|switch|option|other`), `ordinal` 선택 정수0–10000, `destination` 선택 source route 또는 `external`, `interaction_id` 필수 UUID입니다. Source-literal route segment만 보존하고 동적 resource/token segment는 `:id`로 바꿉니다. Query/hash/percent/원본URL·임의 text/value/label/actor/project/status 같은 추가 field는 거부합니다.
- 수용201은 `{"accepted":개수}`이며 한 transaction으로 browser/observed/ui.* 행을 저장합니다. 이는 버튼/링크가 관측됐다는 신고이지 로그인·native 생성·업무 성공 proof가 아닙니다. 형식422·body초과413·Content-Type415·인증401/권위503·한도429·저장 불가503을 구분하고 실패를 accepted로 반환하지 않습니다.
- Root collector는 마우스/키보드 button·link activation, form submit, 이동, 안전한 client/API 실패 metadata만 관측합니다. 메모리 최대200개·batch20으로 전송하며 원문 입력/선택 값·DOM text/label·URL query/hash·credential·body·stack/message는 읽어 전송하지 않습니다. Ordinary same-owner 자격 갱신은 최신 token으로 보내되 logout/사용자/프로젝트/authority 세대 교체는 대기 관측을 다른 소유자에게 귀속하지 않습니다. Mockup/tutorial은 수집하지 않습니다.
- 서버 `request_id`는 자체 생성되고 `X-Afterglow-Interaction-Id`는 client가 신고한 UUID를 정제한 별도 연결 값입니다. 이 header나 browser row는 신원·권한·완전한 인과관계의 증명이 아닙니다. 관리자 상세는 동일 scope/기간의 최대50개 관련 행을 조회하고 출처별로 나눠 확인합니다. Method/template/stage/duration·구조 control/순번/destination·오류 class/code와 application source 위치만 allowlist로 표시합니다.
- Browser buffer/drop/failure는 현재 tab의 관측이며 server 전체 수집률이나 무손실 전달 보장이 아닙니다. 실패·응답 불명 POST를 자동 재전송하거나 인증 복구를 실행하지 않고, DB/offline/page 종료/crash/차단기·scope 변경에서 누락될 수 있습니다. 기존 best-effort 감사·선택 native notification collector와 별개이며 보존기간을 새로 정하거나 과거 이력을 소급 생성하지 않습니다.

## 의미 기반 경험 관측 v2 — 기본 꺼짐

`[experience].enabled=true`인 별도 승인 환경에서만 다음 API를 제공합니다. 기존
`activity_logs`와 v1 interaction 계약은 유지하며 v2 진단 행은 SQL107의 별도
`experience_*` 테이블에 저장합니다. 화면 녹화·입력 재생·업무 API 재실행 기능이 아닙니다.

| 메서드 | 경로 | 계약 |
|---|---|---|
| `GET` | `/api/v1/activity/experience-contract` | `schema_version=2`, redaction revision, backend build와20개/32768byte 한도. 꺼짐은404 |
| `POST` | `/api/v1/activity/experience-events` | JSON v2 batch1–20개, 전체32KiB,60회/분.201 `{schema_version,accepted,duplicates}` |
| `GET` | `/api/v1/admin/experiences/segments` | 현재 scope의 최근 구간 metadata. `days=1|7|30`(기본1), 선택 exact `user_id`(1–64), `limit=1..50`(기본20) |
| `GET` | `/api/v1/admin/experiences` | 필수 canonical UUID `segment_id`, 선택 UUID `action_id`, 양수 `before_id`, `limit=1..200`(기본200) |
| `GET` | `/api/v1/admin/experiences/export` | 같은 필터·권위의 static JSON download. 최대2000행; 원래 자원 API를 호출하지 않음 |

### 수집·신뢰 경계

- Envelope는 `schema_version=2`, `redaction_revision=1`, `event_id`, `segment_id`,
  `page_view_id`, sequence·monotonic elapsed·timezone 시각, canonical source route,
  registry의 `feature/action/component`, frontend/catalog revision과 event별 strict
  payload를 사용합니다. 선택 action/cause/trace/span UUID는 연결 참조이지 권위가 아닙니다.
  임의 필드·입력·actor/project/source·업무 성공 선언·원본 URL/query는 거부합니다.
- Browser event는 view/action/validation/message/result/exposure/gap 관측만 허용합니다.
  Actor/project는 기존 인증 결과, `source=browser`와 수신 시각은 서버가 결정합니다.
  잘못된 bearer를 익명으로 낮추지 않으며 익명은 등록된 공개 route만 허용합니다.
  검증422·body413·JSON415·인증401·rate429·event identity409·SQL503을 구분합니다.
- `(trusted owner,segment_id,event_id)`가 같은 동일 payload는 중복 삽입하지 않습니다.
  같은 ID의 다른 payload 또는 server-source 행과의 충돌은409입니다. v2 진단 전송은
  최대 두 번으로 제한하지만 업무 POST·one-time callback·unknown native 작업은 재실행하지 않습니다.
- API client는 명시 context를 비동기 경계로 전달합니다. Server request pair와 실제 HTTP
  transport, operation 및 지원하는 Afterglow worker 단계는 별도 출처입니다. Shared/cache
  응답과 physical request도 구분합니다. 형제 서비스의 미지원 내부 span은 만들어내지 않습니다.
- `blocking`은 일반 동기 호출, `native`는 명시적으로 표시한 native 호출입니다.
  `cancel_requested`는 취소 요청만 뜻합니다. `blocking.drain`/`native.drain`의 `observed`는
  해당 소유 호출이 실제 종료된 뒤에만 남기는 종료 확인이며 provider 작업 취소·guest 준비·
  업무 성공을 뜻하지 않습니다. SDK가 응답한 뒤에도 외부 효과가 불명일 수 있습니다.
  Caller 취소·lease 상실 중에도 진단 저장 실패가 실제 drain/connection 정리를 중단시켜서는 안 됩니다.
- 최대200개 tab memory queue,60초 deadline과 bounded gap counter를 사용합니다.
  Logout/owner/project/권위/ABA/tutorial 전환은 이전 관측을 새 owner로 재귀속하지 않습니다.
  종료·crash·offline·SQL 장애의 tail은 복구 보장이 없으며 지원 코드는 저장 성공 영수증이 아닙니다.

### 조회·한국어 해설

조회는 매번 `require_admin`과 fresh `AdminResourceScope`를 사용합니다. Domain/project
교집합을 SQL WHERE에서 limit 전에 적용하고 child/operation 참조도 같은 owner/scope로
제한합니다. `include_anonymous=true`는 operator의 별도 `anonymous_read_enabled=true`,
현재 전역 관리자, domain/project 미선택이 모두 필요합니다. 지원 코드만으로 조회 권한이
생기지 않습니다. SQL·권위·열람 감사 commit 실패는503이며 빈 정상 결과로 위장하지 않습니다.

최근 검색은 `{schema_version,segments,has_more,coverage}`를 반환합니다. Segment metadata는
`segment_id,user_id,project_id,last_received_at,event_count`만 포함합니다. 기간은 서버 수신
시각 기준이고 count는 저장 행 수입니다. 고유 사용자·업무 횟수·전체 수집률을 뜻하지 않습니다.
정확 조회/export는 `{schema_version,events,catalogs,has_more,coverage}`이며 ID 내림차순
bounded window입니다. Cross-window/off-scope 참조는 지우거나 미확인으로 표시합니다.
시계 오차 때문에 wall time을 전체 인과 순서로 해석하지 않습니다.

카탈로그는 이 bounded·인가된 window에서 나온 ID만 일괄 조회하고 각 사건의 revision/key/실제
locale을 따로 대조합니다. 같은 catalog ID를 공유하는 다른 사건이 복원됐다는 이유로 불일치 사건의
복원을 허용하지 않습니다. 사라지거나 불일치한 카탈로그는 해당 사건만 `unavailable`입니다.

관리자 기존 이벤트 화면에서 최근 지원 코드 검색→구간 선택→정확 조회→export를 각각
사람이 실행합니다. 각 disclosure는 기존 업무 감사에 기록하고 응답은 `no-store/nosniff`입니다.
브라우저 신고·서버 요청 proof·업무 terminal·결과 수신·상태 적용·DOM commit·document/viewport
노출·폐기를 구분합니다. DOM commit/노출도 사용자의 인지 증거가 아니며, 누락·tail·미지원
remote span은 한국어로 명시합니다. HTML/script/URL/operation 참조는 실행하지 않습니다.

메시지는 producer가 실제 표시한 key·locale·정확한 catalog revision만 보존합니다. 현재 선택
언어와 과거 formatted 오류의 언어가 달라도 후자로 기록합니다. 정적 template는 참조 중인
immutable catalog로 복원하고 임의 parameter·오류 원문은 수집하지 않습니다. 카탈로그가 없으면
`unavailable`, 민감/dynamic 값은 `redacted`이며 최신 번역으로 과거 문구를 추측하지 않습니다.

보존·hold·backup/restore·운영 opt-in은 [배포 가이드](../deployment.md#의미-기반-경험-관측-v2의-전환과-보존)를
따릅니다. 기존 업무 감사와 unknown/irreversible 작업 원장은 이 진단 보존 정책으로 삭제하지 않습니다.
