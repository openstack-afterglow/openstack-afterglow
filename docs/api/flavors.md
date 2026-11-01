---
title: 플레이버 (Flavors)
parent: API 레퍼런스
nav_order: 33
---

# 플레이버 (Flavors) API

> 태그: `flavors`
> 기본 경로: `/api/v1/flavors`

Nova 플레이버(인스턴스 스펙)를 조회하고 현재 프로젝트의 CPU·메모리·승인 GPU 조합을 검증·저장·재사용합니다.

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
| `GET` | `/api/v1/flavors/composer-options` | 현재 자원 조합의 조건부 CPU·RAM·GPU 선택 범위 |
| `GET` / `POST` | `/api/v1/flavors/compositions` | 본인·현재 프로젝트의 저장 구성 / 검증 후 native flavor 저장·재사용 |
| `GET` | `/api/v1/flavors/compositions/operations/{operation_id}` | 본인·현재 scope의 exact 저장 요청 결과를 fresh 검증하여 반환, 아직 확인 불가이면 null |
| `GET` | `/api/v1/admin/instances/flavor-composer-options` | 명시 대상 프로젝트의 조건부 선택 범위 (관리자) |
| `GET` / `POST` | `/api/v1/admin/instances/flavor-compositions` | 본인·명시 대상 프로젝트의 저장 구성 / native 저장·재사용 (관리자) |
| `GET` | `/api/v1/admin/instances/flavor-compositions/operations/{operation_id}` | 필수 `project_id` 대상의 exact 저장 요청 결과 fresh 검증 (관리자) |
| `GET` | `/api/v1/admin/instances/flavors-for-project` | 대상 프로젝트의 생성용 플레이버·쿼터·호스트 용량 반환 (관리자) |
| `PUT` | `/api/v1/admin/flavors/{flavor_id}/frontend-visibility` | Afterglow 사용자 화면 노출 여부 설정 (시스템 관리자) |
| `PUT` | `/api/v1/admin/flavors/{flavor_id}/usage-schedule-requirement` | 수동·자동 관리 플레이버의 추가 일정 필수 지정 (시스템 관리자) |
| `GET` / `PUT` | `/api/v1/admin/flavor-automation` | 자동 관리 상태 / revision·enabled 변경 |
| `POST` | `/api/v1/admin/flavor-automation/reconcile` | 활성 정책의 native 지원 규격·metadata·ACL readback 조정 |
| `GET` / `PUT` | `/api/v1/admin/flavor-automation/policy` | retained host·승인 GPU profile 조회 / revision·profiles 저장 |
| `GET` | `/api/v1/admin/flavor-automation/pci-devices` | Nova alias 설정 snapshot과 Placement PCI 관측·사용량·매핑 조회 |
| `POST` | `/api/v1/admin/flavor-automation/discover` | 표준 Nova/Placement host 관측 병합 |
| `PUT` | `/api/v1/admin/flavor-automation/hosts/{host_id}` | revision·removed 명시 변경; 제거 전 Nova service disable/readback |

---

## 직접 자원 구성과 저장

VM wizard의 기본 경로는 코어·메모리·선택적 GPU 모델/장 수를 직접 구성하고 명시적으로 저장한 뒤 다음 단계로 가는 방식입니다. 저장 구성과 기존 flavor catalog도 사용할 수 있습니다. 저장은 VM 생성이나 CPU/RAM/GPU 예약이 아닙니다.

### GET /api/v1/flavors/composer-options

`vcpus`(기본2), `ram_mb`(기본4096), `gpu_profile_id`(생략=GPU 없음), `gpu_count`(기본0), 선택적 `availability_zone`을 받습니다. CPU는 정수1–128, RAM은1024MiB 단위의1–2048GiB이며 GPU는 승인 profile과 정확한 primary/companion alias만 사용합니다. 임의 extra specs·resource class·native 이름/ID는 받지 않습니다. GPU 없는 요청의 count는0, profile을 지정한 요청은1이상이어야 합니다.

응답의 `vcpus`·`ram_mb`는 **나머지 선택 값을 유지했을 때** 생성 가능한 값 배열입니다. 서로 다른 호스트의 CPU/RAM 최대치를 합친 독립 범위가 아닙니다. `gpu_profiles`는 `{id,name,status}` 배열이고 소진/미확인 profile도 각각 `insufficient`/`unavailable`로 남깁니다. `gpu_counts`는 선택한 profile과 현재 CPU/RAM을 **같은 eligible 컴퓨트**에서 함께 만족하는 장 수 배열이며1/2/4/8로 한정하지 않습니다. Primary와 모든 companion의 남은 수량·numbered-group16한도·native 프로젝트 quota·domain/project cap을 함께 검사합니다. 예를 들어 두 호스트의 GPU 잔량이 각각2장이라도4장을 한 VM의 선택지로 합산하지 않습니다.

`selection`은 현재 exact 조합의 `FlavorInfo` 또는 null이고, 전체 `status`는 `available|insufficient|unavailable`, `checked_at`은 관측 시각입니다. 목록 GET은 native flavor·VM·ACL·quota를 변경하지 않습니다. 옵션은 advisory이며 polling 중 다른 소비자가 자원을 사용할 수 있습니다. 저장과 실제 VM 생성은 각각 최신 권위·현재 잔량을 다시 확인합니다. 기본AZ·정책·native quota·Placement 미확인은 가용0 또는 충분함으로 대체하지 않습니다. Host/provider/다른 사용자·VM 원문은 반환하지 않습니다.

