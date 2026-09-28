---
title: 이미지 (Images)
parent: API 레퍼런스
nav_order: 32
---

# 이미지 (Images) API

> 태그: `images`
> 기본 경로: `/api/v1/images`

Glance 이미지 카탈로그를 조회하고, 이미지 업로드·메타데이터 수정·활성화 상태 변경·공유 멤버 관리를 수행합니다.

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
| `GET` | `/api/v1/images` | 이미지 목록 |
| `POST` | `/api/v1/images` | 이미지 업로드 (3/분) |
| `GET` | `/api/v1/images/{image_id}` | 이미지 상세 |
| `DELETE` | `/api/v1/images/{image_id}` | 이미지 삭제 |
| `PATCH` | `/api/v1/images/{image_id}` | 이미지 기본 메타데이터 수정 |
| `PATCH` | `/api/v1/images/{image_id}/properties` | 임의 properties 추가/삭제 |
| `POST` | `/api/v1/images/{image_id}/deactivate` | 이미지 비활성화 |
| `POST` | `/api/v1/images/{image_id}/reactivate` | 이미지 재활성화 |
| `GET` | `/api/v1/images/{image_id}/members` | 공유 멤버(프로젝트) 목록 |
| `POST` | `/api/v1/images/{image_id}/members` | 공유 프로젝트 추가 |
| `DELETE` | `/api/v1/images/{image_id}/members/{member_id}` | 공유 프로젝트 삭제 |
| `GET` | `/api/v1/admin/images` | 시스템 관리자 전체 목록 (`limit=1..100`, `marker`, `search`, `visibility`) |
| `GET` | `/api/v1/admin/images/{image_id}` | 시스템 관리자 상세 |
| `PUT` | `/api/v1/admin/images/{image_id}/verification` | 시스템 관리자 검증 승인·해제 |
| `PATCH` | `/api/v1/admin/images/{image_id}` | 관리자 이미지 메타데이터 수정 |
| `PATCH` | `/api/v1/admin/images/{image_id}/properties` | 관리자 이미지 properties 수정 |
| `DELETE` | `/api/v1/admin/images/{image_id}` | 관리자 이미지 삭제·검증 기록 정리 |
| `POST` | `/api/v1/admin/images/{image_id}/deactivate` | 관리자 이미지 비활성화 |
| `POST` | `/api/v1/admin/images/{image_id}/reactivate` | 관리자 이미지 재활성화 |

---

## GET /api/v1/images

프로젝트에서 사용 가능한 Glance 이미지 목록을 반환합니다. 원본 Glance 정보는 캐시됩니다(`?refresh=true`로 강제 갱신 가능). 검증 상태는 캐시 결과를 읽은 뒤 매 요청마다 Afterglow DB에서 일괄 조회하므로 승인·해제가 오래된 검증 캐시에 가려지지 않습니다.

### 응답 (200 OK) — `ImageInfo` 배열

