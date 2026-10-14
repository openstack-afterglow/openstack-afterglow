## Why

볼륨 이전은 같은 도메인과 다른 도메인의 프로젝트 모두에서 수신할 수 있어야 한다. 기존 모달은 수신을 개별 소유 볼륨에 종속시키고, 현재 프로젝트 전송 목록만 보여주며 출발 도메인·프로젝트를 확인할 수 없다.

## What Changes

- 기존 Cinder 전송 생성·수락·취소 API와 볼륨 메뉴를 사용한다. 생성은 현재 프로젝트의 available·미연결 볼륨만 허용하고 자동 VM 분리를 제거한다.
- 목록 상단의 독립 수신 진입점에서 전체 transfer UUID를 검색한다. 모든 도메인·프로젝트를 대상으로 정확한 ID 하나를 직접 조회하고 awaiting-transfer 볼륨만 반환한다.
- 조회 결과에 볼륨 이름·UUID·용량·유형, 출발 프로젝트와 도메인의 이름·UUID를 표시한다.
- 기존 설정의 관리자 연결은 정확한 transfer·volume·Keystone 소유자 메타데이터 읽기에만 사용한다. 전체 전송/볼륨 목록·키·메타데이터는 공개하지 않는다.
- 수락은 현재 선택 프로젝트의 사용자 자격과 쓰기 권한으로 Cinder에 auth key를 전달한다. 관리자 자격으로 수락하지 않는다. 잘못된 키·이미 수락/취소·현재 상태 변경을 오류로 구분한다.
- 생성한 transfer ID와 auth key는 발급 화면에서 복사 가능하며 auth key는 저장·로그·검색 응답에 포함하지 않는다. 전송 목록·취소는 현재 프로젝트 소유만 허용한다.
- 같은 도메인과 다른 도메인 모두 동일한 조회·확인·키 인증·수신 흐름을 사용한다. 프로젝트/사용자 전환, 창 닫힘, ID 변경 뒤 이전/늦은 조회 응답과 secret을 폐기한다.

## Capabilities

### New Capabilities

- `cross-domain-volume-transfer-lookup`: 현재 인증 사용자가 정확한 transfer ID로 모든 도메인·프로젝트의 대기 전송 및 출발 범위를 확인한다.
- `independent-volume-receive`: 수신 프로젝트에 기존 볼륨이 없어도 ID 조회와 auth key 인증으로 소유권을 이전한다.

### Modified Capabilities

- `volume-transfer`: 현재 프로젝트 쓰기/소유권, 미연결 상태, 현재 프로젝트 전송 목록·취소, 오류 및 cache invalidation 경계를 정정한다.

## Impact

FastAPI 볼륨 라우터·Cinder adapter 및 focused pytest, Svelte 볼륨 목록·공용 모달·관련 controller/작업 메뉴와 네 locale을 변경한다. 새 DB/schema/migration, dependency, configuration, production deployment 또는 별도 클라우드 간 데이터 복사는 없다. 현재 configured Keystone/Cinder cloud와 region 내부 도메인 간 소유권 이전이며 외부 독립 OpenStack cloud 간 복사는 지원하지 않는다. 공유 worktree/index와 동시 변경을 보존한다.
