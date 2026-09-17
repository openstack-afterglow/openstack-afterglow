# Afterglow Kolla Operator Environment

This directory defines the operator virtual environment for Afterglow Kolla-Ansible service deployment.

## Overview

The operator environment manages the dependencies required for running `kolla-ansible` and service role wheels (such as `drover-kolla` and `lumen-kolla`).

- **Kolla-Ansible**: pinned to git commit `34daacfbf2d5987f543787f57535b2bebe7dee19` (21.2.0).
- **Drover Kolla Role**: pinned to git release tag `v0.2.21` (`drover-kolla`).
- **Lumen Kolla Role**: pinned to git release tag `v0.2.1` (`lumen-kolla`).
- **Waygate Kolla Role**: pinned to git release tag `v0.1.2` (`waygate-kolla`).
- **Palimpsest Kolla Role**: pinned to git release tag `v0.1.3` (`palimpsest-kolla`).
## Installation Options

### Option A: Git Source Dependencies via `[tool.uv.sources]`

To install and build Kolla packages directly from the official Git repositories (e.g., specific Git revisions or tags):

```toml
[project]
name = "afterglow-kolla-operator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "kolla-ansible",
    "drover-kolla",
    "lumen-kolla",
    "waygate-kolla",
    "palimpsest-kolla",
]

[tool.uv.sources]
kolla-ansible = { git = "https://opendev.org/openstack/kolla-ansible", rev = "34daacfbf2d5987f543787f57535b2bebe7dee19" }
drover-kolla = { git = "https://github.com/openstack-afterglow/drover", rev = "v0.2.21", subdirectory = "deploy/kolla" }
lumen-kolla = { git = "https://github.com/openstack-afterglow/lumen", rev = "v0.2.1", subdirectory = "deploy/kolla" }
waygate-kolla = { git = "https://github.com/openstack-afterglow/waygate", rev = "v0.1.2", subdirectory = "deploy/kolla" }
palimpsest-kolla = { git = "https://github.com/openstack-afterglow/palimpsest", rev = "v0.1.3", subdirectory = "deploy/kolla" }
```

> **Note on Monorepo Subdirectories:** Because `drover`, `lumen`, `waygate`, and `palimpsest` maintain their core service runtime packages at the repository root and package their Kolla roles under `deploy/kolla`, `subdirectory = "deploy/kolla"` is required by `uv` to target the role wheel build correctly.

### Option B: Adding & Managing Dependencies via CLI (`uv add`)

To add or update Kolla dependencies using `uv add`, supply the Git URL along with the PEP 508 `#subdirectory=deploy/kolla` fragment:

```bash
uv add "kolla-ansible @ git+https://opendev.org/openstack/kolla-ansible.git@34daacfbf2d5987f543787f57535b2bebe7dee19"
uv add "drover-kolla @ git+https://github.com/openstack-afterglow/drover.git@v0.2.21#subdirectory=deploy/kolla"
uv add "lumen-kolla @ git+https://github.com/openstack-afterglow/lumen.git@v0.2.1#subdirectory=deploy/kolla"
uv add "waygate-kolla @ git+https://github.com/openstack-afterglow/waygate.git@v0.1.2#subdirectory=deploy/kolla"
uv add "palimpsest-kolla @ git+https://github.com/openstack-afterglow/palimpsest.git@v0.1.3#subdirectory=deploy/kolla"
```

`uv add` automatically parses the URL, records the dependency in `dependencies`, and populates the `[tool.uv.sources]` table with the matching `rev` and `subdirectory`.

### Option C: Direct Installation via `pip install` or `uv pip install`

If installing directly into the Kolla virtual environment without using `uv sync` / `pyproject.toml`:

**Using standard `pip`:**
```bash
/etc/kolla/.venv/bin/pip install \
  "git+https://opendev.org/openstack/kolla-ansible.git@34daacfbf2d5987f543787f57535b2bebe7dee19" \
  "git+https://github.com/openstack-afterglow/drover.git@v0.2.21#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/lumen.git@v0.2.1#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/waygate.git@v0.1.2#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/palimpsest.git@v0.1.3#subdirectory=deploy/kolla"
```

**Using `uv pip install`:**
```bash
uv pip install --python /etc/kolla/.venv \
  "git+https://opendev.org/openstack/kolla-ansible.git@34daacfbf2d5987f543787f57535b2bebe7dee19" \
  "git+https://github.com/openstack-afterglow/drover.git@v0.2.21#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/lumen.git@v0.2.1#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/waygate.git@v0.1.2#subdirectory=deploy/kolla" \
  "git+https://github.com/openstack-afterglow/palimpsest.git@v0.1.3#subdirectory=deploy/kolla"
```

