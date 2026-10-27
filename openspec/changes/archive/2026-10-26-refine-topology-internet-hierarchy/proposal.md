## Why
External provider switches currently visually stand in for the Internet and sit inside network zones; curved dense wiring obscures downstream hierarchy and multiple interface endpoints.

## What Changes
- Project/admin canvas projects each external network as distinct Internet cloud, provider switch and downstream network/instance nodes. The symbol denotes an external gateway, not verified reachability.
- Network boxes enclose downstream members only; upstream switch and Internet remain outside, while native domain ownership remains unchanged.
- Orthogonal cables with top ingress/bottom egress and distinct per-interface endpoints; retain real NIC identities, traffic, selection, pan/zoom/drag and native mutation protections.

## Scope
Frontend canvas only; no new backend/API/schema/config, deployment, resource mutation or operational connectivity assertion.

## Acceptance
External and shared-only networks differ; Internet/cloud never substitutes for switch. Multi-NIC instances retain each interface connection. Right-angle paths and hierarchy survive fit/drag; responsive dark/light and reduced motion verified on actual compiled UI, with focused regressions and evidence boundaries recorded.
