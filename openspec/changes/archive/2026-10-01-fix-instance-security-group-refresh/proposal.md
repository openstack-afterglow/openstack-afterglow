## Why

인스턴스 보안 그룹 합집합의 silent polling은 매번 정상 표를 로딩 상태로 숨긴다. 저장 직후 ordinary GET은 저장 전부터 진행 중인 API broker 요청에 합류할 수 있어 최신 generation이 이전 적용 그룹을 채택할 수 있다.

## What Changes

- 실제 API broker와 소비자 화면에서 저장 전 지연 조회/저장 후 조회 race를 재현한다.
- 일반 silent polling은 직전 snapshot과 오류 상태를 유지하며 성공한 최신 응답에서만 오류를 해제한다.
- 비-silent 상세 전환은 이전 보안 그룹과 포트 snapshot을 비운다.
- 보안 그룹 저장 후 기존 `api.get(..., { refresh: true })`를 사용하여 브라우저에서 독립 조회를 시작하고 조회 완료 전에는 정책을 로딩 상태로 둔다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- instance-security-group-union: silent refresh 표시 안정성과 저장 후 브라우저 요청 합류 방지. 실제 서버 snapshot의 즉시 최신성을 보장하지 않는다.

## Impact

상세 controller와 소비자 회귀 테스트 및 기존 상세 문서만 변경한다. backend/API 응답·권한·DB·배포 설정은 변경하지 않는다. 실제 SG GET은 refresh query를 읽지 않으며 POST의 cache 삭제도 진행 중인 `_inflight` load를 제거하지 않으므로 저장 전 느린 Neutron 조회가 저장 후 응답으로 다시 cache되는 위험이 남는다. 규칙 CRUD의 인스턴스별 SG cache 무효화도 범위 밖이다. 합성 네트워크 fixture는 이 서버 측 race 해결이나 실제 Neutron mutation을 증명하지 않는다.
