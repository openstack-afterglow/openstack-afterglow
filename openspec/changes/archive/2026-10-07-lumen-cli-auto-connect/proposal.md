## Why

사용자는 설치 스크립트 실행 후 추가 환경변수나 provider/model flag 없이 Claude Code와 Codex가 Lumen으로 연결되기를 요청했다. Claude Code의 safeguards 422는 별도 Lumen 0.6.4 서버 수정으로 복구한다. 현재 설치기는 Codex Lumen provider만 등록하고 기본 provider를 보존하므로 plain codex는 기존 codex-lb/OpenAI로 갈 수 있다.

## What Changes

POSIX와 Windows 설치기가 관리하는 셸 프로필에 terminal-only codex 함수를 추가하여 현재 Codex 0.134.0+의 native `lumen-cli.config.toml` profile로 Lumen provider와 선택 모델을 지정한다. 기존 TOML 기본 provider/model 및 데스크톱 앱 설정은 보존한다. 호출자가 명시한 -m 또는 subcommand -c override는 계속 사용할 수 있고 argument boundaries를 유지한다. Claude에는 수동 workaround 환경변수를 강제하지 않는다. 관련 문서와 네 언어 연결 안내를 동기화하고 설치기·실제 CLI·프로젝트 gate를 검증한다.

## Capabilities

### Modified Capabilities

- CLI bootstrap: plain terminal codex/claude 연결. Secure local credential storage 및 idempotent marker replacement 유지.

## Impact

공개 `/install/lumen.sh`와 `/install/lumen.ps1`, 설치기 테스트 및 연결 문서. 사용자는 새 설치기 실행 뒤 새 터미널을 열면 된다. 운영 반영은 scoped Afterglow frontend release와 Lumen 0.6.4 release/rollout을 필요로 한다. 무관한 서비스나 공유 작업 트리는 변경하지 않는다.
