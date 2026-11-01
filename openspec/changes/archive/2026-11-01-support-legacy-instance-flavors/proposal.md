## Why

기존 인스턴스는 Nova가 원래 flavor 이름을 반환하더라도 검증된 CPU 표시 투영이 없으면 모든 소비자 화면에서 확인 불가로 표시된다.

## What Changes

검증된 CPU 사양 표시를 우선하고, 투영이 없거나 해석 불가하면 서버의 비어 있지 않은 원래 flavor_name을 표시한다. 양쪽 모두 없으면 기존 지역화된 확인 불가를 유지한다. Native 이름은 역사적 식별 표시일 뿐 하드웨어 증거로 해석하지 않는다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

대시보드 최근 인스턴스, 소비자 인스턴스 목록과 상세에서 과거·수동·GPU flavor 이름을 보존한다.

## Impact

공통 frontend 표시 helper와 관련 행동 테스트·문서만 변경한다. Backend API, 생성/resize admission, flavor UUID/name/spec, VM, DB/schema, 설정과 배포는 변경하지 않는다. 관리자 표시는 유지한다. 공유 dev checkout의 기존 변경과 index를 보존한다.
