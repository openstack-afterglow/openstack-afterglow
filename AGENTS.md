# Afterglow — AI 에이전트 시작 지침

이 파일과 `CLAUDE.md`는 2,000자 이내의 시작 지침이다. 작업별 상세 규칙은 [`docs/agent-development-guide.md`](docs/agent-development-guide.md)에 원문 그대로 보존했다. 코드·설정·배포·UI·테스트 작업 전 해당 가이드의 관련 절과 root `ARCHITECTURE.md`를 읽고 적용한다. UI는 `DESIGN.md`, Union Mount는 `union.md`도 읽는다. 현재 source가 오래된 문서보다 우선한다.

- AI 개발은 `dev`에서만 한다. `main` 직접 커밋·force-push 금지. `dev → main` PR·머지는 pie_root가 수행한다. 기존 사용자의 변경을 덮어쓰지 않는다.
- 시작 전 목표·범위·제약·완료 기준을 정한다. 새로운 기능·수정은 OpenSpec change와 checklist로 추적하고 완료 시 archive한다.
- 코드·설정·스키마·의존성·배포·테스트 변경은 영향받는 `ARCHITECTURE.md`와 상세 문서를 함께 검토·갱신한다. 변경 전후 아키텍처 검증 절차는 상세 가이드를 따른다.
- 백엔드 endpoint에는 pytest를 추가한다. 정확한 selector부터 관련 target까지 검증하고, 커밋 전 프로젝트의 `npm run test:gate`를 따른다. 미실행·실패는 명시한다.
- 운영 Compose/볼륨·인증정보·키를 보존한다. 광역 prune, `down --volumes`, 개발 HTTP endpoint의 운영 사용, 시크릿 커밋을 금지한다. 배포·상태 변경은 별도 승인 범위를 따른다.
- 설정 변경 시 예시·K8s 생성 경로를 동기화하고 비밀은 secret에 둔다. 구현 결과는 변경 파일·검증 증거·남은 위험으로 보고한다.

긴 절차를 이 시작 파일에 되돌려 붙이지 않는다. 새로운 규칙은 상세 가이드의 해당 절에 기록하고, 시작 파일에는 판단에 꼭 필요한 한 줄만 남긴다.
