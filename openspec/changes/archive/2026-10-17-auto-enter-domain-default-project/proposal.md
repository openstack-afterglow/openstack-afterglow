## Why

Authenticated users currently reach an empty resource selector when their domain has no canonical `Default` project. Domain creation grants domain-management authority but not project ownership, and multi-domain membership forces an unrelated chooser even after the login domain was explicitly selected.

## What Changes

- Prepare a canonical `Default` project on the first authenticated login to an authorized domain when it is absent; reuse the existing native mutation lease, disabled staging, readbacks and quota policy.
- Give the creator of each newly created `Default` the native `project_owner` role. Give subsequent authorized domain members direct `project_reader` access without changing existing owners or other grants.
- Preserve the separate `manager` grant for the actual creator of a new domain, including personal domains created by enrollment. First login to a pre-existing domain does not invent a domain creator or grant manager.
- Exchange the real caller token into the selected domain's accessible project before issuing the browser session; enter that scoped project directly after password or configured provider login even when other domains are available.
- Reuse the current owner-controlled member role editor and explicit ownership transfer; do not introduce global role seeding, provider/domain-specific branches or ownership takeover.

## Capabilities

### New Capabilities

- `domain-project-onboarding`: Idempotent authenticated domain landing, first-login Default creation, creator ownership, participant reader membership, and domain-creator manager separation.

### Modified Capabilities

None. This capability supersedes the archived implementation's no-bootstrap-on-login behavior; current canonical spec inventory has no matching capability at proposal time.

## Impact

Backend authentication preparation, domain Default lifecycle, enrollment journaled provisioning, frontend post-login navigation and affected consumer tests. Public token DTOs and role-management APIs remain unchanged. No new DB schema, migration, provider registry, dependency or deployment topology is planned. Native canonical roles and their safe hierarchy remain explicit operator prerequisites; this change does not silently seed global roles or alter existing shared infrastructure.
