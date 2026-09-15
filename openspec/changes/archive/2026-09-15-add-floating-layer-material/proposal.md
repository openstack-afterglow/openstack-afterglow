## Why

The product owner approved adding a translucent material after the geometry and elevation work landed. Apple's own guidance scopes it tightly: `materials.md › Liquid Glass` confines the effect to "a distinct functional layer for controls and navigation elements ... that floats above the content layer", says plainly "Don't use Liquid Glass in the content layer", and directs authors to "use Liquid Glass effects sparingly".

Afterglow already carries translucency, but as scattered ad-hoc values: `Toast` and `BulkSelectionOverlay` each hardcode `blur(12px)`, the landing strip uses `1.125rem` and its proof note `0.75rem`, and three scrims use Tailwind `backdrop-blur-sm` — four radii, no shared vocabulary, and no accessibility guard anywhere.

## What Changes

- Add a material token family to `layout.css` and `tokens.ts`: `--material-chrome-alpha`, `--material-overlay-alpha` (both per-theme), and `--material-chrome-blur`, `--material-scrim-blur` (deliberately one value for both themes).
- Apply the chrome material to the application header only, on a negative-z `inset-0` child rather than the `<header>` element, because a non-`none` `backdrop-filter` makes an element a containing block and would trap the header's own popovers.
- Apply the overlay material to `BulkSelectionOverlay`, which already shipped the same dark alpha and blur with no light-theme value and no guard.
- Consolidate the full-viewport scrims of `Modal`, `CmdPalette`, `ConfirmDialog`, `EvacuateModal` and `RecoveryModal` onto one guarded blur.
- Make the opaque surface the base declaration and translucency the enhancement, so an unsupported browser, `prefers-reduced-transparency`, and `forced-colors` all fail safe; pin the source order in `designSystemRules`, because the three blocks carry equal specificity and a wrong order silently overrides the accommodation.
- Record in `DESIGN.md` both the adopted set and the surfaces excluded on evidence.

## Capabilities

### New Capabilities

- A token-backed material confined to the floating layer, with accessibility accommodations that fail safe.

### Modified Capabilities

- The header separates from scrolling content by depth rather than by a hard fill alone.
- Scrim blur becomes one shared value instead of four ad-hoc radii.

## Impact

- `layout.css`, `tokens.ts`, the header, five overlay/scrim components, the design-system tests, and `DESIGN.md` change.
- Source files change, so `ARCHITECTURE.md` requires a re-stamp.
- No palette change. No content-layer surface becomes translucent.
- The sidebar, the sub-`md` drawer, `ActionMenu`, `SlidePanel` panels, `ProjectSelector`, `Toast` and the landing surfaces are deliberately excluded; the reasons are recorded in `DESIGN.md` and in this change.
