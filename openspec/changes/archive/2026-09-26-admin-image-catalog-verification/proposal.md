## Why

관리자 이미지 목록은 사용자 repository/tag 카탈로그와 달리 평면 marker 페이지에 머물러 있다. 페이지 내부에서만 묶으면 repository의 다른 버전을 잃으며, 현재 사용자 카탈로그는 업로드일 대신 updated_at을 우선한다. 사용자는 관리자도 같은 카드·태그 탐색과 최신 업로드 우선 정렬을 원하고 관리자 검증/커뮤니티 미검증을 구분하기를 요청했다.

## What Changes

- 관리자/사용자 공통 repository 그룹·태그 필터·카드를 재사용한다. 관리자 목록은 전체 Glance marker 페이지를 읽은 뒤 그룹화하여 repository가 페이지 경계에서 분리되지 않게 한다. UI 페이지 단위는 repository/태그 결과 기준이며 기존 관리자 상세·수정·삭제·활성/비활성 액션을 유지한다.
- 기본 정렬은 created_at 내림차순. repository 대표 및 순서는 포함된 이미지의 최대 업로드일이다. 잘못된/없는 날짜는 마지막, 동률은 이름/ID로 결정적 정렬한다. updated_at 변경으로 위로 올라오지 않으며 사용자가 이름순·관련도순을 선택할 수 있다.
- 사용자는 명시적 관리자 검증 정책을 선택했다. 기존 이미지/public/private/프로젝트명으로 신뢰를 추정하지 않는다. 새 관리자 업로드는 검증 기록을 만들고 기존 이미지는 관리자 승인/해제로 전환한다. 이 표시는 관리자 승인이지 악성코드 스캔 증명이 아니다.
- 검증은 서버 소유 DB 레코드로 관리하며 이미지 ID·소유 프로젝트·생성 시각·콘텐츠 해시를 묶는다. Glance 임의 property/tag로 위조하거나 승인 해제 뒤 예전 property를 복원하여 재승인할 수 없어야 한다. 해시/소유자 불일치는 미검증, DB 조회 장애는 unavailable로 명시한다.
- 두 화면의 repository 카드에는 검증/미검증 수, 각 태그에는 상태를 표시하고 검증 상태 필터를 추가한다. 공개 범위는 별도로 유지한다.

## Capabilities

### New Capabilities

- 관리자 전용 이미지 검증 승인·해제 및 영속 provenance.
- 관리자 repository 카드 기반 카탈로그와 검증 상태 탐색.

### Modified Capabilities

- 사용자 이미지 카탈로그 최신 업로드 정렬과 신뢰 배지.
- 이미지 목록·상세 응답에 verification_status(verified/unverified/unavailable), verified_at 필드 추가.

## Impact

- Backend: image schemas, Glance projection, compute/admin image APIs, SQLAlchemy verification table/service and behavioral regression tests.
- Frontend: shared catalog state/components, user/admin page, image types/detail badge and admin behavior tests. Existing mutation permissions/visibility semantics remain unchanged.
- Contract: PUT /api/v1/admin/images/{image_id}/verification with {verified:boolean}, returning ImageDetail; only system administrators may mutate. Non-active/unidentifiable image approvals fail explicitly. No user-authorable verification field.
- Preserve all current unrelated worktree changes and previous usage-report implementation. No commit/push or production deployment requested.
- Verification: focused image/domain/design tests, svelte-check, actual authenticated browser mobile/tablet/desktop and cutovers, amd64/arm64 builds, canonical local Compose deployment with volumes/siblings preserved, full gate, docs/architecture stamp and archive.
