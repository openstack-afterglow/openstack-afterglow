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
| `GET` | `/api/v1/profile/ssh-key-preference` | 계정의 기본 SSH 키 조회 |
| `PUT` | `/api/v1/profile/ssh-key-preference` | 기본 SSH 키 지정·해제 |

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

삭제한 키가 기본 키이면 설정도 해제합니다. 삭제 처리 중 다른 기본 키로 바꾼 경우 새 설정은 보존합니다. Nova 삭제 후 설정 저장소 정리에 실패하면 `503`을 반환할 수 있으므로 자동 재시도하지 말고 목록과 설정을 다시 조회합니다.

## 기본 SSH 키 설정

`GET /api/v1/profile/ssh-key-preference`는 `{"keypair_name": null}` 또는 저장된 키 이름을 반환합니다. `PUT`은 같은 형태의 본문을 받으며 `keypair_name` 필드는 필수이고 명시적 `null`로 해제합니다. 이름은 1–255자이며 호출자 연결의 현재 Nova 키 목록에 없으면 `404`, 잘못된 본문은 `422`, Redis 장애는 `503`입니다. 응답은 `Cache-Control: private, no-store`입니다.

설정은 원래 소속 도메인 UUID와 사용자 UUID의 해시로 Redis에 저장하며 프로젝트를 전환해도 유지합니다. 권한이나 키 자료를 저장하지 않습니다. 계정 SSH 키 화면은 지정·해제와 기본 배지를 제공합니다. VM 생성은 현재 목록에 저장된 키가 있을 때만 미리 선택하고 사용자가 바꿀 수 있습니다. 사라진 키·설정 없음·설정 조회 실패는 선택하지 않으며, Windows·관리자 생성·GitHub SSH 경로에는 적용하지 않습니다.

GitHub SSH에서 등록 키 방식으로 돌아오거나 생성 완료 후 새 생성을 시작하면 기본 키를 다시 적용합니다. 같은 등록 키 설정 과정에서 사용자가 선택을 바꾸거나 비운 값은 재조회만으로 덮어쓰지 않습니다.