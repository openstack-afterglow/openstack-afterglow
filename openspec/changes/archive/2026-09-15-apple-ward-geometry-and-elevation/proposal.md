## Why

The product owner asked that Afterglow follow Apple's design outside the system's own characteristics and items, while preserving the warm orange emphasis and the modern feel. The preceding change recorded that boundary in `DESIGN.md`; this change applies the part of it that touches no color.

Two concrete defects make the case. `--shadow-restraint` is referenced in 103 files across 110 occurrences — `Modal`, `SlidePanel`, `CmdPalette`, `Toast`, `ActionMenu`, `SearchSelect`, `ProjectQuotaPanel`, and many route modals — and is defined nowhere; verified in the running app, `box-shadow: var(--shadow-restraint)` computes to `none`, so every overlay in the console renders flat against `DESIGN.md`'s own rule that modal and popover elevation carries a restrained shadow. Separately, the radii `DESIGN.md` prescribes exist only as prose: there is no `--radius-*` token, `ui/` primitives carry about thirty literal `border-radius` values, and feature files reach for Tailwind `rounded-*` across 396 files.

## What Changes

- Define the missing elevation token(s) in `frontend/src/routes/layout.css` for both the dark default and the `:root.light` remap, restoring the depth the overlay layer was always meant to have, and expose them through `frontend/src/lib/design/tokens.ts`.
- Define an Afterglow radius scale in `@theme static`, overriding the Tailwind `--radius-*` values that `rounded-md`/`rounded-lg`/`rounded-xl` already resolve against, so the geometry retunes centrally rather than through a 396-file sweep.
- Reconcile the literal `border-radius` values in `frontend/src/lib/components/ui/*.svelte` with that scale so primitives and feature files stop diverging.
- Update the `DESIGN.md` geometry and elevation prose to the shipped token names and values, and add the `designSystemRules` assertions that keep them from drifting again.

## Capabilities

### New Capabilities

- A token-backed radius and elevation contract, retunable from `layout.css` alone.

### Modified Capabilities

- Overlay surfaces regain the elevation `DESIGN.md` already prescribes.
- Corner geometry moves Apple-ward by a margin calibrated against the densest real surfaces rather than against a consumer-app default.

## Impact

- `frontend/src/routes/layout.css`, `frontend/src/lib/design/tokens.ts`, `frontend/src/lib/components/ui/*.svelte`, the design-system tests, and `DESIGN.md` change.
- Source files enter the architecture digest, so this change requires an `ARCHITECTURE.md` re-stamp, unlike the documentation-only change before it.
- No palette, gradient, tone, or contrast-token change. The warm orange emphasis, the light remap, the Korean type stack, the sidebar model, and every Afterglow-specific item are untouched.
- Translucency, blur, and Liquid Glass are explicitly out of scope and remain undecided.
