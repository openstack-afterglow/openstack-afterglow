## Why

사용자가 현재 완료 변경의 실제 배포와 정확한 1.32.1 버전을 요청했다. 새 release tag는 v1.32.1이 아니라 1.32.1이며 미래 자동화도 접두사 없는 안정 SemVer를 처리해야 한다.

## What Changes

- 현재 완료된 온도 모니터링·관리자 executor/Swift 집계·flavor 소유 재채택/FIFO 관측 수정 및 정적 로그인 시안을 보존·통합한다.
- root/backend/frontend/Helm metadata를 1.32.1로 동기화한다.
- tag 기반 테스트·이미지/Helm 발행·version apply/check·operator tag promotion은 X.Y.Z와 기존 vX.Y.Z를 인식한다. 새 정식 tag는 X.Y.Z로 발행한다.
- 필수 gate와 실행 smoke, exact SHA CI 뒤 불변 1.32.1과 이미지/latest/Helm·release notes를 검증한다.
- 운영 복구·native 인증·schema·cold restore·writer fencing은 별도 선행 조건이다. 후속 질문에서 사용자가 직접 운영 유지보수 중임을 확인하여 이번 실행은 GitHub 발행까지만 수행하고 Kolla 전환·재시작·DDL은 보류한다.

## Capabilities

### New Capabilities
- 없음.

### Modified Capabilities
- Release version identity: 접두사 없는 안정 tag를 정식 release로 처리하며 기존 prefixed tag 호환을 유지한다.

## Impact

CI/release 및 기존 완료 source 통합. 새 migration·권한 완화·인증 복구 비활성화·서비스 topology 변경은 추가하지 않는다. 운영 old/new schema 및 native first-password 선행 조건은 이전 운영 버전과의 차이를 기준으로 별도 검증한다. dev만 게시하며 main PR/merge는 pie_root 소유다.
