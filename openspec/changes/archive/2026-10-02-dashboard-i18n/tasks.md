## Implementation Tasks

- [x] Create the isolated `i18n` worktree from `dev` (initially named `feat/dashboard-i18n`, renamed at the user's request) and inventory visible frontend text (≈7.8k Korean-bearing code lines in 661 files).
- [x] Implement the i18n runtime: locales, ICU subset formatter, rich-text segments, namespace binding with typed keys, fallback chain, cookie persistence, SSR `<html lang>` and page remount on language change.
- [x] Add the language picker to the console header; convert root layout, navigation, breadcrumbs, status labels, sidebars, command palette, error page, tutorial banner and UI primitives.
- [x] Provide catalog tooling (check, scan, report, export/import CSV, review, format), review manifests and the terminology glossary.
- [x] Convert every remaining public, user, admin and shared surface into feature namespaces with ko/en/ja/zh-CN catalogs, and add the picker to login and landing pages.
- [x] Add regression coverage: runtime/formatter, catalog validation, hard-coded text guard, review/CSV tooling and SSR locale resolution; adapt tests broken by the conversion.
- [x] Apply language-specific CJK font fallbacks and document typography, picker placement and RichText in `DESIGN.md`.
- [x] Write the Korean and English localization contribution guides and update `ARCHITECTURE.md`, the agent development guide and `CHANGELOG.md`.
- [x] Verify in a real browser: all four languages on landing, login, user dashboard and admin preview; persistence across reload; header switching without losing chrome state; responsive overflow at 320–1440px; `svelte-check`, frontend unit suite and production build.
- [x] Review the architecture stamp for this change and archive it.

## Verification evidence

- Final catalogs: 36 namespaces, 8,367 Korean source messages and complete en/ja/zh-CN catalogs; `i18n:check` 0 errors/0 warnings. `i18n:scan` found 0 hard-coded Korean lines in 911 source files. All 8,367 messages per target locale remain explicitly unreviewed drafts (0 reviewed, 0 missing).
- Focused formatter/runtime/rich/CSV-review regressions: 4 files, 50 tests passed. Full frontend suite: 273 files, 1,706 tests passed; file-log runner 9 tests passed. `svelte-check` and production build passed after fixing canonical floating-IP keys and declaring custom rich snippets outside Alert props.
- Actual isolated Chromium: four-language landing/login/user/admin surfaces and persisted cookie/reload; retained sidebar/header nodes and expanded groups; 32 landing breakpoint measurements and 28 table measurements at 320–1440px; zero unintended overflow. Actual terminal locale changes retained xterm textarea/buffer; loading animation/reduced motion and rich tutorial emphasis exercised.
- Final administrator provider screen: four languages × 320/390/768/1024px, zero overflow and no error alerts with synthetic API fixtures. ChatGPT policy anchor and Perplexity code URLs rendered correctly without changing stable provider choices. Screenshot proof used the corrected query-bearing fixtures; the earlier CORS/preflight error fixture run is not loaded-data evidence.
- Built preview on isolated loopback port 57663: 16 simultaneous `/login` HTTP requests returned 200 with matching cookie/SSR html lang; four additional requests verified visible translated submit labels. No real login/provider/OpenStack operation performed.
- Architecture working/staged digest: `09b9239b3a80ede149d184fa1fbbb5d5636f4e8dc077827b368c5d44c983a445` (2,320 files), staged check used a temporary index; actual index SHA256 remained `e798d25b9254dab66b731e01d3b2e0dcbd86fbbaa413236f7019b01395ae2272`.
- Full `npm run test:gate` passed with test-process-only `SERVICE_CLOUD_SHELL_ENABLED=false LOGO_PATH=/logo.png LOGO_DARK_PATH=/logo-white.png LOGO_LIGHT_PATH=/logo-dark.png AFTERGLOW_TEST_PROJECT_NAME=afterglow-i18n-gate`. The first attempt stopped on local Cloud Shell `network_id`; the second exposed two branding default assertions contaminated by local SVG settings. Explicit source-default overrides isolated the tests without backend/test/production config edits. JS orchestration/Kolla, backend/frontend units, 136 contracts, 28 real-datastore functional tests and Ruff passed; disposable test services/network were removed.
- `sync-gbrain` could not run: CLI and standard preflight executable are absent. No inaccurate search guidance/config was written. Locale changes intentionally remount page contents and can reset unsaved page forms; retained chrome/global stores are outside that boundary. API/auth/backend data/operator text remain unchanged.
- Owned browser tabs, Vite integration/production preview services and temporary contributor CSV were cleaned up. No commit, push, merge or deployment was performed.
