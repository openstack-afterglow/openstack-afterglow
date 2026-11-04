# Experience timeline replay

## Purpose

검증된 범위 안에서 사용자 경험의 서버 증거·화면 관측·미확인을 구분하는 한국어 읽기 전용 타임라인과 감사된 export·수용 경계를 정의한다.

## Requirements

### Requirement: Scope-bound experience timeline
시스템은 SHALL 기존 관리자 activity 탐색에 경험 단위 한국어 timeline을 연결하고 사용자 행동·서버 실행·업무 결과·화면 결과·누락을 구분한다.

#### Scenario: 지원 코드 조회
- **WHEN** 운영자가 비밀이 아닌 지원 코드로 경험을 조회한다
- **THEN** 기존 fresh admin/resource scope를 검증하고 허용된 event/operation만 연결하며 코드 자체를 열람 자격으로 취급하지 않는다

#### Scenario: 타 프로젝트 링크
- **WHEN** 인과관계에 현재 viewer 범위 밖 parent/child/operation이 포함된다
- **THEN** 타 scope 내용과 식별 정보를 노출하지 않고 허용된 부분 및 범위 제한만 표시한다

#### Scenario: 한국어 해설과 원래 표시 언어
- **WHEN** 사용자에게 외국어 안내가 표시된 사건을 재생한다
- **THEN** 운영자 해설은 한국어로 제공하고 당시 문구와 locale 증거는 별도로 보존한다

### Requirement: Honest disagreement and incomplete evidence
시스템은 SHALL server proof와 browser observed의 불일치·미확인·위조 가능성·유실을 명시하고 기록되지 않은 과거 사건을 생성하지 않는다.

#### Scenario: 서버와 화면 불일치
- **WHEN** 서버 결과 unknown인데 브라우저가 성공 안내를 신고하거나 서버 성공 뒤 stale 응답을 폐기한다
- **THEN** 두 사실을 나란히 표시하고 한쪽을 다른 쪽의 증거로 대체하지 않는다

#### Scenario: 원격 내부 span 부재
- **WHEN** BFF HTTP 왕복만 있고 형제 서비스 내부 계측은 없다
- **THEN** 왕복 관측과 내부 미확인을 표시하고 native/worker 내부 원인을 추정하지 않는다

### Requirement: Read-only replay and audited export
시스템은 SHALL replay를 비실행 renderer로 격리하고 조회·export를 감사하며 payload를 데이터로 escape하고 정제한다.

#### Scenario: 악성 또는 오래된 이벤트 내용
- **WHEN** 저장된 사건에 임의 HTML/script/URL 또는 과거 operation 참조가 포함된다
- **THEN** 운영 요청·외부 navigation·임의 코드 실행·메일·credential 로드가 발생하지 않는다

#### Scenario: 내보내기
- **WHEN** 허가된 운영자가 경험을 export한다
- **THEN** fresh scope와 필드 allowlist를 다시 적용하고 열람/export의 actor·대상·시각을 별도 감사한다

### Requirement: Complete phased coverage and qualification
시스템은 SHALL 인증/복구·MCP 동의·VM/볼륨 생성부터 실제 compiled browser/API/worker/datastore 경로로 검증하고 전체 주요 기능 계열의 coverage 목록을 관리한다.

#### Scenario: 첫 적용 완료
- **WHEN** 첫 대표 흐름의 검증이 끝난다
- **THEN** 기능별 미계측 범위를 표시하고 첫 흐름만으로 모든 서비스의 comprehensive coverage를 완료 처리하지 않는다

#### Scenario: 운영 전환
- **WHEN** 수집 범위를 운영에서 확대한다
- **THEN** 비밀 누출·scope/ABA·무재실행·유실·부하·mixed-version·복구 수용 증거와 설정/schema-before-writer 승인을 먼저 확인한다
