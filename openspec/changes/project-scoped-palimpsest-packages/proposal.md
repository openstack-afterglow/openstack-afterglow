## Why

The requested `palimpsest push cloud.dmslab.re.kr/openstack-afterglow/test:v1` workflow needs project membership, narrowly scoped non-admin upload keys, validated complete packages and a visible selected-project inventory. Current top-level Palimpsest push is a Docker CLI wrapper; extracted Hub `/v1` stores digested artifacts/cache, not named package/tag versions. `/admin/libraries` in the supplied screenshot lists Afterglow's own layer/build records; it cannot show a private CLI-pushed Hub package by refreshing those endpoints.

Palimpsest's current token-method validation can re-scope a token to the user's default project. A previous proof wrote four observed private cache rows into the admin project plus two superseded uploads with unrecorded ownership. This is not an acceptable publication path; admin tokens/service credentials/default-project inference cannot be the upload authority.

## What Changes

- Define `palimpsest.project-packages.v1` in the separate Palimpsest repository's `docs/project-package-registry.md`: authority/project-namespace/package/tag references, namespace-to-immutable-project-UUID binding, non-admin opaque keys, complete OCI image/runtime-bundle publication, immutable digests and atomic mutable tags.
- Keep Hub native `/v1` and genuine Docker `/v2` transports explicit; reference syntax is shared, protocols are not. A BuildKit cache upload is not a pushed package or running/sealed VM artifact.
- Make Hub the sole package/tag/key data authority. Afterglow adds authenticated member read/control endpoints and an allowlisted native package-key gateway; do not mirror package metadata into LayerArtifact or reuse Notion/SSH/MCP credentials.
- Add `/palimpsest/packages` with selected-project namespace, Hub package/tag/version inventory, scopes/expiry/revocation and once-only key reveal. Link from the screenshot's `/admin/libraries` and normal Palimpsest navigation. Retain administrator-only server build/SSH controls; ordinary members need no administrator mode for package operations.
- Fence stale project-switch requests and secret state. JWT/current-project UUID and Hub response UUID must agree. Never inject configured admin/service credentials when package-key authentication fails.
- Implement only after contract review: identity correction, Hub migrations/keys/validator/publication, native client, then Afterglow BFF/UI, isolated local proof and separately authorized production rollout.

## Capabilities

### New Capabilities

- Membership-bound native project package registry and narrowly scoped upload keys.
- Private project package inventory, version details, verified downloads and key lifecycle in Afterglow.

### Modified Capabilities

- Original-token validation and fail-closed project consistency in Hub/Afterglow boundaries.
- Protocol-aware native build/push/pull/login and explicitly scoped mandatory cache transfer.
- Palimpsest navigation and read/control APIs without weakening existing privileged builder or legacy sealed-layer visibility rules.

## Impact

Source baselines inspected: Afterglow `dev` `0f59e0ee8e7cea6d36db33f1d4e2380fe4fac2b7`; Palimpsest `dev` `dc8a164fd7ad4243f0e01bf7e48e613608674ccb`, both dirty. Existing work is preserved. This change currently records a specification/implementation plan only: no runtime source/schema/config changes, new key/token issuance, uploads, production calls, deployment, commits or resource cleanup.

Afterglow touch points: `backend/app/api/palimpsest/`, `backend/app/services/service_proxy.py`, `backend/app/main.py` router/audit mounts, existing JWT/project-rescope dependencies, `frontend/src/lib/api/`, auth/project request fencing, new member route and the existing `/admin/libraries` cross-link/navigation; relevant backend/frontend tests and API/design/architecture docs. Public native path `/api/v1/palimpsest/hub/projects/...` maps to upstream `/v1/projects/...`, without a duplicate `/v1`.

No automatic Glance/Manila/Cinder import, VM creation, existing admin-project cache-row migration/deletion, new authentication secrets, global credential sweep or CI/runner/GPU changes. API and runtime qualification remain distinct. No archive/completion claim until implementation and observable acceptance criteria pass.
