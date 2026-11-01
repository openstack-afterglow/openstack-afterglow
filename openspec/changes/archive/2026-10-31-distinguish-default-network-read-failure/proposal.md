## Why

VM composition 최종 review에서 default_network._db_get이 DB unavailable/factory 누락/query 실패를 confirmed absent와 같은 None으로 반환함을 확인했다. 기존 GET/default의 text404만 optional 부재로 처리하면 설정 조회 실패와 명시 retry가 숨겨진다.

## What Changes

- DB 조회 실패는503, 성공한 빈 조회만404 default_network_not_configured로 구분한다.
- Wizard는 해당 code404만 optional 부재로 처리한다. 과거 ambiguous text404와 proxy/auth/server 오류는 계속 표시하고 retry한다.
- 기존 caller가 실패를 부재로 해석해 native 자원을 생성하지 않게 strict read를 전파한다. DB/schema/config·quota·운영 자원에는 변경이 없다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

기본 네트워크 조회의 실패/부재 구분.

## Impact

Default network read helper/API와 wizard optional loader·관련 회귀/문서. 이전 fix-vm-composition-continuation source archive의 review 보완이며 현재 실행 container·shared DB/Redis·native state는 변경하지 않는다.
