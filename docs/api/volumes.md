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
| `POST` | `/api/v1/volumes` | 볼륨 생성 (분당 10회) |
| `POST` | `/api/v1/volumes/{volume_id}/extend` | 볼륨 용량 확장 (분당 10회) |
| `DELETE` | `/api/v1/volumes/{volume_id}` | 볼륨 삭제 |
| `POST` | `/api/v1/volumes/{volume_id}/force-delete` | error/error_deleting 상태 볼륨 강제 삭제 (관리자) |

### GET /api/v1/volumes

![볼륨 목록](../../assets/volume-list.png)
*Cinder 볼륨 목록 — 크기·상태(available/in-use)·연결된 인스턴스·볼륨 타입 확인*

프로젝트의 Cinder 볼륨 목록을 반환합니다. 응답은 약 15초간 캐시됩니다(`ttl_fast`). `?refresh=true`로 캐시를 무시할 수 있습니다.

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

Ceph 온라인 확장을 지원하므로 `available` 볼륨은 물론 **`in-use`(인스턴스에 부착된) 볼륨도 무중단으로 확장**할 수 있습니다. 축소는 지원하지 않습니다 — 새 크기는 반드시 현재 크기보다 커야 합니다. 확장 전 소유권을 검증합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**요청 본문** — `ExtendVolumeRequest`

```json
{
  "new_size": 100
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `new_size` | integer | 예 | `> 0`, 현재 크기보다 커야 함 | 새 용량 (GB) |

**응답 (200 OK)** — 확장 후 `VolumeInfo` 객체

**오류**

| 상태 | 원인 |
|------|------|
| `400` | 새 크기가 현재 크기 이하이거나 Cinder 확장 실패 |
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |
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

볼륨의 소유권을 다른 프로젝트로 이전할 수 있습니다. 흐름은 **송신 측 이전 생성(create) → `auth_key` 공유 → 수신 측 수락(accept)** 순서입니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/volumes/transfers` | 이전 목록 |
| `POST` | `/api/v1/volumes/{volume_id}/transfer` | 이전 생성 |
| `POST` | `/api/v1/volumes/transfer/{transfer_id}/accept` | 이전 수락 |
| `DELETE` | `/api/v1/volumes/transfer/{transfer_id}` | 이전 취소 |

### GET /api/v1/volumes/transfers

현재 프로젝트의 볼륨 이전 목록을 반환합니다.

**응답 (200 OK)** — 배열

### POST /api/v1/volumes/{volume_id}/transfer

볼륨 소유권 이전 요청을 생성합니다. 응답의 `auth_key`는 수신 측 수락에 필요합니다.

볼륨이 인스턴스에 부착되어 있으면 **자동으로 detach한 뒤** `available` 상태를 기다렸다가 이전을 생성합니다. 이전 생성이 실패하면 detach했던 인스턴스에 볼륨을 다시 attach(rollback)합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 이전할 볼륨 UUID |

**요청 본문** — `CreateVolumeTransferRequest` (선택, 생략 가능)

```json
{
  "name": "string (선택) — 이전 이름"
}
```

**응답 (201 Created)**

```json
{
  "id": "transfer-uuid",
  "name": "transfer-name",
  "volume_id": "volume-uuid",
  "auth_key": "auth-key-string"
}
```

> ⚠️ `auth_key`는 생성 시에만 반환됩니다. 안전하게 보관하세요.

**오류**

| 상태 | 원인 |
|------|------|
| `404` | 볼륨이 없거나 소유 프로젝트가 아님 |
| `409` | 부착 볼륨 detach 실패 또는 detach 대기 시간 초과 |
| `500` | 이전 생성 실패 (실패 시 자동 rollback 시도) |

### POST /api/v1/volumes/transfer/{transfer_id}/accept

이전 요청을 수락하여 볼륨 소유권을 현재 프로젝트로 이전합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `transfer_id` | path | string | 예 | 이전 UUID |

**요청 본문** — `AcceptVolumeTransferRequest`

