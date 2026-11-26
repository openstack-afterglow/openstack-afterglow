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

## Follow-up 2026-11-26 (user review: "a separate shrinking screen comes in")

- [x] Merge origin/dev d7165cf6 (1.32.33); resolve ARCHITECTURE.md review block and regenerate experience catalog.
- [x] Remove the overlay eyebrow and `consoleEntry.eyebrow` key per the 1.32.33 eyebrow cleanup.
- [x] One travelling picture: share only the AfterglowOrbit layer, show only the outgoing snapshot at pixel size (`object-fit: none`, clipped group), let the incoming canvas settle at the end.
- [x] Separate copy layers (`data-route-scene-copy`) so text fades above the moving art instead of popping.
- [x] Console entry through `startSceneTransition('console-enter')`: login identity art grows into the overlay; panel outgoing-only (a vanished incoming named element aborted the scene when the dashboard replaced the login page).
- [x] Tests: startSceneTransition and View Transition console-entry path; frontend 632 files / 8,765 tests; svelte-check 0 errors; i18n, catalog, docs checks; backend test_experience* 31 passed.
- [x] Chromium verification of the real app (vite dev, mocked auth API, scene slowed to 3.6s) and the preview artifact.
- [ ] NOT RUN: contract/functional/backend-lint parts of `npm run test:gate` (need Docker DB services).
