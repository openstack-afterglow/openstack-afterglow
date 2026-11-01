## Why

인스턴스·볼륨 목록이 생성 시각 순서를 보장하지 않아 새 자원을 찾기 어렵다. 관리자와 프로젝트 화면 모두 최신순을 기본으로 하며 사용자가 정렬 기준을 선택할 수 있어야 한다.

## What Changes

- 네 목록(관리자/프로젝트 × 인스턴스/볼륨)의 기본 정렬을 생성일 최신순으로 통일한다.
- 기존 필터/toolbar에 최신순·오래된순·이름 오름차순·이름 내림차순 선택을 추가한다.
- 관리자 목록은 전체 필터 결과를 정렬한 후 marker pagination을 적용한다. 정렬 변경은 첫 페이지로 돌아가며 stale 응답·선택·prefetch 경계를 유지한다.
- 시각이 누락되거나 잘못된 자원은 날짜 정렬에서 끝에 두고 같은 값은 ID로 안정적으로 정렬한다. 이름은 대소문자 구분 없는 비교와 ID tie-break를 사용한다.
- 기존 검색·scope·권한·mutation·polling 계약을 보존한다. API 인가는 변경하지 않는다.
- 프로젝트 볼륨 응답의 누락된 native `created_at`을 nullable 표시 필드로 노출하여 실제 생성 시각 정렬을 가능하게 한다.

## Capabilities

### New Capabilities
- 목록의 명시적 정렬 기준 선택.

### Modified Capabilities
- 인스턴스/볼륨 목록의 기본 순서와 관리자 pagination의 정렬 일관성.

## Impact

Frontend 네 목록 및 기존 필터, 지원 locale 카탈로그; 관리자 두 목록 endpoint 및 pytest; 사용자/API/architecture/testing 문서. DB/schema/config/dependency/배포 변경 없음. 실제 UI는 격리 synthetic API로 검증하고 운영 수용과 구분한다.
