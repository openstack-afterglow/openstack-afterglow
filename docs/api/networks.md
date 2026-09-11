---
title: 네트워크 (Networks)
parent: API 레퍼런스
nav_order: 50
---

# 네트워크 (Networks) API

> 태그: `networks`
> 기본 경로: `/api/v1/networks`

Neutron 네트워크, 서브넷, Floating IP, 포트, 그리고 프로젝트 전체 토폴로지를 관리합니다.
Default 네트워크 관리와 실시간 트래픽 조회도 이 라우터에서 제공합니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 공통 사항

- **소유권 검증**: 상세/삭제/수정 계열(`GET·DELETE /{network_id}`, 서브넷 `PUT·DELETE`, Floating IP `associate·disassociate·DELETE`)은
  대상 리소스의 `project_id`가 토큰 프로젝트와 일치하는지 검사합니다. 불일치 시 `404`로 응답합니다(존재 은닉).
- **외부/공유 네트워크 면제**: `GET /{network_id}`는 대상이 외부(`is_router_external`) 또는 공유(`is_shared`) 네트워크이면
  cross-project 정상 노출로 간주하여 소유권 검증을 면제합니다.
- **캐시**: 목록/토폴로지 응답은 Redis에 캐시됩니다. TTL은 `afterglow.conf`의 `[cache]` 항목으로 조정 가능하며 기본값은 아래 표와 같습니다.
  응답 헤더에 `?refresh=true`를 붙이거나 mutation(생성/삭제)이 발생하면 관련 캐시가 무효화됩니다.

| 캐시 대상 | TTL 헬퍼 | 기본값(조정 가능) |
|-----------|----------|-------------------|
| 네트워크 목록 (`GET ""`) | `ttl_normal` | 30초 |
| Floating IP 목록 (`GET /floating-ips`) | `ttl_fast` | 15초 |
| 토폴로지 (`GET /topology`) | `ttl_normal` | 30초 |
| 토폴로지 트래픽 포트맵 (`GET /topology/traffic`) | `ttl_static` | 300초 |

- **Rate limit**: 모든 mutation 엔드포인트(생성/삭제/연결/해제/서브넷 삭제 등)는 `10/minute` 제한이 적용됩니다.

---

## 목차

