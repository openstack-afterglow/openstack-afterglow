## Why

완료된 Afterglow·Lumen·Drover·Waygate·Palimpsest 로컬 결과와 관련 worktree/branch를 최신 local dev에 통합·검증하고 정상 push한 뒤, 정확한 SHA의 CI·불변 patch tag·정식 산출물 발행을 확인한 후 wireguard-server Kolla 배포를 진행한다. 미완료·무관한 공유 작업과 기존 운영 데이터는 보존한다.

## What Changes

- 각 저장소의 현재 변경, 실제 version consumer, architecture와 릴리즈 산출물 계약을 검토한다. 확인된 릴리즈 차단 결함은 최소 수정과 소비자 행동 회귀로 해결한다.
- 저장소별 게이트와 실제 실행 smoke를 완료하고 사용자 변경·자격 증명·볼륨을 보존한 채 dev 커밋과 정상 push를 진행한다.
- main 대상 PR 생성·편집과 merge는 원래 pie_root 소유 경계였다. 2026-10-04 사용자 후속 지시(“필요한 pr 이 있으면 다 pr 요청 보내고 나한테 요청해”)에 따라 이 세션이 필요한 dev→main PR을 생성·갱신하고 링크와 확인된 gate를 사용자에게 요청한다. Main 직접 커밋·강제 push·자동 merge·native reviewer 승인 우회는 하지 않는다.
- 최신 배포 계약(2026-10-05)은 검증된 dev commit의 CI 성공 → 기본 patch tag → version image/package와 latest 또는 게시된 stable alias 검증 → 필요한 operator package만 갱신 → 실제 Kolla rollout이다. Main 직접 커밋·자동 merge와 native reviewer 승인 우회는 하지 않는다. 이전 main 통합 완료 여부와 새 patch의 CI/발행은 별개다.
- 요청한 표준 명령은 `kolla-ansible genconfig -i multimode` → `kolla-ansible pull -i multimode` → `kolla-ansible reconfigure -i multimode`다. 마지막 읽기 전용 관측에서는 `/etc/kolla/multimode`가 없었다. 기존 inventory를 덮어쓰거나 `multinode` 실행을 요청 명령의 성공으로 대체하지 않고 동일 대상의 검증된 연결을 먼저 준비한다.
- 자동 dev push가 별도 tag/prerelease 또는 privileged cloud mutation을 유발하는 저장소는 해당 효과의 권한이 해결될 때까지 로컬 커밋에 보존한다. CI를 변경하거나 candidate branch로 우회하지 않는다.
- 전체 병렬 작업·회귀 검증과 확인된 문제 처리가 끝난 뒤에만 배포한다. 사용자가 확인 중인 기존 WireGuard 서버 keepalive·네트워크 설정은 변경하지 않는다.
- 배포 전후 VIP·ProxySQL·HAProxy뿐 아니라 Keystone과 나머지 활성 서비스의 실제 health·인증·읽기 경로를 확인한다. 비정상 상태는 원인·영향·복구 지점을 확인하고 최소 범위로 처리하며, container running이나 unauthenticated 200만으로 정상 판정하지 않는다.

### Four-service production exception (2026-10-05)

Owner가 요청된 main PR들을 병합했다고 보고한 뒤, 정확한 main push CI·registry 게시·정식 artifact 보존과 source 관계를 읽기 전용으로 검증했다. 후속 선택 `4개만 운영 배포`는 운영 범위를 Afterglow·Lumen·Drover·Waygate로 제한한다. Palimpsest native 입력 업로드/호스팅·URL 설정·승인·정식 발행과 package/image/storage/controller 변경은 계속 보류한다.

요청 inventory 이름은 그대로 `multimode`다. 네 서비스의 `genconfig`·`pull`·`reconfigure`는 표준 CLI에 `--tags afterglow,lumen,drover,waygate`를 명시하며 태그 없는 stock/Palimpsest 재배포를 하지 않는다. 태그 선택도 native loadbalancer의 HAProxy·ProxySQL·Keepalived 변경 handler를 격리하지 않으므로 현재 shared-infrastructure 수용과 복구 가능한 서비스별 datastore 백업을 먼저 확보한다. 기존 Kolla `stable/2025.2`·일반 의존성·키·데이터·기존 WireGuard/keepalive·Palimpsest 입력을 보존하며, operator root source tag는 Drover `v0.3.1`·Lumen `v0.6.2`·Waygate `v0.3.1` 세 개만 승격한다.

