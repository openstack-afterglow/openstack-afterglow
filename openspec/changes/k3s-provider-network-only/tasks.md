## Implementation Tasks

- [x] Replace create-dialog tenant/provider switching and `Default` auto-selection with an optional external-provider-only Field/SelectInput; explain direct attachment and later internal NICs. Clear a selected provider ID if a new network catalog no longer contains it.
- [x] Confirm existing caller request conversion preserves omitted `network_id` for blank and sends selected external ID, and update only meaningful existing tests that pin obsolete network choices.
- [x] Update `docs/api/k3s.md` with provider-only create UI and post-create internal NIC workflow.
- [x] Smoke the actual local container UI with the real private/external catalog; capture blank and selected create request bodies without creating resources. Verify containment and reachable submission at 390x720, 768x900, 1024x768, and 1440x900. Bound the modal height and allow internal scrolling for short viewports. Afterglow test:gate and frontend amd64/arm64 builds pass.
- [ ] Publish and deploy the provider-only frontend to the authorized Kolla production target, verify authenticated UI, and archive the change after integration.
- [ ] Verify the deployed Drover admission and real two-node provider cluster lifecycle: downloaded kubeconfig, internal NIC hotplug, reboot, unchanged provider pin and Kubernetes readiness, then exact resource cleanup.
