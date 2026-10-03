## Context

The admin hypervisor list/detail reports Nova `state` and `status` but offers no service control or whole-host relocation. Nova API microversion 2.53 exposes a hypervisor UUID separately from the `nova-compute` service UUID. Existing individual migration endpoints are admin-only; host-wide actions need stronger source ownership and state checks.

## Goals / Non-Goals

**Goals:** Explicit service enable/disable, whole-host migration for `up/disabled` and fencing-gated evacuation for `down`, truthful per-instance submission outcomes, and separation of physical liveness from scheduling status.

**Non-Goals:** Automatically moving VMs when disabling a host; forcing Nova `forced_down`, powering off/fencing a host, choosing a destination instead of Nova scheduling, guaranteeing that Nova's asynchronous relocation completed, or altering existing per-instance migration APIs.

## Decisions

- Resolve the Nova hypervisor UUID through `GET /os-hypervisors/{id}` with microversion 2.53 and verify the corresponding exact `nova-compute` service host/UUID from `GET /os-services` before changing status. A client-supplied service ID or binary is never accepted. Require a nonempty disable reason; do not alter host `state`.
- Create distinct admin-only `PUT /hypervisors/{id}/service` and `POST /hypervisors/{id}/relocate` operations; keep a separate confirmed UI control for each. Refresh the cached hypervisor list and selected detail after mutation.
- For relocation, re-read authoritative source state and status, traverse every all-tenant server page on the source, recheck current server host/state before dispatch, and report outcomes per VM. On `up/disabled`, request live migration for `ACTIVE` and cold migration for `SHUTOFF`, skipping unsupported states. On `down`, require `fenced=true` and request Nova evacuation for eligible instances, without forcing source down or using an unsafe shared-storage assumption.
- Treat Nova's accepted migration/evacuation request as `requested` (not `completed`); expose `failed`/`skipped` and reasons in the UI. Existing individual VM actions remain usable.

## Risks / Trade-offs

- A `down` heartbeat does not prove power isolation. Requiring administrator fencing acknowledgement prevents accidental one-click evacuation, but cannot independently prove physical fencing; operator procedure must do so.
- The source inventory can change during bulk dispatch. Per-server host/state rechecks reduce but do not eliminate races inside Nova; skipped/rejected items remain visible for operator retry. Dispatch is bounded/sequential rather than a burst of scheduler requests.
- Cold migration may enter Nova `VERIFY_RESIZE`; its completion requires the normal Nova confirmation workflow. A successful HTTP response never promises a moved or healthy VM.
