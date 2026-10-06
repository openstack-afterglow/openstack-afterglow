---
title: 프론트엔드 번역 참여
lang: ko
nav_order: 9
---

# 프론트엔드 번역 참여

Afterglow UI는 한국어(`ko`, 기본·원문), 영어(`en`), 일본어(`ja`), 중국어 간체(`zh-CN`)를 지원합니다. 번역은 `frontend/src/lib/i18n/messages/<locale>/<namespace>.json`에서 같은 키로 대응합니다. 영어는 한국어를 읽지 못하는 번역자의 참고 언어입니다. 리소스 이름·사용자 입력·API 식별자·제품명은 번역하지 않습니다. 서버 오류, 운영자가 작성한 사이트 설명·공지, 튜토리얼의 모의 서버 데이터는 받은 내용을 유지합니다.

[English guide](en/frontend-localization.md) · [아키텍처](../ARCHITECTURE.md) · [용어집](../frontend/src/lib/i18n/glossary.csv)

## How to: 스프레드시트로 번역·검수하기

Node.js 20 이상과 저장소가 필요합니다. 다음 명령은 저장소 루트에서 실행합니다. 스프레드시트만 사용하는 기여자는 유지보수자에게 CSV를 요청하면 됩니다.

```bash
npm --prefix frontend run i18n:report -- --locale ja --by-namespace
npm --prefix frontend run i18n:export -- --locale ja --namespace common --out /tmp/afterglow-ja.csv
```

CSV는 BOM이 있는 UTF-8입니다. `namespace`, `key`, `source_ko`, `reference_en`, `translation`, `status` 열을 포함합니다. **`translation`만 수정**하고 열 이름·키·한국어 원문은 유지하세요. 따옴표, 쉼표와 셀 내부 줄바꿈을 보존하는 UTF-8 CSV로 저장합니다. 참고 영어의 의미가 불명확하면 한국어 원문과 화면을 함께 확인합니다.

번역 셀의 의미 있는 앞뒤 공백·줄바꿈은 유지됩니다. 중복 열 이름, 열 수 불일치, 닫히지 않은 따옴표는 오류입니다. 카탈로그나 검수 JSON을 읽거나 파싱할 수 없으면 쓰기·검수를 중단하며 기존 파일을 빈 내용으로 덮어쓰지 않습니다.

```bash
npm --prefix frontend run i18n:import -- --locale ja --file /tmp/afterglow-ja.csv
npm --prefix frontend run i18n:check
```

빈 번역 셀은 기존 값을 지우지 않고 건너뜁니다. 원문이 바뀌었거나 변수·태그·문법이 잘못된 행이 하나라도 있으면 전체 import가 취소됩니다. 오류를 수정하거나 최신 CSV를 다시 export하세요. 검수를 마친 원어민의 CSV만 `--reviewed`로 가져옵니다.

```bash
npm --prefix frontend run i18n:import -- --locale ja --file /tmp/afterglow-ja.csv --reviewed
npm --prefix frontend run i18n:report -- --locale ja
```

JSON을 직접 수정했다면 검수한 키를 명시할 수 있습니다.

```bash
npm --prefix frontend run i18n:review -- --locale ja --namespace common --key actions.cancel
npm --prefix frontend run i18n:format
npm --prefix frontend run i18n:check
```

번역 파일과 해당 `review/<locale>.json`을 함께 PR에 포함합니다. 검수 명령은 선택한 번역의 문법·변수·태그 오류를 거부하고 검수 기록을 일부만 변경하지 않습니다. `--reviewed`는 사람이 의미·용어·맥락을 확인했다는 선언이며 자동 번역 품질 인증이 아닙니다. 초기 en/ja/zh-CN 번역은 검수 전 초안입니다.

## 검수 상태

| 상태 | 의미 |
|---|---|
| `draft` | 번역은 있지만 한국어 원문에 대한 검수 기록 없음 |
| `reviewed` | 현재 한국어 원문의 해시와 검수 기록 일치 |
| `outdated` | 검수 뒤 한국어 원문 변경; 다시 검수 필요 |
| `missing` | 번역 없음 또는 빈 문자열 |

검수 기록은 `namespace:key` → 한국어 원문 SHA-256의 앞 16자리입니다. 번역 자체의 변경은 해시로 감지하지 않으므로 이미 검수된 문구를 수정할 때에도 원어민 재검수가 필요합니다. `i18n:check`는 키 누락·추가, 문법, 변수·태그 불일치, ICU 렌더 경로별 rich 태그의 균형·중첩, 비한국어 번역의 한글 잔존을 검사합니다. 의미와 자연스러움은 사람이 확인합니다.

