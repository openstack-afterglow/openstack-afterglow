---
title: 파일 스토리지 (File Storage)
nav_order: 55
parent: API 레퍼런스
---

# 파일 스토리지 (File Storage) API

> 태그: `file-storage`  
> 기본 경로: `/api/v1/file-storage`

Manila 공유 파일 시스템(CephFS/NFS)을 관리합니다.

> **활성화 조건:** `afterglow.conf [services] manila = true`.
> Manila는 선택 서비스이므로, 비활성화 상태에서는 이 라우터 자체가 마운트되지 않아
> 모든 `/api/v1/file-storage*` 경로가 `404`를 반환합니다.

> **공유 백업 미지원:** 이 경로는 공유 생성·조회·접근 관리를 제공하며 share-backup 생성·복원 API는 제공하지 않습니다. 운영 Manila의 실험적 share-backup API(2.80+, experimental header)는 확인됐으나 `manila-data`의 독립 NFS 백업 저장소와 데이터 노드 access IP가 설정되지 않았습니다. 현재 기본 NFS backup driver는 native CEPHFS 공유를 mount할 수도 없습니다. 저장소·드라이버 준비와 실제 생성·복원 검증 전에는 File Storage 공유 스냅샷을 백업으로 간주하지 마세요.

콘솔 직접 상세의 접근 규칙과 복사 가능한 CephX key는 share ID·auth token·project에 귀속됩니다. 다른 share 또는 인증 scope로 전환하면 이전 규칙을 즉시 숨기고 새 조회 전까지 revoke 액션을 제공하지 않습니다. 같은 scope의 background refresh는 기존 행을 유지하며, 오래된 응답·확인 결과가 새로운 share에 적용되지는 않습니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

> **소유권 모델:** Afterglow는 share의 `metadata.union_project_id`로 소유 프로젝트를 추적합니다.
> 단건 조회/변경 시 이 값이 호출자 프로젝트와 다르면 `404`(존재 은폐)를 반환합니다.
> 단, 시스템 관리자와 `is_public` share는 cross-project 노출이 정상이므로 검증에서 면제됩니다.

---

## 목차

