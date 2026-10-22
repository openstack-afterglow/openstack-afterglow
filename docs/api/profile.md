---
title: 프로필 (Profile)
parent: API 레퍼런스
nav_order: 11
---

# 프로필 (Profile) API

> 태그: `profile`
> 기본 경로: `/api/v1/profile`

현재 로그인한 사용자 본인의 프로필 조회·수정, 비밀번호 변경, 활동 로그 조회를 제공합니다.
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
| `GET` | `/api/v1/profile/activity` | 본인 활동 로그 조회 (cross-project) |
| `GET` | `/api/v1/profile/image` | 본인 사진 선택·표시 데이터 조회 (private, no-store) |
| `PUT` | `/api/v1/profile/image` | Gravatar 선택 또는 새 아바타 생성·저장 |
| `PUT` | `/api/v1/profile/image/upload` | bounded raw raster 업로드·정규화·저장 |
| `GET` | `/api/v1/profile/login-preference` | 본인 로그인 작업공간 선호 조회 (private, no-store) |
| `PUT` | `/api/v1/profile/login-preference` | `{remember_last_workspace:boolean}` 저장; target은 현재 검증된 scope에서 서버가 결정 |

---
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

현재 비밀번호를 검증한 뒤 새 비밀번호로 변경합니다. Keystone 비밀번호 변경 API를
호출합니다. 비율 제한: **5회/분**.

현재 비밀번호는 작업 중인 조직·프로젝트가 아니라 변경 불가 `identity_domain_id`에서 **unscoped native 증명**으로 검증한다. Identity-only `account`를 workspace로 선택하지 않으므로 신규 공용 account 계정도 개인 프로젝트를 유지한 채 변경할 수 있다. Native 증명의 사용자 ID가 세션 사용자와 다르면403, 검증 불가 장애는503이며 어느 경우에도 비밀번호를 쓰지 않는다. 성공 후 기존 비밀번호는 거절되고 새 비밀번호로 같은 계정·개인 프로젝트에 로그인한다.

> 외부(federated) 로그인 사용자는 로컬 비밀번호가 없으므로 변경할 수 없습니다(403).

### 요청 본문

```json
{
  "current_password": "string (필수)",
  "new_password": "string (필수)"
}
```

### 응답 (200 OK)

```json
{ "status": "changed" }
```

### 오류 응답

| 상태 코드 | 설명 |
|-----------|------|
| `400` | 새 비밀번호 변경 실패 (정책 위반 등) |
| `401` | 현재 비밀번호가 올바르지 않음 |
| `403` | 외부 로그인 사용자 (비밀번호 변경 불가) |
| `429` | 비율 제한 초과 |

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