### POST /api/v1/flavors/compositions

```json
{"vcpus":3,"ram_mb":12288,"gpu_profile_id":null,"gpu_count":0}
```

현재 쓰기 권한과 enabled 자동화·승인 정책, enabled exact 프로젝트, quota와 same-host capacity를 검증한 뒤 native private flavor를 저장하거나 동일한 기존 managed UUID를 재사용합니다. 반환값은 현재 eligibility/capacity를 포함한 `FlavorInfo`입니다. 기존 표준 shape의 UUID/spec·native `cpu.*`/`cpu.ag.*`/`mem.*` 이름과 VM 참조는 보존하며 수동 ID/name 충돌을 덮어쓰지 않습니다. 새 custom shape intent는 후속 automation pass가 비표준 코어/메모리/장 수라는 이유만으로 퇴역시키지 않도록 보존합니다. Host/profile의 명시 제거·승인 변경과 policy 재검증은 계속 적용합니다.

서버는 저장된 ownership/dispatch intent, graph lease, 현재 caller/target/policy fence와 native readback 뒤에만 공개하고 본인·프로젝트별 이력을 기록합니다. 응답 유실·불명 native dispatch는 자동 재전송하지 않습니다. 복구는 아래 exact operation GET으로 수행하며 저장 목록·native 이름 검색이나 브라우저 초안은 해당 요청의 결과·권한 증명이 아닙니다. 기존 automation을 자동으로 켜거나 native quota를 증액하지 않고, 저장 자체는 VM·Cinder volume·Placement allocation을 만들지 않습니다.

구성 저장은 foreground IAM과 같은 최대15초 FIFO graph-lock 대기를 사용합니다. Background reconciler가 이미 native 단위를 실행 중이면 해당 write/readback이 끝난 안전한 경계에서 양보합니다. 대기 후 현재 세션·권한·target·정책·용량을 다시 검사하고, deadline 내 admission 실패는409입니다. 새 POST/native 쓰기를 자동 재전송하거나 기존 lease를 강제로 삭제하지 않습니다.

저장 query `operation_id`는 UUID입니다. 브라우저는 명시 저장마다 새 UUID를 한 번 만들고 POST에 전달합니다. 생략한 API caller에는 서버가 UUID를 만들지만 브라우저의 응답 유실 복구에는 미리 보관한 동일 UUID를 사용합니다. 같은 UUID의 POST가 이미 기록되면 `409 flavor_composition_operation_exists`이며 재전송으로 native 쓰기를 반복하지 않습니다. 실제 사고에서는 `POST /flavors/compositions`가52.2초 뒤200을 반환했지만 브라우저 공통30초 deadline을 넘었습니다. Source cutover는 **이 저장 POST만120초**로 넓히며 공통 API timeout이나 native 쓰기 retry를 바꾸지 않습니다.120초는 완료 SLA가 아닙니다.

### GET /api/v1/flavors/compositions

`{"items":[FlavorInfo]}` 형태의 본인·현재 프로젝트 저장 목록입니다. 저장 이력은 다른 계정/프로젝트와 분리하고 현재 native visibility·정책·eligibility를 다시 평가합니다. 예전 저장 사실이 현재 생성 권한을 부여하지 않습니다. 사용자 화면의 저장 구성 불러오기도 exact 조합을 fresh 검증한 뒤 사용하며 부족·미확인은 선택 불가로 남깁니다.

관리자 변형은 `/api/v1/admin/instances/flavor-composer-options`와 `/api/v1/admin/instances/flavor-compositions`이며 필수 query `project_id`로 대상 quota·visibility·capacity를 평가합니다. 현재 시스템 관리자 권위와 enabled 대상 프로젝트를 별도로 확인하고 caller workspace의 quota로 대신하지 않습니다.

POST와 저장 목록의 `FlavorInfo.composition`은 `{vcpus,ram_mb,gpu_profile_id,gpu_count}` exact tuple을 제공합니다. GPU profile은 현재 승인된 stable slug이며 native 이름이나 companion alias에서 추측하지 않습니다. 프론트엔드는 이 tuple로 저장 구성을 다시 검증합니다.

현재 한도는 전체 custom intent4096개, 계정 홈·user·target project hash별 history bucket4096개, bucket별 최근20개입니다. Native flavor를 자동 삭제하거나 claim을 지워 공간을 회수하지 않으며 한도 초과는409입니다. History와 intent는 기존 `compute.managed_flavors` RuntimeSetting JSON의 private 필드이고 관리자 상태 GET에서도 원문은 제외합니다. 새 DDL/migration은 없습니다.

Native flavor/spec/access 쓰기는 caller의 personal/member connection이 아니라 별도로 인증·검증한 configured administrator-project executor가 수행합니다. Executor의 실제 token에 native admin 역할과 admin-project scope가 있어야 하며 caller의 현재 권한·대상 프로젝트 검증을 대신하지 않습니다. Caller connection은 현재 target quota와 native visibility를 읽는 데 유지합니다. Native 저장/읽기 응답이 불명확하면 private dispatch claim을 보존하고 `503 flavor_composition_native_outcome_unknown`으로 반환하며, 알려진 native/권한 거부는 원래 HTTP 판정을 유지합니다. 실패·불명 save는 새 custom intent나 개인 이력을 기록하지 않습니다.

