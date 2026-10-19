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
| `gpu_vendor` | string \| null | 명시적 Glance property. `nvidia`, `amd`, `intel`; 이름/OS에서 추정하지 않음 |
| `gpu_driver` | string \| null | 명시적 사전 설치 드라이버 종류. `nvidia`, `nvidia-grid`, `nouveau`, `amdgpu`, `i915`, `xe`, `none`; 알 수 없는 값은 opaque metadata로 보존 |
| `created_at` | string \| null | 생성 일시 (ISO 8601) |
| `owner` | string \| null | 소유 프로젝트 UUID |
| `visibility` | string \| null | `private` \| `public` \| `shared` \| `community` |
| `protected` | boolean | Glance 삭제 보호 상태. 관리자·사용자 목록에서도 보존되며 관리자 목록의 삭제 작업을 보호된 업로드에 제공하지 않음 |
| `os_hash_algo`, `os_hash_value` | string \| null | Glance가 계산한 원본 콘텐츠 해시 |
| `verification_status` | string | `verified`(승인과 현재 이미지 일치), `unverified`(승인 없음·불일치·비활성), `unavailable`(검증 저장소 조회 실패) |
| `verified_at` | string \| null | 현재 승인 기록의 UTC 시각. 검증되지 않았으면 `null` |

검증은 **관리자 승인 기록이지 악성코드 검사 결과가 아닙니다**. 기존 public 이미지, admin 프로젝트 소유, 사용자가 설정한 properties/tags는 검증 근거가 아닙니다. 승인 기록은 이미지 UUID·소유 프로젝트·생성 시각(마이크로초 보존)·Glance SHA-256/512에 묶입니다. 기록이 없거나 정체성이 바뀌면 미검증이며, DB 장애를 미검증 또는 검증됨으로 숨기지 않습니다.

### VM 생성 화면의 태그 선택

이미지 이름 카드를 펼치면 바로 아래에서 그 repository의 태그 이름을 검색하고 **태그 이름 · 해시값 · 업로드 시각 · 용량**의 단일 행으로 선택합니다. 검색은 앞뒤 공백·대소문자를 무시하며 다른 이름 카드를 열면 초기화합니다. 좁은 화면에서는 목록 안에서만 가로 스크롤합니다.

Current 업로드는 검색/OS 조건을 적용하기 전의 repository·tag별 최신 `created_at`(마이크로초 포함)으로 정합니다. 비활성 최신 업로드를 과거 active UUID로 대체하지 않으며 선택은 실제 이미지 `id`를 사용합니다. 검색·카드 접기·전환은 기존 선택을 바꾸지 않고 과거/누락 UUID의 경고도 유지합니다.

VM 생성은 Flavor를 먼저 선택한다. 선택한 GPU Flavor의 vendor/장치 요청과 `gpu_vendor`·`gpu_driver`를 대조하여 **current active이며 관리자 검증된** 사전 설치 드라이버 이미지를 추천한다. 이미지 이름에 GPU/CUDA가 있다는 이유만으로 드라이버 설치나 적합성을 주장하지 않는다. GPU 모델·버전·호스트/vGPU 및 라이선스 호환성은 별도 확인 사항이다. CPU Flavor는 GPU driver metadata가 없는 일반 이미지를 우선 안내하고, GPU driver 이미지를 명시적으로 선택하면 불필요한 오버헤드를 경고한다. 추천은 사용자 선택 UUID를 자동 변경하거나 다른 이미지를 차단하지 않는다.

이미지 소유자/관리자는 기존 properties API에서 실제 게스트에 준비한 값만 설정한다. 예: `PATCH /api/v1/images/{image_id}/properties`의 `{"set":{"gpu_vendor":"nvidia","gpu_driver":"nvidia"}}`. Native Glance property 제한·소유권을 그대로 적용하며 설정 자체는 드라이버 설치·관리자 검증 승인이 아니다. 기존 검증은 이미지 UUID/owner/created_at/hash에 대한 승인이지 가변 GPU metadata의 설치·호환성 인증이 아니다. 일반 이미지는 `gpu_driver=none`으로 명시할 수 있다. RAM 최소 요구량은 선택 Flavor와 대조하지만 `min_disk`는 별도 Cinder 부팅 볼륨 크기로 충족하므로 Flavor의 nominal disk보다 크다는 이유만으로 추천에서 제외하지 않는다.

