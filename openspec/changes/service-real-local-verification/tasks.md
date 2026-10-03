## Implementation Tasks

- [x] 선택적 source-build config/up을 구현하고 선택하지 않은 서비스의 callback·자격·checkout 검사를 분리한다.
- [x] 명시 endpoint/credential 입력과 read-only/exercise 구분, 실패·secret·정리 경계를 갖는 HTTP 검증 CLI를 구현한다.
- [x] Lumen native worker/journal/usage 검증을 구현하고 실제 격리 서비스에서 실행한다.
- [ ] Waygate client 설정/export/import/cleanup 검증을 구현하고 실제 격리 서비스에서 실행한다.
- [x] Palimpsest Hub blob digest round-trip/cleanup 검증을 구현하고 실제 격리 서비스에서 실행한다.
- [x] 안전 경계 회귀와 관련 target을 실행하고 현재 계층별 검증 프로세스·로컬 개발 명령·callback 제약 및 실행 증거를 문서에 반영한다.
- [ ] Architecture guard를 갱신·검증하고 정확한 미검증 경계를 기록한 뒤 change를 archive한다.

## Verification Evidence and Blocker

- 선택 실행: `services:up -- --only lumen,palimpsest`의 canonical source build, migration/bootstrap, API/worker readiness 통과; 확인한 API/worker images는 arm64. Lumen-only config는 cloud credential·callback 없는 별도 임시 입력에서도 통과했다. 기존 프로젝트/볼륨/키와 형제 소스는 보존했다.
- Lumen: 서비스 소유 isolated Docker system stack의 실제 API/worker·MariaDB/Redis·seeded scoped API key에 `services:verify -- lumen --exercise`가 0으로 종료했다. Idempotent native run, 11개 연속 journal event, canonical temporary history와 15-token ledger를 대조했다. Upstream은 fake provider이며 유료 외부 provider 검증은 아니다. Native temporary text는 실제 `part.delta` 계약을 사용한다.
- Hub: 별도 canonical test-profile MariaDB/Redis, 같은 source native API와 genuine Keystone/system-admin으로 실제 4096-byte `.sqsh`의 두 chunk/offset, finalize/root chain, blob byte/hash와 OCI bundle 참조/hash 및 소유 registration/upload 삭제·404를 통과했다. API source/auth를 mock하거나 우회하지 않았다. Docker Hub에서 configured Keystone로의 TCP 연결은 timeout이 났으며 이 transport gap을 성공으로 바꾸지 않았다.
- Waygate 구현은 완료했지만 genuine full client/export/import exercise는 미완료다. Native current source·별도 MariaDB schema·기존 실제 callback 설정·genuine Keystone의 read-only CLI는 0, `WAYGATE_SMOKE_SERVER_ID`가 없는 exercise는 mutation 전에 1로 종료했다. 같은 project의 서로 다른 등록된 ACTIVE·client가 없는 **전용** source/target 두 개가 필요하다. 기존 live project catalogue도 비어 있었으며 VM 생성·DB server seed·auth/callback bypass를 하지 않았다. 이 사전 조건 전까지 task 4와 archive는 보류한다.
- `npm run test:orchestration`: 106 tests, 106 pass, 0 fail. CLI `--help` 실제 실행 통과.
- `npm run docs:check`: working `614d4cafd6f778c6e513ec136da8da9001b0c3eb59b4c28c606b8f3b9c481d27`, 2154 source files 통과. HEAD+이 작업의 명시한 파일만 별도 index/review root에서 `--staged --stamp`와 `--staged` 통과: `d4ddae1df10ee48bb324c894dc6f85c5dcd75d507be54300742550fe17915cfd`, 2126 source files. 실제 Git index와 공유 review block byte/hash가 바뀌지 않았다. 다른 동시 변경이나 실제 최종 staged commit을 대신 검토한 결과는 아니다.
- Native smoke 프로세스·일회용 MariaDB/Redis와 이 작업의 isolated Lumen containers/network를 종료했다. Lumen named volumes, canonical local project의 기존 데이터/키는 보존하고 throwaway launch/port/input/CAS 파일은 제거했다. 전체 `test:gate`, amd64 runtime, 실제 외부 provider, Waygate VM/data plane, Hub physical GC/KVM/OpenStack와 운영 배포는 검증하지 않았다.
