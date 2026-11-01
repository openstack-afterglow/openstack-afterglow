## Why

사전 관측 catalog는 기존 flavor cache wildcard를 공유하지만 수동 extra-spec POST/DELETE는 무효화를 호출하지 않아 성공한 편집이 다음 wizard 목록에 최대90초 늦게 보일 수 있다.

## What Changes

- 두 기존 수동 spec writer가 성공한 뒤 기존 `afterglow:nova:*:flavors` 무효화를 호출한다.
- 따뜻한 Redis catalog가 있는 상태에서 숨김 spec 추가/삭제 후 실제 목록 변화와 수동 refresh의 advisory 계약을 검증한다.
- 수동 refresh는 현재 저장 관측을 다시 읽고, submit-time admission만 native fresh라는 현재 계약을 문서에서 명확히 구분한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

기존 관리자 spec 편집 뒤 카탈로그 cache invalidation 보완.

## Impact

기존 두 API handler와 behavior regression·상세 문서만 변경한다. 응답/schema/권한·DB migration은 바꾸지 않는다. Background publisher와 외부 native 쓰기의 분산 원자성 보장은 추가하지 않는다. 기본 로컬/운영 서비스는 재기동하지 않고 현재 후보 backend 이미지만 다시 검증한다.
