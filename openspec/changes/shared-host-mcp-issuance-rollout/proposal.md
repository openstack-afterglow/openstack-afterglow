## Why

The operator requests the public MCP resource at https://cloud.dmslab.re.kr/mcp, on the dashboard origin instead of an unresolved dedicated host. Production logs at 2026-10-08T09:39:56Z and 09:40:56Z show personal key issuance failing because Keystone rejects expires_at with 'Timestamp not in expected format'. The shared checkout has 335 unmerged index entries; preserve it and integrate this completed MCP feature on latest origin/dev in an isolated local dev clone.

## What Changes

- Publish /mcp as the canonical configured resource; route its transport/OAuth paths and well-known discovery through canonical Compose HAProxy, Kolla plugin HAProxy, Helm and generated Kubernetes ingress without redirecting credentials or capturing unrelated paths.
- Preserve user/project-bound restricted application credentials and fix their Keystone expiry serialization from timezone-offset ISO to the upstream accepted UTC format. Add behavior regressions through the installed SDK serialization boundary.
- Ship the completed personal key configuration/check feature and four-language /docs/mcp guide, updating the requested shared-origin examples and operator configuration paths.
- Validate the integration with test:gate and actual HTTP/browser/runtime proof; commit and normally push dev, monitor exact-SHA CI, create immutable patch release only after CI, and deploy only verified published artifacts with recovery prerequisites.

## Scope and risks

No main merge/force-push, no broad cleanup, no shared credentials or privilege bypass, no unrelated unfinished changes. User authorizes commit/push and production deployment. Preserve current production versions, keys, datastore volumes and inventory. Any native qualification/recovery/CI/protected-review gate remains binding. Kolla routing needs role-source adoption as well as new application images. Report independent local, synthetic and production evidence; do not treat health as key issuance proof.
