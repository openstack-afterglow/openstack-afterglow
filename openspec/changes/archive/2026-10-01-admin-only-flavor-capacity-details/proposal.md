## Why

The consumer VM creation wizard repeats per-host VM CPU/RAM ceilings and NUMA/Nova scheduler diagnostics under every flavor. These are operator details, not the selected VM's specifications, and the user requested that they appear only in administrator pages.

## What Changes

- Pass the existing `VmCreatePanel.adminMode` presentation context to `SelectFlavor`; default to the consumer view. Administrator identity alone does not enable details in `/dashboard`.
- Render per-host CPU/RAM ceilings, candidate-host counts, NUMA/GPU-affinity diagnostics and Nova snapshot caveats only in the administrator view, for both responsive lists and the selected-flavor panel.
- Use concise availability/freshness explanations in the consumer view while retaining flavor specifications, project/GPU quotas, disabled reasons, refresh controls and current selection behavior.
- Preserve the capacity API, same-host evaluation, fail-closed admission, polling and all generation/request fences.

## Capabilities

### New Capabilities

None; no new route or permission boundary.

### Modified Capabilities

- VM flavor selection separates consumer-facing specifications and availability from administrator-only operational capacity details.

## Impact

Frontend-only presentation change in `VmCreatePanel.svelte` and `SelectFlavor.svelte`, related regression tests and existing architecture/design/API documentation. No backend, API response, AZ policy, deployment topology or datastore changes. Hiding these values in the UI is not API-level redaction. Consumer and administrator creation remain blocked on insufficient or unavailable capacity.
