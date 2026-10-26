## Why

Palimpsest currently has separate native Hub layer/blob/bundle APIs, private project package APIs, and Afterglow-managed layer/profile/build/consume APIs. Existing dashboards expose legacy build authoring first, raw layer internals and loaded-page package filtering. They do not provide reliable source provenance, an administrator native catalog, complete name/tag search or an accessible named bundle use path.

The user confirmed broad public/shared plus project-private asset discovery and BOTH local and cloud use. Existing authority, private scopes, source data and build controls must be preserved. Native runtime support is not inferred from package download or a successful catalog read.

## What Changes

- Add read-only native Hub asset-bundle discovery and fresh-human-system-admin layer inventory/detail, based on current real source/visibility/ancestor and build/export evidence.
- Add optional native private-package query search without weakening namespace/action/key scopes; bind query to paging.
- Add Afterglow BFF and side-effect-free local managed catalog/provenance projection, published immutable environment discovery and caller-project cloud consumption using existing orchestration (never admin service-project compute defaults).
- Put inventory, recorded/unrecorded provenance and root-to-parent/direct-child relations first on the administrator route, retaining build studio and histories.
- Add a consumer asset-search workspace with independent public/shared Hub, project-private package and published cloud-environment results; select versions and use actual local bundle/OCI SDK paths or exact compatible cloud launch. No fake endpoints/launch-success, raw recipe/config/private credentials or per-layer knowledge required for ordinary reuse.
- Defer Docker Hub federated search; no synchronous external registry lookup blocks local results.

## Capabilities

### New Capabilities

- Policy-aware native asset catalog and administrator origin/ancestry inspection.
- Named asset-bundle discovery and supported local/cloud use from the dashboard.

### Modified Capabilities

- Native package inventory supports bounded name/tag search with query-bound pagination.
- Existing administrator library surface becomes inventory-first while retaining authoring and lifecycle workflows.

## Impact

Afterglow frontend/BFF and sibling native Hub source API/tests/docs are affected; no new SQL schema is planned. Reuse existing models, blobs, authorization and worker/run mechanisms. Operate-mode UI extends existing DESIGN.md shared primitives; all supported locales and mobile/tablet/desktop preserve task parity. No deployment, operational DB/bootstrap, native resource creation, account/role/mapping changes, commit/push/tag or unrelated dirty-work replacement is authorized. Tests use isolated public-source snapshots and disposable data with real API/SQL where possible and explicit synthetic identity/cloud boundaries.
