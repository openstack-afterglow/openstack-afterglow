---
title: 프로젝트·초대 (Projects)
parent: API 레퍼런스
nav_order: 12
---

# 프로젝트·초대 (Projects) API

> 태그: `projects`, `invitations`
> 기본 경로: `/api/v1/projects`, `/api/v1/invitations`

사용자가 프로젝트를 만들고, 이메일로 일반 구성원을 초대하며, 현재 Keystone 역할 ID와
상속 그래프를 기준으로 프로젝트 소유권·관리 권한·서비스별 권한을 위임합니다.

---

## 셀프서비스 권한 모델

- **현재 Keystone 권한** — 역할 카탈로그·직접 상속 DAG·유효 프로젝트 할당을 다시 조회합니다. 같은 이름의 도메인 역할, 오래된 JWT 역할 배열, 앱 DB의 기존 `project_roles` 행은 권한 근거가 아닙니다. 조회 실패는 `503`이며 오래된 권한으로 대체하지 않습니다.
- **기존 프로젝트 계층 유지** — `project_owner → project_admin → project_member → project_reader`, `project_member → member`, `project_reader → reader`. 기존 역할 ID·할당을 재사용하며 서비스 권한은 이 계층에 자동 연결하지 않습니다.
- **프로젝트 생성** — 생성자에게 기존 `project_owner`를 명시적으로 할당합니다. 소유권 할당에 실패하면 새 프로젝트 삭제를 보상 시도합니다. 필요한 계층을 임의 생성하거나 DB manager를 등록하지 않습니다.
- **소유자와 관리자** — 현재 `project_owner` 또는 `project_admin`은 멤버·초대·허용된 서비스 역할을 관리합니다. 소유권 및 `project_admin` 부여·회수는 소유자만 가능합니다. 마지막 유효 소유자를 제거하는 변경은 `409`입니다.
- **직접 역할만 교체** — 안전한 전역 프로젝트/서비스 역할의 정확한 ID를 선택합니다. 그룹·도메인 상속과 편집 불가 기존 할당은 유지합니다. 직접 제거할 수 없는 그룹/상속 멤버를 삭제하지 않습니다.
- **서비스 권한 분리** — Waygate·Lumen·Drover·Palimpsest의 `admin/editor/user/reader` 부모와 독립 세부 권한은 실제 Keystone inference edge로만 확장합니다. 서비스 역할에 OpenStack `admin`·`manager` 권한을 연결할 수 없습니다. 프로젝트 소유권 자체도 서비스 사용 권한이 아닙니다.
- **명시적 이전** — 기존 DB 관리자 기록의 이전은 시스템 관리자가 대상 소유자를 지정해 실행합니다. 조회·로그인·프로젝트 전환이 이를 자동 수행하지 않습니다.
- 콘솔의 멤버·초대 목록은 현재 auth/project에만 속합니다. 다른 프로젝트로 전환하면 이전 행·액션·feedback을 즉시 비우고 늦은 응답·mutation 결과를 차단합니다. 동일 scope의 재조회는 기존 행을 유지합니다. 계정 MCP token·OAuth grant·발급 직후 secret도 같은 scope 경계를 사용하며, 확인 dialog가 열린 뒤 scope가 바뀌면 기존 폐기 요청을 제출하지 않습니다.

### 서비스 등급과 명시적 운영 cutover

