## Why
The user rejected tiling every table, card and button with the full Afterglow scene. Full-area art is for whole page/panel or large primary list loading only; smaller regions follow the character-interface theme in `output/afterglow-loading/progress.html` (with `output/lumen-assets` and `frontend/static/theme/afterglow` as companion assets). The public main page first screen should become the authored scene with a soft mouse light.

## What Changes
- `LoadingState`: `surface` keeps the animated authored scene; `section` becomes the indeterminate character flow bar; new `table` keeps column structure with drifting `··::··` cells and an unconfirmed row count; `inline`/`control` show the `[~]` status glyph. One shared 140ms step clock, paused when hidden/reduced motion. Decorative characters are aria-hidden generated content, so owner copy remains the visible/accessible text.
- `ProgressTrack` indeterminate uses the same flow bar; `StepProgress` active step uses `›`; StatusChip transitional status uses a pulsing dot.
- Sub-panel loaders previously set to `surface` (account sections, cards, overlays) downgraded to `section`; table-fronting admin lists use `table`.
- Landing hero replaced by the authored scene (signature, motion toggle, eyebrow, wordmark, actual body copy, console/explore actions, footer tagline) with an opt-in pointer light on `AfterglowOrbit` (mouse only, touch ignored, eased, listeners released). Retired hero kinetic graphic and its locale keys.
