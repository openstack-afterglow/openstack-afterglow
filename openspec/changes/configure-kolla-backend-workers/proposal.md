## Why

Kolla fixes the backend to a single Uvicorn process per host, preventing operators from tuning process concurrency.

## What Changes

- Add an operator-configurable positive integer worker count, defaulting to one.
- Validate it before configuration or activation and pass it to Uvicorn without changing proxy trust.
- Document capacity, startup and streaming tradeoffs; verify rendering and real multiprocess startup without touching production.

## Capabilities

### New Capabilities
- `kolla-backend-workers`: Configure and validate backend Uvicorn worker processes per Kolla host.

### Modified Capabilities

None.
