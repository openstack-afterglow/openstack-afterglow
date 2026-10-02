## Why

사용자가 제공한 실제 콘솔 화면에서 Cloud Shell은 왼쪽 breadcrumb 옆에 있고 프로젝트 선택은 오른쪽에 있다. 요청한 작업 순서에 맞춰 프로젝트 맥락은 브랜드 바로 오른쪽, 리소스 검색은 전체 화면 중앙, Cloud Shell은 기존 오른쪽 프로젝트 선택 위치에 배치한다.

## What Changes

- Root layout의 기존 CloudShellTrigger를 오른쪽 유틸리티 그룹 첫 위치로 이동한다. 서비스 capability와 desktop-only 조건, 승인 및 세션 lifecycle은 유지한다.
- 기존 ProjectSelector를 로고 오른쪽의 헤더 왼쪽 그룹으로 이동한다. 긴 프로젝트명은 버튼 안에서 말줄임하며 dropdown의 기존 portal·키보드·project scope 동작은 유지한다.
- 리소스 검색을 사이드바를 제외한 콘텐츠 중앙이 아니라 전체 viewport의 중앙에 맞춘다. 좁은 desktop에서는 검색 폭을 줄여 양쪽 컨트롤과 겹치지 않게 한다. 모바일·태블릿 검색 진입점과 sidebar 맥락 선택은 유지한다.
- Breadcrumb는 tablet과 여유 있는 넓은 desktop에서 유지하고 좁은 desktop에서는 프로젝트 선택과 검색을 우선한다. 기존 테마·48px 헤더·popover layering은 바꾸지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- Console header composition: 프로젝트 선택 → 중앙 검색 → 우측 Cloud Shell 및 기존 유틸리티의 시각적 순서.

## Impact

Frontend root layout와 ProjectSelector의 폭/말줄임 처리만 변경한다. Backend, Zun/Cinder 설정·영구 홈·IAM·API 계약은 변경하지 않는다. 실제 인증 브라우저에서 user/admin, breakpoint 경계, project dropdown, 검색과 승인 취소를 확인한다. 로컬 frontend만 재빌드·적용하며 운영 배포·commit·push는 하지 않는다.
