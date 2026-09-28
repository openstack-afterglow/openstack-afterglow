---
title: 대시보드 및 공통 (Dashboard)
parent: API 레퍼런스
nav_order: 70
---

# 대시보드 및 공통 (Dashboard & Common) API

> 태그: `dashboard`, `libraries`, `site`, `user-dashboard`  
> 기본 경로: `/api/v1/dashboard`, `/api/v1/libraries`, `/api/v1/site-config`, `/api/v1/user-dashboard`

프로젝트 대시보드 요약, 사용자 대시보드, 라이브러리 카탈로그, 사이트 설정을 제공합니다.

![대시보드 개요](../../assets/dashboard-overview.png)
*인스턴스 수·컴퓨트·스토리지 한도·GPU 사용량을 한눈에 확인할 수 있는 프로젝트 대시보드 메인 화면*

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 목차

1. [프로젝트 대시보드](#1-프로젝트-대시보드)
2. [사용자 대시보드](#2-사용자-대시보드)
3. [라이브러리 카탈로그](#3-라이브러리-카탈로그)
4. [사이트 설정](#4-사이트-설정)

---

## 1. 프로젝트 대시보드

> 태그: `dashboard`  
> 기본 경로: `/api/v1/dashboard`

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/dashboard/summary` | 인스턴스 수, 컴퓨트/스토리지 한도, GPU 사용량 |
| `GET` | `/api/v1/dashboard/config` | 프론트엔드 설정 (새로고침 간격 등) |
| `GET` | `/api/v1/dashboard/quotas` | 프로젝트 쿼터 조회 |
| `GET` | `/api/v1/dashboard/gpu-available` | GPU 가용량 조회 |
| `GET` | `/api/v1/dashboard/usage` | 프로젝트 리소스 사용량 |
| `GET` | `/api/v1/dashboard/usage-stats` | 기간별 인스턴스·vCPU 시간 요약 |
| `GET` | `/api/v1/dashboard/usage-report` | 플레이버·인스턴스 사용 시간과 다중 리소스 쿼터 예측 |

### GET /api/v1/dashboard/summary

프로젝트의 리소스 사용량 요약을 반환합니다. Nova 한도, Cinder 한도, 인스턴스 상태별 집계를 포함합니다.

**응답 (200 OK)**

```json
{
  "instances": {
    "total": 10,
    "active": 8,
    "shutoff": 1,
    "error": 1
  },
  "compute": {
    "instances": {"limit": 20, "in_use": 10},
    "cores": {"limit": 40, "in_use": 20},
    "ram": {"limit": 81920, "in_use": 40960}
  },
  "storage": {
    "volumes": {"limit": 10, "in_use": 5},
    "gigabytes": {"limit": 1000, "in_use": 250}
  },
  "gpu_used": 2
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `instances` | object | 상태별 인스턴스 수 |
| `compute` | object | Nova 컴퓨트 쿼터 및 사용량 |
| `storage` | object | Cinder 스토리지 쿼터 및 사용량 |
| `gpu_used` | integer | 사용 중인 GPU 인스턴스 수 |

### GET /api/v1/dashboard/config

프론트엔드에서 사용하는 설정값을 반환합니다.

**응답 (200 OK)**

```json
{
  "refresh_interval_ms": 5000,
  "manila_enabled": true,
  "magnum_enabled": false,
  "zun_enabled": false
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `refresh_interval_ms` | integer | 대시보드 자동 새로고침 간격 (ms) |
| `manila_enabled` | boolean | Manila 파일 스토리지 서비스 활성화 여부 |
| `magnum_enabled` | boolean | Magnum 컨테이너 인프라 서비스 활성화 여부 |
| `zun_enabled` | boolean | Zun 컨테이너 서비스 활성화 여부 |

### GET /api/v1/dashboard/quotas

프로젝트의 OpenStack 리소스 쿼터를 반환합니다. `view=full`이 기본이며, `view=overview`는 대시보드 요약 전용입니다. 기간 사용량 화면의 리소스 현황은 full 응답을 사용합니다.

**응답 (200 OK)** — 각 쿼터 항목은 `{limit, in_use}`를 포함합니다.

| 그룹 | full 응답 항목 |
|---|---|
| `compute` | `instances`, `cores`, `ram`, `key_pairs`, `server_groups` |
| `storage` | `volumes`, `gigabytes`, `snapshots`, `backups`, `backup_gigabytes` |
| `network` | `floatingip`, `network`, `subnet`, `port`, `router`, `security_group`, `security_group_rule` |
| `file_storage` | Manila 활성 시 `shares`, `gigabytes`, `share_networks`, `snapshot_gigabytes` |
| `gpu`, `gpu_available` | Afterglow GPU 타입별 쿼터와 조회 성공 여부 |
| `object_storage` | Swift의 `container_count`, `object_count`, `bytes_used` 통계 |
| `database` | Trove의 `instances_count` 통계 |

프론트엔드는 Manila·Swift·Trove를 사이트 서비스 설정으로 게이트하고, 부분 응답에서 `{limit, in_use}`가 없는 항목은 표시하지 않습니다. 키페어는 사용자 범위 리소스이며 Nova 프로젝트 쿼터에서 사용량을 제공하지 않으므로 **사용자별 한도만** 표시합니다. Swift·Trove는 쿼터 비율이 아닌 개수/용량 통계입니다. 이 요청이 실패해도 병렬로 불러온 사용량 리포트는 유지하고 현황 섹션에 경고를 표시합니다.

### GET /api/v1/dashboard/gpu-available

프로젝트에서 사용 가능한 GPU 리소스를 반환합니다. GPU가 설정되지 않은 경우 빈 응답을 반환합니다.

**응답 (200 OK)** — GPU 가용량 정보

### GET /api/v1/dashboard/usage

프로젝트의 리소스 사용량을 반환합니다.

**응답 (200 OK)** — 사용량 객체

Nova 총합 키는 `total_hours`, `total_vcpus_usage`, `total_memory_mb_usage`, `total_local_gb_usage`를 유지합니다. `server_usages`는 기존 스펙·시간·상태 외에 `flavor`, `started_at`, `ended_at`, `uptime`을 포함합니다. 시각은 timezone을 포함한 ISO 문자열이며, naive Nova 시각은 UTC로 해석하고 누락/파싱 불가 값은 `null`입니다.

### GET /api/v1/dashboard/usage-stats

기간별 인스턴스 시간과 vCPU 시간을 반환합니다. `vcpu_hours`는 Nova SDK의 `total_vcpus_usage`에서 읽습니다.

### GET /api/v1/dashboard/usage-report

`range=7d|14d|30d|90d`(기본 `30d`)를 사용합니다. `start`·`end`는 날짜이며, 조회 끝은 오늘 00:00 UTC입니다. `Cache-Control: private, max-age=60`을 반환합니다. 인증·프로젝트 범위와 `refresh=true` 캐시 갱신 규칙은 다른 대시보드 요청과 같습니다.

**응답 (200 OK)**

| 필드 | 의미 |
|---|---|
| `range`, `start`, `end` | 요청 범위와 Nova 조회 날짜 |
| `stats` | `instance_hours`, `vcpu_hours`, `ram_gb_hours`, `gpu_hours`, `active_instances`, `total_instances` |
| `flavor_hours[]` | 사용 시간 내림차순 상위 15개: `flavor`, `instance_count`, `usage_hours`, `vcpus`, `ram_mb`, `gpu_count`, `vcpu_hours`, `gpu_hours` |
| `instance_usage[]` | 시간 내림차순 상위 10개: `instance_id`, `name`, `flavor`, `state`, `hours`, `started_at`, `ended_at`, `vcpus`, `memory_mb`, `gpu_count` |
| `quota` | `instances`, `vcpus`, `ram_mb`, `volume_gb`, `volumes` 각각 `{in_use, limit}`; `gpu[]`는 `{gpu_type, in_use, limit}` |
| `quota.*_available` | `compute_available`, `storage_available`, `gpu_available`; 조회 실패는 무제한이나 정상 0 사용량으로 표시하지 않음 |
| `forecast` | `window_days=7`, `horizon_days=30`, `vcpus`, `ram_mb`, `volume_gb`, 타입명을 키로 하는 `gpu` 객체 |

Nova·Cinder quota는 정규화 전에 필수 `limit`/`in_use`를 검증합니다. 빈 `quota_set`이나 사용량 누락을 기본 `-1`/`0`으로 채우지 않으며 해당 `*_available=false`로 반환합니다. strict 전용 캐시 키를 사용해 이전에 정규화된 불완전 응답과 섞이지 않습니다.

`instance_hours`·`vcpu_hours`·`ram_gb_hours`는 SDK 총합을 사용하며 RAM의 MB·h를 1024로 나눕니다. GPU 시간은 서버 시간 × 플레이버 GPU 수의 합입니다. 그룹별 스펙은 해당 이름의 첫 사용량 행을 사용하고, 시간은 각 서버 스펙으로 가중 합산합니다. 총합은 소수 둘째 자리, 표의 시간은 첫째 자리로 반올림합니다. `active_instances`는 사용량 행 중 현재 `state=active`인 수이며, 종료된 서버도 기간 내 사용량에 포함합니다.

각 예측 항목의 계약:

| 필드 | 계산 / 부재 의미 |
|---|---|
| `current_pct` | 양수 한도에서 현재 할당/한도 × 100, 최대 100; 한도 0 또는 -1이면 `null` |
| `series` | 조회 일수만큼 일별 00:00 UTC 시점의 할당량; 마지막 샘플은 `end` |
| `trend_available` | 시작 시각이 알려진 서버가 있고 샘플이 2개 이상인지 여부 |
| `slope_per_day` | 최근 최대 7개 샘플의 최소제곱 선형 기울기, 소수 둘째 자리; 추세 부재 시 `null` |
| `projected_pct` | `(현재 할당 + 기울기 × 30) / 한도 × 100`, 0~100으로 제한; 추세 부재 또는 한도 ≤ 0이면 `null` |
| `days_to_limit` | 양수 한도와 추세가 있을 때 이미 한도 이상이면 0, 증가 추세이면 잔여량/기울기의 올림, 그 외 `null` |

일별 할당량은 `started_at ≤ sample < ended_at`인 서버의 vCPU·RAM·GPU 수를 합산합니다. 종료 시각이 없으면 계속 포함하고, 시작 시각이 없으면 시계열에서 제외합니다. 이는 **실측 CPU/GPU 이용률이나 과금 예측이 아니라 할당량의 선형 연장**입니다. API의 RAM 예측 단위는 MB이며 화면은 GB로 변환합니다.

블록 스토리지는 Nova가 아니라 Cinder 쿼터를 사용합니다. Cinder 사용 이력 API가 없으므로 `volume_gb`는 현재 사용률만 반환하고 `series=[]`, `trend_available=false`, 나머지 예측값은 `null`입니다. 삭제된 볼륨을 현재 목록으로 추정하지 않습니다.

GPU 스펙은 기존 `parse_gpu_demand`의 alias/이름 규칙을 재사용합니다. 삭제된 플레이버는 이름 기반 fallback만 가능하므로 GPU 수·타입을 복구하지 못한 서버의 GPU 시간/타입별 추세가 누락될 수 있습니다. 리사이즈의 과거 스펙 변화도 별도 이력으로 복원하지 않습니다. GPU 쿼터 DB 조회 실패는 `gpu_available=false`, `gpu=[]`로 표시하며 나머지 보고서는 유지합니다. Nova 사용량 adapter의 기존 오류 시 빈 사용량 fallback은 유지됩니다.

프론트엔드와 mock transport는 이 중첩 계약을 사용합니다. 이전 평면 `quota.vcpus_in_use/vcpus_limit`, `forecast.vcpu_pct/memory_pct/storage_pct`는 더 이상 제공하지 않습니다.

---

## 2. 사용자 대시보드

> 태그: `user-dashboard`  
> 기본 경로: `/api/v1/user-dashboard`

### GET /api/v1/user-dashboard

현재 사용자의 인스턴스, 볼륨 등 개인 리소스 요약을 반환합니다.

**응답 (200 OK)**

사용자가 소유한 인스턴스, 볼륨, 파일 스토리지 목록과 요약 통계를 포함합니다.

---

## 3. 라이브러리 카탈로그

> 태그: `libraries`  
> 기본 경로: `/api/v1/libraries`

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/libraries` | 라이브러리 카탈로그 목록 |
| `GET` | `/api/v1/libraries/shares` | 사전 빌드된 Manila share 목록 |
| `POST` | `/api/v1/libraries/validate` | 라이브러리 호환성 검증 |

### GET /api/v1/libraries

Afterglow 라이브러리 카탈로그를 반환합니다. 각 라이브러리의 사전 빌드 share 가용 여부를 포함합니다.

**응답 (200 OK)** — `LibraryConfig[]` 배열

```json
[
  {
    "id": "python311",
    "name": "Python 3.11",
    "version": "3.11",
    "packages": ["numpy", "pandas", "scipy"],
    "depends_on": [],
    "file_storage_id": "uuid-string",
    "available_prebuilt": true
  },
  {
    "id": "pytorch",
    "name": "PyTorch",
    "version": "2.1",
    "packages": ["torch", "torchvision", "torchaudio"],
    "depends_on": ["python311"],
    "file_storage_id": null,
    "available_prebuilt": false
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 라이브러리 식별자 (예: `python311`) |
| `name` | string | 라이브러리 표시명 |
| `version` | string | 버전 |
| `packages` | array[string] | 포함된 pip 패키지 목록 |
| `depends_on` | array[string] | 의존하는 다른 라이브러리 ID |
| `file_storage_id` | string\|null | 사전 빌드된 share UUID. 없으면 `null` |
| `available_prebuilt` | boolean | 사전 빌드 share 사용 가능 여부 |

### GET /api/v1/libraries/shares

사전 빌드된 Manila share 목록을 반환합니다. 관리자가 빌드한 라이브러리 share를 확인할 수 있습니다.

**응답 (200 OK)** — 배열

### POST /api/v1/libraries/validate

라이브러리 조합의 호환성을 검증합니다. Ubuntu 버전, Python 버전 충돌 등을 감지합니다.

**요청 본문**

```json
{
  "library_ids": ["python311", "pytorch"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `library_ids` | array[string] | 예 | 검증할 라이브러리 ID 목록 |

**응답 (200 OK)**

```json
{
  "valid": true,
  "conflicts": [],
  "warnings": []
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `valid` | boolean | 호환성 검증 통과 여부 |
| `conflicts` | array | 충돌 목록 (빈 배열이면 문제 없음) |
| `warnings` | array | 경고 목록 (빈 배열이면 문제 없음) |

---

## 4. 사이트 설정

> 태그: `site`  
> 기본 경로: `/api/v1/site-config`

### GET /api/v1/site-config

프론트엔드에서 사용하는 전역 사이트 설정을 반환합니다. 인증이 필요하지 않을 수 있습니다.

**응답 (200 OK)**

```json
{
  "site_name": "Afterglow",
  "refresh_interval_ms": 5000,
  "manila_enabled": true,
  "magnum_enabled": false,
  "zun_enabled": false
}
```