## Why

VM 생성 flavor 선택기에 차단된 flavor와 quota/host 부족 진단이 함께 표시되어 선택 가능한 사양을 찾기 어렵다. GPU 타입을 한 번에 고를 수 없고 도메인 pool일 때 프로젝트 CPU/RAM 사용량까지 숨겨져 있다.

## What Changes

- 상단의 GPU 타입 버튼으로 현재 생성 가능한 GPU flavor를 한 번에 필터링한다. 승인된 primary 그룹/기존 검증 helper를 재사용하며 companion을 별도 GPU 타입으로 만들지 않는다.
- 생성 가능성이 확인된 flavor만 목록·검색·분류 개수·페이지 계산에 포함한다. 부족 진단과 GPU 잔여량 배지/선택 상세를 제거한다. 조회 실패/미확인 상태는 한 안내로 구분하고 선택 세대/생성 admission은 유지한다.
- native 프로젝트 VM/CPU/RAM/storage quota를 항상 표시한다. 무제한에서도 현재 사용량과 선택한 VM 추가량을 유지하며 없는 관측은 0이나 무제한으로 만들지 않는다.
- Dashboard full quota 응답에 원래 native compute 관측을 `native_compute`로 분리해 제공한다. 기존 `compute` domain/effective projection과 다른 소비자 계약은 유지하고 VM wizard만 native source를 사용한다. 관리자 target quota는 기존 native source를 그대로 쓴다.

## Capabilities

### Modified Capabilities
- VM 생성 flavor 선택과 프로젝트 native quota preview.

## Impact

UI/DTO read projection만 변경한다. Native quota/pool 정책·auth·실제 fresh admission·DB schema·설정·의존성은 변경하지 않는다. 현재 공유 dev 변경/index/architecture marker를 보존한다. Canonical Compose/운영 배포나 cloud resource 변경은 수행하지 않는다. 관련 회귀와 실제 Chromium에서 합성 identity/API로 desktop/tablet/mobile·light/dark·지원 언어를 확인한다.
