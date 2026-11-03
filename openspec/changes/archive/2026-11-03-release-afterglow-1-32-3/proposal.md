## Why

사용자가 현재 완료된 변경을 빌드·커밋하고 명시적으로1.32.3 발행을 요청했다. 버전 상향은 정확한 SHA CI 뒤 불변 numeric tag·GitHub Release·GHCR images/latest·Helm 검증까지 포함한다.

## What Changes

- dev b30baf0f 기반 요청 시점 public snapshot184paths의 SSO native-state 비밀번호 생성/복구, 관리자 웹 이메일/SQL105, Pi 출처·진행·source navigation와 아키텍처 중립 frontend asset build를 검토·통합한다.
- 기존 도구로 root/frontend/backend/lock/Helm metadata를1.32.3으로 동기화하고 격리 clone에서 전체 gate·production build와 실제 compiled/runtime smoke를 실행한다.
- 검증된 snapshot만 기본 공유 dev에 커밋·정상 push하고 정확한 SHA CI 성공 뒤 정식 tag·Release·images/alias·Helm을 발행·검증한다. 이후 도착한 다른 세션 변경은 보존·제외한다.

## Capabilities

### New Capabilities

새 기능 설계는 없다. 이미 완료·archive된 기능 source의 release qualification이다.

### Modified Capabilities

버전 metadata와 발행 artifact identity만 새 release로 변경한다. 기존 native authority·SQL105 schema-before-writer·원래 key·cohort·Pi history rollback 제한은 유지한다.

## Impact

Afterglow API/frontend/worker의 현재 declared linux/amd64 deliverable과 Helm chart가 대상이다. 기존1.32.2 tag/artifact·main PR/merge·형제 저장소·운영 Kolla/native/schema/SMTP와 shared datastore는 변경하지 않는다. Synthetic/native/메일 경계와 운영 수용은 분리해 보고한다.
