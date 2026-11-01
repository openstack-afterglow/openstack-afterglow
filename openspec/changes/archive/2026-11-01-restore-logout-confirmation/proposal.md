## Why
명시 로그아웃의 진행 페이지 도입 중 기존 확인 단계가 제거됐다. 사용자는 확인 후에만 로그아웃 페이지로 이동하기를 요청했다.

## What Changes
- Header와 workspace chooser의 일반 로그아웃은 기존 ConfirmDialog와 현지화 문구를 재사용한다.
- 취소는 route·credential·revocation 상태를 바꾸지 않는다. 확인 뒤에만 startLogout으로 즉시 /logout 전환과 기존 정리를 수행한다.
- 전체 로그아웃의 기존 별도 확인, 만료 복구·owner fence·진행 화면은 보존한다. Backend/schema/deployment 영향 없음.

## Acceptance
실제 compiled UI에서 취소 시 세션과 경로 유지·logout API0, 재확인 시 /logout 진행과 정상 완료를 관측한다. 관련 회귀와 check/build를 실행한다.
