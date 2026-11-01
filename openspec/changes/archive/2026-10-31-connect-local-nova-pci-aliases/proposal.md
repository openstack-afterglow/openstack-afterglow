## Why

로컬 관리자 컴퓨트 풀 조회는 기존 Placement PCI 사용량에 대응하는 승인 GPU profile이 없어 `compute_pool_gpu_accounting_unqualified`로 차단된다. 로컬 backend에 정제된 Nova alias snapshot mount가 빠져 그룹 작성에 필요한 configured alias도 unavailable이다.

## What Changes

- 개발 Compose backend에 정제 snapshot 전용 디렉터리를 read-only mount한다. 원본 Nova 설정이나 비밀은 복사하지 않는다.
- 기존 Kolla 수집기를 재사용하여 controller 3대의 동일한 공개 alias snapshot을 로컬 private 디렉터리에 저장한다.
- 현재 관리자 인증과 revision/graph lease를 사용하는 기존 API로, 기존 Nova flavor의 정확한 alias 조합에 근거한 GPU profile을 승인한다. 임의 장치 역할이나 동일 카드 귀속을 추정하지 않는다.
- 현재 DB/키/포트/기존 mount/VM/수동 flavor를 보존하며 로컬 backend만 재기동한다. 도메인 quota 숫자는 설정하지 않고 조회/편집 가능 상태를 검증한다.

## Capabilities

### New Capabilities

없음. 기존 non-Kolla snapshot 제공 계약을 로컬 Compose에 연결한다.

### Modified Capabilities

로컬 관리자 GPU profile 및 compute pool의 실제 configured PCI observation과 accounting 준비 상태를 복구한다.

## Impact

개발 Compose backend의 read-only mount 하나와 운영 문서만 구조적으로 달라진다. DB schema/migration·K8s 설정 필드는 추가하지 않는다. 기존 `compute.flavor_automation_policy`만 기존 서비스 API로 변경하며 enabled managed flavor loop가 새 profile에 따라 Nova flavor/ACL을 조정할 수 있다. 변경 전에 기존 상태와 복구 이미지를 보존한다. 운영 앱 배포·Kolla reconfigure·기존 VM 변경은 범위 밖이다. 실제 GPU passthrough와 같은 카드 companion 배정은 별도 검증이다.
