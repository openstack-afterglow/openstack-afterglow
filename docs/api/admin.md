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
| `X-Project-Id` | (선택) 논리적 요청 프로젝트 UUID. 대상 ID만으로 Keystone 토큰의 실제 인증 범위나 서비스 조회 권한이 바뀌지는 않음 |

**모든 관리자 엔드포인트에는 `Depends(require_admin)`가 적용**됩니다(개별 데코레이터 또는 라우터 레벨 의존성으로 선언). 관리자가 아닌 사용자는 `403 Forbidden`을 받습니다. 아래 표에서는 이 사항을 매 행마다 반복하지 않습니다.

- 대부분의 라우터는 `/api/v1/admin` prefix에 마운트됩니다.
- 예외: 라이브러리 관리(`/api/v1/admin/libraries`), 공지(`/api/v1/admin/announcements`).
- 캐시 기반 조회 엔드포인트는 대부분 `refresh` (query, boolean, 기본 `false`) 파라미터로 캐시 무시 재조회를 지원합니다.
- 목록 조회는 대체로 `limit`(1~100, 기본 20) + `marker` 커서 페이지네이션을 사용하며 `{ "items": [...], "next_marker": ..., "count": N }` 형태로 응답합니다.

![관리자 개요](../../assets/admin-page.png)
*관리자 개요 페이지 — 클러스터 전체 vCPU·RAM·Disk 사용률, 총 VM/하이퍼바이저 수, 프로젝트별 리소스 할당량을 한 화면에서 조회*

---

