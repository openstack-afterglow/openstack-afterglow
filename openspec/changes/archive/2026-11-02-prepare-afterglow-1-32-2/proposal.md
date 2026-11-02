## Why

사용자가 현재 기본 dev 변경의 커밋과 명시적 patch version 1.32.2를 요청했다. 기존 source-only 수정과 이미 통합한 worktree 결과를 보존하고, 발행·운영 배포와 구분해 metadata를 준비한다.

## What Changes

- 기본 dev의 MCP Cinder 목록 필터 호환성, 관리자 federated 비밀번호 reset 사전 거부, VM wizard 단계 조회 진단·무효화 복구, 프로젝트 quota 소비 표시 및 관련 회귀·문서를 검토하고 커밋한다.
- 저장소의 `version:bump:patch` / `version:sync`로 root/frontend/backend·lock·Helm·명시적 Kolla sample pin을 1.32.2로 동기화한다. 의존성 업그레이드는 하지 않는다.
- 1.32.2 CHANGELOG와 architecture/source review를 갱신하고 최신 전체 test:gate, frontend build/check, 실제 버전 runtime smoke를 수행한다.
- 기존 native 최초 비밀번호·VM wizard 운영 acceptance checklist는 별도 승인·증거가 필요하므로 거짓 완료/archiving을 하지 않는다.

## Capabilities

### New Capabilities

없음. 기존 수정의 검증·커밋과 patch metadata 준비만 수행한다.

### Modified Capabilities

기존 조회·진단·표시·reset 사전 거부 동작은 해당 feature change가 소유한다. 이번 change는 준비 source의 검증 경계와 1.32.2 metadata 일치를 소유한다.

## Impact

기본 `/Users/pieroot/code/afterglow`의 dev에서만 커밋한다. Secret·ignored 설정·키·기존 서비스·DB·형제 저장소/clone은 보존한다. Push, dev→main PR/merge, Git tag, GitHub/GHCR/Helm 발행, Kolla/native/schema 운영 변경은 수행하지 않는다. 이전 1.32.1 published artifact와 운영 상태는 변경하지 않는다.
