## Implementation Tasks

- [x] 백엔드 `precheck_admin_password` 및 `set_admin_password`의 인가 로직을 시스템 관리자 또는 인스턴스 생성자 본인으로 수정하고 단위 테스트를 갱신한다.
- [x] 프론트엔드 `Instance` 타입에 `user_id`를 추가하고 `instanceDetailController`에서 생성자/관리자 조건에 맞춰 precheck를 호출하도록 수정한다.
- [x] `InstanceHeader.svelte`에서 관리자 페이지(기존 3행) 및 일반 사용자 페이지(본인 소유 인스턴스, 2행)에 비밀번호 변경 버튼을 노출하도록 템플릿과 스타일을 구현한다.
- [x] 백엔드 pytest 단위 테스트(관리자 성공, 생성자 본인 성공, 타인 생성 인스턴스 거부 403, 비활성 409, QGA 미지원 409 등) 및 프론트엔드 컴포넌트/컨트롤러 테스트를 검증한다.
- [x] 실제 로컬 HTTP/브라우저 스모크 검증과 프로젝트 확정 게이트를 통과시키고 문서를 갱신한다.
