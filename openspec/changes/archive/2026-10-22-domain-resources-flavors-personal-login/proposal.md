## Why

The requested administrator surfaces still present project-only ownership, domain-filter failures obscure complete inventory, public GPU flavors do not consistently respect the same admission rules as private flavors, Enter does not submit login, and existing administrators can land without a personal workspace.

## What Changes

- Replace overview project resource monitoring with domain-owned resource aggregation and drill-down.
- Correct all-instance domain/project inventory, full-query filtering and stable pagination; enrich hypervisor VM rows with domain/project/flavor.
- Add full-inventory domain volume counts/GiB and detailed domain/project/status/text/capacity filters, preserving selection and stale-response fences.
- Apply project compute/GPU quota eligibility to public and private flavors alike; private flavors additionally require Nova project access. Creation shows only usable flavors based on fresh same-host compute service state and CPU/RAM/GPU capacity, never cluster-summed headroom or guessed unknown capacity. Recheck before dispatch.
- Replace quota-driven private access reconciliation as authorization with native access semantics; add a domain selector for explicit project access selection. Nova has no native domain flavor grant; no synthetic inheritance or implicit future-project grant is introduced.
- Restore native form Enter submission with single-flight and IME protections.
- Ensure all supported human logins, including existing system administrators, land in their verified personal primary by default; expose opt-in last-workspace restore that freshly validates authority and falls back safely. Preserve identity and all existing grants/resources.
- Personal project default entitlement is 2 vCPU, 4096 MiB RAM and 1024 GiB Cinder disk quota, not a provisioned volume. Existing project convergence must be explicit and ownership/usage checked; no operational quota writes are executed during implementation.

## Capabilities

### New Capabilities

- Domain resource and volume summaries with exact native project attribution.
- User-controlled remembered-workspace landing, default personal.

### Modified Capabilities

- Administrator instance filtering and hypervisor VM ownership display.
- Native flavor visibility plus uniform quota and same-host create eligibility.
- Human personal provisioning and default quota policy.
- Keyboard login submission.

## Impact

Changes affect Afterglow backend APIs/services/models, administrator and login/account UI, all nine locale catalogs, focused tests and existing architecture/API/testing docs. Reuse existing native operation journals, unknown-write settlement fences, immutable identity, live system-admin/native ownership guards, auth ABA/session/logout protection and UI primitives. No sibling repository changes, production login/password replay, runtime restart, schema migration, IAM/credential mutation, deployment or commit/push is authorized by this implementation request. Tests and smoke use isolated public configuration, disposable datastores and synthetic native services. Source is not operational acceptance.
