# Afterglow 작업 규칙

- `dev`에서만 작업한다. `main` 배포·병합은 관리자 권한이다. 기존 작업 트리 변경을 보존하고 목표·범위·설계·완료 기준을 먼저 정한다. 요청 없는 commit/push/deploy는 하지 않는다.
- 작업 전 [`ARCHITECTURE.md`](ARCHITECTURE.md)와 변경 영역의 source·문서를 읽는다. 현재 source가 계획·과거 기록보다 우선한다. code/config/schema/deploy/test 변경은 관련 architecture·`docs/`를 같이 갱신하고, 구조 영향이 없으면 최신 review summary에 근거를 남긴다. 실제 source를 검토한 뒤에만 `python3 scripts/check_architecture.py --stamp --summary "검토 내용"`; 제출 전 `--staged` 검사.
- 신규 작업은 `openspec new change <slug> --schema rapid`로 기록하고 proposal/tasks를 작성·갱신한다. 승인 없이 archive하지 않는다. 상세 작업 계약: [`agent-workflow`](openspec/specs/agent-workflow/spec.md).
- 테스트는 정확한 selector → 도메인 target → 필요한 전체 gate 순으로 실행한다. backend endpoint에는 소비자 행동 테스트가 필요하다. unit/contract/functional/live 결과를 구분하고 실행하지 않은 검증은 통과로 쓰지 않는다. commit이 승인된 경우 `npm run test:gate` 통과 후 변경 파일만 stage한다.
- 시각 변경 전 [`DESIGN.md`](DESIGN.md)의 responsive hierarchy를 읽고 공통 token/primitive를 우선 사용한다. 모바일·태블릿·데스크톱 실화면에서 확인한다. Palimpsest 작업은 `docs/palimpsest.md` → `docs/squashfs-layer-pipeline.md` → `union.md` 순으로 읽는다.
- Compose 개발/운영/테스트 환경을 혼용하거나 volume·타 프로젝트를 삭제하지 않는다. 신규 API는 `/api/v1`에만 mount하고 project ownership·admin 권한을 검증한다. shell/cloud-init 입력은 검증·인용하고 비밀은 secret.yaml 경계 밖에 기록하지 않는다. 세부 예외와 설정 동기화: [`agent-runtime-security`](openspec/specs/agent-runtime-security/spec.md).
- CI 변경은 전후 실측과 계약 검증에 근거한다. 테스트 실패를 가린 발행, PR 코드의 self-hosted runner·비밀 접근을 금지한다. 이벤트별 gate·중복 실행·shard·revision 판단: [`agent-ci-safety`](openspec/specs/agent-ci-safety/spec.md).

결과에는 변경 경로, 실행한 검증, 미검증·위험을 구분해 기록한다. `CLAUDE.md`는 이 파일을 가리키는 링크다.