## 메시지 규칙

- 키는 의미가 드러나는 점 구분 lowerCamelCase입니다. 예: `deleteDialog.body`.
- `{name}` 같은 변수는 모든 언어에서 동일해야 합니다. 변수의 순서는 바꿔도 됩니다.
- 영어 개수 표현은 `{count, plural, one {# instance} other {# instances}}`로 작성할 수 있습니다. `other`는 필수이고 숫자 변수로 호출해야 합니다. 한국어·일본어·중국어에는 `{count}`가 적절할 수 있습니다.
- `select`도 `other`가 필수입니다. ICU의 `number`, `date`, `selectordinal`, `offset`은 지원하지 않습니다.
- ICU 구문으로 해석될 중괄호는 작은따옴표로 감싸고(`'{'name'}'`), 작은따옴표 자체는 `''`로 작성합니다.
- `<strong>`, `<em>`, `<code>`, `<kbd>`, `<br/>`와 사용자 정의 태그는 원문과 일치시킵니다. 링크 URL이나 HTML을 새로 넣지 않습니다.
- Rich 태그는 각 렌더 결과에서 올바르게 중첩·종료되어야 합니다. 태그를 전체 plural 바깥에 두거나 각 분기 안에서 닫는 방식이 권장됩니다. `<model>` 같은 단독 사용자 정의 코드 힌트는 닫히지 않은 rich 태그로 취급하지 않습니다.
- [용어집](../frontend/src/lib/i18n/glossary.csv)의 OpenStack 용어·제품명, 원문의 의미·상세도·경고 수준을 유지합니다. 고유명사와 코드/명령은 그대로 둡니다.

## How to: 화면에서 번역 키 찾기

언어 선택기는 공개 페이지, 로그인 페이지, 콘솔 헤더에서 모국어 이름으로 표시됩니다. 선택은 `afterglow_locale` 쿠키에 1년간 저장되며 새로고침의 서버 HTML도 같은 언어로 렌더링됩니다. 브라우저 언어를 자동 적용하지 않고 선택이 없으면 한국어입니다.

개발자 도구 콘솔에서 다음을 실행하고 새로고침하면 문구 대신 `namespace:key`가 표시됩니다.

```js
localStorage.setItem('afterglow.i18n.debug', 'keys');
location.reload();
```

종료:

```js
localStorage.removeItem('afterglow.i18n.debug');
location.reload();
```

키 표시 모드는 hydration 뒤 켜집니다. 언어 변경 시 페이지 내용은 다시 mount되므로 저장하지 않은 페이지 폼은 초기화될 수 있습니다. 헤더·사이드바 펼침 상태·VM 생성 패널·루트의 Cloud Shell·업로드 등 전역 상태는 유지합니다. 이미 발생한 토스트·저장된 오류 문구는 발생 당시 언어를 유지할 수 있습니다. 검수할 때 좁은 화면에서 줄바꿈·버튼 잘림·접근성 이름도 확인하세요.

Dashboard·관리자·Palimpsest는 `main` 안의 일반 페이지 children만 다시 mount합니다. Live 터미널을 포함하는 컨테이너 상세와 Drover 목록·상세·관리자 목록은 예외이며, 언어 변경 시 페이지·WebSocket·scrollback을 유지하고 표시 문구와 터미널 접근성 이름만 갱신합니다. Palimpsest 패키지의 저장 전 초안과 일회성 발급 secret은 여전히 폐기되므로 언어를 바꾸기 전에 필요한 secret을 안전하게 보관하세요. 보안 그룹 합집합은 규칙·정렬 등 정책 의미를 그대로 두고 현재 언어의 표시 label만 계산합니다. 이미지 스타일 안내의 한국어 suffix는 번역 누락이 아니라 실제 provider 요청에 사용하는 원문입니다.

## 개발자 작업 시작·재개

현지화 코드 작업은 사용자 승인된 별도 `i18n` worktree에서만 진행합니다. 매번 최신 GitHub `dev`를 먼저 가져와 병합하고 충돌을 해결한 뒤, 추가·수정된 화면을 기준으로 번역합니다. 기존 변경을 보존하며 공유 checkout의 브랜치를 전환하거나 게시된 `i18n`을 rebase·force push하지 않습니다.

```bash
git fetch origin dev
git merge origin/dev
git merge-base --is-ancestor origin/dev HEAD
npm --prefix frontend run i18n:check
npm --prefix frontend run i18n:scan
```