```json
[
  {
    "id": "uuid-string",
    "name": "ubuntu:22.04",
    "repository": "ubuntu",
    "tag": "22.04",
    "status": "active",
    "size": 2147483648,
    "min_disk": 20,
    "min_ram": 512,
    "disk_format": "qcow2",
    "os_type": "linux",
    "os_distro": "ubuntu",
    "created_at": "2024-01-01T00:00:00Z",
    "owner": "uuid-string",
    "visibility": "private",
    "verification_status": "unverified",
    "verified_at": null
  }
]
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 이미지 UUID |
| `name` | string | 이미지 이름 |
| `repository`, `tag` | string | Docker-style 이미지 이름의 repository와 tag. tag 생략 시 `latest` |
| `status` | string | 상태 (`active`, `queued`, `saving`, `deactivated` 등) |
| `size` | integer \| null | 바이트 단위 크기 |
| `min_disk` | integer | 최소 디스크 요구량 (GB) |
| `min_ram` | integer | 최소 RAM 요구량 (MB) |
| `disk_format` | string \| null | 디스크 포맷 (`qcow2`, `raw` 등) |
| `os_type` | string \| null | OS 타입 |
| `os_distro` | string \| null | OS 배포판 (`ubuntu`, `centos` 등) |
| `created_at` | string \| null | 생성 일시 (ISO 8601) |
| `owner` | string \| null | 소유 프로젝트 UUID |
| `visibility` | string \| null | `private` \| `public` \| `shared` \| `community` |
| `protected` | boolean | Glance 삭제 보호 상태. 관리자·사용자 목록에서도 보존되며 관리자 목록의 삭제 작업을 보호된 업로드에 제공하지 않음 |
| `os_hash_algo`, `os_hash_value` | string \| null | Glance가 계산한 원본 콘텐츠 해시 |
| `verification_status` | string | `verified`(승인과 현재 이미지 일치), `unverified`(승인 없음·불일치·비활성), `unavailable`(검증 저장소 조회 실패) |
| `verified_at` | string \| null | 현재 승인 기록의 UTC 시각. 검증되지 않았으면 `null` |

검증은 **관리자 승인 기록이지 악성코드 검사 결과가 아닙니다**. 기존 public 이미지, admin 프로젝트 소유, 사용자가 설정한 properties/tags는 검증 근거가 아닙니다. 승인 기록은 이미지 UUID·소유 프로젝트·생성 시각(마이크로초 보존)·Glance SHA-256/512에 묶입니다. 기록이 없거나 정체성이 바뀌면 미검증이며, DB 장애를 미검증 또는 검증됨으로 숨기지 않습니다.

---

## POST /api/v1/images

이미지 파일을 업로드합니다(`multipart/form-data`). **속도 제한: 3회/분.**

### 요청 (multipart/form-data)

| 필드 | 타입 | 필수 | 기본값 | 설명 |
|------|------|------|--------|------|
| `file` | file | 예 | — | 업로드할 이미지 파일 |
| `name` | string | 예 | — | 이미지 이름 (공백 불가) |
| `disk_format` | string | 아니오 | `raw` | 허용 포맷만 가능(`raw`/`qcow2`/`vmdk` 등). 미허용 시 `400` |
| `visibility` | string | 아니오 | `private` | `private`/`public`/`shared`/`community` |
| `os_distro` | string | 아니오 | — | OS 배포판. 지정 시 이미지 property로 설정 |

> `public`/`community` 가시성은 **시스템 관리자만** 설정할 수 있습니다. 일반 사용자 요청은 `403`입니다.

### 응답 (201 Created)

```json
{
  "id": "uuid-string", "name": "my-image:latest", "repository": "my-image", "tag": "latest",
  "status": "queued", "disk_format": "raw", "verification_status": "unverified",
  "verified_at": null, "verification_message": null
}
```

**오류**: `400`(disk_format/visibility/이름), `403`(권한), `413`(크기 초과), `500`(업로드 실패)

시스템 관리자의 새 업로드는 성공한 Glance PUT 뒤 이미지를 다시 조회해 active 상태와 강한 해시를 확인하고 자동 승인합니다. Glance 업로드는 성공했지만 후속 조회·검증 기록이 실패하면 **201과 생성된 UUID를 유지**하고 `verification_status=unavailable` 및 `verification_message`를 반환합니다. 같은 파일을 무작정 재업로드하지 말고 기존 이미지의 상세를 확인한 뒤 승인합니다. 일반 사용자 업로드는 자동 승인하지 않습니다.

## 관리자 카탈로그와 검증 변경

`GET /api/v1/admin/images`는 `{items, next_marker, count}`를 반환합니다. 관리자 화면은 모든 marker 페이지가 성공한 뒤 한 번에 카탈로그를 교체하고, repository 단위로 묶은 결과를 화면에서 페이지 분할합니다. 중간 페이지 실패 시 이전의 완전한 목록을 유지하고 오류를 표시하며, 인증 scope가 바뀐 뒤 도착한 응답은 버립니다.
사용자 대시보드 목록도 프로젝트 또는 인증 토큰 변경 시 다시 조회합니다. 이전 요청이 뒤늦게 성공하거나 실패해도 새 scope의 목록·로딩·오류 상태를 덮어쓰지 않습니다.

사용자·관리자 카탈로그의 기본 정렬은 `created_at` 최신순입니다. repository 순서는 내부 최신 업로드 이미지 기준이며 `updated_at` 변경은 순서에 영향을 주지 않습니다. ISO offset과 마이크로초를 실제 시각으로 비교하고 timezone 없는 OpenStack ISO 시각은 UTC로 처리합니다. 잘못되거나 없는 날짜는 최신순·오래된순 모두 마지막입니다. 동일 repository/tag의 생성 시각이 같거나 모두 없으면 UUID 내림차순으로 대표를 고정합니다. 신뢰 필터는 업로드별로 적용하고 repository 카드도 모든 업로드의 검증/미검증/조회 불가 수를 각각 표시합니다.

### 동일 repository/tag의 현재 이미지와 이전 업로드

Glance 이름은 고유 키가 아닙니다. 카탈로그는 호출자에게 보이는 전체 목록에서 동일 `repository:tag`의 최신 `created_at` UUID를 **현재**로 표시합니다. 검색·신뢰·공개 범위 필터는 이 대표를 바꾸지 않으며, 필터에 맞는 이전 업로드는 **이전**으로 표시합니다. 관리자와 사용자가 볼 수 있는 목록 자체가 다르면 대표도 다를 수 있습니다. API의 이미지 선택·수정·삭제와 VM 생성은 계속 UUID를 사용하며 이름 기반 서버 resolver를 추가하지 않습니다.

Repository 미리보기에는 tag를 한 번만 표시합니다. 사용자 repository 상세는 현재 이미지와 펼쳐 볼 수 있는 이전 업로드를, 관리자 목록과 사용자 tag 카드는 개별 업로드를 보존합니다. `os_hash_algo`/`os_hash_value`의 SHA-512(또는 SHA-256) 축약값과 UUID를 함께 표시하고 전체 해시·UUID로 검색할 수 있습니다. 전체 값은 상세에서도 확인합니다. 동일 콘텐츠·동일 해시라도 UUID가 다르면 별도 업로드이며 자동 병합·덮어쓰기·이름 변경하지 않습니다.

해시가 없는 `queued`/`saving`은 **해시 계산 중**, 나머지는 **해시 없음**으로 표시하고 UUID로 구분합니다. VM picker는 필터를 적용하기 전에 현재 tag 대상을 정하며, 아직 active가 아니면 선택을 막고 이전 active 이미지로 조용히 대체하지 않습니다. 이미 선택한 이전 UUID도 자동 변경하지 않고 이전 선택임을 명시합니다.


관리자 목록의 `protected`는 Glance `is_protected`를 `ImageInfo` 검증/승인 enrichment가 통과시킨 값입니다. 동일한 SHA와 이름인 업로드에서도 각 UUID의 보호 상태를 따로 유지하며, 보호된 UUID의 관리자 삭제 버튼은 숨깁니다.

`PUT /api/v1/admin/images/{image_id}/verification` 요청은 `{"verified": true}`(승인) 또는 `{"verified": false}`(해제)입니다. 시스템 관리자만 가능하며 성공 시 갱신된 `ImageDetail`을 반환합니다. 승인에는 active 이미지, 소유자·생성 시각·Glance SHA-256/512가 필요합니다. 비관리자는 `403`, 검증 불가능한 상태/정체성은 `409`, 저장소 장애는 `503`입니다. 해제는 기존 승인 행을 제거합니다.

정본 테이블은 `image_verifications`입니다. 새 DB는 `python -m app.bootstrap`으로 만들며, 기존 DB의 명시적 SQL rollout은 `backend/migrations/manifest.txt` 순서에 따라 `081_image_verifications.sql`을 적용합니다. `image_created_at`·`verified_at`은 `DATETIME(6)`입니다. 기존 이미지에 대한 자동 backfill은 없습니다.

---

## GET /api/v1/images/{image_id}

이미지 상세 정보를 반환합니다.

### 응답 (200 OK) — `ImageDetail`

`ImageInfo`의 모든 필드에 더해 다음을 포함합니다.

| 필드 | 타입 | 설명 |
|------|------|------|
| `checksum` | string \| null | MD5 체크섬 |
| `container_format` | string \| null | 컨테이너 포맷 |
| `virtual_size` | integer \| null | 가상 크기(바이트) |
| `updated_at` | string \| null | 수정 일시 |
| `protected` | boolean | 삭제 보호 여부 |
| `tags` | array[string] | 태그 목록 |
| `properties` | object | 임의 메타데이터 |
| `os_hash_algo` / `os_hash_value` | string \| null | 해시 알고리즘/값 |
| `direct_url` | string \| null | 직접 접근 URL |

**오류**: `404 Not Found`

---

## DELETE /api/v1/images/{image_id}

이미지를 삭제합니다.

**응답**: `204 No Content` · **오류**: `500`(삭제 실패)

사용자·관리자 삭제 경로 모두 Glance 삭제가 성공한 뒤 Afterglow 검증 기록을 지웁니다. 검증 DB가 이때 접근 불가능하면 경고를 남기고 이미 완료된 삭제의 `204`는 유지합니다. 남은 기록은 Glance 이미지가 없거나 UUID·owner·생성 시각·콘텐츠 해시가 달라지면 검증 근거로 사용되지 않습니다.

---

## PATCH /api/v1/images/{image_id}

이미지 기본 메타데이터를 수정합니다. 값을 지정한 필드만 갱신됩니다.

### 요청 본문

```json
{ "name": "new-name", "os_distro": "ubuntu", "os_type": "linux", "min_disk": 20, "min_ram": 1024, "visibility": "private" }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | string \| null | 이미지 이름 |
| `os_distro` | string \| null | OS 배포판 |
| `os_type` | string \| null | OS 타입 |
| `min_disk` | integer \| null | 최소 디스크(GB) |
| `min_ram` | integer \| null | 최소 RAM(MB) |
| `visibility` | string \| null | 가시성 |