1. [네트워크](#1-네트워크)
2. [Default 네트워크](#2-default-네트워크)
3. [서브넷](#3-서브넷)
4. [Floating IP](#4-floating-ip)
5. [포트](#5-포트)
6. [네트워크 토폴로지](#6-네트워크-토폴로지)

---

## 1. 네트워크

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/networks` | 네트워크 목록 (30초 캐시) |
| `POST` | `/api/v1/networks` | 네트워크 생성 |
| `GET` | `/api/v1/networks/{network_id}` | 네트워크 상세 (서브넷·라우터 포함) |
| `DELETE` | `/api/v1/networks/{network_id}` | 네트워크 삭제 |

### GET /api/v1/networks

프로젝트의 Neutron 네트워크 목록을 반환합니다. 응답은 30초간 캐시됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `refresh` | query | boolean | 아니오 | `true`이면 캐시를 무시하고 재조회 |

**응답 (200 OK)** — `NetworkInfo[]` 배열

```json
[
  {
    "id": "uuid-string",
    "name": "private-net",
    "status": "ACTIVE",
    "subnets": ["uuid-string"],
    "is_external": false,
    "is_shared": false
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 네트워크 UUID |
| `name` | string | 네트워크 이름 |
| `status` | string | 상태 (`ACTIVE`, `DOWN` 등) |
| `subnets` | array[string] | 서브넷 UUID 목록 |
| `is_external` | boolean | 외부 네트워크 여부 |
| `is_shared` | boolean | 공유 네트워크 여부 |

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 네트워크 목록 조회 실패 |

### POST /api/v1/networks

새 네트워크를 생성합니다.

**요청 본문** — `CreateNetworkRequest`

```json
{
  "name": "string (필수)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 네트워크 이름 |

**응답 (201 Created)** — `NetworkInfo` 객체

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 네트워크 생성 실패 |

### GET /api/v1/networks/{network_id}

특정 네트워크의 상세 정보를 반환합니다. 서브넷 상세와 연결된 라우터 목록을 포함합니다.
외부/공유 네트워크가 아니면 소유권 검증을 수행합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `network_id` | path | string | 예 | 네트워크 UUID |

**응답 (200 OK)** — `NetworkDetail`

```json
{
  "id": "uuid-string",
  "name": "private-net",
  "status": "ACTIVE",
  "subnets": ["uuid-string"],
  "is_external": false,
  "is_shared": false,
  "subnet_details": [
    {
      "id": "uuid-string",
      "name": "subnet-name",
      "cidr": "192.168.1.0/24",
      "gateway_ip": "192.168.1.1",
      "dhcp_enabled": true
    }
  ],
  "routers": [
    {
      "id": "uuid-string",
      "name": "router-name",
      "status": "ACTIVE",
      "project_id": "uuid-string",
      "external_gateway_network_id": "uuid-string",
      "connected_subnet_ids": ["uuid-string"]
    }
  ]
}
```

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 네트워크를 찾을 수 없음 / 소유권 불일치 |

### DELETE /api/v1/networks/{network_id}

네트워크를 삭제합니다. 서브넷이나 연결된 포트가 있으면 삭제할 수 없습니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `network_id` | path | string | 예 | 네트워크 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 네트워크를 찾을 수 없음 / 소유권 불일치 |
| `500` | 네트워크 삭제 실패 (하위 자원 존재 등) |

---

## 2. Default 네트워크

프로젝트별 "기본 네트워크"를 앱 DB에 기록해 인스턴스 생성 등에서 재사용합니다.
`afterglow.conf`의 `default_network_enabled`가 꺼져 있으면 `ensure-default`는 `404`를 반환합니다.

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/networks/ensure-default` | Default 네트워크 조회 또는 생성 |
| `GET` | `/api/v1/networks/default` | 저장된 Default 네트워크 레코드 조회 |
| `PUT` | `/api/v1/networks/default` | Default 네트워크 지정 |

### POST /api/v1/networks/ensure-default

프로젝트의 Default 네트워크를 조회하거나, 없으면 생성합니다. 프론트엔드에서 프로젝트 전환 시 호출됩니다.
DB에 이미 기록되어 있으면 빠르게 반환하고, 없으면 설정값(`default_network_external_id`, `default_network_cidr`)을
기반으로 네트워크·서브넷·라우터를 프로비저닝합니다. 성공 시 네트워크 목록 캐시를 무효화합니다.

**응답 (200 OK)** — `NetworkInfo` 객체

**오류**

| 코드 | 설명 |
|------|------|
| `404` | Default 네트워크 기능이 비활성화 상태(`default_network_enabled = false`) |
| `500` | Default 네트워크 처리 실패 |

### GET /api/v1/networks/default

현재 프로젝트에 저장된 Default 네트워크 레코드(DB 기준)를 반환합니다.

**응답 (200 OK)** — 레코드 dict

```json
{
  "project_id": "uuid-string",
  "network_id": "uuid-string",
  "subnet_id": "uuid-string",
  "router_id": "uuid-string",
  "auto_created": true,
  "created_at": "2026-01-01T00:00:00+00:00",
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `project_id` | string | 프로젝트 UUID |
| `network_id` | string | Default 네트워크 UUID |
| `subnet_id` | string\|null | 대표 서브넷 UUID |
| `router_id` | string\|null | 연결된 라우터 UUID |
| `auto_created` | boolean | `ensure-default`로 자동 생성되었는지 여부 |
| `created_at` | string\|null | 생성 시각 (ISO 8601) |
| `updated_at` | string\|null | 갱신 시각 (ISO 8601) |

**오류**

| 코드 | 설명 |
|------|------|
| `404` | Default 네트워크가 설정되지 않음 |

### PUT /api/v1/networks/default

사용자가 원하는 네트워크를 프로젝트의 Default 네트워크로 지정합니다. 서브넷 ID는 해당 네트워크의 첫 번째 서브넷을 사용합니다.
지정 후 네트워크 목록 캐시를 무효화합니다.

**요청 본문**

```json
{
  "network_id": "uuid-string (필수)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `network_id` | string | 예 | Default로 지정할 네트워크 UUID |

**응답 (200 OK)** — 갱신된 레코드 dict (`GET /default`와 동일 형태)

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 대상 네트워크를 찾을 수 없음 |

---

## 3. 서브넷

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/networks/{network_id}/subnets` | 서브넷 생성 |
| `PUT` | `/api/v1/networks/subnets/{subnet_id}` | 서브넷 편집 (이름/게이트웨이/DHCP) |
| `DELETE` | `/api/v1/networks/subnets/{subnet_id}` | 서브넷 삭제 |

> **경로 우선순위**: 고정 경로(`/subnets/{subnet_id}`)는 동적 경로(`/{network_id}`)보다 먼저 등록되어야 하므로,
> 서브넷 편집/삭제는 `/networks/subnets/...` 형태이고 서브넷 생성만 `/networks/{network_id}/subnets`입니다.

### POST /api/v1/networks/{network_id}/subnets

지정한 네트워크에 서브넷을 생성합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `network_id` | path | string | 예 | 대상 네트워크 UUID |

**요청 본문** — `CreateSubnetRequest`

```json
{
  "name": "string (필수)",
  "cidr": "192.168.1.0/24 (필수)",
  "gateway_ip": "string (선택)",
  "enable_dhcp": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 서브넷 이름 |
| `cidr` | string | 예 | CIDR 표기법 (예: `192.168.1.0/24`). 네트워크 내에서 다른 서브넷과 겹치지 않아야 함 |
| `gateway_ip` | string | 아니오 | 게이트웨이 IP. 생략 시 CIDR의 첫 번째 IP 사용 |
| `enable_dhcp` | boolean | 아니오 | DHCP 활성화 여부 (기본값: `true`) |

**응답 (201 Created)** — `SubnetDetail`

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 서브넷 생성 실패 (CIDR 충돌 등) |

### PUT /api/v1/networks/subnets/{subnet_id}

서브넷의 이름, 게이트웨이, DHCP 설정을 수정합니다. 소유권 검증 대상입니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `subnet_id` | path | string | 예 | 서브넷 UUID |

**요청 본문** — `UpdateSubnetRequest` (모든 필드 선택; 전달된 필드만 갱신)

```json
{
  "name": "string (선택)",
  "gateway_ip": "string (선택)",
  "enable_dhcp": true
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 아니오 | 서브넷 이름 |
| `gateway_ip` | string | 아니오 | 게이트웨이 IP 주소 |
| `enable_dhcp` | boolean | 아니오 | DHCP 활성화 여부 |

**응답 (200 OK)** — `SubnetDetail`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 서브넷을 찾을 수 없음 / 소유권 불일치 |
| `500` | 서브넷 업데이트 실패 |

### DELETE /api/v1/networks/subnets/{subnet_id}

서브넷을 삭제합니다. 소유권 검증 대상입니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `subnet_id` | path | string | 예 | 서브넷 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 서브넷을 찾을 수 없음 / 소유권 불일치 |
| `500` | 서브넷 삭제 실패 (라우터 인터페이스·포트 존재 등) |

---

## 4. Floating IP

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/networks/floating-ips` | Floating IP 목록 (15초 캐시) |
| `POST` | `/api/v1/networks/floating-ips` | Floating IP 생성 |
| `POST` | `/api/v1/networks/floating-ips/{fip_id}/associate` | Floating IP 인스턴스 연결 |
| `POST` | `/api/v1/networks/floating-ips/{fip_id}/disassociate` | Floating IP 해제 |
| `DELETE` | `/api/v1/networks/floating-ips/{fip_id}` | Floating IP 삭제 |

### GET /api/v1/networks/floating-ips

프로젝트의 Floating IP 목록을 반환합니다. 응답은 15초간 캐시됩니다.

**응답 (200 OK)** — `FloatingIpInfo[]` 배열

```json
[
  {
    "id": "uuid-string",
    "floating_ip_address": "203.0.113.10",
    "fixed_ip_address": "10.0.0.5",
    "status": "ACTIVE",
    "port_id": "uuid-string",
    "floating_network_id": "uuid-string",
    "project_id": "uuid-string",
    "instance_id": "uuid-string",
    "instance_name": "web-01"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | Floating IP UUID |
| `floating_ip_address` | string | Floating IP 주소 |
| `fixed_ip_address` | string\|null | 연결된 고정 IP 주소 |
| `status` | string | 상태 (`ACTIVE`, `DOWN` 등) |
| `port_id` | string\|null | 연결된 포트 UUID |
| `floating_network_id` | string | 외부 네트워크 UUID |
| `project_id` | string\|null | 프로젝트 UUID |
| `instance_id` | string\|null | 연결된 인스턴스 UUID |
| `instance_name` | string\|null | 연결된 인스턴스 이름 |

### POST /api/v1/networks/floating-ips

새 Floating IP를 외부 네트워크에서 할당받습니다.

**요청 본문** — `CreateFipRequest`

```json
{
  "floating_network_id": "uuid-string (필수)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `floating_network_id` | string | 예 | 외부 네트워크 UUID (`is_external = true`인 네트워크여야 함) |

**응답 (201 Created)** — `FloatingIpInfo` 객체

### POST /api/v1/networks/floating-ips/{fip_id}/associate

Floating IP를 인스턴스에 연결합니다. 대상 Floating IP는 소유권 검증을 거치며,
인스턴스에 연결 가능한 포트(고정 IP)가 있어야 연결이 성립합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `fip_id` | path | string | 예 | Floating IP UUID |

**요청 본문** — `AssociateFipRequest`

```json
{
  "instance_id": "uuid-string (필수)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `instance_id` | string | 예 | 연결할 인스턴스 UUID |

**응답 (200 OK)** — `FloatingIpInfo` 객체

**오류**

| 코드 | 설명 |
|------|------|
| `404` | Floating IP를 찾을 수 없음 / 소유권 불일치 |
| `500` | Floating IP 연결 실패 |

### POST /api/v1/networks/floating-ips/{fip_id}/disassociate

Floating IP를 인스턴스에서 해제합니다. Floating IP 자체는 유지됩니다. 해제 후 목록 캐시를 무효화합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `fip_id` | path | string | 예 | Floating IP UUID |

**응답 (200 OK)** — `FloatingIpInfo` 객체

**오류**

| 코드 | 설명 |
|------|------|
| `404` | Floating IP를 찾을 수 없음 / 소유권 불일치 |
| `500` | Floating IP 해제 실패 |

### DELETE /api/v1/networks/floating-ips/{fip_id}

Floating IP를 삭제(반환)합니다. 삭제 후 목록 캐시를 무효화합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `fip_id` | path | string | 예 | Floating IP UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | Floating IP를 찾을 수 없음 / 소유권 불일치 |
| `500` | Floating IP 삭제 실패 |

---

## 5. 포트

### GET /api/v1/networks/ports

현재 프로젝트의 Neutron 포트 목록을 반환합니다.

**응답 (200 OK)** — dict 배열

```json
[
  {
    "id": "uuid-string",
    "name": "",
    "status": "ACTIVE",
    "mac_address": "fa:16:3e:00:00:01",
    "fixed_ips": [{ "ip_address": "10.0.0.5", "subnet_id": "uuid-string" }],
    "network_id": "uuid-string",
    "device_owner": "compute:nova",
    "device_id": "uuid-string"
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 포트 UUID |
| `name` | string | 포트 이름 (없으면 빈 문자열) |
| `status` | string | 상태 |
| `mac_address` | string | MAC 주소 |
| `fixed_ips` | array[object] | 고정 IP 목록 (`ip_address`, `subnet_id`) |
| `network_id` | string | 소속 네트워크 UUID |
| `device_owner` | string | 포트 소유 디바이스 유형 (예: `compute:nova`) |
| `device_id` | string | 연결된 디바이스(인스턴스 등) UUID |

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 포트 조회 실패 |

---

## 6. 네트워크 토폴로지

![네트워크 토폴로지](../../assets/network-topology.png)
*라우터·로드밸런서·인스턴스 간 연결 구조와 실시간 송수신 트래픽 수치를 그래프 뷰로 시각화 — 이름·IP 검색 지원*

토폴로지는 두 엔드포인트로 나뉩니다. **구조**(`/topology`)는 30초 캐시로 노드·엣지 관계를 반환하고,
**트래픽**(`/topology/traffic`)은 캐시 없이 매 호출 실시간 rx/tx bps를 계산하는 단주기 폴링 전용 엔드포인트입니다.
값은 Prometheus `rate(...[30s])` 로 계산한 **최근 30초 평균**입니다. 이 윈도우는 scrape interval 에 종속됩니다 — 토폴로지가 읽는 `instances-node`·`instances-libvirt` job 의 `scrape_interval` 이 10초여야 윈도우 안에 3 샘플이 들어옵니다(`deploy/k8s*/monitoring/prometheus/configmap.yaml`). 윈도우 상수는 `app.api.network.networks.TOPOLOGY_RATE_WINDOW` 이고, `backend/tests/test_topology_traffic.py` 가 윈도우와 scrape interval 의 결합을 배포본·template **양쪽** configmap 에 대해 함께 고정합니다.

> **실패 모드**: 30초 윈도우 / 10초 scrape 는 정확히 3 샘플이라 여유가 1 샘플뿐입니다. http_sd 타깃 갱신 등으로 **scrape 를 연속 2회 놓치면** `rate()` 가 결과를 주지 않아 그 인스턴스가 `instances`·`networks`·히스토리 `series` 에서 통째로 빠집니다 — 화면에는 `0` 이 아니라 값 없음(`—`)으로 보입니다. 여유가 더 필요하면 윈도우를 45~60초로 올립니다(`scrape × 3 ≤ window` 계약은 그대로 통과합니다).

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/networks/topology` | 토폴로지 구조 (30초 캐시) |
| `GET` | `/api/v1/networks/topology/traffic` | 실시간 트래픽 (rx/tx bps) |
| `GET` | `/api/v1/networks/topology/traffic/history` | 네트워크 1개의 사용량 시계열 + 평균·최대 |

### GET /api/v1/networks/topology

프로젝트의 전체 네트워크 토폴로지를 반환합니다. 네트워크, 라우터, 인스턴스, Floating IP, 로드밸런서 관계를 포함합니다. 인스턴스·라우터·Floating IP·로드밸런서는 현재 프로젝트 소유분만, 네트워크는 프로젝트 소유분과 external/shared 네트워크만 포함됩니다.
user scope에서는 현재 프로젝트 소유 리소스 + 외부/공유 네트워크만 표시합니다. 응답은 30초간 캐시됩니다.

**응답 (200 OK)** — `TopologyData`

```json
{
  "networks": [
    {
      "id": "uuid-string",
      "name": "private-net",
      "status": "ACTIVE",
      "is_external": false,
      "is_shared": false,
      "project_id": "uuid-string",
      "subnet_details": [],
      "mtu": 1450
    }
  ],
  "routers": [
    {
      "id": "uuid-string",
      "name": "router-name",
      "status": "ACTIVE",
      "external_gateway_network_id": "uuid-string",
      "external_gateway_ips": ["203.0.113.1"],
      "interface_ips": [{ "ip_address": "192.168.1.1", "subnet_id": "uuid-string" }],
      "is_distributed": false,
      "is_ha": false,
      "connected_subnet_ids": ["uuid-string"],
      "dvr_subnet_ids": [],
      "project_id": "uuid-string",
      "enable_snat": true,
      "routes": [{ "destination": "10.20.0.0/16", "nexthop": "192.168.1.254" }]
    }
  ],
  "instances": [
    {
      "id": "uuid-string",
      "name": "web-01",
      "status": "ACTIVE",
      "project_id": "uuid-string",
      "network_names": ["private-net"],
      "ip_addresses": [
        {
          "addr": "10.0.0.5",
          "type": "fixed",
          "network_name": "private-net",
          "network_id": "uuid-string",
          "port_id": "uuid-string",
          "mac_addr": "fa:16:3e:00:00:01"
        }
      ],
      "flavor_name": "m1.small",
      "image_id": "uuid-string",
      "is_database": false
    }
  ],
  "floating_ips": [],
  "load_balancers": [
    {
      "id": "uuid-string",
      "name": "lb-01",
      "vip_address": "10.0.0.100",
      "vip_subnet_id": "uuid-string",
      "vip_network_id": "uuid-string",
      "provisioning_status": "ACTIVE",
      "operating_status": "ONLINE",
      "project_id": "uuid-string",
      "listeners": [],
      "members": []
    }
  ]
}
```

주요 필드:

| 그룹 | 필드 | 설명 |
|------|------|------|
| `networks[]` | `mtu` | 네트워크 MTU (Neutron 속성 없으면 `null`) |
| `routers[]` | `is_distributed` / `is_ha` | DVR / HA 라우터 여부 |
| `routers[]` | `external_gateway_ips` | 게이트웨이 외부 고정 IP (SNAT IP 포함) |
| `routers[]` | `enable_snat` | 외부 게이트웨이 SNAT 여부. 게이트웨이가 없으면 `null` |
| `routers[]` | `routes` | 정적 경로 `[{destination, nexthop}]` (형식이 어긋난 항목은 제외) |
| `instances[]` | `flavor_name` / `image_id` | 인스턴스 flavor 이름·부팅 이미지 UUID (볼륨 부팅이면 `image_id`는 `null`) |
| `instances[]` | `is_database` | Trove DB 인스턴스를 구성하는 Nova 인스턴스 여부. Trove fixed IP 와 일치할 때만 `true` (floating IP 는 매칭 제외) |
| `instances[].ip_addresses[]` | `network_id` | compute 포트 매핑으로 보강된 소속 네트워크 UUID |
| `instances[].ip_addresses[]` | `port_id` / `mac_addr` | 해당 IP를 가진 Neutron compute 포트 UUID·MAC. 포트가 없는 IP(floating 등)는 `null` |
| `load_balancers[]` | `listeners` / `members` | LB에 연결된 리스너·멤버 요약 |

> 포트 메타(`network_id` / `port_id` / `mac_addr`)와 `flavor_name` / `image_id` 는 모두 기존 Neutron/Nova
> 배치 조회 결과에서 채우므로 OpenStack 호출 수는 변하지 않습니다.
> `is_database` 는 optional 서비스인 Trove 인스턴스 목록 1회 조회로 채웁니다. Trove가 배포되지 않았거나
> 조회가 실패하면 오류가 아니라 정상 상황으로 간주해 모든 인스턴스가 `is_database: false` 로 반환됩니다.
> provider 세그먼트 메타(`provider_network_type` / `provider_segmentation_id` / `provider_physical_network`)는
> 사용자 응답에 포함되지 않으며 관리자 전용 `GET /api/v1/admin/topology`(`AdminTopologyData`)에서만 반환됩니다.

### GET /api/v1/networks/topology/traffic

현재 토폴로지 리소스의 instant 트래픽(rx/tx bps)을 반환합니다. 구조 엔드포인트와 분리된 **단주기 폴링 전용**입니다.
libvirt/node_exporter 메트릭을 Prometheus에서 instant 쿼리로 수집하며, 포트↔MAC↔네트워크 매핑은 300초 캐시를 사용합니다.
Prometheus 장애 시 트래픽 값은 0으로 폴백합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `all_projects` | query | boolean | 아니오 | 모든 프로젝트 트래픽 조회 (기본값 `false`). **시스템 admin 전용** |

**응답 (200 OK)**

```json
{
  "ts": 1767225600,
  "instances": { "uuid-string": { "rx_bps": 1024.0, "tx_bps": 2048.0 } },
  "networks": { "uuid-string": { "rx_bps": 4096.0, "tx_bps": 8192.0 } },
  "interfaces": {
    "port-uuid": {
      "instance_id": "uuid-string",
      "network_id": "uuid-string",
      "mac_address": "fa:16:3e:00:00:01",
      "rx_bps": 1024.0,
      "tx_bps": 2048.0
    }
  },
  "routers": {},
  "load_balancers": { "uuid-string": { "rx_bps": 512.0, "tx_bps": 512.0 } },
  "_meta": { "router_traffic": "exporter_required" }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `ts` | integer | 응답 생성 Unix 타임스탬프(초) |
| `instances` | object | 인스턴스 UUID → `{rx_bps, tx_bps}` |
| `networks` | object | 네트워크 UUID → `{rx_bps, tx_bps}` |
| `interfaces` | object | 포트 UUID → NIC 단위 트래픽 (instance/network/mac 포함) |
| `routers` | object | 라우터 트래픽. 현재 항상 `{}` — ovs/libvirt exporter 활성화(Phase 2) 후 채워짐 |
| `load_balancers` | object | LB UUID → `{rx_bps, tx_bps}` (Octavia `/stats` 차분) |
| `_meta` | object | 메타 정보 (`router_traffic: exporter_required`) |

**오류**

| 코드 | 설명 |
|------|------|
| `403` | `all_projects=true`를 시스템 admin이 아닌 사용자가 호출 |

### GET /api/v1/networks/topology/traffic/history

네트워크 **1개**의 rx/tx bps 시계열과 평균·최대·최근 통계를 반환합니다. 캔버스 네트워크 패널의 "사용량 추이" 섹션이 **패널을 열 때 1회**, 그리고 사용자가 구간 토글(15분·30분·1시간)을 바꿀 때 호출합니다.

instant 엔드포인트와 **같은 귀속 규칙**을 씁니다 — 즉 이 값은 해당 네트워크에 붙은 NIC 들의 합이며 라우터↔스위치 트래픽이 아닙니다(라우터 exporter 없음). 같은 이유로 east-west(내부 인스턴스 간) 트래픽도 포함됩니다.

설계 제약:

- **폴링 금지.** 전체 네트워크에 대해 주기적으로 호출하면 Prometheus 부하가 네트워크 수만큼 곱해집니다.
- `step_s` 는 range 별 고정값이며 항상 `TOPOLOGY_RATE_WINDOW`(30초) **이하**입니다. `calc_step()`(range/100)을 쓰면 1시간 구간에서 36초가 나와 샘플 사이 트래픽이 그래프에서 사라집니다. `backend/tests/test_topology_traffic.py::test_history_step_never_exceeds_rate_window` 가 이 계약을 고정합니다.
- `stats` 는 별도 `avg_over_time` 쿼리가 아니라 **반환한 `series` 에서 계산**합니다. 두 소스를 쓰면 그래프 최고점과 라벨 숫자가 어긋납니다.
- `stats` 는 rx+tx 합계가 아니라 **방향별**입니다. instant 엔드포인트가 방향별 값을 주므로 합계로 내보내면 같은 패널에서 `▼ 5.8M ▲ 2.0M` 옆에 대조 불가능한 `7.8M` 이 붙습니다. `max` 의 rx·tx 는 서로 다른 시점일 수 있습니다(각 방향의 독립적인 최고값).
- 현재 포트맵에 없는(삭제된) 인스턴스의 과거 트래픽은 귀속 대상이 없어 빠집니다 — instant 엔드포인트도 동일한 한계입니다.
- node_exporter 폴백은 libvirt 미관측 + **단일 NIC** 인스턴스만 귀속합니다. 다중 NIC 는 device 이름으로 네트워크를 가릴 수 없습니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `network_id` | query | string | 예 | 조회할 네트워크 ID |
| `range` | query | string | 아니오 | `15m`(기본) · `30m` · `1h` |
| `all_projects` | query | boolean | 아니오 | 모든 프로젝트 포트 대상 (기본값 `false`). **시스템 admin 전용** |

| `range` | 구간 | `step_s` | 표본 수 |
|---------|------|----------|---------|
| `15m` | 900초 | 15초 | 60 |
| `30m` | 1800초 | 30초 | 60 |
| `1h` | 3600초 | 30초 | 120 |

**응답 (200 OK)**

```json
{
  "network_id": "uuid-string",
  "range": "15m",
  "step_s": 15,
  "window": "30s",
  "series": [
    { "ts": 1767225585, "rx_bps": 4096.0, "tx_bps": 8192.0 },
    { "ts": 1767225600, "rx_bps": 5120.0, "tx_bps": 8192.0 }
  ],
  "stats": {
    "avg": { "rx_bps": 4608.0, "tx_bps": 8192.0 },
    "max": { "rx_bps": 5120.0, "tx_bps": 8192.0 },
    "latest": { "rx_bps": 5120.0, "tx_bps": 8192.0 }
  },
  "_meta": { "source": "network_nic_sum", "router_traffic": "exporter_required" }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `step_s` | integer | 표본 간격(초). rate 윈도우 이하임이 보장됩니다 |
| `window` | string | 백엔드 rate 윈도우(`TOPOLOGY_RATE_WINDOW`) |
| `series` | array | `{ts, rx_bps, tx_bps}` 표본. Prometheus 장애 시 빈 배열 |
| `stats` | object | `series` 에서 계산한 방향별 `avg`·`max`·`latest`. 각 항목은 `{rx_bps, tx_bps}` 이고 표본이 없으면 `null`(0 과 구분) |
| `_meta.source` | string | 항상 `network_nic_sum` — 라우터↔스위치가 아니라 NIC 합산임을 명시 |

**오류**

| 코드 | 설명 |
|------|------|
| `403` | `all_projects=true`를 시스템 admin이 아닌 사용자가 호출 |
| `422` | `network_id` 누락 또는 `range` 가 허용값이 아님 |
