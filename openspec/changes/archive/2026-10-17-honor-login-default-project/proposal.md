## Why

사용자가 프로필에서 기본 프로젝트를 저장해도 새 로그인은 도메인의 `Default`로 들어간다. 최근 `_prepare_domain_session` 자동 진입 변경이 Keystone 사용자 `default_project_id`를 무시하고 도메인 Default를 우선 선택하면서 생긴 회귀다.

## What Changes

- 명시한 프로젝트 선택을 최우선으로 보존한다.
- 자동 선택은 선택 도메인의 활성·접근 가능한 사용자 기본 프로젝트 → 도메인 Default → 기존 프로젝트 목록 첫 항목 순서로 처리한다.
- Password와 설정 기반 provider callback의 공통 native scope 준비 경로에서 수정한다. 다른 도메인·비활성·권한 회수·삭제된 기본 프로젝트는 권한을 만들지 않는다.
- Default 생성/reader·owner/manager 정책은 그대로 유지한다. 실제 최종 native scope 확인과 session 발급 전 검증도 보존한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- 로그인 기본 프로젝트 우선순위와 응답 hint를 실제 사용자 선호와 접근 가능한 inventory에 맞춘다.

## Impact

`backend/app/api/identity/auth.py`, 관련 native 로그인 consumer 회귀, 로그인 API/검증 문서·changelog·architecture 기록. 새 설정·schema·의존성·라우터·service ownership·deployment topology 없음. 사용자 private 설정/index/volumes 보존. 실제 사용자 GitLab 로그인·운영 native 변경·운영 배포는 이 수정의 검증 범위가 아니다.
