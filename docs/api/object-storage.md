---
title: 오브젝트 스토리지 (Swift)
parent: API 레퍼런스
nav_order: 63
---

# 오브젝트 스토리지 (Object Storage / Swift) API

> 태그: `object-storage`, `object-storage-upload`
> 기본 경로: `/api/v1/object-storage`

OpenStack Swift(Ceph RGW) 기반의 오브젝트 스토리지를 관리합니다. 컨테이너(버킷)와 오브젝트의 CRUD, 스트리밍 업로드/다운로드, 복사·이동·이름변경, 그리고 소프트 삭제(휴지통) 기능을 제공합니다.

> **활성화 조건:** `afterglow.conf [services] swift = true`
> 비활성화 상태에서 이 엔드포인트에 접근하면 라우터가 등록되지 않습니다.

---

## 인증 헤더

| 헤더 | 설명 |
|------|------|
| `Authorization` | `Bearer <access_token>` (로그인 응답의 access JWT) |
| `X-Project-Id` | (선택) 프로젝트 UUID — 생략 시 토큰의 프로젝트로 처리, 다른 값이면 rescope |

> 예외: `GET .../download` 는 헤더 대신 단발 다운로드 토큰(`?token=`)으로 인증합니다(아래 [다운로드 토큰](#다운로드-토큰-흐름) 참조).

---

## 개요

### 테넌트 격리와 소유권 모델

오브젝트 스토리지의 접근 제어는 **Swift account 모델이 1차 방어선**입니다. 각 요청은 Keystone 프로젝트에 스코프된 연결(`get_os_conn`)로 처리되며, Swift/RGW 계정은 프로젝트 단위로 분리되어 있어 다른 프로젝트의 컨테이너에 접근할 수 없습니다. 즉 앱 DB 소유권 검증(`project_id == token_info["project_id"]`)을 별도로 수행하지 않고, Keystone 스코핑이 격리를 보장합니다.

방어 심화(defense-in-depth)를 위해, 신규 컨테이너 생성 시 호출자의 프로젝트 ID를 `X-Container-Meta-Owner-Project-Id` 메타데이터로 부착합니다. 실제 RBAC는 Swift account 모델이 담당하며, 이 owner 메타데이터는 admin/operator 도구가 컨테이너 소유자를 식별·검증하는 보조 수단입니다. (근거: `docs/security.md`, 아키텍처 문서)

### 소프트 삭제(휴지통)

컨테이너와 오브젝트 삭제는 기본적으로 **소프트 삭제**입니다.

- **컨테이너 삭제**: 기본값(`permanent=false`)은 소프트 삭제로, Redis sorted-set과 컨테이너 메타데이터에 삭제 시각을 기록합니다. 설정된 보관 기간(`os_trash_retention_days`, 기본 30일) 동안 복구할 수 있습니다. 소프트 삭제 대기 중인 이름과 동일한 컨테이너를 재생성하면 `409`가 반환됩니다.
- **오브젝트 삭제**: 기본값은 `{container}-trash` 버킷으로 이동하며, 보관 기간 내 복구할 수 있습니다.
- `permanent=true` 지정 시 즉시 영구 삭제(복구 불가)합니다.

### 오브젝트 이름(`object_name:path`)

오브젝트 이름은 `/`를 포함할 수 있으므로(가상 디렉토리), 개별 오브젝트 경로 파라미터는 FastAPI `:path` 타입을 사용합니다. 서버는 업로드 시 오브젝트 키를 정규화합니다: ASCII 제어문자/DEL/NUL 제거, path traversal segment(`.`, `..`) 제거, leading/trailing/연속 slash 정리, 최대 1024자. 정규화 후 유효한 이름이 없으면 `unnamed`으로 대체됩니다.

---

## 엔드포인트 목록

| 메서드 | 경로 | 설명 |
|--------|------|------|
| `GET` | `/api/v1/object-storage/account` | 계정 사용량 메타데이터 |
| `GET` | `/api/v1/object-storage` | 컨테이너 목록 |
| `POST` | `/api/v1/object-storage` | 컨테이너 생성 |
| `GET` | `/api/v1/object-storage/{container}` | 컨테이너 메타데이터 |
| `DELETE` | `/api/v1/object-storage/{container}` | 컨테이너 삭제(소프트/영구) |
| `GET` | `/api/v1/object-storage/{container}/objects` | 오브젝트 목록 |
| `POST` | `/api/v1/object-storage/{container}/objects` | 오브젝트 업로드(multipart) |
| `PUT` | `/api/v1/object-storage/{container}/objects/{object_name}` | 오브젝트 업로드(streaming) |
| `POST` | `/api/v1/object-storage/{container}/upload` | 백엔드 프록시 업로드(quarantine 경유) |
| `POST` | `/api/v1/object-storage/{container}/objects/{object_name}/download-token` | 단발 다운로드 토큰 발급 |
| `GET` | `/api/v1/object-storage/{container}/objects/{object_name}/download` | 오브젝트 다운로드 |
| `GET` | `/api/v1/object-storage/{container}/objects/{object_name}/metadata` | 오브젝트 메타데이터 |
| `GET` | `/api/v1/object-storage/{container}/objects/{object_name}/preview` | 오브젝트 인라인 미리보기 |
| `GET` | `/api/v1/object-storage/{container}/objects/{object_name}/thumbnail` | 이미지·PDF 축소 미리보기(WebP) |
| `DELETE` | `/api/v1/object-storage/{container}/objects/{object_name}` | 오브젝트 삭제(소프트/영구) |
| `POST` | `/api/v1/object-storage/{container}/objects/bulk-delete` | 오브젝트 일괄 삭제 |
| `POST` | `/api/v1/object-storage/{container}/objects/directory` | 가상 디렉토리 생성 |
| `POST` | `/api/v1/object-storage/{container}/objects/copy` | 오브젝트 복사 |
| `POST` | `/api/v1/object-storage/{container}/objects/move` | 오브젝트 이동 |
| `POST` | `/api/v1/object-storage/{container}/objects/rename` | 오브젝트 이름 변경 |
| `GET` | `/api/v1/object-storage/{container}/trash` | 휴지통 오브젝트 목록 |
| `POST` | `/api/v1/object-storage/{container}/trash/restore` | 휴지통 오브젝트 복구 |
| `DELETE` | `/api/v1/object-storage/{container}/trash/{trash_key}` | 휴지통 오브젝트 영구 삭제 |
| `GET` | `/api/v1/object-storage/trash/containers` | 소프트 삭제 컨테이너 목록 |
| `POST` | `/api/v1/object-storage/trash/containers/{container}/restore` | 컨테이너 복구 |
| `DELETE` | `/api/v1/object-storage/trash/containers/{container}` | 컨테이너 영구 삭제 |

---

## 1. 계정 / 컨테이너

### GET /api/v1/object-storage/account

현재 계정의 Swift 오브젝트 스토리지 사용량 메타데이터(컨테이너 수, 총 오브젝트 수, 총 바이트 등)를 반환합니다.

### GET /api/v1/object-storage

컨테이너(버킷) 목록을 반환합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `all_projects` | query | boolean | `false` | **admin 전용.** 모든 프로젝트의 버킷을 병렬 집계 |
| `include_quarantine` | query | boolean | `false` | **admin 전용.** `*-quarantine` 버킷 포함 |
| `include_trash` | query | boolean | `false` | **admin 전용.** `*-trash` 버킷 포함 |
| `include_deleted` | query | boolean | `false` | 소프트 삭제 대기 버킷을 `is_deleted`/`deleted_at` 필드와 함께 포함(모든 사용자) |

> `all_projects`/`include_quarantine`/`include_trash`는 시스템 admin이 아니면 `403`을 반환합니다. `include_deleted`는 인증된 모든 사용자가 자신의 삭제 대기 버킷을 조회할 때 사용합니다.

### POST /api/v1/object-storage

컨테이너를 생성합니다.

**요청 본문**

```json
{ "name": "my-bucket" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `name` | string | 예 | 버킷 이름 (1–255자) |

- 이름 검증: `validate_bucket_name`이 시스템 예약어/S3 형식 위반(점·하이픈 시작 등)을 차단합니다. 위반 시 `400` + 한국어 사유.
- 소프트 삭제 대기 중인 동명 버킷이 있으면 `409`(휴지통에서 복구하거나 영구 삭제 후 재생성).
- 생성 시 `X-Container-Meta-Owner-Project-Id` owner 메타데이터를 부착합니다.

**응답**: `201 Created`

### GET /api/v1/object-storage/{container}

컨테이너 메타데이터(오브젝트 수, 총 바이트 등)를 반환합니다. 없으면 `404`.

### DELETE /api/v1/object-storage/{container}

컨테이너를 삭제합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `permanent` | query | boolean | `false` | `true` 시 즉시 영구 삭제. 기본값은 보관 기간(기본 30일) 동안 복구 가능한 소프트 삭제 |

**응답**: `204 No Content`

---

## 2. 오브젝트 목록 / 업로드

### GET /api/v1/object-storage/{container}/objects

컨테이너 내 오브젝트 목록을 반환합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `prefix` | query | string | `""` | 조회할 경로 prefix |
| `delimiter` | query | string | `"/"` | `/`(기본): 현재 prefix의 직속 파일·서브디렉토리만. `""`: 전체 오브젝트를 flat하게 반환 |

Afterglow는 세 가지 업로드 방식을 제공합니다. 용도에 맞게 선택합니다.

### POST /api/v1/object-storage/{container}/objects — multipart 업로드

`multipart/form-data`로 파일을 수신해 Swift에 스트리밍 업로드합니다. 1 GiB 초과 시 Swift SLO가 자동 적용됩니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `file` | form-data | file | 예 | 업로드할 파일 |

**응답**: `201 Created`

### PUT /api/v1/object-storage/{container}/objects/{object_name} — streaming 업로드

디스크 spool 없이 raw body를 Swift에 직접 forward합니다.

| 헤더 | 필수 | 설명 |
|------|------|------|
| `Content-Length` | 예 | 없으면 `411`. 값이 잘못되면 `400` |
| `Content-Type` | 아니오 | 기본값 `application/octet-stream` |

- `Content-Length`가 `app_max_upload_gb`(설정값, 0이면 무제한)를 초과하면 `413`.
- `Content-Length > 1 GiB`이면 Swift SLO 자동 적용.

**응답**: `201 Created`

### POST /api/v1/object-storage/{container}/upload — 백엔드 프록시 업로드

브라우저 → RGW 직접 PUT의 CORS 차단을 회피하기 위한 프록시 흐름입니다. 클라이언트가 backend로 form 업로드하면, 백엔드가 내용 검사 → `{container}-quarantine` 버킷으로 스트리밍 업로드(boto3, 5 GB+ 자동 multipart) → 저장 객체 검증 → target 버킷으로 server-side copy → quarantine 원본 삭제를 수행합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `file` | form-data | file | 예 | 업로드할 파일 |
| `prefix` | form-data | string | 아니오 | 오브젝트 키 앞에 붙일 prefix |
| `sha256` | form-data | string | 아니오 | 브라우저가 계산한 64자 소문자 hex SHA-256. 프론트엔드는 256 MiB 이하 파일에만 계산해 보냅니다. 형식이 어긋나면 `422` |

**형식 검사.** 안티바이러스가 아니라 좁은 형식 정책입니다. 파일 앞부분(8 KiB)의 magic byte로 실제 형식을 판정하고, 아래 **두 가지만** 거부합니다(`400`).

- **렌더링 확장자 위장** — `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.bmp`, `.pdf`의 내용이 해당 형식이 아니면 거부합니다. 이 확장자들은 축소본·미리보기로 브라우저에 인라인 해석되기 때문이며, 내용을 식별할 수 없는 경우도 거부합니다.
- **실행 파일 위장** — PE(`MZ`)·ELF·Mach-O 이미지가 실행 파일이 아닌 확장자를 달고 있으면 거부합니다. `.exe`, `.dll`, `.so`, `.bin`, 확장자 없음 등 정직한 이름이면 그대로 업로드됩니다.

그 외에는 거부하지 않고 탐지 결과만 기록합니다. `.html`·`.svg`·`.js`·`.sh`·`.tar.gz`와 ZIP 컨테이너인 Office 문서(`.docx`/`.xlsx`/`.pptx`)는 정상 업로드됩니다. 다운로드는 `Content-Disposition: attachment`이고 `/preview`는 Authorization 헤더를 요구하므로 최상위 탐색으로 실행되는 경로가 없습니다. 브라우저가 신고한 `Content-Type`은 그대로 보존하며, 비어 있거나 `application/octet-stream`일 때만 탐지 결과 또는 확장자 추론으로 채웁니다.

**무결성 검증.** 서버가 spooled 파일을 한 번 훑어 크기·SHA-256·MD5를 계산합니다. `sha256`이 오면 `hmac.compare_digest`로 비교하고(불일치 `400`), quarantine 저장 객체는 HEAD 한 번으로 검증합니다 — 단일 PUT은 ETag(=content MD5) 비교, multipart는 크기와 part 수 비교입니다. 객체 전체를 다시 내려받지 않습니다. 승격 후 대상 객체의 크기가 어긋나면 그 객체를 삭제하고 `502`로 실패합니다.

검증된 digest와 탐지 형식은 업로드 시점에 `x-amz-meta-sha256` / `x-amz-meta-detected-content-type`으로 부착합니다. server-side copy는 기본 `MetadataDirective=COPY`이므로 `Content-Type`과 user metadata가 대상 객체까지 그대로 따라가며, metadata 응답의 `sha256`/`detected_content_type` 필드로 노출됩니다.

- 파일 이름이 비었거나 정규화 후 `unnamed`이면 `400`.
- 크기가 `app_max_upload_gb`(기본 10 GB)를 초과하면 `413`.
- 클라이언트 disconnect 감지 시 검사 loop와 multipart 업로드를 중단하고 quarantine을 정리합니다(`499`).
- 컨테이너 검증 실패 시 `404`. 모든 실패 경로에서 quarantine 객체를 정리합니다.
- `reader` 역할은 `require_project_write`로 `403` 거부됩니다.

**응답 (200 OK)**

```json
{
  "success": true,
  "name": "docs/report.pdf",
  "bytes": 20480,
  "etag": "…",
  "content_type": "application/pdf",
  "sha256": "…",
  "detected_content_type": "application/pdf"
}
```

---

## 다운로드 토큰 흐름

브라우저 네이티브 다운로더는 커스텀 인증 헤더를 붙일 수 없으므로, 단발 토큰을 먼저 발급받아 URL 쿼리로 전달합니다.

### POST /api/v1/object-storage/{container}/objects/{object_name}/download-token

단발 다운로드 토큰을 발급합니다(TTL 60초, 1회 사용). 발급된 토큰은 Redis에 저장되며, 요청한 `{container}`/`{object_name}`과 일치할 때만 유효합니다.

**응답 (200 OK)**

```json
{
  "url": "/api/v1/object-storage/my-bucket/objects/dir%2Ffile.txt/download?token=...",
  "expires_in": 60
}
```

### GET /api/v1/object-storage/{container}/objects/{object_name}/download

오브젝트를 스트리밍 다운로드합니다.

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `token` | query | string | 예 | 위에서 발급받은 단발 다운로드 토큰 |

- 토큰은 Redis에서 `getdel`로 원자적 1회 소비되며, 요청 리소스와 일치하지 않으면 `403`.
- 응답 헤더에 RFC 5987 형식의 `Content-Disposition: attachment`(한글 파일명 처리)를 포함합니다.

> 보안: 다운로드 토큰 비교는 `hmac.compare_digest` 기반 타이밍 안전 비교와 Redis 원자적 소비로 보호됩니다.

---

## 3. 개별 오브젝트

### GET /api/v1/object-storage/{container}/objects/{object_name}/metadata

오브젝트 상세 메타데이터를 반환합니다. 없으면 `404`.

### GET /api/v1/object-storage/{container}/objects/{object_name}/preview

오브젝트를 인라인으로 미리보기합니다(`Content-Disposition: inline`). 이미지·텍스트 등 브라우저 내장 뷰어용. 없으면 `404`.

### GET /api/v1/object-storage/{container}/objects/{object_name}/thumbnail

이미지(PNG/JPEG/GIF/WebP/BMP/TIFF)와 PDF 첫 페이지를 최대 320px WebP로 렌더링해 반환합니다. 오브젝트 브라우저 그리드가 사용하며, 호출자의 Swift 연결로 읽으므로 별도의 공개 URL이 생기지 않습니다.

- 결과는 `afterglow:swift:{project}:thumbnail:*` 키로 24시간 캐시하고 응답에 `Cache-Control: private, max-age=3600`과 원본 `ETag`를 붙입니다. Redis 장애는 캐시 미스로 처리합니다.
- 지원하지 않는 형식은 `415`, 64 MiB 초과 원본은 `413`(HEAD 단계에서 본문을 읽기 전에 거부), 디코딩 실패는 `422`, 오브젝트 부재는 `404`.
- 렌더링은 픽셀 수 4천만 상한과 PDFium 전역 lock을 적용하며, 알파 채널이 있는 원본(PNG/GIF)은 투명도를 유지합니다.

### DELETE /api/v1/object-storage/{container}/objects/{object_name}

오브젝트를 삭제합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `permanent` | query | boolean | `false` | `true` 시 즉시 영구 삭제. 기본값은 `{container}-trash`로 이동 |

**응답**: `204 No Content`

---

## 4. 일괄 삭제 / 디렉토리 / 복사·이동·이름변경

### POST /api/v1/object-storage/{container}/objects/bulk-delete

오브젝트를 일괄 삭제합니다.

| 파라미터 | 위치 | 타입 | 기본값 | 설명 |
|----------|------|------|--------|------|
| `permanent` | query | boolean | `false` | `true` 시 즉시 영구 삭제. 기본값은 휴지통 이동 |

**요청 본문**

```json
{ "objects": ["a/b.txt", "a/c/"], "recursive": false }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `objects` | array[string] | 예 | 삭제 대상 (1–1000개) |
| `recursive` | boolean | 아니오 | `true`이면 `/`로 끝나는 디렉토리 하위 전체 삭제 |

**응답 (200 OK)**: `{ "deleted": [...], "failed": [{"name": ..., "error": ...}] }`

### POST /api/v1/object-storage/{container}/objects/directory

가상 디렉토리를 생성합니다.

```json
{ "path": "folder/subfolder/" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `path` | string | 예 | 디렉토리 경로 (1–1024자) |

**응답**: `201 Created`

### POST /api/v1/object-storage/{container}/objects/copy

오브젝트를 복사합니다.

```json
{ "source": "a/b.txt", "destination": "a/b-copy.txt", "dest_container": null }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `source` | string | 예 | 원본 오브젝트 키 |
| `destination` | string | 예 | 대상 오브젝트 키 |
| `dest_container` | string\|null | 아니오 | 대상 컨테이너. 생략 시 동일 컨테이너 |

### POST /api/v1/object-storage/{container}/objects/move

오브젝트를 이동합니다. `destination`이 `/`로 끝나면 원본 파일명을 자동으로 붙입니다(예: `source="a/b.txt"`, `destination="folder/"` → `folder/b.txt`).

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `source` | string | 예 | 원본 오브젝트 키 |
| `destination` | string | 예 | 대상 오브젝트 키 또는 디렉토리 경로 |
| `dest_container` | string\|null | 아니오 | 대상 컨테이너. 생략 시 동일 컨테이너 |

### POST /api/v1/object-storage/{container}/objects/rename

오브젝트 이름을 변경합니다.

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `source` | string | 예 | 원본 오브젝트 키 |
| `new_name` | string | 예 | 새 이름 |

---

## 5. 휴지통

### 오브젝트 단위

#### GET /api/v1/object-storage/{container}/trash

버킷 휴지통(`{container}-trash`)의 오브젝트 목록을 반환합니다. 각 항목에 `trash_key`, `original_name`, `deleted_at`(epoch seconds)를 포함합니다.

#### POST /api/v1/object-storage/{container}/trash/restore

휴지통 오브젝트를 원본 버킷으로 복구합니다.

```json
{ "trash_key": "{epoch}/{uuid8}/{original_name}" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `trash_key` | string | 예 | 휴지통 목록에서 얻은 키. 형식 오류 시 `400` |

#### DELETE /api/v1/object-storage/{container}/trash/{trash_key}

휴지통 오브젝트를 영구 삭제합니다(복구 불가). **응답**: `204 No Content`

### 컨테이너 단위

#### GET /api/v1/object-storage/trash/containers

소프트 삭제 대기 중인 버킷 목록을 반환합니다(Redis sorted-set 기반). 각 항목에 `is_deleted`/`deleted_at`를 포함합니다.

#### POST /api/v1/object-storage/trash/containers/{container}/restore

소프트 삭제된 버킷을 복구합니다(다시 목록에 노출). 삭제 대기 상태가 아니면 `404`.

**응답 (200 OK)**: `{ "name": "...", "restored": true }`

#### DELETE /api/v1/object-storage/trash/containers/{container}

소프트 삭제된 버킷을 내용물까지 영구 삭제합니다(복구 불가). 삭제 대기 상태가 아니면 `404`. **응답**: `204 No Content`
