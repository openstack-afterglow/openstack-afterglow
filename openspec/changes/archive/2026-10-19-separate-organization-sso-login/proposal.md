## Why

메인 로그인에 조직별 GitLab/OIDC/SAML 제공자가 모두 나열되어 개인 계정 로그인과 조직 SSO 선택이 섞여 보인다. 메인은 도메인 없는 username/email+password와 단일 `SSO로 로그인` 진입만 제공하고 조직별 선택은 그 안으로 분리한다.

## What Changes

- 기존 `LoginPage` 안에서 비밀번호 화면과 SSO 선택 화면을 명시적으로 전환한다. 새 route/query/auth API는 추가하지 않는다.
- 메인에는 SSO 진입 버튼 하나를 표시한다. SSO 선택에는 서버의 public login-options 등록을 그대로 사용하고 이름과 origin 도메인으로 식별하며 loading/empty/unavailable와 돌아가기 상태를 제공한다.
- SSO 전환 시 입력한 password와 방법별 오류를 지우며 키보드 focus를 새 화면 heading/복귀 trigger로 옮긴다. 요청 pending·logout·scope 전환 중에는 방법 변경과 중복 요청을 막는다.
- 공개 catalog의 mounted-page 수명, credential/provider authorize owner·ABA fence, exact origin, 비밀 없는 catalog, home-first session 및 후속 workspace chooser는 변경하지 않는다.
- 한국어 원문과 en/ja/zh-CN 카탈로그, 영향받는 회귀/문서를 함께 갱신한다.

## Capabilities

### New Capabilities

- 없음. 기존 인증 UI의 progressive disclosure만 변경한다.

### Modified Capabilities

- 공개 로그인: SSO 진입과 제공자 선택을 비밀번호 form에서 분리한다.

## Impact

- 영향: LoginPage, 기존 UI 회귀, domain-auth 네 locale, DESIGN/ARCHITECTURE/인증·검증 문서 및 CHANGELOG.
- Backend, 데이터, schema, dependency, native authority, 개인-domain enrollment, quota/admission, 서비스 ownership, 배포 topology에는 영향이 없다.
- 완료 기준: 메인에서 조직 제공자 숨김, 명시 진입 뒤 정확한 제공자 authorize, 돌아가기/비밀번호 계속 사용, 상태·request lock·stale-response fence 유지, 실제 Chromium responsive/theme/locale 검증.
- dev의 기존 사용자 변경·index·private configuration·실행 서비스/볼륨을 보존한다. commit/push/deploy 및 실제 사용자 GitLab/Keystone 인증은 요청 범위가 아니다.
