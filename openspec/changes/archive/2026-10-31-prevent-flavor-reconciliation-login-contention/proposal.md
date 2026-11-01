## Why

Password and provider login fail HTTP409 before session creation because domain_iam._iam_write immediately rejects the shared IAM graph lease. Current managed_flavors.reconcile holds that same renewable lease across inventory discovery and the entire multi-flavor pass. User-provided callback diagnostic reaches domain_auth.complete_authorization -> _iam_write -> identity_roles._graph_lock, matching retained runtime evidence. CORS preflight and provider authorization are200.

## What Changes

- Keep the existing identity endpoint graph lease, ownership checks, renewal, graph-before-SQL ordering and provider completion shields. Add a bounded FIFO wait for foreground _iam_write callers; ordinary direct graph mutations remain fail-fast. Pending foreground callers are expiring Redis sorted-set entries, not credentials or persistent work. Queue/cancel/timeout/store failure must not delete or steal another owner's lease.
- Managed flavor reconciliation checks foreground demand only between settled work units; it saves an idle/partial diagnostic and releases the lease instead of running the whole remaining batch ahead of login. No mid-write cancellation, blind native replay, stale state continuation or global graph-lock removal.
- Observe read-only supported hardware before taking the graph lease; merge against the latest policy under lease. Keep all native publication, claim/intents/ACL changes, policy merge, revision fencing and exact readback under the original lease. Unknown native effects remain non-replayable.
- Existing password/SSO verification, canonical identity/admission, personal project provisioning and session issuance stay intact. Add deterministic contention/fairness/failure/cancellation regression and actual HTTP smoke.

## Capabilities

### New Capabilities
None; this repairs foreground availability under cooperating background reconciliation.

### Modified Capabilities
Existing IAM mutation serialization and managed-flavor reconciliation scheduling. Existing native flavor identities/history/quota and automation opt-in are preserved.

## Impact

Source: identity_roles.py, domain_iam.py, managed_flavors.py, flavor_automation_policy.py and focused tests; ARCHITECTURE.md/docs/testing.md/CHANGELOG.md. No schema/config/dependency or native quota change. Redis queue is ephemeral and uses the existing store. Old writers do not cooperatively yield, so an all-writer source cutover is required for this availability guarantee; no claim of cross-store/native atomicity. No global cleanup, account changes, forced unlock, automation disable or implicit production deployment. Preserve current shared dev/index and actual runtime env/config/keys/mounts.