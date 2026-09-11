---
title: 관리자 (Admin)
parent: API 레퍼런스
nav_order: 20
---

# 관리자 (Admin) API

> 태그: `admin`, `admin-instances`, `admin-services`, `admin-worker-runtime`, `admin-flavors`, `admin-identity`, `admin-gpu`, `admin-libraries`, `admin-notion`, `admin-images`, `admin-activity`, `admin-orphans`, `admin-dashboard`, `admin-announcements`, `admin-key-manager`
> 기본 경로: `/api/v1/admin`

관리자 API는 클러스터 전체(모든 프로젝트)를 대상으로 하는 **시스템 스코프** 관리 기능입니다. 하이퍼바이저·리소스 집계, 전체 리소스 조회, VM 마이그레이션, 볼륨/네트워크 관리, 사용자·프로젝트·쿼터·역할, GPU·이미지·Notion 연동, 고아 리소스 정리, 워커 런타임, 공지, k3s 클러스터 관리 등을 포함합니다.

## 인증 및 권한

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` — 관리자(system admin) 권한 계정의 access JWT |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

**모든 관리자 엔드포인트에는 `Depends(require_admin)`가 적용**됩니다(개별 데코레이터 또는 라우터 레벨 의존성으로 선언). 관리자가 아닌 사용자는 `403 Forbidden`을 받습니다. 아래 표에서는 이 사항을 매 행마다 반복하지 않습니다.

- 대부분의 라우터는 `/api/v1/admin` prefix에 마운트됩니다.
- 예외: 라이브러리 관리(`/api/v1/admin/libraries`), 공지(`/api/v1/admin/announcements`).
- 캐시 기반 조회 엔드포인트는 대부분 `refresh` (query, boolean, 기본 `false`) 파라미터로 캐시 무시 재조회를 지원합니다.
- 목록 조회는 대체로 `limit`(1~100, 기본 20) + `marker` 커서 페이지네이션을 사용하며 `{ "items": [...], "next_marker": ..., "count": N }` 형태로 응답합니다.

![관리자 개요](../../assets/admin-page.png)
*관리자 개요 페이지 — 클러스터 전체 vCPU·RAM·Disk 사용률, 총 VM/하이퍼바이저 수, 프로젝트별 리소스 할당량을 한 화면에서 조회*

---

## 클러스터 개요·모니터링

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/overview` | 하이퍼바이저·인스턴스·vCPU/RAM/Disk 사용량·GPU 인스턴스 수 등 클러스터 개요 |
| `GET` | `/api/v1/admin/overview/projects` | 프로젝트별 컴퓨트/스토리지 쿼터·사용량·GPU 인스턴스 수 |
| `GET` | `/api/v1/admin/monitoring/summary` | 서비스 상태·리소스·알림을 종합한 모니터링 요약 |
| `GET` | `/api/v1/admin/notifications` | 관리자 알림(이상 상태·경고) 목록 |
| `GET` | `/api/v1/admin/topology` | 전체 프로젝트 네트워크/라우터/인스턴스 토폴로지 (`AdminTopologyData`). 사용자용 `GET /api/v1/networks/topology` 응답에 더해 `networks[]`에 `provider_network_type` / `provider_segmentation_id` / `provider_physical_network`를 추가한다 (관리자 응답 전용). `instances[].is_database`는 Trove 전체 프로젝트 목록(`all_projects=True`)의 fixed IP 매칭으로 채우며 Trove 미배포 시 모두 `false` |
| `GET` | `/api/v1/admin/timeseries/{resource_type}` | 리소스 유형별 시계열 스냅샷 (1시간 간격) |
| `GET` | `/api/v1/admin/version` | 백엔드/배포 버전 정보 |

`GET /overview` 응답 예시:

```json
{
  "hypervisor_count": 5,
  "running_vms": 42,
  "gpu_instances": 3,
  "instance_stats": {"total": 42, "active": 38, "shutoff": 2, "error": 1, "other": 1},
  "vcpus": {"total": 160, "allowed": 320, "used": 85},
  "ram_gb": {"total": 512.0, "used": 256.5},
  "disk_gb": {"total": 10000, "used": 3500},
  "containers_count": 0,
  "file_storage_count": 12
}
```

