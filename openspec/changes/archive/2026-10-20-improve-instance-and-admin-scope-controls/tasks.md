## Implementation Tasks

- [x] 기존 크기 변경의 공용 SHUTOFF 노출과 사용자/admin API를 확인하고 변경하지 않는다.
- [x] 인스턴스 이름 변경의 사용자 ownership/write·fresh admin API 및 Nova cache invalidation을 구현한다.
- [x] 관리자·사용자 공용 상세 이름 변경과 응답/권한 fence 및 아홉 locale를 구현한다.
- [x] 관리자 프로젝트 소유 inventory의 domain_id/project_id 교집합과 페이지 분할 전 필터를 구현한다.
- [x] 관리자 자원·quota·IAM 등 전체 scope 조건을 점검하고 일관된 도메인→프로젝트 UI를 적용한다.
- [x] Workspace chooser의 짧은 읽기 cache와 중복 조회 병합·명시 refresh 및 세션/권한/생성 invalidation을 구현한다.
- [x] 정확한 관련 selector·도메인 target과 로컬 HTTP·실제 브라우저 흐름을 검증한다.
- [x] 실행 증거 및 한계에 맞춰 architecture/design/API/testing/changelog를 갱신하고 architecture guard·OpenSpec archive를 완료한다.