## 이벤트 조사

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/api/v1/admin/events` | 모든 프로젝트의 활동·OpenStack 알림을 필터/커서로 조회 |
| `GET` | `/api/v1/admin/events/stats` | 현재 필터의 서비스·프로젝트·페이지·액션별 성공/실패 집계 |
| `GET` | `/api/v1/admin/events/{id}` | 실패 원인, actor, 대상과 요청/외부 이벤트 식별자 확인 |

필터, 수집 전제 및 기존 활동 API와의 차이는 [관리자 이벤트](events.md)를 참조하세요.

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

관리자 개요의 프로젝트별 리소스 표는 CPU·RAM·Disk 막대와 수치를 별도 공간에 표시합니다. 열 사이 간격을 유지하고 긴 수치는 해당 셀 안에서 줄바꿈하며, 좁은 화면에서는 표 내부를 가로 스크롤해 모든 열을 조회합니다. 프로젝트 행 선택은 기존 쿼터 패널을 열며 API 응답·쿼터 계산·저장 동작은 바뀌지 않습니다.

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
| `PUT` | `/api/v1/admin/hypervisors/{hypervisor_id}/service` | 연결 상태와 별개로 해당 호스트의 `nova-compute` 스케줄링 변경. 본문 `{ "status": "enabled" }` 또는 `{ "status": "disabled", "reason": "점검 사유" }`; 비활성화 사유 필수 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/relocate` | `up/disabled`일 때 `{ "mode": "migrate" }`로 전체 인스턴스 이동 요청, `down`일 때 원본 전원 차단·펜싱 확인 후 `{ "mode": "evacuate", "fenced": true }`로 대피 요청. 서버가 호스트 상태·소속을 재확인하고 모든 페이지를 읽으며 인스턴스별 `requested`/`failed`/`skipped` 결과를 반환 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/removal-check` | 캐시를 우회해 호스트 메타데이터·현재/보존 서버·이주·Placement tree를 점검. `{report, review_token, expires_at}`를 반환하고 모든 조건을 통과한 보고서에만 5분·1회용 승인 발급 |
| `POST` | `/api/v1/admin/hypervisors/{hypervisor_id}/remove` | 보고서 검토·실제 `nova-compute` 중지 확인·정확한 호스트명·제거 사유를 받은 뒤 최신 상태를 재점검하고 검증한 Nova compute service 등록만 삭제. 삭제 접수와 검증 완료를 구분 |

`state`(`up/down`)는 호스트 생존 상태, `status`(`enabled/disabled`)는 새 인스턴스 스케줄링 허용 여부로 독립입니다. 비활성화는 기존 인스턴스를 자동으로 이동시키지 않습니다. 전체 이동은 `ACTIVE`의 live migration과 `SHUTOFF`의 cold migration을 별도로 요청하고, 다른 상태는 이유와 함께 건너뜁니다. `down`만으로 호스트가 펜싱되었다고 판단할 수 없으므로, 대피 전 운영자가 원본의 전원 차단·격리를 반드시 확인해야 합니다. API의 `requested`는 Nova가 비동기 작업을 접수했다는 뜻이며 **이동 완료·복구 성공이 아닙니다**. 개별 VM의 상태와 목적지, cold migration의 `VERIFY_RESIZE` 확정 여부를 후속 확인하세요.

### 호스트 메타데이터 검토와 등록 제거

시스템 관리자 전용 기능입니다. 먼저 운영자가 해당 장비의 **실제 `nova-compute` 프로세스를 중지하고 계속 중지 상태로 유지**해야 합니다. 이 확인은 운영자의 승인 진술이며 Afterglow가 SSH·전원 제어로 수행하거나 증명하지 않습니다. `down`과 `forced_down`은 물리 종료 증거가 아닙니다. Nova 공식 [compute service 삭제 계약](https://docs.openstack.org/api-ref/compute/#delete-compute-service)에 따라 중지하지 않으면 compute node 등록이 다시 생길 수 있습니다. 물리 장비·다른 OpenStack 서비스·VM·스토리지는 삭제하지 않습니다.

1. 호스트 상세에서 **제거 점검 새로고침**을 선택합니다. 보고서는 정확한 hypervisor/service UUID 매핑과 단일 compute node, 양쪽 `disabled/down`, `forced_down=false`, 유효한 서비스 갱신 시각, 전체 프로젝트의 현재 서버·soft-deleted 서버, 보존 삭제 서버·이주 이력, Placement root와 모든 child provider의 consumer/resource 할당을 보여줍니다.
2. 실행 중 VM 수만 0인 것으로 충분하지 않습니다. `SHUTOFF` 등 모든 현재 서버와 soft-deleted 서버, 미완료 이주(`finished`/`VERIFY_RESIZE` 포함), GPU child를 포함한 Placement 할당이 있으면 차단합니다. 필수 조회·필드·전체 페이지·provider 매핑을 확인하지 못하면 `unknown`이며 승인 token을 발급하지 않습니다. 호스트의 정상 메모리 overhead가 0일 필요는 없습니다.
3. `service.updated_at`은 서비스 갱신/마지막 통신의 참고 값이며 실제 ping 시각은 아닙니다. Uptime은 정보이지 제거 허용 조건이 아닙니다. 실제 성공 관측만 Redis에 cloud/hypervisor/service별 30일 보관하고, 현재 조회가 실패하면 `source=last_observed`와 `observed_at`을 명시합니다. 이전 관측도 없으면 `unavailable`입니다. 과거 uptime으로 현재 생존·프로세스 중지를 추정하지 않습니다.
4. 보존 이력은 불완전합니다. 이미 정리된 서버·이력 및 Nova가 숨기는 cross-cell migration copies는 볼 수 없으며 빈 이력은 미사용 호스트라는 증거가 아닙니다. Migration completeness는 compute 2.58의 unpaged host-filtered 응답으로 확인하고 2.59의 UUID 페이지 조회와 대조합니다. Hidden 기록만 있는 중간 페이지에서 2.59 응답이 비더라도 뒤의 미완료 이주를 놓치지 않습니다. 한쪽 compute가 명시적 `null`인 완료된 실패 이력은 다른 쪽이 호스트와 정확히 일치하면 그대로 표시하며, 누락된 key·잘못된 값·모순된 응답은 `unknown`입니다. UUID가 없는 보존 기록은 ID와 UUID 미제공을 표시합니다.
5. 메타데이터 검토와 실제 프로세스 중지 checkbox, **정확한 호스트명** 및 공백이 아닌 제거 사유를 입력합니다. 요청 본문은 다음과 같습니다.

```json
{
  "review_token": "<removal-check에서 받은 1회용 token>",
  "confirm_hostname": "compute-host-name",
  "reason": "인스턴스 이동 및 실제 nova-compute 중지 후 장비 퇴역",
  "reviewed_metadata": true,
  "compute_stopped": true
}
```

승인은 사용자·프로젝트·cloud endpoint·hypervisor·service와 검토 fingerprint에 묶입니다. 제거 요청 시 token을 원자적으로 소비하고 호스트 작업 잠금 아래 다시 Nova/Placement를 조회합니다. 메타데이터 변경·만료·잘못된 호스트·차단 조건은 `409`, 승인/사유 누락은 `422`, coordination 불가 시 `503`이며 잠금 없는 삭제로 우회하지 않습니다. 승인 실패 후에도 token은 재사용하지 말고 새 점검·승인을 수행하세요. UI는 새 점검·수동 새로고침·호스트/프로젝트 변경·관련 상태 변경·만료·요청 실패에서 승인 입력을 초기화합니다. 시간/uptime 관측만 달라지면 검토 내용을 변경한 것으로 취급하지 않습니다.

Nova `DELETE /os-services/{service_uuid}`의 `204`는 접수입니다. 이후 service와 대체 등록, hypervisor, 검토한 Placement root/child provider의 부재 및 aggregate membership 제거를 별도로 조회합니다. 모두 확인한 `{status:"removed", verified:true}`만 UI가 완료로 표시하고 패널을 닫아 목록을 갱신합니다. 잔여 등록 또는 검증 실패는 `{status:"removal_unverified", verified:false, checks:[...]}`이며 보고서·차단 사유를 보존합니다. Nova가 거부하면 `409` 또는 `502`입니다. `forced_down` 설정, Placement 수동 삭제, 강제 workload 삭제는 하지 않습니다.

스케줄링·전체 호스트 이주도 같은 host lock을 사용합니다. 취소된 HTTP 요청의 SDK thread가 끝나기 전에 잠금을 해제하지 않으며, 잠금을 잃은 이후 이주 요청은 건너뜁니다. 점검·제거 감사 로그에는 actor·대상·사유·검토/최신 check·검증 결과를 남기고 review token은 남기지 않습니다. 삭제 시도 뒤 관련 호스트 목록·모니터링·개요·서비스·GPU cache를 무효화합니다.

`removal_unverified`처럼 HTTP 200으로 반환하는 비검증 결과도 감사 status는 `failed`입니다. 자동 middleware는 endpoint의 terminal 실패 이력을 2xx 기반 성공으로 덮어쓰거나 중복 추가하지 않으며, 명시적 terminal 기록이 없는 4xx/5xx와 예외는 계속 자동 기록합니다.

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
*전체 프로젝트의 볼륨을 시계열 차트와 함께 일괄 조회 — 양수 상태만 노출하는 상태·프로젝트 필터, 현재 page 선택, 확인 기반 부분 성공 일괄 삭제, 단건 수정·삭제 지원*

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/volumes/status-summary` | 상태별 볼륨 수 집계 | - |
| `GET` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 상세 조회 | - |
| `PATCH` | `/api/v1/admin/volumes/{volume_id}` | 이름/설명 수정 | `name`, `description` (모두 선택) |
| `DELETE` | `/api/v1/admin/volumes/{volume_id}` | 볼륨 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/bulk-delete` | 최대 50개 볼륨 일괄 삭제, ID별 성공/실패 반환 | `volume_ids` (중복 없는 1~50개) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/force-delete` | 강제 삭제 (`204`) | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/extend` | 용량 확장 | `new_size` (현재보다 커야 함) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/reset-status` | 상태 강제 초기화 | `status` (기본 `available`) |
| `POST` | `/api/v1/admin/volumes/{volume_id}/transfer` | 다른 프로젝트로 볼륨 이관 | 대상 프로젝트 지정 |
| `GET` | `/api/v1/admin/volumes/{volume_id}/delete-diagnostics` | 삭제 실패 원인 진단 | - |
| `POST` | `/api/v1/admin/volumes/{volume_id}/recover-delete` | 삭제 실패 복구 시도 | - |

