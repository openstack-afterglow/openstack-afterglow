## Why

Lumen deployment roles have been externalized to the published immutable `lumen-kolla` v0.1.0 wheel release. Consuming the published wheel directly from the Kolla-Ansible operator virtual environment removes duplicate role definitions and completes Afterglow's clean cutover from embedded Lumen role sources.

## What Changes

- Add the immutable `lumen-kolla` v0.1.0 wheel dependency with URL `https://github.com/openstack-afterglow/lumen/releases/download/v0.1.0/lumen_kolla-0.1.0-py3-none-any.whl#sha256=0eda72dc95ad562717aa422d4465408280cc182149ae1c9b7a86ee3ce218da24` to Afterglow's operator `pyproject.toml` and update `uv.lock`.
- Remove the embedded tracked `deploy/kolla/ansible/roles/lumen` directory without source fallback or local path aliases.
- Refactor `install.sh` to validate both package-owned roles (`drover-kolla` and `lumen-kolla`) and distribution versions (`drover-kolla==0.2.17` and `lumen-kolla==0.1.0`), reject legacy/unexpected symlinks fail-closed, require Lumen role lifecycle/default/template files, and cease creating a `roles/lumen` symlink.
- Refactor `uninstall.sh` to remove only the remaining source-linked roles (`afterglow`, `waygate`, `palimpsest`) and leave package-installed roles untouched.
- Update documentation and DMSLab sample globals to reflect package-owned Lumen/Drover roles and pin exact linux/amd64 digests for `lumen-api` and `lumen-worker`.
- Update Afterglow contract tests to remove tests for embedded Lumen role internals while retaining and strengthening tests for externalized package roles, installer/uninstaller behavior, aggregate dispatch, and enabled-role verification.

## Capabilities

### New Capabilities

- The Kolla operator virtual environment installs both `drover-kolla` and `lumen-kolla` as immutable package-owned roles.
- `install.sh` fail-closes with explicit instructions if legacy Lumen or Drover role symlinks remain or if package roles are uninstalled or mismatched.

### Modified Capabilities

- The Afterglow Kolla installer manages source role symlinks only for `afterglow`, `waygate`, and `palimpsest`.
- Lumen role lifecycle task internals and files are tested and maintained exclusively in the Lumen repository.

## Impact

The Lumen wheel cutover is fail-closed: `enable_lumen=yes` requires the installed `lumen-kolla` package and role files. Existing live globals, secrets, inventory, generated configuration, containers, and data are untouched. Operators update `deploy/kolla/operator`, run `uv sync --frozen`, rerun `install.sh`, and use standard `kolla-ansible` commands.
