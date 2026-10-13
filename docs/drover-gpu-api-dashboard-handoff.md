# Drover GPU API → Afterglow 대시보드 인수인계

## 상태와 범위

**상태: Drover v0.4.14 발행·3-controller 배포·새 GPU/CSI/자연 축소 인수시험 완료 / 대시보드 구현 미착수.** 발행 소스는 `f7daeec609f90437c5da1305ae6d5a17d772f9b4`이며 아래 §6은 2026-10-13의 새 native receipts다. v0.4.13 과거 GPU 실행이나 Afterglow v1.30.15의 기본 Stampede 스위치 증거를 v0.4.14의 격리·mount 증거로 전용하지 않는다. Afterglow runtime/frontend/version은 이번 인계에서 바꾸지 않는다.

이 문서는 API 기능을 대시보드 소유자에게 알리는 독립 인계 문서다. **대시보드 변경은 별도 작업**이며 이번 문서 변경이나 Drover 런타임 작업에 포함되지 않는다. [OpenSpec proposal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/openspec/changes/gpu-nodegroup-api-dashboard-handoff/proposal.md)과 [미완료 tasks](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/openspec/changes/gpu-nodegroup-api-dashboard-handoff/tasks.md)에서 추적한다. 후속 UI가 남아 있으므로 change를 의도적으로 archive하지 않는다.