```json
{
  "auth_key": "string (필수) — 이전 생성 시 발급된 인증 키"
}
```

**응답 (200 OK)**

```json
{
  "id": "transfer-uuid",
  "volume_id": "volume-uuid"
}
```

**오류**

| 상태 | 원인 |
|------|------|
| `422` | `auth_key` 누락 |
| `500` | 이전 수락 실패 (잘못된 auth_key 포함) |

### DELETE /api/v1/volumes/transfer/{transfer_id}

이전 요청을 취소합니다. 이미 수락된 이전은 취소할 수 없습니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `transfer_id` | path | string | 예 | 이전 UUID |

**응답**: `204 No Content`

---

## 5. 볼륨 백업

> 태그: `volume-backups`  
> 기본 경로: `/api/v1/volumes/backups`

저장된 브라우저 선호가 없으면 프론트엔드는 볼륨 백업 메뉴와 화면을 기본 노출합니다. 계정 설정에서 현재 브라우저에 한해 다시 끌 수 있으며, 명시적으로 저장한 `false` 선호는 유지됩니다. 이 UI 상태는 Cinder backup service의 실제 가용성을 뜻하지 않으므로 운영 배포에서는 서비스 `enabled`/`up` 상태를 별도로 확인해야 합니다.

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

**요청 본문** — `CreateBackupRequest`

```json
{
  "volume_id": "uuid-string (필수)",
  "name": "string (필수)",
  "description": "string (선택)",
  "incremental": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `volume_id` | string | 예 | 백업할 볼륨 UUID |
| `name` | string | 예 | 백업 이름 |
| `description` | string | 아니오 | 설명 |
| `incremental` | boolean | 아니오 | 증분 백업 여부 (기본값: `false`) |

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
| `404` | 원본 볼륨이 없거나 소유 프로젝트가 아님 |
| `4xx/5xx` | Manila/Cinder API 오류를 상태 코드와 메시지 그대로 전달 |
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

볼륨의 정기 자동 백업을 설정하고 관리합니다. 자동 백업 설정은 Afterglow가 관리하며, **활성화 즉시 첫 번째 백업 사이클을 백그라운드에서 실행**합니다. 이후 사이클은 보관 정책(daily/weekly/monthly)에 따라 스케줄러가 순환시킵니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/volumes/backups/auto-backup/configs` | 프로젝트의 자동 백업 설정 목록 |
| `GET` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 볼륨 자동 백업 설정 조회 |
| `POST` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 자동 백업 활성화 |
| `DELETE` | `/api/v1/volumes/backups/auto-backup/{volume_id}` | 자동 백업 비활성화 |

### POST /api/v1/volumes/backups/auto-backup/configs

현재 프로젝트의 모든 자동 백업 설정 목록을 반환합니다.

**응답 (200 OK)** — 배열

### GET /api/v1/volumes/backups/auto-backup/{volume_id}

지정된 볼륨의 자동 백업 설정을 조회합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답 (200 OK)** — 자동 백업 설정 객체

**오류**: `404` (설정이 없음)

### POST /api/v1/volumes/backups/auto-backup/{volume_id}

지정된 볼륨에 자동 백업을 활성화합니다. 활성화 직후 첫 백업 사이클이 백그라운드에서 시작됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**요청 본문** — `AutoBackupRequest` (선택, 생략 시 기본값 적용)

```json
{
  "max_daily": 2,
  "max_weekly": 2,
  "max_monthly": 1
}
```

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `max_daily` | integer | 아니오 | `2` | 보관할 일간 백업 수 |
| `max_weekly` | integer | 아니오 | `2` | 보관할 주간 백업 수 |
| `max_monthly` | integer | 아니오 | `1` | 보관할 월간 백업 수 |

**응답**: `201 Created` — 생성된 자동 백업 설정 객체

### DELETE /api/v1/volumes/backups/auto-backup/{volume_id}

지정된 볼륨의 자동 백업을 비활성화합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `volume_id` | path | string | 예 | 볼륨 UUID |

**응답**: `204 No Content`

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
