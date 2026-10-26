## Implementation
- [x] Native admin 신규 project grant를 서버에서 거부하고 기존 direct admin 제거를 지원한다.
- [x] 사용자/관리자 역할 편집 UI의 admin 추가 차단·기존 제거 및 system admin 예외를 보존한다.

## Verification
- [x] API 회귀와 실제 HTTP/browser 실행으로 신규 거부·기존 제거·system scope 유지 경계를 확인한다.
- [x] 격리 canonical gate와 architecture guard를 통과한다.
- [x] 관련 문서·CHANGELOG·verification을 갱신하고 OpenSpec을 archive한다.
