# 채팅 설정 팝업 복원

## 목표

독립 `/dashboard/chat/settings` 화면으로 전환된 채팅 설정을 기존 채팅 화면 위의 큰 모달 오버레이로 복원한다. 사용자 피드백상 독립 페이지의 실제 콘텐츠가 화면 폭에 비해 지나치게 작아 탐색성과 정보 밀도가 떨어진다.

## 설계

- 채팅 사이드바 설정과 명령 팔레트 사용량 항목은 URL 이동 없이 `ChatSettingsOverlay`를 연다.
- 오버레이는 사용량, API 키, 메모리, MCP 서버, 도구, 스킬 탭과 이번 변경에서 추가한 주간 쿼터 및 API 키 rename/한도 기능을 그대로 유지한다.
- Lumen OAuth 복귀 URL인 `/dashboard/chat/settings?section=mcp&...`는 제거하지 않는다. 해당 라우트는 채팅 패널을 렌더하고 지정 섹션의 오버레이를 즉시 열어 deep-link 계약을 보존한다.
- mobile에서는 모달이 viewport 안에서 스크롤 가능하고, tablet/desktop에서는 기존 최대 52rem 폭의 모달을 사용한다.

## 영향 범위

Afterglow frontend의 채팅 설정 컴포넌트, ChatPanel 상태 연결, 설정 deep-link route, 관련 테스트·문서·architecture 기록만 변경한다. Lumen API와 OAuth redirect 경로는 변경하지 않는다.
