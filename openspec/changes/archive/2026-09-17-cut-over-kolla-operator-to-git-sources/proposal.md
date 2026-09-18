## Why

Operators deploying Afterglow and its sibling services (Drover, Lumen, Waygate, Palimpsest) via Kolla-Ansible need the ability to install service-owned role packages directly from Git repositories using `[tool.uv.sources]` alongside `kolla-ansible`, rather than depending on hardcoded wheel binary URLs with sha256 hashes or fragile local in-tree role symlinks.

## What Changes

- Package `waygate-kolla` in `waygate` repository and `palimpsest-kolla` in `palimpsest` repository under `deploy/kolla/`.
- Update `deploy/kolla/operator/pyproject.toml` and `uv.lock` to consume `kolla-ansible`, `drover-kolla`, `lumen-kolla`, `waygate-kolla`, and `palimpsest-kolla` via `[tool.uv.sources]` Git dependencies using `subdirectory = "deploy/kolla"`.
- Update `deploy/kolla/install.sh` to validate all four package-installed roles (`drover-kolla==0.2.21`, `lumen-kolla==0.2.1`, `waygate-kolla==0.1.2`, `palimpsest-kolla==0.1.3`) and symlink only the core `afterglow` role from source.
- Update `deploy/kolla/uninstall.sh` to preserve all four package-installed roles and remove only the `afterglow` source role link.
- Update `deploy/kolla/README.md` and `deploy/kolla/operator/README.md` documentation.
- Update `scripts/kolla-contract.test.js` to assert the 4-package git-sourced contract.

## Capabilities

### New Capabilities

- Operators can install all four microservice Kolla role packages directly from reviewed Git tags or branches in `[tool.uv.sources]`.
- All four sibling microservices publish clean standalone Kolla role wheels from their own repositories.

### Modified Capabilities

- `install.sh` verifies four package-installed roles and symlinks only `afterglow`.
- `uninstall.sh` removes only the `afterglow` source link.

## Impact

- Zero impact on live containers or data.
- Operators configure `[tool.uv.sources]` in `/etc/kolla/pyproject.toml` and run `uv sync --frozen --inexact --no-install-project`.
