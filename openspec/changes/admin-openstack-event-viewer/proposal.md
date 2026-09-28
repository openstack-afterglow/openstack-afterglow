## Why

현재 `activity_logs`는 프로젝트별 최근 변경 기록을 보존하지만 전역 운영 조회/집계가 없고, 자동 감사는 일부 성공한 mutation만 기록한다. 사용자 장애 신고 시 실패한 요청의 원인, 프로젝트, 서비스, 리소스를 한 곳에서 추적할 수 없다. Afterglow 외부에서 발생한 OpenStack 이벤트는 Afterglow HTTP 기록만으로는 알 수 없으므로 별도 알림 수집 경계를 명시해야 한다.

## What Changes

- 기존 활동 테이블을 출처, 서비스, OpenStack/request correlation ID, HTTP 상태와 외부 이벤트 ID로 확장하고 기존 데이터도 조회한다.
- 인증된 Afterglow 변경 요청의 성공/실패를 중복 없이 기록한다. 인스턴스 SSE 실패의 기존 명시 기록을 유지하고 승인된 로그인 성공도 기록한다. 비밀/요청 본문/토큰은 저장하지 않는다.
- 선택적으로 OpenStack oslo.messaging 알림을 전용 durable AMQP queue에서 소비해 정규화한다. 알림이 발행·설정된 서비스만 포착할 수 있으며 알림 미발행 서비스나 broker 불가 상태는 전체 수집으로 광고하지 않는다.
- 시스템 관리자 전용 전역 이벤트 목록/상세/필터/기간별 집계 API와 관리자 사이드바 이벤트 뷰어를 추가한다. 서비스·프로젝트·사용자·상태·액션·리소스별 조사 경로를 제공한다.

## Capabilities

### New Capabilities

- 관리자 이벤트 타임라인, 실패 상세, 필터와 서비스/프로젝트/액션별 실패 빈도.
- 구성된 OpenStack 알림의 영속 소비 및 중복 방지.

### Modified Capabilities

- 기존 사용자/프로젝트 활동 API와 기록의 하위 호환 유지; 기록 출처와 HTTP 실패/성공을 보강.

## Impact

- DB migration 및 AMQP 권한/배포 설정(선택)을 요구한다. DB 불능 시 기록 실패는 요청을 막지 않지만 화면에는 수집 공백이 생긴다. OpenStack 알림은 운영자가 각 서비스의 notification 발행과 broker 접근을 활성화해야 한다. 이전의 누락된 이벤트는 복원되지 않는다.
- dev 워크트리의 다른 미커밋 수정은 보존한다. 별도 지시 없이 배포/커밋하지 않는다.
