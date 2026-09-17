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

### Option B: Frozen Wheel Environment Installation

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
