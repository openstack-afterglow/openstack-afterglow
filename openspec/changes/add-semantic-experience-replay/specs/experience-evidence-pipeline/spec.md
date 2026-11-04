## ADDED Requirements

### Requirement: Credential-free typed collection
시스템은 SHALL client 생성·server 수신·저장/조회/export의 각 경계에서 allowlist를 적용하고 기존 credential/입력/DOM/원본 URL/body/채팅/terminal 비수집 정책을 유지한다.

#### Scenario: 비밀 canary
- **WHEN** password/token/query/hash/request body/채팅/터미널/DOM 자유 텍스트에 식별 가능한 canary를 넣는다
- **THEN** 수집 payload, 진단 저장, 일반 로그, 조회와 export에 해당 값이 남지 않는다

#### Scenario: 검토된 의미 enum
- **WHEN** MCP 접근 수준 같은 안전한 의미 선택을 기록한다
- **THEN** field별 source enum만 허용하고 임의 선택값이나 입력 문자열은 수집하지 않는다

#### Scenario: 잘못된 bearer
- **WHEN** 수집 요청이 잘못됐거나 검증 불가능한 credential을 제시한다
- **THEN** 익명으로 낮추지 않고 기존 인증 경계대로 거부한다

### Requirement: Bounded delivery with deduplication and explicit gaps
시스템은 SHALL 제한된 메모리 queue/batch/body/rate/deadline과 server-scope-bound event dedup을 적용한다. 진단 재전송은 업무 요청을 재실행하지 않으며 누락과 종료의 불확실성을 보존한다.

#### Scenario: 중복과 응답 유실
- **WHEN** 수집 응답이 유실되어 같은 event UUID가 허용된 횟수 내 다시 전달된다
- **THEN** 같은 verified stream/scope에서 한 사건으로 저장하고 다른 scope 사건을 중복 제거하거나 합치지 않는다

#### Scenario: offline과 overflow
- **WHEN** 브라우저가 offline이거나 수집기가 장애/과부하이고 queue가 가득 찬다
- **THEN** 무한 retry/자동 로그인 복구 없이 제한에 따라 폐기하고 가능한 gap/health 증거를 남기며 본 업무 요청의 결과를 바꾸지 않는다

#### Scenario: crash로 마지막 사건 없음
- **WHEN** 브라우저가 종료되어 gap 통지도 보내지 못한다
- **THEN** 마지막 관측 이후를 미확인으로 표시하고 사건 부재를 사용자 무행동이나 서버 실패로 단정하지 않는다

#### Scenario: 순서가 다른 수신
- **WHEN** client/server/worker 사건이 역순 또는 중복 수신되거나 시계가 어긋난다
- **THEN** 구간 sequence와 causal edge를 사용하고 증명되지 않은 전역 순서를 확정하지 않는다

### Requirement: Distinct audit durability and diagnostic storage
시스템은 SHALL 기존 업무 감사·작업 원장의 권위와 보존 정책을 진단 데이터와 분리한다. Best-effort 로그를 lossless 원장으로 승격하지 않고 native 효과와 SQL의 원자성을 주장하지 않는다.

#### Scenario: 진단 sink 장애
- **WHEN** 진단 저장이 실패해도 기존 도메인에서 업무 결과가 확정된다
- **THEN** 진단 실패만으로 native 요청을 replay/rollback하지 않고 기존 업무 감사 정책을 유지한다

#### Scenario: 고빈도 관측
- **WHEN** UI state 사건 수가 증가한다
- **THEN** 모든 사건을 기존 ActivityLog 테이블에 복제하지 않고 측정·검토된 별도 진단 저장과 제한된 projection을 사용한다

### Requirement: Versioned rollout and reviewed retention
시스템은 SHALL 구형/신형 schema의 수용 범위를 표시하고 수집·보존 삭제를 명시 승인 없이 운영 활성화하지 않는다.

#### Scenario: 구형 서버 또는 reader
- **WHEN** 필요한 schema/catalog/span 계약을 제공하지 못한다
- **THEN** unsupported/partial coverage를 표시하고 fake fallback이나 legacy 관측으로 전체 재생 성공을 주장하지 않는다

#### Scenario: 보존 활성화와 삭제
- **WHEN** 운영 보존 정책을 적용한다
- **THEN** 상세30일/집계90일 초안의 승인 여부, audit 별도 보존, index/export/backup/hold와 복구 경계를 확인하고 승인된 범위만 삭제한다
