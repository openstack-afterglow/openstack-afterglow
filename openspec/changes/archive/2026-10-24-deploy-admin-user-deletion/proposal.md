## Why

사용자가 완료된 관리자 사용자 삭제 기능의 정식 발행과 운영·로컬 배포를 승인했다. 현재 운영1.30.24와 기존 사용자·native 자원·키·설정을 보존하면서 의존 관계가 있는 Accounts/OIDC 명시적 onboarding 및 마지막 native federation unlink 보호를 함께1.30.25로 배포한다. Source 검증·artifact 발행·schema 준비·운영 수용을 각각 증거로 구분한다.

## What Changes

- Root version을1.30.25로 올리고 canonical `version:sync`로 backend/frontend·Python lock·Helm과 명시적 Kolla pin을 동기화한다. 자동 `latest`/`stable` image channel은 보존한다. 완료 feature changelog를2026-10-24 release로 묶되 Cloud Shell workload의 미발행 항목은 Unreleased에 남긴다.
- 공유 checkout/index/private state를 보존하고 완료된 의존 source를 검토·검증해 `dev`에 정상 commit/push한다. 정확한 pushed dev SHA의 CI 성공 뒤 동일 commit에 불변 `v1.30.25`를 발행한다. Version/latest image·Helm artifact의 revision/digest와 arm64/amd64 실제 실행을 확인한다.
- 운영·로컬의 동일 Afterglow DB를 쓰는 모든 API/worker writer를 식별·drain/정지하고 SQL/Redis·원래 키의 cold snapshot을 보호한다. 격리 restore 및 old/new writer/schema 양방향 호환성을 확인한 뒤 SQL102의 additive `account_identity_transfers` 표만 적용하고, 새 writer 시작 전에 readback한다. 기존 identity·native federation·grant/resource·policy를 이전하거나 backfill하지 않는다.
- Kolla 배포서버172.30.0.50의 `/etc/kolla`에서 실제 `/etc/kolla/multinode` 전체 Afterglow 대상으로 표준 genconfig→pull→prechecks→reconfigure를 실행한다. 각 명령은 `--tags afterglow --skip-tags haproxy`로 비대상 stock HAProxy/서비스를 보존한다. `--limit`나 controller별 SSH/Python wrapper로 정식 배포를 대체하지 않는다.
- 로컬은 현재 프로젝트와 private env/override를 재사용하는 canonical `docker-compose.dev.yml` targeted Compose로 Afterglow backend/frontend 및 실제 존재하는 해당 worker만 교체한다. 실제 apply와 같은 실행기·환경에서 DB URL·키·mount·port·service definition/effective config를 비교하고 형제 서비스·datastore·volume은 재생성하지 않는다.
- 배포 뒤 exact revision/digest·health/readiness·worker 실제 tick 및 stdout/stderr·보존 fingerprint·공개 HTTPS 화면/인증 경계를 확인한다. 실사용 계정/native resource 삭제나 실제 OIDC association 이전은 수행하지 않는다. 삭제 success 경로의 합성/격리 proof와 운영 read-only/비파괴 수용을 구분한다.

## Capabilities

### New Capabilities

없음. 기존 완료 기능의 release/rollout이며 spec delta를 추가하지 않는다.

### Modified Capabilities

없음. 관리자 삭제의 fresh system-admin·exact home-domain·graph lease·self/service/last-admin/owner/journal 보호와 Accounts 명시 확인·native last-unlink 차단 계약을 변경하지 않는다.

## Impact

Afterglow API/frontend/Notion worker·Helm release metadata와 SQL102의 additive 표가 대상이다. 새 backend는 journal 표가 준비되기 전에 시작하지 않는다. Cloud Shell workload release/native amd64 acceptance, Lumen 등 형제 release/schema 승격, 별도 Identity list transport 및 orphan candidate404 수정은 범위 밖이다. `main`·기존 tag·운영자 비밀/설정·native identity/grant/resource는 보존한다. Backup restore가 검증되기 전에는 운영 쓰기를 시작하지 않으며 image rollback과 DB 복구의 한계를 별도로 기록한다.