**제한**: `force-delete` / `reset-status`는 Cinder의 정상 상태 전이를 우회하므로 데이터 정합성 위험이 있습니다. 오류 상태 복구 용도로만 사용하고, `extend`는 축소가 불가능합니다.

`bulk-delete`는 요청 순서대로 모든 ID를 처리하며 한 볼륨의 Cinder 거부가 다음 삭제를 중단하지 않습니다. 응답은 `{ "results": [{ "id": "...", "ok": true, "error": null }] }` 형태이고, 연결·상태 경쟁으로 삭제할 수 없는 볼륨은 `ok: false`와 항목별 오류 메시지를 반환합니다. 관리자 화면의 전체 선택은 현재 marker page에만 적용되며, 필터·page size·page·project scope 변경 시 초기화됩니다. 성공한 ID만 선택에서 제거하고 실패한 ID는 재확인을 위해 유지합니다. 상태 card와 선택지는 `status-summary`에서 count가 0보다 큰 상태만 표시합니다.

새 filter/page/project 결과를 기다릴 때 이전 행을 즉시 지워 stale 선택을 막습니다. 확인 대기 중 결과 경계나 user/project가 바뀌면 요청을 보내지 않습니다. 같은 결과의 백그라운드 새로고침은 기존 행을 유지합니다. 항목별 실패는 고정된 공개 메시지이며 upstream 응답·접속 정보·credential을 응답이나 activity에 복제하지 않습니다.

두 endpoint는 요청 token으로 만든 **system-admin connection**을 그대로 사용하며 volume project로 재범위화하지 않습니다. Cinder message는 원인 추정용 evidence일 뿐 삭제 허용 근거가 아닙니다. 진단은 Cinder volume/attachment/snapshot/backup/clone/group·migration, Nova attachment, 선택적 Ceph RBD 상태를 각각 `present | absent | unknown`으로 반환합니다. 필수 check 하나라도 `unknown`이면 fail-closed로 `recovery_available=false`이고 복구는 `blocked`입니다. 401/403, timeout, SDK/CLI parse 오류를 `absent`로 바꾸지 않습니다.

RBD 검사가 활성화되면 `backend`에 `mode`, `classification`, pool, image name/id, size/order, parent를 반환합니다. Cinder의 404만으로 `already_deleted`를 확정하지 않습니다. RBD image/header/data/trash가 남아 있으면 `api_absent_backend_present`, 조회가 불완전하면 `backend_lookup_unknown`입니다. `rbd_id.volume-<uuid>`만 빠지고 directory·image id·size/order·parent·watcher/snapshot/child 상태가 일치할 때만 mapping을 복원합니다. 반대로 stale mapping 제거는 Cinder와 모든 backend artifact의 부재가 확인되고 mapping payload가 예상 image id와 정확히 같을 때만 실행합니다. Image data/header/trash 자체는 이 API가 삭제하지 않습니다.

복구 결과 `status` 계약:

- `deleted`, `already_deleted`: Cinder 부재와 활성화된 RBD backend 부재가 검증된 terminal success
- `delete_submitted`: Cinder 삭제 요청은 수락됐지만 아직 Cinder record가 남아 있음
- `backend_residue`: Cinder record는 사라졌지만 RBD residue가 확인됨
- `backend_unverified`: Cinder record는 사라졌지만 RBD 검사가 비활성 또는 `unknown`
- `blocked`: dependency, attachment, fresh `deleting`, 권한/인증, backend 불일치 또는 unknown 때문에 mutation하지 않음
- `failed`: 허용된 mutation 자체가 실패함

`verified_deleted`는 `deleted`/`already_deleted`에서만 `true`입니다. `backend_verification`은 `verified | unavailable | residue | unknown`, `quota_verification`은 `verified | mismatch | unavailable`을 별도로 반환합니다. UI는 terminal success에서만 상세 패널을 닫고 `delete_submitted`, residue, unverified 결과에서는 check·backend evidence를 유지한 채 상세를 새로고침합니다.

