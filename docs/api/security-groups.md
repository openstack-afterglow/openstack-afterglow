---
title: 보안 그룹 (Security Groups)
parent: API 레퍼런스
nav_order: 53
---

# 보안 그룹 (Security Groups) API

> 태그: `security-groups`  
> 기본 경로: `/api/v1/security-groups`

Neutron 보안 그룹과 규칙을 관리합니다. 인스턴스의 네트워크 트래픽 접근 제어에 사용됩니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 목차

1. [보안 그룹](#1-보안-그룹)
2. [보안 그룹 규칙](#2-보안-그룹-규칙)

---

## 1. 보안 그룹

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/security-groups` | 보안 그룹 목록 (60초 캐시) |
| `GET` | `/api/v1/security-groups/quota` | 현재 프로젝트의 그룹·규칙 쿼터와 사용량 |
| `GET` | `/api/v1/security-groups/{sg_id}/instances` | 해당 그룹을 포트에 적용한 프로젝트 인스턴스 |
| `POST` | `/api/v1/security-groups` | 보안 그룹 생성 |
| `DELETE` | `/api/v1/security-groups/{sg_id}` | 보안 그룹 삭제 |

### GET /api/v1/security-groups

프로젝트의 보안 그룹 목록을 반환합니다. 응답은 60초간 캐시됩니다.

**응답 (200 OK)** — 배열

```json
[
  {
    "id": "uuid-string",
    "name": "default",
    "description": "Default security group",
    "rules": [
      {
        "id": "uuid-string",
        "direction": "ingress",
        "protocol": null,
        "port_range_min": null,
        "port_range_max": null,
        "remote_ip_prefix": null,
        "ethertype": "IPv4",
        "remote_group_id": null
      }
    ]
  }
]
```

규칙에는 `remote_group_id`가 포함됩니다. CIDR 규칙이면 `null`, 보안 그룹 대상 규칙이면 현재 지정된 그룹의 UUID입니다. 화면에는 해당 프로젝트 그룹의 이름과 UUID를 함께 표시합니다.

### GET /api/v1/security-groups/quota

현재 프로젝트 Neutron의 보안 그룹/규칙 쿼터 `limit`과 실제 `in_use`를 반환합니다. `limit: -1`은 무제한이며, 상세 사용량을 확인할 수 없으면 0으로 대체하지 않고 조회 오류를 반환합니다.

```json
{
  "security_group": { "limit": 10, "in_use": 2 },
  "security_group_rule": { "limit": 100, "in_use": 7 }
}
```

### GET /api/v1/security-groups/{sg_id}/instances

현재 프로젝트 소유 그룹만 조회할 수 있습니다. 해당 그룹이 적용된 프로젝트의 Neutron compute 포트를 Nova 인스턴스와 조합해, 포트가 여러 개여도 인스턴스별로 한 번만 반환합니다. 빈 목록은 연결된 인스턴스가 없다는 뜻이며 조회 실패는 빈 목록으로 숨기지 않습니다.

```json
[{ "id": "instance-uuid", "name": "app-vm", "status": "ACTIVE" }]
```

### POST /api/v1/security-groups

새 보안 그룹을 생성합니다.

**요청 본문**

```json
{
  "name": "string (필수)",
  "description": "string (선택)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 보안 그룹 이름 |
| `description` | string | 아니오 | 설명 |

**응답 (201 Created)**

### DELETE /api/v1/security-groups/{sg_id}

보안 그룹을 삭제합니다. 기본 보안 그룹은 삭제할 수 없습니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `sg_id` | path | string | 예 | 보안 그룹 UUID |

**응답**: `204 No Content`

---

## 2. 보안 그룹 규칙

![보안 그룹 규칙 상세](../../assets/security-group-detail.png)
*규칙 목록의 IP 버전 열은 각 규칙의 `ethertype`(`IPv4`/`IPv6`)을 표시하고 표 안에서 규칙을 추가·제거합니다. Neutron은 포트·대상 등 규칙 필드의 직접 수정을 제공하지 않으므로 편집은 기존 값을 복사한 뒤 명시적으로 제거하고 새 규칙을 만드는 흐름이며, 두 요청 사이 정책이 바뀔 수 있습니다.*

### 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `POST` | `/api/v1/security-groups/{sg_id}/rules` | 보안 그룹 규칙 추가 |
| `DELETE` | `/api/v1/security-groups/{sg_id}/rules/{rule_id}` | 보안 그룹 규칙 삭제 |

### POST /api/v1/security-groups/{sg_id}/rules

보안 그룹에 새 규칙을 추가합니다.

**요청 본문**

```json
{
  "direction": "ingress",
  "protocol": "tcp",
  "port_range_min": 22,
  "port_range_max": 22,
  "remote_ip_prefix": "0.0.0.0/0",
  "ethertype": "IPv4"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `direction` | string | 예 | 트래픽 방향 (`ingress`, `egress`) |
| `protocol` | string | 아니오 | 프로토콜 (`tcp`, `udp`, `icmp`, `null` = 모든 프로토콜) |
| `port_range_min` | integer | 아니오 | 최소 포트 번호 |
| `port_range_max` | integer | 아니오 | 최대 포트 번호 |
| `remote_ip_prefix` | string | 아니오 | 원격 IP 대역 (CIDR 표기법, 예: `0.0.0.0/0`) |
| `remote_group_id` | string | 아니오 | 원격 보안 그룹 UUID (현재 프로젝트 소유). `remote_ip_prefix`와 함께 지정할 수 없음 |
| `ethertype` | string | 아니오 | 이더타입 (`IPv4`, `IPv6`, 기본값: `IPv4`) |

CIDR과 보안 그룹 중 한 가지 대상만 선택합니다. 둘 다 생략하거나 CIDR을 비우면 IPv4에서 `0.0.0.0/0`, IPv6에서 `::/0`을 사용합니다. 시작 포트만 입력하면 끝 포트는 같은 번호로 생성합니다. 그룹 대상에는 기본 CIDR을 동시에 전송하지 않습니다.

| direction 허용 값 | 설명 |
|-------------------|------|
| `ingress` | 인바운드 트래픽 (수신) |
| `egress` | 아웃바운드 트래픽 (송신) |

| protocol 허용 값 | 설명 |
|-----------------|------|
| `tcp` | TCP |
| `udp` | UDP |
| `icmp` | ICMP |
| `null` | 모든 프로토콜 |

**응답 (201 Created)**

```json
{
  "id": "uuid-string",
  "direction": "ingress",
  "protocol": "tcp",
  "port_range_min": 22,
  "port_range_max": 22,
  "remote_ip_prefix": "0.0.0.0/0",
  "ethertype": "IPv4",
  "security_group_id": "uuid-string",
  "remote_group_id": null
}
```

### DELETE /api/v1/security-groups/{sg_id}/rules/{rule_id}

보안 그룹 규칙을 삭제합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `sg_id` | path | string | 예 | 보안 그룹 UUID |
| `rule_id` | path | string | 예 | 규칙 UUID |

**응답**: `204 No Content`