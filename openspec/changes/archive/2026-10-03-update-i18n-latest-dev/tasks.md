## Implementation Tasks

- [x] Fetch latest origin/dev and preserve the existing workflow rule before ordinary merge; initial selected dev SHA ff007edb6e4bf75f0c0a05107ca6340b593675ff.
- [x] Reconcile unified console navigation, layout/chrome and route metadata with reactive four-locale labels.
- [x] Reconcile consumer landing behavior and localize new journey/console preview surfaces.
- [x] Reconcile current administrator model/media pricing and provider/SDK guide behavior and messages.
- [x] Reconcile media studio/model selection and audio API display messages without changing stable model/provider IDs.
- [x] Reconcile VM capacity/refresh/admission behavior and localize security-group union without changing policy semantics.
- [x] Localize new Palimpsest package/ProxySQL surfaces and all remaining current-dev visible text; resolve documentation conflicts and retain workflow rule.
- [x] Finish ordinary merge with latest dev ancestry and preserve user changes/published i18n history.
- [x] Pass catalog/scanner/Svelte checks, frontend suite/build, full project gate and actual browser verification of changed four-locale surfaces.
- [x] Fetch latest dev again, integrate any advancement, record final dev SHA/architecture evidence and update documentation/changelog for archive.

## Verification evidence

- Re-fetched origin/dev on continuation; it remains `ff007edb6e4bf75f0c0a05107ca6340b593675ff`. Ordinary merge only; no rebase/force-push.
- Catalog check: 37 namespaces, 8,922 Korean source messages, 0 errors/warnings. Scanner: 0 hard-coded Korean lines in 925 files; native provider prompts and explicit fixture data use exact-line documented exceptions.
- Svelte check: 2,218 files, 0 errors/warnings. Production adapter-node build passed. Integration corrected a string-vs-number count comparison and removed a nonexistent `/palimpsest` root equality from the generated route union.
- Existing admin model consumer regression: 35 passed after deleting two incidental Korean wording pins; price-pair admission, exact payload and editable context draft assertions remain. Full frontend gate: 281 files / 1,935 tests passed.
- Full `npm run test:gate` passed: backend unit 3,523; contract 141; functional 28 with isolated real MariaDB/PostgreSQL/Redis; backend Ruff check and 530-file format check. Test-only environment isolates Cloud Shell/logo configuration and uses `AFTERGLOW_TEST_PROJECT_NAME=afterglow-i18n-gate`; disposable services were removed without touching development services/volumes.
- Architecture reviewed working digest: `93a2fb9bfe8776b156b7539117ea83ac9eab41ebe2317dd5f01c4f94e329d3e1` (2,369 source files). Review covers preserved dev contracts and active-locale display boundaries, not live service acceptance.
- Actual Chromium on isolated source Vite `127.0.0.1:5198`: ko/en/ja/zh-CN at 390/768/1024/1440px. Verified landing hero/locale chooser; user/admin navigation labels and unchanged destinations; instance SG direction expand/collapse and tables; VM flavor unavailable-capacity blocker stays disabled; media pricing dialog; group/project results; ProxySQL missing-config state; image/audio Studio empty-model states; package inventory and access-key scope dialog; OpenAI SDK guide and quota formatting. Measured page/dialog horizontal overflow 0; screenshots inspected. Fixture metadata was corrected where incomplete; missing fixture failures are not application regressions.
- Browser identity/API and tutorial data were synthetic, not real authentication, paid provider inference, scheduler/Placement or Hub execution. No VM/package-key creation, deployment or production changes performed. Foreign-language translations remain drafts, not native-reviewed.
- SG utility/component SSR smoke also passed all4 through the same Vite SSR runtime: semantics invariant, translated call-time labels and loading/error precedence preserved.
- Optional GBrain sync unavailable: `gbrain` is not on PATH. No false capability guidance or tool installation added.
- Final fetch still selected `ff007edb6e4bf75f0c0a05107ca6340b593675ff`; merge commit `630b3d01dcee466c27c3c549f36fbbae901629ef` includes it and `git merge-base --is-ancestor origin/dev HEAD` passed. Staged architecture digest matched the reviewed working digest before commit. No push or deployment performed.
- Isolated Vite server and both managed QA browsers stopped; only their session-owned profiles and temporary review index removed. Shared development services, worktree and user data preserved.
