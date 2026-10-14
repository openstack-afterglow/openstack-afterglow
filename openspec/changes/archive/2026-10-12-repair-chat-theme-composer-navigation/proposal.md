## Why

사용자 스크린샷과 보고에 따르면 Lumen 밝은 테마의 표면/박스 경계가 흐릿하고, 빈 채팅의 작성창이 이전 full-bleed 복원 이후 지나치게 넓다. 처음/이전/다음/최신 탐색 막대는 필요 없으며 프로젝트·대화 사이드바 전환이 ChatPanel을 재생성해 기록을 다시 읽는다.

## What Changes

- 기존 semantic palette와 dark theme를 보존하며 Lumen light canvas, assistant boxes, controls, selected history의 경계/표면 계층을 개선한다.
- 새 대화의 짧은 작성창은 48rem readable width로 제한한다. 초안이 160자 이상 또는 명시적 3줄 이상이면 기존 80rem content bound까지 확장하고 저장된 대화는 기존 content width를 유지한다. 짧게 줄이면 다시 compact로 돌아오고 Mobile은 viewport 안에 유지한다.
- 상단 처음/이전/다음/최신 막대와 사용하지 않는 first callback/locale keys를 제거한다. Opaque cursor pagination, 3×40-message memory bound, prepend scroll anchor, latest-response action은 유지하고 scroll edge에서 앞/뒤 page를 불러온다.
- 프로젝트 index/detail와 chat을 shallow client navigation으로 같은 ChatPanel에서 전환한다. URL/deep link/back-forward, 새 대화·project assignment, active stream, draft, sidebar state와 authority fences를 보존한다. 이미 선택된 대화로 복귀할 때 message page를 다시 조회하지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

Lumen light theme, empty composer width, bounded transcript scrolling, sidebar workspace navigation.

## Impact

Frontend chat components, affected route props/tests/locales, DESIGN.md, chat architecture/detail docs, CHANGELOG.md. Backend/native API, DB/schema, deployments, model/provider behavior에는 영향이 없다. 사용자 동시 변경/index/private inputs는 보존한다. 실제 Chromium에서 light/dark와 mobile/tablet/desktop, empty/long/existing draft, scroll paging, project/history/back-forward와 request counts를 검증한다. Identity/API는 합성 fixture이며 운영 인증·inference·배포 proof가 아니다.
