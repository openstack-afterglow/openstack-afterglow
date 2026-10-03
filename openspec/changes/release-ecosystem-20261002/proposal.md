## Why

현재 기본 checkout의 Afterglow·Lumen·Drover·Waygate·Palimpsest 변경을 검증하고 dev에 커밋/push한 뒤 main 통합, 버전 tag/release와 Kolla 배포를 진행한다. 다른 worktree·저장소와 운영 데이터는 범위 밖이다.

## What Changes

- 각 저장소의 현재 변경, 실제 version consumer, architecture와 릴리즈 산출물 계약을 검토한다. 확인된 릴리즈 차단 결함은 최소 수정과 소비자 행동 회귀로 해결한다.
- 저장소별 게이트와 실제 실행 smoke를 완료하고 사용자 변경·자격 증명·볼륨을 보존한 채 dev 커밋과 정상 push를 진행한다.
- main 대상 PR 생성/편집 및 merge는 pie_root 소유 경계다. 승인된 dev 후보의 main PR 본문은 로컬에 준비하며 이 세션에서 main PR·merge를 대신 수행하지 않는다.
- main 통합 후 불변 tag와 wheel/image 게시 결과를 검증하고 Kolla operator dependency를 정확한 릴리즈에 고정한다. 이미 게시된 Lumen 0.5.0은 중복 릴리즈하지 않는다.
- 배포 호스트 `/etc/kolla/multimode`는 없으며 사용자가 기존 `multinode`로 실행하는 선택을 명시했다. 배포 순서는 `uv sync` → `kolla-ansible genconfig -i multinode` → `kolla-ansible reconfigure -i multinode`이다.
- 자동 dev push가 별도 tag/prerelease 또는 privileged cloud mutation을 유발하는 저장소는 해당 효과의 권한이 해결될 때까지 로컬 커밋에 보존한다. CI를 변경하거나 candidate branch로 우회하지 않는다.
- 전체 병렬 작업·회귀 검증과 확인된 문제 처리가 끝난 뒤에만 배포한다. 사용자가 확인 중인 기존 WireGuard 서버 keepalive·네트워크 설정은 변경하지 않는다.
- 배포 전후 VIP·ProxySQL·HAProxy뿐 아니라 Keystone과 나머지 활성 서비스의 실제 health·인증·읽기 경로를 확인한다. 비정상 상태는 원인·영향·복구 지점을 확인하고 최소 범위로 처리하며, container running이나 unauthenticated 200만으로 정상 판정하지 않는다.
- 2026-10-02 사용자 후속 선택은 즉시 신규 후보 rollout 대신 wireguard-server의 현재 운영 상태에서 표준 `kolla-ansible reconfigure -i multinode`가 커스텀 서비스를 재배포할 수 있게 준비하는 것이다. 현재 image digest·키·볼륨·inventory·사용자 변경은 유지하고, 이미 게시된 운영 버전의 operator role pin·설치 연결과 실행 선행 조건만 정리한다. 실제 서비스 restart와 신규 main/tag/release는 이 준비 acceptance와 분리한다.
- 2026-10-03 사용자 지시는 Kolla `stable/2025.2`의 최신 branch 상태를 유지하는 것이다. `/etc/kolla/pyproject.toml`과 operator uv 프로젝트를 직접 편집하거나 commit pin으로 되돌리지 않는다. 새 dependency 정보는 `uv sync`로만 취득하며 branch ref 갱신 옵션과 실제 설치 revision을 확인한다. 최신 branch/release의 실패한 build/test/package를 모두 파악·수정하고 로컬 검증과 GitHub Actions 발행 성공이 전부 확인된 뒤에만 Kolla rollout한다. 이 조건부 배포 승인은 main PR·merge 소유권, native KVM publication gate, 운영 backup·auth·datastore 보호를 우회하지 않는다.

## Capabilities

### New Capabilities

없음. 현재 변경의 릴리즈 준비와 배포 검증이다.

### Modified Capabilities

- 프로젝트 선택과 튜토리얼 탐색의 auth/project fence.
- 프로젝트 원본 주체를 유지하는 Palimpsest native gateway와 검증된 TLS.
- Nova host capacity projection의 PCI count bound와 aggregate metadata 일치.
- mutation 이후 관리자 project inventory 캐시의 freshness.

## Impact

서비스 ownership은 변경하지 않는다. Afterglow는 인증된 UI/BFF이며 독립 실행·저장소·provider·worker·package authority는 해당 서비스가 소유한다. main 통합·별도 publication/cloud acceptance 권한과 게시 산출물은 운영 배포 선행 조건이며 로컬 테스트를 운영 성공으로 표시하지 않는다. 광역 prune, 데이터/키 rotation, 강제 push, 인증 우회와 VM 생성은 수행하지 않는다.
