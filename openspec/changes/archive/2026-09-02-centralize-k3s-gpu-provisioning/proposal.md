## Why

Drover's K3s Stampede controller correctly owns Kubernetes-specific capacity decisions, but its scale-up worker currently reads GPU flavor metadata and creates GPU-capable Nova servers with no Afterglow GPU admission. This can bypass the project GPU quota authority restored in Afterglow and duplicates PCI alias classification.

The complete transfer of K3s VM provisioning requires a separate durable service-to-service provisioning workflow because Drover still owns encrypted K3s bootstrap material, node readiness, and drain lifecycle. This change closes the immediate admission bypass without changing those lifecycle boundaries.

## What Changes

- Add a fail-closed, service-authenticated Afterglow GPU admission endpoint for K3s capacity workers. The endpoint receives a project ID and a flavor identifier, resolves the flavor with an administrative project connection, and runs the existing canonical Afterglow GPU quota admission check.
- Add a dedicated shared service credential configuration with secret-only deployment rendering. The endpoint accepts only a constant-time matching internal credential and never falls back to a user token or an unavailable quota authority.
- Make Drover Stampede call the Afterglow admission endpoint before it persists or performs a GPU scale-up. A denied or unavailable admission records an explicit blocked reason and creates no VM.
- Keep Drover's Kubernetes pod observation, nodegroup selection, durable jobs, readiness check, and cordon/drain lifecycle unchanged. Keep Nova/Placement as the final VM placement authority.
- Replace Drover's local PCI alias GPU guess with the admission authority for policy decisions; retain its capacity estimate only for K3s bin-packing and correct it to exclude known non-GPU PCI aliases.

## Capabilities

### New Capabilities

- `k3s-gpu-admission`: A fail-closed internal contract that admits or rejects a K3s nodegroup GPU flavor under Afterglow's effective project quota policy before Drover schedules VM provisioning.

### Modified Capabilities

- `drover-stampede-resource-autoscaling`: GPU nodegroup scale-up is blocked before job enqueue when Afterglow denies the project quota or the admission service is unavailable.

## Impact

- Afterglow: internal API/authentication dependency, configuration, deployment secret rendering, and contract/unit tests.
- Drover sibling checkout: settings/client, Stampede admission call and blocked-state behavior, PCI classification correction, and focused tests.
- No public tenant API shape, existing K3s nodegroup behavior, quota data migration, or production deployment is changed by this source change.
