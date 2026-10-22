---
title: 인증 (Auth)
parent: API 레퍼런스
nav_order: 10
---

# 인증 (Auth) API

> 태그: `auth`
> 기본 경로: `/api/v1/auth`

로그인, JWT 토큰 발급·회전, 세션 관리, 작업 도메인 선택·생성 및 프로젝트 스코프 전환을 제공합니다.
도메인별 로그인 정책과 OIDC/GitHub provider federation, 이메일 검증 onboarding도 제공합니다.

현재 비밀번호 로그인은 도메인 입력 없이 **실제 native `Accounts`**를 서버에서 조회하고 그 UUID 안의 username/email만 선택해 인증합니다. 다른 domain의 동명 username/email은 로그인 후보가 아니며 외부 home으로 fallback하지 않습니다. 표시 이름이 Accounts인 다른 조직도 후보가 아닙니다. 기존 계정 이동·password/grant 복제는 없으므로 다른 home 계정은 이 로그인 경로를 사용할 수 없습니다. 신규 user와 개인 프로젝트는 운영자가 사전 생성한 native `Accounts`/`Personal`을 사용하고 shared domain 자체를 생성/수정하지 않습니다.

---

## 인증 방식

Afterglow는 **JWT(access + refresh) 쌍** 기반 인증을 사용합니다.
로그인 시 서버는 호출자 소유의 **unscoped Keystone 로그인 증명**을 Redis 세션에 보관하고, 클라이언트에는
access JWT와 refresh JWT를 발급합니다. 이후 인증이 필요한 모든 요청은 아래 헤더를
포함해야 합니다.

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | 예 | `Bearer <access_jwt>` 형식. 로그인 응답의 `token` 값 |
| `X-Project-Id` | 아니오 | 요청을 처리할 프로젝트 UUID. 생략 시 JWT에 담긴 프로젝트로 처리. JWT의 프로젝트와 다른 값을 주면 서버가 Keystone rescope를 수행(프로젝트 전환) |

> access JWT는 내부적으로 refresh 세션(`rjti`)을 가리키며, 서버는 매 요청마다
> Redis의 로그인 증명을 검증하고 현재 프로젝트 권한으로 native token을 새로 교환합니다. 역할을 담은 검증 결과를 요청 간 60초 cache로 재사용하지 않습니다. 권한은 JWT payload가 아니라 현재 도메인·멤버십·역할 할당에서 확인하며, 관리자 `require_admin`도 native token·`domain_context`·정확한 `system:all` 권한을 다시 확인합니다. 파생 project token은 SDK 요청용이며 로그인 증명 대신 저장하거나 브라우저에 노출하지 않습니다.

