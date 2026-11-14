# Scheduled recovery-point authentication failures

## Why

The live DMSLAB automatic-backup policy cannot authenticate its configured service account to the target project and repeats Unauthorized warnings every 15 seconds. Tenant-visible policy state does not record that failure. An admin-project executor would create recovery points under the wrong owner, so authorization must not be bypassed merely to hide the incident.

## What Changes

Preserve exact target-project authentication for Cinder backup and snapshot creation. Add a shared Redis failure window per project/volume/recovery-point lane, with a 300-second retry delay and one bounded warning per window. Preserve policies, due events, submission fences and unknown operations. Do not grant roles, create trusts, change ordinary credentials, alter mail execution or write to production.

The original fixed-admin proposal is unsafe for creation. Cinder stable/2025.2 `cinder/backup/api.py:API.create` assigns the backup's project from `context.project_id`; `cinder/api/openstack/wsgi.py` rejects a URL project different from the token's project. An operator target binding cannot change that identity. The default factory therefore authenticates the real target and proves its native token scope, explicitly rejecting usage-operator bindings. A returned recovery point must also pass target owner/source identity checks before it can be recorded as accepted.

Upstream evidence: https://github.com/openstack/cinder/blob/stable/2025.2/cinder/backup/api.py and https://github.com/openstack/cinder/blob/stable/2025.2/cinder/api/openstack/wsgi.py . Fake Cinder tests stamp both backup and snapshot owners from the token, never from the requested source owner.

## Production evidence and remaining authorization decision

The coordinator's read-only observation on 2026-11-14 22:37–22:38 UTC found one configured auto-backup policy. Target project `06020453ded64757b552591d8c557ec3` (DMSLAB) exists and is enabled, domain `3de8d34d778e423ab7a92a4992378583`. The project's four direct role assignments belong to its human owner or manager group; the Afterglow service account has no target assignment. Current controller1 Unauthorized warnings still occurred every approximately 15 seconds. This is a live policy, not proof of a deleted/disabled project. No production policy was removed or disabled.

The safe scope of this change is failure containment, not restored DMSLAB backup execution. The owner must choose an explicit authorization mechanism:

- Operator-managed per-project service role: native target-project tokens and tenant-owned recovery points work without impersonation. Grant only for approved projects. Registration/removal needs explicit operator authority and lifecycle ownership; disabling one policy must not revoke a role needed by other policies or services. No blanket grant or automatic grant/revoke is added here.
- Project-owner/admin-created Keystone trust: delegated role and exact project can bound execution without storing a human password. This requires trust issuance, non-impersonating identity semantics, encrypted trust lifecycle storage, revocation/rotation and native policy qualification. It is not a factory-only change and is not added here.

Until that decision is approved and configured, DMSLAB scheduled backups remain unable to run. Authentication errors alone do not prove a deleted project or justify destroying its policy/history. Users can explicitly remove stale policies through existing policy APIs; active unknown journals remain non-replayable.

## Failure window and visibility

Use Redis `<lane>:retry:<project>:<volume>` with a UTC retry timestamp and 300-second TTL only when target connection construction/scope authentication raises Keystone Unauthorized or Forbidden. Leader scans and assigned workers honor the shared window, including handoff. Under the live volume lease, one Lua compare-and-set checks the exact original policy bytes (including revision), writes existing `last_status="error"` / `last_error` fields with the fixed secret-free message `Scheduled protection cannot authenticate to this project; operator authorization is required.`, and creates the retry key only if absent. Concurrent edit/disable/removal or lost lease rejects the update. The first accepted write emits one warning naming the lane and project (`project_id` field), exception type and retry duration, with `check whether service account has no role in project`; this is diagnostic guidance, not proof that every denial means missing roles. The warning contains no volume ID, native exception message, URL, response body or credential. Other volumes continue. After 300 seconds a persistent authentication denial creates one new window/warning. Successful cycles replace the error through normal result handling or a lease/revision-fenced clear; a deferred unsubmitted slot returns to `never` (or `unknown` for existing run history), never fake success. Cinder volume/read/reconcile/transient errors retain existing handling and are not delayed by this authentication window. Unknown writes are never resubmitted. Redis failure remains a coordination failure. Mixed-version old workers do not honor the window.

`VolumeBackupPolicies.svelte` already renders `last_error` as a danger Alert on desktop and mobile and translates `last_status` through existing `autoPolicy.status.*` keys. No frontend or locale change is required to make this fixed backend diagnostic visible. This is source inspection, not a new browser acceptance claim.

Compared with the reported 232 warnings/hour, persistent failure is bounded to approximately 12 warnings/hour per volume/lane (one attempt per 300 seconds, plus scheduling jitter). This is a source/fake-clock bound, not a new production measurement. Unknown accepted writes are observed only, never resubmitted.

## Flavor discovery investigation (read-only)

`flavor_discovery.discovery_loop` already authenticates the fixed admin project; this is not tenant password rescoping. The loop waits 10 seconds after each refresh. `_observe` parses distinct shapes, reads host facts and provider roots, then reads allocation candidates and CPU/RAM inventories sequentially under a shared 15-second deadline. It warns if any shape fails or the deadline leaves shapes unattempted. `_failure_reason` separates deadline, timeout, transport, rejected native observation and unexpected exceptions; the warning includes stage/count/status metadata. A roughly four-second refresh plus the fixed ten-second sleep is consistent with a fourteen-second warning cadence, but source alone cannot establish that timing or identify the two failed native shapes. Native non-2xx, invalid Placement resource classes/shape responses, inventory errors and deadline exhaustion remain distinct possibilities. No clear same-family bug is demonstrated. Follow-up requires the existing structured `failures`/`shapes_skipped` metadata and read-only matching Nova/Placement responses, without weakening fail-closed capacity semantics or hiding warnings.

## Residual risks

No role/trust, deployment, native Cinder backup repository, guest consistency or restore acceptance is proven. Read-only fixed-admin target filters depend on native policy honoring list scope: filtered/foreign-only lists do not prove absence, as documented for `layer_build._layer_resource`. This change introduces no admin list executor. Redis primary/DB sharing and TTL continuity remain prerequisites. Only target-authentication recovery can be delayed up to 300 seconds; native Cinder reconciliation keeps its existing cadence and unknown-write fences. There is no schema migration or new secret/configuration key.