### GET /api/v1/flavors/compositions/operations/{operation_id}

응답은 fresh 검증된 `FlavorInfo` 또는 JSON `null`입니다. 관리자 경로는 `/api/v1/admin/instances/flavor-compositions/operations/{operation_id}?project_id={target_uuid}`이고 POST에도 같은 필수 `project_id`와 `operation_id` query를 사용합니다. 선택적 `availability_zone`은 기존 저장/평가 경계를 따릅니다.

Private `compute.managed_flavors.composition_operations` receipt는 native dispatch 전에 UUID에 exact actor(home/user/target)·user/admin surface·안정적인 session/scope/provider signature·원래 tuple·shape fingerprint·native ID를 연결합니다. Credential/token 원문은 저장하지 않습니다. Receipt는24시간 유효하고 전체4096개로 제한되며 관리자 상태 GET과 다른 계정/프로젝트에는 원문을 공개하지 않습니다. 한도 초과는 `409 flavor_composition_operation_limit`이고 GET은 이력 저장·reconcile·native mutation을 실행하지 않습니다.

Receipt는 기존 RuntimeSetting JSON의 additive 필드이므로 새 DDL은 없지만 mixed-version 안전을 뜻하지 않습니다. **Receipt를 쓰기 전에 모든 해당 API/worker를 같은 버전으로 함께 전환해야 합니다.** 구형 관리 상태 응답의 public projection은 새 private 필드를 제외하지 않을 수 있고, 구형 전체 setting snapshot writer는 receipt를 덮어쓸 수 있습니다. 구형 writer/API를 남긴 동시 운영·rollback 호환성은 검증됐다고 주장하지 않습니다.

조회는 현재 쓰기 권한·enabled target·자동화/승인 정책·exact native 소유권·불변 shape·전체 scheduling specs와 ACL·현재 visibility·quota/same-host capacity를 다시 확인하고 반환 직전 같은 authority/policy/receipt를 재검사합니다. Receipt가 없거나 만료됐거나 원래 요청이 대기 중/부분 publication 상태이면 `null`이며 실패·완료·안전한 재전송을 뜻하지 않습니다. 다른 actor/session/scope는403, 정책·소유권 충돌/현재 선택 불가는409 등 실제 오류를 유지합니다. HTTP200의 `null`도 저장 unknown을 해제하지 않습니다.

Predispatch operation row는 **실행 의도일 뿐 publication 완료 receipt가 아닙니다.** 성공 복구에는 publication 뒤 같은 SQL commit으로 저장된 `custom_intents[flavor_id]`의 exact tuple과 해당 actor의 `composition_history`에 같은 native ID가 모두 있어야 하며 GET 시작과 반환 직전에 다시 검사합니다. Native flavor가 보이더라도 이 durable commit이 없으면 `null`/unknown을 유지합니다. GET은 누락 SQL을 보수하거나 저장 POST를 재실행하지 않으므로 계속 미확인이면 운영자가 원래 요청을 조사해야 하며 native 이름/유사 사양 수동 매칭으로 성공을 대신하지 않습니다.

같은 버전 writer의 `_save`는 SQL row lock 아래에서 만료되지 않은 receipt UUID를 병합하고 같은 UUID의 기존 내용이 바뀌면 `409 flavor_composition_operation_conflict`로 거부합니다. 만료 정리와 전체4096개 상한은 유지하며 이 SQL fence가 native/Redis와의 원자 transaction을 제공하지는 않습니다.

브라우저는 저장 응답 유실/timeout 뒤 원래 UUID의 GET만2초 간격으로 최대120초 확인합니다. Exact tuple·실제 native ID·현재 selectable 결과가 확인되면 기존 selection callback을 한 번 호출해 사양을 자동 선택하고 이미지 단계로 이어갑니다. 확인되지 않으면 원래 tuple과 unknown 차단을 유지하고 **저장 결과 새로 확인**도 같은 UUID를 GET-only 재조회합니다. 빈 저장 목록·같은 이름·유사한 사양을 찾아 대체하거나 새 POST를 보내지 않습니다. 이 경로는 자원 예약·native/SQL/Redis 원자 commit·배포 검증을 의미하지 않습니다.

## GET /api/v1/flavors

현재 프로젝트에 native 접근 가능한 Nova 플레이버와 `eligibility`를 반환합니다. 이 GET 자체는 flavor를 생성/수정하지 않습니다. 자동 카탈로그는 별도 관리자/background reconcile이 소유하고 enabled domain 정책의 잔여량·optional project cap과 **native 프로젝트 CPU/RAM quota를 함께** 검사합니다. 미전환 domain은 기존 프로젝트 quota/GPU 정책을 사용합니다. 기본 목록도 fresh 정책/usage를 확인하고 same-host fitting은 `capacity=create`에만 추가합니다.

Public/Private와 CPU/GPU 모두 같은 target quota를 검사하며 private에는 native project ACL이 추가로 필요합니다. 관리자 전체 카탈로그를 target의 접근 목록으로 취급하지 않고 cache hit도 현재 visibility로 제한합니다. 새 자동 생성 flavor는 private staging·spec readback 후 활성 pool의 실제 enabled project에 자동 ACL을 부여합니다. 기존/새 수동 flavor 중 명확히 CPU-only로 확인된 항목도 automation이 활성화되면 기존 ID·사양을 유지한 채 관리하며, private 접근은 확인된 domain project에 대해 조정합니다. Public은 Nova에서 계속 공개됩니다. GPU/미확인 수동 항목은 자동 편입하지 않습니다. Domain 선택 자체가 Nova domain grant나 미래 프로젝트 상속 권한인 것은 아니며 background reconcile이 새 프로젝트의 실제 native ACL을 검증합니다.

