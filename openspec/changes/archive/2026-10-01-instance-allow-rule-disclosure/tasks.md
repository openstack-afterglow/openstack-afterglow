## Implementation Tasks

- [x] 1. 인바운드·아웃바운드의 인터페이스별 독립 접기/펼치기를 기존 Button·TableShell 패턴으로 구현.
- [x] 2. 사용자 표시명 `허용 규칙 (합집합)`을 `적용된 허용 규칙`으로 변경하고 영향받는 소비자 계약 테스트 갱신.
- [x] 3. 관련 frontend 검증과 실제 Chromium의 mouse/keyboard·상태 독립성·반응형·오류 표시를 확인하고 문서·architecture를 갱신한 뒤 archive.

## Verification

- 정확한 변경 소비자: `node scripts/test-target.js frontend:src/lib/components/instance/__tests__/SecurityGroupUnion.test.ts frontend:src/lib/components/instance/__tests__/NetworkSection.test.ts frontend:src/lib/components/instance/__tests__/NetworkSection.refresh.test.ts` — 3 files, 16 tests passed. 독립 방향 상태·규칙 갱신 중 상태 보존과 포트 순서 변경 시 포트별 상태 보존을 포함한다.
- 관련 회귀: `node scripts/test-target.js frontend:src/lib/components/instance/__tests__ frontend:src/lib/stores/__tests__/instanceDetailController.loading.test.ts frontend:src/lib/stores/__tests__/instanceDetailController.resize.test.ts frontend:src/lib/utils/__tests__/securityGroupUnion.test.ts frontend:src/lib/api/__tests__/client.prefetch.test.ts` — 13 files, 97 tests passed.
- Frontend 전체 타입·Svelte 검사: `npm run check` — 2127 files, 0 errors, 0 warnings. 앞선 union 작업 당시의 Sidebar/AdminSidebar 40 errors 결과와 별개의 최신 실행이다.
- 실제 Chromium: source preview `http://localhost:3091/`의 직접 상세에서 합성 identity/API의 두 포트를 사용했다. 초기 4개 버튼 `aria-expanded=false`, 표 0; mouse로 첫 인바운드를 펼쳤을 때 22/443만 표시되고 두 번째 포트는 접힌 상태 유지. Enter로 아웃바운드를 펼치고 Space로 인바운드를 접었다. 두 번째 포트의 인바운드 53은 첫 포트와 섞이지 않았다. 복구 후 Enter/Space의 펼침/접힘도 한 실행에서 다시 확인했다.
- 390·768·1440px에서 변경 policy 영역의 폭과 44px 높이 버튼을 확인하고 dark/light의 실제 screenshot을 확인했다. 좁은 화면의 표는 내부 가로 스크롤을 사용한다. 전체 상세 `main`은 768px에서 규칙을 모두 접어도 scrollWidth가 clientWidth보다 55px 크며, 넘치는 요소는 변경하지 않은 metrics 시간 범위/auto-refresh toolbar다. 상세 전체 toolbar 배치는 이 요청에서 변경하지 않았다.
- 모든 방향을 접은 상태에서 SG GET의 합성 503 응답 1건을 주입했을 때 두 포트의 오류 안내가 표시되고 표·disclosure 버튼은 표시되지 않았다. fixture를 복구한 뒤 정상 조회와 기본 접힘 버튼의 복구를 확인했다. 임시 main-world fetch wrapper·script·DOM marker는 finally에서 제거했다.
- Backend/API·규칙 계산·저장·polling은 변경하지 않았다. 서버 cache 최신성 한계는 유지하며 운영 배포·실제 Neutron 변경으로 주장하지 않는다. staging/commit·`test:gate`·배포는 수행하지 않았다. gbrain sync는 앞서 확인한 local CLI 부재로 수행하지 않았으며 agent startup 파일은 변경하지 않았다.
- Architecture: 구조 변화 없음(기존 공용 컴포넌트 내부 disclosure 상태·명칭·keyed port identity만 변경). `docs/api/instances.md`, `ARCHITECTURE.md`, `CHANGELOG.md`를 함께 갱신했다. 검토한 기존 디자인 primitive 계약은 유지하므로 `DESIGN.md`는 변경하지 않았다.
- Architecture scope 검증: 변경 소비자·원래 union/refresh 전제의 파일을 임시 `GIT_INDEX_FILE`에만 게시하고 기존 checker의 `_stamped_document`로 만든 review를 임시 index blob에만 기록한 뒤 `python3 scripts/check_architecture.py --staged` 통과 — `source_sha256=f1a913419f47b3a4d41894f85473ad22e73d5b487240c6ecba60290fbb57c882`, 2127 files. 실제 index SHA-256과 working architecture review block이 검증 전후 동일했다.
- 공유 review 보호: `memory://root/memory_summary.md`의 shared-stamp 경고를 현재 `scripts/check_architecture.py`의 `_atomic_write_document`와 `main`으로 재확인했다. `--staged --stamp`도 working `ARCHITECTURE.md`를 쓰므로 다른 작업의 review를 덮지 않고 임시 index에서만 stamped review를 검증했다. Working 전체 freshness나 `test:gate` 통과로 주장하지 않으며, 실제 committer는 자신의 최종 staged set을 다시 stamp해야 한다.
- 임시 source preview와 이 작업이 생성한 QA Chromium을 종료하고 `/tmp/afterglow-instance-policy-disclosure-qa`를 삭제했다. 임시 architecture index도 검증 종료 시 자동 제거했다.
