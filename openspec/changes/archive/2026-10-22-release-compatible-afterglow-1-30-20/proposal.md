## Why
사용자가 현재까지 완료된 변경사항의 commit, push 및 실제 배포를 요청했다. 기존 native identity/data/credential과 공유 Lumen0.6.9 호환성을 보존하면서 검증된 Afterglow source를 정식 patch release로 발행한다.

## What Changes
- 기존 console/account-entry 및 legacy Lumen compatibility 완료분을 dev에 정상 커밋·push한다.
- Afterglow metadata를1.30.20으로 동기화하고 exact-SHA CI 성공 뒤 불변v1.30.20을 발행한다.
- 게시된 version/latest image revision/digest와 native schema 선행 조건·복구 지점을 확인하고 canonical Kolla inventory/명령으로 배포한다.
- Lumen0.6.9 및 다른 native 서비스의 기존 release, datastore/키/설정/identity는 보존한다. Native account-runtime 승격과027 replay는 범위 밖이다.
- main 직접 commit/push/merge 및 보호 규칙 우회는 하지 않는다.
- Precheck가 발견한 운영자 원본 `services.cloud_shell=true`와 실행 중 false의 차이에 대해 사용자는 **Cloud Shell 활성화 준비 후 배포**를 선택했다. 이미지 선택 실패와 전용 프로젝트·network/security-group·HTTPS/WSS 준비 상태를 확인하고 fail-closed gate를 통과한 뒤 배포한다. 기존 자원·grant를 임의 변경하거나 활성화를 끄는 우회는 하지 않으며 신규 native 자원 생성이 필요하면 구체적 범위를 확인한다.

## Acceptance
정본 gate·exact-SHA CI·tag artifact 검증, 실제 Kolla rollout/readiness 및 public HTTPS 사용자 화면/인증 경계의 증거를 남긴다. 실사용 provider/OAuth 수용과 schema 복구의 과거 증거는 이번 release 증거와 구분한다.
