## Why

사용자가 메인 소개 페이지와 로그인된 콘솔에서 서비스 사용 방법을 찾을 수 있는 공개 문서 경로가 없다. 기존 `docs/api/`는 개발자 API 참고 자료이며 실제 콘솔 사용 순서를 대신하지 않는다.

## What Changes

- 인증·프로젝트 선택 없이 열리는 `/docs`와 `/docs/<service>`를 제공한다. 서비스 가이드와 시작하기, 검색, 서비스별 내비게이션, 문서 내 목차를 구성한다.
- Nova, Neutron, Octavia, Cinder, Manila와 Drover, Waygate, Lumen, Palimpsest의 현재 콘솔 사용 절차를 설명한다. 관련 Glance, Object Storage, Trove, Barbican 가이드도 제공한다.
- 준비 사항, 생성/사용/확인/정리 절차, 장애 대응과 서비스 활성화·권한·백업/스냅샷 한계를 명시한다. 실제 지원하지 않는 기능이나 배포 성공을 광고하지 않는다.
- 공개 메인 페이지 내비게이션·주요 동선과 콘솔 공통 헤더·전체 메뉴·검색에서 문서를 열 수 있게 한다.
- 기존 SvelteKit·디자인 토큰·UI primitive만 사용하며 문서 본문을 typed static content로 렌더링해 HTML 주입과 별도 docs runtime 의존성을 만들지 않는다.

## Capabilities

### New Capabilities

- 공개 사용자 문서 허브와 직접 링크 가능한 서비스 가이드.
- 서비스 이름·본문을 검색하는 문서 탐색.

### Modified Capabilities

- 공개 경로 판정에 정확한 `/docs` 및 `/docs/` 하위 경로를 추가한다. `/docsevil` 등 비문서 경로의 인증은 유지한다.
- 공개·인증된 화면에 Docs 진입점을 추가한다. 튜토리얼에서 문서로 이동해도 모의 콘솔로 강제 복귀하지 않는다.

## Impact

Frontend route, hooks, root layout 및 landing/navigation만 변경한다. OpenStack API·서비스 권한·자원 변경 계약은 바꾸지 않는다. 문서는 현재 source 동작을 설명하며 운영 클라우드 provisioning이나 서비스 provider-real 성공의 증거가 아니다. 기존 공유 작업 트리를 보존하고 commit/push/deploy하지 않는다.
