## Why

메모리 특화 탭이 이름 접두사만 보므로 기존4/8GiB-per-vCPU CPU-only 자동 사양도 CPU로 분류된다. 사용자는1vCPU/4GiB·8GiB 이상 메모리 특화 자동 생성을 요청했다.

## What Changes

- GPU 없는 표준 사양은 CPU당2GiB CPU와4/8/16GiB memory로 나눈다. GPU 조합은 기존2/4/8GiB와 승인 정책을 유지한다.
- 신규 memory 이름/display는 mem.{vcpus}c_{ram_gib}g. 하드웨어 결정 UUID·기존 cpu native 이름·VM 참조는 유지하고 동일 사양을 다시 만들지 않는다.
- 동일 retained included 호스트의 CPU/RAM 지원 한도·step/min/max와 기존 readback/claim/ACL 경계를 그대로 적용한다.
- Wizard는 이름보다 GPU와 실제 RAM/vCPU 비율로 분류하며 생성 가능 필터·검색·선택/refresh fence를 유지한다.

## Capabilities

### Modified Capabilities
- 기존 standard flavor automation과 검증된 CPU-only 표시/VM wizard memory 분류.

## Impact

기존 backend reconciler/presentation와 frontend picker 동작을 확장하며 endpoint·schema·config는 추가하지 않는다.4/8GiB shape의 결정적 ID는 바뀌지 않는다. Native flavor 자동화 writer 변경은 배포 전 구형 writer drain이 필요하다. 구현·격리 smoke는 실제 cloud mutation/배포 승인으로 간주하지 않는다.