**timeseries 제한**: `resource_type`은 `instances` / `volumes` / `file_storage` / `networks` 중 하나여야 하며, 그 외 값은 `400`. `range` (query)는 `1d` / `2d` / `7d` / `30d` (기본 `7d`).

---

## 하이퍼바이저·컴퓨트 호스트

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/hypervisors` | 컴퓨트 하이퍼바이저 상세 목록(호스트별 vCPU/RAM/디스크/VM 수) |
| `GET` | `/api/v1/admin/hypervisors/{hypervisor_id}` | 특정 하이퍼바이저 상세 |
| `GET` | `/api/v1/admin/compute-hosts` | 마이그레이션 대상 선택용 컴퓨트 호스트 목록 |

![하이퍼바이저 목록](../../assets/admin-hv-list.png)
*호스트별 VM 수, vCPU 사용률, RAM 사용량, 로컬 디스크 현황을 테이블로 일괄 조회*

---

## 전체 리소스 조회 (all-*)

전체 프로젝트를 가로지르는 조회 엔드포인트입니다. `all-instances` / `all-volumes`는 `limit`+`marker` 페이지네이션(`project_id` 필터 지원), 나머지는 `refresh` 파라미터를 사용합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/all-instances` | 전체 인스턴스 목록 (페이지네이션, `project_id` 필터) |
| `GET` | `/api/v1/admin/all-volumes` | 전체 볼륨 목록 (페이지네이션) |
| `GET` | `/api/v1/admin/all-containers` | 전체 Zun 컨테이너 목록 (Zun 활성화 시) |
| `GET` | `/api/v1/admin/all-file-storages` | 전체 Manila 파일 스토리지 목록 (Manila 활성화 시) |
| `GET` | `/api/v1/admin/all-networks` | 전체 네트워크 목록 |
| `GET` | `/api/v1/admin/all-loadbalancers` | 전체 로드밸런서 목록 (Octavia 활성화 시) |
| `GET` | `/api/v1/admin/all-floating-ips` | 전체 Floating IP 목록 |
| `GET` | `/api/v1/admin/all-routers` | 전체 라우터 목록 |
| `GET` | `/api/v1/admin/all-ports` | 전체 포트 목록 |

`GET /all-instances` 응답 예시:

```json
{
  "items": [
    {"id": "uuid", "name": "vm", "status": "ACTIVE", "project_id": "uuid",
     "user_id": "uuid", "flavor": "m1.small", "host": "compute01",
     "created_at": "2024-01-01T00:00:00Z", "fault": null}
  ],
  "next_marker": "uuid-or-null",
  "count": 20
}
```

---

## VM 마이그레이션·복구

인스턴스를 다른 호스트로 이동하거나 상태 전이/복구를 수행하는 **파괴적·상태전이** 엔드포인트입니다. 대상 인스턴스의 현재 상태가 전제 조건을 만족해야 하며(예: resize는 `VERIFY_RESIZE`를 거쳐 confirm/revert 필요), 진행 중 작업은 되돌리기 어려우므로 대상 검증이 필수입니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate` | 라이브 마이그레이션 시작 | `host` (선택), `block_migration` (선택) |
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate/abort` | 진행 중 라이브 마이그레이션 중단 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/live-migrate/force-complete` | 라이브 마이그레이션 강제 완료 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/cold-migrate` | 콜드 마이그레이션 (`host` 지정 시 해당 호스트로) | `host` (선택) |
| `POST` | `/api/v1/admin/instances/{server_id}/evacuate` | 다운된 호스트에서 인스턴스 대피 | `host` (선택) |
| `GET` | `/api/v1/admin/instances/{server_id}/migration-status` | 마이그레이션 진행 상태 조회 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/resize` | 인스턴스 리사이즈 시작 (`VERIFY_RESIZE`로 전이) | `new_flavor` |
| `POST` | `/api/v1/admin/instances/{server_id}/confirm-resize` | 리사이즈 확정 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/revert-resize` | 리사이즈 되돌리기 | - |
| `GET` | `/api/v1/admin/instances/{server_id}/recovery-analysis` | 오류/멈춤 인스턴스 복구 분석 | - |
| `POST` | `/api/v1/admin/instances/{server_id}/recover` | 분석 결과 기반 인스턴스 복구 수행 | - |
| `GET` | `/api/v1/admin/instances/health` | 전체 인스턴스 헬스 스냅샷 | - |
| `POST` | `/api/v1/admin/instances/bulk-action` | 다수 인스턴스 일괄 제어 | `instance_ids[]`, `action`, `snapshot_name` (선택) |

