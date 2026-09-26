## Why

The Drover create dialog currently defaults to a tenant network named `Default` and allows selecting any private tenant network, although initial cluster creation is intended to attach directly to an external provider network. The UI should not silently override the server's administrator-controlled provider default.

## What Changes

- Remove the tenant/provider switch and the client-side `Default` network auto-selection.
- Offer only networks with `is_external` in the create dialog, with a blank choice that leaves the administrator's external provider default to the server.
- Describe initial direct provider attachment and explain that internal NICs can be attached later to cluster nodes.
- Keep `onCreate` and the existing create request conversion unchanged: an empty `network_id` is omitted from the outgoing request; a selected external network ID is sent.
- Update the k3s API documentation to reflect the create-dialog choice and the separate post-create interface flow.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- Drover cluster creation network selection is provider-only and optional in the UI; the admin external provider default remains a server decision.

## Impact

Afterglow changes the frontend create dialog and its architecture/API documentation. The companion Drover service change validates the external provider at admission, freezes the selected network into durable state, removes missing-network Nova fallback, and prevents secondary Ubuntu NIC IPv6 router advertisements from replacing provider routing. Existing primary-interface pinning remains authoritative. Integration covers canonical multi-architecture images, local container UI, authorized Kolla production rollout, and a temporary real two-node cluster with internal NIC hotplug and reboot; existing clusters are not migrated.
