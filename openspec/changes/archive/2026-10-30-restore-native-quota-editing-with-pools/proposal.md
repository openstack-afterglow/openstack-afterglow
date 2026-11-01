## Why

The stock-Nova flavor cutover preserved native CPU/RAM quota enforcement, but legacy writer/default and UI suppression still treats domain pools as a replacement for native quotas. A GPU-only pooled project can therefore be blocked by a quota that Afterglow no longer lets administrators fix.

## What Changes

- Restore native cores/RAM project quota writes, allocation budgets and future-project defaults regardless of pool metadata.
- Remove obsolete pool-specific writer rejections, value stripping, response coupling and quota editor props/readiness gates; pool caps remain separate Keystone policy edits.
- Preserve explicit authorization, domain allocation-budget checks, usage/reservation validation, durable operations, native readback and no automatic quota enlargement.
- Add GPU-only-pool quota-adjustment→eligibility and default-before-enable behavioral acceptance.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `domain-compute-pools`: Native project quota/default editing remains independently available for active and paused pools.

## Impact

Backend domain_quotas and quota tests; administrator/domain quota editors and callers/tests; relevant architecture/API/operator guidance. No schema/dependency/production deployment, automatic native quota changes, pool policy relaxation or shared private configuration changes.
