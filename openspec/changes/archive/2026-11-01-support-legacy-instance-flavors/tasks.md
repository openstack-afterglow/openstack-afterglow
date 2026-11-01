## Implementation Tasks

- [x] 원인과 소비자 공통 helper·서버 원래 이름 계약을 확인한다.
- [x] 검증 사양 우선·원래 이름 fallback·양쪽 부재 unknown을 구현하고 행동 회귀를 검증한다. 수정 전 legacy3case 실패, 수정 후4files63tests 통과.
- [x] 실제 Chromium에서 현재 source RecentInstancesCard를 합성 데이터로 mount하여390/820/1440px × light/dark6조건의 이름·사양·unknown 및 overflow없음을 확인한다. 운영 인증/API는 미검증.
- [x] DESIGN.md·ARCHITECTURE.md·docs/api/flavors.md·CHANGELOG.md에 표시 예외와 구조 영향 없음을 기록한다. HEAD+표시 helper/네 테스트 파일의 격리 index에서 architecture --staged 검사가 통과했다(3538files, e9beadce77ac5256a1577225d77dae2202705c96beed82be37c7bc5ddbf82b7e). 공유 working-tree 전체 stamp는 이 작업의 검토 증거로 철회하고 원래 다른 작업의 marker를 복원했다. 실제 index는 보존했다. svelte-check0errors/17기존경고. 전체 test:gate·운영 배포는 미실행. 완료 change를 archive했다.

## 최종 회귀 결과

`npm run test:target -- instances`: backend2654passed/1skipped/5warnings, frontend58files1064passed. Frontend stderr에 jsdom canvas getContext 미구현 경고가 발생했지만 suite는 통과했다. 이 변경의 실제 canvas/UI 증거는 위 Chromium 합성 component 실행이며 운영 인증·native cloud 검증으로 간주하지 않는다. 전체 test:gate와 배포는 실행하지 않았다.