**bulk-action 제한**: `action`은 시작/정지/재부팅/스냅샷 등 허용된 값이어야 하며, 각 인스턴스별 결과가 개별 집계됩니다. 일부 실패해도 나머지는 계속 진행됩니다.

### 관리자 인스턴스 생성 (대리 프로비저닝)

관리자가 특정 프로젝트를 대신하여 인스턴스를 생성할 때 사용하는 헬퍼입니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/instances/networks-for-project` | 대상 프로젝트에서 선택 가능한 네트워크 |
| `GET` | `/api/v1/admin/instances/security-groups-for-project` | 대상 프로젝트의 보안 그룹 |
| `GET` | `/api/v1/admin/instances/volumes-for-project` | 대상 프로젝트의 볼륨 |
| `POST` | `/api/v1/admin/instances/async` | 대상 프로젝트에 인스턴스 비동기 생성 |

---

## 볼륨 관리

![전체 볼륨 관리](../../assets/admin-volume.png)
*전체 프로젝트의 볼륨을 시계열 차트와 함께 일괄 조회 — 상태·크기·프로젝트별 필터링, 수정·삭제 지원*

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/volumes/status-summary` | 상태별 볼륨 수 집계 | - |
| `GET` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 상세 조회 | - |
| `PATCH` | `/api/v1/admin/volumes/{volume_id}` | 이름/설명 수정 | `name`, `description` (모두 선택) |
| `DELETE` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/force-delete` | 강제 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/extend` | 용량 확장 | `new_size` (현재보다 커야 함) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/reset-status` | 상태 강제 초기화 | `status` (기본 `available`) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/transfer` | 다른 프로젝트로 볼륨 이관 | 대상 프로젝트 지정 |
| `GET` | `/api/v1/admin/volumes/{volume_id}/delete-diagnostics` | 삭제 실패 원인 진단 | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/recover-delete` | 삭제 실패 복구 시도 | - |

**제한**: `force-delete` / `reset-status`는 Cinder의 정상 상태 전이를 우회하므로 데이터 정합성 위험이 있습니다. 오류 상태 복구 용도로만 사용하고, `extend`는 축소가 불가능합니다.

---

## 네트워크·라우터·포트·Floating IP

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/networks/{network_id}` | 네트워크 상세 | - |
| `POST` | `/api/v1/admin/networks` | 네트워크 생성 (`201`) | `name`(필수), `is_external`, `is_shared`, `cidr`, `enable_dhcp` |
| `PUT` | `/api/v1/admin/networks/{network_id}` | 네트워크 수정 | `name`, `is_shared` (선택) |
| `DELETE` | `/api/v1/admin/networks/{network_id}` | 네트워크 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/floating-ips` | Floating IP 생성 (`201`) | `floating_network_id` (필수) |
| `DELETE` | `/api/v1/admin/floating-ips/{fip_id}` | Floating IP 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/floating-ips/pool-stats` | Floating IP 풀 사용 통계 | - |
| `POST` | `/api/v1/admin/routers` | 라우터 생성 (`201`) | `name`(필수), `external_network_id` (선택) |
| `PUT` | `/api/v1/admin/routers/{router_id}` | 라우터 수정 (`null`이면 게이트웨이 제거) | `name`, `external_network_id` (선택) |
| `DELETE` | `/api/v1/admin/routers/{router_id}` | 라우터 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/ports` | 포트 생성 (`201`) | 네트워크/고정 IP 지정 |
| `PUT` | `/api/v1/admin/ports/{port_id}` | 포트 이름 수정 | `name` (선택) |
| `DELETE` | `/api/v1/admin/ports/{port_id}` | 포트 삭제 (`204`) | - |

`cidr`을 지정하면 네트워크와 함께 서브넷도 생성됩니다.

---

## 파일 스토리지 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/file-storage` | 전체 Afterglow 파일 스토리지(Manila share) 목록 (prebuilt + dynamic) |
| `POST` | `/api/v1/admin/file-storage/build` | 사전 빌드 share 생성 트리거 (`202`) — `library_id` (query, 필수) |
| `GET` | `/api/v1/admin/file-storage/builds` | 진행 중/대기 중 빌드 목록 |
| `GET` | `/api/v1/admin/file-storage/{file_storage_id}/delete-diagnostics` | share 삭제 실패 진단 |
| `POST` | `/api/v1/admin/file-storage/{file_storage_id}/force-delete` | share 강제 삭제 (`202`) |

