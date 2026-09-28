## Why

Waygate currently shows attachment UUIDs, updates peer traffic only on a slow reconcile cycle, and forces client settings to be repeated for every new peer. Operators need recognizable project network names, timely gateway-observed traffic, and per-server defaults without surprising existing peers. Afterglow is the authenticated BFF/UI; Waygate owns defaults, peer state, persistence, and reporting.

## What Changes

- Resolve attached network IDs to project-visible OpenStack names in Afterglow; retain IDs as fallback and keep project isolation.
- Run a single long-lived sequential gateway agent with a 15-second monotonic reconcile deadline and an independently scheduled, operator-configurable 1–60-second status deadline (1 second by default). Replace the obsolete reconcile timer/CLI instead of creating concurrent token writers. Report the observed cadence in agent status, preserve Redis's five-minute observational cache, and retain cloud-init/prebuilt asset parity.
- Add per-server client defaults (`dns`, `persistent_keepalive`) to Waygate create/read/PATCH and SDK. New clients inherit both when omitted; explicit `dns:null` suppresses DNS and `persistent_keepalive:0` disables it. Persist strict `inherit_dns`/`inherit_persistent_keepalive` flags; migrate existing clients to override mode without changing stored values. Server PATCH dynamically affects inherited client list/config/QR, but never overrides custom clients or installed apps. MTU remains per-client only. Export snapshots effective settings into explicit overrides when imported on another server.
- Expose server defaults and inheritance/override choices in the shared Afterglow workspace, with fixed accessible icon actions. A separate peer-only `createAutoRefresh` controller offers Off/1/2/5/10/15/30/60-second preferences, default 1 second, and serializes forced refreshes; metadata/network catalog remain on the existing 15-second cadence. Preserve bounded history and stale, reset, missing and project-switch fences.
- Update contracts, focused tests, architecture and operator documentation; verify local API/agent/UI/boot/WireGuard paths before any production rollout.

## Capabilities

### New Capabilities

- `waygate-live-peer-controls`: named attachments, one-second observational peer traffic and server-scoped client defaults.

### Modified Capabilities

- `waygate-vpn-client-dashboard`: preserve its report-derived traffic and per-client controls while adding server defaults and a faster reporting cadence.

## Impact

- Waygate adds an additive migration after 003 (server keepalive; two non-null client inheritance flags default false), a server PATCH API, and changes its existing reconcile service into the one long-lived run unit. Existing clients and stored keys remain unchanged. A mixed-version rollout must migrate schema before new API/worker images, then upgrade gateway assets/image before enabling live reporting; old agents remain compatible with the endpoint but still report slowly.
- Afterglow extends existing Waygate proxy and UI contracts without storing gateway secrets or traffic history. Local project names are cosmetic, not authority for attachment mutations; network ID remains the API identity.
- No production deploy is authorized by this change; live OpenStack and remote gateway proof require an available safe environment.
