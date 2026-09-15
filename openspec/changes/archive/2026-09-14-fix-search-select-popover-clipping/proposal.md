## Why

`SearchSelect`의 absolute popover는 `Card`의 `overflow: hidden` 안에 있어 긴 결과가 card 경계에서 잘린다. z-index는 ancestor clipping을 벗어날 수 없으므로 실제 긴 사용자·프로젝트 목록의 하단 항목이 보이거나 클릭되지 않는다.

## What Changes

- SearchSelect popover를 열 때 `document.body`로 옮겨 viewport-fixed overlay로 배치한다.
- trigger의 viewport rect와 사용 가능한 위·아래 공간으로 방향과 높이를 정하고 resize/scroll 중 위치를 동기화한다.
- outside click 판정은 trigger container와 body portal 양쪽을 포함한다.
- 긴 결과의 마지막 항목 클릭 가능성과 Card 가로 스크롤 불변을 실제 브라우저로 검증한다.

## Capabilities

### New Capabilities

- 없음.

### Modified Capabilities

- 검색형 단일 선택 popover가 overflow clipping ancestor와 무관하게 viewport 위에 표시된다.

## Impact

- `frontend/src/lib/components/ui/SearchSelect.svelte`와 관련 테스트, 디자인/아키텍처 설명만 변경한다.
- API·데이터·권한 계약에는 영향이 없다.
