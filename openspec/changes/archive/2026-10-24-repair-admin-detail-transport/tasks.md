## Implementation

- [x] Identity 관리자 transport와 선택 domain/object boundary를 일관되게 수정하고 부정 회귀를 작성한다.
- [x] 관리자 인스턴스 상세/연관 조회/콘솔/로그 및 기존에 노출된 lifecycle·연결·보안 그룹·비밀번호 작업의 전용 경로와 부모/child 검증 및 frontend 선택을 수정한다.
- [x] 관리자 이미지 상세/관련 작업 경로를 수정하고 private 이미지 권한 경계를 검증한다.
- [x] 관리자 파일 스토리지/LB/DB 상세와 child reads를 수정하고 불일치·nonadmin 경계를 검증한다.

## Verification

- [x] 격리 snapshot에서 exact selector와 관련 target을 실행하고 실패를 해결한다.
- [x] 실제 HTTP/설치 SDK와 compiled browser로 관리자 foreign-project 상세 및 사용자 거부를 exercise한다.
- [x] 동일 source의 canonical gate를 실행한다.
- [x] ARCHITECTURE/API/CHANGELOG/testing 증거를 갱신하고 architecture guard 및 OpenSpec archive를 마친다.
- [x] 관리자 VM storage 및 share rule 응답의 CephX key를 제거하고 실제 TCP·canonical gate를 재검증한 뒤 canonical 개발 의존성 경로를 복구한다.
