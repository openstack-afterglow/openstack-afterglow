## Why

현재 공개 IAM 가이드는 등급별 권한을 긴 목록으로 설명하여 상위 등급에 무엇이 포함되는지 한눈에 파악하기 어렵다. 사용자 요청에 따라 실제 포함 관계를 본문 그래프로 시각화한다.

## What Changes

- 프로젝트 역할과 Waygate·Drover·Lumen·Palimpsest 네 서비스의 등급 절에 정적 방향 그래프를 표시한다.
- 프로젝트는 `project_owner → project_admin → project_member → project_reader`, `project_member → member`, `project_reader → reader` 연결을 표시한다.
- 서비스는 `_admin → _editor → _user → _reader`의 native 기본 정책 기능 포함을 표시한다. 실제 Keystone 역할 상속과 구분하고 세부 역할 자동 부여로 설명하지 않는다.
- 작은 typed hierarchy 데이터와 docs 전용 Svelte 컴포넌트로 SSR/무JavaScript·화면낭독기·좁은 화면·두 테마를 지원한다. 외부 그래프 라이브러리·별도 viewer·시각 토큰은 추가하지 않는다.
- 그래프 설명은 기존 strict 문서 번역과 검색에 연결하고 아홉 언어를 보존한다. 기존 상세 작업·소유권·credential 조건은 유지한다.

## Capabilities

### New Capabilities
- 공개 문서의 접근 가능한 역할 포함 관계 그래프.

### Modified Capabilities
- 문서 번역·검색이 그래프의 설명과 변경되지 않는 역할 식별자를 처리한다.

## Impact

Frontend 문서 data/type/translate/search/render와 관련 설명 문서만 변경한다. API·Keystone 역할 연결·정책·스키마·설정·운영 배포는 변경하지 않는다. 다른 미커밋 작업과 직전 IAM commit은 보존하며 이번 요청에는 commit/push가 포함되지 않는다.
