## Why

사용자는 Cloud Shell 기본값을 `image = "ghcr.io/openstack-afterglow/openstack-client:slim"`, `image_pull_policy = ""`, `registry_id = ""`로 일치시키고, Kolla가 globals/passwords로 배포 설정을 자동 갱신하되 명시한 operator TOML 항목만 최종 override하도록 요청했다. K8s·Helm에도 동일 base configuration을 이용한 자동 생성과 curl로 실행하는 TUI의 로컬 설정 편집·배포 파일 생성을 요청했다.

현재 Kolla는 generated base → operator → zz-kolla 및 globals 기반 env 순서여서 많은 명시적 operator 설정이 실제 runtime에서 무시된다. Root `setup.py`는 별도 오래된 TOML/K8s renderer를 가지고 Helm 선택을 지원하지 않는다. `generate_k8s.py`와 `config2helm.py`는 수동 생성한 base 파일을 전제로 하고 서로 다른 override 처리를 한다.

## What Changes

- Cloud Shell 세 기본값을 backend/examples/K8s/Helm/Kolla와 setup 초기화에서 통일한다. Production digest 검증은 완화하지 않고 활성화된 workload의 moving image는 기존 신뢰된 resolver 경로로 실제 배포 전에 고정한다.
- Kolla의 generated inputs는 매 genconfig/reconfigure에서 native globals/passwords 값을 다시 반영한다. Operator 소스는 별도 read-only 입력으로 보존하고 제공한 key만 가장 높은 파일 우선순위로 재귀 병합한다. False/0/빈 문자열/배열도 명시 값이며 생략과 구분한다. 오래된 final-wins layer와 env가 이를 다시 무효화하지 않게 runtime/bootstrap/policy/worker/frontend/precheck 소비자를 함께 이행한다.
- Kolla source/생성물은 분리하고 secret은 no_log와 private mode로 다룬다. Frontend는 기존 closed public projection만 전달한다. Native infrastructure validation·image digest·TLS·권한·DB bootstrap 경계는 유지한다.
- `afterglow.conf.example`을 유일한 full default template로 재사용한다. 기존 로컬 `afterglow.conf` 및 지원하는 sparse override를 보존한 상태에서 K8s/Helm 설정을 생성한다. Setup의 중복 renderer를 정본 생성기로 통합한다.
- Namespace 선택만으로 저장소의 DMSLab 전용 URL profile을 자동 적용하지 않는다. 공용 setup과 direct generator는 로컬 endpoint 설정을 보존하며 기존 환경 profile은 `--override`로 명시할 때만 사용한다.
- 기존 `setup.py`를 실제 terminal UI로 확장하고 trusted GitHub bundle을 받아 동일 workflow를 실행하는 curl entrypoint를 제공한다. 터미널 입력은 curl pipe와 분리하고, 저장·생성 전에 확인하며 시크릿·미지정/사용자 정의 값·취소/오류 시 기존 파일을 보존한다. 자동 모드도 같은 생성 경로를 사용한다.
- 설정/Secret 및 민감 backup의 권한을 제한하며 source ref를 기록한다. Script는 로컬 설정과 deploy artifacts 생성까지만 하고 sudo/kubectl/helm/kolla apply·클러스터 생성·운영 변경을 실행하지 않는다.

## Capabilities

### New Capabilities

- GitHub curl entrypoint에서 base 초기화, local TUI 편집과 Kubernetes/Helm artifact 생성을 수행하는 단일 operator workflow.

### Modified Capabilities

- Kolla 자동 구성과 operator sparse override 우선순위.
- Cloud Shell defaults 및 K8s/Helm configuration generation consistency.

## Impact

배포 역할·generator/setup·config examples와 해당 consumer tests/docs가 범위다. API·DB schema·사용자 workspace·Cloud Shell source image 구현은 바꾸지 않는다. 공유 dev checkout/index와 이전 작업·private credential·기존 running stack/volume을 보존한다. 운영 Kolla 실행·클러스터 apply·Afterglow main merge/release는 승인 범위가 아니다. 새로운 curl source가 GitHub에 게시되기 전에는 원격 URL 실행이 완료되었다고 주장하지 않는다. 실제 native Ansible/CLI/PTY/renderer 및 격리 container proof와 미검증 운영/cluster 경계를 분리한다.
