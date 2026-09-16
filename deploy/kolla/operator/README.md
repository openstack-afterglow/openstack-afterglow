# Afterglow Kolla Operator Environment

This directory defines the operator virtual environment for Afterglow Kolla-Ansible service deployment.

## Overview

The operator environment manages the dependencies required for running `kolla-ansible` and service role wheels (such as `drover-kolla` and `lumen-kolla`).

- **Kolla-Ansible**: pinned to git commit `34daacfbf2d5987f543787f57535b2bebe7dee19` (21.2.0).
- **Drover Kolla Role**: pinned to wheel release `drover_kolla-0.2.19-py3-none-any.whl` (v0.2.19).
- **Lumen Kolla Role**: pinned to wheel release `lumen_kolla-0.2.0-py3-none-any.whl` (v0.2.0).
## Installation

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
