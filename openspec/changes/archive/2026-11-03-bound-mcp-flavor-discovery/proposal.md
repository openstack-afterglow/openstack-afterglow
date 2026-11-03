## Why

Post-implementation review of Nova2025.2 controller/object source confirms is_public=None means global flavor enumeration for native admins, while the default is_public=True includes public and the token project's private ACL entries. MCP must use the native target-visible catalog, not pay per-row ACL/spec reads across unrelated projects. CPU/RAM filters currently run after expensive reads.

## What Changes

Explicitly pass is_public=True because installed SDK3.3 injects None when the argument is omitted; Nova's True filter includes public plus target-project private ACL entries. Retain exact target ACL defense for returned private flavors with current native admin, and apply cheap validated CPU/RAM matching before ACL/extra-spec reads. Preserve raw-row page bounds and next markers. Do not modify operator/global Nova catalog helpers.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
Bounded MCP flavor discovery uses native project-visible default and does not issue ACL/spec reads for shape-filtered rows.

## Impact

catalog adapter and native HTTP regression only, existing API/architecture/testing docs. No registry name/schema/version, authority, migration, dependency, deployment or live resource changes. Run failing-before/passing-after installed SDK HTTP regression, existing scope tests and exact owned-overlay whole gate; preserve the separately observed shared-tree42failures and unrelated WIP.