**build 오류**: `404` 알 수 없는 `library_id`, `409` 이미 존재하는 사전 빌드 스토리지.

---

## 라이브러리 관리 (squashfs 레이어)

관리자 라이브러리 화면은 squashfs 레이어 워크플로우(레이어 artifact·프로필·소비 인스턴스)를 관리합니다. prefix는 `/api/v1/admin/libraries`이며 `/api/v1/admin/layers` alias는 제공하지 않습니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/admin/libraries/build` | squashfs 레이어 빌드 시작 |
| `GET` | `/api/v1/admin/libraries/builds` | 레이어 빌드 목록 |
| `GET` | `/api/v1/admin/libraries/builds/{id}` | 레이어 빌드 상세 |
| `POST` | `/api/v1/admin/libraries/builds/{id}/cancel` | 레이어 빌드 취소 |
| `GET` | `/api/v1/admin/libraries/artifacts` | 봉인된 레이어 artifact 목록 |
| `GET` | `/api/v1/admin/libraries/artifacts/{id}/delete-preview` | artifact 삭제 영향 미리보기 |
| `DELETE` | `/api/v1/admin/libraries/artifacts/{id}` | artifact 삭제 |
| `POST` | `/api/v1/admin/libraries/profiles` | 레이어 프로필 생성/갱신 |
| `DELETE` | `/api/v1/admin/libraries/profiles/{profile_name}` | 레이어 프로필 삭제 |
| `POST` | `/api/v1/admin/libraries/consume` | 프로필 소비 인스턴스 생성 |
| `GET` | `/api/v1/admin/libraries/consumes` | 소비 인스턴스 목록 |

---

## Zun 컨테이너 관리

Zun 서비스 활성화 시에만 사용 가능합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/containers/{container_id}` | 컨테이너 상세 |
| `GET` | `/api/v1/admin/containers/{container_id}/logs` | 컨테이너 로그 |
| `POST` | `/api/v1/admin/containers/{container_id}/start` | 컨테이너 시작 |
| `POST` | `/api/v1/admin/containers/{container_id}/stop` | 컨테이너 정지 |
| `DELETE` | `/api/v1/admin/containers/{container_id}` | 컨테이너 삭제 (`204`) |

---

## 사용자 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/users` | 사용자 목록 (페이지네이션) | - |
| `GET` | `/api/v1/admin/users/stats` | 사용자 통계(총계·활성 등) | - |
| `GET` | `/api/v1/admin/users/activity` | 사용자 활동 집계 | - |
| `POST` | `/api/v1/admin/users` | 사용자 생성 (`201`) | `name`(필수), `email`, `password`, `enabled`, `domain_id` |
| `PATCH` | `/api/v1/admin/users/{user_id}` | 사용자 수정 | `name`, `email`, `enabled`, `password` (선택) |
| `POST` | `/api/v1/admin/users/{user_id}/revoke-sessions` | 사용자 세션 전체 무효화 | - |
| `GET` | `/api/v1/admin/users/{user_id}/sessions` | 사용자의 활성 세션 목록 | - |
| `POST` | `/api/v1/admin/users/unlock-account` | 로그인 실패로 잠긴 계정 잠금 해제 | 대상 사용자 지정 |
| `GET` | `/api/v1/admin/users/lock-status` | 계정 잠금 상태 조회 | - |

