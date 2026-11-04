## Why

현재 사용자 행동 관측과 서버 감사만으로는 사용자가 무엇을 보았고, 내부에서 무엇이 처리됐으며, 그 결과가 왜 화면에 적용되거나 폐기됐는지 한 사건으로 설명하기 어렵다. 승인된 방향은 민감정보 원문이나 화면 녹화 대신 의미 기반 경험 타임라인을 구축하고 서버 사실과 브라우저 관측을 명확히 분리하는 것이다.

## What Changes

- 기존 interaction/request/activity/operation 경계를 확장해 경험 구간 → 화면 → 사용자 작업 → API/worker/native 실행 → 업무 결과 → 화면 반영을 연결한다.
- 소스 고정 action/component ID, 화면 상태, 검증 거부, 메시지 key·실제 표시 언어·catalog 버전, 결과 적용/폐기와 수집 누락 이벤트를 정의한다.
- 비동기·재시도·후속 조회의 인과관계와 순서/신뢰 수준을 보존한다. HTTP 접수·업무 완료·결과 불명·화면 반영을 서로 다른 사실로 취급한다.
- 별도 버전의 strict 진단 수집 계약과 제한된 저장/검색/내보내기를 설계한다. 기존 activity 감사와 generic JSON 로그를 무손실 원장으로 재정의하지 않는다.
- 한국어 관리자 경험 타임라인과 읽기 전용 재생을 제공한다. 당시 사용자 언어와 운영자 해설 언어를 분리한다.
- 인증/계정 복구, MCP 동의, VM/볼륨 생성부터 검증하고 공통 UI·기능 상태 owner를 통해 확대한다. 첫 적용 흐름은 전체 기능 범위를 대체하지 않는다.
- 보존 초안은 상세 진단30일/비식별 집계90일이며 실제 활성화 전에 운영·보안 검토를 완료한다. 기존 업무 감사 보존은 변경하지 않는다.
- 시각/DOM/동영상 기록은 별도 승인 change로 분리한다. 이 change에서 활성화하거나 의존성으로 넣지 않는다.

## Capabilities

### New Capabilities
- `semantic-experience-events`: 의미 기반 UI 관측, 명시적 인과 연결, 실제 메시지·화면 결과와 순서 계약.
- `experience-evidence-pipeline`: 신뢰 구분, 비밀 비수집, 제한·중복 제거·누락·분리 저장·보존 계약.
- `experience-timeline-replay`: 범위 제한된 한국어 조회/재생·불일치 설명·안전한 export.

### Modified Capabilities
없음. 기존 감사·인증·작업 원장의 권위 및 API 요청 재실행 금지 계약은 보존한다.

## Impact

- 구현 대상: `frontend/src/lib/utils/experience.ts`, 기존 interaction/API client·공통 UI·실제 상태 owner와 root layout, `backend/app/api/common/experience.py`, `app/middleware/experience.py`, `app/services/experience*.py`, 관리자 기존 events projection, SQL107 및 실제 operation/worker 경계.
- 형제 서비스 내부 span은 해당 서비스의 명시적 계약 확장이 필요하다. Afterglow BFF 관측만으로 원격 내부 처리를 추정하지 않는다.
- 현재 단계는 승인된 source/local 구현과 수용 검증이다. 별도 SQL107 진단 저장소를 추가하되 기본 수집은 꺼짐이며 운영 DB/schema·보존 삭제 job·배포·IAM은 자동 변경하지 않는다. 실제 compiled browser/API/worker·성능·복구·gate와 남은 수용 기준을 통과하기 전에는 전체 완료나 archive로 표시하지 않는다.
