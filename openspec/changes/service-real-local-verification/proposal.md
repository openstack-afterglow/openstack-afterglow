## Why

Afterglow의 `test:lumen`, `test:waygate`, `test:palimpsest`는 소비자/BFF 계약이며 독립 서비스의 실제 HTTP·DB·worker 실행 성공을 증명하지 않는다. 기존 `services:smoke`는 hardcoded loopback endpoint, 전체 Drover readiness 및 원격 dashboard를 한 번에 요구하고 provider 호출 없이 조회만 검증한다. 개별 서비스를 수정하면서 실제 로직을 실행하는 개발 루프가 필요하다.

## What Changes

- 기존 source-build dev Compose를 유지하며 `services:config/up -- --only <service,...>`로 Lumen·Waygate·Palimpsest만 선택해 실행한다. 선택하지 않은 Drover의 service-project/callback 및 다른 sibling checkout을 요구하지 않는다. full-stack 기본 동작과 private volumes/keys는 보존한다.
- Docker나 repository config 없이도 실행 가능한 `services:verify` CLI를 추가한다. 서비스별 origin, API key 또는 Keystone token, project, model/server/artifact를 환경변수로 직접 지정한다. read-only 연결 확인과 명시적 `--exercise` 실제 로직 검증을 구분한다. 비밀은 출력하거나 파일에 저장하지 않는다.
- Lumen 실제 native admission→worker completion→journal replay→run 귀속 usage, Waygate 소유 server의 임시 client 설정/export/import 및 삭제, Palimpsest Hub의 실제 blob digest/upload/finalize/download와 생성 자원 정리를 공개 HTTP API로 검증한다. 실제 공급자 호출 비용과 변경 범위는 opt-in이다.
- Drover cloud callback, Waygate VM provisioning/agent callback/data plane, Palimpsest KVM/OpenStack build/consume, Lumen 외부 provider/media 인증은 별도 경계로 기록한다. 인증 bypass나 upstream 실패 fallback을 만들지 않는다.
- 검증 프로세스는 unit/contract, datastore-only functional, service-real HTTP, live cloud/provider, fixture UI를 별개 증거로 기록하고 실제 로직 변경은 service-real 실행을 필수로 한다.

## Capabilities

### New Capabilities

- service-real-local-verification: 선택한 독립 서비스 실행 및 manually configured 실제 HTTP 로직 검증.

### Modified Capabilities

- local-source-stack: callback 종속 서비스를 전체 시작의 필수 전제로 만들지 않는 opt-in 부분 실행.

## Impact

`package.json`, `scripts/local-services.mjs`, 공개 HTTP 기반 검증 실행기/회귀, `docs/testing.md`, `docs/deployment.md`, `docs/agent-development-guide.md`, `ARCHITECTURE.md`, `CHANGELOG.md`. 서비스 protocol, DB schema, 운영 manifest, 인증/인가 및 형제 repository source는 변경하지 않는다. 모든 사용자 변경과 existing projects/volumes/keys를 보존한다. 실제 provider 호출과 원격 cloud mutation은 자동 실행하지 않으며 실행하지 못한 경계는 검증 공백으로 보고한다.
