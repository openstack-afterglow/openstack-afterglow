## Implementation Tasks

- [x] 실제 터미널·bootstrap·image profile과 빈 영구 홈 조건을 확인하고 누락 원인을 특정한다.
- [x] 독립 dev worktree에서 시스템 Bash completion/CLI 도움말 초기화를 구현하고 사용자 설정·비대화형 shell을 보존한다.
- [x] 실제 TAB 입력·빈/기존 영구 홈·중첩 shell·credential/권한 경계를 확인하는 image PTY 회귀를 구현한다.
- [ ] source 회귀와 slim/alpine × amd64/arm64 정본 이미지 build·실행·실제 PTY smoke를 완료한다. (source 7/7, arm64 두 base 전체 PTY smoke 통과, amd64 두 base build·interactive 완성 assertion 통과; amd64 전체 PTY smoke는 Rosetta 홈 오염으로 native runner 필요)
- [x] Afterglow 사용/배포/architecture/changelog와 독립 workload README를 동기화하고 실행 증거·운영 rollout 경계를 기록한다.
