## Why

VM 생성의 프로젝트 쿼터가 남아 있어도 요청한 GPU를 가진 동일 compute 호스트에 CPU·RAM까지 남아 있지 않으면 Nova 배치가 실패한다. 현재 `flavor_eligibility`는 프로젝트 instances/cores/ram 및 Afterglow GPU 쿼터만 검사하고, wizard의 GPU 배너는 전체 GPU 합계만 별도로 조회한다. RTX 3090 Ti 호스트의 남은 CPU·RAM과 GPU의 교집합을 선택지에 반영해야 한다.

## What Changes

- 기존 flavor의 고정 vCPU/RAM/GPU 규격은 유지하고, 생성용 목록에 호스트 용량 사전검증을 추가한다. 임시 flavor 생성·기존 flavor 수정·Nova 자원 예약이나 운영 설정 변경은 하지 않는다.
- 기존 프로젝트 쿼터와 별도로 운영자 연결의 Nova/Placement 읽기 전용 조회로 GPU alias→PCI resource class→provider tree/root compute 호스트를 매핑한다. CPU·RAM·GPU가 같은 eligible compute에 함께 존재하는지 확인한다. disabled/down host, availability zone, flavor의 Placement resources/traits 및 aggregate 제약을 반영한다.
- Placement의 inventory/usage, reserved/allocation_ratio 및 allocation 단위 제약을 사용한다. vCPU logical thread를 물리 코어로 간주하거나 임의로 2로 나누지 않는다. dedicated CPU의 PCPU와 일반 VCPU를 구분한다.
- 조회 오류·권한 부족·지원되지 않는/불명확한 매핑은 확인 불가(`unavailable`)로 표시한다. GPU flavor는 이 상태에서 선택/생성을 차단하고 일반 flavor는 경고 후 Nova에 맡긴다(아래 Design Boundaries). 단일 NUMA 셀 요청은 호스트 합계가 셀 배치의 필요조건이므로 합계로 판정하고 `numa_unverified`로 공개한다. tenant 응답에는 host 이름·provider UUID·다른 프로젝트/VM 식별자를 노출하지 않는다.
- 생성용 `eligibility.capacity`는 status, checked_at, candidate_hosts, cpu_resource_class 및 한 실제 후보 호스트의 remaining_vcpus/remaining_ram_mb 쌍을 제공한다. 서로 다른 호스트의 CPU 최대값과 RAM 최대값을 합쳐 가능한 규격처럼 표시하지 않는다.
- 사용자 및 관리자 VM 생성 목록·sync/SSE 제출에 같은 검사를 적용한다. 조회의 snapshot은 예약/생성 보장이 아니며 제출 전에 uncached 재검증하고 최종 atomic allocation은 Nova scheduler에 맡긴다. 기존 resize/K3s 증분 쿼터 계약에는 create-only 용량 검사를 적용하지 않는다.
- wizard는 생성 가능한 목록과 제한/미확인 사유를 구분하고 호스트 capacity·project quota를 별도로 표시한다. 해당 단계에 있는 동안 기존 refresh 패턴으로 갱신하고 수동 새로고침도 제공한다. 조회 중/실패/갱신 후 선택 불가인 flavor로 진행·제출하지 않으며 프로젝트 전환/폐기 후 늦은 응답은 기존 fence로 무시한다.

## Capabilities

### New Capabilities

- 같은 eligible GPU 호스트의 CPU·RAM 용량을 반영한 VM create flavor 사전검증 및 동적 선택지.

### Modified Capabilities

- 생성용 flavor eligibility, sync/SSE admission 및 VM wizard availability/refresh 표시. 프로젝트별 quota, 인가, GPU quota reservation, rollback 및 기존 flavor 정의는 유지한다.

## Impact

- Backend: `app/services/flavor_eligibility.py`, 별도 FastAPI-free host capacity 서비스, `app/models/compute.py`, compute flavor/instance 및 admin instance routes, 관련 pytest.
- Frontend: `types/flavor.ts`, `stores/vmCreateStore.svelte.ts`, `components/VmCreatePanel.svelte`, `components/wizard/SelectFlavor.svelte`, 관련 behavior tests.
- Docs: root `ARCHITECTURE.md`, `DESIGN.md`, `CHANGELOG.md`, `docs/api/instances.md` 및 flavor API 문서.
- 검증: 실제 SDK/API 및 Chromium smoke와 회귀. Synthetic cloud origin은 admission/선택의 증거이며 production capacity/실제 VM scheduling 성공을 입증하지 않는다. 운영자 자격/권한이 불가능하면 그 한계를 명시한다.

## Design Boundaries

- 이 검사는 자원 용량과 확인 가능한 flavor/AZ/trait/aggregate/`cpu_info` capability 제약의 사전검증이다. 이미지 정책, PCI NUMA affinity, scheduler weights, server groups 등 Nova 전체 scheduler를 복제하지 않는다. UI는 “즉시 생성 보장”이라고 표시하지 않는다.
- NUMA: Placement는 셀별 여유를 노출하지 않지만 모든 생성은 Placement 호스트 할당을 먼저 통과한다. 따라서 `hw:numa_nodes=1`, `hw:mem_page_size=small|any`, dedicated CPU(암묵적 단일 셀)는 호스트 합계 부족이면 `insufficient`로 확정 차단한다. 합계가 충분하면 `available`+`numa_unverified`로 허용하고 셀은 Nova `NUMATopologyFilter`에 맡긴다. 운영 flavor 76/79개가 이 정책을 사용하므로 전부 차단하면 생성 자체가 불가능해진다. 셀 구조가 필요한 `hw:numa_nodes>1`, hugepage pool이 필요한 `large`/명시 page size, mixed CPU는 경계를 정할 수 없어 `unavailable`로 둔다.
- Opt-in과 장애 범위: capacity는 VM wizard의 `capacity=create` 목록과 단일 VM 생성 admission에만 적용한다. 기본 flavor 목록을 쓰는 K3s·Drover와 resize, batch(`count>1`)는 쿼터 계약을 유지한다. 확인된 부족은 모든 flavor를 막는다. 미확인은 이미 운영자 권한(GPU 쿼터)에 의존하는 GPU flavor만 막는다. 운영자 자격증명·Placement 장애가 일반 VM 생성 전체로 번지지 않게 하기 위해서다.
- 비용: 운영자 세션을 재사용한다. 요청 timeout은 5초로 두고 재시도하지 않으며, 평가 deadline은 15초다. Placement는 shape당 1회 조회한다. 목록은 10초 single-flight snapshot을 쓰고 admission은 fresh로 읽는다. 표시값은 VM 하나의 한도(`min(잔여, max_unit)`)다.
- 물리 코어 보장은 Nova CPU pinning/thread policy 및 compute CPU set 구성의 별도 운영 결정이며 이번 변경은 그 정책을 임의로 변경하지 않는다.
- 근거: https://docs.openstack.org/api-ref/placement/#list-allocation-candidates , https://docs.openstack.org/nova/latest/admin/pci-passthrough.html , https://docs.openstack.org/nova/latest/admin/cpu-topologies.html
