## Why
The pre-deployment review found that pending result-boundary loads retain selectable old volumes and that ordinary upstream deletion errors expose raw diagnostics in bulk responses and activity records.

## What Changes
- Clear previous rows when a filter, page or identity boundary loads, while preserving same-boundary background refresh.
- Reject a bulk confirmation whose result boundary or identity changed before acceptance; prevent duplicate submissions.
- Sanitize shared deletion failures at their source and keep per-item continuation and admin authorization.
- Reproduce both boundaries, update the existing regressions and documentation, run the final gate, then archive.

## Capabilities
No new capability, route or schema. Correct safety boundaries of the existing admin bulk-delete contract.

## Impact
Admin volume route, its existing tests, architecture and API documentation. No live cloud volume deletion during verification.
