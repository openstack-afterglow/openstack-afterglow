# Tasks: auth-route-scene-transitions

Base: origin/dev 29131d05.

- [x] Add `--motion-duration-scene` token through layout.css, tokens.ts, designSystemRules test.
- [x] Add route-scene classifier/runner and wire `onNavigate` in root layout.
- [x] Mark landing hero / auth identity / auth panel scene parts; add global view-transition CSS.
- [x] Add console entry store + overlay; use it in password login and SSO callback publish.
- [x] Add i18n keys (9 locales); regenerate experience catalog.
- [x] Unit tests: routeScene, consoleEntry store, overlay component.
- [x] Update DESIGN.md Motion and ARCHITECTURE.md; architecture stamp.
- [x] Frontend vitest 633 files / 8,803 tests passed; svelte-check 0 errors; i18n:check 0/0; docs:check OK; experience:catalog:check OK; backend test_experience*.py 31 passed / 23 skipped.
- [x] Visual verification in Chromium (vite dev, mocked auth API): desktop 1600×1000 and mobile 390×844, landing→login morph and password login→console entry→dashboard.
- [ ] NOT RUN: full `npm run test:gate` (contract/functional need Docker DB services; full backend lint/unit not run). SSO callback path verified by unit tests only, not in a browser against a real provider.
