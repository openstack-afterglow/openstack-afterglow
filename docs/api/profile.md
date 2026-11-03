---
title: 프로필 (Profile)
parent: API 레퍼런스
nav_order: 11
---

# 프로필 (Profile) API

> 태그: `profile`
> 기본 경로: `/api/v1/profile`

현재 로그인한 사용자 본인의 프로필 조회·수정, 기존 로컬 비밀번호 변경, 조건부 최초 로컬 비밀번호 생성, 활동 로그 조회를 제공합니다.
모든 엔드포인트는 [인증](auth.html)이 필요합니다.

---

## 인증 헤더

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Authorization` | 예 | `Bearer <access_jwt>` |
| `X-Project-Id` | 아니오 | 처리 대상 프로젝트 UUID |

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/profile` | 본인 프로필 조회 |
| `PATCH` | `/api/v1/profile` | 본인 프로필 수정 (이름·이메일·설명·기본 프로젝트) |
| `POST` | `/api/v1/profile/password` | 비밀번호 변경 (5회/분) |
| `GET` | `/api/v1/profile/password/capability` | 표시용 비밀번호 기능 상태 (`change`·`create`·`unavailable`) |
| `POST` | `/api/v1/profile/password/create/request` | 본인의 등록 이메일로 최초 생성 증명 발급 (3회/분) |
| `POST` | `/api/v1/profile/password/recovery/request` | 본인 등록 메일로 기존 비밀번호 복구 또는 SSO 최초 생성 링크 요청 (3회/분) |
| `POST` | `/api/v1/auth/recovery/password/create/complete` | 일회용 이메일 증명과 새 외부 로그인 세션으로 최초 생성 (5회/분) |
| `GET` | `/api/v1/profile/activity` | 본인 활동 로그 조회 (cross-project) |
| `GET` | `/api/v1/profile/image` | 본인 사진 선택·표시 데이터 조회 (private, no-store) |
| `PUT` | `/api/v1/profile/image` | Gravatar 선택 또는 새 아바타 생성·저장 |
| `PUT` | `/api/v1/profile/image/upload` | bounded raw raster 업로드·정규화·저장 |
| `GET` | `/api/v1/profile/login-preference` | 본인 로그인 작업공간 선호 조회 (private, no-store) |
| `PUT` | `/api/v1/profile/login-preference` | `{remember_last_workspace:boolean}` 저장; target은 현재 검증된 scope에서 서버가 결정 |
| `GET` | `/api/v1/profile/email-notifications` | 현재 immutable user/home의 이메일 알림 선호 조회 |
| `PUT` | `/api/v1/profile/email-notifications` | `{announcements:boolean,resource_alerts:boolean}` strict 저장 |

---
## 이메일 알림 선호

계정 **프로필 → 이메일 알림**에서 공지·리소스 알림을 선택합니다. `GET/PUT /api/v1/profile/email-notifications`는 현재 검증된 user/home만 사용하며 다른 사용자 ID·email·home을 지정하지 못합니다. 기본은 `announcements:true, resource_alerts:false`이고 public/no-cache 데이터가 아니라 private/no-store 응답입니다.

공지는 관리자 명시 이메일 요청과 global announcement policy, 현재 audience 접근·사용자 선호를 모두 따릅니다. Resource alert는 global gate와 본인 opt-in이 모두 필요하고 미래의 safe failure event 및 현재 VM 오류·native quota 임박/가득 참·사용기간 알림을 전달합니다. Opt-in 시각 전에 일어난 event를 새 구독의 history mail로 재발송하지 않고, 권한/home/email 변경이나 opt-out은 아직 pending인 delivery를 거부합니다. 이미 SMTP에 접수된 메일은 회수하지 못합니다. 명시적인 개별 관리자 메시지는 일반 알림 opt-out과 독립입니다.

## 로그인 작업공간 선호

