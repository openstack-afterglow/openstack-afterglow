## Why

사용자가 새 `afterglow-logo.svg`, `afterglow-symbol.svg`, `favicon.svg`를 제공했다. 기존 raster 로고·favicon과 링 마크, 별도 랜딩 심볼 참조가 남아 있어 모든 기본 브랜딩을 새 자산으로 통일해야 한다.

## What Changes

- 로그인/관리자 브랜딩 preview의 기본 로고는 `afterglow-logo.svg`, 사이드바와 랜딩 기본 심볼은 `afterglow-symbol.svg`, favicon은 `favicon.svg`를 사용한다.
- frontend/backend fallback, 예시 설정, setup 및 K8s/Helm/Kolla 생성 경로를 같은 SVG 기본값으로 변경한다.
- 커스텀 로고·favicon 및 관리자 업로드 우선순위와 보안 정책은 유지한다. 제거할 구형 bundled 경로만 기존 설정·생성 결과에서 교체하며 credentials·DB·운영 배포는 변경하지 않는다.
- 새 wordmark의 글자색만 embedded SVG theme media query로 다크/라이트 배경에 대응하고, 가로 로고는 로그인 컨테이너 안에 비율을 유지해 표시한다.
- 추가 요청에 따라 artwork 경계를 기준으로 좌우 여백을 맞춘다. 가로 로고의 wordmark는 이미 번들한 Pretendard의 Latin(Inter-derived) bold glyph를 path로 변환해 OS/font fallback에 따른 폭 변동을 없앤다. 이미 좌우 대칭인 심볼·favicon 도형은 보존한다.
- 구형 raster/랜딩 심볼/RingMark를 제거하고 실제 브라우저에서 반응형·테마·자산 로딩을 검증한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- 기본 사이트 브랜딩 자산의 SVG 전환. 기존 API 필드와 커스텀 브랜딩 계약은 유지한다.

## Impact

- frontend 브랜딩 UI/config/head, backend 설정 기본값, 배포·설치 예시/생성기와 관련 테스트.
- 정적 브랜드 자산, `DESIGN.md`, `ARCHITECTURE.md`, `CHANGELOG.md`, 브랜딩 API 상세 문서.
- commit/push, 운영 배포, provider 호출, 인증정보·데이터 변경은 범위 밖이다.
