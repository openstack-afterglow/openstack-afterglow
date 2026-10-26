## Why

Domain managers can enter IAM but cannot evict organization members or create projects from that surface; invitations allow only one project and monitoring/allocation are fragmented.

## What Changes

- Add current-domain membership eviction, never native account deletion, preserving foreign-domain access and resource ownership safeguards.
- Expose existing manager-authorized project creation without project_creator.
- Collect email first, then choose multiple project/role allocations in one invitation and apply/recover them through the existing enrollment journal.
- Consolidate domain resource observations, attribution, evidence-based forecasts and allocation editing.

## Capabilities

### New Capabilities
- Current-domain member eviction with complete preflight and explicit unknown outcome.
- One email invitation with multiple project allocations.

### Modified Capabilities
- Domain-manager project management and unified monitoring/allocation UI.


User clarification: eviction only clears current access for a mistakenly linked foreign-home account. Preserve existing SSO auto-join policy and pending invitations; either can re-admit the user later. This is not an admission ban, identity relink or account merge. Disclose this in confirmation/help/docs rather than adding a durable ban or invitation revocation.
## Impact

Fresh native authority and role graph lease remain mandatory. Accounts, resource objects, other domains, private configuration and existing concurrent changes are preserved. No production rollout or live native mutation is authorized. Current-domain home identities have intrinsic home membership, which cannot be removed without changing identity; surface that limitation rather than deleting/moving accounts. All supported locales, affected API contracts, documentation and local verification are in scope.
