## Implementation Tasks

- [x] 프로필 저장 경로, native 사용자 기본 프로젝트와 로그인·provider 공통 선택 경로를 추적해 원인을 확인한다.
- [x] 사용자 선호·명시 선택·접근 불가/타 도메인·Default 생성 경계를 검증하는 회귀를 추가하고 공통 우선순위를 최소 수정한다. 수정 전 password/provider2건 실패, 수정 후 native consumer34건 통과.
- [x] 정확한 selector와 auth target, 실제 HTTP/session 및 브라우저 자동 진입 경로를 검증한다. Consumer203·native34통과, real HTTP profile 저장 뒤 password/provider와 세션 Work 일치·브라우저 Work header 확인. Auth target472passed/4failed/4errors, 전체 gate8181passed/18failed/91skipped의 기존 범위 밖 실패와 downstream 미실행은 docs/testing.md에 기록했다.
- [x] 로그인 계약·architecture·changelog·검증 결과와 한계를 기록한다. 양 architecture backend/worker build·uid1000 source parity와 기존 DB URL/config hash를 보존한 정본 backend rollout/health200 확인. 격리 public snapshot working/staged architecture guard digest 일치, 공유 index/global marker·private 입력 보존. 검증 완료 후 OpenSpec archive.
