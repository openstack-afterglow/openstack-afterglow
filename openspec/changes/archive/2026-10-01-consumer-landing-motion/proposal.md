## Why

소비자 소개 페이지는 운영 보드 시나리오와 필터 외에는 정적인 설명·SVG가 이어진다. 사용자가 환경 제공 과정을 눈으로 따라가고 직접 조작할 수 있는 스크롤 스토리와 안전한 브라우저 체험을 제공한다.

## What Changes

- 기존 graphite/warm 브랜드와 로컬 IBM Plex/Pretendard 폰트를 유지하고 짧은 hero 문구와 체험 진입을 강조한다.
- 운영 보드를 신청 → 정책 확인 → 배정 → 재사용의 유한 실행 체험으로 바꾼다. 실행/일시정지/재실행, 시나리오 전환을 제공하고 실제 자원이나 API를 만들지 않는 예시임을 명시한다.
- 정적인 overview/method 반복을 하나의 스크롤 스토리로 통합한다. desktop에서 설명/그래픽이 스크롤에 따라 바뀌고 mobile/tablet/짧은 viewport/reduced-motion에서는 명시적인 단계 선택과 읽기 흐름을 유지한다.
- 기능별 워크플로우 이동과 제품 화면 미리보기 전환을 제공한다.
- GSAP ScrollTrigger는 public page에서만 지연 로드한다. 기존 motion duration과 semantic CSS token을 사용하며 reduced-motion 변경 및 unmount 시 애니메이션/리스너를 정리한다.

## Capabilities

### New Capabilities

- 소비자 페이지의 브라우저 내 환경 구성 체험과 진행 컨트롤.
- 스크롤/터치/키보드로 탐색 가능한 연구 환경 제공 스토리.
- 선택형 제품 화면 미리보기.

### Modified Capabilities

- Public landing의 hero/overview/capability/workflow/product 구성과 responsive hierarchy.
- 기존 copy/source-shape 테스트는 삭제하고 사용자-visible 상태 전이·접근성·실제 콘솔 목적지 계약을 유지한다.

## Impact

Frontend public landing와 GSAP dependency에 한정한다. Backend, 인증, 실제 provisioning, 사이트 설정과 로고 경로는 변경하지 않는다. 기존 작업 트리의 다른 변경을 보존한다. 브라우저에서 desktop/mobile/tablet, breakpoint 경계, 두 테마, reduced-motion, 키보드와 짧은 viewport를 검증하고 DESIGN/ARCHITECTURE/CHANGELOG를 갱신한다.
