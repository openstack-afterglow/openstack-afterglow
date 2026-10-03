## Why

VM 생성 wizard가 같은 호스트 용량을 확인하지 못한 일반(CPU) flavor를 `생성 가능`으로 보여 주었다. 로컬 DMSLAB에서는 `nova.default_compute_availability_zone`과 `cinder.default_volume_availability_zone` 정책이 비어 있었다. 그래서 AZ를 생략한 `capacity=create` 목록이 Placement 조회 전에 실패했고(`ResourcePolicyValidationError`), CPU flavor 21개가 모두 `호스트 용량 미확인 · Nova 최종 확인`으로 선택 가능했다. 그중 `cpu.16c_128g`(131,072 MB)는 13개 compute 어디에도 배치할 수 없다. MEMORY_MB `max_unit` 최대값은 128,687 MB, 최대 잔여는 103,509 MB다. 같은 정책 누락 때문에 생성 사전검증도 503으로 거부하므로 목록과 제출이 서로 달랐다.

2026-10-02 사용자는 Placement·운영자 장애를 포함해 용량을 확인하지 못한 모든 flavor를 차단하기로 결정했다. 기존 설계는 미확인일 때 GPU flavor만 막았다.

## What Changes

- `capacity=create` 목록과 단일 VM 생성 admission에서 `capacity.status == "unavailable"`이면 GPU 여부와 무관하게 `host_capacity_unavailable` blocker를 붙인다. 목록에서는 선택할 수 없다. 제출은 GPU 단기 예약, Cinder/Nova mutation, SSE handshake 전에 503으로 거부한다. 기본 AZ 정책 조회 실패, 운영자 인증·Placement 장애·시간 초과, 표현할 수 없는 flavor 제약을 모두 포함한다.
- 확인된 부족(`insufficient`)은 기존처럼 409와 `host_capacity_insufficient`다. 호스트 합계가 맞는 `available` + `numa_unverified`는 미확인 capacity가 아니므로 계속 허용한다.
- VM wizard의 `flavorCreateBlock`은 blocker가 없어도 capacity snapshot이 없거나 `unavailable`이면 생성 불가(`unchecked`)로 판정한다. 미확인 허용 문구(`호스트 용량 미확인 · Nova 최종 확인`, `생성은 허용되며 …`)를 제거하고 `호스트 용량 확인 불가`로 표시한다.
- 기본 `/api/v1/flavors`(K3s·Drover), resize 증분, batch(`count>1`)는 기존 쿼터 계약을 유지한다.
- 로컬 DMSLAB 배치 정책 두 개는 사용자 승인에 따라 유일한 Nova/Cinder AZ인 `nova`로 저장했다. 운영 환경 설정은 변경하지 않는다.

## Capabilities

### New Capabilities

- 없음

### Modified Capabilities

- VM create flavor eligibility·admission: 미확인 host capacity를 flavor 종류와 무관하게 fail-closed로 처리한다.
- VM wizard flavor 선택: 미확인 용량을 선택·진행할 수 있던 경로를 제거한다.

## Impact

- Backend: `backend/app/services/flavor_eligibility.py`, `backend/tests/test_flavor_capacity_admission.py`.
- Frontend: `frontend/src/lib/types/flavor.ts`, `frontend/src/lib/components/wizard/SelectFlavor.svelte`, `frontend/src/lib/components/wizard/__tests__/SelectFlavor.test.ts`.
- Docs: `docs/api/flavors.md`, `docs/api/instances.md`, `ARCHITECTURE.md`, `DESIGN.md`, `CHANGELOG.md`.
- 운영 영향: 운영자 자격증명·Nova/Placement 장애나 AZ 정책 누락 동안에는 Afterglow wizard/API로 어떤 VM도 생성할 수 없다. 사용자가 선택한 tradeoff다. CLI와 직접 Nova API 생성 경로는 바꾸지 않는다.
