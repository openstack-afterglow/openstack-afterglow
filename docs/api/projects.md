---
title: 프로젝트·초대 (Projects)
parent: API 레퍼런스
nav_order: 12
---

# 프로젝트·초대 (Projects) API

> 태그: `projects`, `invitations`
> 기본 경로: `/api/v1/projects`, `/api/v1/invitations`

사용자가 직접(셀프서비스) 프로젝트를 만들고, 이메일로 멤버를 초대하고, 프로젝트
관리자(manager)를 지정하는 기능을 제공합니다.

---

## 셀프서비스 권한 모델

Afterglow는 Keystone role 위에 앱 수준의 **프로젝트 매니저(manager)** 개념을 둡니다.
manager 정보는 앱 DB(`project_roles` 테이블)에 저장됩니다.

- **프로젝트 생성** — 인증된 사용자는 누구나 프로젝트를 만들 수 있습니다. Keystone에
  프로젝트가 생성되고, 생성자에게 Keystone `member` role이 부여되며, 앱 DB에
  생성자를 `manager`로 등록합니다.
- **manager 권한** — 멤버 조회, 초대 생성/조회/취소, 매니저 승격/해제는 **해당
  프로젝트의 manager만** 수행할 수 있습니다(`require_project_manager`). 시스템
  관리자는 이 검사를 bypass합니다. manager가 아니면 403입니다.
- **마지막 매니저 보호** — 프로젝트에는 최소 1명의 manager가 필요합니다. 마지막
  매니저는 해제할 수 없습니다(409).

### 초대 흐름

```
매니저가 이메일로 초대 생성
  → (해당 이메일의 Keystone 사용자 존재 시) 초대 메일 발송, status=pending
  → (Keystone 사용자 없음)                     status=no_user (메일 미발송)
피초대자가 초대 링크 접속 (GET /invitations/{token})
  → 수락 (POST /invitations/{token}/accept)  → Keystone role 할당, status=accepted
  → 거절 (POST /invitations/{token}/decline) → status=declined
```

- 초대 토큰은 평문으로 발급되어 링크에만 담기고, 서버에는 SHA-256 해시로 저장됩니다.
- 초대 만료 기간은 `smtp_invitation_token_expiry_days` 설정을 따릅니다.
- 이메일 열거(enumeration) 방지를 위해 초대 생성은 사용자 존재 여부와 무관하게
  항상 201을 반환합니다.
- 수락 시 **로그인한 사용자의 이메일 == 초대 이메일** 검증을 통과해야 합니다(불일치 403).

---

## 엔드포인트 목록

### 프로젝트 (manager 권한)

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/projects` | 필요 | 프로젝트 생성 (생성자가 manager) |
| `GET` | `/api/v1/projects/current/permissions` | 필요 | 현재 프로젝트에 대한 역할 및 실효 권한 조회 |
| `GET` | `/api/v1/projects/{project_id}/permissions` | 필요 | 지정 프로젝트에 대한 역할 및 실효 권한 조회 |
| `GET` | `/api/v1/projects/{project_id}/members` | manager | 프로젝트 멤버 목록 |
| `POST` | `/api/v1/projects/{project_id}/invitations` | manager | 이메일 초대 생성 |
| `GET` | `/api/v1/projects/{project_id}/invitations` | manager | 초대 목록 조회 |
| `DELETE` | `/api/v1/projects/{project_id}/invitations/{invitation_id}` | manager | 초대 취소 (pending만) |
| `POST` | `/api/v1/projects/{project_id}/managers/{user_id}` | manager | 멤버를 manager로 승격 |
| `DELETE` | `/api/v1/projects/{project_id}/managers/{user_id}` | manager | manager 해제 |

### 초대 응답 (피초대자)

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/api/v1/invitations/{token}` | 없음 | 초대 링크 정보 조회 |
| `POST` | `/api/v1/invitations/{token}/accept` | 필요 | 초대 수락 (이메일 일치 검증) |
| `POST` | `/api/v1/invitations/{token}/decline` | 없음 | 초대 거절 |

---

## GET /api/v1/projects/current/permissions

현재 활성 프로젝트 컨텍스트에 대한 호출자의 역할 및 실효 권한(`can_write`, `is_reader`, `is_manager` 등)을 조회합니다.

### 응답 (200 OK)

```json
{
  "project_id": "p-123",
  "user_id": "u-456",
  "roles": ["reader"],
  "is_system_admin": false,
  "is_manager": false,
  "is_reader": true,
  "can_read": true,
  "can_write": false
}
```

---

## GET /api/v1/projects/{project_id}/permissions

특정 프로젝트에 대한 호출자의 역할 및 실효 권한을 조회합니다. 호출자가 해당 프로젝트의 멤버가 아니거나 관리자가 아닌 경우 403 Forbidden을 반환합니다. `project_id`로 `current`를 전달하면 현재 활성 프로젝트의 권한을 반환합니다.

---

## POST /api/v1/projects

인증된 사용자가 프로젝트를 생성합니다. 생성자는 자동으로 manager가 됩니다.

### 요청 본문

