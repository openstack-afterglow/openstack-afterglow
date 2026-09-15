## Why

Afterglow's `DESIGN.md` is an authoritative but inward-looking rulebook: it fixes tokens, primitives, layering, responsive tiers, and legacy debt, yet says little about the interaction quality those primitives are supposed to produce. Reviews therefore land on "which primitive" and rarely on "does this behave well". Apple's Human Interface Guidelines are the most complete public statement of that missing layer, and the `apple-design` skill (122 HIG pages pulled from developer.apple.com) makes them citable.

The requested direction is explicit: imitate Apple's UI/UX, not Apple's theme. A previous Apple-inspired pass changed the palette toward monochrome, was rejected by the product owner, and was reverted across seven commits. The value that remains is behavioural, and it has to be fenced so a future agent cannot read the same document as authorization for another palette shift.

## What Changes

- Add an Apple HIG-derived interaction layer to `DESIGN.md` covering feedback and alerts, modality and dismissal, data entry, action and error wording, navigation orientation, progressive disclosure, text scaling, motion restraint, pointer and keyboard affordances, destructive-action recovery, and chart legibility. Every added rule binds to an existing Afterglow primitive, token, or path.
- Add a named non-goal section to `DESIGN.md` recording what Apple material is deliberately excluded and why: palette and contrast-token changes, Liquid Glass and any translucency or blur material, the HIG's "no app-specific appearance switch" rule, SF Pro and SF Symbols as families, title-style capitalization, and mobile tab bars as top-level navigation.
- Correct the stale motion durations in `DESIGN.md` (`fast`, `base`, `panel`) to the values `layout.css` and `tokens.ts` actually ship.
- Install the `apple-design` skill locally so future design reviews can cite the guidelines from source rather than from memory.

## Capabilities

### New Capabilities

- A citable interaction-quality contract for new and materially changed frontend surfaces, expressed in the existing primitive and token vocabulary.
- An explicit, documented exclusion boundary that prevents Apple's visual system from being imported alongside its interaction patterns.

### Modified Capabilities

- `DESIGN.md` gains behavioural obligations alongside its existing structural ones; design review and `/design-review` gain a documented basis for interaction findings.

## Impact

- `DESIGN.md` changes. No frontend source, token, or test file changes in this change.
- `ARCHITECTURE.md` needs no fresh source stamp: `_is_excluded` in `scripts/check_architecture.py` excludes every root-level Markdown file except `AGENTS.md` and `CLAUDE.md`, so `DESIGN.md` is outside the source digest and `npm run docs:check` stays green.
- Existing `DESIGN.md` assertions in `frontend/src/routes/__tests__/designSystemRules.test.ts`, `frontend/src/lib/design/__tests__/typographyRoles.test.ts`, and `frontend/src/lib/components/landing/__tests__/LandingCapabilityComposition.test.ts` are `toContain` checks on sentences this change preserves verbatim.
- No palette, gradient, tone, or contrast-token value changes. Contrast problems are raised as findings, never resolved by editing a token in this change.
