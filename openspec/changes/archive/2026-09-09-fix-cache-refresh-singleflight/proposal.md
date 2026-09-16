## Why

동일 cache key의 일반 miss가 실행 중일 때 `refresh=True` 요청이 그 작업에 합류하면 명시적 refresh가 자신의 loader를 실행하지 않고 오래된 snapshot을 반환한다. 기존 작업과 refresh가 별도로 실행되더라도 완료 순서에 따라 오래된 작업이 새 cache 값을 덮어쓸 수 있으므로 freshness 계약이 깨진다.

## What Changes

- 명시적 refresh는 동일 key의 선행 작업 뒤에 연결하되 항상 자신의 loader를 실행한다.
- refresh가 선행 작업 완료 후 cache를 삭제하고 새 값을 기록하게 해 이전 작업이 refresh 결과를 덮어쓰지 못하게 한다.
- 일반 cache miss single-flight와 요청 취소 격리 계약은 유지한다.
- Event로 선행 loader를 정지한 회귀 테스트에서 refresh 반환값과 최종 cache 값이 모두 새 값인지 검증한다.

## Capabilities

### New Capabilities

- 없음.

### Modified Capabilities

- Cache abstraction의 `refresh=True`는 동시 실행 중인 동일 key 작업과 무관하게 새 loader 실행과 최종 cache freshness를 보장한다.

## Impact

`backend/app/services/cache/__init__.py`의 cache load 순서와 `backend/tests/test_cache_abstraction.py`의 refresh 회귀 검증이 변경된다. API, 인증, TTL, 일반 cache-hit 및 일반 miss single-flight 계약은 변경하지 않는다.
