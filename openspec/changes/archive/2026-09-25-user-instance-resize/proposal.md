## Why

The instance detail UI offers resize only to admins, although project members can manage their own instances. The existing flavor list evaluates full create demand rather than the resize delta, so quota-limited projects cannot correctly select an upgrade.

## What Changes

- Add project-owned instance resize, confirm, revert and resize-flavor eligibility routes under `/api/v1/instances/{id}`. Require project write authority and enforce instance ownership before mutation; retain admin routes for admin operations.
- Evaluate visible target flavors against incremental resource demand from the current flavor, while disallowing unchanged flavor and image-backed disk shrink (volume-backed instances may select a smaller flavor disk). Revalidate target eligibility on POST.
- In instance detail, expose resize and VERIFY_RESIZE actions in user mode; load instance-scoped eligible flavors and submit to owned endpoints. Preserve admin controls and the existing confirmation flow.
- Cover owner/reader boundaries, quota deltas, and UI mode/action behavior with regression tests; document API and architecture.

## Capabilities

### New Capabilities

- Project members can resize owned VMs and confirm or revert the resulting VERIFY_RESIZE state.
- Resize choices report eligibility for the incremental CPU, RAM, and GPU requirement.

### Modified Capabilities

- Instance detail resize actions target the project-owned API for user mode and the admin API in admin mode.

## Impact

FastAPI compute routes and quota evaluation, Svelte instance detail controller/header/modal, backend/frontend tests, and compute documentation. No schema change. Nova's resize still involves downtime and explicit confirmation or revert; live cloud verification depends on available credentials and a safe VM.
