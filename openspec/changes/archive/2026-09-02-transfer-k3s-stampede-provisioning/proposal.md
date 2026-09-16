## Why

Drover Stampede makes the correct Kubernetes capacity decision, but it currently submits Cinder and Nova operations itself. That bypasses Afterglow's intended authority for project-scoped GPU quota admission and leaves no durable cross-service record that resolves a retry after an uncertain OpenStack submission.

The preceding `centralize-k3s-gpu-provisioning` change closed the immediate admission bypass. This change completes the narrow Stampede scale-up handoff: Afterglow owns durable, idempotent VM submission while Drover retains Kubernetes demand, encrypted bootstrap material, Ready/GPU readiness, and drain/delete lifecycle.

## What Changes

- Add an Afterglow-owned durable K3s node provisioning intent with a unique Drover idempotency key, immutable non-secret server specification, submission state/error fields, and created OpenStack resource references.
- Expose machine-authenticated internal endpoints that create/query an intent and submit a one-time, in-memory cloud-init payload to its claimed intent. The persistent intent never stores the K3s node token, kubeconfig, or rendered bootstrap.
- On submit, claim the intent, run the existing effective GPU quota admission before any OpenStack mutation, create the required boot volume and Nova server through Afterglow-owned helpers, persist all resulting IDs, and make retries return the same recorded outcome rather than create another server.
- Make Drover Stampede create and submit an intent instead of directly calling Cinder/Nova. Drover retains its durable job, nodegroup VM record, bootstrap rendering, K3s readiness checks, and scale-down deletion.
- Preserve fail-closed behavior: unavailable/mismatched service credentials, invalid immutable payloads, exhausted GPU quota, foreign claims, ambiguous in-progress submissions, and opaque OpenStack failures produce explicit terminal or retryable intent states without a second resource submission.

## Capabilities

### New Capabilities

- `k3s-node-provisioning-intents`: A service-authenticated, durable and idempotent submission boundary for Drover-selected K3s Stampede agent nodes. It separates non-secret instance intent persistence from transient bootstrap delivery, records resource ownership, and enforces Afterglow GPU quota admission before Nova submission.

### Modified Capabilities

- `drover-stampede-resource-autoscaling`: Scale-up persists the selected-node identity before resource submission, delegates Cinder/Nova creation to Afterglow, and consumes the recorded server result for existing readiness tracking. It no longer invokes Cinder or Nova directly for Stampede agent scale-up.

## Impact

- Afterglow backend: database migration/model, internal K3s router/service, machine-authenticated status/submit endpoints, configuration/deployment secret rendering, and contract tests.
- Drover sibling checkout: Afterglow provisioning client, Stampede job payload/state transition, VM tracking update, Kolla service credentials, and focused tests.
- Excluded: cluster control-plane bootstrap, HA control-plane joiners, Octavia/Neutron cluster topology creation, public tenant APIs, user VM creation, and Drover scale-down. Those remain Drover-owned lifecycle concerns.
