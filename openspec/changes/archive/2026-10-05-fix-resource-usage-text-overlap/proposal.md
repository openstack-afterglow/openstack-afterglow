## Why

관리자 개요의 프로젝트별 리소스 표에서 사용량 막대가 수치와 인접 열 위로 겹친다. 제공된 스크린샷의 VM/CPU 헤더도 붙어 보인다. 기존 콘솔 motion 작업을 유지하면서 읽을 수 있는 사용량 레이아웃을 복구한다.

## What Changes

- 공용 UsageBar의 기본 폭과 호출자의 폭 utility 사이 CSS cascade를 조사하고 수정한다.
- 관리자 프로젝트 표의 열 간격을 확보하고 동일 primitive의 좁은 inline 사용처를 확인한다.
- 실제 Chromium에서 작은/큰 사용량, 모바일·태블릿·데스크톱, light/dark, reduced-motion 및 200% zoom 등가 레이아웃을 확인한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- resource-usage-presentation: 막대·숫자·인접 열이 독립된 공간을 유지한다. 사용량·쿼터 계산과 프로젝트 선택은 그대로다.

## Impact

Frontend 표현만 변경한다. API, 권한, store, 데이터, 배포 구조에는 영향이 없다. 기존 motion과 동시 작업의 수정·Git index 및 공유 architecture review block은 보존한다. 검증은 합성 API fixture의 실제 브라우저 UI이며 live OpenStack 검증으로 확대하지 않는다.