Recovery는 볼륨별 Redis `NX EX=600` lock을 잡습니다. 같은 볼륨의 동시 요청은 HTTP 409, Redis 장애는 fail-closed HTTP 503이며 lock은 `finally`에서 소유 token과 일치할 때만 해제합니다. 모든 결과와 단계, backend/quota 검증은 감사 로그에 기록됩니다.

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
| `POST` | `/api/v1/admin/libraries/consume` | 프로필 또는 완료된 Dockerfile 작업의 고정 artifact ID로 소비 인스턴스 생성 |
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
| `GET` | `/api/v1/admin/projects` | 전체 inventory 검색·필터·최신 생성순 후 marker 페이지네이션 | - |
| `GET` | `/api/v1/admin/projects/names` | 전체 프로젝트 id/name 목록 (페이지네이션 없음) | - |
| `POST` | `/api/v1/admin/projects` | 프로젝트 생성 (`201`) | `name`(필수), `description`, `domain_id`, `enabled` |
| `GET` | `/api/v1/admin/projects/{project_id}` | 프로젝트 상세 | - |
| `PATCH` | `/api/v1/admin/projects/{project_id}` | 프로젝트 수정 | `name`, `description`, `enabled` (선택) |
| `GET` | `/api/v1/admin/projects/{project_id}/deletion-check` | 대상 프로젝트의 실제 할당 리소스를 캐시 없이 검사 | - |
| `DELETE` | `/api/v1/admin/projects/{project_id}` | 새 리소스 검사를 통과한 빈 프로젝트만 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/projects/{project_id}/members` | 사용자·그룹 역할 할당 목록 | - |
| `GET` | `/api/v1/admin/projects/{project_id}/activity` | 프로젝트 활동 로그 | - |
| `POST` | `/api/v1/admin/projects/{project_id}/sync-monitoring-sg` | 모니터링용 보안 그룹 동기화 | - |

`GET /projects` query는 `limit`(기본 20, 1–100), `marker`, `search`(이름·전체 ID·설명의 앞뒤 공백 제거/대소문자 무시 부분 검색), `enabled`(`true`/`false`)와 `domain_id`를 받습니다. 조건은 AND로 결합하며 전체 목록을 필터·정렬한 뒤 페이지를 나눕니다. 기존 `items`/`next_marker`/`count`에 필터 결과 총계 `total`과 검색 조건에 제한되지 않는 도메인 후보 `domain_ids`를 추가합니다. 마지막 페이지에는 `next_marker: null`을 반환합니다. 사라졌거나 현재 결과에 없는 marker는 `400`이며 화면의 새로고침으로 첫 페이지에 돌아갈 수 있습니다.

프로젝트·그룹 `created_at`은 Keystone의 유효한 시각을 우선하고, 없으면 해당 resource ID의 성공한 `project.create`/`project_create`/`identity.project.created` 또는 대응 group 생성 이벤트의 가장 이른 UTC 시각을 사용합니다. 수정·실패·단순 최초 활동 시각은 생성일로 사용하지 않습니다. UTC 마이크로초를 보존해 생성일 내림차순, 동률은 ID 내림차순으로 정렬하며 기록이 없거나 activity DB를 읽을 수 없으면 `null` 항목을 마지막에 둡니다. Afterglow 이전 또는 외부에서 생성된 항목, 수집되지 않았거나 보존기간 밖의 생성 이벤트는 생성 순서를 복원할 수 없습니다.

관리자 생성은 새 resource ID를 포함한 성공 이벤트를 기록합니다. 프로젝트 생성·수정·삭제와 셀프서비스 생성은 프로젝트 inventory 및 이름 cache를 무효화합니다. UI의 검색·상태·도메인 변경은 첫 페이지로 돌아가고, 백그라운드 갱신과 다음 페이지 prefetch는 현재 조건을 유지합니다.

같은 backend 프로세스·event loop에서는 mutation의 cache 무효화가 이전 조회 flight를 분리하고 늦은 snapshot의 cache 재저장을 막습니다. 무효화 이전 호출자는 이전 결과를 받을 수 있으나 이후 목록 조회는 그 작업에 합류하지 않습니다. 정상 cache I/O에 대한 국소 순서 보장이며 다른 worker의 진행 중 조회까지 fence하는 분산 보장은 아닙니다.

`GET /projects/{project_id}/members` 응답에는 사용자 할당과 그룹 할당(`type: "group"`, `group_id` 포함)이 함께 반환됩니다.

### 프로젝트 삭제 전 리소스 재확인

프로젝트 목록에서 삭제를 선택하면 기존 확인 modal 안에서 새 검사를 시작합니다. 검사 중에는 삭제가 비활성화되고, 남은 리소스 수와 유형별 최대 5개 이름·ID, 조회 실패 사유를 표시합니다. **리소스 다시 확인**은 이전 빈 결과를 폐기하고 새로 조회합니다. 선택 프로젝트·사용자·인증 프로젝트·토큰 변경이나 modal 닫기 뒤의 늦은 결과는 사용하지 않습니다. 긴 결과 목록만 `40dvh` 안에서 스크롤하여 취소·삭제 버튼을 유지합니다.

두 endpoint는 검증된 요청자의 `get_os_conn`을 그대로 사용합니다. 쿼터·dashboard cache·프런트엔드 서비스 활성화 flag는 빈 프로젝트의 증거가 아닙니다. 각 공급자의 모든 페이지와 실제 소유권을 확인하며, 중지·오류·shelved VM과 연결되지 않은 `available` 볼륨도 포함합니다. 명시적으로 다른 프로젝트 소유인 공유·외부 리소스는 제외하지만 대상 소유인 외부 네트워크는 포함합니다.

검사 범위는 다음 28개 유형입니다. 핵심 서비스는 필수이고, 선택 서비스는 **인증된 catalog에서 부재가 확인된 경우에만** 건너뜁니다.

| 서비스 | 검사 유형 |
|---|---|
| Nova | `instances`, `server_groups` |
| Cinder | `volumes`, `volume_snapshots`, `volume_backups` |
| Neutron | `networks`, `subnets`, `routers`, `ports`, `floating_ips`, `security_groups` |
| Glance | `images` — hidden/visible 두 구간과 community/shared 이미지 포함 |
| Octavia | `load_balancers` |
| Manila | `shares`, `share_snapshots`, `share_networks`, `security_services` |
| Swift/RGW | `object_containers` — 빈 컨테이너·segment/trash 등도 포함 |
| Barbican | `secrets`, `secret_containers`, `secret_orders` — payload는 조회·반환하지 않음 |
| Trove | `database_instances`, `database_backups`, `database_configurations` |
| Zun | `containers` |
| Magnum | `clusters`, `cluster_templates` |
| Heat | `stacks` — nested/hidden stack 포함 |

대상 소유 보안 그룹 중 `name=default`인 한 개만 자동 baseline 예외로 제외합니다. 공개 API의 이름 판정이며 DB `is_default` 판정을 주장하지 않습니다. 같은 이름의 대상 소유 그룹이 여러 개면 소유권이 모호한 것으로 차단합니다. Neutron은 GET 과정에서 자동 기본 그룹을 보장할 수 있지만 검사기가 명시적 자원 생성·삭제를 요청하지는 않습니다.

#### 다른 프로젝트를 조회하는 관리자 인증 범위

관리자 목록의 대상 프로젝트와 토큰의 실제 프로젝트는 다를 수 있습니다. 논리적 `X-Project-Id`만으로 account-scoped 목록을 대상 소유라고 추정하거나 서비스 password로 재인증하지 않습니다.

**native admin 전제:** Afterglow 시스템 관리자 판정은 Keystone `system:all` 등 별도 역할 할당을 사용하지만 공급자는 요청의 project-scoped 토큰을 인가합니다. Cinder `all_tenants`, Neutron `project_id`, Glance `owner`, Heat 목록은 관리자 문맥이 없으면 HTTP 200으로 호출자 범위만 반환할 수 있습니다. 따라서 토큰에 `admin` 역할(대소문자 무시)과 `is_admin_project=true`(Keystone이 값을 생략하면 기본 `true`)가 없으면 공급자 조회 없이 28개 유형 전체를 `admin_authority_unverified`로 반환하고 DELETE는 `503`입니다. UI는 admin 역할이 있는 관리자 프로젝트로 전환한 뒤 재확인하라고 안내합니다.

| 서비스 | 다른 프로젝트 검사 정책 |
|---|---|
| Trove DB | `/mgmt/instances` 관리자 목록에서 실제 owner를 검사 |
| Trove 백업 | `/backups?all_projects=True&project_id=<target>` 관리자 조회 후 owner 재검사 |
| Trove 구성 | 관리자 전체 목록을 확인하지만 2025.2 목록 응답은 owner를 반환하지 않음. 행이 있으면 target token이어도 `resource_ownership_unverified`; 빈 전체 목록만 빈 것으로 인정 |
| Magnum | 관리자 전체 목록 사용. cluster는 owner를 유지하는 `/clusters/detail`, template은 `/clustertemplates`; 실제 `project_id` 검사 |
| Heat | 기본 정책이 `deny_everybody`인 `global_tenant`는 쓰지 않음. 관리자 문맥의 일반 `/stacks?tenant=<target>&show_nested=True&show_hidden=True`가 반환하는 `project`를 검사 |
| Swift/RGW | 실제 토큰 프로젝트가 대상과 같고 account endpoint가 `AUTH_<target>`인 경우만 검사 |
| Barbican | 실제 토큰 프로젝트가 대상과 같은 경우만 프로젝트의 secret/container/order 목록 검사 |

권한 부족·정책 거부·소유권 누락은 빈 목록으로 축소하지 않습니다. Swift/Barbican의 범위 불일치는 **관리자 범위에서 확인 불가**와 대상 프로젝트에 admin 역할이 있는 관리자 계정으로 프로젝트를 전환한 뒤 재확인하라는 조치를 표시합니다. 역할을 자동 부여하지 않으며, 권한이 없으면 삭제는 계속 차단됩니다. Trove 구성은 cloud 어디에든 구성 그룹이 있으면 owner를 확인할 수 없어 차단될 수 있으며, target token으로도 보완되지 않습니다. 강제 우회는 없습니다. Heat는 공급자의 `context_is_admin` 기본값(`role:admin and is_admin_project:True`)과 Afterglow 전제가 일치한다고 가정합니다. 이 정책을 변경한 배포에서 빈 결과는 검증 공백입니다.

관련 공급자 계약: [Trove 백업 관리자 조회](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/backup/service.py), [Trove 구성 전체 조회](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/configuration/models.py)와 [소유권 미제공 응답](https://raw.githubusercontent.com/openstack/trove/stable/2025.2/trove/configuration/views.py), [Magnum cluster detail/관리자 목록](https://raw.githubusercontent.com/openstack/magnum/stable/2025.2/magnum/api/controllers/v1/cluster.py), [Heat 목록](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/api/openstack/v1/stacks.py)·[global_index 정책](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/policies/stacks.py)·[관리자 tenant 필터](https://raw.githubusercontent.com/openstack/heat/stable/2025.2/heat/db/api.py).

#### 응답과 최종 삭제

GET은 검사 결과가 차단이어도 `200`과 `{project_id, checked_at, can_delete, resources}`를 반환합니다. `checked_at`은 검사 완료 UTC 시각이며 원자적 cloud snapshot을 뜻하지 않습니다. `resources`의 각 항목은 `{kind, service, status, count, samples, reason}`입니다.

| `status` | `count` | 의미 |
|---|---|---|
| `ok` | 0 이상의 정수 | 해당 유형의 전체 조회와 대상 소유권 검사 완료 |
| `unavailable` | `null` | 조회·전체 페이지·소유권·인증 범위를 확인하지 못함. 0개가 아님 |
| `skipped` | `null` | 인증된 catalog에서 선택 서비스가 없음 (`service_not_present`) |

샘플은 제한된 ID·이름·상태만 반환합니다. 조회 실패 시 부분 count/샘플은 폐기하고 원본 provider 오류·토큰·endpoint URL·secret payload는 공개하지 않습니다. 공개 사유는 `resource_check_failed`, `resource_ownership_unverified`, `admin_authority_unverified`, `project_scope_unverified`, `service_catalog_unavailable`, `service_not_present`입니다.

DELETE는 GET 결과의 시각이나 UI 확인 여부에 의존하지 않고 같은 검사를 **다시 수행**합니다. 하나라도 `unavailable`이면 잔여 리소스 유무보다 불확실성을 우선하여 `503`, 확인된 할당이 남으면 `409`입니다. 오류 `detail`은 `{code, message, check}`이며 code는 각각 `project_resource_check_failed` / `project_has_resources`입니다. 어느 경우에도 Keystone DELETE를 호출하지 않습니다. 모든 적용 항목이 `ok/count=0` 또는 확인된 `skipped`인 경우에만 정확한 프로젝트를 삭제하고 inventory/name cache를 무효화합니다. UI는 최종 거부 보고서를 표시하며 확인 창을 유지합니다. 취소된 검사 thread가 끝나기 전에 요청 connection을 닫지 않고, 검사 도중 요청 취소는 Keystone 삭제를 예약하지 않습니다.

**한계:** 자원 자동 정리·force 옵션·cloud-wide freeze는 없습니다. 최종 재검사는 이전 확인 결과의 stale race를 줄이지만 독립 서비스 간 분산 트랜잭션이 아니므로 마지막 조회 뒤 새 자원이 생성되는 경쟁까지 제거하지 않습니다.

---

## 쿼터 관리

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/admin/quotas/{project_id}` | 대상 프로젝트의 Nova·Cinder·Neutron·선택적 Manila 쿼터 한도와 사용량 조회 |
| `PUT` | `/api/v1/admin/quotas/{project_id}` | 요청 본문에 포함된 쿼터만 대상 프로젝트에 적용 |

