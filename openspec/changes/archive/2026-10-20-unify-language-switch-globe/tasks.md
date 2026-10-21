## 구현

- [x] 모든 언어 변경 진입점과 공통 LocaleSelect·기존 지구본 표시 조건을 확인한다.
- [x] 두 variant에서 같은 지구본을 표시하고 기존 동작·접근성을 보존한다.
- [x] 실제 브라우저에서 각 위치·언어 전환·키보드·반응형 표시를 검증하고 기록한다.
- [x] 관련 문서를 갱신하고 working·격리 임시 index staged architecture 검토를 통과한다.

## 검증 기록

- 실제 source Vite를 별도127.0.0.1:43181에서 실행했다. 외부 API는 fixture로 차단하고 콘솔은 기존 tutorial을 사용했다. Native 인증·운영 배포 수용이 아니다.
- 7화면(랜딩·로그인·회원가입·계정 찾기·문서·사용자/관리자 콘솔) × 390/768/1440px × light/dark = 42조건에서 장식용16px globe가1개씩 보이고 가로 넘침0이었다.
- 320px 문서의9언어 trigger·메뉴가 viewport 안에 유지됐다. 앱 한국어→영어 선택의 HTML lang·cookie·focus 복원, End/Escape 닫기, 문서 일본어 링크·URL/cookie 및 SSO 화면 globe를 확인했다.
- Proof: `~/.local/share/afterglow-proofs/language-globe-pLwhdUCN/{responsive-matrix,narrow-locales,keyboard-switch,docs-switch}.json`.
- QA 준비 중 `waitFor`에 selector 대신 expression을 준 오류와 login-options에 빈 객체를 준 fixture 오류를 교정했다. 제품의 인증 guard나 API 계약은 변경하지 않았다.
- Svelte check: 0 errors / 기존16 warnings. Working·staged architecture guard는 같은 source digest `61a3ead57e66ed863edc04f180dbe33cf30755b817e88808fd9636da536c637a` / 3358files로 통과했다. 실제 index는 변경하지 않았다.
- `gbrain` CLI가 없어 선택적 검색 index sync는 실행하지 않았다. 전체 test:gate·이미지 build·commit/push·서비스 배포는 이번 표시 변경에서 실행하지 않았다.
