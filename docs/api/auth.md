---
title: 인증 (Auth)
parent: API 레퍼런스
nav_order: 10
---

# 인증 (Auth) API

> 태그: `auth`
> 기본 경로: `/api/v1/auth`

로그인, JWT 토큰 발급·회전, 세션 관리, 프로젝트 스코프 전환을 제공합니다.
GitLab OIDC(federated) 로그인 콜백도 같은 라우터에 마운트됩니다.

---

## 인증 방식

Afterglow는 **JWT(access + refresh) 쌍** 기반 인증을 사용합니다.
로그인 시 서버는 Keystone 토큰을 Redis 세션에 보관하고, 클라이언트에는
access JWT와 refresh JWT를 발급합니다. 이후 인증이 필요한 모든 요청은 아래 헤더를
포함해야 합니다.

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | 예 | `Bearer <access_jwt>` 형식. 로그인 응답의 `token` 값 |
| `X-Project-Id` | 아니오 | 요청을 처리할 프로젝트 UUID. 생략 시 JWT에 담긴 프로젝트로 처리. JWT의 프로젝트와 다른 값을 주면 서버가 Keystone rescope를 수행(프로젝트 전환) |

> access JWT는 내부적으로 refresh 세션(`rjti`)을 가리키며, 서버는 매 요청마다
> Redis 세션에 저장된 Keystone 토큰을 라이브 검증(60초 캐시)합니다. 권한(roles,
> is_system_admin)은 JWT payload가 아니라 항상 Keystone 검증 결과를 사용합니다.

JWT 검증의 algorithm allow-list는 access/refresh 모두 `HS256` 하나이며 HMAC과 asymmetric algorithm을 섞지 않는다. Backend는 [PEM guard bypass](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-ffc3-869f-jxw9)와 [pre-verification payload recursion](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)이 수정된 PyJWT `>=2.15.0`을 요구한다. Upstream 취약점의 mixed-algorithm/raw-PEM·unsigned payload 조건이 현재 브라우저 JWT 경로에 없더라도 vulnerable library로 downgrade하지 않는다.

OIDC·서비스 HTTP client의 TLS verify/설정 CA·hostname 검증은 유지한다. Backend는 [IDNA 2003 hostname confusion](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6)이 수정된 AnyIO `>=4.14.2`를 요구한다. 이 의존성 갱신은 인증 방식·endpoint·계정 잠금/세션 정책을 변경하거나 인증서 검증을 끄지 않는다.

### 세션·토큰 수명 모델

- **access JWT** — 단기 토큰. 만료 시각은 응답의 `expires_at`.
- **refresh JWT** — Redis 세션(`session_store`)에 대응. Keystone 토큰, 프로젝트,
  로그인 출처 IP/기기 지문, 인증 방식이 함께 저장됩니다.
- **세션 타임아웃** — Keystone 토큰 수명과 별개로, Redis에 세션 시작 시간을 기록해
  `session_timeout_seconds`를 초과하면 401로 만료 처리합니다.
- **토큰 회전** — `POST /refresh`는 기존 refresh 세션을 즉시 삭제하고 새 쌍을
  발급합니다. 같은 refresh 토큰을 두 번 사용하면 두 번째 호출은 401입니다.

### 보안 제한 (참고)

- **로그인 실패 계정 잠금** — 반복 실패 시 일시 잠금(`login_guard`). Redis 장애 시에는
  가용성 우선으로 **잠금을 생략(fail-open)** 합니다(의도된 동작, `CLAUDE.md` §3 참조).
- **토큰 출처 바인딩** — access 토큰의 출처 IP/기기 지문이 최초 로그인과 불일치하면
  차단할 수 있습니다. 바인딩 검사 자체가 실패(Redis 장애 등)하면 **요청을 거부
  (fail-closed, 401)** 합니다.

---

