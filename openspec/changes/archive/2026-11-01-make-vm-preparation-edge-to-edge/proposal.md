## Why

The authored VM preparation scene is currently framed inside a padded panel with separate title, help and close-button rows. It must own the entire preparation surface and follow the console's current palette and appearance instead of remaining a fixed dark artwork card.

## What Changes

- Fill the preparation panel edge-to-edge with the existing glyph renderer; remove visible preparation heading/help/footer and preparation-only outer spacing.
- Keep the existing accessible close action as an integrated overlay; retain loaded wizard layout unchanged.
- Map artwork colors to existing semantic accent/surface/ink tokens and redraw on live root appearance/palette updates without reading styles per animation frame.
- Preserve analytic ring/status alignment, actual dependency settlement, explicit errors/retry, reduced motion, renderer fallback and observer cleanup.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `vm-create-experience`: Full-surface, live-themed preparation with accessible lifecycle behavior.

## Impact

Frontend presentation, the SlidePanel's optional overlay-close placement, canvas palette refresh, focused regression tests and design/architecture/user documentation only. The authored `output/afterglow-loading` assets and glyph algorithm, API/authority/resource lifecycle and cloud/deployment configuration remain unchanged. Verification is delegated to the main agent; no tests, builds, lint or runtime checks are executed during implementation.
