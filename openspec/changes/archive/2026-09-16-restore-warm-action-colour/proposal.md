## Why

A five-lens Apple HIG review across nine surface clusters produced 69 source-verified findings — 27 Critical, 28 High, 14 Medium. The most consequential is that the product's warm accent, which the owner asked to preserve, was not rendering at all.

Tailwind 4 generates a utility only from a `--color-*` name declared inside `@theme`. `--color-action-warm` and `--color-action-warm-hover` were declared nowhere; `--color-action-on-warm` and `--color-action-on-accent` were declared in `:root`, which is too late. Verified against the built stylesheet and in the running app: `.bg-action-warm`, `.text-action-warm`, `.border-action-warm` and `.text-action-on-warm` produced no rule, `bg-action-warm` computed to `rgba(0,0,0,0)`, and roughly 1,200 class occurrences across 262 files rendered nothing. `Tabs.svelte` compounded it — an invalid `var()` substitution left the selected tab's underline falling back to `currentColor`, painting it near-white instead of brand orange.

## What Changes

- Move `--color-action-warm`, `--color-action-warm-hover`, `--color-action-on-warm` and `--color-action-on-accent` into `@theme static`, so the utilities generate. `--color-action-warm` aliases `--color-warm`, so no new hue enters the system and the existing light remap applies for free.
- Split fill from text rather than sharing one key. Warm as text on a light surface is 3.56:1, below AA, while warm as a fill under `--color-action-on-warm` is 4.94:1 and passes. Fills and borders keep `action-warm`; the 422 `text-action-warm` occurrences across 167 files move to `text-warm-text`, which is 5.18:1 in light and 8.18:1 in dark.
- Add `--color-warm-text-hover`, derived with the same `color-mix` toward `--color-ink-0` that `.btn-primary:hover` already uses, so the hover shifts in the direction that preserves contrast in each theme.
- Give `--focus-ring` a light counterpart. Its only visible band was `--color-line-2` #cbd5e1 on white at 1.48:1, against the 3:1 WCAG 1.4.11 requires of a non-text indicator; it now uses `--color-ink-2` at 7.58:1. The dark definition is untouched.

## Capabilities

### Modified Capabilities

- The warm accent renders on every surface that asks for it: selected range and interval toggles, the mode chip, chart legends, progress fills, primary panel actions, and the selected tab underline.
- Keyboard focus is visible in light mode.

## Impact

- `frontend/src/routes/layout.css` and 167 component and route files change; the change to those 167 is a class-name substitution only.
- No new hue is introduced and no palette value is redesigned. `--color-action-warm` resolves to the existing `--color-warm`.
- Source files change, so `ARCHITECTURE.md` requires a re-stamp.
- The remaining 25 Critical findings from the review are not addressed here.
