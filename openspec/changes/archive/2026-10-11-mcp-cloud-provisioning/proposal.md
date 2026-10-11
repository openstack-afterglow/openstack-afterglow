## Why

개인 MCP 및 동일 registry를 사용하는 Lumen 위임에서 조회·lifecycle/delete는 가능하지만 인스턴스 생성, 볼륨 생성, 기존 인스턴스에 네트워크 연결이 없다. 사용자가 요청한 세 작업을 기존 프로젝트 권한과 내구성 변경 원장으로 제공한다.

## What Changes

- `afterglow_vm_create`: 이름, Glance 이미지 ID, Nova flavor ID, Neutron network ID와 boot volume size를 받아 한 VM의 비동기 생성 요청을 접수한다. 기존 이름 규칙·프로젝트 flavor quota/host/GPU admission을 재사용하고 이미지·네트워크·선택적 본인 keypair를 검증한다. Nova image→volume block-device mapping으로 disk=0 flavor도 지원한다. Boot 볼륨은 기본 보존하며 `delete_boot_volume_on_termination=true`를 명시할 때만 VM 삭제에 따라 삭제한다. 안전한 server ID/status만 반환하며 ACTIVE·guest readiness를 보장하지 않는다.
- `afterglow_volume_create`: 이름·1–16384 GiB 크기·선택적 availability zone으로 빈 Cinder 볼륨 한 개의 비동기 생성 요청을 접수하고 안전한 ID/status/size를 반환한다.
- `afterglow_vm_network_attach`: exact-project Nova server에 owned 또는 명시적으로 공유된 Neutron network의 새 interface를 연결한다. 기존 타인 port를 재사용하지 않고 최종 parent/port/network ownership과 server state를 검증한다.
- 세 도구는 `mcp:write`, strict allowlisted arguments, non-mutating preview 및 final SDK deadline fence, 현재 grant/target project 재검증과 idempotency ledger를 그대로 적용한다. Credential fallback·자동 재전송·force·임의 provider 호출·비밀 반환은 없다. 기존 default read-only Lumen 권한을 확대하지 않는다.

## Capabilities

### New Capabilities

- 프로젝트 범위 VM 생성, 빈 볼륨 생성, VM network interface 연결.

### Modified Capabilities

- canonical registry tool/schema inventory와 registry version, MCP 및 Lumen 소비자 공개 계약.

## Impact

Backend MCP compute/storage/network adapters와 registry·pytest 회귀, 영향을 받는 architecture/API/security/testing 문서. 새 DB schema·설정·의존성·일반 REST router·UI 구조 변경은 없다. 현재 공유 변경·index·설정/키·기존 컨테이너/볼륨을 보존한다. 실제 cloud provisioning·운영 배포/DB migration·발행은 이번 승인 범위가 아니다. 실제 MCP/SDK HTTP는 loopback synthetic identity/provider와 disposable DB/Redis에서 실행하고 경계를 구분한다.