1. [파일 스토리지 CRUD](#1-파일-스토리지-crud)
2. [접근 규칙 (Access Rules)](#2-접근-규칙-access-rules)
3. [쿼터·타입·네트워크 조회](#3-쿼터타입네트워크-조회)

---

## 1. 파일 스토리지 CRUD

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/file-storage` | 파일 스토리지 목록 |
| `GET` | `/api/v1/file-storage/{file_storage_id}` | 파일 스토리지 상세 |
| `POST` | `/api/v1/file-storage` | 파일 스토리지 생성 (분당 5회) |
| `DELETE` | `/api/v1/file-storage/{file_storage_id}` | 파일 스토리지 삭제 |

### GET /api/v1/file-storage

프로젝트의 Manila share 목록을 반환합니다. 응답은 약 15초간 캐시됩니다(`ttl_fast`). 관리자는 전체 프로젝트의 share를 조회할 수 있습니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `refresh` | query | boolean | `false` | 캐시 무시 여부 |

**응답 (200 OK)** — `FileStorageInfo[]` 배열

```json
[
  {
    "id": "uuid-string",
    "name": "union-prebuilt-python311",
    "status": "available",
    "size": 20,
    "share_proto": "CEPHFS",
    "export_locations": ["10.0.0.1:/volumes/_nogroup/..."],
    "metadata": {
      "union_type": "prebuilt",
      "union_library": "python311"
    },
    "is_public": false,
    "library_name": "python311",
    "library_version": "3.11",
    "built_at": "2024-01-01T00:00:00Z"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | Share UUID |
| `name` | string | Share 이름 |
| `status` | string | 상태 (`available`, `creating`, `error` 등) |
| `size` | integer | 크기 (GB) |
| `share_proto` | string | 프로토콜 (`CEPHFS`, `NFS`) |
| `export_locations` | array[string] | 마운트 경로 목록 |
| `nfs_export_location` | string\|null | NFS 전용 export 경로 |
| `metadata` | object | 메타데이터 (Afterglow 전용 필드 포함) |
| `is_public` | boolean | 공개 share 여부 |
| `library_name` | string\|null | Afterglow 라이브러리 ID |
| `library_version` | string\|null | 라이브러리 버전 |
| `built_at` | string\|null | 빌드 일시 |

### GET /api/v1/file-storage/{file_storage_id}

특정 파일 스토리지의 상세 정보를 반환합니다. 소유권을 검증합니다.

> `host` 필드는 백엔드 컨트롤러·CephFS 풀 토폴로지 정보이므로 **관리자에게만 노출**되며,
> 비관리자 응답에서는 `null`로 마스킹됩니다.
> 상세 조회 시 `user_name`(Keystone 이름) 등 확장 필드가 best-effort로 해석됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `file_storage_id` | path | string | 예 | 파일 스토리지 UUID |

**응답 (200 OK)** — `FileStorageInfo` 객체

**오류**: `404` (없거나 소유 프로젝트가 아님)

### POST /api/v1/file-storage

새 Manila share를 생성합니다. **속도 제한: 분당 5회**

`share_type`/`share_network_id`를 생략하면 설정 파일의 기본값이 적용됩니다. 프로토콜에 따라 기본 share 타입이 달라집니다 — `NFS`는 `os_manila_nfs_share_type`, 그 외는 `os_manila_share_type`.

NFS share의 `share_network_id`는 선택한 share type이 `DHSS=True`일 때만 Manila에 전달됩니다. `DHSS=False`이면 제외하고, share type의 DHSS 값을 확인할 수 없으면 잘못된 share를 생성하지 않고 오류로 중단합니다.

**요청 본문** — `CreateFileStorageRequest`

```json
{
  "name": "string (필수, 1~255자)",
  "size_gb": 20,
  "share_type": "cephfstype (선택)",
  "share_network_id": "uuid-string (선택)",
  "metadata": {},
  "share_proto": "CEPHFS"
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `name` | string | 예 | 1~255자 | Share 이름 |
| `size_gb` | integer | 예 | 1~16384 | 크기 (GB) |
| `share_type` | string | 아니오 | 최대 255자 | Manila share 타입. 기본값: 설정 파일 |
| `share_network_id` | string | 아니오 | | Share 네트워크 UUID. 기본값: 설정 파일 |
| `metadata` | object | 아니오 | | 메타데이터 |
| `share_proto` | string | 아니오 | `CEPHFS` \| `NFS` | 프로토콜 (기본값: `CEPHFS`) |

**응답 (201 Created)** — `FileStorageInfo` 객체

**오류**

| 상태 | 원인 |
|------|------|
| `4xx` | Manila API가 4xx로 응답 (상태 코드·메시지 그대로 전달) |
| `409` | Manila 폴링 오류 (error 상태, capabilities filter 실패 등 — 실패 사유 노출) |
| `422` | 요청 본문 검증 실패 |
| `429` | 분당 생성 한도 초과 |
| `502` | Manila API 5xx (외부 서비스 장애) |
| `500` | 기타 생성 실패 |

### DELETE /api/v1/file-storage/{file_storage_id}

파일 스토리지를 삭제합니다. 소유권을 검증하며, cross-project 소유 share 삭제 시 소유 프로젝트의 캐시도 무효화합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `file_storage_id` | path | string | 예 | 파일 스토리지 UUID |

**응답**: `204 No Content`

> `dhss_false_share_network_mismatch` 등으로 일반 삭제가 실패하는 경우를 위한
> 관리자 전용 진단(`delete-diagnostics`)·강제 삭제(`force-delete`) 엔드포인트가
> 별도 admin 라우터에 존재합니다. (`FileStorageDeleteDiagnostic` 모델 참조)

---

## 2. 접근 규칙 (Access Rules)

Manila share에 대한 접근 제어를 관리합니다. CephX 인증 또는 IP 기반 접근이 가능합니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/file-storage/{file_storage_id}/access-rules` | 접근 규칙 목록 |
| `POST` | `/api/v1/file-storage/{file_storage_id}/access-rules` | 접근 규칙 추가 |
| `DELETE` | `/api/v1/file-storage/{file_storage_id}/access-rules/{access_id}` | 접근 규칙 삭제 |

모든 접근 규칙 엔드포인트는 대상 share의 소유권을 먼저 검증합니다.

### GET /api/v1/file-storage/{file_storage_id}/access-rules

파일 스토리지의 접근 규칙 목록을 반환합니다.

**응답 (200 OK)** — 배열

### POST /api/v1/file-storage/{file_storage_id}/access-rules

파일 스토리지에 접근 규칙을 추가합니다.

**요청 본문** — `CreateAccessRuleRequest`

```json
{
  "access_to": "string (필수, 1~255자)",
  "access_level": "ro",
  "access_type": "cephx",
  "root_squash": true,
  "sec_flavor": "sys"
}
```

| 필드 | 타입 | 필수 | 제약 | 설명 |
|------|------|------|------|------|
| `access_to` | string | 예 | 1~255자 | 접근 대상 (CephX ID 또는 IP/CIDR) |
| `access_level` | string | 아니오 | `ro` \| `rw` | 접근 수준 (기본값: `ro` 읽기 전용) |
| `access_type` | string | 아니오 | `cephx` \| `ip` | 접근 타입 (기본값: `cephx`) |
| `root_squash` | boolean | 아니오 | | `ip` 타입 NFS 전용. root UID를 nobody로 매핑 (기본값: `true`) |
| `sec_flavor` | string | 아니오 | `sys` \| `krb5` \| `krb5i` \| `krb5p` | `ip` 타입 NFS 보안 flavor (기본값: `sys`) |

> **보안 기본값:** `root_squash`와 `sec_flavor` 기본값은 보안 권장 설정입니다.
> IP 기반 NFS 접근에서 `root_squash=true`는 클라이언트 root의 무단 파일 소유권 획득을 막고,
> Kerberos flavor(`krb5i`/`krb5p`)는 무결성·기밀성을 추가로 보장합니다.
> 자세한 배경은 아키텍처·보안 문서를 참고하세요.

**응답 (201 Created)**

**오류**

| 상태 | 원인 |
|------|------|
| `4xx` | Manila API 4xx (상태 코드·메시지 그대로 전달) |
| `502` | Manila API 5xx |
| `500` | 기타 생성 실패 |

### DELETE /api/v1/file-storage/{file_storage_id}/access-rules/{access_id}

접근 규칙을 삭제(회수)합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `file_storage_id` | path | string | 예 | 파일 스토리지 UUID |
| `access_id` | path | string | 예 | 접근 규칙 UUID |

**응답**: `204 No Content`

---

## 3. 쿼터·타입·네트워크 조회

### GET /api/v1/file-storage/quota

프로젝트의 Manila 파일 스토리지 쿼터를 반환합니다.

**응답 (200 OK)**

```json
{
  "gigabytes": {"limit": 1000, "in_use": 200},
  "shares": {"limit": 50, "in_use": 10},
  "snapshots": {"limit": 50, "in_use": 5}
}
```

### GET /api/v1/file-storage/types

사용 가능한 Manila share 타입 목록을 반환합니다.

**응답 (200 OK)** — 배열

### GET /api/v1/file-storage/networks

파일 스토리지 생성에 사용할 수 있는 Manila share 네트워크 목록을 반환하는 편의 엔드포인트입니다.

> 이 엔드포인트는 조회 전용입니다. Share 네트워크의 생성·삭제 및 상세 관리는
> [공유 스냅샷·네트워크 API](share-management.md)의 `/api/v1/share-networks`를 사용하세요.

**응답 (200 OK)** — 배열
