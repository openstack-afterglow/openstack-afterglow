## Why

Project compute policy is currently split across Nova compute quotas, Afterglow GPU quotas, and per-flavor Nova access grants. The user flavor catalog only removes GPU flavors whose effective limit is zero; it does not account for current GPU use, requested GPU count, remaining instances, vCPU, or RAM. The VM wizard therefore claims to show creatable flavors while still allowing selections that cannot be admitted, and administrators must coordinate multiple screens manually.

## What Changes

- Add one backend flavor-eligibility evaluator that derives flavor resource demand and compares it with project-scoped Nova instance/vCPU/RAM quota and Afterglow GPU quota usage.
- Return explicit selectable state, requirements, remaining quota, and stable blocker codes with flavor options. Use the same evaluator immediately before mutation so UI and admission cannot drift.
- Keep Nova Flavor Access as the coarse authorization boundary. Add an explicit quota-managed access mode for private GPU flavors and an idempotent admin reconciliation operation that derives grants from configured effective GPU limits, with dry-run/drift reporting.
- Make the project quota administration surface a unified compute-policy workflow with effective quota, GPU limits, and managed-flavor preview rather than independent immediate writes.
- Show selectable flavors by default and retain blocked flavors in a separate view with concrete quota reasons on mobile, tablet, and desktop.
- Migrate ordinary VM creation, administrator target-project creation, resize, and K3s flavor selectors to project- and intent-aware eligibility contracts.
- Correct storage semantics: flavor local disk is not compared to Cinder gigabyte quota; volume eligibility uses the actual requested boot/additional volume demand.
- Add short-lived GPU admission reservations so concurrent Afterglow admissions cannot all consume the same observed remaining GPU quota.

Private Flavor Access and Afterglow reservations do not create a cloud-wide aggregate GPU quota for direct Nova clients. A project that already has access to a private flavor can create through Nova without passing Afterglow's admission service. Reservations protect Afterglow-controlled admissions only. Cloud-wide hard enforcement therefore requires either routing every creation path through Afterglow or adding Nova-side quota enforcement. This change preserves and clearly reports that boundary rather than claiming private access alone is a hard quota.

## Capabilities

### New Capabilities

- Project- and intent-aware flavor eligibility with structured quota blockers.
- Quota-managed private GPU flavor access reconciliation and drift preview.
- Afterglow GPU admission reservations for concurrent request safety.
- Unified project compute-policy administration and blocked-flavor explanation.

### Modified Capabilities

- Flavor discovery returns current project eligibility rather than only static access plus non-zero GPU limits.
- VM, admin target-project, resize, and K3s creation flows consume the shared eligibility decision.
- Project quota and GPU quota administration uses one staged apply flow while retaining Nova and Afterglow as their respective authorities.

## Impact

- Backend compute models, flavor routes, instance admission, admin quota/flavor APIs, GPU quota persistence, cache invalidation, and focused tests change.
- Frontend flavor types, VM creation store/picker, admin quota controller/components, resize selectors, K3s selectors, and responsive tests change.
- A forward-only database migration is required for GPU reservations.
- Existing private flavor grants remain manual until an administrator explicitly marks a flavor quota-managed and applies reconciliation. Public and special-purpose private flavors are not migrated implicitly.
- Direct Nova/API clients remain governed by Nova Flavor Access and Nova native compute quotas, but not by Afterglow aggregate GPU reservations; operations documentation and UI diagnostics must state this enforcement boundary.
