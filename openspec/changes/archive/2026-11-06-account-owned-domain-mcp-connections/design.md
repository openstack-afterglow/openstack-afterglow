## Context
The existing delegated-grant database stores exact user and issuance-project ownership. Both account list queries incorrectly reuse the issuance-project filter for discovery. Caller membership and independent project connection validation already enforce one working domain for multiselect issuance.

## Goals / Non-Goals
**Goals:** Own connection inventory is visible from any workspace; original ownership drives revoke/cleanup; account listing is usable with authenticated identity but no selected workspace; saved scope stays visible.
**Non-Goals:** Domain-wide sharing across users, widening existing grants, native role changes, schema migration, credential renewal, release or deployment.

## Decisions
- Select account inventory by exact authenticated user only. Keep execution, owner serialization locks, credentials, quotas and Lumen selections on their original strict project boundaries.
- Include owner_project_id and owner_project_name, deriving names from saved approved project snapshots with exact ID fallback. No invented historical domain label or DB backfill.
- Resolve a revocation target's original project from an exact-user-owned database row before invoking existing lock/audit/cleanup. Never accept a caller-supplied issuance origin.
- Split UI list availability from workspace-dependent creation and preview. Preserve synchronous identity/logout/ABA fences and one-time secret clearing.
- Retain existing same-domain membership filtering and fresh independently validated project tokens for OAuth selected/all-project scopes.

## Risks / Trade-offs
- Origin snapshots can retain an old project name; they are historical display, not native authority.
- Cross-project native credential cleanup may fail under current native policy; local revocation must remain durable and cleanup pending, not silently broaden native authority.
- Account-wide visibility must never expose another user's credentials, even in the same domain.
- Additive response fields require matching UI/API qualification but no database rollout. Existing writers/readers retain the same schema and runtime checks.
