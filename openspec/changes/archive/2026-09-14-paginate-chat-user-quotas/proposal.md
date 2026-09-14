## Why

The admin chat quota page drains every Keystone user page before rendering. Large installations therefore make multiple sequential identity requests and hold the entire user directory in browser memory even though an administrator only needs a bounded working set at once.

## What Changes

- Fetch one marker-based Keystone user page of 20 users at a time.
- Add previous/next navigation with the shared Pagination primitive and retain the current page during quota mutations.
- Reset pagination when the authenticated token or project scope changes.
- Clarify that the existing client-side name/email/ID search filters the current page.
- Join Lumen quota records only to the current Keystone page so users from later pages are not mislabeled as orphaned accounts.

## Capabilities

### New Capabilities

- Bounded, marker-based navigation through user quota rows.

### Modified Capabilities

- Admin user quota search operates on the currently loaded user page.

## Impact

The change is limited to the existing `/admin/chat/quotas` frontend route, focused frontend coverage, design/changelog documentation, and the architecture review marker. Backend routes, Keystone authorization, Lumen quota APIs, stored quota records, and deployment configuration remain unchanged.
