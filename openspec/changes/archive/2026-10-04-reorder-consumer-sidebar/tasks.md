## Implementation

- [x] 소비자 메뉴 선언과 기존 노출 조건을 확인한다.
- [x] Compute → 볼륨 → 네트워크 → File Storage → Palimpsest 순서로 선언을 이동하고 나머지 상대 순서를 유지한다.
- [x] 합성 identity/API fixture를 사용한 실제 Chromium에서 모바일·태블릿·데스크톱 메뉴 순서와 그룹 탐색을 확인한다.
- [x] 구조 영향 없음과 검증 범위를 기존 디자인·아키텍처·변경 기록에 반영하고 change를 archive한다.

## Verification

- 실제 Vite 소스 앱과 합성 identity/API fixture의 Chromium에서 522×732와 390·767·768·1023·1024·1440px 소비자 메뉴 순서·개요 링크 보존·가로 넘침 0을 확인했다. 네트워크와 Palimpsest 목적지 이동, drawer 닫힘과 현재 페이지 선택을 확인했다.
- HEAD+`nav.ts` source의 격리 staged snapshot에서 architecture guard stamp/check를 통과했다(`26240b4ac6be7661e69a49302b02c26a8bee23ac049572192dfa3ba25d0b32f9`, 2,164 files). 실제 index와 공유 review block은 보존했다.
- 임시 브라우저와 Vite preview를 종료했다. 운영 배포·실제 OpenStack 인증·전체 gate는 수행하지 않았다. gbrain CLI는 설치되어 있지 않아 선택적 code-index sync를 실행하지 않았다.