> **쿼터·호스트 용량 판정 및 적용 범위**:
> - `eligibility.quota_scope=domain`이면 domain 공용 잔여량·project cap과 native 프로젝트 CPU/RAM quota를 모두 검사합니다. GPU map은 승인 PCI resource class이고 domain CPU/RAM 한도 부재는 추가 제한 없음, GPU 부재는0입니다. Native instance 수 등 다른 quota도 유지합니다.
> - `capacity=create`이면 단일 VM 생성 기준으로 확인된 같은 호스트 부족을 `host_capacity_insufficient`, 확인하지 못한 용량을 `host_capacity_unavailable` blocker로 막습니다. 미확인은 GPU 여부와 무관하게 선택할 수 없습니다. 운영자 권한·Placement 장애·시간 초과·기본 compute AZ 정책 누락 동안에는 생성 가능한 flavor가 없으며, 확인되지 않은 용량을 Nova 판단에 맡기지 않습니다.
> - Domain pool과 GPU SQL reservation은 Afterglow 제어 경로의 정책입니다. Stock Nova/Placement가 실제 할당을 소유하며 custom Nova 확장/capability/fleet qualification은 요구하지 않습니다. 외부 CLI/API의 우회와 domain 총량의 비원자적 동시성 한계를 명시하고 전역 native enforcement로 표시하지 않습니다.
> - 시스템 관리자가 `afterglow:frontend_visible=false`로 설정한 플레이버는 쿼터 적격성 판정 전에 일반 사용자 응답에서 제외됩니다. 설정이 없으면 기존 호환성을 위해 노출됩니다.
> - 이 설정은 Afterglow의 VM·Resize·K3s 플레이버 선택 화면에만 적용됩니다. Nova의 Public/Private 상태, Flavor Access, CLI 및 직접 Nova API 접근 권한은 변경하지 않습니다.
> - 이 목록의 `eligibility`는 새 VM **생성**에 필요한 전체 자원 수요입니다. 기존 VM 리사이즈 선택에는 `GET /api/v1/instances/{instance_id}/resize-flavors`를 사용하여 현재 플레이버 대비 증분 수요와 디스크 제약을 평가합니다. 두 응답을 서로 대신 사용하지 않습니다.
> - 명시 pool의 `paused`는 Afterglow 신규 admission 차단이며 직접 Nova 요청을 가로채지 않습니다. Metadata 부재인 unmanaged와 다르고 legacy quota로 fallback하지 않습니다. `domain_pool_unavailable`·`domain_pool_paused`·domain/project 부족은 구분합니다.

VM wizard는 quota와 같은 호스트 용량이 모두 확인된 생성 가능 항목만 목록·분류 개수·검색·페이지 계산에 포함합니다. GPU 타입은 승인된 primary 그룹의 상단 버튼으로 한 번에 필터링하며 다른 분류·검색과 조합합니다. 부족·미확인 항목을 비활성 행으로 나열하거나 GPU 잔여량·부족 사유를 표시하지 않습니다. 조회/공통 기본 AZ 오류는 한 안내로 구분하고, 새로 막힌 선택 UUID는 자동 대체·전송하지 않습니다. 프로젝트 quota preview는 full dashboard quota의 별도 `native_compute`를 사용하여 domain pool의 공용 사용량과 섞지 않고 CPU/RAM의 실제 사용량·한도를 보여줍니다. 무제한이어도 사용량과 선택 후 값은 표시하며 관측이 없으면0/무제한으로 만들지 않습니다. 관리자 전체 목록은 authReady와 현재 system-admin scope가 준비된 뒤 조회하고 이전 scope/요청의 늦은 응답을 폐기합니다. API의 `eligibility` 진단 필드와 실제 생성 시 native fresh admission은 그대로 유지합니다.

생성용 목록은 backend의 `flavor-discovery` 역할이 기본10초 간격으로 준비한 공통 관측을 사용합니다. 카탈로그 metadata는 최대90초, 같은 호스트 capacity는 수집 시작부터 최대30초만 유효하며 `capacity.checked_at`은 관측 시각을 유지합니다. 목록 요청에서는 현재 native visibility/private ACL과 프로젝트 quota·domain pool을 다시 읽고, 저장된 host/provider 관측으로 target project/AZ의 판정만 계산합니다. 전체 host 관측·다른 프로젝트의 원문은 응답에 포함하지 않습니다. 누락·만료·변경된 승인 profile·미관측 shape는 `unavailable`로 차단하고, 다음 백그라운드 수집 후 목록을 다시 읽습니다. 실제 생성은 항상 fresh native admission으로 재검증하므로 목록은 예약/허가가 아닙니다.

### 자동 관리 규격과 소유권

