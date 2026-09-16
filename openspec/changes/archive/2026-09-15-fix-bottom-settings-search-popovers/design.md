## Context

관리자 기본 설정 페이지는 여러 OpenStack resource 기본값을 한 세로 목록에서 검색·선택한다. 페이지 하단의 검색 필드가 결과 popover를 아래쪽에 고정하면 목록이 viewport 밖으로 나가며, 사용자는 검색 결과가 없는 것으로 오인한다. Afterglow의 공통 `SearchSelect` 계약은 body portal, viewport-fixed 배치, roomier-side 선택, bounded list height를 이미 정의하므로 관리자 설정도 동일한 배치 정본을 사용해야 한다.

## Goals / Non-Goals

**Goals:**

- trigger 아래 공간이 부족한 하단 picker의 결과 목록을 위쪽에 표시한다.
- popover와 결과 목록을 viewport 안에 유지한다.
- 검색, 선택, 키보드 탐색, dismiss, focus 복귀 동작을 보존한다.
- mobile, tablet, desktop의 기존 설정 페이지 layout과 scroll ownership을 보존한다.

**Non-Goals:**

- 관리자 기본 설정 API나 저장 형식을 변경하지 않는다.
- picker의 검색 결과, 정렬, 선택 의미를 변경하지 않는다.
- 새 overlay primitive나 component-specific breakpoint를 추가하지 않는다.

## Decisions

1. **공통 SearchSelect 배치 계약을 정본으로 사용한다.** 관리자 설정의 picker가 별도 dropdown 구현을 사용하면 공통 primitive로 합성하거나 동일 primitive의 기존 public API로 배치를 위임한다. Route 전용 `bottom/top` CSS와 임의 z-index를 추가하는 대안은 viewport·scroll 변화에 취약하고 두 번째 convention을 만들기 때문에 사용하지 않는다.
2. **방향은 고정된 행 번호가 아니라 실제 공간으로 결정한다.** trigger의 viewport rect와 상·하단 여유를 비교해 더 넓은 쪽을 선택하고, popover 높이는 선택한 쪽의 가용 공간으로 제한한다. 따라서 목록 순서나 viewport 높이가 변해도 하단 picker가 위로 열린다.
3. **배치는 overlay가 열려 있는 동안 최신 geometry를 따른다.** resize와 scroll에서 trigger 기준 위치를 다시 계산하며 body portal과 fixed positioning으로 ancestor overflow clipping을 피한다.
4. **행동 계약은 유지한다.** 이름/ID filtering, ArrowUp/ArrowDown/Enter/Escape, outside dismissal, 선택 후 trigger focus 복귀를 placement 변경과 분리하지 않는다.

## Risks / Trade-offs

- **[Risk] 설정 route의 scroll container가 window scroll과 별개일 수 있음** → 열린 동안 capture-phase scroll과 resize에서 geometry를 다시 계산한다.
- **[Risk] 위쪽 공간도 작은 viewport에서는 전체 목록을 표시할 수 없음** → popover 자체가 아니라 내부 list 높이를 가용 공간 안으로 제한하고 스크롤 가능하게 유지한다.
- **[Risk] shared primitive 변경이 다른 화면의 picker를 회귀시킬 수 있음** → shared 동작은 roomier-side 계약을 유지하고 관리자 설정의 실제 하단·상단 picker를 브라우저에서 함께 검증한다.

## Migration Plan

Frontend-only clean cutover다. 별도 migration은 없으며, 문제가 생기면 관련 component 변경만 되돌릴 수 있다.

## Open Questions

- 없음.
