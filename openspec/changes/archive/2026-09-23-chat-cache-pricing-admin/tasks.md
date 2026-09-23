## Implementation Tasks

- [x] Read `DESIGN.md` (including Layout & responsive hierarchy) and confirm the admin model surface uses existing `Field`/`TextInput`/`Pill`/`Alert`/`Button` primitives with no new colour.
- [x] Add the optional `cache_read_price_per_million`, `cache_write_price_per_million`, `cache_write_1h_price_per_million` fields to the admin `Model` type.
- [x] Add a labelled, optional cache-price group to the model create form; omit blank keys and do not apply the input/output pair rule.
- [x] Add the three cache inputs to the price editor; send only keys that changed from the prefill, with a blanked previously set cache price → `null`.
- [x] Validate cache prices as finite non-negative decimals in `Field`'s error slot before submit.
- [x] Show set cache prices in the model list, or a neutral "billed at 0 USD until set" note.
- [x] Keep the models.dev import copy accurate (catalog cache prices are still not applied) and point to the price editor.
- [x] Confirm `backend/app/api/lumen/proxy.py` forwards the admin model request/response bodies unchanged and pin it with a contract test.
- [x] Add/update vitest coverage for create/patch payloads, null semantics, pair-rule independence, validation and list display.
- [x] Update `docs/api/chat.md` and `ARCHITECTURE.md` prose for the admin model pricing surface.
- [x] Run targeted vitest, `npm run test:unit:frontend`, `npm run check`, `npm run test:frontend:design`, the focused contract test and `npm run lint:backend`.

## 검증

- [x] Focused frontend: `admin_models_cache_pricing.test.ts` (8 new), `page.test.ts` (21, including the updated PATCH payload) and `admin_models_short_display.test.ts` (2) all pass, 31 in total. Mutation check: making create send `null` cache keys fails 2 omission tests.
- [x] `npm run test:unit:frontend`: 247 files and 1416 vitest tests pass, plus `node --test` 9/9.
- [x] `npm run check` (`svelte-check`): 2060 files, 0 errors, 0 warnings.
- [x] `npm run test:frontend:design` (`designSystemRules`, `visualDebt`, UI primitives): 22 files and 109 tests pass. No new raw colour.
- [x] `pytest tests/contracts/test_lumen_proxy.py`: 36 pass, including 3 new byte-exact POST/PATCH/GET admin model passthrough cases. `npm run lint:backend` passes.
- [x] `npm run test:orchestration` (20/20, including `--validate`) passes. `npm run test:target -- lumen` passes: backend 36, frontend 10 files and 111 tests. The admin chat vitest files are not in any named target, as before; they run under `test:unit:frontend`.
- [x] Browser check on the real Vite `/admin/chat/models` route, using a synthetic `/api/*` fetch stub and no live Lumen:
  - The cache group is 1 column at 390 and 767px, 2 columns at 768 and 1023px, and 3 columns at 1024 and 1440px. Page-level horizontal overflow is 0 at every width.
  - The edit modal fits at 390×844 and is 3 × 149px at 1440.
  - Typed `-2` shows the `Field` error with `aria-invalid` and sends no PATCH. After the value is corrected, the error clears and the PATCH is sent. This check ran before the review fixes below, when the editor still sent every key; the changed-only body is pinned by the vitest cases in the review-fix section.
  - Escape closes the modal.

## 리뷰 수정 (F1–F3)