병합 직후 검사는 신규 누락과 작업 범위를 확인하는 기준입니다. 누락을 갱신한 뒤 검사·관련 테스트·실제 네 언어 화면 검증을 다시 완료합니다. 완료·push 직전에 다시 fetch하여 dev가 진행했으면 병합·번역·검증을 반복하고, OpenSpec과 보고에 실제 반영한 dev SHA를 기록합니다. 상세 절차는 [에이전트 개발 규정](agent-development-guide.md)의 최신 dev 기준을 따릅니다. 스프레드시트 기여자에게는 이 기준으로 유지보수자가 export한 최신 CSV를 제공합니다.

## 개발자 계약

`ns/<namespace>.ts`는 한국어 JSON 키를 타입으로 쓰고 네 언어 JSON을 eager glob으로 가져옵니다. 해당 namespace를 가져온 코드의 번들에 카탈로그가 포함됩니다. `t()`는 markup, `$derived`, getter 또는 이벤트 호출 시점에 사용합니다. 모듈 최상위나 SvelteKit `load`에서는 호출하지 않습니다. 서버 locale은 루트 layout의 동기 render 시작에서 초기화하므로 render 밖에서 번역하면 요청 간 언어가 섞일 수 있습니다.

```svelte
<script lang="ts">
  import { t } from '$lib/i18n/ns/common';
</script>

<button>{t('actions.cancel')}</button>
```

태그가 포함된 메시지는 `t.rich(key, values)`와 `<RichText segments={...} />`로 렌더링합니다. 변수는 텍스트로 보호되며 임의 HTML을 삽입하지 않습니다. `t()`는 태그 문자열을 그대로 반환하므로 rich 메시지에 사용하지 않습니다. 링크는 custom snippet으로 연결하고 하위 요소의 scoped CSS는 `:global(...)` 또는 `classes`로 지정합니다.

전역 Cloud Shell·컨테이너 터미널·k3s 셸은 `terminalLocale.ts`로 xterm 입력의 접근성 이름과 출력 과다 알림을 갱신합니다. 기존 터미널 버퍼나 원격 출력은 번역·초기화하지 않습니다. 한국어 카탈로그는 원래 UI에 있던 영어 기본 알림을 그대로 유지합니다.

날짜·숫자는 `intlLocale()`을 포맷할 때 호출합니다. API의 ISO 시간·ID·코드·백엔드 요청 값은 바꾸지 않습니다. 하드코딩 회귀는 다음으로 검사합니다.

```bash
npm --prefix frontend run i18n:scan
```

의도적인 서버 데이터·파싱 정규식·운영자 설정은 `hardcoded-text-allowlist.json`에 정확한 줄과 이유를 기록합니다. 파일 전체 허용으로 UI 누락을 숨기지 않습니다. 유일한 예외는 `/docs`의 한국어 정본 가이드(`src/lib/docs/*Guides.ts`·`gettingStarted.ts`), 한국어 원문을 lookup key로 쓰는 `src/lib/docs/translations/<locale>/` 사전, 그리고 `src/lib/docs/locales.ts`의 언어별 docs UI 사전입니다. 이 파일들은 `translateDocGuide`·`docsMessages`를 거쳐 네 언어로 표시되는 데이터이므로 `"lines": "all"`로 허용합니다. 이 검사는 한글 잔존을 찾으며 하드코딩된 영어까지 자동으로 판별하지는 않습니다.

## 문제 해결

- `argument-mismatch`: 누락하거나 이름을 바꾼 `{변수}`를 원문과 맞춥니다.
- `tag-mismatch`: 태그 구조를 원문과 맞춥니다. 새 태그나 HTML은 추가하지 않습니다.
- `rich-structure`: ICU 분기마다 태그의 열림·닫힘과 중첩 순서를 확인합니다. 단순히 같은 태그 개수를 유지하는 것으로는 충분하지 않습니다.
- `syntax`: `other` 분기, 중괄호, 작은따옴표를 확인합니다.
- `Korean source changed since export`: 최신 CSV를 다시 받고 번역을 옮긴 뒤 맥락을 재검수합니다.
- `namespace:key`가 보임: 키 모드가 켜졌거나 모든 fallback 카탈로그에서 문구가 누락됐습니다.
- 일본어·중국어 글꼴이 환경마다 다름: 라틴 문자는 번들 글꼴, CJK는 언어에 맞는 시스템 글꼴을 사용합니다. [DESIGN.md](../DESIGN.md)의 typography 계약을 참고합니다.
