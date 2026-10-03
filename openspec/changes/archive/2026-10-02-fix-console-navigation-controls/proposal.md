## Why

사용자 screenshot에서 header 햄버거와 drawer 닫기 버튼·브랜드의 padding/gap이 다르고, 전체 drawer의 현재 페이지 메뉴 표시와 서비스 sidebar의 전체 메뉴가 중복된다. 후속 screenshot은 상세 sidebar를 닫아 없애거나 header의 프로젝트 오른쪽에 복원 버튼을 놓는 대신, 각 메뉴 아이콘만 남는 rail과 그 최상단의 펼치기 버튼을 요구한다.

## What Changes

- Header와 drawer brand row의 inset, gap, control size, symbol·text geometry를 일치시킨다.
- 전체 drawer의 현재 페이지 문맥/메뉴 표시 항목과 서비스 sidebar의 전체 메뉴를 제거한다.
- 토폴로지는 활동 바로 뒤에 놓고 프로젝트 설정은 기존 ProjectSelector popup에서 제공한다.
- 상세 sidebar는 tablet/desktop에서 15rem 전체 패널과 3.5rem 아이콘 rail을 전환한다. 최상단의 같은 버튼이 접기/펼치기로 바뀌고 현재 선택·프로젝트·모드와 keyboard focus를 유지한다. Header의 별도 복원 control은 제거한다.
- Context availability는 ConsoleNavigation이 판단하고 workspace·panel·dock offset에 expanded/collapsed/hidden 상태를 공유한다. Standalone topology는 서비스 sidebar를 만들지 않는다. 목적지별 SVG icon은 기존 nav 선언과 같은 stroke-path 방식으로 정의한다.

## Capabilities

### New Capabilities

새 API 기능은 없다.

### Modified Capabilities

콘솔 전역·서비스 탐색의 배치, 중복 제거, contextual icon rail과 같은 위치의 접기/펼치기를 수정한다.

## Impact

Frontend navigation, header control, state와 관련 행동 테스트·문서만 변경한다. API URL, auth·project rescope, service/beta/mockup gate, VM 생성·Cloud Shell lifecycle은 보존한다. dev에서 작업하고 다른 동시 변경·설정·volume·키를 보존한다. Canonical local frontend 이미지/실제 인증 UI를 검증하고 staging·commit·push·운영 배포·OpenStack 자원 생성은 하지 않는다.