| 증거 층 | 현재 기록 | 갱신 책임 |
|---|---|---|
| Source | v0.4.14 `f7daeec609f90437c5da1305ae6d5a17d772f9b4`; 초기 agent metadata를 control-plane 자원 생성 전에 preflight한다. 기존 API/schema·권한 경계는 유지한다. | Drover 소유자 |
| Test / CI | 최종 local service 1430 passed/3 skipped, SDK 114 passed, Ruff 통과. exact-SHA [dev CI](https://github.com/openstack-afterglow/drover/actions/runs/38426713616)와 [tag CI](https://github.com/openstack-afterglow/drover/actions/runs/38427233796) 통과. API/Worker amd64·arm64 실제 로컬 이미지와 발행 amd64 immutable 이미지에서 SDK HTTP·CSI scheduling smoke를 실행했다. 합성 Nova loopback이며 native GPU 운영 증거는 아니다. | 부모 통합 소유자 |
| Release / live | [v0.4.14 wheel release](https://github.com/openstack-afterglow/drover/releases/tag/v0.4.14). API index `sha256:3765274889e8615101032701cead27276992cadd5bb318c2d8cd123e1860f194`, Worker index `sha256:b338a56df50151cf556c5b2cd851b799bdf47d59eb5b124394435d407494b003`. 3-controller parity/readiness, GPU 실행·native CSI mount·자연 축소·정리/보존은 §6 및 [Drover 운영 기록](https://github.com/openstack-afterglow/drover/blob/dev/docs/release-0.4.0.md#live-0414-gpu-csi-and-natural-scale-in-acceptance) 참조. | 부모 통합 소유자 |
| Dashboard | 현재 소스의 제한을 아래에 명시한다. 후속 UI 구현·검증·배포는 모두 pending이다. | 별도 Afterglow 대시보드 소유자 |

Drover 소스 링크는 immutable `v0.4.14` 태그, Afterglow 소스·인계 링크는 `dev` 저장소 경로다. native 운영·후속 UI receipts는 아래 계약과 분리해 기록한다. 대시보드 runtime/frontend 파일은 이번 인계에서 수정하지 않는다.

## 1. 기존 API와 책임 경계

- 클러스터 생성: native `POST /v1/clusters/async` → 브라우저/BFF `POST /api/v1/k3s/clusters/async`. 기존 응답은 **SSE progress stream**이며 일반 JSON/즉시 완료 응답이 아니다. stream의 `cluster_id`/`operation_id`를 보존하고 내구성 상태를 조회한다. stream 수신 실패만으로 create POST를 재전송하지 않는다.
- GPU 그룹 생성: native `POST /v1/clusters/{cluster_id}/nodegroups` → BFF `POST /api/v1/k3s/clusters/{cluster_id}/nodegroups`.
- 그룹 조회·수정: 같은 경로의 `GET`, 단건 `GET`·`PATCH`를 사용한다. 새 GPU 전용 endpoint를 추가하지 않는다.
- Stampede 상태: native `GET /v1/clusters/{cluster_id}/stampede` 및 `/stampede/events`; BFF에서는 `/api/v1/k3s` 접두사를 사용한다.
- 내구성 작업: native `GET /v1/operations/{operation_id}` 및 `/events?since_sequence=0`; BFF는 `GET /api/v1/k3s/operations/{operation_id}` 및 `/events?since_sequence=0`이다. SSE의 operation ID 또는 Stampede status의 `last_operation_id`/`active_operation_ids`를 사용한다. nodegroup201 응답 자체가 새 operation ID를 반환한다고 가정하거나 없는 list endpoint/ID를 만들지 않는다. 접수와 실제 완료는 구별한다.
- Drover의 Pod/Deployment/PVC **생성 API는 없다**. 기존 workload 조회·restart·scale API를 생성 API로 해석하지 않는다. GPU manifest는 호출자가 인가받은 kubeconfig로 **표준 Kubernetes API**에 제출한다. 대시보드 후속 작업은 YAML 표시·다운로드와 제출 안내를 제공할 수 있지만 미구현 Drover create endpoint를 제안하지 않는다.

계약 소스: [native API reference](https://github.com/openstack-afterglow/drover/blob/v0.4.14/docs/drover-api-v1-reference.md), [nodegroups API](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/api/nodegroups.py), [request schemas](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/models/schemas.py), [operations API](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/api/operations.py), [Afterglow proxy](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/api/drover/proxy.py), [gateway authorization](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/services/drover_authorization.py).

### 기본값·opt-out·소유권

- v0.4.13부터 새 클러스터 생성 요청의 `stampede_enabled` 생략은 `true`다. v0.4.14에서도 유지한다. UI는 선택값을 항상 JSON boolean으로 보내며 사용자가 끄면 명시적 `false`를 유지한다.
- 명시적 `flavor_id`를 가진 새 agent 그룹도 Stampede 생략 시 활성화된다. flavor 없는 placeholder는 자동 확장 대상이 아니다. 초기 `default-agent` 및 server 그룹은 `stampede_enabled=false`이며 클러스터 기본 켜짐이 모든 그룹의 자동 축소를 뜻하지 않는다.
- 기존 명시적 `stampede_enabled:false`는 opt-out이다. 기존 클러스터·그룹·Node를 자동 retrofit/backfill하지 않는다. 자동 GPU taint도 없다.
- 그룹 생성은 `role: agent`를 사용한다. 커스텀 server 그룹은 지원되지 않는다. 생성 본문은 `min_size <= node_count <= max_size`를 만족해야 한다. `node_count`의 schema 범위는 0–20이며 GPU 전용 예제는 0/0/1로 시작한다.
- Afterglow는 인증·프로젝트 범위 전달과 UI를 소유한다. Drover는 그룹/작업 상태·planner·VM provisioning·GPU label 및 CSI template을 소유한다. GPU admission은 Afterglow의 기존 target-project quota 경계이며 Nova scheduling 예약이나 GPU 성공 보장이 아니다.
- 기존 권한을 유지한다: inventory 조회, `drover-clusters_editor`의 생성/수정, `drover-clusters_admin`의 삭제를 혼합하지 않는다. 클러스터 편집 권한만으로 Kubernetes workload 쓰기나 관리자 kubeconfig 권한을 만들지 않는다. manifest 제출은 실제 workload 쓰기 권한과 native가 발급한 credential grade/RBAC를 따른다.
- 오래된 클러스터의 resource authority 부재·회수는 기존 재인가 흐름으로 처리한다. 서비스/admin identity로 우회하거나 quota·auth·KEK force/reset을 추가하지 않는다.

## 2. v0.4.14 GPU 계약

### Flavor metadata와 정규화 label

Drover의 [nova.list_flavors](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/services/nova.py)는 목록 extra specs가 비어 있으면 `compute.fetch_flavor_extra_specs`로 명시 조회한다. 조회 오류를 CPU `{}`로 숨기지 않고 전파한다. 성공한 빈 specs는 정상 CPU flavor다. 이 계약은 Drover flavor catalog, 초기 agent, 수동 nodegroup, Stampede planner에 적용된다.

GPU 타입은 flavor의 GPU PCI alias를 대문자 영숫자로 정규화한다. 예를 들어 `RTX-3060-LHR:1,GA106-audio:1`의 GPU 타입은 **`RTX3060LHR`**다. audio/NIC 등 비-GPU function은 제외한다. 서로 다른 GPU 타입이 섞이거나 유효한 Kubernetes label 값이 되지 않으면 임의의 타입을 선택하지 않는다. flavor 이름이나 UI 추정값으로 실제 Node label·장치 수·가용 용량을 합성하지 않는다.

| 등록 label | 의미 |
|---|---|
| `accelerator=RTX3060LHR` | GPU Pod의 타입 selector. 사용자 `labels.accelerator` override는 기존 계약상 유지되므로 helper는 실제 설정과 일치해야 한다. 기본 GPU preset은 이 키를 임의로 덮어쓰지 않는다. |
| `afterglow.io/gpu-type=RTX3060LHR` | flavor-derived 예약 label. 사용자 입력으로 덮어쓰지 않는다. |
| `afterglow.io/gpu=true` | GPU worker 표시. CPU Node에 합성하지 않는다. |

세부 정규화·예약 label 규칙은 [native GPU scheduling reference](https://github.com/openstack-afterglow/drover/blob/v0.4.14/docs/drover-api-v1-reference.md#gpu-타입-기반-스케줄링)와 [Afterglow quota normalization](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/services/gpu_quota.py)을 따른다. GPU 개수와 정규화 타입은 서로 다른 값이다. label은 스케줄링 조건이며 장치 할당을 대신하지 않는다.

### GPU image·taint·CSI

- `image_id`는 프로젝트에 허용된 실제 VM 이미지 ID다. NVIDIA 드라이버·container runtime 및 `nvidia` RuntimeClass/device plugin과 호환되는 이미지를 선택한다. 아래 CUDA **컨테이너 이미지**와 VM `image_id`를 혼동하지 않는다. flavor/image 가시성은 기존 서버 검증에 맡긴다.
- GPU 전용 그룹은 기존 `taints` 필드에 `nvidia.com/gpu=true:NoSchedule`을 **명시**한다. GPU flavor 선택만으로 taint가 붙지 않는다. taint 없는 GPU worker에는 일반 Pod도 배치될 수 있어 storage/protected workload가 축소를 막을 수 있다. CPU/control-plane에 시스템 workload 용량을 확보한다.
- v0.4.14 대상 [Cinder node template](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/templates/k3s_plugins/cinder_csi/manifests.yaml.j2), [Manila node template](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/templates/k3s_plugins/manila_csi/manifests.yaml.j2), [NFS node template](https://github.com/openstack-afterglow/drover/blob/v0.4.14/drover/templates/k3s_plugins/manila_csi/nfs_csi.yaml.j2)은 node DaemonSet에만 `key: nvidia.com/gpu`, `operator: Exists`, `effect: NoSchedule` toleration을 추가하는 계약이다. 모든 taint 허용이나 `NoExecute` 허용, CSI controller/credential 변경은 아니다.
- 새 template은 기존 클러스터의 CSI 설치를 자동 갱신하지 않는다. 이전 버전으로 만들어진 guest에 v0.4.14 template이 적용되었다고 가정하지 않는다. GPU taint 사용 전 실제 node plugin의 toleration과 GPU Node의 plugin Ready 상태를 확인한다.
- GPU Pod에도 matching toleration을 직접 넣는다. `ExtendedResourceToleration` 또는 자동 GPU admission mutation을 구성한 계약이 아니므로 `resources`만으로 toleration이 생긴다고 안내하지 않는다.

## 3. API 사용 예제

아래는 **요청 예제**이며 실행 결과나 배포 receipt가 아니다. 프로젝트에 허용된 실제 ID와 인증 값을 사용한다. 브라우저는 기존 Afterglow Bearer 인증·`X-Project-Id` 경로를 사용하며 native 직접 호출의 인증/위임을 우회하지 않는다.

### 클러스터 생성과 기본값

관리자 기본 정책이 구성된 프로젝트에서 native `POST /v1/clusters/async` / BFF `POST /api/v1/k3s/clusters/async`에 다음 본문을 보낸다:

```json
{
  "name": "gpu-lab",
  "agent_count": 1,
  "os_type": "ubuntu"
}
```

`stampede_enabled`를 생략했으므로 클러스터 Stampede는 켜진다. 처음 만든 기본 agent는 자동 축소 대상이 아니다. API opt-out은 같은 본문에 `"stampede_enabled": false`를 넣는다. 현재 UI는 생략 대신 사용자의 boolean 선택을 전송한다. 초기 GPU agent를 고르더라도 이미지·taint 전용 구성을 대신하지 않으므로 전용 GPU 그룹은 다음 기존 nodegroup API를 사용한다.

### 0에서 시작하는 GPU 전용 agent 그룹

native `POST /v1/clusters/{cluster_id}/nodegroups`와 대응되는 BFF 호출:

```bash
curl --fail-with-body -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "X-Project-Id: $PROJECT" \
  -H 'Content-Type: application/json' \
  "https://afterglow.example.com/api/v1/k3s/clusters/$CLUSTER_ID/nodegroups" \
  --data '{
    "name": "gpu-workers",
    "role": "agent",
    "node_count": 0,
    "min_size": 0,
    "max_size": 1,
    "flavor_id": "<gpu-flavor-id>",
    "image_id": "<driver-compatible-image-id>",
    "stampede_enabled": true,
    "taints": [{"key": "nvidia.com/gpu", "value": "true", "effect": "NoSchedule"}]
  }'
```

ID placeholder는 실제 허용된 GPU flavor·VM 이미지 ID로 교체한다. `labels`는 기존 선택 필드지만 기본 preset은 정규화 GPU label을 Drover에 맡기므로 위 본문에서 생략한다. 예약 label을 입력받지 않는다. 이 요청의 `201`은 구성/요청 접수이며 GPU 실행 완료가 아니다.

자동 증설을 끄려면 `stampede_enabled:false`를 명시한다. 0개 그룹에서 끄면 Pod만으로 worker가 생기지 않는다. 수동 bootstrap은 기존 native/BFF 단건 `PATCH`에 `{"node_count":1,"min_size":1,"max_size":1}`을 보내는 방식으로 준비할 수 있다. 이는 별도 실행 선택이며 idle scale-in을 원하면 workload/storage 정리 후 `min_size`를 0으로 돌려야 한다.

### PVC 없는 GPU manifest helper의 기준

다음 YAML은 인가된 kubeconfig로 Kubernetes에 제출할 예제다. 실제 flavor 정규화 타입이 `RTX3060LHR`이고 해당 클러스터에 `nvidia` RuntimeClass, 호환 runtime, NVIDIA device plugin이 있는 것이 전제다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: gpu-type-check
  namespace: default
spec:
  runtimeClassName: nvidia
  restartPolicy: Never
  nodeSelector:
    accelerator: RTX3060LHR
  tolerations:
    - key: nvidia.com/gpu
      operator: Equal
      value: "true"
      effect: NoSchedule
  containers:
    - name: cuda
      image: nvcr.io/nvidia/cuda:12.4.1-base-ubuntu22.04
      command:
        - sh
        - -c
        - 'set -eu; nvidia-smi --query-gpu=name,uuid,driver_version --format=csv,noheader; echo GPU_EXECUTION_OK; sleep 3600'
      resources:
        requests:
          nvidia.com/gpu: "1"
        limits:
          nvidia.com/gpu: "1"
```

`metadata.labels`만으로 GPU를 요청하지 않는다. `nodeSelector` + request/limit + runtimeClass + toleration의 네 요소를 함께 제공한다. 다른 타입이거나 toleration이 맞지 않으면 그 이유를 보여 주며 CPU/다른 GPU로 fallback하지 않는다. namespace와 credential grade는 호출자의 실제 권한을 따른다.

YAML을 `/tmp/gpu-type-check.yaml`에 저장하고, workload 쓰기 권한이 있는 사용자의 발급된 kubeconfig를 `/tmp/gpu-handoff-kubeconfig.yaml`에 보관한 경우의 제출/관찰 명령:

```bash
kubectl --kubeconfig=/tmp/gpu-handoff-kubeconfig.yaml apply -f /tmp/gpu-type-check.yaml
kubectl --kubeconfig=/tmp/gpu-handoff-kubeconfig.yaml get nodes -L accelerator,afterglow.io/gpu-type
kubectl --kubeconfig=/tmp/gpu-handoff-kubeconfig.yaml get nodes -o 'custom-columns=NAME:.metadata.name,GPU:.status.allocatable.nvidia\.com/gpu'
kubectl --kubeconfig=/tmp/gpu-handoff-kubeconfig.yaml -n default describe pod gpu-type-check
kubectl --kubeconfig=/tmp/gpu-handoff-kubeconfig.yaml -n default logs gpu-type-check
```

이 CLI 예시는 호출자를 위한 제출 안내다. 이번 native 인수시험은 같은 selector/resources/runtime/toleration 요소의 manifest를 인가된 Kubernetes HTTP API에 제출해 §6의 GPU 실행을 확인했다. CLI 예시를 직접 실행한 증거나 후속 UI 검증으로 바꾸지 않는다. Node Ready나 GPU badge만으로 성공을 판정하지 않으며 kubeconfig/token/secret은 문서·receipt·공개 로그에 붙이지 않는다.

## 4. CSI/PVC 순서와 완료 판정

**Pending PVC 또는 unbound storage 때문에 Pending인 Pod는 Stampede 증설 수요가 아니다.** GPU+PVC Pod를 먼저 만들고 0개 그룹이 자동으로 생길 것이라고 안내하면 순환 대기가 생길 수 있다.

1. 위의 **PVC 없는 GPU Pod** 또는 명시적 `node_count`/`min_size`로 먼저 GPU worker를 준비한다.
2. 해당 작업의 durable Operation 상태와 실패 사유를 확인하고 GPU Node Ready + 실제 `nvidia.com/gpu` allocatable을 별도로 확인한다.
3. GPU Node에 배치된 Cinder/Manila/NFS node plugin의 matching toleration과 Ready 상태를 확인한다. RuntimeClass/device plugin 문제를 스토리지 성공으로 덮지 않는다.
4. 실제 클러스터 StorageClass를 확인한 뒤 **Cinder RWO**, **Manila NFS RWX** PVC/workload를 각각 구성한다. Kubernetes 이벤트로 binding/attach/mount를 구분하고 GPU Node의 실제 컨테이너 안에서 읽기·쓰기를 확인한다. PVC Bound만으로 mount 성공을 선언하지 않는다. 이 문서는 존재하지 않는 StorageClass 이름이나 Drover PVC create endpoint를 만들지 않는다.

   DMS Lab의 이번 native Manila mount에는 시험 GPU VM에만 승인된 shared `private_provider` NIC를 같은 tenant의 Nova interface API로 연결했다. 기존 Drover cluster-node interface API는 server/default-agent VM 목록만 검사하며 이번 autoscale GPU VM을 포함하지 않았다. 새 nodegroup-interface API나 자동 NIC·guest route/DNS patch를 구현한 것이 아니다. 후속 화면은 필요한 provider 연결과 해당 API의 실제 VM 범위를 먼저 확인해야 한다.
5. 축소 관찰 전 GPU workload를 삭제하고 해당 인수시험의 PVC 및 storage-dependent workload도 정리한다. 삭제 전 데이터 보존/StorageClass reclaim policy를 확인하며 다른 사용자 workload나 운영 데이터를 삭제하지 않는다. 수동 bootstrap으로 올린 `min_size`도 필요에 따라 0으로 되돌린다.
6. 기존 **600초 idle / 300초 cooldown**, min/max, PDB, local storage·PVC/protected Pod 및 control-plane guard를 유지한 상태에서 축소를 관찰한다. 차단 이유는 표시하되 drain guard를 force로 우회하지 않는다.

Durable Operation `SUCCEEDED`는 필요한 작업 상태 증거지만 실제 GPU 실행/볼륨 mount를 대신하지 않는다. Redis Stampede 이벤트가 비어 있어도 성공이나 작업 부재로 단정하지 않는다. `/operations/{operation_id}`와 sequence 기반 `/events`가 내구성 진행/실패의 정본이다. nullable `message`와 payload를 보존한다.

## 5. 대시보드 소유자에게 넘기는 소스 지도

아래는 **변경 후보와 현재 한계**다. 이번 인계에서 runtime/frontend 파일을 수정하지 않는다.

| 후속 작업 | 정확한 현재 소스 | 현재 상태와 인계 요구 |
|---|---|---|
| GPU image/labels/taints 입력과 dedicated preset | [K3sNodegroupCreateModal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupCreateModal.svelte), [K3sNodegroupEditModal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupEditModal.svelte) | 생성은 name/role/node_count/flavor + Stampede/minmax만 전송한다. 생성·수정 모두 image/labels/taints UI가 없다. 기존 필드를 노출하고 실제 image ID, 명시적 GPU taint, 예약 label 제한을 적용한다. 설정 수정이 기존 Node retrofit이라고 안내하지 않는다. |
| Request/response·GPU 타입 표현 | [K3s types](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/types/k3s.ts), [flavors API](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/api/compute/flavors.py), [FlavorInfo](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/models/compute.py) | `K3sNodegroup`에는 이미 image/labels/taints 응답 필드가 있다. `K3sFlavor`는 optional extra_specs/gpu_count를 가지지만 정규화 타입 필드는 없다. 새 native schema가 있는 것처럼 쓰지 않는다. 아래 데이터 경로 계약 질문을 먼저 확정한다. |
| 기본 켜짐·명시적 opt-out 보존 | [K3sCreateClusterModal](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sCreateClusterModal.svelte), [list controller](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/stores/k3sClusterListController.svelte.ts) | 기본 `true`, 선택값 boolean 전송은 이미 존재한다. GPU preset 때문에 사용자의 `false`나 기존 그룹을 덮어쓰지 않는다. 기본 agent/server 제외와 min/max를 명시한다. |
| GPU 타입/실제 상태·CSI readiness·durable operation | [K3sNodegroupCard](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/dashboard/drover/K3sNodegroupCard.svelte), [K3sStampedeTab](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/components/k3s/K3sStampedeTab.svelte), [detail controller](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/stores/k3sClusterDetailController.svelte.ts) | card는 flavor summary/allocatable에서 GPU badge를 계산하고 tab은 Stampede 상태와 Redis 이벤트를 읽는다. GPU 타입·설정량·allocatable·실행·CSI mount를 구별한다. 실제 관측이나 안내를 표시하고 없는 CSI 성공 상태/용량을 합성하지 않는다. 기존 operation ID의 durable 조회/오류를 연결한다. |
| Manifest helper·권한 유지 | [k3sPermissions](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/stores/k3sPermissions.ts), [detail kubeconfig owner](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/frontend/src/lib/stores/k3sClusterDetailController.svelte.ts), [BFF permission table](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/services/drover_authorization.py) | YAML helper의 selector/resources/runtime/toleration을 함께 안내한다. 다운로드·표준 Kubernetes 제출은 실제 grade/RBAC를 유지하며 일반 cluster editor를 workload editor/admin으로 승격하지 않는다. PVC 순서와 정리/guard 안내를 같은 흐름에 배치한다. |

### 후속 대시보드 체크리스트 — 전부 pending

- [ ] 기존 nodegroup API의 `image_id`, 허용 사용자 labels, explicit taints 및 GPU dedicated preset을 생성/설정 화면에 노출한다.
- [ ] 기본 Stampede `true`/명시적 boolean `false`, min/max·수동 node_count, 기본 agent/server 제외, 기존 자원 opt-out을 유지한다.
- [ ] 신뢰 가능한 flavor metadata에서 정규화 GPU 타입을 표시한다. GPU count·타입·allocatable을 구별하며 누락/오류/혼합 타입을 CPU나 임의 GPU로 보정하지 않는다.
- [ ] YAML helper에 resources requests/limits + 정규화 accelerator selector + `runtimeClassName:nvidia` + matching toleration을 함께 넣고 표준 Kubernetes API 제출을 안내한다.
- [ ] 실제 CSI node readiness, durable operation 상태/오류, GPU allocatable과 실행 증거를 별도로 표시한다. API ack·Node Ready·Redis event를 live 성공으로 승격하지 않는다.
- [ ] PVC-free bootstrap → GPU Ready/allocatable → Cinder RWO/Manila NFS RWX mount → workload/PVC 정리 → guard 기반 scale-in 순서를 안내한다.
- [ ] 기존 project/resource ownership·permission·credential grade를 유지하고 quota/auth/KEK force/reset과 자동 backfill을 추가하지 않는다.
- [ ] 별도 UI 변경의 source SHA·검증·배포 receipt를 기록한다. 그 전에는 이 change를 archive하지 않는다.

### 열려 있는 계약 질문

**정규화 GPU 타입을 대시보드에 공급할 검증된 기존 데이터 경로를 어디로 확정할 것인가?** 현재 두 nodegroup modal은 `/api/v1/flavors`를 읽는다. 이 경로의 [Afterglow nova.list_flavors](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/backend/app/services/nova.py)는 빈 specs에 `get_flavor`를 시도하고 오류를 무시하는 현재 소스다. 이는 Drover v0.4.14의 `fetch_flavor_extra_specs`/오류 전파 수정 대상과 **다른 구현**이며, Drover 배포만으로 UI catalog가 보강되지 않는다. `K3sFlavor`에도 정규화 타입 필드는 없다.

후속 소유자는 기존 응답/metadata 경로의 신뢰성을 확인하고 같은 정규화 계약을 재사용하는 표시 방법을 확정해야 한다. 검증할 수 없으면 미확인으로 표시하고 API/schema 추가가 필요하다고 판단한 경우 별도 승인 범위를 정한다. 이번 문서는 runtime 변경이나 새 `gpu_type` 응답 필드를 약속하지 않는다. 이 질문은 API 예제 인계 자체를 막지는 않지만 normalized flavor UI의 완료 조건이다.

## 6. v0.4.14 실제 운영 receipt

2026-10-13 신규 disposable cluster `e2551749-a75a-492d-9a6f-3c4fce2398b9` (`drover-0414-api-d1d749c39f9a`)의 원래 test actor/project 권한으로 수행했다. Kubernetes는 발급된 admin grade와 저장 CA/hostname 검증을 유지했다. 이 결과는 대시보드 구현·검증·배포 완료가 아니다.

| 항목 | 새 native 관측 |
|---|---|
| 배포 | 18:54:05Z API/Worker6개 모두 v0.4.14/revision/source hash 일치; controller3대·VIP·공개 HTTPS readiness200. 동시 OpenSearch 작업 중 c2 backup LB image drift로 최초 runner가 중단됐고, 사용자 확인 후 c3는 `--skip-tags haproxy`로 재개해 non-Drover ID/image를 유지했다. 최초 census를 덮어쓰거나 전체 기간의 무변경을 주장하지 않는다. |
| 기본값·GPU 그룹 | cluster Stampede 생략→true, 초기 server/agent 그룹 false. GPU 그룹 `03f2c69e-d72d-4f3d-a90b-78a364e0b8c1`: explicit image/NoSchedule taint, node_count/min/max0/0/1, 생략→Stampede true. |
| 실제 GPU 실행 | scale-up `e38e418c-e4cd-4a5e-b2f8-6bf5d432fb03` SUCCEEDED. PVC-free Pod Running, RTX3060/driver535.309.01/nvidia-smi와 `GPU_EXECUTION_OK`. VM `adb8fca7-7882-4e3a-9519-4e5bfb3203b2`의 Node Ready/allocatable1, `accelerator`/예약 타입 `RTX3060LHR`, 명시적 GPU taint, CSI node plugin3개 Running/Ready. |
| native storage | 같은 GPU Pod에서 Cinder RWO volume `0a76ef04-ee4b-43cf-9837-6e72a2f312ef` `/dev/vdb` ext4, Manila RWX share `92805dca-89af-4ddc-ac00-f15404df26d7` native `.104` NFSv4, 각각1Gi 실제 쓰기·읽기 SHA256 일치. GPU-node mount/I/O를 검증했으며 새 cross-node 동시 RWX 검증은 아니다. |
| 자연 축소 | workload/PVC를 UID-guarded ordinary DELETE로 정리한 뒤 idle600s/cooldown300s/min0/max1 그대로 유지. 19:44:10Z `4a44728f-cf74-4a25-9b6f-211cda7303b5` SUCCEEDED, count/in-flight0/0, GPU VM/Node/boot/data volume/share 및 해당 Pods/PVCs/PVs404. resize·force·guard 우회 없음. |
| 정리·보존 | cluster delete `e07e8f73-3a01-4e43-8da4-0ada5d5f2037` SUCCEEDED/DELETED, 소유 VM3개/volume4개/provider port404. GPU VM404 뒤 임시 flavor ACL만 회수하고 나머지 tenant3개·quota 유지. 기존 ERROR fixture/group/`error_deleting` volume, baseline Pod UID·VM2개·ports·metadata-only KEK ACTIVE는 그대로다. 복원 guest healthz200/Ready2, legacy DELETED도 read-only로 확인했다. |

상세 immutable 발행·CI, CSI/PVC/VM ID, hash, 관측 시각·권한·보존 경계는 [Drover 릴리스 기록](https://github.com/openstack-afterglow/drover/blob/dev/docs/release-0.4.0.md#immutable-0414-publication-and-canonical-rollout)에 있다. 기존 Node/CSI 자동 backfill과 Afterglow catalog 보강은 하지 않았고, 별도 UI checklist가 남아 있으므로 OpenSpec은 unarchived로 유지한다.

## 관련 문서

- [Afterglow k3s API reference](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/docs/api/k3s.md)
- [Afterglow architecture](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/ARCHITECTURE.md)
- [미완료 OpenSpec tasks](https://github.com/openstack-afterglow/openstack-afterglow/blob/dev/openspec/changes/gpu-nodegroup-api-dashboard-handoff/tasks.md)
