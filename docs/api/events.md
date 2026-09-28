---
title: 관리자 이벤트
parent: API 레퍼런스
---

# 관리자 이벤트 조회

`/api/v1/admin/events`는 `require_admin` 시스템 관리자만 사용할 수 있습니다. 사용자 개인 기록(`/api/v1/profile/activity`) 및 프로젝트별 기록(`/api/v1/admin/projects/{project_id}/activity`)과 동일한 `activity_logs` 이력을 전역으로 조회합니다. 읽기 API는 OpenStack에 실시간 요청하지 않으며, 과거에 기록되지 않은 사건을 소급 생성하지 않습니다.

| 메서드 | 경로 | 결과 |
|---|---|---|
| `GET` | `/api/v1/admin/events` | ID 내림차순 이벤트 배열. `limit` 기본 50, 1–200. 마지막 행의 `id`를 `before_id`로 전송해 다음 페이지 조회 |
| `GET` | `/api/v1/admin/events/stats` | 현재 필터의 총/성공/실패/진행 중 건수와 서비스·프로젝트·페이지·액션별 `{key,total,failed}` 집계 |
| `GET` | `/api/v1/admin/events/{id}` | 단일 이벤트 상세, 없으면 404 |

목록·집계는 `project_id`, `user_id`, `username`, `resource_type`, `resource_id`, `action`, `status` (`started`, `success`, `failed`), `service`, `source` (`afterglow`, `openstack`), `request_id`, `page`, `from_at`, `to_at`을 공유합니다. 기간은 UTC 오프셋이 포함된 ISO 8601 시각으로 지정하며 페이지 커서는 집계에 적용되지 않습니다. 서비스·페이지의 실패 건수는 **기록된 행** 기준이며 운영 서비스의 실제 전체 오류 수나 고유 요청 수가 아닙니다.

각 이벤트는 `created_at`, `project_id`, `user_id`, `username`, `resource_type`, `resource_id`, `resource_name`, `action`, `status`, `error_message`, `extra`, `source`, `service`, `page`, `request_id`, `external_id`, `event_type`, `http_status`를 포함합니다. 기존 행의 `source=null`은 API에서 `afterglow`로 표시하고 같은 출처 필터에 포함합니다. 나머지 신규 컬럼은 기존 행에서 `null`입니다. `X-Request-Id`는 Afterglow가 처리한 변경 요청에서 생성하는 추적 ID이며 OpenStack이 발행한 `request_id`와 자동으로 동일하지 않습니다. 동일 자원 ID·프로젝트·시간을 함께 확인하세요.

## 수집 범위와 운영 경계

- Afterglow의 인증된 자원 변경 요청은 명시적으로 기록한 결과가 우선하며, 기록이 없는 경로는 감사 미들웨어가 성공/실패 HTTP 결과를 기록합니다. SSE 응답의 200 handshake는 최종 성공이 아니므로 기록하지 않고 생성 작업 자체의 종료 이벤트를 사용합니다. 승인된 password/GitLab 로그인을 기록하지만 로그인 실패에는 검증된 사용자 ID가 없어 임의의 신원을 부여하지 않습니다.
- HTTP 202는 완료가 아닌 `started`로 기록합니다. 관리자 화면의 새로고침은 적용된 조건을 유지하면서 조회 기간의 끝을 현재 시각으로 갱신합니다. 다음 페이지는 같은 기간을 유지합니다.
- OpenStack 자체에서 발행한 알림은 별도의 **선택적** RabbitMQ AMQP 0-9-1 collector 설정과 각 서비스의 notification 발행이 있어야 도착합니다. 알림이 발행된다면 CLI/Horizon/내부 작업도 수집할 수 있지만, 해당 서비스가 발행하지 않는 이벤트·설정 이전 기록·끊긴 broker·누락된 사용자/프로젝트 정보는 추론할 수 없습니다. `source=openstack`은 Afterglow 요청 결과와 구분합니다. Keystone CADF의 명시적 outcome과 Nova/Cinder의 종료/오류 접미사는 성공·실패 상태를 정규화하며, 불확실한 알림은 `started`로 남습니다.
- native 알림의 원문 오류 메시지/metadata는 비밀값이 섞일 수 있어 저장하지 않습니다. 오류 알림은 안전한 식별자 형태의 `extra.error_type` (예: `MaxRetriesExceeded`), 숫자 `extra.error_code`/`http_status`가 있을 때만 원인을 좁혀 표시합니다. 명시된 값이 없다면 원문을 추측하거나 만들어내지 않습니다. 비정상·과대 payload는 거부하고 재시도하지 않으며, broker 복구 시 이미 ack하지 않은 메시지는 DB 외부 ID 제약으로 중복 없이 재전달합니다. Durable queue 자체는 발행자가 persistent 메시지를 보내고 broker 저장 정책이 유지되어야 재시작 후 내구성이 있습니다.
- 수집 DB가 사용 불가능한 동안 Afterglow의 best-effort 활동 기록은 요청을 중단시키지 않습니다. 관리자 조회는 DB 장애를 빈 기록으로 가장하지 않습니다. 중요한 보안/컴플라이언스 감사의 유일한 저장소로 사용하지 마세요. API는 비밀번호·토큰·요청 본문·원본 알림 payload를 저장하지 않습니다.
