## Release
- [x] 현재 dev 변경과 이전 exact-source gate·배포 증거를 확인한다.
- [x] 1.30.20 metadata와 문서·architecture를 동기화하고 정본 gate·staged guard를 통과한다.
- [x] 완료된 변경을 dev에 커밋하고 origin/dev로 정상 push한다.
- [x] 정확한 SHA의 CI 성공 뒤 불변v1.30.20을 발행하고 version/latest artifact를 확인한다.
- [ ] 실제 inventory·native schema·복구 지점과 기존 service release/config/key 보존을 확인한다.
- [ ] canonical Kolla genconfig/pull/prechecks/reconfigure로 배포하고 readiness·running revision/digest를 확인한다.
- [ ] public HTTPS 화면·인증 경계를 확인하고 결과·검증 한계를 기록한다.

## Deployment hold
- Release SHA `5a7588145d6ebda31fde55d304f1af5a451c1e56`; dev CI39804083098, tag images39805181098 and Helm39805181104 passed. Version/latest image digest parity verified.
- Canonical image pull passed and target-image parsing of preserved generated settings passed on all three controllers. No production container stop/replacement yet.
- Canonical prechecks failed at `Cloud Shell image | Resolve the selected moving workload reference`. Running generated configuration has `services.cloud_shell=false`, but operator source has explicit `true` with no cloud_shell image/project/network/WSS fields. Operator intent must be resolved; do not bypass prechecks or silently override it.

## Approved Cloud Shell preparation and 1.30.21
- [x] 사용자가 Cloud Shell 활성화 준비 및 기존 cloud_shell 프로젝트 재사용을 선택했다.
- [x] 실제 전용 project/network/router/default 보안 그룹·HTTPS/WSS·Zun topology를 조회하고 기존 자원을 보존했다.
- [x] 승인된 afterglow_admin→cloud_shell admin 직접 역할1건만 추가하고 검증된 공개 image digest·기존 network/보안 그룹·trusted endpoint 설정을 준비했다. 새 project/network/volume/container·registry secret 생성은 없다.
- [x] stock kolla_toolbox의 appcontainer CLI 부재를 실제 출력으로 확인하고 역할 소유 기존 SDK 기반 native Zun precheck로 수정했다. 실제 toolbox에서 exact dedicated project native list가 성공했다.
- [ ] 1.30.21 정본 gate·exact-SHA CI·불변 release 및 artifact 검증을 완료한다. 1.30.20 tag는 이동하지 않는다.
- [ ] 새 역할로 canonical prechecks와 stopped-writer rollout·readiness·설정/키/형제 서비스 보존을 검증한다.

## Actual Ansible invocation correction
- [x]1.30.21 direct native probes passed but the real exec module rejected the `command` argument array. Installed module schema and actual Ansible smoke verified `argv`; real controller1 tasks2 passed/changed0/failed0.
- [ ]1.30.22 exact-source gate·dev/tag CI·version/latest artifact 검증 후 canonical rollout을 완료한다. 이전 tag는 보존한다.
