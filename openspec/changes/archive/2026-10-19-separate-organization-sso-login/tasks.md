## Implementation Tasks

- [x] 기존 LoginPage·catalog/owner fence·responsive/i18n 규약을 검토하고 UI-only 범위를 정의한다.
- [x] 메인의 단일 SSO 진입과 독립 선택 화면, 돌아가기/focus, loading/empty/error, 비밀번호 삭제와 request locks를 구현한다.
- [x] ko/en/ja/zh-CN 문구와 기존 LoginPage의 사용자 가시 회귀를 갱신한다.
- [x] exact frontend selector와 auth frontend target, i18n/static checks를 실행하고 결과 범위를 기록한다.
- [x] 실제 Chromium에서 password/SSO 전환·exact origin authorize·오류 복귀·responsive/theme/locale를 검증한다. API/IdP는 합성으로 격리한다.
- [x] ARCHITECTURE/DESIGN/상세 문서/CHANGELOG와 검증 증거를 갱신하고 architecture guard 실행 뒤 change를 archive한다.