GPU 없는 자동 shape는1/2/4/8/16/32/64/128 vCPU에 CPU당RAM2GiB(CPU)와4/8/16GiB(memory)를 조합합니다. GPU는 기존CPU당2/4/8GiB와 **관리자 승인 profile**별1/2/4/8장을 유지합니다. 모두 retained included 동일 호스트의 CPU/RAM·자원별min/step/최대1요청 한도를 함께 만족해야 하며 서로 다른 호스트의 CPU/RAM을 합산하지 않습니다. 관리자는 Nova alias 설정 snapshot에서 주 GPU와 동반 alias를 선택해 정확한 `pci_passthrough:alias` 및 resource-class 연결을 만들고 명시 승인합니다. 미분류 장치는 역할을 직접 확인해야 합니다. 모든 physical GPU/companion은 실제 alias 부착 요청이 필요하고 Placement resources-only·중복 RC 요청은 거부합니다. Alias 수만 GPU 개수로 배수화하고 다른 승인 spec은 보존합니다. Shared CPU는 VCPU, dedicated는 별도 PCPU inventory로 fitting하며 mixed/isolated emulator는 미지원입니다. Builtin/새 장치는 자동 승인하지 않고 Disk0은 volume boot용입니다.

생성 flavor의 managed marker는 `afterglow:managed_by=domain-compute-v1`이고 GPU access_mode=gpu_quota, CPU/memory=domain_quota입니다. 새2GiB-per-vCPU CPU Nova 이름은 `cpu.{vCPU}c_{RAM GiB}g`, 새 GPU 이름은 `gpu.{그룹명}x{수}_{vCPU}c_{RAM GiB}g`입니다. 기존 소유 이름과 ID는 유지합니다. GPU 이름 충돌에는 결정적 접미사를 사용하고, CPU/memory의 표준 native 이름이 이미 점유되면 다른 flavor를 덮어쓰지 않고 충돌을 보고합니다. ID는 결정적입니다. Down/disabled/disconnect/목록 누락·축소는 마지막 host 지원 사양을 지우지 않습니다. 명시 host 제거만 registry에서 제외하고 존재하는 native compute service를 disable/readback합니다. 재발견은 제거를 취소하지 않으며 restore도 native enable을 하지 않습니다. 실제 down host는 생성 용량상 사용 불가지만 flavor는 유지합니다. Explicit profile/host/policy 변경에 따른 퇴역은 ACL/publication만 회수하고 flavor·VM은 삭제하지 않습니다. Managed 수동 DELETE/specs/access/visibility는409입니다.

Memory 신규 native 이름은 `mem.{vCPU}c_{RAM GiB}g`이며 검증된 CPU-only 표시명도 실제RAM/vCPU≥4GiB이면 같은 prefix를 사용합니다. 기존4/8GiB shape와 GPU의 UUID identity/spec은 변경하지 않으며 exact 하드웨어/소유권의 과거 `cpu.*`/`cpu.ag.*` 이름·claim을 그대로 인정합니다. 기존 native 이름·ID·VM 참조는 수정하거나 중복 생성하지 않습니다. Memory도 CPU-only의 기존 domain_quota·private staging/readback·ACL·unknown-dispatch 경계를 사용합니다. Wizard의 memory 탭은 GPU 우선 후 실제 비율로 분류하므로 이름이 `cpu.*`인 기존4/8GiB도 memory에 포함하고 잘못된 `mem.*` 접두사를 하드웨어 증거로 쓰지 않습니다.

기존 수동 CPU의 자동 관리 권위는 `compute.managed_flavors`의 per-ID claim과 native `afterglow:cpu_control_token` 표식을 함께 사용합니다. 원문 claim은 내부에만 보존하고 Nova 표식은 claim의 digest이며, Afterglow flavor API와 cache에는 그 값을 반환하지 않고 `cpu_automation_managed` boolean만 표시합니다. Native 이름·설명·하드웨어 스펙과 VM ID는 수정하지 않습니다. 정확한 baseline·전체 프로젝트 디렉터리·읽기 확인이 없거나 PCI/가속기 여부가 모호하면 편입 또는 ACL 조정을 보류합니다. Public flavor는 Nova에서 비공개로 변경할 수 없고 Afterglow admission 범위에서만 도메인 정책을 검사합니다. Native `name`은 그대로이며 별도 nullable `display_name`을 검증된 CPU 투영으로 반환합니다. VM의 `flavor_display_name`도 완전한 native snapshot에서만 제공합니다. 소비자 생성 화면은 실제 vCPU·RAM과 확인된 GPU 모델/장 수를 표시하고 미확인 사양을 native 이름으로 추측하지 않습니다. 기존 VM의 원래 이름 표시 예외는 아래를 따릅니다. Native 이름·ID는 내부 선택/API 식별자로 유지하고 관리자 native 관리 표시는 변경하지 않습니다. 표시명은 Nova 요청·권한·quota의 식별자가 아닙니다.

기존 인스턴스 표시의 예외: 최근 인스턴스·일반 목록·상세는 검증된 `flavor_display_name`을 우선 사용하되 투영이 없거나 해석할 수 없으면 Nova가 서버에 보존한 원래 `flavor_name`을 표시합니다. 과거 CPU·GPU·수동 flavor가 현재 생성 목록에 없어도 원래 이름을 표시할 수 있습니다. 이름과 투영 모두 없으면 기존 확인 불가를 유지합니다. 이름을 vCPU/RAM/GPU 증거로 해석하거나 UUID로 대체하지 않으며 생성 가능 여부·resize admission을 완화하지 않습니다.

