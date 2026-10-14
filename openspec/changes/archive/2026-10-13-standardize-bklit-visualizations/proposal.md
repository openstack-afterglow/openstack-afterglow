## Why

대시보드의 자체 SVG/CSS 차트·막대·링은 축·tooltip·motion·접근성 구현이 분산되어 있다. 사용자 요청에 따라 Bklit UI 원본 컴포넌트를 공통 수치 시각화 기반으로 사용하고 기존 화면 및 앞으로의 개발 규칙을 일치시킨다.

## What Changes

- 전체 frontend의 사용자·관리자·서비스 시각화와 호출자를 조사하여 전환 목록을 확정한다. 기존 API, 권한, scope fence, 새로고침, 단위·시간 의미를 보존한다.
- SvelteKit/Svelte 5는 유지한다. MIT Bklit UI의 필요한 shadcn registry source를 upstream commit `f7b3bd2999a5c993863f9cc5523c9cf60b9f3bc2`에 고정해 도입하고 React root는 client-only 공통 chart adapter 안에 한정한다. 운영 중 CDN source fetch는 없다.
- 선/영역·분포/막대·quota/capacity/usage meter·원형 사용량·트래픽 시각화의 직접 geometry를 Bklit composition으로 교체한다. 실제 원본 library를 사용하며 Svelte 모사 구현으로 대체하지 않는다.
- 기존 semantic theme tokens와 locale formatter를 연결하고 responsive 크기·reduced motion·명명된 정보/legend·loading/error/empty·실제 0과 unavailable·무제한 quota·누락 구간을 보존한다.
- 폐기된 실험용 LayerChart 경로와 사용되지 않는 의존성을 정리한다. 향후 시각화는 공통 Bklit adapter를 사용하도록 DESIGN/architecture/개발 가이드를 갱신한다.

## Capabilities

### New Capabilities

- 공통 Bklit chart rendering boundary 및 pinned upstream provenance/license.

### Modified Capabilities

- 자체 대시보드 시계열·분포·사용량·트래픽 차트의 표현 및 상호작용.

## Impact

- 사용자 확인: **편집 토폴로지·Grafana는 유지**. 네트워크 연결 편집·확대/이동, 구조/역할 그래프, 외부 Grafana 원본 쿼리·대시보드는 일반 차트로 바꾸지 않는다. 이 화면에 포함된 자체 수치 그래프는 전환한다. Task progress, status indicators, icons, QR, terminal, 사용자 제공 Mermaid는 통계 차트가 아니다.
- backend API/schema/auth/deploy 계약은 변경하지 않는다. 현재 `dev` working tree의 기존 동시 변경과 index를 보존한다. commit/push/deploy는 요청 범위가 아니다.
- 완료 기준: 모든 조사된 자체 수치 시각화가 Bklit 렌더러를 사용하고 기존 동작을 유지한다. 관련 계약 검사와 실제 Chromium에서 주요 route 및 경계 입력, mobile/tablet/desktop·theme·reduced motion을 검증한다. 합성 API 검증은 운영 인증/데이터 검증과 구분한다.
