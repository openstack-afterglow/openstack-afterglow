## Context

`domain_projects.ensure_login_access` returns without mutation if no canonical Default exists. `_bootstrap` stages a disabled project, grants manager and reader, verifies projection and quotas, and then enables it, but does not grant ownership. Enrollment has a separate durable intent/journal path for personal-domain provisioning. `_prepare_domain_session` retains legacy selections and does not consistently refresh Default after a mutation without a NativeOperation. Frontend `loginDestination` prioritizes the domain chooser over an already server-scoped project.

## Goals / Non-Goals

**Goals:** One canonical Default per authorized domain; creator project ownership; reader membership for later participants; manager authority only for actual new-domain creators; automatic entry into the chosen domain's real native project; unchanged owner-managed member-role and transfer policies.

**Non-Goals:** Global role/inference seeding, retroactive takeover of existing Default projects, assigning manager to a first login in a pre-existing domain, provider/host/domain special cases, production infrastructure mutation, schema or token DTO changes.

## Decisions

1. Login is an explicit provisioning boundary, unlike directory reads. After password/provider policy and native subject checks, `ensure_login_access` may bootstrap an absent Default under the existing shared native role-graph lease. It rechecks membership and absence inside the lease, so a concurrent login reuses the newly created project and receives only reader. Existing `Default` lookup remains read-only and fail-closed for ambiguous, wrong-case, disabled or foreign data.
2. Separate project creator from domain creator. Every newly created Default grants the exact canonical safe `project_owner` plus direct baseline reader. Only create-domain, personal-domain enrollment and the explicit administrator bootstrap workflow grant manager. A first login to an existing domain grants ownership of the newly created project, not ownership/management of the domain. Existing Default projects are reused without auto-owner adoption.
3. Reuse exact-created-resource disabled staging and native unique-owner readback helpers. Verify owner, reader, optional manager, quotas and manager projection before activation. On known failure clean up only exact operation-owned resources; never retry ambiguous creates or delete by name. Enrollment adds owner through the existing durable per-role grant intent rather than bypassing its recovery journal.
4. Auth preparation uses the real caller token, refreshes observations after provisioning, and exchanges exactly the final chosen project. Explicit requested project choices remain authorized; ordinary domain login defaults to canonical Default. No blank/foreign native scope is manufactured, and failed setup issues no browser session. Retain a true no-write fast path for already-current membership/projection.
5. Fresh password and configured-provider login use the server-selected working domain and scoped project as destination even if additional domains are available. The existing resource selector stays available for deliberate later switching. Do not substitute `default_project_id` for a missing native project scope merely to claim readiness. Invitation/consent continuations keep their existing precedence.
6. Existing project_owner/project_admin member-role APIs remain authoritative. Owner can delegate ordinary project/service roles; reader cannot. The UI consumes the server-filtered grantable catalog and its `is_owner` subject flag, not `can_manage_owners` (which is deliberately false for generic editing because ownership transfer is separate). Drop the misleading modal prop at every caller. Domain-manager and explicit ownership-transfer/last-owner boundaries are not relaxed.

## Risks / Trade-offs

- First authorized login claims the newly created Default's project ownership in a legacy domain by user request. It must never claim an already-existing project or grant manager. Native membership, active user/domain and in-lease checks constrain this boundary.
- Login now depends on canonical project owner hierarchy and quota availability when provisioning. Fail closed instead of auto-seeding roles or returning a projectless success. Existing unchanged membership avoids writes.
- External native mutations do not honor the local lease. Exact-ID/readback checks and ambiguity failure remain required; a native creation conflict is not automatically replayed.
- The manager role remains the existing grant on Default that the application treats as domain authority; project_owner must not imply manager/admin.
- No schema change is needed. Existing writers can read the new assignments, but old writers keep their previous no-bootstrap/no-owner behavior. Production mixed-version and real-user acceptance require separately authorized rollout and native IAM evidence; local synthetic evidence is not production qualification.
