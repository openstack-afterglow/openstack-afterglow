## Why

In `docker-compose.prod.yml`, `SERVICE_*_INTERNAL_URL` defaulted to `http://` URLs (e.g. `http://lumen-api:8012`). In production (`AFTERGLOW_ENV=production`), Settings validation requires non-empty explicit service internal URLs to use `https://`. This caused production Compose default configurations to fail startup validation. Furthermore, the local Lumen direct endpoint override rules, precedence order, Docker Compose empty-env masking behavior, and BFF proxy scope were insufficiently documented and lacked focused contract test coverage in `backend/tests/test_config_insecure_guard.py` and `backend/tests/contracts/test_service_proxy.py`.

## What Changes

1. **Harden Production Compose**: Update `docker-compose.prod.yml` so `SERVICE_*_INTERNAL_URL` defaults to empty (`${SERVICE_*_INTERNAL_URL:-}`), ensuring production deployments retain Keystone catalog lookup by default without triggering HTTPS validation errors.
2. **Reconcile Kolla Integration**: Fix working-tree Kolla installer artifacts, restore valid `install.sh` control flow, stock `site.yml` patching, `globals.d` links, and JavaScript test contracts in `scripts/kolla-contract.test.js`. Remove the obsolete untracked in-tree `drover` role while keeping `drover-kolla` package-installed.
3. **Operator Dependency Pin Alignment**: Align documentation statements in `deploy/kolla/operator/README.md` and `deploy/kolla/README.md` with `deploy/kolla/operator/pyproject.toml` and `uv.lock` for the `kolla-ansible` commit pin (`34daacfbf2d5987f543787f57535b2bebe7dee19`).
4. **Document Direct Endpoint Overrides**: Update `docs/openstack-service-catalog.md` with topology-specific direct Lumen internal URLs (`127.0.0.1`, `lumen-api`, `host.docker.internal`), precedence rules (`env > alphabetically merged afterglow.*.conf > afterglow.conf > catalog/default`), Docker Compose empty-env masking warning (requiring Compose users to supply overrides via `.env`/`--env-file`), HTTPS production requirement, fail-closed override behavior, and BFF `service_proxy` scope notice (noting other SDK calls may retain catalog discovery).
5. **Contract Test Coverage**: Add focused contracts in `backend/tests/test_afterglow_conf_config.py` (proving production Compose emits empty service override defaults), `backend/tests/test_config_insecure_guard.py` (proving empty production settings are accepted and valid HTTPS overrides succeed), and `backend/tests/contracts/test_service_proxy.py` (proving non-empty Lumen override skips catalog while empty override falls through to caller-scoped Keystone internal catalog).

## Capabilities

### New Capabilities
- Production Compose deployments initialize cleanly without self-conflicting HTTP override defaults.
- Operators can configure topology-specific direct Lumen endpoint overrides or rely on Keystone catalog discovery with clear precedence rules, Compose masking warnings, and BFF proxy scope documentation.

### Modified Capabilities
- `docker-compose.prod.yml` passes default `SERVICE_*_INTERNAL_URL` as empty to retain Keystone catalog discovery unless an HTTPS override is explicitly provided.

## Impact

No breaking changes to Keystone catalog discovery in Kolla or production. Standalone Compose in production no longer fails Settings validation when `SERVICE_*_INTERNAL_URL` environment variables are omitted.
