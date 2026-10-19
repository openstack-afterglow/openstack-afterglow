## Why

사용자가 최신화한 `https://git.dmslab.re.kr/system/openstack/openstack-client` 소스를 Cloud Shell의 이미지 정본으로 사용하고, `openstack-afterglow` GitHub 조직 아래에서 빌드하도록 요청했다. 원본 로컬 checkout은 `/Users/pieroot/code/openstack-client`, baseline `434529e`이다. README의 실제 원본 registry는 `glcr.dmslab.re.kr/system/openstack/openstack-client`다. 현재 Afterglow는 자체 중복 CLI image를 빌드하며 source image에는 Afterglow의 PTY bootstrap helper가 없어 주소만 교체하면 실행할 수 없다.

## What Changes

- Git 이력을 보존한 `openstack-afterglow/openstack-client` GitHub 저장소를 생성한다. 명시적 라이선스가 없고 GitLab이 인증을 요구하므로 공개 범위를 늘리지 않고 우선 private으로 만든다. 기존 GitLab remote와 working source는 보존한다.
- Afterglow의 root-only setuid launcher / echo-off PTY handshake / tmpfs mode0600 token / UID1000 shell / persistent-home 보안 계약과 검증을 openstack-client로 이전한다. 갱신된 pinned CLI dependency와 Debian/Alpine build를 재사용하고 amd64/arm64를 실제 검증한다.
- GitHub Actions는 소스 검사와 실제 architecture별 image/CLI/bootstrap smoke 성공 뒤 GHCR `ghcr.io/openstack-afterglow/openstack-client`의 immutable revision tags 및 multiarch slim/alpine/latest를 게시한다. PR은 게시하지 않는다. 로컬 검사 후 최초 소스 push와 정확한 SHA의 Actions 결과를 확인한다.
- Afterglow는 위 GHCR 이미지를 기본으로 선택한다. 기존 `image` reference 설정을 재사용하여 다른 registry도 선택할 수 있고 `image_pull_policy` (`always` / `ifnotpresent` / `never`), optional Zun `registry_id`를 TOML/env/K8s/Helm/Kolla에 동기화한다. Registry 자격 증명은 Zun 소유이며 Afterglow/browser에 넣지 않는다. Zun driver는 명시적 docker다.
- 운영 immutable sha256 digest 요구와 missing-image failure/cleanup 계약을 유지한다. 빌드·이미지 준비 전에도 비활성 설정 저장은 가능하고, fallback image나 성공 상태를 위조하지 않는다.
- 기존 Afterglow-owned Cloud Shell build/package/version-sync/CI 경로는 제거해 독립 image 정본을 중복 유지하지 않는다. 일반 Cloud Shell API/UI/lease/Cinder 소유권과 사용자 consent는 변경하지 않는다.

## Capabilities

### New Capabilities

- GitHub 조직 소유의 OpenStack client multiarchitecture image build/publication 및 Afterglow 호환 bootstrap.

### Modified Capabilities

- 운영자가 선택하는 Cloud Shell image reference, pull policy, private Zun registry ID.
- Cloud Shell image 소유권을 Afterglow monorepo에서 전용 openstack-client repository로 cutover.

## Impact

Backend settings/Zun payload, deployment renderers, image source ownership와 CI만 변경한다. DB/schema/migration·production IAM·사용자 workspace는 변경하지 않는다. GitHub source push와 GHCR 게시를 요청 범위로 포함하지만 Afterglow main merge/tag/release/운영 배포와 실제 tenant mutation은 포함하지 않는다. 공유 dev/index/진행 중인 동시 변경을 보존한다. 실제 upstream registry pull과 authenticated OpenStack attach acceptance는 source/build 증거와 구분한다.

## Verification evidence

- Parent configuration: focused backend Cloud Shell/safety/K8s selectors84passed. Actual TOML/env loader → native keystoneauth/Zun adapter → synthetic loopback HTTP create/exec/exact-cleanup6cases passed (default/member,3explicit admin policies, unpublished image, explicit-policy403). Provider/network/home are synthetic; no live OpenStack or Redis mutation. Initial throwaway fixture lacked stop handling/cache reset and was corrected without product-code changes before this proof.
- Actual generate_k8s renderer, `helm template`, both Kolla Cloud Shell Jinja sections and TOML/env precedence passed. Private dev input `.local-services/afterglow.conf` and root base choose the new GHCR reference; this does not claim a running backend restart or live shell acceptance.
- Required pre-change CI timing baseline: latest20completed Afterglow push runs, IDs38692251346…38256798938, job+step API timings collected. Created-to-last Layered Tests job median131.5s/p90140s. Afterglow pipeline changes remain local and the new client repo has no previous GitHub CI; no post-change20run comparison or performance improvement is claimed. Scope is image ownership, not CI optimization.
- Source `4ea9cbd4e6ee6b25815417e02646e7179ab1b9a3` was pushed to private GitHub with parent `434529e` retained. Exact Actions run38882078745 passed all four native build/runtime gates and GHCR publication. Published slim/latest index `sha256:239c7d3972de6e2df7387904ae8fa7a637f0c021d56d4254bba91880a34827a2`; Alpine index `sha256:2bb98716d81bd04894438e2e4fcb32943987abe8201c9a0cd7280d8720cfe2d9`. Local package API and existing Docker inspection remain403 without required package scopes; ACL details/authenticated pull/live Zun are not claimed.
- Afterglow cutover regression: Cloud Shell backend30/frontend29, orchestration166, Kolla24+11, CI decisions52, version sync1.30.12; configuration consumers161passed. Real config2helm CLI→Helm ConfigMap reproduced a lost Cloud Shell toggle before the full mapping fix and passed four selected-policy/image/registry cases after. Both actual backend architectures passed the six native-SDK/loopback HTTP lifecycle/error scenarios.
- Frozen public source architecture working/staged guard: `0a12d3631aaf68fdf966e6a051b87265fff1a196f094b8d7735227011924e840`,2994files. Shared index/review marker and private credentials remain untouched. No full Afterglow gate, commit/push/release, production or live tenant acceptance is claimed; independent source upload/build is complete.
