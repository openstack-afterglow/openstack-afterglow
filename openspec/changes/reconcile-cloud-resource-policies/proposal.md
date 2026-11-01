## Why

The running local Afterglow backend uses an empty resource-policy table. Default compute-zone resolution fails before Placement access, so every VM flavor becomes unselectable even though an observed explicit `nova` zone permits 17 of 18 visible public shapes. Managed-flavor state is absent/disabled and native fleet capability currently returns HTTP 404. The user requests fixes and automatic reconciliation for fresh databases and drift after updates.

## What Changes

- Add lifecycle-owned, idempotent resource-policy reconciliation using the existing database authority, discovered native resources and dispatcher. Preserve every valid selected ID; refresh stale display names. Automatically initialize/repair only safe uniquely-discovered Compute/Cinder AZ defaults. For all other policy types validate and expose missing/stale/unavailable state without silently choosing a different network, project, builder flavor or share resource. Explicit manual clears must not be immediately undone; concurrent administrator writes must win over stale observations.
- On fresh DB/startup and later bounded periodic reconciliation, retry unavailable authority without discarding valid data or creating cloud resources. No startup synchronous native calls, no request-time implicit policy writes, no new configuration authority or schema migration.
- Distinguish default-AZ policy failure from actual host capacity failure in flavor eligibility, while remaining fail-closed for submission. Show existing blocked flavor inventory and actionable reasons in consumer/admin selectors rather than making the catalog appear absent.
- Expose disabled/no-run automation and native-readiness blockers clearly in administrator UI. Preserve manual-disable semantics and native fleet gating; never adopt or overwrite manual flavors. Finish reachable configuration recovery through the same reconciler rather than an ad hoc SQL write.
- Build and exercise changed backend/frontend containers using canonical local deployment with exact effective environment preservation. Native Nova fleet rollout is a separate operational safety boundary: inspect current prerequisites and obtain explicit approval for a system-wide deployment/cutover if needed rather than bypass checks.

## Capabilities

### New Capabilities

- Safe automatic AZ policy initialization and ongoing repair, with exact-ID preservation and concurrency fencing.

### Modified Capabilities


The user explicitly selected “Afterglow 수정·복구까지만”: Afterglow implementation/local recovery is approved; Nova production rollout, native quota cutover and managed flavor activation remain outside this change. Retain and report the native prerequisite rather than bypassing it.
- Resource-policy freshness/readiness and flavor failure diagnosis.
- Existing flavor inventory visibility independent of selection eligibility.
- Managed-flavor automation readiness visibility.

## Impact

- Backend policy storage/discovery, dispatcher lifecycle, flavor eligibility DTO, administrative status API, frontend flavor selector and automation panel, related contract/regression tests and operational documentation.
- Database remains the resource-policy authority. No cloud creates/deletes, IAM grants, arbitrary resource replacement, schema migration, key changes, or production rollout are implicit in startup reconciliation.
- Acceptance requires empty DB initialization, valid ID/name refresh, uniquely repairable stale AZ, ambiguous/failed discovery preservation, explicit-clear and concurrent-admin protection, complete flavor list visibility with disabled blocked choices, concrete failure reasons, and real runtime verification. Actual cloud automatic flavor publication cannot be claimed until native fleet capability and deployment acceptance are satisfied.
