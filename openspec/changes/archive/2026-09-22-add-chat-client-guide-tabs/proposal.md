## Why

채팅 설정의 연결 방법 영역이 OpenAI SDK, Anthropic SDK, Codex CLI, Claude Code 문서를 한꺼번에 펼쳐 긴 스크롤과 낮은 탐색성을 만든다. 사용자가 원하는 클라이언트를 먼저 선택하고 필요한 설정만 읽고 복사할 수 있어야 한다.

## What Changes

- 연결 방법 영역에 Codex, Claude Code, OpenAI, Claude 선택 버튼을 제공한다.
- 기본 선택은 Codex로 두고 선택한 클라이언트의 설명, 설치·환경 변수 안내, 설정 예제와 복사 동작만 표시한다.
- 공통 Tabs primitive를 사용해 키보드 탐색, 선택 상태, tab/panel 연결을 유지한다.
- 기존 discovery 기반 URL 검증, 일반 Lumen API 키 사용, provider 선택 안내와 복사 payload는 유지한다.

## Capabilities

### New Capabilities

- `chat-client-connection-guides`: 채팅 설정에서 클라이언트별 Lumen 연결 문서를 선택하고 복사하는 반응형·접근 가능한 안내 경험.

### Modified Capabilities

없음.

## Impact

- `frontend/src/lib/components/chat/ChatApiKeysManager.svelte`
- `frontend/src/lib/components/chat/__tests__/ChatApiKeysManager.test.ts`
- 공통 `frontend/src/lib/components/ui/Tabs.svelte`를 변경 없이 재사용한다.
- Backend API, 인증·권한, discovery 응답, 배포 구조에는 영향이 없다.