관리자 flavor 목록은 승인된 managed GPU의 `gpu_count`와 `gpu_primary_aliases`(`name`, `count`, `resource_class`, `profile_name`)를 반환하며 임의 이름의 동반 alias는 GPU에 포함하지 않습니다. 정책·정확한 alias 수량·spec 또는 퇴역 상태를 확인할 수 없으면 managed `is_gpu`, `gpu_count`, `gpu_primary_aliases`는 `null`이고 목록 관리는 유지됩니다. 수동 GPU flavor는 기존 GPU 표시 규칙을 유지합니다. 프로젝트 flavor와 관리자 대상 프로젝트 flavor의 `gpu_primary_aliases`도 현재 승인에 부합할 때만 제공되며 `null`은 미확인입니다. 생성 wizard는 해당 그룹명과 primary 수만 표시하고 실제 quota 계산은 RC를 사용합니다.

GPU shape의 모델 allocation이 허용하는 enabled domain의 **모든 enabled 프로젝트**에 ACL을 부여합니다. GPU 접근에 별도 project opt-in/CPU·RAM domain 입력이 필요하지 않습니다. 새 프로젝트도 후속 pass에 포함하며 transient usage/project cap은 ACL 회수 근거가 아닙니다. 상태 GET의 비저장 `readiness:{verified,reason}`는 Afterglow policy storage/validation 준비이며 native fleet 집행 증거가 아닙니다. Row 부재는 disabled/never-run이고 자동 활성화하지 않습니다. Policy 불명은503, revision/lease409, 오류 후 blind mutation replay는 하지 않습니다.


### 사용 일정 필수 판정과 추가 지정

