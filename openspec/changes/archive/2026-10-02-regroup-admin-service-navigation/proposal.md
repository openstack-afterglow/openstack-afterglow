## Why

관리자 사이드바의 서비스 그룹은 기능 영역과 무관한 Drover·Lumen·Palimpsest·Waygate를 한 목록에 섞는다. 사용자 요청대로 각 기능 영역에서 찾을 수 있게 재분류한다.

## What Changes

- Drover와 클러스터 템플릿을 컨테이너 그룹에 둔다.
- Lumen, 채팅 통계, 사용자 쿼터, 모델 설정, 도구 설정은 Lumen 대분류로 묶는다.
- Palimpsest는 접는 그룹 안이 아닌 독립 최상위 링크로 제공한다.
- 관리자 Waygate는 네트워크 그룹에 넣고 서비스 그룹을 제거한다.
- 기존 URL, service/beta gate, 사용자 메뉴와 관리자 권한은 유지한다. 관리자 사이드바와 명령 팔레트는 같은 adminNavSections 분류를 소비한다.

## Capabilities

### New Capabilities

- `admin-navigation-grouping`: 관리자 탐색 분류, 그룹 자동 확장, 독립 Palimpsest 링크 및 명령 팔레트 분류의 검증 가능한 계약. 새 서비스나 API를 추가하지 않는다.

### Modified Capabilities

기존 main spec 변경은 없음. 기존 서비스·권한·URL을 유지하며 탐색 분류만 변경한다.

## Impact

frontend/src/lib/config/nav.ts, AdminSidebar.svelte와 관련 회귀 테스트, DESIGN.md·ARCHITECTURE.md·CHANGELOG.md. 실제 관리자 컴포넌트의 mobile/tablet/desktop 렌더링과 이동/표시 조건을 검증한다. 백엔드 API·배포·운영 자원은 변경하지 않는다.
