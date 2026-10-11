## Why

프로젝트 구성원 역할 편집은 모든 영역의 등급·세부 권한과 긴 유효 역할 목록을 세로로 펼쳐 확인과 수정이 어렵다. GCP 역할 선택처럼 먼저 영역을 고르고 그 영역의 권한만 편집할 수 있어야 한다.

## What Changes

- 기존 역할 편집 진입점·저장 API를 유지하고 Modal + Card로 viewport 안에 고정된 권한 탐색 창을 구성한다.
- 서버가 제공한 area별 목록에서 영역을 선택하면 그 영역의 등급·세부 권한만 표시한다. Desktop/tablet은 좌측 목록·우측 권한, mobile은 영역 선택 상자·권한 목록을 사용한다.
- 전체 역할의 이름·ID·설명 검색과 영역별 직접 선택/상속 개수를 제공한다. 검색 결과의 첫 사용 가능한 영역을 보여주되 원래 영역과 숨긴 선택을 잃지 않는다.
- 현재 서버 snapshot의 유효 역할은 개수 요약 뒤 접어서 표시하고, 제목·검색·취소·저장은 목록 스크롤과 분리한다.
- 직접 권한 ID 및 서버 transitive closure/external_role_ids, owner/admin·group-only·busy 보호는 변경하지 않는다.
- ko/en/ja/zh-CN UI 문구와 기존 소비자 회귀를 함께 이관한다.

## Capabilities

### New Capabilities

- 영역 우선 프로젝트 구성원 권한 탐색.

### Modified Capabilities

- 프로젝트 구성원 직접 역할 편집 UI의 정보 구조·스크롤 및 검색 결과 탐색.

## Impact

`ProjectMemberRolesModal.svelte`, 기존 관련 테스트, 네 account locale 및 디자인·아키텍처·변경 기록. Backend·API wire contract·역할 그래프·DB·의존성·운영 IAM/배포는 변경하지 않는다. 실제 Chromium의 합성 identity/API에서 영역 이동·검색·상속·저장 payload·취소·반응형과 테마를 검증하며 운영 권한 변경의 증거로 간주하지 않는다.
