## Why

The desktop header already presents the active application mode while using the same control to navigate to the opposite mode. Below the desktop breakpoint, the sidebar footer instead presents the destination mode, so the same state appears differently across responsive layouts.

## What Changes

- Show `사용자 모드` with the user icon in the dashboard sidebar footer.
- Show `관리자 모드` with the shield icon in the admin sidebar footer.
- Preserve the existing opposite-mode destinations: dashboard to `/admin`, admin to `/dashboard`.
- Add accessible labels and titles that distinguish the current mode from the navigation action.
- Verify the mode indicator at mobile, tablet, and desktop breakpoint boundaries.

## Capabilities

### New Capabilities

- Consistent current-mode indication across desktop header and responsive sidebar layouts.

### Modified Capabilities

- None.

## Impact

The change is limited to the shared dashboard/admin sidebars, focused frontend coverage, changelog/OpenSpec bookkeeping, and the required no-structure-impact architecture review. Authorization, routes, API contracts, tokens, project selection, and responsive breakpoints remain unchanged.
