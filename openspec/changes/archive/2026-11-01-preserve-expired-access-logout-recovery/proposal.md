## Why

전용 logout workflow가 replayOnUnauthorized:false로 기존 expired-access401→refresh→fresh-token logout 복구를 막았다. 실제 API client를 연결한 일반/전체 로그아웃 회귀2개가 실패해 서버 세션 미폐기 위험을 재현했다.

## What Changes

- suppressAuthRedirect는 유지하고 기존 owner-fenced401 인증 복구만 허용한다. 네트워크/503 mutation 재전송은 추가하지 않는다.
- 실제 client·workflow 통합 회귀로 두 logout endpoint의 expired-token 복구와 network/503 non-replay를 검증한다.

## Capabilities

### New Capabilities
없음.

### Modified Capabilities
만료된 access와 유효 refresh의 명시 로그아웃 서버 세션 폐기 보존.

## Impact
Frontend logout 호출 옵션·회귀·상세 기록만 수정. Backend/schema/배포/공유 index 변경 없음.
