## Why

The desktop header mode control currently labels the destination surface, so an administrator on a normal dashboard sees “관리자 모드” and an administrator inside `/admin` sees “사용자 모드”. The requested contract is to show the current route mode while preserving the control as a link to the opposite surface.

## What Changes

- Show a user icon and `사용자 모드` on non-admin app routes.
- Show a shield icon and `관리자 모드` on `/admin` and its descendants.
- Keep the existing opposite-surface href and visual tones.
- Add accessible labels and titles that distinguish current state from the navigation action.

## Capabilities

### New Capabilities
- Route-derived current-mode indication in the desktop application header.

### Modified Capabilities
- None.

## Impact

Only the shared desktop header markup in `frontend/src/routes/+layout.svelte`, changelog, OpenSpec bookkeeping, and architecture review marker change. Mobile drawer navigation, authorization, routes, APIs, tokens, and breakpoints remain unchanged.
