## Why
네 native 서비스의 로컬 표준 프로젝트 역할 전환과 실제 운영 이미지가 다르다. 사용자는 manager/member 관리와 reader 비밀 없는 조회를 네 서비스의 정식 발행과 Kolla 배포까지 요청했다.

## What Changes
- Lumen, Drover, Waygate, Palimpsest의 native 인증·정책·route와 운영 override를 대조한다.
- 전용 서비스 역할 없이 현재 native core 역할로 허용하며 owner/project/private/credential 및 genuine human system-admin 경계를 유지한다.
- 동시 작업의 미발행 Pi/Manila/worker 변경을 포함하지 않고 배포 기준 dev에서 필요한 권한 변경만 별도 검증한다.
- 각 서비스의 새 불변 버전·이미지·package-owned Kolla role을 발행하고 원 datastore/key/config를 보존해 표준 Kolla 실행으로 전환한다.
- 운영 인증 경로와 각 controller revision/digest/health를 검증한다. 실제 검증 공백과 배포 실패를 source proof로 대체하지 않는다.

## Capabilities
### New Capabilities
- `native-standard-role-rollout`: 네 서비스의 표준 프로젝트 권한과 보안 경계를 보존하는 발행·운영 수용 계약.
### Modified Capabilities
없음. 네 서비스 자체 권한 요구 사항은 각각의 change에서 추적한다.

## Impact
네 sibling repository와 운영 /etc/kolla의 네 root package/image pin이 대상이다. Afterglow의 동시 미완성 변경과 main merge는 제외한다. 배포는 /etc/kolla/multinode의 compute 전체, 이어 control 전체의 afterglow,lumen,waygate,drover,palimpsest tags를 사용한다. 별도 Palimpsest build-worker 호스트는 이 두 실행의 대상이 아니며 자동 포함하지 않는다.
