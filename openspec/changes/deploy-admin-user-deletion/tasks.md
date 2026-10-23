## Implementation Tasks

### Source and release qualification

- [x] 1.30.25 release metadata를 auto-stage/commit/tag 없이 canonical root npm bump와 `version:sync` 소유 범위에서 동기화한다. Frontend npm lock의 기존1.30.19 version drift는 script 소유 범위 밖이므로 보존한다. Architecture overview와2026-10-24 changelog에 발행/운영 대기·Cloud Shell 제외 경계를 명시한다.
- [ ] 공유 dev/worktree/index/private state와 기존1.30.24 복구 지점을 보존한다. 관리자 삭제·Accounts 명시적 onboarding/last-unlink safety의 완료 source를 함께 검토하고 무관한 미완료 작업은 포함하지 않는다.
- [ ] 최종 통합 source의 architecture review/stamp와 필수 `npm run test:gate`, 관련 exact selector·실제 HTTP/compiled UI·API/worker/frontend arm64/amd64 build/runtime 증거를 확보한다. 합성 identity/provider와 실제 실행·운영 proof를 구분한다.
- [ ] 검증된 source를 dev에 정상 commit/push하고 정확한 pushed SHA와 CI 성공을 기록한다. Main·shared index/private files·기존 tag를 보존하며 보호 규칙을 우회하지 않는다.
- [ ] 같은 CI 통과 SHA에 불변 `v1.30.25`를 발행한다. Tag workflow 성공과 API/frontend/worker version/latest revision·immutable digest, Helm version/appVersion, 실제 arm64/amd64 실행을 확인한다. Cloud Shell workload tag/image는 발행·교체하지 않는다.

### Cold schema prerequisite before writers

- [ ] 운영/로컬 effective DB·Redis 목적지와 모든 공유 Afterglow API/worker writer를 식별한다. 실행 revision/digest·기존 schema/manifest·table/row 수·native/provider/키/config 및 비대상 container fingerprint를 비밀 없이 보존하고 롤백 범위를 기록한다.
- [ ] 공유 DB의 모든 해당 writer를 drain/정지한 상태에서 일관된 cold SQL/Redis snapshot과 원래 key/companion state를 보호한다. 같은 engine/version·charset/collation·sql_mode의 격리 복원으로 snapshot 복구를 확인한다.
- [ ] 복원본에서 구/신 writer와 기존/SQL102 schema의 호환성, 실제 ORM/journal 경로·row 보존·rollback 한계를 검증한다. 과거 SQL replay·native backfill/identity 이동이 없음을 확인한다.
- [ ] 새 writer를 시작하기 전에 승인된 SQL102의 additive `account_identity_transfers` 표만 적용하고 manifest/checksum·실제 schema/readback 및 기존 row 보존을 기록한다. 실제 계정·federation·grant/resource는 변경하지 않는다.

### Canonical full-inventory Kolla rollout

- [ ] 배포서버172.30.0.50의 `/etc/kolla`에서 기존 `/etc/kolla/multinode` parse·Afterglow 전체 대상·operator package/release pin·effective DB/Redis/Keystone/key/mount/port 보존을 확인한다. `--skip-tags haproxy`는 기존 stock HAProxy와 비대상 서비스 보존을 위한 제한임을 기록한다.
- [ ] 같은 배포서버에서 `kolla-ansible genconfig -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy`를 실행하고 기존 effective 설정·키 보존을 비교한다.
- [ ] `kolla-ansible pull -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy` 및 `kolla-ansible prechecks -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy`가 전체 승인 대상에서 통과한 증거를 남긴다.
- [ ] `kolla-ansible reconfigure -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy`를 호스트 제한 없이 전체 Afterglow 대상에 한 번 실행한다. `--limit`·controller별 wrapper/순회로 대체하지 않고 recap의 실제 대상·failed/unreachable을 확인한다.

### Targeted local Compose and postrollout acceptance

- [ ] Local canonical targeted Compose의 현재 project·private env/override를 재사용하고 실제 apply와 동일 실행기/환경에서 이전과 새 service definition 및 effective DB/key/mount/port를 비교한다. Backend/frontend·해당 Afterglow worker만 교체하며 형제 서비스·datastore·volume과 키를 보존한다.
- [ ] 모든 대상의1.30.25 exact revision/digest·API/frontend health/readiness·worker restart/tick과 stdout/stderr 오류를 확인한다. Native/provider/config/key fingerprint 및 비대상 container 보존을 비교하고 public HTTPS 화면/인증 경계를 확인한다.
- [ ] 실제 계정 삭제·native resource 삭제·OIDC association 이전 없이 관리자 삭제 UI/UUID 확인·취소·현재 권한 보호 경계를 비파괴로 확인한다. 실사용 관리자 인증이 없어 미수용인 경로와 합성 fixture proof를 명시하며 별도 Identity list transport/orphan404를 이번 배포 성공으로 해결했다고 주장하지 않는다.
- [ ] Parent 소유 `docs/testing.md`와 release receipt에 exact SHA/tag/image·SQL cold restore·fleet/local rollout·비파괴 수용·미검증 경계를 기록한다. 모든 실제 완료 항목만 체크하고 배포가 끝난 뒤 OpenSpec을 spec delta 없이 archive한다.
