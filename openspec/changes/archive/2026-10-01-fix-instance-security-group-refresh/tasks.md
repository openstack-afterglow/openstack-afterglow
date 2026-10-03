## Implementation Tasks

- [x] 1. 실제 API broker의 저장 전 지연 조회 race 및 silent polling/오류/상세 전환을 failing-before 회귀로 재현.
- [x] 2. SG 저장 후 독립 refresh와 silent snapshot 보존을 구현하고 관련 소비자 회귀 및 frontend check 실행 결과를 기록.
- [x] 3. 실제 Chromium에서 변경된 refresh 경로를 실행하고 기존 상세 문서·architecture·changelog를 갱신한 뒤 archive.

## Verification Evidence

- 수정 전 실제 API broker를 사용하는 소비자 회귀 3건 실패: 제거한 HTTPS 443이 다시 표시됨, silent polling 중 정상 표가 로딩으로 대체됨, 다른 인스턴스 전환 시 이전 그룹/포트 snapshot이 남음.
- 수정 후 `node scripts/test-target.js frontend:src/lib/components/instance/__tests__ frontend:src/lib/stores/__tests__/instanceDetailController.loading.test.ts frontend:src/lib/stores/__tests__/instanceDetailController.resize.test.ts frontend:src/lib/utils/__tests__/securityGroupUnion.test.ts frontend:src/lib/api/__tests__/client.prefetch.test.ts`: 13 files, 95 tests passed.
- `npm run check`: 2127 files, 40 errors, 0 warnings. 오류는 변경 범위 밖 `Sidebar.test.ts`·`AdminSidebar.test.ts`의 ByRoleOptions `exact` 속성에만 있으며 이 작업 파일의 diagnostic은 없다. 해당 사용자 작업을 수정하지 않았고 전체 check를 통과로 기록하지 않는다.
- Source Vite의 실제 Chromium·합성 identity/API에서 지연된 ordinary SG GET 중 정책 표를 유지하고, 실제 편집/저장 버튼으로 `sg-default`만 저장한 뒤 `refresh=true` 독립 GET을 확인했다. 이후 저장 전 응답을 완료해도 443이 재등장하지 않고 다른 인터페이스의 DNS 53이 유지됐다.
- 503 실패 시 두 정책의 표가 숨겨지고, 지연된 silent 재시도 중 기존 오류가 유지되며 성공 후 복구됐다. Desktop 정책 화면 screenshot과 document overflow 0을 확인했다. 실제 Neutron mutation·운영 배포 증거는 아니다.
- 서버 측 남은 위험: 실제 SG GET은 `refresh=true`를 읽지 않고 기존 `cached_call`에 합류한다. POST는 저장된 cache만 삭제하고 진행 중인 `_inflight` load는 유지하므로 저장 전 느린 Neutron 응답이 저장 후 응답 및 cache로 재사용될 수 있다. 이번 소비자 test/Chromium fixture는 이 서버 경계를 다루지 않으며 해결한 것은 브라우저 broker race뿐이다. Backend/API 변경 금지 범위에 따라 서버를 수정하지 않았다.
- `node scripts/test-target.js instances`: backend 371 passed (5 existing warnings), frontend 15 files/95 tests passed. 이는 SG 서버 cache 최신성 테스트가 아니다.
- Architecture: working source `8b9783788981e53c9b7b5bd0a9a6dc36c1cf057dc7430ad9eef44699f64e6648`, 2148 files stamp/check 통과. 기존 index의 `--staged`도 통과했으나 이 작업은 stage하지 않았으므로 index 검사는 새 변경의 staged 검증을 의미하지 않는다. `test:gate`·commit·배포·실제 Neutron 변경은 수행하지 않았다.
- QA Chromium과 source Vite service를 종료하고 이번 작업의 `/tmp/afterglow-instance-union-refresh-qa` profile을 삭제했다. Gbrain은 기존에 확인한 CLI 미설치 상태 때문에 sync하지 않았으며 agent 시작 문서를 수정하지 않았다.