**주의**: `revoke-sessions`는 해당 사용자의 토큰/세션 캐시를 즉시 무효화합니다.

---

## 프로젝트 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/projects` | 프로젝트 목록 (페이지네이션) | - |
| `GET` | `/api/v1/admin/projects/names` | 전체 프로젝트 id/name 목록 (페이지네이션 없음) | - |
| `POST` | `/api/v1/admin/projects` | 프로젝트 생성 (`201`) | `name`(필수), `description`, `domain_id`, `enabled` |
| `GET` | `/api/v1/admin/projects/{project_id}` | 프로젝트 상세 | - |
| `PATCH` | `/api/v1/admin/projects/{project_id}` | 프로젝트 수정 | `name`, `description`, `enabled` (선택) |
| `DELETE` | `/api/v1/admin/projects/{project_id}` | 프로젝트 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/projects/{project_id}/members` | 사용자·그룹 역할 할당 목록 | - |
| `GET` | `/api/v1/admin/projects/{project_id}/activity` | 프로젝트 활동 로그 | - |
| `POST` | `/api/v1/admin/projects/{project_id}/sync-monitoring-sg` | 모니터링용 보안 그룹 동기화 | - |

`GET /projects/{project_id}/members` 응답에는 사용자 할당과 그룹 할당(`type: "group"`, `group_id` 포함)이 함께 반환됩니다.

---

## 쿼터 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/quotas/{project_id}` | 프로젝트 컴퓨트/볼륨 쿼터·사용량 조회 | - |
| `PUT` | `/api/v1/admin/quotas/{project_id}` | 프로젝트 쿼터 수정 | `instances`, `cores`, `ram`(MB), `volumes`, `gigabytes` (모두 선택) |

```json
{
  "compute": {"instances": {"limit": 20, "in_use": 5}, "cores": {"limit": 40, "in_use": 10}, "ram": {"limit": 81920, "in_use": 20480}},
  "volume": {"volumes": {"limit": 10, "in_use": 3}, "gigabytes": {"limit": 1000, "in_use": 200}}
}
```

---

## 그룹 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/groups` | 그룹 목록 | - |
| `POST` | `/api/v1/admin/groups` | 그룹 생성 (`201`) | `name`(필수), `description`, `domain_id` |
| `PATCH` | `/api/v1/admin/groups/{group_id}` | 그룹 수정 | `name`, `description` (선택) |
| `DELETE` | `/api/v1/admin/groups/{group_id}` | 그룹 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/groups/{group_id}/users` | 그룹 멤버 목록 | - |
| `PUT` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에 사용자 추가 (`204`) | - |
| `DELETE` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에서 사용자 제거 (`204`) | - |

**주의**: 멤버십 변경 시 Keystone이 관련 토큰을 revoke할 수 있어 관련 세션 캐시가 함께 삭제됩니다.

---

## 역할·시스템 역할 관리

프로젝트 스코프 역할(assign/assign-group)과 시스템 스코프 역할(system-roles)을 구분해 관리합니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/roles` | 역할 목록 | - |
| `POST` | `/api/v1/admin/roles/assign` | 사용자에게 프로젝트 역할 할당 | `user_id`, `project_id`, `role_id` (body) |
| `DELETE` | `/api/v1/admin/roles/assign` | 사용자 프로젝트 역할 회수 | `user_id`, `project_id`, `role_id` (query) |
| `POST` | `/api/v1/admin/roles/assign-group` | 그룹에 프로젝트 역할 할당 | `group_id`, `project_id`, `role_id` (body) |
| `DELETE` | `/api/v1/admin/roles/assign-group` | 그룹 프로젝트 역할 회수 | `group_id`, `project_id`, `role_id` (query) |
| `GET` | `/api/v1/admin/identity/system-roles` | 시스템 스코프 역할 할당 목록 | - |
| `POST` | `/api/v1/admin/identity/system-roles/grant` | 시스템 역할 부여 | 사용자·역할 지정 |
| `POST` | `/api/v1/admin/identity/system-roles/revoke` | 시스템 역할 회수 | 사용자·역할 지정 |
| `POST` | `/api/v1/admin/identity/system-roles/migrate-from-project` | 프로젝트 admin → 시스템 역할로 마이그레이션 | - |
| `GET` | `/api/v1/admin/identity/security-policy` | 보안 정책(비밀번호·잠금 등) 조회 | - |
| `GET` | `/api/v1/admin/identity/summary` | identity 도메인 요약(사용자·프로젝트·역할 수) | - |