```json
{
  "name": "string (필수)",
  "description": "string (선택)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 프로젝트 이름 (공백만은 불가) |
| `description` | string | 아니오 | 프로젝트 설명 |

### 응답 (201 Created)

```json
{
  "id": "uuid-string",
  "name": "project-name",
  "description": "프로젝트 설명"
}
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |
| `422` | 프로젝트 이름 누락 |
| `500` | 프로젝트 생성 실패 (Keystone/DB 실패 시 보상 삭제 수행) |

---

## GET /api/v1/projects/{project_id}/members

프로젝트 멤버 목록을 반환합니다. Keystone에 직접 role이 할당된 사용자와, 요청자
본인이 속한 그룹의 멤버를 확장해서 함께 반환합니다. 각 멤버에는 manager 뱃지가
붙습니다.

### 응답 (200 OK)

```json
{
  "items": [
    {
      "user_id": "uuid-string",
      "username": "user-name",
      "email": "user@example.com",
      "is_manager": true,
      "source": "direct"
    },
    {
      "user_id": "uuid-string",
      "username": "user-name",
      "email": "",
      "is_manager": false,
      "source": "group",
      "group_name": "dev-team"
    }
  ]
}
```

| 필드 | 설명 |
|------|------|
| `source` | `direct`(직접 할당) 또는 `group`(그룹 멤버십 경유) |
| `is_manager` | 앱 DB 기준 manager 여부 |
| `group_name` | `source=group`일 때만 포함 |

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | manager 권한 없음 |
| `500` | 멤버 목록 조회 실패 |

---

## POST /api/v1/projects/{project_id}/invitations

이메일 주소로 프로젝트에 초대합니다. 이메일 열거 방지를 위해 사용자 존재 여부와
무관하게 항상 201을 반환합니다.

### 요청 본문

```json
{
  "email": "string (필수)",
  "keystone_role": "member (선택)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `email` | string | 예 | 초대할 이메일 주소 |
| `keystone_role` | string | 아니오 | 수락 시 부여할 Keystone role (기본 `member`) |

### 응답 (201 Created)

```json
{
  "id": 1,
  "project_id": "uuid-string",
  "invited_email": "user@example.com",
  "status": "pending",
  "expires_at": "2026-01-08T00:00:00+00:00",
  "created_at": "2026-01-01T00:00:00+00:00"
}
```

`status`는 초대 이메일의 Keystone 사용자가 존재하면 `pending`(메일 발송),
없으면 `no_user`(메일 미발송)입니다.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | manager 권한 없음 |

---

## GET /api/v1/projects/{project_id}/invitations

프로젝트의 초대 목록을 최신순으로 조회합니다.

### 응답 (200 OK)

```json
{
  "items": [
    {
      "id": 1,
      "invited_email": "user@example.com",
      "invited_by_name": "inviter-name",
      "status": "pending",
      "keystone_role": "member",
      "expires_at": "2026-01-08T00:00:00Z",
      "accepted_at": null,
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

`status`는 `pending`, `no_user`, `accepted`, `declined`, `revoked`, `expired` 중 하나입니다.

---

## DELETE /api/v1/projects/{project_id}/invitations/{invitation_id}

초대를 취소합니다. `pending` 상태만 취소할 수 있습니다.

### 응답

`204 No Content`.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | manager 권한 없음 |
| `404` | 초대를 찾을 수 없음 |
| `409` | 취소할 수 없는 상태 (pending이 아님) |

---

## POST /api/v1/projects/{project_id}/managers/{user_id}

프로젝트 멤버를 manager로 승격합니다. 이미 manager이면 멱등적으로 동작합니다.

### 응답

`204 No Content`.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | manager 권한 없음 |

---

## DELETE /api/v1/projects/{project_id}/managers/{user_id}

manager 권한을 해제합니다. 마지막 manager는 해제할 수 없습니다.

### 응답

`204 No Content`.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | manager 권한 없음 |
| `404` | 해당 사용자가 이 프로젝트의 manager가 아님 |
| `409` | 마지막 manager는 해제 불가 |

---

## GET /api/v1/invitations/{token}

초대 링크 정보를 조회합니다(**인증 불필요**). 초대 수락 페이지에서 호출합니다.
만료된 pending 초대는 조회 시점에 `expired`로 갱신됩니다.

### 응답 (200 OK)

```json
{
  "project_id": "uuid-string",
  "project_name": "project-name",
  "inviter_name": "inviter-name",
  "invited_email": "user@example.com",
  "status": "pending",
  "expires_at": "2026-01-08T00:00:00+00:00"
}
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `404` | 유효하지 않은 초대 링크 |

---

## POST /api/v1/invitations/{token}/accept

초대를 수락합니다. **JWT 인증 필수** + 수락자 이메일 == 초대 이메일 검증을 통과하면
Keystone role이 할당됩니다.

### 응답 (200 OK)

```json
{ "status": "accepted", "project_id": "uuid-string" }
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |
| `403` | 초대 이메일과 로그인 이메일 불일치 |
| `404` | 유효하지 않은 초대 링크 |
| `410` | 이미 처리되었거나 만료된 초대 |
| `500` | Keystone role 할당 실패 |

---

## POST /api/v1/invitations/{token}/decline

초대를 거절합니다(**인증 불필요** — 토큰만으로 처리). 이미 accepted/declined/revoked
상태이면 해당 상태를 그대로 반환합니다.

### 응답 (200 OK)

```json
{ "status": "declined" }
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `404` | 유효하지 않은 초대 링크 |
