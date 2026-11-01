## Context

The owner has approved the current VM preparation canvas artwork, not merely a circle/spinner metaphor. The console contains full-area first loads, bounded dependency sections, dense table/control waits and real progress stages. They must share that artwork without treating decoration as measured work.

## Goals / Non-Goals

**Goals:** replace all unrelated indeterminate pending ornaments; preserve useful loaded surfaces during background refresh; retain existing localized task text, accessibility and honest outcomes; keep many simultaneous controls inexpensive.

**Non-Goals:** changing request/auth/native operation behavior, smoothing or inventing progress, adding timers/minimum waits, deploying services, modifying shared data, or redesigning the approved VM preparation scene.

## Decisions

1. `LoadingState` owns four scales. `surface` fills its owner, `section` has a bounded self-contained scene, and `inline`/`control` render phrasing-safe spans with adjacent copy. Existing HTML attributes and snippets are forwarded; `label=""` explicitly requests decorative-only artwork when an adjacent label already explains the work. The default copy uses the existing shared localized loading message. Size/color knobs and compatibility wrappers would perpetuate old conventions and are removed.
2. All scales use `AfterglowOrbit` and the same `createAfterglowScene` glyph renderer. Compact controls paint one static frame at virtual 320×240 with 0.5 backing resolution (160×120 pixels), not a new CSS/SVG ring or approximate text symbol. Static controls need no RAF, resize/intersection observer or visibility/media listener. Their palette observer redraws on root theme changes and disconnects on destruction. Animated area scenes retain the established 24fps, DPR1.5, 2.4-million-pixel caps and all suspension/cleanup boundaries. A second compact animation system or shared scheduler is unnecessary.
3. Area labels use the renderer's analytic center and radius; width is bounded to 1.45 radii. Canvas is decorative, while existing task/status and failure/retry controls remain real DOM. No busy ancestor delays live status announcements. Forced colors keeps actual DOM content and omits decorative canvas.
4. Initial loading may replace only its unavailable region. A background refresh preserves available data/drafts and limits the pending ornament to its control or dependent subsection. PageShell recognizes a direct surface child and flex-fills the workspace; panel owners provide their bounded flex/height and remove obsolete padding.
5. ProgressTrack keeps measured fill/ARIA values and measured active sheen. Unknown active work displays the authored compact scene without a value. StepProgress/ProvisionPipeline retain observed stages, success/failure icons, labels and connectors; only the current indeterminate ornament changes. No decoration advances a stage or signals completion.
6. Migrate every internal caller before deleting LoadingSpinner, LoadingSkeleton, ActivityIndicator and their exports. Remove old structure-only tests; retain independent state/accessibility/progress behavior coverage. No new permanent source-text/wiring/appearance tests are introduced.

## Risks / Trade-offs

- Static compact artwork is quieter than spinning controls → accurate labels and aria-busy still convey pending state; the identical authored renderer preserves the family without per-row animation work.
- Full-area height depends on the owner → PageShell handles direct page loaders; bounded panels retain explicit owner sizing, checked separately in integrated browser QA.
- Canvas unavailable/forced colors → preserve actual localized DOM status and existing recovery actions, never claim successful work from a blank canvas.
- Broad presentation migration may accidentally alter conditional boundaries → retain the existing pending conditions and owner state; integration verification must cover loading, error, empty, retained refresh and real progress.

## Migration Plan

Source-only cutover in one frontend revision, after all caller migrations are ready. Parent performs integrated checks and browser QA, records evidence separately, and stamps/archives only after completion. No runtime deployment is part of this change. A rollback uses a coherent prior frontend revision rather than restoring obsolete primitive shims.

## Open Questions

None for implementation. Live production acceptance remains outside this source-only assignment.
