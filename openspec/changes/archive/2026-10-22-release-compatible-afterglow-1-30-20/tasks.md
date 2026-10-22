## Release
- [x] 현재 dev 변경과 이전 exact-source gate·배포 증거를 확인한다.
- [x] 1.30.20 metadata와 문서·architecture를 동기화하고 정본 gate·staged guard를 통과한다.
- [x] 완료된 변경을 dev에 커밋하고 origin/dev로 정상 push한다.
- [x] 정확한 SHA의 CI 성공 뒤 불변v1.30.20을 발행하고 version/latest artifact를 확인한다.
- [x] 실제 inventory·native schema·복구 지점과 기존 service release/config/key 보존을 확인한다.
- [x] canonical Kolla genconfig/pull/prechecks 및 **전체 대상 표준 reconfigure**로 배포하고 readiness·running revision/digest를 확인한다.
- [x] public HTTPS 로그인 화면·인증 경계를 확인하고 결과·검증 한계를 기록한다. 사람의 실제 로그인/terminal 수용은 별도 미검증이다.

## Initial deployment hold (resolved by the preparation and final native reconfigure below)
- Release SHA `5a7588145d6ebda31fde55d304f1af5a451c1e56`; dev CI39804083098, tag images39805181098 and Helm39805181104 passed. Version/latest image digest parity verified.
- Canonical image pull passed and target-image parsing of preserved generated settings passed on all three controllers. No production container stop/replacement yet.
- Canonical prechecks failed at `Cloud Shell image | Resolve the selected moving workload reference`. Running generated configuration has `services.cloud_shell=false`, but operator source has explicit `true` with no cloud_shell image/project/network/WSS fields. Operator intent must be resolved; do not bypass prechecks or silently override it.

## Approved Cloud Shell preparation and 1.30.21
- [x] 사용자가 Cloud Shell 활성화 준비 및 기존 cloud_shell 프로젝트 재사용을 선택했다.
- [x] 실제 전용 project/network/router/default 보안 그룹·HTTPS/WSS·Zun topology를 조회하고 기존 자원을 보존했다.
- [x] 승인된 afterglow_admin→cloud_shell admin 직접 역할1건만 추가하고 검증된 공개 image digest·기존 network/보안 그룹·trusted endpoint 설정을 준비했다. 새 project/network/volume/container·registry secret 생성은 없다.
- [x] stock kolla_toolbox의 appcontainer CLI 부재를 실제 출력으로 확인하고 역할 소유 기존 SDK 기반 native Zun precheck로 수정했다. 실제 toolbox에서 exact dedicated project native list가 성공했다.
- [x] 1.30.21 정본 gate·exact-SHA CI·불변 release 및 artifact 검증을 완료했다. 1.30.20 tag는 이동하지 않았다. 실제 module argv 문제는 다음1.30.22에서 수정했다.
- [x] 최종1.30.22 역할의 canonical prechecks·stopped-writer 복구·전체 native fleet reconfigure·readiness 및 설정/키/형제 서비스 보존을 검증했다.

## Actual Ansible invocation correction
- [x] 1.30.21 direct native probes passed but the real exec module rejected the `command` argument array. Installed module schema and actual Ansible smoke verified `argv`; real controller1 tasks2 passed/changed0/failed0.
- [x] 1.30.22 exact-source gate·dev/tag CI·version/latest artifact 검증 후 native fleet reconfigure를 완료했다. 이전 tag는 보존했다.

## User clarification: native fleet reconfigure
- 사용자는 배포의 의미를 **Kolla-Ansible 배포서버에서 전체 대상에 표준 reconfigure 실행**으로 재확인했다. Controller별 `--limit` 순회는 정식 배포 완료가 아니다.
- 진행 중인 controller3 loop driver를 다음 mutation 전에 중지하고 이미 실행 중인 native precheck가 끝난 것을 확인했다. 서버는 실제 `172.30.0.50`이며 native inventory의 deployment/local executor와 일치한다.
- [x] `/etc/kolla`에서 `kolla-ansible reconfigure -i /etc/kolla/multinode --tags afterglow --skip-tags haproxy`를 **--limit 없이** 한 번 실제 실행했다. c1/c2/c3 recap 모두 failed0/unreachable0; 전체 API/frontend6개 healthy·worker3개 running·restart0이며697개 비대상 container의 변경·추가0을 확인했다. 원문 artifact://1672 및 verification.json을 따른다.
