## Why

Users request automatic renewal past OAuth grant expiry with no authority expansion. Existing finite grants were explicitly approved until a displayed deadline and use equally expiring restricted Keystone credentials; they cannot be silently extended or replaced using restricted token authority. User chose one fresh owner consent for existing connections.

## What Changes

Offer explicit ongoing, revocable OAuth authorization at fresh human consent; preserve finite legacy approvals. Keep exact issued projects/scopes/role-ID/name ceilings and current authority revalidation; OAuth access remains short-lived with rotating refresh. Existing approvals must reconnect and re-consent once; no retrospective extension, administrator fallback or trust escalation. Native non-expiring credential permission remains fail-closed and operational rollout separately authorized. Detailed cross-layer contract in local://mcp-renewal-contract.md.

## Capabilities

### Modified Capabilities
- Explicit ongoing OAuth approval, restricted Keystone authority and token rotation lifecycle.

## Impact

MCP OAuth backend, additive database migration, authenticated consent and docs/tests; preserves personal-token and internal Lumen scope, no live cloud changes or deployment. Current-source authority and revocation, legacy compatibility, failure/race behavior and actual isolated SDK/DB verification are mandatory.
