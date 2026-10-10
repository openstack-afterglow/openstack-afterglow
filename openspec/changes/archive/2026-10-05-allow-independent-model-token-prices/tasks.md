## Implementation Tasks

- [x] 이미지·음성 가격 저장의 UI·Lumen API/repository 쌍 검증과 기존 admission 경계를 추적한다.
- [x] 이미지 및 기존 text-kind 미디어의 텍스트 입력·출력 단가를 독립 등록·수정한다.
- [x] TTS/STT/realtime 단방향·모달리티별 가격의 null/0/미변경 보존 회귀를 적용한다.
- [x] 실제 브라우저와 실제 Lumen 관리자 HTTP·DB 저장/재조회 경로를 검증하고 결과·계약 문서를 갱신한다.

## Verification

- 실제 Chromium UI → Lumen 관리자 HTTP → SQLite: 기존 text-kind `gpt-image-2`, image, TTS, STT, realtime의 단방향 저장·재열기와 다른 텍스트·캐시·모달리티 단가 보존을 확인했다. `null` 해제, explicit `0`, 변경 없는 저장의 무요청, 단방향 수동 등록(201), 조회 후보 단방향 비활성 등록(201)을 확인했다. 후보 text 활성화와 incomplete effective text pricing gate는 차단 상태다.
- 합성 identity/discovery이며 모델 CRUD와 저장 projection은 실제 Lumen source/SQLite다. Desktop 1280×1080·mobile 390×844의 실제 modal을 확인했다. 운영 Keystone/BFF 통합·MariaDB worker·유료 provider 호출·운영 배포는 하지 않았다.
- 관리자 가격 UI 3 files/70 tests, Svelte check 2,174 files/0 errors/0 warnings 통과. `npm run test:lumen`의 backend BFF 41·frontend 147 tests 통과.
- HEAD+가격 관련 source/test 4개만 담은 격리 architecture index(2,164 files, `f0e17563820478c4bfb97d12dc572a2e244806265d4c5e50e5a2c4994d9b1603`)의 stamp·`--staged` 통과. 실제 index·공유 review marker와 동시 사용자 변경을 보존했다. 공유 worktree 전체 `test:gate`는 실행하지 않았으며 commit/push/배포도 하지 않았다.
- 임시 가격·후보 HTTP server와 Vite preview, 브라우저 tab, SQLite 및 smoke script를 정리했다. GBrain CLI와 detector가 설치되지 않아 sync는 미실행이다.