- [x] F1: a stored zero that Lumen serializes as `0E-10` showed raw in the list, prefilled raw in the editor, failed the cache pattern, and blocked every later price save. `normalizeDecimalString` now maps any all-zero decimal (including scientific form; it requires a zero digit, so `""`/`.`/`E5` do not match) to `0` and otherwise uses `formatPricePerMillion`. The cache prefill and the list display both use it. No float conversion.
- [x] F2: a cache-only edit on a models.dev-priced model sent the input/output pair, which made Lumen flip it to `manual`, clear `price_metadata`, and block later models.dev imports with 409. `savePrice` now sends only changed keys. Input/output are compared, trimmed, to the raw prefill (`?? ''`) and sent together only if either changed, so Lumen's pair rule still holds. Each cache key is compared to the normalized prefill and is sent as the value, or as `null` when a set price was blanked. Only changed cache keys are validated. A save with no changes closes the modal without a PATCH. A side effect: an input/output-only edit no longer sends cache keys that an older Lumen (`extra='forbid'`) would reject.
- [x] F3: the models.dev modal paragraph that holds the new cache sentence moved from `--color-ink-3` (reserved for disabled text) to `--color-ink-2`, matching the price-editor paragraph.
- [x] Docs: the `docs/api/chat.md` PATCH row and admin prose paragraph, and the `ARCHITECTURE.md` `ChatConfiguration` row, now describe changed-only sending instead of always sending every key.
- [x] Tests: `admin_models_cache_pricing.test.ts` gains 4 cases: the `0E-10` list line reads `캐시 읽기 0`; the editor prefills `0`, and an output-only change sends exactly `{input:"3", output:"16"}` with no field error; a models.dev fixture with storage-precision prices (`3.0000000000`/`15.0000000000`) that edits only 캐시 읽기 sends exactly `{cache_read_price_per_million:"0.3"}`; an unchanged save sends no PATCH. The two always-send cases and the `page.test.ts` PATCH expectation were rewritten for changed-only bodies.
- [x] Mutation checks, each reverted afterwards: disabling the zero normalizer fails 2 tests; always running `pricePayload` fails 3; sending every cache key fails 6.
- [x] Targeted vitest (`admin_models_cache_pricing`, `page`, `admin_models_short_display`): 3 files, 35 tests pass.
- [x] `npm run test:unit:frontend`: 247 files, 1420 vitest tests pass; `node --test` 9/9.
- [x] `npm run check` (`svelte-check`): 2060 files, 0 errors, 0 warnings.
- [x] `npm run test:frontend:design`: 22 files, 109 tests pass.

## 2차 리뷰 수정 (배포 순서·이전 Lumen·usage kind)

- [x] 배포 순서를 Afterglow frontend → Lumen으로 바로잡았다(`docs/api/chat.md`, `ARCHITECTURE.md`, `proposal.md`). 새 Lumen의 cache/advisor-cache `usage.updated` kind를 이전 frontend parser가 거부해 web run이 멈추기 때문이다.
- [x] `frontend/src/lib/api/chatContracts.ts`의 usage kind type과 parser allowlist에 `cache_read_input_tokens`, `cache_creation_5m_input_tokens`, `cache_creation_1h_input_tokens`, `advisor_cache_read_tokens`, `advisor_cache_creation_5m_tokens`, `advisor_cache_creation_1h_tokens`를 추가하고 모르는 kind는 계속 거부한다. `chatContracts.test.ts`에 1개 case를 추가했고 HEAD parser로 되돌리면 실패함을 확인했다.
- [x] 이전 Lumen 감지: cache key가 아예 없는 모델 행은 0 USD 안내 대신 `캐시 단가 미지원`으로 표시하고 가격 수정의 cache 입력을 숨긴다. 불러온 모델이 모두 그런 행이면 등록 form의 cache 입력도 숨기고, 숨겨진 입력의 값·오류는 등록 시 비운다. 모델이 하나도 없으면 버전을 구분할 수 없어 입력을 유지한다(첫 모델에 cache 단가를 넣으면 이전 Lumen이 422로 거절).
- [x] 테스트 fixture `model()`은 새 Lumen처럼 세 cache key를 `null`로 포함하고, `legacyModel()`은 key를 뺀다. `admin_models_cache_pricing.test.ts`는 14 case이며, 감지 함수를 항상 `true`로 바꾸면 2개가 실패한다.
- [x] 검증(다른 세션의 미커밋 작업을 뺀 우리 변경만의 트리): 대상 vitest 4 files 49 tests pass, `npm test`(frontend) 247 files 1422 tests + `node --test` 9 pass, `npm run check` 2059 files 0 errors 0 warnings, `npm run test:frontend:design` 22 files 109 tests pass. 같은 트리의 `npm run test:all`(backend unit 2902, contract 131, 실제 MariaDB/PostgreSQL/Redis functional 27 포함)과 `npm run lint:backend`가 이 라운드의 Svelte/문서 수정 직전 통과했다.

## 발견 사항

- `backend/app/api/lumen/proxy.py` → `service_proxy._forward` streams `request.stream()` and the upstream `aiter_raw()` bytes unchanged. No Pydantic schema or middleware reads or rewrites these bodies (the audit middleware only maps the path), so no backend fix was needed.
- Existing debt, out of scope: the model create form's first row (`md:grid-cols-5` of bare `<input>`s with placeholder-only labels) truncates its placeholders at 768px tablet width.
