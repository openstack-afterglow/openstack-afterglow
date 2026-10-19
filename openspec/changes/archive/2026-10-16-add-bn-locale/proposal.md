## Why

사용자가 기존 여덟 언어와 같은 범위의 방글라데시 언어 지원을 요청했다. 방글라데시의 벵골어를 `bn`, 메뉴 `বাংলা`, Intl `bn-BD`로 제공한다.

## What Changes

- 기존 한국어 정본과 동일한 모든 UI namespace와 공개 가이드 15개에 벵골어 번역을 추가한다.
- 공유 locale registry, 문서 UI/검색/loaders, 공용 `afterglow_locale` 쿠키, SSR HTML lang, 숫자·날짜, CSV 번역 도구에 `bn`을 연결한다.
- 검수 manifest는 빈 상태로 유지하며 기계 작성 초안을 원어민 검수로 표시하지 않는다.
- 기존 언어 및 문서의 path/query/fragment·쿠키 우선순위·preload 경계를 유지한다.

## Capabilities

### New Capabilities

- 벵골어 UI 및 공개 문서, 원어 메뉴 항목, 방글라데시 지역 서식.

### Modified Capabilities

- 기존 공용 언어 선택·쿠키·번역 기여 도구는 아홉 언어를 지원한다.

## Impact

현지화 전용 `/Users/pieroot/code/afterglow-i18n` (`i18n`)에서 작업하며 시작 시 최신 `origin/dev` SHA `08e272422cd855b30d39929c24993047ec0cd6ad`를 fetch·merge했고 ancestry를 확인했다. 기존 미커밋 네 언어 추가와 공유 checkout/index/config/data를 보존한다. Backend API·권한·schema·의존성·운영 배포는 변경하지 않는다. 완료 기준은 번역 키/ICU/태그 검사, 관련 회귀, 타입 검사·빌드 및 실제 브라우저의 벵골어 문서·로그인·합성 콘솔 간 언어 유지와 반응형 화면이다. 실제 Keystone/공급자 검증·커밋·push·운영 배포는 범위 밖이다.
