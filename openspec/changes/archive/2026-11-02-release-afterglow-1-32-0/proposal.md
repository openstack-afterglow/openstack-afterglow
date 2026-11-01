## Why

사용자가 현재 변경 전체의 GitHub 게시와 minor version-up, release notes를 요청했다. 이미 발행한1.31.4를 변경하지 않고1.32.0으로 게시한다.

## What Changes

- 현재 완료된 resize composer, IAM, authentication recovery, instance detail 변경을 함께 검토·검증한다.
- 기존 version sync로1.32.0 metadata를 맞추고 dev exact-SHA CI 뒤 불변tag, images 및 GitHub notes를 발행한다.
- controller1 incident에 따른 운영 cutover hold는 유지한다.

## Capabilities

### New Capabilities
- `minor-release-publication`: verified GitHub-only minor publication with explicit production boundary.

### Modified Capabilities
None; underlying feature contracts are tracked by their existing changes.

## Impact

Root/frontend/backend/Helm/Kolla version metadata, CHANGELOG and existing reviewed implementation. No new migration, dependency or production operation is introduced by this release procedure.
