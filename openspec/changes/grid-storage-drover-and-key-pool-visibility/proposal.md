## Why

Owner requests (2026-11-20): dashboard usage charts show a "chart data" disclosure and a "telemetry collection" disclosure nobody needs; the instance network grid draws security groups as one instance-wide zone that looks attached to the network instead of the interface (ports); attached volumes and file shares are invisible; Drover cluster detail has no grid view of node connectivity, open ports, CSI storage and traffic; and the provider API-key pool cannot tell keys apart (no registration date, no monthly spend, ambiguous `default #14` / `default (#2)` labels).

## What Changes

- **Dashboard trends:** remove the chart-data table disclosure and the telemetry-collection disclosure; partial coverage and refresh failure stay as short inline text.
- **Instance grid:** security groups are per-port chips on the slab beside each port; remote sources expand only for the selected group; attached Cinder volumes and Manila associations (`GET /instances/{id}/storage-attachments`) hang behind the instance.
- **Drover grid:** grid/list view in the cluster main tab: shared network slabs, per-port groups, Service ports, node volumes (boot/CSI inferred), shares, measured RX/TX badges; PVC/PV bindings stay unknown (Drover has no endpoint).
- **Key pool:** typed account vs API-key IDs, `created_at`, per-key UTC month ledger usage, last use, exact-decimal account/provider totals. Needs Lumen's additive `created_at` and `/usage` month fields; absent fields render as unknown.

## Non-goals

- No Drover API change; no PVC/PV discovery. No measured traffic on edges. No provider invoice figures.

## Dependencies

- Lumen release carrying `created_at` and month usage fields (feat/key-pool-month-usage) for the key-pool dates and spend; older Lumen shows unknown.