현재 `multinode`에는 compute4를 HTML comment로 감싼 문법 오류가 있어 Ansible INI parser가 실패한다. Compute4 비활성화 의도를 유지하는 INI comment 정정과 검증된 동일 inventory 연결만 준비하며 호스트/그룹의 소유권·대상을 바꾸지 않는다. 원본을 보존하고 요청 inventory parse/dispatch를 실제 확인한 뒤 다음 단계로 진행한다. Scope 선택은 auth·schema·backup·storage·runtime 선행 조건을 면제하지 않는다.

## Historical Decisions

아래 날짜별 지시는 당시의 선택과 관측을 보존한다. 현재 순서·inventory·버전 정책은 위 2026-10-05 계약과 tasks의 `Explicit Release-first Deployment Contract`가 우선한다. 과거 local/hosted/main 증거는 새 patch publication 또는 현재 운영 health를 증명하지 않는다.

- 2026-10-02 사용자 후속 선택은 즉시 신규 후보 rollout 대신 wireguard-server의 현재 운영 상태에서 표준 `kolla-ansible reconfigure -i multinode`가 커스텀 서비스를 재배포할 수 있게 준비하는 것이다. 현재 image digest·키·볼륨·inventory·사용자 변경은 유지하고, 이미 게시된 운영 버전의 operator role pin·설치 연결과 실행 선행 조건만 정리한다. 실제 서비스 restart와 신규 main/tag/release는 이 준비 acceptance와 분리한다.
- 2026-10-03 사용자 지시는 Kolla `stable/2025.2`의 최신 branch 상태를 유지하는 것이다. `/etc/kolla/pyproject.toml`과 operator uv 프로젝트를 직접 편집하거나 commit pin으로 되돌리지 않는다. 새 dependency 정보는 `uv sync`로만 취득하며 branch ref 갱신 옵션과 실제 설치 revision을 확인한다. 최신 branch/release의 실패한 build/test/package를 모두 파악·수정하고 로컬 검증과 GitHub Actions 발행 성공이 전부 확인된 뒤에만 Kolla rollout한다. 이 조건부 배포 승인은 main PR·merge 소유권, native KVM publication gate, 운영 backup·auth·datastore 보호를 우회하지 않는다.
- 2026-10-04 사용자는 “네 source tag만 제한적 수정 허용”을 선택했다. 모든 정식 발행을 확인한 뒤 live/repo operator `[tool.uv.sources]`의 Droverv0.3.0·Lumenv0.6.1·Waygatev0.3.0·Palimpsestv0.3.0 tag만 갱신할 수 있다. Kolla `stable/2025.2`와 나머지 설정은 보존하고 lock은 직접 편집하지 않고 `uv sync`로만 생성한다. Owner main 통합·native reviewer·backup/auth/storage gate와 배포 선행 조건은 그대로 유지한다.
- 2026-10-04 사용자는 배포 진행을 재요청하며 필요한 PR을 모두 생성해 자신에게 요청하도록 승인했다. 현재 GitHub refs와 main 대비 후속 커밋을 다시 확인해 이미 통합된 후보는 중복 PR을 만들지 않고, 빠진 최신 수정만 PR로 요청한다. 기존 전체 발행·native proof·auth/backup/storage 선행 조건과 허용된 operator 변경 범위는 유지한다.

## Capabilities

### New Capabilities

없음. 현재 변경의 릴리즈 준비와 배포 검증이다.

### Modified Capabilities

- 프로젝트 선택과 튜토리얼 탐색의 auth/project fence.
- 프로젝트 원본 주체를 유지하는 Palimpsest native gateway와 검증된 TLS.
- Nova host capacity projection의 PCI count bound와 aggregate metadata 일치.
- mutation 이후 관리자 project inventory 캐시의 freshness.

## Impact

서비스 ownership은 변경하지 않는다. Afterglow는 인증된 UI/BFF이며 독립 실행·저장소·provider·worker·package authority는 해당 서비스가 소유한다. 정확한 patch의 CI·정식 publication 및 별도 native/auth/backup/storage acceptance는 운영 배포 선행 조건이며 로컬 테스트를 운영 성공으로 표시하지 않는다. 광역 prune, 데이터/키 rotation, 강제 push, 인증 우회와 VM 생성은 수행하지 않는다.