Glance SHA-256/512는 축약 표시와 전체 title·접근성 이름, `created_at`은 현재 언어·브라우저 시간대의 초 단위 시각과 전체 ISO title, `size`는 사람이 읽는 용량으로 표시합니다. 날짜·크기를 알 수 없으면 `-`이며 이미지 UUID는 이 선택 행에서만 숨깁니다. 기존 catalog·관리자 상세의 SHA·UUID 표시는 그대로입니다. 태그 목록 표시는 추가 조회를 하지 않으며 Flavor 추천에는 위 `gpu_vendor`·`gpu_driver` 목록 필드를 사용합니다.

VM chooser의 compact 표시는 SHA 값의 앞 8자리만 보이며 알고리즘 이름·suffix는 생략합니다. 전체 알고리즘·SHA는 기존 title·aria-label에 보존하고 태그 이름 셀 전체의 native title로 전체 태그를 확인합니다. 메타데이터 열을 좁혀 태그 이름이 남은 폭을 쓰지만 초 단위 시각·용량 내용은 유지합니다. 이는 서버 SHA 값이나 이미지 identity를 축약하는 계약이 아니며 8자리 prefix로 UUID를 비교하거나 합치지 않습니다.

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
| `gpu_vendor` | string | 아니오 | 미지정 | 명시적 GPU 제조사: `nvidia`/`amd`/`intel` 또는 빈 문자열 |
| `gpu_driver` | string | 아니오 | 미지정 | 사전 설치 드라이버: `nvidia`/`nvidia-grid`/`nouveau`/`amdgpu`/`i915`/`xe`/`none` 또는 빈 문자열 |

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
| `gpu_vendor` | string \| null | 제조사 선언. 업로드와 같은 허용 값. 생략/null은 변경하지 않음 |
| `gpu_driver` | string \| null | 드라이버 선언. 업로드와 같은 허용 값. 생략/null은 변경하지 않음 |

Typed GPU metadata를 포함한 수정은 공급한 표준 필드와 함께 단일 native Glance JSON Patch로 저장하고 재조회한다. Shared/public 이미지를 사용하는 다른 프로젝트의 목록 cache도 무효화한다. 허용하지 않은 typed 선언은 native 호출 전에422이며 임의 properties API는 기존 opaque 속성 계약을 유지한다. GPU metadata 입력은 사전 설치된 게스트 상태를 설명할 뿐 드라이버를 설치하지 않는다.

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

### 브라우저의 Windows 설정

사용자 **Compute → 이미지** 또는 **관리자 → 이미지**의 개별 상세에서 **Windows 설정 → Windows 메타데이터 설정**을 엽니다. 이미지 소유자 또는 관리자만 저장할 수 있습니다. 실제 게스트 준비를 확인하고 현재→변경값을 검토한 뒤 **메타데이터 저장**을 누르면 기존 properties API의 단일 요청/Glance JSON-Patch로 달라진 값만 적용합니다. 임의 속성 편집기와 동시에 편집하지 않으며 실패 시 초안을 유지합니다.

| 적용 범위 | 속성 | 값 / 조건 |
|---|---|---|
| 기본 | `os_type` | `windows` — Afterglow의 OS 판정 근거 |
| 기본 | `os_distro` | `windows` — 배포판 표시·분류 |
| 기본 | `os_admin_user` | 실제 게스트에서 준비한 로컬 계정. 예: `Admin`; RDP의 `.\Admin` 표기와 구분 |
| 기본 | `windows_initial_password_method` | `nova-adminpass-configdrive` — Afterglow가 지원하는 최초 암호 전달 계약 |
| 기본 | `img_config_drive` | `mandatory` — 이미지가 ConfigDrive를 요구함 |
| 선택: 준비된 x86 Windows 11 | `hw_firmware_type` | `uefi` |
| 선택: 준비된 x86 Windows 11 | `hw_machine_type` | `q35` |
| 선택: 준비된 x86 Windows 11 | `hw_tpm_version` | `2.0` |
| 선택: 준비된 x86 Windows 11 | `hw_tpm_model` | `tpm-crb` |
| 선택: 준비된 x86 Windows 11 | `os_secure_boot` | `required` |
| 선택: 실제 설치된 에이전트 | `hw_qemu_guest_agent` | `yes` — QGA 설치·구성 확인 시만 적용; 최초 암호 전달의 필수 조건은 아님 |

