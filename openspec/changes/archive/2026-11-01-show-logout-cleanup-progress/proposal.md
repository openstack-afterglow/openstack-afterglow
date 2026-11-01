## Why

로그아웃이 서버 응답을 기다리는 동안 기존 화면에 머물러 동작이 보이지 않는다. 사용자는 즉시 전용 페이지에서 세션 정리와 웹 인증정보 제거 상태를 확인하고 직접 로그인으로 돌아가길 요청했다.

## What Changes

- 명시 로그아웃은 네트워크 정리 전에 /logout으로 이동한다. 전용 페이지는 실제 진행·완료·부분 실패를 보여주며 자동 로그인 이동을 하지 않는다.
- refresh/late response fencing, cloud shell 종료, 최신 토큰 서버 폐기, browser credential 제거와 탭 broadcast를 공유 workflow로 유지한다. 서버 실패도 local cleanup을 막지 않으며 확인되지 않은 서버 폐기를 성공이라고 하지 않는다.
- header·workspace selector의 일반 로그아웃과 보안 설정의 확인된 전체 로그아웃이 같은 화면을 사용한다. 자동401·비밀번호 변경 등 비명시 보안 종료는 기존 계약을 유지한다.
- 무자격 직접 접근/재새로고침은 idempotent이며 비밀은 URL/새 저장소에 넣지 않는다. 모든 지원 locale과 기존 primitives를 사용한다.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
명시적 로그아웃의 즉각적인 진행 피드백과 지속되는 완료 화면.

## Impact
Frontend route·공유 logout workflow·명시 진입점·public route guards·9locale·관련 테스트와 문서. Backend API/schema/운영 설정 변경·배포는 없다. dev 공유 tree/index를 보존한다.
