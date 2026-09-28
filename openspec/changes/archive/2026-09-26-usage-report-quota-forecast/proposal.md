## Why

`/dashboard/usage-report` currently reports every flavor as `unknown`, displays `0.0` vCPU-hours and labels a vCPU-only current-usage value as a seven-day linear forecast. Nova usage rows omit flavor and timestamp fields, dashboard readers use obsolete total names, block-storage quota is read from Nova, and the frontend's `90d` request silently falls back to 30 days.

## What Changes

- Preserve Nova simple-tenant-usage per-server flavor, launch/deletion timestamps and uptime; read the SDK total names in usage-stats and usage-report.
- Rebuild usage-report with 7/14/30/90-day ranges, flavor specs and derived vCPU/GPU hours, top instance usage, Nova compute, Cinder block-storage and Afterglow GPU quota rows with explicit availability flags.
- Compute seven-day allocation-series least-squares forecasts for vCPU, RAM and each GPU type. Show block storage as current use only because OpenStack does not expose historical volume allocation.
- Recompose the usage-report UI around KPIs, flavor usage, multi-resource forecast, instance usage and a project resource inventory from `/api/v1/dashboard/quotas`.
- Replace stale mocks with real service-shaped fixtures and add backend, frontend and runtime verification.

## Capabilities

### New Capabilities

- Usage report shows RAM and GPU hours, instance-level usage, and per-resource quota projections with estimated days to limit.
- Usage report displays network, block/file/object storage, database and compute-limit inventory already exposed by Afterglow quota adapters.

### Modified Capabilities

- Flavor usage reports real Nova flavor names, vCPU, RAM, GPU counts and vCPU-hours.
- `usage-stats.vcpu_hours` uses Nova's `total_vcpus_usage` total.
- `usage-report` replaces legacy `quota.vcpus_*` and `forecast.*_pct` fields with the resource-specific quota and forecast contract.

## Impact

FastAPI dashboard aggregation and Nova usage adapter, Svelte usage-report route, mock transport, frontend quota types, backend/frontend tests and dashboard documentation. No new OpenStack API call, database schema, configuration key or deployment topology. Actual project GPU data depends on local quota rows; no Cinder historical trend is inferred.
