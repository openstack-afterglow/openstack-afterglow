---
title: 라우터 (Routers)
parent: API 레퍼런스
nav_order: 51
---

# 라우터 (Routers) API

> 태그: `routers`
> 기본 경로: `/api/v1/routers`

Neutron 라우터와 인터페이스, 외부 게이트웨이를 관리합니다.
라우터는 서브넷 간 라우팅(내부 인터페이스)과 외부망 연결(게이트웨이) 두 역할을 담당합니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 공통 사항

- **소유권 검증**: 단일 라우터를 다루는 엔드포인트와 모든 mutation은 라우터 `project_id`가 토큰 프로젝트와 일치하고 비어 있지 않은 경우에만 처리합니다. 인터페이스 추가·제거는 대상 서브넷도 같은 조건을 만족해야 합니다. 불일치 또는 owner metadata 누락은 `404`로 응답합니다(존재 은닉). system admin만 이 검사에서 우회합니다.
- **캐시**: 라우터 목록(`GET ""`)은 `ttl_normal`(`afterglow.conf`로 조정, 기본 30초)로 캐시됩니다.
  생성/삭제 mutation 시 목록 캐시가 무효화됩니다.
- **Rate limit**: 모든 mutation 엔드포인트(생성/삭제/인터페이스/게이트웨이)는 `10/minute` 제한이 적용됩니다.

### 인터페이스 vs 게이트웨이

| 구분 | 대상 | 방향 | 엔드포인트 |
|------|------|------|-----------|
| 내부 인터페이스 | 테넌트 서브넷 | 서브넷 ↔ 라우터 | `POST·DELETE /{router_id}/interfaces` |
| 외부 게이트웨이 | 외부 네트워크(`is_external`) | 라우터 → 외부망(SNAT) | `POST·DELETE /{router_id}/gateway` |

