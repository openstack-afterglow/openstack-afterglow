## Why

The supplied runtime logs show `/auth/domains` taking 4.4–4.5 seconds, duplicate overlapping domain reads, and `/auth/workspaces` taking 10.24 seconds after that wait. The chooser reloads the full domain directory before every project browse. Backend workspace assembly repeatedly opens service clients and reconstructs the same native role graph, membership and domain context within one read operation.

## What Changes

- Reuse the existing explicitly owned `NativeOperation` transport and read snapshot within each directory operation, including project membership and project-creator capability checks.
- Preserve a separate fresh final authority check before workspace publication; invalidate operation-local observations before it. Do not extend cross-request authority caches or trust JWT/display roles.
- Coalesce same-target chooser loads and avoid serial domain-list/project-list waits when the target is known. Browsing another already listed domain must not reload the entire domain directory. Explicit refresh still revalidates the directory.
- Preserve generation/login/scope/abort fences, non-mutating browse, uncertain-create fencing, and single explicit project/domain switch mutations.
- Extend the same operation ownership to explicit project/domain scope changes and refresh. Live debug logs show workspace selection taking 19.07 seconds, followed by `/auth/me` reads of 6.10 and 6.71 seconds.
- Inspect actual access/refresh, Redis session, native token and absolute login lifetimes. Diagnose unintended early logout and qualify rotation versus scope-transition concurrency. Preserve the configured absolute timeout, revocation, policy and origin checks; do not silently make the refresh JWT expiry the session policy.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

Workspace directory reads and chooser request orchestration become less redundant without changing the accessible-domain/project, role, preference, or session contracts.

## Impact

Backend authentication/domain/project authority helpers, chooser controller and behavioral regressions. No new endpoint, schema, dependency, configuration, role hierarchy, or deployment interface. Root architecture and existing authentication/testing documentation will record the read-lifetime boundary and qualification evidence. Qualification includes native SDK over HTTP with deterministic synthetic membership, compiled browser interaction, canonical affected multi-architecture images and isolated Compose runtime. Production changes and unrelated CORS/Drover errors are excluded; supplied slow logs are accepted as evidence, not rerun to reconfirm.
