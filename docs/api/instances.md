---
title: 인스턴스 (Instances)
parent: API 레퍼런스
nav_order: 31
---

# 인스턴스 (Instances) API

> 태그: `instances`, `instance-metrics`
> 기본 경로: `/api/v1/instances`

Nova 인스턴스(가상 머신)의 생성, 조회, 제어, 삭제와 볼륨·네트워크·보안 그룹·Floating IP·데이터 스토리지 연결 및 리소스 메트릭 조회를 관리합니다. Afterglow의 핵심 기능인 OverlayFS/Manila 기반 Union Mount VM 생성을 지원합니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

> 소유권 검증: 관리자가 아닌 사용자는 자신의 프로젝트가 소유한 인스턴스만 조회·제어할 수 있습니다. 타 프로젝트 인스턴스 접근 시 404/403으로 응답합니다(IDOR oracle 방지를 위해 일부 경로는 generic error로 통일).

---

## 목차

1. [기본 CRUD](#1-기본-crud)
2. [인스턴스 제어](#2-인스턴스-제어)
3. [볼륨 관리](#3-볼륨-관리)
4. [네트워크 인터페이스](#4-네트워크-인터페이스)
5. [보안 그룹](#5-보안-그룹)
6. [소유자 정보](#6-소유자-정보)
7. [Floating IP 관리](#7-floating-ip-관리)
8. [관리자 패스워드 재설정](#8-관리자-패스워드-재설정)
9. [데이터 스토리지 연결](#9-데이터-스토리지-연결-storage-attachments)
10. [리소스 메트릭](#10-리소스-메트릭)

---

## 1. 기본 CRUD

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances` | 인스턴스 목록 (단기 캐시) |
| `GET` | `/api/v1/instances/availability-zones` | 가용 영역 목록 |
| `GET` | `/api/v1/instances/{instance_id}` | 특정 인스턴스 상세 정보 |
| `POST` | `/api/v1/instances` | 인스턴스 동기 생성 (5/분) |
| `POST` | `/api/v1/instances/async` | 인스턴스 SSE 비동기 생성 |
| `POST` | `/api/v1/instances/bulk-action` | 인스턴스 일괄 액션 (10/분) |
| `DELETE` | `/api/v1/instances/{instance_id}` | 인스턴스 삭제 (연관 리소스 포함, 5/분) |

### GET /api/v1/instances

![인스턴스 목록](../../assets/instance-list.png)
*프로젝트 전체 VM 인스턴스 목록 — 상태·플레이버·IP·생성일시 표시, 자동 갱신*

프로젝트의 인스턴스 목록을 반환합니다. 각 항목의 `flavor_name`/`image_name`은 서버 측에서 resolve되며, 볼륨 부팅 인스턴스는 `image_name`이 `"볼륨에서 부팅"`으로 표시됩니다. 응답은 단기간 캐시됩니다(`?refresh=true`로 강제 갱신 가능).

**응답 (200 OK)** — `InstanceInfo` 배열

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 인스턴스 UUID |
| `name` | string | 인스턴스 이름 |
| `status` | string | Nova 상태 (`ACTIVE`, `SHUTOFF`, `BUILD`, `ERROR` 등) |
| `image_id` / `image_name` | string \| null | 부팅 이미지 |
| `flavor_id` / `flavor_name` | string \| null | 플레이버 |
| `ip_addresses` | array | `{addr, type("fixed"\|"floating"), network_name}` |
| `created_at` | string \| null | 생성 일시 (ISO 8601) |
| `metadata` | object | Nova 서버 메타데이터 |
| `union_libraries` | array[string] | Union Mount 라이브러리 목록 |
| `union_strategy` | string \| null | `prebuilt` \| `dynamic` |
| `union_share_ids` | array[string] | 연결된 Manila share ID |
| `union_upper_volume_id` | string \| null | OverlayFS upper 볼륨 ID |
| `scheduling` | string \| null | `standard` \| `ha` |
| `key_name` | string \| null | SSH 키페어 이름 |
| `user_id` / `project_id` | string \| null | 소유 사용자/프로젝트 |
| `fault` | object \| null | ERROR 상태의 fault 정보 `{message, code, created}` |
| `host` | string \| null | 하이퍼바이저 호스트 (관리자 스코프에서만 채워짐) |

`union_*` 응답 필드는 retained layer 라이브러리를 선택한 VM에서만 Nova metadata로 저장됩니다. 라이브러리가 없는 plain/GPU/data-mount VM은 해당 metadata key를 만들지 않으며 응답 파서는 누락된 필드를 `[]`/`null`로 반환합니다.

### GET /api/v1/instances/availability-zones

사용 가능한 가용 영역(AZ) 목록을 반환합니다. 인스턴스 생성 시 `availability_zone` 선택에 사용합니다.

**응답 (200 OK)** — 가용 영역 배열

### GET /api/v1/instances/{instance_id}

![VM 인스턴스 상세](../../assets/admin-instance.png)
*인스턴스 기본 정보(ID·이미지·플레이버·키페어·IP 목록)와 구간별 CPU·메모리·네트워크·디스크 I/O 그래프를 패널에서 바로 확인*

특정 인스턴스의 상세 정보를 반환합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `instance_id` | path | string | 예 | 인스턴스 UUID |

**응답 (200 OK)** — `InstanceInfo` (위 표 참조)

**오류**: `404 Not Found` — 인스턴스가 없거나 타 프로젝트 소유

### POST /api/v1/instances

인스턴스를 동기적으로 생성합니다. 모든 단계(Manila → 부트 볼륨 → upper 볼륨 → cloud-init → Nova 서버 → Floating IP)가 완료될 때까지 응답을 기다립니다. **속도 제한: 5회/분.**

**요청 본문** (`CreateInstanceRequest`)

```json
{
  "name": "my-vm",
  "image_id": "uuid-string",
  "flavor_id": "uuid-string",
  "libraries": ["python311", "pytorch"],
  "strategy": "prebuilt",
  "scheduling": "standard",
  "network_id": "uuid-string",
  "key_name": "my-key",
  "admin_pass": "string(8-128)",
  "availability_zone": "nova",
  "security_groups": ["default"],
  "boot_volume_size_gb": 20,
  "delete_boot_volume_on_termination": false,
  "data_mounts": [{ "file_storage_id": "uuid", "mount_point": "/mnt/data", "read_only": false }]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 아니오 | 인스턴스 이름. 생략/중복 시 서버가 유일 이름으로 정규화·부여 |
| `image_id` | string | 조건부 | Glance 이미지 UUID. `boot_volume_id`와 **상호 배타**이며 둘 중 하나는 필수 |
| `boot_volume_id` | string | 조건부 | 기존 부팅 볼륨 재사용. `image_id`와 상호 배타. `available` + `bootable` 볼륨만 허용 |
| `flavor_id` | string | 예 | Nova 플레이버 UUID |
| `libraries` | array[string] | 아니오 | 설치할 라이브러리 ID 목록. 의존성은 서버가 자동 확장 |
| `strategy` | string | 아니오 | `prebuilt` \| `dynamic`. **`libraries`가 있을 때만 의미** (없으면 Union Mount 미구성) |
| `scheduling` | string | 아니오 | `standard`(기본) \| `ha` |
| `network_id` | string | 아니오 | 연결할 네트워크 UUID. 생략 시 기본 네트워크 자동 결정 |
| `key_name` | string | 아니오 | SSH 키페어 이름 |
| `admin_pass` | string | 아니오 | 관리자 비밀번호 (8–128자) |
| `availability_zone` | string | 아니오 | 가용 영역. 생략 시 서버 기본 AZ |
| `security_groups` | array[string] | 아니오 | 보안 그룹 이름 목록. libraries/GPU 여부에 따라 서버가 필수 SG를 추가 |
| `boot_volume_size_gb` | integer | 아니오 | 부트 볼륨 크기(GB, 1–16384). 생략 시 서버 설정 기본값 |
| `delete_boot_volume_on_termination` | boolean | 아니오 | 인스턴스 삭제 시 부트 볼륨 동반 삭제 (기존 볼륨 재사용 시 강제 false) |
| `existing_upper_volume_id` | string | 아니오 | 복구 시 기존 upper 볼륨 재사용 (`available` 필요) |
| `additional_volume_ids` | array[string] | 아니오 | 생성 직후 연결할 기존 볼륨 UUID 목록 |
| `new_volumes` | array | 아니오 | 신규 생성·연결할 볼륨 `{name, size_gb}` 목록 |
| `data_mounts` | array | 아니오 | 기존 Manila share 직접 마운트 `{file_storage_id, mount_point, read_only}` |

> `data_mounts[].mount_point`는 `/mnt`, `/data`, `/srv`, `/home` 하위 절대 경로만 허용되며 `..`/`.` 세그먼트 및 `/opt`·`/etc`·`/usr`·`/var` 등 시스템 경로는 거부됩니다. NFS share 마운트에는 `network_id`(subnet CIDR 해석용)가 필요합니다.

**cloud-init 및 metadata 경계**

- `libraries`가 실제로 resolve된 경우에만 OverlayFS script/unit, `/etc/profile.d/union-env.sh`, layer health report/token, `union_libraries`·`union_strategy`·`union_share_ids`·`union_upper_volume_id`·`union_health_id` Nova metadata를 생성합니다.
- plain VM은 typed empty `packages`/`write_files`/`runcmd` cloud-config를 사용합니다. GPU-only와 `data_mounts`-only VM은 각 bootstrap만 유지하고 layer artifact 또는 `union_*` placeholder를 만들지 않습니다.
- direct data mount lifecycle은 새 `afterglow_data_share_ids` metadata를 사용합니다. 기존 VM 정리를 위해 읽기 경로에서만 과거 `union_data_share_ids`를 fallback으로 허용합니다.
- GPU VM은 `/opt/afterglow/install_gpu_monitoring.sh`가 NVIDIA CUDA repository의 `datacenter-gpu-manager`와 `datacenter-gpu-manager-exporter` 패키지를 설치하고 vendor `nvidia-dcgm`/`nvidia-dcgm-exporter` unit을 활성화합니다. repository architecture는 `amd64 → x86_64`, `arm64 → sbsa`만 허용하고 그 외에는 설치를 중단합니다.

이 계약은 새로 생성되는 VM의 rendered user-data에 적용되며 기존 guest를 자동 변경하지 않습니다. Palimpsest/SquashFS artifact 생성·외부 consume 경로는 VM의 retained library 선택 여부와 별도입니다.

**전략 설명**

| 전략 | 설명 |
|------|------|
| `prebuilt` | 관리자가 미리 빌드한 read-only share(CephFS/NFS)에 접근 규칙을 추가합니다. 빠르고 스토리지 효율적입니다. 해당 라이브러리의 사전 빌드 share가 없으면 실패합니다. |
| `dynamic` | VM 전용 read-write share를 새로 생성합니다. 격리가 완전하지만 생성 시간이 더 걸립니다. |

**응답 (201 Created)** — 생성된 Nova 서버 객체

**오류**
- `400 Bad Request` — boot source 검증 실패(`image_id`/`boot_volume_id` 동시 지정 또는 둘 다 누락), 볼륨 상태 불량, 이름 정규화 실패
- `409 Conflict` — GPU 쿼터 초과
- `500 Internal Server Error` — 생성 실패(리소스는 역순 롤백됨). 비관리자에게는 상세 원인이 숨겨집니다

### POST /api/v1/instances/async

인스턴스를 비동기적으로 생성하며 SSE(Server-Sent Events) 스트림으로 실시간 진행률을 전달합니다.

**요청 본문**: `POST /api/v1/instances`와 동일

**응답**: `text/event-stream`. 각 이벤트는 `ProgressMessage` JSON.

```json
{
  "step": "MANILA_PREPARING",
  "progress": 20,
  "message": "파일 스토리지 준비 완료",
  "elapsed_seconds": 3.2,
  "instance_id": null,
  "error": null
}
```

**step 값 목록** (실제 진행률 구간)

| step | 진행률 | 설명 |
|------|--------|------|
| `MANILA_PREPARING` | 0 → 20% | 파일 스토리지(라이브러리 share / data_mounts) 접근 규칙 준비 |
| `BOOT_VOLUME_CREATING` | 20 → 45% | 부트 볼륨 생성(이미지 기반) 또는 기존 볼륨 검증 |
| `UPPER_VOLUME_CREATING` | 45 → 60% | OverlayFS upper 볼륨 생성 또는 기존 볼륨 재사용 (libraries 있을 때만) |
| `USERDATA_GENERATING` | 60 → 65% | cloud-init user-data 생성 (libraries/GPU/data_mounts 중 하나라도 있을 때) |
| `SERVER_CREATING` | 65 → 95% | Nova 서버 생성 |
| `ATTACHING_VOLUME` | 95 → 100% | upper·추가·신규 볼륨 연결 |
| `FLOATING_IP_CREATING` | 100% | Floating IP 생성·연결 (tenant 네트워크 선택 시) |
| `COMPLETED` | 100% | 완료. `instance_id` 포함 |
| `FAILED` | — | 실패. `error` 포함(비관리자에게는 generic 메시지) |

**실패 시 롤백**

생성 도중 오류가 발생하면 이미 생성된 리소스를 역순으로 정리합니다.

| 순서 | 롤백 대상 |
|------|-----------|
| 1 | Floating IP 삭제 |
| 2 | Nova 서버 삭제 |
| 3 | 부트 볼륨(신규 생성분) / upper 볼륨(신규 생성분) 삭제 |
| 4 | Manila access rule 취소 |
| 5 | 동적(dynamic) 파일 스토리지 삭제 |

> 기존 볼륨을 재사용(`boot_volume_id`/`existing_upper_volume_id`)한 경우 롤백에서 삭제하지 않습니다.

### POST /api/v1/instances/bulk-action

여러 인스턴스에 대해 동일 액션을 일괄 수행합니다. 각 인스턴스마다 소유권을 검증하며 **부분 성공을 허용**합니다. **속도 제한: 10회/분.**

**요청 본문**

```json
{ "action": "stop", "instance_ids": ["uuid-1", "uuid-2"] }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `action` | string | 예 | `start` \| `stop` \| `delete` \| `reboot` |
| `instance_ids` | array[string] | 예 | 대상 UUID 목록 (1–50개) |

**응답 (200 OK)** — per-id 결과 배열. 오류는 소유권/존재 여부를 노출하지 않도록 generic 메시지로 통일합니다.

```json
{ "results": [ { "id": "uuid-1", "ok": true }, { "id": "uuid-2", "ok": false, "error": "처리 실패" } ] }
```

### DELETE /api/v1/instances/{instance_id}

인스턴스와 연관 리소스(헬스 토큰, dynamic share, upper 볼륨, CephX/NFS access rule, Floating IP)를 함께 정리합니다. 연관 리소스 정리는 best-effort입니다. **속도 제한: 5회/분.**

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `instance_id` | path | string | 예 | 인스턴스 UUID |

**응답**: `204 No Content`

---

## 2. 인스턴스 제어

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/instances/{instance_id}/start` | 인스턴스 시작 (30/분) |
| `POST` | `/api/v1/instances/{instance_id}/stop` | 인스턴스 중지 (30/분) |
| `POST` | `/api/v1/instances/{instance_id}/reboot` | 인스턴스 재시작 (30/분) |
| `POST` | `/api/v1/instances/{instance_id}/shelve` | 인스턴스 쉘브 (리소스 해제, 디스크 유지, 30/분) |
| `POST` | `/api/v1/instances/{instance_id}/unshelve` | 쉘브된 인스턴스 복원 (30/분) |
| `GET` | `/api/v1/instances/{instance_id}/console` | VNC 콘솔 URL 반환 |
| `GET` | `/api/v1/instances/{instance_id}/log` | 콘솔 로그 반환 |

각 제어 액션은 소유권 검증 후 수행되며, 모두 **`204 No Content`** 를 반환합니다. `start`는 정지(`SHUTOFF`) 상태, `stop`은 실행 상태를 전제로 하며, 상태가 맞지 않으면 하위 Nova 오류가 `500`으로 전달됩니다.

### GET /api/v1/instances/{instance_id}/console

인스턴스의 VNC 콘솔 접속 URL을 반환합니다.

**응답 (200 OK)**

```json
{ "url": "https://.../vnc_auto.html?token=..." }
```

### GET /api/v1/instances/{instance_id}/log

인스턴스의 콘솔 로그를 반환합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `length` | query | integer | 100 | 반환할 로그 라인 수 (`0`–`100000`, `0`이면 전체 로그) |

**응답 (200 OK)**

```json
{ "output": "콘솔 로그 텍스트..." }
```

---

## 3. 볼륨 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances/{instance_id}/volumes` | 연결된 볼륨 목록 |
| `POST` | `/api/v1/instances/{instance_id}/volumes` | 볼륨 연결 |
| `DELETE` | `/api/v1/instances/{instance_id}/volumes/{volume_id}` | 볼륨 해제 |
| `PATCH` | `/api/v1/instances/{instance_id}/volumes/{volume_id}` | 볼륨 연결 옵션 수정 |

### GET /api/v1/instances/{instance_id}/volumes

연결된 볼륨 목록을 반환합니다. 각 항목에 `name`/`size`/`status`가 함께 resolve됩니다.

### POST /api/v1/instances/{instance_id}/volumes

인스턴스에 기존 볼륨을 연결합니다.

**요청 본문**

```json
{ "volume_id": "uuid-string" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `volume_id` | string | 예 | 연결할 볼륨 UUID |

**응답**: `201 Created`

### DELETE /api/v1/instances/{instance_id}/volumes/{volume_id}

인스턴스에서 볼륨 연결을 해제합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `instance_id` | path | string | 예 | 인스턴스 UUID |
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답**: `204 No Content`

### PATCH /api/v1/instances/{instance_id}/volumes/{volume_id}

볼륨 연결의 `delete_on_termination` 플래그를 변경합니다(인스턴스 삭제 시 볼륨 동반 삭제 여부).

**요청 본문**

```json
{ "delete_on_termination": true }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `delete_on_termination` | boolean | 예 | 인스턴스 종료 시 볼륨 동반 삭제 여부 |

**응답**: `204 No Content`

---

## 4. 네트워크 인터페이스

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances/{instance_id}/interfaces` | 네트워크 인터페이스 목록 |
| `POST` | `/api/v1/instances/{instance_id}/interfaces` | 인터페이스 추가 |
| `DELETE` | `/api/v1/instances/{instance_id}/interfaces/{port_id}` | 인터페이스 제거 |

### POST /api/v1/instances/{instance_id}/interfaces

인스턴스에 새 네트워크 인터페이스를 추가합니다.

**요청 본문**

```json
{ "net_id": "uuid-string" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `net_id` | string | 예 | 연결할 네트워크 UUID |

**응답**: `201 Created`

### DELETE /api/v1/instances/{instance_id}/interfaces/{port_id}

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `instance_id` | path | string | 예 | 인스턴스 UUID |
| `port_id` | path | string | 예 | 포트 UUID |

**응답**: `204 No Content`

---

## 5. 보안 그룹

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances/{instance_id}/security-groups` | 인스턴스의 포트 및 보안 그룹 목록 |
| `POST` | `/api/v1/instances/{instance_id}/ports/{port_id}/security-groups` | 포트 보안 그룹 교체 |

### GET /api/v1/instances/{instance_id}/security-groups

인스턴스의 포트 목록과 프로젝트 전체 보안 그룹 목록을 함께 반환합니다.

**응답 (200 OK)**

```json
{ "ports": [ ... ], "security_groups": [ { "id": "uuid", "name": "default" } ] }
```

### POST /api/v1/instances/{instance_id}/ports/{port_id}/security-groups

지정된 포트의 보안 그룹을 교체합니다(기존 목록 대체).

**요청 본문**

```json
{ "security_group_ids": ["uuid-1", "uuid-2"] }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `security_group_ids` | array[string] | 예 | 설정할 보안 그룹 UUID 목록 (기존 목록 교체) |

---

## 6. 소유자 정보

### GET /api/v1/instances/{instance_id}/owner

인스턴스 소유 사용자의 표시 정보를 반환합니다.

**응답 (200 OK)**

```json
{ "display": "alice(alice@example.com)", "name": "alice", "email": "alice@example.com" }
```

> 사용자 조회에 실패하면 `{"display": "<user_id>"}`, `user_id`가 없으면 `{"display": "-"}`를 반환합니다.

---

## 7. Floating IP 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/instances/{instance_id}/floating-ip` | Floating IP 자동 생성 + 인스턴스 연결 |
| `DELETE` | `/api/v1/instances/{instance_id}/floating-ip` | 인스턴스 Floating IP 해제 + 삭제 |

### POST /api/v1/instances/{instance_id}/floating-ip

인스턴스 포트의 서브넷 → 라우터 → 연결된 외부 네트워크를 자동 판별하여 Floating IP를 생성·연결합니다. 연결 실패 시 생성된 Floating IP는 자동 정리됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `instance_id` | path | string | 예 | 인스턴스 UUID |
| `port_id` | query | string | 아니오 | 연결할 포트 ID (미지정 시 미점유 첫 포트 자동 선택) |

**응답 (200 OK)**

```json
{ "id": "uuid-string", "floating_ip_address": "203.0.113.10" }
```

**오류**
- `400 Bad Request` — 인스턴스에 포트가 없음 / 모든 인터페이스에 이미 FIP 할당됨
- `404 Not Found` — 지정한 인터페이스 없음
- `409 Conflict` — 해당 인터페이스에 이미 Floating IP 할당됨
- `422 Unprocessable Entity` — 서브넷이 외부 네트워크와 라우터로 연결되어 있지 않음/도달 불가
- `500 Internal Server Error` — 할당 실패

### DELETE /api/v1/instances/{instance_id}/floating-ip

인스턴스에 연결된 모든 Floating IP를 해제·삭제합니다(best-effort).

**응답**: `204 No Content`

---

## 8. 관리자 패스워드 재설정

QEMU Guest Agent(QGA)를 통해 게스트 관리자 계정의 패스워드를 재설정합니다. **두 엔드포인트 모두 시스템 관리자 전용**(`require_admin`)입니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances/{server_id}/admin-password/precheck` | 재설정 가능 여부 사전 점검 |
| `POST` | `/api/v1/instances/{server_id}/admin-password` | 패스워드 재설정 |

### GET /api/v1/instances/{server_id}/admin-password/precheck

**응답 (200 OK)** — `AdminPasswordPrecheck`

| 필드 | 타입 | 설명 |
|------|------|------|
| `supported` | boolean | 재설정 가능 여부 |
| `reason` | string \| null | 불가 사유 |
| `os_admin_user` | string \| null | 게스트 관리자 계정명 (이미지 메타데이터 기준) |
| `server_status` | string | 현재 Nova 상태 |

> `supported=true` 조건: 인스턴스가 `ACTIVE` 상태 **그리고** 이미지 메타데이터에 `hw_qemu_guest_agent=yes`가 설정되어 QGA가 활성화되어 있어야 합니다.

### POST /api/v1/instances/{server_id}/admin-password

**요청 본문**

```json
{ "new_password": "string(8-128)" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `new_password` | string | 예 | 새 관리자 비밀번호 (8–128자) |

**응답**: `204 No Content`

**오류**
- `404 Not Found` — 인스턴스 없음
- `409 Conflict` — `ACTIVE` 상태가 아님 / QGA 미활성 / Nova 패스워드 변경 충돌
- `500 Internal Server Error` — 변경 요청 실패

> 게스트 내부에서 QGA 데몬이 실제로 실행 중이어야 반영됩니다. 재설정 시도는 감사 로그에 기록됩니다.

---

## 9. 데이터 스토리지 연결 (storage-attachments)

실행 중인 VM에 사용자 소유(또는 public) Manila 파일 스토리지 접근 규칙을 부여하고 게스트에서 실행할 마운트 명령을 반환합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/instances/{instance_id}/storage-attachments` | 파일 스토리지 접근 규칙 부여 + 마운트 명령 반환 |
| `GET` | `/api/v1/instances/{instance_id}/storage-attachments` | 연결된 데이터 파일 스토리지 목록 |
| `DELETE` | `/api/v1/instances/{instance_id}/storage-attachments/{file_storage_id}` | 접근 규칙 회수 |

### POST /api/v1/instances/{instance_id}/storage-attachments

**요청 본문** (`StorageAttachRequest`)

```json
{ "file_storage_id": "uuid-string", "mount_point": "/mnt/data", "read_only": false }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `file_storage_id` | string | 예 | Manila share UUID |
| `mount_point` | string | 예 | `/mnt`·`/data`·`/srv`·`/home` 하위 절대 경로 (시스템 경로/`..` 금지) |
| `read_only` | boolean | 아니오 | 읽기 전용 마운트 여부 (기본 false) |

**응답 (200 OK)** — 프로토콜에 따라 마운트 명령이 다릅니다.

```json
{
  "file_storage_id": "uuid-string",
  "share_proto": "CEPHFS",
  "mount_command": "sudo mkdir -p ... && sudo mount -t ceph ...",
  "keyring_file": "[client.data-rw-...]\n    key = ...\n",
  "keyring_path": "/etc/ceph/ceph.client.data-rw-....keyring",
  "access_id": "uuid-string"
}
```

> NFS share인 경우 `keyring_file`/`keyring_path`는 `null`이며, VM의 fixed IP 기반 접근 규칙이 부여됩니다(fixed IP를 찾지 못하면 `409`). 접근 권한이 없거나 share가 `available`이 아니면 각각 `403`/`409`.

### GET /api/v1/instances/{instance_id}/storage-attachments

**응답 (200 OK)** — 배열 `[{file_storage_id, name, share_proto, status}]`

### DELETE /api/v1/instances/{instance_id}/storage-attachments/{file_storage_id}

해당 인스턴스에 대해 부여된 CephX/NFS 접근 규칙을 회수하고 메타데이터에서 제거합니다.

**응답**: `204 No Content`

---

## 10. 리소스 메트릭

Prometheus(node_exporter 우선, 테넌트망 격리 인스턴스는 libvirt-exporter 폴백)에서 인스턴스 시계열/요약 메트릭을 조회합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/instances/{instance_id}/metrics` | 단일 메트릭 시계열 (deprecated, batch 권장) |
| `GET` | `/api/v1/instances/{instance_id}/metrics-batch` | 다중 메트릭 시계열 일괄 조회 |
| `GET` | `/api/v1/instances/metrics-summary-batch` | 프로젝트 전체 7일 CPU/메모리 요약 + 저사용 판단 |
| `GET` | `/api/v1/instances/{instance_id}/metrics-summary` | 인스턴스 min/avg/max 요약 + 리사이즈 권장 |

**공통 파라미터**

| 파라미터 | 값 | 설명 |
|----------|-----|------|
| `metric` | `cpu`, `memory`, `network_rx`, `network_tx`, `disk_read`, `disk_write`, `gpu_util`, `gpu_mem` | 조회할 메트릭 키 |
| `metrics` | 위 키를 쉼표로 구분 | batch 전용. 예: `cpu,memory,disk_read` |
| `range` | `15m`, `1h`, `6h`, `24h`, `7d` | 조회 구간 (단일/batch 기본 `1h`, summary 기본 `7d`) |

> GPU 메트릭(`gpu_util`/`gpu_mem`, DCGM 기반)은 GPU 인스턴스(플레이버명이 `gpu.`로 시작)에서만 유효합니다. 단일 엔드포인트는 비GPU 인스턴스에서 `400`, batch 엔드포인트는 GPU 메트릭을 조용히 제외합니다.

### GET /api/v1/instances/{instance_id}/metrics-batch

**응답 (200 OK)**

```json
{
  "instance_id": "uuid-string",
  "range": "1h",
  "metrics": {
    "cpu": { "series": [ { "ts": 1710000000, "value": 12.3 } ], "error": null },
    "memory": { "series": [ ... ], "error": null }
  }
}
```

**오류**: `422` — `metrics` 비어 있음/알 수 없는 키. Prometheus 장애 시 각 메트릭 `error` 필드에 사유가 담깁니다.

### GET /api/v1/instances/metrics-summary-batch

프로젝트 내 모든 인스턴스의 7일 평균 CPU/메모리와 저사용(underutilized) 여부를 반환합니다. 목록 화면의 배지용입니다.

**응답 (200 OK)**

```json
{
  "range": "7d",
  "prometheus_available": true,
  "instances": { "uuid-string": { "cpu_avg": 8.1, "mem_avg": 15.0, "underutilized": true } }
}
```

### GET /api/v1/instances/{instance_id}/metrics-summary

인스턴스의 CPU·메모리·디스크 I/O 통계(min/avg/max)와 저사용 시 리사이즈 권장 플레이버를 반환합니다. 권장은 GPU 인스턴스에서는 산출하지 않으며, Nova resize 제약(디스크 축소 불가)을 반영합니다.

**응답 (200 OK)**

```json
{
  "instance_id": "uuid-string",
  "range": "7d",
  "prometheus_available": true,
  "stats": { "cpu": { "min": 1.0, "avg": 8.1, "max": 20.0 }, "memory": { ... }, "disk_read": { ... }, "disk_write": { ... } },
  "recommendation": {
    "underutilized": true,
    "reason": "cpu_avg<10,mem_avg<20",
    "current_flavor": { "id": "...", "name": "m1.large", "vcpus": 4, "ram": 8192, "disk": 40 },
    "suggested_flavor": { "id": "...", "name": "m1.small", "vcpus": 2, "ram": 2048, "disk": 40 }
  }
}
```

> Prometheus 연결 불가 시 `prometheus_available: false`, `stats: {}`, `recommendation: null`로 응답합니다.
