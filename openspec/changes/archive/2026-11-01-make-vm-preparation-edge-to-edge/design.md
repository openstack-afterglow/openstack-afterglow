## Context

The existing authored glyph algorithm and shared analytic geometry already provide the requested visual scene. Framing originates in two owners: VmResourcePreparation adds a stage/title/help layout, while VmCreatePanel adds body padding and SlidePanel's close button occupies a normal-flow row. Current console appearance is ThemeSelect → theme/resolvedTheme → html.light; the app has no separate selectable accent preference.

## Goals / Non-Goals

**Goals:** Fill the actual preparation panel, retain its one accessible close action, preserve truthful dependency/error/retry semantics, and react to current semantic palette and light/dark updates even when animation is paused.

**Non-Goals:** Change output/afterglow-loading source assets, glyph geometry/noise/stream/water calculations, cloud APIs/authority, resource loading ownership, loaded wizard composition, deployment, or add a theme picker.

## Decisions

- VmCreatePanel owns the preparation-only unpadded surface. VmResourcePreparation fills its dimensions rather than using a viewport approximation or negative-margin card. Loaded/admin-project-selection paths retain their current padding.
- SlidePanel adds optional closePlacement=overlay; its default flow behavior is unchanged. The same labelled close button, Escape handling, focus containment/restoration and pointer close callback remain. The overlay is 44px and occupies no layout row.
- Heading/help remain screen-reader-only accessible name/description, not visible outside the artwork. Current pending status remains DOM text at the exact renderer analytic center. Error Alert/retry occupies a bounded scrollable lower region without moving the center or resizing the scene. No busy ancestor contains status/Alert.
- Existing artwork token names become semantic CSS colors referencing surface-canvas/accent/accent-2/ink-0/ink-2. Canvas caches those colors and the authored 32 opacity levels; globalAlpha preserves the exact original per-level opacity without assuming RGB-channel token syntax.
- One MutationObserver watches root class/style (the existing appearance/palette application boundary). It refreshes cached colors and redraws the current elapsed frame, without remounting the renderer, resetting elapsed time, issuing requests or starting RAF in reduced motion. Cleanup disconnects it alongside existing lifecycle observers. No computed style lookup occurs in draw/tick.

## Risks / Trade-offs

- Appearance must be observed in rendered mobile/tablet/desktop and short/zoomed surfaces; source tests cannot establish geometry or contrast acceptance. Main agent owns those checks.
- Inline root palette overrides must use the existing semantic tokens; no new user-facing accent setting is introduced. Source preview themes remain separate authored assets.
- Error details may exceed the lower scene region and intentionally scroll there, while close and centered status stay separate and reachable.
- Shared dirty source is preserved; this change does not qualify unrelated changes or production behavior.
