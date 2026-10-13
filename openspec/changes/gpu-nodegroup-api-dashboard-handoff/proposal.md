## Why

Drover v0.4.14는 기존 cluster/nodegroup API로 GPU 전용 worker를 구성하고 flavor metadata 실패를 CPU로 숨기지 않으며 GPU NoSchedule taint를 CSI node plugin이 좁게 허용한다. 2026-10-13 immutable 발행·3-controller 배포와 새 native GPU 실행·Cinder RWO/Manila NFS RWX I/O·자연 축소·정리/보존이 별도 receipts로 확인됐다. Afterglow의 현재 생성 화면은 flavor·Stampede·min/max를 전송하지만 GPU image/labels/taints를 노출하지 않아 API capability와 UI 사이의 인계가 필요하다.

**대시보드 구현은 별도 소유자의 별도 작업**이다. 이 change는 문서 인계·실제 Drover receipts와 pending UI 범위를 추적하며 UI 완료나 Afterglow runtime 배포를 선언하지 않는다. 독립 한국어 [인수인계 문서](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/drover-gpu-api-dashboard-handoff.md)를 기준으로 후속 작업을 수행한다.

## What Changes

### 이번 문서 인계

- 기존 native `POST /v1/clusters/async`, `POST /v1/clusters/{cluster_id}/nodegroups`와 Afterglow BFF 경로, 명시적 GPU image/taint 예제 및 표준 Kubernetes GPU manifest를 독립 문서로 전달한다. 새 native API/schema나 Drover Pod/Deployment/PVC create endpoint를 추가하지 않는다.
- normalized `accelerator: RTX3060LHR`, `nvidia.com/gpu` requests/limits, `runtimeClassName: nvidia`, matching toleration을 함께 설명한다. 자동 GPU taint·admission mutation·기존 자원 backfill을 약속하지 않는다.
- PVC Pending은 Stampede 수요가 아니라는 timing caveat, PVC-free 또는 명시적 capacity bootstrap, GPU Ready/allocatable 이후 Cinder RWO·Manila NFS RWX mount, workload/PVC 정리 후 기존 idle/cooldown/drain guard 기반 축소를 설명한다.
- source/test/live 증거를 분리하고 v0.4.14 release/CI/운영 receipts를 새 실제 결과로 기록한다. initial SSE 관측 오류를 create 재전송으로 보정하지 않았으며 native provider NIC와 기존 node-interface VM 범위를 명시한다.
- [k3s reference](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/k3s.md)와 [architecture](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/ARCHITECTURE.md)의 GPU 경계에 좁은 안내 링크를 추가한다.

### 별도 대시보드 소유자의 후속 범위 — 미구현

- nodegroup image/허용 labels/explicit taints와 GPU dedicated preset, boolean opt-out·min/max·기본 agent/server 제외를 노출한다.
- 신뢰 가능한 기존 flavor metadata의 normalized GPU 타입을 표시한다. 누락 metadata를 CPU로, 설정량을 allocatable로 합성하지 않는다.
- GPU YAML helper와 caller-authorized Kubernetes API 제출 안내, CSI readiness와 durable Operation 상태/오류, PVC 준비·정리 순서를 제공한다.
- 기존 project/resource ownership·permissions·kubeconfig grade를 유지한다. quota/auth/KEK force/reset은 범위 밖이다.

## Capabilities

### New Capabilities

- `gpu-nodegroup-api-dashboard-handoff`: [delta spec](specs/gpu-nodegroup-api-dashboard-handoff/spec.md)의 versioned API 인계·소스/운영 구분과 별도 대시보드 configuration/metadata/manifest/CSI 완료 계약. 후속 UI 요구를 규정하며 이번 문서 change에서 runtime 기능을 구현하지 않는다.

### Modified Capabilities

- 후속 대시보드 작업이 기존 nodegroup 필드와 workload 안내를 UI에 노출할 예정이다. 이 문서 change에서 frontend/backend 구현은 변경하지 않는다.

## Impact

이번 편집은 이 proposal, [tasks](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/openspec/changes/gpu-nodegroup-api-dashboard-handoff/tasks.md), [delta spec](specs/gpu-nodegroup-api-dashboard-handoff/spec.md), 독립 인수인계 문서, k3s API GPU 경계와 architecture notice로 한정한다. Afterglow runtime/frontend/package/version/config/deploy 변경은 없다. 통합 소유자는 repository gate와 architecture review/stamp 후 문서만 dev에 발행하며 별도 UI 검증으로 승격하지 않는다.

후속 변경 후보는 [K3sNodegroupCreateModal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupCreateModal.svelte), [K3sNodegroupEditModal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupEditModal.svelte), [K3s types](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/types/k3s.ts), [K3sNodegroupCard](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupCard.svelte), [K3sStampedeTab](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/k3s/K3sStampedeTab.svelte), [detail controller](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/stores/k3sClusterDetailContr…

## Open Contract Question

현재 UI의 `/api/v1/flavors`는 Afterglow [nova.list_flavors](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/services/nova.py)를 사용한다. Drover v0.4.14의 metadata 보강과 별개이며 `K3sFlavor`에는 normalized GPU 타입 필드가 없다. 후속 소유자는 검증된 기존 metadata 경로와 같은 정규화 계약을 재사용할 표시 방법을 확정해야 한다. 이 change는 새 응답 필드를 가정하거나 backend 변경을 승인하지 않는다.

## Lifecycle

Drover release/live receipts는 통합 소유자가 기록했다. 별도 대시보드 구현·검증·배포 checklist와 metadata 데이터 경로 질문은 미완료다. **다운스트림 작업이 남아 있으므로 change를 의도적으로 unarchived 상태로 둔다.**
