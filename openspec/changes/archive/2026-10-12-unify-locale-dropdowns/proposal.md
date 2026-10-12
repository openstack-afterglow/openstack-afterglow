## Why

사용자 첨부 화면에서 문서는 테마를 따르는 언어 disclosure지만 메인·콘솔은 투명한 native select 위에 OS popup이 표시되어 표면·글자·선택 상태가 통일되지 않는다. 문서의 기존 테마형 메뉴를 기준으로 언어 선택 UI를 하나로 합친다.

## What Changes

- 기존 LocaleSelect를 문서와 같은 native details/summary 기반의 theme-token 메뉴로 전환한다. 운영체제 option popup과 투명 select는 제거한다.
- 문서도 같은 LocaleSelect를 사용한다. compact globe/code와 labelled native-name trigger는 공간별로 유지하되, 펼친 메뉴는 동일한 raised/line/selected/ink/radius/focus tokens, 네 언어의 원어 이름과 선택 상태를 쓴다.
- 앱 선택은 기존 setLocale/cookie/html-lang/remount와 stable-id focus restoration을 유지한다. 문서는 기존 lang query의 실제 link를 써서 path/query/hash·no-JS navigation을 보존한다. 문서 URL 언어를 앱 cookie에 강제로 저장하지 않는다.
- Escape·밖 클릭·Tab 이탈·navigation 종료, Arrow/Home/End 이동과 Enter 선택(앱 버튼은 Space도 지원), mobile target와 메뉴 clipping을 검증한다.
- Auth/backend/API/schema·theme palette·번역 내용·콘솔/문서 이동 목적지는 변경하지 않는다. 새 dependency나 일반 form select의 변경은 없다.

## Capabilities

### New Capabilities

없음. 기존 언어 선택기의 시각·상호작용 일관성 수정이다.

### Modified Capabilities

- 문서·메인·로그인·사용자/관리자 콘솔이 동일한 언어 메뉴를 공유한다.

## Impact

frontend/src/lib/i18n/LocaleSelect.svelte, 문서 layout의 중복 언어 disclosure와 관련 디자인/현지화/검증 문서. 사용자 보고는 재확인할 오류가 아닌 ground truth로 취급하고, 실제 loopback Chromium에서 변경 전/후 화면과 네 언어·테마·반응형·키보드·document/cookie/URL 결과를 관측한다. 콘솔은 기존 tutorial UI로 검증하며 실인증/운영 배포 증거로 확대하지 않는다.
