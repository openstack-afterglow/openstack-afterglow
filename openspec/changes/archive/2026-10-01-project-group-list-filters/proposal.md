## Why

관리자 프로젝트와 그룹 목록은 이름·ID·설명으로 검색하거나 도메인별로 좁힐 수 없고, 프로젝트는 Keystone의 ID 순 marker page를 그대로 보여준다. 신규 항목을 찾기 어렵고 현재 page만 정렬하면 전체 최신순을 보장하지 못한다.

## What Changes

- 프로젝트에 전체 목록 대상 이름·ID·설명 검색, 활성/비활성 및 도메인 필터를 추가한다. 검색·필터 변경은 첫 페이지로 돌아가며 prefetch와 refresh에 같은 조건을 사용한다.
- 그룹에 이름·ID·설명 검색과 도메인 필터, 결과 수와 초기화 및 조건에 맞는 결과가 없는 상태를 추가한다. 기존 멤버·수정·삭제 기능은 보존한다.
- 두 목록은 확인된 생성일 내림차순을 기본으로 사용한다. 프로젝트는 서버에서 전체 inventory를 정렬·필터한 뒤 marker page를 잘라낸다.
- Keystone의 생성일이 없으면 성공한 해당 자원의 생성 이벤트만 배치 조회한다. 최초 활동일·조회 시각·UUID를 생성일로 추정하지 않는다. 생성 기록이 없는 기존 항목은 `created_at: null`로 뒤에 표시하고 UI에 한계를 명시한다.
- 관리자의 프로젝트·그룹 생성도 안정적인 resource ID를 포함한 생성 이벤트를 남긴다. 기존 셀프서비스 `project_create` 및 Keystone 생성 notification 기록을 재사용한다.

## Capabilities

### New Capabilities

- 관리자 Identity inventory의 검색 및 상태/도메인 필터.

### Modified Capabilities

- 전체 inventory 기반 최신 생성순 및 필터를 보존하는 프로젝트 페이지 이동.
- 기존 activity store 기반의 nullable 생성일 투영.

## Impact

`admin_identity.py`, activity service, 프로젝트/그룹 route와 group type/card, 관련 기존 테스트에 국한한다. 기존 API 경로와 admin-only 권한, project page response envelope 및 group array response를 유지한다. 프로젝트 응답에는 필터 결과 총계 `total`과 전체 후보 `domain_ids`를 추가한다. DB schema·새 provider API·운영 배포·실제 OpenStack mutation은 범위 밖이다. 실제 생성 이벤트가 없는 과거 자원의 생성 순서는 복구할 수 없다. API 동작 회귀 및 실제 Chromium 합성 identity에서 검색·필터·page reset·최신순·반응형 UI를 확인한다.
