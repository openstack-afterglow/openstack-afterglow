## Why
The Afterglow `/palimpsest/packages` page currently makes all content depend on native-package project context. Administrative identities receive the native policy's intentional 403 and cannot browse the separate legacy Hub artifacts or learn the supported local-client workflow. The owner requested actual Hub package/layer lookup, monitoring/search, and local-use onboarding for `https://palimpsest.dmslab.re.kr`.

## What changes
- Make an always-reachable workspace for legacy Hub images/layers, native packages/keys, and local Palimpsest usage; keep native denial local to the native panel.
- Use authenticated existing Hub BFF routes for bounded artifact search, exact digest/chain details, explicit downloads, and recent build/export status. Add the narrowly classified native Hub identity read `/hub/me`; no auth/role/schema bypass.
- Preserve native package owner/namespace/service-leaf validation, package-key isolation and one-time-secret lifecycle. Add truthful search of loaded native packages with explicit pagination scope.
- Add localized, copyable install/authenticate/inspect/download/local-web instructions. Real credentials stay in the original local process or existing approved helper, not page state/copy snippets.
- Verify current HTTP/backend/browser behavior, dependency/authority failure states, actor/token/filter races, responsive/theme/locales, and canonical affected image builds/local deployment. No production rollout or unrelated publication is inferred.

## Impact and constraints
Affected Afterglow frontend route/API/controller/locales, Hub BFF identity action classification/tests, architecture/design/domain/testing/changelog records. No new DB table, dependency, role, service credential, schema migration or VM/provider mutation. Preserve the large shared `dev` worktree and index; retain existing operational Hub 0.3.5 and native protected-administration policy. Package inventory and legacy shared/public artifact visibility remain distinct authority domains. Failed/partial observations are never labeled as verified zero/healthy.
