## Implementation
- [x] Record approved root package and dependency isolation contract.
- [ ] Unify Drover root package and migrate container/build consumers.
- [ ] Unify Lumen root package and migrate container/build consumers.
- [ ] Unify Waygate root package and migrate container/build consumers.
- [ ] Unify Palimpsest root package without modifying the user feature branch.
- [ ] Migrate Afterglow operator, ownership checks, docs and cross-repository consumers.

## Verification
- [ ] Build root wheels and verify role data and dependency isolation.
- [ ] Exercise uv add, pip install, uv pip install and install/uninstall in disposable environments.
- [ ] Run sibling validation and Afterglow test:gate; finalize immutable Git references.
- [ ] Update source-backed architecture/docs and archive the completed change.

### Contract cleanup evidence

- `node scripts/kolla-contract.test.js`: 22 passed, 0 failed. Afterglow-only role assertions and aggregate dispatch remain; sibling-only source assertions were removed with their externalized roles. Installer fixtures use actual root-distribution metadata lookup and verify install/reinstall/uninstall preserves role, metadata, and operator-file bytes.
- Afterglow dev full gate passed after removing the two externalized validator regression tests (ownership transferred to sibling repos): backend 2779 passed, frontend 241 files/1382 tests, contract 124, functional 25, `ruff` clean, `docs:check` pass. Operator manifest/lock still reference legacy tags; do not sync an operator environment from it until immutable SHA pins land.
- This focused gate does not complete immutable Git pinning, operator lock regeneration, the full gate, or container validation. Keep the parent change open until those checks complete.
