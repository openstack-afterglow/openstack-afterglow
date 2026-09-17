## Tasks

- [x] Package `waygate-kolla` in `waygate` repository under `deploy/kolla/` and verify assets test
- [x] Package `palimpsest-kolla` in `palimpsest` repository under `deploy/kolla/`, clean untracked user docs, and verify assets test
- [x] Align `drover-kolla` (v0.2.21) and `lumen-kolla` (v0.2.1) Git sources and role metadata
- [x] Update `deploy/kolla/operator/pyproject.toml` and `uv.lock` with all 4 packages using `[tool.uv.sources]`
- [x] Update `deploy/kolla/install.sh` and `uninstall.sh` to validate 4 package roles and preserve them on uninstall
- [x] Update `deploy/kolla/README.md` and `deploy/kolla/operator/README.md` documentation
- [x] Update `scripts/kolla-contract.test.js` and verify all 25 contract tests pass
- [x] Exercise `install.sh` and `uninstall.sh` against real git-installed environment
