## 1. Full-surface preparation

- [x] 1.1 Preserve the authored source assets, glyph algorithm, shared geometry and existing pending/error/retry semantics.
- [x] 1.2 Remove preparation-only framed stage, visible title/help rows, body padding and close-button flow row; fill the actual panel dimensions.
- [x] 1.3 Keep the existing accessible close as a 44px integrated overlay and preserve loaded wizard/admin-target chrome and spacing.
- [x] 1.4 Keep centered real pending status, screen-reader task states and bounded in-scene failure/retry with no busy live-region ancestor; name/focus the scrollport with visible focus even while retry is disabled.

## 2. Live appearance

- [x] 2.1 Map existing artwork token names to semantic canvas/accent/accent-2/ink-0/ink-2 CSS colors, preserving authored glyph opacity.
- [x] 2.2 Refresh cached palette and redraw current elapsed frame on root class/style changes without per-frame style reads, remount, new requests or elapsed reset.
- [x] 2.3 Release palette observation with existing RAF/resize/intersection/media/visibility lifecycle; retain reduced-motion/fallback/forced-color behavior.

## 3. Regression definition and documentation

- [x] 3.1 Extend actual VmCreatePanel/store integration tests for edge-to-edge owner layout, close/Escape, absent preparation chrome and loaded-form handoff; retain auth, failed-lane retry, scope/ABA, reopen and background-refresh regressions.
- [x] 3.2 Extend renderer lifecycle tests for live root appearance/palette updates, static reduced-motion/settled redraw, no per-frame computed-style reads and no redraw after unmount.
- [x] 3.3 Define the semantic artwork mapping in the existing design-system regression test.
- [x] 3.4 Surgically update DESIGN.md, ARCHITECTURE.md, docs/user-guide.md and CHANGELOG.md without changing docs/testing.md or archived artifacts.

## 4. Main-agent verification handoff

- [x] 4.1 Main agent: final16files279tests with topology integration; Svelte0errors17warnings (16existing,1focusable failure region); scan0. Full gate/build not run.
- [x] 4.2 Actual compiled panel390/768/1440px×light/dark6conditions full coverage, live keyboard ThemeSelect/pixel change and error focus/PageDown→retry→loadedform verified. Safari, short/zoomed scroll stress remain unverified; no production claim.
- [x] 4.3 Main agent documented source/synthetic evidence and completed archive/architecture checks.
