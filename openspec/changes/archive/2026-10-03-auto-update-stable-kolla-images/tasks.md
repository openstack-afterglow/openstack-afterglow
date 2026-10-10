## Implementation Tasks

- [x] Verify existing five-project `latest` publication and the Kolla 2025.2 pull/deployment contract.
  - Verified read-only GHCR manifest/index descriptors for all 11 application images across Afterglow, Drover, Waygate, Lumen, and Palimpsest via remote Docker SDK probe on `dms-controller1`.
- [x] Implement a read-only Docker distribution-descriptor resolver with consumer-visible regression coverage for moving aliases, explicit pins, ports, and registry failures.
  - Implemented `deploy/kolla/ansible/roles/afterglow/files/resolve_image_refs.py`.
  - Added 11 regression tests in `scripts/test_resolve_image_refs.py` (all passed).
- [x] Integrate per-service resolution before the custom roles; preserve serial batches, service tags, host limits, source mode, and disabled components.
  - Implemented `deploy/kolla/ansible/roles/afterglow/tasks/resolve_image_refs.yml` and wired into `site.yml` and 5 standalone playbooks (`afterglow.yml`, `drover.yml`, `waygate.yml`, `lumen.yml`, `palimpsest.yml`).
  - Actual native Kolla parser/globals/extra-vars and real resolver/task/helper passed 23 regressions, including serial channel movement, fresh invocation, limits, failures, disabled/source/pinned paths, homogeneous enablement and runtime-derived Lumen controller selection. Only the registry descriptor boundary and role side effects are synthetic in this suite.
- [x] Synchronize the moving image sample, JSON image refs, and release/version checks without changing sibling package promotion or CI publishing.
  - Updated moving tag sample and resolved JSON image refs. Source/default assertions are not behavioral proof and were removed.
  - Verified with `node scripts/check-version-sync.js` (aligned).
- [x] Exercise real registry resolution and moving-tag pull/container replacement behavior; run focused and related Kolla/version checks once after implementation.
  - Tested real remote `resolve_image_refs.py` on `dms-controller1` via python3 with valid sha256 output and zero errors.
  - `npm run test:kolla:contract`: 26 Node tests and 11 Python helper tests passed.
  - `npm run test:kolla:runtime`: 23 tests passed. JS and shell version checks aligned at 1.30.0.
  - Fresh canonical frontend images built and executed for arm64 and emulated amd64. Real isolated registry/native Kolla deploy0/pull0/reconfigure0 froze A across serial consumers, selected B next invocation, retained containers on pull and replaced both on reconfigure with HTTP200 health. Conflicting bare extra-var rc2 was an intentional fail-before-dispatch check. Runtime architectures were arm64/x64; owned fixture resources were removed.
- [x] Update deployment/architecture/changelog documentation with evidence and verification limits, then archive the completed implementation change.
  - Updated `docs/deployment.md`, `docs/en/deployment.md`, `CHANGELOG.md`, `ARCHITECTURE.md`.
  - Scoped isolated architecture staged/working snapshot: `95249e7be232f93502d738ee428d25f0d209b31950c70856acd38acbec555ec8` (2167 files). Real index and concurrent working review block remained unchanged.
  - Full `npm run test:gate` passed in the isolated owned-source snapshot: orchestration106, Kolla26+resolver11, backend3523, frontend1896+runner9, contracts141, real disposable datastore28, Ruff/format530. Installer13passed/15skipped. Native runtime23 was verified separately. Snapshot setup initially failed freshness because a dependency symlink was counted as source, then frontend optimization because generated SvelteKit configuration was absent; exact dependency exclusion and canonical `svelte-kit sync` corrected those setup prerequisites before the successful gate.

## Verification Evidence

