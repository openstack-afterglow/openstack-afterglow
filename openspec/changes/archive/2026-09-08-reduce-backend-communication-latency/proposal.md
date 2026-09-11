# Backend 통신 지연 병목 제거

## Why

사용자·관리자 화면에서 Backend API 응답을 기다리는 시간이 체감되며, 현재는 네트워크 왕복·Afterglow 처리·OpenStack 공급자 호출 중 어느 구간이 병목인지 구분할 관측 근거가 부족하다.

## What Changes

- 실제 읽기 전용 화면/API 시나리오의 지연을 계측해 느린 endpoint와 반복 요청을 식별한다.
- frontend 요청 수명주기와 backend/OpenStack 호출 경로를 추적해 확인된 병목만 수정한다.
- 기존 인증, 프로젝트 scope, cache freshness, background refresh 계약을 유지한다.
- 동일 시나리오로 수정 전후 지연과 요청 수를 검증한다.

## Constraints

- `dev` 브랜치와 기존 미커밋 작업을 보존한다.
- 운영 계측은 읽기 전용 요청만 사용하며 시크릿과 토큰을 출력하지 않는다.
- 사용자·관리자 권한 경계와 late-401 처리, 명시적 refresh 의미를 변경하지 않는다.
- 원인이 확인되기 전에는 추측성 cache나 timeout을 추가하지 않는다.

## Acceptance

- 체감 지연을 만드는 endpoint 또는 중복 요청 경로가 측정값으로 확인된다.
- 수정 전 실패하고 수정 후 통과하는 회귀 검증이 존재한다.
- 동일한 live-like 시나리오에서 지연 또는 불필요한 요청이 감소한다.
- 관련 exact target과 `npm run test:gate`가 통과한다.
