## Why

Administrators need a clear domain GPU ceiling, while domain managers need project GPU caps and a traceable way to request additional capacity. Existing source has shared pool/cap controls but no GPU quota-request workflow.

## What Changes

- Reuse the existing administrator domain pool and exact-domain manager project cap, rather than introduce a second quota authority.
- Add a durable, project-specific GPU increase request with authenticated current-domain scoping and exact approved GPU primary-resource identity.
- A system administrator reviews the request and manually changes existing pool/project limits. Mark fulfilled only after fresh native-policy readback proves the requested target; rejection records the decision without changing quotas. The selected user choice explicitly excludes automatic approval-based quota mutation.
- Show request history to the domain manager and a cross-domain review queue to system administrators, with bounded paging, proper authority/session fences, no automatic replay, and honest unknown/error states.
- Add an additive SQL migration and document schema-before-writer and shared DB deployment limits; no production migration, activation or deployment is authorized.

## Capabilities

### New Capabilities
- Domain-manager GPU quota increase requests and manual administrator review.

### Modified Capabilities
- Existing domain GPU pool and per-project ceiling discoverability in administrator/IAM screens.

## Impact

- FastAPI authorization and readback, durable SQL request table, frontend admin/IAM controls and localization, endpoint/regression tests, architecture and operational documentation. Existing Nova quotas, Placement allocation and project pool policy remain authoritative.