## 엔드포인트 목록

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/auth/login` | 없음 | 사용자 이름/비밀번호로 JWT 발급 (10회/분) |
| `GET` | `/api/v1/auth/me` | 필요 | 현재 토큰의 사용자/프로젝트 정보 |
| `POST` | `/api/v1/auth/logout` | 필요 | 현재 세션 로그아웃 (refresh 세션 삭제 + Keystone revoke) |
| `POST` | `/api/v1/auth/refresh` | refresh 토큰 | access/refresh JWT 재발급 (회전, 30회/분) |
| `POST` | `/api/v1/auth/token/project` | 필요 | 다른 프로젝트로 스코프 전환 (새 토큰 쌍) |
| `POST` | `/api/v1/auth/logout-all` | 필요 | 현재 사용자의 모든 세션 폐기 |
| `GET` | `/api/v1/auth/sessions` | 필요 | 현재 사용자의 활성 세션 목록 |
| `DELETE` | `/api/v1/auth/sessions/{jti}` | 필요 | 개별 세션 삭제 (소유권 확인) |
| `GET` | `/api/v1/auth/groups` | 필요 | 현재 사용자가 속한 Keystone 그룹 목록 |
| `GET` | `/api/v1/auth/projects` | 필요 | 접근 가능한 프로젝트 목록 |
| `GET` | `/api/v1/auth/projects/recent` | 필요 | 최근 접근순 프로젝트 목록 |
| `GET` | `/api/v1/auth/gitlab/enabled` | 없음 | GitLab OIDC 활성화 여부 |
| `GET` | `/api/v1/auth/gitlab/authorize` | 없음 | GitLab OAuth2 인증 URL |
| `POST` | `/api/v1/auth/gitlab/callback` | 없음 | GitLab 콜백: code로 JWT 발급 (10회/분) |
| `GET/POST` | `/api/v1/auth/mcp-tokens` | 필요 | 현재 사용자·프로젝트의 개인 MCP 키 조회/발급 (MCP 활성화 필요) |
| `POST` | `/api/v1/auth/mcp-tokens/verify` | 필요·동일 사이트 | 본인 개인 키로 공개 MCP 초기화·도구 목록 확인 (6회/분) |
| `DELETE` | `/api/v1/auth/mcp-tokens/{id}` | 필요·동일 사이트 | 본인 키 회수 |

---

## 공통 스키마

### TokenResponse

로그인·리프레시·프로젝트 전환·GitLab 콜백이 공통으로 반환하는 스키마입니다.

```json
{
  "token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "user_id": "uuid-string",
  "username": "user-name",
  "expires_at": "2026-01-01T00:00:00+00:00",
  "roles": ["member", "reader"],
  "default_project_id": "uuid-string",
  "is_system_admin": false,
  "can_write": true,
  "auth_method": "password"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `token` | string | access JWT. `Authorization: Bearer` 헤더에 사용 |
| `refresh_token` | string\|null | refresh JWT. `POST /refresh`에 사용 |
| `project_id` | string | 스코프된 프로젝트 UUID |
| `project_name` | string | 프로젝트 이름 |
| `user_id` | string | 사용자 UUID |
| `username` | string | 사용자 이름 |
| `expires_at` | string | access JWT 만료 시각 (ISO 8601) |
| `roles` | array[string] | 표시용 프로젝트 역할 이름. 일반 사용자에게 `admin`·`manager` 및 이들을 상속하는 사용자 정의 역할은 노출하지 않음 |
| `default_project_id` | string | 사용자 기본 프로젝트 UUID (없으면 `""`) |
| `is_system_admin` | boolean | 시스템 관리자 여부 |
| `can_write` | boolean | 숨기기 전 검증된 역할로 계산한 프로젝트 쓰기 권한. 프론트엔드는 표시용 이름에서 이를 재추론하지 않음 |
| `auth_method` | string | `password` 또는 `federated` |

### UserInfo

```json
{
  "user_id": "uuid-string",
  "username": "user-name",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "roles": ["member", "reader"],
  "is_system_admin": false,
  "can_write": true,
  "auth_method": "password"
}
```

`roles`는 authorization 입력이 아니라 public projection입니다. 시스템 관리자는 전체 이름을 받으며, 일반 사용자의 분류 불가 사용자 정의 이름은 숨깁니다. 분류 cache에 새 외부 역할이 없으면 한 번 갱신하고 metadata 장애는 로그인·`/me`를 실패시키지 않습니다. 서버는 원래 Keystone 검증 결과와 별도의 프로젝트 소유권을 계속 검사하며, 이름 숨김이 실제 `can_write`를 바꾸지 않습니다.

### ProjectInfo

```json
{
  "id": "uuid-string",
  "name": "project-name",
  "description": "프로젝트 설명",
  "domain_id": "uuid-string",
  "domain_name": "Default",
  "enabled": true,
  "last_accessed_at": null
}
```

`last_accessed_at`은 `/projects/recent`에서만 채워집니다(그 외에는 `null`).

---

## POST /api/v1/auth/login

사용자 자격증명으로 Keystone에 인증하고 JWT 쌍을 발급합니다. 로그인 성공 직후
백그라운드로 대시보드 캐시를 프리워밍하고 최근 프로젝트 접근을 기록합니다.
비율 제한: **10회/분**.

### 요청 본문

```json
{
  "username": "string (필수)",
  "password": "string (필수)",
  "project_name": "string (선택)",
  "domain_name": "string (선택, 기본값: Default)"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `username` | string | 예 | OpenStack 사용자 이름 |
| `password` | string | 예 | OpenStack 비밀번호 |
| `project_name` | string | 아니오 | 스코프할 프로젝트 이름. 생략 시 기본 프로젝트 |
| `domain_name` | string | 아니오 | 사용자 도메인 이름 (기본값 `Default`) |

### 응답 (200 OK)

[TokenResponse](#tokenresponse) — `auth_method`는 `password`.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 인증 실패 (잘못된 자격증명) |
| `429` | 계정 잠금(반복 실패) 또는 비율 제한 초과 |

---

## GET /api/v1/auth/me

현재 access 토큰의 사용자와 프로젝트 정보를 반환합니다.

### 응답 (200 OK)

[UserInfo](#userinfo).

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |

---

## POST /api/v1/auth/logout

현재 세션을 로그아웃합니다. refresh 세션 삭제 + Keystone 토큰 revoke + 검증/세션
캐시 무효화를 수행합니다.

브라우저는 진행 중인 refresh 또는 서버 폐기 요청이 실패해도 로컬 로그아웃을 완료합니다. 서버 폐기 확인에 실패했다면 성공으로 숨기지 않고 이 기기에서만 로그아웃했음을 알립니다.

### 응답 (200 OK)

```json
{ "message": "로그아웃 완료" }
```

---

## POST /api/v1/auth/refresh

refresh JWT로 새 access/refresh JWT 쌍을 발급합니다(**토큰 회전**). 기존 refresh
JTI는 즉시 삭제되므로 같은 refresh 토큰으로 두 번 호출하면 두 번째는 401입니다.
비율 제한: **30회/분**. 이 엔드포인트는 Authorization 헤더가 아니라 본문의
refresh 토큰으로 인증합니다.

### 요청 본문

```json
{ "refresh_token": "string (필수)" }
```

### 응답 (200 OK)

[TokenResponse](#tokenresponse).

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않은 refresh 토큰 / 세션 만료 / 세션 차단(블랙리스트) |
| `429` | 갱신 요청 제한; 브라우저는 Retry-After cooldown을 적용 |
| `503` | Redis/Keystone 연결·검증 장애; 현재 요청은 거부하고 세션은 재시도를 위해 보존 |

Keystone가 token authentication에서 반환하는 `404 Failed to validate token`과 `404 Could not recognize Fernet token`은 무효 token으로 분류해 `401`로 변환합니다. 일반 endpoint/resource 404는 인증 무효를 확정하지 못하므로 `503`입니다. 브라우저는 background refresh의 401에도 인증을 정리해 로그인으로 이동하고, 503/네트워크 실패에는 재시도·로그아웃을 제공하는 지속적인 인증 복구 dialog를 표시합니다. 서비스의 일반 resource 오류는 이 전역 인증 상태로 승격하지 않습니다.

---

## POST /api/v1/auth/token/project

현재 토큰으로 접근 가능한 다른 프로젝트에 스코프된 새 토큰 쌍을 발급합니다(rescope).
프로젝트 전환 시 사용합니다.

### 요청 본문

```json
{ "project_id": "uuid-string (필수)" }
```

### 응답 (200 OK)

[TokenResponse](#tokenresponse).

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |
| `403` | 대상 프로젝트 접근 권한 없음 |

---

## POST /api/v1/auth/logout-all

현재 사용자의 **모든 세션**을 폐기합니다(Keystone 직접 폐기 포함). federated 사용자
포함. 현재 세션도 함께 폐기되므로 호출 후 재로그인이 필요합니다.

### 응답 (200 OK)

```json
{ "message": "모든 세션이 폐기되었습니다.", "revoked_count": 3 }
```

---

## GET /api/v1/auth/sessions

현재 사용자의 활성 세션 목록을 반환합니다. 출처 IP·기기·마지막 사용 정보가 포함되며,
`keystone_token` 등 민감 필드는 제거된 채 반환됩니다.

### 응답 (200 OK)

```json
{
  "sessions": [
    { "jti": "...", "origin_ip": "...", "device_type": "...", "os": "...", "last_seen_at": "..." }
  ],
  "count": 1
}
```

---

## DELETE /api/v1/auth/sessions/{jti}

개별 세션을 삭제합니다. **소유권 확인 필수** — 대상 `jti`가 현재 사용자의 세션이
아니면 404를 반환합니다(타인 세션 은닉). Keystone 토큰도 best-effort로 폐기됩니다.

### 응답 (200 OK)

```json
{ "message": "세션이 삭제되었습니다." }
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `404` | 현재 사용자의 세션이 아니거나 존재하지 않는 세션 |

---

## GET /api/v1/auth/groups

현재 사용자가 속한 Keystone 그룹 목록을 반환합니다. policy가 조회를 허용하지 않으면
빈 리스트를 반환합니다.

### 응답 (200 OK)

```json
[
  { "id": "uuid-string", "name": "group-name", "description": null, "domain_id": "uuid-string" }
]
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `500` | 그룹 목록 조회 실패 |

---

## GET /api/v1/auth/projects

현재 사용자가 접근 가능한 모든 프로젝트 목록을 반환합니다(2분 캐시).

### 응답 (200 OK)

[ProjectInfo](#projectinfo) 배열 (`last_accessed_at`은 `null`).

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `500` | 프로젝트 목록 조회 실패 |

---

## GET /api/v1/auth/projects/recent

최근 접근 순으로 정렬된 프로젝트 목록을 반환합니다. Redis에 기록된 접근 시각 기준으로
정렬하고 `last_accessed_at`을 채웁니다. 접근 기록이 없는 프로젝트는 이름순으로
뒤에 덧붙입니다.

### 응답 (200 OK)

[ProjectInfo](#projectinfo) 배열 (`last_accessed_at` 포함).

---

## GitLab OIDC (federated)

`config`에서 GitLab OIDC가 활성화된 경우에만 동작합니다. 비활성 시 `authorize`/
`callback`은 404를 반환합니다.

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/auth/gitlab/enabled` | `{ "enabled": bool }` — 프론트엔드 버튼 노출 판단 |
| `GET` | `/api/v1/auth/gitlab/authorize` | `{ "authorize_url": "..." }` — OAuth2 인증 URL |
| `POST` | `/api/v1/auth/gitlab/callback` | authorization code로 JWT 발급 (10회/분) |

### POST /api/v1/auth/gitlab/callback 요청 본문

```json
{ "code": "string (필수)", "state": "string (필수)" }
```

응답은 [TokenResponse](#tokenresponse) (`auth_method`는 `federated`). 인증 실패 시 401.

## MCP 프로젝트 리소스 생성·네트워크 연결

다음 세 도구는 개인 MCP와 Lumen 위임의 같은 canonical registry(`2026-10-11.2`)를 사용한다. 명시적으로 승인된 `manage`/`mcp:write` grant에만 노출·실행되며 `read` grant는 호출 이름을 직접 지정해도 거부한다. 선택적 `project_id`는 승인된 프로젝트만 지정할 수 있고 해당 프로젝트의 restricted application credential로 실행한다. 기본 Lumen 읽기 전용 권한은 확대하지 않는다.

| 도구 | 필수 입력 | 선택 입력·제한 | 접수 결과 |
|---|---|---|---|
| `afterglow_vm_create` | `name`, `image_id`, `flavor_id`, `network_id` | VM 이름 1–63자·영숫자로 시작·영숫자/`_`/`-`만 허용. `boot_volume_size_gb` 기본50·1–16384GiB, `key_name`, host 지정을 허용하지 않는 `availability_zone`, `delete_boot_volume_on_termination` 기본false | 안전한 server ID·이름·현재 status·timestamp와 `requested_action: "create"`; ACTIVE/guest readiness 보장 아님 |
| `afterglow_volume_create` | `name`, 정수 `size_gb` | 공백 아닌 이름 1–255자, 1–16384GiB, 선택 `availability_zone` | 빈 Cinder volume ID·이름·현재 status·size·timestamp와 `requested_action: "create"`; `creating`은 사용 가능 상태 아님 |
| `afterglow_vm_network_attach` | `server_id`, `network_id` | 대상 프로젝트의 ACTIVE/SHUTOFF server와 owned 또는 명시적으로 shared network만 허용. 기존 `port_id`·fixed IP·security group override는 받지 않음 | 검증된 server/network/new port ID·MAC과 `requested_action: "attach_network"`; guest 내부 설정·통신 성공 보장 아님 |

MCP 변경 호출은 `idempotency_key`를 함께 보내며 같은 key/arguments의 완료 결과는 재사용한다. Lumen `/api/v1/mcp/lumen/preview`는 리소스를 만들지 않고 `/execute`가 별도 key로 원장을 사용한다. 실행 직전에 grant·대상·리소스 상태와 SDK deadline을 다시 검증한다. 결과가 불확실하면 `unknown`으로 남기며 동일 grant/source/tool/arguments는 새 key로도 자동 재전송하지 않는다. 실제 provider 상태를 확인해야 한다.

VM 생성은 기존 프로젝트 flavor quota·host capacity·GPU admission과 이름 중복 규칙을 재사용한다. Active Glance image의 공개/공유/owner 가시성·min disk/RAM과 network를 검증하고 선택 keypair의 owner는 Nova 응답으로 증명해야 한다. Nova image→volume boot mapping으로 disk=0 flavor도 지원하며 boot volume은 기본 보존한다. 삭제 연동은 `delete_boot_volume_on_termination=true`를 명시할 때만 적용한다. `user_data`·비밀번호·임의 provider 속성을 받지 않고 응답에도 application credential, private key, `adminPass`를 포함하지 않는다.

이 계약은 로컬 source의 추가 기능이다. MCP handshake/tools discovery 성공과 실제 cloud provisioning 또는 운영 배포 성공은 별개다.

## 개인 MCP 키와 공개 연결 확인

사용자 화면은 `/dashboard/account`의 **외부 AI 접근**, 연결 안내는 공개 `/docs/mcp`다. 나란한 OAuth/API 키 선택지에서 선택한 방식의 setup와 저장된 연결/키 목록만 표시한다. 각 `mcp.json`은 전체 복사 버튼을 제공한다. MCP 개인 키는 브라우저 access JWT나 Lumen 추론 API 키와 다르다. 발급 사용자·승인 프로젝트와 restricted Keystone application credential에 묶이며 `read` 또는 명시적 `manage`를 사용한다. 평문 키는 발급 응답 한 번만 반환하고 `Cache-Control: no-store`/`Pragma: no-cache`로 캐싱을 금지한다. 목록에는 prefix만 포함되고 서버는 해시를 저장한다.

`GET /api/v1/auth/mcp-tokens`는 현재 로그인 사용자·프로젝트의 저장된 metadata만 반환합니다. `POST /api/v1/auth/mcp-tokens`는 `{name, access_level: "read"|"manage", expires_at?: ISO timestamp, non_expiring?: boolean, project_scope?, project_ids?}`를 받고 `201`에서 한 번만 평문 `token`을 반환합니다. 개인 키의 finite 최대 기간은 `max(366일, mcp.max_grant_ttl_days)`이며 만료 field를 모두 생략한 API 요청은 기존 서버 기본 기간을 사용합니다. 명시적 `non_expiring: true`는 만료 없는 개인 키를 만들고 응답/목록의 `expires_at`은 `null`입니다. 미래 `expires_at`과 `non_expiring: true`의 동시 입력, 문자열 boolean, 과거·naive timestamp는 거부합니다. Finite expiry는 UTC `Z` timestamp로 Keystone에 전달하며 무기한 credential에는 expiry를 보내지 않습니다. OAuth/내부 Lumen 위임은 기존 finite TTL 정책을 유지합니다.

UI는 기본1달과1일·1주일·3달·6달·1년·만료 없음·직접 선택을 제공합니다. 일·주는 UTC elapsed time, 월·년은 UTC calendar arithmetic으로 target month-end를 보정하고 현지 custom 시각은 UTC로 변환합니다. Finite POST는 실제 `expires_at`만, 만료 없음은 `non_expiring: true`만 보냅니다. 무기한도 현재 멤버십·역할·user/project binding·revocation·credential epoch·dispatch 한계를 우회하지 않습니다.

`GET /api/v1/auth/mcp-tokens`와 `GET /api/v1/auth/mcp-oauth/grants`는 명시적으로 폐기된 항목을 제외합니다. 아직 폐기하지 않은 만료 항목은 표시하여 사용자가 폐기할 수 있습니다. `DELETE /api/v1/auth/mcp-tokens/{token_id}`와 `DELETE /api/v1/auth/mcp-oauth/grants/{grant_id}`는 본인·현재 프로젝트 소유 항목만 `204`로 폐기하며, 만료 항목도 `revoked`로 전환합니다. 반복 폐기는 같은 결과를 유지합니다. 계정 화면은 성공 뒤 두 목록을 다시 조회하므로 항목·개수·빈 상태가 즉시 갱신되고 새로고침 뒤에도 유지됩니다.

폐기는 물리적 행 삭제가 아닙니다. Grant/token tombstone·감사 기록과 upstream credential 정리 재시도를 보존하고, 선택된 Lumen 기본 토큰은 해제합니다. Upstream 정리가 실패해도 로컬 폐기는 유지되어 접근·OAuth refresh가 거부되고 해당 항목은 사용자 목록에 다시 나타나지 않습니다.

MCP의 cloud tool은 이 application credential의 원래 scope로 인증하며 별도 project scope를 요청하지 않습니다. Keystone token의 user/project가 저장된 grant principal과 정확히 일치해야 provider에 요청하고, 다른 owner/project 또는 unscoped 응답은 거부합니다. Manager/admin/browser credential로 fallback하지 않습니다. 연결 확인의 handshake·tools/list 성공은 실제 cloud `tools/call` 성공과 별개의 증거입니다.

`POST /api/v1/auth/mcp-tokens/verify`는 browser access JWT와 현재 프로젝트, 허용된 Origin 및 `Sec-Fetch-Site: same-origin|same-site`가 필요합니다. `Content-Type: application/json`의 정확한 `{ "token": "<본인 개인 키>" }`만 받으며 본문은 최대1024bytes입니다. 잘못된·만료·폐기·다른 user/project의 키는 공개 URL에 접속하기 **전** 거부합니다. 임의 endpoint를 지정할 수 없습니다.

성공 `200`의 응답은 다음 구조이며 token을 포함하지 않습니다.

```json
{
  "endpoint": "https://cloud.dmslab.re.kr/mcp",
  "protocol_version": "2025-11-25",
  "server_name": "Afterglow",
  "server_version": "<running-version>",
  "tool_count": 18
}
```

프로토콜/version/count는 실제 응답을 따릅니다. 위 값은 형식 예시이며 운영 성공 증거가 아닙니다. 확인은 SDK initialize·initialized·모든 tools/list 페이지만 실행하고 tools/call을 실행하지 않습니다. 실제 클라우드 접근 권한/작업 성공이나 개별 AI client의 연결을 증명하지 않습니다. TLS를 검증하며 proxy·redirect·retry를 사용하지 않습니다. 전체20초, 응답2MiB, 최대50페이지·5000도구, 분당6회 제한과 `Cache-Control: no-store`/`Pragma: no-cache`가 적용됩니다.

| HTTP | `code` | 의미 |
|---|---|---|
| 400 | `invalid_request` | token 외 필드/본문 형식 오류 |
| 400 | `invalid_token` | 잘못된·만료·폐기·다른 owner/project의 개인 키 |
| 502 | `rejected` | 공개 MCP resource의 인증 거부 |
| 502 | `redirect` | 다른 주소로 이동; 비밀을 전송하지 않고 중단 |
| 502 | `protocol` | 올바른 MCP handshake/tool-list 응답이 아님 |
| 503 | `not_configured` | 공개 MCP resource 미설정 |
| 504 | `unavailable` | DNS/TLS/connection/timeout |
| 429 | - | 확인 rate limit; 1분 뒤 재시도 |

서비스 비활성은404, session/same-site/authority-storage 오류는401/403/503을 유지합니다. Audit action은 `mcp_grant.verify`이며 확인의 user/project·상태와 안전한 실패 원인만 기록합니다. Token/Authorization이나 upstream 오류 본문을 결과·감사에 기록하지 않습니다. API client의 `ApiError.code`와 계정의 네 언어 문구가 안정된 실패 분류를 사용합니다. 발급 창 종료·로그인/프로젝트 변경·component 해제는 화면의 비밀과 pending 결과를 폐기합니다. 개인 token·인증 JSON은 개인 설정에만 저장하고, 클립보드/파일 정리는 사용자 책임입니다. 사용 안내와 클라이언트별 형식은 `/docs/mcp`를 따릅니다.

외부 클라이언트에는 계정 화면의 **인증 JSON 복사** 또는 클라이언트별 개인 Bearer/OAuth 설정을 사용한다. 명시한 `mcp.public_url` 자체가 리소스이며 origin-only URL은 루트 `/`를 유지한다. 미설정 시만 `<public_api_base>/api/v1/mcp`로 대체한다. Root 리소스는 `/.well-known/oauth-protected-resource`와 `/oauth/{register,authorize,token,revoke}`를 사용한다. 전용 MCP 호스트의 DNS·정상 TLS·백엔드 routing과 Afterglow 서버의 outbound 접근은 운영자 준비 사항이다. `https://mcp.cloud.dmslab.re.kr` 예시는 운영 연결 성공 증거가 아니다. Lumen에서 외부 MCP를 등록하는 outbound 설정에 이 개인 키를 공유하지 않는다.


### MCP OAuth 동의·갱신과 cold schema cache

개인 Bearer 키와 OAuth는 별도 인증 방식입니다. OAuth 클라이언트 설정 JSON은 HTTP MCP resource URL만 포함하고 개인 키·`Authorization` header·`client_secret`을 넣지 않습니다. 예시 `https://cloud.dmslab.re.kr/mcp`의 discovery는 `/mcp/oauth/{register,authorize,token,revoke}`를 광고합니다. Authorization endpoint를 매개변수 없이 직접 여는 것은 유효한 요청이 아닙니다. 등록한 `client_id`, 정확한 callback/resource, `response_type=code`, 허용 scope, PKCE S256과 state를 포함한 클라이언트 요청을 사용합니다. Public client 등록은 `token_endpoint_auth_method=none`과 authorization-code·refresh grant 모두를 요구하며 HTTP loopback callback은 `127.0.0.1`·`[::1]` IP literal만 허용합니다.

정확한 `/oauth/mcp/authorize`는 공개 브라우저 동의 shell이며 protected console 전체를 공개하지 않습니다. 불투명 ticket은 URL에서 제거해 `sessionStorage`에만 보존하고 password/GitLab login·프로젝트 선택 뒤 같은 동의 화면으로 돌아옵니다. Ticket은 권한이나 access token이 아닙니다. 동의 조회·approve/deny는 현재 browser access bearer와 `X-Project-Id`가 있는 scoped session에서만 수행합니다. 승인은 해당 user/project의 restricted application credential과 grant를 만들며 클라이언트에는 opaque access/refresh token만 반환하고 upstream credential은 보내지 않습니다.

Refresh의 필수 `client_id`는 최초 authorization code의 client와 정확히 일치해야 합니다. 빈 값·다른 client·불명확한 persisted binding은 `invalid_grant`이며 token rotation이나 replay revocation을 일으키지 않습니다. `client_id` 생략도 거부하고 올바른 client의 consumed refresh 재사용은 기존 family/grant 폐기를 유지합니다. Binding은 consumed code row에 남으므로 code expiry·authorization ticket cleanup 뒤에도 유지됩니다. 계정의 OAuth 회수 또는 resource의 revoke endpoint는 기존 내구성 cleanup 경로로 grant/family와 downstream authority를 폐기합니다. Token·code·ticket·upstream secret은 문서·audit·QA receipt에 기록하지 않습니다.

SDK 내부 cold schema-cache refresh의 `list_tools(None)`은 현재 principal에게 허용된 전체 schema를 반환합니다. 외부 `tools/list` 요청은 기존 page-size와 grant-bound cursor를 유지하고, SDK input/output validation과 모든 `tools/call`의 현재 principal 권한·strict arguments·mutation ledger를 그대로 적용합니다. Manage schema가 cache에 있어도 read grant가 mutation을 실행할 수 없습니다. 실제 tool 성공은 HTTP200뿐 아니라 `isError=false`와 typed 결과를 확인해야 하며, 위 연결 확인의 handshake·목록 성공으로 대신하지 않습니다. OAuth 세부 안전 계약은 [보안 가이드](../security.md#mcp-oauth와-개인-api-키)를 따릅니다.

### 브라우저 세션 보안 패치 호환성

Login 시 최초 started_at을 기록하며 refresh/project rescope가 이 시간을 변경하지 않습니다. 만료 후 반복 요청도 401이고, 동시 refresh/rescope는 Redis 원자적 소비로 하나만 성공합니다. GitLab login도 요청 origin/device를 기록하고, 출처가 없는 과거 세션은 strict/subnet에서 재로그인이 필요합니다. Logout 폐기 실패는 503이며 브라우저는 로컬 정리와 서버 폐기 확인을 구분합니다.

JWT는 탭 sessionStorage에만 저장합니다. 구형 localStorage 자격은 제거하므로 적용 뒤 한 번 재로그인이 필요하고 새 탭은 독립 인증합니다. 탭 복제는 브라우저 정책에 따라 자격을 복사할 수 있습니다. CSP의 script nonce/hash 정책은 JavaScript-readable 자격을 HttpOnly로 바꾸는 것은 아닙니다.