일반·관리자 flavor 응답의 `usage_schedule_required`는 native flavor의 계산 결과입니다. **모든 GPU**, `vcpus >= 12` **또는** `ram >= 65536` MiB, 또는 truthy `afterglow:usage_schedule_required`(`true`/`1`/`yes`/`on`)이면 true입니다. 이름에 CPU/GPU 문자열이 있다는 이유만으로 CPU/RAM 기준을 추정하지 않습니다. `false`/키 삭제는 추가 지정만 해제하며 GPU·CPU·RAM 기본 조건을 우회할 수 없습니다. 대상 신규 VM 생성에는 `usage_schedule` object가 필요하고 기존 VM도 첫 성공적인 native metadata 등록부터 한 calendar month 유예를 받습니다. [일정 API](instances.md#13-사용-일정-usage-schedule)를 참조하세요.

시스템 관리자는 `PUT /api/v1/admin/flavors/{flavor_id}/usage-schedule-requirement`에 `{"required": true}` 또는 `{"required": false}`를 보냅니다(strict boolean; 다른 필드 불가). 응답은 `{"flavor_id":"uuid-string","usage_schedule_required":true,"additional_requirement":true}`입니다. `additional_requirement`는 요청한 추가 지정이고 `usage_schedule_required`는 기본 조건까지 합친 실제 판정이므로 해제 후에도 후자는 true일 수 있습니다.

`true`는 해당 native extra spec 하나만 `"true"`로 저장하고 `false`는 그 key만 지웁니다. **Managed flavor에도 이 전용 설정은 허용**되며 재조정/재활성화가 보존합니다. Hardware·ACL·visibility의 기존 managed 편집 잠금은 풀지 않습니다. 일반 extra-spec POST/DELETE로 이 key를 바꾸면409이며 전용 경로를 사용해야 합니다. Native ID/spec 전체 readback을 확인하고 프로젝트별 카탈로그를 무효화합니다. Native mutation의 redirect·reauth·retry는 끄며 결과 불명은502입니다. 이를 성공/안전한 재전송으로 해석하지 말고 fresh flavor를 먼저 조회하세요.

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
| `refresh` | 일반 목록은 `true`일 때 metadata cache를 갱신합니다. `capacity=create`는 매 요청 최신의 유효한 background 관측과 현재 visibility/quota를 사용하며, 이 값으로 전체 host 관측의 동기 수집을 강제하지 않습니다. 실제 생성 admission은 이 값과 무관하게 새로 검증합니다. |

응답 필드 `eligibility.capacity.reason`은 기본 ComputeAZ 정책 해석 실패 시 `default_compute_zone_unavailable`, 실제 Placement 조회 실패나 정상 판정 시 `null`입니다. 기존 `host_capacity_unavailable` blocker와 생성 거부는 유지합니다.

### 응답 (200 OK)

```json
[
  {
    "id": "uuid-string",
    "name": "m1.small",
    "display_name": "cpu.2c_2g",
    "vcpus": 2,
    "ram": 2048,
    "disk": 20,
    "is_public": true,
    "cpu_automation_managed": false,
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
| `display_name` | string \| null | 검증된 CPU flavor의 별도 화면 이름. `name`과 ID는 native 권위이며 `null`은 미확인 또는 CPU-only 아님 |
| `cpu_automation_managed` | boolean | 수동 CPU flavor의 관리 표식 존재 여부. 소유권은 서버가 별도 검증하며 표식 digest는 반환하지 않음 |
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
| `checked_at` | string | 생성 목록은 유효한 background 관측을 시작한 UTC ISO 8601 시각, admission은 해당 Placement 응답 시각. 최대30초 나이이며 예약이나 만료 시각이 아님 |
| `candidate_hosts` | integer | 요청 전체를 충족하는 확인된 root compute 수. GPU 장치 수가 아님 |
| `cpu_resource_class` | string/null | 일반 `VCPU`, dedicated `PCPU`. 해석 불가 시 null |
| `remaining_vcpus` | integer/null | 한 후보 호스트에서 VM **하나**가 받을 수 있는 최대 CPU 단위 = `min(capacity − used, max_unit)`. 호스트 전체 잔여량이 아님 |
| `remaining_ram_mb` | integer/null | 위 CPU 값과 **같은 호스트**에서 VM 하나가 받을 수 있는 최대 RAM MB |
| `numa_unverified` | boolean | 단일 NUMA 셀을 요구하는 flavor(`hw:numa_nodes=1`, `hw:mem_page_size=small`/`any`, dedicated CPU)이면 true. `available`은 호스트 합계 기준이고 셀 여유와 GPU의 NUMA 근접성은 Nova가 생성 시 판단합니다. `insufficient`는 셀과 무관하게 확정입니다. |

**VM wizard 표시 범위**: 소비자 화면(`/dashboard`)은 native flavor 이름/UUID 대신 실제 vCPU·RAM과 확인된 GPU 모델/장 수로 사양을 구분하며 디스크 규격, 프로젝트 쿼터, 생성 가능/불가 및 차단 사유와 갱신 상태를 유지합니다. 내부 선택과 POST payload의 native ID/name은 바꾸지 않습니다. 호스트별 VM 최대 CPU·RAM, 후보 호스트 수, NUMA·GPU 근접성 및 Nova snapshot 설명은 관리자 VM wizard(`/admin`)에서만 표시합니다. 관리자 계정으로 소비자 모드를 사용해도 이 세부 정보는 렌더링하지 않습니다. 기존 wizard의 `adminMode`를 공유 선택기에 전달하는 표시 구분이며 API 필드 제거·추가나 권한 변경은 아닙니다. 두 화면은 동일한 capacity 판정·자동 갱신·제출 직전 검증을 사용하고 관리자 native flavor 관리 화면은 유지합니다.

생성 선택 화면에는 `eligibility.selectable=true`이고 capacity가 `available`인 Flavor만 표시합니다. Background refresh로 기존 선택이 막히거나 목록에서 사라지면 해당 선택은 생성 불가 경고로 남고 자동으로 다른 Flavor를 선택하지 않습니다. 생성 직전 다시 검사하고 서버도 fresh admission을 수행합니다. 부족하거나 미확인인 항목을 숨기는 것은 Nova ACL이나 quota를 변경하지 않으며 Resize에는 증분 수요의 별도 계약을 계속 사용합니다.

**평가 방식**: 운영자 연결로 Nova 2.53의 hypervisor/service UUID·host 상태·AZ·aggregate·`cpu_info`와 Placement 1.36의 provider tree를 읽습니다. 그다음 flavor *shape*마다 allocation candidates를 한 번 조회합니다. shape는 CPU class, 명시적 `resources:*`, trait, PCI 장치당 numbered group으로 구성하며 CPU와 RAM은 1 단위로 요청합니다. 각 flavor의 실제 CPU/RAM은 그 응답의 `provider_summaries`(capacity·used)와 공급 provider inventory의 `max_unit`으로 **같은 후보 root**에서 맞춰 봅니다. Nova는 VCPU/PCPU/MEMORY_MB의 `min_unit`·`step_size`를 1로 보고하므로 1 단위 조회가 후보를 빠뜨리지 않습니다. disabled/down/forced-down 호스트는 제외합니다. 확인 가능한 aggregate/tenant 제약과 `capabilities:cpu_info:<field>` 단순 일치(ComputeCapabilitiesFilter)를 반영합니다. PCI alias는 GPU 카탈로그의 vendor/product resource class로 매핑합니다. alias가 등록되지 않은 GPU HDMI audio function은 정규화한 장치 이름으로 매핑합니다(`GA102 Audio` ↔ `GA102-audio`). 다른 호스트의 CPU/RAM과 GPU를 합치지 않으며 CPU와 RAM도 서로 다른 후보의 최대값을 조합하지 않습니다.

Aggregate metadata의 쉼표 구분 값은 공백을 제거한 후보 값으로 나눠 Nova와 같은 방식으로 비교합니다. PCI 장치 수의 합계는 numbered-group 한도 16을 list 할당 전에 확인하며 초과하면 `unavailable`로 반환합니다.

Placement capacity는 `(total − reserved) × allocation_ratio`입니다. VM 하나는 `max_unit`(Nova가 보고하는 물리 thread/메모리 총량)을 넘을 수 없습니다. 예를 들어 VCPU total 24, ratio 2.0인 호스트는 VM들에 48까지 할당할 수 있지만 VM 하나는 24를 넘지 못합니다. dedicated CPU 및 emulator isolate 추가 PCPU를 구분합니다. 부트 볼륨을 사용하는 생성에서는 flavor disk를 임의의 `DISK_GB` 수요로 더하지 않으며 명시적인 `resources:DISK_GB`는 반영합니다.

**NUMA 경계**: Placement는 호스트 합계만 제공하고 NUMA 셀별 여유를 노출하지 않습니다. 모든 생성은 NUMA 정책과 무관하게 Placement 호스트 할당을 먼저 통과해야 하므로, 호스트 합계 부족이면 어떤 셀에도 배치할 수 없습니다. 따라서 단일 셀 요청은 일반 flavor와 같은 Placement query로 평가하고 `numa_unverified=true`를 붙입니다. 합계 부족은 `insufficient`로 막고, 합계가 충분하면 선택·생성을 허용하되 Nova `NUMATopologyFilter`가 최종 거부할 수 있습니다. 호스트 셀 구조가 필요한 `hw:numa_nodes>1`, hugepage pool이 필요한 `large`/명시 page size, mixed CPU, `hw:numa_cpus.*`/`hw:numa_mem.*`은 경계를 정할 수 없으므로 `unavailable`입니다. 매핑할 수 없는 PCI alias, granular request group, operator가 있는 aggregate/capability 조건도 마찬가지입니다. 이미지 정책·PCI NUMA affinity·scheduler weight·server group을 포함한 Nova 전체 scheduler를 복제하지 않습니다.

확인된 부족에는 `host_capacity_insufficient`, 미확인에는 flavor 종류와 무관하게 `host_capacity_unavailable` blocker를 붙입니다. 미확인은 용량 0이나 충분한 용량으로 오인하지 않으며 값을 확인할 수 없으면 null을 반환합니다. Placement에 등록되지 않은 resource class는 `unavailable`입니다. 운영 Placement는 이 경우 allocation candidates에 HTTP 400을 반환하며, 후보가 없을 때도 `/resource_classes/{rc}`로 다시 확인합니다. 등록된 class의 여유 장치가 없으면 `insufficient`입니다. 호스트 이름, provider UUID, 다른 프로젝트/VM 식별자는 응답에 포함하지 않습니다.

**비용 경계**: fresh admission의 운영자 세션은 프로세스에서 재사용하고 snapshot 수준 오류 뒤에 폐기합니다. Native 요청은5초 timeout·재시도 없이 내부15초 deadline, async caller는 최대20초를 유지합니다. `capacity=create`는 read-only background 역할의 저장 관측을 project/AZ별로 local projection하며 foreground Placement 요청은 없습니다. 수집 pass 안에서 shape·provider inventory·resource-class 조회를 공유하고 실패 shape만 미확인입니다. 일반 quota-only catalog에는 Placement 조회가 없으며 기존 process-local10초 discovery cache는 제거했습니다.

이 한도는 전체 목록 endpoint나 인증의 SLA가 아닙니다. Native target visibility/ACL·quota/domain pool은 요청마다 확인하며 SDK 인증·이미 시작한 worker thread를 강제 종료하는 보장은 없습니다. 아래2026-10-01 수치는 이전 구현의 역사적 측정이고, 현재 저장 관측 경로의 실측은 `docs/testing.md`의2026-10-31 절을 따릅니다.

2026-10-01 운영 읽기 전용 측정: 이전 전체 79 flavor 평가 27.0초/HTTP 170회 → shape 공유 후 cold 4.4초/52회. 당시 3.5초는 **전체 카탈로그 fresh 평가**였으며 실제 단일 flavor admission 시간이 아닙니다. 실패 shape 캐시까지 반영한 후, 운영자 catalog/access 조회로 일반 프로젝트에 보일 public+허용 private flavor를 재구성해 평가한 값은 다음과 같습니다(AZ `nova`; 목록·쿼터 API 전체 지연은 제외).

| 일반 프로젝트 가시 범위 | Flavor / GPU / shape 수 | Cold(인증 포함) | TTL 내 warm | 전체 목록 fresh 6회 min / median / max | 단일 flavor fresh 6회 min / median / max |
| --- | --- | --- | --- | --- | --- |
| private 접근이 가장 많은 프로젝트 | 61 / 43 / 17 | 3.64초 / HTTP 45회 | 0.00초 / HTTP 0회 | 2.77 / 2.90 / 3.00초 / HTTP 42회 | GPU 0.43 / 0.45 / 0.47초 / HTTP 6회 |
| public-only 프로젝트 | 18 / 0 / 1 | 1.48초 / HTTP 21회 | 0.00초 / HTTP 0회 | 0.75 / 0.77 / 0.82초 / HTTP 18회 | CPU 0.76 / 0.80 / 0.88초 / HTTP 18회 |

2026-10-01 당시 private-heavy fresh 목록의 HTTP42회는 Nova facts3, Placement root 목록1, allocation candidates17, provider inventory13, resource-class 확인8이었다. GPU 단일 admission은 facts3+root1+candidates1+inventory1이었다. 별도 신규 연결 token 발급0.49–0.61초와 warm token services0.14–0.22초를 포함해 이 표본6회로 p95를 주장하지 않는다. 당시에는 추가 조회 병렬화가 없고15초 polling이10초 TTL보다 길어 보통 fresh 비용을 지불했다. 현재 구현은 background 저장 관측과 최대8개의 native ACL 병렬 읽기를 사용하므로 이 역사적 TTL/warm 비용을 현재 목록 지연으로 해석하지 않는다.

목록은 **advisory snapshot**입니다. 기본15초 자동 갱신·수동 새로고침·제출 직전 목록 갱신은 모두 유효한 저장 관측(용량 최대30초·metadata90초)을 다시 읽으며 native 전체 수집을 강제하지 않습니다. 수동·제출 갱신 중이거나 실패하면 진행을 보류하고 자동 갱신은 기존 선택을 유지합니다. **실제 생성 API의 admission만 native flavor·현재 quota·host capacity를 fresh로 다시 검증**합니다. 목록 조회와 제출 사이 결과가 달라질 수 있으며 Nova의 최종 atomic allocation이나 GPU 예약을 대신하지 않습니다. Resize 증분 수요와 K3s batch admission에는 create-only 목록 판정을 재사용하지 않습니다.

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
