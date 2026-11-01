## Why

The resource chooser repeatedly loads domain/project inventory after browser navigation despite existing short-lived memory snapshots. Browser-session display reuse and authorized backend display caching should reduce repeated hydration without making cached membership authoritative.

## What Changes

- Extend the existing owner-fenced chooser display snapshots to bounded browser-session storage without storing credentials.
- Separate ordinary cached reads from explicit fresh refresh; preserve current display where revalidation can safely do so.
- Reuse backend cache conventions for expensive directory display data while retaining fresh native authority checks and mutation invalidation.
- Verify warm read call counts, refresh bypass, scope/login/permission isolation and late-response races.

## Capabilities

### New Capabilities
- `workspace-display-cache`: Bounded browser/backend display caching with fresh authority boundaries.

### Modified Capabilities

None.

## Impact

Frontend workspace controller, backend identity browse handlers and cache services, focused regression tests, architecture and cache documentation. No schema migration, deployment, credential TTL extension or authorization relaxation.
