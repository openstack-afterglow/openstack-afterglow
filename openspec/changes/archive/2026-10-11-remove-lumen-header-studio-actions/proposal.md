## Why

Lumen의 텍스트 채팅 상단에 제거하기로 한 이미지 Studio·오디오 Studio·실시간 음성 바로가기 버튼이 여전히 표시된다. 서비스 사이드바에 있는 별도 Studio 목적지는 유지하고 채팅 toolbar의 중복 진입점만 제거한다.

## What Changes

- `ChatPanel.svelte`의 상단 이미지 Studio·오디오 Studio·실시간 음성 버튼 markup과 해당 권한 조건을 제거한다. CSS로 숨기거나 다른 메뉴로 옮기지 않는다.
- 이 세 버튼에만 쓰이던 여섯 번역 키를 ko/en/ja/zh-CN 카탈로그에서 함께 삭제한다.
- 모델·에이전트·기록·출처·임시 채팅과 기존 Studio sidebar/global drawer/command palette 목적지, 직접 route 및 서비스 인가·API를 유지한다.
- 실제 frontend를 실행한 Chromium에서 네 locale, light/dark, mobile/tablet/desktop 및 breakpoint의 버튼 부재와 유지된 컨트롤·탐색을 확인한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

Lumen 텍스트 채팅 toolbar의 표시 계약만 변경한다. Studio 및 realtime 기능·직접 URL은 삭제하지 않는다.

## Impact

변경 source는 ChatPanel과 네 chat-panel 카탈로그로 제한한다. 새 의존성·설정·backend·DB schema·권한·서비스 소유권 구조에는 영향이 없다. 기존 사용자 변경과 운영 컨테이너/DB는 보존하고 이번 작업에서 배포·재시작·commit/push하지 않는다. 문서와 architecture scoped review는 실제 검증 뒤 갱신한다.
