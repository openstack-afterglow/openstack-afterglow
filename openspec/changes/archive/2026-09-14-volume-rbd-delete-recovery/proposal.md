## Why

The admin volume delete recovery path currently re-scopes the system administrator connection into the owning project, treats dependency lookup failures as absence, and proceeds through reset/delete/force-delete. A 401 can therefore be misclassified as a safe recovery, while a missing Ceph `rbd_id.<name>` mapping can leave Cinder and Ceph inconsistent and make a force-delete orphan backend objects.

## What Changes

- Keep Cinder cross-project diagnosis and recovery on the caller's system-admin connection.
- Make every dependency and backend lookup tri-state (`present`, `absent`, `unknown`) and fail closed on authentication, authorization, network, parsing, permission, or configuration uncertainty.
- Add opt-in `[ceph]` configuration, deployment mounts, Ceph CLI image support, and validated backend-to-pool routing.
- Add an argv-only Ceph RBD inspection/recovery service that can restore a missing name mapping, verify backend deletion, and remove only an exactly matched stale mapping after strict preconditions.
- Extend volume delete diagnostics and recovery results with structured checks, backend classification, backend verification, and quota verification.
- Serialize recovery per volume with a fail-closed Redis lock, update cache invalidation/audit output, and expose the detailed state in the admin volume UI.
- Add focused backend/frontend regression coverage for the reported failure modes and deterministic fake-runner recovery scenario.

## Capabilities

### New Capabilities

- Opt-in Ceph RBD inspection and narrowly scoped `rbd_id` mapping repair for administrator volume-delete recovery.
- Post-delete backend residue detection, stale mapping cleanup, and quota delta verification.
- Structured three-state dependency/backend checks in the administrator diagnostics API and UI.

### Modified Capabilities

- Administrator volume delete recovery uses the caller system-admin connection, performs one force-delete attempt unless the exact detached-reset fallback applies, and never treats failed lookups as absence.
- Deployment configuration supports mounting a Ceph config and restricted keyring into backend containers without enabling the feature by default.

## Impact

Affected areas: backend settings and deployment rendering, Docker/Kubernetes/Helm/Kolla backend images, Cinder adapters, volume recovery models/service/API, admin volume frontend types/controller/component, storage tests, deployment/API documentation, and architecture metadata. Existing Cinder-only deployments remain functional with explicit `backend_unverified` results because Ceph inspection is disabled until both configured paths plus FSID and pool mappings are supplied.