1. **Remote Read-Only Descriptor Probes (`dms-controller1`)**:
   - `ghcr.io/openstack-afterglow/afterglow-api:latest`: `sha256:8cdff615b1d6f9e206f652ab3c26f880e6441eb889865a812de92f1703d5d80a`
   - `ghcr.io/openstack-afterglow/afterglow:latest`: `sha256:fa6525223a0138e943f43c5dab67a7886dfdd7fab8e1881b54bd03bc38d4ffa1`
   - `ghcr.io/openstack-afterglow/afterglow-worker:latest`: `sha256:5aac7ea5a8ccc1a522ae19e2eaed5ed542aee0e17dca1020b1759d3eaa069add`
   - `ghcr.io/openstack-afterglow/drover-api:latest`: `sha256:2400be784888595a520199cc5a0d8056d38f545010f1f08803e9f06272a48e87`
   - `ghcr.io/openstack-afterglow/drover-worker:latest`: `sha256:b50a30efdf1cf2278f4060cc273a1ccb52f0e8a648e0b7664e80180f89980ff1`
   - `ghcr.io/openstack-afterglow/waygate-api:latest`: `sha256:5f53a6090e87c8a041951851445017e9ba458d127e66e35d4750dc5d2334e54a`
   - `ghcr.io/openstack-afterglow/waygate-worker:latest`: `sha256:d83b02feb8f8ccde2ab813a0009dcaaa9621c4a3eb92f4bbbc8b4ef9b3242182`
   - `ghcr.io/openstack-afterglow/lumen-api:latest`: `sha256:d75a55761dc7efebd9591e2d135e7d53a0aa2e7bc6b1450299b2769ca174e3a1`
   - `ghcr.io/openstack-afterglow/lumen-worker:latest`: `sha256:d2d2fb988673a52842b3cfc435b0672f7a1a937dd008337e800ad82f8b2ce95a`
   - `ghcr.io/openstack-afterglow/palimpsest-hub-api:latest`: `sha256:63e3dfcc5a632c56c8204d4807cdf09cab60738a08a640f512f4df9f976d3b4a`
   - `ghcr.io/openstack-afterglow/palimpsest-hub-worker:latest`: `sha256:f0194baf9b6ddd3a9f1245bb45311340976c89d13a8179e26caea7beb3826fdb`
2. **Remote Resolver Execution**:
   - Executed `resolve_image_refs.py` on `dms-controller1` with JSON input specifying multiple moving refs and pinned refs; correctly resolved moving refs to manifest digests while preserving pinned refs. Exit code: 0.
3. **Automated Test Suites**:
   - `python3 scripts/test_resolve_image_refs.py`: 11 tests passed in 0.02s.
   - `npm run test:kolla:contract`: 26 Node tests + 11 Python tests passed.
   - `npm run test:kolla:runtime`: 23 tests passed.
   - JavaScript and shell version checks: all versions aligned (1.30.0).
4. **Architecture Review**:
   - Isolated staged/working source snapshot: `95249e7be232f93502d738ee428d25f0d209b31950c70856acd38acbec555ec8`, 2167 files. Concurrent native VM inputs excluded.
   - Working review block in `ARCHITECTURE.md` preserved for concurrent session.

## Verification Boundaries

- Verified read-only registry descriptor retrieval and digest resolution on `dms-controller1`.
- Production execution was limited to the existing approved immutable-image `kolla-ansible pull -i /etc/kolla/multinode --tags afterglow,waygate,drover,lumen,palimpsest`: exit0; all17hosts changed0/failed0/unreachable0. Before/after snapshots of 30 ecosystem and 9 loadbalancer containers were identical. Config render/LB reconcile were skipped; no restart, genconfig, new resolver adoption or datastore mutation occurred. Installed plugin remains049a0c22 and all11 operator application digest pins remain explicit.
- Fresh operator auth was not found in the probe environment; existing credential-file metadata is unchanged. Historical401 credentials were not retried. Authenticated production acceptance and genconfig/reconfigure remain blocked rather than inferred from pull success.

## Follow-up correction

The 23-test/95249e7b snapshot above is historical. A later native serial probe exposed cross-service fact reuse when the next service's first target was disabled or in source mode. [`2026-10-03-prevent-cross-service-image-selection`](../2026-10-03-prevent-cross-service-image-selection/tasks.md) records the service-owner fix, both failing-before/passing-after consumer regressions, final25-test native suite, final arm64/amd64 smoke and full gate for source digest `f022cc9f92ba8d11e06dff75012b9143bf4468b37315f419d988e7ed1a55a6dc`. The earlier archive alone is not final corrected-source acceptance. Production boundaries above are unchanged.

