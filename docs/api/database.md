---
title: 데이터베이스 (Trove)
parent: API 레퍼런스
nav_order: 62
---

# 데이터베이스 (Trove) API

Trove 기반 관리형 데이터베이스(DBaaS)를 프로비저닝하고 관리합니다. MySQL·MariaDB·PostgreSQL 등의 인스턴스를 생성하고, 그 안의 데이터베이스·유저·백업을 관리하며, floating IP를 붙여 외부에 노출할 수 있습니다.

> **선택 서비스** — `afterglow.conf [services]` 에서 활성화해야 사용할 수 있습니다.
> 비활성화 상태에서 이 엔드포인트에 접근하면 라우터 미등록(404)이 반환됩니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |
| `Authorization: Bearer <JWT>` | 변경(mutation) 엔드포인트에 필요한 사용자 세션 JWT |

개별 인스턴스와 그 하위 리소스(databases/users/backups/floating-ip/auto-backup)는 `instance_id` 소유권을 검증합니다. 소유하지 않았거나 존재하지 않는 인스턴스는 `404` 로 응답합니다.

---

## 목차

1. [메타데이터 (생성 폼용)](#1-메타데이터-생성-폼용)
2. [인스턴스 라이프사이클](#2-인스턴스-라이프사이클)
3. [데이터베이스 서브리소스](#3-데이터베이스-서브리소스)
4. [유저 서브리소스](#4-유저-서브리소스)
5. [Floating IP](#5-floating-ip)
6. [백업](#6-백업)
7. [자동 백업 설정](#7-자동-백업-설정)

기본 경로: `/api/v1/database-instances`

---

## 1. 메타데이터 (생성 폼용)

인스턴스 생성에 필요한 선택지 목록입니다. 모두 조회 전용이며 캐시됩니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances/flavors` | DB 플레이버 목록 |
| `GET` | `/api/v1/database-instances/datastores` | 데이터스토어(MySQL/MariaDB/PostgreSQL 등) 및 버전 |
| `GET` | `/api/v1/database-instances/configurations` | Configuration group 목록 |
| `GET` | `/api/v1/database-instances/volume-types` | 볼륨 타입 목록 (Cinder) |

인스턴스를 만들려면 최소한 `flavor_id`(flavors), `datastore_type`/`datastore_version`(datastores)이 필요합니다. `volume_type`·`configuration_id` 는 선택입니다.

---

## 2. 인스턴스 라이프사이클

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances` | 인스턴스 목록 (`all_projects` 는 admin 전용) |
| `POST` | `/api/v1/database-instances` | 인스턴스 생성 (201) |
| `GET` | `/api/v1/database-instances/{instance_id}` | 인스턴스 상세 |
| `DELETE` | `/api/v1/database-instances/{instance_id}` | 인스턴스 삭제 (204) |
| `POST` | `/api/v1/database-instances/{instance_id}/restart` | 재시작 (204) |
| `POST` | `/api/v1/database-instances/{instance_id}/root` | root 유저 활성화 |

### GET /api/v1/database-instances

프로젝트의 DB 인스턴스 목록을 반환합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `all_projects` | query | boolean | 아니오 | `true` 면 전체 프로젝트 조회. **시스템 admin 전용**(아니면 `403`) |

시스템 admin의 `all_projects=true` 요청은 Trove 관리 API `/mgmt/instances`를 사용하며, 응답의 `tenant_id`를 `project_id`로 정규화합니다. 이 목록은 사용자가 Trove로 생성한 관리형 DB 인스턴스만 반환합니다. OpenStack control-plane MariaDB/MySQL이나 `mysqld_exporter` 대상은 포함하지 않습니다. 관리 API 조회가 실패하거나 응답 형식이 잘못된 경우 빈 배열이 아니라 `500`을 반환하므로, 관리 화면은 실제 0건과 조회 실패를 구분합니다.

### POST /api/v1/database-instances

새 DB 인스턴스를 생성합니다. `is_public=true` 면 BUILD 완료 후 백그라운드에서 floating IP 자동 할당을 시도합니다(best-effort).

**요청 본문 (주요 필드)**

```json
{
  "name": "string (필수)",
  "flavor_id": "string (필수)",
  "volume_size": 10,
  "datastore_type": "mysql",
  "datastore_version": "8.0",
  "databases": ["appdb"],
  "users": [{ "name": "app", "password": "...", "host": "%", "databases": ["appdb"] }],
  "is_public": false,
  "allowed_cidrs": ["203.0.113.0/24"],
  "volume_type": "ssd",
  "configuration_id": null,
  "replica_of": null,
  "replica_count": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 인스턴스 이름 (1–255자) |
| `flavor_id` | string | 예 | DB 플레이버 ID ([flavors](#1-메타데이터-생성-폼용)) |
| `volume_size` | integer | 예 | 볼륨 크기 GB (1–1024) |
| `datastore_type` | string | 예 | 데이터스토어 종류 |
| `datastore_version` | string | 예 | 데이터스토어 버전 |
| `databases` | string[] | 아니오 | 초기 생성할 DB 이름 목록 |
| `users` | object[] | 아니오 | 초기 유저 (`name`·`password`·`host`·`databases`) |
| `is_public` | boolean | 아니오 | 외부 노출 + FIP 자동 할당 (기본값: `false`) |
| `allowed_cidrs` | string[] | 아니오 | 접근 허용 CIDR 목록 |
| `availability_zone` | string | 아니오 | 가용 영역 |
| `volume_type` | string | 아니오 | 볼륨 타입 ([volume-types](#1-메타데이터-생성-폼용)) |
| `nics` | string[] | 아니오 | 네트워크 UUID 목록 |
| `locality` | string | 아니오 | `affinity` \| `anti-affinity` |
| `configuration_id` | string | 아니오 | Configuration group ID |
| `replica_of` | string | 아니오 | 원본 인스턴스 ID (읽기 복제본 생성) |
| `replica_count` | integer | 아니오 | 복제본 개수 |

**응답 (201 Created)** — 생성된 인스턴스. 생성 실패 시 `502`(백엔드 오류) 또는 `500`.

### POST /api/v1/database-instances/{instance_id}/root

root 유저를 활성화하고 `{ "name", "password" }` 를 반환합니다.

---

## 3. 데이터베이스 서브리소스

인스턴스 내부의 논리 데이터베이스를 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances/{instance_id}/databases` | DB 목록 |
| `POST` | `/api/v1/database-instances/{instance_id}/databases` | DB 생성 (201) |
| `DELETE` | `/api/v1/database-instances/{instance_id}/databases/{db_name}` | DB 삭제 (204) |

### POST .../{instance_id}/databases

**요청 본문**: `{ "name": "string (필수, 1–64자)", "character_set": "utf8mb4", "collate": "utf8mb4_general_ci" }`

---

## 4. 유저 서브리소스

인스턴스 내부의 DB 유저를 관리합니다. Trove의 유저 identity는 `name@host` 이므로 동명 유저는 `host` 로 구분합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances/{instance_id}/users` | 유저 목록 |
| `POST` | `/api/v1/database-instances/{instance_id}/users` | 유저 생성 (201) |
| `DELETE` | `/api/v1/database-instances/{instance_id}/users/{username}` | 유저 삭제 (204) |

### POST .../{instance_id}/users

**요청 본문**: `{ "name": "string (필수, 1–64자)", "password": "string (필수)", "host": "%", "databases": ["appdb"] }`

### DELETE .../{instance_id}/users/{username}

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `host` | query | string | 아니오 | 유저 host (기본값: `%`). 동명 유저를 `name@host` 로 구분 |

---

## 5. Floating IP

인스턴스에 외부 접근용 floating IP를 수동으로 붙이거나 뗍니다. 연결된 라우터의 외부 네트워크를 자동 탐색합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/database-instances/{instance_id}/floating-ip` | FIP 할당 (201, 멱등) |
| `DELETE` | `/api/v1/database-instances/{instance_id}/floating-ip` | FIP 해제 (204) |

### POST .../{instance_id}/floating-ip

인스턴스에 FIP를 할당합니다. 이미 FIP가 붙은 port면 기존 정보를 반환합니다(멱등). IP가 아직 없거나(BUILD 중) 외부 네트워크를 못 찾으면 `400`.

**응답 (201 Created)** — `{ "floating_ip_address", "floating_ip_id", "port_id" }`

### DELETE .../{instance_id}/floating-ip

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `delete` | query | boolean | 아니오 | `true` 면 FIP까지 삭제, 기본은 dissociate만 (기본값: `false`) |

연결된 FIP가 없으면 `404`.

---

## 6. 백업

백업은 인스턴스별 하위 경로와, 프로젝트 전역 경로 두 방식으로 접근합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances/backups` | 프로젝트 전체 백업 목록 (복원 폼용) |
| `DELETE` | `/api/v1/database-instances/backups/{backup_id}` | 백업 삭제 (204) |
| `POST` | `/api/v1/database-instances/restore` | 백업에서 새 인스턴스 복원 (201) |
| `GET` | `/api/v1/database-instances/{instance_id}/backups` | 인스턴스 백업 목록 |
| `POST` | `/api/v1/database-instances/{instance_id}/backups` | 인스턴스 백업 생성 (201) |

### POST /api/v1/database-instances/restore

지정한 백업으로 **새 인스턴스**를 복원 생성합니다.

**요청 본문**

```json
{
  "backup_id": "uuid (필수)",
  "name": "string (필수)",
  "flavor_id": "string (필수)",
  "volume_size": 10
}
```

### POST .../{instance_id}/backups

**요청 본문**: `{ "name": "string (필수, 1–255자)", "description": "" }`. 백엔드 오류 시 `502`.

---

## 7. 자동 백업 설정

인스턴스별 자동 백업 스케줄과 보존 개수를 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/database-instances/{instance_id}/auto-backup` | 설정 조회 (없으면 404) |
| `PUT` | `/api/v1/database-instances/{instance_id}/auto-backup` | 활성화/갱신 (200) |
| `DELETE` | `/api/v1/database-instances/{instance_id}/auto-backup` | 비활성화 (204) |

### PUT .../{instance_id}/auto-backup

**요청 본문**

```json
{ "max_daily": 7, "max_weekly": 0, "max_monthly": 0 }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `max_daily` | integer | 아니오 | 일간 백업 보존 개수 (0–30, 기본값: `7`) |
| `max_weekly` | integer | 아니오 | 주간 백업 보존 개수 (0–30, 기본값: `0`) |
| `max_monthly` | integer | 아니오 | 월간 백업 보존 개수 (0–12, 기본값: `0`) |
