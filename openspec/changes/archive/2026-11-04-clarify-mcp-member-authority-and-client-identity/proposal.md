## Why

The screenshot presents a member's projects as cloud read-only while the key form is set to read. Native project authority and the explicit key/consent ceiling must be distinguishable. Client signatures already captured from MCP initialize are hidden behind a count-only collapsed summary, making connections hard to identify.

## What Changes

Verify native member management through current-project role checks, grant issuance and execution without weakening ownership, role ceilings or independent native service policy checks. Fix actual defects found; present project capability separately from selected key/consent access so a read-only key is not mistaken for a read-only member. Existing read grants remain read; unknown native service policy is not silently allowed. Keep Lumen excluded from MCP control.

Make existing sanitized client name/version/source visible on each connection without exposing raw client IDs, project IDs, bearer values or raw User-Agent. Preserve exact owner-scoped revoke, scope/refresh/ABA fences and truthful self-reported/unknown distinctions.

## Verification

Run focused backend and frontend behavior regressions, real local smoke for the changed path and desktop/mobile light/dark browser inspection. Review architecture/design/auth docs and archive. This request does not approve another production deployment, IAM mutation or version bump. Preserve concurrent checkout/index changes.
