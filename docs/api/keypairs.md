---
title: 키페어 (Keypairs)
parent: API 레퍼런스
nav_order: 35
---

# 키페어 (Keypairs) API

> 태그: `keypairs`  
> 기본 경로: `/api/v1/keypairs`

Nova SSH 키페어를 관리합니다. 인스턴스 생성 시 SSH 접속에 사용됩니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/keypairs` | 키페어 목록 반환 |
| `POST` | `/api/v1/keypairs` | 키페어 생성 |
| `DELETE` | `/api/v1/keypairs/{keypair_name}` | 키페어 삭제 |

---

## GET /api/v1/keypairs

현재 인증된 사용자의 SSH 키페어 목록을 반환합니다. OpenStack Compute(Nova)의 키페어는 사용자(`user_id`) 단위로 격리되며, 동일 프로젝트 내 다른 사용자에게 노출되지 않습니다.

### 응답 (200 OK)

```json
[
  {
    "name": "my-key",
    "fingerprint": "SHA256:...",
    "type": "ssh",
    "created_at": "2024-01-01T00:00:00Z"
  }
]
```

---

## POST /api/v1/keypairs

새 SSH 키페어를 생성합니다.

### 요청 본문

```json
{
  "name": "string (필수)",
  "public_key": "string (선택, 없으면 Nova가 생성)",
  "key_type": "ssh"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 키페어 이름 |
| `public_key` | string | 아니오 | 공개키. 생략 시 Nova가 개인키와 함께 생성 |
| `key_type` | string | 아니오 | 키페어 타입 (기본값: `ssh`) |

### 응답 (200 OK)

```json
{
  "name": "my-key",
  "fingerprint": "SHA256:...",
  "public_key": "ssh-rsa AAAA...",
  "private_key": "-----BEGIN RSA PRIVATE KEY-----\n...(Nova가 생성한 경우만 포함)\n-----END RSA PRIVATE KEY-----"
}
```

> **참고**: `public_key`를 제공하지 않은 경우에만 `private_key`가 응답에 포함됩니다. 개인키는 이 시점에만 확인 가능하므로 반드시 안전하게 보관해야 합니다.

---

## DELETE /api/v1/keypairs/{keypair_name}

키페어를 삭제합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `keypair_name` | path | string | 예 | 키페어 이름 |

### 응답

`204 No Content`