**주의**: 시스템 역할은 클러스터 전역 권한을 부여하므로 `grant`/`revoke`는 신중히 수행합니다. `migrate-from-project`는 기존 프로젝트 스코프 admin 권한을 시스템 스코프로 승격시키는 일회성 전환 작업입니다.

---

## Flavor 관리

> 태그: `admin-flavors`

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/flavors` | 전체 flavor 목록(공개+비공개) | `limit`, `marker`, `is_public` (query) |
| `POST` | `/api/v1/admin/flavors` | flavor 생성 (`201`) | `name`, `vcpus`, `ram`(MB), `disk`(GB), `is_public`, `description` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}` | flavor 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/flavors/{flavor_id}/access` | 비공개 flavor 접근 허용 프로젝트 목록 | - |
| `POST` | `/api/v1/admin/flavors/{flavor_id}/access` | 프로젝트 접근 권한 추가 | `project_id` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}/access/{project_id}` | 프로젝트 접근 권한 제거 (`204`) | - |
| `POST` | `/api/v1/admin/flavors/{flavor_id}/extra-specs` | extra_spec 추가/수정 (GPU 지정 등) | `key`, `value` |
| `DELETE` | `/api/v1/admin/flavors/{flavor_id}/extra-specs/{key}` | extra_spec 삭제 (`204`) | - |

`extra-specs`는 `resources:VGPU` = `1` 처럼 GPU 리소스 요청 지정에 사용됩니다.

---

## GPU 호스트·디바이스·쿼터

> 태그: `admin-gpu`

![GPU 리소스 관리](../../assets/admin-gpu-list.png)
*GPU 타입별 전체/사용 중/사용 가능 수량과 호스트별 GPU 구성 및 가동률*

### GPU 호스트 모니터링

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-hosts` | Placement 기반 호스트별 GPU 집계(개별/병합/요약/타입) |
| `GET` | `/api/v1/admin/gpu-hosts/raw` | Placement 원본 데이터(디버깅용) |

`gpu-hosts` 응답은 `hosts`(PCI 주소 단위) · `aggregated_hosts`(호스트명 병합) · `summary`(total/used/available) · `gpu_types`(모델별 집계)로 구성됩니다.

### GPU 디바이스 카탈로그

vendor_id/device_id → 표시 이름 매핑을 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-devices` | GPU 디바이스 이름 매핑 목록 |
| `GET` | `/api/v1/admin/gpu-devices/export` | 디바이스 매핑 내보내기 |
| `POST` | `/api/v1/admin/gpu-devices` | 디바이스 매핑 추가/수정 |
| `DELETE` | `/api/v1/admin/gpu-devices/{vendor_id}/{device_id}` | 디바이스 매핑 삭제 (`204`) |
| `POST` | `/api/v1/admin/gpu-devices/import` | 디바이스 매핑 일괄 가져오기 |

