## Why

Afterglow centrally stores and symlinks Kolla roles for extracted services. That makes a Drover deployment change require an Afterglow source edit and leaves two independently drifting role implementations. Service-owned `*-kolla` wheels can install their role trees directly beside Kolla-Ansible under the active virtual environment's `share/kolla-ansible/ansible/roles` path, while Afterglow remains responsible only for aggregate lifecycle registration and shared operator integration.

## What Changes

- Consume the released `drover-kolla` wheel from the operator Kolla environment and remove Afterglow's central Drover role without a fallback.
- Discover Kolla's active data-files root from the running environment instead of assuming the Afterglow checkout contains every role.
- Replace static optional-service role plays with guarded dynamic `include_role` dispatch so disabled missing wheels are no-ops and enabled missing wheels fail closed with a named preflight error.
- Retain the one-time stock-site aggregate registration, inventory and `globals.d` links, shared HAProxy reconciliation, and operator-owned globals/secrets.
- Move Drover-specific role contracts to Drover; keep installed-wheel composition, aggregate dispatch, Kolla compatibility, and shared HAProxy contracts in Afterglow.
- Pin production role wheels through exact GitHub Release URLs and an immutable Kolla-Ansible source in the operator project/lock.

## Capabilities

### New Capabilities

- A Kolla virtual environment can install service-owned role wheels with `uv sync` and run them through standard Kolla lifecycle commands.
- Aggregate preflight distinguishes disabled uninstalled services from enabled missing role packages.

### Modified Capabilities

- Afterglow's Kolla installer registers composition assets but no longer copies or symlinks service-owned role source trees.
- Drover deployment role source and service-specific tests are owned exclusively by the Drover repository.

## Impact

The Drover cutover is intentionally fail-closed: `enable_drover=yes` requires the installed `drover-kolla` role and compatible Kolla-Ansible version. Existing live globals, secrets, inventory, generated configuration, containers, and data are untouched. Operators update `/etc/kolla/pyproject.toml` and `uv.lock`, run `uv sync --frozen`, rerun the idempotent aggregate registrar when Kolla changes, and then use normal `kolla-ansible pull/deploy/reconfigure/upgrade` commands.
