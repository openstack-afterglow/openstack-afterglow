## Why
A real-client refresh can be invalidated by a concurrent same-scope member mutation even if the server returns HTTP 200, causing a false group-list failure and unmounting the group cards.

## Change
Replace the invalidated read with one fresh scoped lookup, retaining existing authorization and failing visibly if that lookup also fails. Do not infer that this explains the separately observed production 401 or the console warning.
