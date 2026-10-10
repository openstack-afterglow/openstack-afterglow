## Why

소비자 전체 메뉴에서 Palimpsest가 기본 인프라보다 먼저 표시되고 네트워크가 마지막에 있다. 요청한 탐색 우선순위로 정렬한다.

## What Changes

- `userNavSections`를 Compute → 볼륨 → 네트워크 → File Storage → Palimpsest → 컨테이너 → Database → Object Storage → Key Manager → AI 채팅 순서로 배치한다.
- 나머지 서비스의 상대 순서, 개요·사용량·활동·토폴로지 위치, 관리자 메뉴, URL과 서비스/beta/mockup 조건은 유지한다.
- 모바일·태블릿·데스크톱의 실제 Chromium 전체 메뉴에서 순서와 그룹 탐색을 확인한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

소비자 탐색의 서비스 표시 순서만 변경한다.

## Impact

`frontend/src/lib/config/nav.ts`의 기존 선언을 이동한다. `Sidebar`와 명령 팔레트는 같은 선언을 사용한다. 컴포넌트·권한·API·반응형 구조는 변경하지 않는다.
