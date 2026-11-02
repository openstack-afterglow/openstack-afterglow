## Implementation Tasks

- [x] 저장→전체 load→skeleton 및 이동 차단의 원인을 확인하고 지연 응답으로 재현한다. 실제 Chromium의 `/admin/chat/models`: 첫 이동 후 다음 버튼 disabled=true, 204 후 모델 GET을 지연하면 노출 행 3→0. Identity·API는 합성 fixture.
- [x] 저장 중 노출된 목록·드래그·위/아래 이동을 유지한다. `modelOrderBusy`에서 saving을 분리하고 오류 복구만 잠근다. 키보드 focus는 이동 직후 보존한다.
- [x] 직렬 CAS 저장과 provider별 최신 대기 순서를 구현한다. 확정 순서 snapshot과 provider별 queue를 분리하며 다음 CAS는 직전 204의 순서를 기대값으로 쓴다. 같은 provider의 대기 중 여러 이동은 최신 하나로 합친다.
- [x] 동일 서버 내용의 무변경 반영과 오래된 조회·응답 fence, 실패/409 복구를 구현한다. 모델-only background 조회로 JSON 값을 비교하고 실제 변경이 있을 때만 keyed rows를 갱신한다. 이동 revision·auth/project·수명 fence를 유지한다. 다른 CRUD의 full load는 순서 저장 완료를 기다린다.
- [x] 연속 이동·필터 슬롯·scope 및 저장 실패 회귀와 실제 Chromium 지연 저장 동선을 검증한다. 수정 전 신규 회귀 2건이 이동 disabled/목록 unmount로 실패했고 수정 후 full frontend 318 files/2,241 tests + log script 9 tests가 통과했다. Svelte check 2,311 files/0 errors/기존 DocCodeBlock warning 1, i18n 0 errors/0 warnings. 실제 `/admin/chat/models`의 연속 native drag 2회, 지연 POST 중 연속 위/아래 이동 4회, stale GET 뒤 추가 이동, 503 복구·retry·서버 가격 반영을 실행했다. 모든 카드/목록 identity 유지, 공백 관측 0, 화면/최종 저장 순서 일치. 390/767/768/1023/1024/1385px light/dark 12조건에서 overflow 0·버튼 44×44px.
- [x] 관련 문서·CHANGELOG·DESIGN·ARCHITECTURE 검토와 OpenSpec 완료 기록을 반영한다. 임시 index의 `check_architecture.py --staged --stamp`·`--staged` 및 working 검사 모두 통과했다(`source_sha256=7f20de63998806e19d212c4523efb31e5b96bc424ee10a1a51673c402ad44a25`, source 2,480 files). 실제/shared index는 변경하지 않았다. `continuous-model-reordering`은 rapid schema·skip-specs archive 대상으로 완료했다.

## Evidence and limits

- Screenshot/JSON evidence: `~/.gstack/projects/afterglow/designs/continuous-model-order-20261008/{desktop-saving.png,mobile-saving.png,verification.json}`.
- Runtime: 실제 Chromium·현재 격리 Vite source·`/admin/chat/models`. Identity 및 CAS API는 합성이다. 실제 Lumen/Keystone·provider inference·운영 배포는 실행하지 않았다.
- 전체 `npm run test:gate` 및 backend/contract/functional 계층은 미실행이다. Backend·Lumen API/DB는 변경하지 않았다.
- gbrain CLI 미설치(`command -v gbrain` exit 1)로 동기화는 수행하지 않았다. 공유 checkout과 이전 CLI worktree, 실제 사용자 설정·운영 자원은 변경하지 않았다. 커밋·push·배포도 수행하지 않았다.
