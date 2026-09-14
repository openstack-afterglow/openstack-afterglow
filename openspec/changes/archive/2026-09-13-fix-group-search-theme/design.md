## Context

`GroupCard.svelte` already uses semantic surface and ink utilities for the group card, member rows, search field, result text, and borders. Its result and empty-state panels are the exception: both retain `style="background:#1a1f2e"`, and the populated panel also retains `bg-gray-850`. Inline `background` wins over theme utilities, so `:root.light` cannot remap the panel.

## Goals / Non-Goals

**Goals:**
- Make populated and empty member-search overlays derive their background from the active theme.
- Give active identifiers and member email metadata readable secondary contrast in both themes.
- Use shared Button variants for the add action and semantic danger styling for destructive actions.
- Reduce the legacy visual-debt allowance for every raw token removed from GroupCard.

**Non-Goals:**
- Redesign group management or introduce a new popover primitive.
- Change theme tokens, membership APIs, filtering rules, or responsive geometry.
- Migrate unrelated legacy styling outside `GroupCard.svelte`.

## Decisions

- Use `bg-surface-raised` for both result states. The design system assigns raised surfaces to popovers, and it maps to `#1c1d20` in dark mode and `#ffffff` in light mode. Reusing this token avoids a second component-specific theme branch.
- Remove both the inline background declaration and `bg-gray-850`. Keeping either would retain a non-semantic dark-only path or competing background declarations.
- Preserve `border-line-2`, semantic ink colors, and restrained popover shadow. Those already adapt through the shared theme and establish the required interactive boundary/elevation.
- Tighten `legacyVisualDebt.ts` rather than adding a source-text-only test. The existing visual-debt guard is the repository contract that prevents removed raw palette tokens from returning, while actual browser verification proves computed light/dark presentation.
- Use `text-ink-2` for active descriptions, identifiers, emails, loading/empty copy; reserve `text-ink-3` for disabled states as required by the design system.
- Use `Button variant="primary" size="sm"` for the result-row add action so warm fill, on-warm ink, hover, focus, and disabled states resolve from defined primitive CSS.
- Replace raw red classes on delete, remove, and error text with semantic danger CSS-variable utilities; keep their existing compact geometry and event handlers.

## Risks / Trade-offs

- [Risk] The light raised surface matches the white group-card surface closely. → Keep the stronger `border-line-2` boundary and restrained shadow already used by the overlay.
- [Risk] Removing a hard-coded color could alter dark mode slightly (`#1a1f2e` to `#1c1d20`). → Use the canonical raised-surface value intended for popovers; verify both themes in the browser.
