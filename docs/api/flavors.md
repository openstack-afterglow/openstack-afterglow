---
title: 플레이버 (Flavors)
parent: API 레퍼런스
nav_order: 33
---

# 플레이버 (Flavors) API

> 태그: `flavors`
> 기본 경로: `/api/v1/flavors`

Nova 플레이버(인스턴스 스펙) 카탈로그를 조회합니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/flavors` | Nova 플레이버 목록 반환 |
| `GET` | `/api/v1/admin/instances/flavors-for-project` | 대상 프로젝트의 생성용 플레이버·쿼터·호스트 용량 반환 (관리자) |
| `PUT` | `/api/v1/admin/flavors/{flavor_id}/frontend-visibility` | Afterglow 사용자 화면 노출 여부 설정 (시스템 관리자) |

---

## GET /api/v1/flavors

프로젝트에서 사용 가능한 고정 Nova 플레이버 목록과 프로젝트 쿼터 적격성(`eligibility`)을 반환합니다. 새 플레이버를 만들거나 기존 vCPU/RAM/GPU 규격을 변경하지 않습니다. 같은 호스트의 CPU·RAM·GPU 용량은 VM 생성 wizard가 `capacity=create`로 요청할 때만 평가합니다. 기본 응답은 쿼터만 판정하며 `eligibility.capacity`가 `null`이고 운영자 연결이나 Placement 조회를 하지 않습니다. 이 기본 목록은 K3s 모달과 Drover 화면 prefetch도 사용합니다.

> **쿼터·호스트 용량 판정 및 적용 범위**:
> - 기본 응답의 `eligibility.selectable`은 현재 프로젝트의 잔여 인스턴스·vCPU·RAM·GPU 쿼터만 반영합니다.
> - `capacity=create`이면 단일 VM 생성 기준으로 확인된 같은 호스트 부족을 `host_capacity_insufficient`, 확인하지 못한 용량을 `host_capacity_unavailable` blocker로 막습니다. 미확인은 GPU 여부와 무관하게 선택할 수 없습니다. 운영자 권한·Placement 장애·시간 초과·기본 compute AZ 정책 누락 동안에는 생성 가능한 flavor가 없으며, 확인되지 않은 용량을 Nova 판단에 맡기지 않습니다.
> - Afterglow GPU 쿼터 및 단기 예약은 대시보드와 Afterglow 생성 요청을 보호합니다. 이미 Flavor 접근 권한(addTenantAccess)이 부여된 프로젝트의 CLI 또는 직접 Nova API 생성은 Nova 자체 쿼터 한계가 적용됩니다.
> - 시스템 관리자가 `afterglow:frontend_visible=false`로 설정한 플레이버는 쿼터 적격성 판정 전에 일반 사용자 응답에서 제외됩니다. 설정이 없으면 기존 호환성을 위해 노출됩니다.
> - 이 설정은 Afterglow의 VM·Resize·K3s 플레이버 선택 화면에만 적용됩니다. Nova의 Public/Private 상태, Flavor Access, CLI 및 직접 Nova API 접근 권한은 변경하지 않습니다.
> - 이 목록의 `eligibility`는 새 VM **생성**에 필요한 전체 자원 수요입니다. 기존 VM 리사이즈 선택에는 `GET /api/v1/instances/{instance_id}/resize-flavors`를 사용하여 현재 플레이버 대비 증분 수요와 디스크 제약을 평가합니다. 두 응답을 서로 대신 사용하지 않습니다.

### 요청 헤더

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | 예 | `Bearer <access_token>` 형식의 access JWT |
| `X-Project-Id` | 아니오 | 프로젝트 UUID (생략 시 토큰의 프로젝트) |

### 쿼리 매개변수

| 매개변수 | 설명 |
|----------|------|
| `capacity` | 선택. `create`이면 단일 VM 생성용 같은 호스트 용량(`eligibility.capacity`)을 함께 평가합니다. VM 생성 wizard 전용이며 생략하면 쿼터만 판정합니다. |
| `availability_zone` | 선택. 생성에 사용할 compute AZ. 생략하면 DB 정책 `nova.default_compute_availability_zone`을 해석합니다. 정책을 확인할 수 없으면 용량은 `unavailable`이며 모든 flavor가 생성 불가입니다. 같은 정책이 없으면 AZ를 생략한 생성 요청도 사전검증에서 503입니다. |
| `refresh` | `true`이면 캐시된 카탈로그를 새로 읽습니다. 쿼터와 capacity는 이 값과 무관하게 요청마다 평가하므로 wizard는 수동 새로고침에서만 보냅니다. |

### 응답 (200 OK)

```json
[
  {
    "id": "uuid-string",
    "name": "m1.small",
    "vcpus": 2,
    "ram": 2048,
    "disk": 20,
    "is_public": true,
    "extra_specs": {},
    "eligibility": {
      "selectable": true,
      "requirements": { "instances": 1, "cores": 2, "ram_mb": 2048, "gpus": {} },
      "remaining": { "instances": 10, "cores": 18, "ram_mb": 30720, "gpus": {} },
      "blockers": [],
      "capacity": {
        "status": "available",
        "checked_at": "2026-10-01T00:00:00+00:00",
        "candidate_hosts": 2,
        "cpu_resource_class": "VCPU",
        "remaining_vcpus": 14,
        "remaining_ram_mb": 16384,
        "numa_unverified": false
      }
    },
    "is_gpu": false,
    "gpu_count": 0
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 플레이버 UUID |
| `name` | string | 플레이버 이름 |
| `vcpus` | integer | vCPU 수 |
| `ram` | integer | RAM (MB) |
| `disk` | integer | 루트 디스크 (GB) |
| `is_public` | boolean | 공개 여부 |
| `extra_specs` | object | 추가 스펙 (GPU `pci_passthrough:alias` 등 포함) |
| `is_gpu` | boolean | GPU 플레이버 여부 (이름이 `gpu.`로 시작) |
| `gpu_count` | integer | GPU 수 (0이면 GPU 없음) |
| `eligibility` | object | 프로젝트 쿼터, 고정 VM 자원 수요, 차단 사유와 생성용 호스트 snapshot |

### `eligibility.capacity`

| 필드 | 타입 | 설명 |
|------|------|------|
| `status` | string | `available`: 하나 이상의 eligible 호스트에 수요가 함께 들어감. `insufficient`: 확인 가능한 후보에 여유 부족. `unavailable`: 권한·조회·응답·시간 초과·매핑 또는 경계를 정할 수 없는 제약 때문에 검증 불가. `available`만 생성을 허용하며 `insufficient`와 `unavailable`은 생성 불가입니다. |
| `checked_at` | string | 해당 Placement 응답을 읽은 UTC ISO 8601 시각. 목록은 최대 10초 된 snapshot일 수 있으며 예약이나 만료 시각이 아님 |
| `candidate_hosts` | integer | 요청 전체를 충족하는 확인된 root compute 수. GPU 장치 수가 아님 |
| `cpu_resource_class` | string/null | 일반 `VCPU`, dedicated `PCPU`. 해석 불가 시 null |
| `remaining_vcpus` | integer/null | 한 후보 호스트에서 VM **하나**가 받을 수 있는 최대 CPU 단위 = `min(capacity − used, max_unit)`. 호스트 전체 잔여량이 아님 |
| `remaining_ram_mb` | integer/null | 위 CPU 값과 **같은 호스트**에서 VM 하나가 받을 수 있는 최대 RAM MB |
| `numa_unverified` | boolean | 단일 NUMA 셀을 요구하는 flavor(`hw:numa_nodes=1`, `hw:mem_page_size=small`/`any`, dedicated CPU)이면 true. `available`은 호스트 합계 기준이고 셀 여유와 GPU의 NUMA 근접성은 Nova가 생성 시 판단합니다. `insufficient`는 셀과 무관하게 확정입니다. |

**VM wizard 표시 범위**: 소비자 화면(`/dashboard`)은 플레이버 자체의 vCPU·RAM·디스크·GPU 규격, 프로젝트 쿼터, 생성 가능/불가 및 차단 사유와 갱신 상태를 유지합니다. 호스트별 VM 최대 CPU·RAM, 후보 호스트 수, NUMA·GPU 근접성 및 Nova snapshot 설명은 관리자 VM wizard(`/admin`)에서만 표시합니다. 관리자 계정으로 소비자 모드를 사용해도 이 세부 정보는 렌더링하지 않습니다. 기존 wizard의 `adminMode`를 공유 선택기에 전달하는 표시 구분이며 API 필드 제거·추가나 권한 변경은 아닙니다. 두 화면은 동일한 capacity 판정·자동 갱신·제출 직전 검증을 사용합니다.

**평가 방식**: 운영자 연결로 Nova 2.53의 hypervisor/service UUID·host 상태·AZ·aggregate·`cpu_info`와 Placement 1.36의 provider tree를 읽습니다. 그다음 flavor *shape*마다 allocation candidates를 한 번 조회합니다. shape는 CPU class, 명시적 `resources:*`, trait, PCI 장치당 numbered group으로 구성하며 CPU와 RAM은 1 단위로 요청합니다. 각 flavor의 실제 CPU/RAM은 그 응답의 `provider_summaries`(capacity·used)와 공급 provider inventory의 `max_unit`으로 **같은 후보 root**에서 맞춰 봅니다. Nova는 VCPU/PCPU/MEMORY_MB의 `min_unit`·`step_size`를 1로 보고하므로 1 단위 조회가 후보를 빠뜨리지 않습니다. disabled/down/forced-down 호스트는 제외합니다. 확인 가능한 aggregate/tenant 제약과 `capabilities:cpu_info:<field>` 단순 일치(ComputeCapabilitiesFilter)를 반영합니다. PCI alias는 GPU 카탈로그의 vendor/product resource class로 매핑합니다. alias가 등록되지 않은 GPU HDMI audio function은 정규화한 장치 이름으로 매핑합니다(`GA102 Audio` ↔ `GA102-audio`). 다른 호스트의 CPU/RAM과 GPU를 합치지 않으며 CPU와 RAM도 서로 다른 후보의 최대값을 조합하지 않습니다.

Aggregate metadata의 쉼표 구분 값은 공백을 제거한 후보 값으로 나눠 Nova와 같은 방식으로 비교합니다. PCI 장치 수의 합계는 numbered-group 한도 16을 list 할당 전에 확인하며 초과하면 `unavailable`로 반환합니다.

Placement capacity는 `(total − reserved) × allocation_ratio`입니다. VM 하나는 `max_unit`(Nova가 보고하는 물리 thread/메모리 총량)을 넘을 수 없습니다. 예를 들어 VCPU total 24, ratio 2.0인 호스트는 VM들에 48까지 할당할 수 있지만 VM 하나는 24를 넘지 못합니다. dedicated CPU 및 emulator isolate 추가 PCPU를 구분합니다. 부트 볼륨을 사용하는 생성에서는 flavor disk를 임의의 `DISK_GB` 수요로 더하지 않으며 명시적인 `resources:DISK_GB`는 반영합니다.

**NUMA 경계**: Placement는 호스트 합계만 제공하고 NUMA 셀별 여유를 노출하지 않습니다. 모든 생성은 NUMA 정책과 무관하게 Placement 호스트 할당을 먼저 통과해야 하므로, 호스트 합계 부족이면 어떤 셀에도 배치할 수 없습니다. 따라서 단일 셀 요청은 일반 flavor와 같은 Placement query로 평가하고 `numa_unverified=true`를 붙입니다. 합계 부족은 `insufficient`로 막고, 합계가 충분하면 선택·생성을 허용하되 Nova `NUMATopologyFilter`가 최종 거부할 수 있습니다. 호스트 셀 구조가 필요한 `hw:numa_nodes>1`, hugepage pool이 필요한 `large`/명시 page size, mixed CPU, `hw:numa_cpus.*`/`hw:numa_mem.*`은 경계를 정할 수 없으므로 `unavailable`입니다. 매핑할 수 없는 PCI alias, granular request group, operator가 있는 aggregate/capability 조건도 마찬가지입니다. 이미지 정책·PCI NUMA affinity·scheduler weight·server group을 포함한 Nova 전체 scheduler를 복제하지 않습니다.

확인된 부족에는 `host_capacity_insufficient`, 미확인에는 flavor 종류와 무관하게 `host_capacity_unavailable` blocker를 붙입니다. 미확인은 용량 0이나 충분한 용량으로 오인하지 않으며 값을 확인할 수 없으면 null을 반환합니다. Placement에 등록되지 않은 resource class는 `unavailable`입니다. 운영 Placement는 이 경우 allocation candidates에 HTTP 400을 반환하며, 후보가 없을 때도 `/resource_classes/{rc}`로 다시 확인합니다. 등록된 class의 여유 장치가 없으면 `insufficient`입니다. 호스트 이름, provider UUID, 다른 프로젝트/VM 식별자는 응답에 포함하지 않습니다.

**비용 경계**: 운영자 세션은 프로세스에서 재사용하고 snapshot 수준 오류(인증·Nova·provider tree) 뒤에 폐기합니다. 명시적 Nova/Placement 요청은 5초 timeout·재시도 없이 남은 평가 deadline 안에서 실행합니다. 내부 deadline은 15초이고, 비동기 호출자는 최대 20초(15+5) 대기 후 `unavailable`로 반환합니다. SDK 인증·endpoint discovery와 이미 실행 중인 worker thread까지 강제 종료하는 15초 endpoint SLA는 아닙니다. 목록(`capacity=create`)은 최대 10초 된 snapshot을 single-flight로 공유하며 실패한 shape도 다시 묻지 않습니다. 캐시된 shape 조회 실패는 snapshot에서 한 번만 단문으로 기록하고 재사용은 반복 traceback을 남기지 않습니다. 생성 admission은 항상 새로 읽습니다.

2026-10-01 운영 읽기 전용 측정: 이전 전체 79 flavor 평가 27.0초/HTTP 170회 → shape 공유 후 cold 4.4초/52회. 당시 3.5초는 **전체 카탈로그 fresh 평가**였으며 실제 단일 flavor admission 시간이 아닙니다. 실패 shape 캐시까지 반영한 후, 운영자 catalog/access 조회로 일반 프로젝트에 보일 public+허용 private flavor를 재구성해 평가한 값은 다음과 같습니다(AZ `nova`; 목록·쿼터 API 전체 지연은 제외).

| 일반 프로젝트 가시 범위 | Flavor / GPU / shape 수 | Cold(인증 포함) | TTL 내 warm | 전체 목록 fresh 6회 min / median / max | 단일 flavor fresh 6회 min / median / max |
| --- | --- | --- | --- | --- | --- |
| private 접근이 가장 많은 프로젝트 | 61 / 43 / 17 | 3.64초 / HTTP 45회 | 0.00초 / HTTP 0회 | 2.77 / 2.90 / 3.00초 / HTTP 42회 | GPU 0.43 / 0.45 / 0.47초 / HTTP 6회 |
| public-only 프로젝트 | 18 / 0 / 1 | 1.48초 / HTTP 21회 | 0.00초 / HTTP 0회 | 0.75 / 0.77 / 0.82초 / HTTP 18회 | CPU 0.76 / 0.80 / 0.88초 / HTTP 18회 |

private-heavy fresh 목록의 HTTP 42회는 Nova facts 3, Placement root 목록 1, allocation candidates 17, provider inventory 13, resource-class 확인 8입니다. GPU 단일 admission은 facts 3+root 1+candidates 1+inventory 1입니다. 별도 신규 연결의 token 발급은 0.49–0.61초, warm token의 services 조회는 0.14–0.22초였습니다. 과거 5.1초 전부가 인증 시간이었다고 해석하지 않습니다. 표본 6회로 p95를 주장하지 않으며 추가 조회 병렬화는 적용하지 않았습니다. 15초 기본 폴링은 10초 TTL보다 길어 단독 poller는 보통 fresh 비용을 치릅니다. warm 값은 정상 15초 폴링 지연이 아니라 동시 조회·짧은 재조회 재사용 비용입니다. 이 측정은 tenant-authenticated 목록 endpoint 검증이나 실제 VM 생성 증거가 아닙니다.

목록은 **advisory snapshot**입니다. 생성 API는 mutation 전에 다시 평가하며 조회와 제출 사이 다른 VM의 할당으로 결과가 달라질 수 있습니다. Nova의 최종 atomic allocation을 대신하거나 GPU를 예약하지 않습니다. VM wizard는 기본 15초 자동 갱신, 수동 갱신, 제출 직전 갱신을 사용합니다. 자동 갱신은 선택을 잠그지 않고 기존 snapshot을 유지합니다. 수동·제출 갱신 중이거나 실패하면 진행을 보류합니다. resize의 증분 수요와 별도 K3s batch admission에는 이 create-only 검사 계약을 재사용하지 않습니다.

## GET /api/v1/admin/instances/flavors-for-project

관리자 생성 wizard는 관리자 자신의 프로젝트가 아닌 필수 `project_id` 대상의 flavor 접근 권한과 잔여 쿼터를 사용합니다. `capacity`와 `availability_zone` 선택자는 사용자 목록과 같습니다. capacity는 `capacity=create`이고 `count=1`(기본)일 때만 평가합니다. 여러 VM/batch 쿼터 평가(`count>1`)는 `capacity: null`을 반환하며 단일 VM snapshot으로 배치 전체를 보장하지 않습니다.

---

## PUT /api/v1/admin/flavors/{flavor_id}/frontend-visibility

시스템 관리자가 일반 사용자용 Afterglow 플레이버 카탈로그 노출 여부를 설정합니다. Nova 플레이버 extra spec `afterglow:frontend_visible`에 `true` 또는 `false`를 저장합니다.

### 요청 본문

```json
{
  "visible": false
}
```

### 응답 (200 OK)

```json
{
  "flavor_id": "uuid-string",
  "frontend_visible": false
}
```

관리자 `GET /api/v1/admin/flavors` 응답은 각 플레이버에 계산된 `frontend_visible` 값을 포함합니다. extra spec이 없으면 `true`입니다.