`GET` 응답의 `compute`, `volume`, `network`, `file_storage`는 각 서비스의 `{필드명: {limit, in_use}}` 객체입니다. `limit: -1`은 무제한입니다. 상세 사용량을 조회하지 못한 서비스는 **`null`**이며 `availability[서비스] = false`, `errors[서비스] = "quota_unavailable"`입니다. Manila가 비활성화되었으면 `file_storage: null`과 `errors.file_storage = "service_disabled"`입니다. 배포 환경이 노출하지 않는 개별 필드는 0으로 채우지 않고 생략하므로 해당 항목을 조정할 수 없습니다. 다른 서비스 조회 실패가 정상 서비스의 쿼터를 숨기지는 않습니다.

| 서비스 | `GET` 필드 (프로바이더 이름) | `PUT` 필드 (변경할 항목만 전송) |
|--------|------------------------------|-----------------------------------|
| `compute` (Nova) | `instances`, `cores`, `ram` (MB), `metadata_items`, `key_pairs`, `server_groups`, `server_group_members`, `injected_files`, `injected_file_content_bytes`, `injected_file_path_bytes` | 동일 |
| `volume` (Cinder) | `volumes`, `snapshots`, `gigabytes` (볼륨·스냅샷의 총 GiB) | 동일 |
| `network` (Neutron) | `network`, `subnet`, `port`, `router`, `floatingip`, `security_group`, `security_group_rule` | 동일 |
| `file_storage` (Manila) | `shares`, `gigabytes`, `snapshots`, `snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots` | `shares`, `share_gigabytes`, `share_snapshots`, `share_snapshot_gigabytes`, `share_networks`, `share_groups`, `share_group_snapshots` |

