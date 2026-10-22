## Why
The explicit administrator provider executor correctly separates logical Personal workspace from native authenticated execution project. Manila still builds its REST URL from the logical project. A catalog endpoint already ending /v2/<executor-project> therefore becomes /v2/<executor-project>/<personal-project>/shares, which is not a Manila API route. Existing service tests replace get_client and cannot detect that boundary.

## What Changes
- Build Manila URL scope from _afterglow_authenticated_project_id or the SDK's current native project when metadata is absent; never from logical workspace metadata.
- Preserve the separate logical project as the quota target and keep provider token, workspace and caller authority unchanged.
- Add actual loopback HTTP regressions through the real installed SDK catalog and unmocked get_client for both project-scoped and version-root endpoints, SDK scope fallback and missing native scope.
- Exercise the production administrator Manila route with distinct logical/native IDs, then run storage and canonical gates, architecture checks, docs and corrected receipts.

## Impact
Only Manila transport construction, behavior regressions and existing architecture/API/testing documentation. No runtime/config/schema/IAM/credential/quota/resource changes, deployment or commit/push. Reuse public-config snapshot and owned native fixtures; retain executed proof sources and raw failures.
