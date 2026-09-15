## ADDED Requirements

### Requirement: Search results remain visible inside the viewport
관리자 기본 설정의 검색형 resource picker는 결과 popover를 trigger 위·아래 중 더 넓은 가용 공간에 배치하고, 목록을 viewport 경계 안에 유지해야 한다(SHALL).

#### Scenario: Bottom picker opens upward
- **WHEN** 사용자가 viewport 하단에 가까운 resource picker를 열고 trigger 위 공간이 아래 공간보다 넓다
- **THEN** 결과 popover는 trigger 위쪽에 표시되며 검색 결과가 viewport 안에서 보이고 선택 가능하다

#### Scenario: Upper picker opens downward
- **WHEN** 사용자가 trigger 아래 공간이 위 공간보다 넓은 resource picker를 연다
- **THEN** 결과 popover는 trigger 아래쪽에 표시된다

#### Scenario: Constrained viewport bounds the result list
- **WHEN** 선택한 방향의 공간이 전체 결과 목록 높이보다 작다
- **THEN** 결과 목록은 가용 공간 안에서 높이가 제한되고 내부 스크롤로 모든 결과에 접근할 수 있다

### Requirement: Placement preserves picker interaction
관리자 기본 설정의 resource picker는 popover 방향과 관계없이 기존 검색·키보드·dismiss·focus 계약을 유지해야 한다(SHALL).

#### Scenario: Search and select in an upward popover
- **WHEN** 사용자가 위쪽으로 열린 picker에서 이름 또는 stable ID를 검색하고 결과를 선택한다
- **THEN** 해당 resource가 선택되고 popover가 닫히며 focus가 picker trigger로 복귀한다

#### Scenario: Dismiss an upward popover
- **WHEN** 사용자가 위쪽으로 열린 picker에서 Escape를 누르거나 picker 밖을 선택한다
- **THEN** popover가 닫히고 선택 값은 변경되지 않는다
