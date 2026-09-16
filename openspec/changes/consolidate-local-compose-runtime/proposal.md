## Why

The development machine has two Afterglow Compose projects. The familiar localhost:3080/8000 stack still discovers an older remote Lumen, while the current-source local stack uses alternate ports. The user explicitly requests removal of obsolete Afterglow containers/images and a single working local deployment. Dashboard requests also return upstream 503 responses and must be investigated rather than hidden by health-only checks.

## What Changes

- Consolidate local testing onto the existing private `afterglow-local-services` project and its data volumes, exposing the conventional loopback frontend 3080/backend 8000 and sibling API ports.
- Remove the two old sets of owned application containers and obsolete Afterglow/sibling application images, then rebuild current repository/sibling sources and run migrations before starting services.
- Preserve all named volumes, private configuration and encryption keys; do not remove unrelated containers, images, BuildKit infrastructure or remote cloud resources.
- Diagnose and correct local OpenStack communication configuration using actual API/DNS evidence. Extend local smoke to include dashboard summary/quotas and the current Lumen administrator billing contract.
- Verify authenticated dashboard/service communication and the actual browser surface after deployment.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Local Compose lifecycle: one current-source stack on canonical ports, private datastores retained, obsolete alternate-port deployment retired.
- Local smoke: application contract and dashboard communication, not liveness alone.

## Impact

Changes are limited to local deployment runner/overlay, appropriate behavioral regression coverage, and architecture/deployment documentation. Local services will be temporarily unavailable during cleanup and rebuild. Production Lumen/OpenStack configuration and data are not modified. Real provider billing/completion validation still requires provider credentials; no synthetic credentials will be saved to existing providers.