프리셋의 현재값/변경 판정은 실제 `properties`를 기준으로 합니다. 목록·상세 표시용 `os_distro`는 이미지 이름에서 추측될 수 있으므로, 실제 배포판 property가 없으면 `os_distro=windows`를 필수 변경에 포함합니다.


선택하지 않은 하드웨어/QGA 키는 삭제하거나 비활성화하지 않습니다. 디스크·NIC 버스/드라이버, CPU 토폴로지, 공개 범위, 소유자, 해시, 관리자 검증 및 `production_ready` 같은 무관한 속성도 보존합니다. `min_disk`/`min_ram`은 예약된 기본 metadata 필드이므로 이 properties 요청에 넣지 말고 기존 이미지 수정에서 실제 이미지 요구량으로 지정하세요. VM wizard는 선택 이미지의 최소 디스크보다 작은 초기 초안을 올리고 더 큰 초안은 줄이지 않으며, 부족한 정수 용량은 다음 단계·제출에서 차단합니다. 예를 들어 `min_disk=80` 이미지에는80GB 이상이 필요합니다.

**플래그가 대신하지 않는 준비:** 이미지 내부 Cloudbase-Init의 `inject_user_password=true`, `ConfigDriveService` 우선 공급자와 활성 `SetUserPasswordPlugin`, 실제 로컬 계정 일치, 최초 부팅용 일반화·봉인과 저장소/네트워크 드라이버가 필요합니다. RDP에서 강제 최초 암호 변경이 접속을 막지 않도록 게스트의 `first_logon_behaviour` 정책도 확인하세요(`no`는 강제 변경 없음). UEFI/GPT·서명된 부트 체인과 호스트 OVMF/q35·Secure Boot/vTPM 지원은 선택한 Windows11 구성에 맞아야 합니다. RDP 활성화·방화벽·허용된 출발지의 보안 그룹은 별도입니다. ConfigDrive의 평문 초기 암호 보호와 실제 첫 부팅·RDP 로그인 검증은 운영자 책임입니다.

`cloudbase-user-data` 또는 `inject_user_password=false`인 이전 게스트를 marker만 바꾸어 네이티브 지원 이미지로 만들 수 없습니다. 먼저 별도 이미지에서 게스트를 준비하고 실제 암호로 부팅·로그인을 확인하세요. 브라우저 확인란은 운영자 확인이지 게스트 검사/승인이 아니며, 메타데이터 저장이나 Nova ACTIVE도 서비스 준비 완료 증거가 아닙니다. 기존 VM/볼륨의 암호를 바꾸거나 게스트를 설치·봉인하지 않습니다.

사용자/admin properties 저장은 모든 프로젝트의 Glance 목록 캐시를 무효화해 다음 카탈로그·wizard 조회가 새 OS/계정/방식을 읽도록 합니다. SDK가 별도 필드로 분리한 ConfigDrive·machine type·Secure Boot·QGA도 상세 `properties`로 재투영합니다. Glance 버전 상대 경로로 PATCH하고 공급자 오류를 명시적으로 전파하므로 실패 응답을 성공한 저장으로 반환하지 않습니다. 저장 응답은 공급자의 새 상세 재조회 결과입니다.

참고: [Nova ConfigDrive](https://docs.openstack.org/nova/latest/user/metadata.html), [UEFI](https://docs.openstack.org/nova/latest/admin/uefi.html), [Secure Boot](https://docs.openstack.org/nova/latest/admin/secure-boot.html), [emulated TPM](https://docs.openstack.org/nova/latest/admin/emulated-tpm.html), [Cloudbase-Init password plugin](https://cloudbase-init.readthedocs.io/en/latest/plugins.html#setting-password-main).


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
