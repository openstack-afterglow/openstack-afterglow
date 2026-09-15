---
title: 시스템 서비스
parent: API 레퍼런스
nav_order: 65
---

# 시스템 서비스 (System Services) API

여러 소규모 보조 서비스 라우터를 한 문서로 묶었습니다: 사용자 공지, 튜토리얼 진행 상태, 모니터링 Service Discovery(SD) 타깃, Grafana 임베드, 사이트 설정·브랜딩, 사용자 크로스-프로젝트 대시보드.

---

## 인증 헤더

대부분의 엔드포인트는 Keystone 인증을 사용합니다.

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

> 예외: **모니터링 SD 타깃**(`/api/v1/sd/...`)은 Keystone 헤더가 아니라 `Authorization: Bearer <monitoring_sd_token>`을 사용합니다. **사이트 설정 공개 엔드포인트**(`GET /api/v1/site-config`, `GET /api/v1/site-config/assets/{slot}`)는 인증이 필요 없습니다.

---

## 목차

1. [공지 (Announcements)](#1-공지-announcements)
2. [튜토리얼 (Tutorials)](#2-튜토리얼-tutorials)
3. [모니터링 SD 타깃 (Service Discovery)](#3-모니터링-sd-타깃-service-discovery)
4. [Grafana 임베드](#4-grafana-임베드)
5. [사이트 설정 / 브랜딩 (Site Config)](#5-사이트-설정--브랜딩-site-config)
6. [사용자 대시보드 (User Dashboard)](#6-사용자-대시보드-user-dashboard)

---

## 1. 공지 (Announcements)

> 태그: `announcements`
> 기본 경로: `/api/v1/announcements`

호출자에게 타겟된 공지를 수신하고 읽음 처리합니다. 타겟팅 판별은 **항상 서버가 `token_info`(user_id/project_id)로 계산**하며, 클라이언트가 타겟 파라미터를 보내지 않습니다(IDOR 방지).

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/announcements` | 본인에게 타겟된 활성 공지 목록 |
| `GET` | `/api/v1/announcements/unread-count` | 읽지 않은 공지 수 |
| `POST` | `/api/v1/announcements/{announcement_id}/read` | 공지 읽음 처리 |

### GET /api/v1/announcements

호출자에게 타겟된 활성 공지(전체 / 본인 프로젝트 / 본인 유저)만 반환합니다.

**응답 (200 OK)** — `AnnouncementUserResponse[]`

```json
[
  {
    "id": 1,
    "created_at": "2026-01-01T00:00:00Z",
    "created_by_username": "admin",
    "title": "정기 점검 안내",
    "body": "...",
    "severity": "info",
    "starts_at": null,
    "ends_at": null,
    "is_read": false
  }
]
```

### GET /api/v1/announcements/unread-count

**응답 (200 OK)**: `{ "unread_count": 3 }`

프론트엔드 shell은 로그인 직후와 project scope 변경 직후 미읽음 수를 조회하고 60초 주기 polling을 보조로 유지합니다. 미읽음 공지가 있으면 header 알림 버튼에 작은 danger 점멸 점과 count가 포함된 접근성 이름을 표시하며, reduced-motion 환경에서는 점을 정적으로 유지합니다. 알림함의 발송자 표시는 관리자 전용 생성 경계를 드러내기 위해 `created_by_username (관리자)` 형식을 사용합니다.

### POST /api/v1/announcements/{announcement_id}/read

읽음 처리 전 타겟팅을 서버에서 재검증합니다. 다른 유저/프로젝트 대상 공지는 (구분되지 않게) `404`로 응답합니다. 저장소 장애 시 `503`.

**응답**: `204 No Content`

---

## 2. 튜토리얼 (Tutorials)

> 태그: `tutorials`
> 기본 경로: `/api/v1/tutorials`

사용자별 튜토리얼(투어) 진행 이력을 관리합니다. `user_id`는 항상 서버가 `token_info`로 계산합니다(IDOR 방지). `tour_id`/`status`는 서비스 레이어에서 화이트리스트로 검증합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/tutorials/status` | 본인의 투어 진행 상태 맵 |
| `POST` | `/api/v1/tutorials/{tour_id}/status` | 특정 투어 상태 기록(upsert) |

### GET /api/v1/tutorials/status

**응답 (200 OK)**

```json
{ "statuses": { "welcome": "completed", "storage": "dismissed" } }
```

기록이 없는 투어는 키에 없습니다(프론트에서 강조 대상으로 판단). 값은 `completed` 또는 `dismissed`.

### POST /api/v1/tutorials/{tour_id}/status

본인의 특정 투어 상태를 기록합니다.

```json
{ "status": "completed" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `status` | string | 예 | 허용값: `completed`, `dismissed`. 위반 시 `422` |

- 저장소 장애 시 `503`.

**응답**: `204 No Content`

---

## 3. 모니터링 SD 타깃 (Service Discovery)

> 태그: `sd-targets`
> 기본 경로: `/api/v1/sd`

Prometheus `http_sd_config` 호환 타깃 목록을 노출합니다. Nova admin 연결로 all-tenants 조회하며, 60초 Redis 캐시로 호출 부하를 제어합니다.

> **인증:** Keystone 헤더가 아니라 `Authorization: Bearer <monitoring_sd_token>`를 사용합니다. `monitoring_sd_token`(설정값)과 `hmac.compare_digest`로 타이밍 안전 비교합니다. 미설정 시 `503`, 헤더 누락/불일치 시 `401`.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/sd/prometheus/targets` | 각 VM의 node_exporter/dcgm_exporter 타깃 |
| `GET` | `/api/v1/sd/prometheus/libvirt-targets` | compute 노드별 libvirt_exporter 타깃 |

### GET /api/v1/sd/prometheus/targets

모든 VM의 fixed IP를 기준으로 `node_exporter` 타깃을, GPU flavor VM은 추가로 `dcgm_exporter` 타깃을 노출합니다.

**응답 (200 OK)** — Prometheus http_sd 타깃 그룹 배열

```json
[
  {
    "targets": ["10.0.0.5:9100"],
    "labels": {
      "instance": "vm-1",
      "project_id": "...",
      "flavor": "gpu.a100",
      "gpu": "true",
      "job": "node_exporter"
    }
  },
  {
    "targets": ["10.0.0.5:9400"],
    "labels": { "...": "...", "job": "dcgm_exporter" }
  }
]
```

### GET /api/v1/sd/prometheus/libvirt-targets

compute 노드별 `host_ip:libvirt_exporter_port`를 단일 그룹으로 노출합니다. libvirt_exporter는 hypervisor 측에서 실행되므로 게스트 OS의 node_exporter 설치 여부와 무관하게 모든 VM 메트릭을 커버합니다.

> kolla `enable_prometheus_libvirt_exporter: yes` 설정 후 reconfigure가 필요합니다.

---

## 4. Grafana 임베드

> 태그: `grafana-auth`
> 기본 경로: `/api/v1/grafana`

Grafana 대시보드 임베드를 지원합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/grafana/dashboards` | 대시보드 UID 매핑 + 기본 URL |

### GET /api/v1/grafana/dashboards

Grafana 기본 URL과 대시보드 UID 매핑을 반환합니다. 미설정 시 `grafana_url`은 빈 문자열이며 항상 `200`을 반환합니다(프론트엔드가 `grafana_url` 유무로 빈 상태 판단).

**응답 (200 OK)**

```json
{
  "grafana_url": "https://grafana.example.com",
  "dashboards": {
    "node": "...", "rabbitmq": "...", "mysqld": "...", "memcached": "...",
    "etcd": "...", "haproxy": "...", "libvirt": "...", "openstack": "...",
    "ceph": "...", "instance-cpu": "...", "instance-gpu": "..."
  }
}
```

> 임베드용 JWT 발급 등 상세 흐름은 아키텍처 문서를 참조하세요.

---

## 5. 사이트 설정 / 브랜딩 (Site Config)

> 태그: `site`
> 기본 경로: `/api/v1/site-config`

공개 사이트 설정과 브랜딩(로고·파비콘) 에셋을 제공합니다. 조회는 공개, 브랜딩 관리는 admin 전용입니다.

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/api/v1/site-config` | 불필요 | 공개 사이트 설정(이름·설명·로고·서비스 활성화 맵) |
| `GET` | `/api/v1/site-config/assets/{slot}` | 불필요 | 브랜딩 에셋(로고/파비콘) 바이너리 |
| `GET` | `/api/v1/site-config/admin/branding` | admin | 브랜딩 슬롯 상태 |
| `POST` | `/api/v1/site-config/admin/branding/{slot}` | admin | 브랜딩 에셋 업로드 |
| `DELETE` | `/api/v1/site-config/admin/branding/{slot}` | admin | 브랜딩 에셋 초기화 |

### GET /api/v1/site-config

인증 없이 사이트 표시 이름·설명·로고 경로 및 서비스 활성화 여부를 반환합니다.

**응답 (200 OK)** — `PublicSiteConfigResponse`

```json
{
  "site_name": "Afterglow",
  "site_description": "...",
  "logo_path": "...",
  "logo_dark_path": "...",
  "logo_light_path": "...",
  "favicon_path": "...",
  "services": {
    "magnum": false, "manila": true, "zun": false, "k3s": true,
    "trove": false, "swift": true, "barbican": true, "vpn": false, "chat": false
  }
}
```

### GET /api/v1/site-config/assets/{slot}

브랜딩 에셋 바이너리를 반환합니다. `?v=<sha 접두>`가 자산 해시와 일치하면 `Cache-Control: public, max-age=31536000, immutable`, 아니면 `max-age=60`. 응답에 `X-Content-Type-Options: nosniff`를 포함합니다. 슬롯/버전 불일치 시 `404`.

### 브랜딩 관리 (admin 전용)

- `GET /admin/branding` — 슬롯 정의, 유효(effective) 값, 업로드된 에셋 상태를 반환.
- `POST /admin/branding/{slot}` — `multipart/form-data`로 에셋 업로드(`file`). 검증 실패 시 `400`, 저장소 장애 시 `503`.
- `DELETE /admin/branding/{slot}` — 슬롯 에셋을 초기화.

모두 `require_admin` 의존성으로 보호되며 `BrandingStatusResponse`를 반환합니다.

---

## 6. 사용자 대시보드 (User Dashboard)

> 태그: `user-dashboard`
> 기본 경로: `/api/v1/user-dashboard`

로그인 사용자가 소속된 **모든 프로젝트**의 인스턴스/볼륨/네트워크/FIP를 병렬로 집계합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/user-dashboard/summary` | 크로스-프로젝트 리소스 요약 |

### GET /api/v1/user-dashboard/summary

사용자가 소속된 각 프로젝트를 병렬 조회해, 프로젝트별 리소스와 전체 합계를 반환합니다. 프로젝트 목록 조회 실패 시 `500`, 개별 프로젝트 조회 실패는 해당 프로젝트에 `error: true`로 표시하고 계속 진행합니다.

**응답 (200 OK)**

```json
{
  "current_project_id": "...",
  "projects": [
    {
      "project_id": "...",
      "project_name": "...",
      "instances": [ { "id": "...", "name": "...", "status": "ACTIVE", "flavor_name": "...", "vcpus": 2, "ram_mb": 4096, "created_at": "..." } ],
      "volumes": [ { "id": "...", "name": "...", "status": "...", "size": 10, "volume_type": "...", "created_at": "..." } ],
      "instance_count": 1,
      "volume_count": 1,
      "storage_gb": 10,
      "vcpus": 2,
      "ram_mb": 4096,
      "network_count": 1,
      "fip_count": 0
    }
  ],
  "totals": {
    "instances": 1, "volumes": 1, "storage_gb": 10,
    "vcpus": 2, "ram_mb": 4096, "networks": 1, "floating_ips": 0
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `current_project_id` | string | 현재 스코프된 프로젝트 UUID |
| `projects` | array | 프로젝트별 리소스 요약 |
| `totals` | object | 전 프로젝트 합계 |
