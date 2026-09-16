## Implementation Tasks

- [x] Event-controlled regression으로 진행 중인 일반 miss와 명시적 refresh 경쟁을 재현한다.
- [x] `refresh=True`가 선행 작업 뒤에 자신의 loader를 실행하고 최종 cache 값을 보존하도록 수정한다.
- [x] 일반 miss coalescing과 waiter cancellation 회귀를 포함한 cache exact target을 통과시킨다.
- [x] 관련 문서와 architecture review stamp를 갱신하고 `npm run test:gate`를 통과시킨다.
- [x] 체크리스트를 완료하고 `openspec archive fix-cache-refresh-singleflight --skip-specs --yes`로 archive한다.
