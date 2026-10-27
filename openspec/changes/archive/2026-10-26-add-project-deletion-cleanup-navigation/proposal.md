## Why

프로젝트 삭제 검사에서 잔여 할당을 확인해도 사용자가 해당 프로젝트의 리소스 관리 화면을 다시 찾아야 한다.

## What Changes

- 관리자 삭제 보고서의 항목마다 제거 진입 동작을 제공한다. 직접 삭제하지 않고 대상 domain/project UUID 및 kind로 필터된 통합 관리자 리소스 모니터로 이동한다.
- 확인된 0개·서비스 미설치 항목은 정리 대상이 아니며, 미확인 항목은 0개로 처리하지 않는다.
- 사용자 선택에 따라 기존 관리 UI가 없는 유형도 포함하여 28종 및 하위 프로젝트 목록·명시적 개별 삭제 기능을 구현한다. 자동 cascade·bulk·force bypass는 제공하지 않는다.
- 기존 사용자 IAM modal과 관리자 권한 경계, empty-only/final-fresh 삭제 검사 및 no-replay 계약을 보존한다.

## Capabilities

### New Capabilities
- 프로젝트 삭제 전 리소스별 scoped 정리 화면 진입.

### Modified Capabilities
- 관리자 프로젝트 삭제 보고서의 actionable navigation.

## Impact

Frontend modal·통합 project resource monitor·nine locale·behavior tests와 명시적 개별 resource list/delete API·DESIGN/ARCHITECTURE 및 상세 문서. 기존 프로젝트 삭제 API와 native 삭제 정책·스키마·운영 설정은 변경하지 않는다.