**응답 (200 OK)** — 갱신된 `ImageInfo`

---

## PATCH /api/v1/images/{image_id}/properties

이미지의 임의 property를 추가/수정/삭제합니다. **소유자 또는 시스템 관리자만** 가능합니다.

### 요청 본문

```json
{ "set": { "hw_qemu_guest_agent": "yes" }, "remove": ["old_key"] }
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `set` | object \| null | 추가/수정할 key-value |
| `remove` | array[string] \| null | 삭제할 key 목록 |

**응답 (200 OK)** — 갱신된 `ImageDetail`

**오류**: `403`(본인 소유 아님), `404`(없음), `400`(수정 실패)

---

## POST /api/v1/images/{image_id}/deactivate · reactivate

본인 프로젝트가 소유한 이미지를 비활성화/재활성화합니다. 비활성 이미지는 부팅에 사용할 수 없습니다.

**응답 (200 OK)**: `{"status": "deactivated"}` 또는 `{"status": "active"}`

**오류**: `403`(본인 소유 아님), `404`(없음), `400`(처리 실패)

---

## 이미지 멤버 (공유 프로젝트 관리)

`shared` 가시성 이미지를 특정 프로젝트에 공유하기 위한 멤버 관리입니다.

### GET /api/v1/images/{image_id}/members

공유 멤버(프로젝트) 목록을 반환합니다.

### POST /api/v1/images/{image_id}/members

**요청 본문**

```json
{ "member": "project-uuid" }
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `member` | string | 예 | 공유 대상 프로젝트 UUID |

**응답**: `201 Created`

### DELETE /api/v1/images/{image_id}/members/{member_id}

| 파라미터 | 위치 | 타입 | 필수 | 설명 |
|----------|------|------|------|------|
| `image_id` | path | string | 예 | 이미지 UUID |
| `member_id` | path | string | 예 | 공유 프로젝트 UUID |

**응답**: `204 No Content`
