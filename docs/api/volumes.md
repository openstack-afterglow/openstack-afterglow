---
title: 볼륨 (Volumes)
nav_order: 54
parent: API 레퍼런스
---

# 볼륨 (Volumes) API

> 태그: `volumes`, `volume-backups`, `volume-snapshots`  
> 기본 경로: `/api/v1/volumes`, `/api/v1/volumes/backups`, `/api/v1/volume-snapshots`

Cinder 블록 스토리지 볼륨, 백업, 스냅샷을 관리합니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

> 볼륨·백업·스냅샷은 앱 소유권 검증 대상이 아닌 OpenStack 네이티브 리소스이지만, 경로 파라미터로
> 접근하는 단건 조회/변경 엔드포인트는 `assert_resource_owner`로 프로젝트 소유권을 재확인합니다.
> 소유자가 아니면 존재를 노출하지 않기 위해 일괄 `404`를 반환합니다.

---

## 목차

1. [볼륨](#1-볼륨)
2. [볼륨 확장](#2-볼륨-확장)
3. [볼륨 강제 삭제 및 삭제 복구 진단](#3-볼륨-강제-삭제-및-삭제-복구-진단)
4. [볼륨 이전 (Transfer)](#4-볼륨-이전-transfer)
5. [볼륨 백업](#5-볼륨-백업)
6. [자동 백업](#6-자동-백업)
7. [볼륨 스냅샷](#7-볼륨-스냅샷)

---

## 1. 볼륨

> 태그: `volumes`  
> 기본 경로: `/api/v1/volumes`

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/volumes` | 볼륨 목록 (15초 캐시) |
| `GET` | `/api/v1/volumes/{volume_id}` | 볼륨 상세 정보 |
| `PATCH` | `/api/v1/volumes/{volume_id}` | 소유 볼륨 이름 변경 (`in-use` 허용) |
| `POST` | `/api/v1/volumes` | 볼륨 생성 (분당 10회) |
| `POST` | `/api/v1/volumes/{volume_id}/extend` | 볼륨 용량 확장 (분당 10회) |
| `DELETE` | `/api/v1/volumes/{volume_id}` | 볼륨 삭제 |
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | error/error_deleting 상태 볼륨 강제 삭제 (관리자) |

### GET /api/v1/volumes

![볼륨 목록](../../assets/volume-list.png)
*Cinder 볼륨 목록 — 크기·상태(available/in-use)·연결된 인스턴스·볼륨 타입 확인*

프로젝트의 Cinder 볼륨 목록을 반환합니다. 응답은 약 15초간 캐시됩니다(`ttl_fast`). `?refresh=true`로 캐시를 무시할 수 있습니다.

목록 메뉴, 목록 SlidePanel, `/dashboard/volumes/{id}` 상세는 같은 작업 조건을 적용합니다. 상세에서 연결 가능한 볼륨은 `인스턴스에 연결`을 제공하고, 두 상세 화면의 작업 메뉴에서는 이름 변경, 부팅 가능한 `available` 볼륨의 VM 부팅, `available`/`in-use` 볼륨의 용량 확장·백업 생성, 설정에서 활성화한 스냅샷 생성, `available` 볼륨의 이전, 삭제를 사용할 수 있습니다. 연결된 볼륨의 일반 삭제는 비활성화하고, 시스템 관리자의 `error`/`error_deleting`/`deleting` 볼륨에서만 강제 삭제를 제공합니다. 작업은 기존 생성·이전 다이얼로그와 VM 생성 마법사를 사용하며, 용량 확장·스냅샷 생성·백업 요청 후 상세와 열린 목록을 새로고침합니다. 목록 메뉴의 `연결`은 상세를 열고, 상세의 `인스턴스에 연결`은 연결 대상을 선택합니다.

자동 백업은 즉시 활성화·비활성화하는 토글 대신 `autoPolicy.settings` 카탈로그의 `자동 백업 설정` 링크(영어: `Auto Backup settings`)를 제공합니다. 데스크톱 목록 열과 모든 화면 폭의 공통 목록·상세 작업 메뉴는 `/dashboard/volumes/backups?auto-backup=${encodeURIComponent(volume.id)}`로 이동하며, 백업 화면에서 현재 프로젝트의 볼륨 목록·권한 확인 후 해당 볼륨을 미리 선택합니다. 링크에는 인증 토큰이나 프로젝트 전환 정보를 넣지 않습니다. 목록 controller는 자동 백업 설정을 조회하거나 변경하지 않으므로 설정 조회 실패를 비활성 상태로 표시하지 않습니다. 일정·보존 설정의 검토와 저장은 기존 백업 화면의 정책 편집기가 담당합니다.

연결된 인스턴스 이름은 현재 프로젝트의 인스턴스 상세에서 확인하고 UUID를 함께 표시합니다. 이름 조회가 실패하면 다른 프로젝트의 이름을 추측하지 않고 UUID와 조회 불가 상태를 표시합니다.

**응답 (200 OK)** — `VolumeInfo[]` 배열

```json
[
  {
    "id": "uuid-string",
    "name": "volume-name",
    "status": "in-use",
    "size": 50,
    "volume_type": "ceph",
    "attachments": [
      {
        "server_id": "uuid-string",
        "device": "/dev/vdb"
      }
    ],
    "bootable": false,
    "volume_image_metadata": null
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 볼륨 UUID |
| `name` | string | 볼륨 이름 |
| `status` | string | 상태 (`available`, `in-use`, `error`, `error_deleting` 등) |
| `size` | integer | 크기 (GB) |
| `volume_type` | string\|null | 볼륨 타입 |
| `attachments` | array | 연결 정보 (`server_id`, `device` 등) |
| `bootable` | boolean | 부팅 가능 볼륨 여부 |
| `volume_image_metadata` | object\|null | 이미지에서 생성된 경우의 메타데이터 |

**오류**

| 상태 | 원인 |
|------|------|
| `500` | 볼륨 목록 조회 실패 |

### GET /api/v1/volumes/{volume_id}

특정 볼륨의 상세 정보를 반환합니다. 조회 전 소유권을 검증합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답 (200 OK)** — `VolumeInfo` 객체

**오류**

| 상태 | 원인 |
|------|------|
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |

### PATCH /api/v1/volumes/{volume_id}

현재 프로젝트 소유 볼륨의 이름만 수정합니다. 쓰기 권한과 소유 프로젝트를 확인하며 연결 중인 `in-use` 볼륨도 이름을 바꿀 수 있습니다. 공백을 제거한 이름은 1~255자여야 합니다.

**요청 본문** — `{ "name": "새 볼륨 이름" }`

**응답 (200 OK)** — 변경 후 `VolumeInfo` 객체. 목록 캐시를 무효화하고 변경 성공·실패를 활동 기록에 남깁니다.

| 상태 | 원인 |
|------|------|
| `403` | 프로젝트 쓰기 권한이 없음 또는 Cinder가 변경을 거부함 |
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |
| `409` | Cinder가 현재 상태의 변경을 거부함 |
| `422` | 이름이 공백이거나 255자를 초과함 |
| `500`/`502` | 볼륨 조회 또는 Cinder 서비스 실패 |

### POST /api/v1/volumes

새 Cinder 볼륨을 생성합니다. **속도 제한: 분당 10회**

**요청 본문** — `CreateVolumeRequest`

```json
{
  "name": "string (필수, 1~255자)",
  "size_gb": 50,
  "availability_zone": "string (선택)"
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `name` | string | 예 | 1~255자 | 볼륨 이름 |
| `size_gb` | integer | 예 | 1~16384 | 크기 (GB) |
| `availability_zone` | string | 아니오 | | 가용 영역 |

**응답 (201 Created)** — `VolumeInfo` 객체

**오류**

| 상태 | 원인 |
|------|------|
| `422` | 요청 본문 검증 실패 (이름 길이, 크기 범위 등) |
| `429` | 분당 생성 한도 초과 |
| `500` | 볼륨 생성 실패 |

### DELETE /api/v1/volumes/{volume_id}

볼륨을 삭제합니다. `in-use`(인스턴스에 부착된) 상태의 볼륨은 삭제할 수 없으며, 먼저 분리해야 합니다. 삭제 전 소유권을 검증합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답**: `204 No Content`

**오류**

| 상태 | 원인 |
|------|------|
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |
| `500` | 삭제 실패 (부착 상태, 종속 스냅샷/백업 등) |

---

## 2. 볼륨 확장

### POST /api/v1/volumes/{volume_id}/extend

볼륨 용량을 확장합니다. **속도 제한: 분당 10회**

프로젝트 API는 available/unattached 볼륨 또는 모든 attachment의 Nova 서버가 같은 effective project 소유이며 `SHUTOFF`, 실제 power state `4`, 명시적 idle task, 상호 일치하는 volume attachment일 때만 확장합니다. 시스템 관리자도 이 프로젝트 API의 소유권을 우회하지 않습니다. 마지막 Nova 확인 뒤 Cinder owner/status/size/attachments를 다시 확인하고 변경이 있으면 거부합니다. 별도 global admin endpoint의 계약은 변경하지 않습니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**요청 본문** — `ProjectExtendVolumeRequest`

```json
{
  "new_size": 100
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `new_size` | integer | 예 | strict integer, `1..2147483647`, 현재 크기보다 커야 함 | 새 용량 (GB). bool·문자열·소수·축소를 거부 |

**응답 (200 OK)** — 요청 뒤 제공자에서 다시 읽은 실제 `VolumeInfo`. 비동기 `extending` 중이면 이전 크기를 반환할 수 있으며 요청한 크기로 낙관적으로 덮어쓰지 않습니다. 접수는 capacity 확장 완료나 guest 파일시스템 성장 증거가 아닙니다. 게스트 재부팅/재검색과 파티션·LVM·파일시스템 확장은 OS/도구 구성에 맞게 별도 확인해야 하며 API는 guest 작업을 실행하지 않습니다. 인스턴스의 root/data 볼륨 행과 기존 볼륨 목록·상세는 동일한 scoped modal을 사용합니다.

**오류**

| 상태 | 원인 |
|------|------|
| `400` | 새 크기가 현재 크기 이하이거나 Cinder 확장 실패 |
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |
| `403` | 프로젝트 쓰기 권한이 없음 |
| `409` | 연결·상태·전원·task·상호 연결을 확인할 수 없거나 최종 상태가 변경됨 |
| `422` | 엄격한 양의 정수·범위 검증 실패 |
| `502` | provider 조회 실패 또는 접수 뒤 실제 결과 확인 불가 |
| `429` | 분당 확장 한도 초과 |

---

## 3. 볼륨 강제 삭제 및 삭제 복구 진단

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | error/error_deleting 상태 볼륨 강제 삭제 |
| `GET` | `/api/v1/admin/volumes/{volume_id}/delete-diagnostics` | 관리자 전용 삭제 실패 원인 진단 |
| `POST` | `/api/v1/admin/volumes/{volume_id}/recover-delete` | 관리자 전용 진단 기반 자동 삭제 복구 |

### POST /api/v1/volumes/{volume_id}/force-delete

**관리자 전용** (`require_admin`). `error` 또는 `error_deleting` 상태의 볼륨을 강제 삭제합니다. 현재 구현은 Cinder의 `os-reset-status`로 상태를 `error`로 재설정한 뒤 `os-force_delete`를 수행합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답**: `204 No Content`

**오류**

| 상태 | 원인 |
|------|------|
| `403` | 관리자 권한 없음 |
| `500` | 강제 삭제 실패 |

### GET /api/v1/admin/volumes/{volume_id}/delete-diagnostics

관리자 전용 엔드포인트입니다. `error_deleting` 등 삭제 실패 상태의 볼륨에 대해 Cinder 상태, attachment, snapshot/backup 종속성, Cinder messages를 확인하고 자동 복구 가능 여부를 반환합니다. Cinder messages 조회는 best-effort이며 실패해도 진단은 계속됩니다.

### POST /api/v1/admin/volumes/{volume_id}/recover-delete

관리자 전용 엔드포인트입니다. 서버가 진단을 다시 수행한 뒤 attachment와 snapshot/backup 종속성이 없는 경우에만 `reset_status(error, detached)` → 일반 삭제 → 삭제 검증 → 필요 시 force-delete → 삭제 검증 순서로 실행합니다. 스냅샷/백업 종속성은 자동 삭제하지 않으며, 존재하면 `blocked` 결과로 반환하므로 관리자가 별도 명시 작업으로 보존 또는 삭제를 결정해야 합니다.

---

## 4. 볼륨 이전 (Transfer)

같은 OpenStack cloud·region의 **같은 도메인 또는 다른 도메인의 프로젝트**로 볼륨 소유권을 이전합니다. 독립된 다른 클라우드로 데이터를 복사하는 기능은 아닙니다.

송신 프로젝트에서 미연결 `available` 볼륨의 **이전**을 생성해 transfer ID와 auth key를 전달합니다. 수신 프로젝트를 선택한 뒤 볼륨 목록 상단의 **볼륨 수신**에서 전체 ID를 검색하고, 출발 도메인·프로젝트와 볼륨 정보를 확인한 다음 auth key로 수신합니다. 수신 프로젝트에 기존 볼륨이 없어도 사용할 수 있습니다. **대기 중인 이전**은 현재 프로젝트가 보낸 전송만 조회·취소합니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/volumes/transfers` | 현재 프로젝트의 대기 전송 목록 |
| `GET` | `/api/v1/volumes/transfer/{transfer_id}` | 모든 도메인·프로젝트에서 정확한 ID 하나의 대기 전송 조회 |
| `POST` | `/api/v1/volumes/{volume_id}/transfer` | 소유 미연결 볼륨의 이전 생성 |
| `POST` | `/api/v1/volumes/transfer/{transfer_id}/accept` | auth key로 현재 프로젝트에 수신 |
| `DELETE` | `/api/v1/volumes/transfer/{transfer_id}` | 현재 프로젝트 소유 전송 취소 |

조회·수신·취소의 `transfer_id`는 소문자·하이픈을 포함한 전체 canonical UUID여야 합니다. 부분·이름·접두사 검색이나 전체 도메인 전송 목록은 제공하지 않습니다. 조회/목록에는 로그인, 변경에는 현재 프로젝트의 쓰기 권한이 필요합니다. 모든 transfer 응답에는 `Cache-Control: no-store, private`와 `Pragma: no-cache`를 적용합니다.

### GET /api/v1/volumes/transfers

사용자의 실제 scoped credential로 현재 프로젝트의 대기 전송만 조회합니다. 시스템 관리자가 다른 프로젝트를 선택해도 관리자 home 프로젝트나 전체 프로젝트 목록으로 대체하지 않습니다. 각 항목은 `{id, name, volume_id, created_at}`이며 auth key는 반환하지 않습니다. 공급자가 다른 프로젝트 항목이나 불명확한 소유 정보를 반환하면 빈 목록으로 숨기지 않고 오류로 처리합니다.

### GET /api/v1/volumes/transfer/{transfer_id}

현재 configured operator 연결은 정확한 native transfer, 해당 볼륨 및 Keystone 출발 프로젝트·도메인을 **읽기만** 합니다. 출발 프로젝트 membership은 필요하지 않습니다. 실제 `awaiting-transfer`·미연결 볼륨과 일치하는 ID/소유권을 확인한 뒤 아래 필드만 반환합니다. Auth key, 사용자, endpoint, volume metadata 및 attachment 본문은 공개하지 않습니다.

**응답 (200 OK)**

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "name": "data-handoff",
  "volume_id": "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  "created_at": "2026-10-14T01:01:00Z",
  "volume_name": "research-data",
  "size": 24,
  "volume_type": "ceph_hdd",
  "status": "awaiting-transfer",
  "source_project": { "id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "name": "Research" },
  "source_domain": { "id": "11111111111111111111111111111111", "name": "Source domain" }
}
```

이름·용량·유형은 표시용 snapshot이며 수신 권한을 부여하지 않습니다. 검색 ID가 바뀌면 기존 결과·키를 폐기하고 새 조회를 요구합니다. 존재하지 않거나 이미 수락/취소되었거나 더 이상 대기 중이 아닌 전송은 `404`입니다. 소유자/출발 범위 불명·불일치는 `502`, operator 인증·정책·서비스 장애는 `503`입니다. Operator에 Cinder 단건 전송/볼륨과 Keystone 프로젝트/도메인 조회 권한이 필요하며 권한을 자동 변경하거나 실패를 우회하지 않습니다.

### POST /api/v1/volumes/{volume_id}/transfer

현재 프로젝트가 소유한 `available`·미연결 볼륨만 허용합니다. **인스턴스를 자동 분리하거나 실패 후 다시 연결하지 않습니다.** 연결된 볼륨은 먼저 사용자가 안전하게 분리해야 합니다. 시스템 관리자도 출발 프로젝트 소유권을 우회하지 않습니다.

**요청 본문** — 선택 가능: `{ "name": "data-handoff" }`. 이름은 최대255자입니다.

**응답 (201 Created)** — `{ "id": "transfer-uuid", "name": "data-handoff", "volume_id": "volume-uuid", "created_at": null, "auth_key": "issued-key" }`.

Auth key는 이 응답에서만 발급됩니다. 생성 화면에서 ID와 키를 각각 복사하고 안전한 경로로 전달하세요. 목록 새로고침은 발급 화면을 닫지 않습니다. 닫기·해제·사용자/프로젝트/토큰·쓰기 권한 전환은 키를 폐기합니다. 분실하거나 발급 응답을 받지 못한 경우 현재 프로젝트의 대기 전송을 취소한 뒤 다시 생성할 수 있습니다. 서버와 브라우저는 전송 키를 영속화하지 않습니다.

### POST /api/v1/volumes/transfer/{transfer_id}/accept

**요청 본문** — `{ "auth_key": "issued-key" }`. 키는 필수·비공백·최대512자이며 URI에 넣지 않습니다. 잘못된 입력의 `422` 응답도 키를 되돌려 주지 않습니다.

수락 직전 native 전송·상태를 다시 확인하고 출발=대상 프로젝트는 `409`로 거부합니다. **수신 사용자의 실제 사용자 ID와 선택한 대상 프로젝트가 일치하는 Keystone scoped credential**로만 Cinder에 제출합니다. Operator/service 자격으로 수락하지 않으며 Cinder가 키·쿼터·native policy를 검사합니다. 반환된 ID와 실제 대상 프로젝트 소유권을 다시 읽어 확인한 뒤 성공으로 보고합니다.

**응답 (200 OK)** — `{ "id": "transfer-uuid", "name": "data-handoff", "volume_id": "volume-uuid" }`.

생성·취소는 출발 볼륨 목록, 수락은 출발·대상 볼륨 목록 cache를 무효화합니다. 응답 유실·수락 후 readback 오류도 두 목록을 무효화하지만 POST를 재전송하지 않습니다. 오류 뒤 대상 목록을 새로 조회해 실제 소유권을 확인하세요. 이전된 볼륨의 게스트·데이터 일관성이나 애플리케이션 동작을 보장하지 않습니다.

### DELETE /api/v1/volumes/transfer/{transfer_id}

현재 프로젝트 소유의 미연결 대기 전송만 해당 사용자의 scoped credential로 취소합니다. 이미 수락되거나 취소된 전송은 `404`; 다른 출발 프로젝트의 전송은 native policy에 따라 `403` 또는 소유권 재검사에서 `404`입니다. **응답: `204 No Content`**.

### 오류

| 상태 | 원인 |
|------|------|
| `401` | 로그인 자격 없음 |
| `403` | 현재 쓰기/프로젝트 scope·native 권한 없음 또는 잘못된 auth key |
| `404` | 전송/볼륨 부재, 소비된 전송 또는 현재 출발 프로젝트 소유가 아님 |
| `409` | 연결/상태 변경, 출발=대상, native 상태·쿼터 충돌 |
| `413` | Cinder 대상 프로젝트 쿼터 부족 |
| `422` | 전체 UUID 또는 이름·키 입력 제약 위반 |
| `502`/`503` | 공급자 identity/readback 불일치·장애 또는 operator 조회 불가 |

SDK3.3.0은 지원 microversion에 따라 `/os-volume-transfer` 또는3.55 이상의 `/volume-transfers` native API를 선택합니다. 스냅샷·암호화 볼륨 지원과 정책·쿼터는 Cinder에 따르며 앱에서 우회하거나 별도 복사를 하지 않습니다. [Cinder native API reference](https://docs.openstack.org/api-ref/block-storage/v3/index.html#volume-transfers-os-volume-transfer).

---

## 5. 볼륨 백업

> 태그: `volume-backups`  
> 기본 경로: `/api/v1/volumes/backups`

볼륨 백업 메뉴·화면·인라인 작업·자동 백업은 브라우저별 베타 선호와 무관하게 노출됩니다. 과거 `afterglow.beta.volumeBackups=false` 값은 더 이상 적용되지 않습니다. 프로젝트가 바뀌면 이전 백업 목록과 늦은 응답을 폐기합니다. UI 가시성은 Cinder backup service의 실제 가용성이나 복원 성공을 뜻하지 않으므로 운영 배포에서는 서비스 `enabled`/`up` 상태와 실제 백업·복원을 별도로 확인해야 합니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/volumes/backups` | 볼륨 백업 목록 |
| `GET` | `/api/v1/volumes/backups/{backup_id}` | 백업 상세 정보 |
| `POST` | `/api/v1/volumes/backups` | 백업 생성 |
| `POST` | `/api/v1/volumes/backups/{backup_id}/restore` | 백업 복원 |
| `DELETE` | `/api/v1/volumes/backups/{backup_id}` | 백업 삭제 |

### GET /api/v1/volumes/backups

프로젝트의 Cinder 볼륨 백업 목록을 반환합니다. 응답은 캐시됩니다(`ttl_slow`). `?refresh=true`로 캐시를 무시할 수 있습니다.

**응답 (200 OK)** — 배열

```json
[
  {
    "id": "uuid-string",
    "name": "backup-name",
    "status": "available",
    "size": 50,
    "volume_id": "uuid-string",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 백업 UUID |
| `name` | string | 백업 이름 |
| `status` | string | 상태 (`available`, `creating`, `restoring`, `error` 등) |
| `size` | integer | 크기 (GB) |
| `volume_id` | string | 원본 볼륨 UUID |
| `created_at` | string | 생성 일시 (ISO 8601) |

### GET /api/v1/volumes/backups/{backup_id}

특정 백업의 상세 정보를 반환합니다. 조회 전 백업 소유권을 검증합니다.

**오류**: `404` (백업이 없거나 소유 프로젝트가 아님)

### POST /api/v1/volumes/backups

새 볼륨 백업을 생성합니다. 원본 볼륨의 소유권을 검증합니다.

사용 중(`in-use`)인 볼륨은 `force: true`를 명시해야 합니다. 서버가 소유권과 현재 Cinder 상태를 확인하며, 강제 선택이 없으면 Cinder 생성 요청 전에 `400`과 활성화 안내를 반환합니다. 볼륨 목록/상세 및 백업 목록의 생성창은 일관성 경고와 기본 미선택 체크박스를 표시하고 선택해야 제출할 수 있습니다. 원본을 바꾸거나 창을 다시 열면 동의가 초기화되며, `available` 볼륨은 강제하지 않습니다.

`force`는 연결 중 백업을 허용하는 옵션이지 원본의 분리·삭제·덮어쓰기가 아닙니다. 쓰기 중 복사한 데이터는 일관성이 깨질 수 있으며 DB·애플리케이션 일관성과 복구 가능성을 보장하지 않습니다. Force 옵션 자체를 crash-consistent snapshot의 보장으로 해석하지 않으며 백업 I/O가 성능에 영향을 줄 수 있습니다. 필요한 경우 쓰기를 정지/flush하거나 서비스별 백업 절차를 수행하고 별도 복원 검증을 합니다. VM을 정지해도 attachment가 남아 `in-use`이면 강제 선택이 필요합니다. 활동 기록의 기존 `extra`에 요청한 `force` 값을 남깁니다. 수동 강제 선택은 기존 자동 백업 정책으로 승계하지 않습니다.

**요청 본문** — `CreateBackupRequest`

```json
{
  "volume_id": "uuid-string (필수)",
  "name": "string (필수)",
  "description": "string (선택)",
  "incremental": false,
  "force": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `volume_id` | string | 예 | 백업할 볼륨 UUID |
| `name` | string | 예 | 백업 이름 |
| `description` | string | 아니오 | 설명 |
| `incremental` | boolean | 아니오 | 증분 백업 여부 (기본값: `false`) |
| `force` | boolean | 아니오 | 연결 중 백업의 명시적 허용. `in-use`이면 `true` 필수, 기본값 `false` |

**응답 (201 Created)**

```json
{
  "id": "uuid-string",
  "name": "backup-name",
  "status": "creating",
  "volume_id": "uuid-string"
}
```

**오류**

| 상태 | 원인 |
|------|------|
| `400` | `in-use` 볼륨인데 강제 백업을 명시적으로 활성화하지 않음 |
| `404` | 원본 볼륨이 없거나 소유 프로젝트가 아님 |
| `4xx/5xx` | 하위 Cinder API 오류 |
| `500` | 백업 생성 실패 |

### POST /api/v1/volumes/backups/{backup_id}/restore

백업을 복원합니다. 백업 소유권을 검증하며, `volume_id`를 지정한 경우 대상 볼륨의 소유권도 검증합니다.

**요청 본문** — `RestoreBackupRequest` (선택, 생략 가능)

```json
{
  "volume_id": "uuid-string (선택, 기존 볼륨에 덮어쓸 경우)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `volume_id` | string | 아니오 | 기존 볼륨에 덮어쓸 경우 해당 볼륨 UUID. 생략 시 새 볼륨으로 복원 |

**응답 (200 OK)**

```json
{
  "restore": {
    "backup_id": "uuid-string",
    "volume_id": "uuid-string",
    "volume_name": "restored-volume"
  }
}
```

### DELETE /api/v1/volumes/backups/{backup_id}

백업을 삭제합니다. 소유권을 검증합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `backup_id` | path | string | 예 | 백업 UUID |

**응답**: `204 No Content`

---

## 6. 자동 백업

`볼륨 → 볼륨 백업 → 자동 백업 설정`에서 원본·실행 시각·시간대·일/주/월 보존과 활성 상태를 저장한다. 목록·공용 상세의 같은 설정 메뉴는 `/dashboard/volumes/backups?auto-backup=<volume_id>`로 이동한다. **저장·재개 직후에는 백업을 만들지 않으며 응답의 다음 예정 시각부터 실행한다.** 예약 시각은 해당 IANA 시간대의 calendar 기준이며 주기는 24시간/7일/30일 경과가 아니다.

### 다중 컨트롤러의 예약·실행 분배

같은 Redis/Valkey primary·logical DB·`afterglow:auto_backup` namespace를 사용하는 backend process들은 자동으로 참여한다. Controller별 cron이나 별도 worker service를 만들지 않는다. Redis server-time45초 membership/leader lease와 독립10초 heartbeat로 리더 하나를 유지하며, 리더만15초 간격으로 전체 정책을 확인한다. 실행 loop는 스캔과 독립이어서 리더의 SDK 요청이 느려도 다른 작업의 배정은 계속된다.

새 due 작업과 장애 소유자의 작업은 살아 있는 worker에 균등 배정하고, 정상 소유자의 pending/active 배정은 유지한다. 각 worker는 자기 작업만 가져가며 현재 membership·assignment와 renewable90초 volume lease를 원자적으로 확인한다. 같은 볼륨/예약 slot은 한 번만 제출하며 서로 다른 볼륨은 분산 실행할 수 있다. Idle·일시 중지·0tier에는 새 SDK 연결을 열지 않는다(이미 접수된 작업의 완료 관측은 계속한다).

정상 종료는 SDK drain/close와 lease release 뒤 participant를 제거한다. Crash는45초 membership/leader 만료와 다음 heartbeat/poll 뒤 인계하되 해당 볼륨의 남은90초 lease를 기다린다. 늦은 claim 응답·Redis 장애·lost incarnation은 fail-closed이며 재참여는 새 identity를 쓴다. Cinder가 접수하고 응답을 잃어도 생성 POST의 SDK 자동 retry를 하지 않고 `unknown` journal을 조회해 확인한다.

분배 단위는 API process이며 서로 다른 worker 수를 가진 controller의 물리 부하가 같다는 뜻은 아니다. 모든 replica가 이 구현을 사용하고 공유 Redis의 policy/slot/journal 데이터를 영속·보존해야 한다. 독립 Redis, key 삭제, failover 데이터 유실에서는 중복 방지를 보장하지 않는다. 운영 backup storage·복원·배포 검증과 로컬 분산 실행 증거는 [검증 가이드](../testing.md)에 분리한다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/v1/volumes/backups/auto-backup/configs` | 현재 프로젝트의 저장된 정책과 원본 조회 상태 |
| `GET` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 현재 소유 볼륨의 정책 조회 |
| `POST` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 정책 생성·수정·일시 중지·재개 |
| `DELETE` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 정책만 제거; 기존 백업 보존 |

### POST /api/v1/volumes/backups/auto-backup/{volume_id}

쓰기 권한과 fresh 원본의 **정확한 현재 프로젝트 소유권**을 확인한다. 시스템 관리자도 다른 프로젝트 원본을 예약할 수 없다. 활성 정책의 원본은 `available` 또는 `in-use`여야 하며 `in-use`에는 별도로 저장한 `force=true`가 필요하다.

**요청 본문** — `AutoBackupRequest` (생략 시 아래 기본값)

```json
{
  "enabled": true,
  "max_daily": 2,
  "max_weekly": 2,
  "max_monthly": 1,
  "schedule_time": "03:00",
  "timezone": "UTC",
  "weekly_day": 0,
  "monthly_day": 1,
  "force": false
}
```

| 필드 | 타입·범위 | 기본값 | 의미 |
|---|---|---|---|
| `enabled` | boolean | `true` | `false`는 설정을 보존한 일시 중지 |
| `max_daily` | integer, 0–30 | `2` | 매일 실행 및 보존 개수; 0은 미실행 |
| `max_weekly` | integer, 0–30 | `2` | 지정 요일의 주별 실행 및 보존 개수 |
| `max_monthly` | integer, 0–30 | `1` | 지정 일자의 월별 실행 및 보존 개수 |
| `schedule_time` | `HH:mm`, 00:00–23:59 | `03:00` | 시간대 내 wall-clock 실행 시각 |
| `timezone` | 유효한 IANA 시간대 | `UTC` | 예: `Asia/Seoul` |
| `weekly_day` | integer, 0–6 | `0` | 월요일=0, 일요일=6 |
| `monthly_day` | integer, 1–28 | `1` | 매월 존재하는 실행일 |
| `force` | boolean | `false` | 이 정책의 이후 예약 실행에 대한 강제 백업 동의 |

활성 정책에는 하나 이상의 양수 보존 개수가 필요하다. 0인 tier의 기존 백업은 삭제하지 않는다. 겹친 시각에는 `monthly > weekly > daily`의 한 개 **전체 백업**만 생성하며 해당 tier에만 계산한다. 서버 중단으로 지난 예약은 한 번으로 합치고 다음 시각을 현재 이후로 이동하며 밀린 백업을 연속 생성하지 않는다. DST에서는 시간이 건너뛰거나 반복될 수 있으므로 [CronTrigger의 wall-clock 주의](https://apscheduler.readthedocs.io/en/3.x/modules/triggers/cron.html#daylight-saving-time-behavior)를 확인하거나 UTC를 사용한다.

`force`는 수동 백업의 일회성 동의를 승계하지 않는다. 연결 중 백업을 허용할 뿐 원본을 분리·덮어쓰거나 게스트 쓰기를 멈추지 않으며 DB·애플리케이션 일관성과 복원 성공을 보장하지 않는다.

**응답**: `201 Created` — 저장된 정책. 입력 필드와 `project_id`, `volume_id`, `created_at`, `updated_at`, `schema_version`, `revision`, `next_run_at`, `next_tier`, `last_run_at`, `last_status`, `last_backup_id`, `last_error`를 반환한다. 실행 시각은 UTC ISO 8601이고 화면은 정책 시간대로 표시한다. `last_status`는 `never | creating | available | error | unknown | skipped`다. Cinder 접수·`creating`은 완료가 아니며 `unknown`은 요청 결과를 확정할 수 없음을 뜻한다. 자동 재발행 없이 기존 ID/정확한 이름으로 관측한다.

**오류**: `400` (활성 원본 상태/강제 동의), `403` (쓰기 권한 또는 공급자 권한), `404` (원본 없음·소유권 불일치), `422` (설정 검증), `503` (Redis·원본 일시 조회 장애). `enabled=false`로 같은 입력을 저장하면 일시 중지, `true`로 저장하면 새 미래 시각부터 재개한다.

### 정책 조회와 원본 부재

`GET .../{volume_id}`는 fresh 소유권과 저장 정책을 확인하며 원본/정책 부재·소유권 불일치는404다. `POST .../configs`는200 배열이다. 저장된 현재 프로젝트 정책은 원본이 사라지거나 읽을 수 없어도 보존하여 표시한다. 해당 행만 response-only `source_status=missing | not_owned | unavailable`, `source_available=false | null`, 안전한 `source_error`를 추가하고 기존 오류가 없으면 `last_error`에 같은 이유를 표시한다. 저장된 활성·보존·이력은 조회로 재작성하지 않는다.

### DELETE /api/v1/volumes/backups/auto-backup/{volume_id}

**응답**: `204 No Content`. 설정만 제거하며 Cinder 백업은 삭제하지 않는다. Fresh 소유권이 일치하거나, 원본이 authoritative404/None으로 없고 **원래 저장 identity가 정확한 현재 프로젝트·원본**인 경우에만 허용한다. 다른 소유자·소유권 누락은404, 공급자403은403, timeout/5xx는503이며 정책을 보존한다. 원본 부재를 일시 오류와 혼동하지 않는다.

보존 삭제는 새로운 백업의 `available` 확인 이후에만, 정확한 같은 프로젝트·원본의 관리 이름, 유효한 생성 시각, full이며 의존성이 명시적으로 없는 오래된 완료본에 한정한다. 수동·외부·pending·error·incremental·소유권/의존성 불명 항목은 삭제하지 않는다. 삭제 직전 원본·백업·현재 정책 revision/활성 상태·실행 lease를 재검증한다.

기존 정상 정책은 활성 상태·보존·이력·확장 필드를 유지하며 UTC03:00/월요일/매월1일과 기존 `force`(없으면false)를 한 번 정규화한다. 잘못된 저장 JSON·일정은 원문을 보존한 disabled/error 표시로 실행을 막으며, 명시적인 수정 저장으로 복구한다. 원본 삭제 후 정책 제거는 백업 보존과 별개다.

---

## 7. 볼륨 스냅샷

> 태그: `volume-snapshots`  
> 기본 경로: `/api/v1/volume-snapshots`

백업과 달리 스냅샷은 원본 볼륨과 동일한 Ceph 풀에 상주하는 시점 복제본입니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/volume-snapshots` | 스냅샷 목록 |
| `GET` | `/api/v1/volume-snapshots/{snapshot_id}` | 스냅샷 상세 정보 |
| `POST` | `/api/v1/volume-snapshots` | 스냅샷 생성 |
| `DELETE` | `/api/v1/volume-snapshots/{snapshot_id}` | 스냅샷 삭제 |

### GET /api/v1/volume-snapshots

프로젝트의 Cinder 볼륨 스냅샷 목록을 반환합니다. 응답은 캐시됩니다(`ttl_normal`).

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | query | string | 아니오 | 특정 볼륨의 스냅샷만 필터링 |
| `refresh` | query | boolean | 아니오 | 캐시 무시 여부 |

**응답 (200 OK)** — 배열

```json
[
  {
    "id": "uuid-string",
    "name": "snapshot-name",
    "status": "available",
    "size": 50,
    "volume_id": "uuid-string",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 스냅샷 UUID |
| `name` | string | 스냅샷 이름 |
| `status` | string | 상태 (`available`, `creating`, `error` 등) |
| `size` | integer | 크기 (GB) |
| `volume_id` | string | 원본 볼륨 UUID |
| `created_at` | string | 생성 일시 (ISO 8601) |

### GET /api/v1/volume-snapshots/{snapshot_id}

특정 스냅샷의 상세 정보를 반환합니다. 조회 전 소유권을 검증합니다.

**오류**: `404` (스냅샷이 없거나 소유 프로젝트가 아님)

### POST /api/v1/volume-snapshots

새 볼륨 스냅샷을 생성합니다. 원본 볼륨의 소유권을 검증합니다.

**요청 본문** — `CreateSnapshotRequest`

```json
{
  "volume_id": "uuid-string (필수)",
  "name": "string (필수)",
  "description": "string (선택)",
  "force": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `volume_id` | string | 예 | 스냅샷을 생성할 볼륨 UUID |
| `name` | string | 예 | 스냅샷 이름 |
| `description` | string | 아니오 | 설명 |
| `force` | boolean | 아니오 | `in-use` 상태의 볼륨도 강제 스냅샷 (기본값: `false`) |

**응답 (201 Created)**

**오류**

| 상태 | 원인 |
|------|------|
| `404` | 원본 볼륨이 없거나 소유 프로젝트가 아님 |
| `4xx/5xx` | Cinder API 오류를 상태 코드와 메시지 그대로 전달 |
| `500` | 스냅샷 생성 실패 |

### DELETE /api/v1/volume-snapshots/{snapshot_id}

스냅샷을 삭제합니다. 소유권을 검증합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `snapshot_id` | path | string | 예 | 스냅샷 UUID |

**응답**: `204 No Content`
