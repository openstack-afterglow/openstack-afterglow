## Why
사용자는 매번 모든 서비스를 펼쳐야 하는 불편을 보고했으며 관리자와 사용자 모두 첨부 화면처럼 카테고리 목록이 처음부터 보이기를 요청했다.

## What Changes
- 모든 서비스 catalog는 초기 진입, 메뉴 재열기 및 actor/mode 변경에서 기본 펼침.
- 개별 category 하위 항목은 기존 접힘과 명시 토글 유지.
- Hub, pins, search, 권한·beta·service 필터와 focus/scroll 유지.

## Capabilities
### New Capabilities
없음.
### Modified Capabilities
전역 탐색 catalog의 기본 노출 상태.

## Impact
공통 ConsoleNavigation의 display state만 변경한다. API, native 권한, DB/schema/config/runtime 배포에는 영향 없다. 기존 source의 닫힘 회귀를 새 사용자 계약에 맞춰 수정하고 관리자/사용자 실제 compiled UI를 확인한다.