JWT 검증의 algorithm allow-list는 access/refresh 모두 `HS256` 하나이며 HMAC과 asymmetric algorithm을 섞지 않는다. Backend는 [PEM guard bypass](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-ffc3-869f-jxw9)와 [pre-verification payload recursion](https://github.com/jpadilla/pyjwt/security/advisories/GHSA-42vr-xj54-vc7v)이 수정된 PyJWT `>=2.15.0`을 요구한다. Upstream 취약점의 mixed-algorithm/raw-PEM·unsigned payload 조건이 현재 브라우저 JWT 경로에 없더라도 vulnerable library로 downgrade하지 않는다.

OIDC·서비스 HTTP client의 TLS verify/설정 CA·hostname 검증은 유지한다. Backend는 [IDNA 2003 hostname confusion](https://github.com/agronholm/anyio/security/advisories/GHSA-82r6-8w77-94w6)이 수정된 AnyIO `>=4.14.2`를 요구한다. 이 의존성 갱신은 인증 방식·endpoint·계정 잠금/세션 정책을 변경하거나 인증서 검증을 끄지 않는다.

### 세션·토큰 수명 모델

- **access JWT** — 단기 토큰. 만료 시각은 응답의 `expires_at`.
- **refresh JWT** — Redis 세션(`session_store`)에 대응. Unscoped 로그인 증명, 현재 native 프로젝트와 논리 작업 대상,
  로그인 출처 IP/기기 지문, 인증 방식, 변경 불가 `identity_domain_id`와 선택한 작업 `domain_id`를 저장합니다. Federated 세션은 `provider_id`, `provider_revision`, **로그인을 시작한 provider 정책 도메인 `provider_domain_id`**, 검증된 `login_email`도 보존합니다. 필수 identity/working/provider-origin 문맥이 없는 과거 세션은 재로그인이 필요합니다.
- **세션 타임아웃** — Keystone 토큰 수명과 별개로, Redis에 세션 시작 시간을 기록해
  `session_timeout_seconds`를 초과하면 401로 만료 처리합니다.
- **토큰 회전** — `POST /refresh`는 기존 refresh 세션을 즉시 삭제하고 새 쌍을
  발급합니다. 같은 refresh 토큰을 두 번 사용하면 두 번째 호출은 401입니다.
- **명시적 작업 범위 전환** — `/token/domain`과 `/token/workspace`만 작업 도메인을 변경합니다. `/token/workspace`는 정확한 domain/project 쌍을 한 번에 commit하며 중간 도메인 세션을 발급하지 않습니다. Refresh·프로젝트 전환은 계정 소속, 원래 세션 시작 시간·출처·provider를 유지합니다. 이전 JTI alias는 세션 회수에만 쓰며 이전 access/refresh를 다시 유효하게 만들지 않습니다.
- **프로젝트 role 변경** — 본인을 포함한 직접·그룹·상속·역할 추론 변경은 현재 권위와 기존 검증 cache를 무효화하지만 로그인 family를 일괄 삭제하지 않습니다. 회수한 권한은 새 요청부터 반영되어 해당 작업이 `403`일 수 있으며 다음 로그인까지 권한을 유지하지 않습니다. 명시적 세션 회수·계정 차단·실제 native 로그인 증명 무효는 별도 보안 경계입니다.
- **선택 프로젝트 접근 상실** — 로그인과 작업 도메인 정책이 여전히 유효하면 인증 문맥·다른 프로젝트 선택은 사용할 수 있고 refresh는 실제 native 범위를 projectless로 회전할 수 있습니다. 관리자 논리 작업 대상도 현재 `system:all`과 대상 도메인·프로젝트를 다시 검증한 경우에만 유지합니다. Refresh·인증 조회·`/token/project` 복구는 철회된 grant를 자동 복원하지 않습니다. 검증된 신규 로그인과 명시 domain/workspace 전환의 기존 onboarding은 그대로입니다.
- **다른 도메인에서 projectless 복구** — 서버는 실제 native subject와 변경 불가 home을 먼저 검증한 뒤 현재 membership으로 선택 working domain을 적용합니다. 따라서 프로젝트 회수 후 반복 refresh·`/me`·workspace 탐색은 home과 working domain이 달라도 사용할 수 있습니다. Scoped native token의 프로젝트/도메인 불일치, 계정·home 비활성, working membership 상실이나 원 native 로그인 증명 회수는 허용하지 않습니다. Frontend는 refresh·`/me`의 명시적 null/빈 `project_id`에서 ID와 이름을 함께 지우며, 필드 생략은 기존 값을 유지합니다. 예상치 못한 다른 nonempty project를 scope 전환으로 받아들이지 않습니다.

Refresh JWT의 `exp`와 Redis key의 양수 TTL은 로그인 세션의 유효성을 보장하지 않습니다. 기본값은 access900초·refresh604800초·절대 세션3600초이며 실제 실행 설정이 우선합니다. 절대 만료는 최초 `started_at + session_timeout_seconds`이고 refresh·프로젝트/도메인 전환으로 연장되지 않습니다. 유효하지 않은 native 로그인 증명·명시적 회수·절대 만료는 기존대로401이며, 계정·도메인·로그인 정책도 우회하지 않습니다. Keystone 자체가 group membership 변경으로 사용자의 unscoped 증명까지 회수한 경우에는 재로그인이 필요합니다. JWT `exp−iat`, 현재 설정, 원래 `started_at`과 native 만료를 각각 관찰해야 하며 설정 기본값을 실측 수명으로 보고하지 않습니다.

2026-10-16의 새 격리 정본 실행에서는 실제 서명 JWT 수명과 회전 전후의 동일 `started_at`, 양 JWT/Redis TTL이 남은 절대 만료의401을 확인했습니다. 공유 debug 세션도 read-only Redis/native-token 관찰로 native 만료와 별개의 최초 로그인 deadline을 확인했습니다. 합성 deadline 이동·실제 사용자 세션·현재 브라우저 JWT 관측의 제한은 [검증 기록](../testing.md#작업-영역-지연조기-로그아웃-조사-2026-10-16-frozen-local-qualification-일부-수용-차단)에서 구분합니다. 만료나 회수 정책을 느슨하게 바꾼 것은 아닙니다.

### 보안 제한 (참고)

- **로그인 실패 계정 잠금** — 도메인 ID와 사용자 이름으로 분리하며 native `v3.Password` 자격증명 거부만 실패 횟수에 반영합니다. Directory 장애는 503이고 실패 횟수를 늘리지 않습니다. Redis 장애 시 잠금은 가용성 우선으로 생략(fail-open)합니다.
- **토큰 출처 바인딩** — access 토큰의 출처 IP/기기 지문이 최초 로그인과 불일치하면
  차단할 수 있습니다. 바인딩 검사 자체가 실패(Redis 장애 등)하면 **요청을 거부
  (fail-closed, 401)** 합니다.

---

## 엔드포인트 목록

| 메서드 | 경로 | 인증 | 설명 |
|--------|------|------|------|
| `POST` | `/api/v1/auth/login` | 없음 | native Accounts 안의 username/email로 비밀번호 인증해 초기 JWT 발급 (10회/분) |
| `POST` | `/api/v1/auth/personal-project/recovery` | native password 증명 | 동일 Accounts 로그인 guard·정책 뒤 안전한 개인 프로젝트 단계 재개 및 JWT 발급 (10회/분) |
| `GET` | `/api/v1/auth/me` | 필요 | 현재 토큰의 사용자/프로젝트 정보 |
| `POST` | `/api/v1/auth/logout` | 필요 | 현재 세션 로그아웃 (refresh 세션 삭제 + Keystone revoke) |
| `POST` | `/api/v1/auth/refresh` | refresh 토큰 | access/refresh JWT 재발급 (회전, 30회/분) |
| `POST` | `/api/v1/auth/token/project` | 필요 | 현재 작업 도메인 내 다른 프로젝트로 전환 (새 토큰 쌍) |
| `GET` | `/api/v1/auth/domains` | 필요 | 현재 접근 가능한 활성 작업 도메인 목록 |
| `GET` | `/api/v1/auth/workspaces` | 필요 | 선택 query `domain_id`의 현재 접근 가능한 프로젝트·capability를 읽기만 함 |
| `POST` | `/api/v1/auth/domains` | 필요 | 가입 정책 또는 현재 systemadmin 권한으로 도메인·Default 생성 |
| `POST` | `/api/v1/auth/token/domain` | 필요 | 작업 도메인 명시적 전환 (원자적 세션 회전) |
| `POST` | `/api/v1/auth/token/workspace` | 필요 | `{domain_id,project_id}`를 원자적으로 선택 (새 토큰 쌍) |
| `POST` | `/api/v1/auth/logout-all` | 필요 | 현재 사용자의 모든 세션 폐기 |
| `GET` | `/api/v1/auth/sessions` | 필요 | 현재 사용자의 활성 세션 목록 |
| `DELETE` | `/api/v1/auth/sessions/{jti}` | 필요 | 개별 세션 삭제 (소유권 확인) |
| `GET` | `/api/v1/auth/groups` | 필요 | 현재 사용자가 속한 Keystone 그룹 목록 |
| `GET` | `/api/v1/auth/projects` | 필요 | 접근 가능한 프로젝트 목록 |
| `GET` | `/api/v1/auth/projects/recent` | 필요 | 최근 접근순 프로젝트 목록 |
| `GET` | `/api/v1/auth/login-options` | 없음 | 도메인 입력 없는 로그인 화면용 공급자 등록 metadata (30회/분) |
| `GET` | `/api/v1/auth/domains/resolve` | 없음 | 도메인과 로그인 방법 조회 (30회/분) |
| `POST` | `/api/v1/auth/domains/{domain_id}/providers/{provider_id}/authorize` | 없음·동일 사이트 | provider 인증 시작 (20회/분) |
| `POST` | `/api/v1/auth/providers/callback` | 없음·state cookie | code/state로 JWT 발급 (10회/분) |
| `POST` | `/api/v1/auth/providers/link` | 없음·동일 사이트·state cookie | 기존 계정의 정확한 username/password로 provider 연결 (5회/분) |
| `POST` | `/api/v1/auth/providers/link/authenticated` | 필요·동일 사이트·state cookie | 현재 인증된 canonical 계정에 provider 연결 (5회/분) |
| `GET` | `/api/v1/auth/invitations/{token}` | 없음 | 전달된 초대 링크 조회 (20회/분) |
| `POST` | `/api/v1/auth/invitations/accept` | 없음 | 초대로 새 계정 생성 (5회/분) |
| `POST` | `/api/v1/auth/invitations/accept-existing` | 필요 | 본인 기존 계정으로 초대 수락 (5회/분) |
| `GET` | `/api/v1/auth/signup/options` | 없음 | 전역 signup/SMTP/recovery 구성 가능 여부 (20회/분) |
| `POST` | `/api/v1/auth/registrations` | 없음 | 전역 이메일 우선 개인 계정 가입 링크 요청 (3회/분) |
| `GET` | `/api/v1/auth/registrations/{token}` | 없음·이메일 proof | 계정 존재와 기존 home 안내 (20회/분) |
| `POST` | `/api/v1/auth/domains/{domain_id}/registrations` | 없음 | 사용 불가; 403 `invitation_required` |
| `POST` | `/api/v1/auth/registrations/accept` | 없음·이메일 proof | 새 개인 home 계정 생성 (5회/분) |
| `POST` | `/api/v1/auth/recovery/username`, `/api/v1/auth/recovery/password` | 없음 | 이메일 소유 기반 복구 요청 (각3회/분) |
| `GET` | `/api/v1/auth/recovery/{token}` | 없음·이메일 proof | 복구 proof 조회; username은 즉시 소비 (20회/분 공유) |
| `POST` | `/api/v1/auth/recovery/password/complete` | 없음·이메일 proof | 비밀번호 복구 (5회/분) |
| `POST` | `/api/v1/auth/email/changes` | 필요·현재 password | 검증된 프로필 이메일 변경 요청 (3회/분) |
| `POST` | `/api/v1/auth/email/changes/accept` | 없음·이메일 proof | 새 이메일 확인·변경 (5회/분) |
| `GET/POST` | `/api/v1/auth/mcp-tokens` | 필요 | 현재 사용자·프로젝트의 개인 MCP 키 조회/발급 (MCP 활성화 필요) |
| `POST` | `/api/v1/auth/mcp-tokens/verify` | 필요·동일 사이트 | 본인 개인 키로 공개 MCP 초기화·도구 목록 확인 (6회/분) |
| `DELETE` | `/api/v1/auth/mcp-tokens/{id}` | 필요·동일 사이트 | 본인 키 회수 |

---

## 첫 로그인 개인 프로젝트 복구

관리자 생성 계정의 개인 프로젝트는 첫 성공한 password/provider 로그인에서 준비합니다. `POST /api/v1/auth/personal-project/recovery`는 `/auth/login`과 같은 `{username,password}` body를 받고 Accounts의 exact native password/subject·로그인 정책을 새로 증명한 뒤 같은 세션 공개 경로를 실행합니다. 기존 refresh/JWT 없이 시작할 수 있으나 자격 증명 없이 provisioning할 수 있는 endpoint는 아닙니다. 잘못된 비밀번호는401, 변조/타 home의 native proof는401/403으로 거부하며 프로젝트를 만들지 않습니다.

안전한 중단의503 `detail`은 `{code:"personal_project_retry_available",operation_id,retryable:true,native_calls_settled_required:false}`입니다. 같은 intent/name·동결 quota의 confirmed/not-sent 단계부터 재개하며 UI는 제출한 비밀번호를 지우고 다시 입력하도록 합니다. Dispatch 결과가 불명하면 `personal_project_recovery_required`, `retryable:false`, `native_calls_settled_required:true`로 구분하고 기존 system-admin settlement 전 재전송하지 않습니다. 성공한 fresh human은 관리자도 verified personal primary에 연결되어 dashboard로 진입합니다. 본인이 명시적으로 켠 마지막 workspace 복원만 fresh native 권위 아래 다른 pair를 선택합니다. Projectless automation의 chooser와 초대/MCP/Claude continuation, 기존 user/home/password·리소스 보존은 유지합니다.


새 기본 개인 quota는2 vCPU·4096MiB RAM·1024GiB Cinder와 보조 count입니다. 저장된 관리자 template 및 기존 frozen intent는 보존합니다. 기존 개인 프로젝트에 새 정책을 적용하려면 [관리자 quota 미리보기·적용](admin.md#가입-정책개인-프로젝트-quota와-승인-대기열)을 별도로 사용합니다.1TiB 볼륨 자동 생성이나 기존 프로젝트 quota의 숨은 로그인 변경은 없습니다.

## 공통 스키마

### TokenResponse

로그인·리프레시·프로젝트/도메인 전환·provider 콜백이 공통으로 반환하는 스키마입니다.

```json
{
  "token": "eyJhbGci...",
  "refresh_token": "eyJhbGci...",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "user_id": "uuid-string",
  "username": "user-name",
  "domain_id": "domain-uuid",
  "domain_name": "Example",
  "is_domain_manager": false,
  "identity_domain_id": "home-domain-uuid",
  "identity_domain_name": "Home",
  "available_domains": [{"id": "domain-uuid", "name": "Example"}],
  "can_create_domain": false,
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
| `project_id` | string | 스코프된 프로젝트 UUID; 접근할 프로젝트가 없으면 `""` |
| `project_name` | string | 프로젝트 이름; 도메인 전용 로그인은 `""` |
| `user_id` | string | 사용자 UUID |
| `username` | string | 사용자 이름 |
| `domain_id`, `domain_name` | string | 현재 선택한 작업 도메인 ID·표시 이름 |
| `identity_domain_id`, `identity_domain_name` | string | 변경 불가 계정 home 도메인; password 정책 기준. Federated provider 정책 origin은 별도 서버 세션의 `provider_domain_id` |
| `available_domains` | array[{id,name}] | 현재 enabled home 및 실제 native project membership으로 joined한 작업 도메인; 시스템 전체 inventory 아님 |
| `can_create_domain` | boolean | 사용자 콘솔의 `auth.organization_creation_enabled` 정책 capability; system-admin identity만으로 표시를 늘리지 않으며 생성 API의 별도 권위 검증은 유지 |
| `is_domain_manager` | boolean | 작업 도메인의 canonical Default 프로젝트에서 현재 유효한 manager; 직접·그룹·범위 상속·실제 역할 추론 포함 |
| `expires_at` | string | access JWT 만료 시각 (ISO 8601) |
| `roles` | array[string] | 표시용 프로젝트 역할 이름. 일반 사용자에게 `admin`·`manager` 및 이들을 상속하는 사용자 정의 역할은 노출하지 않음 |
| `default_project_id` | string | 현재 도메인의 기본 프로젝트 힌트: 활성·접근 가능한 사용자 선호 UUID를 우선하고, 없으면 접근 가능한 canonical `Default` UUID 또는 `""`. 실제 활성 scope는 `project_id`로 확인 |
| `is_system_admin` | boolean | 시스템 관리자 여부 |
| `can_write` | boolean | 숨기기 전 실제 project 역할로 계산한 사용자 콘솔 쓰기 capability; system-admin 권위와 분리하며 프론트엔드는 표시용 이름에서 재추론하지 않음 |
| `auth_method` | string | `password` 또는 `federated` |
| `initial_workspace` | object/null | Fresh human login 전용 `{kind:"personal"\|"remembered",domain_id,project_id}`. 실제 session pair와 정확히 일치해야 하며 refresh/rescope의 권한 증명으로 재사용하지 않음 |

### UserInfo

```json
{
  "user_id": "uuid-string",
  "username": "user-name",
  "project_id": "uuid-string",
  "project_name": "project-name",
  "domain_id": "domain-uuid",
  "domain_name": "Example",
  "is_domain_manager": false,
  "identity_domain_id": "home-domain-uuid",
  "identity_domain_name": "Home",
  "available_domains": [{"id": "domain-uuid", "name": "Example"}],
  "can_create_domain": false,
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

작업 도메인을 입력받지 않고 complete native directory에서 정규화 email 또는 정확한 username의 **유일한 canonical 계정**을 식별합니다. 해당 enabled 계정과 실제 원 소속(home)의 password 정책을 확인한 뒤 **한 계정의 home에 한 번만** password를 시도합니다. 기존 도메인 우선 선택이나 여러 home에 대한 credential 순회는 없으며 모호한 기존 계정은409 `account_ambiguous`입니다. 이메일 사용을 권장하며 이메일 일치만으로 계정을 병합하지 않습니다. 최초 응답의 `domain_id`는 반드시 `identity_domain_id`와 같습니다. 비율 제한: **10회/분**.

### 요청 본문

```json
{
  "username": "alice@example.com",
  "password": "original-account-password"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `username` | string | 예 | 1–255자; global unique normalized email 또는 정확한 username |
| `password` | string | 예 | 1–1024자 비밀번호 |

### 응답 (200 OK)

[TokenResponse](#tokenresponse) — `auth_method`는 `password`.

검증된 interactive human은 관리자도 원래 identity home/계정 ID·비밀번호·federation·기존 grant/리소스를 보존하면서 본인 personal primary를 준비합니다. Native project/system/group의 service authority만 automation으로 제외하고 configured username으로 human을 제외하지 않습니다. 새 개인 프로젝트는 직접 member 하나·동결 native quota·raw/effective provenance를 검증하며 기존 owner 기반 personal은 재작성하지 않습니다. 조직 Default/grant를 로그인으로 새로 추가하지 않고 unknown provisioning을 projectless 성공으로 숨기지 않습니다.

기본 초기 scope는 verified personal primary이며 Accounts는 workspace가 아닙니다. 새 password/provider 로그인은 준비된 프로젝트로 dashboard에 직접 진입하고 초대/MCP/Claude intent가 있으면 그 진행을 우선합니다. **계정 설정의 명시 remember-last-workspace opt-in**만 fresh native 확인 후 다른 pair를 복원합니다. 초기 응답의 `initial_workspace`는 반환된 working pair와 정확히 일치해야 합니다. Pin/order/hidden·단순 최근 목록은 권한이나 landing 근거가 아니며 projectless automation은 기존 chooser를 사용합니다. 로그인 body의 domain/project 추가 selector는422이고 일반 탐색/refresh는 onboarding을 반복하지 않습니다.

Native client와 directory 읽기는 요청 안에서만 공유하고 credential exchange 전 password 방법 정책을 확인합니다. 새 personal primary는 exact marker와 본인 직접 member·전체 native provenance를 다시 검증하며 불명 SQL/native intent·disabled user/home/project·필수 membership 회수는 성공 세션을 만들지 못합니다. 기존 owner 기반 personal은 원래 단일-owner 검증과 grant를 보존합니다. Configured OIDC organization은 현재 binding marker와 조직 membership을 callback 최종 공개·refresh·scope 공개에서도 검사합니다. Provider origin과 immutable identity/working scope는 독립적입니다. 요청 간 authority cache나 token 검증 TTL은 늘리지 않습니다.

브라우저는 완전히 매핑한 새 로그인 응답을 일회성 메모리 proof로 받아 즉시 사용할 수 있으므로 로그인 직후 `/auth/me`를 반복하지 않습니다. 저장된 자격을 새로고침으로 복원하거나 임의/복사된 상태를 주입하면 `/auth/me` 검증이 필요합니다. 서버가 검증한 exact-owner refresh/rescope 응답은 기존 준비된 화면을 유지하지만 새 token의 `/me` 검증을 생략하지 않습니다. Proof는 sessionStorage에 저장하지 않으며 이전 검증 응답·retry는 새 로그인/작업 범위를 덮어쓰지 못합니다.

Root 인증 controller만 `/auth/me`와 해당 검증의 retry를 소유합니다. 관리자 layout은 별도 검증 요청·권한 snapshot을 만들지 않고 `authReady`와 현재 시스템 관리자 flag를 함께 소비합니다. 따라서 전체 document 새로고침은 한 번의 서버 검증 전까지 비공개 화면을 숨기지만, 정상 native token 갱신의 background 재검증은 이미 준비된 화면·입력을 재생성하지 않습니다. 일반 목록 새로고침·관리자 내부 탐색도 인증 검증을 추가하지 않습니다. 명시적 scope 전환 중에는 이전 workspace를 숨기며 확인된 권한 철회·401·검증 장애는 기존 거부/로그아웃/root 복구 경계를 유지합니다. 서버 관리자 endpoint의 live native 검증과 권한 cache/TTL은 변경하지 않습니다.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 인증 실패 (잘못된 자격증명) |
| `403` | 비활성 도메인, password 정책 거부 또는 email allowlist 위반 |
| `409` | canonical username/email에 여러 계정이 대응함; 임의 계정으로 password를 시도하지 않음 |
| `422` | username/password 본문 검증 실패 또는 퇴역한 domain/project selector 등 추가 필드 |
| `503` | Directory·로그인 정책 저장소·인증 서비스 장애; 잘못된 비밀번호로 취급하지 않음 |
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
| `403` | 도메인/사용자/프로젝트 문맥 또는 현재 로그인 정책 거부; 재인증 필요 |
| `429` | 갱신 요청 제한; 브라우저는 Retry-After cooldown을 적용 |
| `503` | Redis/Keystone 연결·검증 장애; 현재 요청은 거부하고 세션은 재시도를 위해 보존 |

Keystone가 token authentication에서 반환하는 `404 Failed to validate token`과 `404 Could not recognize Fernet token`은 무효 token으로 분류해 `401`로 변환합니다. 일반 endpoint/resource 404는 인증 무효를 확정하지 못하므로 `503`입니다. **Refresh 401과 문맥/정책 403은 terminal**이며 인증을 정리하고 재로그인합니다. **429·5xx·네트워크 실패는 transient**이며 세션을 유지하고 재시도합니다(429는 Retry-After cooldown). 브라우저는 복구 dialog에서 재시도·로그아웃을 제공합니다. 일반 서비스 resource 오류는 이 전역 인증 상태로 승격하지 않습니다.

브라우저의 보조 갱신과 일반 요청은 진행 중인 작업 범위 전환의 응답 반영을 기다립니다. 범위 변경 요청만 자기 소유 preflight refresh를 수행할 수 있습니다. 첫 전송뿐 아니라 refresh 후 재시도에서 늦게 온401도 전환 완료 뒤 **실제 전송 토큰과 현재 logical login·사용자·도메인·프로젝트**를 비교한 다음 인증 종료 여부를 결정합니다. 이전 토큰의 거부로 새 scope/login을 지우지 않으며, 세 번째 전송이나 non-replay 변경 요청의 자동 재전송은 하지 않습니다.

---

## POST /api/v1/auth/token/project

현재 작업 도메인의 접근 가능한 활성 프로젝트로 스코프된 새 토큰 쌍을 발급합니다. 대상 프로젝트의 native domain·멤버십을 검증하고 immutable identity domain·로그인 정책·원래 세션 수명을 유지합니다. 다른 작업 도메인의 프로젝트를 이 경로로 선택할 수 없습니다.

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

## 작업 도메인 선택·생성

### 도메인 identity와 표시 이름

`GET /api/v1/auth/domains`는 `[{id,name}]`를 반환합니다. `id`가 identity이며 `name`은 **중복 가능한 표시 이름**입니다. 새 관리 도메인은 Keystone native name에 `afterglow-<uuid4 hex>`를 사용하고 `afterglow_display_name`에 표시 이름을 저장합니다. 기존 도메인은 native name을 표시 fallback으로 유지하며 자동 rename하지 않습니다. 로그인·native scope는 서버가 확인한 domain ID를 사용합니다. 새 계정의 home인 `identity_domain_id`는 불변이고 `domain_id`만 작업 범위로 전환됩니다. 도메인 생성·가입은 기존 계정을 복제하거나 이동하지 않습니다.

목록은 현재 enabled home 및 실제 프로젝트 멤버십으로 joined한 도메인만 포함합니다. Manager 읽기 projection만 남은 stale 접근은 멤버십으로 인정하지 않으며 `system:all`도 selector에 전역 도메인을 추가하지 않습니다. 시스템 전체 관측은 별도 [관리자 API](admin.md#도메인-관리와-관측)를 사용합니다.

### GET /api/v1/auth/workspaces

Query `domain_id`는 선택(1–255자)이며 생략하면 현재 작업 도메인입니다. 정확한 ID와 현재 멤버십·immutable home을 확인하며 **scope 교환·grant 생성·세션 회전 없이** 다음200 응답을 반환합니다.

```json
{
  "domain": {"id": "domain-uuid", "name": "Example"},
  "projects": [{"id": "project-uuid", "name": "Default", "description": "", "domain_id": "domain-uuid", "domain_name": "Example", "enabled": true, "last_accessed_at": null}],
  "default_project_id": "project-uuid",
  "is_domain_manager": true,
  "can_create_project": true
}
```

Manager는 해당 도메인의 enabled 프로젝트 전체를, 일반 사용자는 현재 native 접근과 실제 멤버십을 모두 통과한 enabled 프로젝트만 받습니다. 프로젝트는 이름의 casefold와 ID 순으로 정렬합니다. Canonical Default가 반환 목록에 없으면 `default_project_id=""`입니다. `can_create_project`는 현재 manager 또는 해당 도메인의 `project_creator` capability이며 생성 API가 다시 검증합니다. 마지막 domain authority 재조회가 달라지면403입니다. UUID 기반 pin/order/hidden 같은 표시 설정은 권한을 복원하거나 활성 scope를 바꾸는 근거가 아닙니다.

Directory 조립은 한 요청의 `NativeOperation`에서 서비스 연결·도메인/프로젝트·membership·role graph 관측을 재사용합니다. 응답 직전 별도의 fresh domain authority 확인을 위해 관측을 무효화하며 연결만 유지합니다. 요청 간 권위 cache나 TTL 증가는 없습니다. Refresh·명시적 scope 변경도 동일한 연결 소유권을 사용하되 정책 조회와 native 변경 뒤 publication 경계에서 권위를 다시 검증합니다.

Chooser는 알고 있는 대상 도메인의 directory/workspace 읽기를 병행하고 같은 대상의 진행 중 읽기를 합칩니다. 성공한 표시 snapshot은 현재 logical session/user/home/working-domain/project 및 권한 문맥에만 묶인 브라우저 메모리에서30초 재사용하며, workspace는 최대16개 도메인으로 제한합니다. 재열기·재방문은 남은 수명만 사용하고 수명을 연장하지 않습니다. Logout·새 login·scope/권한 변경·전환 시작은 동기적으로 폐기하므로 닫힌 창 사이의 ABA도 이전 snapshot을 복원하지 않습니다. 목록·capability 표시 cache는 membership이나 mutation 권위가 아니며 실제 선택·생성 API는 기존 fresh native 검증을 수행합니다.

명시적 **목록 새로고침**과 프로젝트/도메인 생성 후 재조회는 기존 snapshot을 버리고 directory/workspace를 다시 읽습니다. 실패한 조회와 늦은 old-owner/unmounted 응답은 저장하지 않습니다. TTL 만료 뒤 자동 탐색 재검증은 미확정 생성 요청의 재전송 잠금을 해제하지 않으며, 성공한 명시적 refresh만 기존 uncertain-write fence를 해제합니다. API 응답 자체의 no-store/private 계약·서버 권한 cache 정책은 바뀌지 않습니다.

### 원자적 작업 범위 선택

`POST /api/v1/auth/token/workspace`는 정확히 `{ "domain_id": "domain-uuid", "project_id": "project-uuid" }`를 받습니다. 두 필드는 필수, 앞뒤 공백은 제거하며 domain ID는1–255자, project ID는최대255자, extra field는422입니다. `project_id=""`도 schema상 허용되지만 현재 구현은 대상 도메인에 접근 가능한 프로젝트가 하나라도 있으면403으로 거부합니다. 프로젝트 없는 도메인에서만 빈 scope를 선택할 수 있고, Default manager는 일반 프로젝트를 선택하지 않아도 Default scope로 IAM을 사용합니다.

서버는 현재 사용자·home·작업 domain/project, 대상의 enabled 상태와 실제 멤버십, home 로그인/provider 정책 및 대상 도메인 email 정책을 재검증합니다. 이후 필요한 기존 Default reader/manager 읽기 접근을 동기화하고 caller의 실제 native token으로 교환합니다. [TokenResponse](#tokenresponse)를 한 번만 발급하며 Redis CAS는 이전 JTI와 작업 도메인이 일치할 때만 회전합니다. 사용자 ID·immutable home·세션 시작 시각·출처·provider 바인딩은 보존되고 이전 access/refresh는 사용할 수 없습니다. 탐색한 domain을 commit하지 않으면 활성 세션은 바뀌지 않습니다. 실패한 요청을 자동 replay하지 말고 현재 세션·대상 scope를 다시 확인합니다.

`POST /api/v1/auth/token/domain`은 `{ "domain_id": "exact-domain-id" }`로 같은 실제 membership 경계를 사용하되 권한이 있는 대상 도메인의 Default를 준비하고 그 프로젝트를 우선 선택합니다. 기존 Default의 소유권은 변경하지 않습니다. 정확한 project 선택은 `/token/workspace`를 사용합니다. `/token/project`는 현재 작업 도메인 내부 전환만 허용합니다. 사용자용 전환은 system-admin이어도 native membership을 요구하며 관리자 관측용 논리 target은 별도 관리자/native service API 경계이지 이 selector의 권한 근거가 아닙니다.

### 도메인 생성

`POST /api/v1/auth/domains` 본문은 `{ "name": "Example", "description": "optional" }`입니다. Name은 trim 후1–64자 표시 이름, description은최대4096자, extra field는 금지합니다. 서버는 현재 native identity와 live `system:all` admin 여부를 다시 확인하고, 일반 사용자는 독립 `[auth].organization_creation_enabled`와 `max_organizations_per_user`를 충족해야 합니다. 공개 signup과 원래 home의 `signup_enabled`는 조직 생성 권위가 아닙니다. 성공201은 `{id,name,description,enabled,kind:"organization",default_project_id}`이며 새 조직과 canonical Default 및 실제 호출자의 `manager`·`project_owner`·직접 `project_reader` grant가 검증됐음을 뜻합니다. Manager는 Default의 조직 관리 권위이며 system admin이 아닙니다. Creator의 원래 계정 ID/home과 로그인 세션은 보존하고 API 자체는 새 작업 조직으로 자동 전환하지 않습니다.

활성 도메인 안에서 Default를 비활성 상태로 준비하고 단일 소유권·manager/reader grant·읽기 projection·quota defaults를 확인한 뒤 활성화합니다. Initial owner는 기존 ownership journal에 기록하며 결과가 applying/unknown이면 정확한 disabled 프로젝트와 intent를 보존해 운영자 settlement/reconciliation 없이 재전송·삭제하지 않습니다. 확정된 후속 실패의 보상도 이번 호출이 소유권을 확인한 정확한 신규 ID만 대상으로 합니다. 이름으로 재생성/삭제하지 않습니다. 기존 도메인의 최초 creator/manager는 추정하지 않으며 새 Default의 프로젝트 생성자와 도메인 생성자를 구분합니다.

공통 오류: 무효/이미 회전한 세션401, 멤버십·정책·비활성·domain/project 불일치403, 대상 부재404, 입력422, native 충돌·bootstrap/동시 변경409, native/Redis/정책 검증 장애503입니다. 인증 route의 validation은 `{detail:"Invalid authentication input"}`이며 정상/처리된 오류 응답에 no-store/private·no-cache를 적용합니다. 실패를 빈 정상 목록이나 성공 회전으로 대체하지 않습니다.

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
    { "jti": "...", "domain_id": "domain-uuid", "project_id": "", "origin_ip": "...", "device_type": "desktop", "os": "macOS", "started_at": 1790000000, "last_seen": 1790000100, "auth_method": "password" }
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

현재 working domain의 fresh workspace membership directory와 같은 프로젝트 목록을 반환합니다. System-admin도 다른 사람의 Personal이나 비소속 도메인 프로젝트를 추가로 받지 않으며 user-project authority 목록의 서버2분 cache는 제거했습니다. `/projects/recent`는 같은 검증 목록에만 최근 접근 시각·정렬을 적용합니다. 이름은 native UUID/name과 분리된 persistent display label을 우선 사용합니다.

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

## 원 도메인 우선 로그인과 provider federation

로그인 화면은 `GET /api/v1/auth/login-options`로 현재 허용된 활성 공급자 등록만 읽습니다. 응답은 `{ "providers": [{ "id": "provider-uuid", "name": "Company SSO", "kind": "oidc", "domain_id": "origin-domain-uuid", "domain_name": "Organization" }] }`입니다. `domain_id`는 **인증 공급자 등록의 정책 origin**이며 사용자가 입력/선택하는 초기 작업 도메인이 아닙니다. 공급자별 독립 ID와 origin을 보존하고 secret/client ID/endpoint·사용자/email 조회를 노출하지 않으며 목록 조회가 issuer discovery를 실행하지 않습니다. 실패는503/no-store로 표시하며 암묵적인 공급자 fallback은 없습니다. Password form은 이 목록과 독립적으로 원 소속 정책 아래 인증합니다.

메인 로그인은 비밀번호 form과 **SSO로 로그인** 버튼 하나를 표시합니다. 공급자 선택 view는 exact provider/origin 등록과 loading/empty/failure를 구분하고 비밀번호 복귀를 제공합니다. 선택 origin은 작업 도메인 전환이나 조직 가입이 아니며 성공 뒤 password와 같은 personal/명시 remembered landing을 사용합니다. View 전환은 password를 지우고 pending 방법 변경을 막습니다. Public catalog는 mounted lifetime에만 묶고 authorize 요청을 자동 실행하지 않습니다.

목록의 origin 후보는 서버에 설정된 기본 native 도메인, `[auth.domain."<exact-domain-id>"]`의 명시적 도메인, 현재 enabled·allowlist를 만족하는 SQL 공급자 소유 도메인입니다. 각 origin의 현재 native enabled 상태와 기존 provider 정책을 확인하며, 설정되지 않은 개인 home마다 공통 레지스트리를 복제하지 않습니다. 이 API는 계정별 가입 도메인 directory가 아니므로 사용자 이름·이메일을 받지 않습니다.

기존 `GET /api/v1/auth/domains/resolve?name=Example`은 특정 enabled 도메인의 설정 metadata를 조회하는 별도 경로로 유지하지만 새 로그인 화면의 선행 조건은 아닙니다. `name`은1–255자의 표시 이름 또는 exact ID이며 중복 표시 이름은409 `domain_ambiguous`입니다. 응답 예:

```json
{"domain_id":"domain-uuid","domain_name":"Example","password_enabled":true,"providers":[{"id":"provider-uuid","name":"Company SSO","kind":"oidc"}],"signup_enabled":false}
```

Provider kind는 `oidc` 또는 `github`입니다. Enabled·configured provider만 공개되며 아직 로그인으로 검증되지 않은 provider도 최초 검증을 위해 노출됩니다. Resolve의 `signup_enabled`는 기존 SQL 도메인 정책/SMTP projection이며 **그 도메인에 공개 가입할 권한이 아닙니다**. 공개 가입 UI는 전역 `/signup/options`를 사용하고 per-domain 등록은 항상 거부됩니다. Secret·email allowlist·Keystone federation 설정은 공개하지 않습니다.

`POST /api/v1/auth/domains/{domain_id}/providers/{provider_id}/authorize`는 본문 없이 `200 {"authorize_url":"..."}`를 반환합니다. 브라우저는 credential 포함 요청으로 cookie를 받고 해당 URL로 이동합니다. Redirect는 설정된 frontend의 `/auth/callback`입니다. 서버는 600초·1회용 state를 Redis에 저장하고 도메인/provider/revision·browser binding·redirect URI·PKCE verifier·nonce에 묶습니다. Cookie `afterglow_provider_auth`는 HttpOnly, SameSite=Lax, Path=`/api/v1/auth/providers`, Max-Age=600이며 production 또는 HTTPS public API에서 Secure입니다. Callback과 link endpoint가 같은 cookie를 사용합니다. PKCE S256은 두 kind 모두 사용하고 OIDC는 nonce도 전송·검증합니다.

Frontend 콜백은 credential 포함 `POST /api/v1/auth/providers/callback`으로 다음 본문만 전송합니다(extra field 금지):

```json
{"code":"provider-authorization-code","state":"returned-state"}
```

`code`는 1–2048자, `state`는 16–256자입니다. 성공은 `200` [TokenResponse](#tokenresponse), `auth_method="federated"`. State는 원자적으로 소비되며 replay·만료·다른 브라우저 cookie는 거부합니다. Cookie는 성공 및 일반 DomainAuthError 콜백 실패에서 삭제하되 **`account_link_required`에서는 연결 완료를 위해 유지**합니다. OIDC signed ID token은 issuer/audience/시간/subject/nonce와 signing key를 검증하고 UserInfo를 사용할 때 subject도 대조합니다. OIDC verified email 또는 GitHub의 정확히 하나인 verified primary email을 정책에 대조합니다. Native exchange 전에 global email 소유권·stable issuer/subject·native federated tuple의 유일성을 확인합니다. Keystone이 canonical user ID와 실제 home을 반환해야 하며 admin/service password로 사용자를 가장하지 않습니다.

Generic callback UI는 이 요청에만 `AbortSignal.timeout(120_000)`을 사용합니다. 일반 API의30초 기본값, `replayOnUnauthorized:false`, no-store와 늦은 응답의 login-owner fence는 그대로입니다. Timeout은 연결/로그인 성공이 아니며 소비 여부를 추정해 같은 code/state를 자동 재전송하지 않습니다. 새 로그인이 필요하면 새 authorize부터 시작합니다.

Backend source의 `issue_federated_login`은 한 요청의 `NativeOperation`에서 native 연결을 공유합니다. 정책 I/O 뒤와 최종 응답 metadata publication 전에는 관측을 폐기하여 현재 enabled identity/home·작업 domain과 권위를 다시 검증하며, 요청 간 cache나 세션 수명 연장은 없습니다. Source 개선과 실제 배포 revision은 다를 수 있습니다. 2026-10-18 로컬 복구에서는 사용자 선택으로 frontend만 교체하고 기존 role/session 변경을 포함한 backend image는 보존했습니다([검증 기록](../testing.md)).


### Canonical 계정 연결과 도메인 admission

계정 생성·이메일 변경·복구는 정규화 이메일/이메일형 사용자명의 전역 소유권을 검사합니다. **OIDC는 허용된 provider의 서명·issuer/audience/subject/nonce/PKCE와 boolean `email_verified=true`를 검증한 뒤 정확한 Accounts 안의 유일한 enabled 이메일 계정에 자동 연결**하며 추가 로컬 비밀번호를 요구하지 않습니다. 전체 federation tuple과 `issuer+sub`를 보존·추가하고 fresh readback 뒤 동일 canonical user/home의 native 발급을 확인해야 `200 TokenResponse`를 반환합니다. 기존 UUID/home/password/default project·다른 metadata/연결·grant/resource는 변경하지 않습니다. 같은 email의 legacy home은 자동 선택/병합하지 않지만 stable/native tuple 소유권은 전역 검사해 다른 계정과 충돌하면409입니다. Accounts 중복409, disabled403 `account_disabled`, 변경된 email409 `account_changed`, 미확인 attachment503을 구분합니다. Plain email·문자열 `"true"`는 proof가 아닙니다.

자동 연결은 운영자 파일 registry `[auth.providers.<key>]`의 OIDC(`cfg:<key>`)에 한정합니다. Tenant manager가 관리하는 SQL provider는 같은 Accounts 이메일·기존 조직 membership이 있어도 first-link에 명시 canonical proof가 필요합니다. 조직이 주장한 verified email로 플랫폼 계정 권위를 만들지 않습니다.

Non-Accounts legacy와 GitHub의 미연결 기존 email 계정은 기존409 `{detail,code:"account_link_required",link_token,domain_id}`와 명시 연결을 유지합니다. Browser-bound ticket은600초·1회용이며 Redis에는 해시 key와 암호화한 provider proof를 저장합니다. 같은 cookie와 same-site 요청으로 다음 중 **명시적 계정 proof**를 제출합니다:

| Endpoint | 정확한 body·proof | 성공 |
|---|---|---|
| `POST /api/v1/auth/providers/link` | `{link_token,username,password}`; token16–256자, exact canonical username1–255자, password1–4096자. 실제 native home password 정책·계정 잠금 적용 | 200 ProviderLinkResponse; JWT 없음 |
| `POST /api/v1/auth/providers/link/authenticated` | `{link_token}`와 기존 canonical 계정의 access bearer; 현재 native token 재검증 및 exact user/home/email 일치 | 200 ProviderLinkResponse; 기존 세션 유지 |

각5회/분이며 extra field는422입니다. Ticket은 proof 검사 전에 소비하므로 실패 뒤 재사용하지 않고 provider 로그인을 다시 시작합니다. **계정 proof와 native attachment는 같은 identity graph lease 안에서** 수행합니다. Authenticated 연결은 현재 native token뿐 아니라 origin refresh record의 exact user/home·blacklist·`exp`·최초 `started_at` 절대 deadline도 재검사하며 없거나 만료되면401 `account_proof_invalid`입니다. 연결은 기존 user ID/home/username/email/password/default project와 다른 provider tuple을 보존하고 native user의 **전체 `federated` 배열을 PATCH**하며 `afterglow_external_identities`에 issuer/subject를 추가합니다. 직접 password proof 또는 이 검사를 통과한 **password-origin authenticated 세션**은 `afterglow_local_password=true`를 확정하지만 federated-origin proof만으로는 local-password capability를 만들지 않습니다. Exact explicit proof로 검토 가능한 untracked legacy mutable-name tuple만 교체할 수 있고 이미 기록된 stable issuer 연결은 덮어쓰지 않습니다. Exact native tuple·stable metadata readback과 provider revision 재검사를 통과해야 연결 성공입니다.

`ProviderLinkResponse={linked:true,domain_id,domain_name,provider_id}`입니다. 두 연결 API는 native federation·프로젝트 scope·provider 검증 stamp·JWT/refresh/session 발급을 하지 않습니다. 브라우저는 비밀번호·소비된 proof를 버리고 연결 완료와 `/login?reauthenticate=1` 버튼을 표시하며 초대·MCP continuation과 기존 세션은 유지합니다. 이 로그인 화면은 기존 세션이 있어도 자동 dashboard 이동을 하지 않습니다. 사용자가 시작한 **새 authorize/callback**에서 canonical native user/home·admission·현재 provider 정책을 다시 검증하고 home에 로그인한 뒤 workspace를 선택합니다. 연결 저장이 불확실하면503 `native_attachment_unconfirmed`이며 timeout·실패를 성공으로 표시하거나 소비한 요청을 자동 재전송하지 않습니다.

**계정 연결과 조직 가입은 별도**입니다. 기존 native 멤버십이 없으면 provider와 verified email host의 configured `auto_join_email_domains`가 필요하며 없으면403 `invitation_required`입니다. 허용된 조직에는 준비된 Default의 project_reader만 추가하고 manager/owner는 부여하지 않습니다. Default 부재는409 `domain_default_required`입니다. 완전히 새로운 외부 human은 승인·accounts identity-only·personal의 자동 생성 이름/direct member 프로젝트 enrollment를 거치며 provider origin 조직에 identity를 직접 생성하지 않습니다. 기존 계정의 home·password·federation tuple은 이동하지 않고, callback의 최초 native project scope는 검증된 personal primary입니다. Provider origin이나 관측 domain 자체는 조직 admission 권위가 아닙니다.

Home identity, 현재 작업 도메인, provider origin은 서로 다를 수 있습니다. Provider-origin의 허용 목록/revision/검증 email 정책을 세션 회전·refresh·작업 전환 뒤에도 유지하며 현재 작업 도메인의 email 제한도 별도로 검사합니다. Password 세션은 home password 정책을 사용합니다. Provider origin이 없는 과거 federated 세션은401 재로그인이며 현재 작업 도메인을 origin으로 추정하지 않습니다.

보안 관련 provider 편집은 revision을 올려 진행 중 state 및 provider-bound 세션을 무효화합니다. 콜백 revision 불일치는 `409 provider_changed`; refresh의 변경/비활성/삭제는 `403 provider_changed`/`provider_disabled`입니다. 표시 이름 변경만으로 revision을 올리지는 않습니다. CRUD와 성공 로그인에 의한 검증 계약은 [도메인 IAM](iam.md)을 참고하세요.

Password를 끄기 전 현재 provider revision에서 실제 native federated session 발급을 먼저 성공시켜야 합니다. 마지막 검증 provider의 보안 편집·비활성화·삭제는 password가 꺼진 동안 `409 last_login_method`로 거부됩니다. Session 저장 뒤 proof stamp 사이 revision race도 `409 provider_changed`이며 생성한 session을 revoke/delete합니다.

**브라우저 frontend와 API는 same-site여야 합니다.** Same-host는 같은 scheme/host(포트는 달라도 됨), subdomain은 정확한 configured frontend Origin과 `Sec-Fetch-Site: same-origin|same-site`가 필요합니다. Cross-site는 `503 cross_site_callback_unsupported`; CORS 허용만으로 충분하지 않고 SameSite=None으로 완화하지 않습니다. 실제 cross-site 배포는 first-party API proxy를 사용해야 합니다. 잘못된 Origin은 `403 origin_mismatch`입니다.

DomainAuthError는 `{detail: "안전한 메시지", code: "안정된 코드"}`이며 응답은 no-store/private·no-cache입니다.

| HTTP | `code` | 의미 |
|---|---|---|
| 401 | `invalid_state` | state 만료·재사용·cookie 부재/불일치 |
| 403 | `domain_disabled`, `provider_disabled`, `foreign_domain` | 도메인/provider 비활성 또는 federation identity 경계 위반 |
| 403 | `email_not_verified`, `email_domain_not_allowed`, `federation_denied` | 검증된 이메일/정책/Keystone federation 거부 |
| 404 | `domain_not_found`, `provider_not_found` | 선택 도메인/provider 없음 |
| 409 | `provider_changed` | revision 또는 discovery token endpoint 변경; 로그인부터 다시 시작 |
| 409 | `domain_ambiguous` | resolve의 중복 표시 이름; 정확한 domain ID로 다시 선택 |
| 409 | `account_link_required` | 기존 계정 proof 필요; link_token과 선택 domain_id 추가 반환 |
| 409 | `account_ambiguous`, `account_email_conflict`, `native_binding_conflict`, `account_changed` | 중복 소유권·기존 연결/계정 변경; 자동 병합 없음 |
| 401/403 | `account_proof_invalid` / `account_proof_mismatch` | password 거부 또는 다른 canonical 계정 proof |
| 401 | `invalid_link_token` | link ticket 만료·소비·browser 불일치 |
| 403 | `invitation_required`, `canonical_subject_mismatch`, `canonical_email_mismatch` | admission 부재 또는 native canonical identity/email 불일치 |
| 409 | `domain_default_required` | auto-admission 대상 Default 사전 준비 필요 |
| 503 | `native_mapping_unsafe`, `native_attachment_unconfirmed` | unsafe/unavailable stable-sub mapping 또는 native 전체 tuple PATCH readback 불확실 |
| 422 | `identity_invalid_input` | query/본문 validation 실패(비밀 입력을 반사하지 않음) |
| 429 | — | resolve30·authorize20·callback10·각 link5회/분 초과 |
| 502 | `provider_error`, `invalid_id_token` | provider 응답·code exchange·ID token 검증 실패 |
| 503 | `unavailable`, `redirect_not_configured`, `cross_site_callback_unsupported` | 저장소/Keystone 장애 또는 frontend/API 구성 불가 |

### `afterglow.conf`의 공통·도메인별 로그인 방법

`[auth.providers.<key>]`는 운영자가 관리하는 독립 공급자 레지스트리입니다. `[auth.default].allow_providers`와 `[auth.domain."<Keystone domain ID>"].allow_providers`는 **파일·SQL 공급자 모두에 적용하는 허용 목록**이며 추가 목록이 아닙니다. 도메인 키는 표시 이름이 아니라 정확한 canonical Keystone ID이며 대소문자를 변경하거나 정규화하지 않습니다. 도메인 없는 로그인 화면의 공급자 버튼은 서버가 반환한 exact origin ID를 authorize handle로 사용하며 브라우저에 별도 registry를 두지 않습니다. `openstack domain show <name> -f value -c id`로 ID를 확인하세요.

| 설정 | 유효한 선택 |
|---|---|
| `[auth]` 또는 default의 `allow_providers` 생략 | 기본은 무제한: 활성 레지스트리 공급자와 해당 도메인의 사용 가능한 SQL 공급자 모두 |
| 도메인 테이블 또는 그 `allow_providers` 생략 | default 상속 (default도 생략되었으면 무제한) |
| default의 명시적 `allow_providers = []` | 상속 도메인의 모든 federated provider 거부 |
| 도메인의 명시적 `allow_providers = []` | 해당 도메인의 모든 federated provider 거부 |
| 도메인의 비어 있지 않은 `allow_providers` | default를 **완전히 대체**; default나 SQL 목록을 뒤에 추가하지 않음 |

무제한은 native federation·enabled 상태·이메일/로그인 정책 검사를 생략한다는 뜻이 아닙니다. 레지스트리 공급자를 활성 상태로 선언하면 별도 선택 없이 모든 도메인에서 후보가 되므로 필요하면 도메인 또는 default 허용 목록으로 제한하세요. `[]`는 비밀번호 로그인을 끄는 설정이 아니며 비밀번호/회원가입/이메일 정책과 SQL 행을 수정·삭제하지 않습니다.

아래는 **서로 다른 두 GitLab OIDC application 등록**입니다. 각 issuer에 별도 client ID/secret을 발급하고 Keystone에서도 별도 native IdP와 protocol/mapping을 준비합니다. `keystone_idp_id`는 그 실제 설정과 일치해야 합니다. `<exact-...-domain-id>`는 교체용 자리표시자이며 실제 ID나 표시 이름 예시가 아닙니다. 사용할 테이블의 키를 실제 canonical ID로 바꾸세요.

```toml
[auth.providers.gitlab_com]
name = "GitLab.com"
kind = "oidc"
issuer_url = "https://gitlab.com"
client_id = "replace-with-gitlab-com-application-id"
keystone_idp_id = "gitlab_com"
keystone_protocol_id = "openid"
scopes = ["openid", "email", "profile"]
federation_token_type = "id_token"
token_endpoint_auth_method = "client_secret_basic"

[auth.providers.dmslab_gitlab]
name = "DMSLab GitLab"
kind = "oidc"
issuer_url = "https://git.dmslab.re.kr"
client_id = "replace-with-dmslab-gitlab-application-id"
keystone_idp_id = "dmslab_gitlab"
keystone_protocol_id = "openid"
scopes = ["openid", "email", "profile"]
federation_token_type = "id_token"
token_endpoint_auth_method = "client_secret_basic"

[auth.default]
# allow_providers 생략: 두 GitLab 및 해당 도메인의 eligible SQL 공급자에 무제한.
# 전역 제한이 필요할 때만 다음 줄을 사용 (SQL도 자동 추가되지 않음):
# allow_providers = ["gitlab_com", "dmslab_gitlab"]

# 선택 사항: 이 정확한 도메인에서는 DMSLab GitLab만 허용.
[auth.domain."<exact-restricted-domain-id>"]
allow_providers = ["dmslab_gitlab"]

# 선택 사항: 이 정확한 도메인에서는 federated provider를 모두 거부.
[auth.domain."<exact-no-federation-domain-id>"]
allow_providers = []

# 필드 생략은 default 상속; 이 테이블 전체를 생략해도 동일.
[auth.domain."<exact-inheriting-domain-id>"]
```

실제 비밀은 `AUTH__PROVIDERS__GITLAB_COM__CLIENT_SECRET`, `AUTH__PROVIDERS__DMSLAB_GITLAB__CLIENT_SECRET`에 각각 주입하거나 보호된 TOML의 해당 `client_secret`에 둡니다. 위 예제는 비밀을 포함하지 않으며 별도 주입 없이 활성 공급자가 시작되지는 않습니다. Nested env는 secret leaf만 교체해 issuer/client ID/선택 metadata를 유지합니다. 최상위 `AUTH` JSON은 TOML auth 객체 전체를 대체하므로 부분 secret override로 사용하지 않습니다. 공개 설정·frontend에는 비밀을 넣지 않습니다.

공급자 키는 소문자로 시작하는 최대32자의 소문자·숫자·단일 내부 밑줄입니다. 끝 밑줄이나 연속 밑줄은 nested env 경로와 충돌하므로 금지합니다. 알 수 없는 필드·레지스트리 참조, 비정규 SQL UUID, 잘못된 URL/필수 scope 및 활성 공급자의 빈 secret은 시작 단계에서 거부합니다.

허용 목록 항목은 레지스트리의 **bare key**(`gitlab_com`, `dmslab_gitlab`; 공개 ID인 `cfg:` 접두사 없이) 또는 SQL IAM 공급자의 **소문자·하이픈 포함 canonical UUID**입니다. SQL provider의 표시 이름·Keystone IdP ID를 사용하지 않습니다. 예를 들어 `allow_providers = ["dmslab_gitlab", "550e8400-e29b-41d4-a716-446655440000", "gitlab_com"]`은 파일·SQL을 섞어 그 순서대로 선택합니다. 이 UUID는 형식 설명용이며 실제 IAM 공급자의 UUID로 교체해야 합니다. SQL UUID의 존재·도메인 소속·사용 가능 여부는 런타임에 검사하므로 형식이 맞는 UUID를 적었다고 공급자가 생성되거나 다른 도메인의 공급자가 허용되지는 않습니다.

명시적 목록은 **목록 순서**대로 표시하고 중복은 최초 위치에 한 번만 표시합니다. 무제한일 때는 **레지스트리 선언 순서 → SQL name/ID 순서**입니다. `enabled = false`인 레지스트리/SQL 공급자는 허용 목록에 있어도 사용할 수 없으며 누락·비활성·다른 도메인 SQL 항목도 공개 목록에 추가되지 않습니다. SQL 장애는 파일 공급자로 우회하지 않고503입니다.

이 선택은 UI 전용 필터가 아닙니다. **resolve**의 공개 목록, **authorize**의 직접 provider ID 요청, **callback**에서 state에 묶인 공급자 재조회, **provider-bound session refresh**의 현재 공급자/정책 재검사에 모두 적용합니다. 거부된 파일 ID(`cfg:dmslab_gitlab`)나 SQL UUID를 직접 호출해도 우회하지 못합니다. Authorize의 선택 불가 공급자는 `404 provider_not_found`, callback/refresh에서 더 이상 허용되지 않거나 비활성·삭제된 공급자는 `403 provider_disabled`, revision 변경은 각 경계의 `provider_changed` 계약을 따릅니다. SQL 공급자도 예외가 아닙니다.

**호환성이 깨지는 설정 마이그레이션:** 과거 `[auth.default]`/`[auth.domain.*]`의 additive selector `providers`는 이제 알 수 없는 필드로 거부됩니다. `allow_providers`로 바꾸되 단순 이름 교체로 끝내지 말고, 각 도메인에 필요한 **전체 대체 목록**(계속 허용할 SQL UUID 포함)을 다시 작성하세요. 기존 common+domain 추가분을 유지하려면 그 합집합을 원하는 순서로 명시해야 합니다. 무제한/상속을 의도하면 필드를 생략하고, `[]`로 변환하지 않습니다. `[auth.providers.<key>]` 레지스트리와 API 응답의 `providers` 필드는 이 제거된 selector와 별개로 유지됩니다.

GitLab은 OIDC issuer의 discovery를 사용합니다. `authorization_url`, `token_url`, `api_url`을 OIDC에 직접 넣지 않습니다. GitHub는 public 기본 endpoint 또는 HTTPS enterprise endpoint를 사용하며 `read:user`/`user:email`, access-token federation과 `client_secret_post`가 기본입니다. OIDC는 `id_token`/`client_secret_basic`가 기본이며 공급자에 맞춰 `federation_token_type`, `token_endpoint_auth_method`를 명시할 수 있습니다. 기존 HTTPS/DNS-pinning·verified email·native domain/IdP/protocol 검증은 두 설정 경로에 동일하게 적용됩니다.

레지스트리 선언만으로 Keystone federation이 생성되지는 않습니다. Keystone IdP/protocol/mapping과 **각** upstream application의 `<app.frontend_base_url>/auth/callback` 등록을 먼저 준비해야 합니다. Afterglow용 native mapping은 **stable subject를 `user.id`로 사용하는 user-only ephemeral mapping**이어야 하며 email 덮어쓰기·groups/projects/roles provisioning은 금지합니다. 이는 Keystone 자체의 project auto-provisioning 기능 부재가 아니라 canonical 계정·승인·개인 quota·조직 admission을 우회하지 않게 하는 Afterglow 경계입니다. `preferred_username`/email/name을 identity key로 쓰지 않습니다. Callback과 link는 native exchange 전에 mapping을 검사하고 unsafe/조회 불가는503 `native_mapping_unsafe`로 거부합니다. Native Keystone은 기존 local user에 full federated tuple을 PATCH하고 그 tuple로 동일 canonical ID/home을 발급할 수 있어야 합니다. 상세 설치·연결 책임과 cutover 전제는 [배포 가이드](../deployment.md#native-keystone-선행-조건)를 따릅니다.

구형 `[gitlab_oidc]`와 frontend의 같은 이름 플래그는 현재 공급자 레지스트리를 구성하지 않습니다. 기존 등록을 이관할 때는 client ID/secret을 보호된 `[auth.providers.<key>]`로 옮기고, `gitlab_url`은 discovery 응답과 정확히 같은 `issuer_url`로, `idp_id`/`protocol_id`는 `keystone_idp_id`/`keystone_protocol_id`로, 공백 구분 scope 문자열은 배열로 바꿉니다. 콜백은 과거 `/auth/gitlab/callback`이 아니라 `/auth/callback`입니다. Provider를 작업 도메인에 노출한다고 계정 home이 바뀌지 않습니다. 기존 mutable-username native 연결과 중복 이메일 계정은 운영자가 exact user ID·issuer/sub·IdP/protocol tuple·현재 grant/소유권을 검토해 명시적으로 이관해야 하며 자동 merge/reset하지 않습니다.

운영자 파일 공급자는 같은 issuer/application의 서로 다른 native protocol/mapping을 별도 인스턴스로 등록해 도메인별로 선택할 수도 있습니다. Native 결과는 **선택한 작업 도메인이 아니라 연결된 canonical 계정의 실제 home**과 일치해야 합니다. IdP의 default domain만 보고 성공을 단정하지 않으며 Apache의 서명 bearer 검증과 stable subject 전달을 설치된 Keystone에서 확인해야 합니다. 다른 도메인의 관리 그룹/역할을 mapping에서 자동 부여하지 않습니다. Callback 이관도 기존 다른 application 용도를 보존한 채 필요한 정확한 origin/path만 등록합니다.

파일 공급자의 공개 ID는 `cfg:<key>`입니다. SQL IAM 공급자 CRUD로 파일 항목을 편집하지 않으며 config/Secret/허용 목록 수정 후 artifact를 재생성·적용하고 모든 API·worker를 재시작합니다. 보안 필드·secret 변경은 state/세션 revision을 바꾸고 표시 이름만 바꾸는 것은 기존 세션을 유지합니다. 파일 공급자의 로그인 성공은 SQL provider의 검증 stamp가 아니므로 IAM에서 마지막 검증 공급자를 제거하거나 비밀번호를 끄는 근거로 사용하지 않습니다.

### 전역 signup과 provider별 자동 가입 설정

```toml
[auth]
public_signup_enabled = false
signup_email_domains = ["example.org"] # []는 전역 signup host 제한 없음

[auth.default.auto_join_email_domains]
dmslab_gitlab = ["example.org"]

[auth.domain."<exact-team-domain-id>"]
allow_providers = ["dmslab_gitlab"]
auto_join_email_domains = {} # 이 작업 도메인에서는 자동 가입 전부 거부
```

`auto_join_email_domains`는 bare registry key 또는 canonical SQL provider UUID → exact email-host 배열 map입니다. 도메인의 map 생략은 default 상속, 명시 map은 **전체 대체**, `{}`·누락 provider·빈 배열은 자동 가입 없음입니다. Default도 생략하면 자동 가입은 기본 거부입니다. `allow_providers`와 독립 설정이므로 provider가 허용/활성이지 않으면 사용할 수 없습니다. Host는 wildcard·`@` 없이 exact IDNA lowercase ASCII, 최대100개·중복제거·정렬이며 하위 도메인을 암묵 허용하지 않습니다. 이것은 **조직 admission**이며 Accounts OIDC 자동 연결 또는 legacy 명시 proof와 별개입니다. Stable issuer/sub를 이전하거나 manager/owner를 만들지 않고 prepared Default reader만 부여합니다. 기존 native membership에는 새 auto-join 허가가 필요하지 않지만 provider/login 정책은 계속 적용합니다.

전역 `signup_email_domains`도 같은 exact-host normalization/최대100개를 사용하지만 빈 배열 의미는 **제한 없음**입니다. Public signup opt-in과 이 allowlist는 SQL domain 정책과 별도이며, API/worker 재시작을 동반하는 같은 operator 설정 경로를 사용합니다. 설정 변경·생성 경로·migration096/097 및 native prerequisite는 [배포 가이드](../deployment.md#canonical-계정공개-가입복구-cutover)를 따릅니다.

파일 OIDC discovery 목적지는 issuer/client-ID/secret의 keyed fingerprint별로 Redis의 `afterglow:domain_auth:config_binding:`에 최초 고정합니다(TTL 없음). **TTL이 없다는 것은 영속성 보장이 아닙니다.** Pin이 존재하는 동안 이후 authorization/token/JWKS/UserInfo 목적지 변경은 같은 자격으로 따라가지 않고409 `provider_changed`를 반환합니다. Redis eviction·flush·데이터 유실 또는 이전 snapshot 복원으로 pin이 사라지면 다음 discovery가 같은 자격에 새 pin을 만들 수 있어 이전 목적지와의 비교를 잃는 **잔여 위험**이 있습니다. 저장소 접근 실패는503이지만 사라진 pin과 최초 등록은 구분하지 못합니다. 합법적인 목적지 변경에도 새 secret을 배포해야 하며 pin 삭제나 Redis 유실을 변경 승인 수단으로 쓰지 않습니다. 이 키는 로그인 proof·회원가입·권한 부여가 아니며 원본 secret을 저장하지 않습니다. K8s/Helm의 비밀 분리·생략 보존·적용 절차는 [배포 가이드](../deployment.md#공통도메인별-로그인-공급자)를 따릅니다.

### 설정만으로 로그인 연결 추가

`Default`, `dmslab`, GitLab 주소와 공급자 표시 이름은 인증 분기 조건이 아닙니다. 레지스트리 키는 인스턴스 ID이고 `kind`는 구현된 wire protocol입니다. UI는 resolve 응답의 ID/이름을 그대로 표시하며 모든 인스턴스가 같은 authorize와 `/auth/callback`을 사용합니다. 지원되는 `oidc` 또는 `github` 인스턴스 추가에는 애플리케이션 소스·이미지 수정이 필요하지 않습니다.

1. OIDC issuer 또는 GitHub application과 native Keystone IdP/protocol/mapping을 준비합니다. 각 upstream application에 실제 `<app.frontend_base_url>/auth/callback`을 등록합니다.
2. `[auth.providers.<새 키>]`에 표시 이름, kind, issuer/client와 native IdP/protocol을 적고 대응하는 Secret을 주입합니다. OIDC 호환 공급자는 vendor 이름 대신 `kind = "oidc"`와 실제 discovery issuer를 사용합니다. GitHub는 `kind = "github"`이며 enterprise endpoint는 기존 HTTPS 설정 필드로 지정합니다.
3. 필요한 exact-domain `allow_providers`에 새 키를 추가합니다. 비어 있지 않은 목록은 전체 대체 목록이므로 기존에 계속 허용할 키/SQL UUID도 남깁니다. 다른 도메인에서 후보가 되지 않아야 하면 default를 `[]`로 두고 각 도메인을 명시합니다.
4. 사용 중인 배포 경로의 Config/Secret을 갱신하고 모든 API·worker를 재시작합니다. 파일 수정만으로 hot reload되지 않습니다. Resolve의 실제 공개 목록, authorize의 issuer/callback과 실제 사용자 callback·native session을 순서대로 확인합니다. 새 키 추가는 기존 인스턴스의 보안 설정을 바꾸지 않으며 기존 pending login/세션 revision을 일괄 변경하지 않습니다.

같은 issuer/application을 두 작업 도메인에서 사용하되 native mapping이 다르면 **별도 인스턴스**로 선언합니다. 아래 두 OIDC 인스턴스는 같은 client 자격을 사용하지만 protocol을 각각 선택하며, 두 번째 도메인에는 독립 GitHub 옵션도 추가합니다. 실제 native ID·protocol·client 값으로 교체하고 각 키의 `AUTH__PROVIDERS__<대문자 키>__CLIENT_SECRET`을 주입해야 합니다. Secret alias/상속 규칙은 없습니다.

```toml
[auth.providers.organization_home]
name = "Organization SSO"
kind = "oidc"
issuer_url = "https://login.example.org"
client_id = "replace-with-organization-application-id"
keystone_idp_id = "organization"
keystone_protocol_id = "home_oidc"

[auth.providers.organization_team]
name = "Organization SSO"
kind = "oidc"
issuer_url = "https://login.example.org"
client_id = "replace-with-organization-application-id"
keystone_idp_id = "organization"
keystone_protocol_id = "team_oidc"

[auth.providers.code_host]
name = "GitHub"
kind = "github"
client_id = "replace-with-github-application-id"
keystone_idp_id = "github"
keystone_protocol_id = "oauth2"

[auth.default]
allow_providers = []

[auth.domain."<exact-home-domain-id>"]
allow_providers = ["organization_home"]

[auth.domain."<exact-team-domain-id>"]
allow_providers = ["organization_team", "code_host"]
```

이 설정은 Keystone mapping·membership을 생성하지 않습니다. 같은 issuer/표시 이름이어도 인스턴스를 합치지 않으며 native 결과의 실제 user ID/home이 canonical 계정과 다르거나 반환된 federation IdP/protocol이 선택과 다르면 callback을 거부합니다. SAML 또는 임의 OAuth 방식은 새 `kind` 문자열이나 endpoint 설정만으로 지원되지 않으며 별도의 검증 구현이 필요합니다.


## 공개 이메일 검증 onboarding

초대 생성·목록·회수는 [도메인 IAM](iam.md)의 domain-manager 전용 API입니다. 프로젝트 owner/admin의 eligible joined-user 역할 변경과 email 도메인 초대는 다릅니다. 아래는 `/api/v1/auth` 기준이며 accept-existing만 access bearer를 요구합니다. 임의 email·user ID·가입 target domain을 수락 본문에 넣을 수 없습니다.

| 메서드·경로 | 정확한 본문 | 성공 | 제한 |
|---|---|---|---|
| `GET /signup/options` | 없음 | 200 `{signup_enabled,smtp_configured,recovery_enabled,approval_mode}` | 20회/분 |
| `POST /registrations` | `{email}` | 202 `{accepted:true}` | 3회/분 |
| `GET /registrations/{token}` | 없음 | 200 `{email,account_exists,identity_domain_id?,identity_domain_name?}` | 20회/분 |
| `POST /registrations/accept` | `{token,name,password}` | 200 EnrollmentResult | 5회/분 |
| `POST /domains/{domain_id}/registrations` | `{email}` | **항상403** `{detail:"invitation_required"}` | 3회/분 |
| `GET /invitations/{token}` | 없음 | 200 `{email,account_exists,identity_domain_id?,identity_domain_name?,domain_id,domain_name,expires_at,project_name}` | 20회/분 |
| `POST /invitations/accept` | `{token,name,password}` | 200 EnrollmentResult | 5회/분 |
| `POST /invitations/accept-existing` | `{token}` | 200 EnrollmentResult | 5회/분 |

전역 signup enabled는 시스템 관리자의 persisted enrollment policy를 우선하며 최초 정책 row 부재에서만 `[auth].public_signup_enabled`(기본false)를 사용합니다. `signup_email_domains`(기본[]; 비어 있으면 host 제한 없음)는 설정의 exact host 제한입니다. 옵션의 SMTP/recovery readiness는 SMTP enabled/host/from-address와 frontend base URL의 **구성 여부**이며 실제 배달 증거가 아닙니다. Signup flag는 그 readiness와 공개 opt-in의 conjunction입니다. 요청 시 signup 비활성403 `signup_disabled`, readiness 부재503 `smtp_not_configured`, host 위반403 `email_domain_not_allowed`입니다. 수락에서도 현재 정책을 다시 확인합니다. SQL domain `signup_enabled/signup_email_domains`는 전역 signup이나 임의 작업 도메인 가입 권한을 대신하지 않습니다.

Email-first 요청은 기존 계정 여부를 조회하지 않고 같은 검증 메일을 전송하며 native account/project/grant를 만들지 않습니다. SMTP 실패는503이고 redeemable 링크를 발급한 성공으로 표시하지 않습니다. 계정 존재/home 안내는 전달된 비밀 링크를 가진 조회자에게만 반환합니다. 등록 조회는 token을 소비하지 않습니다. 중복 email 소유권은409 account_email_ambiguous이며 새 username은 전역 native username/email login alias와도 충돌할 수 없습니다. 기존 계정이면 로그인/복구 후 초대를 수락하고 신규 계정을 만들지 않습니다. 공개 가입은 accounts identity와 personal primary만 만들며 기존 조직에 직접 가입시키지 않습니다.

`approval_mode=admin`이면 verified 신규 email의 링크 조회/수락과 신규 초대 계정, fresh OIDC/GitHub 가입은 native 생성 전에403 `signup_approval_pending`으로 멈춥니다. 거절은403 `signup_approval_rejected`, 이미 소비된 승인 재사용은409 `signup_approval_consumed`입니다. 대기 중 password·OAuth code·세션은 보관하거나 자동 재전송하지 않습니다. 관리자는 [가입 정책·승인 API](admin.md#가입-정책개인-도메인-quota와-승인-대기열)에서 결정합니다. 공개 email 승인은 새 검증 메일로 계속하며 공개 가입이 꺼진 초대 가입은 원래 초대의 GET 재조회 버튼으로 새 빈 입력 화면을 엽니다. Provider는 승인 후 새 로그인부터 시작합니다. 기존 계정의 초대 수락/로그인은 신규 승인 대상이 아니며 ID/home을 유지합니다.

`EnrollmentResult={user_id,domain_id,domain_name,identity_domain_id,identity_domain_name,personal_domain_id,personal_project_id,personal_project_name}`입니다. 신규 계정의 domain_id/domain_name은 personal, identity_domain_id/identity_domain_name은 accounts이고 personal_domain_id는 working domain과 같습니다. 초대 target 조직은 원래 invitation 조회/요청 문맥에 보존하며 개인 생성 결과를 target 조직으로 오해하면 안 됩니다. 기존 계정 수락은 원래 identity를 유지합니다. Token32–256자, name1–255자·앞뒤 공백 금지, password12–1024자, email3–255자이며 personal_domain_name을 포함한 extra field는422입니다. 개인 프로젝트 이름은 정규화 username 최대47자+하이픈+암호학적 임의 소문자8자+숫자8자리로 최대64자입니다. 등록 링크는1시간·1회용, 초대 expiry는 SMTP 설정이며 SHA-256 해시만 저장합니다. 수락은 JWT를 발급하거나 기존 세션을 자동 전환하지 않습니다.

신규 human은 accounts user와 personal project를 disabled로 준비한 뒤 본인 직접 native member 하나, raw/effective 사용자·scope·role-ID provenance, 동결된 project quota update/readback을 확인하고 활성화합니다. 개인 owner/admin/reader·manager·Default·공유 domain budget은 자동 생성하지 않습니다. Email 계정만 password를 가지며 external-only에 로컬 password를 만들지 않습니다. 명시적 초대에만 target 조직 Default reader와 선택 project safe role을 추가하고 target Default 부재는409 domain_default_bootstrap_required입니다. Trusted OIDC 조직 admission도 별도 정책을 통과해야 하며 provider origin만으로 가입하지 않습니다. 관리자 생성의 선택 domain은 admission이 아닙니다. 기존 계정 accept-existing은 enabled 본인·global unique email 일치와 보호 정책을 확인하고 user ID/home/email/password를 유지합니다. Service/privileged IAM 보호도 유지합니다.

기타 실패는403 정책/초대자 권한 회수/계정 보호,404 링크 없음,409 계정/role·동시 변경,410 만료·회수·소비·수락 불가,422 입력,429 rate limit,503 SMTP/native/storage입니다. 응답은 no-store/private·no-cache·no-referrer입니다. Native intent 이후 실패는 operation ID와 failed/recovery_required journal을 남기며 링크·unknown native create를 replay하지 않습니다. 정리는 이번 작업의 grant와 exact provenance의 새 empty project/account에 한정하고 공유 account/personal domain이나 기존 identity를 삭제·이동·reset하지 않습니다. Enrollment와 별도 topology intent는 [관리자 복구 API](admin.md)로 명시 settlement하며 원래 native call 종료 여부를 확인해야 합니다.

브라우저의 기존 계정 수락은 시작 시점의 session ID·user ID·identity domain·working domain·project ID와 invitation token/화면 generation을 캡처합니다. Auth 준비 전·logout/project 전환 중에는 수락을 차단하고, account/domain/project/session 변경 또는 화면 이탈 뒤 도착한 성공·오류·finally 결과를 폐기합니다. 중간 변경 후 같은 scope로 돌아온 ABA도 generation으로 구분합니다. 일반 refresh의 token 문자열 변경만으로는 session owner를 바꾸지 않습니다. 수락 POST는 no-store와 `replayOnUnauthorized:false`로 보내며401 뒤 자동 refresh/replay하지 않습니다. 늦은 응답을 UI에서 버렸다는 사실은 이미 시작된 서버의 durable enrollment가 취소됐다는 뜻이 아닙니다.

## 이메일 소유 기반 계정 복구·프로필 이메일 변경

모든 경로는 `/api/v1/auth` 기준입니다. Public username/password 복구는 email만 받으며 domain이나 username을 추가 입력받지 않습니다. JSON body의 extra field는 금지합니다.

| 메서드·경로 | 정확한 요청 | 성공 | 제한 |
|---|---|---|---|
| `POST /recovery/username` | `{email}` | 202 `{accepted:true}` | 3회/분 |
| `POST /recovery/password` | `{email}` | 202 `{accepted:true}` | 3회/분 |
| `GET /recovery/{token}` | 없음 | 200 `{kind,email,identity_domain_id,identity_domain_name,username?}` | 20회/분 공유 |
| `POST /recovery/password/complete` | `{token,new_password}` | 200 `{status:"changed"}` | 5회/분 |
| `POST /email/changes` | access bearer + `{email,current_password}` | 202 `{accepted:true}` | 3회/분 |
| `POST /email/changes/accept` | `{token}` | 200 `{status:"changed"}` | 5회/분 |

Email3–255자, token32–256자, new_password12–1024자, current_password1–1024자입니다. 공개 요청은 유효한 email에 대해 계정 부재·중복·부적격·SMTP 비활성/실패·DB/Redis/native 장애·주소 budget 초과에도 **같은202**이며 계정 존재/home/username/token을 노출하지 않습니다. 잘못된 입력은422, IP route limit은429입니다. 주소별 SHA-256 Redis key의60초 budget은 username/password 종류 및 출처 IP 사이에 공유됩니다. 이202는 메일 발송/수신 성공 확인이 아닙니다.

대상은 global unique email을 가진 enabled native local-password 계정 및 enabled home입니다. **사람의 manager/system admin도 복구 가능**하며 그 권한만으로 제외하지 않습니다. 설정된 operational `os_username`, 실제 effective `service` 역할, external-only 계정은 제외합니다. 명시적 `afterglow_local_password=true`가 있으면 linked federated 계정도 가능하고, 과거 marker 없는 계정은 native `federated` 연결이 없어야 합니다. 복구가 external-only 사용자에게 password를 새로 만드는 우회가 되지 않습니다.

Proof는 `/recover/{token}` 메일 링크로만 전달하며 SHA-256 해시와 exact user ID/home/original native email·kind·상태를 SQL에 저장합니다. 수명은 발급부터 **1시간·1회용**이고 전달 완료 `pending`만 사용할 수 있습니다. 조회 시에도 enabled/local eligibility·현재 original email·global unique 소유권을 다시 검사합니다. Username kind의 GET은 그 자리에서 소비하고 username을 반환합니다. Password/email_change kind 조회는 소비하지 않으며 username을 포함하지 않습니다.

프로필 변경 요청은 현재 bearer의 **실제 home 계정에 current_password 재인증** 후 기존/신규 email의 global 유일성과 home email 정책을 검사합니다. 기존 주소에 token·신규 주소 없는 알림을 먼저 전달하고, 성공한 경우에만 신규 주소로 proof를 보냅니다. 어느 전달이 실패해도 redeemable proof가 되지 않습니다. `/api/v1/profile`의 일반 PATCH는 다른 email이면409 `{detail:"email_verification_required"}`로 거부하며 직접 변경하지 않습니다. 기존과 같은 email만 보내고 다른 metadata가 없으면 변경할 항목 없음400입니다.

Password/email 변경은 graph lease → SQL proof row lock 아래 session 저장소 readiness를 먼저 확인하고, **native 쓰기 전에** proof를 `dispatching`으로 commit하면서 같은 사용자의 다른 pending password/email-change proof를 `superseded`로 만듭니다. 성공뿐 아니라 거부·timeout·취소·process death도 같은 proof를 재실행하지 못합니다. Native rollback/replay는 하지 않습니다. 실패/불명확 결과에도 Afterglow의 캡처된 session family와 native subject token을 회수하고 authority cache를 무효화합니다. Browser 세션의 원자적 제거와 native revoke의 완료는 별개입니다. Strict 회수는 모든 captured token을 시도한 뒤 실패를 반환하며 이미 삭제한 세션은 복원하지 않습니다.

| HTTP | `{detail:{code}}` | 의미 |
|---|---|---|
| 401 | `password_rejected` | 이메일 변경 current password 거부 |
| 403 | `recovery_ineligible` | 이메일 변경의 본인/local-password/operational 보호 위반 |
| 409 | `email_in_use`, `email_unchanged` | global email 충돌 또는 같은 주소 |
| 410 | `recovery_invalid` | 없는·만료·소비·전달 실패·다른 kind·현재 binding 부적합 proof |
| 422 | `invalid_email`, `invalid_password` | 서비스 입력 검증; body 검증은 `{detail:"Invalid IAM request"}` |
| 502 | `recovery_outcome_unknown` | native 쓰기 실패/결과 불명; journal `outcome_unknown`, token 재사용 금지 |
| 503 | `recovery_unavailable`, `recovery_sessions_failed` | 재인증 장애 또는 쓰기 후 session/native 회수 불완전; 후자는 journal `sessions_failed` |

Email 정책 오류는 기존 IAM `{detail:"..."}` 형식을 유지하고 기타 native/storage 오류는 공통 IAM 경계를 따릅니다. 모든 복구 응답(429 포함)은 no-store/private·no-cache·no-referrer입니다. `dispatching/outcome_unknown/sessions_failed`는 운영자가 exact native 결과와 회수를 조사할 증거이며 성공/reset/replay로 자동 변환하지 않습니다. Native revoke는 authenticated operator로 **캡처한 토큰 하나씩** 수행합니다. 토큰 endpoint의 정확한 native404 `Failed to validate token` 또는 `Could not recognize Fernet token`만 이미 무효화됨으로 수용하고 일반 proxy/directory/endpoint404·권한·연결 오류는 완료 증거가 아닙니다. 이는 모든 Keystone 토큰·application credential 또는 외부 IdP 세션 전체를 회수했다는 보장이 아닙니다.

이 문서는 현재 source 계약이며 운영 배포·실제 mailbox 수신·최종 real GitLab/native acceptance를 주장하지 않습니다. Schema096/097·native mapping과 tuple PATCH·기존 중복의 검토된 이관이 선행되어야 합니다.



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

### 관측된 클라이언트와 연결 제거

두 목록 GET은 `Cache-Control: no-store`/`Pragma: no-cache`와 각 grant의 `client_observations` 배열을 반환합니다. 현재 로그인 사용자와 발급 당시 anchor project의 소유 범위만 조회하며, 다른 프로젝트 실행 허용 목록을 사용자 목록 소유권으로 바꾸지 않습니다. 관측이 없는 기존/새 grant는 빈 배열입니다.

| 관측 field | 의미 |
|---|---|
| `client_name`, `client_version` | 정제한 클라이언트 신고 값; 없거나 안전하지 않으면 null |
| `product`, `kind` | 고정 product label 또는 null, browser/agent/bot/sdk/unknown 추정 |
| `identity_source` | client_info/user_agent/unknown: 제품·종류 추정 근거 |
| `browser`, `os` | User-Agent에서 추정한 고정 label 또는 null; raw UA/IP는 없음 |
| `first_seen_at`, `last_seen_at` | 해당 정제 서명의 처음/마지막 성공 initialize 관측 UTC 시각 |

최근10개 서로 다른 관측만 유지하고 반복 초기화는 첫 시각을 보존해 마지막 시각을 갱신합니다. 이는 실제 단말/세션 목록이나 실시간 접속 상태가 아닙니다. `clientInfo`/User-Agent는 위조 가능하므로 실제 제품 인증이나 인가 판단 근거로 사용하지 않습니다. 내부 서명·Authorization·token/hash·upstream credential·capabilities는 응답에 포함하지 않습니다.

화면의 **연결 제거**는 위 기존 DELETE를 호출해 해당 OAuth grant/API 키 전체를 철회합니다. 같은 자격을 공유하는 모든 클라이언트와 선택된 Lumen 기본 위임에도 영향을 줍니다. 관측 행이나 User-Agent만 차단하는 방식은 아닙니다. 실패한 목록은0개로 표시하지 않으며 다른 방식의 성공 목록과 독립적으로 재시도합니다. Refresh·actor/project/method 변경 뒤 이전 confirmation은 실행할 수 없습니다.

Migration087을 reader/writer 배포 전에 적용해야 합니다. 기존084–086 이전 스키마도 먼저 동기화해야 하며 `project_scope` 누락SQL1054를 빈 목록/0개로 숨기지 않습니다. 공유/운영 DB 자동 변경은 없고 schema-before-writer rollout은 별도 운영 절차입니다.

MCP의 cloud tool은 이 application credential의 원래 scope로 인증하며 별도 project scope를 요청하지 않습니다. Keystone token의 user/project가 저장된 grant principal과 정확히 일치해야 provider에 요청하고, 다른 owner/project 또는 unscoped 응답은 거부합니다. Manager/admin/browser credential로 fallback하지 않습니다. 연결 확인의 handshake·tools/list 성공은 실제 cloud `tools/call` 성공과 별개의 증거입니다.

생성은 실제 대상 scoped token의 role ID/name을 저장하고 Keystone payload의 `roles`를 생략합니다. 이는 token 역할을 사용하는 native 기본값이며 읽기/관리 권한 확대가 아닙니다. Role 이름을 명시해 현재 inference 그래프를 재확장하면 token에 없는 역할 때문에 유효한 승인도 Keystone400으로 실패할 수 있습니다. 반환 role ID 집합이 승인 snapshot과 다르면 remote ID를 먼저 기록한 상태에서 credential을 폐기·확인하고 grant activation/token 발급을 거부합니다. Restricted flag, finite expiry, owner/project 및 승인된 target 검증은 유지됩니다.

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

정확한 `/oauth/mcp/authorize`는 공개 브라우저 동의 shell이며 protected console 전체를 공개하지 않습니다. 불투명 ticket은 URL에서 제거해 `sessionStorage`에만 보존하고 password/provider login·프로젝트 선택 뒤 같은 동의 화면으로 돌아옵니다. Ticket은 권한이나 access token이 아닙니다. 동의 조회·approve/deny는 현재 browser access bearer와 `X-Project-Id`가 있는 scoped session에서만 수행합니다. 승인은 해당 user/project의 restricted application credential과 grant를 만들며 클라이언트에는 opaque access/refresh token만 반환하고 upstream credential은 보내지 않습니다.

Restricted credential은 대상 프로젝트에 scoped된 실제 SDK token의 role ID/name snapshot을 사용합니다. 생성 payload의 `roles`를 생략하여 Keystone의 token-role 기본값을 적용하고 `unrestricted=False`와 기존 UTC `Z` 만료를 유지합니다. 역할 이름을 명시하면 현재 role-inference 그래프가 token에 없는 descendant까지 재확장하여 `Cannot create an application credential with unassigned role`로 거부할 수 있습니다. 반환 credential의 정확한 project ID와 role ID 집합이 승인 snapshot과 일치하지 않으면 활성화하지 않습니다. Remote ID를 SQL에 먼저 commit하므로 검증 실패도 기존 내구성 cleanup 경로로 회수하며 privileged credential이나 다른 프로젝트로 대체하지 않습니다.

Restricted credential은 대상 프로젝트에 scoped된 실제 SDK token의 role ID/name snapshot을 사용합니다. 생성 payload의 `roles`를 생략하여 Keystone의 token-role 기본값을 적용하고 `unrestricted=False`와 기존 UTC `Z` 만료를 유지합니다. 역할 이름을 명시하면 현재 role-inference 그래프가 token에 없는 descendant까지 재확장하여 `Cannot create an application credential with unassigned role`로 거부할 수 있습니다. 반환 credential의 정확한 project ID와 role ID 집합이 승인 snapshot과 일치하지 않으면 활성화하지 않습니다. Remote ID를 SQL에 먼저 commit하므로 검증 실패도 기존 내구성 cleanup 경로로 회수하며 privileged credential이나 다른 프로젝트로 대체하지 않습니다.

Refresh의 필수 `client_id`는 최초 authorization code의 client와 정확히 일치해야 합니다. 빈 값·다른 client·불명확한 persisted binding은 `invalid_grant`이며 token rotation이나 replay revocation을 일으키지 않습니다. `client_id` 생략도 거부하고 올바른 client의 consumed refresh 재사용은 기존 family/grant 폐기를 유지합니다. Binding은 consumed code row에 남으므로 code expiry·authorization ticket cleanup 뒤에도 유지됩니다. 계정의 OAuth 회수 또는 resource의 revoke endpoint는 기존 내구성 cleanup 경로로 grant/family와 downstream authority를 폐기합니다. Token·code·ticket·upstream secret은 문서·audit·QA receipt에 기록하지 않습니다.

SDK 내부 cold schema-cache refresh의 `list_tools(None)`은 현재 principal에게 허용된 전체 schema를 반환합니다. 외부 `tools/list` 요청은 기존 page-size와 grant-bound cursor를 유지하고, SDK input/output validation과 모든 `tools/call`의 현재 principal 권한·strict arguments·mutation ledger를 그대로 적용합니다. Manage schema가 cache에 있어도 read grant가 mutation을 실행할 수 없습니다. 실제 tool 성공은 HTTP200뿐 아니라 `isError=false`와 typed 결과를 확인해야 하며, 위 연결 확인의 handshake·목록 성공으로 대신하지 않습니다. OAuth 세부 안전 계약은 [보안 가이드](../security.md#mcp-oauth와-개인-api-키)를 따릅니다.

### 브라우저 세션 보안 패치 호환성

Login 시 최초 started_at을 기록하며 refresh/project rescope가 이 시간을 변경하지 않습니다. 만료 후 반복 요청도 401이고, 동시 refresh/rescope는 Redis 원자적 소비로 하나만 성공합니다. Provider login도 요청 origin/device를 기록하고, 출처가 없는 과거 세션은 strict/subnet에서 재로그인이 필요합니다. Logout 폐기 실패는 503이며 브라우저는 로컬 정리와 서버 폐기 확인을 구분합니다.

JWT는 탭 sessionStorage에만 저장합니다. 구형 localStorage 자격은 제거하므로 적용 뒤 한 번 재로그인이 필요하고 새 탭은 독립 인증합니다. 탭 복제는 브라우저 정책에 따라 자격을 복사할 수 있습니다. CSP의 script nonce/hash 정책은 JavaScript-readable 자격을 HttpOnly로 바꾸는 것은 아닙니다.
