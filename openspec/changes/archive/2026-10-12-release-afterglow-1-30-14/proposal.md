## Why

운영 세 controller의 Afterglow backend는 v1.30.13 (`25f3557f`)이며 frontend/Notion worker는 v1.30.12다. 승인된 Afterglow 통합 commit `aac6b9c5`는 배포된 GPU admission hotfix와 갈라져 있어 단순 교체하면 운영 수정이 사라진다. 현재 운영 기준을 보존한 patch release와 실제 배포 검증이 필요하다.

## What Changes

- 격리 local `dev`에서 배포된 v1.30.13 hotfix를 승인된 Afterglow 결과에 merge하고 v1.30.14 metadata를 동기화한다.
- 미완료 Palimpsest/block layer, SQL088/089, sibling release/operator dependency 변경은 제외한다. 공유 checkout/index와 모든 기존 작업을 보존한다.
- 정확한 dev SHA gate/실행 smoke/CI 후 immutable tag와 세 image를 발행하고 version/latest revision·digest를 검증한다.
- 현재 schema와 SQL084–087의 postcondition을 대조하고 보호 backup의 실제 격리 restore 및 old/new writer 호환성을 검증한 뒤 필요한 migration만 적용한다.
- 운영 설정·원래 키·DB/volume·inventory·sibling image를 유지하며 canonical `/etc/kolla/multinode` Kolla afterglow tag로 세 controller를 순차 배포한다.
- 실제 version/digest/readiness/auth 경계·공개 화면·unrelated container 보존을 확인하고 증거를 기록한다.

## Capabilities

### New Capabilities

새 기능을 설계하지 않는다. 이미 승인·검증한 Afterglow 구현과 운영 hotfix의 릴리스·배포다.

### Modified Capabilities

운영 Afterglow release integration, MCP schema cutover 및 해당 복구/배포 증거를 갱신한다.

## Impact

Afterglow API/frontend/Notion worker와 해당 DB에 한정한다. 기본 patch 정책으로 v1.30.14를 사용하고 기존 tag는 이동하지 않는다. `main` PR/merge는 수행하지 않는다. Migration은 원래 ciphertext key와 복원 가능한 운영 backup을 보존하고 old writer/new schema 호환성 확인을 선행한다. 실제 cloud resource 생성·삭제, 유료 모델 호출, sibling 배포나 DNS/인증 완화는 범위 밖이다. API liveness만으로 전체 provider/guest/RDP acceptance를 주장하지 않는다.
