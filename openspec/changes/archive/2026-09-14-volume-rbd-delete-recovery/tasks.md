## Implementation Tasks

- [x] Add validated opt-in `[ceph]` settings, secret/config rendering, container mounts, Kolla variables, and `ceph-common` backend tooling.
- [x] Implement the argv-only `ceph_rbd` service with tri-state inspection, mapping restoration, sampled deletion verification, and strict stale-mapping cleanup.
- [x] Replace backend and frontend volume delete contracts with structured checks, backend inspection, and verification result fields.
- [x] Rewrite volume delete diagnosis/recovery to use the caller system-admin connection, fail closed on unknown dependencies, repair missing mappings, and verify backend/quota state.
- [x] Add the per-volume Redis recovery lock, updated cache invalidation, and complete audit details to the admin API.
- [x] Update the admin volume recovery controller and diagnostic panel for residue, unverified backend, checks, and confirmation copy.
- [x] Add focused backend/frontend tests and include the Ceph RBD test in the storage target.
- [x] Update deployment/admin/architecture documentation and regenerate affected class diagrams.
- [x] Run exact selectors, storage target, deterministic incident reproduction, backend image build, full gate, architecture stamp/staged guard, then archive the change.
