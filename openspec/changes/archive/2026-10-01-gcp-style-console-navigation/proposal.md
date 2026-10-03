## Why

현재 로고 영역과 별도 헤더 사이의 세로선·Admin badge·페이지 경로가 상단을 분절하고, desktop 사이드바를 숨길 수 없다. 사용자가 제공한 GCP 화면처럼 전역 컨텍스트와 서비스별 탐색을 분리한다.

## What Changes

- 하나의 전체 폭 헤더에 햄버거·현재 브랜드·프로젝트 선택을 배치하고 로고 오른쪽 세로선, Admin badge와 페이지 breadcrumb를 제거한다.
- 전체 메뉴를 모든 화면 크기에서 열고 닫을 수 있는 drawer로 제공한다. 기존 목적지·권한·서비스 및 beta 조건은 보존한다.
- 세부 경로에서는 해당 페이지 이름과 같은 서비스의 항목을 왼쪽 사이드바에 표시한다. 사이드바 숨김과 다시 열기를 제공하고 숨김 상태에서 workspace와 고정 panel/dock의 좌측 offset을 함께 조정한다.
- 검색은 전체 viewport 중심을 유지하고 Cloud Shell과 모드 전환은 오른쪽 utility 영역에 유지한다.

## Capabilities

### New Capabilities

- 전체 메뉴 drawer와 서비스별 사이드바의 독립적인 탐색·숨김.

### Modified Capabilities

- 콘솔 header/sidebar composition 및 responsive navigation.

## Impact

Frontend shell·navigation composition·geometry와 해당 행동 테스트·디자인/아키텍처 문서만 변경한다. 브랜드 자산, API, 인증, project rescope, Cloud Shell lifecycle, 운영 구성과 다른 작업의 변경은 보존한다. 실제 로그인된 로컬 Chromium에서 사용자·관리자, menu dismissal/focus, direct/nested navigation, sidebar hide/reopen, project dropdown, search, breakpoint·theme·overflow를 확인하고 현재 frontend만 로컬 적용한다. commit/push/운영 배포는 하지 않는다.
