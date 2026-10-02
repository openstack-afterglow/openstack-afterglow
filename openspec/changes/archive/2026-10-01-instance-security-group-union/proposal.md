## Why

인스턴스 상세 인터페이스에는 적용된 보안 그룹 이름만 표시되어 실제 허용 규칙을 그룹마다 확인해야 한다. 각 인터페이스의 적용 그룹 합집합을 바로 아래에서 읽을 수 있어야 한다.

## What Changes

- 기존 인스턴스 보안 그룹 응답의 프로젝트 그룹/규칙과 포트별 적용 ID를 재사용한다. 목록 상세 패널, 직접 상세 및 관리자 공용 상세에 동일하게 적용한다.
- 인터페이스별 보안 그룹 아래에 인바운드/아웃바운드 허용 규칙을 IP 버전, 프로토콜, 포트 또는 ICMP 유형/코드, 출발지/대상으로 표시한다.
- 동일 방향·IP 버전·프로토콜·원격 대상의 중복을 제거하고 TCP/UDP/SCTP의 겹치거나 연속된 포트 범위를 합친다. 다른 CIDR/원격 그룹/방향/IP 버전 및 ICMP 유형·코드는 섞지 않는다.
- 전체 프로토콜/전체 포트와 IPv4/IPv6 전체 대역을 명시하며, 원격 보안 그룹은 이름과 ID를 확인할 수 있게 표시한다.
- 불러오는 중, 조회 실패, 적용 그룹 누락, 규칙 없음, 미적용 상태를 구분한다. 부분 규칙을 완전한 합집합으로 표시하지 않는다.
- 저장된 적용 ID를 사용하며 편집 미저장 선택으로 허용 규칙을 바꾸지 않는다. 보안 그룹 조회의 포트 snapshot을 사용해 별도 interfaces cache의 오래된 그룹 ID를 피한다.
- 기존 TableShell과 semantic token으로 좁은 화면에서도 페이지가 넘치지 않는 읽기 전용 표를 구성한다.

## Capabilities

### New Capabilities

- 인터페이스별 보안 그룹 허용 규칙 합집합 표시.

### Modified Capabilities

- 보안 그룹 조회 실패를 빈 정상 목록으로 오인하지 않도록 상세 controller에 로딩/오류 상태를 추가한다.

## Impact

frontend security group union utility, read-only instance rule component, NetworkSection, instance detail controller 및 행동/경계 테스트가 변경된다. 기존 API·Neutron 권한·보안 그룹 mutation은 유지한다. 표시 결과는 보안 그룹 정책이며 게스트 서비스 실행, OS 방화벽, 라우팅 또는 실제 접속 가능성을 증명하지 않는다. 실제 OpenStack 검증 및 배포는 별도 증거가 필요하다.
