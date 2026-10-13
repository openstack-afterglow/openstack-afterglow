## Why

The user asked for Stampede to be on by default after deployment, without users toggling it, so GPU Pods that request resources and select an accelerator can make Drover create a labeled worker automatically. Drover `v0.4.13` now enables omitted cluster requests and labels GPU workers with `accelerator=<type>`. The Afterglow create screens still start with both autoscaling switches off, and the cluster create caller omits the field when off; with Drover's new default that omission would silently enable Stampede.

## What Changes

- Start the Drover cluster create Stampede switch and the node group create autoscale switch on.
- Always send the cluster create choice as a `stampede_enabled` boolean so turning it off remains an explicit opt-out.
- Replace the default-visible Stampede warning (which referred to a server setting) with the actual behavior in ko/en/ja/zh-CN: min/max of Stampede node groups only, initial default workers are not scaled down.
- Document the default, the `accelerator` label and the GPU Pod `nodeSelector` + `nvidia.com/gpu` usage in `docs/api/k3s.md`; Drover remains the owner of autoscaling and labels.

## Capabilities

### Modified Capabilities

- Drover cluster and node group creation defaults in the dashboard.

## Impact

Frontend create modal, list controller and node group modal; four locale catalog entries; focused component/controller regressions; K3s API, architecture and changelog docs; patch version `1.30.15`. No backend endpoint, schema, migration, configuration or service topology change. Existing clusters keep their stored Stampede state.