```json
{
  "project_id": "project-uuid",
  "compute": {"instances": {"limit": 20, "in_use": 5}, "cores": {"limit": 40, "in_use": 10}, "ram": {"limit": 81920, "in_use": 20480}},
  "volume": {"volumes": {"limit": 10, "in_use": 3}, "snapshots": {"limit": 10, "in_use": 2}, "gigabytes": {"limit": 1000, "in_use": 200}},
  "network": {"security_group": {"limit": 20, "in_use": 4}, "security_group_rule": {"limit": 100, "in_use": 12}},
  "file_storage": {"shares": {"limit": 10, "in_use": 2}, "share_groups": {"limit": 5, "in_use": 1}},
  "availability": {"compute": true, "volume": true, "network": true, "file_storage": true},
  "errors": {}
}
```

`PUT`은 최상위 JSON 정수 필드로 한도 `-1` 이상을 받습니다. 빈 본문·`null`·지원하지 않는 필드는 `422`입니다. 서비스마다 독립적으로 적용되므로 관리자 화면은 수정한 서비스의 필드만 저장합니다. 여러 서비스를 함께 변경하는 API 요청이 부분 성공하면 `status: "partial"`, 성공한 `updated` 서비스 목록, 실패한 `errors` (`update_failed` 또는 `service_disabled`)를 반환합니다. 부분 성공을 원자적 성공으로 간주하지 말고 다시 조회해야 합니다. GPU 한도 및 flavor access는 별도의 관리자 GPU/compute-policy API를 사용합니다.

```json
{"status":"updated","project_id":"project-uuid","updated":["network"],"errors":{}}
```

---

## 그룹 관리

| 메서드 | 경로 | 설명 | 요청 본문 |
|--------|------|------|-----------|
| `GET` | `/api/v1/admin/groups` | 생성일이 포함된 전체 그룹 목록, 최신 생성순 | - |
| `POST` | `/api/v1/admin/groups` | 그룹 생성 (`201`) | `name`(필수), `description`, `domain_id` |
| `PATCH` | `/api/v1/admin/groups/{group_id}` | 그룹 수정 | `name`, `description` (선택) |
| `DELETE` | `/api/v1/admin/groups/{group_id}` | 그룹 삭제 (`204`) | - |
| `GET` | `/api/v1/admin/groups/{group_id}/users` | 그룹 멤버 목록 | - |
| `PUT` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에 사용자 추가 (`204`) | - |
| `DELETE` | `/api/v1/admin/groups/{group_id}/users/{user_id}` | 그룹에서 사용자 제거 (`204`) | - |

그룹 응답은 배열 계약을 유지하며 각 항목에 nullable `created_at`을 포함합니다. 전체 그룹에서 이름·전체 ID·설명을 검색하고 `domain_id`로 AND 필터링하는 것은 브라우저에서 수행하며, 검색·필터·초기화는 멤버 관리와 독립적입니다. 조회·갱신 후에도 조건을 유지하고 생성·수정·삭제 후 서버 inventory cache를 무효화합니다. 목록 중간에 Keystone 조회가 실패하면 부분 목록 대신 `500`을 반환합니다.

**주의**: 멤버십 변경 시 Keystone이 관련 토큰을 revoke할 수 있어 관련 세션 캐시가 함께 삭제됩니다.

---

## 역할·시스템 역할 관리

프로젝트 스코프 역할(assign/assign-group)과 시스템 스코프 역할(system-roles)을 구분해 관리합니다.

| 메서드 | 경로 | 설명 | 파라미터/본문 |
|--------|------|------|---------------|
| `GET` | `/api/v1/admin/roles` | 실제 역할과 직접·간접 상속 목록 | `refresh=true`로 캐시 우회 |
| `GET` | `/api/v1/admin/roles/presets` | 변경 없는 프로젝트/서비스 역할·상속 프리셋 미리보기 | - |
| `POST` | `/api/v1/admin/roles/presets/apply` | 기존 ID를 재사용하는 명시적 멱등 프리셋 적용 | 시스템 관리자 확인 뒤 호출 |
| `POST` | `/api/v1/admin/roles` | 역할 생성 (`201`) | `name`, 선택 `description`, `domain_id` (body) |
| `PATCH` | `/api/v1/admin/roles/{role_id}` | 이름·설명 편집 | 변경할 `name` 또는 `description` (body); 도메인은 변경 불가 |
| `DELETE` | `/api/v1/admin/roles/{role_id}` | 할당·연결이 없는 역할 삭제 | - |
| `PUT` | `/api/v1/admin/roles/{prior_role_id}/implies/{implied_role_id}` | 직접 하위 역할 선택·연결 | 상위·하위의 정확한 역할 ID |
| `DELETE` | `/api/v1/admin/roles/{prior_role_id}/implies/{implied_role_id}` | 해당 직접 연결만 해제 | 간접 상속 경로는 유지될 수 있음 |
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

