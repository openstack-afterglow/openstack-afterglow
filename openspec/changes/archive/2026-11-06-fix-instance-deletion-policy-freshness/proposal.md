## Why
Consumer attachment reads ignored refresh and could suppress typed deletion confirmation with stale cache.
## What Changes
Honor CacheMode and preserve Union/retained storage notices in consumer lists.
## Capabilities
### New Capabilities
- `instance-deletion-policy-freshness`: origin-backed deletion preflight.
### Modified Capabilities
None.
## Impact
Existing volume endpoint and consumer list; no schema or native policy change.