### GPU 쿼터

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/gpu-aliases` | GPU alias 목록 (모델 → 사용자 친화 이름) |
| `GET` | `/api/v1/admin/gpu-quotas/defaults` | 기본 GPU 쿼터 조회 |
| `PUT` | `/api/v1/admin/gpu-quotas/defaults` | 기본 GPU 쿼터 수정 (신규 프로젝트에 적용) |
| `DELETE` | `/api/v1/admin/gpu-quotas/defaults/{gpu_type}` | 기본 쿼터 유형별 삭제 (`204`) |
| `GET` | `/api/v1/admin/gpu-quotas/{project_id}` | 프로젝트 GPU 쿼터 (없으면 기본값 반환) |
| `PUT` | `/api/v1/admin/gpu-quotas/{project_id}` | 프로젝트 GPU 쿼터 수정 |
| `DELETE` | `/api/v1/admin/gpu-quotas/{project_id}/{gpu_type}` | 프로젝트 쿼터 유형별 삭제 → 기본값 복귀 (`204`) |

---

## 이미지 관리

> 태그: `admin-images`

전체 프로젝트의 Glance 이미지를 관리합니다. 상태 전이(deactivate/reactivate)와 삭제는 사용자 부팅에 영향을 줄 수 있으므로 대상 확인이 필요합니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/images` | 전체 이미지 목록 | `limit`, `marker`, `search`, `visibility` (query) |
| `GET` | `/api/v1/admin/images/{image_id}` | 이미지 상세 | - |
| `PATCH` | `/api/v1/admin/images/{image_id}` | 이미지 메타데이터 수정 | 이름·가시성 등 |
| `PATCH` | `/api/v1/admin/images/{image_id}/properties` | 이미지 커스텀 속성 수정 (`ImageDetail`) | 속성 key/value |
| `DELETE` | `/api/v1/admin/images/{image_id}` | 이미지 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/images/{image_id}/deactivate` | 이미지 비활성화(부팅 불가) | - |
| `POST` | `/api/v1/admin/images/{image_id}/reactivate` | 이미지 재활성화 | - |

---

## Notion 연동

> 태그: `admin-notion`

OpenStack 리소스를 Notion 데이터베이스와 동기화하는 관리자 기능입니다. 단일 연동 설정(`config`)과 다중 동기화 대상(`targets`)을 관리합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/notion/config` | Notion 연동 설정 조회(토큰은 마스킹) |
| `POST` | `/api/v1/admin/notion/config` | Notion 연동 설정 저장 |
| `DELETE` | `/api/v1/admin/notion/config` | Notion 연동 설정 삭제 |
| `POST` | `/api/v1/admin/notion/test` | 연동 설정 연결 테스트 |
| `GET` | `/api/v1/admin/notion/targets` | 동기화 대상(DB) 목록 |
| `POST` | `/api/v1/admin/notion/targets` | 동기화 대상 추가 |
| `PATCH` | `/api/v1/admin/notion/targets/{target_id}` | 동기화 대상 수정 |
| `DELETE` | `/api/v1/admin/notion/targets/{target_id}` | 동기화 대상 삭제 |
| `POST` | `/api/v1/admin/notion/targets/{target_id}/test` | 특정 대상 동기화 테스트 |

![Notion 연동](../../assets/admin-notion.png)
*Notion Integration 설정 — 다중 데이터베이스(인스턴스 DB·이미지 DB·GPU Spec DB) 연결, 즉시 동기화 및 마지막 동기화 시각 표시*

---

## 고아 리소스 정리 (orphans)

> 태그: `admin-orphans`

프로젝트가 사라졌거나 장기 미사용/미연결 상태인 리소스를 탐지·정리합니다. **삭제는 되돌릴 수 없으므로** 정리 전 스캔 결과 검토가 필수이며, 정리 시 race-safe 재검증 후 각 결과가 audit log에 기록됩니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/orphans` | 전체 프로젝트 orphan 후보 스캔 | `min_age_days` (query, 1~365, 기본 14) |
| `POST` | `/api/v1/admin/orphans/cleanup` | ID 목록 일괄 정리 | `kind`, `ids[]` (min 1) |

- `kind`: `floating_ip`(port 미연결) / `volume`(available·attachments 없음) / `manila_share`(프로젝트 소멸) / `security_group`(자동생성 후 미연결).
- 응답은 `deleted[]`와 `failed[]`(`{id, error}`)로 분리됩니다.

---

## 워커 런타임 관리

> 태그: `admin-worker-runtime`

백그라운드 워커(`drover`, `notion_worker`)의 관측 상태와 희망 레플리카 수를 관리합니다. 런타임 모드는 `static` / `docker` / `kubernetes` 중 하나이며, 모드가 관리 불가(`capable=false`)이면 변경이 거부될 수 있습니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/worker-runtime/status` | 런타임 능력 + 워커별 상태 (`WorkerRuntimeStatus`) | - |
| `PATCH` | `/api/v1/admin/worker-runtime/desired` | 희망 레플리카 수 오버라이드 | `workers[]` (`name`, `desired_replicas≥0`; 1~2개, 이름 유일) |
| `POST` | `/api/v1/admin/worker-runtime/reconcile` | 희망 상태로 즉시 재조정 | - |