역할 CRUD·상속·프리셋 적용은 서버가 검증한 시스템 관리자에게만 열립니다. 프로젝트 `admin` 이름이나 기존 DB manager 기록은 권한이 아닙니다. 프로젝트 owner/admin은 별도의 [프로젝트 API](projects.md)에서 안전한 현재 역할 ID로 멤버 권한을 관리합니다. 일반 사용자 identity 응답은 표시용 이름과 OpenStack `can_write`를 분리하고, 독립 서비스는 현재 `service_permissions`로 액션을 판단합니다. 초대는 `project_member`·`project_reader`만 선택할 수 있습니다.

목록 항목은 `id`, `name`, `description`, `domain_id`, `protected`, `system_only`, `implied_role_ids`(직접 하위), `inherited_role_ids`(전체 하위), `parent_role_ids`(직접 상위)를 반환합니다. `A → B`는 A 보유자가 B 권한을 얻는다는 뜻입니다. 화면의 `admin → manager → member → reader`는 실제 Keystone에 저장된 연결을 표시하며, 목록 조회로 기본 계층을 자동 생성하지 않습니다. 이름·ID·상속 수 정렬, 이름/ID/설명 검색, 다중 부모·공유 역할을 표시하는 상속 트리를 제공합니다.

새 역할 및 이름 변경은 `area_grade` 형식입니다. 영역과 등급을 각각 소문자로 바꾸고 연속 공백을 `-`로 치환합니다(경계 공백도 동일). 예: `My Area_Read Only` → `my-area_read-only`. UI는 영역/등급 입력과 전송될 정확한 이름을 미리 보여줍니다. native core 역할과 `project_owner`는 이름 변경·삭제를 보호합니다.

프리셋 미리보기는 읽기 전용입니다. 적용은 기존 `project_owner/project_admin/project_member/project_reader`와 native `member/reader` ID를 보존하고, 빠진 서비스 부모·세부 역할·직접 inference edge만 추가합니다. 재실행은 이미 있는 역할/edge를 다시 만들지 않습니다. 실제 그래프가 불명확하거나 안전 경계를 넘으면 적용하지 않습니다. 중간 실패는 `created_roles`, `created_implications`와 원인을 반환하므로 현재 목록을 확인한 뒤 같은 프리셋을 재실행합니다. 계층은 런타임의 이름 기반 가상 확장이 아닙니다.

프리셋의 서비스 부모는 `<service>_admin/editor/user/reader`, 세부 권한은 `<service>-<area>_<grade>`입니다. editor는 생성·편집만, user는 허용된 사용·다운로드만, reader는 비밀 없는 메타데이터만 허용합니다. destructive/security 액션은 별도 admin leaf입니다. 프로젝트 관리자나 서비스 admin으로 시스템 역할·전역 Drover 관리자 API·Palimpsest builder/GC 권한을 얻지 않습니다. 일반 역할 assign/assign-group API에서 소유자 계층을 우회할 수 없으며 소유권은 프로젝트 전용 워크플로를 사용합니다.

서버는 최신 그래프와 endpoint별 Redis lease 아래 변경을 검사합니다. 자기 상속·직접/간접 순환·기본 역할의 역방향 승격·사용자 정의 역할의 `admin`/`manager` 상속은 `409`입니다. 도메인 역할은 같은 도메인 또는 전역 하위 역할만 상속할 수 있고, 전역 역할은 전역 하위 역할만 상속할 수 있습니다. 기본 네 역할은 이름 변경·삭제가 금지되며 설명과 안전한 하위 연결만 편집합니다. 역할 삭제는 사용자·그룹 할당이나 직접 상위/하위 연결이 있으면 `409`, 대상이 없으면 `404`, 그래프·잠금·필수 세션 회수를 확인할 수 없으면 `503`입니다. Keystone 변경 뒤 세션 회수 실패도 `503`이므로 재시도 전에 목록을 새로 확인합니다.

권한을 바꾸는 이름·연결 수정은 직접·그룹·상속 할당의 영향받은 사용자 세션을 회수하고 역할 cache를 무효화합니다. HTTP 요청 취소 이후에도 이미 진행된 변경과 필수 세션 회수를 끝내며 감사 로그를 남깁니다. 목록 조회 실패를 빈 정상 목록으로 바꾸지 않으며, UI는 이전 행을 남기되 최신 조회가 성공할 때까지 변경을 비활성화합니다. Lease는 Afterglow 간 변경을 직렬화할 뿐 Keystone CLI 등 외부 변경을 잠그는 분산 트랜잭션은 아닙니다.

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

사용자 flavor 목록은 Redis cache hit로 payload가 일반 dict가 된 경우에도 `FlavorInfo`로 다시 해석한 뒤 frontend visibility와 GPU 쿼터를 판정합니다(캐시 payload가 `extra_specs`를 이미 보존하므로 flavor별 Nova 재조회는 하지 않습니다). GPU quota DB, Nova server inventory, 또는 legacy flavor metadata를 확인할 수 없으면 GPU flavor를 목록에서 숨기거나 `in_use=0`으로 간주하지 않습니다. 해당 flavor는 `eligibility.selectable=false`와 `gpu_quota_unavailable` blocker를 유지하고, authority 실패는 warning으로 기록됩니다.

