## Why

계정 설정은 현재 프로필·세션·로그인 설정·Beta·SSH 키·MCP·활동을 하나의 긴 페이지에 렌더링한다. 사용자가 원하는 설정을 바로 찾고 기존 콘솔과 같은 왼쪽 탐색으로 이동할 수 있어야 한다.

## What Changes

- 기존 `ConsoleNavigation`과 shared navigation declarations를 재사용해 계정 설정의 프로필·SSH 키·Beta 기능·세션·MCP·활동 순서의 contextual sidebar를 제공한다.
- `/dashboard/account`는 프로필 기본 화면이며 SSH 키는 `/keypairs`, Beta는 `/beta`, 세션은 `/sessions`, MCP는 `/mcp`, 활동은 `/activity` 하위 경로로 분리한다. Browser back/forward·직접 진입·새로고침이 같은 화면을 유지한다.
- 프로필·비밀번호 변경·로그인 작업 공간은 프로필 화면에 유지하고 기존 section component의 API·권한·민감 데이터 정리 경계를 변경하지 않는다. 선택하지 않은 경로는 mount하지 않는다.
- Tablet/desktop은 기존 접기 가능한 sidebar/rail을 사용하고 mobile은 기존 global drawer의 계정 설정 항목으로 이동한다. 새 visual token·별도 sidebar convention은 만들지 않는다.
- 기존 Beta/MCP 진입 링크를 정확한 새 목적지로 옮기고 모든 지원 언어의 탐색 문구를 동기화한다.

## Capabilities

### New Capabilities

없음. 기존 계정 기능의 탐색·구성만 변경한다.

### Modified Capabilities

계정 설정의 섹션별 경로, contextual/global navigation, command-palette destination과 직접 링크.

## Impact

Frontend account routes, shared navigation declarations/catalogs와 기존 Beta/MCP link consumers. Backend endpoint·DB/schema·dependency·config·native IAM·배포에는 영향이 없다. 기존 shared dev/index/private/runtime state를 보존한다. 실제 브라우저 synthetic fixture로 각 경로·내비게이션·선택적 section mount·반응형과 테마를 검증하며 실제 Keystone/MCP 인증 또는 운영 배포 증거로 취급하지 않는다. 커밋·push·배포는 요청 범위가 아니다.
