## Why

로드밸런서 대시보드는 사용자 목록에만 일괄 삭제가 있고 관리자 목록에는 선택 기능이 없다. 또한 Drover가 K3s HA 제어면을 위해 소유하는 로드밸런서도 일반 삭제와 구분되지 않아, 대시보드에서 실수로 삭제하면 클러스터가 손상될 수 있다.

## What Changes

- Octavia 응답의 `tags`를 Afterglow 로드밸런서 목록·상세 계약에 보존한다.
- `drover.managed=true`와 `drover.resource_type=load_balancer` 태그를 모두 가진 로드밸런서를 Drover 관리 리소스로 판별한다. 이름 prefix는 소유권 근거로 사용하지 않는다.
- 사용자와 관리자 목록에서 Drover 관리 로드밸런서를 일반 일괄 삭제 선택 대상에서 제외하고 이유를 표시한다.
- 관리자 로드밸런서 목록에 공용 선택 primitive 기반 일괄 삭제를 추가한다.
- 사용자·관리자 상세 화면에서 Drover 관리 로드밸런서의 일반 `삭제`를 `강제 삭제` 경로로 대체하고 위험을 명시한 별도 확인을 요구한다.
- Afterglow DELETE API와 Drover 자동화 경로는 변경하지 않는다. 따라서 Drover의 클러스터 삭제·재구성은 기존대로 동작한다.

## Capabilities

### New Capabilities

- 관리자 로드밸런서 일괄 선택·삭제
- Drover 관리 로드밸런서의 대시보드 일반 삭제 보호 및 명시적 강제 삭제

### Modified Capabilities

- 로드밸런서 목록·상세 응답이 OpenStack `tags`를 전달한다.
- 사용자 일괄 삭제는 Drover 관리 리소스를 제외한다.

## Impact

변경 범위는 Afterglow Octavia 직렬화, 로드밸런서 TypeScript 계약, 사용자·관리자 목록/상세 UI와 회귀 테스트다. OpenStack 삭제 API의 인가·cascade 동작 및 Drover 서비스 코드는 변경하지 않는다. 태그가 없는 리소스는 기존 일반 로드밸런서로 취급한다.
