## Implementation
- [x] Record approved root package and dependency isolation contract.
- [x] Unify Drover root package and migrate container/build consumers.
- [x] Unify Lumen root package and migrate container/build consumers.
- [x] Unify Waygate root package and migrate container/build consumers.
- [x] Unify Palimpsest root package without modifying the user feature branch.
- [ ] Migrate Afterglow operator, ownership checks, docs and cross-repository consumers.

## Verification
- [x] Build root wheels and verify role data and dependency isolation.
- [x] Exercise uv add, pip install, uv pip install and install/uninstall in disposable environments.
- [ ] Run sibling validation and Afterglow test:gate; finalize immutable Git references.
- [ ] Update source-backed architecture/docs and archive the completed change.

### Contract cleanup evidence

- `node scripts/kolla-contract.test.js`: 22 passed, 0 failed. Afterglow-only role assertions and aggregate dispatch remain; sibling-only source assertions were removed with their externalized roles. Installer fixtures use actual root-distribution metadata lookup and verify install/reinstall/uninstall preserves role, metadata, and operator-file bytes.
- Afterglow full gate passed before release-version synchronization: backend 2779, frontend 1382, API contract 124, functional 25, and backend lint. The release-version changes require a fresh gate before commit.
- Operator manifest and lock now resolve full immutable SHAs to drover 0.2.22, lumen 0.2.2, waygate 0.1.3, and palimpsest-local 0.1.4. Palimpsest's final pin is c82bc0f494077779452c21e98714bec8b51cafa2; Kolla-Ansible remains independently pinned. Real disposable installation verified package metadata and four shared-data roles; installer/uninstaller completed without removing sibling roles.
- Transferred behavioral image-ref regressions pass in their owning repositories. Waygate also has restored role-contract coverage (243 total tests passed); Palimpsest's three Kolla test files pass 23 tests. Those role-contract assertions inspect source text, not executed Ansible/HAProxy/Valkey behavior; end-to-end coverage remains a gap. Aggregate dispatch and inventory checks remain Afterglow-owned.
- Drover, Lumen, Waygate, and Palimpsest dev image-build workflows succeeded. Palimpsest's Test workflow remains red (macOS unit, KVM, and pure-contract jobs); fixing formatter drift alone did not establish a green release gate. Do not merge, tag, publish a release, or archive this change until the remaining gates are satisfied.