**제한**: `workers[].name`은 `drover` 또는 `notion_worker`만 허용되며 중복 불가. `desired_replicas`는 `max_replicas`를 넘을 수 없습니다.

---

## Key Manager(Barbican) 쿼터

> 태그: `admin-key-manager`

Barbican(key-manager) 서비스가 활성화된 경우에만 마운트됩니다. 프로젝트별 시크릿/컨테이너 쿼터를 관리하며 rate limit(30/min)이 적용됩니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/key-manager/project-quotas` | 전체 프로젝트 쿼터 목록 |
| `GET` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 조회 |
| `PUT` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 설정 |
| `DELETE` | `/api/v1/admin/key-manager/project-quotas/{project_id}` | 프로젝트 쿼터 초기화 (`204`) |

---

## 서비스 상태 모니터링

> 태그: `admin-services`

### GET /api/v1/admin/services

Nova·Cinder·Neutron·Manila·Heat·Zun 서비스 상태, API 엔드포인트, 스토리지 풀 정보를 종합 조회합니다. `refresh` (query) 지원.

응답은 `compute` / `block_storage` / `network` / `shared_file_system` / `orchestration` / `container` / `container_infra` / `endpoints` / `storage_pools` 필드로 구성됩니다.

---

## 공지사항 (announcements)

> 태그: `admin-announcements`
> prefix: `/api/v1/admin/announcements`

사용자에게 표시할 공지를 관리합니다(사용자 수신 측 API는 별도). 라우터 레벨에서 `require_admin`이 적용됩니다.

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/announcements` | 공지 목록 (`AnnouncementAdminResponse[]`) | - |
| `POST` | `/api/v1/admin/announcements` | 공지 생성 (`201`) | `title`, `body`, `severity`, `target_type`, `target_id`, `starts_at`, `ends_at`, `is_active` |
| `PATCH` | `/api/v1/admin/announcements/{announcement_id}` | 공지 수정 | 위 필드 부분 갱신 |
| `DELETE` | `/api/v1/admin/announcements/{announcement_id}` | 공지 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/announcements/meta/options` | severity/target_type 등 선택지 메타 | - |

- `severity`: `info` 등(기본 `info`).
- `target_type`: 대상 범위(전체/프로젝트 등), `target_id`로 특정 대상 지정.
- `starts_at`/`ends_at`으로 노출 기간, `is_active`로 활성 여부 제어.

---

## k3s 클러스터 관리 (admin)

관리자가 전체 프로젝트의 k3s 클러스터를 조회·스케일·삭제·인증서 관리하는 엔드포인트입니다. 사용자용 k3s API와 달리 프로젝트 소유권에 관계없이 접근합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/k3s-clusters` | 전체 k3s 클러스터 목록 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}` | 클러스터 상세 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/kubeconfig` | kubeconfig 조회(복호화) |
| `PATCH` | `/api/v1/admin/k3s-clusters/{cluster_id}/scale` | 노드그룹 스케일 조정 |
| `DELETE` | `/api/v1/admin/k3s-clusters/{cluster_id}` | 클러스터 삭제 (`204`) |
| `POST` | `/api/v1/admin/k3s-clusters/{cluster_id}/delete-async` | 클러스터 비동기 삭제 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/ca-certificate` | 클러스터 CA 인증서 조회 |
| `GET` | `/api/v1/admin/k3s-clusters/{cluster_id}/certificate-expiry` | 인증서 만료 정보 |
| `POST` | `/api/v1/admin/k3s-clusters/{cluster_id}/rotate-certs` | 클러스터 인증서 회전 |
| `GET` | `/api/v1/admin/k3s-cluster-templates` | k3s 클러스터 템플릿 목록 |

**주의**: `delete`/`delete-async`는 VM·볼륨·네트워크 등 클러스터 리소스를 함께 정리하며 되돌릴 수 없습니다. `rotate-certs`는 진행 중 클러스터 접속에 일시적 영향을 줄 수 있습니다.
