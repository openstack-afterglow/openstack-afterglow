## Why

The admin group member-search result panel keeps a hard-coded dark background in light mode, producing dark-on-dark text and controls with poor readability. The panel must follow the active semantic theme like the surrounding search field and group card.

## What Changes

- Replace the member-search result and empty-state hard-coded dark background with the shared raised-surface theme token.
- Promote active group metadata and member email text from disabled-only ink, migrate destructive controls to semantic danger styling, and render the add action with the shared Button primitive.
- Preserve the existing search, filtering, add-member, overflow, and dark-mode behavior.
- Tighten the visual-debt baseline so the removed raw color cannot silently return.
- Verify readable result content in both light and dark themes.

## Capabilities

### New Capabilities

- `admin-group-member-search-theme`: Theme-aware presentation requirements for the admin group member-search result panel and empty state.

### Modified Capabilities

- None.

## Impact

The change is limited to `frontend/src/lib/components/admin/groups/GroupCard.svelte`, its visual-debt contract, focused verification, changelog, and architecture review metadata. APIs, group membership behavior, theme tokens, routes, and responsive layout remain unchanged.
