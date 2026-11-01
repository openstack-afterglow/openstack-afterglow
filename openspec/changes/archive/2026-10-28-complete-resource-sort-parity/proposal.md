## Why

완료된 목록 정렬 기능의 tutorial transport가 UUID 순서를 유지하여 관리자 모의 화면에서는 정렬 선택이 작동하지 않았다. 이전 nullable 생성일 없는 volume 캐시를 새 응답이 재사용하면 TTL 동안 기본 최신순을 보장할 수 없다.

## What Changes

- 관리자 tutorial instance/volume transport가 공통 sortResources의 기본 최신순 및 선택한 sort를 marker 앞에 적용한다.
- 프로젝트 tutorial 볼륨 fixture에도 명시적 합성 생성 시각을 제공한다.
- 프로젝트 volume 응답 cache namespace를 v3으로 바꾸고 모든 해당 mutation invalidation을 함께 이동한다. 이전 v2는 TTL로 소멸하며 재사용/이중 쓰기하지 않는다.
- 동일 정렬/marker·cache 계약을 failing-before 회귀와 실제 tutorial UI로 확인한다.

## Capabilities

### New Capabilities
- 없음.

### Modified Capabilities
- 인스턴스·볼륨 정렬의 tutorial 및 warm-cache cutover 일관성.

## Impact

frontend mockup transport/state/tests, backend volume cache route/tests, 기존 docs/architecture/changelog. 새 schema/dependency/config/native write/배포 없음.
