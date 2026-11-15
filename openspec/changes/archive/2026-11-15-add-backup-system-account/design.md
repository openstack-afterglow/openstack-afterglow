# Design

## Identity and secret lifecycle

The generated 64-character mixed-class password lives only in an AES-GCM envelope under the existing application encryption master key, with a distinct HKDF domain and cloud/domain/name-bound associated data. The durable Redis identity record shares the persistence/failover assumptions of the authoritative policy/journal store. No SQL migration or new operator secret is introduced. An operator-provisioned secret would require additional provisioning, distribution, rotation and outage coordination; the wholly system-owned identity permits bounded recovery using the existing fixed-admin identity authority instead.

Only an elected reconciler under its renewable execution lease may create, re-enable, repair options or reset the machine account. Password reset requires failed **unscoped** password proof; a project-scoped 401 only enters the existing fenced 300-second policy retry window and requests role reconciliation. The reset minimum interval is 900 seconds. Persist a new encrypted credential only after Keystone accepted it and a fresh unscoped authentication verified it. A crash between those steps leaves the old/missing Redis secret: the next leader detects failure and repairs it after the reset window. Native policy rejection uses fixed secret-free status codes, never native exception text.

Create/repair options `ignore_lockout_failure_attempts`, `ignore_password_expiry` and `ignore_change_password_upon_first_use` as true, and clear MFA rules. Native user ID is canonical; re-creation resolves the exact reserved name in the configured user domain and updates the encrypted identity record. Stored ID/native provenance distinguish the managed principal from a coincidentally named user. Direct Keystone mutations cannot be blocked; periodic reconciliation repairs deletion, disabled state, machine options and eligible direct role drift within one healthy cycle plus bounded backlog. Native outages, failed identity proof and password-reset backoff prevent guarantees of a fixed recovery deadline.

## Roles, personal spaces and grants

Needs are authoritative backup/snapshot policy records (enabled or paused), or active operation journals. Request markers are only scheduling hints. Grant only exact `(managed user ID, project ID, canonical global member role ID)` and read back. When no needs remain, wait 300 seconds, then re-read both registries immediately before revocation. Incomplete Redis/native inventory never authorizes deletion. Remove unexpected managed-user direct authority only through exact known assignments, never broad roles or other principals. Bound writes per cycle and rotate traversal to avoid starvation.

Personal authority must tolerate only this exact machine user's **direct**, non-group, non-inherited project `member` grant on that same project. Any extra role, domain/system/inherited/group assignment or unrelated user remains unexpected authority. Owner identity and sole-owner checks remain unchanged. Ordinary domain manager projection must not interpret the machine member as an owner or manager. Lists either expose the explicit system marker or omit the principal where selection is inappropriate.

## Quotas

The authoritative derived global capacity is `backup_gigabytes := 3 * gigabytes`; unlimited `-1` stays unlimited. All existing Afterglow volume-quota/default/enrollment writers enforce this pair, and project creation derives backup capacity from fresh native global disk quota even if no other volume default is configured. The reconciler corrects every existing native project's drift. Manual native backup-capacity edits are overwritten after activation. Typed `gigabytes_<type>` quotas are unchanged and do not add to the global quota. Backup COUNT (`backups`, currently 20 by default) is independent: capacity does not imply a safe count, so it remains unchanged. Retention tiers across volumes may exceed that count; operators must explicitly review/raise count quotas separately. No speculative count derivation is implemented.

## Execution and activation

Backup and snapshot creation share token ownership semantics and therefore use the same dedicated account factory. Eager native access proves both exact user and target-project token scope. Existing owner/source checks, no-replay submission, journals, leases, retention fences and the 300-second authentication backoff remain intact. Other `get_admin_connection_for_project` callers, including Trove, retain fixed-operator behavior.

The new reconciler is disabled by default. Its read-only CLI and administrator status/report expose intended account/options/role/quota writes and safe failures. Enable only after owner approval, protected Redis/key recovery, complete native inventory and the dry-run review. No production activation is performed by this work.