### Option D: Frozen Wheel Environment Installation (Recommended for Production)
From this directory, explicitly target the environment used by Kolla:

```bash
UV_PROJECT_ENVIRONMENT=/etc/kolla/.venv uv sync --frozen --inexact --no-install-project
source /etc/kolla/.venv/bin/activate
```

`--inexact` preserves unrelated operator packages. This manifest supplies pinned
runtime dependencies; it has no application package to install. Review the
pinned Kolla version before updating an existing operator environment.

After preparing inventory and plugin globals/secrets, run `../install.sh` once.
The installer adds the stock-site import and checks the installed role versions.
See [the complete deployment guide](../README.md) for configuration prerequisites
and migration of conflicting legacy files.

Subsequent deployment from `/etc/kolla` is:

```bash
kolla-ansible deploy -i multinode
```

Custom service and HAProxy plays own `become: true`; the SSH account must already
have noninteractive sudo. Lumen is executed from its installed wheel, not a
copied role or a separate manual playbook.

For isolated development verification instead of a live operator environment:

```bash
uv sync --frozen --inexact --no-install-project
cd ../../..
npm run test:kolla:runtime
```

The runtime contract uses this directory's `.venv` and never performs real
service deployment.

## Eliminating `subdirectory = "deploy/kolla"` (Design & Future Registry Strategy)

Currently, the Git source definition requires `subdirectory = "deploy/kolla"`:

```toml
drover-kolla = { git = "https://github.com/openstack-afterglow/drover", rev = "v0.2.21", subdirectory = "deploy/kolla" }
```

### Why is it needed now?
Each sibling repository (`drover`, `lumen`, `waygate`, `palimpsest`) is structured as a monorepo:
- The **repository root** defines the microservice application (`drover`, `lumen`, etc.) for runtime container builds.
- The **`deploy/kolla`** directory defines the Ansible role packaging (`drover-kolla`, `lumen-kolla`, etc.) for operator installation.

If `subdirectory` is omitted from a Git dependency, package tools (`pip`, `uv`) inspect the repository root `pyproject.toml`, discover that the package name is `drover` instead of `drover-kolla`, and fail with a metadata mismatch error (`Package metadata name 'drover' does not match given name 'drover-kolla'`).

### Approaches to Eliminate `subdirectory`

1. **Python Package Index (PEP 503 / PyPI) or GitHub Releases Wheels:**
   Publish the built `.whl` files to **PyPI**, an internal PEP 503 package index (such as devpi or Cloudsmith), or attach `.whl` assets directly to GitHub Releases.
   *(Note: GitHub Packages / GHCR hosts OCI/Docker container images and does not implement a PEP 503 Python package index for `pip`).*
   When wheels are published to a PEP 503 index:
   ```toml
   dependencies = [
       "kolla-ansible==21.2.0",
       "drover-kolla==0.2.21",
       "lumen-kolla==0.2.1",
       "waygate-kolla==0.1.2",
       "palimpsest-kolla==0.1.3",
   ]
   ```
   The `[tool.uv.sources]` table and all `subdirectory` specifications are completely eliminated.

2. **Root Python Package + Subdirectory Docker Strategy:**
   Structure each microservice repository so that the **root `pyproject.toml`** defines the primary Python package and bundles the Kolla Ansible roles via `shared-data` / `data_files`, while container assets (`Dockerfile`, compose files) reside under a `docker/` subdirectory:
   - Microservice runtime dependencies are declared under `[project.optional-dependencies] service = [...]` so installing the root package in the Kolla operator venv (`pip install git+...`) installs only the lightweight role files without pulling in heavy server dependencies (FastAPI, PyTorch, database drivers).
   - Container builds invoke `docker build -f docker/Dockerfile .` and run `pip install .[service]`.
   - Result: Root Git URLs (`git+https://...`) install directly without any `subdirectory` parameter.

3. **Single-line PEP 508 URL (Inline Alternative):**
   Instead of separating `[tool.uv.sources]`, the subdirectory can be passed inline in the PEP 508 URL string:
   ```bash
   uv add "drover-kolla @ git+https://github.com/openstack-afterglow/drover.git@v0.2.21#subdirectory=deploy/kolla"
   ```
   This maintains standard PEP 508 compatibility without manual table editing.

4. **Dedicated Repositories for Kolla Roles:**
   Splitting roles into dedicated repositories (`openstack-afterglow/drover-kolla`) places `pyproject.toml` at the root, removing the need for a subdirectory, at the expense of managing additional repositories.
