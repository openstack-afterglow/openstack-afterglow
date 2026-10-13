## 1. 문서 인계 — 이번 작업

- [x] [독립 한국어 GPU 인수인계 문서](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/drover-gpu-api-dashboard-handoff.md)에 기존 API 예제, normalized selector/resources/runtime/toleration, image/taint·CSI 계약, PVC timing 및 소유권/opt-out/기본값을 기록한다.
- [x] 현재 UI components·types·BFF/native 계약을 저장소 소스 링크로 연결하고 API capability와 현재 UI 한계를 구분한다.
- [x] [k3s API reference](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/k3s.md)와 [architecture](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/ARCHITECTURE.md)에 API 계약·새 v0.4.14 운영 receipt와 별도 UI pending 상태를 추가한다.
- [x] frontend/backend/runtime/version/config 변경 없이 proposal/tasks를 작성하고 후속 UI 작업을 pending·unarchived로 유지한다. 문서 agent는 중간 gate/commit을 생략하고 통합 소유자가 최종 gate·source review·dev-only 발행을 담당한다.
- [x] validator가 요구하는 [delta spec](specs/gpu-nodegroup-api-dashboard-handoff/spec.md)을 ADDED Requirements/Scenario 형식으로 작성하고 인계·후속 UI 계약만 규정한다. 누락 metadata, opt-out, 권한, PVC timing, 완료 오인과 기존 window/guard 경계를 포함하며 UI implementation checklist는 완료로 바꾸지 않는다.

## 2. Drover release / 실제 운영 receipts — 완료

- [x] v0.4.14 `f7daeec609f90437c5da1305ae6d5a17d772f9b4`, exact-SHA dev/tag CI와 immutable wheel/image digest를 [인계 receipt](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/drover-gpu-api-dashboard-handoff.md#6-v0414-실제-운영-receipt)에 연결했다. 과거 v0.4.13 결과를 전용하지 않았다.
- [x] 실제 3-controller rollout·GPU Operation SUCCEEDED/Ready/allocatable1/nvidia-smi, Cinder RWO/Manila NFS RWX mount/I/O, storage 정리 후 기존 guard/window의 자연1→0 SUCCEEDED/VM·Node·volume404와 최종 fixture/ACL 정리·보존을 각각 기록했다. 동시 OpenSearch/LB census 중단과 c3 격리 재개, native provider NIC 전제조건도 성공 범위와 분리했다.

## 3. 별도 대시보드 구현 — Afterglow 대시보드 소유자, 전부 pending

- [ ] 현재 `/api/v1/flavors`의 검증된 metadata와 normalized GPU 타입 표시 경로를 확정한다. Drover metadata 수정이 Afterglow catalog까지 바꾼다고 가정하지 않고, 새 API/schema가 필요하면 별도 승인 범위를 확정한다.
- [ ] 기존 nodegroup 생성/설정 UI에 `image_id`, 허용 labels, explicit `nvidia.com/gpu=true:NoSchedule` taints 및 GPU dedicated preset을 노출한다. VM image와 CUDA container image를 구분하고 예약 GPU label override·기존 Node 자동 retrofit을 약속하지 않는다.
- [ ] cluster/group Stampede boolean 선택·명시적 false opt-out, node_count/min/max와 기본 agent/server 그룹 제외를 유지한다. GPU preset으로 기존 선택값이나 자원을 backfill하지 않는다.
- [ ] flavor normalized GPU 타입과 count, 실제 allocatable/free capacity를 구별해 표시한다. metadata 누락·오류·혼합 타입에 임의의 GPU label/용량이나 CPU fallback을 합성하지 않는다.
- [ ] GPU manifest helper에 `accelerator`, `nvidia.com/gpu` requests/limits, `runtimeClassName:nvidia`, matching toleration을 함께 제공한다. 인가된 kubeconfig/표준 Kubernetes API 제출만 안내하며 Drover Pod/Deployment/PVC 생성 endpoint를 만들지 않는다.
- [ ] 실제 CSI node readiness와 durable Operation 상태/오류를 기존 operation ID·sequence 조회로 연결한다. 접수·Node Ready·Redis event를 GPU 실행/볼륨 mount 성공으로 승격하지 않는다.
- [ ] Pending PVC는 autoscale 수요가 아님을 표시하고 PVC-free/명시 capacity bootstrap → GPU Ready/allocatable → Cinder RWO/Manila NFS RWX mount → workload/PVC 정리 → 600s idle/300s cooldown 및 기존 drain guard 기반 scale-in 순서를 안내한다.
- [ ] 기존 project/resource ownership·inventory/cluster/workload permission·credential grade를 유지한다. quota/auth/KEK force/reset이나 자동 admission mutation·all-taint toleration은 추가하지 않는다.
- [ ] 별도 UI 변경의 정확한 source와 검증/배포 증거를 해당 소유자가 기록한다. 이 문서 인계 작업에서는 실행하지 않는다.

## 4. 종료 정책

**이 change는 의도적으로 archive하지 않는다.** 부모가 Drover release receipts를 채워도 위 별도 대시보드 작업이 완료된 것은 아니다. 후속 소유자의 구현·검증·배포와 열려 있는 metadata 계약 질문이 해결될 때까지 체크리스트를 pending으로 유지한다.
