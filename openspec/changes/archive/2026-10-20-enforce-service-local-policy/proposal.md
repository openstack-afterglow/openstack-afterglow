## Why

서비스 admin/editor/user/reader 역할을 Keystone에서 모든 세부 role로 확장하면 token/delegation payload가 커지고 VM user-data 생성에도 영향을 준다(사용자 관측). 서비스 API 권한은 OpenStack의 실제 oslo.policy처럼 각 서비스의 운영자 정책에서 평가해야 한다.

## What Changes

- Lumen·Drover·Waygate·Palimpsest에 등록된 기본 action 정책과 `/etc/<service>/policy.yaml` override, 표준 policy 생성 도구, 설정·배포 mount를 제공한다. 이미 oslo.policy를 사용하는 Drover는 실제 기본 action 규칙을 cut over한다.
- 서비스 grade가 직접 action을 허용하도록 규칙에 명시하고, 기존 명시적 leaf 할당은 세분화 권한으로 보존한다. role 이름·native ID·직접 할당은 변경하지 않는다.
- Afterglow는 native 서비스가 계산한 capability를 소비하며 운영자 override를 별도 고정 leaf 검사로 덮어쓰지 않는다. 명시적 preset 적용에서 기존 관리 service implication edge를 제거하고 native project/member/reader 연결과 운영자 custom edge는 보존한다.
- 프로젝트·사용자 소유권, 현재 native scope/identity/권한 회수, reduced key ceiling, system-only 작업과 provider 실행 자격 경계는 정책과 별도로 유지한다.
- 실제 생성 경로에서 최소 role/delegation과 VM user-data를 검증한다. 운영 VM 생성·운영 IAM 변경·배포는 하지 않는다.

## Capabilities

### New Capabilities

- 서비스별 운영자 제어 policy YAML과 인증된 effective capability 조회.

### Modified Capabilities

- 서비스 role preset, BFF permission projection, 정책 파일 설정·패키징·Compose/Kolla 배포 경로.

## Impact

네 독립 서비스와 Afterglow의 auth/권한·UI projection·테스트·배포 예시·문서가 영향받는다. Native OpenStack의 project role implication은 별개이며 유지한다. 기존 서비스 edge 제거는 명시적 관리자 preset action에서만 수행한다. 계정/personal/organization change와 함께 통합 gate를 실행하되 운영 qualification과 구분한다. YAML은 신뢰된 운영자 설정이며 프로젝트 tenant가 편집할 API를 추가하지 않는다.
