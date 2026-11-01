## Why
An unconfigured optional default produces HTTP404 on each lookup and appears as a network failure in DevTools.

## What Changes
- Return HTTP200 with network_id:null for confirmed database absence.
- Remove obsolete wizard404 special handling; keep actual failures as errors.

## Capabilities
### New Capabilities
- `optional-default-network`: normal absence response.
### Modified Capabilities
None.

## Impact
Network endpoint, wizard caller, regression tests and API docs; no DB/schema/native writes or deployment.
