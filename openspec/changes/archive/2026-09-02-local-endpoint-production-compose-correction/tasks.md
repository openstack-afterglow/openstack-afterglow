## Implementation Tasks

- [x] Reconcile Kolla installer artifacts, restore valid `install.sh`, `site.yml`, `uninstall.sh`, and `scripts/kolla-contract.test.js`, and remove the untracked duplicate in-tree Drover role.
- [x] Align operator pin documentation with `deploy/kolla/operator/pyproject.toml` and `uv.lock` (`kolla-ansible` commit `34daacfbf2d5987f543787f57535b2bebe7dee19`).
- [x] Harden `docker-compose.prod.yml` default `SERVICE_*_INTERNAL_URL` values to empty (`${SERVICE_*_INTERNAL_URL:-}`) so production Compose does not violate Settings HTTPS validation.
- [x] Document direct Lumen endpoint overrides, topology-specific values, precedence (`env > alphabetically merged afterglow.*.conf > afterglow.conf > catalog/default`), Compose present-but-empty masking warning, production HTTPS rules, fail-closed catalog fallback, and BFF `service_proxy` scope.
- [x] Add focused contracts in `backend/tests/test_afterglow_conf_config.py` (production Compose empty defaults), `backend/tests/test_config_insecure_guard.py` (empty/HTTPS setting validation), and `backend/tests/contracts/test_service_proxy.py` (Lumen override skipping catalog vs empty override falling through to caller-scoped Keystone internal catalog).
- [x] Verify installer shell syntax, Kolla contracts, config-domain backend tests, and extracted-service backend contracts.
- [x] Archive the completed change.
