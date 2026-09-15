## Why

관리자 기본 설정의 하단 resource 검색 필드는 결과 목록을 항상 아래에 열어 viewport 밖으로 잘리게 한다. 사용자가 검색 결과를 확인하거나 선택할 수 있도록, viewport 하단에 가까운 검색 필드는 결과 목록을 위쪽에 표시해야 한다.

## What Changes

- 관리자 기본 설정의 검색형 resource picker가 trigger 위·아래의 실제 가용 공간을 기준으로 결과 목록 방향을 선택한다.
- 화면 하단에 있는 picker는 목록을 위쪽으로 열고, 상단·중앙의 picker는 더 넓은 방향을 사용한다.
- 방향이 바뀌어도 이름/ID 검색, 키보드 탐색, 선택, Escape/outside dismissal, focus 복귀를 유지한다.
- 모바일·태블릿·데스크톱 viewport에서 목록이 화면 안에 유지되도록 높이와 위치를 제한한다.

## Capabilities

### New Capabilities

- `admin-default-settings-picker-placement`: 관리자 기본 설정의 검색형 resource picker가 viewport 안에서 결과를 노출하고 선택 가능하게 유지하는 배치 계약.

### Modified Capabilities

- 없음.

## Impact

- 관리자 기본 설정 route/component와 사용 중인 shared search-select primitive 및 관련 frontend 검증이 영향받는다.
- API, 데이터 모델, 권한, backend, dependency, deployment 계약에는 영향이 없다.