게이트웨이 설정에는 반드시 **외부 네트워크**(`is_external = true`)의 UUID가 필요합니다.

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/routers` | 라우터 목록 (30초 캐시) |
| `POST` | `/api/v1/routers` | 라우터 생성 |
| `GET` | `/api/v1/routers/{router_id}` | 라우터 상세 (인터페이스 포함) |
| `DELETE` | `/api/v1/routers/{router_id}` | 라우터 삭제 |
| `POST` | `/api/v1/routers/{router_id}/interfaces` | 서브넷 인터페이스 추가 |
| `DELETE` | `/api/v1/routers/{router_id}/interfaces/{subnet_id}` | 인터페이스 제거 |
| `POST` | `/api/v1/routers/{router_id}/gateway` | 외부 게이트웨이 설정 |
| `DELETE` | `/api/v1/routers/{router_id}/gateway` | 게이트웨이 제거 |

---

## GET /api/v1/routers

프로젝트의 Neutron 라우터 목록을 반환합니다. 응답은 30초간 캐시됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `refresh` | query | boolean | 아니오 | `true`이면 캐시를 무시하고 재조회 |

**응답 (200 OK)** — `RouterInfo[]` 배열

```json
[
  {
    "id": "uuid-string",
    "name": "router-name",
    "status": "ACTIVE",
    "project_id": "uuid-string",
    "external_gateway_network_id": "uuid-string",
    "connected_subnet_ids": ["uuid-string"]
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 라우터 UUID |
| `name` | string | 라우터 이름 |
| `status` | string | 상태 (`ACTIVE`, `DOWN` 등) |
| `project_id` | string\|null | 프로젝트 UUID |
| `external_gateway_network_id` | string\|null | 외부 게이트웨이로 설정된 네트워크 UUID (없으면 `null`) |
| `connected_subnet_ids` | array[string] | 연결된 내부 서브넷 UUID 목록 |

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 라우터 목록 조회 실패 |

---

## POST /api/v1/routers

새 라우터를 생성합니다. `external_network_id`를 함께 전달하면 생성과 동시에 외부 게이트웨이가 설정됩니다.

**요청 본문** — `CreateRouterRequest`

```json
{
  "name": "string (필수)",
  "external_network_id": "uuid-string (선택)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 라우터 이름 |
| `external_network_id` | string | 아니오 | 외부 게이트웨이로 설정할 외부 네트워크 UUID |

**응답 (201 Created)** — `RouterInfo` 객체

**오류**

| 코드 | 설명 |
|------|------|
| `500` | 라우터 생성 실패 |

---

## GET /api/v1/routers/{router_id}

특정 라우터의 상세 정보를 반환합니다. 연결된 인터페이스 목록과 외부 게이트웨이 네트워크 이름을 포함합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |

**응답 (200 OK)** — `RouterDetail`

```json
{
  "id": "uuid-string",
  "name": "router-name",
  "status": "ACTIVE",
  "project_id": "uuid-string",
  "external_gateway_network_id": "uuid-string",
  "external_gateway_network_name": "external-net",
  "interfaces": [
    {
      "id": "uuid-string (포트 ID)",
      "subnet_id": "uuid-string",
      "subnet_name": "subnet-name",
      "network_id": "uuid-string",
      "ip_address": "192.168.1.1"
    }
  ]
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `external_gateway_network_name` | string\|null | 외부 게이트웨이 네트워크 이름 |
| `interfaces[].id` | string | 인터페이스 포트 UUID |
| `interfaces[].subnet_id` | string | 연결된 서브넷 UUID |
| `interfaces[].ip_address` | string | 라우터가 해당 서브넷에서 갖는 인터페이스 IP |

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터를 찾을 수 없음 / 소유권 불일치 |

---

## DELETE /api/v1/routers/{router_id}

라우터를 삭제합니다. 연결된 인터페이스나 게이트웨이가 있으면 먼저 제거해야 합니다. 삭제 후 목록 캐시를 무효화합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터를 찾을 수 없음 / 소유권 불일치 |
| `500` | 라우터 삭제 실패 (인터페이스·게이트웨이 잔존 등) |

---

## POST /api/v1/routers/{router_id}/interfaces

라우터에 **같은 프로젝트가 소유한** 서브넷 내부 인터페이스를 추가합니다. `auto_gateway`가 `true`이면 서브넷의 게이트웨이 IP를 인터페이스 IP로 사용합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |

**요청 본문** — `RouterInterfaceRequest`

```json
{
  "subnet_id": "uuid-string (필수)",
  "auto_gateway": false
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `subnet_id` | string | 예 | 연결할 서브넷 UUID |
| `auto_gateway` | boolean | 아니오 | 서브넷 게이트웨이 IP를 인터페이스로 사용 (기본값: `false`) |

**응답 (201 Created)**

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터 또는 서브넷을 찾을 수 없음 / 소유권 불일치 / owner metadata 누락 |
| `500` | 인터페이스 추가 실패 |

---

## DELETE /api/v1/routers/{router_id}/interfaces/{subnet_id}

라우터에서 서브넷 인터페이스를 제거합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |
| `subnet_id` | path | string | 예 | 제거할 서브넷 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터를 찾을 수 없음 / 소유권 불일치 |
| `500` | 인터페이스 제거 실패 |

---

## POST /api/v1/routers/{router_id}/gateway

라우터에 외부 게이트웨이를 설정합니다. 대상은 외부 네트워크(`is_external = true`)여야 합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |

**요청 본문** — `RouterGatewayRequest`

```json
{
  "external_network_id": "uuid-string (필수)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `external_network_id` | string | 예 | 외부 게이트웨이로 설정할 외부 네트워크 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터를 찾을 수 없음 / 소유권 불일치 |
| `500` | 게이트웨이 설정 실패 |

---

## DELETE /api/v1/routers/{router_id}/gateway

라우터의 외부 게이트웨이를 제거합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `router_id` | path | string | 예 | 라우터 UUID |

**응답**: `204 No Content`

**오류**

| 코드 | 설명 |
|------|------|
| `404` | 라우터를 찾을 수 없음 / 소유권 불일치 |
| `500` | 게이트웨이 제거 실패 |
