---
title: 프로젝트 (Projects)
parent: API 레퍼런스
nav_order: 12
---

# 프로젝트 (Projects) API

> 태그: `projects`
> 기본 경로: `/api/v1/projects`

현재 **working domain**의 도메인 manager와 위임받은 `project_creator`가 프로젝트를 만들고, 도메인 manager 또는 프로젝트 owner/admin이 현재 Keystone 역할 ID와 상속 그래프에 따라 멤버 권한을 관리합니다. 계정의 immutable identity domain과 작업 대상 domain은 서로 다를 수 있습니다. 이메일 초대는 현재 [도메인 IAM](iam.md), 공개 링크 수락·가입은 [인증 onboarding](auth.md#공개-이메일-검증-onboarding)을 사용합니다. 아래 계약은 현재 프로젝트 router/schema/service 기준이며 proposal의 미구현 경로를 API로 가정하지 않습니다.

---

## 셀프서비스 권한 모델

- **현재 Keystone 권한** — 역할 카탈로그·직접 상속 DAG·유효 프로젝트 할당을 다시 조회합니다. 같은 이름의 도메인 역할, 오래된 JWT 역할 배열, 앱 DB의 기존 `project_roles` 행은 권한 근거가 아닙니다. 조회 실패는 `503`이며 오래된 권한으로 대체하지 않습니다.
- **기존 프로젝트 계층 유지** — `project_owner → project_admin → project_member → project_reader`, `project_member → member`, `project_reader → reader`. 기존 역할 ID·할당을 재사용하며 서비스 권한은 이 계층에 자동 연결하지 않습니다.
- **시스템 관리자가 확장한 하위 역할** — 전역 custom 역할(예: `project_reader → audit`)을 명시적으로 연결한 그래프에서도 기존 프로젝트 등급의 관리·멤버 할당을 유지합니다. Custom 역할의 직접 독립 위임은 허용하지 않으며 해당 등급을 통해 현재 ID 그래프대로만 상속합니다. 알려진 core/project/서비스 권한 승격·도메인 혼합·중복 역할 ID 바인딩은 계속 거부합니다.
- **프로젝트 생성** — 대상 도메인의 현재 Default manager 또는 정확한 native domain scope에서 `project_creator`가 유효한 가입 사용자만 가능합니다. 프로젝트 owner/admin 등급이나 `system:all` admin만으로 생성 권한이 생기지 않습니다. 새 프로젝트는 disabled로 만들고 생성자 한 명의 직접 `project_owner`, manager 접근 projection, 도메인 quota defaults와 readback을 완료한 뒤 활성화합니다. 불확실한 실패를 자동 삭제하거나 재생성하지 않습니다.
- **유일한 명시적 소유권** — 일반 프로젝트는 정확한 `project_owner` 직접 사용자 할당 하나만 정상 소유권입니다. 복수 owner, owner를 함의하는 다른 역할, group/domain/ancestor 상속 owner는 conflict이며 자동으로 한 명을 선택하지 않습니다. `manager > owner`는 도메인 관리 우선순위이지 `manager → project_owner` inference edge가 아닙니다. Default는 별도의 도메인 권위 프로젝트이며 소유권 이전·삭제 대상이 아닙니다.
- **멤버 관리와 소유권 분리** — owner 또는 도메인 manager는 `project_admin`을 변경할 수 있고 project admin은 그보다 낮은 허용 역할만 관리합니다. 일반 역할 편집·멤버 제거는 owner-bearing grant를 추가/제거할 수 없습니다. 소유권 변경은 전용 transfer 경로만 사용하며 `assignable-roles.can_manage_owners`는 항상 `false`입니다. 직접 역할만 교체하고 편집 불가 기존 직접 할당과 그룹·도메인 상속은 유지합니다.
- **로그인과 권한 분리** — 본인을 포함한 프로젝트 role 추가·교체·회수는 로그인 세션을 일괄 폐기하지 않습니다. 새 요청은 현재 Keystone 권한으로 검증하므로 회수한 역할은 다음 로그인까지 유지되지 않습니다. 프로젝트 관리 권한 자체를 없애면 이후 관리 요청은 `403`입니다. 명시적 세션 폐기·계정 차단·유효하지 않은 native 로그인 증명은 기존대로 재로그인 대상입니다.
- **서비스 권한 분리** — Waygate·Lumen·Drover·Palimpsest의 `admin/editor/user/reader` 부모와 독립 세부 권한은 실제 Keystone inference edge로만 확장합니다. 서비스 역할에 OpenStack `admin`·`manager` 권한을 연결할 수 없습니다. 프로젝트 소유권 자체도 서비스 사용 권한이 아닙니다.
- **명시적 이전** — 기존 DB 관리자 기록의 이전은 시스템 관리자가 대상 소유자를 지정해 실행합니다. 조회·로그인·프로젝트 전환이 이를 자동 수행하지 않습니다.
- 프로젝트 멤버·개인 MCP token·OAuth grant·발급 직후 secret은 현재 auth/project 경계를 사용합니다. 프로젝트 전환 뒤 이전 행·액션·feedback과 늦은 결과를 사용하지 않습니다. 도메인 IAM의 초대 inventory는 project-only 목록이 아니라 현재 working domain 전체 목록이며 동일한 user/domain 경계를 유지합니다.

### 도메인 및 현재 프로젝트 경계

일반 지정 프로젝트 경로는 native 프로젝트의 `domain_id`가 세션의 **working `domain_id`**와 같고 enabled인지 확인합니다. identity domain으로 작업 대상을 대체하지 않습니다. 멤버·assignable-role·eligible-user·ownership 조회 및 멤버 변경은 일반 owner/admin의 **현재 프로젝트**에서만 가능합니다. 현재 Default manager는 선택 프로젝트가 없어도 같은 working domain의 프로젝트를 관리할 수 있습니다. 시스템 관리자라는 이유만으로 이 관리 경계를 우회하지 않습니다. 경계 위반·비활성 프로젝트는 `403`, native 대상 부재는 `404`, directory/graph 조회 불가는 `503`입니다.

생성·capabilities·creators는 선택적 `domain_id`로 다른 도메인을 명시할 수 있지만 해당 ID에 대한 현재 가입/manager/creator 권한을 다시 검증합니다. 생략하면 working domain을 사용하며 ID 대신 display name을 보내는 계약이 아닙니다. 이 호출은 세션을 전환하지 않습니다. 별도 system-admin settlement 경로만 명시한 target domain의 journal을 처리합니다.

멤버 대상은 native home-domain 사용자뿐 아니라 현재 해당 도메인에 실제 가입한 외부 identity 사용자도 포함합니다. 외부 identity의 `domain_id`는 원래 home ID 그대로이며 credential/profile 관리 권한을 뜻하지 않습니다. 역할 추가·교체와 ownership transfer는 enabled user 및 현재 도메인 가입을 재확인합니다. remove는 기존 유효 멤버의 관리 가능한 직접 grant만 제거합니다.

`/projects/{project_id}/permissions`는 같은 working domain의 다른 프로젝트를 조회할 때 일반 호출자의 native rescope 접근을 확인합니다. 이 조회에만 verified system admin의 rescope 예외가 있으며 도메인 경계는 그대로 적용됩니다. 도메인 관리 권한과 project `is_owner`/`is_manager`는 다릅니다. 도메인 IAM의 `/api/v1/iam/projects/...`도 같은 소유권 전용 변경 정책을 사용하며 generic owner 편집을 허용하지 않습니다.

### 서비스 등급과 명시적 운영 cutover

일반 사용자에게 `member`만 있다는 이유로 네 서비스를 허용하지 않습니다. 시스템 관리자가 [역할 프리셋](admin.md#역할-관리-roles)을 미리보고 명시적으로 적용한 뒤, 프로젝트 owner/admin이 필요한 서비스 부모 또는 세부 역할 ID를 부여합니다. 기존 core/project ID·할당은 교체하지 않으며 GET/login/startup은 역할/edge/manager 이전을 실행하지 않습니다. Native 서비스 directory credential은 현재 enabled user/project, 전역 역할 metadata, inference graph와 유효 할당을 읽을 수 있어야 합니다. 읽기 실패 시 권한을 넓히거나 tenant `admin`/`manager`를 부여하는 fallback은 없습니다.

Waygate의 `waygate-inventory_reader`는 비밀 없는 metadata, `waygate-connect_user`는 본인에게 할당된 enabled client `.conf`/QR만 허용합니다. `waygate-clients_editor`와 `waygate-gateways_editor`는 각각 생성·편집, `waygate-clients_admin`과 `waygate-gateways_admin`은 삭제/폐기, `waygate-routing_admin`은 네트워크 연결·보안 routing 액션입니다. Export/import는 client-admin과 routing-admin을 함께 요구하며 다른 사용자의 할당된 private profiles를 export하지 않습니다. Owner가 미지정인 legacy client는 connect-only 사용자에게 공개하지 않고 editor/admin이 명시적으로 한 번 소유자를 지정합니다. 플랫폼 resource policy는 verified system-admin 전용입니다.

다른 서비스의 독립 leaf·credential 경계는 [Lumen](chat.md#lumen-서비스-세부-권한), [Drover](k3s.md#drover-서비스-권한과-자격-등급), [Palimpsest](../palimpsest.md#프로젝트-package-서비스-등급)를 따릅니다. Runtime은 실제 현재 graph만 읽으므로 부모를 유지한 채 leaf edge를 제거해도 해당 권한이 회수됩니다.




---

## 엔드포인트 목록

### 프로젝트와 역할 관리

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/projects` | 대상 도메인 manager 또는 creator | 생성자 한 명의 직접 owner를 설정하고 활성화; `201` |
| `GET` | `/api/v1/projects/capabilities` | 대상 도메인 가입 사용자 | `?domain_id=...`; 현재 생성 가능 여부 |
| `GET` | `/api/v1/projects/creators` | 대상 도메인 manager | `?domain_id=...`; creator 위임 목록 |
| `PUT` | `/api/v1/projects/creators/{user_id}` | 대상 도메인 manager | `{enabled,domain_id?}`; 직접 creator grant 위임/회수 |
| `GET` | `/api/v1/projects/current/permissions` | 필요 | 현재 프로젝트 역할 및 실효 권한 |
| `GET` | `/api/v1/projects/{project_id}/permissions` | 필요 | 같은 working domain 프로젝트 역할 및 실효 권한 |
| `GET` | `/api/v1/projects/{project_id}/members` | 도메인 manager 또는 현재 프로젝트 owner/admin | 직접·유효·그룹·상속 멤버 |
| `GET` | `/api/v1/projects/{project_id}/assignable-roles` | 동일 | 안전한 역할 ID 카탈로그; owner 제외 |
| `GET` | `/api/v1/projects/{project_id}/eligible-users` | 동일 | enabled home/joined 사용자 목록 |
| `PUT` | `/api/v1/projects/{project_id}/members/{user_id}/roles` | 동일, 등급 ceiling 적용 | `{role_ids:[...]}`; 관리 가능한 직접 역할 교체 |
| `DELETE` | `/api/v1/projects/{project_id}/members/{user_id}` | 동일, 등급 ceiling 적용 | 직접 역할만 제거; `200` |
| `GET` | `/api/v1/projects/{project_id}/ownership` | 도메인 manager 또는 현재 프로젝트 owner/admin | native 소유권·durable operation·액션 가능 여부 |
| `POST` | `/api/v1/projects/{project_id}/ownership-transfer` | 도메인 manager 또는 현재 sole owner | `{user_id}`; 명시적 소유권 이전 |
| `POST` | `/api/v1/projects/{project_id}/ownership-transfer/reconcile` | 현재 verified `system:all` admin | `{operation_id,domain_id?,native_calls_settled:true}`; 수동 settlement |
| `GET` | `/api/v1/projects/{project_id}/deletion-check` | 도메인 manager 또는 creator이면서 sole owner | 자원·child 프로젝트 삭제 안전성 조회 |
| `DELETE` | `/api/v1/projects/{project_id}` | 동일 | 재검사 후 빈 프로젝트만 삭제; `204` |
| `POST` | `/api/v1/projects/{project_id}/members/migrate-legacy-managers` | verified system admin 및 프로젝트 관리 경계 충족 | `{owner_user_id}`; 명시적 기존 DB 관리자 이전 |

---

## GET /api/v1/projects/current/permissions

현재 활성 프로젝트의 `is_owner`, `is_manager`, `service_permissions`와 OpenStack 읽기·쓰기 권한을 조회합니다. UI는 현재 `service_permissions`의 정확한 세부 권한을 사용하며 `can_write`로 서비스 권한을 추측하지 않습니다. 확인 중·장애·프로젝트 전환 중에는 액션을 비활성화합니다.

일반 사용자 응답의 `roles`는 표시용입니다. 시스템 전용 `admin`·`manager` 및 이들을 상속하는 사용자 정의 역할 이름을 숨기며, 분류할 수 없는 사용자 정의 이름도 노출하지 않습니다. 원래 검증된 역할로 계산한 `can_write`를 전달하므로 이름이 숨겨져도 기존 프로젝트 쓰기 권한은 사라지지 않습니다. Login·refresh·프로젝트 전환 응답과 `/auth/me`도 같은 `roles`/`can_write` 계약을 사용합니다. 서버 서비스 authorization은 이 표시용 배열이나 JWT의 과거 부모 역할이 아니라 현재 검증한 전역 역할 ID·유효 할당·DAG와 프로젝트 소유권을 사용합니다. 이 permissions 응답의 `is_manager`는 현재 프로젝트 owner/admin **또는 system admin**이며 DB manager를 의미하지 않습니다. 이 값만으로 lifecycle·membership endpoint 허용 여부를 추측하지 않습니다. 현재 프로젝트가 없으면 `403`입니다.

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

특정 enabled 프로젝트에 대한 호출자의 역할 및 실효 권한을 조회합니다. 먼저 프로젝트의 native `domain_id`가 현재 **working domain**과 같은지 검증하며 시스템 관리자도 예외가 아닙니다. 일반 호출자의 다른 프로젝트는 Keystone rescope 접근 검증을 통과해야 합니다. `project_id=current`는 현재 프로젝트 권한을 반환합니다. 응답 형태는 current/permissions와 같고 `project_id`는 조회 대상을 나타냅니다. 경계·rescope 거부는 `403`, 대상 부재는 `404`, native 권한 조회 불가는 `503`입니다.

---

## POST /api/v1/projects

대상 도메인의 현재 manager 또는 native domain-scoped `project_creator`가 프로젝트를 생성합니다. `domain_id` 생략 시 working domain을 사용하고 명시 시 해당 도메인 가입과 생성 권한을 별도로 검증합니다. 시스템 관리자/프로젝트 owner/admin 권한만으로 생성할 수 없습니다. 이름은 앞뒤 공백을 제거하며 대소문자 무관 `Default`는 예약되어 있습니다. 생성은 세션의 working domain/project를 자동 전환하지 않습니다.

### 요청 본문

```json
{
  "name": "string (필수)",
  "description": "string (선택, 기본값 빈 문자열)",
  "domain_id": "target-domain-id (선택, 기본값 working domain)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 앞뒤 공백 제거 후 비어 있으면 `422`; `Default`는 `409` |
| `description` | string | 아니오 | 기본값 `""` |
| `domain_id` | string 또는 null | 아니오 | canonical target ID; 문자열은 길이 1 이상; 생략/null이면 working domain |

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
| `403` | 대상 도메인 가입/생성 권한 없음·회수됨, domain 경계 위반 또는 비활성 domain |
| `404` | 대상 도메인 부재 |
| `409` | 예약 이름 `Default`, native 충돌, 안전한 project role preset/hierarchy 미설정 또는 소유권 충돌 |
| `422` | 이름 누락·공백만인 이름·잘못된 본문/domain ID |
| `503` | directory/graph/SQL journal/quota 또는 native 생성·소유권·활성화 readback 불가 |

서버는 disabled 생성 → 직접 owner journal/grant 및 유일성 확인 → manager projection → quota defaults → 생성 권한 재확인 → enabled 활성화/readback 순서로 처리합니다. 중간 실패 시 불확실한 프로젝트를 자동 삭제하지 않습니다. disabled 프로젝트나 불확실한 native 결과는 관리자가 inventory/journal을 확인해 명시적으로 복구해야 하며 같은 create를 맹목적으로 재실행하지 않습니다.

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
      "domain_id": "identity-home-domain-id",
      "identity_read_only": false,
      "is_manager": true,
      "is_owner": false,
      "roles": ["project_admin", "project_member", "member", "project_reader", "reader"],
      "direct_role_ids": ["project-admin-role-id"],
      "effective_role_ids": ["project-admin-role-id", "project-member-role-id", "native-member-role-id", "project-reader-role-id", "native-reader-role-id"],
      "external_role_ids": [],
      "source": "direct"
    },
    {
      "user_id": "joined-user-id",
      "username": "joined-user",
      "email": "",
      "domain_id": "other-identity-domain-id",
      "identity_read_only": true,
      "is_manager": false,
      "is_owner": false,
      "roles": ["project_reader", "reader"],
      "direct_role_ids": [],
      "effective_role_ids": ["project-reader-role-id", "native-reader-role-id"],
      "external_role_ids": ["project-reader-role-id", "native-reader-role-id"],
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
| `domain_id`, `identity_read_only` | native home identity domain과 working domain 불일치 여부; 가입자의 원래 identity를 변경하지 않음 |

콘솔의 **역할 편집**에서는 먼저 서버 카탈로그의 권한 영역을 선택한 뒤 그 영역의 등급·세부 역할만 수정합니다. Tablet/desktop은 좌측 영역 목록, mobile은 영역 선택 상자를 사용합니다. 영역별 직접 선택·상속 개수는 검색 여부와 무관하게 전체 영역을 기준으로 표시합니다. 이름·ID·설명 검색은 모든 영역에서 수행하며 선택 영역에 결과가 없으면 일치하는 영역을 임시 표시하고, 검색을 지우면 원래 영역으로 돌아갑니다. 다른 영역이나 검색 뒤에 숨은 직접 선택·기존 카탈로그 밖 ID도 보존합니다. 현재 유효 역할은 접힌 조회 snapshot이며 저장 payload에는 `direct_role_ids`에 해당하는 선택 ID만 전달하고 그룹·도메인 상속을 직접 할당으로 복사하지 않습니다. 제목·검색·취소·저장은 목록 스크롤과 분리됩니다.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `403` | working-domain/current-project 경계 위반, 비활성 프로젝트 또는 관리 권한 없음 |
| `404` | native 프로젝트/사용자/그룹 부재 |
| `503` | 현재 멤버십·역할 카탈로그·provenance 조회 실패 |

---


## 역할 교체·제거와 기존 관리자 이전

`PUT /projects/{project_id}/members/{user_id}/roles`는 `{ "role_ids": ["exact-role-id"] }`를 받으며 응답 `200`은 갱신된 단일 member 객체입니다. Enabled home/joined 사용자를 대상으로 아직 프로젝트 멤버가 아니어도 허용 역할을 직접 부여할 수 있습니다. 정확한 안전한 전역 프로젝트/서비스 ID만 추가할 수 있고 기존 편집 불가 직접 ID는 payload에 보존할 수 있지만 추가/제거할 수 없습니다. 중복·안전 카탈로그 밖 신규 ID는 `422`, admin의 owner/admin 변경이나 다른 owner 편집은 `403`, owner-bearing 직접 grant의 변경은 owner/도메인 manager에게도 `409`(`Use explicit project ownership transfer`)입니다. `project_owner`를 generic 역할 선택으로 추가하거나 소유자를 제거하지 않습니다.

`DELETE /members/{user_id}`는 같은 정책으로 관리 가능한 직접 역할만 제거하고 `200 {"status":"removed","member":{...}}`를 반환합니다. 유효 멤버가 아니면 `404`이고, 직접 제거할 수 없는 group/inherited grant는 유지됩니다. Default의 필수 직접 `project_reader` baseline도 유지되므로 성공이 모든 유효 멤버십 제거를 뜻하지 않습니다. Native 경계·provider 오류는 `403/404/409/422/503`으로 전파될 수 있습니다.

멤버 응답은 `direct_role_ids`(현재 직접 할당), `effective_role_ids`(모든 유효 할당의 현재 ID 그래프 확장), `external_role_ids`(group/domain inherited 할당만 같은 그래프로 확장)를 분리합니다. `external_role_ids`는 merged effective 목록에서 직접 부모의 descendant를 빼서 추정하지 않습니다. 같은 하위 역할이 직접 부모와 그룹·도메인 양쪽에서 부여된 경우에도 부모 제거 후 외부 상속은 남아 checked/read-only로 표시됩니다. 이 provenance projection은 조회 응답만 보완하며 실제 Keystone 할당·인가·DB schema를 변경하지 않습니다.

`assignable-roles`의 각 role은 `implied_role_ids`(직접 연결)와 `inherited_role_ids`(검증된 현재 ID 그래프의 전체 descendant)를 제공합니다. 브라우저는 직접 선택한 부모의 descendant를 자동으로 체크·비활성화하고 선택을 해제하면 다시 계산합니다. 공유 부모의 상속, 기존 명시적 direct child, 편집 범위 밖의 group/domain inheritance는 유지합니다. 이름·ID·설명의 대소문자 무관 검색은 숨겨진 선택을 지우지 않으며 저장 요청에는 direct ID만 포함합니다. 이 UI projection은 새로운 Keystone grant를 만들거나 기존 direct child를 자동 삭제하지 않습니다.

기존 `/managers/{user_id}` 승격·해제 경로는 제거했습니다. DB manager 행은 조회 권한이 아닙니다. 시스템 관리자의 `POST /projects/{project_id}/members/migrate-legacy-managers`만 `{ "owner_user_id": "chosen-user-id" }`를 받아 명시한 소유자와 기존 대상자를 안전한 역할 계층으로 이전하고 DB 기록을 정리합니다. 이 legacy 경로는 현재 `_domain_access` 경계도 충족해야 하며 모든 대상의 native home domain이 working domain과 같고 기존 유효 프로젝트 멤버여야 합니다. 기존 소유권은 missing이거나 지정한 한 명의 unique owner여야 하고 unresolved journal·다른 owner/conflict·남은 legacy 행 부재는 `409`입니다. 소유자 이외의 이전 대상에게는 `project_admin`을 부여하며 유일성 확인 뒤에만 DB 행을 지웁니다.

성공 `200`은 `{project_id,owner_user_id,migrated_user_ids,deleted_legacy_rows}`입니다. 호출 전에 현재 역할 카탈로그·할당을 검토하고 실패하면 native/SQL 결과를 확인한 뒤 명시적으로 복구합니다. 조회·로그인·startup이 이 이전이나 preset 적용을 실행하지 않습니다.

---

## 생성 capability와 creator 위임

### GET /api/v1/projects/capabilities

선택적 query `domain_id`(길이 1 이상, 생략 시 working domain)를 받습니다. 해당 도메인의 현재 가입과 enabled identity/domain을 검증한 다음 Default manager 또는 정확한 domain-scoped native role-ID DAG의 `project_creator` 유효 여부를 조회합니다. 프로젝트 scope의 같은 이름 grant나 JWT role 이름은 capability가 아닙니다.

응답 `200`:

```json
{"domain_id":"domain-id","can_create_project":true}
```

가입 사용자에게 creator preset/grant가 없으면 `false`이며 login/startup에서 생성하거나 부여하지 않습니다. 가입 거부·비활성 domain은 `403`, domain 부재는 `404`, query 오류는 `422`, ambiguous role binding/directory/graph 장애는 `503`입니다.

### GET /api/v1/projects/creators

같은 선택적 query를 사용하며 **대상 도메인 manager만** 조회합니다. `200` 응답은 다음 형태입니다.

```json
{
  "domain_id": "domain-id",
  "role": {"id":"creator-role-id","name":"project_creator"},
  "users": [
    {
      "id":"joined-user-id",
      "name":"joined-user",
      "email":"user@example.com",
      "domain_id":"identity-home-domain-id",
      "enabled":true,
      "source":"direct",
      "direct":true
    }
  ]
}
```

`role`은 preset 미설정 시 `null`이고 `users`는 빈 배열입니다. 목록은 manager 전체 목록이 아니라 유효 creator grant 사용자 목록입니다. `source`는 정확한 직접 creator grant가 있으면 `direct`, 그 외 현재 domain-scope graph/group 경유이면 `inherited`이며 `direct` boolean으로 직접 회수 가능 여부를 구분합니다. 여기서 `inherited` 표시는 project에 상속되는 domain grant를 creator 권위로 인정한다는 뜻이 아닙니다. Home-domain ID가 다른 가입 사용자도 표시합니다.

### PUT /api/v1/projects/creators/{user_id}

```json
{"domain_id":"target-domain-id","enabled":true}
```

`enabled`는 **필수 strict boolean**입니다. `domain_id`는 선택적 nullable 문자열(길이 1 이상)이며 생략/null이면 working domain입니다. 도메인 manager가 enabled home/joined 사용자에게 정확한 domain-scoped 직접 `project_creator`를 부여하거나 회수합니다. Graph lease 안에서 권한·preset·가입을 확인하고 native 직접 grant readback과 session/cache invalidation을 수행합니다. 성공 `200`은 GET creators와 같은 갱신된 inventory입니다. `false`는 해당 직접 grant만 회수하므로 다른 유효 경로나 manager의 생성 권한까지 없앤다는 보장은 없습니다.

오류: `401` disabled 대상 identity(`assert_membership`의 native active-user 검사 포함) 또는 무효 세션, `403` manager/가입/활성 domain 조건 실패, `404` native domain/user 부재, `409` 명시적 administrator creator preset setup 필요 또는 native 충돌, `422` 잘못된 필드/boolean, `503` graph/directory/mutation/readback 불가. Preset 설치는 별도의 시스템 관리자 작업이며 위임 endpoint가 자동 적용하지 않습니다.

---

## GET /api/v1/projects/{project_id}/assignable-roles

도메인 manager 또는 현재 프로젝트 owner/admin이 조회하며 본문은 없습니다. `200` 응답의 정확한 최상위 필드는 `{roles,is_owner,can_manage_owners}`입니다. 각 role은 현재 catalog의 `id`, `name`, `description`, `domain_id`, `system_only`, `implied_role_ids`, `inherited_role_ids`와 관리 분류 `area`, `grade`를 제공합니다. `is_owner`는 호출자의 유효 owner 여부이고 `can_manage_owners`는 **항상 false**입니다.

`project_owner`는 모든 호출자의 assignable 목록에서 제외합니다. `project_admin`은 실제 owner 또는 도메인 manager에게만 포함됩니다. `project_creator`와 native `admin`/`manager`를 이 프로젝트 role editor로 위임하지 않습니다. 안전한 core/project/service ceiling과 custom descendant 정책은 위 권한 모델을 따릅니다. 오류는 `403` scope/관리 권한 거부, `404` native 대상 부재, `503` catalog/graph/assignment 불가입니다.

콘솔의 역할 선택지는 이 서버-filtered `roles` 목록을 그대로 따릅니다. `can_manage_owners=false`는 소유권이 별도 transfer 경로라는 뜻이며 `project_admin` checkbox를 막는 권한 flag가 아닙니다. 실제 `is_owner`로 owner 대상 편집/관리자 멤버 관리 여부를 구분하고, 모든 직접 역할 저장은 서버가 현재 scope·역할 그래프·owner 및 필수 Default reader를 다시 검증합니다.

## GET /api/v1/projects/{project_id}/eligible-users

같은 관리 경계로 현재 working domain의 enabled home/joined directory를 반환합니다. 본문·검색 query·pagination 계약은 없으며, 현재 프로젝트에 아직 직접 할당이 없는 사용자도 포함합니다. `200`은 wrapper 없는 배열입니다.

```json
[
  {"id":"joined-user-id","name":"joined-user","email":"user@example.com","domain_id":"identity-home-domain-id","enabled":true}
]
```

위 다섯 필드만 반환하며 password/provider/credential/protected-account inventory가 아닙니다. 외부 사용자는 현재 enabled 프로젝트의 실제 native membership provenance로 가입을 확인하고 manager access용 private projection만으로 외부 가입을 만들지 않습니다. 오류는 `403` scope/관리 권한 거부, `404` native 대상 부재, `503` directory/provenance/graph 불가입니다. 목록은 snapshot이며 쓰기 시점에 대상 가입/활성을 다시 검사합니다.

### 프로젝트 이메일 초대의 현재 경계

현재 프로젝트 router에는 `/projects/{project_id}/invitations` 생성·목록·취소 endpoint가 없습니다. 프로젝트 owner/admin의 joined-user 추가는 위 eligible-users와 `PUT .../members/{user_id}/roles`를 사용합니다. **Owner/admin 역할만으로 이메일 초대를 발급할 수는 없습니다.**

현재 지원되는 이메일 경로는 도메인 manager 전용 `POST /api/v1/iam/invitations`(`201`)이며 요청은 `{email,project_id?,role_ids?}`입니다. `email`은 길이 3–255 문자열, `project_id`는 nullable 길이 1–64 문자열, `role_ids`는 기본 `[]`이며 최대 256개입니다. 알 수 없는 필드는 `422`입니다. 프로젝트 없이 domain 초대가 가능하고 그때 추가 role IDs는 허용하지 않습니다. 프로젝트를 지정하면 중복 없는 안전한 role IDs와 명시적 project membership grade가 필요하며 owner는 제외됩니다. Project/roles 권한은 현재 manager ceiling으로 검증합니다. 발급은 `10/minute` 제한을 받습니다.

성공 응답은 IAM enrollment DTO(`id,domain_id,project_id,project_name,email,role_ids,kind,user_id,identity_domain_id,personal_domain_name,native_writes_settled,recovery_required,status,expires_at,created_at,accepted_at`)이며 raw token을 반환하지 않습니다. `GET /api/v1/iam/invitations`는 `{items:[...]}`, `DELETE /api/v1/iam/invitations/{invitation_id}`는 `204`입니다. Inventory는 working domain 전체입니다. 권한/정책 거부는 `403`, native 대상 부재는 `404`, lifecycle 충돌은 `409`, 본문/role 선택 오류는 `422`, rate limit은 `429`, email/native/storage 불가는 `503`입니다.

수락은 `/api/v1/auth/invitations/{token}`, `/api/v1/auth/invitations/accept`, 인증된 `/api/v1/auth/invitations/accept-existing`를 사용합니다. 기존 계정 수락은 immutable identity/password를 변경하지 않고 invited working domain의 Default reader 및 선택한 프로젝트 역할을 **additive**로 부여합니다. New-human 수락의 personal domain 및 일회용 durable enrollment/recovery 계약은 IAM/auth 문서를 따릅니다. 프로젝트 owner/admin의 별도 이메일 초대는 proposal 요구이지만 현재 이 프로젝트 API의 구현 계약이 아닙니다.

---

## 유일 소유권 조회·이전

### GET /api/v1/projects/{project_id}/ownership

도메인 manager 또는 현재 프로젝트 owner/admin이 native raw provenance와 유효 owner를 대조합니다. `200` 응답:

```json
{
  "project_id":"project-id",
  "owner_user_id":"owner-user-id",
  "status":"unique",
  "owners":[{"user_id":"owner-user-id","name":"owner-name","source":"direct"}],
  "transfer_operation":null,
  "can_transfer":true,
  "can_delete":false
}
```

| 필드 | 계약 |
|------|------|
| `status` | `unique`: 정확한 직접 owner grant 하나; `missing`: owner-bearing source 없음; `conflict`: 복수 또는 group/inherited/custom owner-bearing source |
| `owner_user_id` | `unique`일 때만 사용자 ID, 그 외 `null` |
| `owners` | 모든 owner 사용자와 source `direct` 또는 `group_or_inherited`; 임의 owner 선택 없음 |
| `transfer_operation` | durable journal의 현재 행 또는 `null`; native 소유권의 대체 권위가 아님 |
| `can_transfer` | Default가 아니며 applying/unknown journal이 없고, unique owner의 본인/manager인 경우. Unresolved operation의 settled missing-owner 복구는 manager에게도 표시 가능 |
| `can_delete` | Default가 아니며 모든 journal이 completed이고, manager이거나 creator capability를 가진 sole owner인 경우. **자원 비어 있음의 증명이 아님** |

도메인 manager는 project owner가 아니어도 관리할 수 있습니다. 기존 missing/conflict를 이 GET이 자동 수정하지 않으며 group owner가 한 명이어도 `unique`로 취급하지 않습니다. 오류는 `403` scope/관리 권한 거부, `404` native 대상 부재, `409` role preset/hierarchy 미설정, `503` ownership provenance 불일치·graph/directory/journal 불가입니다.

### POST /api/v1/projects/{project_id}/ownership-transfer

요청은 `{ "user_id": "enabled-joined-user-id" }`(필수, 길이 1 이상)입니다. Target은 현재 프로젝트 멤버일 필요는 없지만 enabled 상태이고 working domain에 이미 가입해야 합니다. 일반 새 이전은 **현재 sole owner 또는 도메인 manager**만 허용합니다. Creator capability만으로 다른 프로젝트 소유권을 이전할 수 없습니다.

Graph lease 안에서 unique ownership·target eligibility·현재 권한을 재확인하고 durable SQL intent를 commit합니다. 기존 직접 owner를 revoke한 다음 target에게 grant하여 일시적으로 두 owner를 만들지 않습니다. 각 native dispatch 전에 stage를 저장하고 target의 unique ownership readback 후에만 completed로 기록합니다. 이전 owner에게 별도 admin/member 역할을 자동 부여하지 않으며 두 당사자의 세션·관련 cache를 invalidation합니다.

성공 `200`은 ownership 객체와 같고 `status:"unique"`, `owner_user_id`는 target, `transfer_operation.status:"completed"`, `stage:"verified"`입니다. 이 POST 응답의 `can_transfer`/`can_delete`는 호출자의 domain-manager 여부로 반환되므로 액션 표시를 갱신하려면 현재 scope에서 ownership GET을 다시 사용합니다.

| 상태 | 주요 실패 |
|------|-----------|
| `401` | 무효 세션 또는 target의 native disabled-identity membership 검사 실패 |
| `403` | working/current-project 경계, sole owner/manager 권한 또는 target 가입/활성 조건 실패 |
| `404` | 프로젝트/target 부재 |
| `409` | missing/conflict ownership, 동일 owner 선택, `project_ownership_native_operation_unresolved`, `project_ownership_recovery_target_mismatch`, settled recovery의 native conflict, role hierarchy 또는 native 충돌 |
| `422` | user ID 누락/빈 값, Default 이전(`domain_default_is_immutable`) |
| `503` | native/graph/readback/SQL journal 불가; 결과가 불확실할 수 있음 |

### Durable transfer journal과 수동 settlement

`project_ownership_transfers`는 프로젝트 ID당 현재 operation 한 행을 보존합니다. 새 완료 후 이전은 새 operation ID로 갱신하고 settled recovery는 같은 ID/당사자를 유지합니다. API DTO에는 `id,project_id,domain_id,from_user_id,to_user_id,status,stage`만 있고 credential이나 timestamp는 포함하지 않습니다.

- `status`: `applying`, `unknown`, `settled`, `completed`.
- `stage`: `prepared`, `revoke`, `grant`, `initial_grant`, `verified`, `native_outcome_unknown`, `reconciled`.
- Exception/timeout 뒤에는 `unknown` fence를 남깁니다. Crash로 남은 `applying`도 replay를 막습니다. 현재 GET에서 원하는 owner가 보이더라도 원래 native 요청이 멈췄다는 증명이 아닙니다.
- Applying/unknown 상태에서 새 transfer/replay는 `409`입니다. Completed 이외 journal은 삭제·managed project 활성화·관련 identity/domain lifecycle도 fence합니다. Settled 상태도 삭제 허용이 아닙니다.

`POST /api/v1/projects/{project_id}/ownership-transfer/reconcile`는 **현재 verified `system:all` admin만** 실행합니다. 도메인 manager/owner에게는 허용하지 않으며 native ownership grant/revoke를 수행하지 않습니다.

```json
{"operation_id":"journal-operation-id","domain_id":"target-domain-id","native_calls_settled":true}
```

`operation_id`는 필수 길이 1 이상, `domain_id`는 선택적 nullable 문자열(길이 1 이상, 생략/null이면 working domain), `native_calls_settled`는 필수 strict boolean이며 **true만 허용**합니다. 명시한 domain과 native project/journal domain을 대조합니다. 이 admin 경로는 target을 명시하므로 일반 working-domain project management 경로와 구분합니다.

운영자는 **기존 native 요청이 모두 더 이상 실행되지 않음**을 외부에서 확인한 뒤에만 true를 보내야 합니다. 서버는 native readback만으로 이를 추론하지 않습니다. Settlement는 현재 native 상태가 unique이면 journal을 `completed/reconciled`, 그 외 일반 이전은 `settled/reconciled`로 기록합니다. 초기 grant(`from_user_id == to_user_id`)가 missing이면 completed로 정리할 수도 있습니다. 따라서 completed/reconciled가 항상 최초 target으로 이전 성공했다는 뜻은 아닙니다. 실제 `status/owner_user_id`를 함께 확인합니다.

응답 `200`은 현재 ownership state와 operation이며 두 action flag는 모두 false입니다. `settled` 일반 이전은 동일 `user_id`의 transfer endpoint로만 재개할 수 있고 원래 from-user 또는 manager가 실행합니다. Conflict는 자동 revoke/승자 선택하지 않으며 명시적 native 정리가 필요합니다. Completed 뒤에는 현재 소유권과 권한으로 새로운 이전 여부를 다시 판단합니다.

오류: `401` invalid native admin session, `403` live system authority 없음 또는 target-domain 불일치, `404` project/operation/domain 매칭 실패, `422` 필드 오류 또는 settlement 확인 false, `503` authority/native/journal 불가. Journal 공개 오류 코드는 `project_ownership_storage_unavailable`, `project_ownership_journal_unavailable`, `project_ownership_journal_changed`입니다. 그 외 일반 `5xx` 내부 설명은 중앙 sanitizer가 공개하지 않을 수 있습니다.

---

## 빈 프로젝트 안전 삭제

### GET /api/v1/projects/{project_id}/deletion-check

삭제 권한은 **현재 도메인 manager** 또는 **현재 creator capability + unique sole ownership을 모두 가진 사용자**에게 있습니다. 단순 owner/admin, creator만인 사용자, system admin만인 사용자는 허용하지 않습니다. Default와 unresolved journal은 삭제할 수 없습니다. 이 endpoint는 자원을 삭제하지 않습니다.

성공 `200`의 필드는 다음과 같습니다. 아래 resources는 개별 entry 형태 예시이며 실제 응답에는 전체 검사 종류가 포함됩니다.

```json
{
  "project_id":"project-id",
  "checked_at":"2026-10-16T00:00:00+00:00",
  "can_delete":false,
  "resources":[
    {"kind":"child_projects","service":"identity","status":"ok","count":1,"samples":[{"id":"child-id"}],"reason":null}
  ]
}
```

각 entry는 `{kind,service,status,count,samples,reason}`입니다. `status`는 `ok`, `skipped`, `unavailable`이고, `count`는 검증된 `ok`에서만 숫자이며 나머지는 `null`입니다. `samples`는 최대 다섯 개의 비밀 없는 ID 및 가능한 name/status로 전체 count를 대신하지 않습니다. `can_delete`는 모든 종류가 `ok/count:0` 또는 명시적 `skipped`일 때만 true입니다.

검사 범위:

- Compute: instances, server groups.
- Volume: volumes, snapshots, backups.
- Network: networks, subnets, routers, ports, floating IPs, security groups. Native 자동 `default` security group 한 개만 제외하고 중복 동명 group은 unknown으로 차단합니다.
- Image: hidden/non-hidden을 포함한 소유 images.
- Catalog에 존재하는 선택 서비스: load balancers, shares/share snapshots/share networks/security services, object containers, secrets/secret containers/orders, database instances/backups/configurations, containers, clusters/cluster templates, hidden/nested stacks.
- Identity: `parent=project_id` 전체 child projects. Disabled child도 존재하면 차단합니다. Hierarchy 결과의 ID 중복/누락/parent 불일치 또는 unsupported/실패는 `unavailable`, `count:null`, `reason:"project_hierarchy_unavailable"`입니다.

선택 서비스가 확실히 catalog에 없을 때만 `skipped/service_not_present`입니다. Native admin authority, service catalog, 전체 pagination, owner attribution 또는 정확한 project/account scope를 검증할 수 없으면 `unavailable`로 둡니다. `admin_authority_unverified`, `service_catalog_unavailable`, `resource_ownership_unverified`, `resource_check_failed` 등의 reason은 빈 자원 수가 아닙니다. 한 서비스 실패를 숨기고 다른 서비스의 0으로 삭제를 허용하지 않습니다.

자원 존재 또는 inventory 일부 unavailable도 조회 자체는 `200/can_delete:false`로 표현할 수 있습니다. 권한·Default·unresolved-operation gate는 `403`, native 대상 부재는 `404`, role/journal 충돌은 `409`, 전체 inventory를 시작할 수 없는 provider/graph/storage 실패는 `503`입니다. Ownership GET의 `can_delete`와 이 resource-proof `can_delete`를 혼동하지 않습니다.

### DELETE /api/v1/projects/{project_id}

본문·force 옵션은 없습니다. Graph lease 안에서 deletion-check를 **다시 실행**하고 Default와 현재 actor authority를 native delete 직전에 다시 확인합니다. 이전 GET의 성공을 삭제 승인 token으로 사용하지 않습니다. 성공은 본문 없는 `204 No Content`이며 authority/project 목록 cache를 invalidation합니다.

| 상태 | 의미 |
|------|------|
| `403` | 삭제 권한 없음/회수됨, working/current-project 경계 위반, 비활성 프로젝트, Default 또는 unresolved operation으로 ownership gate 차단 |
| `404` | native 프로젝트 부재 |
| `409` | 소유 자원 또는 child projects 존재; role/journal/native 충돌 |
| `503` | 하나라도 resource inventory가 unavailable이거나 provider/graph/storage 검증 불가; 안전성 검사 실패 시 native delete를 호출하지 않음 |

프로젝트 소유 자원·child project를 강제로 정리하거나 재귀 삭제하지 않습니다. Native delete 호출 뒤 timeout/실패는 결과를 inventory로 확인하고 복구해야 하며 맹목적 재시도를 하지 않습니다.
