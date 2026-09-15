## Implementation Tasks

- [x] Decide per surface whether content actually passes beneath it, and reject candidates whose blur would sample a flat canvas or a scrim.
- [x] Define the material tokens for both themes and the guarded utility classes in `layout.css`, and expose them in `tokens.ts`.
- [x] Apply the chrome material to the header without making the header a containing block.
- [x] Consolidate the ad-hoc scrim blurs and move `BulkSelectionOverlay` onto the overlay material.
- [x] Add the `designSystemRules` entry, including the guard-order assertion.
- [x] Record the adopted set and the evidence-based exclusions in `DESIGN.md`.
- [x] Measure composited text contrast in both themes on the running app, not against the token. Light, worst backdrop rgb(219,220,223): ink-0 13.02:1, ink-2 5.53:1. Dark, worst backdrop rgb(44,45,47): ink-0 12.54:1, ink-1 9.49:1, ink-2 5.02:1. All pass AA at normal size.
- [x] Confirm the header's popovers still escape it and that no dropdown is trapped. The header computes backdrop-filter none, so it creates no containing block, and the notification dropdown renders from y=48 to y=150, unclipped.
- [x] Run the design target, the frontend unit suite and the build, then re-stamp `ARCHITECTURE.md`.
