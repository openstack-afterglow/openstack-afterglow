## Why

현재 GPU quota는 Afterglow SQL의 project/default 정책이며 도메인 quota는 native project limit 합계의 allocation budget이다. 사용자는 GPU 모델별 수량과 CPU·RAM을 도메인 공용 사용량 풀로 관리하고 OpenStack 직접 CLI/API도 우회하지 못하도록 요구했다.

## What Changes

- **BREAKING**: 도메인 GPU·vCPU·RAM 공용 사용량 quota로 전환한다. 프로젝트는 별도 배분 없이 도메인 잔여량을 공유한다. 도메인 manager 또는 fresh system-scope admin만 해당 pool 이하의 선택적 프로젝트 상한을 설정할 수 있다. 프로젝트 상한은 예약 배분이 아니며 그 합이 domain ceiling을 넘는 것 자체로 거부하지 않는다.
- Afterglow UI/API, 직접 Nova CLI/API, 외부 서비스의 native 생성·증설 및 자원 재할당 경로에 일관된 native enforcement가 필요하다. Afterglow-only admission으로 요구를 축소하지 않는다.
- 사용자 선택: CPU 1·2·4·8… vCPU × RAM/vCPU 2·4·8GiB, GPU 모델별 1·2·4… 장의 표준 규격을 같은 eligible host가 지원하는 경우 자동 관리한다. 유한한 profile bound와 GPU 부가 CPU/RAM 규칙은 design에서 확정한다.
- Flavor lifecycle은 검증된 Nova/Placement host capabilities와 PCI alias 매핑을 사용한다. 순간 free capacity와 supported shape를 구분한다. 기존 VM 사양은 수정하지 않으며 native scheduler가 실제 장치를 할당한다.
- 첨부 예시의 `pci_passthrough:alias=RTX-3060-LHR:1,GA106-audio:1`는 매핑이 검증될 때 자동 작성한다. `afterglow:access_mode=gpu_quota`는 기존 source에서 native 권한을 강제하지 않는 metadata임을 분명히 하고 새 enforcement 계약과 정합되게 처리한다. GPU/audio alias를 장치명만 보고 추정하지 않는다.
- 기존 private flavor ACL·프로젝트 GPU override/default·CPU allocation budget과의 전환은 명시적 preview/readback을 요구한다. 기존 자원이나 운영 설정에 silent mutation을 하지 않는다.

## Capabilities

### New Capabilities

- `domain-compute-pools`: native domain shared CPU/RAM/GPU usage caps, optional project caps, exact authority, concurrency and transition semantics.
- `managed-compute-flavors`: hardware-supported stable CPU/GPU profile reconciliation, validated extra_specs, native visibility and safe retirement.

### Modified Capabilities

기존 VM 생성·resize·quota UI/API와 operator 배포 계약에 영향을 준다. 구체적인 기존 spec delta는 native integration 선택 후 정의한다.

## Impact

- Backend: `gpu_quota`, `flavor_eligibility`, `flavor_capacity`, `gpu_inventory`, `domain_quotas`, native quota transport, user/admin create·resize, MCP, internal K3s admission, SQL migration과 operation journal.
- Frontend: domain quota/manager project caps, admin flavors lifecycle/status, user/admin VM flavor eligibility, dashboard/report/mockup/i18n.
- Native OpenStack: Nova API/conductor quota enforcement 및 Placement PCI accounting, Keystone domain/project policy 읽기. 관련 native component source/image integration을 명시적으로 선택해야 한다.
- Deployment: source development와 운영 적용은 분리한다. Shared DB/config/IAM/기존 VM/volume 변경·배포는 이 proposal 작성으로 승인되지 않는다. 기존 concurrent source/index를 보존한다.

## Verified feasibility boundary

- Current repository `ARCHITECTURE.md:416`, `services/domain_quotas.py`는 domain ceiling이 actual usage cap이 아님을 명시한다.
- `services/gpu_quota.py:378-382`는 direct Nova가 Afterglow reservation에 참여하지 않는다고 명시한다.
- Nova 2025.2 unified limits는 Placement resource classes를 quota resource로 지원하지만 stock `oslo.limit stable/2025.2`의 `_StrictTwoLevelEnforcer` 모든 연산은 `NotImplementedError`이다. Keystone의 hierarchy 저장/검증 지원만으로 Nova의 domain aggregate usage enforcement를 증명할 수 없다.
- Sources: https://docs.openstack.org/nova/2025.2/admin/unified-limits.html ; https://raw.githubusercontent.com/openstack/oslo.limit/stable/2025.2/oslo_limit/limit.py (229–246); https://docs.openstack.org/keystone/2025.2/admin/unified-limits.html . Current master도 조사 당시 해당 enforcer는 미구현이었다.
- 자동 flavor reconciling owner와 standard profile contract는 기존 repository에 없다. 기존 manual CRUD와 read-only capacity projector를 재사용하되 scope/권한/사용량/예약을 혼동하지 않는다.
- Native source integration 유지보수 방향을 사용자에게 확인 중이다. 구현·schema 변경·운영 변경·runtime smoke는 아직 수행하지 않았다.
