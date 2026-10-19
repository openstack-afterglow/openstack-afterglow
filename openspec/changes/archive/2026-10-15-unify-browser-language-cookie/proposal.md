## Why

문서의 URL 전용 언어와 앱의 `afterglow_locale` 쿠키가 분리되어 `/docs` 진입 및 문서에서 로그인·콘솔로 이동할 때 선택 언어가 달라진다. 실제 로컬 Chromium에서 로그인 영어 선택 후 `/docs`는 한국어, 문서 일본어 선택 후 로그인 복귀는 영어인 것을 확인했다.

## What Changes

- 같은 origin의 공개 메인·문서·로그인·인증 후 페이지는 기존 1년 수명 root-path `afterglow_locale` 쿠키를 공통 선호로 사용한다.
- 문서의 유효한 `?lang=ko|en|ja|zh-CN`은 명시적 선택으로 우선 적용하고 공통 쿠키에 반영한다. 언어가 없거나 잘못되면 쿠키, 쿠키도 유효하지 않으면 한국어다.
- 한국어 선택 링크도 `lang=ko`를 명시하여 저장된 다른 언어를 JS 없이 덮어쓸 수 있게 한다. 기사·query·fragment는 보존한다.
- SSR과 재사용되는 root layout의 클라이언트 내비게이션을 같은 언어로 갱신한다. SvelteKit 데이터 미리 읽기는 쿠키를 변경하지 않고 실제 내비게이션에서만 반영한다.

## Capabilities

### New Capabilities

없음.

### Modified Capabilities

- 공통 UI 언어 영속화와 문서 언어 선택·오류 화면·로그인 전후 연속성.

## Impact

프론트엔드 hooks, root/documentation loaders와 layouts, 기존 회귀 테스트 및 언어 계약 문서만 변경한다. 번역 카탈로그·시각 디자인·인증/인가·backend/API·DB·운영 배포는 범위 밖이다. 번역 작업이 아닌 현재 dev의 언어 영속화 bugfix이며 공유 checkout의 동시 변경·index·설정·서비스를 보존한다. 검증은 격리 frontend dev 서버와 합성 인증/API 경계의 실제 Chromium으로 수행하며 운영 로그인 성공으로 보고하지 않는다.