기본 `{remember_last_workspace:false}`는 관리자도 자신의 verified personal primary로 로그인합니다. PUT true는 현재 활성·접근 가능한 domain/project를 fresh native 확인한 뒤 exact user+immutable home별 Redis에 저장합니다. 임의 target/user/home 필드는422이고 프로젝트 없는 상태는409입니다. 이후 성공한 scope publication만 활성 선호의 pair를 갱신하며 opt-out을 atomic하게 보존합니다. 다음 password/provider 로그인에서 저장 pair를 다시 검증하고 철회·삭제·비활성은 personal fallback, directory/Redis 장애는503입니다. 선호는 권한이 아니며 Redis persistence/복구 정책에 따라 보존됩니다. False 저장은 선택 프로젝트 접근을 잃은 뒤에도 가능합니다.


## GET /api/v1/profile

현재 인증된 사용자의 상세 프로필을 반환합니다.

### 응답 (200 OK)

```json
{
  "id": "uuid-string",
  "name": "user-name",
  "email": "user@example.com",
  "description": "",
  "default_project_id": "uuid-string"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 사용자 UUID |
| `name` | string | 사용자 이름 |
| `email` | string | 이메일 주소 (없으면 `""`) |
| `description` | string | 설명 (없으면 `""`) |
| `default_project_id` | string | 기본 프로젝트 UUID (없으면 `""`) |

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |
| `500` | 프로필 조회 실패 |

---

## PATCH /api/v1/profile

본인 프로필을 수정합니다. 전달한 필드만 갱신되며, 하나도 없으면 400을 반환합니다.

### 요청 본문

```json
{
  "name": "string (선택)",
  "email": "string (선택)",
  "description": "string (선택)",
  "default_project_id": "uuid-string (선택)"
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string\|null | 사용자 이름 |
| `email` | string\|null | 이메일 주소 |
| `description` | string\|null | 설명 |
| `default_project_id` | string\|null | 기본 프로젝트 UUID |

### 응답 (200 OK)

`GET /api/v1/profile`과 동일한 프로필 객체를 반환합니다.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `400` | 수정할 항목이 없거나 프로필 수정 실패 |
| `401` | 유효하지 않거나 만료된 토큰 |

---
## 프로필 사진

`GET /api/v1/profile/image`는 `{ "kind": "gravatar|generated|upload", "url": "… 또는 null" }`을 반환한다. 저장된 선택이 없으면 현재 native 이메일을 trim → lower-case → SHA-256 처리한 [Gravatar 규격](https://docs.gravatar.com/rest/hash/)을 사용한다. 주소는 고정 `https://www.gravatar.com/avatar/<hash>?s=128&d=404`이며 이메일 원문·토큰·secret은 URL에 넣지 않는다. 이메일이 없으면 null, 외부 이미지 로딩 실패 때 브라우저는 접근성 이름이 있는 이니셜로 대체한다. 요청은 `no-referrer`이고 CSP는 정확한 Gravatar origin만 추가한다. 기본 Gravatar는 이메일 해시와 브라우저 네트워크 정보를 해당 외부 서비스에 공개하므로 UI에 이를 설명한다. 생성/업로드는 외부 fetch나 AI API를 사용하지 않는다.

`PUT /api/v1/profile/image`의 strict JSON은 `{ "kind": "gravatar" }` 또는 `{ "kind": "generated" }`만 허용한다. Generated 선택마다 서버가 새 random seed로 대칭 raster를 생성하고 seed를 저장하므로 재생성도 명시적 사용자 동작이다. 요청에 `user_id`, home, URL 등을 넣을 수 없다. 두 PUT은 20회/분 제한이며 응답은 GET과 같다.

`PUT /api/v1/profile/image/upload`는 multipart가 아닌 **원본 파일 bytes**를 받는다. 스트림은 2 MiB에서 차단한다. 실제 Pillow decode에 성공한 정지 PNG/JPEG/WebP/GIF만 허용하고 SVG·임의 URL·손상/잘린 raster·animation을 거부한다. 각 변 최대4096px, 총4,194,304픽셀이다. EXIF orientation을 반영해 중앙 crop한128×128 raster로 바꾸고 alpha는 중립 배경에 합성하며128색 PNG로 저장한다. 원본 filename·EXIF·ICC·XMP·text metadata는 보존하지 않는다. 업로드 이미지 응답은 정규화된 `data:image/png;base64,…`이고 별도 공개 파일 endpoint는 없다. 원본 byte 초과413, 형식/차원/animation/저장 크기 위반422, native authority 거절403, native 장애·불일치·미확정 readback503이다.

### 저장과 bounded application authority

선택은 기존 Keystone native user extra의 **`afterglow_profile_image` 한 키**에 저장한다. Gravatar는 kind, generated는 kind+seed, upload는 kind+정규화 PNG base64만 저장하므로 reload·logout/login·다른 프로젝트에서도 같은 native subject의 선택을 유지한다. 새 Afterglow DB/schema·의존성·public branding slot·localStorage를 추가하지 않는다. 업로드는 작은 palette PNG로 bounded하며 기존 metadata와 교체할 한 키를 합친 전체 visible user JSON을 ASCII-escape 직렬화한 byte 수가60,000을 넘으면 **쓰기 전에 거절**한다(native extra TEXT65,535byte 한계의 여유). 다른 extra·credentials·federation tuple·이메일은 PATCH하지 않는다.

일반 member는 stock Keystone `identity:update_user` 정책에 따라 직접 self PATCH를 할 수 없다. 따라서 이 API는 **명시적으로 허용된 Afterglow own-profile 이미지 전용 writer**다. 먼저 호출자의 native 연결로 token의 user_id와 immutable identity_domain_id 및 enabled 상태가 같은 exact user를 읽는다. 이후 기존 configured service-admin 연결이 같은 exact enabled user와 enabled home을 다시 확인하고 `afterglow_profile_image`만 PATCH한다. exact fresh user readback에서 home/ID/enabled/선택이 일치해야 성공하며 연결은 항상 닫는다. client가 고른 subject 또는 일반 native user update 권한을 위임하지 않고 native policy를 변경하지 않는다. configured writer 자체가 거절되면403이며 다른 credential로 재시도하지 않는다. Native metadata는 Keystone 사용자 조회 권한을 가진 운영자에게 보일 수 있어 secret 저장소가 아니다.

헤더와 프로필은 한 in-memory display store를 공유해 저장 성공 즉시 갱신한다. logical session·identity/home·working scope·verification/logout/switching 변경은 동기적으로 snapshot을 지우고 pending 결과를 generation으로 차단한다. 마지막 consumer unmount도 pending 결과를 폐기한다. 토큰 refresh만으로 owner가 바뀌지 않으면 snapshot을 유지한다. 불확실한 쓰기는 자동 replay하지 않고 명시적 새 조회로 현재 native 선택을 확인한다.

---


## POST /api/v1/profile/password

현재 비밀번호를 검증한 뒤 Keystone 본인 변경 `POST /v3/users/{user_id}/password`를 한 번 호출합니다. 비율 제한: **5회/분**.

현재 비밀번호는 작업 프로젝트가 아니라 immutable `identity_domain_id`의 unscoped native 인증으로 검증합니다. 세션과 native 증명의 사용자 ID 및 home이 모두 일치해야 하며, 검증된 본인 토큰과 기존·새 비밀번호를 self-service 요청에 전달합니다. 일반 member에게 허용되지 않는 관리자 `PATCH /users/{id}`는 사용하지 않습니다. Redirect, 401 재인증 및 연결·상태 재시도는 비활성화합니다. 입력값과 upstream 오류는 로그에 기록하지 않습니다.

이 API는 **기존 로컬 비밀번호**의 증명을 요구하므로 로컬 비밀번호가 있는 외부 로그인 세션도 사용할 수 있습니다. 최초 생성은 아래 별도 경로를 사용합니다. Native 성공 시 Keystone이 기존 토큰을 회수할 수 있으므로 브라우저는 비밀 입력과 로그인 상태를 지우고 재로그인을 안내합니다. 현재 비밀번호 거절은 폼 안에서 표시하며 자동 로그아웃하지 않습니다. 502 또는 응답 유실은 native 쓰기 결과가 불명확하므로 자동 재전송하지 않고 재로그인으로 확인합니다.

### 요청 본문

```json
{
  "current_password": "string (필수)",
  "new_password": "string (필수)"
}
```

입력 길이 등 검증 오류(422) 응답에는 현재·새 비밀번호 원문을 포함하지 않습니다.

### 응답 (200 OK)

```json
{ "status": "changed" }
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `400` | native 비밀번호 정책 거절 (`password_change_rejected`) |
| `401` | 현재 비밀번호 거절 (`password_current_invalid`) 또는 세션 만료 |
| `403` | native 본인·home 불일치 또는 native 권한 거절 |
| `429` | 비율 제한 초과 |
| `502` | 쓰기 결과 불명확: 자동 재전송 금지, 재로그인해 확인 |
| `503` | 현재 비밀번호의 native 증명 불가 |

## 최초 로컬 비밀번호 생성

이 절은 **소스 구현 계약**이며 배포·실서비스 수용 결과가 아닙니다. `services/keystone-first-password` 확장(고정 Keystone **28.1.0**, API revision **`first-password-galera-v2`**, DB schema revision v1)의 설치·모든 writer/Galera qualification이 필요합니다. 최초 생성은 관리자 `openstack user set --password`와 같은 native manager/setter를 사용하되 **현재 보존된 password history가 하나도 없는 경우만** 같은 transaction에서 허용하며, 무조건적인 관리자 PATCH로 fallback하지 않습니다. Privileged SQL로 모든 이력을 제거한 과거까지 증명하는 영구 ever-set bit는 없으며 `afterglow_local_password=false`만으로 부재를 주장하지 않습니다.

> **보안 경계:** 로컬 비밀번호로 로그인하면 외부 IdP의 MFA 또는 IdP 계정 비활성화 정책을 우회할 수 있습니다. 아래 외부 재로그인은 최근 Afterglow/provider 왕복만 증명하며 IdP 비밀번호 재입력·MFA 수행·MFA freshness를 증명하지 않습니다. Keystone 사용자/home 활성 여부와 Afterglow provider admission 검사는 별도로 적용됩니다.

### GET /api/v1/profile/password/capability

인증된 본인의 fresh 표시용 snapshot을 `{ "mode": "change" }`, `{ "mode": "create" }`, `{ "mode": "unavailable" }` 중 하나로 반환합니다. 응답은 `Cache-Control: no-store, private`이며 허가나 예약이 아닙니다. POST는 identity mutation lease 아래 조건을 다시 확인합니다.

- `change`: password 로그인은 관리자 directory·SMTP·최초 생성 확장 없이 폼을 제공합니다. 외부/매핑 계정도 native snapshot이 `password_state: existing`이면 marker true/false와 무관하게 변경합니다. POST의 현재 비밀번호·exact user/home 증명이 최종 권위입니다.
- `create`: native `password_state: absent`와 exact identity revision, recovery/SMTP·본인 provider 세션·메일 유일성·정책·회수 준비·미정산 작업 부재를 확인한 경우입니다. 현재 보존 history가 없다는 뜻이며 기존 비밀번호를 덮어쓰지 않습니다.
- Native 상태/확장을 확인할 수 없으면 `{ "mode": "change", "reason": "password_state_unknown" }`으로 현재 비밀번호 경로만 유지합니다. 이 응답은 비밀번호 존재 확인이나 최초 생성 허가가 아니며 UI는 관리자 확인을 안내합니다. Identity/정책 등 다른 부적격 조건은 `unavailable`입니다.

매핑 세션은 native `federated` 배열·local-password marker가 없어도 server-side `auth_method=federated`에 따라 actual native state를 조회합니다. 공개/프로필 recovery도 native state/revision이 최종 기준이며 `existing`은 기존 복구, SSO의 `absent`는 같은 계정의 새 SSO 로그인까지 필요한 생성 proof로 분기합니다. Metadata 부재만으로 password 존재·최초 생성 권한을 판단하지 않습니다.

### POST /api/v1/profile/password/recovery/request

인증된 본인의 **현재 등록 메일**로만 복구를 요청합니다. Strict 본문 `{}`이며 대상 이메일·user/home을 지정할 수 없습니다. 경로3회/분·주소별60초 제한, no-store/private/no-referrer와 항상202 `{ "accepted": true }`를 사용해 계정·메일 가용성을 공개하지 않습니다. 접수는 발송·수신 확인이 아닙니다. 링크는 새 비밀번호 입력 폼을 열며 비밀번호 자체를 보내지 않습니다. 메일 접근 불가·미수신 시 관리자 문의를 안내합니다.

Existing password recovery는 발급 revision과 exact user/home/email/actual history를 native `/users/{id}/OS-AFTERGLOW/password-reset`에서 검사합니다. Absent SSO는 `password_create` proof를 등록 메일로 보내고 아래 create-complete의 같은 사용자·새 provider session 검사를 적용합니다. Public 요청은 federation/stable external 연결을 요구하며 markerless mapped 프로필은 현재 federated owner를 검증합니다. 일반 local absent에는 생성 링크를 보내지 않습니다. 두 경로 모두 password admission·미정산 생성 fence를 확인하고 native guard 불가는202/no-mail, NULL-revision 기존 proof는410이며 stock PATCH fallback은 없습니다.

최초 설정의 exact native token GET은 native `TokenNotFound`의 알려진 만료/회수404만401 `password_create_session_invalid`로 구분합니다. Service token401/403·일반 endpoint/proxy404·전송/해석 장애는503 `password_create_session_unavailable`이며 사용자 증명이 무효라고 단정하지 않습니다. 반환된 native user/home을 비교하고 SDK가 입력 token을 다시 넣는 `auth_token` echo는 권위로 사용하지 않습니다.

### POST /api/v1/profile/password/create/request

인증 필수이며 strict 본문은 **`{}`**입니다. 이메일·사용자 ID·home·비밀번호를 client가 지정할 수 없습니다. 성공은 **202 `{ "accepted": true }`**로, 이메일을 발송했다는 뜻이며 비밀번호 생성 완료가 아닙니다. 경로 제한 3회/분과 정규화된 주소별 공유 60초 발급 간격이 적용됩니다.

서버는 exact enabled user와 immutable home, service 계정 제외, 현재 이메일의 유일성·도메인 정책, 실제 native token 및 server-side refresh session을 확인합니다. 세션의 user/home/native token과 `auth_method`, `provider_id`, `provider_revision`, `provider_domain_id`, `login_email`이 요청의 인증 정보와 일치해야 하며, 현재 provider revision/admission 정책도 재검증합니다. Native capability와 exact user/home/email에 결합된 단조 `identity_revision`을 읽은 뒤 등록 이메일로 `/recover/{token}` 링크를 보냅니다. 증명은 **1시간 만료**, DB에는 hash만 저장하며, 같은 계정의 이전 pending 생성 증명은 superseded 처리합니다.

공개 `GET /api/v1/auth/recovery/{token}`으로 링크를 검사하면 `kind: "password_create"`, 이메일, identity domain ID/이름을 받습니다(20회/분 공유 제한). 검사 자체는 이 생성 증명을 소비하지 않습니다. 완료에는 별도의 인증이 필요합니다. 링크·응답에는 `no-store, private`, `no-referrer`가 적용됩니다.

### POST /api/v1/auth/recovery/password/create/complete

인증 필수이며 strict 본문은 다음과 같습니다.

```json
{
  "token": "이메일의 일회용 증명 (32–256자)",
  "new_password": "새 비밀번호 (12–1024자)"
}
```

본인 user/home과 등록 이메일, 이메일 유일성·도메인 정책, native identity revision을 다시 확인합니다. 인증은 **같은 native 계정의 유효한 federated 세션**이어야 하며, server-side 세션 `started_at`이 증명 `created_at`보다 **엄격히 뒤**이고 서버 현재 시각 이하이며 **15분 이내**여야 합니다. 세션 만료·최대 수명도 별도 검사합니다. JWT 발급/refresh 시각이나 URL `reauthenticated=1` 표시는 이 조건의 증명이 아닙니다. 현재 server-side 세션과 native token, 현재 provider 설정·revision/admission, 로그인 이메일이 일치해야 합니다.

서버는 증명을 **`dispatching`으로 먼저 커밋해 소비**하고 다른 pending 비밀번호·이메일 변경 증명을 무효화한 뒤 native `POST /v3/users/{id}/OS-AFTERGLOW/initial-password`를 한 번 보냅니다. 본문은 새 비밀번호와 서버가 결합한 home/email/identity revision입니다. Native 요청은 redirect, 401 재인증, 연결·상태 재시도 및 credential logging을 끕니다. Native의 원자적 no-history 검사가 최종 권한이며 관리자 비밀번호 reset으로 fallback하지 않습니다.

성공은 **200 `{ "status": "created" }`**입니다. 알려진 성공 및 결과 불명확 시 모든 Afterglow 세션과 연결 native 세션의 회수를 시도하고 authority cache를 무효화합니다. 브라우저는 비밀번호·증명·continuation·로컬 인증을 지우고 로그인으로 이동합니다. **503 `password_create_sessions_failed`는 native 생성 성공 후 세션 회수 실패**이므로 다른 세션이 살아 있을 수 있고 관리자가 회수를 완료해야 합니다. 502·통신 유실은 생성 실패가 아니라 결과 불명확이며 자동 재전송하지 않습니다. `dispatching`·`outcome_unknown`·`sessions_failed` 작업은 운영자 확인·명시적 settlement 전까지 새 발급/완료를 막습니다. 세션 회수나 outcome 확인을 위해 생성 POST를 반복하지 마십시오.

### 생성 오류 응답

생성 경로의 서비스 오류는 `detail.code`에 아래 코드를 반환합니다(일반 인증·입력·rate-limit 오류 형식은 해당 공통 계약을 따릅니다).

| 상태 | 주요 코드 / 의미 |
|------|------------------|
| `401` | `password_create_session_invalid`: 만료·없는·검증할 수 없는 본인 세션 또는 일반 인증 실패 |
| `403` | `password_create_external_session_required`, `password_create_session_mismatch`, `password_create_ineligible`: 외부 세션·본인/home/email·provider 정책 거절 |
| `403` | `password_create_reauthentication_required`: 증명 발급 뒤 15분 이내의 새 provider 세션 필요; 이 사전 검사 거절은 증명을 소비하지 않음 |
| `409` | `password_create_email_ambiguous`, `password_create_ineligible`: 발급 대상 부적격; `password_create_reconciliation_required`: 미정산 작업으로 차단 |
| `409` | `password_already_exists`: native 409, 비밀번호 이력 존재; `password_create_identity_changed`: native 412, identity 변경. 이미 dispatch한 증명은 소비됨 |
| `410` | `recovery_invalid`: 만료·소비·superseded·잘못된 증명 또는 바뀐 native identity/email binding |
| `422` | strict 본문·길이 검증; `password_create_invalid_password`는 native 정책/byte 제한의 명시적 사전 거절(native 422)이며 dispatch한 증명은 소비됨 |
| `429` | route 제한 또는 `password_create_rate_limited` 주소 제한 |
| `502` | `password_create_outcome_unknown`: native/DB-stage 또는 최종 기록 결과 불명확. 재전송 금지·관리자 reconciliation 필요 |
| `503` | `password_create_email_unavailable`, `password_create_native_unavailable`, `password_create_session_unavailable`, `password_create_unavailable`: 준비/사전 검증 불가; `password_create_sessions_failed`는 위의 생성 성공 후 회수 실패와 구분 |

Native 409/412/422의 명시적 거절에는 생성 경로의 세션 회수를 하지 않습니다. 그 외 native 오류·응답 유실은 성공 여부를 추정하지 않고 세션 회수와 outcome-unknown fencing을 적용합니다. Native 거절로 소비된 증명은 재사용하지 않고 적절한 조치 뒤 프로필에서 새 메일을 요청합니다.

---

## GET /api/v1/profile/activity

본인의 활동 로그를 반환합니다. `user_id` 기준의 cross-project 로그로, 여러 프로젝트에
걸친 활동이 함께 조회됩니다.

### 쿼리 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|----------|------|--------|------|
| `limit` | int | 50 | 반환 개수 (1~200) |
| `before_id` | int | (없음) | 페이지네이션 커서. 이 ID 이전 항목 조회 |
| `resource_type` | string | (없음) | 리소스 유형 필터 (예: `auth`, `project`, `invitation`) |
| `action` | string | (없음) | 액션 필터 (예: `session_delete`) |

### 응답 (200 OK)

활동 로그 객체 배열을 반환합니다.

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `401` | 유효하지 않거나 만료된 토큰 |

## 관리자 난수 비밀번호 재설정·등록 메일 전송

`POST /api/v1/admin/users/{user_id}/password/reset-email`은 현재 system-admin만 사용합니다. Strict 본문은 `{}`이며 비밀번호·수신 주소·home은 client가 지정하지 않습니다. 경로3회/분과 같은 cloud/user에 대한 관리자 공통300초 cooldown을 적용합니다. Exact enabled user/home·유일한 canonical 등록 메일·service 계정 제외·실제 system 권위·executor binding·회수 store·검증된 STARTTLS 연결을 변경 전에 확인합니다. SMTP가 비활성/평문이거나 준비되지 않았으면 password를 변경하지 않습니다.

SSO(federated/stable external identity/명시적 no-local marker) 계정은 marker true/false 대신 native `first-password-galera-v2` capability와 exact user/home/email/state/revision을 확인합니다. `absent`면 atomic create, `existing`이면 conditional reset을 사용합니다. 확장·snapshot 불가 또는 미정산 최초 생성은 `409 admin_password_reset_external_account`로 cooldown·감사 dispatch fence·native 쓰기·메일·세션 회수 전에 거부합니다. 이 코드는 SSO 자체의 영구 금지가 아니라 안전한 native 전제 미충족입니다.

서버는 암호학적 난수32자를 생성합니다. 일반 local은 원 native executor의 `PATCH /v3/users/{id}`, SSO는 configured service credential의 조건부 `POST /v3/users/{id}/OS-AFTERGLOW/initial-password` 또는 `/password-reset`을 한 번 호출합니다. SSO 본문은 password와 서버가 읽은 exact home/email/revision이고 원 UUID/federation을 보존합니다. 기존 password/email-change/create proof를 supersede하고 비밀 없는 dispatch 감사 기록을 **먼저 commit**합니다. Known 성공만 등록 메일로 password를 보내며 응답·로그·감사·DB에는 password를 남기지 않습니다. 성공/불명 결과는 세션·native token/cache 회수를 시도합니다.

**200 `{ "status": "changed", "delivered": true }`**는 native 변경과 SMTP 접수를 확인한 결과이지 실제 받은편지함 도착 보장이 아닙니다. Afterglow는 강제 첫 로그인 만료를 추가하지 않으며 native password/만료 정책은 그대로 적용됩니다. 사용자는 로그인 직후 자신의 비밀번호로 변경해야 합니다. 실제 password가 메일함에 남으므로 사용자 셀프 복구의 일회용 링크보다 위험합니다. 관리자 확인 창과 메일에 이를 안내하고 공개 분실 요청만으로 이 동작을 실행하지 않습니다.

| 응답 | 효과/다음 조치 |
| --- | --- |
| 409 `admin_password_reset_external_account` | SSO native capability/state 검증 불가 또는 미정산 최초 생성; 쓰기·메일·세션 회수·cooldown 없이 사전 거부 |
| `admin_password_reset_native_rejected` | SSO 조건부409/412/422 또는 일반 local PATCH의 명시적400/401/403/404/409/412/422 거절; `changed:false`, password 메일 없음 |
| 503 `admin_password_reset_email_unavailable` | SMTP/검증 TLS 준비 실패, 변경 전 차단 |
| 503 `admin_password_reset_email_failed` | `changed:true, delivered:false`; 이전 password는 무효일 수 있으며 관리자 확인 뒤 새 명시 요청 필요 |
| 503 `admin_password_reset_sessions_failed` | `changed:true`, 실제 `delivered`; 다른 세션이 남아 있을 수 있어 별도 회수 필요 |
| 503 `admin_password_reset_audit_failed` | `changed`·`delivered`·회수 효과를 확인하고 감사/실제 계정을 조사; 실패를 미변경으로 추정하지 않음 |
| 502 `admin_password_reset_outcome_unknown` | 변경 여부 불명, 성공 password 메일·자동 replay·rollback 없음; native 종료/계정 확인 필요 |

모든 응답은 private/no-store/no-referrer입니다. Canonical email 정규화는 SMTP가 comment/display-name 문법을 다른 수신 주소로 해석하는 입력을 거부합니다. Native 거절/메일 실패/회수 실패/불명 결과는 자동 재시도하지 않습니다.