일반 사용자에게 `member`만 있다는 이유로 네 서비스를 허용하지 않습니다. 시스템 관리자가 [역할 프리셋](admin.md#역할-관리-roles)을 미리보고 명시적으로 적용한 뒤, 프로젝트 owner/admin이 필요한 서비스 부모 또는 세부 역할 ID를 부여합니다. 기존 core/project ID·할당은 교체하지 않으며 GET/login/startup은 역할/edge/manager 이전을 실행하지 않습니다. Native 서비스 directory credential은 현재 enabled user/project, 전역 역할 metadata, inference graph와 유효 할당을 읽을 수 있어야 합니다. 읽기 실패 시 권한을 넓히거나 tenant `admin`/`manager`를 부여하는 fallback은 없습니다.

Waygate의 `waygate-inventory_reader`는 비밀 없는 metadata, `waygate-connect_user`는 본인에게 할당된 enabled client `.conf`/QR만 허용합니다. `waygate-clients_editor`와 `waygate-gateways_editor`는 각각 생성·편집, `waygate-clients_admin`과 `waygate-gateways_admin`은 삭제/폐기, `waygate-routing_admin`은 네트워크 연결·보안 routing 액션입니다. Export/import는 client-admin과 routing-admin을 함께 요구하며 다른 사용자의 할당된 private profiles를 export하지 않습니다. Owner가 미지정인 legacy client는 connect-only 사용자에게 공개하지 않고 editor/admin이 명시적으로 한 번 소유자를 지정합니다. 플랫폼 resource policy는 verified system-admin 전용입니다.

다른 서비스의 독립 leaf·credential 경계는 [Lumen](chat.md#lumen-서비스-세부-권한), [Drover](k3s.md#drover-서비스-권한과-자격-등급), [Palimpsest](../palimpsest.md#프로젝트-package-서비스-등급)를 따릅니다. Runtime은 실제 현재 graph만 읽으므로 부모를 유지한 채 leaf edge를 제거해도 해당 권한이 회수됩니다.



### 초대 흐름

```
프로젝트 소유자/관리자가 이메일로 초대 생성
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

### 프로젝트와 역할 관리

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/projects` | 필요 | 프로젝트 생성, 생성자에게 기존 `project_owner` 할당 |
| `GET` | `/api/v1/projects/current/permissions` | 필요 | 현재 프로젝트에 대한 역할 및 실효 권한 조회 |
| `GET` | `/api/v1/projects/{project_id}/permissions` | 필요 | 지정 프로젝트에 대한 역할 및 실효 권한 조회 |
| `GET` | `/api/v1/projects/{project_id}/members` | 프로젝트 owner/admin | 직접·유효·그룹·상속 멤버 조회 |
| `GET` | `/api/v1/projects/{project_id}/assignable-roles` | 프로젝트 owner/admin | 안전한 역할 ID 카탈로그와 호출자 소유권 |
| `PUT` | `/api/v1/projects/{project_id}/members/{user_id}/roles` | 프로젝트 owner/admin | 관리 가능한 직접 역할 교체; `{ "role_ids": ["role-id"] }` |
| `DELETE` | `/api/v1/projects/{project_id}/members/{user_id}` | 프로젝트 owner/admin | 관리 가능한 직접 역할만 제거 |
| `POST` | `/api/v1/projects/{project_id}/members/migrate-legacy-managers` | 시스템 관리자 | `{ "owner_user_id": "user-id" }`로 명시적 기존 DB 관리자 이전 |
| `POST` | `/api/v1/projects/{project_id}/invitations` | 프로젝트 owner/admin | 일반 프로젝트 역할 이메일 초대 |
| `GET` | `/api/v1/projects/{project_id}/invitations` | 프로젝트 owner/admin | 초대 목록 조회 |
| `DELETE` | `/api/v1/projects/{project_id}/invitations/{invitation_id}` | 프로젝트 owner/admin | pending 초대 취소 |

### 초대 응답 (피초대자)

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `GET` | `/api/v1/invitations/{token}` | 없음 | 초대 링크 정보 조회 |
| `POST` | `/api/v1/invitations/{token}/accept` | 필요 | 초대 수락 (이메일 일치 검증) |
| `POST` | `/api/v1/invitations/{token}/decline` | 없음 | 초대 거절 |

---

## GET /api/v1/projects/current/permissions

현재 활성 프로젝트의 `is_owner`, `is_manager`, `service_permissions`와 OpenStack 읽기·쓰기 권한을 조회합니다. UI는 현재 `service_permissions`의 정확한 세부 권한을 사용하며 `can_write`로 서비스 권한을 추측하지 않습니다. 확인 중·장애·프로젝트 전환 중에는 액션을 비활성화합니다.

일반 사용자 응답의 `roles`는 표시용입니다. 시스템 전용 `admin`·`manager` 및 이들을 상속하는 사용자 정의 역할 이름을 숨기며, 분류할 수 없는 사용자 정의 이름도 노출하지 않습니다. 원래 검증된 역할로 계산한 `can_write`를 전달하므로 이름이 숨겨져도 기존 프로젝트 쓰기 권한은 사라지지 않습니다. Login·refresh·프로젝트 전환 응답과 `/auth/me`도 같은 `roles`/`can_write` 계약을 사용합니다. 서버 서비스 authorization은 이 표시용 배열이나 JWT의 과거 부모 역할이 아니라 현재 검증한 전역 역할 ID·유효 할당·DAG와 프로젝트 소유권을 사용합니다. `is_manager`는 현재 프로젝트 owner/admin에 해당하며 DB manager를 의미하지 않습니다.

### 응답 (200 OK)

```json
{
  "project_id": "p-123",
  "user_id": "u-456",
  "roles": ["reader"],
  "is_system_admin": false,
  "is_owner": false,
  "service_permissions": { "waygate": [], "lumen": [], "drover": [], "palimpsest": [] },
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

인증된 사용자가 프로젝트를 생성하며 생성자에게 기존 `project_owner`를 할당합니다.

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
| `503` | 현재 역할 카탈로그/계층 검증 불가; 초기 소유권 할당 실패 시 새 프로젝트 삭제를 보상 시도 |

---

## GET /api/v1/projects/{project_id}/members

프로젝트의 직접 할당·그룹·상속 유효 멤버를 반환합니다. `is_owner`와 `is_manager`는
현재 역할 그래프에서 계산하며, 역할 교체는 `direct_role_ids` 중 안전한 카탈로그의
관리 가능한 역할만 대상으로 합니다. `effective_role_ids`를 직접 할당으로 복사하지 않습니다.

### 응답 (200 OK)

```json
{
  "items": [
    {
      "user_id": "uuid-string",
      "username": "user-name",
      "email": "user@example.com",
      "is_manager": true,
      "is_owner": false,
      "roles": ["project_admin", "project_member", "member", "project_reader", "reader"],
      "direct_role_ids": ["project-admin-role-id"],
      "effective_role_ids": ["project-admin-role-id", "project-member-role-id", "native-member-role-id", "project-reader-role-id", "native-reader-role-id"],
      "external_role_ids": [],
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
| `source` | `direct`, `group`, `inherited`, `mixed`; 그룹/상속 권한은 직접 교체·제거 불가 |
| `is_owner`, `is_manager` | 현재 유효 `project_owner`, owner/admin 여부 |
| `roles`, `effective_role_ids` | 현재 유효 이름·ID; 직접 할당과 구분 |
| `direct_role_ids` | 사용자의 직접 프로젝트 할당 ID |
| `external_role_ids` | 그룹·도메인 상속 할당만 현재 ID 그래프로 확장한 역할 ID; 직접 부모를 제거해도 남는 외부 상속을 별도로 표시 |
| `group_name` | 그룹 경유 할당의 그룹 표시명 |

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | 현재 프로젝트 관리 권한 없음 |
| `503` | 현재 멤버십·역할 카탈로그 조회 실패 |

---

## POST /api/v1/projects/{project_id}/invitations

이메일 주소로 프로젝트에 초대합니다. 이메일 열거 방지를 위해 사용자 존재 여부와
무관하게 항상 201을 반환합니다.

### 요청 본문

```json
{
  "email": "string (필수)",
  "keystone_role": "project_member (선택)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `email` | string | 예 | 초대할 이메일 주소 |
| `keystone_role` | `project_member` 또는 `project_reader` | 아니오 | 기본 `project_member`; 소유자·관리자·서비스 역할·native `admin`/`manager`는 `422` |

이 두 역할 외의 권한을 요청하는 기존 초대도 수락 시 `403`으로 거부하며 임의로 이전하지 않습니다. 서비스 역할은 초대 수락 후 관리 화면에서 정확한 역할 ID로 따로 위임합니다.

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
| `403` | 현재 프로젝트 관리 권한 없음 |

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
      "keystone_role": "project_member",
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
| `403` | 현재 프로젝트 관리 권한 없음 |
| `404` | 초대를 찾을 수 없음 |
| `409` | 취소할 수 없는 상태 (pending이 아님) |

---

## 역할 교체·제거와 기존 관리자 이전

`PUT /projects/{project_id}/members/{user_id}/roles`는 `assignable-roles`가 반환한 정확한 ID 목록을 받습니다. 관리자에게 허용되지 않는 소유자/관리자 전환, 시스템 전용 역할, native `admin`·`manager`로 이어지는 역할은 거부합니다. 기존 편집 불가 직접 역할과 그룹·도메인 상속은 유지합니다. `DELETE /members/{user_id}`도 같은 정책으로 관리 가능한 직접 역할만 제거하며 마지막 유효 소유자를 제거하지 않습니다.

멤버 응답은 `direct_role_ids`(현재 직접 할당), `effective_role_ids`(모든 유효 할당의 현재 ID 그래프 확장), `external_role_ids`(group/domain inherited 할당만 같은 그래프로 확장)를 분리합니다. `external_role_ids`는 merged effective 목록에서 직접 부모의 descendant를 빼서 추정하지 않습니다. 같은 하위 역할이 직접 부모와 그룹·도메인 양쪽에서 부여된 경우에도 부모 제거 후 외부 상속은 남아 checked/read-only로 표시됩니다. 이 provenance projection은 조회 응답만 보완하며 실제 Keystone 할당·인가·DB schema를 변경하지 않습니다.

`assignable-roles`의 각 role은 `implied_role_ids`(직접 연결)와 `inherited_role_ids`(검증된 현재 ID 그래프의 전체 descendant)를 제공합니다. 브라우저는 직접 선택한 부모의 descendant를 자동으로 체크·비활성화하고 선택을 해제하면 다시 계산합니다. 공유 부모의 상속, 기존 명시적 direct child, 편집 범위 밖의 group/domain inheritance는 유지합니다. 이름·ID·설명의 대소문자 무관 검색은 숨겨진 선택을 지우지 않으며 저장 요청에는 direct ID만 포함합니다. 이 UI projection은 새로운 Keystone grant를 만들거나 기존 direct child를 자동 삭제하지 않습니다.

기존 `/managers/{user_id}` 승격·해제 경로는 제거했습니다. DB manager 행은 조회 권한이 아닙니다. 시스템 관리자의 `POST /projects/{project_id}/members/migrate-legacy-managers`만 명시한 소유자와 기존 대상자를 안전한 역할 계층으로 이전하고 DB 기록을 정리합니다. 호출 전에 현재 역할 카탈로그·할당을 검토하고, 실패 시 결과를 확인한 뒤 재실행합니다. 이 변경은 운영 데이터나 역할을 자동 수정하지 않습니다.
주요 실패: `403` 권한·안전 경계 위반, `409` 마지막 소유자/동시 변경 충돌, `503` Keystone 카탈로그·할당 검증 불가. 오류를 오래된 역할이나 DB manager로 대체하지 않습니다.

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
