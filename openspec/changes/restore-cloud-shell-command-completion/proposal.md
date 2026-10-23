## Why

실제 Cloud Shell은 연결되지만 명령/옵션 자동완성과 도움말 발견성이 부족하다. root Dockerfile은 bash-completion을 설치하나 scripts/profile.sh는 PATH만 설정한다. Cinder 영구 홈은 이미지의 기본 .bashrc를 가릴 수 있어 사용자 홈 skeleton에 의존한 수정은 충분하지 않다. 터미널은 xterm onData를 그대로 전송하고 bootstrap은 Bash login shell을 실행한다.

## What Changes

- 독립 workload 저장소 openstack-client의 dev worktree에서 시스템 Bash 초기화를 보완하고 설치된 OpenStack 플러그인의 command/subcommand/option 완성을 제공한다. 완성 데이터는 인증 없이 build-time CLI에서 생성한다.
- 빈 영구 홈·기존 사용자 홈·중첩 interactive shell에서 기존 dotfile/alias를 덮어쓰지 않고 작동한다. 비대화형 스크립트에는 출력/부작용을 추가하지 않는다.
- 오프라인 도움말 안내와 지원 명령 설명 진입을 제공하고 ll 편의 alias는 사용자 정의가 없을 때만 제공한다. Bash를 다른 shell로 교체하지 않는다.
- 실제 setuid bootstrap PTY에 TAB을 입력해 completion 결과를 확인하고 두 base × 두 architecture의 image를 build/run한다. Credential echo/권한강하/영구 홈 보존 회귀도 유지한다.

## Capabilities

### New Capabilities

- `cloud-shell-interactive-environment`: 기존 workload의 명령 완성·오프라인 도움말·사용자 홈 보존을 명시하는 capability spec을 추가한다. 새 API나 native 권한은 추가하지 않는다.

### Modified Capabilities

기존 workload shell 초기화와 실제 image smoke를 확장한다. OpenStack 권한·resource API·Afterglow terminal transport는 바꾸지 않는다.

## Impact

변경 구현은 /Users/pieroot/code/openstack-client-shell-dev의 dev branch에 격리하며 원본 main checkout과 사용자의 .DS_Store는 보존한다. Afterglow에는 운영/사용 문서와 OpenSpec 기록만 추가한다. 기존 운영 Cloud Shell 컨테이너/영구 홈/세션·native 권한·workload image pin은 무단 변경하지 않는다. 로컬 실제 이미지 수용과 운영 신규 세션의 image rollout은 별도로 보고하며 registry publication/운영 반영은 사용자 승인 범위에 따른다. 자동완성은 설치된 명령/옵션 중심이며 리소스 목록을 자동 조회하지 않는다.