GPU 사용량은 인증된 project scope와 대상 `project_id`가 다를 때만 Nova의 all-project inventory를 조회한 뒤 대상 project로 제한합니다. 같은 scope의 connection은 전역 inventory를 요청하지 않습니다. Microversion 2.47+ embedded flavor snapshot(`original_name` + `extra_specs`)은 `extra_specs`가 비어 있어도 authoritative로 취급하며 legacy snapshot만 flavor 상세를 조회합니다. 저장된 legacy alias(`RTX3090Ti` 등)는 읽기에서 canonical alias로 정규화하며 같은 alias의 중복 row는 `updated_at`이 가장 최신인 row(동률이면 `id`가 큰 row)의 limit를 사용합니다. PUT/DELETE도 같은 기준으로 survivor를 고른 뒤 중복 row를 제거합니다. Migration `079_normalize_gpu_quota_types.sql`은 동일 규칙으로 중복을 정리하고 `gpu_type`만 정규화하며 `updated_at`을 보존합니다.

관리자 쿼터 화면은 `GET /api/v1/admin/gpu-aliases`의 클러스터 전체 alias(Flavor `pci_passthrough:alias` + Placement inventory), 전체 기본값, 선택 프로젝트의 effective quota/usage를 합쳐 GPU 타입 행을 구성합니다. 따라서 프로젝트에 저장된 row나 현재 사용량이 없어도 RTX3060·RTX3090 같은 클러스터 GPU 타입이 표시되며 즉시 프로젝트 limit을 설정할 수 있습니다. 별도 기본값이 없는 타입의 effective limit은 `0`입니다.

Private GPU Flavor가 `extra_specs["afterglow:access_mode"] = "gpu_quota"`이면 access reconcile 대상입니다. Reconcile은 Flavor의 GPU 요구량을 effective project limit과 비교하고 Nova Flavor Access의 현재 tenant 목록을 읽어 `add`·`remove`·`none`을 계산합니다. `/api/v1/admin/flavors/access-reconcile`의 `apply=false`는 관리자 화면의 `권한 추가/회수 예정` 미리보기만 만들며 Nova 권한을 변경하지 않습니다. 실제 `addTenantAccess`/`removeTenantAccess` 호출은 `apply=true` 또는 `PUT /api/v1/admin/compute-policy/{project_id}`의 통합 정책 적용 시 수행됩니다. 관리자 Flavor 목록은 이 정책을 Private GPU 행의 `Quota 연동` 또는 `수동` 배지로 표시합니다.

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

### 관리자 화면의 필터·정렬

`/admin/services`의 9개 탭은 조회한 category 데이터 안에서 필터·검색·정렬합니다. 필터 조작은 추가 API 요청이나 클라우드 서비스 상태 변경을 일으키지 않습니다.

| 탭 | 조합 가능한 조건 | 정렬 |
|---|---|---|
| Compute / Block Storage / File Storage / Orchestrator / Container / Magnum | Binary, Host, 표시되는 경우 Zone, Status, State | 표시되는 모든 열; Updated는 UTC 시각 기준 |
| Network | Agent Type, Binary, Host, Zone, Alive, Admin State | 표시되는 모든 열; Alive와 Admin State는 독립 |
| API Endpoints | 이름, 서비스 유형, 리전 | 이름, 서비스 유형, 리전 |
| Storage Pools | backend, protocol, vendor | 이름, backend/protocol/vendor, 전체·남은·할당 용량(숫자) |

- 조건은 AND로 적용합니다. 예: Network에서 `Alive=down`, `Host=compute2`, `Admin State=UP`을 동시에 선택할 수 있습니다. Alive 미확인은 down과 별개입니다.
- 검색은 대소문자와 양끝 공백을 무시하고 공백으로 나눈 모든 검색어를 메타데이터에서 찾습니다. API Endpoints의 URL과 Storage Pools의 driver version도 검색 대상입니다.
- 문자열은 `host2`가 `host10`보다 앞서는 자연 정렬이며, 용량은 표시 문자열이 아닌 숫자 기준입니다. 비어 있거나 유효하지 않은 정렬 값은 오름차순·내림차순 모두 마지막에 둡니다. 같은 값의 원래 순서는 유지합니다.
- 표 머리글의 버튼은 클릭 또는 키보드로 방향을 전환하며 `aria-sort`를 제공합니다. 작은 화면에서는 표를 가로 스크롤하지 않고 상단 정렬 선택기와 방향 버튼을 사용할 수 있습니다.
- 탭별 검색·필터·정렬은 페이지가 유지되는 동안 탭 전환과 수동/자동 새로고침 뒤에도 남습니다. 다른 페이지 이동이나 전체 새로고침 이후의 영속화는 하지 않습니다.
- 초기 로딩과 백그라운드 새로고침을 구분합니다. 새로고침 중에는 기존 행에서 계속 필터·정렬할 수 있습니다. 선택지가 새 응답에서 사라져도 선택을 보존하며 `표시 / 전체` 건수와 초기화 동작을 제공합니다. 원본 0건과 조건에 맞는 결과 0건을 구분합니다.
- User/project identity가 바뀌면 이전 서비스 행을 즉시 비우고 늦게 도착한 응답을 차단합니다. 같은 identity의 token 갱신은 기존 행과 필터를 유지하면서 새 요청 세대를 사용합니다.
- 초기화는 현재 탭에만 적용하며 API Endpoints는 이름 오름차순, 나머지 탭은 응답 원본 순서로 돌아갑니다. 기존 lazy load·hover prefetch·선택 탭 refresh 계약은 바뀌지 않습니다.

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

관리자 화면의 특정 사용자·프로젝트 대상은 긴 native 선택 목록 대신 `SearchSelect`로 고릅니다. 팝오버 검색은 표시 이름과 stable ID를 모두 대상으로 하며 키보드 방향키·Enter·Escape를 지원합니다. 대상 유형을 바꾸면 이전 `target_id` 선택은 제거됩니다. 사용자 후보는 `/api/v1/admin/users?limit=100`, 프로젝트 후보는 `/api/v1/admin/projects/names` 응답을 사용하며 생성 payload와 서버 권한 계약은 바뀌지 않습니다.

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
