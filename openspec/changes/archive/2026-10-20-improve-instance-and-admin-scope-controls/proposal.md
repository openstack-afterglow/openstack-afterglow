## Why

인스턴스 이름을 관리자와 사용자가 수정할 수 없고, 관리자 자원 목록의 프로젝트 조건은 도메인 조건과 일관되게 연결되지 않는다. 리소스 선택창은 재개방과 도메인 재탐색 때 디렉터리를 반복 조회해 이미 확인한 목록도 늦게 표시한다.

## What Changes

- 기존 인스턴스 크기 변경은 공용 InstanceHeader가 SHUTOFF에서만 노출하므로 요청대로 유지한다. 기존 사용자/admin resize·confirm·revert API와 상태 계약은 변경하지 않는다.
- 사용자·관리자 공용 인스턴스 상세에 이름 변경 폼을 추가한다. 사용자 쓰기/소유권과 관리자 fresh 권한을 기존 경계에서 검증하고 Nova metadata update 뒤 상세·목록 캐시를 무효화한다. 폼과 응답은 target/actor/session/project/mode/permission 변경에 fence한다.
- 관리자 인스턴스·볼륨·DB·네트워크 등 프로젝트 범위 목록 및 quota/프로젝트/사용자/credential 등 기존 범위 선택 화면을 전수 점검하여 도메인→프로젝트 조회 조건을 일관되게 제공한다. DomainScope 기반 IAM의 명시적 도메인 경계는 보존한다. 서버 페이지 분할 전에 도메인의 프로젝트 ID로 필터하며 이름으로 소유 도메인을 추정하지 않는다. 필터 변경 시 marker·selection·old result를 분리한다.
- 프로젝트·도메인 디렉터리는 기존 캐시 규칙을 재사용하여 중복 요청을 합치고 짧은 수명의 메모리 읽기 snapshot을 재사용한다. 정확한 logical session/actor/home/working scope가 소유하며 logout·권한/scope 전환·명시 refresh·생성 뒤에는 폐기한다. 목록 snapshot을 서버 권위나 mutation 허용 근거로 사용하지 않는다. 서버의 fresh native authorization은 유지한다.

## Capabilities

### New Capabilities

- 관리자 및 프로젝트 사용자의 인스턴스 이름 변경.
- 관리자 프로젝트 소유 자원에 대한 독립 도메인 및 종속 프로젝트 필터.

### Modified Capabilities

- 리소스 선택창의 디렉터리 읽기 재사용과 명시 새로고침.
- 기존 관리자 scope selector의 일관된 조회·loading/error/empty 처리.

## Impact

영향 영역은 FastAPI Nova/admin inventory 조회, 공용 Svelte 인스턴스 상세·관리자 scope 필터·workspace chooser 및 디렉터리 store다. DB/schema·설정·의존성·서비스 소유권·배포 topology는 변경하지 않는다. 운영 VM/IAM/DB·Compose 및 credentials는 변경하지 않는다. 관련 pytest·frontend behavior tests와 실제 로컬 HTTP/브라우저 smoke를 실행하고 합성 Nova/identity 경계와 실제 운영 미검증을 구분한다. ARCHITECTURE.md·DESIGN.md와 관련 API/검증 문서·CHANGELOG는 최종 구현 및 실행 증거에 맞춰 갱신한다.
