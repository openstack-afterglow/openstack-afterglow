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
- Immutable root-commit pins recorded in `deploy/kolla/operator/pyproject.toml` (drover 3d21f785, lumen 3ab1f2ff, waygate 9933deb9, palimpsest 0f89d5d4; kolla-ansible 34daacf unchanged) and `operator/uv.lock` regenerated from them (verified: drover 0.2.22, lumen 0.2.2, waygate 0.1.3, palimpsest-local 0.1.4; `uv sync --dry-run` resolves all five Git sources). README placeholder warnings replaced with the resolved pinning contract.
- This focused gate does not complete, operator lock regeneration, the full gate, or container validation. Keep the parent change open until those checks complete.
