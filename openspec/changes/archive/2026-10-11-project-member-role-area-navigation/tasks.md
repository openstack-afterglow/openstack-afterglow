## Implementation Tasks

- [x] 현재 역할 편집·서버 area 및 상속 계약·공유 UI·디자인 규칙을 확인하고 범위를 확정한다.
- [x] 영역 우선 권한 탐색, 전체 검색, 선택 보존, 접힌 유효 역할 요약과 고정 action을 구현하고 네 locale을 갱신한다.
- [x] 기존 권한/계정 소비자 회귀를 영역 선택 흐름으로 이관하고 영역 이동·검색·상속·direct-only 저장을 검증한다.
- [x] 실제 Chromium에서 mobile/tablet/desktop·767/768·1023/1024·네 locale·light/dark, 검색/영역/저장/오류/취소와 focus를 검증한다.
- [x] 관련 문서·변경 기록과 범위별 architecture receipt를 갱신하고 change를 archive한다.

## Verification

- 정확한 role/account24개, design27files/139개; 역할 전용 locale overlay의 check0errors/기존 DocCodeBlock warning1·i18n0문제.
- 실제 current-source Chromium56조건·긴 값3조건·409 draft/취소·direct-only payload·owner/admin/inheritance/group/busy·focus 경계 확인.
- Canonical Dockerfile/frontend linux/arm64·linux/amd64 실제 build와 기존 dev Compose 별도 QA project의 healthy·Node platform 확인. Compiled Chromium112조건과 desktop/mobile direct-only PUT200 → 목록 refresh → 편집 재진입의 저장 상태 확인.
- Baseline `7f2572197747bb80e09255879836b415b0d96edd`+역할 전용 source7개. Working와 임시 index staged architecture digest `89ce2937adcd8705a78432b7b2e05cb355f264c05ee8038dd2f1c8c4d2704730`/2546files 일치; 공유 WIP/index/review marker 보존.
- 전체 `npm run test:gate` 통과: backend4595·frontend2710·contracts154·functional73(22deselected), orchestration175·Kolla27·shell installer19·frontend runner9 및 Ruff573files. PowerShell runtime 부재로36개 skip. 첫 QA의 DB driver/Redis socket 및 auth storage/animation/refresh fixture 실패와 최종 proof는 `docs/testing.md`에서 분리한다.
- Evidence: `/Users/pieroot/.local/share/afterglow-proofs/project-role-area-20261011-d5d71a9c/`. 실제 IAM·DB/secret 변경·release/publish/production deploy 없음.
