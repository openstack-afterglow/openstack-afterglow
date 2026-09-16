## Implementation Tasks

- [x] Pin `lumen-kolla` v0.1.0 wheel URL and SHA256 in `deploy/kolla/operator/pyproject.toml` and update `uv.lock`.
- [x] Delete the embedded tracked `deploy/kolla/ansible/roles/lumen` tree completely without fallback.
- [x] Refactor `install.sh` to validate package-installed `lumen-kolla` and `drover-kolla` roles, reject legacy/unexpected symlinks, and remove Lumen source symlink creation.
- [x] Refactor `uninstall.sh` to remove only remaining source role symlinks and preserve package-installed roles.
- [x] Update Kolla/operator documentation and DMSLab sample globals with exact image digests and cutover steps.
- [x] Update Afterglow contract tests for embedded Lumen source absence, package role verification, and hermetic integration.
- [x] Verify operator lock/sync, real package-owned role installation, installer shell syntax, Kolla contracts, published wheel availability, and independent review.
- [x] Archive the completed change.
