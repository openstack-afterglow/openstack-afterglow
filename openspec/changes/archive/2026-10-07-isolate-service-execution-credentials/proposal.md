## Why

Waygate scopes its service password to tenant projects, Palimpsest's image-export worker uses an equivalent fallback, and Drover creates durable manager users with tenant role assignments. These execution identities appear in project membership and can be independently removed. API role checks do not eliminate the background worker's independent authority. Lumen already uses caller authority for tenant requests and operator-owned credentials for its own infrastructure; that distinction must remain explicit.

## What Changes

- Keep each service identity in its service project. Do not create tenant role assignments, tenant manager users, or broad admin execution fallbacks.
- Admit tenant operations using the requester's current enabled identity, exact project and current native service capability. Use only a subset of current non-administrative OpenStack roles for execution.
- Use bounded, operation-owned Keystone Trusts for deferred tenant OpenStack operations. Persist only delegation references and scope metadata, never requester passwords or login tokens. Verify current actor authority before new cloud work; completion, rejection and abandoned admissions revoke delegations, with durable cleanup and finite expiry.
- Synchronous tenant OpenStack operations use caller-scoped least-privilege delegation with deterministic cleanup. System-admin authority is not permission to impersonate a tenant through the service password.
- Drover continuous autoscale and guest cloud plugins use separately owned, restricted user application credentials for the resource lifetime. This policy was explicitly selected by the user. Revocation or current authority loss stops new work. A currently authorized operator can replace the resource delegation or delete the resource using a fresh operation delegation; the original creator is not the permanent deletion authority.
- Retain Lumen provider credentials, operator-owned Nova infrastructure and machine callbacks, and Palimpsest local KVM/build/native-package credentials as separate execution domains. Remove unused tenant-admin escape hatches rather than injecting Trusts into unrelated execution.
- Make Waygate zero-disk flavor boot compatible with project-member execution using a volume-backed root disk, without broadening Nova policy or tenant roles.
- Preserve original-token package/BFF contracts, tenant resource ownership, project quotas, native capability checks, durable worker fencing and encrypted stored secrets.

## Capabilities

### New Capabilities

- `isolated-service-execution`: bounded tenant delegation without service membership, validated execution scope, explicit revocation and credential cleanup.
- `drover-resource-reauthorization`: restricted continuous resource authority and replacement by a currently authorized user without permanent creator dependence.

### Modified Capabilities

- Drover cluster, nodegroup, autoscale, callback, reconciliation and guest-plugin execution authority.
- Waygate gateway create/delete and network attach/detach execution authority and zero-disk boot path.
- Palimpsest deferred Glance image-export authority.
- Lumen's documented caller/operator credential separation and removal of unused tenant-password connection factory.

## Impact

The implementation spans the independent sibling repositories `/Users/pieroot/code/drover`, `/Users/pieroot/code/waygate`, `/Users/pieroot/code/lumen` and `/Users/pieroot/code/palimpsest`, plus Afterglow forwarding contracts if a current caller needs migration. Existing uncommitted work is preserved. Schema changes are additive and packaged migration ledgers remain immutable. Old queued operations without delegation do not acquire new authority through a service fallback; current authorized users must re-admit or reauthorize them. Existing persistent resources require explicit credential replacement before old tenant-manager assignments are retired.

Local tests and native SDK/HTTP smoke are required. Synthetic Keystone/cloud fixtures are not production evidence. No commits, publication, deployment, live Trust creation, tenant role removal, VM mutation or production migration is authorized by this code change. Operational cutover must separately qualify the exact release and cloud policy, then explicitly rotate existing resources and retire only verified-unused legacy assignments.
